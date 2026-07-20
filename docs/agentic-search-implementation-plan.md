# Agentic Search — Phased Implementation Plan (for Sonnet 5 execution)

**Date:** 2026-07-20 · **REV 2** (platform shape — design §2.5 added same day; this plan
updated to match: tensor A/B in P1, new Phase 2.5 ETL plane, P4 figures persist to dataset)
**Design:** `docs/agentic-search-design.md` (read it first, every phase — §2.5 is the core idea)
**Format:** one phase per fresh Cowork thread, TRAUM-style. Every phase ends with the
standard close: tests green → CHANGELOG.md → CURRENT-STATE.md → commit → debrief.
**Standing rules that apply to every phase (non-negotiable):**
- KB-write/ES-write verification rule (kb/session-learnings.md 2026-07-20): verify every
  write via independent ground truth (`_version` bump / real-time GET / content hash),
  never trust a script's own success tally.
- Gateway code changes require restart + fresh session to take effect (per-session stdio
  instances keep old code in memory).
- SearXNG config deploys: edit `docker/searxng_data/settings.yml` in repo, then
  `sudo_delegation_block` for `sudo install … && docker compose restart searxng`
  (root-owned live copy + searxng-config-guard — see 2026-07-20 debrief).
- No new model on any GPU without measuring VRAM headroom first (`nvidia-smi` via
  ssh_run to node3090); no embed-path latency changes without re-measuring against the
  8s timeout (`_EMBED_CHAR_LIMIT` lesson).
- All new valves: names ending in `_API_KEY`/`_TOKEN`/`_SECRET` for auto log-redaction.

---

## Phase 0 — SearXNG fine-tune + telemetry + gold set (XS, do first)

**Objective:** make the L2 engine layer trustworthy and measurable before building on it.

**Steps:**
1. `docker/searxng_data/settings.yml` edits (repo copy, then delegated deploy):
   - Confirm `formats: [html, json]` enabled (json is the tool path).
   - Add `time_range` support verification: `curl 'localhost:8088/search?q=test&time_range=month&format=json'` — if engines ignore it, note which.
   - Engine review: current whitelist minus bing (disabled 2026-07-20). Add/verify:
     `duckduckgo`, `brave`, `startpage`, `wikipedia`, `github`, `stackexchange` family,
     `arxiv` (science category), and the existing `!nl` neural engine. Per-engine
     `timeout: 4.0` and `suspended_times: {SearxEngineAccessDenied: 86400}` stanzas.
   - Enable `images` category with at least 2 engines (duckduckgo images, bing images
     stays OFF) — required by Phase 4's visual path.
   - Keep `keep_only` whitelist discipline — no engine additions outside this file.
2. Fix the searxng-logger metrics-token mismatch (open item, 2026-07-20 debrief:
   logger sends no auth; SearxNG metrics endpoint expects `SEARXNG_METRICS_PASSWORD`
   from vault). Verify with a live scrape returning 200.
3. Harvest the eval gold set: mine episode journals for real `search_web` calls +
   search_kb misses → `eval/agentic-search-gold-v1.jsonl` (~40 rows:
   `{question, acceptable_domains[], key_facts[], freshness_class, visual_likely}`).
   Include the KV-cache-VRAM-chart question as the first `visual_likely: true` row.
   sha256-freeze into `eval/SHA256SUMS` (DATA-3 convention).
4. Baseline run: current `search_web()` against the gold set; record junk-leak rate,
   citation-supported rate, wall-clock into `eval/agentic-search-baseline.md`.

**Acceptance gate:** json+time_range verified live; metrics scrape 200; gold set frozen;
baseline numbers recorded. **Rollback:** settings.yml is git-tracked — revert + redeploy.

---

## Phase 1 — Rerank layer + relevance floor + structured results (S, highest leverage)

**Objective:** no unranked engine output ever reaches an agent again.

**Steps:**
1. Stand up the reranker sidecar on node3090 per `neural-search-design.md`:
   bge-reranker-v2-m3 GGUF on llama-server `:8091`, systemd unit `rerank-server.service`,
   lazy-start + 10-min idle-stop watchdog. **Measure VRAM before enabling**
   (~0.7 GB claimed — verify live next to Qwen3.6 + emb sidecar).
2. New module `tools/goethe_search.py` (mixin pattern, exactly like `goethe_kb.py` —
   goethe.py must not grow): `SearchMixin` with
   `_serp(query, category, time_range) -> list[dict]` (the current search_web body,
   returning structured dicts not markdown),
   `_rerank(query, candidates) -> list[(score, dict)]` (POST :8091, fail-open to
   engine order if sidecar unreachable — degraded flag set),
   `_canonicalize(results)` (url normalization + content-hash dedup).
