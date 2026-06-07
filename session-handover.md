# Session Handover — LSE
> Updated: 2026-06-07 (P16 Cowork)
> **Read order at session start:** CURRENT-STATE.md → this file → ROADMAP.md

---

## Session Start Checklist

```bash
# Run from WSL on LUCIFER before anything else
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
git log --oneline -5          # confirm on main, see last commits
cat CURRENT-STATE.md          # deployed versions + pending items

# Sync repo config → live Docker host (prevents Grafana "No Data" drift — Rule 26)
bash scripts/sync-docker-config.sh --reload
```

**Last deployed tool: v1.5.27** — date-sensitive query rule.
**DHCP backend: Kea** (migrated from ISC DHCP, 2026-06-07 P18). 32 static mappings intact. API key rotated post-migration.
**Net-discovery probe_dhcp.py: ready.** Static mapping endpoint confirmed: `/services/dhcp_server/static_mapping?parent_id=<id>&id=<n>`.

**Grafana admin password:** rotated 2026-06-07. Stored in Vaultwarden as `Grafana_ADMIN_PASSWORD`. New password has no special characters — safe for shell scripts.
**Prometheus:** was `restart: unless-stopped`, now `restart: always` — will auto-recover after any stop event.
**Topology API:** `python3 net-discovery/echarts_topology.py` (port 8766) — must be running for Grafana net-topology dashboard. Not daemonized; start from WSL with nohup.
**pfSense LAN IP: 192.168.1.50** (NOT .1). ASUS GT-BE19000 management IP: 192.168.1.1.

---

## Critical Rules

1. **Edit tool truncates large Python files on NTFS.** Use bash `cat << 'PYEOF'` heredoc for ALL `.py` files > 100 lines and all JSON files. Never use the Write or Edit tool for these.
2. **Git commits from Cowork sandbox fail** — commit from WSL terminal only.
3. **NAS is `n45.home.arpa`** — IPs 192.168.5.44 + .45 (dual NIC failover). DNS returns both A records.
4. **SearXNG config requires sudo** — `/home/sy5/docker/searxng_data/` is root-owned. Workflow: validate YAML → `sudo cp` → `docker compose restart` → `sleep 8` → verify with category-specific query (not "test").
5. **pfSense auth: `x-api-key` header** — NOT `Authorization: Bearer`. Wrong header → 401.
6. **pfSense base URL: `https://pfsense.home.arpa/api/v2`** — NOT bare IP. CA cert CN matches hostname only.
7. **pfSense SSH is out of scope for LSE** — SSH to pfSense = root shell, bypasses all API boundaries. Human-only.
8. **pfSense Read Only toggle is Web UI only** — `System → REST API → Read Only`. Must disable before any POST, re-enable immediately after.
9. **`docker compose restart` shows `0/1`** — display quirk, not an error. Check `docker logs searxng --tail 20`.
10. **HAOS `sshd_config` regenerates on reboot** — `AllowUsers`/`PermitRootLogin` don't survive. Use `ssh sy5@homeassistant.home.arpa sudo <cmd>`.
11. **HA long-lived tokens are ~183-char JWTs** — `eyJ` prefix. 55-char = truncated. Use Copy button in HA UI.
12. **WoL for node3090 goes via pfSense OPT1:**
    - API: `POST /api/v2/services/wake_on_lan/send` with `{"interface": "opt1", "mac": "0c:9d:92:84:6e:6a"}`
    - ⚠️ `/send` suffix is REQUIRED — bare endpoint returns 404
    - pfSense sends on UDP port 40000 (not 7 or 9). Boot time: ~55s.
