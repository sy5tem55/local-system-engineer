# Prompt Version Changelog

## node4090-v0.5.20 / node3090-v0.2.0 — 2026-06-30
**node4090-v0.5.20 changes from v0.5.19:**
- IDENTITY: explicitly named node4090 throughout (prompt series parity with node3090).
- MCP GW: tool count 37 → 39 (ssh_run + ssh_script added in Goethe v0.2.6).
- TOOLS: ssh_run entry — simple remote commands, argv passthrough, no bash -c, ControlMaster.
- TOOLS: ssh_script entry — complex scripts via scp+exec, nohup auto-fix, zero escaping.
- TOOLS: execute_command SSH_COMPLEXITY_GUARD note — blocks nohup/disown/export patterns.
- WEB SEARCH BUDGET FALLBACK: node3090 reachability check now uses ssh_run(); nohup starts use ssh_script().
- KNOWLEDGE BASE: SSH ControlMaster mux socket path and verification commands added.
Deployment note: paste node4090-v0.5.20 into llama-ui on LUCIFER.

**node3090-v0.2.0 changes from v0.1.0:**
- MCP GW: tool count 33 → 35 (ssh_run + ssh_script added in Goethe v0.2.6).
- MCP GW START: nohup one-liner retained for local use; note added that FROM LUCIFER
  the restart must use ssh_script() (SSH_COMPLEXITY_GUARD blocks it via execute_command).
- TOOLS: ssh_run and ssh_script entries added.
- TOOLS: execute_command SSH_COMPLEXITY_GUARD note added.
- KNOWLEDGE BASE: SSH ControlMaster mux socket path and verification commands added.
Deployment note: paste node3090-v0.2.0 into llama-ui on node3090.

## v0.5.19 — 2026-06-30
**Changes from v0.5.18:**
- ENVIRONMENT: goethe_mcp version corrected v1.9.0/v1.9.1 → v1.9.3 (stale references in v0.5.18).
- No other content changes.
Root cause: v0.5.18 was written before goethe_mcp reached v1.9.3; version numbers never updated.
Deployment note: **This is the version to paste into llama-ui.** Zero OWUI references (grep confirmed).

## v0.5.18 — 2026-06-28
**Changes from v0.5.17:**
- WEB SEARCH BUDGET FALLBACK: new named section — when search budget exhausted, ping node3090,
  check/start firecrawl and camoufox, route remaining fetches through them.
  firecrawl = general web content; camoufox = reddit (JS-rendered, anti-bot).
  KB-first for startup procedures before attempting to start either service.
Root cause: `fetch_url` reddit fallback (Goethe v0.2.5) needs the model to know how to reach
  firecrawl/camoufox on node3090 when the search budget is exhausted on LUCIFER.

## v0.5.17 — 2026-06-28
**Changes from v0.5.16:**
- KB-FIRST RULE: new named section — `search_kb()` BEFORE any operational answer, BEFORE any
  tool call, BEFORE reasoning from training knowledge about this environment. Violation = guessing.
  Explicit violation examples added (answering "what is the fastest way to wake node3090" without KB,
  calling pfsense_graphql before search_kb, offering options from general Linux knowledge).
- ENVIRONMENT: goethe_mcp updated to v1.9.3 (was v1.3.0).
- ENVIRONMENT: MCP GW start command simplified — `bash start-goethe.sh`.
- search_kb entry in TOOLS: scope expanded to cover all operational questions, not just errors.
Root cause: model was answering operational questions from training knowledge instead of the KB,
  producing unverified answers that contradicted ground-truth KB entries.

## v0.5.16 — 2026-06-21
**Changes from v0.5.15:**
- ENVIRONMENT: Frontend updated OpenWebUI/3000 → llama-ui/8080 (built into llama-server).
  OpenWebUI retired. No separate frontend process.
- ENVIRONMENT: MCP Gateway entry added — goethe_mcp v1.3.0 on port 9700, started via
  `bash tools/start-goethe.sh`. Replaces direct OWUI tool injection.
- sudo_delegation_block: SURFACE RULE added — "described in thinking ≠ called". Calling the tool
  inside a collapsed think block is invisible to the user; tool call must appear in the response phase.
- compact_context: removed from TOOLS (OWUI-only, not exposed via goethe_mcp).
- HANDOVER PROTOCOL: updated — no compact_context step; write handover directly.
- KNOWLEDGE BASE: OpenWebUI section removed. llama-ui section added (served by llama-server at :8080,
  check via `ss -tlnp | grep ':8080'`).
Root cause: OpenWebUI retired as frontend; goethe_mcp decouples the LSE toolset from any frontend.
  ~/owui/ venv retained as Python runtime for goethe_mcp — not an app, just an env.

