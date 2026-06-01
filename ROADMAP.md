# LSE Project Roadmap & Progress Report

**Last updated:** 2026-05-31 (RAG stack deployed; WAN2.1 deployment + RAG eval complete; model shootout v4 Runs 1-2 done)
**Current state:** Active development. RAG stack (ES + nomic-embed-text + rag_tools_v2) is live in OpenWebUI. WAN2.1 fully deployed on LUCIFER — inference test pending VRAM. Model shootout v4 paused at Run 2 (44/50). Supervisor Pipe track closed and deleted.

---

## Project Summary

The Local System Engineer (LSE) is a locally-hosted AI sysadmin agent running Qwen3.6-27B-Q4_K_M on llama.cpp via OpenWebUI. It operates within a strict permission boundary on a WSL2/Ubuntu 24.04 machine: execute commands, read/write files in allowed paths, delegate sudo to the user, search the web only when necessary, and monitor its own context budget.

**Current production versions:**

| Component | Version | Date |
|---|---|---|
| Tool | v1.5.9 | 2026-05-31 |
| RAG Tools | v2 (live) | 2026-05-31 |
| Prompt | v0.5.5 | 2026-05-29 |
| Routing filter | v1.1.0 | 2026-05-23 |
| Context monitor filter | ~~v1.3.0~~ retired | 2026-05-28 |
| Launch script (CLI) | v1.075 | 2026-05-31 |
| Launch script (GUI wrapper) | v1.1 | 2026-05-29 |
| Eval framework | v4 shootout (Runs 1-2 done) | 2026-05-30 |

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

## Completed — Session 2026-05-29 (late) — GUI v1.1 and Supervisor Pipe parallel build

Two pieces of work landed in this session that don't belong in the main tool-based stack lineage above. They are recorded here as their own block so the lineage of the main tool / prompt / launcher remains readable.

### GUI Launcher v1.1 — regression fix

`gui/lse-stack-launch-gui.ps1` was crashing the spawning PowerShell window on every *Launch Stack* click — silent, no captured error. Root cause: the click handler dispatched work to `[ThreadPool]::QueueUserWorkItem`. ThreadPool threads don't carry a PowerShell runspace, so the first command inside the work item (`Write-LaunchScripts`) threw `"There is no Runspace available"`; the `catch` block also needed a runspace and couldn't run; the exception escaped to the CLR and killed the powershell host.

- [x] Click handler rewritten: synchronous Write-LaunchScripts + Start-WTSession on the UI thread (which owns the runspace), then a `DispatcherTimer` for the 10-second model PID poll so the UI stays responsive without leaving the runspace.
- [x] Version label bumped to v1.1 (XAML banner + header comment in the .ps1).
- [x] Stale Authenticode signature stripped (the edits invalidated it). `.cmd` launchers use `-ExecutionPolicy Bypass` so unsigned runs fine; re-sign via `certsign.ps1` when convenient.
- [x] Errors now display in the GUI status line instead of killing the host.

### Supervisor Pipe — parallel architecture exploration (code-complete v0.3.1)