13. **node3090 llama.cpp server is on port 8080** — port 1234 = LM Studio (different app).
14. **node3090 SSH always use FQDN** — `ssh lse-admin@node3090.home.arpa`. Short name fails (DHCP option 119 not configured yet).
15. **node3090 models path** — `/opt/models` is a symlink → `/home/sy5/.lmstudio/models/`.
16. **`index_to_kb` is capped at 4000 chars** — call at most once per task. Do NOT call `search_kb()` after to verify.
17. **Only one tool file in OpenWebUI at a time** — duplicate tool functions = OpenWebUI warning.
18. **Elasticsearch is a CORE LSE service** — powers SearxNG result indexing AND KB RAG pipeline. `DO NOT stop or remove`. Container: `elasticsearch:8.17.0`, ports :9200/:9300.
19. **PRE-INSTALL RULE (net-discovery):** Before any `pip install`, ALWAYS run `pip show <package>` first. Many packages are already installed in the owui venv (`/home/sy5/owui/bin/python3`). Avoid Docker duplicates.
19b. **net-discovery Vaultwarden secrets:** pfSense API key → item `LSE-pfsense_API_key`, password field → `PFSENSE_API_KEY` env var. ASUS + RUTX50 passwords NOT in Vaultwarden — manual export only.
20. **`.pyc` files on NTFS mount cannot be deleted from the Cowork sandbox** (Operation not permitted). When testing Python edits in sandbox, use `importlib.util.spec_from_file_location()` to force load from source and bypass cached bytecode.
21. **ws_server.py requires `websockets` library** — wsproto (installed) is a codec only, not a server. Check: `pip show websockets`. Install if missing: `pip install websockets --break-system-packages`.
22. **net-discovery `db/` directory** — auto-created by `schema.py __init__`. No manual `mkdir` needed. Do NOT `mkdir` from `~` (wrong location).
23. **Teltonika RUTX50 topology confirmed:**
    - IP: `192.168.5.3` (managed from pfSense OPT1, DHCP lease)
    - LAN is `br-lan` bridge, bridged to pfSense OPT1 — Z WiFi clients visible on 192.168.5.0/24
    - WAN: mob1s1a1 Vodafone 5G (100.85.214.85, active) — eth1 OPT2 (192.168.10.3) physically disconnected
    - WoL relay available on `br-lan` for OPT1 hosts
    - `probe_wifi.py` Teltonika: RutOS JSON-RPC /ubus implemented. `enabled: false` until first live test.
      Prerequisite (fw≥07.18): install 'JSON-RPC support' via Package Manager on RUTX50.
      Enable: set `wifi_routers[teltonika_rutx50].enabled=true` + export `RUTX50_PASS`.
