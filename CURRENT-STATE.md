# LSE Current State
> Auto-reconcile at session start: read file headers, update this table.
> Last updated: 2026-06-03

## Deployed Versions

| Component | Version | File | Notes |
|---|---|---|---|
| Tool | v1.5.16 | `tools/openwebui-tool-v1.5.16.py` | PFSENSE_CA_CERT valve + _pfsense_verify() · deployed ✅ |
| Tool (prev) | v1.5.15 | `tools/openwebui-tool-v1.5.15.py` | pfsense_query() + PFSENSE_URL/KEY valves · deployed ✅ |
| Prompt | v0.5.12 | `prompts/v0.5.12.md` | deployed ✅ |
| RAG Tools | v2 | (embedded in tool) | search_kb, index_to_kb, record_error, check_error_kb |
| Vaultwarden tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` | env var wins over valve · deploy pending |
| Routing filter | v1.1.0 | `tools/lse-routing-filter-v1.1.0.py` | |
| Context monitor | retired | — | removed in v0.5.4; replaced by Grafana alert pipeline |
| Launch script (CLI) | v1.078 | `LSEStack_gui\lse-stack-launch-1.078.ps1` | LaunchDir → /tmp/lse/launch (tmpfs, RAM-backed, ~10× faster than vhdx) · secrets pre-flight check |
| Launch script (GUI) | v1.4 | `LSEStack_gui\lse-stack-launch-gui.ps1` | Profiles from lse-profiles.xml · LaunchDir → /tmp/lse/launch · secrets in webui.sh · tested ✅ |
| Eval framework | Run 6 last complete | `eval/eval-report-v5.md` | 58/63 |
| Test suite | v3.5 | `eval/test-suite-v2.md` (header) | 21 tests |

## Tool Checksums (SHA-256)

Verify on-disk files match deployed versions. Generate with:
`sha256sum tools/openwebui-tool-v1.5.1*.py`

| File | SHA-256 |
|---|---|
| `openwebui-tool-v1.5.16.py` | `bcc04bb0fa3d944c9fa5a4e4786393950b2efc32f0ad69962716a217f88a66d1` |
| `openwebui-tool-v1.5.15.py` | `b9d00a17ad44eda7c4630368a7a19fde9d282e7871536ae306482e619a9c9dd0` |

---

## Hardware Inventory

| Node | CPU | RAM | GPU | OS | Role |
|---|---|---|---|---|---|
| LUCIFER | Intel 9900K | ? | RTX 4090 24GB | Win11 + WSL2 Ubuntu 24.04 | Primary LSE stack |
| NODE2 | Intel 9900K | 32GB | RTX 3090 24GB | Ubuntu (native) | LM Studio installed · parallel LSE candidate |
| NODE3 | AMD 9800X3D | 64GB | RTX 5090 | Win11 (no WSL) | Gaming PC — do not touch |
| HA Pi | ARM Cortex-A72 | 4GB (est) | — | HA OS (rpi4-64) | Home Assistant hub |
| Pi 4 (spare) | ARM Cortex-A72 | 4GB (est) | — | undeployed | Future ARM64 Docker node |
| TS-419P II | Marvell Kirkwood ARMv5 | — | — | QTS | NFS/SMB archive only |

## Hardware / Stack — LUCIFER (192.168.1.57)

### Docker Services

| Service | Ext Port | Int Port | Notes |
|---|---|---|---|
| SearXNG | 8088 | 8080 | lse-net; config: `/home/sy5/docker/searxng_data/settings.yml` |
| Elasticsearch | 9200, 9300 | 9200, 9300 | lse-net, mem_limit=2g |
| Prometheus | 9090 | 9090 | lse-net |
| Node Exporter | 9100 | 9100 | lse-net |
| Grafana | 3002 | 3000 | lse-net |
| Portainer | 9000, 9443 | 9000, 9443 | Docker management UI |
| Vaultwarden | 3003 | 80 | lse-net |
| Vite.js | 5173 | 5173 | IG scraper frontend container |
| Valkey (Redis) | internal only | 6379 | lse-net — connected via env var but settings.yml missing `redis:` section |

### Native WSL2 Processes

| Process | Bind | Port | Notes |
|---|---|---|---|
| llama-server (Qwen3.6-27B-Q4_K_M) | 0.0.0.0 | 8080 | RTX 4090, sm_89, CUDA 13.3 |
| OpenWebUI | 0.0.0.0 | 3000 | venv ~/owui |
| OpenWebUI worker | 127.0.0.1 | 3001 | |
| Open-Terminal | 0.0.0.0 | 5000 | |
| grafana-owui-adapter | 0.0.0.0 | 9837 | systemd exporter |
| llama-context-exporter | 0.0.0.0 | 9836 | systemd exporter |
| llamacpp-slots-exporter | 0.0.0.0 | 9838 | systemd exporter |
| download-speed-exporter (probable) | 0.0.0.0 | 9839 | Grafana network speed data — `/opt/local-se/download-speed-exporter.py` |
| anon Python exporter | 0.0.0.0 | 9835 | identify — likely Prometheus/Grafana data carrier |
| automation-mcp-gateway (Docker) | — | 8000 | Exited code 0, 2026-05-21 · port FREE · automation-filesystem-service also exited |
| Ollama (nomic-embed-text) | 127.0.0.1 | 11434 | CPU-only, RAG embeddings |
| systemd-resolved | 127.0.0.53 | 53 | |
| WSL DNS | 10.255.255.254/127.0.0.54 | 53 | |

**⚠️ Port 8080:** llama-server binds on WSL2 host; SearXNG internal Docker port is also 8080 but only exposed as 8088 externally via Docker NAT. No collision.

## Known Gaps (as of last reconcile)

## Network Infrastructure (2026-06-03)

| Node | IP | Status | Notes |
|---|---|---|---|
| pfSense Plus 26.03.1 | 192.168.1.50 | ✅ SSH confirmed | syslog → LUCIFER live |
| LUCIFER (WSL2) | 192.168.1.57 | ✅ | Static DHCP mapping |
| HA Pi 4 | 192.168.1.x | ❓ | Token not yet created |
| TS-419P II NAS | 192.168.5.x | ❓ | Credentials not yet verified |
| Solar inverter | 192.168.10.3 | ✅ | igc3, already in HA |
| Samsung S90C TV | 192.168.1.90 | ⚠️ | DHCP hammer, WAN block needed |

**Subnets confirmed:** 192.168.1.0/24 (LAN), 192.168.5.0/24 (NAS), 192.168.10.0/24 (solar/IoT via igc3)

**Syslog pipeline:** pfSense → UDP 514 → LUCIFER WSL2 ✅ live  
**pfSense SSH:** `ssh admin@192.168.1.50` ✅ confirmed  
**pfSense API:** ❌ not available in Plus 26.03.1 — using SSH + config.xml instead  
**WSL2 mirrored networking:** ✅ confirmed (`networkingMode=mirrored` in .wslconfig)

## SearXNG Engine Configuration

| State | Detail |
|---|---|
| Live production engines | **27 engines configured** ✅ · 11 active on technical queries · 108 results confirmed |
| Brave status | ✅ Demoted to weight 1 · suspended 180s during testing (VPS sensitivity confirmed) |
| Config deployed | ✅ 2026-06-03 · limiter disabled · valkey key corrected · redis section present |
| Config location | `/home/sy5/docker/searxng_data/settings.yml` (host) = `/etc/searxng/settings.yml` (container) |
| Config backups | `settings.yml.backup`, `settings.yml.backup-v1.0-20260525`, `settings.yml.bak` |
| Valkey/Redis state | env var wired ✅ · `settings.yml` has `redis:` section ✅ (line 161) · limiter disabled ✅ (line 113) |
| Grafana observability | Live — shows `searxng_engines_*` metrics, but only reflects current 4-engine production config |
| searxng-logger | Still polling Prometheus with wrong logic — rewrite pending (backlog) |

## Open Issues Found via Syslog
- Samsung TV (192.168.1.90) hammering DHCP every 1–2 min + needs WAN block
- `filterdns: cisco.lan` stale DNS entry — delete from DNS Resolver host overrides
- Syslog collector container not yet built (using nc for testing only)
- `v1.5.10.py` renamed to `v1.5.11.py` by git at commit c5e3d84 (96% similarity — duplicate resolved)

## Eval Score Trajectory

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored baseline |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (budget 3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think (budget 0) | 49/57 |
| Run 5 (partial) | v1.5.6 | v0.5.2 | thinking (budget 3072) | 15/21 subset |
| Run 6 | v1.5.13 | v0.5.11 | thinking (budget 3072) | **58/63** |
