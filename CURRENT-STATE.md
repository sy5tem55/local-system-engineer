# LSE Current State
> Last updated: 2026-06-13 (P27 Cowork)
> Source of truth for deployed versions. Update this file at the end of every session.

---

## Deployed Versions

| Component | Version | File | Status |
|---|---|---|---|
| OpenWebUI Tool | **Cogitator v1.7.13** | `tools/cogitator-v1.7.13.py` | READY FOR DEPLOY (P27) — SSH KB-FIRST RULE: search_kb before any ssh command, no topic_filter, never bare ssh without key. black-norm `866b0b4d…`, 4508 lines. Previous deployed: v1.7.12 ✅ |
| System Prompt | v0.5.15 | `prompts/v0.5.15.md` | ✅ deployed — PFSENSE LOG RULE section |
| Routing Filter | **v1.2.0** | `tools/lse-routing-filter-v1.2.0.py` | ✅ deployed — model-aware passthrough; Qwen3 preset only |
| Context Monitor | v1.3.0 | `tools/lse-context-monitor-v1.3.0.py` | 🚫 retired (2026-05-29) — wrong metric prefix; replaced by Grafana alert pipeline (now also removed) |
| Vaultwarden Tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` | ✅ deployed — env var wins over valve |
| Launch Script (CLI) | v1.078 | `LSEStack_gui/lse-stack-launch-1.078.ps1` | ✅ |
| Launch Script (GUI) | **v1.5** | `LSEStack_gui/lse-stack-launch-gui.ps1` | ✅ — PS7 DispatcherTimer scope fix; launch cycle + kill buttons fully working |
| pfsense-agent | **v1.0** | `pfsense-agent.py` + `/opt/local-se/pfsense-agent.conf` | ✅ — Qwen3.6 orchestrator → LSE; `--think/--no-think/--prompt-only/--auto`; tool_ids pass-through |
| llama.cpp | **b9577** | `/usr/local/bin/llama-server` (WSL) | ✅ — upgraded from b9553 (2026-06-09) |
| Dify | **v1.14.2** | `/opt/dify/docker/docker-compose.yaml` | ✅ — on-demand only; port 4000; `docker compose up -d` to start (2026-06-09) |
| GP Shutdown Script | — | `LSEStack_gui/docker-graceful-stop.ps1` | ✅ — graceful Docker stop on Windows shutdown; Dify conditional; signed SY5TEM5Cert (2026-06-09) |

### Tool Changelog Summary (recent — Cogitator)
- **Cogitator v1.7.13** — SSH KB-FIRST RULE in execute_command docstring: search_kb('{hostname} SSH access') with NO topic_filter before any ssh; never bare ssh without -i key; never apply another device's topic_filter. Closes rutx50 live-test incidents (bare SSH timeout + wrong topic_filter=pfsense).
- **Cogitator v1.7.12** — SSH DEVICE AUTO-FINGERPRINT: execute_command intercepts `ssh ` prefix, runs os-release+uname on first connection, prepends [DEVICE FINGERPRINT] banner. Failed fingerprints NOT cached. Restored from OWUI backup + cache fix.
- **Cogitator v1.7.11** — KB source_tier quality gate on index_to_kb/skill_record/skill_outcome.
- **Cogitator v1.7.10** — verify_source_claims(): re-fetches source, FOUND/PARTIAL/NOT_FOUND per claim.
- **Cogitator v1.7.9** — hermes_plan kanban card INSERT.
- **v1.6.1** — pfSense three-tool arch: pfsense_graphql/pfsense_query/pfsense_log_summary; schema introspection prohibition. (See VERSION.md for full history.)

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
| LUCIFER | Intel 9900K | — | RTX 4090 24GB | Win11 + WSL2 Ubuntu 24.04 | 192.168.1.x | Primary — Qwen3.6 27B Q4_K_M on port 8080; pfsense-agent.py orchestrator |
| node3090 | Intel 9900K | 32GB | RTX 3090 24GB | **Ubuntu 24.04** ✅ | 192.168.5.41 | ✅ Fully commissioned — llama-server :8080 (llama-cpp, Qwen3.6-27B Q4_K_M, 96k ctx); pfsense-agent orchestrator target |
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

---

## Infrastructure

### pfSense
- Version: Plus 26.03.1-RELEASE (amd64)
- REST API pkg: **v2.8.0** — already installed, no upgrade needed
- Base URL: `https://pfsense.home.arpa/api/v2`
- Auth: `x-api-key` header (NOT `Authorization: Bearer`)
- Read Only mode: must be disabled via Web UI before any POST call, re-enabled after

### Running Docker Containers (key services)
| Container | Image | Port | Notes |
|---|---|---|---|
| prometheus | prom/prometheus:latest | :9090 | DO NOT start second instance |
| grafana | grafana/grafana:latest | :3002→3000 | DO NOT start second instance |
| viteOnNodeJsv26 | node:26-alpine | :5173 | Vite dev server |
| elasticsearch | elasticsearch:8.17.0 | :9200/:9300 | Core LSE — SearxNG + KB RAG. DO NOT stop. |

### Ollama (WSL systemd service)
- **Version**: 0.24.0 · `systemctl status ollama` · auto-starts via systemd (`/etc/wsl.conf` has `[boot] systemd=true`)
- **GPU VRAM overhead**: `OLLAMA_GPU_OVERHEAD=20500000000` (~20.5 GB reserved from Ollama's allocation)
  - Config: `/etc/systemd/system/ollama.service.d/override.conf`
  - Leaves ~3.4 GB VRAM headroom alongside 27B llama-server (confirmed 2026-06-08)
- **Models**: `nomic-embed-text` (768-dim, 137M params, 8192-ctx) — KB embeddings + OpenWebUI RAG
  - VRAM footprint: ~417 MiB at inference time

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

### Claude Presets in OpenWebUI
| Preset | Model |
|---|---|
| LSE L2 — Claude Opus | claude-opus-4-6 |
| LSE Research — Claude Sonnet | claude-sonnet-4-6 |
