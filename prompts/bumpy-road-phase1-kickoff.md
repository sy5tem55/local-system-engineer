# Kickoff: goethe.py Bumpy Road refactor — Phase 1 verification

Paste this as the first message of the new thread.

---

We are refactoring `tools/goethe.py` in the LSE project to fix CodeScene "Bumpy Road" findings.
Repo (from WSL via goethe MCP): `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer`
Branch: `refactor/bumpy-road-phase1` — the LSE commits one extraction per commit (no diffs handed over; verify via `git log` / `git show`).

## Prior state (already verified, do not redo)
- CodeScene ACE cannot auto-refactor Python (JS/TS/Java only); no API token available (trial). Verification is done locally: AST metrics + tests, CodeScene UI re-scan manually per phase.
- The LSE's bumpy_road_report.md was validated against source via AST: all 10 line ranges exact, depths confirmed (execute_command 2308–2714 depth 6; planner 6728–6997 depth 4; verify_source_claims 4021–4190 depth 5).
- Two boundary corrections were applied to the LSE's instructions:
  1. `_validate_command_safety` covers 2498–2551 (includes `_dl_block` + `_is_allowed_read(cwd)` checks); SSH fingerprinting starts ~2552 and is Phase 3.
  2. In `planner`, `_parse_planner_envelope` (6870–6900) is nested inside `_call_planner_backend` (6862–6920) — extract parser first in Phase 2, backend helper calls it.

## Phase 1 scope (LSE is executing)
1. execute_command → `_validate_command_safety(self, command, cwd) -> Optional[str]` (lines 2498–2551)
2. fetch_url → `_extract_text_from_html(self, html, max_chars) -> str`
3. verify_source_claims → `_extract_pdf_text(self, pdf_bytes) -> str` (pdfminer→pypdf chain, ~4100–4125)

## Your job in this thread
Create a task block and work it:
1. Check branch exists and list commits: `git -C /mnt/c/... log --oneline main..refactor/bumpy-road-phase1`
2. Per commit: `git show <sha>` — confirm verbatim code movement, no logic/string changes, correct call-site wiring.
3. Re-run AST gate independently (ast.parse + per-function line count and max nesting depth for the 3 touched functions). Pass criteria: execute_command < 360 lines, fetch_url < 140, verify_source_claims < 145, no function deeper than before (baselines: 407/6, 178/4, 170/5).
4. Confirm test suite passed (LSE ran it per commit; re-run once via goethe `run_tests` or execute_command).
5. If all green: approve merge to main, remind me to re-scan in CodeScene UI (http://localhost:3004) and record the Code Health delta for goethe.py.
6. On failure: identify the offending commit, instruct revert of that commit only, hand corrected instructions back to the LSE.
7. When done, log the session learnings to the KB (lse-session-debrief skill).

Rules: verify with tools, don't trust the LSE's summary; the live goethe tool in OpenWebUI must not be reloaded from the branch — merge first, reload after.
