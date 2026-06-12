# Session Handover — P23 (2026-06-12)

## State: GREEN. Tool v1.7.8 BUILT, NOT yet deployed (deploy candidate).

Stack verified all-up at session start (health-check skill): llama-server, OWUI, SearxNG,
Elasticsearch (5/5 indices incl. lse-skills, 764 docs), Prometheus (9/9 targets incl.
searxng=up), Playwright, VRAM 22.1/24 GB. lse-skills index already existed (P22 deploy).

## What shipped this session

- **lse-skills seeded** (P22 open item #1 closed). `rag/07-seed-skills.py` (idempotent, mirrors
  `skill_record` exactly — embed prefix, doc-id scheme, so tool-side dedup stays consistent):
  - skill #1 `linux-sysadmin/...permission-blocked...` (sudo-blocker, S0.3) — also written long-form
    to `kb/skills/linux-sysadmin--permission-blocked-cleanup.md`
  - skill #2 `sre/...restart-llama-server...node3090` (distilled from Restart _Hermes.md + learnings)
  - both quality 0.5, verified present via _search.
- **lse-errors corrected** (P22 #2 closed). LSE recorded the correct resolution for the
  compact_context "Invalid action slots" entry: `POST /slots/0?action=erase` is a QUERY PARAM
  (fixed v1.7.4); the "slots API removed in v9577" diagnosis was a fabrication.
- **Planner-orchestrator implemented** (P22 #3, spec §4 steps 1/2/4):
  - `hermes_plan()` tool function — pre-flight triage, wraps call_hermes intent=plan, parses the
    plan envelope, writes the initial task block (packaged_prompt → next_prompt), degrades to
    "PLANNER UNAVAILABLE — proceed with default budgets, checkpoint early". Docstring-optimizer pass done.
  - **Planner contract v2** (`prompts/hermes-planner-prompt.md`) installed persistent on node3090 at
    `/home/hermes-admin/.hermes/planner-contract.md` (4149 B). Adds KANBAN CARD RULES from the
    kanban_db.py source survey.
  - **kanban survey done.** `~/.hermes/kanban.db` is a DISPATCHER, not just a board: task_runs,
    claim locks, goal_mode (judge-loop workers), force-loaded skills. Dispatcher claims from `ready`
    (and auto-promotes `todo`→`ready`). VALID_INITIAL_STATUSES={running,blocked}. **`triage` is the
    only inert state** — contract v2 mandates lse plan cards land in `triage`, never promoted. Board
    was empty (0 tasks/runs).
- **Three tool fixes from one research run** (all fold into v1.7.8):
  - **v1.7.6** `hermes_plan()` + FIX: `call_hermes` error handling was truncated (latent since
    v1.7.3) — HTTPError handler fell through to implicit None, URLError/timeout raised uncaught;
    the documented `ERROR:` returns were unreachable, so the GATE "check for ERROR:" could never fire.
    Restored from `tools/call_hermes_draft.py`.
  - **v1.7.7** `fetch_url` CONTENT-TYPE GUARD: fed `resp.text` to the HTML parser unconditionally;
    on a PDF that dumped raw FlateDecode binary into context AND broke OWUI `<details>` rendering
    downstream (control chars + stray `<<`/`>>` derailed the sanitizer → every later tool card
    showed as raw escaped text). Now: PDF→pdfminer/pypdf text extract (clean refusal if neither lib
    present), non-text content-types refused, all output control-char-sanitized. Binary never returned.
  - **v1.7.8** `search_web` category fix: requested `categories="general,it,science"` on EVERY call;
    arxiv (in [science,it,technology], weight 2, ~15% reliable) fired on all queries and returned
    off-domain hits, burning the web budget. Now `categories="general"` only. Root cause was
    tool-side, NOT a SearxNG misconfiguration.

## Open items (priority order)

1. **DEPLOY v1.7.8 to OWUI** — supersedes v1.7.6/v1.7.7, single deploy candidate. sha256
   `fd65fea6…`. Tool runs in OWUI venv on LUCIFER (`/home/sy5/owui`), NOT node3090.
2. **Optional: `/home/sy5/owui/bin/pip install pdfminer.six`** — without it, v1.7.8 PDF path
   returns a clean refusal (no binary either way); with it, refusal upgrades to text extraction.
3. **Smoke-test hermes_plan** — run a research-shaped task prefixed "plan first", expect a PLAN
   ENVELOPE (task_id, steps w/ verify, abort criteria) + `CHECKPOINT saved`. Then ground-truth the
   card: `sqlite3 ~/.hermes/kanban.db "SELECT id,title,assignee,status,goal_mode FROM tasks ORDER BY created_at DESC LIMIT 3"`
   — must read `status=triage, assignee=lse, goal_mode=0` and STAY triage minutes later. If it ever
   shows ready/running, a worker claimed it → revisit contract rule 2.
4. **Swap Hermes memory PLANNER CONTRACT entry to a pointer** — it currently holds a condensed v1
   inline (the 2,200-char cap can't fit v2; v1 install proved Hermes silently condenses). Replace with:
   "On any message beginning with PLAN REQUEST, read /home/hermes-admin/.hermes/planner-contract.md
   and follow it exactly."
5. **Planner remaining**: spec §4 step 3 (context-monitor v1.3 suggestion hook on fresh complex
   tasks — suggestion only, SY5 can bypass) and step 5 (calibration report after ~20 plans).
6. **v1.7.x candidate — WATERFALL PROVENANCE RULE** (SY5 P23 observation): the source-of-truth
   hierarchy (KB→vendor docs/master README→github→web) exists as available tools but not as a
   mandatory path for claims. Enforce at the WRITE path: `record_error`/`index_to_kb` reject
   external-software behavior claims ("removed/changed in version X") lacking waterfall provenance,
   else persist tagged UNVERIFIED at quality ≤0.3. (Roadmap, under v1.7.0 section.)
7. **Launcher docker container visibility** (roadmap, GUI & Stack) — show all running containers +
   resource usage (`docker stats --format json`) in the launcher GUI ≥1.078. Repo: `LSEStack_gui`.
8. **Optional defense-in-depth**: tighten arxiv to `categories: [science]` in settings.yml (verify
   canonical path via docker exec read first). Low priority now the tool no longer requests it/science.
9. Carried from P22: regression tests (research re-ask ≤8 searches/checkpoint; "metrics token" →
   docker exec read not recall; compaction → context % DROP with n_erased); LM Studio repoint to
   `/opt/models` on node3090; search_rfc triggering review.

## Operating rules / lessons added this session

- **Root-cause at the layer that failed, not the loudest symptom.** A garbled OWUI chat looked like
  a rendering bug; the cause was `fetch_url` dumping PDF binary that broke the sanitizer downstream.
  Fix the primitive, the presentation heals with it.
- **Planner/budget machinery is sound; the leaks were in the data primitives.** The orchestration
  planned, checkpointed, hit the budget gate, and surfaced partial findings with unverified items
  marked — exactly as designed. The failures were all in fetch_url / search_web categories beneath it.
- **kanban is a dispatcher, not a board.** Creating a card in a claimable state (`ready`, or `todo`
  which auto-promotes) would make a Hermes worker EXECUTE an LSE task — a capability-split violation.
  Plan cards live in `triage` and are never promoted except triage→done on completion.
- **Agent self-report vs ground truth, again.** Hermes reported "saved full content" of the contract;
  it had silently condensed it (4149 B file vs 2200-char memory cap). Usable, but the claim was false.
  Persistent files + memory-as-pointer is the durable pattern, not "save this into memory".
- **Cowork sandbox edits can lag the host mount** on large files — a fresh-written file may transiently
  read truncated in bash. Re-stat/retry, or build via a `python3` heredoc that reads+writes in one shot.

## Key paths

- Tool: `tools/cogitator-v1.7.8.py` (deploy candidate, sha `fd65fea6…`) · registry VERSION.md current
- Planner: `prompts/hermes-planner-prompt.md` (v2) → node3090 `/home/hermes-admin/.hermes/planner-contract.md`
- Skills seed: `rag/07-seed-skills.py` · `kb/skills/linux-sysadmin--permission-blocked-cleanup.md`
- kanban dispatcher: node3090 `~/.hermes/kanban.db` (statuses: triage/todo/scheduled/ready/running/
  blocked/review/done/archived; claim from `ready`; inert=`triage`)
- Designs: `docs/planner-orchestrator-design.md` (1.7.2 phase) · `docs/self-learning-trajectory.md`
- node3090: ssh lse-admin@192.168.5.41 · Hermes gateway :8643 (socat→8642) · OWUI venv: /home/sy5/owui
