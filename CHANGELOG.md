# LSE Changelog
> Append-only. One entry per session. Never edit past entries.
> Format: `## YYYY-MM-DD — <what shipped>`

---

## 2026-06-03 — Tool v1.5.16, pfSense SSL, session close

**Tool v1.5.16** — deployed ✅ (SHA-256: bcc04bb0fa3d944c9fa5a4e4786393950b2efc32f0ad69962716a217f88a66d1)
- `PFSENSE_CA_CERT` valve + `_pfsense_verify()` helper
- Uses `/opt/local-se/cert/pfsense-webgui-ca.crt` (sy5:sy5 644, valid → Apr 2036)
- Falls back to `verify=False` with logged warning if cert missing
- pfSense TLS now fully verified against WebGUI CA
- git: `7275f45`

**Repo hygiene pending:** `openwebui-tool-v1.5.14-BKP.py` committed accidentally — needs `git rm` + `.gitignore` rule for `*.BKP`

## 2026-06-03 — Tool v1.5.15, security hardening, launcher v1.078 + GUI v1.4

**Tool v1.5.15** — deployed ✅ (SHA-256: b9d00a17ad44eda7c4630368a7a19fde9d282e7871536ae306482e619a9c9dd0)
- `pfsense_query(endpoint, method, payload, api_key)` — pfSense REST API v2 client
- `PFSENSE_URL` + `PFSENSE_API_KEY` valves added
- `LOG_FILE` default moved to `/opt/local-se/agent_commands.log` (away from root-owned `~/.lse/`)
- SSL `verify=False` with rationale (LAN-only, self-signed cert); v1.5.16 will add `PFSENSE_CA_CERT` valve

**Tool v1.5.14** — deployed ✅ (SHA-256: 1cf298f74364426c4d25a06fb64cf43f7519c80a91b7d58a0799b3b4986b0e17)
- `sudo_delegation_block` gains `step_number`, `total_steps`, `verify_command` params
- THINKING PHASE RULE: never call inside `<think>` block

**Security hardening — `.lse` directory and secrets**
- `/home/sy5/.lse/` → root:sy5 710 (traversable by sy5 group, not listable)
- `/home/sy5/.lse/secrets` → root:sy5 640 (sy5 group readable, BW_PASSWORD via env var)
- `BW_PASSWORD` removed from OpenWebUI valve (plaintext SQLite) → sourced from `~/.lse/secrets`
- Vaultwarden tool v1.3.0: env var priority over valve, placeholder default in UI
- VALVES.md created — full valve registry with security posture for all tools

**Launcher v1.078 (CLI) + GUI v1.4**
- `$LaunchDir` moved from `/home/sy5/.lse/launch` to `/tmp/lse/launch` (tmpfs, RAM-backed, ~10× faster)
- Secrets pre-flight check + `webui.sh` sources `~/.lse/secrets` before OpenWebUI starts
- GUI v1.4: profiles from `lse-profiles.xml` (fixed broken line-offset parsing from v1.076)

**pfSense REST API**
- pfrest.org package installed (v2.8, Plus 26.03) — one SSH command
- Read-only, LAN+WAN+OPT1+OPT2 interfaces, access list: 192.168.1.57/32
- Write access protocol documented in arena doc and ROADMAP

**Checksums introduced** — SHA-256 for last two tool versions tracked in CURRENT-STATE.md

## 2026-06-03 — Prompt v0.5.12 + Tool v1.5.14, Challenge Arena design consolidated

**Prompt v0.5.12 + Tool v1.5.14** — deployed to OpenWebUI ✅
- Fix 1: STEP MILESTONE HEADERS — `── Step N/Total: [description] ──` required before each step on 4+-step tasks
- Fix 2: THINKING PHASE RULE added to sudo_delegation_block — must not fire inside `<think>` block
- Fix 3: sudo_delegation_block gains `step_number`, `total_steps`, `verify_command` params; block format updated

**LSE Challenge Arena** — design document written (`docs/lse-challenge-arena.md`)
- Reconstructed from lost session conversations
- Covers: point structure, discipline weights, escalation protocol (convergence detection), KB isolation (shared pool / public goods game), architecture sketch, 50-challenge ladder across pfSense and HA domains, challenge schema (SQLite), build order
- HA sandbox: HA Core Docker confirmed as approach (~1hr deploy, frictionless config porting)
- pfSense sandbox: log replay (syslog corpus already flowing to LUCIFER)
- VRAM concurrency strategy for 3-model parallel episodes: open, decision pending

