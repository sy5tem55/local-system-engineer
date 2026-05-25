# LSE Project Roadmap & Progress Report

**Last updated:** 2026-05-25  
**Current state:** Active development — Run 5 prep in progress

---

## Project Summary

The Local System Engineer (LSE) is a locally-hosted AI sysadmin agent running Qwen3.6-27B-Q5_K_M on llama.cpp via OpenWebUI. It operates within a strict permission boundary on a WSL2/Ubuntu 24.04 machine: execute commands, read/write files in allowed paths, delegate sudo to the user, search the web only when necessary, and monitor its own context budget.

**Current production versions:**

| Component | Version | Date |
|---|---|---|
| Tool | v1.5.5 | 2026-05-25 |
| Prompt | v0.5.2 | 2026-05-25 |
| Routing filter | v1.1.0 | 2026-05-23 |
| Context monitor filter | v1.0.0 | 2026-05-23 |
| Launch script | v1.061 | 2026-05-25 |
| Test suite | v3.2 | 2026-05-25 |

**Eval score trajectory:**

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored baseline |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (budget 3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think (budget 0) | 49/57 |

Run 4's 49/57 is not a regression — it's a no-think mode experiment. The 57/57 ceiling from Run 3 has not been re-confirmed against the current versions. Run 5 will establish that baseline.

---

## Completed Work

### Infrastructure
- [x] llama.cpp + OpenWebUI + SearxNG + Playwright stack
- [x] Windows Terminal launcher with three model profiles (32k, 64k, no-think)
- [x] SearxNG rate-limit config (suspended_times correctly placed under `search:`)
- [x] VRAM budget documented (RTX 4090: 18–22 GB normal for 32k profile)
- [x] Stack health check one-liner and `lse:stack-health-check` skill

### Tool (openwebui-tool-v1.5.5.py)
- [x] execute_command — denylist, combine rule, live service rule, privileged path block
- [x] read_file — routing rules, privileged path block
- [x] write_file — 5-step protocol, confirmation gate
- [x] sudo_delegation_block — return value semantics, stop protocol, read-first rule
- [x] search_web — announcement gate, single-call rule
- [x] get_context_status — correct field names for llama-server build ≥9307

### Prompt (v0.5.2)
- [x] Three-tier permission model (execute / delegate / deny unconditionally)
- [x] Context handover protocol (70% threshold → save state → fresh start)
- [x] LIVE SERVICE RULE (pgrep before any rebuild/restart)
- [x] Web search gate (announce reason before calling)
- [x] SUDO DELEGATION FORMAT conflict resolved (section removed in v0.5.2)

### Eval infrastructure
- [x] Test suite v3.2 (19 tests across S/P/M/W/A categories)
- [x] `lse:eval-runner` skill — structured session guide with scoring rubric
- [x] 4 eval runs completed with written reports

### Skills (all have SKILL.md + evals.json)
- [x] `lse:eval-runner` — structured eval session guide
- [x] `lse:docstring-optimizer` — reviews docstrings against LSE failure history
- [x] `lse:stack-health-check` — pre-session service verification
- [x] `lse:session-debrief` — end-of-session KB update guide
- [x] `lse:version-manager` — changelog + co-test matrix management

### Documentation
- [x] `docs/01-model-evaluation.md` — model selection rationale (updated to Qwen3.6-27B)
- [x] `docs/02-terminal-interaction.md` — OpenWebUI tool design and safety model
- [x] `docs/03-context-management.md` — context observability and remediation
- [x] `docs/04-knowledge-base.md` — KB design and injection strategy
- [x] `docs/05-skills-planning.md` — skills roadmap (largely completed)
- [x] `docs/06-safety-and-delegation.md` — three-tier model, denylist, SEP template
- [x] `docs/07-operations-runbook.md` — stack start, recovery, hot-swap, shutdown

---

## Immediate — Run 5 Prep

These are the specific items needed before Run 5 can produce a clean score.

### Tool v1.5.6 (three changes)

**1. Fix P3 — post-delete verify step missing**  
Add to `execute_command` docstring (or write_file if destructive-delete path lives there):  
"After any deletion, always verify with a follow-up call confirming the file/directory no longer exists."

**2. Fix W2 — search query date injection**  
Add to `search_web` docstring:  
"Do not append a year to the query — use the current date from the system prompt if recency matters, not your training-data estimate of the year."

**3. Add `get_github_release(repo)` function**  
New function querying `https://api.github.com/repos/{repo}/releases/latest`. Directly solves the W2 llama.cpp version lookup without SearxNG. Read-only, narrow scope.

### Test suite v3.3 (four precondition fixes)

**P2:** Change target setting from `vm.swappiness=10` (already present in `/etc/sysctl.conf`) to `vm.dirty_ratio=20` to force the write path.

**M2:** Change alias from `ll='ls -lah --color=auto'` (already in `.bashrc` at line 21) to `alias gs='git status'` to force the 5-step write protocol.

**A2:** Run inside a session with >70% context fill to exercise the save-state + fresh-start path. Current test hits 35% — the high-context response path is never triggered.

**A3:** Redesign prompt so commands cannot be trivially semicoloned. Current "run these 5 commands in sequence" correctly triggers the combine rule from S1. Use prompts that require separate calls (e.g. "check if process X is running, then if it is, show its open ports").

### Context monitor filter — debug flag cleanup

Change `debug: bool = Field(default=True, ...)` back to `default=False` in `lse-context-monitor-v1.0.0.py`. The runtime valve is already set to False from the UI — this is a code hygiene item only. Hot-swap via Admin → Functions after editing.

### Run 5

Run the full test suite (v3.3) against tool v1.5.6 + prompt v0.5.2 with the standard 32k profile (`--reasoning-budget 3072`). Expected target: reproduce 57/57 or close to it, confirming the current production versions are solid.

---

## Medium-Term

### README update
`README.md` is severely out of date — still references Gemma 4 and the v0.3 prompt as "latest". Should be updated to reflect Qwen3.6-27B, the full component stack, current version table, and accurate repo layout.

### Architecture decision: filter vs tool for context monitoring
The context monitor is currently an OpenWebUI filter (inlet hook). An alternative is moving the trigger logic into the tool itself — specifically having `execute_command` track a call counter and emit a `get_context_status` reminder when the count hits threshold. The filter approach is cleaner (model-agnostic, no tool pollution) but has shown one failure mode (Run 4 no-think regression). Evaluate after Run 5.

### `get_github_release` — extend scope if useful
After shipping for llama.cpp, assess whether the function is useful for other packages (open-webui releases, Ubuntu package versions via GitHub). Could replace a whole class of W2-type searches.

### `fetch_url(url)` function consideration
A read-only URL fetcher (no code execution, localhost blocked) would allow the model to read documentation pages, GitHub raw files, and man pages online. Lower priority than the Run 5 fixes — assess after Run 5.

### L1 test (LIVE SERVICE RULE)
Test added to eval suite for the LIVE SERVICE RULE (pgrep check before rebuild). Verify it's in test-suite v3.3 and covered in the eval-runner skill.

---

## Deferred / Not Planned

- `engineering:incident-response` — solo dev environment, no on-call structure
- `engineering:standup` — solo project
- `engineering:deploy-checklist` — eval-runner covers this implicitly
- Generic Python REPL tool from community — bypasses all LSE safety controls; not worth the risk
- OpenWebUI Skills system — LSE uses Tools (admin-level), not Skills (workspace-level); Skills tab is empty and unrelated

---

## Key Architectural Principles (stable)

1. **Three-tier model:** execute directly / delegate via sudo_delegation_block / deny unconditionally. No exceptions to the deny tier.
2. **Confirmation before write:** any file write or destructive operation requires the model to show the proposed change and wait for an explicit yes.
3. **Read before write:** any sudo operation that modifies a config file must read the file first to check current state.
4. **Context-first:** session state is saved to `/opt/local-se/session-handover.md` when context exceeds 70%. The KB at `/opt/local-se/kb/` is the persistent knowledge store.
5. **Eval-driven development:** every version bump gets an eval run before being considered production-ready.
6. **No silent escalation:** sudo is never run autonomously. Every privilege escalation is visible, explicit, and in the user's hands.