24. **ASUS GT-BE19000:** AP mode (192.168.1.1). `asusrouter` Python library used (wraps HTTP CGI API, used by Home Assistant core). SSH disabled due to confirmed Dropbear firmware bug on stock firmware.
25. **FastAPI port is NOT 8000** — Three projects: IG Scraper=:8001, Portrait-3D v2=:8787 (own venv), Portrait-3D v1=:8787 (superseded). nginx.conf `/api/` block stays commented until a specific FastAPI is deployed.
26. **Repo config ≠ live host config — always sync after editing.** The repo (`C:\Users\SY5\Claude\Projects\local-system-engineer\`) is on NTFS. The live Docker stack runs from `/home/sy5/docker/` in WSL2. They are two separate file trees. Editing `prometheus/prometheus.yml` or `docker/grafana/...` in the repo does NOT update the running containers. After any config change, run from WSL2: `bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/sync-docker-config.sh --reload`. For searxng_data/settings.yml (root-owned), see Rule 4. **Forgetting this sync is what caused the Grafana "No Data" outage (2026-06-07).**

---

## Active Work (2026-06-07, P15–P16)

### Network Observability — Written, Awaiting First Live Test

All core net-discovery files are written and unit-tested in isolation. The system has never been run against live pfSense. First run will exercise the full pipeline: pfSense API → probes → snapshot.json → index.html visualization.

**What works (tested):**
- `schema.py` — all CRUD methods, event detection, duplicate-free `get_current_devices()` ✅
- `graph.py` — type classification, edge inference, Cytoscape.js serialisation ✅
- `discovery_engine.py` — `_normalise_snapshot()` tested with synthetic data: type classification, icmp.alive, sources, dhcp.expires all correct ✅

**Not yet tested against live infrastructure:**
- pfSense REST API calls (probe_dhcp.py) — needs `PFSENSE_API_KEY` env var
- nmap sweep (probe_icmp.py) — needs nmap + appropriate privileges
- asusrouter WiFi probe (probe_wifi.py) — needs `ASUS_PASS` env var
- ws_server.py — needs `websockets` library installed
- Nginx container — first-time deploy, never started

**Run order for first test:**
```bash
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery

# 1. Set env vars
export PFSENSE_API_KEY=<key>

# 2. Single verbose run
python3 discovery_engine.py --verbose

# 3. If snapshot.json is written, open index.html in browser
# (or python3 -m http.server 8080 → http://localhost:8080/netobs/)

# 4. If that works, check websockets and start ws_server
pip show websockets || pip install websockets --break-system-packages
python3 ws_server.py &

# 5. Continuous loop with persistence
python3 discovery_engine.py --loop --interval 60 &
python3 prometheus_exporter.py &
```

---

## Pending Items

| Item | Priority | Blocked on |
|---|---|---|
| First live test of discovery_engine.py | **HIGH** | PFSENSE_API_KEY env var |
| Verify `websockets` installed for ws_server.py | HIGH | — |
| Deploy Nginx container (`cd webserver && docker compose up -d`) | HIGH | First test passing |
| Sync Prometheus + Grafana config to live host | MEDIUM | `bash scripts/sync-docker-config.sh --reload && docker compose restart grafana` |
| Enable Teltonika probe (probe_wifi.py) | LOW | Install JSON-RPC pkg on RUTX50 + set RUTX50_PASS env var |
| probe_mdns.py (L2 enrichment) | LOW | zeroconf already installed |
| pfSense DHCP option 119 — add `home.arpa` search domain | MEDIUM | — (fixes `ssh node3090` short name) |
| Run node-t3-001 GPU Node Lifecycle challenge | MEDIUM | pfSense Read Only toggle (human gate) |
| Run net-t1-013, net-t1-014 challenges | MEDIUM | — |
| Run sec-t3-001 challenge | MEDIUM | — |
| Deploy v1.5.27 (date-sensitive query rule) | MEDIUM | — |
| searxng-error-exporter (P1 ROADMAP) | LOW | — |
| P0 ROADMAP: ground-truth assertion verifier (verify_ssh) | LOW | design doc in ROADMAP.md |
| node3090: add RTX 2080Ti | LOW | watercooling loop prep (human) |
| node5090: WoL + SSH setup | LOW | deferred |
| ASUS GT-BE19000 SSH (asusrouter HTTP API works) | LOW | Dropbear firmware bug on stock |

27. **pfSense data is KB-first.** Before any live API call for pfSense config (leases, mappings, interfaces), run `search_kb("pfsense dhcp")` first. The KB may already have the answer. Saves many wasted API probes.
28. **pfSense interface display names ≠ REST API IDs (CONFIRMED 2026-06-07):**
    ```
    Display name  REST API id  Subnet
    LAN           lan          192.168.1.0/24
    OPT1          opt4         192.168.5.0/24  pf label: Studio_API_id_opt4_igc2
    OPT2          opt2         192.168.10.0/24 pf label: Solar_Inverter_OPT2_API_id_opt2_igc3
    WLAN          opt3         (no subnet in config.json yet)
    IoT VLAN 55   opt6         192.168.55.0/24 (inactive)
    ```
    `?parent_id=opt1` returns 404. Must use `opt4`. DHCP static mapping endpoint: `GET /services/dhcp_server/static_mapping?parent_id=<id>&id=<n>` -- iterate n from 1 until 404. ARP: `GET /diagnostics/arp_table` (confirmed working).
29. **3 devices are static ARP entries, NOT DHCP clients** -- exclude from Kea migration:
    - `192.168.1.1`  GT-BE19000  (router gateway, not a DHCP client)
    - `192.168.5.2`  netgear GS308E  (dumb switch, static ARP)
    - `192.168.10.2` ksem Kostal meter  (static ARP)

---

## Network Topology

```
Physical NIC  pfSense label  API id  Notes
igc0          WAN            wan     upstream internet
igc1          LAN            lan     192.168.1.0/24
igc2          Studio         opt4    192.168.5.0/24  pf desc: Studio_API_id_opt4_igc2
igc3          Solar_Inv      opt2    192.168.10.0/24 pf desc: Solar_Inverter_OPT2_API_id_opt2_igc3
igc1.55       IoT VLAN 55    opt6    192.168.55.0/24 (inactive scaffold)
              WLAN           opt3    (no dedicated subnet in config.json yet)

Internet
  │
  ▼
pfSense (192.168.1.50 / pfsense.home.arpa)   REST API: https://pfsense.home.arpa/api/v2
  ├─ LAN (192.168.1.0/24, igc1, API: lan)
  │    ├─ LUCIFER WSL2 (192.168.1.x) — probe host + Cowork + OpenWebUI
  │    ├─ HA Pi (192.168.1.80, homeassistant.home.arpa)
  │    ├─ ASUS GT-BE19000 (192.168.1.1) — AP mode, asusrouter HTTP API
  │    │    └─ LAN WiFi clients (2.4/5/6 GHz)
  │    └─ LAN wired clients
  │
  ├─ Studio / OPT1 (192.168.5.0/24, igc2, API: opt4)
  │    ├─ node3090 (192.168.5.41 static) — Ubuntu 24.04, RTX 3090, llama-server :8080
  │    ├─ n45 NAS (192.168.5.44 + .45, n45.home.arpa)
  │    ├─ Teltonika RUTX50 (192.168.5.3, DHCP from pfSense)
  │    │    ├─ br-lan bridges Z WiFi clients → OPT1 (visible to pfSense DHCP)
  │    │    ├─ WAN: mob1s1a1 Vodafone 5G (100.85.214.85, active)
  │    │    └─ WoL relay available on br-lan for OPT1 hosts
  │    └─ Z WiFi clients (192.168.5.x, discoverable via pfSense DHCP + nmap)
  │
  └─ Solar_Inverter / OPT2 (192.168.10.0/24, igc3, API: opt2) — failover WAN only
       └─ Teltonika eth1 (192.168.10.3, static) — cable DISCONNECTED, no active clients

IoT VLAN 55 (192.168.55.0/24, igc1.55, API: opt6) — scaffold in config.json, inactive
```

DNS: `*.home.arpa` via pfSense Unbound. All nodes reachable by hostname within the LAN.

---

## Session History

| Session | Key outcome |
|---|---|
| P16 (2026-06-07) | Net-discovery integration complete: discovery_engine.py rewrite with --loop mode, normalisation, SQLite wiring. schema.py, graph.py, ws_server.py, prometheus_exporter.py all written + tested. nginx.conf FastAPI blocks commented (no backend). FastAPI audit: 3 projects (ports 8001/8787), none running. |
| P15 (2026-06-07) | Net-discovery project started. Compared LSE v3 vs P14 code — P14 wins. config.json, probe_dhcp.py, probe_icmp.py, probe_wifi.py (asusrouter), discovery_engine.py, index.html (Cytoscape.js) written. Teltonika topology confirmed (router mode, OPT1 bridge). Nginx Alpine webserver created. Docker audit: Prometheus/Grafana are containers not PIDs; FastAPI not running; Elasticsearch is core LSE. |
| P14 (2026-06-07) | node3090 fully commissioned. CUDA 13.3, llama.cpp built, Qwen3.6-27B running 96k ctx 19.3GB. v1.5.24 deployed (start/stop_node_agent). Reddit via site: operator confirmed working. |
| P13 (2026-06-06) | node-t3-002 janitor challenge added (24 total). Post-upgrade CUDA+llama.cpp design. |
| P12 (2026-06-06) | node-t3-001 challenge added (23 total). node3090 Ubuntu upgrade started. |
| P11 (2026-06-06) | v1.5.22 WoL fix. v1.5.23 registry fix. WoL tested end-to-end (55s boot). |
| P10 (2026-06-06) | WoL root cause found. pfSense API KB seeded (264 paths). net-t1-013/014 seeded. |
| P8 (2026-06-04) | 6 challenges solved. Leaderboard 373.1 pts / 21 eps. SSH hardening done. |
| P6 (2026-06-03) | DNS aliases live. NODE2 renamed node3090. pfSense auth/URL corrected everywhere. |
| P5 (2026-06-02) | 63/63 eval. 4 