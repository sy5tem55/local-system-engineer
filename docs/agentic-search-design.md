# Agentic Web Search — Ground-Up Redesign

**Date:** 2026-07-20 (Cowork) · **Status:** PROPOSAL — nothing implemented
**Supersedes:** the raw `search_web()` SearXNG wrapper as the primary web-research path.
**Companion docs:** `neural-search-design.md` (L1 layer, already live), `docs/threat-model-kb.md` (§ trust), `kb/session-learnings.md` (2026-07-20 bing soft-block postmortem).

---

## 1. Why the current setup is severely lacking — honest audit

What `search_web()` is today (`tools/goethe.py:3715`):

| Weakness | Consequence, observed live |
|---|---|
| Single-shot, top-5, 300-char snippets | Agent answers from fragments; `fetch_url` follow-up is a docstring *plea*, not code — small local models skip it |
| No relevance floor | The 2026-07-20 pizzeria incident: bing's soft-block filler ranked alongside real results with nothing to catch it — a cross-encoder rerank would have scored it near zero |
| No result structure | Markdown blob return; the agent re-parses its own tool output; no dates, no engine attribution, no trust tier |
| "Do not search twice per topic" | Right rule for a budget, wrong rule for research — complex questions need decomposition + follow-up hops; the blunt rule forces one bad query to be final |
| Year-stripping is the only freshness logic | SearXNG supports `time_range`; we strip "2025" instead of routing recency intent |
| Engines are all-or-nothing | An engine going bad (bing) silently poisons results until a human notices a pizzeria; no per-engine quality telemetry |
| No caching | Same query re-hits engines; nothing learned from fetched pages |
| Search / fetch / index are separate tools glued by prompt protocol | The KB-first → search → fetch → synthesize → index_to_kb loop lives in docstrings; every step the model can (and does) skip |

The core diagnosis: **we built retrieval infrastructure but left orchestration to the LLM's discipline.** For a 27B local model, discipline-by-docstring measurably fails (three self-report failures documented 2026-07-20 alone). State-of-the-art agentic search moves the loop INTO code and gives the model one high-level tool with structured output.

## 2. What we already own (don't rebuild)

| Asset | State | Role in new design |
|---|---|---|
| `lse-kb` (146 docs, qwen3-embedding 1024, verified clean 2026-07-20) | live | L0 — answer without touching the network |
| `lse-web-idx` (44,751 chunks, bge-m3, node3090 :8092 API, `!nl` engine) | live | L1 — local web corpus, ~100ms answers |
| SearXNG :8088 (bing disabled, engine whitelist) | live | L2 — live meta-search |
| Firecrawl node3090 :3002 | live | L3 — page → clean markdown |
| bge-reranker-v2-m3 sidecar (lazy-start design, :8091) | designed in neural-search-design.md | THE missing quality gate — reuse for live results |
| `fetch_url`, `_camoufox_scrape` (Playwright anti-bot) | live | L3 fetchers (fast path / hostile path) |
| `TrustPolicy` tiers + origin tags (goethe_kb.py) | live | domain → tier mapping at search time |
| `planner()` w/ pluggable backends (local/chatgpt/claude/rest) | live | query decomposition brain |
| SEARCH_BUDGET rolling window | live | keep, apply to the whole loop |
| eval harness culture (`eval_retrieval.py`, gold sets, threshold sweeps) | live | same methodology, new gold set |

The gap is **one orchestrator and three small services-glue pieces** — not a new stack.

## 2.5 Platform shape (REV 2, 2026-07-20) — the core idea

REV 1 of this doc designed a better *search pipeline*. The correct target is a
**retrieval platform** with three planes — web search is just one feeder and one
consumer of it:

```
┌─────────────────── INGESTION / ETL PLANE ─────────────────────────────┐
│  web pages · PDFs · images/charts · repo docs · READMEs · man pages   │
│        │ parse (Firecrawl md / PDF extractor / VLM figure-read)       │
│        │ chunk (512/64, heading-aware) · enrich (title, domain, tier, │
│        │ dates, origin, embed_model_version) · dedup (content hash)   │
│        ▼                                                              │
│   ONE canonical chunk schema → lse-web-idx (the "dataset")            │
│   (lse-kb stays separate: curated, trust-lifecycle, human-gated)      │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌─────────────────── INDEX / RETRIEVAL PLANE ───────────────────────────┐
│  Signal 1: dense kNN (bge-m3 dense, int8_hnsw)                        │
│  Signal 2: full-text BM25 (ES, english analyzer)                      │
│         └─► RRF fusion (in code, k=60 — basic license)                │
│  Signal 3 (precision): TENSOR late-interaction maxsim                 │
│         bge-m3's native ColBERT multi-vectors, computed query-time    │
│         on the fused top-50 via the GPU sidecar — no multi-vector     │
│         storage cost, precision of token-level interaction.           │
│         A/B'd against bge-reranker cross-encoder on the gold set;     │
│         the winner takes the indexed-corpus path, cross-encoder       │
│         keeps the live-SERP path either way (snippets have no         │
│         precomputed vectors and need a text-pair scorer).             │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌─────────────────── ORCHESTRATION PLANE ───────────────────────────────┐
│  research() workflow · planner backends (local/claude/chatgpt/rest)   │
│  MCP tools · Console panels · dream/TRAUM passes · missions           │
│  — every consumer hits the same retrieval API (:8092), never a raw    │
│  engine; live SearXNG is the L2 *feeder* that fills the dataset       │
└───────────────────────────────────────────────────────────────────────┘
```

Three consequences of the platform framing that REV 1 missed:

1. **Ingestion is a first-class plane, not a side effect.** REV 1's "auto-ingest
   fetched pages" (§3.5) becomes THE canonical write path: everything the agent
   ever reads — a web page, a PDF manual, a benchmark chart parsed by the VLM,
   a repo README — lands in the same chunk schema with the same enrichment.
   Images are ingested as *documents* (the VLM's structured extraction is the
   chunk text, the image URL is the source), so a chart found once is retrievable
   forever without re-parsing.
2. **Precision is a pluggable third signal, not one hard-coded reranker.**
   bge-m3 (already the chosen corpus embedder) natively emits dense + sparse +
   ColBERT multi-vectors from one forward pass — the tensor stage costs one
   extra sidecar call, not a new model. Whether tensor maxsim or the
   cross-encoder wins on our data is an eval question, not an opinion — the
   gold set decides.
3. **One retrieval API, many consumers.** TRAUM's dream passes, `check_error_kb`,
   future missions, and research() all query the same plane. Retrieval quality
   work done once lifts every workflow.

**Alternative appraised honestly — adopt RAGFlow wholesale:** it implements this
exact picture (DeepDoc parsing, Infinity's tensor reranking, visual workflow
builder, MCP) and is Apache-2.0. Rejected as the *platform*, for now: it brings
its own MySQL+Redis+MinIO+engine stack (node3090 `/` is at 88%), would run
beside — not replace — our ES/trust-lifecycle/perms investment, and its write
paths don't pass through our human-gated trust rules. Worth stealing from
selectively: its DeepDoc PDF/layout parser is importable as a library and is the
strongest candidate for the ETL plane's PDF lane. Revisit the wholesale option
if the native build stalls.

## 3. Target architecture — the request path through the platform

```
            research(question, depth=quick|standard|deep, freshness=auto)
                                   │
                    ┌── QUERY PLANNER (planner backend) ──┐
                    │ decompose → sub-queries              │
                    │ classify: freshness / domain intent  │
                    └──────────────┬───────────────────────┘
                                   ▼
      L0 lse-kb ──hit(q≥0.6)──► ANSWER (no network)         [exists]
                                   │ miss
                                   ▼
      L1 lse-web-idx (:8092) ──hit(rerank≥τ)──► ANSWER      [exists]
                                   │ miss
                                   ▼
      L2 SearXNG :8088  (per-sub-query, engine-routed,
                         time_range from freshness intent)
                                   ▼
              CANONICALIZE + DEDUP (url norm, content hash)
                                   ▼
              RERANK (bge-reranker-v2-m3, :8091 lazy-start)  ← kills junk
                     score < floor → dropped + per-engine telemetry
                                   ▼
              FETCH top-k full pages (Firecrawl → fetch_url → camoufox
                     escalation ladder; parallel; per-page timeout)
                                   ▼
              CHUNK + RERANK CHUNKS against original question
                                   ▼
      ┌── enough evidence? ──no──► next hop (budget-gated, max_hops) ──┐
      │ yes                                                            │
      ▼                                                                │
   STRUCTURED RESULT ◄─────────────────────────────────────────────────┘
   {answer_evidence[], citations[], per-source: url, domain, tier,
    published_at, fetched_at, engines[], rerank_score, chunk_text}
                                   ▼
   SIDE EFFECTS: SERP cache (TTL by freshness class) · fetched pages
   auto-ingested into lse-web-idx (corpus grows from agent behavior) ·
   index_to_kb PROPOSAL emitted (human-gated, existing trust rules)
```

