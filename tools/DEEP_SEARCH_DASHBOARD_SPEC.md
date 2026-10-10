# Deep Search Dashboard — Dossier Data Model + Run-State Contract

Version: v0.3 (2026-10-09) — DRAFT for operator review
Status: decisions 1–3 LOCKED; decision 4 RESOLVED by live data.

## 0. Grounding (verified from code, 2026-10-09)

- Core state machine (deep_search_core.py):
  `PLANNING → SEARCHING → REASONING → (SEARCHING|READING) → READING → SYNTHESIZING → DONE`;
  `FAILED` legal from any state. `state_trace` entries = `{state, t_offset_s, note}`.
- `DeepSearchResult` = `{status, report, sources:[{url,title,snippet,fetched}],
  plan:[{n,action,target,why}], state_trace, budgets_used, error:{class,message,state_at_failure}}`.
- `Budgets` defaults: maxSteps=8, maxSources=10, maxBriefs=2, totalBudgetSeconds=1800,
  modelTimeoutSeconds=420, toolTimeoutSeconds=300, firstOutputSeconds=420, idleSeconds=120.
- Search/read go via websearch-lb `127.0.0.1:9703` (jina→firecrawl→exa→searxng→ddg).
  Deep search does NOT consume Tavily credits — cost lands in LB pool counters.
  Model: node3090 `:8080` (valve default), key via `GOETHE_PLANNER_FORCE_API_KEY` env fallback.
- Live state (checked 2026-10-09, gateway pid 1565441): NO `DEEP_SEARCH_*` valves exist in
  the running Valves class (all defaults apply); `GOETHE_PLANNER_FORCE_API_KEY` IS present
  in gateway env; `/opt/local-se/state/deep_search` does not exist → ZERO historical runs.

## 1. Terminology

| term | meaning |
|---|---|
| topic | one research subject = one dossier |
| dossier | accumulated, structured knowledge artifact (findings + sources + convergence) — what the planner consumes |
| pass | one `deep_search()` run against a topic ("run") |
| finding | one tagged unit of knowledge extracted from a pass's report |
| source | a deduped URL across all passes of a topic |

## 2. State layout (all under /opt/local-se/state/deep_search/)

```
topics.json                        # index: [{id, title, status, updated_at}]
topics/<topic_id>.json             # the dossier (single file, atomic rewrite)
runs/<run_id>/state.json           # runner-owned live state (UI poll target)
runs/<run_id>/result.json          # terminal: full DeepSearchResult dict
runs/<run_id>/report.md            # terminal: cited markdown report
runs/<run_id>/extraction.json      # terminal: raw extraction-call output (audit)
runs/<run_id>/trace.jsonl          # append-only state_trace mirror (1 line per transition)
promotions.json                    # KB promotion queue (decision 3)
```

Rules:
- Single writer per file. `runs/*` written ONLY by the detached run worker.
  `topics/<id>.json` written by the worker (pass append) or by in-process
  user-action handlers (tag / queue-promotion / handoff) — never by UI routes.
  `promotions.json` written by the queue handler (append request) and by the
  agent (complete/reject).
- All writes atomic: write `<file>.tmp` → `os.replace()`. Topic files are small
  (tens of KB); full rewrite on append is fine.
- IDs: `run_id` = `ds-<UTC:%Y%m%dT%H%M%S>-<4hex>`; `topic_id` = `topic-<slug>`;
  `finding id` = `f-<nnn>` (per-topic monotonic); `source id` = `s-<nnn>` (per-topic).
- `DEEP_SEARCH_LOG_DIR` MUST be set explicitly at worker spawn (see §9) — the core
  writes its audit log to CWD when unset.

## 3. Schemas

### Topic / dossier (topics/<id>.json)
```json
{
  "id": "topic-wan22-fine-tune",
  "title": "Wan 2.2 fine-tune on node4090",
  "status": "researching",
  "created_at": "...", "updated_at": "...",
  "passes": [PASS_ENTRY],
  "findings": [FINDING],
  "sources": [SOURCE],
  "convergence": CONVERGENCE,
  "handoff": null,
  "budget": {"steps": 8, "sources_fetched": 10, "passes": 1}
}
```
- `status`: researching | done | converged | handed_off | archived — lifecycle: researching = active pass in flight; done = terminal pass, not yet converged; converged = >= 2 stable (DONE) passes; handed_off / archived = manual
- `handoff` (when set): `{"task_id", "at", "dossier_sha256", "dossier_chars"}`
- `PASS_ENTRY` (one per pass, appended by the worker): `{"run_id", "status": DONE|FAILED, "question", "started_at", "finished_at", "steps_used", "sources_fetched", "report_chars", "error"}` — the dashboard reads the LAST entry's run_id (accepts bare-string entries too)

