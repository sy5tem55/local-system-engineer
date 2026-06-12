# Session Handover — P25 (2026-06-12)

## State: GREEN. v1.7.9 DEPLOYED + smoke-test verified. auto_decompose DISABLED on node3090. Fabrication #5 caught, corrected, and root-caused to synthesis (not retrieval).

## What shipped / verified this session

- **Cogitator v1.7.9 deployed + verified** (black-norm `2e15e467…` MATCH; repo sha
  `36d9dcc2…`). `_kanban_create_card()`: hermes_plan INSERTs the triage card into
  node3090 kanban.db over ssh (status=triage, assignee=lse, created_by=lse-cogitator,
  goal_mode=0, idempotency_key=`hermes_plan:<tid>`, created_at INTEGER epoch,
  INSERT OR IGNORE). Fail-open card_error line. Smoke test `rutx50web01`: card
  created, STAYED triage, no children, no workers. Pre-checks that made it safe:
  tasks schema has NO CHECK on status; `VALID_INITIAL_STATUSES={running,blocked}`
  gates only the Python API; lse-admin has NOPASSWD sudo wide enough for sqlite3
  (BatchMode-proven).
- **Planner contract v2.2** installed (node3090, 6,466 B): card creation REMOVED from
  Hermes side (P24 ground truth: planner session has no board tool). Hermes emits
  envelope immediately; never-promote-lse-cards rules retained.
- **AUTO-DECOMPOSER INCIDENT (first live card)**: Hermes `kanban_decompose.py` claims
  EVERY triage card on dispatcher tick — flipped our card triage→todo, created 3
  `t_*` step-children (created_by=auto-decomposer), dispatched workers 9788 + 11699
  which re-did finished LSE research (node3090 GPU + Browserbase quota). P22
  "triage is the only safe state" FALSIFIED — triage is the decomposer's INPUT QUEUE.
  Fix applied: `auto_decompose: false` in `/home/hermes-admin/.hermes/config.yaml`
  (~line 441, backup `.bak-P25`) + hermes-gateway restart. Verified by smoke test.
  LESSON: archiving a card does NOT stop its in-flight worker — kill
  `tasks.worker_pid` as well (11699 ran 10+ min on an archived card).
- **P24 "unattributed LSE invocation" CLOSED**: SY5's own OWUI chat
  "🛡️ Claude Code Security Check" (06-10 22:12 local; npm supply-chain worry after
  Check Point research; Claude Code is npm-installed → the ~/.claude sweep was the
  LSE answering the question). P24's "webui.db clean" was a FALSE NEGATIVE — text
  grep for never-persisted command text; a time-window SQL on `chat` found it in
  seconds. The handover's P0 escalation is MOOT (not an episode; harness exonerated:
  run_episode.py talks to llama-server directly, never the cogitator).
- **FABRICATION #5** (RUTX50 task): LSE cited phantom firmwares **07.23.5** and
  **07.22.4** with invented dates/changelogs (recombined from the REAL 07.23
  changelog) — AFTER successfully fetching the wiki page showing 07.22.3=Stable /
  07.23.4=Latest, and DESPITE explicit "no version newer than 07.23.4 exists" in
  its context. Evidence overwrite at synthesis, not a retrieval gap. Caught by
  independent re-fetch minutes later. Corrected deliverable:
  `docs/rutx50/rutx50-remediation-decision.md` (correction header; forum draft clean
  and postable). Device-side evidence verified sound and retained.
- KB debrief P24 confirmed landed (count=1).

## RUTX50 webui-login bug — state of knowledge (VERIFIED)

- Symptom: login page serves, valid credentials rejected; SSH (dropbear) always
  works; reboot fixes temporarily; factory reset does NOT. fw RUTX_R_00.07.23.4.
- No fix released (07.23.4 = newest, 2026-05-29, CVE-only). Official fallback:
  **07.22.3** "Stable FW" (2026-05-19). Downgrade WITHOUT keep-settings.
- Prime suspect: 07.23 login-path rework (WebUI 2FA + SSH 2FA + API Core
  Lua 5.1→LuaJIT 2.1). Device stack: uhttpd → api_dispatcher.lua (LuaJIT) → ubus
  session; only `uhttpd` in init.d.
