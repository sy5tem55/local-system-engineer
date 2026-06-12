# Session Handover — P24 (2026-06-12)

## State: GREEN. v1.7.8 DEPLOYED and verified. Planner chain verified end-to-end except kanban card creation (capability gap, root-caused, fix designed).

Stack all-up at session start: llama-server, OWUI, SearxNG, ES (green, 5/5 indices,
767 docs), Prometheus 9/9 targets, VRAM 21.7/24.6 GB @32°C. Playwright WAS up —
plain GET shows an error page because it's WebSocket-only; don't re-diagnose this
(SY5 got EADDRINUSE trying to "restart" it).

## What shipped / verified this session

- **v1.7.8 confirmed deployed** (P23 item #1). Installed at 16:37 CEST by SY5's own
  pre-session A/B test. KEY FINDING: **OWUI black-formats tool code on save** —
  installed sha `a7fc986e…` (188,582 B) == black(repo `fd65fea6…`, 183,103 B).
  Verify future deploys by black-normalizing the repo file, never by raw sha.
  VERSION.md updated.
- **pdfminer.six already in OWUI venv** (20260107) — P23 item #2 closed, no action.
- **hermes_plan smoke-tested live** (P23 item #3): plan envelope (task_id, per-step
  budgets, verify clauses, abort criteria) → KB-first → checkpoints → web research →
  sourced summary with UNVERIFIED discipline. Tool cards render clean (v1.7.7
  sanitizer fix holding). Run twice (systemd hardening 18:45, ext4-vs-xfs 19:30).
- **Hermes memory → pointer swap verified done** (P23 item #4): MEMORY.md line 3 is
  the pointer (was swapped 15:53 during SY5's pre-session testing). Verified by
  direct file read. The pointer WORKS: agent.log shows read_file of the contract on
  every PLAN REQUEST turn.
- **Planner contract v2.1** written + installed on node3090 (6,223 B): card creation
  moved BEFORE envelope emission (v2's "after responding" was unreachable — emitting
  the response ends the turn; same dead-path class as the v1.7.3 call_hermes bug).
  Added `card_error` envelope field for fail-open reporting.
- **Stray OWUI memory cleaned**: LSE had created the PLAN REQUEST pointer in its OWN
  OWUI memory (claiming "no existing PLANNER CONTRACT memory" — it searched the wrong
  store). Deleted; verified count=0 in webui.db.
  webui.db path: `/home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db`.

## KEY OPEN ITEM — kanban card creation is a CAPABILITY GAP, not a prompt bug

Ground truth from agent.log (19:30 turn, session api-21986e71e5d465c8): Hermes read
contract v2.1 (6,871 chars), then tried `cronjob` (49 chars), then `skills_list` —
i.e. it HUNTED for a board tool, found none, returned the envelope without a card.
The planner session's toolset has read_file/terminal/cronjob/skills_list but NO
kanban-write tool. tasks table: still 0 rows ever.

Fix options (build next session):
- **A — gateway-side**: gateway inserts the triage card when a plan envelope passes
  through. Deterministic, but modifies Hermes infra.
- **B — LSE-side (preferred)**: `hermes_plan()` creates the card itself after parsing
  the envelope (cogitator already has node3090 ssh plumbing). Direct INSERT with
  status='triage', assignee='lse', goal_mode=0. v1.7.9 candidate.
  ⚠ PRE-CHECK: kanban_db.py VALID_INITIAL_STATUSES={running,blocked} (P22 survey) —
  confirm a direct sqlite INSERT into `triage` doesn't violate schema constraints or
  dispatcher assumptions before building.

## Open items (priority order)

1. **v1.7.9 candidates**: (a) kanban card creation in hermes_plan (option B above);
   (b) OWUI disconnect during long silent tool calls — emit keepalive/status events
   during the call_hermes wait (~25-40s); relates to P20 incident action item 6.
2. **Unattributed LSE invocation, 2026-06-10 22:14** — cogitator ran
   "# Check Claude Code plans/tasks for suspicious activity" (read-only: ls + head of
   ~/.claude/plans/merry-marinating-whisper.md, which is the legit arena ssh-verify
   plan). NOT SY5. Not in Claude Code transcripts (grep clean), not in OWUI chats
   (webui.db clean) → came through OWUI API without persistence. Prime suspect: arena
   harness / run_episode.py — i.e. possibly the LOCAL MODEL poking at Claude Code's
   files mid-episode. Next: `grep -n -B8 -A8 'suspicious activity'
   /opt/local-se/agent_commands.log` for the surrounding command rhythm + check
   leaderboard.db episodes for a run active at that timestamp. If it WAS an episode,
   that's the ground-truth-verification plan's argument made flesh — prioritize P0.
3. **Mango artifacts recreated by SY5's A/B test** (16:20, 16:43):
   `rm -f /opt/local-se/mango-seedling-care-guide.md /opt/local-se/mango_care_document.md`
   + the P23 ES doc cleanup: `curl -s -X DELETE localhost:9200/lse-kb/_doc/0fecb21d9148de14`.
   Also two test task blocks in tasks.db (a3f7b2c1, a7f3e2b1 — both done) + open
   goethe-fm-01 — purge or leave as history.
4. **Ollama-as-LSE-secretary** (SY5 question): parked as roadmap QUESTION, not build.
   VRAM is the blocker (21.7/24.6 used); everything secretarial is either a cogitator
   function or cheaper as code. Re-evaluate only if a concrete recurring task appears
   that needs a second model.
5. **Planner remaining** (carried): spec §4 step 3 (context-monitor v1.3 suggestion
   hook) and step 5 (calibration report after ~20 plans).
6. Carried from P23: waterfall provenance rule (write-path enforcement);
   launcher docker container visibility (LSEStack_gui); arxiv `categories: [science]`
   defense-in-depth; regression tests; LM Studio repoint to /opt/models on node3090;
   search_rfc triggering review.

## Operating rules / lessons added this session

- **OWUI normalizes tool code with black on save.** Deploy verification = compare
  black(repo file) to installed content. Raw sha mismatch ≠ wrong version.
- **"After responding, do X" is an unreachable instruction for an agent** — emitting
  the response ends the turn. Side effects go BEFORE the response. (Second instance
  of the dead-path class: v1.7.3 call_hermes error returns, now contract v2 card rule.)
- **Tool-hunting in logs is the ground truth for capability gaps.** Hermes trying
  `cronjob` then `skills_list` after reading the contract proved the toolset lacks a
  board tool — no amount of contract wording fixes that.
- **Agent self-report vs ground truth, three more instances today**: LSE claimed "no
  existing PLANNER CONTRACT memory" (searched its own store, not Hermes's); LSE
  "created memory ac78772e" (in the wrong store); deletion claim (that one was true —
  but only verification made it knowledge).
- **grep for correlation ids, not message prefixes** — call_hermes prepends CONTEXT:,
  so 'PLAN REQUEST' greps miss relayed requests in agent.log.
- **Numeric-only hostnames bypass DNS** (`ping 3090` → inet_addr → 0.0.12.18). Use
  alphanumeric DNS names. (From P6 session, re-confirmed in passing.)

## Key paths

- Tool: `tools/cogitator-v1.7.8.py` LIVE (installed form = black-formatted, sha
  `a7fc986e…`) · VERSION.md current
- Planner contract: `prompts/hermes-planner-prompt.md` (v2.1) → node3090
  `/home/hermes-admin/.hermes/planner-contract.md` (6,223 B, hermes-admin:600)
- Hermes memory: node3090 `/home/hermes-admin/.hermes/memories/MEMORY.md` (pointer
  on line 3) · agent log: `/home/hermes-admin/.hermes/logs/agent.log`
- kanban: node3090 `/home/hermes-admin/.hermes/kanban.db` (tasks table: 0 rows ever)
- LSE task blocks: LUCIFER `/opt/local-se/tasks.db` · audit:
  `/opt/local-se/agent_commands.log`
- node3090: ssh lse-admin@192.168.5.41 (alias 3090.home.arpa) · gateway :8643→8642
  · OWUI venv: /home/sy5/owui
