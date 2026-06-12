# Session Handover — P22 (2026-06-12)

## State: GREEN, committed (88fe8b5 → f0bf717 + final commit pending for this file)

- **Tool: Cogitator v1.7.5 DEPLOYED** (renamed from openwebui-tool; sha256 `94a428a9…`, 3415 lines).
  Version chain this session, all field-incident-driven:
  - 1.7.0 skills layer: `skill_search`/`skill_record`/`skill_outcome` → ES index `lse-skills`
  - 1.7.1 anti-spiral: `_budget_gate()` on search_web/search_reddit/fetch_url + task blocks
    (`task_checkpoint`/`task_resume`, SQLite `/opt/local-se/tasks.db`) — Goethe incident (34 searches/78K tokens/no output)
  - 1.7.2 budget window 30→2 min (window leaked across task_resume sessions, RUTX50 incident)
  - 1.7.3 UNVERIFIED-URL RULE (LSE invented `fbidownload.teltonika-networks.com`, diagnosed its own
    hallucination as a DNS outage)
  - 1.7.4 compact_context KV-erase fixed: `POST /slots/0?action=erase` is a QUERY PARAM — JSON body was
    never valid; "slots API removed in v9577" diagnosis was FALSE (verified vs llama.cpp master README)
  - 1.7.5 CONFIG GROUND-TRUTH RULE (execute_command + search_kb) + per-hit age display in search_kb
- **Hermes skill learning analyzed from ground truth** (`docs/hermes-skill-learning-analysis.md`):
  SKILL.md files + full-manifest prompt injection + weekly idle curator; 0 skills in 44h, curator
  run_count=0 — wired but inert. Surpass design = retrieval > injection, evidence > age, provenance mandatory.
- **Observability de-fragiled**: `observability/observability.env` (single source of truth — real token
  `JZVeoVch…`, real dirs `/home/sy5/docker/{searxng_data,prometheus}`, net `docker_searxng_net`,
  target `searxng:8080`) + `deploy-observability.sh` (idempotent repair + end-to-end verify).
  Prometheus target `searxng=up` verified. 4 stale searxng KB docs carry correction headers.
- **Health-check skill updated** (repo + .skill package installed via Save-skill button):
  prometheus targets probe + 5-index ES `_count` probe (closes P21 item #3).
- **Planner-orchestrator SPEC ready** (`docs/planner-orchestrator-design.md`): Hermes pre-flight triage —
  packaged_prompt + sessions_estimate + per-step budgets + abort criteria; kanban.db board,
  tasks.db execution ground truth (one-way LSE→Hermes sync). Three layers: planner estimates,
  budgets enforce, task blocks carry over — no layer trusts model attention.
- P22 debrief in `kb/session-learnings.md` (rides into lse-kb on next reseed).

## Open items (priority order)

1. **lse-skills index**: run `python3 rag/06-skills-index-setup.py` on LUCIFER (idempotent), then
   verify `curl -s localhost:9200/lse-skills/_count`. Seed skill #1 (sudo-blocker, S0.3) + distill
   t3-003/004 restart procedure as skill #2.
2. **Correct false lse-errors entry**: LSE recorded "slots API removed in v9577" during the
   compact_context incident — have LSE `check_error_kb("Invalid action slots")` then `record_error`
   with the real resolution (query-param form, fixed in v1.7.4).
3. **Planner-orchestrator implementation (1.7.2 phase)**: Hermes-side planner prompt (install via
   call_hermes task, never hand-edit), `hermes_plan()` tool function, kanban.db schema survey first.
4. **Regression tests pending**: (a) Goethe re-ask — expect ≤8 searches, checkpoint, partial surface
   with unverified marked; (b) "what's the SearxNG metrics token?" — expect docker exec read, not recall;
   (c) compaction — expect context % DROP with n_erased reported.
5. Carried from P21: LM Studio repoint to `/opt/models` on node3090; search_rfc triggering review
   (0 calls in 44,637 commands); node-t3-006 challenge design; VERSION.md registry now current.

## Operating rules added this session (full detail: kb/session-learnings.md 2026-06-12 P22 entry)

- **Attention is not a control plane**: termination, budget, and carryover decisions are enforced in
  code (sudo-blocker philosophy). Never fix a spiral with a docstring alone.
- **Fabrication-under-pressure pattern** (4 instances today: Goethe quote, fbidownload hostname,
  "slots API removed", invented metrics token + "no scrape job"): blocked retrieval → confident
  invention wrapped in diagnostic narrative. Tool-layer counters now: UNVERIFIED-URL rule (1.7.3),
  CONFIG GROUND-TRUTH rule (1.7.5), findings-vs-UNVERIFIED split in task blocks (1.7.1).
- Rate-limit windows for interactive agents must be shorter than a conversation turn (2 min, not 30).
- Agent incident diagnoses need ground-truthing before acting: the real outage cause and the agent's
  stated cause were different things twice today (slots API, prometheus job).
- Cowork skill updates: repo SKILL.md edits don't reach the installed copy — package as `.skill` zip,
  present, user clicks Save skill.
- llama.cpp slots API: action is a query parameter. SearxNG metrics: Basic auth, empty user,
  token from `observability/observability.env` ONLY.

## Key paths

- Tool: `tools/cogitator-v1.7.5.py` (deployed) · registry: VERSION.md (now current through 1.7.5)
- Task blocks: `/opt/local-se/tasks.db` · budget state: `/opt/local-se/.search_budget.json`
- Observability: `observability/{observability.env,deploy-observability.sh}` · dashboard :3002
- Designs: `docs/hermes-skill-learning-analysis.md` · `docs/planner-orchestrator-design.md` ·
  `docs/lse-1.7.0-design.md` (§3.5.2 hybrid claim corrected in changelog) · `docs/self-learning-trajectory.md`
- node3090: ssh lse-admin@192.168.5.41 · Hermes: gateway :8643 (socat→8642), `~/.hermes/` (hermes-admin)