- Recovery PREPARED, untested: `/etc/init.d/uhttpd restart` (restarts LuaJIT
  children, no network/SSH disruption). Script + decision doc + forum draft:
  `docs/rutx50/`. NEXT FAILURE: run script, capture logread before/after, then post
  forum draft and decide stay-vs-fallback.

## Open items (priority order)

1. **node3090 post-incident cleanup (NOT yet done)**: (a) contamination check —
   `skills/node3090-shutdown-notification/SKILL.md` and `memories/USER.md` were
   modified during the incident window: stat + inspect, revert if worker-written;
   (b) `rm -rf ~/.hermes/kanban/workspaces/a3f7c912` (duplicate research);
   (c) verify 4 archived cards stayed archived.
2. **RUTX50 next-failure protocol** (see above). Forum draft ready in docs/rutx50/.
3. **v1.7.10 candidates**: (a) NEW LEAD — code-enforced source-claim verification:
   fabrication #5 proves prompt fences don't hold at synthesis; design = post-answer
   verify step that re-fetches cited sources and diffs claimed facts (enforcement in
   code, sudo-blocker lineage); (b) async keepalive during call_hermes wait
   (needs sync→async refactor with __event_emitter__; P20 item 6).
4. **Seed `rutx50-t2-blind` challenge** (SY5's valid critique: P25's test handed the
   answer key in context — it tested discipline, not research). Answer key held:
   07.22.3 Stable / 07.23.4 Latest / no fix / 07.23 login rework / uhttpd-only
   stack. Run the same task COLD via the harness, score against key. This is the
   ground-truth-verification arena made real-world.
5. **P24 carry, still pending**: mango artifact cleanup
   (`rm -f /opt/local-se/mango-seedling-care-guide.md /opt/local-se/mango_care_document.md`;
   `curl -s -X DELETE localhost:9200/lse-kb/_doc/0fecb21d9148de14`; test task blocks
   a3f7b2c1/a7f3e2b1 purge-or-keep; goethe-fm-01 open block).
6. **Planner remaining** (carried): spec §4 step 3 (context-monitor v1.3 suggestion
   hook), step 5 (calibration report after ~20 plans).
7. Carried from P23: waterfall provenance rule; launcher docker container visibility;
   arxiv categories defense-in-depth; regression tests; LM Studio repoint;
   search_rfc triggering review. Ollama-secretary still parked (VRAM).

## Operating rules / lessons added this session

- **Triage is NOT inert** — it is the auto-decomposer's input queue. Any state
  assumption about a foreign board must be verified against the consumer code,
  not the schema.
- **Archive ≠ stop**: archiving a kanban card leaves its worker running; kill
  worker_pid explicitly.
- **Fabrication survives prompt fences when the source is in context** — #5
  recombined real changelog fragments into phantom versions AFTER fetching the
  truth. Only independent re-verification catches it. Code-enforce it (v1.7.10).
- **Verify absence with storage-shaped queries**: P24's "webui.db clean" grep
  missed a chat titled exactly what we were looking for; time-window SQL found it
  instantly.
- **Capability tests need held-out answer keys** — context-provisioned tests
  measure discipline (floor), blind tests measure research (ceiling). Both matter;
  P25 ran the floor test by design (and the floor failed at synthesis).

## Key paths / state

- Tool: `tools/cogitator-v1.7.9.py` LIVE (black-norm `2e15e467…`) · VERSION.md current
- Contract: `prompts/hermes-planner-prompt.md` (v2.2) → node3090
  `/home/hermes-admin/.hermes/planner-contract.md` (6,466 B)
- node3090 hermes config: `~/.hermes/config.yaml` — `auto_decompose: false`
  (backup `.bak-P25`) · decomposer source: hermes_cli/kanban_decompose.py
- kanban.db: 4 archived cards from incident + rutx50web01 (triage, ours)
- RUTX50 docs: `docs/rutx50/` (decision doc + recovery script, corrected)
- Task block: `rutx50web01` open in /opt/local-se/tasks.db (LSE side)