A separate prototype lives in the sibling folder `C:\Users\SY5\Documents\Claude\Projects\Local System Engineer Super Shell Terminal\`. It explores an alternative LSE architecture: instead of an OpenWebUI Tool, the LSE model emits **keyword directives** (`EXECUTE`, `LIST_DIR`, `READ_FILE`, `WRITE_FILE`, `GET_TIME`, `WEB_SEARCH`, `FETCH_URL`) which a Supervisor Pipe parses, gates, executes against Open Terminal (HTTP), and audit-logs. This is conceptually different from the main tool track — the model never holds tool definitions; the Supervisor enforces everything from the model's plain-text output.

- [x] Open Terminal API contract verified (POST `/execute` async, GET `/execute/{id}/status`, DELETE for kill); `OpenTerminalExecutor` rewritten as a poll-based client; echo-marker protocol removed (process-id isolation replaces it).
- [x] Open Terminal API key pinned in `~/.config/open-terminal/config.toml` (file is the single gate on bare-metal shell access, mode 600).
- [x] `_call_lse_model` wired to `open_webui.utils.chat.generate_chat_completion` (signature verified against the installed OpenWebUI; `__user__` dict resolved to a real user object via `Users.get_user_by_id`).
- [x] `WebClient` for SearXNG `WEB_SEARCH` (returns ranked title/URL/snippet) and `FETCH_URL` for full-page reads — SSRF-gated (loopback/private/link-local rejected, redirects re-validated each hop).
- [x] KB directive-protocol doc and system prompt updated to seven directives with proactive-search guidance (v0.3.1). KB re-uploaded to OpenWebUI Knowledge.
- [x] Stage C install-and-configure checklist written into the Super Shell Terminal runbook.
- [x] 29 + 22 unit tests pass; full-file `python3 -m py_compile` verified in the user's own WSL.

Sources: `Local System Engineer Super Shell Terminal/lse-supervisor-pipe.py`, `LSE-Deployment-Runbook.md`, `Local-System-Engineer-Architecture.md`, `LSE-system-prompt-revised.md`, `LSE-knowledge-base/01-directive-protocol.md`.

---

## Completed Work

### Infrastructure
- [x] llama.cpp + OpenWebUI + SearxNG + Playwright stack
- [x] Windows Terminal launcher with three model profiles (32k, 64k, no-think)
- [x] SearxNG rate-limit config (suspended_times correctly placed under `search:`)
- [x] VRAM budget documented (RTX 4090: 18–22 GB normal for 32k profile)
- [x] Stack health check one-liner and `lse:stack-health-check` skill

### Tool (openwebui-tool-v1.5.8.py)
- [x] execute_command — denylist, combine rule, live service rule, privileged path block
- [x] execute_command — POST-DELETE VERIFY RULE (v1.5.6)
- [x] execute_command — DESTRUCTIVE OPERATION PROTOCOL: confirm before rm/truncate/overwrite (v1.5.7)
- [x] read_file — routing rules, privileged path block
- [x] write_file — 5-step protocol, confirmation gate
- [x] sudo_delegation_block — return value semantics, stop protocol, read-first rule
- [x] search_web — announcement gate, single-call rule, NO YEAR INJECTION (v1.5.6)
- [x] get_context_status — correct field names for llama-server build ≥9307
- [x] get_github_release(repo) — live release lookup via GitHub API (v1.5.6)
- [x] compact_context(summary) — true in-place compaction via direct SQLite write + KV cache erase (v1.5.8)

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

## Completed — RAG Stack Deployment (2026-05-31)

Elasticsearch 8.17.0 (Docker, lse-net), Ollama CPU nomic-embed-text, and LSE RAG Tools v2 are all live in OpenWebUI. The self-improving KB loop is operational: `search_kb` → web fallthrough → `index_to_kb` → `record_error`/`record_outcome`/`mentor_correct`. 12 seed KB docs present. Error KB populated from WAN2.1 deployment session. Mentor-authority entries indexed for observability pattern (Grafana check before process intervention, quality 0.95).

**Known issue:** ES container exited with code 143 (SIGTERM — likely OOM). Investigate Docker memory limits and set a memory floor on the container. Also add ES health check to `lse:stack-health-check` skill.

---

## Completed — WAN2.1 Deployment (2026-05-31)

Full deployment on LUCIFER (RTX 4090, WSL2 Ubuntu 24.04). All models present and verified. Two workflows tested working (I2V, T2V basic). Two additional workflows patched and ready (T2V simplified, I2V upscale+framegen). ComfyUI Manager v4.2.1 active. wan2-manager.sh written. First end-to-end inference test pending VRAM availability (requires stopping llama-server).

WAN2.2 partially researched: 14B MoE (≥16 GB VRAM) and 5B hybrid (~8 GB) confirmed released, Apache 2.0, day-zero ComfyUI support. Deep-dive (Kijai GGUF builds, per-quant VRAM, benchmarks) deferred to next session.

---

## Immediate — write_file Overwrite Safety Gap (v1.5.9)

**Root cause identified 2026-05-29:** The LSE destroyed a 323-line GUI PowerShell file by calling `write_file` in overwrite mode with only a 5-line snippet. The existing `write_file` docstring requires a full read before overwrite and explicit confirmation — but compliance was zero in this instance. The model skipped both steps under the pressure of a recovery loop.

**Fix:** Add a new P-class eval test case covering `write_file` overwrite on a large existing file. The test must verify that the model:
1. Reads the full file before proposing any overwrite
2. States the current line count and the proposed new line count
3. Asks explicit yes/no confirmation before writing

This mirrors the DESTRUCTIVE OPERATION PROTOCOL added to `execute_command` in v1.5.7 — the same pattern needs enforcement weight in `write_file`.

**Also:** Add a `write_file` SIZE SANITY CHECK — if `mode=overwrite` and the new content is dramatically shorter than the existing file (e.g. <25% of current line count), the function should return an error requiring the model to confirm it intends to truncate.

- [ ] Write eval test case: write_file overwrite with size regression
- [ ] Add SIZE SANITY CHECK to write_file in v1.5.9
- [ ] Run targeted P-class eval subset against v1.5.9

---

## Immediate — Prompt v0.5.6

Four improvements identified from the WAN2.1 RAG eval session:

1. **BACKGROUND PROCESS RULE** — Before killing or restarting any background process, check Grafana at http://localhost:3002. Tool call timeouts (30s) do not mean a process stalled.
2. **`index_to_kb()` enforcement** — After every `search_web` that produces actionable findings, call `index_to_kb()`. Not optional.
3. **`check_error_kb()` proactive trigger** — Before killing or restarting any process, call `check_error_kb()` first.
4. **`record_outcome()` vs `record_error()` clarification** — These serve different purposes: `record_outcome(success=True)` increments `empirical_runs` on a KB doc; `record_error()` creates a new error pattern entry.

- [ ] Write v0.5.6 incorporating all four changes
- [ ] Run targeted eval subset confirming background-process and post-search-indexing behaviour

---

## Immediate — ES stability (lse-elasticsearch container)

Container exited with code 143 during session. Root cause unconfirmed.

- [ ] Check `dmesg` and Docker stats for OOM evidence
- [ ] Set `--memory` and `--memory-swap` limits on the container in Portainer
- [ ] Add ES health preflight to `lse:stack-health-check` skill
- [ ] Add proactive troubleshoot to `search_kb` docstring: if error contains 'connection refused', call `execute_command` with `docker ps -a --filter name=elasticsearch` before retrying

---

## ~~Immediate — Supervisor Pipe~~ CLOSED

The Supervisor Pipe / Super Shell Terminal repo has been deleted. This track is closed. the user observed during a Stage C smoke test: `FETCH_URL http://127.0.0.1:5000` was correctly refused by the SSRF gate, but the model immediately rerouted with `EXECUTE: curl http://127.0.0.1:5000` and the EXECUTE gate let it through — `curl` is neither denylisted nor on the mutation-pattern list. The structural issue: EXECUTE is a general shell, so a *denylist* on it is porous; anything `FETCH_URL`/`READ_FILE`/`WRITE_FILE` would escalate can be done with the equivalent shell command.

