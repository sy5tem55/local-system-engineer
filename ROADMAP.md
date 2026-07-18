# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-07-02 (Cowork) — **full reconciliation pass**: roadmap re-baselined against
> the actual code in `tools/` (Goethe v0.2.9 frontier). Retired sections removed: P20 Active,
> v1.7.0 Hermes Core (superseded by Goethe MCP), Claude L2 (done, OWUI-era), Eval Run 7 (OWUI-era).
> Surviving items redistributed into the Phased Plan below. Note: working-copy ROADMAP.md was
> found truncated at "Backlog — Arena" this session; tail recovered from git HEAD.

---

## Current Frontier — what this roadmap is baselined against (2026-07-02)

**Deployed stack (verified in `tools/`, not from memory):**

| Component | Actual | Notes |
|---|---|---|
| LSE Tool | **Goethe v0.2.9** (`tools/goethe.py`, 5819 lines, 2026-07-01) | ⚠️ CURRENT-STATE.md / VERSION.md still say v0.2.5 — doc drift, see P0-1 |
| MCP Gateway | **goethe_mcp v1.9.3** (`tools/goethe_mcp.py`) | HTTP :9700, `_TokenGuard`, `SKIP_TOOLS={compact_context}`, `--also` vaultwarden v1.3.0 |
| Frontend | **llama-ui** (built into llama-server :8080) | OWUI **retired** |
| Planner | **`planner()`** (v0.2.9 rename of `hermes_plan`) | 3-path cascade: node3090 llama-server :8080 → Ollama :11434 qwen3:4b → local VRAM-gated Gemma GGUF spawn (E4B/26B-A4B/31B, vision via mmproj). `<think>`-strip before JSON envelope regex. |
| Hermes agent | **RETIRED** (v0.2.7) | `_call_hermes`/`_kanban_create_card` are stubs. Multi-agent coordination moved to **Faust** rooms. |
| SSH layer | `ssh_run` (argv, no double-shell) + `ssh_script` (scp + nohup guard) + ControlMaster mux + complexity guard (v0.2.6) | |
| System prompt | v0.5.19 (tools/) marked "ready to deploy"; `prompts/node4090-v0.5.21.md` exists and is NEWER | lineage forked — reconcile, see P0-5 |

**Goethe changelog since the docs stopped tracking (v0.2.5 → v0.2.9):**
v0.2.6 SSH overhaul (3 root causes of exit-255 fixed) · v0.2.7 Hermes retired → `_call_node_planner`
cascade · v0.2.8 PATH-3 VRAM-aware Gemma spawn (+valves `PLANNER_MODEL_DIR/PORT/LLAMA_BIN`) ·
v0.2.9 `hermes_plan`→`planner` rename + think-tag JSON extraction fix.

**Findings from the tools/ analysis that create new work:**
1. **SEC:** `start-goethe.sh` hardcodes `GOETHE_MCP_TOKEN=6e003f5c…` (committed to git history)
   and launches with `--host 0.0.0.0 --cors-origin '*'` — directly contradicting goethe_mcp.py's
   own security header (bind 127.0.0.1, token = the "who", CORS = specific origin). This is a
   remote-code-execution surface exposed LAN-wide with a public token. → P0-2.
2. **Doc drift:** CURRENT-STATE/VERSION at v0.2.5; four Goethe releases undocumented. → P0-1.
3. **Repo hygiene:** 25 cogitator + 28 openwebui-tool + assorted superseded copies (~4.5 MB)
   still in `tools/`; git is the version store. → P0-3.
4. **Stale skill:** `skills/lse-eval-runner` still instructs OWUI Admin-panel checks and
   `openwebui-tool-v1.5.x` version confirmation — unusable against llama-ui + MCP. → PH3-3.
5. Waterfall "remaining gap" (a)+(b) from old v1.7.6 item **SHIPPED** in Goethe v0.2.2
   (VENDOR-BEHAVIOR GROUND-TRUTH + RELEASE ASSET rules in `execute_command`) — closed, removed.

---

## Phased Plan — all remaining work, dependency-ordered

> Workstream item IDs (KB-DECAY-n, CHRONOS-n, PROVE-n, DATA-n, SCRIBE-n, REFACTOR-n) are
> defined in detail in the next section. Phases bundle them with carried-over backlog items.

### Phase 0 — Reconcile & lock down (immediate, ~half a day)