## 2026-06-03 — SearXNG 27-engine deploy, syslog live, network topology

**SearXNG 27-engine config deployed** ✅
- Config already written to `/home/sy5/docker/searxng_data/settings.yml` — container just needed restart
- `valkey:` section added (replacing deprecated `redis:` key) — wires Valkey to limiter + caching
- `limiter: true` re-enabled after testing
- Verified: 27 engines configured, 11 active on `q=llama.cpp&categories=general,it,science`, 108 results
- Brave suspended during testing (VPS rate-limiting confirmed) — weight 1 is correct
- **Bug found:** `search_web` tool sends no `X-Forwarded-For` header → gets 429 from limiter; also missing `categories=general,it,science` → misses arxiv/github/scholar. Fix in tool v1.5.13.

## 2026-06-03 — Network infrastructure bootstrap, syslog live

**pfSense syslog pipeline established**
- pfSense Plus 26.03.1 confirmed at 192.168.1.50 — no built-in REST API (docs verified)
- SSH access confirmed: `ssh admin@pfsense.home.arpa`
- Syslog config was not written to `/etc/syslog.conf` on first GUI save — root cause: syslogd was not restarted
- Fix: re-saved settings in GUI → config regenerated → syslogd restarted with new PID
- pfSense → LUCIFER:514 UDP syslog now live and verified with tcpdump + nc
- WSL2 mirrored networking confirmed working (ping + port binding)

**Network topology expanded — three subnets confirmed**
- 192.168.1.0/24: LAN (pfSense, LUCIFER, HA Pi, Samsung TV)
- 192.168.5.0/24: NAS subnet (TS-419P II via igc2)
- 192.168.10.0/24: Solar/IoT subnet (inverter at 192.168.10.3 via igc3, already in HA)

**Syslog-derived findings (first 10 min of data)**
- Samsung S90C TV (192.168.1.90, MAC 1c:af:4a:04:5f:b6): DHCP hammer every 1–2 min + unblocked WAN access
- `filterdns: cisco.lan` stale DNS host override — superseded by .home.arpa domain migration
- cloudflare.time.com DNS reverse lookup error on Samsung TV DHCP events (benign)

**docs/network-topology.md** created with full node inventory, subnet map, service placement, WSL2 networking options, T1 challenge set (10 challenges), HA Pi add-on capacity table, future Pi 4 NAS plan, pfSense bootstrap section

## 2026-06-02 — Tool v1.5.12 deployed, prompt v0.5.10, tracking restructure `c5e3d84`

**Tool v1.5.12** — deployed to OpenWebUI
- `write_file` SIZE SANITY CHECK: code-level gate rejects overwrites where new content < 25% of existing line count; `force=True` override after explicit user confirmation
- `record_outcome(doc_id, success, notes)`: tracks empirical_runs, success_count, failure_count on KB docs
- `mentor_correct(doc_id, correction, new_quality)`: human correction with re-embed; never lowers quality score

**Prompt v0.5.10** — written (deploy to OpenWebUI pending)
- ENVIRONMENT: v0.5.10, tool v1.5.12
- TOOLS `write_file`: added `force` parameter documentation
- TOOLS `mentor_correct`: corrected signature `authority` → `new_quality`
- TOOLS `record_outcome`: corrected parameter `note` → `notes`
- OUTPUT RULES: added write_file SIZE SANITY CHECK handling rule

**Eval test-suite-v2.md** — P6 added (write_file overwrite size regression); total /57 → /60

## 2026-06-02 — Tracking restructure

- Introduced `CURRENT-STATE.md` (auto-reconcilable version table)
- Introduced `CHANGELOG.md` (this file, append-only)
- Stripped `ROADMAP.md` to open items only
- Fixed tool filename mismatch: `openwebui-tool-v1.5.10.py` renamed to `openwebui-tool-v1.5.11.py`
- Identified gaps: `record_outcome` / `mentor_correct` not yet implemented in tool; `write_file` SIZE SANITY CHECK not yet implemented

---

## 2026-06-01 — Tool v1.5.11 (fetch_url, monitor_download), RAG stack, ES memory floor, SearXNG observability, prompt v0.5.9