**Fix decided, implementation paused:** flip the EXECUTE gate to an allowlist. Auto-run only a defined set of read-only inspection commands (`ls`, `cat`, `head`, `tail`, `stat`, `find`, `grep`, `sort`, `uniq`, `cut`, `tr`, `diff`, `wc`, `du`, `df`, `ps`, `ss`, `ip`, `uname`, `hostname`, `uptime`, `whoami`, `id`, `groups`, `date`, `free`, `lsof`, `dmesg`, `printenv`, `which`, `whereis`, `apt-cache`, `dpkg-query`, the `echo`/`printf`/`true`/`false`/`test`/`cd`/`pwd` builtins). Everything else escalates. Also: escalate on opaque constructs (`$(`, backtick, `<(`, `>(`); escalate on file-writing redirection (preserving safe `2>&1`/`>/dev/null`); escalate on secret-path references (`~/.ssh`, `/etc/shadow`, `/etc/sudoers`, `/etc/ssl/private`, `/root`); special-case `find -exec`/`-delete`/`-ok`.

Pivoted to the GUI v1.1 fix before this change was applied. Picking it up is the first thing on the next session's plate.

- [ ] Replace `MUTATION_PATTERNS` with `EXECUTE_ALLOWLIST` + `EXECUTE_SECRET_PATHS` + helpers in `lse-supervisor-pipe.py`
- [ ] Rewrite the EXECUTE branch of `gate()` to call `_classify_execute()`
- [ ] Add `_execute_segments` + `_classify_execute` helpers
- [ ] Extend the test_pipe.py logic suite (curl/python3/etc. escalate; cd-and-ls passes; sensitive-path-via-cat escalates; `2>&1` allowed; `> file` escalates)
- [ ] Update `LSE-knowledge-base/02-denylist.md` and the system prompt §6 ("Respect the gate") to explain the allowlist model so the model expects EXECUTE escalations more often

## Open — Supervisor Pipe: intermittent missing final reply

Observed in the Stage C smoke test: occasionally the chat shows the `▶ step N` directive lines but no final assistant reply afterwards. Cause not yet diagnosed. Plausible suspects, in order: (a) `generate_chat_completion` returning a non-OpenAI-shaped object on some code paths in the installed OpenWebUI build (the `_call_lse_model` extraction would `RuntimeError` and the Pipe surfaces no final text); (b) Open Terminal `/execute/{id}/status` paginating output by `next_offset` for large outputs (we currently read `state["output"]` once on `status="done"` — windowing would lose data); (c) the model rarely emits an empty reply that the parser treats as "done" with `reply.strip()` returning empty.

- [ ] Capture a concrete failing chat transcript with `/home/sy5/automation/lse-audit.log` lines for the affected directives, plus the OpenWebUI server log around that timestamp
- [ ] Confirm or rule out (a) by inspecting the actual `resp` shape with a temporary log line in `_call_lse_model`
- [ ] Confirm or rule out (b) by checking whether the failing case had unusually large EXECUTE output and whether `next_offset > len(output)` was returned

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
`README.md` is severely out of date —