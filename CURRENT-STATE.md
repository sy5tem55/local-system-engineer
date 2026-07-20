# LSE Current State
> Last updated: 2026-07-20 (Cowork)
> Source of truth for deployed versions. Update this file at the end of every session.

---

## Deployed Versions

| Component | Version | File | Status |
|---|---|---|---|
| **LSE Tool (LUCIFER)** | **Goethe v0.4.0-a** | `tools/goethe.py` | ✅ **DEPLOYED** (2026-07-12, HTTP gateway restarted, PID confirmed listening :9700) — TRAUM Thread 3 (TRAUM-INSIGHT): `[DREAM]` digest banner rides the same once-per-session gate as `[TIME]` (Prompt 3.5); `time_check()` now also carries `[DREAM]` (Thread 3 close fix — see TRAUM row); patterns/insights cross-session mining, prompt-rule proposals (`prompts/learned-rules.md`, human-gated), null-result discipline. 306/306 tests green, run live against LUCIFER's real `lse-kb`/ES (not mocked). Cutoff 2026-01 in gateway env. REMINDER: llama-ui threads snapshot the tool schema — start a FRESH thread after any gateway deploy (this deploy included — existing llama-ui threads have NOT picked this up yet) |
| **LSE Tool (node3090)** | **Goethe v0.3.6** | `tools/goethe.py` (rsynced via start-goethe-node3090.sh) | ✅ **DEPLOYED** (2026-07-03) — Gemma-4-31B serving on :8080 (unified Q4 cache) as cross-family planner backend. run_tests scopes needing rag//tests/ report SKIP there (assets not rsynced; REPO_DIR valve). Swap/restore scripts in tools/ |
| **MCP Gateway** | **goethe_mcp v1.12.0** | `tools/goethe_mcp.py` | ✅ **DEPLOYED** (2026-07-20, restarted, gateway confirmed reloaded — see Goethe Console row) — `_TokenGuard` accepts `Bearer <token>` or raw token; port 9700; started via `bash tools/start-goethe.sh`. TRAUM episode journaling live: every tool call appends a redacted, capped JSONL line; day-dir cap 500MB default; blanket-redacts `_SENSITIVE_TOOLS` results. **1.11.1→1.12.0**: mounts Goethe Console (`tools/goethe_ui.py` UIRouter) into the HTTP stack outside `_TokenGuard` so `/ui` loads tokenless while `/api/ui/*` stays token-gated by the router itself; fail-safe (a broken console never takes down `/mcp`), `GOETHE_UI=off` disables. Built 2026-07-19, actually deployed 2026-07-20 — this is the version bump that had been sitting uncommitted for a day. |
| **TRAUM (dreaming workstream)** | **Threads 1–4 complete** | `docs/traum-dreaming-plan.md`, `docs/dreaming/` | ✅ **PRODUCTION READY** — Thread 1 (TRAUM-CORPUS) shipped 2026-07-11: episode journaling + manifest/rotation live on the gateway; SCRIBE-1/2/3 (debrief write path, backfill distiller, contradiction check). Thread 2 (TRAUM-ENGINE) CLOSED 2026-07-11: `dream_runner.py`/`dream_apply.py` (offline propose / human-gated apply) live; first supervised dream (13 sessions, 368 docs) — 3 dedup merges applied, all 7 stale-contradiction + 1 error-cluster proposals correctly rejected at the gate; no retrieval regression. **Thread 3 (TRAUM-INSIGHT) CLOSED 2026-07-12**: patterns pass (3.1, mechanical log mining, no LLM); insights pass (3.2, cross-session LLM mining with verbatim-evidence enforcement → kb-fact/skill-candidate/prompt-rule proposals); ledger-mining recon against `tasks.db` (3.3, done as a one-off analysis doc — `kb/ledger-mining-proposals.md` — never turned into an automated dream_runner.py pass); `dream_digest.py` (3.4, ≤30-line digest, applied/insights/pending sections); `[DREAM]` in-session banner (3.5, rides `[TIME]`'s once-per-session gate); prompt-rule proposals → `prompts/learned-rules.md`, human-merge-only, never touches `prompts/node4090-*` (3.6, `append_learned_rule`, target invariant enforced at both generation and apply time); null-result discipline — every pass emits a structured `looked`/`corpus_size`/`thresholds` record so "nothing there" is distinguishable from "didn't look" (3.8); test coverage extended (patterns.json determinism, digest/banner caps, learned-rules target-invariant, insight schema — 3.9). **Deployed live to LUCIFER 2026-07-12** (Goethe v0.4.0-a, HTTP gateway restarted): `[TIME]`+`[DREAM]` banner confirmed appearing together on a real first `search_kb` call against real digest content. **Live-deploy fix, same close**: `time_check()` shared `_time_banner_emitted` with `_consume_time_banner()` but never appended `[DREAM]` itself — a session calling `time_check()` first (which the system prompt's own TIME DISCIPLINE section tells the model to do for date-sensitive work) permanently lost the `[DREAM]` banner for the rest of that session; fixed so both banners always ride together regardless of which tool fires first. **Live-deploy finding, not yet fixed — flagged for Thread 4**: `report.md`/`proposals.jsonl` are single-pass-per-day-dir snapshots (by design, pre-3.8) — running a multi-pass "full cycle" without applying each pass's proposals first silently discards earlier passes' real pending proposals when a later pass overwrites the same day-dir. Recovered by hand this close (re-ran dedup last); Prompt 3.8 fixed this for null-results only (append-mode `null-results.jsonl`), not for real proposals. **Live-deploy finding, security, flagged for Thread 4**: the `patterns` pass's `command_frequency` mining reads `agent_commands.log` verbatim with no secret-redaction — a real run surfaced a live plaintext password embedded in a repeated `sshpass` command; had this been run with `--no-dry-run` it would have written the credential into a git-tracked `patterns.json`/`report.md`, and the `insights` pass would have sent it off-host to node3090's LLM as prompt "evidence." Not run for real this close as a result — the `patterns`/`insights` findings in this close's digest review come from a `--dry-run` preview only, deliberately not persisted. Operator should rotate the credential and move it to Vaultwarden; a redaction pass belongs in `dream_runner.py` before Thread 4 (TRAUM-AUTO) considers any auto-apply. **Thread 4 (TRAUM-AUTO) CLOSED 2026-07-13 — WORKSTREAM COMPLETE (v0.4.0 line = TRAUM era)**: both flagged findings FIXED before anything else (pass-scoped `report-<pass>.md`/`proposals-<pass>.jsonl` end the multi-pass day-dir clobber, readers glob + stay legacy-compatible; `redact_log_text()` scrubs `agent_commands.log` at parse time — `sshpass -p`/Bearer/assignment-shaped secrets never reach patterns.json, reports, or the off-host LLM; credential rotation itself still on the operator). 4.1: repository-owned `goethe-dream.service`/`.timer` installed live with the fail-visible five-pass cycle, authoritative checkout, 45-minute outer timeout, and `ignore_errors=no`; timer enabled/active for 03:30 + jitter. Manual acceptance returned `Result=success`; every pass correctly honored the 30-minute active-session guard and the digest refreshed. Prompt 3.3 ledger mining remains the reviewed one-off `kb/ledger-mining-proposals.md`, not a generic nightly pass. 4.2: lockfile + 30-min session-activity guard + per-run budgets (LLM calls, 45-min wall clock) + structural no-dream-of-dreams assert. 4.3: crash discipline (FAILED-banner partial report, `crashes.jsonl`, `record_error` provenance=dream-infra, sessions NOT marked dreamed, 3-failed-nights digest escalation) — verified by fault injection through the real `main()`. 4.4: `dream_apply --queue` (oldest-first, grouped, 14-day auto-expiry with reason, fail-closed on malformed day-dirs). 4.5/4.6: A/B eval designed pre-registered, then RUN — **verdict LOSS (A=53/60, B=51/60), recorded as-is**; root cause methodological (≈15-min divergence window, n=1, unpinned sampling — see `eval/eval-report-traum-1.md` §6-7), retrieval metrics bit-identical between conditions, `record_error` `6122c47830260f4e` filed. NOTE: no true pre-dreaming ES snapshot existed (no snapshot repo configured) — Condition A was frozen-at-eval-start; `eval/v35_harness.py` is a reconstruction (original never committed; `.gitignore` blanket-ignored `eval/` — carve-out added at this close for the 5 citable artifacts). 4.7: `docs/threat-model-kb.md` (Shostack ×4; found origin=web/human/local-probe tagging UNIMPLEMENTED in live `index_to_kb` — laundering protection is a blunt ceiling; all 22 cited test node-id groups re-verified 2026-07-13). 4.8: **`DREAM_AUTO_APPLY` stays empty; nightly cadence retained** — decision + evidence in DESIGN.md §7.4 (measurement window starts with first unattended cycle; revisit trigger recorded). 4.9: runbook §10 "Dreaming operations" (every command executed live), VALVES.md +17 Thread-4 valve rows, README layout. Full suite: 420 passed on `/usr/bin/python3`; shell syntax and tracked systemd units also verify cleanly. Interpreter note: tracked units run `/usr/bin/python3` (ES client 9.4.1, verified against live ES 9.4.3); owui venv still carries 8.19.3 — **no requirements.txt pins the client anywhere; drift risk stands** (2026-07-11 unpinned-pip lesson). |
| **Goethe Console (web UI)** | **goethe_ui v0.2.0** | `tools/goethe_ui.py` + `tools/goethe_dashboard.html` | ✅ **DEPLOYED** (2026-07-20, gateway restarted, mount confirmed live at `GET :9700/ui`) — dashboard surfacing KB trust lifecycle, TRAUM digest + 14-night cycle table, tasks.db ledger step progress (now with a per-task **backend** column, see Planner Backends row), 7-day episode stats. Stdlib-only (urllib/sqlite3-ro/file reads — no ES client, per the drift-risk note below); `/api/ui/*` gated by GOETHE_MCP_TOKEN; static `/ui` page tokenless. Tests: `tests/test_ui_router.py` 15/15, still green against the v0.2.0 file (no regression from the panels added below). **v0.1.1 (2026-07-19)**: KB panel 400 fix — `lse-kb` alias's source_tier/volatility/origin are mapped text+`.keyword`, not raw keyword; terms aggs now target `.keyword`. **v0.2.0 (2026-07-20)**: two new panels, the Console's first and only write surface (everything else stays strictly read-only by construction, see the module docstring) — **Permissions**: `GET /api/ui/perms` + `POST /api/ui/perms/{approve,deny,revoke}` against `goethe_perms.py`'s SQLite grants/requests tables, three-way approve-always / approve-once / deny UI matching the CLI exactly, confirm-gated on the persistent "always" action, auto-hides a reminder that `sudo`-kind grants still need `goethe-perm sync-sudoers` run by hand (the Console never touches `/etc/sudoers.d/`). **Planner Backend status**: `GET /api/ui/backends`, active backend + per-backend configured/health (no live pings to paid APIs on refresh — see Planner Backends row). Product track: `docs/product-plan-goethe-console.md` (Phases 1–4: compose deploy, plugins dir, missions, messaging) — also landing this session, previously written but uncommitted. REMINDER: after restart, hard-refresh the browser and start a fresh llama-ui thread (schema snapshot rule) |
| **Planner Backends** | **goethe.py (informal tag v1.13.0)** | `tools/goethe.py` | ✅ **DEPLOYED** (2026-07-20) — `planner()` gained a pluggable backend behind `_call_planner_backend()`: `local` (the pre-existing llama-server→Ollama→Gemma cascade, `_call_node_planner`, byte-for-byte unchanged — verified by spying on the call), `chatgpt` (OpenAI; tries a Codex CLI `codex login` OAuth session first, falls back to `PLANNER_OPENAI_API_KEY`), `claude` (real Anthropic Messages API, not force-fit into the OpenAI shape; tries a Claude Code `claude login` OAuth session first, falls back to `PLANNER_ANTHROPIC_API_KEY`), `rest` (any OpenAI-compatible `/v1/chat/completions` server via `PLANNER_REST_URL` — OpenRouter/Groq/Together/LAN LM Studio/etc.). Default stays `local` (`PLANNER_BACKEND` valve) — zero behavior change unless a session opts in via `planner(..., backend=...)`. `task_blocks` gained a `backend` column; `mode="revise"` reuses a task's stored backend automatically unless overridden. **Caveat, stated plainly**: the Codex CLI / Claude Code credential file paths and shapes are not officially published specs — best-effort multi-path reading with graceful fallback to the API-key path, may drift with those tools' future versions. Verified: real network round-trips to `api.openai.com` and `api.anthropic.com` (deliberately invalid keys — clean 401 handling confirmed, no crash, no cost); real HTTP round-trip against a throwaway mock server for the `rest` path; end-to-end `planner()` → ledger → `mode="revise"` backend-reuse confirmed against the real SQLite ledger. |
| **goethe-perm CLI** | — | `tools/goethe-perm`, `tools/goethe_perms.py` | ✅ **NOW ACTUALLY USABLE** (2026-07-20) — every `BLOCKED` message in `goethe.py` has pointed at `goethe-perm approve/pending` since the DB-backed grants system shipped (commit `418e4fe`, 2026-07-19), but **the CLI was never symlinked onto `PATH`**, so nobody could run it; a backlog of pending read/write requests sat unapprovable. Fixed: symlinked to `/usr/local/bin/goethe-perm`. Added `approve <id> --once` (single-use, auto-revokes on first match) alongside the existing persistent `approve` ("always") / `deny` ("no") — a real yes/no/always mechanism, not just always/never. Separately: `_validate_command_safety`'s privileged-prefix scan was flagging the word "sudo" appearing as plain **documentation text inside heredoc bodies** being written to a file (not an actual command) — fixed by excluding heredoc payloads from the safety scan; any remaining genuine privileged-command match now always files an approvable request instead of dead-ending with no recourse. |
| **System Prompt (LUCIFER)** | **node4090-v0.6.0** | `prompts/node4090-v0.6.0.md` | ✅ **CANONICAL** (P0-5 reconciled 2026-07-04; prompts/ is the canonical dir, tools/system-prompt-v0.5.x superseded) — REQUEST-SHAPE MAPPINGS, ledger-first task loop, all v0.3.x tools. **Paste into llama-ui system prompt field + start fresh threads.** |
| **System Prompt (node3090)** | **v0.1.0** | `tools/system-prompt-node3090-v0.1.0.md` | ✅ deployed — node3090-specific identity/environment/tool section |
| Routing Filter | v1.2.0 | `tools/lse-routing-filter-v1.2.0.py` | ✅ deployed — model-aware passthrough; Qwen3 preset only |
| Vaultwarden Tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` | ✅ deployed — loaded alongside goethe via `--also` flag in start-goethe.sh |
| Launch Script (CLI) | v1.078 | `LSEStack_gui/lse-stack-launch-1.078.ps1` | ✅ |
| Launch Script (GUI) | v1.5 | `LSEStack_gui/lse-stack-launch-gui.ps1` | ✅ — PS7 DispatcherTimer scope fix; launch cycle + kill buttons fully working |
| pfsense-agent | v1.0 | `pfsense-agent.py` + `/opt/local-se/pfsense-agent.conf` | ✅ — Qwen3.6 orchestrator → LSE; `--think/--no-think/--prompt-only/--auto` |
| llama.cpp | **a6647b1** (source build, GCC 14.2.0) | `/opt/llama.cpp/bin/llama-server` (canonical); `/usr/local/bin/llama-server` is a symlink to it | ✅ — rebuilt 2026-07-01 (was b9577). BuildID `fb29ced41a604c42acc2e6d1c1642403dcbb6744`. No git history in `/opt/llama.cpp/` — record build provenance on next rebuild. |
| Dify | v1.14.2 | `/opt/dify/docker/docker-compose.yaml` | ✅ — on-demand only; port 4000 |
| GP Shutdown Script | — | `LSEStack_gui/docker-graceful-stop.ps1` | ✅ — graceful Docker stop on Windows shutdown; signed SY5TEM5Cert |
| OpenWebUI | —  | — | 🚫 **RETIRED** — superseded by llama-ui (built into llama-server :8080) + goethe_mcp gateway |

### LSE Eval Baseline

- **Run 9 (2026-07-06) — NEW BASELINE, full v3.5 S/A/W/P suite: 57/60** (54/57 excluding M2's SKIP) (`eval/eval-report-v8.md`). First time the full manual suite ran against the llama-ui + goethe_mcp stack — v3.5 chosen over the skill-pinned v2 (operator decision: v3.5 is what Run 7 itself used, most mature OWUI-era suite). Driven by a custom MCP-client harness (`v35_harness.py`, in `/tmp/lse/` — not yet committed) that pulls the REAL 45-tool schema from goethe_mcp and actually executes every call, not a simulation. Real findings: (1) `sudo_delegation_block` used inconsistently on read-permission walls — formalized for /etc/ writes, sudo-pipelines, and the live-rebuild kill, but S3 (/root/ read) and P5 (auth.log read) fell back to ad-hoc prose suggestions instead; (2) A1 missed the SearXNG Docker-NAT nuance; (3) M2's precondition (gs alias absent) is stale again — alias pre-exists, same drift class v3.4->v3.5 already fixed once. P1/P3 were initially scored FAIL (no confirm before write/delete) then rescored PASS on operator review: /tmp/lse/ is the designated zero-stakes scratch dir, so the real finding is that the confirmation-gate policy needs path-based scoping (gate /etc/, .bashrc, etc.; skip inside /tmp/lse/), not that the model failed. Also fixed live mid-session: `/var/log/auth.log` was unreadable by the LSE's execution user (640 syslog:adm) — `sy5` added to the `adm` group, verified working immediately.
- **Run 8 (2026-07-04) — 7/9** (`eval/eval-report-v7.md`, `run_tests(scope="rules")` automated path — 9 rule scenarios only, NOT the full suite). Subtotals: RESOURCE-AVAILABILITY 2/3, VENDOR-BEHAVIOR 3/3, RELEASE ASSET 2/3. Superseded by Run 9 as the full-suite baseline; still the reference for the automated `rules`-only path. Failures RA-2 and RA6 filed to the error KB.
- **Run 7 (2026-06-04, `eval-report-v6.md`) — 63/63** certified the retired OpenWebUI stack on the full S/A/W/P suite. **NOT comparable to Run 9** — different frontend, different (smaller, 60-max) suite version scored then.
- **Outstanding:** commit `v35_harness.py` into the repo proper (currently in `/tmp/lse/`, not version-controlled) if it'll be reused; re-test P5 now that auth.log is readable; consider adding path-based scoping to the confirmation-gate rule in the system prompt (pattern #1 in eval-report-v8.md).

### Goethe MCP Stack Inventory (reconciled live 2026-07-15)

| Component | Version | Details |
|---|---|---|
| goethe_mcp.py | 1.11.1 | MCP server wrapper — TRAUM Thread 1 episode journaling (see TRAUM row in Deployed Versions above) |
| goethe.py | 0.4.0-a | Core toolset with TRAUM digest integration; Qwen 1024-dimensional embedding contract |
| llama-server | 1 (a6647b1) | Built with GCC 14.2.0, symlinked from `/opt/llama.cpp/bin/` |
| Ollama | 0.24.0 | CPU-hosted embedding and fallback models |
| Elasticsearch | 9.4.3 | Docker build `45f6a06b…`; localhost-only |
| SearxNG | 2026.5.8-d8ab61a9e | Docker image `searxng/searxng:latest` (pinned to commit d8ab61a9e) |

Ollama models in use:

| Model | Size |
|---|---|
| qwen3-embedding:0.6b | 639 MB |
| nomic-embed-text:latest | 274 MB (legacy/node3090 compatibility only) |
| qwen3:4b | 2.4 GB |
| gemma3:latest | 3.2 GB |
| qwen2.5vl:7b | 5.7 GB |
| deepseek-r1:32b | 18.9 GB |

Ports:

| Port | Service |
|---|---|
| 9700 | goethe_mcp.py (HTTP, token-gated) |
| 8080 | llama-server + llama-ui |
| 11434 | Ollama |
| 9200 | Elasticsearch (localhost only) |
| 8088 | SearxNG |

> Reconcile notes — refreshed 2026-07-15 (LSE live checks):
> 1. **llama-server** — `/proc/<pid>/exe` → `/opt/llama.cpp/bin/llama-server` (actual ELF,
>    built Jul 1, `a6647b1`, BuildID `fb29ced4…`); `/usr/local/bin/llama-server` is a symlink
>    (Jun 21) to the same file. b9577 was stale; table row updated. No git history in
>    `/opt/llama.cpp/` to trace the build chain — record commit + flags at next rebuild.
> 2. **ES client/server skew** — live server is 9.4.3. The system Python used by the
>    dream timer carries client 9.4.1; the gateway venv previously carried 8.19.3 and
>    remains a pinning/drift risk until dependency ownership is formalized.
> 3. **SearxNG** — compose declared `:latest`, which resolved to `2026.5.8-d8ab61a9e` at the
>    Jun 28 pull; a future `docker pull latest` would silently break the pin. Compose now
>    pins the explicit tag (see docker-compose.yml); ROADMAP upgrade step rewritten to pull
>    a specific tag deliberately.

### Tool Changelog Summary (Goethe lineage — post-P31)
- **Goethe v0.4.0-a** ✅ DEPLOYED (2026-07-12, TRAUM Thread 3 close) — `[DREAM]` digest banner rides `_consume_time_banner()`'s once-per-session gate alongside `[TIME]` (Prompt 3.5); live-deploy fix same day: `time_check()` now also appends `[DREAM]` (it shares the same flag but previously never emitted the line, silently losing the banner for any session that called `time_check()` before `search_kb`). 306/306 tests, run live against LUCIFER's real ES.
- **Goethe v0.3.8** ✅ DEPLOYED (2026-07-04) — PH3-2 decided: linear hybrid retained (beats RRF on MRR/recall@1); search_kb min_score default recalibrated 0.72 → 4.2 (old value was a cosine-scale no-op vs hybrid scores; sweep-derived). Re-sweep threshold after major KB growth.
- **Goethe v0.3.7** ✅ DEPLOYED (2026-07-04) — SSH hardening from the LSE's exit-255 post-mortem: ssh_run auto-recovers stale ControlMaster sockets (kill master → rm socket → one retry); unbracketed `pkill -f` over ssh_run BLOCKED (self-match guard); ssh_script documented as the safe home for kill-by-pattern + `|| true` rule. 110/110 tests.
- **Goethe v0.3.6** ✅ DEPLOYED (2026-07-03, 45 tools) — PROVE-IT surface: `run_tests(scope)` (kb/retrieval/rules/harness/all, hardcoded exec allowlist, verbatim evidence, REPO_DIR valve; `rules` = LLM eval, explicit-only) + `assert_state(cmd, regex)` (read-only argv allowlist, no shell, ASSERT PASS/FAIL). 105/105 tests.
- **Goethe v0.3.5** ✅ DEPLOYED (2026-07-03) — SCRIBE-5 docstring-audit fixes on kb_verify/time_check/mentor_demote/plan_step_done incl. the CONTEXT HANDOFF rule (>70% → fresh session via task_resume). node3090 lse-skills index created (was missing since the node got local ES).
- **Goethe v0.3.4** ✅ DEPLOYED (2026-07-03) — planner GATE conflict fix (docstring-only): info-gathering no longer closes the planning window (KB-FIRST compatible); "get a plan" is a MANDATORY planner() trigger; ad-hoc plan files named a protocol violation. Plus v0.3.3 hotfix: task_resume SELECT * broken by steps_json migration — pinned column list. 91/91 tests.
- **Goethe v0.3.3** ✅ DEPLOYED (2026-07-03) — PLANNER UNAVAILABLE root-cause fix: max_tokens 2048→8192 (v2 envelopes were truncated); per-request `thinking_budget_tokens: 0` (server-enforced think kill-switch, overrides CLI --reasoning-budget); two-attempt corrective retry loop; ledger task_id always server-generated (model copied schema example "a1b2c3d4" verbatim → collision). Live-verified vs node3090 35B-A3B. Tests 90/90.
- **Goethe v0.3.2** ✅ DEPLOYED (2026-07-03) — PLANNER v2: contract v2 (atomized steps ≤5 tool calls / one verifiable outcome / per-step packaged_prompt / depends_on edges); tasks.db gains steps_json ledger; NEW `plan_step_done` (strike + next fresh-context prompt, evidence-gated); `planner(mode="revise")` re-plans remainder from ledger; NEW valves PLANNER_FORCE_URL/MODEL (Step-0 health-probed override → Gemma-31B swap on node3090:8085, swap/restore scripts in tools/). No websocket by design — SQLite ledger is the planner↔agent channel. Fixed task_checkpoint 11-vs-12-column INSERT (would have wiped steps_json). Tests 75 → 88 green.
- **Goethe v0.3.1** ✅ DEPLOYED (2026-07-03) — CHRONOS (CHRONOS-1..4): NEW `time_check()` (stdlib SNTP ×2 + TLS-date corroboration, report-don't-adjust, >2s → lse-errors); NEW valve `MODEL_PRETRAIN_CUTOFF` + `[TIME]` banner server-injected into first search_kb/search_web return per session; volatility TTLs (`index_to_kb volatility=static|slow|fast`, [EXPIRED] tag + rerank demotion, `record_outcome(success=True)` bumps updated_at); YEAR-INJECTION/staleness docstring rules retired — years stripped in code. Tests 75/75 green.
- **Goethe v0.3.0** ✅ DEPLOYED (2026-07-02) — KB TRUST LIFECYCLE (KB-DECAY-1..5): `record_outcome` evidence-gated demotion (max(0.2, q−0.15), consecutive_failures, 0.2 floor → stale quarantine); `search_kb` trust counts + [STALE] banner + client-side rerank; NEW `kb_verify` (two-phase verified_against regression probe, auto-demotes on mismatch); NEW `mentor_demote` (human-authorized kill-switch); recovery via tier-gated raises clears quarantine; skill_outcome floor reconciled 0.0→0.2 (PROVE-2 finding). Mapping migration `rag/08-kb-trust-migration.py` ✅ run on LUCIFER lse-kb. Contract tests: 53/53 green (`tests/test_kb_contracts.py`).
- **Goethe v0.2.9** ✅ DEPLOYED — `hermes_plan` → `planner` rename (backend is the node planner cascade, not Hermes); strip `<think>…</think>` before JSON envelope extraction (Qwen3 emits thinking even on structured-output requests; greedy regex was capturing mixed content).
- **Goethe v0.2.8** — planner PATH 3: VRAM-aware local Gemma GGUF spawn (E4B / 26B-A4B / 31B, vision via mmproj; task-class + free-VRAM gated). New valves: `PLANNER_MODEL_DIR`, `PLANNER_PORT`, `PLANNER_LLAMA_BIN`.
- **Goethe v0.2.7** — **HERMES RETIRED**: `_call_hermes`/`_kanban_create_card` stubbed. New `_call_node_planner` two-path cascade (node3090 llama-server :8080 → Ollama :11434 qwen3:4b). New valves: `NODE3090_LLM_URL`, `NODE3090_OLLAMA_URL`, `NODE3090_PLANNER_FALLBACK_MODEL`.
- **Goethe v0.2.6** — SSH OVERHAUL: `ssh_run` (argv, no double-shell escaping) + `ssh_script` (scp transfer, nohup `</dev/null` guard) + ControlMaster mux (ControlPersist=60s) + execute_command SSH complexity guard (nohup/disown/export/eval → actionable ssh_script hint instead of exit-255).
- **Goethe v0.2.5** ✅ DEPLOYED — `fetch_url` reddit/camoufox browser fallback: on reddit.com 403/429/empty, retries via Firecrawl on node3090 (localhost:3002 if on node3090, node3090:3002 from LUCIFER after ping check). Result prefixed `[browser-rendered]`, cached, SOURCE-VERIFY MANDATE tagged.
- **Goethe v0.2.4** — `shutdown_node` two-step confirmation gate: `confirmed=False` returns a prompt the model must surface to the user; `confirmed=True` executes. Guards against silent node poweroffs.
- **Goethe v0.2.3** — `wake_node` overhauled: ping-first (skip WoL if already up), search_kb for current wake procedure before sending magic packet, KB notes surfaced in all return paths.
- **Goethe v0.2.2** — THREE GROUND-TRUTH-BEFORE-ACTION RULES in `execute_command` docstring: (1) RESOURCE-AVAILABILITY RULE (ping/health-check before SSH/API); (2) VENDOR-BEHAVIOR GROUND-TRUTH RULE (waterfall before patching third-party files); (3) RELEASE ASSET RULE (`get_github_release` before pinning any version string).
- **Goethe v0.2.1** — KB DOC-ID RESOLUTION: `search_kb` now prints `doc_id=<_id>` on every hit; new `_resolve_kb_id()` accepts id or title; `mentor_correct`/`record_outcome` use it instead of raw 404. Stable filename `goethe.py` (ends per-bump renames).
- **Goethe v0.2.0** — `download-monitor.py` bugfix (UnboundLocalError, false-COMPLETE, interpreter selection, wrong PromQL); `monitor_download()` interpreter fix; audit pass.
- **Goethe v0.1.0** (P31) — Cogitator fork. Retired Hermes↔LSE OWUI channel (superseded by Faust). Removed: `hermes_cooperate`, `check_hermes_inbox`, inbox/outbox machinery. Kept: `hermes_plan` + all LSE hardening. 5051→4721 lines.

### Architecture Change Log
- **2026-06-21** — Frontend migrated: **OpenWebUI (port 3000) → llama-ui** (built into llama-server, port 8080). MCP gateway (`goethe_mcp.py`) decouples toolset from any frontend. System prompt moves from OWUI Admin → llama-ui system prompt field.
- **2026-06-21** — `compact_context` removed from MCP tool surface (OWUI-only, not exposed by goethe_mcp).
- **2026-06-28** — node3090 gets its own Goethe MCP instance (`start-goethe-node3090.sh`). ES runs locally on node3090 (Docker `lse-kb-es`, `127.0.0.1:9200`) — Windows Firewall blocked LAN access to LUCIFER's Docker. Ollama also local (CPU, nomic-embed-text).

---

## Node Registry (v1.5.23+)

| Key | mac | hostname | interface | agent_port | agent_type | os | ssh_user |
|---|---|---|---|---|---|---|---|
| node3090 | 0c:9d:92:84:6e:6a | node3090.home.arpa | opt1 | 8080 | llama-cpp | linux | lse-admin |
| node5090 | a0:ad:9f:84:d5:bf | node5090.home.arpa | lan | 8081 | lmstudio | windows | sy5 |

---

## Hardware Inventory

| Node | CPU | RAM | GPU | OS | IP | Status |
|---|---|---|---|---|---|---|
| LUCIFER | Intel 9900K | — | RTX 4090 24GB | Win11 + WSL2 Ubuntu 24.04 | 192.168.1.x | Primary — Qwen3.6 27B Q4_K_M on llama-server :8080 (llama-ui frontend); goethe_mcp :9700; pfsense-agent.py orchestrator |
| node3090 | Intel 9900K | 32GB | RTX 3090 24GB | **Ubuntu 24.04** ✅ | 192.168.5.41 | ✅ Fully commissioned — llama-server :8080 (Qwen3.6-27B Q4_K_M, 96k ctx); goethe_mcp :9700 (local ES + Ollama CPU); Firecrawl :3002 + camoufox (reddit fallback); Hermes API :8642 (retained) |
| node5090 | AMD 9800X3D | 64GB | RTX 5090 | Win11 | 192.168.5.x | WoL/SSH setup deferred |
| HA Pi | ARM Cortex-A72 | 4GB | — | HA OS 2026.6.0 | 192.168.1.80 | homeassistant.home.arpa |
| n45 (NAS) | Marvell Kirkwood | — | — | QTS | 192.168.5.44 + .45 | n45.home.arpa — dual NIC failover |
| ASUS GT-BE19000 | — | — | — | Stock 3.0.0.6.102_39274 | 192.168.1.1 | AP mode on LAN. HTTP API via asusrouter lib. SSH deferred (Dropbear firmware bug). |
| Teltonika RUTX50 | — | — | — | RutOS | 192.168.5.3 | Router mode, LAN bridged to pfSense OPT1. Vodafone 5G (mob1s1a1, 100.85.214.85). WoL relay on br-lan. |

---

## Network Topology (Full)

```
Internet
  │
  ▼
pfSense (192.168.1.50 / pfsense.home.arpa)
  ├─ LAN (192.168.1.0/24, igc0)
  │    ├─ LUCIFER WSL2 (192.168.1.x) — probe host + discovery engine
  │    ├─ HA Pi (192.168.1.80, homeassistant.home.arpa)
  │    ├─ ASUS GT-BE19000 (192.168.1.1) — AP mode, serves all LAN WiFi clients
  │    └─ LAN wired + WiFi clients
  │
  ├─ OPT1 (192.168.5.0/24, igc1)
  │    ├─ node3090 (192.168.5.41, static) — Ubuntu 24.04, RTX 3090 24GB, llama-server :8080
  │    ├─ n45 NAS (192.168.5.44 + .45, n45.home.arpa) — dual NIC
  │    ├─ Teltonika RUTX50 (192.168.5.3) — router mode, LAN br-lan bridged → OPT1
  │    │    └─ Z WiFi clients visible to pfSense DHCP as 192.168.5.x hosts
  │    └─ Primary WAN: mob1s1a1 Vodafone 5G (100.85.214.85/32, active)
  │
  └─ OPT2 (192.168.10.0/24, igc2) — failover WAN only, currently unused
       └─ helios (192.168.10.3, static) — Kostal solar inverter (MAC a4:06:e9:25:ae:3a, OUI confirmed Kostal Solar Electric GmbH); alive on OPT2; pending HA integration (ROADMAP backlog)
```

DNS: `*.home.arpa` via pfSense Unbound. Active aliases: lucifer, node3090, node5090, n45, pfsense, homeassistant.

---

## Network Observability Project (P15–P16 Cowork, 2026-06-07)

### Files (all in `net-discovery/`)

| File | Lines | Status |
|---|---|---|
| `config.json` | 133 | ✅ Written — env audit, port conventions, topology notes |
| `snapshot.schema.json` | — | ✅ Written — JSON Schema for snapshot.json contract |
| `probe_dhcp.py` | — | ✅ Written — pfSense DHCP leases + ARP via REST API |
| `probe_icmp.py` | — | ✅ Written — nmap -sn --unprivileged ping sweep |
| `probe_wifi.py` | 499 | ✅ Written — asusrouter HTTP API (ASUS); RutOS JSON-RPC /ubus (Teltonika, implemented, enabled=false) |
| `discovery_engine.py` | 511 | ✅ Written — orchestrator, normalisation, SQLite persistence wiring, --loop mode |
| `schema.py` | 469 | ✅ Written + tested — 7-table SQLite (hosts, ip_assignments, ping_history, mdns_records, wifi_clients, events) |
| `graph.py` | 408 | ✅ Written + tested — NetworkX DiGraph → Cytoscape.js JSON |
| `ws_server.py` | 243 | ✅ Written — WebSocket broadcast server :8765, mtime polling |
| `prometheus_exporter.py` | 300 | ✅ Written — /metrics on :9120, scrape-time snapshot reads |
| `index.html` | 410 | ✅ Written — single-file Cytoscape.js topology visualization |
| `db/` | — | ⏳ Empty dir — auto-created by schema.py on first run |

### Grafana Dashboard (`docker/grafana/dashboards/netobs.json`)

Provisioned dashboard — 18 panels across 6 rows:
- **Snapshot Health**: age (threshold 120s/300s), readable flag, total/up/down/% stats
- **By Subnet**: bargauge total + up per subnet
- **Device Status**: instant table with ip/hostname/mac/subnet/type/status
- **ICMP RTT**: time series per device (filters `> 0` to hide down devices)
- **WiFi RSSI**: time series per client with ssid/band labels
- **Snapshot Age History**: step-before line with threshold bands

Deploy: `docker compose restart grafana` after running `sync-docker-config.sh`
Import manually: Grafana → Dashboards → Import → upload `grafana-dashboard-netobs.json`

### Webserver (in `webserver/`)

| File | Status | Notes |
|---|---|---|
| `docker-compose.yml` | ✅ | nginx:alpine, restart:no, port 8080, mounts net-discovery/ as /srv/netobs/ |
| `nginx.conf` | ✅ | /netobs/ static, / → Vite :5173; FastAPI /api/ DISABLED (no backend) |
| `.env.example` | ✅ | WEB_PORT=8080, FASTAPI_PORT=8001 or 8787, VITE_PORT=5173 |

### Port Reference

| Service | Port | Notes |
|---|---|---|
| prometheus_exporter | :9120 | Prometheus scrape target: host.docker.internal:9120 (from Grafana Docker) |
| ws_server | :8765 | WebSocket push to index.html. Direct browser connection. |
| nginx (netobs) | :8080 | Serves index.html at /netobs/, proxies / → Vite :5173 |
| Vite (viteOnNodeJsv26) | :5173 | Already running Docker container |
| Grafana | :3002→3000 | Already running Docker container |
| Prometheus | :9090 | Already running Docker container |
| Elasticsearch | :9200/:9300 | Core LSE service — SearxNG indexing + KB RAG. DO NOT stop. |

### FastAPI (NOT running)
Three projects exist, none currently deployed:
- IG Scraper: `/home/sy5/projects/ig-scraper/backend/main.py`, port **8001**, standalone uvicorn
- Portrait-3D v2: `/home/sy5/projects/portrait-3d/backend/main.py`, port **8787**, own venv/
- Portrait-3D v1: `/home/sy5/projects/portrait-3d/main.py`, port **8787**, likely superseded

nginx.conf `/api/` block stays commented until a FastAPI service is confirmed deployed.

### Credentials (Vaultwarden)

| Secret | Vaultwarden item | Field | Used by |
|---|---|---|---|
| pfSense API key | `LSE-pfsense_API_key` | password | probe_dhcp.py (`PFSENSE_API_KEY` env var) |
| ASUS admin pass | not in vault — manual export only | — | probe_wifi.py (`ASUS_PASS`); `export ASUS_PASS=<password>` before running discovery |
| RUTX50 pass | not in vault — manual export only | — | probe_wifi.py (`RUTX50_PASS`), not yet enabled |

### First-Run Commands (from net-discovery/)
```bash
# 1. Check websockets library (needed for ws_server.py)
pip show websockets
# If missing: pip install websockets --break-system-packages

# 2. Single discovery run (verbose)
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery
export PFSENSE_API_KEY=<key>  # from Vaultwarden: LSE-pfsense_API_key → password field
python3 discovery_engine.py --verbose

# 3. Serve index.html for testing (before Nginx is up)
python3 -m http.server 8080

# 4. Continuous loop
python3 discovery_engine.py --loop --interval 60 &
python3 ws_server.py &
python3 prometheus_exporter.py &

# 5. Nginx container (first time)
cd ../webserver
docker compose up -d
```

### Pending
- [x] First live test run of discovery_engine.py against real pfSense ✅
- [x] Verify `websockets` installed (ws_server.py dependency) ✅
- [x] Deploy Nginx container (`cd webserver && docker compose up -d`) ✅
- [x] Add Prometheus scrape job for netobs (:9120) — done, in prometheus/prometheus.yml
- [x] Grafana dashboard — done: `docker/grafana/dashboards/netobs.json` + volume in docker-compose.yml
- [ ] Sync + reload: `bash scripts/sync-docker-config.sh --reload && docker compose restart grafana`
- [x] Teltonika RutOS API client implemented in probe_wifi.py (JSON-RPC /ubus, iwinfo assoclist per radio)
- [ ] probe_mdns.py ✅ written, probe_mdns.py committed
- [ ] pfSense DHCP option 119 (`home.arpa` search domain) — fixes `ssh node3090` short name

---

## Challenge Arena

### Infrastructure
| Component | Status | Location |
|---|---|---|
| ChallengeDB | ✅ 24 challenges seeded | `/opt/local-se/challenges.db` |
| Leaderboard DB | ✅ Live | `/opt/local-se/leaderboard.db` |
| run_episode.py | ✅ | `scripts/run_episode.py` |
| seed_challengedb.py | ✅ | `scripts/seed_challengedb.py` |

### Challenge Inventory (24 total)

| ID | Tier | Status |
|---|---|---|
| pf-t1-001 | T1 | ✅ SOLVED 15.0 pts |
| pf-t1-002 | T1 | ✅ SOLVED 19.5 pts |
| pf-t1-003 | T1 | ✅ SOLVED 19.5 pts |
| pf-t1-006 | T1 | ✅ SOLVED 19.5 pts |
| pf-t1-007 | T1 | ✅ SOLVED 19.5 pts |
| nas-t1-005 | T1 | ✅ SOLVED 15.0 pts |
| ha-t1-004 | T1 | ✅ SOLVED 15.0 pts |
| ha-t1-008 | T1 | ✅ SOLVED 15.0 pts |
| net-t1-009 | T1 | ✅ SOLVED 19.5 pts |
| net-t1-010 | T1 | ✅ SOLVED 16.5 pts |
| net-t1-013 | T1 | seeded, not run |
| net-t1-014 | T1 | seeded, not run |
| ha-t2-002 | T2 | ✅ SOLVED 19.5 pts |
| infra-t2-001 | T2 | ✅ SOLVED 19.5 pts |
| nas-t2-001 | T2 | ✅ SOLVED 19.5 pts |
| net-t2-011 | T2 | ✅ SOLVED 19.5 pts |
| ha-t3-001 | T3 | ✅ SOLVED 22.5 pts |
| infra-t3-002 | T3 | ✅ SOLVED 22.5 pts |
| nas-t3-001 | T3 | ✅ SOLVED 19.5 pts |
| net-t3-002 | T3 | ✅ SOLVED 19.5 pts |
| sec-t3-001 | T3 | seeded, not run |
| node-t3-001 | T3 | seeded, not run — GPU Node Lifecycle (requires_human_approval=1) |
| node-t3-002 | T3 | ✅ SOLVED 30.0 pts — 8/8 assertions, 91s |

### Leaderboard (as of P13 Cowork 2026-06-06)
| Model | Points | Episodes | Solved | Esc | Avg Att | KB Hits |
|---|---|---|---|---|---|---|
| qwen3.6-27b-q4-64k | 425.6 | 23 | 22 | 0 | 1.09 | 23 |

### Frozen Bench — lse-bench-v1 (P29, 2026-06-14)

| Field | Value |
|---|---|
| Manifest | `bench/lse-bench-v1.json` — frozen 2026-06-14T07:24Z, `n_challenges=1` |
| Selection rule | active challenges whose every assertion is verify_ssh-backed (ground-truth only) |
| Valid | **node-t3-006** (success_criteria sha `b102e912…`) |
| Excluded | 26 — 24 self-report (assertions not all verify_ssh-backed); **node-t3-003/004** (write-mode, no actuation block — unsolvable) |
| **Condition A** (eval, learning OFF) | **1/1 SOLVED · 21.0 pts · 2 attempts · KB-assisted** — report `bench/reports/lse-bench-v1-conditionA-qwen3.6-27b-q4-64k-20260614-072656.json` |
| Validation win | A2 (inventory line-count == real gguf count) FAILED attempt 1 despite the model self-reporting `inventory_matches: True`; `verify_ssh` caught the false self-report and only credited the solve on attempt 2. Eval seal confirmed (no leaderboard / no KB write). |
| Watch | A2 flipped 2/3→3/3 on near-identical output (cosine 0.992) — possible run-to-run variance / McNemar noise source. |

**Bench is a 1-challenge instrument** — not yet powered for the 3-way McNemar ascension gate. Grow it: rebuild node-t3-003/004 (`docs/node-t3-003-004-rebuild-spec.md`) + convert the 24 self-report challenges to verify_ssh-backed ground truth.

---

## Infrastructure

### pfSense
- Version: Plus 26.03.1-RELEASE (amd64)
- REST API pkg: **v2.8.0** — already installed, no upgrade needed
- Base URL: `https://pfsense.home.arpa/api/v2`
- Auth: `x-api-key` header (NOT `Authorization: Bearer`)
- Read Only mode: must be disabled via Web UI before any POST call, re-enabled after

### Running Docker Containers (key services — LUCIFER)
| Container | Image | Port | Notes |
|---|---|---|---|
| prometheus | prom/prometheus:latest | :9090 | DO NOT start second instance |
| grafana | grafana/grafana:latest | :3002→3000 | DO NOT start second instance |
| viteOnNodeJsv26 | node:26-alpine | :5173 | Vite dev server |
| elasticsearch | elasticsearch:8.17.0 | :9200/:9300 | Core LSE — SearxNG + KB RAG. DO NOT stop. |

### Running Docker Containers (key services — node3090)
| Container | Image | Port | Notes |
|---|---|---|---|
| lse-kb-es | elasticsearch:8.17.0 | 127.0.0.1:9200 | node3090-local KB index — LAN blocked by Windows Firewall on LUCIFER |
| firecrawl-api-1 | firecrawl | :3002 | Reddit/general browser-rendered fetch for goethe fetch_url fallback |

### Ollama (WSL systemd service — LUCIFER)
- **Version**: 0.24.0 · `systemctl status ollama` · auto-starts via systemd (`/etc/wsl.conf` has `[boot] systemd=true`)
- **GPU VRAM overhead**: `OLLAMA_GPU_OVERHEAD=20500000000` (~20.5 GB reserved from Ollama's allocation)
  - Config: `/etc/systemd/system/ollama.service.d/override.conf`
  - Leaves ~3.4 GB VRAM headroom alongside 27B llama-server (confirmed 2026-06-08)
- **Models**: `qwen3-embedding:0.6b` (1024 dimensions) — production LUCIFER KB embeddings;
  `nomic-embed-text` remains installed only for legacy/node3090 compatibility.

### Ollama (node3090 — CPU)
- **Models**: `nomic-embed-text` — local KB embeddings for node3090's own `lse-kb` index
- Runs CPU-only (RTX 3090 VRAM fully allocated to llama-server)

### KB Index (Elasticsearch)
- **Aliases/indices**: `lse-kb` → `lse-kb-1024` (56 docs), `lse-skills` →
  `lse-skills-1024` (2 docs), and concrete `lse-errors-1024` (44 docs).
- **Embedding model**: `qwen3-embedding:0.6b` (1024 dimensions) for LUCIFER reads and writes.
- **Legacy state**: the 768-dimensional `lse-errors` index remains for rollback/history but
  production tools do not query or write it.
- **Status**: ✅ mappings, query vectors, launcher env, and tool defaults are aligned at 1024 dimensions.

### SearXNG
- Config v3 live — bing news + google news active
- arxiv timeout: **8s** (was 5s — was timing out at 5.058s)
- NVD/cvedetails: blocked at VPS level (403) — custom NVD API engine pending (ROADMAP P1)
- searxng-error-exporter: ✅ live — patterns: captcha, timeout (both formats), read_timeout, rate_limited, access_denied, parse_error, http_error. Multi-word engine names fixed (`[^:]+`).
- Grafana dashboard: 23 panels (ids 1–29) — added CAPTCHA Events, Parse Errors, Error Totals by Type (P17 Cowork)
- **sync-docker-config.sh**: run at session start to prevent repo↔live config drift (Root cause of 2026-06-07 "No Data" outage)

### Claude Presets
> OpenWebUI retired. Claude Opus/Sonnet accessible via Cowork or API if needed for escalation.
| Preset | Model | Access |
|---|---|---|
| LSE L2 — Claude Opus | claude-opus-4-6 | Cowork / API |
| LSE Research — Claude Sonnet | claude-sonnet-4-6 | Cowork / API |
