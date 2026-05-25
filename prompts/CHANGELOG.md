# Prompt Version Changelog

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