### 3.1 The one-tool contract

`research()` replaces the search_web/fetch_url/synthesize docstring protocol with a code loop. `search_web()` stays as the low-level escape hatch (renamed docstring: "raw single SERP call — prefer research()").

Return is JSON-structured (the agent stops parsing markdown blobs), every evidence chunk carries its citation, and the whole call is bounded: `depth=quick` ≈ 1 hop / 3 fetches; `standard` ≈ 2 hops / 6 fetches; `deep` ≈ 4 hops / 12 fetches, all inside the existing SEARCH_BUDGET window. One `research()` call consumes budget proportional to its actual engine hits, not 1.

### 3.2 Query planning (small but high-leverage)

- **Decomposition:** multi-clause questions → 2-4 sub-queries via `planner()` (already pluggable — a `deep` research call can use a paid backend for planning while fetching stays local).
- **Freshness intent** replaces year-stripping: classify {evergreen, slow, breaking} → SearXNG `time_range=` {none, year, month/week}. Keep the compound-id survival rule (CVE-2025-1234).
- **Engine routing:** code intent → `!github !stackoverflow`; docs intent → `site:` operators on vendor domains from a maintained map (`official_docs_map.py` already exists in rag/); news intent → news category. Default stays the general whitelist.

### 3.3 Reranking is the load-bearing quality fix

Everything L2 returns passes the cross-encoder before the agent ever sees it. This single stage:
- makes engine misbehavior (pizzeria-class filler) score ≈0 and vanish regardless of which engine lies,
- produces **per-engine mean-rerank-score telemetry** — an engine whose scores collapse gets auto-suspended (`suspended_times`) and flagged in the Console, turning the bing incident from a human-noticed anomaly into a metric,
- gives an honest "no good results" signal (all scores < floor) instead of confidently returning junk.

VRAM math already done in neural-search-design.md: reranker ~0.7 GB, lazy-start + 10-min idle-stop inside node3090's ~3.8 GB headroom.

### 3.4 Trust and provenance at search time

Extend `TrustPolicy` with a domain→tier table (vendor docs/RFCs → primary; StackOverflow/Reddit/blogs → secondary; unknown → inferred). Each result carries its tier; the synthesis step must cite ≥1 primary-tier source for version/behavior claims or the result is tagged the same way `index_to_kb`'s waterfall rule already tags unprovenanced claims. `verify_source_claims` plugs in unchanged for post-hoc audit.

### 3.5 Caching + the self-growing corpus

- **SERP cache:** normalized query → results, TTL by freshness class (breaking 15m / slow 1d / evergreen 7d). SQLite, same pattern as goethe-perms.db.
- **Page cache → corpus:** every successfully fetched page goes through the §2.5
  ETL plane into `lse-web-idx` with `fetched_at` (and `embed_model_version`, per
  the 2026-07-20 lesson). Next time a related question arrives, L1 answers in
  ~100ms without touching the live web. The index stops being a static crawl
  snapshot and becomes a working set shaped by what the agent actually
  researches — and VLM-parsed figures persist as retrievable documents, so a
  chart is read once, not on every question that needs it.
- Disk guard: node3090 `/` is 88% full — cap auto-ingest with LRU eviction by `last_hit_at`, and stamp every auto-ingested chunk `origin=web` (asymmetric trust rule already forbids it minting ground_truth).

### 3.6 Visual evidence (charts, diagrams, screenshots)