3. Relevance floor valve `SEARCH_RERANK_FLOOR` (default 0.25, calibrate in step 5).
   Dropped results are counted per engine → append-only
   `/opt/local-se/search-telemetry.jsonl` (`{ts, engine, kept, dropped, mean_score}`).
4. Rewire `search_web()` to: `_serp` → `_canonicalize` → `_rerank` → floor →
   formatted return **plus** a `json=True` param returning the structured list
   (research() consumes this in Phase 2; the markdown path stays for compatibility).
5. Calibrate the floor: run the Phase-0 gold set, sweep floor 0.1–0.5, pick the
   highest floor with zero dropped-correct (same methodology as the min_score=4.0
   recalibration, 2026-07-20). Record the sweep in `eval/agentic-search-p1.md`.
6. **Tensor A/B (design §2.5 signal 3):** for the *indexed-corpus* path (:8092),
   implement bge-m3 ColBERT maxsim computed query-time over the RRF-fused top-50
   (the emb sidecar already runs bge-m3 — request its multi-vector output; no
   storage change). Run the gold set with (a) cross-encoder rerank, (b) tensor
   maxsim, (c) both cascaded. Winner by recall@3/MRR takes the corpus path —
   record the loser's numbers too (A/B LOSS precedent). Live-SERP snippets keep
   the cross-encoder regardless (no precomputed vectors).
7. Contract tests `tests/test_search_contracts.py`: rerank fail-open, floor drop,
   dedup, telemetry line shape, markdown-path unchanged-shape, tensor-path
   fail-open to fused order.

**Acceptance gate:** pizzeria-class junk (replay the saved 2026-07-20 SERP if
available, else a synthetic off-topic injection) scores < floor and is dropped;
gold-set junk-leak rate strictly better than baseline; full suite green.
**Rollback:** valve `SEARCH_RERANK=off` bypasses to pre-P1 behavior.

---

## Phase 2 — research() orchestrator + fetch ladder (M, the core)

**Objective:** the L0→L1→L2 waterfall + fetch-then-read loop moves from docstring
protocol into code. One tool, structured output, citations mandatory.

**Steps:**
1. `SearchMixin.research(question, depth="standard", freshness="auto") -> str(JSON)`:
   - L0: `search_kb` internally; quality ≥ 0.6 hit → return with `source: "kb"`.
   - L1: query node3090 `:8092` neural API; rerank-score ≥ floor → return `source: "web-idx"`.
   - L2: `_serp` per sub-query (Phase 3 adds decomposition; until then, the raw question),
     rerank, floor, take top-k.
   - Fetch ladder per candidate (parallel, per-page 20s cap): Firecrawl `:3002`
     (markdown) → `fetch_url` (fast raw) → `_camoufox_scrape` (hostile/JS pages).
     Ladder order + availability probed once per call, cached for the call.
   - Chunk fetched pages (512 tok / 64 overlap, heading-aware — same chunker as
     lse-web-idx ingest), rerank chunks against the ORIGINAL question, assemble
     top chunks as evidence.
   - Hop loop: if evidence coverage judged insufficient (all chunk scores < floor,
     or key_facts-style entities unmatched) → reformulate once per remaining hop.
     Budgets: quick=1 hop/3 fetches, standard=2/6, deep=4/12. Every engine hit
     decrements the existing SEARCH_BUDGET window — research() is budget-honest.
   - Return JSON: `{answer_evidence: [{chunk, url, domain, tier, engines,
     published_at, fetched_at, rerank_score}], hops_used, degraded_flags[],
     budget_remaining}`. No synthesis in the tool — the agent writes the answer
     FROM the evidence (synthesis stays where judgment lives).
2. `search_web()` docstring rewritten: "raw single SERP — prefer research()".
   KB-FIRST language moves into research()'s own L0 (it calls search_kb itself,
   so the protocol is now enforced, not requested).
3. MCP exposure: verify tool-list diff shows exactly +1 (`research`) — same
   release gate as PH5-2.
4. Tests: waterfall short-circuit (L0 hit never touches network — assert zero
   HTTP calls via mock), ladder failover, hop budget exhaustion, JSON schema,
   budget decrement.

**Acceptance gate:** gold-set run beats P1 on citation-supported rate; wall-clock
≤ 2× baseline on `standard`; full suite green; live smoke: one real question
answered end-to-end with ≥2 cited sources through the real stack.
**Rollback:** research() is additive — worst case agents keep using search_web.

---

## Phase 2.5 — Unified dataset / ETL plane (M) ★ REV 2, the platform core

**Objective:** one canonical ingestion path for EVERYTHING the agent reads — web
pages, PDFs, figures, repo docs — so retrieval quality work lifts every consumer
(design §2.5, plane 1). This is what turns the pipeline into a platform.

