# LSE Current State
> Last updated: 2026-07-02 (Cowork)
> Source of truth for deployed versions. Update this file at the end of every session.

---

## Deployed Versions

| Component | Version | File | Status |
|---|---|---|---|
| **LSE Tool (LUCIFER)** | **Goethe v0.2.9** | `tools/goethe.py` | ✅ **DEPLOYED** — `planner()` rename + think-strip JSON fix; 5819 lines |
| **LSE Tool (node3090)** | **Goethe v0.2.9** | `tools/goethe.py` (rsynced via start-goethe-node3090.sh) | ✅ synced — node3090 runs its own local goethe_mcp instance |
| **MCP Gateway** | **goethe_mcp v1.9.3** | `tools/goethe_mcp.py` | ✅ **DEPLOYED** — `_TokenGuard` accepts `Bearer <token>` or raw token; port 9700; started via `bash tools/start-goethe.sh` |
| **System Prompt (LUCIFER)** | **v0.5.19** | `tools/system-prompt-v0.5.19.md` | ✅ ready to deploy — goethe_mcp corrected to v1.9.3 (v0.5.18 had stale v1.9.0/v1.9.1). Zero OWUI references confirmed. **Paste into llama-ui system prompt field.** |
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

### Goethe MCP Stack Inventory (recorded 2026-07-02, operator-verified)

| Component | Version | Details |
|---|---|---|
| goethe_mcp.py | 1.9.3 | MCP server wrapper |
| goethe.py | 0.2.9 | Core toolset (title: "LSE Goethe v0.2.9") |
| llama-server | 1 (a6647b1) | Built with GCC 14.2.0, symlinked from `/opt/llama.cpp/bin/` |
| Ollama | 0.22.1 | CPU-only, 5 models loaded |
| Elasticsearch | 8.13.0 | Docker image `docker.elastic.co/elasticsearch/elasticsearch:8.13.0` |
| SearxNG | 2026.5.8-d8ab61a9e | Docker image `searxng/searxng:latest` (pinned to commit d8ab61a9e) |

Ollama models in use:

| Model | Size |
|---|---|
| nomic-embed-text:latest | 261 MB |
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

> Reconcile notes — RESOLVED 2026-07-02 (LSE live checks):
> 1. **llama-server** — `/proc/<pid>/exe` → `/opt/llama.cpp/bin/llama-server` (actual ELF,
>    built Jul 1, `a6647b1`, BuildID `fb29ced4…`); `/usr/local/bin/llama-server` is a symlink
>    (Jun 21) to the same file. b9577 was stale; table row updated. No git history in
>    `/opt/llama.cpp/` to trace the build chain — record commit + flags at next rebuild.
> 2. **ES client/server skew** — client `elasticsearch==8.19.3` (pip) vs server 8.13.0
>    (Docker): compatible per the elasticsearch-py matrix, no functional issue. NOTE:
>    goethe.py line ~674 mentions `elasticsearch:8.17.0` — that line is the v1.5.9
>    HISTORICAL changelog entry, not current state; do not "fix" the changelog. Live server
>    version is 8.13.0.
> 3. **SearxNG** — compose declared `:latest`, which resolved to `2026.5.8-d8ab61a9e` at the
>    Jun 28 pull; a future `docker pull latest` would silently break the pin. Compose now
>    pins the explicit tag (see docker-compose.yml); ROADMAP upgrade step rewritten to pull
>    a specific tag deliberately.

### Tool Changelog Summary (Goethe lineage — post-P31)
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
- **Models**: `nomic-embed-text` (768-dim, 137M params, 8192-ctx) — KB embeddings
  - VRAM footprint: ~417 MiB at inference time

### Ollama (node3090 — CPU)
- **Models**: `nomic-embed-text` — local KB embeddings for node3090's own `lse-kb` index
- Runs CPU-only (RTX 3090 VRAM fully allocated to llama-server)

### KB Index (Elasticsearch)
- **Index**: `lse-kb` · embedding model: `nomic-embed-text` (768-dim)
- **Documents**: 19 docs indexed with consistent 768-dim vectors (rebuilt 2026-06-08 after WSL cascade failure)
- **Previous state**: was indexed with `all-MiniLM-L6-v2` (384-dim) while querying with `nomic-embed-text` (768-dim) → dimension mismatch → meaningless cosine similarity scores
- **Status**: ✅ fixed — same model for both indexing and querying

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
