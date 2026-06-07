# LSE Current State
> Last updated: 2026-06-07 (P16 Cowork)
> Source of truth for deployed versions. Update this file at the end of every session.

---

## Deployed Versions

| Component | Version | File | Status |
|---|---|---|---|
| OpenWebUI Tool | **v1.5.26** | `tools/openwebui-tool-v1.5.26.py` | ✅ deployed — search_web hang fix (5,10) timeout + year injection rule hardened |
| System Prompt | v0.5.15 | `prompts/v0.5.15.md` | ✅ deployed — PFSENSE LOG RULE section |
| Routing Filter | v1.1.0 | `tools/lse-routing-filter-v1.1.0.py` | ✅ deployed — Global OFF · Qwen3 preset only |
| Context Monitor | v1.3.0 | `tools/lse-context-monitor-v1.3.0.py` | ✅ deployed |
| Vaultwarden Tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` | ✅ deployed — env var wins over valve |
| Launch Script (CLI) | v1.078 | `LSEStack_gui/lse-stack-launch-1.078.ps1` | ✅ |
| Launch Script (GUI) | v1.4 | `LSEStack_gui/lse-stack-launch-gui.ps1` | ✅ |

### Tool Changelog Summary (recent)
- **v1.5.26** — search_web hang fix (5,10) timeout + year injection rule hardened
- **v1.5.25** — `search_reddit(query, subreddit="")` — Reddit via SearxNG site: operator. No OAuth, no API footprint
- **v1.5.24** — `start_node_agent` / `stop_node_agent` — on-demand llama-cpp lifecycle via SSH. `agent_profile` in `_NODE_REGISTRY` (96k ctx, q8_0 KV, Qwen3.6-27B)
- **v1.5.23** — `_NODE_REGISTRY` node3090: `agent_port` 1234→**8080**, `agent_type` lmstudio→**llama-cpp**
- **v1.5.22** — `wake_node`: WoL endpoint `/api/v2/services/wake_on_lan` → `/api/v2/services/wake_on_lan/send`. Fast-fail guard on pfSense error.

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
| LUCIFER | Intel 9900K | — | RTX 4090 24GB | Win11 + WSL2 Ubuntu 24.04 | 192.168.1.x | Primary — Qwen3.6 27B Q4_K_M on port 8080 |
| node3090 | Intel 9900K | 32GB | RTX 3090 24GB | **Ubuntu 24.04** ✅ | 192.168.5.41 | ✅ Fully commissioned — driver 595, CUDA 13.3 toolkit, llama-server built + running (19.3GB VRAM, 96k ctx) |
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
       └─ Teltonika eth1 (192.168.10.3, static) — physically disconnected
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
| `probe_wifi.py` | 291 | ✅ Written — asusrouter HTTP API client; Teltonika stub disabled |
| `discovery_engine.py` | 511 | ✅ Written — orchestrator, normalisation, SQLite persistence wiring, --loop mode |
| `schema.py` | 469 | ✅ Written + tested — 7-table SQLite (hosts, ip_assignments, ping_history, mdns_records, wifi_clients, events) |
| `graph.py` | 408 | ✅ Written + tested — NetworkX DiGraph → Cytoscape.js JSON |
| `ws_server.py` | 243 | ✅ Written — WebSocket broadcast server :8765, mtime polling |
| `prometheus_exporter.py` | 300 | ✅ Written — /metrics on :9120, scrape-time snapshot reads |
| `index.html` | 410 | ✅ Written — single-file Cytoscape.js topology visualization |
| `db/` | — | ⏳ Empty dir — auto-created by schema.py on first run |

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

### First-Run Commands (from net-discovery/)
```bash
# 1. Check websockets library (needed for ws_server.py)
pip show websockets
# If missing: pip install websockets --break-system-packages

# 2. Single discovery run (verbose)
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery
export PFSENSE_API_KEY=<key>  # or ASUS_PASS for wifi probe
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
- [ ] First live test run of discovery_engine.py against real pfSense
- [ ] Verify `websockets` installed (ws_server.py dependency)
- [ ] Deploy Nginx container (`cd webserver && docker compose up -d`)
- [ ] Add Prometheus scrape job for netobs (:9120) in prometheus/prometheus.yml
- [ ] Implement Teltonika RutOS API client in probe_wifi.py stub
- [ ] probe_mdns.py (optional L2 enrichment, zeroconf installed)
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