**Steps:**
1. `tools/goethe_ingest.py`: `ingest_chunks(source_kind, url_or_path, raw) ->
   upserted_ids[]` implementing the canonical chunk schema on `lse-web-idx`:
   `{chunk, title, url, domain, source_kind: web|pdf|figure|repo-doc, tier,
   origin, published_at, fetched_at, embed_model_version, content_hash,
   last_hit_at}`. ES mapping migration: additive fields only, alias-swap
   pattern from `rag/migrate_kb_index.py` if a reindex is unavoidable.
2. Parse lanes: web → Firecrawl markdown (exists); PDF → evaluate RAGFlow's
   DeepDoc as an importable library first (layout/table-aware — design §2.5
   appraisal), fall back to pymupdf if DeepDoc drags in too much; figure →
   Phase 4's VLM extraction JSON rendered as chunk text with `source_kind:
   figure`; repo-doc → plain markdown chunker.
3. Rewire Phase 2's fetch ladder to write through `ingest_chunks` (replaces the
   ad-hoc "auto-ingest" previously scheduled in Phase 5 — Phase 5 keeps only
   the SERP cache + LRU disk-guard work).
4. Backfill: re-enrich the existing 44,751 lse-web-idx chunks with the new
   fields where derivable (domain, content_hash; `source_kind: web`), verified
   by independent count + spot-check GETs (standing rule).
5. Tests: schema round-trip per lane, dedup-by-hash, idempotent upsert,
   mapping-migration dry-run.

**Acceptance gate:** one question answered from each lane (web page, a PDF, a
figure via the Phase-4 stub or a hand-fed extraction) through the same :8092
query path; backfill verified; suite green.
**Rollback:** additive mapping — old query path unaffected; `ingest_chunks`
behind valve `SEARCH_ETL=off` reverts fetch ladder to no-persist.

---

## Phase 3 — Query intelligence (S-M)

**Objective:** better queries in, engine-appropriate routing out. Retires year-stripping.

**Steps:**
1. `_plan_search(question) -> {sub_queries[], freshness_class, intent, visual_likely}`
   via `_call_planner_backend` (pluggable — local default; `deep` runs may use a paid
   backend, valve `SEARCH_PLANNER_BACKEND` defaulting to empty = inherit PLANNER_BACKEND).
   Strict JSON envelope, one repair-retry, fail-open to `{sub_queries: [question]}`.
2. Freshness → SearXNG `time_range` mapping (breaking→week, slow→year, evergreen→none).
   Delete `_strip_years` from the search path (keep compound-id survival note in tests).
3. Intent → engine routing: code→`!github !stackexchange`, docs→`site:` from
   `rag/official_docs_map.py`, news→news category, visual_likely→images category
   sub-query queued for Phase 4. Routing table lives in `goethe_search.py`, not prose.
4. Tests: planner fail-open, time_range mapping, routing table, CVE-id survival.

**Acceptance gate:** gold-set freshness-sensitive rows improve (recorded); no
regression elsewhere; suite green. **Rollback:** valve `SEARCH_PLANNING=off`.

---

## Phase 4 — Visual evidence pipeline (M) ★ the chart lesson

**Objective:** when a chart answers the question, read the chart — don't parse 5,000
words around it. (Motivating incident: KV-cache-VRAM scaling answered entirely by one
benchmark plot, 2026-07-20.)

**Steps:**
1. VLM backend, `VISION_BACKEND` valve = `local | claude | chatgpt | off` (default `off`
   until step 5 passes):
   - `local`: small VLM GGUF (Qwen2.5-VL-3B-class + mmproj) as `vlm-server.service` on
     node3090, lazy-start/idle-stop like emb/rerank. **Gate on measured VRAM**: it must
     fit the free headroom with emb+rerank idle-stopped; if it doesn't fit, `local` is
     not offered and the doc says so honestly.
   - `claude`/`chatgpt`: reuse the planner-backend credential plumbing
     (`_read_claude_oauth_token` / `_read_codex_oauth_token` / API-key valves) with
     image attachment per each API's multimodal format.
2. Discrimination wiring: `visual_likely` from Phase 3's planner, OR'd with page-side
   signals during fetch (figure/img density near matched text, chart-token
   alt/filenames, canvas/svg). Either signal → visual path activates for that source.
3. Acquisition: candidate `<img>` URLs downloaded directly (fetch_url, binary);
   JS-rendered charts → Camoufox full-page screenshot (extend `_camoufox_scrape` with
   `screenshot=True`, node3090 execution, PNG capped 2MB). SearXNG `images` category
   sub-query when intent is visual (needs Phase 0's category enablement).
4. Extraction: VLM prompt contract — return STRICT JSON
   `{figure_desc, axes: {x, y, units}, series[], data_points[], caveats}`; one
   repair-retry; failure → text-only fallback with `degraded_flags += ["vlm"]`.
   Extracted facts become evidence chunks (`url#figure-N`, `origin: "vlm-extraction"`,
   tier capped at the PAGE's tier — a chart is not more trustworthy than its page),
   AND persist through Phase 2.5's `ingest_chunks` with `source_kind: figure` —
   a chart is parsed once, retrievable forever (REV 2).