### Pass (embedded in topic; live details under runs/)
```json
{
  "run_id": "ds-20261009T103012-a1b2",
  "question": "...", "instructions": "...",
  "status": "DONE",
  "started_at": "...", "finished_at": "...",
  "steps_done": 5, "steps_total": 8,
  "findings_added": 12,
  "extraction_status": "ok",
  "delta": "one line: what this pass added that earlier passes didn't",
  "error": null
}
```
- `status`: DONE | FAILED; `extraction_status`: ok | failed | skipped

### Finding (the load-bearing unit — planner context is built from these)
```json
{
  "id": "f-014",
  "kind": "fact",
  "text": "...",
  "sources": ["s-003", "s-007"],
  "pass_id": "ds-...",
  "created_at": "...",
  "tags": ["hardware"],
  "kb_doc_id": null,
  "supersedes": null
}
```
- `kind`: fact | claim | open_question | contradiction
- `kb_doc_id` set when the promotion queue completes for this finding.
- `supersedes`: finding id — a later pass resolves a question/contradiction.

### Source (deduped ledger)
```json
{
  "id": "s-003",
  "url": "...", "title": "...",
  "first_seen_run": "ds-...", "seen_in": ["ds-..."],
  "tier": "primary",
  "fetched_via": "firecrawl",
  "citations": 4,
  "volatility": "slow"
}
```
- `tier`: ground_truth | primary | secondary | inferred (waterfall assignment)
- `fetched_via`: which LB backend delivered it (jina|firecrawl|exa|searxng|ddg)

### Convergence (deterministic — every signal visible in UI)
```json
{
  "open_questions": 1,
  "contradictions": 0,
  "stable_passes": 1,
  "kb_covered": true,
  "sufficient": true
}
```
- `open_questions` = kind=open_question, not superseded
- `contradictions` = kind=contradiction, not superseded
- `stable_passes` = consecutive terminal passes with 0 new findings
- `kb_covered` = search_kb(topic) has >=1 hit, quality >= 0.8 (computed at read)
- `sufficient` = open_questions <= 1 AND contradictions == 0 AND stable_passes >= 1

## 4. Finding extraction — SEPARATE EXTRACTOR CALL (LOCKED, decision 1)

After the research pass reaches DONE and `report.md` exists, the runner makes a
SECOND model call (same node3090 endpoint, no tools):

- Input: the full cited report + the `sources` list (numbered 1..N).
- Constraint (prompted, hard): EXTRACTION ONLY — the model may not add, infer, or
  reword claims that are not in the report. Output = strict JSON array:
  `[{"kind": "...", "text": "...", "sources": [1, 7]}, ...]`
- `kind` enum: fact | claim | open_question | contradiction.
- `sources` = 1-based indexes into the sources list; every finding must cite >= 1.
- Output validated: JSON parse, enum check, index range check, text non-empty.
  One retry on malformed output.
- Raw extractor output stored verbatim at `runs/<id>/extraction.json` (audit).
- Cost note: the extraction call is report-only, no search/tool steps — the
  "2x model cost" bound is an upper limit; real overhead is one small completion.
- Failure (both attempts malformed / transport error): `extraction_status: "failed"`,
  `findings_added: 0`, report still stored, UI shows "needs structuring"
  (agent can structure the pass manually from the report).

## 5. Run-state contract (detached worker, LOCKED decision 2)

### Worker lifecycle
- Spawn: gateway route (POST passes) → detached process via setsid/nohup
  (same launcher posture as existing start scripts). Run params via argv
  (run_id, topic_id, question, instructions, budgets, state dir); SECRETS via env
  only (model key, LB token) — never argv (argv is visible in ps).
- The worker inherits the gateway env at spawn, so the model key
  (`GOETHE_PLANNER_FORCE_API_KEY` fallback) and LB token are available.
- Concurrency: one active run per topic; global cap 2 concurrent runs
  (protects the single node3090 model). A third request is rejected with 409.
- A gateway restart does NOT orphan a running pass (worker is independent).
  ORPHANED means the WORKER died mid-run (crash/OOM) — heartbeat stops.

