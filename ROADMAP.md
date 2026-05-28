# LSE Project Roadmap & Progress Report

**Last updated:** 2026-05-28  
**Current state:** Active development — Run 6 pending; context monitoring decoupled to Grafana pipeline

---

## Project Summary

The Local System Engineer (LSE) is a locally-hosted AI sysadmin agent running Qwen3.6-27B-Q5_K_M on llama.cpp via OpenWebUI. It operates within a strict permission boundary on a WSL2/Ubuntu 24.04 machine: execute commands, read/write files in allowed paths, delegate sudo to the user, search the web only when necessary, and monitor its own context budget.

**Current production versions:**

| Component | Version | Date |
|---|---|---|
| Tool | v1.5.7 | 2026-05-26 |
| Prompt | v0.5.4 | 2026-05-28 |
| Routing filter | v1.1.0 | 2026-05-23 |
| Context monitor filter | ~~v1.3.0~~ retired | 2026-05-28 |
| Launch script | v1.070 | 2026-05-27 |
| Test suite | v3.5 | 2026-05-26 |

**Eval score trajectory:**

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored baseline |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (budget 3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think (budget 0) | 49/57 |
| Run 5 (partial) | v1.5.6 | v0.5.2 | thinking (budget 3072) | 15/21 subset |

Run 4's 49/57 is not a regression — it's a no-think mode experiment. Run 5 was a targeted subset eval confirming P2 (3/3), W2 (3/3), A3 (3/3) fixes. P1/P3 were 0/3 — root cause: execute_command lacked a destructive-op confirmation gate. Fixed in v1.5.7. A1 was 0/3 — root cause: questions answerable from model inference; context monitor never triggered. Fixed in v1.2.0 + test-suite v3.5. Run 6 will be the first full scored run against the corrected stack.

---

## Completed — Grafana Context Alert Pipeline (2026-05-28)

Context monitoring fully decoupled from the LSE model. The v1.3.0 inlet filter has been
retired — it was silently doing nothing because this llama.cpp build exports metrics with
the `llamacpp:` prefix, not the `llama_` prefix the filter expected.

**Architecture:**

```
llama-server /slots + /metrics
        ↓
llama-context-exporter (port 9836, systemd)
  → computes llama_kv_cache_usage_ratio = n_tokens_max / n_ctx
  → n_ctx is dynamic: 32768 (32k profile) or 65536 (64k profile)
        ↓
Prometheus scrapes every 15s
        ↓
Grafana alert: llama_kv_cache_usage_ratio > 0.8, for=1m
        ↓
grafana-owui-adapter (port 9837, systemd)
  → converts Grafana JSON payload → {"content": "⚠ ..."}
        ↓
OpenWebUI channel webhook → lse-alerts channel
```

**Services installed:**
- [x] `llama-context-exporter` — `/opt/local-se/llama-context-exporter.py`, port 9836
- [x] `grafana-owui-adapter` — `/opt/local-se/grafana-owui-adapter.py`, port 9837
- [x] Prometheus scrape job `llama-context-exporter` targeting `172.17.0.1:9836`
- [x] Grafana contact point `OpenWebUI LSE Alerts` → `http://172.17.0.1:9837`
- [x] Grafana alert rule `LSE Context Fill > 80%` (folder: LSE, group: lse-context)
- [x] OpenWebUI channel `lse-alerts` with webhook `Grafana Context Monitor`
- [x] Docker network `lse-net` consolidating grafana, prometheus, vaultwarden, node-exporter, searxng
- [x] End-to-end smoke test passed — message delivered to lse-alerts channel

**Retired:**
- [x] `lse-context-monitor-v1.3.0.py` inlet filter — disable in OpenWebUI Admin → Functions
- [x] Prompt CONTEXT HANDOVER section removed in v0.5.4

---

## Completed Work

### Infrastructure
- [x] llama.cpp + OpenWebUI + SearxNG + Playwright stack
- [x] Windows Terminal launcher with three model profiles (32k, 64k, no-think)
- [x] SearxNG rate-limit config (suspended_times correctly placed under `search:`)
- [x] VRAM budget documented (RTX 4090: 18–22 GB normal for 32k profile)
- [x] Stack health check one-liner and `lse:stack-health-check` skill

### Tool (openwebui-tool-v1.5.7.py)
- [x] execute_command — denylist, combine rule, live service rule, privileged path block
- [x] execute_command — POST-DELETE VERIFY RULE (v1.5.6)
- [x] execute_command — DESTRUCTIVE OPERATION PROTOCOL: confirm before rm/truncate/overwrite (v1.5.7)
- [x] read_file — routing rules, privileged path block
- [x] write_file — 5-step protocol, confirmation gate
- [x] sudo_delegation_block — return value semantics, stop protocol, read-first rule
- [x] search_web — announcement gate, single-call rule, NO YEAR INJECTION (v1.5.6)
- [x] get_context_status — correct field names for llama-server build ≥9307
- [x] get_github_release(repo) — live release lookup via GitHub API (v1.5.6)

### Prompt (v0.5.2)
- [x] Three-tier permission model (execute / delegate / deny unconditionally)
- [x] Context handover protocol (70% threshold → save state → fresh start)
- [x] LIVE SERVICE RULE (pgrep before any rebuild/restart)
- [x] Web search gate (announce reason before calling)
- [x] SUDO DELEGATION FORMAT conflict resolved (section removed in v0.5.2)

### Eval infrastructure
- [x] Test suite v3.5 (21 tests — unfakeable A1 questions, all preconditions verified)
- [x] `lse:eval-runner` skill — structured session guide with scoring rubric
- [x] 4 full eval runs + 1 partial targeted subset (Run 5) with written reports
- [x] .gitattributes — CRLF enforcement for PS1 files across WSL/Windows boundary

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

## Immediate — Run 6

Full scored eval against the corrected stack. All precondition fixes are in place.

**Stack for Run 6:**
- Tool: v1.5.7 (DESTRUCTIVE OPERATION PROTOCOL)
- Prompt: v0.5.3 (aligned with context-monitor v1.3.0 — no proactive get_context_status)
- Context monitor: v1.3.0 (self-fetching filter — no model action required)
- Test suite: v3.5 (unfakeable A1 questions)
- Profile: 32k · MTP · thinking (--reasoning-budget 3072)

**Deploy checklist before Run 6:**
- [x] Hot-swap tool to v1.5.7 in OpenWebUI Admin → Tools
- [x] Hot-swap context monitor to v1.3.0 in OpenWebUI Admin → Functions
- [x] Hot-swap prompt to v0.5.3 in OpenWebUI Admin → Models
- [ ] Set metrics_url valve to http://localhost:8080/metrics (default is correct)
- [ ] Verify debug flag is OFF (valve in UI)
- [ ] Fresh conversation (no prior tool-call history)
- [ ] Run all 21 questions per test-suite-v3.5 using lse:eval-runner skill

**Expected outcome:** P1/P3 confirmation gates enforced by v1.5.7. Context fill injected as a fact by v1.3.0 — model reacts to ⚠/🔴 signals without calling get_context_status. A1 questions are unfakeable. Targeting 19–21/21.

---

## Completed — Grafana Metrics Integration

The launcher v1.063 added `--metrics` to the llama-server command, exposing a Prometheus-compatible endpoint at `http://localhost:8080/metrics`. Dashboard build completed 2026-05-26.

- [x] `--metrics` flag in launcher v1.063
- [x] Prometheus scrape config targeting `localhost:8080/metrics`
- [x] Grafana dashboard with llama.cpp performance panels
- [ ] Add metrics endpoint reference to ops runbook (docs/07-operations-runbook.md)

---

## Medium-Term

### README update
`README.md` is severely out of date — still references Gemma 4 and the v0.3 prompt as "latest". Should be updated to reflect Qwen3.6-27B, the full component stack, current version table, and accurate repo layout.

### Architecture decision: filter vs tool for context monitoring
**Resolved in v1.3.0.** All compliance-based approaches (v1.0–v1.2) failed because task-focused models always prioritise answering the user over calling a meta-tool. v1.3.0 removes the model from the loop: the filter fetches context fill from `/metrics` directly and injects it as a fact in the system message. The model reads it and acts naturally — no tool call required. The `/metrics` endpoint is available thanks to launcher v1.063.

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