- [ ] **P0-1** — Update `CURRENT-STATE.md` + `VERSION.md` to Goethe v0.2.9 / goethe_mcp v1.9.3;
      record the v0.2.6–v0.2.9 lineage + line-count tally (5819); note Hermes retirement and
      `planner()` rename so no future session re-documents `hermes_plan`.
      **PARTIAL ✅ (2026-07-02):** CURRENT-STATE.md updated — v0.2.9 rows, v0.2.6–v0.2.9
      changelog, operator-verified stack inventory recorded (goethe_mcp 1.9.3 / goethe 0.2.9 /
      llama-server a6647b1 / Ollama 0.22.1 ×5 models / ES 8.13.0 / SearxNG 2026.5.8-pinned +
      port map). Remaining: VERSION.md registry + sha256/black-norm hashes; reconcile
      llama-server build identity (a6647b1 source build vs recorded b9577) per node.
      **✅ DONE (2026-07-18, Cowork):** VERSION.md reconciled — goethe.py v0.4.0-a live-verified
      (7238 lines, raw `ba0c1a2015c89098…`), goethe_mcp `__version__` 1.11.1 (815 lines,
      `1d903a29ca63ec50…`; registry's v1.9.3 was stale). llama-server identity settled: BOTH
      recorded builds obsolete — LUCIFER = version 20 (`bf2c86ddc`), node3090 = version 64
      (`e8f19cc0a`). System-prompt row updated to v0.6.0 canonical.
- [ ] **P0-2** — **SEC: goethe_mcp exposure.** Rotate `GOETHE_MCP_TOKEN` (old one is in git
      history — treat as public); move it into `~/.lse/secrets` (already sourced by
      start-goethe.sh); decide binding: 127.0.0.1 if only llama-ui on LUCIFER needs it, else
      bind the LAN IP + pfSense allow-rule scoped to node3090; CORS `'*'` → the actual llama-ui
      origin. Same audit for `start-goethe-node3090.sh`. Verify with `ss -tlnp` + a tokenless
      curl (expect 401).
- [x] **P0-3** — Purge superseded copies from `tools/` (= REFACTOR-3): cogitator v1.7.0–v1.7.24,
      openwebui-tool v1.4.0–v1.6.4, goethe-v0.2.1/v0.2.2, goethe_mcp_v1.8.0,
      backupfromOWUI1.7.12.py, lse-context-monitor v1.0–1.2, lse-routing-filter v1.0–1.1,
      vaultwarden v1.0/v1.2, root `lse-stack-launch-1.05…1.077`. Sentimental → `.backups/`.
      Gitignore `__pycache__/`. Git tag `pre-purge` first.
      **✅ DONE (2026-07-18, Cowork):** bulk of the named versions were already purged 2026-07-02
      (`.backups/pre-purge-20260702`); final sweep moved 29 files (system-prompt v0.5.16–19,
      `goethe - 110726.py`, *.bak/*.bak.step5, stray root eval logs) → `.backups/pre-purge-20260718/`;
      tag `pre-purge` set; commit `be53e52`. `__pycache__/` gitignored.
- [x] **P0-4** — Documentation cleanup (carried): delete `docs/searxng-settings-patch-v2.yml`;
      archive `docs/searxng-config.md`; move `mesh_builder.py` + `portrait_3d_pifuhd.py` out of
      root; grep-audit remaining OWUI references across docs/ + kb/ + skills/.
      **✅ DONE (2026-07-18, Cowork):** both searxng files already gone (only
      `docs/searxng-operations.md` remains); mesh/portrait scripts already in `tools/`;
      OWUI grep-audit: references confined to historical docs (docs/01–10, dreaming reports,
      hermes specs) — no operative doc or skill instructs OWUI usage.
- [x] **P0-5** — Prompt lineage reconcile: `tools/system-prompt-v0.5.19.md` ("ready to deploy")
      vs `prompts/node4090-v0.5.20/21.md` (newer) — pick ONE canonical dir (`prompts/`), confirm
      what is actually pasted into llama-ui on each node, deploy/record it.
      **✅ RECONCILED (2026-07-04):** v0.5.21 confirmed the newer lineage; canonical dir =
      `prompts/`; NEW **`prompts/node4090-v0.6.0.md`** built on it for Goethe v0.3.8 (45
      tools): REQUEST-SHAPE MAPPINGS section (plan→planner, prove-it→run_tests/assert_state,
      resume→task_resume, human-says-wrong→mentor_demote), MULTI-BLOCK TASK RULE **rebuilt
      around the tasks.db ledger** (the old rule MANDATED hand-written active-task.md — root
      cause of the DNS-audit ledger bypass), planner v2 / plan_step_done / kb_verify /
      time_check / run_tests / assert_state tool entries, SSH v0.3.7 guard notes, TIME
      DISCIPLINE, ledger-first HANDOVER. tools/system-prompt-v0.5.x = superseded (purge with
      P0-3). OPERATOR: paste v0.6.0 into llama-ui on node4090 + start fresh threads;
      node3090's prompt (v0.1.0) needs its own smaller update — follow-up.
- [x] **P0-6** — Carried P21 leftovers: ES index-existence probe added to stack health check
      (`curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`); delete
      vestigial `lse-kb.sqlite` (0 bytes, unreferenced).
      **✅ VERIFIED DONE (2026-07-18, Cowork):** probe already present in
      `skills/lse-stack-health-check/SKILL.md` (5-index `_count`, P21 addition); `lse-kb.sqlite`
      no longer exists anywhere in the repo.

### Phase 1 — Safety net, then KB trust lifecycle (Workstreams C→A)

- [x] **PH1-1** — PROVE-2 contract tests FIRST (pin current tier/evidence/dedup behavior against
      a throwaway `lse-kb-test` index).
      **✅ DONE (2026-07-02, Cowork):** `tests/test_kb_contracts.py` — 34 tests, all green on
      live ES 8.13.0 via owui-venv python. Index-rewrite proxy makes production indices
      unreachable; deterministic fake embeddings (no Ollama dep). Pins: tier ceilings, evidence
      gates, waterfall cap, dedup-updates, record_outcome quality-never-touched (KB-DECAY-1
      flip point marked in-test), mentor_correct raise-only, skill quality clamp/floor,
      skill_outcome demotion + archive. Found: skill_outcome demotion floor is 0.0 in code vs
      0.2 in docstring — test pins code; reconcile in KB-DECAY-1. See CHANGELOG 2026-07-02.
- [x] **PH1-2** — KB-DECAY-1..5 (demotion in `record_outcome`, [STALE] quarantine + trust counts
      in `search_kb`, `kb_verify` regression probe on `verified_against`, `mentor_demote`,
      mapping migration). Ship as **Goethe v0.3.0** — this is the headline behavior change.
      **✅ SHIPPED (2026-07-02, Cowork):** Goethe v0.3.0, 6128 lines. All five KB-DECAY items
      implemented + skill_outcome floor reconciled to 0.2 (PROVE-2 finding). Migration run on
      live lse-kb. Contract tests 34 → 53, all green. See CHANGELOG 2026-07-02 (PH1-2 entry).
      Deploy note: system prompt should gain the mentor_demote human-authorization rule and
      the "prove it" → kb_verify mapping (fold into P0-5 canonical prompt work).

### Phase 2 — Sense of time (Workstream B)

- [x] **PH2-1** — CHRONOS-1 `time_check()` (multi-NTP + TLS-date sanity, report-don't-adjust).
- [x] **PH2-2** — CHRONOS-2 `MODEL_PRETRAIN_CUTOFF` valve + server-side `[TIME]` banner injection.
- [x] **PH2-3** — CHRONOS-3 volatility TTLs on KB docs; CHRONOS-4 retire the now-redundant
      docstring date rules. Ship as **Goethe v0.3.1**.
      **✅ SHIPPED (2026-07-02, Cowork):** Goethe v0.3.1, 6387 lines; tests 53 → 75 green.
      Year injection now stripped in code (`_strip_years`), not policed by prose.
      OPERATOR TODO: set `export GOETHE_MODEL_PRETRAIN_CUTOFF=<YYYY-MM>` (Qwen3.6's real
      published cutoff) in ~/.lse/secrets on BOTH nodes — banner nags UNSET until then.
      See CHANGELOG 2026-07-02 (PH2 entry).

### Phase 3 — Prove-it surface + eval re-baseline

- [x] **PH3-1** — PROVE-1 `run_tests(scope)` + PROVE-3 `assert_state()` + PROVE-4 health-check
      wiring. Ship as **Goethe v0.3.2**.
      **✅ SHIPPED (2026-07-03, as Goethe v0.3.6):** both tools live on both gateways
      (45 tools), 105/105 contract tests. Deviations from spec: `rules` scope is an LLM
      eval (GPU-minutes) → explicit-only, excluded from `all`; PROVE-4 wiring deferred to
      PH3-3 (installed health-check skill is Cowork-side read-only). System prompt should
      gain "prove it" → run_tests/assert_state mapping (fold into P0-5).
- [x] **PH3-2** — Retrieval decision (carried from 1.7.0-c, the only piece not yet shipped):
      run `rag/eval_retrieval.py --compare` on live ES; adopt linear vs RRF on recall@3/MRR
      numbers; settle the 0.72 threshold with `--threshold-report`. Update `search_kb` if RRF wins.
      **✅ DECIDED (2026-07-04, Goethe v0.3.8):** linear wins (recall@3 0.84 / MRR 0.800 vs
      RRF 0.84 / 0.735) — ranking unchanged, RRF rejected on data. BONUS FINDING: the 0.72
      threshold was a cosine-scale no-op against hybrid scores (~3.5–16); recalibrated to 4.2
      via sweep (38/38 correct kept, 3/11 wrong dropped, 0 correct lost). KB doc + re-sweep
      maintenance rule recorded. See CHANGELOG 2026-07-04.
- [ ] **PH3-3** — Rewrite `skills/lse-eval-runner` for the llama-ui + goethe_mcp stack (pre-run
      checklist becomes `run_tests`-backed; drop OWUI Admin steps; version checks read goethe.py
      frontmatter via MCP). Then **full eval re-run** — Run 7's 63/63 was scored on
      OWUI + openwebui-tool v1.5.18 and does not certify the current stack. New baseline =
      Run 8 on Goethe v0.3.x + llama-ui, with `tools/system-prompt` canonical version from P0-5.
- [x] **PH3-4** — Run `lse-docstring-optimizer` on every new tool docstring from Phases 1–3
      (kb_verify, time_check, run_tests, assert_state, mentor_demote, planner) — SCRIBE-5.
      **✅ DONE (2026-07-18, Cowork, Goethe v0.4.3):** full 8-dimension audit on all six.
      Result: 0 FAIL; planner/kb_verify/mentor_demote exemplary (no changes); 3 WARNs fixed —
      time_check delegation-edge GOOD/BAD pair, run_tests scope-misuse GOOD/BAD (rules =
      GPU-minutes, double-check reruns), assert_state explicit GATE line (one assert per
      claimed state). Docstring-only release; tests unaffected (424 green); gateway restarted.

### Phase 4 — Data quality + the self-writing loop (Workstreams D+E)

- [ ] **PH4-1** — DATA-1..4 (self-harvested gold sets — no HF/Kaggle; `dataset_lint.py`;
      sha256-frozen datasets; reseed preserves trust fields).
- [x] **PH4-2** — SCRIBE-1..4 **ABSORBED INTO TRAUM** (2026-07-11) — **ALL 4
      THREADS COMPLETE (2026-07-13)**. Thread 1 (TRAUM-CORPUS) ✅ 2026-07-11:
      episode journaling live on the gateway (goethe_mcp v1.11.1),
      manifest/rotation, SCRIBE-1/2/3, 137 backfill facts applied. Thread 2
      (TRAUM-ENGINE) ✅ 2026-07-11: dream_runner/dream_apply, first supervised
      dream (3 dedup merges applied, 8/11 proposals correctly gate-rejected).
      Thread 3 (TRAUM-INSIGHT) ✅ 2026-07-12: patterns/insights mining,
      digest + [DREAM] banner live (Goethe v0.4.0-a), SCRIBE-4
      self-measurement, null-result discipline. Thread 4 (TRAUM-AUTO) ✅
      2026-07-13: nightly timer installed+enabled (03:30, first unattended
      fire 2026-07-14), guardrails (lock/budgets/activity), crash discipline,
      --queue + 14-day expiry, A/B eval RUN (pre-registered verdict: LOSS,
      methodologically inconclusive — eval/eval-report-traum-1.md §6-7),
      threat model, DREAM_AUTO_APPLY held empty (DESIGN.md §7.4), runbook §10.
      Both Thread-3 security/data-loss findings fixed at Thread 4 open
      (agent-log redaction, pass-scoped output files).
- [x] **PH4-3** — RFC KB verdict (carried P21): still ZERO `search_rfc` calls. Either wire it
      into episode prompts (topology/DNS challenges cite RFC 8375 etc.) or retire the index.
      Decide with usage-log data, not sentiment.
      **✅ DECIDED — RETIRED (2026-07-18, Cowork, goethe_mcp v1.11.2):** usage data final:
      **0 `search_rfc` calls in 6,967 journaled tool calls** (entire episode corpus,
      2026-07-11 → present; top tools: execute_command 4781, ssh_run 491, search_kb 332).
      Retirement is the reversible kind: `search_rfc` added to gateway `SKIP_TOOLS`
      (tool surface 38 → 37; one-line revert), method + `lse-rfc-kb` index (1490 chunks)
      kept dormant. If RFC content earns its place later, ingest into `lse-web-idx`
      (neural search) instead of reviving the bespoke tool.

### Phase 5 — Refactor under green tests (Workstream F)

- [x] **PH5-1** — REFACTOR-1 (single `TrustPolicy`, kills 3× `_TIER_CEILING`).
      **✅ SHIPPED (2026-07-18, Cowork, Goethe v0.4.1):** `TrustPolicy` class in new
      `goethe_kb.py` — one `TIER_CEILING` dict + `ceiling(tier, default)`; semantics
      preserved exactly (index_to_kb/skill_record default "inferred", skill_outcome
      default "secondary" — pinned by contract tests).
- [x] **PH5-2** — REFACTOR-2 (extract `goethe_kb.py`; MCP tool-list diff must be empty).
      **✅ SHIPPED (2026-07-18, Cowork, Goethe v0.4.1):** 14 KB/skill methods (goethe.py
      lines 4663–6067) moved verbatim to `KBMixin` in `tools/goethe_kb.py` (1435L);
      `Tools(KBMixin)` inherits — goethe_mcp discovers via `dir(inst)` so exposure is
      identical. goethe.py 7238 → 5851 lines. **Gates: MCP tool-list diff EMPTY (38/38
      pre/post), contract tests 420/420 green.** Gateway restarted on v0.4.1
      (pid verified, tokenless curl → 401). Raw sha: goethe.py `47d9fd659615d6a1…`,
      goethe_kb.py `82d4201dd69ddf2d…`. goethe.py growth unblocked.
      **Urgency re-assessed at TRAUM close (2026-07-13):** goethe.py is now
      7,228 lines (the "5819… do this before v0.4" bar above is stale — v0.4.0-a
      shipped anyway; TRAUM deliberately kept its ~140 goethe.py lines to the
      banner/digest read path and put everything else in new files). The
      original condition is now breached, not approaching: **schedule PH5-2
      before the next feature workstream that touches goethe.py**, and treat
      any further goethe.py growth as blocked on it.
- [x] **PH5-3** — REFACTOR-4 threat-model doc (`docs/threat-model-kb.md`) — includes the P0-2
      gateway exposure as its first worked example, plus KB poisoning origin-tags.
      **✅ COMPLETED (2026-07-18, Cowork, Goethe v0.4.2):** §5 written — P0-2 worked example
      (binding/CORS/token status verified live; rotation = the deferred residual) + §5.3
      still-open surfaces. Origin-tags IMPLEMENTED, not just documented: `index_to_kb origin=`
      ∈ {web, human, local-probe} stored on docs, `TrustPolicy.apply_origin` enforces
      web-never-mints-ground_truth (auto-downgrade to primary + warning). 4 new contract
      tests (TestOriginTags), suite 424 green. §2's stale "no origin=web tagging" claim
      annotated with an UPDATE pointer to §5.2.
      **PARTIAL (2026-07-12, TRAUM Prompt 4.7):** the file now exists with the
      DREAMING chapter fully worked (Shostack ×4, mitigations mapped to named
      contract tests). Still open: the P0-2 gateway worked example, and the
      origin-tags themselves — 4.7 found `origin=web/human/local-probe` tagging
      is NOT implemented in the live `index_to_kb` path (grep-verified), so the
      laundering mitigation is currently the blunt "dream never mints
      ground_truth" ceiling.

### Phase 6 — Arena, episodes, autonomy (parallel track, gated on Phase 1)

- [ ] **PH6-1** — **Episode actuation layer** (carried 1.7.0-a, still the arena P0): env executes
      model-emitted command blocks via SSH with goethe's safety gates ported; without it every
      write-mode challenge measures world state, not the model. `--eval --no-learn` flag;
      freeze `lse-bench-v1`; record Condition A baseline (bench/reports/ has 2 runs already).
- [ ] **PH6-2** — Carried arena items: net-t3-002 re-run (a3 assertion verification);
      Samsung TV DHCP hammer T2.5/T4 (rate measurement, lease-time confirmation, remediation
      spec); ChallengeGenerator assertion AST-validation before DB insert.
- [ ] **PH6-3** — Network Topology Challenge Series (T1 discovery → T2 analysis → T3 JSON+PNG
      deliverable) — see backlog section below for the full challenge specs.
- [ ] **PH6-4** — Occupational curriculum batches + learning-lift run #1 (A vs B) (carried
      1.7.0-d) — now unblocked: lse-skills index, skill lifecycle (record/outcome/archive), and
      demotion (Phase 1) all live.

---

## Workstreams — KB Trust Lifecycle, Sense of Time, Prove-It Tests (2026-07-02)

> Source: Cowork analysis of the RAG/KB corpus (`tools/goethe.py`, `rag/`, `eval/`, `skills/`),
> read against the four polar-star texts: Fowler (*Refactoring*), Ousterhout (*APoSD*),
> Hunt/Thomas (*Pragmatic Programmer*), Shostack (*Threat Modeling*).
>
> **Core findings (verified in code, not vibes):**
> 1. **lse-kb quality is monotonic upward.** `index_to_kb` takes `max(existing, new)`;
>    `mentor_correct` REJECTS any lower `new_quality` by design;
>    `record_outcome(success=False)` increments `failure_count` but **never touches
>    `quality_score`** — failure evidence is collected, then discarded from ranking.
>    Meanwhile `skill_outcome` on lse-skills already does it right: −0.15 verified
>    failure, floor 0.2 → auto-archive. The demotion pattern exists; it was never
>    ported to lse-kb. This is the regression gap (app updated → KB "ground truth"
>    silently wrong forever).
> 2. **Sense of time is prompt-level only.** DATE-SENSITIVE and YEAR-INJECTION rules
>    live in the `search_web` docstring; nothing is enforced server-side. No NTP
>    cross-check, no pretraining-cutoff comparison, no volatility TTLs on KB docs.
>    Qwen treating pretraining as gospel is exactly the failure mode Ousterhout says
>    to *define out of existence* rather than police with rules.
> 3. **No user-callable test surface.** Test assets exist (`rag/eval_retrieval.py`
>    with `--self-test`, `eval_goethe_rules.py`, `scripts/test_*.py`, gold set
>    `eval/retrieval-gold-v1.jsonl` @50 queries) but the model exposes no `run_tests`
>    tool — the user cannot say "prove it" and get pytest output as evidence.
> 4. **DRY violations & god-class risk (Fowler):** `_TIER_CEILING` dict duplicated 3×
>    (index_to_kb / skill_record / skill_outcome); goethe.py is a 5819-line single
>    class; per-version file copies are VCS-inside-VCS.
> 5. **Threat surface (Shostack, STRIDE-lite):** web-fetched content can be indexed
>    into KB (poisoning/prompt-injection path — tier ceilings mitigate but origin is
>    not tagged); NTP is unauthenticated (spoofable time source); a future test-runner
>    tool is an arbitrary-code-exec surface if paths are not scoped; the MCP gateway
>    is currently LAN-exposed with a git-committed token (see P0-2). Prior art: the
>    pfSense self-grant incident (P26) is exactly a Shostack "tampering with trust
>    metadata" case — the tier gate fixed elevation, demotion still ungated.

### Workstream A — KB-DECAY: trust lifecycle for lse-kb (demotion + regression)

- [x] **KB-DECAY-1** ✅ v0.3.0 — Port the skill_outcome demotion math to `record_outcome`:
      `success=False` + evidence (≥20 chars, same evidence gate as skill_outcome) →
      `quality_score = max(0.2, q − 0.15)`; add `consecutive_failures`; floor 0.2 →
      set `stale: true` (quarantine, NEVER silent-delete — keep for forensics).
      Success on a previously-failing doc resets `consecutive_failures` but regains
      quality only via the existing tier-gated paths (no free re-elevation).
- [x] **KB-DECAY-2** ✅ v0.3.0 — `search_kb` must surface the trust state: show
      `runs/success/failure` counts per hit; prepend `[STALE — quarantined, verify
      live before use]` banner on floored docs; penalize ranking by failure ratio
      (client-side rerank multiplier is enough — don't over-engineer ES function_score
      on day one; measure with the gold set first).
- [x] **KB-DECAY-3** ✅ v0.3.0 (two-phase: model supplies the probe output) — Make `verified_against` (stored since v1.7.11, consumed by
      NOTHING) actually work: new `kb_verify(doc_id)` tool — re-probes the recorded
      version/config snapshot against the live system (`get_github_release`, os
      probe, `read_file`); mismatch → auto `record_outcome(success=False,
      evidence=<probe output>)` with note "verified_against regression: fw X → Y".
      This is the "application updated → KB no longer relevant" detector.
- [x] **KB-DECAY-4** ✅ v0.3.0 — Human demotion path: `mentor_correct` keeps its raise-only
      rule (good — protects against model self-sabotage), but add explicit
      `mentor_demote(doc_id, new_quality, reason)` documented as human-authorized
      only, mirrored in system prompt. Today the ONLY way to say "this entry is
      wrong" is a competing entry — that leaves the poisoned high-quality doc
      outranking its correction.
- [x] **KB-DECAY-5** ✅ v0.3.0 (run on live lse-kb 2026-07-02) — Migration: add `stale`, `consecutive_failures`,
      `volatility` (see CHRONOS-3) fields to the lse-kb mapping via a
      `rag/08-kb-trust-migration.py` (idempotent, same pattern as 02-es-setup.py).

### Workstream B — CHRONOS: enforced sense of time

> Pipeline: system time → NTP cross-check → report/adjust discrepancy → compare with
> model pretraining cutoff → web-verify degradable datapoints. Enforcement must be
> server-side (injected into tool returns), not docstring pleading.

- [x] **CHRONOS-1** ✅ v0.3.1 (stdlib SNTP, no ntplib dep) — New tool `time_check()`: query ≥2 NTP servers (`pool.ntp.org`,
      `time.cloudflare.com`; ntplib, 2s timeout, graceful degrade to system clock
      with a WARN), report offset vs system clock in ms; offset >2s → surface
      discrepancy + suggested fix (`chronyc`/`timedatectl`), and log to lse-errors.
      *Threat note (Shostack): NTP is unauthenticated — require both servers to
      agree within bounds AND sanity-check against system clock + TLS date header
      from a known HTTPS endpoint before "adjust" is ever suggested. Never
      auto-adjust the clock; report and ask.*
- [x] **CHRONOS-2** ✅ v0.3.1 — Pretraining anchor: `MODEL_PRETRAIN_CUTOFF` valve (per-model,
      e.g. Qwen3.6 = its published cutoff). `time_check()` returns a banner:
      `[TIME] verified now=<date> | model cutoff=<date> | gap=<N months> — any
      version/price/CVE/firmware claim from model memory is presumed stale;
      web-verify before asserting.` Wire the same banner **server-side** into the
      first `search_kb`/`search_web` return of each session (cheap: cache a
      session flag) so compliance does not depend on the model reading docstrings.
- [x] **CHRONOS-3** ✅ v0.3.1 — Volatility classes on KB docs: `volatility: static|slow|fast`
      (default slow) with TTLs — static=∞ (topology facts change rarely), slow=90d
      (procedures), fast=7d (versions, CVEs, firmware, prices). `search_kb` computes
      age vs TTL and tags `[EXPIRED — pointer only, re-verify live]`, demoting the
      hit below fresh ones. This moves the existing docstring staleness table
      (30d/7d rules in search_web) into enforced metadata. Expired+re-verified →
      bump `updated_at` via `record_outcome(success=True)`.
- [x] **CHRONOS-4** ✅ v0.3.1 (went further: years stripped in code via `_strip_years`) —
      Retire YEAR-INJECTION/date rules from docstrings once
      CHRONOS-2/3 land (single source of truth — Pragmatic Programmer DRY: the
      rule lives in code OR prose, not both drifting apart).

### Workstream C — PROVE-IT: user-callable unit tests as evidence

- [ ] **PROVE-1** — New tool `run_tests(scope)` — scopes: `kb` (ES index probes +
      count sanity), `retrieval` (`rag/eval_retrieval.py --self-test`, and `--compare`
      when ES is up), `rules` (`eval_goethe_rules.py`), `harness`
      (`scripts/test_*.py` via pytest), `all`. Returns raw pytest/pass-fail output
      verbatim (it IS the evidence; feeds skill_outcome/record_outcome evidence
      gates). *Threat note: exec surface — hardcode the allowlisted commands per
      scope; NO arbitrary path/args from the model. Same pattern as the sudo
      allowlist (v1.7.17).*
- [x] **PROVE-2** ✅ SHIPPED 2026-07-02 (see PH1-1) — Contract tests for every KB-mutating tool function
      (`tests/test_kb_contracts.py`): tier ceilings hold, evidence gates reject
      thin evidence, demotion floors at 0.2, mentor_correct rejects lowering,
      dedup updates instead of duplicating. These are Fowler's safety net —
      **must land BEFORE Phase 5 refactoring starts.** Run against a
      throwaway ES index (`lse-kb-test`), never production indices.
- [ ] **PROVE-3** — Post-action assertion helper `assert_state(check_command,
      expected_regex)` (read-only allowlist: df/ss/systemctl is-active/curl -s
      health endpoints/sha256sum): turns "the model claims it worked" into "the
      model ran the check and the output matched". Surface in docstrings as the
      preferred `evidence=` producer. User phrase "prove it" → system prompt maps
      to run_tests/assert_state, never prose.
- [ ] **PROVE-4** — Wire `run_tests(scope=harness)` into the stack health-check
      skill and the eval-runner pre-run checklist (replaces "ask the user to
      confirm" rows where a command can answer).

### Workstream D — DATA: clean, always-relevant datasets (no HF/Kaggle)

- [ ] **DATA-1** — All gold/eval data is **self-harvested from own telemetry**:
      grow `eval/retrieval-gold-v2.jsonl` by mining the goethe log for real
      `search_kb` misses and mis-rankings (the q01 "classic miss" pattern —
      every real retrieval failure becomes a gold row); episode outcomes from
      `leaderboard.db`; skill `evidence_log` entries as verification-format exemplars.
- [ ] **DATA-2** — `scripts/dataset_lint.py`: JSONL schema validation (required
      fields per dataset type), duplicate-query detection, provenance field
      REQUIRED on every row (episode id / log line / incident doc — unattributed
      rows rejected, same rule as skill_record), expected-file existence check
      against `kb/`. Run in PROVE-1 `scope=all`.
- [ ] **DATA-3** — Freeze + fingerprint datasets like models: sha256 in
      `eval/SHA256SUMS`, version-bumped filenames (`freeze_bench.py` already does
      this for the bench — extend to gold sets). A changed gold set silently
      invalidates every historical eval number; the hash makes that loud.
- [ ] **DATA-4** — KB reseed hygiene: `03-kb-seed.py --reindex` must preserve
      trust fields (quality/stats/stale/volatility) — today a reseed would reset
      earned trust. Snapshot trust metadata before reindex, re-apply after
      (extend `kb-reseed-procedure.md`).

### Workstream E — SCRIBE: self-improving + auto-writing skill, next stage

> **⟶ ABSORBED INTO TRAUM (2026-07-11).** SCRIBE items below are retained for
> traceability but execute inside the TRAUM dreaming workstream —
> `docs/traum-dreaming-plan.md`. TRAUM adds what SCRIBE lacked: out-of-band
> post-session reflection (episode capture at the goethe_mcp gateway, an offline
> local-model dream runner for dedup/demotion/insight mining, gated apply path,
> nightly timer, and an A/B learning-lift eval). Mapping: SCRIBE-1→T1.5,
> SCRIBE-2→T1.7, SCRIBE-3→T1.6, SCRIBE-4→T3.7, SCRIBE-5→standing discipline.

> Today: `lse-session-debrief` (markdown append to session-learnings.md, human-
> confirmed, good format discipline) and the lse-skills loop
> (skill_record/skill_search/skill_outcome — evidence-gated, deduped, decays,
> auto-archives) are TWO disconnected memories. The debrief writes prose no
> retrieval loop consumes; the skills index never learns from debriefs.

- [x] **SCRIBE-1** ✅ DONE (2026-07-11, TRAUM Thread 1 Prompt 1.5) — Unify the
      write path: debrief Step 4 additionally proposes structured calls —
      facts → `index_to_kb(source_tier=..., verified_against=...)`,
      procedures → `skill_record(provenance="debrief YYYY-MM-DD")` — shown in
      the same human-confirm gate (one yes commits file + ES together; file
      remains the human-readable journal, ES the retrieval surface). Live in
      `skills/lse-session-debrief/SKILL.md`; format contract mirrored in
      `docs/dreaming/DESIGN.md` §6 for Thread 2's `dream_apply.py` to reuse.
- [x] **SCRIBE-2** ✅ DONE (2026-07-11, TRAUM Thread 1 Prompt 1.7) — Backfill
      distiller (`scripts/distill_learnings.py`): one-shot script proposing
      index_to_kb/skill_record candidates from the existing
      `kb/session-learnings.md` corpus; human reviewed a diff-style list
      (`docs/dreaming/backfill-review.md`), approved per-tier. **Run for real**
      against the live corpus — 197 candidates generated, 137 high-confidence
      approved and applied to production `lse-kb` (234 → 364 docs); 39 medium
      + 21 low confidence explicitly not approved this pass. Every applied
      entry carries `provenance=debrief-backfill-YYYY-MM-DD` (repudiation
      trace per Shostack).
- [x] **SCRIBE-3** ✅ DONE (2026-07-11, TRAUM Thread 1 Prompt 1.6) — Close the
      loop with decay: debrief template gains a "Contradicts existing KB?"
      step — before finalizing any `index_to_kb` proposal, `search_kb` for
      conflict (not just duplication); a genuine contradiction pairs
      `record_outcome(doc_id, success=False, evidence=...)` (uses KB-DECAY-1)
      with the correcting fact, never demotes alone. Live in
      `skills/lse-session-debrief/SKILL.md`. A real, live contradiction
      (`lse-kb` doc `a9361df7b6b60bb8`, Hermes port/auth doc still asserting
      decommissioned key-based auth) was found while writing this step and
      documented as the worked example — not yet applied, still requires
      going through the normal confirm gate like any other proposal.
- [x] **SCRIBE-4** ✅ DONE (2026-07-12, TRAUM Thread 3 Prompt 3.7 — continuous,
      not monthly: every dream run appends a retrieval-of-dreamed-docs section
      to its report + skills stats + month-over-month deltas; re-verified live
      against ES 9.4.3 on 2026-07-13's sanity pass) — original framing:
      monthly `run_tests(scope=retrieval)`
      + skills-index report (uses/successes/failures/archived count — data already
      in `stats`) appended to the debrief; the skill that writes learnings should
      report whether learnings are being retrieved (RFC-KB lesson: 0 calls in
      44,637 commands — build the usage counter in from day one).
- [~] **SCRIBE-5** — Run `lse-docstring-optimizer` on every new tool docstring
      added by A–D (kb_verify, time_check, run_tests, assert_state, mentor_demote)
      before deploy — eval regressions traced to docstring ambiguity are a known
      failure class.
      **PARTIAL ✅ (2026-07-03, pulled forward):** kb_verify, time_check,
      mentor_demote, plan_step_done audited + fixed (Goethe v0.3.5). Remaining:
      run_tests/assert_state when they land (PH3-1), and opportunistic passes on
      older docstrings. The v0.3.4 planner-gate conflict is a live example of why
      this audit must run BEFORE deploy, not after a field failure.
      **FURTHER ✅ (2026-07-11, TRAUM Thread 1 Prompt 1.9):** ran the audit over
      `skills/lse-session-debrief/SKILL.md` and `docs/dreaming/DESIGN.md` §6
      (the SCRIBE-1/3 text). Found and fixed a v0.3.4-class gate conflict
      (overloaded "skip" — a legitimate no-write result of running Step 1's
      duplicate check read the same as the forbidden "skipped a step") and a
      staleness risk in a worked example referencing live, mutable KB state.
      Standing discipline continues into Thread 2/3's new tool surfaces
      (`dream_runner.py`, `dream_apply.py`) when they land.

### Workstream F — REFACTOR: pay down before the next 1000 lines (Fowler/Ousterhout)

- [ ] **REFACTOR-1** — Extract `_TIER_CEILING` + evidence-gate logic into ONE
      module-level `TrustPolicy` (3 copies today → 1). Zero behavior change;
      covered by PROVE-2 contract tests first.
- [ ] **REFACTOR-2** — Extract KB layer (`search_kb/index_to_kb/record_*/
      mentor_*/skill_*` + `_embed/_es`) from the Tools god-class into
      `tools/goethe_kb.py`, goethe.py keeps thin delegating methods (deep module,
      shallow interface — the MCP gateway surface must not change; verify with
      `run_tests(scope=rules)` + goethe_mcp `--list` diff).
- [x] **REFACTOR-3** — folded into **P0-3** (purge superseded version copies).
- [ ] **REFACTOR-4** — Threat-model pass (Shostack 4-question frame) written as
      `docs/threat-model-kb.md`: what are we building (KB trust dataflow diagram),
      what can go wrong (poisoning via fetch_url→index_to_kb, tier self-grant,
      NTP spoof, test-runner exec, MCP gateway exposure P0-2, ES unauthenticated
      on LAN), what do we do (origin tags: `origin: web|local-probe|human` on every
      KB doc — web-origin can NEVER carry source_tier=ground_truth without a local
      probe corroboration), did we do a good job (contract tests assert each
      mitigation).

---

## Backlog — SearXNG

- [ ] **Defense-in-depth: tighten arxiv to science-only in settings.yml** — the tool now
  requests `general` only (fixed v1.7.8), but arxiv's `categories: [science, it, technology]`
  means any future `it`/`technology` query would re-pull it. Low priority. Verify canonical
  settings path via docker exec read before editing.
- [ ] **[P1] searxng-error-exporter** — Grafana "Failing engines" panel (Panel 24) shows 0.
  Without this, silently-failing engines (e.g. cvedetails 403) are invisible until manual
  diagnosis. Scrape SearXNG `/metrics`, parse `searx_engine_*` counters, expose
  `searxng_engine_errors_total{engine,error_type}` on :9840. Replaces the stale searxng-logger
  approach (do together). Deploy as systemd service alongside other exporters.
- [ ] **[P1] NVD custom SearXNG engine** — cvedetails.com VPS blocked (403). CVE search critical
  for security audit challenges. Custom engine hitting NVD REST API directly:
  `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=<q>&resultsPerPage=10`;
  rate 5 req/30s unauth. Deploy `/usr/local/searxng/searx/engines/nvd_api.py` via volume mount;
  categories `[it, security]`, weight 3. Workaround until built: `site:nvd.nist.gov <CVE-ID>`.
- [ ] **URL redirect leak fix** — google.com/search?q= URLs in results. SearXNG parser issue.
  NOTE (2026-07-02): image is now PINNED to `searxng/searxng:2026.5.8-d8ab61a9e` in
  docker-compose.yml — do NOT `docker pull latest`. Upgrade path: pick a newer explicit tag,
  `docker manifest inspect` it, update the compose pin, staging test, then roll.
- [ ] **Reddit engine** — blocked on VPS IPs for anonymous access. NOTE (reconcile 2026-07-02):
  Goethe v0.2.5 shipped the Firecrawl/camoufox browser fallback for reddit URLs in `fetch_url`,
  and `search_reddit` exists — the SearXNG-engine-level fix is now lower priority. Options if
  still wanted: (a) Reddit OAuth app + bearer token, (b) site:reddit.com via Google (current).
- [ ] **Google Scholar** — 0% reliability, VPS IP blocked. Debug via docker exec curl;
  re-enable checklist in `docs/searxng-operations.md`.

---

## Backlog — Network Topology Challenge Series

> **Goal:** A progressive set of challenges whose collective deliverable is a high-quality
> illustrated network topology diagram with vendor icons — comparable to Cisco Visio-style
> diagrams. The LSE model discovers, validates, and documents the topology; the final
> challenge renders it as a PNG using the `diagrams` Python library (diagrams.mingrammer.com).
> Each challenge is independently solvable and feeds structured data into the next.

### T1 — Discovery Layer
- [ ] **net-t1-013 Subnet Host Enumeration** — nmap sweep of all three subnets (1.x, 5.x, 10.x).
  Note: 192.168.1.x includes ALL WiFi devices (AP at 192.168.1.1 bridges WiFi into LAN).
  192.168.10.x is dedicated wired IoT only (solar inverter). Expect most IoT on 1.x, not 10.x.
  Produce: JSON list of `{ip, mac, hostname, open_ports[], vendor}` for each live host.
  Assertions: a1=hosts found on each subnet, a2=MAC vendors resolved, a3=JSON written to KB.
- [ ] **net-t1-014 pfSense Interface Inventory** — enumerate pfSense interfaces, IPs, and
  assigned subnets via `pfsense_query("/api/v2/network/interface")`.
  Produce: `{interface, description, ip, subnet, connected_to}` per interface.
  Assertions: a1=3+ interfaces found, a2=each subnet mapped to interface, a3=KB indexed.

### T2 — Analysis Layer
- [ ] **net-t2-012 DNS Architecture Audit** — verify *.home.arpa resolution via DNS queries.
  Method: `dig +short @192.168.1.50 <host>` from LUCIFER — read-only, no API/SSH needed.
  ⚠️ Do NOT use SSH to pfSense or attempt to read /var/unbound/unbound.conf — SSH admin = root,
  bypasses the read-only API boundary. DNS queries are the correct read-only verification path.
  Confirm: pfsense/homeassistant/n45 resolve correctly. Identify gaps (lucifer, node2 = NXDOMAIN).
  Assertions: a1=known hosts resolve to correct IPs, a2=gap hosts return NXDOMAIN (documented),
  a3=resolution report produced with all 3 subnets' static hosts tested.
- [ ] **net-t2-013 NAS Subnet Topology** — map 192.168.5.0/24 physical topology.
  Discover Netgear switch (IP, model via SNMP/nmap), confirm NODE2 presence and MAC.
  Assertions: a1=switch identified, a2=all 5.x hosts mapped with MAC, a3=topology JSON produced.
- [ ] **net-t2-014 DHCP Static Mapping Audit** — enumerate all pfSense static DHCP mappings.
  Identify: which hosts have static mappings, which are dynamic, hostname coverage gaps.
  Assertions: a1=static mappings retrieved, a2=dynamic hosts identified, a3=gaps documented.

### T3 — Deliverable Layer
- [ ] **net-t3-003 Network Topology JSON** — produce a validated topology document combining
  all T1/T2 findings into a single canonical JSON:
  `{subnets[], hosts[], connections[], dns_entries[], missing_dns[]}`.
  Assertions: a1=all 3 subnets present, a2=all known hosts present with MAC+hostname,
  a3=JSON validates against schema.
- [ ] **net-t3-004 Network Topology Diagram** — render topology as PNG using `diagrams` library.
  Requirements: vendor icons, per-subnet clustering, labeled links. Input: net-t3-003 JSON.
  Assertions: a1=PNG rendered, a2=all subnets/hosts from JSON present, a3=file written to repo.

---

## Backlog — Arena

- [x] **Ground-truth assertion verifier (`verify_ssh`)** ✅ RECONCILED 2026-07-02 — shipped:
  `lse_challenge_env.step()` runs `verify_ssh` ground truth and overrides model self-report
  (confirmed in the P20 root-cause note). Original design (node-t3-002 hallucination incident)
  kept in git history. Remaining related gap is the actuation layer → **PH6-1**.
- [ ] **Samsung TV T4** — DHCP hammer confirmed firmware noise (lease 7200s normal).
  Design challenge: measure DHCP rate from MAC 1c:af:4a:04:5f:b6 via DHCP logs,
  confirm lease time is not the cause, document remediation options (rate-limit UDP 67/68).
  Assertions: a1=DHCP request rate measured, a2=lease time confirmed normal (>3600s),
  a3=remediation documented (rate-limit rule spec or benign-noise classification).
- [ ] **net-t3-002 re-run** (optional) — a3 was patched after the solve. Re-run to confirm
  `write_access_verified_inactive` assertion works with the API probe approach.
- [ ] **ChallengeGenerator quality** — llama3.2:3b produces broken assertions (a2 bug in
  Samsung T2 proposal). Validate assertions with AST parse before inserting to DB.
- [ ] **node-t3-006 "Model Store Reconciliation"** — design with inode-level assertions
  (replaces retired node-t3-005 — premise was false; see CHANGELOG P21).

---

## Backlog — Infrastructure

- [ ] **Local DNS Architecture** — converge all hosts to coherent `*.home.arpa` naming.
  Confirmed via `dig @192.168.1.50` (2026-06-06): `pfsense`, `homeassistant`,
  `n45` (both NICs — failover, both MACs in static DHCP) ✅. `3090.home.arpa` → 192.168.5.41 ✅.
  Missing (add in pfSense DNS Resolver → Host Overrides):
  - `lucifer.home.arpa` → 192.168.1.57 · `4090.home.arpa` → 192.168.1.57 (GPU alias)
  - `5090.home.arpa` → node5090 IP (after setup)
  GPU naming strategy: DNS aliases only — machine hostnames unchanged.
  Work items: audit host overrides via `pfsense_query("/api/v2/services/unbound/host")`;
  PTR records for readable firewall logs; update NETWORK_CONTEXT + KB docs to hostnames.
  Design as arena challenges (see Topology Series). Ref: RFC 8375.
- [x] **node3090 commissioning** ✅ RECONCILED 2026-07-02 — fully commissioned: llama-server
  :8080 (Qwen3.6-27B, 96k ctx), local goethe_mcp :9700 + ES + Ollama, Firecrawl :3002 +
  camoufox. The old "NODE2 — LM Studio server mode :8081" item is superseded.
- [ ] **node5090 (NODE3)** — WoL/SSH setup deferred; WSL2 install, llama-server deploy,
  test `wsl-gaming-teardown.ps1`; then `5090.home.arpa` + 35B-A3B coding-delegation experiments
  (carried from v1.7.0 — model shootout Runs 3–4 first: Qwopus 35B vs Qwen3-Coder 30B).
- [ ] **Kostal Smart Energy Meter** — disconnected, pending integration on 192.168.10.x (OPT2).
  When connected: static DHCP mapping, `kostal.home.arpa`, HA integration.
  Design as arena challenge: `ha-t2-003` Energy Meter Integration.
- [ ] **Launcher docker container visibility** (carried) — show ALL running docker containers +
  resource usage in the LSE Stack launcher GUI (≥1.078). Launcher repo:
  `C:\Users\SY5\Claude\Projects\LSEStack_gui` (edit there, sign SY5TEM5Cert —
  `docs/08-launcher-edit-workflow.md`). Source: `docker stats --no-stream --format json`.
- [ ] **Tool-call ceiling under llama-ui** (rewritten 2026-07-02; was "16-tool-call limit") —
  the OWUI-era investigation (Admin → Models → Max Tool Calls) is obsolete. Re-test on the
  current stack: llama-ui + goethe_mcp — count sequential MCP calls until stall; candidates now:
  llama-server/llama-ui loop cap, Qwen3 self-termination, context_monitor CRITICAL yield.

---

## Backlog — Faust multi-agent planning protocol (carried from 1.7.0-b)

> Coordination lives in **Faust** (`Faust/`) — realtime group-chat, humans + local-model agents
> as first-class room participants (REST + WS + SQLite). Hermes push channel retired.
> Design: `docs/lse-1.7.0-b-faust-planning-design.md`.

- [ ] **Planning state machine** — PLANNING (round-robin proposals, ≤5 rounds, vote
  `[[CONVERGED]]`) → AWAITING_APPROVAL (moderator posts plan; human `/approve` or `/revise`) →
  TASKING (`@handle: <task>`, emit `[[DONE]]`) → IDLE (assignment ledger; mention-reply resumes).
  Implementation (additive): `planning.ts` `PlanningController` + `PlanningPolicy implements
  SpeakerPolicy` + one `onTurnComplete` server seam. Moderator framing as `role:"assistant"`.
- [ ] **Plugin integration** — fold `gate3-plugin-forge` into `gate2-group-server` so one
  `npm start` serves chat + plugins + UI. Seams exist (`onMessage`, `staticFiles`).
  `exec` capability omitted (no sandboxed runner on host).
- [ ] **Repo sanity (Faust)** — `git config core.fileMode false` (86 files of mode churn);
  remove `archive/*.py` cogitator forks, `archive/stale-gate3-root/`, `src/server.ts.bak6e`;
  delete stale `.git/index.lock` (Windows-side).
- Deferred: real-time typing (model streaming + delta WS envelope + UI), SQLite persistence of
  plan state, wiring assignments to real agent work-loops.

---

## Backlog — Multi-Agent UI (Dify)

> Reconciled 2026-07-02: deployed v1.14.2, on-demand, port 4000, `/opt/dify`. The OWUI pipe
> function item is dropped (OWUI retired). **Decision pending:** Faust rooms may supersede the
> Dify workflow use case entirely — evaluate after the Faust planning state machine lands.

- [ ] **Dify model connections** — add providers: LUCIFER llama-server `http://192.168.1.x:8080/v1`
  (orchestrator) + node3090 llama-server `http://192.168.5.41:8080/v1` (executor). Model string
  must match what the server reports.
- [ ] **Dify pfSense workflow** — User → Qwen3.6 orchestrator → structured LSE prompt → LSE node
  (goethe_mcp HTTP call) → streamed output; human-in-the-loop approval node; persistent history.

---

## Deferred — Zero-Persistence Trust (ZPT) Architecture

> **Definition:** A session-scoped secret architecture where no operational secret persists
> on disk between sessions. A physical USB key is the session gate — present to start,
> removed to terminate all secret access. Extends Zero Trust with a physical persistence
> boundary: even a fully compromised host cannot access secrets after USB removal.
> **2026-07-02 note:** the P0-2 finding (MCP token hardcoded in a committed script) is exactly
> the failure class ZPT eliminates — P0-2 is the tactical fix, ZPT the strategic one.
> **STATUS CHANGE (2026-07-02, operator):** ZPT is now the COMMITTED security direction, not
> just deferred exploration — all secrets move to an external file on a USB key (→ tmpfs).
> `tools/start-goethe-stdio.sh` was written ZPT-ready: its single `source` line is the only
> change needed when the USB/tmpfs layout lands.

### Design Principles

1. **Single physical gate** — USB presence is the only requirement to start a session.
   No USB = no secrets = no session. Removes the "always-on credential" attack surface.
2. **Load-once, session-scoped** — Secrets are read from USB once at launch into tmpfs
   (`/run/lse-secrets/`). tmpfs is wiped on unmount/reboot. No disk writes.
3. **Secret tiering by access frequency:**
   - `HIGH FREQ` (pfSense API key, HA token, HF_TOKEN, GOETHE_MCP_TOKEN) → USB → tmpfs
   - `LOW FREQ` (user passwords, OAuth tokens) → Vaultwarden only
   - `GATE KEY` (Vaultwarden master password) → USB only, never written to disk
4. **Vaultwarden role narrows** — store for secrets requiring human-level protection or rare
   access. High-frequency operational keys bypass it entirely.
5. **Plaintext env secrets removed from `.bashrc`** — currently exposed. Must move to
   USB → tmpfs load before ZPT can be considered complete.

### Implementation Tasks (deferred)

- [ ] Audit all plaintext secrets currently in `.bashrc`, `.lse/secrets`, env vars, launch scripts
- [ ] Design USB filesystem layout (encrypted LUKS partition recommended)
- [ ] Modify launcher — USB presence check + secrets load to tmpfs
- [ ] Replace `.bashrc` `export HF_TOKEN=...` with tmpfs-loaded env injection at launch
- [ ] Write shutdown hook — wipe tmpfs on session end / USB removal
- [ ] Design as arena challenge: `infra-t3-003` ZPT Bootstrap (T3, security, 1.5×)
- [ ] Test: disconnect USB mid-session → verify new secret fetches fail gracefully

---

## Deferred — `lse-canon` (principle corpus + review gate)

> **Definition:** A KB topic seeded with **distilled, checkable principles mined from the
> field-defining canon**, plus an intermediate **review gate** (a skill) that runs after the
> model completes a unit of work and before it claims done — it retrieves the relevant
> principles and cross-references the diff against them, then the model course-corrects. The
> generalized examiner: the harness catches what is *encoded as a test*; this catches design /
> security / craft issues that aren't. Named *biblos* — striving.
> **2026-07-02 note:** same four polar-star books now drive the Workstreams A–F analysis —
> lse-canon is the mechanism that would make that review repeatable by the local model itself.

### The canon (best-in-field; seed source)

- **Design / complexity** — *A Philosophy of Software Design*, John Ousterhout.
- **Craft / smells → fixes** — *Refactoring* (2nd ed), Martin Fowler.
- **Engineering judgment** — *The Pragmatic Programmer* (20th-anniversary ed), Hunt & Thomas.
- **Security depth** — *Security Engineering* (3rd ed), Ross Anderson **(free)**.
- **Security as verifiable checklist** — **OWASP ASVS + Cheat Sheet Series (open)**.
- **Threat modeling** — *Threat Modeling: Designing for Security*, Adam Shostack.
- (optional judgment axis: *The Mythical Man-Month*; Polya *How to Solve It*.)

### Design principles

1. **Distill, don't ingest prose.** RAG over book chunks ≈ pattern-matching, not insight.
   Seed the KB with **structured principles** (smell → why → fix; ASVS-style requirement →
   how to verify), not raw text. The value is the **retrieval anchor + forced cross-reference**.
2. **Respect copyright.** Anderson + OWASP are free/open → ingest wholesale. The four
   copyrighted books → seed **own paraphrased principle notes** only (also the more effective form).
3. **Gate placement** — between "harness green" and "claim done." Diff → retrieve top-K
   principles per axis (design/security/correctness) via `search_kb`/RRF → structured critique
   (principle → honored|violated → fix) → model revises before done.
4. **Measure it (Galilean).** Run gauntlet gates with vs without the review gate; McNemar the
   outcomes. Adopt only if it catches more than it costs in tokens — null result is a result.

### Implementation tasks (deferred)

- [ ] `lse-canon` ES topic + schema (principle_id, axis, source, statement, smell/anti-pattern,
      check, fix, severity) — reuse the `lse-kb` index conventions.
- [ ] Seed 15–20 starter principles (Ousterhout + Fowler + ASVS) as the v0 corpus.
- [ ] `canon-review` skill: diff → per-axis retrieval → structured critique → revise loop, with a
      give-up budget; wire as the gauntlet's pre-"done" gate.
- [ ] A/B measurement run (review-gate ON vs OFF) on Gate 2/3-class tasks; McNemar.
- [ ] Cross-family critic (GLM) as an alternate/parallel reviewer — compare canon-RAG critique vs
      cross-family critique vs both.

---

## SSH COMMAND= PROTOCOL — read-only SSH escalation

When a challenge requires read access to pfSense or another host's filesystem that is
not exposed via REST API, the approved pattern is OpenSSH `command=` in authorized_keys:

```
command="<exact read-only command>",no-pty,no-port-forwarding,no-agent-forwarding ssh-ed25519 AAAA...
```

This locks the key to one specific command — the SSH client cannot request a shell or
run anything else. The key is added by a human (setup step) before the challenge runs.

Rules:
- One key per command — never reuse a `command=` key for a different operation
- Command must be read-only (grep, cat, dig, etc.) — never write/restart/edit
- Key is added to the target host's `~/.ssh/authorized_keys` by the human operator
- Document the key and command in the challenge's `starting_state` / pre-requisites
- Remove the key after the challenge series is complete

This is NOT general SSH access. It is a scoped, auditable, read-only channel.
Full SSH access to pfSense (admin shell) remains human-only — never delegated to LSE.

---

## WRITE ACCESS PROTOCOL — permanent rule

pfSense REST API is read-only by default. For T3+ write challenges:
1. Enable write in pfSense UI (System → REST API → disable Read Only) immediately before task
2. Complete task and verify
3. Re-enable Read Only before ending the session
4. Log in CHANGELOG: timestamp + what was changed

Verify re-enabled: `pfsense_query('/api/v2/firewall/rule', method='PATCH', payload={})` should return 403.
**NOTE:** `/api/v2/system/api` returns 404 — read-only toggle NOT available via REST API, web UI only.
**SECURITY INVARIANT (clarified 2026-07-02, operator):** the REST API exposes the *enabling*
bit for read-only but NOT the *disabling* bit — write access can only ever be granted through
the web UI by a human. This asymmetry is the load-bearing control on the most critical point of
the infra: no agent (LSE, Claude via MCP, or any API caller) can self-escalate pfSense to write
mode. Any future pfSense-API version bump must re-verify this asymmetry still holds before
deploy (add to kb_verify targets once KB-DECAY-3 lands).
