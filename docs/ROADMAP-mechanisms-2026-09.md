# ROADMAP — Gateway Mechanisms (2026-09)

Source: adapted from an external agent architecture (mechanisms only, 2026-09).
Decision: adopt the mechanisms, not the surface. We keep the verification-first
trust layer (evidence gates, verify_source_claims, tier-gated demotion) and add
the code-driven runtime machinery.

## Status

| # | Phase | Status |
|---|-------|--------|
| 1 | Exact context accounting + rolling compaction | DONE 2026-09-17 (accounting live; compaction DORMANT under Studio — docs/03 §7) |
| 2 | Progressive tool loading | DONE 2026-09-17 (54.0% envelope reduction; CORE/COLD tiering + tool_search/tool_invoke bridges, EAGER_TOOLS=1 fallback — docs/05-skills-planning.md §4) |
| 3 | Scoped child delegation | OPEN |
| 4 | Restart recovery semantics | OPEN |
| 5 | Graph layer over the KB | OPEN |

Order is intentional: 1 and 2 shrink the fixed prompt envelope and make long
sessions survivable; 3 and 4 need 2 (children get the core tier) and 1
(children run long); 5 is independent but last because it changes recall
behaviour everyone else depends on.

---

## Phase 1 — Exact context accounting + rolling compaction

### The mechanism (adapted) (the mechanism to steal)
- Counts the **complete next provider input**: system prompt + full history +
  projected tool responses + **exact bound tool schemas**, together, every call.
- **Fixed-envelope preflight**: if prompt+schemas alone cannot fit the window,
  the turn stops with an exact capacity message (no compaction can save it).
- **Auto rolling compaction at 75%** of effective limit: compacts complete
  older turn groups (keeps ≥2 recent complete turns, keeps tool call/result
  pairs atomic), summary persisted behind **compare-and-swap** against the
  checkpoint revision, then the **real request is rebuilt exactly** and
  re-validated before the summary is saved.
- Compacted history re-enters as an explicit **untrusted `HISTORICAL_CONTEXT`
  boundary**, subordinate to the newest raw user instruction.

### Goethe today (2026-09-17, verified)
- `tools/context_monitor.py` (280 lines): polls llama-server `/slots`
  (`n_past`/`n_ctx`/`kv_cache_usage_ratio`). **Observe-only** — P22 lesson:
  "the context-monitor filter can watch but not intervene."
- `get_context_status` (goethe.py) surfaces the same numbers to the model.
- `compact_context` (goethe.py:2147) can **write chat history directly** —
  the actuation path exists — but it sits in `SKIP_TOOLS`
  (goethe_mcp.py:172): hidden from the tool list, purely manual.
- Handoff at 70% is a **prose protocol** in the system prompt (model attention
  based). Demonstrated failure: P22 session — 34 searches, budget exhaustion,
  monitor never triggered.

### Design
1. **Accounting in the gateway** (goethe_mcp.py):
   - Fixed envelope = byte size of the 48 tool schemas + system prompt.
     Computed **once per register()** (schemas are static) and cached.
   - Live fill = `/slots` `n_past` (existing fetch, context_monitor.py:60).
   - `projected_next_input = n_past + envelope + reserve` (reserve = valve,
     default 2000 tokens for the next tool round-trip).
   - `get_context_status` returns exact numbers: envelope, n_past, projected,
     effective limit, compact-at threshold, hard-stop threshold — not a ratio
     the model has to interpret.