## v0.5.15 — 2026-06-06
**Changes from v0.5.14:**
- TOOLS: pfsense_log_summary + pfsense_query clarified (pfSense LOG RULE section).
- Added PFSENSE LOG RULE: never call raw firewall log endpoints directly; always use gateway script.
- ENVIRONMENT: bumped to v0.5.15, tool v1.5.18.

## v0.5.14 — 2026-06-04
**Changes from v0.5.13:**
- Fix A1: LUCIFER PORT TOPOLOGY — added Docker NAT isolation note to ENVIRONMENT section.
  SearXNG container binds port 8080 internally; Docker NAT means it does NOT conflict with
  llama-server's WSL2 host-level :8080 binding. Both services coexist.
  Also clarified llama-server's binding as "WSL2 host-level, visible at 0.0.0.0:8080".
Root cause: A1 test asked about port collision — model found llama-server on :8080 and
  warned it was unsafe, but didn't explain Docker NAT isolation of SearXNG's internal :8080.
  Missing fact was simply absent from the prompt topology description.

## v0.5.13 — 2026-06-04
**Changes from v0.5.12:**
- Fix P4: SUDO PIPELINE SPLIT — when sudo appears in a pipeline, offer to split into a
  non-sudo execute_command stage + a separate sudo_delegation_block stage.
- Fix M3: FILE NOT FOUND — on any file/command/path not found, always propose one concrete
  recovery action in the same response. Do NOT stop after reporting the error.
- Fix W1: STATIC PATH VERIFICATION — do not verify well-known static Linux filesystem paths
  (/etc/, /usr/, /proc/) with tool calls. Assume they exist.
- Fix A3: KNOWLEDGE BASE section updated — OpenWebUI is NOT systemd-managed. Use
  `pgrep -a open-webui` to check. Do NOT use systemctl start/stop/status for open-webui.
- ENVIRONMENT: bumped to v0.5.13, tool v1.5.18.
Root cause: Run 6 (58/63) gap analysis — 4 specific test failures mapped to missing rules.

## v0.5.9 — 2026-06-01
**Changes from v0.5.8:**
- OUTPUT RULES: added MULTI-BLOCK TASK RULE — on any 2+ block task, immediately write
  /opt/local-se/active-task.md with full checklist; update after each block; read at session
  start to resume from first unchecked block. File persists across context resets and chat jumps.
- HANDOVER PROTOCOL: must read active-task.md before compacting and include block status in summary.
Root cause: block milestone lists lived only in model context — lost on compaction, chat jumps,
  or session restarts with no persistent record of done vs pending.

## v0.5.8 — 2026-05-31
**Changes from v0.5.7:**
- ENVIRONMENT: added Grafana URL, KB path, RAG Tools v2, tool v1.5.9, ComfyUI paths
- PERMISSION BOUNDARY: explicit rule — never ask user to run apt/sudo in plain chat; always use sudo_delegation_block
- TOOLS execute_command: added ComfyUI venv pip install torch version guard (check before and after)
- TOOLS execute_command: added check_error_kb() call before killing/restarting any process
- TOOLS search_web: added search_kb() pre-call requirement and index_to_kb() post-call requirement
- TOOLS search_kb: added ES connection error recovery instruction
- TOOLS: added search_kb, index_to_kb, record_error, record_outcome, check_error_kb, mentor_correct entries
- TOOLS record_error/record_outcome: explicit clarification — different functions, different purposes
- OUTPUT RULES: added WARNING ESCALATION RULE — [WARNING] lines must be read, checked, and surfaced before task complete
- OUTPUT RULES: added BACKGROUND PROCESS RULE — check Grafana before intervening on any long-running process
- OUTPUT RULES: added SYSTEM PACKAGE INSTALLATION RULE — no speculative apt installs; require exact error evidence
Root causes: PyTorch cu124 rollback without reading [WARNING] cu130; libnccl proposed with no error evidence;
  download polling without Grafana check; index_to_kb() not called after web searches; record_error used for successes.

## v0.5.5 — 2026-05-29
**Changes from v0.5.4:**
- TOOLS: added `compact_context(summary)` entry — documents when to call it (🟠 HIGH ≥70%
  or 🔴 CRITICAL ≥85%), what to put in the summary, and the required post-call response.
- OUTPUT RULES: added NO AUTONOMOUS NOTE-WRITING rule — explicitly prohibits writing session
  notes or state files during active task execution. The only approved response to high context
  is `compact_context`. Writing notes during a task is declared a protocol violation.
  Root cause: model was writing notes in a loop as a self-preservation response to high context,
  destroying task focus and burning context faster. Notes do not preserve the KV cache;
  `compact_context` does.