### Live state (runs/<run_id>/state.json — UI poll target)
```json
{
  "run_id": "ds-...",
  "topic_id": "topic-...",
  "status": "RUNNING",
  "state": "READING",
  "step": {"i": 3, "n": 8},
  "trace_tail": [{"state": "...", "t_offset_s": 412.3, "note": "..."}],
  "budgets": {"steps_used": 3, "sources_used": 5, "elapsed_s": 412, "limit_s": 1800},
  "heartbeat_ts": "2026-10-09T10:37:02Z",
  "started_at": "...", "pid": 12345
}
```
- `status`: QUEUED | RUNNING | DONE | FAILED | ORPHANED
- `state`: live core State name (PLANNING|SEARCHING|READING|REASONING|SYNTHESIZING)
- `trace_tail`: last 12 state_trace entries
- Heartbeat: refreshed on every state transition AND at least every 10 s.
- `step.i` / `budgets.steps_used` count SEARCHING/READING transitions (a batched
  action round consumes one budget step each); `step.n` is the max_steps budget.
  This is BUDGET consumption, not plan progress — plan progress is the
  "actions executed: k/n" figure in the trace notes. Live since rev4:
  updated in transition() on every SEARCHING/READING, not only at terminal
  (previously 0 throughout the run).

### Orphan rule (reader-side, display only)
`status == RUNNING && (now - heartbeat_ts > 60 s || pid not alive)` → render
`ORPHANED`, "worker died mid-run — result incomplete". Readers never rewrite the
file. A post-mortem entry (stderr tail) is captured at spawn into
`runs/<id>/worker.log`.

### Terminal sequence (worker, ordered)
1. `result.json` (full DeepSearchResult)
2. `report.md`
3. extraction call → `extraction.json`
4. `state.json` status DONE|FAILED (+ budgets)
5. ONE atomic rewrite of `topics/<id>.json`: append pass record, merge findings
   (id/supersedes handling), merge sources (dedup by URL, bump citations/seen_in),
   recompute convergence, bump `budget`
6. done — UI's next poll sees terminal state + updated dossier

## 6. API surface (new goethe_ui.py routes, served-mode HTML)

| route | method | posture |
|---|---|---|
| /deepSearch | GET | served HTML, not token-gated (loopback-only bind; same as /webSearch) |
| /deepSearch/topics | GET | token-gated (posture of /webSearch/stats) |
| /deepSearch/topics/{id} | GET | token-gated |
| /deepSearch/topics/{id} | DELETE | token-gated; deletes dossier + topics.json index entry + runs/<run_id>/ for every pass listed in the dossier. Fail-closed: a run dir is removed only when its state.json is absent OR confirms topic_id == tid. 409 while a pass is QUEUED/RUNNING; 404 when the dossier is missing |
| /deepSearch/topics | POST {title} | token-gated |
| /deepSearch/topics/{id}/passes | POST {question, instructions?, max_steps?, max_sources?} → run_id | token-gated; spawns detached worker; 409 on concurrency cap |
| /deepSearch/runs/{run_id} | GET | token-gated, READ-ONLY (file-read, same posture as /webSearch/quota) |
| /deepSearch/topics/{id}/findings/{fid} | PATCH {kind?, tags?, supersedes?} | token-gated |
| /deepSearch/topics/{id}/findings/{fid}/promote | POST | token-gated; appends to promotions.json (NEVER writes KB) |
| /deepSearch/topics/{id}/handoff | POST {goal?} | token-gated; calls planner(task, context=dossier), stores task_id + sha256 |
| /webSearch (right panel) | — | one-line bridge: "deep search: N topics · M running → /deepSearch" |

UI polling: 3 s while a run is QUEUED/RUNNING, 30 s otherwise. No SSE in MVP
(consistent with the existing 5 s poll pattern).

UI (deep_search.html, rev4 2026-10-09):
- Topic rectangles carry a red lowercase-x delete control at the top-right
  corner, inscribed in the rectangle, sized 1em (exactly the size of a
  lowercase x in the topic font). Click deletes the topic in the UI and
  calls DELETE (full backend cleanup); it never selects the topic.
- Clicking a topic renders its last run IMMEDIATELY (render-on-click);
  the tick loop (3 s active / 30 s idle) is only the refresh loop.
