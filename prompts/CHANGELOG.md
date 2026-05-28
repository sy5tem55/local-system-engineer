# Prompt Version Changelog

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
- Added web search gate: explicit justification required before any `search_web` call
- Added path compression rule: Windows paths translated once, Linux path used thereafter
- Added output compression directive: agent extracts key facts from verbose tool output immediately
- Added token budget estimation step inside plans
- Added hard reset procedure instruction
- Tightened step-by-step protocol with explicit "STEP N" labelling
- Added few-shot compaction example

**Test result target:** Pass all M1–M4 long-context tests with no more than 1-point drop from mid-context baseline.

---

## v0.2-structured — 2026-05-23
**Changes from v0.1:**
- Added explicit tool use protocol section
- Added sudo delegation protocol with `SUDO_REQUIRED` block format
- Added step-by-step execution requirement with numbered plan format
- Added error handling protocol
- Tightened allowed/blocked path definitions
- Added web search declaration requirement (no justification gate yet — that's v0.3)
- Added confirmation requirement before destructive writes

**Test result target:** Pass S1–S5 short-context tests perfectly; M1–M4 mid-context with score ≥ 10/12.

---

## v0.1-baseline — 2026-05-23
**Initial version.** Minimal role definition, basic constraints, and tool listing. No structured protocols — used to establish a baseline eval score.

**Test result target:** Pass S1–S5 short-context tests. No expectation of long-context reliability.