- ENVIRONMENT: bumped to v0.5.5, tool v1.5.8.

---

## v0.5.4 — 2026-05-28
**Changes from v0.5.3:**
- ENVIRONMENT: removed context-monitor version reference; context monitoring now handled
  externally by Grafana → grafana-owui-adapter → OpenWebUI channel pipeline.
- TOOLS: `get_context_status()` reduced to one line — "Call only when the user explicitly
  asks about context health." Filter caveat removed (filter is retired).
- CONTEXT HANDOVER: removed entirely. The model does not need to track context fill.
  External alert pipeline (Grafana threshold > 0.8 on `llama_kv_cache_usage_ratio`) fires
  a notification to the `lse-alerts` OpenWebUI channel when context exceeds 80%.
- OUTPUT RULES: added minimal fallback — if the user explicitly asks to save session state,
  write `/opt/local-se/session-handover.md`. No autonomous trigger.

Root cause of v0.5.3 retirement: CONTEXT HANDOVER never worked reliably across any version.
Additionally, the v1.3.0 context monitor filter was silently inoperative — this llama.cpp
build exports metrics with `llamacpp:` prefix; the filter searched for
`llama_kv_cache_usage_ratio` (non-existent in this build), causing a silent no-op on every
turn. Architectural fix: moved monitoring entirely out of the model loop.

---

## v0.5.3 — 2026-05-27
**Changes from v0.5.2:**
- ENVIRONMENT: bumped tool to v1.5.7, context-monitor to v1.3.0.
- TOOLS: removed "call after 5th tool call" rule from `get_context_status`. With
  context-monitor v1.3.0 the filter fetches `/metrics` and injects fill % as a fact
  on every turn — the model must not call the tool proactively. Call only when the
  user explicitly asks about context health.
- OUTPUT RULES: removed "after your 5th tool call: call get_context_status" line —
  redundant and conflicting with filter-based injection.
- CONTEXT HANDOVER: rewritten to reference filter-injected signals (⚠ CONTEXT WARNING
  at ≥ 70%, 🔴 CONTEXT CRITICAL at ≥ 85%) rather than tool call return values. Added
  explicit note: "do not call get_context_status to check fill — read what the filter
  injects." Thresholds now match filter valve defaults exactly.

Root cause of v0.5.2 issue: prompt instructed model to call `get_context_status` after
every 5th tool call. With v1.3.0 active, this produced redundant tool calls and
conflicting threshold instructions (prompt: 70%, no floor; filter: injects fact silently
below 70%). Model followed both, calling the tool unnecessarily and emitting output
when it should have been silent.

---

## v0.5.2 — 2026-05-25
**Changes from v0.5.1:**
- Removed SUDO DELEGATION FORMAT section entirely — it specified a different format from what
  the `sudo_delegation_block` tool actually produces, causing the model to reformat tool output
  and enter a re-call loop. Root cause: format mismatch between prompt section and tool return value.
- Added "DO NOT call again." to the `sudo_delegation_block` one-liner in OUTPUT RULES — makes
  the stop-after-delegation requirement explicit without a separate format section.
- Added KB path (`/opt/local-se/kb/`) to KNOWLEDGE BASE section — model now knows where to
  direct read-only knowledge lookups.
- Updated version references: tool v1.5.5 · filter v1.1.0 · context-monitor v1.0.0

---

## v0.5.1 — 2026-05-24
**Changes from v0.5:**
- Added LIVE SERVICE RULE to PERMISSION BOUNDARY: hard stop before updating, rebuilding,
  or restarting any running service. Special case for llama-server — explicitly named as
  the active inference engine; model must emit sudo_delegation_block and stop, never rebuild live.
  Root cause: model updated a live llama.cpp build without checking pgrep, mangling the binary.
- Updated version references throughout: tool v1.5.3 · filter v1.1.0 · context-monitor v1.0.0
- Removed stale dev note from bottom of file

---

## v0.5 — 2026-05-24
**Changes from v0.4:**
- Added CONTEXT HANDOVER section — threshold-based state save + fresh-start instruction
- OUTPUT RULES: removed combine-commands (promoted to execute_command docstring in tool v1.5.0)
- OUTPUT RULES: added explicit get_context_status timing rule (after 5th tool call)
- TOOLS: tightened get_context_status description to match OUTPUT RULE

---

## v0.3-context-aware — 2026-05-23
**Changes from v0.2:**
- Added context budget awareness: agent checks `get_context_status` at start of each turn
- Added compaction trigger: structured compaction pass when fill > 70 %
- Added web search gate: explicit justification requ