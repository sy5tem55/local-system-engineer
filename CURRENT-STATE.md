# LSE Current State
> Auto-reconcile at session start: read file headers, update this table.
> Last updated: 2026-06-05 (P3 Cowork — Grafana tuning dashboard)

## Deployed Versions

| Component | Version | File | Notes |
|---|---|---|---|
| Tool | v1.5.18 | `tools/openwebui-tool-v1.5.18.py` | search_rfc() · deployed ✅ |
| Tool (prev) | v1.5.17 | `tools/openwebui-tool-v1.5.17.py` | pfsense_log_summary() + nmap_summary() |
| Prompt | v0.5.14 | `prompts/v0.5.14.md` | Docker NAT topology fix · deployed ✅ |
| Prompt (prev) | v0.5.13 | `prompts/v0.5.13.md` | 4 Run-6 fixes · deployed ✅ |
| RAG Tools | v2 | (embedded in tool) | search_kb, index_to_kb, record_error, check_error_kb |
| Vaultwarden tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` | env var wins over valve · deployed ✅ |
| Routing filter | v1.1.0 | `tools/lse-routing-filter-v1.1.0.py` | deployed ✅ · Global OFF · Qwen3 preset only |
| Launch script (CLI) | v1.078 | `LSEStack_gui/lse-stack-launch-1.078.ps1` | tmpfs launch dir · secrets pre-flight |
| Launch script (GUI) | v1.4 | `LSEStack_gui/lse-stack-launch-gui.ps1` | profiles from lse-profiles.xml |

## Tool Checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `openwebui-tool-v1.5.18.py` | `017443197a3d53fcf66a910fb8daa54248c98993411e297295d18e73dcb8a34a` |
| `openwebui-tool-v1.5.17.py` | `f30c1e97493aa6f58fe3498df94c15784d747a5e1e04a209a405251e5211c973` |
| `openwebui-tool-v1.5.16.py` | `bcc04bb0fa3d944c9fa5a4e4786393950b2efc32f0ad69962716a217f88a66d1` |
| `openwebui-tool-v1.5.15.py` | `b9d00a17ad44eda7c4630368a7a19fde9d282e7871536ae306482e619a9c9dd0` |

---

## LSE Challenge Arena Components

| Component | Status | Notes |
|---|---|---|
| ChallengeDB | ✅ Seeded | `/opt/local-se/challenges.db` — 10 T1 · **needs --reset** for new schema columns |
| Leaderboard DB | ✅ Live | `/opt/local-se/leaderboard.db` — 6 episodes recorded |
| LSEChallengeEnv | ✅ Done (2026-06-04) | `scripts/lse_challenge_env.py` · 7/7 smoke tests |
| EscalationWrapper | ✅ Done (2026-06-04) | `scripts/escalation_wrapper.py` · 9/9 smoke tests |
| LeaderboardService | ✅ Done (2026-06-04) | `scripts/leaderboard.py` · 9/9 smoke tests |
| run_episode.py | ✅ Done (2026-06-04) | Full stack wired · MAX_TOKENS=8192 · auto-leaderboard |
| ChallengeGenerator | ✅ Done (2026-06-04) | `scripts/challenge_generator.py` · wired into run_episode.py |
| rfc_kb.py | ✅ Done (2026-06-04) | 20 RFC registry · 1490 chunks · `--tag-only` running PID 188339 |

## Arena Leaderboard (2026-06-04)

| Model | Points | Episodes | Solved | Esc | Avg Att | KB Hits |
|---|---|---|---|---|---|---|
| qwen3.6-27b-q4-64k | 373.1 | 21 | 20 | 0 | 1.10 | 21 |

## T1 Challenge Run Status

| Challenge | Status | Points | Notes |
|---|---|---|---|
| pf-t1-001 LAN Device Map | ✅ SOLVED a1 | 15.0 | KB hit 13.188 |
| pf-t1-002 NAS Subnet Map | ✅ SOLVED a1 | 19.5 | **5 unexpected ports on 192.168.5.10** |
| pf-t1-003 Firewall Log Baseline | ✅ SOLVED a1 | 19.5 | KB hit 18.514 (from failed episode web search) |
| pf-t1-006 Firewall Rule Map | ✅ SOLVED a1 | 19.5 | KB hit 27.396 |
| pf-t1-007 DNS Resolver Audit | ✅ SOLVED a1 | 19.5 | host_overrides: 0 (clean state confirmed) |
| net-t1-009 Open Port Audit | ✅ SOLVED a1 | 19.5 | **NAS 192.168.5.10 unexpected ports confirmed** |
| net-t1-010 Traffic Baseline | ✅ SOLVED a1 | 16.5 | KB hit 26.227 · 3 top talkers |
| nas-t1-005 NAS Service Inventory | ✅ SOLVED a1 | 15.0 | KB hit 16.219 · 3 NFS + 4 SMB · 450.2 GB free |
| ha-t1-004 HA Inventory | ✅ SOLVED a1 | 15.0 | HA 2026.6.0 · 192.168.1.80 |
| ha-t1-008 HA Automation Audit | ✅ SOLVED a1 | 15.0 | **2 stale automations found** |
| ha-t2-002 HA Template Sensor Audit | ✅ SOLVED a1 | 19.5 | 2 sensors identified · migration YAML produced |
| ha-t3-001 HA Template Sensor Migration | ✅ SOLVED a1 | 22.5 | YAML fixed · error confirmed gone post-reboot |
| infra-t2-001 SSH Posture Audit HA Pi | ✅ SOLVED a1 | 19.5 | PasswordAuthentication + AllowUsers documented |
| infra-t3-002 SSH Key Hardening LUCIFER→Pi | ✅ SOLVED a1 | 22.5 | Key auth live (sy5) · password auth disabled |

---

## Hardware Inventory

| Node | CPU | RAM | GPU | OS | Role |
|---|---|---|---|---|---|
| LUCIFER | Intel 9900K | ? | RTX 4090 24GB | Win11 + WSL2 Ubuntu 24.04 | Primary LSE stack · active: Qwen3.6 27B Q4_K_M 64k q8_0 think:3072 → :8080 |
| NODE2 | Intel 9900K | 32GB | RTX 3090 24GB | Ubuntu (native) | LM Studio installed · parallel LSE candidate · **setup pending** |
| NODE3 | AMD 9800X3D | 64GB | RTX 5090 | Win11 (no WSL yet) | Gaming PC — WSL2 setup pending |
| HA Pi | ARM Cortex-A72 | 4GB | — | HA OS | Home Assistant hub |
| Pi 4 (spare) | ARM Cortex-A72 | 4GB | — | undeployed | Future ARM64 Docker node |
| TS-419P II | Marvell Kirkwood | — | — | QTS | NFS/SMB at 192.168.5.x |

## Docker Services (LUCIFER)

| Service | Port | Notes |
|---|---|---|
| SearXNG | 8088 | lse-net · v3 config · NVD + Semantic Scholar + bing/google news live · SSL_CERT_FILE fix applied |
| Elasticsearch | 9200/9300 | lse-net · mem_limit=2g · indexes: lse-kb, lse-rfc-kb |
| Prometheus | 9090 | lse-net |
| Node Exporter | 9100 | lse-net |
| Grafana | 3002 | lse-net · dashboard `searxng-engine-health` — 20 panels · 6 tuning-signal panels added P3 · provisioned (`allowUIUpdates: false`, edit JSON file) |
| Portainer | 9000/9443 | Docker UI |
| Vaultwarden | 3003 | lse-net |
| Valkey (Redis) | internal 6379 | lse-net |

## Native WSL2 Processes (LUCIFER)

| Process | Port | Notes |
|---|---|---|
| llama-server (Qwen3.6-27B-Q4_K_M) | 8080 | RTX 4090 · 64k · KV:q8_0 · think:3072 |
| OpenWebUI | 3000 | venv ~/owui |
| Ollama | 11434 | nomic-embed-text (CPU) + llama3.2:3b (CPU) |
| grafana-owui-adapter | 9837 | systemd |
| llama-context-exporter | 9836 | systemd |
| llamacpp-slots-exporter | 9838 | systemd |
| download-speed-exporter | 9839 | systemd |

## Network Infrastructure

| Node | IP | Status |
|---|---|---|
| pfSense Plus 26.03.1 | 192.168.1.50 | ✅ SSH + REST API |
| LUCIFER (WSL2) | 192.168.1.57 | ✅ Static DHCP |
| HA Pi 4 | homeassistant.home.arpa:8123 · 192.168.1.80 | ✅ Token live · SSH key auth (sy5) · template YAML fixed |
| TS-419P II NAS | 192.168.5.45 (nas.home.arpa) | ⚠️ Unexpected ports found |
| Samsung S90C TV | 192.168.1.90 | ⚠️ DHCP hammer + WAN unblocked |
| Solar inverter | 192.168.10.3 | ✅ In HA |

**Subnets:** 192.168.1.0/24 (LAN) · 192.168.5.0/24 (NAS) · 192.168.10.0/24 (IoT)
**pfSense REST API:** v2.8 · read-only · access list: 192.168.1.57/32 · CA cert: `/opt/local-se/cert/pfsense-webgui-ca.crt`

## Open Issues

| Issue | Status |
|---|---|
| NAS 192.168.5.45 (nas.home.arpa) unexpected ports | ✅ nas-t2-001 + nas-t3-001 SOLVED |
| Samsung TV DHCP hammer + WAN unblocked | ✅ WAN blocked (net-t2/t3 SOLVED) · DHCP rate still high — T4 open |
| HA long-lived access token | ✅ Live · JWT format · 183 chars · Vaultwarden: HomeAssistant_API_Token |
| HA template sensor misconfiguration | ✅ Fixed (2026-06-05) · migrated to `template:` key · confirmed post-reboot |
| NODE2/NODE3 setup | ❌ Pending |
| ChallengeDB schema migration (needs --reset) | ⚠️ Do before next episode run |
| RFC tag-only job | ⏳ Running PID 188339 (~1-2h) |
| Syslog collector container | 🎯 Arena T2 challenge |

## Eval Score Trajectory

| Run | Tool | Prompt | Mode | Score |
|---|---|---|---|---|
| Run 1 | v1.4.0 | v0.1-baseline | thinking | unscored |
| Run 2 | v1.5.1 | v0.4.1 | thinking | 45/57 |
| Run 3 | v1.5.4 | v0.5.1 | thinking (3072) | **57/57** |
| Run 4 | v1.5.5 | v0.5.2 | no-think | 49/57 |
| Run 5 (partial) | v1.5.6 | v0.5.2 | thinking | 15/21 |
| Run 6 | v1.5.13 | v0.5.11 | thinking (3072) | **58/63** |
| Run 7 | v1.5.18 | v0.5.14 | thinking (3072) | **63/63** ✅ · all gaps closed |
| Run 8 | pending | v0.5.14 | — | after SearXNG v3 + Claude L2 setup |