5. Eval: the gold set's `visual_likely` rows (incl. the KV-cache chart question) must
   be answered with figure-derived citations; manual spot-check of extracted
   data_points against the actual chart for ≥3 rows.
6. Tests: discrimination triggers, JSON contract repair, fallback, tier cap,
   screenshot size cap.

**Acceptance gate:** the KV-cache-chart gold row answered from the figure in ≤1 hop;
no VLM failure ever blocks an answer; suite green.
**Rollback:** `VISION_BACKEND=off` is the shipped default; enabling is opt-in.

---

## Phase 5 — Cache + corpus lifecycle (S — REV 2: ingestion itself moved to Phase 2.5)

**Steps:**
1. SERP cache: SQLite `/opt/local-se/search-cache.db` (normalized query+category+
   time_range → results JSON, TTL by freshness class: breaking 15m / slow 1d /
   evergreen 7d). Cache hits skip SEARCH_BUDGET decrement but are flagged in return.
2. Disk guard for the Phase-2.5 dataset: node3090 `/` is 88% full — hard cap
   auto-ingest corpus share (valve, default 10 GB), LRU-evict by `last_hit_at`
   (figure-kind chunks evict last — they're the most expensive to recreate),
   weekly report line into the dream digest. Verify cap enforcement with a
   synthetic over-cap test.
3. Tests: TTL expiry, budget-flag, LRU eviction order incl. figure-last, cap.

**Acceptance gate:** repeat gold-set run shows L1 hit-rate increase on second pass
(the corpus learned); disk usage within cap; suite green.
**Rollback:** valves `SEARCH_CACHE=off`, `SEARCH_ETL=off` (Phase 2.5's).

---

## Phase 6 — Trust, Console, close-out (M)

**Steps:**
1. Domain→tier table in `TrustPolicy` (vendor-docs/RFC/official repos → primary;
   SO/Reddit/blogs → secondary; unknown → inferred). research() stamps tiers;
   version/behavior claims lacking any primary-tier citation get the same
   `[UNVERIFIED]` treatment as index_to_kb's waterfall rule.
2. Console panel (goethe_ui, read-only, same pattern as v0.2.0 panels):
   per-engine health (mean rerank score, drop rate, suspended state — from
   search-telemetry.jsonl), cache stats, last-N research() traces (question,
   hops, sources, degraded flags).
3. Engine auto-suspend: telemetry consumer flags an engine whose 7-day mean rerank
   score collapses below half its own baseline → writes the `suspended_times`
   stanza to a PROPOSED settings.yml diff (human deploys via the delegated-sudo
   path — config writes stay human-gated, same as sudoers).
4. Final eval: full gold set, all phases on, side-by-side vs Phase-0 baseline in
   `eval/agentic-search-final.md`. Ship report includes the honest deltas, wins
   AND regressions.
5. Close: CHANGELOG, CURRENT-STATE (new rows: goethe_search, sidecars, valves),
   VALVES.md, runbook section "Search operations", KB entry via index_to_kb
   (origin=human, tier per evidence), session debrief.

**Acceptance gate:** every Phase 0–5 valve documented; Console panel live;
final eval published; suite green; gateway restarted and verified.

---

## Dependency graph

```
P0 ──► P1 ──► P2 ──► P2.5 ──► P3 ──► P4
              │        │        └───► (P4 needs P3's visual_likely; page-side
              │        │             signals alone can ship P4 degraded)
              │        └───► P4 persists figures via P2.5's ingest_chunks
              ├──────► P5 (needs P2 fetch ladder + P2.5 dataset)
              └──────► P6 (needs P1 telemetry; final close needs all)
```

## What NOT to do (carried from design doc §6 + this session's lessons)

- Do not put embedding or VLM load on LUCIFER's CPU path — all new model inference
  is node3090 sidecars or paid-API valves.
- Do not let any phase write ES/KB and self-report success without an independent
  read-back check.
- Do not auto-deploy SearXNG config or sudoers changes — propose diffs, human runs
  the delegated block.
- Do not grow goethe.py — all new code in `tools/goethe_search.py` (+ tests).
- Do not skip the eval gates. A phase that can't beat the previous one on its own
  metric doesn't merge — record the loss honestly and stop (A/B LOSS precedent,
  TRAUM 4.6).