- All fetch failures surface in the UI (run-state pane / report pane),
  never swallowed. The header shows a build stamp ("ui revN · date") so
  the served revision is visible in the browser.
- No run for the selected topic (new topic, no passes yet) → the run pane
  is CLEARED ("no run", empty trace, report "—"). The pane never shows a
  previous topic's stale run (rev4 fix; rev3 renderRun() early-returned
  and left the previous topic's run state on screen).
- Gauge labels distinguish budget consumption from plan progress: terminal
  runs read "i/n budget steps used · Xs elapsed"; live runs read
  "step i/n · N steps · Xs elapsed" (steps_used is live now, not 0).

## 7. Planner handoff contract

- Dossier rendered to markdown DETERMINISTICALLY: sections = findings by kind
  (each with its citation list), then source ledger (URL, tier, backend,
  volatility), then open questions.
- `planner(task=<title> + goal, context=<dossier markdown VERBATIM>)`.
- Store `{task_id, at, dossier_sha256, dossier_chars}` on the topic.
- If the dossier changes after handoff (sha mismatch), UI flags it.
- Handoff button enables when `convergence.sufficient`; forceable with a warning
  listing the failing signals.

## 8. KB promotion queue (decision 3 — LOCKED)

Mechanism (queue-for-agent):
- POST .../promote appends to `promotions.json` `pending[]`:
  `{"req_id", "finding_id", "topic_id", "finding": {snapshot}, "sources": [snapshot], "requested_at"}`
- The agent (in a session) processes the queue when asked ("process the KB queue")
  or reports the pending count at session start. Per entry:
  1. search_kb dedup check (near-dup exists → complete with existing doc_id, no new doc)
  2. waterfall for external-software version/behavior claims (KB rule)
  3. verify_source_claims for load-bearing claims
  4. index_to_kb (origin=web, tier, volatility, source_url, evidence)
  5. write `completed[]` {req_id, doc_id, at, notes} or `rejected[]` {req_id, at, reason};
     set finding.kb_doc_id on completion
- UI shows pending / completed / rejected counts; pending > 7 days flagged stale.
- No autonomous KB writes: the queue is only processed inside an agent session
  with operator awareness.

Rationale (vs in-process index_to_kb from the route):
- Every KB write keeps the full gate set (waterfall provenance, tier ceilings,
  origin=web can never carry ground_truth, [UNVERIFIED] tagging) applied by an
  accountable actor, not mechanically.
- Per-finding judgment stays with the agent: hardware fact observed live vs
  forum claim vs version claim each get different tier/quality treatment.
- Rejection is a feature: the KB is curated, not a dump.
- Audit trail: request (pending) + receipt (doc_id) + rejection reason in one file.

LOCKED 2026-10-09: v1 is queue-only. The "quick record" hybrid alternative
(in-process, hard-capped: origin=web, tier <=secondary, quality <=0.5, refuses
version/behavior claims) is DEFERRED — revisit only if queue-pending latency
proves annoying in practice. One path = one quality standard for the KB.

## 9. Build prerequisites (decision 4 — RESOLVED by live data, 2026-10-09)

- ZERO historical runs: /opt/local-se/state/deep_search does not exist; no
  DEEP_SEARCH_LOG_DIR set anywhere; clean start, no migration.
- Model key IS available in the running gateway env (GOETHE_PLANNER_FORCE_API_KEY
  present, verified via /proc/1565441/environ) — deep_search is already runnable.
- DEEP_SEARCH_* valves do not exist in the running Valves class → all defaults
  apply (model node3090:8080, LB 127.0.0.1:9703, LOG_DIR empty).
- Required at build time: set DEEP_SEARCH_LOG_DIR explicitly (worker spawn env,
  per run dir) so core audit logs land in runs/<id>/worker.audit, not CWD.
  Optional: add DEEP_SEARCH_MODEL_URL / LOG_DIR to Valves for operator override.

## 10. Phasing

- Phase 1 (MVP): state layout, detached worker, run-state endpoint, minimal page
  (topic list, run button, live trace, final report, source ledger).
- Phase 2: extractor call, findings + tags + delta, promotion queue.
  Phase 3: convergence meter, planner handoff, /webSearch bridge line.

## 11. Deployment

- New goethe_ui.py routes load at gateway boot → operator GUI restart required
  (KB 1dd544d695ba6b48 — agent never self-restarts the gateway).
- Frontend served per-request (same as /webSearch index.html) → HTML edits apply
  without restart; route additions do not.