2. **Auto-compaction actuation** (gateway side, code-enforced):
   - Thresholds (valves): `COMPACT_AT=0.70`, `HARD_STOP=0.85` of n_ctx.
   - At COMPACT_AT: gateway triggers a compaction pass — summarise aged turns
     via the planner backend (already has chat-completion plumbing,
     goethe_planner.py `_post_chat_completion`), rewrite history through the
     existing `compact_context` write path.
   - **CAS guard**: summary records (session revision, message count,
     envelope fingerprint). If the session moved on, the stale summary is
     dropped, not applied. ( compare-and-swap, simplified to a
     revision counter — we have no concurrent writers, only time skew.)
   - **Validated rebuild**: after rewrite, re-query `/slots`; if the new
     `n_past` is not below COMPACT_AT, the rewrite is rolled back (the
     compact_context write path keeps the previous history blob — add a
     snapshot line, mirroring write_file's recovery-snapshot pattern).
   - Compacted history enters with an untrusted-history header (`HISTORICAL_CONTEXT` convention) so the model treats it as reference,
     not instruction.
3. **Documentation**: extend `docs/03-context-management.md` §2.2 with the
   accounting model and new thresholds; update the system-prompt HANDOVER
   PROTOCOL to say compaction is now code-driven (handoff stays for ≥70%
   *projected*, as the human-visible escalation).

### Verification
- Unit: accounting math against a mocked `/slots` (envelope + n_past +
  reserve → projected; threshold crossings).
- Live: long session (planner task, 5+ steps) — evidence = `/slots`
  before/after an auto-compaction + session continuing without user
  intervention + summary revision log line.
- Rollback: force a failed rewrite (mock n_past unchanged) → history intact.

### Risks
- Unsloth Studio owns the inference loop; the gateway rewrites history via the
  existing direct-write path — Studio must re-read it on the next turn.
  Validate this assumption FIRST (probe: does a compact_context rewrite
  actually change the next model input?). If Studio caches the prompt, the
  actuation point moves to Studio config or a fresh-session handoff.
- Compaction quality on a 27B local model — use the planner backend
  (Qwen 27B on node3090) for summaries, not the session model itself.

---

## Phase 2 — Progressive tool loading

### The mechanism (adapted)
- **Recommended Auto loading**: permitted core tools bound directly; enabled
  external MCP/plugin/custom-tool schemas kept in an **immutable authorized
  catalog** and searched+invoked **on demand** via bounded bridges. Eager mode
  remains available as fallback.

### Goethe today
- `register()` (goethe_mcp.py:841) exposes **every public method** of every
  module — 48 tool schemas in every prompt. Only escape hatch is
  `SKIP_TOOLS` (line 172). Every byte of every docstring (and the docstrings
  are long — they carry the policy) is paid on every single model call,
  including trivial ones.

### Design
1. **Tiering** (valve `CORE_TOOLS`, default list below; everything else is
   COLD):
   - CORE (≈14): execute_command, read_file, write_file, ssh_run, ssh_script,
     sudo_delegation_block, search_kb, search_web, fetch_url, index_to_kb,
     record_error, check_error_kb, planner, plan_step_done, task_resume,
     assert_state, get_context_status, compact_context (re-exposed).
   - COLD (≈30): pfSense trio, vault trio, net-discovery trio, node lifecycle
     (wake/start/stop/shutdown/query/drift), mentor_*, kb_verify,
     record_outcome, skill_*, run_tests, monitor_download, time_check,
     task_checkpoint, nmap_summary, verify_source_claims, get_github_release,
     search_reddit, orchestrator tools.
   - Safety-critical gates (sudo_delegation_block, mentor_demote,
     record_outcome, plan_step_done) **never** go cold — they must be visible
     when the user's words trigger them.
2. **Bridges** (2 new CORE tools, small docstrings):
   - `tool_search(query)` → search cold tool names+docstrings (keyword, no
     LLM needed — 30 tools is a grep, not a RAG problem) → returns top-3
     full schemas.
   - `tool_invoke(name, args_json)` → schema-validated dispatch into the
     existing register() machinery. All docstring gates (evidence,
     confirmation, KB-first) still apply — validation happens in the tool
     body, not at bind time, so nothing weakens.
3. **System prompt**: the "48 tools" line becomes "16 core tools +
   tool_search/tool_invoke for the long tail." Request-shape mappings that
   name cold tools keep working (the model searches, finds, invokes).
4. **Fallback valve** `EAGER_TOOLS=1` restores today's behaviour for evals.

### Verification
- Envelope measurement: `len(json.dumps(all schemas))` before/after —
  target ≥50% reduction. sha256 of the tool list in a log line.
- End-to-end: fresh session asks for a cold capability (e.g. "check pfSense
  DHCP leases") → model runs tool_search → tool_invoke → correct result.
- `run_tests(scope=rules)` before/after (the LLM-behavior eval is the real
  regression net for a smaller envelope).
- Budget: search-web-blowout session (P22 replay) — fewer wasted tokens.

### Risks
- 27B local model may not search for tools it was told exist but can't see —
  the system prompt must name the long-tail categories explicitly (it partly
  already does via request-shape mappings). Eval first, tier second: start
  with the smallest cold set (orchestrator + net-discovery), measure, expand.
- Docstring policy text that only exists in cold tools (e.g. vault protocol)
  must survive — it does: tool_search returns the full docstring.

---

## Phase 3 — Scoped child delegation

### The mechanism (adapted)
- **Durable parent/child orchestration**: required vs detached child runs,
  dependency ordering, **folder-scoped writer locks** (parallel children, one
  writer per folder), required results **rejoin the same parent turn**,
  checkpoint-safe work budgets, restart recovery.

### Goethe today
- Planner ledger (`task_blocks` in tasks.db, goethe_planner.py:1263) is
  strictly **linear**: one packaged step at a time, `plan_step_done` loop.
- Node agents (query_node_agent) are stateless one-shot queries — no
  durable child identity, no rejoin.
- Orchestrator (goethe_mcp.py:317, ray backend) exists for infra fan-out but
  is not wired into the ledger.

### Design
1. **Ledger extension** (schema migration, additive):
   `child_runs (child_id, parent_task_id, scope, node, kind[required|detached],
   status[queued|running|done|failed|cancelled], result, depends_on,
   writer_lock, created, finished)`.
2. **Tools**:
   - `delegate_child(task_id, scope, prompt, node="", kind="detached")` →
     spawns a durable child: query_node_agent for node-scoped work, planner
     backend for pure-reasoning work. scope = path prefix or resource tag.
   - Writer lock: a second child with overlapping scope waits (or is refused
     for kind=required). One writer per scope — folder lock,
     generalised.
   - Required children **block plan_step_done** on the parent step that
     depends on them; results rejoin the ledger and are injected into the
     next packaged prompt verbatim.
   - `child_status(task_id)` → compact table.
3. **Budgets**: per-parent child cap (valve, default 4 concurrent, 8 total) —
   Delegation limits, simplified.

### Verification
- Two-node task (node3090 + node5090) with one required child each → both
  results present in parent ledger; step prompt quotes them.
- Overlapping-scope contention: second child refused/queued (log line).
- Kill mid-child → Phase 4 recovery picks it up (cross-phase test).

### Risks
- Children on 27B node agents have no tools (query_node_agent contract) —
  child prompts must be self-contained. Keep children to bounded,
  verifiable scopes (one query, one report).
- Scope-lock granularity: start with exact-match scopes, no prefix
  inference, until evals show it's needed.

---

## Phase 4 — Restart recovery semantics

### The mechanism (adapted)
- On restart: **closes unanswered tool calls without replaying them**;
  resumes the saved parent when required child results are ready;
  orphaned tool calls repaired, never re-executed.

### Goethe today
- Ledger survives restart (tasks.db) — but an in-flight step has no
  interrupted state. `task_resume` returns the next pending step as if the
  previous one never happened. A mutating step that completed its side
  effect but not `plan_step_done` gets **re-executed** on resume.

### Design
1. **In-flight marking**: `plan_step_done` (and `delegate_child`) stamp
   `step.status = in_progress` + timestamp when the step prompt is issued;
   gateway startup sweep finds `in_progress` older than the process start →
   marks `interrupted`.
2. **task_resume output** for an interrupted step: explicit banner
   "Step N was interrupted after its prompt was issued. Re-verify current
   state before re-executing. READ-ONLY steps: resume directly. MUTATING
   steps: verify side effect first (assert_state), then either
   plan_step_done with existing evidence or re-execute."
3. **No auto-replay, ever**: the gateway never re-issues a tool call on
   restart. Recovery is a prompt decision with evidence, not a queue drain.
4. **Child runs**: `interrupted` children with no result are re-queued
   (they are bounded queries — replay-safe by construction); children with a
   partial result are reported, not replayed.

### Verification
- `kill -9` the gateway mid-step (fresh planner task) → restart →
  task_resume shows the interrupted banner; side effect executed exactly
  once (evidence: file mtime / log line count).
- Interrupted child re-queued once; no double node query (node log).

### Risks
- Distinguishing "side effect landed" from "didn't" is fundamentally the
  evidence-gate problem — the design deliberately pushes it to the model
  with assert_state, which is exactly how the trust layer already works.
  Do not try to make it automatic.

---

## Phase 5 — Graph layer over the KB

### The mechanism (adapted)
- Personal knowledge graph: 10 entity types, 67 typed relations, bounded
  semantic/lexical/**graph** recall, duplicate merging, stale-confidence
  decay, graph visualization.

### Goethe today
- Three flat ES surfaces: lse-kb (~346 docs/node), lse-skills, lse-errors.
  Cross-doc structure lives in prose (doc bodies mention nodes, ports,
  doc_ids) — unqueryable. Per-node indexes; NAS unifies files, not vectors
  (KB doc 947eebc90baa8cdd).

### Design
1. **Storage**: new ES index `lse-graph` — two doc types: `entity`
   (id, type, name, attrs) and `edge` (src, rel, dst, evidence_doc_id).
   Types (start small, 6): node, service, model, port, credential, procedure.
   Relations (start, 8): runs_on, serves, documented_by, caused, fixed_by,
   supersedes, uses_credential, part_of.
2. **Extraction**:
   - Inline: `index_to_kb` gains an optional extraction pass (planner backend,
     best-effort, never blocks the index write) → entities/edges with
     `evidence_doc_id` backlink.
   - Backfill: a **dream pass** (dream_runner.py seventh pass) extracts from
     all 346 docs; proposals go through the existing Human Gate — the graph
     never self-writes, mirroring TRAUM's discipline.
3. **Recall**: `search_kb` appends a bounded **one-hop** expansion: top-k
   docs → their documented_by/runs_on entities → linked docs, deduped,
   max +5 results, clearly labelled `related via: <entity>`. Semantic and
   lexical paths untouched — graph is additive, so a bad extraction degrades
   to today's behaviour.
4. **Ops**: `graph_query(entity, rel="")` tool (read-only) for "what runs on
   node3090" style questions. Visualization deferred (Grafana panel later,
   not now).

### Verification
- Backfill completes on the live index (run report, counts).
- Query: "node3090" → graph union includes its services/models docs that a
  pure semantic search misses (before/after top-5 diff).
- Human Gate: extraction proposals appear in traum-state.db as proposals,
  none applied without adjudication (sqlite count).

### Risks
- Extraction noise on 27B — keep the entity/relation vocabulary fixed and
  small (6/8); free-form entity types are how the 67 relations become
  a graph soup eventually.
- Per-node duplication: graph index is per-node like lse-kb; NAS file layer
  stays the doc source of truth, graph is derived.

---

## Cross-cutting rules (all phases)

- Every phase ships behind a **valve** with the old behaviour as the default
  off-state until its verification passes (EAGER_TOOLS, COMPACT_AT=0,
  CHILD_CAP=0, GRAPH_RECALL=0).
- Evidence gates are load-bearing: no phase may weaken an existing gate.
  Phases that touch plan_step_done/record_outcome/skill_outcome keep the
  verbatim-evidence requirement untouched.
- Each phase ends with: run_tests(scope=all) green + record_outcome on this
  roadmap's KB doc + status table update.
- Phase docs: extend the numbered docs (03 for P1, 05 for P2/P3, 04 for P5)
  rather than creating new ones — one home per concern.