Real incident motivating this (2026-07-20): the agent burned a long text-parsing
loop trying to answer "how does KV-cache VRAM scale with context length" when a
single benchmark chart on the page contained the entire answer — every data
point, every configuration, one image.

`research()` therefore discriminates when a question is *visual-evidence-likely*
and routes accordingly:

- **Intent signals (query side):** scaling/benchmark/comparison questions
  ("X vs Y", "how does A scale with B", perf/VRAM/latency curves), topology or
  architecture questions (diagrams), UI/config questions (screenshots).
- **Page signals (fetch side):** high `<figure>`/`<img>` density near matched
  text, chart-suggestive alt/filename tokens (benchmark, chart, vs, scaling,
  plot), `<canvas>`/`<svg>` blocks, arXiv/GitHub-README figure patterns.
- **Direct image search:** SearXNG's `images` category as a first-class
  sub-query when intent is visual (`!images qwen kv cache vram context`).

Pipeline: Camoufox (node3090) screenshots the rendered page / downloads the
candidate `<img>` URLs → VLM extracts structured facts (axes, series labels,
data points, table cells) → extracted facts enter the same chunk-rerank pool as
text evidence, cited as `url#figure-N` with the extraction noted in provenance.

VLM backend behind a `VISION_BACKEND` valve, same pattern as planner backends:
`local` (small VLM GGUF as a lazy-start llama-server sidecar on node3090 —
VRAM-gated, only if measured headroom allows next to emb/rerank sidecars) |
`claude` / `chatgpt` (multimodal APIs, reusing the planner-backend credential
plumbing) | `off` (visual path disabled, text-only fallback). Fail-open: a VLM
failure degrades to text evidence, never blocks the answer.

### 3.7 Ops hardening (small, do first)

1. Fix the searxng-logger metrics-token mismatch (documented 2026-07-20, still open).
2. SearXNG: enable `time_range` passthrough, keep engine whitelist, add per-engine `suspended_times` config stanza.
3. Health: add SearXNG + :8092 + sidecar status to the existing `lse-stack-health-check` skill and Console.

## 4. Evaluation — same discipline as the KB

Build `eval/agentic-search-gold-v1.jsonl`: ~40 real questions from episode logs (the journal already records every search_kb miss → these ARE the gold queries), each labeled with acceptable source domains + key facts. Metrics: answer-supported-by-citation rate, primary-tier citation rate, junk-leak rate (pizzeria detector), wall-clock, engine hits per answer. Run before (current search_web) and after each phase. No phase ships without beating the previous on junk-leak and citation rates without regressing wall-clock ×2.

## 5. Phasing (each independently shippable)

| Phase | What | Reuses | Effort |
|---|---|---|---|
| **P1** | Rerank layer on live SERPs + relevance floor + per-engine telemetry; structured JSON return | reranker sidecar design, existing search_web plumbing | S |
| **P2** | `research()` orchestrator: L0→L1→L2 waterfall, fetch ladder, chunk-rerank, citations, budget integration | everything | M |
| **P3** | Query planner: decomposition, freshness intent (retire year-stripping), engine routing | planner() backends | S-M |
| **P4** | SERP cache + auto-ingest fetched pages into lse-web-idx + LRU disk guard | lse-web-idx, Firecrawl | M |
| **P5** | Trust-tier domain table + primary-source citation rule + Console panel (per-engine health, cache stats, research-call traces) | TrustPolicy, goethe_ui | M |
| **P0 (now)** | Ops hardening §3.6 + gold-set harvest from episode logs | — | XS |

P1 alone would have prevented the pizzeria incident and is the highest value-per-line change in the stack.

## 6. Explicit non-goals

- No paid search APIs as a dependency (optional engines behind valves at most — the stack stays self-hosted).
- No autonomous KB writes from research results — `index_to_kb` proposals remain human/trust-gated exactly as today.
- No general web crawler — Firecrawl stays allowlisted/targeted; the corpus grows from *agent demand*, not breadth-first crawling.
- Do not raise embed input limits or add models to LUCIFER's CPU embedder path without re-measuring latency (2026-07-20 lesson, `_EMBED_CHAR_LIMIT`).