**Tool v1.5.11 — two undocumented additions (reconstructed from code)**
- `fetch_url(url, max_chars)` — HTML-stripped full-page fetch; part of SEARCH-THEN-FETCH protocol (Step 3 of search_web sequence). Strips script/style/nav/footer/head tags.
- `monitor_download(file_path, expected_bytes, interface)` — Prometheus-backed download progress monitor. Returns DOWNLOADING / COMPLETE / STALLED with ETA and SLEEP N. Uses `/opt/local-se/download-monitor.py` and Prometheus at localhost:9090.
- Note: v1.5.11 was saved as `openwebui-tool-v1.5.10.py` — filename mismatch (pending rename).
- Note: `record_outcome` and `mentor_correct` referenced in prompt v0.5.9 TOOLS section were NOT implemented in this version — tracked as open items.

## 2026-06-01 — RAG stack, ES memory floor, SearXNG observability, prompt v0.5.9

**RAG Stack (tool v1.5.9 → v1.5.11, prompt v0.5.7 → v0.5.9)**
- Elasticsearch 8.17.0 + Ollama nomic-embed-text (CPU) deployed on lse-net
- Four RAG tool functions added: `search_kb`, `index_to_kb`, `record_error`, `check_error_kb`
- KB-FIRST RULE: `search_kb` called before every `search_web`
- 12 seed KB docs / 32 chunks indexed at quality 0.3–0.6
- Error KB populated from WAN2.1 deployment session
- Mentor-authority entries indexed (Grafana-check-before-process-kill pattern, quality 0.95)
- `compact_context` (v1.5.8): true in-place compaction via OpenWebUI REST API + KV cache erase

**ES Memory Floor**
- ES was exiting code 143 (Docker OOM) — `docker inspect` confirmed Memory=0
- Migrated to `/home/sy5/docker/docker-compose.yml` with `mem_limit: 2g`, `mem_reservation: 1g`
- Merged alongside grafana, prometheus, searxng — orphan warning eliminated
- Named volume `es-data` preserved
- `dcd` alias added to `~/.bashrc`
- `lse:stack-health-check` skill updated with ES recovery

**SearXNG Observability Restoration**
- `/metrics` endpoint was returning 404 — root cause: `open_metrics` password missing
- Fix: added `open_metrics: 'metrics-admin-2025'` + `enable_metrics: true`
- Prometheus scrape job restored with `basic_auth.password`
- Grafana dashboards now receiving live `searxng_engines_*` data

**SearXNG 27-engine config prepared (NOT YET DEPLOYED)**
- Brave **demoted** (lower weight, not removed) — still contributes despite VPS rate-limiting
- 27-engine target: arXiv T1 weight 4, Google Scholar weight 3, Bing+DDG weight 2, Brave+Mojeek+Qwant weight 1, Wikipedia+Bing News always-on
- Config path confirmed: `/home/sy5/docker/searxng_data/settings.yml` (host) = `/etc/searxng/settings.yml` (container)
- Backups: `settings.yml.backup`, `settings.yml.backup-v1.0-20260525`, `settings.yml.bak`
- Valkey (Redis fork) already deployed on lse-net internal port 6379 — caching may already be available
- Production still running 4-engine set; Grafana confirms only Brave/DDG/Google/Wikipedia active

**Prompt v0.5.7–v0.5.9**
- v0.5.7: Grafana URL, KB path, RAG Tools v2, pip torch version guard, WARNING ESCALATION RULE, BACKGROUND PROCESS RULE, SYSTEM PACKAGE INSTALLATION RULE, RAG tool discipline rules
- v0.5.8: (inherits v0.5.7 changes)
- v0.5.9: MULTI-BLOCK TASK RULE — persistent `/opt/local-se/active-task.md` survives context resets; HANDOVER PROTOCOL updated to include active-task.md

---

## 2026-05-31 — WAN2.1 deployment

- Full WAN2.1 deployment on LUCIFER (RTX 4090, WSL2 Ubuntu 24.04)
- All models present and verified; I2V and T2V basic workflows tested
- T2V simplified and I2V upscale+framegen patched and ready
- ComfyUI Manager v4.2.1 active; `wan2-manager.sh` written
- WAN2.2 partially researched: 14B MoE (≥16 GB VRAM) and 5B hybrid (~8 GB) confirmed released

---

## 2026-05-29 — GUI launcher v1.1, Grafana context alert pipeline

**GUI Launcher v1.1**
- Click handler crashed PowerShell host — root cause: `ThreadPool.QueueUserWorkItem` has no runspace
- Fix: synchronous `Write-LaunchScripts` + `Start-WTSession` on UI thread; `DispatcherTimer` for PID poll
- Stale Authenticode signature stripped; errors now display in GUI status line

**Grafana Context Alert Pipeline**
- `lse-context-monitor-v1.3.0` inlet filter retired (used wrong metric prefix `llama_` vs `llamacpp:`)
- `llama-context-exporter` (port 9836, systemd) computes `llama_kv_cache_usage_ratio`
- `grafana-owui-adapter` (port 9837, systemd) converts Grafana JSON → OpenWebUI channel webhook
- Alert: `llama_kv_cache_usage_ratio > 0.8` for 1 min → `lse-alerts` channel
- Docker network `lse-net` consolidating all services
- End-to-end smoke test passed

**Tool v1.5.6 / v1.5.7**
- v1.5.6: POST-DELETE VERIFY RULE, NO YEAR INJECTION in search_web, `get_github_release` function
- v1.5.7: DESTRUCTIVE OPERATION PROTOCOL for `execute_command` (warn → name → ask yes/no → wait)

---

## 2026-05-26 — Grafana metrics integration

- `--metrics` flag added to launcher v1.063
- Prometheus scrape config targeting `localhost:8080/metrics`
- Grafana dashboard built with llama.cpp performance panels

---

## 2026-05-25 — Eval Run 4 (no-think), Eval Run 5 (partial)

- Run 4: tool v1.5.5 / prompt v0.5.2 / no-think (budget 0) → 49/57
  - S 15/15, P 13/15 (P3 no verify, P4 W2 regressions), M 9/9, W 7/9, A 5/9
  - Confirms thinking budget is load-bearing for P and A categories
- Run 5 (partial subset): tool v1.5.6 / prompt v0.5.2 / thinking → 15/21
  - P2 3/3 ✓, W2 3/3 ✓, A3 3/3 ✓ — targeted fixes confirmed
  - P1 0/3, P3 0/3 — execute_command lacked destructive-op gate → fixed in v1.5.7
  - A1 0/3 — questions answerable from inference, context monitor never triggered → prompt rework

---

## 2026-05-24 — Eval Run 3 — 57/57

- Tool v1.5.4 / prompt v0.5.1 / thinking (budget 3072) / test suite v3.2
- All 19 categories 3/3; perfect score
- P2 fixed (READ-FIRST RULE in sudo_delegation_block)
- A1 fixed (get_context_status field name corrected for llama-server build ≥9307)

---

## 2026-05-23 — Routing filter v1.1.0, tool v1.5.1–v1.5.4

- Routing filter v1.1.0 deployed
- v1.5.1: read_file PRIVILEGED PATH note; sudo_delegation_block stop instruction hardened
- v1.5.2: denylist hardening (shred, blkdiscard, rm -rf patterns, /mnt/ write block)
- v1.5.3: sudo_delegation_block STOP PROTOCOL — surface command in visible text
- v1.5.4: get_context_status field-name fix; sudo READ-FIRST RULE

---

## 2026-05-22 — Eval Run 2, prompt v0.4.1

- Run 2: tool v1.5.1 / prompt v0.4.1 / thinking → 45/57 (corrected to 54/57 on partial rerun)
- Baseline established for comparison

---

## Early sessions — Infrastructure, tool v1.4.x–v1.5.0, prompt v0.1–v0.4

- llama.cpp + OpenWebUI + SearxNG + Playwright stack stood up
- Windows Terminal launcher with three model profiles (32k, 64k, no-think)
- Tool v1.4.0: execute_command, read_file, write_file, sudo_delegation_block, search_web, get_context_status
- Tool v1.4.1–v1.4.3: routing rules, sudo pipeline fix, write_file protocol rewrite
- Tool v1.5.0: COMBINE RULE and search_web announcement promoted to docstrings; port 8088 fix
- Prompt v0.1 → v0.4.1: identity, permission boundary, live service rule, context handover
- Eval Run 1: unscored baseline
- Skills: `lse:eval-runner`, `lse:docstring-optimizer`, `lse:stack-health-check`, `lse:session-debrief`, `lse:version-manager`
- Docs: 01–06 written
