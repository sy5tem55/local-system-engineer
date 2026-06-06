# Network Topology
> Last updated: 2026-06-02
> Status: baseline — to be verified against live environment in T1 Challenge 01

---

## Physical Topology

```
                         INTERNET
                             │
                    ┌────────┴────────┐
                    │   pfSense       │
                    │  192.168.1.1    │  ← Firewall / Router / DNS resolver
                    │                 │    Syslog source · REST API · DHCP server
                    └────┬────────────┘
                         │  Routes between subnets
          ┌──────────────┴──────────────────────┐
          │                                     │
   192.168.1.0/24  (LAN)              192.168.5.0/24  (NAS subnet)
          │                                     │
    ┌─────┴──────┐                    ┌──────────┴──────────┐
    │            │                    │   QNAP TS-419P II   │
    │  LUCIFER   │                    │   192.168.5.x       │
    │  192.168.1.x│                   │   ARMv5 Kirkwood    │
    │  Win11     │                    │   QTS — NFS/SMB     │
    │  RTX 4090  │                    │   NO Docker         │
    │            │                    │   Role: persistent  │
    │  WSL2 ─────┼──── virtual NAT    │   log archive,      │
    │  Ubuntu    │    172.x.x.x       │   NFS mount target  │
    │  Docker    │    (see §WSL2)     └─────────────────────┘
    └─────┬──────┘
          │
    ┌─────┴─────────────────────────────────────┐
    │   Raspberry Pi                            │
    │   192.168.1.x                             │
    │   HA OS on external SSD                   │
    │   Home Assistant Core                     │
    │   Add-ons (Supervisor-managed containers) │
    │   Role: automation hub, MQTT broker,      │
    │          metrics persistence candidate    │
    └───────────────────────────────────────────┘
```

---

## Node Inventory (to be verified in T1 Ch.01)

| Node | Subnet | IP | Role | Docker | Notes |
|---|---|---|---|---|---|
| pfSense Plus | 192.168.1.0/24 | 192.168.1.50 | Gateway, firewall, DNS, DHCP | No | 26.03.1 · Netgate appliance · J3710 · SSH access confirmed |
| LUCIFER | 192.168.1.0/24 | 192.168.1.57 | AI workstation (primary) | Yes (WSL2) | 9900K · RTX 4090 · Main LSE stack |
| NODE2 | 192.168.1.0/24 | 192.168.1.x | AI workstation (secondary) | Yes (native) | 9900K · RTX 3090 24GB · Ubuntu · LM Studio · parallel LSE candidate |
| NODE3 | 192.168.1.0/24 | 192.168.1.x | Gaming PC (untouched) | No | 9800X3D · RTX 5090 · 64GB RAM · no WSL — gaming performance constraint |
| HA Pi (Pi 4) | 192.168.1.0/24 | 192.168.1.x | HA OS, automation hub | Add-ons only | rpi4-64, ext SSD, 1.2 GB in use |
| Pi 4 (spare) | undeployed | — | Future NAS + Docker node | Yes (ARM64) | Same RAM as HA Pi — see §Future |
| TS-419P II | 192.168.5.0/24 | 192.168.5.x | Cold storage NAS | ❌ ARMv5 | NFS/SMB archive only — no containers |
| Solar inverter | 192.168.10.0/24 | 192.168.10.3 | Solar power inverter | No | igc3 · already in HA integration |
| Samsung S90C TV | 192.168.1.0/24 | 192.168.1.90 | Display only (dumb mode) | No | MAC 1c:af:4a:04:5f:b6 · DHCP hammer · needs WAN block |

---

## WSL2 Networking Solution

WSL2 runs behind a virtual NAT by default — its IP (172.x.x.x) is not reachable from LAN devices and cannot reach LAN subnets directly. Three options, in order of preference:

### Option A — WSL2 Mirrored Mode (recommended, Windows 11 only)
Mirrors the Windows host NIC into WSL2. WSL2 gets the same LAN IP as the host.
pfSense, HA Pi, and NAS become directly reachable from WSL2 without any NAT.

```ini
# C:\Users\SY5\.wslconfig
[wsl2]
networkingMode=mirrored
```
Requires WSL2 kernel ≥ 5.15.146 and Windows 11 22H2+. After editing, run `wsl --shutdown` then relaunch.

### Option B — Docker macvlan (if mirrored mode unavailable)
Docker container gets a real 192.168.1.x IP via macvlan driver.
Reaches pfSense and HA directly. WSL2 host cannot communicate with macvlan containers (Linux kernel limitation) — use a bridge shim.

### Option C — Windows host as relay (fallback)
pfSense syslog → Windows host IP (192.168.1.x) → port-forwarded to WSL2.
Works without config changes but adds a relay hop.

**Recommended path:** implement Option A first (one line in `.wslconfig`). Fall back to B if mirrored mode causes WSL2 instability.

---

## Service Placement

Design principle: LUCIFER hosts compute-intensive and stateful services. TS-419P II provides only persistent block storage via NFS. HA Pi hosts automation-adjacent services via HA Add-ons. Nothing requiring Docker goes on the NAS.

| Service | Host | Mechanism | Rationale |
|---|---|---|---|
| pfSense syslog collector | LUCIFER (Docker) | UDP 514 listener container | Resources, already Docker stack |
| pfSense log sandbox (replay) | LUCIFER (Docker) | Log replay container | Isolated, reproducible challenges |
| pfSense API sandbox (mock) | LUCIFER (Docker) | FastAPI mock | Safe rule testing before live |
| HA config sandbox | LUCIFER (Docker) | `homeassistant/home-assistant` on alt port | Test before touching production HA |
| Challenge DB | LUCIFER | SQLite / existing ES | Co-located with LSE stack |
| Long-term log archive | TS-419P II (NFS) | rsync from LUCIFER → NFS share | Survives LUCIFER reboots, large storage |
| MQTT broker | HA Pi (Add-on: Mosquitto) | HA Supervisor | Already HA-native, low overhead |
| InfluxDB (metrics retention) | HA Pi (Add-on) | HA Supervisor | Pairs with HA energy dashboard |
| Grafana (network/LSE metrics) | LUCIFER (Docker) | Existing lse-net stack | Already deployed |

**TS-419P II role:** NFS export mounted by LUCIFER Docker containers for:
- Long-term pfSense log archive (rsync nightly)
- HA config backups
- Challenge sandbox state snapshots

---

## Inter-Subnet Routing (pfSense)

pfSense routes between 192.168.1.0/24 and 192.168.5.0/24.
Current rules governing this routing are unknown — T1 Challenge 06 maps them.

Expected firewall policy (to verify):
- LAN → NAS: allowed (file access)
- NAS → LAN: limited (NAS-initiated connections should be minimal)
- LAN → Internet: NAT + firewall rules
- Specific ports to verify: NFS (2049), SMB (445), HA (8123), MQTT (1883/8883)

---

## HA Pi — Add-on Capacity

Pi 4, rpi4-64, 1.2 GB currently in use. Total RAM unconfirmed — T1-Ch.04 will retrieve it via Supervisor API.
At 1.2 GB in use, even a 2 GB model has 800 MB headroom; a 4 GB model has 2.8 GB free.
Comfortable for 3–4 add-ons. Do not add Studio Code Server or Grafana — Grafana is on LUCIFER.

| Add-on | RAM estimate | Priority | Notes |
|---|---|---|---|
| Mosquitto (MQTT) | ~50 MB | Core | Install now if not present |
| MariaDB | ~300 MB | High | Replace SQLite for HA recorder |
| InfluxDB 2.x | ~400 MB | High | Long-term metrics retention |
| Node-RED | ~200 MB | Medium | Automation logic, T3 challenge |
| SSH & Web Terminal | ~30 MB | Utility | Admin access |
| Grafana | — | Skip | Already on LUCIFER |
| Studio Code Server | ~500 MB | Skip | Too heavy, use File Editor instead |

Estimated post-add-on usage on 4 GB model: ~2.2 GB (comfortable headroom).
Verify actual RAM in T1-Ch.04 before adding InfluxDB or Node-RED.

---

## Future Architecture — Pi 4 NAS Node

The spare Pi 4 (same RAM as HA Pi) deployed with external NVMe storage becomes a
**Docker-capable ARM64 node** — fundamentally different from the TS-419P II (ARMv5, no Docker).

**Recommended stack when deployed:**
- OS: Raspberry Pi OS Lite 64-bit (not HA OS — full Debian base needed)
- NVMe: via USB 3.0 enclosure or PCIe hat (Argon ONE M.2, Pimoroni NVMe Base)
- Services: Docker CE, OpenMediaVault 7 (NFS/SMB), persistent challenge infrastructure

**What this unlocks:**
- Persistent services that survive LUCIFER shutdown (syslog collector, challenge DB replica)
- ARM64 Docker — can run any container in the architecture
- NVMe-backed NFS mounts (replaces TS-419P II as primary NAS)
- Offloads always-on services from LUCIFER (saves idle power on a 4090 workstation)

**Challenge ladder placement:** T4-Ch.36–40 — Pi NAS deployment and service migration.
**Prerequisite:** NVMe enclosure hardware acquired before challenges run.

---

## Tier 1 Challenge Set — Topology Exploration (Challenges 01–10)

All read-only. No system mutation. Safe to run directly against production.
Each challenge has a machine-checkable assertion and a KB index target.

---

### T1-Ch.01 — LAN Device Map

**Goal:** Enumerate all active devices on 192.168.1.0/24 with hostname, MAC, vendor.

**Discipline:** System administration (1.0×)

**Method:** pfSense DHCP lease table (`GET /api/v2/dhcp/server/lease`) + ARP scan from LUCIFER WSL2.

**Starting state:** Live pfSense REST API (read-only, v2.8). No snapshot required — read-only production queries.

**Assertions (machine-checkable):**
```python
assert "192.168.1.50" in [d["ip"] for d in devices]           # pfSense found
assert "192.168.1.57" in [d["ip"] for d in devices]           # LUCIFER found
assert len([d for d in devices if d.get("mac")]) >= 5         # ≥5 devices with MAC resolved
```

**Failure modes:**
- 0/3: Model fails to query pfSense DHCP API or ARP table; returns no device list.
- 1/3: DHCP lease table retrieved, pfSense + LUCIFER found; no ARP scan run, MAC vendor not resolved; third assertion fails.
- 2/3: pfSense and LUCIFER confirmed, MACs listed, but fewer than 5 entries (ARP scan incomplete or nmap not run).
- 3/3: Full inventory — all known devices, hostnames, MACs, vendors; all 3 assertions pass.

**KB target:** `network-topology/lan-device-inventory` (quality 0.9 — live data)

**Sandbox:** Not applicable (read-only). Direct production run safe.

**Escalation candidate:** If pfSense API not reachable from WSL2, this is the first test of mirrored networking.

---

### T1-Ch.02 — NAS Subnet Map

**Goal:** Enumerate 192.168.5.0/24. Confirm TS-419P II presence, identify any unexpected devices.

**Discipline:** Security analysis (1.3×)

**Method:** nmap top-1000 port scan from LUCIFER WSL2 across 192.168.5.0/24.

**Starting state:** Live network, WSL2 mirrored mode confirmed. No snapshot required.

**Assertions (machine-checkable):**
```python
assert nas_subnet_reachable is True                            # 192.168.5.0/24 reachable from WSL2
assert any(2049 in h.get("ports", []) for h in hosts)         # NFS port found on at least one host
assert unexpected_ports == [] or unexpected_ports is not None  # unexpected port analysis performed
```

**Failure modes:**
- 0/3: WSL2 → 192.168.5.0/24 routing fails; subnet unreachable; no results.
- 1/3: Subnet reachable (ping sweep only), NAS found, but no port scan; NFS assertion fails.
- 2/3: NFS confirmed, NAS identified; unexpected port analysis not performed or missing.
- 3/3: Full scan — NAS found, all ports listed, unexpected findings analysed, all 3 assertions pass.

**KB target:** `network-topology/nas-subnet-inventory`

**Blocker:** Requires WSL2 → 192.168.5.0/24 routing (pfSense inter-subnet allow rule). Tests mirrored networking reach.

---

### T1-Ch.03 — pfSense Firewall Log Baseline

**Goal:** Parse the last 24h of pfSense firewall logs. Produce: top 10 blocked source IPs, top blocked destination ports, pass/block ratio per interface.

**Discipline:** Security analysis (1.3×)

**Method:** pfSense syslog stream on LUCIFER:514 UDP (live) or `GET /api/v2/status/logs/firewall` (API). Parse and aggregate.

**Starting state:** Live syslog stream flowing (confirmed ✅). At least 24h of logs accumulated. Syslog collector container running (infra pre-req).

**Assertions (machine-checkable):**
```python
assert len(log_entries) >= 100                                 # sufficient log volume parsed
assert len(top_blocked_ips) >= 5                               # top blocked source IPs ranked
assert "block_ratio" in summary and summary["block_ratio"] > 0 # pass/block ratio computed
```

**Failure modes:**
- 0/3: Model can't reach syslog or pfSense log API; returns no data.
- 1/3: Logs parsed, count ≥100 confirmed, but no ranking of blocked IPs; second assertion fails.
- 2/3: Top blocked IPs produced; pass/block ratio missing or not broken down per interface.
- 3/3: Top 10 blocked IPs, top blocked destination ports, pass/block ratio per interface; all 3 assertions pass.

**KB target:** `pfsense/log-baseline-YYYY-MM-DD`

**Sandbox:** Syslog collector container must be running (infrastructure pre-req, not part of the challenge).

---

### T1-Ch.04 — Home Assistant Inventory

**Goal:** Enumerate HA entities, devices, integrations, and add-ons. Identify Pi model and available RAM.

**Discipline:** System administration (1.0×)

**Method:** HA REST API (`GET /api/states`, `GET /api/config`) + Supervisor API (`GET /api/hassio/host/info`, `GET /api/hassio/addons`).

**Starting state:** Live HA instance on Pi 4. Long-lived access token required (pre-condition; see §Pre-conditions).

**Assertions (machine-checkable):**
```python
assert len(entities) >= 10                                     # entity inventory retrieved
assert ha_version is not None                                  # HA version string present
assert system_info.get("board") is not None or system_info.get("total_ram_mb") is not None  # hardware identified
```

**Failure modes:**
- 0/3: No HA token; authentication fails; no data returned.
- 1/3: Entities listed (≥10), HA version retrieved; Supervisor API not called; hardware info missing.
- 2/3: Entities + version + add-on list retrieved; Pi hardware model/RAM not identified.
- 3/3: Full inventory — entities, devices, integrations, add-ons, Pi model, memory; all 3 assertions pass.

**KB target:** `home-assistant/entity-inventory`, `home-assistant/system-baseline`

---

### T1-Ch.05 — NAS Service Inventory

**Goal:** Enumerate running QTS services and NFS/SMB shares on TS-419P II.

**Discipline:** System administration (1.0×)

**Method:** QNAP QTS API (if credentials available) or nmap service scan + `showmount -e <nas-ip>` from LUCIFER WSL2.

**Starting state:** Live NAS on 192.168.5.x. QNAP admin credentials required (pre-condition — status unknown). Fallback: nmap + showmount (no credentials needed).

**Assertions (machine-checkable):**
```python
assert len(nfs_exports) >= 1                                   # at least one NFS export found
assert len(smb_shares) >= 1                                    # at least one SMB share found
assert disk_free_gb > 0                                        # available disk space retrieved
```

**Failure modes:**
- 0/3: 192.168.5.x unreachable from WSL2; no results (routing issue).
- 1/3: NAS reached via nmap, ports confirmed (2049/445 open), but showmount blocked or credentials absent; NFS exports not enumerated.
- 2/3: NFS exports found; SMB shares or disk space not retrieved.
- 3/3: NFS exports, SMB shares, disk space all retrieved; no Container Station confirmed; all 3 assertions pass.

**KB target:** `nas/service-inventory`, `nas/storage-baseline`

---

### T1-Ch.06 — pfSense Firewall Rule Map

**Goal:** Retrieve all firewall rules. Map rules governing 192.168.1.0/24 ↔ 192.168.5.0/24 routing. Identify any rules with `any/any` source/destination (security risk).

**Discipline:** Security analysis (1.3×)

**Method:** `GET /api/v2/firewall/rule` — returns all rules per interface. Parse for inter-subnet entries and any/any patterns.

**Starting state:** Live pfSense REST API (read-only). No snapshot required.

**Assertions (machine-checkable):**
```python
assert len(lan_rules) > 0                                      # LAN interface rules retrieved
assert inter_subnet_rules is not None                          # rules for .1.x ↔ .5.x identified (list, may be empty)
assert any_any_checked is True                                 # any/any analysis was performed (flag set regardless of findings)
```

**Failure modes:**
- 0/3: API returns rules but model doesn't parse or categorize by interface; raw dump only.
- 1/3: LAN rules listed; inter-subnet rules not specifically extracted; second assertion fails.
- 2/3: Inter-subnet rules mapped; any/any check not performed or not explicitly flagged.
- 3/3: All rules retrieved, inter-subnet rules listed (or confirmed absent), any/any entries flagged as security risk; all 3 assertions pass.

**KB target:** `pfsense/firewall-rule-map`, `pfsense/security-findings-01`

---

### T1-Ch.07 — pfSense DNS Resolver Audit

**Goal:** Retrieve DNS resolver configuration. List custom host overrides and domain overrides. Identify any entries pointing to unexpected IPs.

**Discipline:** Security analysis (1.3×)

**Method:** `GET /api/v2/services/unbound/host_override` + `GET /api/v2/services/unbound/domain_override`. Fallback: SSH → `cat /cf/conf/config.xml | grep -A5 hosts`.

**Starting state:** Live pfSense REST API (read-only). Known stale entry `cisco.lan` was removed 2026-06-03 — audit should reflect clean state.

**Assertions (machine-checkable):**
```python
assert dns_resolver_running is True                            # Unbound service confirmed up
assert isinstance(host_overrides, list)                        # override list retrieved (may be empty)
assert all(is_rfc1918(o["ip"]) for o in host_overrides)       # no overrides pointing to public IPs
```

Where `is_rfc1918(ip)` returns True for 10.x, 172.16–31.x, 192.168.x addresses.

**Failure modes:**
- 0/3: DNS config not retrieved (API error or SSH not used as fallback).
- 1/3: Resolver status confirmed running; override list not retrieved.
- 2/3: Overrides listed (list may be empty); IP analysis not performed.
- 3/3: Resolver confirmed, all overrides listed with IP analysis, public IP entries flagged or confirmed absent; all 3 assertions pass.

**KB target:** `pfsense/dns-resolver-config`

---

### T1-Ch.08 — HA Automation Audit

**Goal:** List all automations. For each: trigger type, last triggered timestamp, enabled/disabled status. Flag automations that haven't fired in 30 days (stale candidates).

**Discipline:** System administration (1.0×)

**Method:** `GET /api/states` filtered to `automation.*` entities. Parse `attributes.last_triggered` and `state` (on/off = enabled/disabled).

**Starting state:** Live HA instance. Long-lived access token required. `last_triggered` is null for automations that have never fired — treat as stale.

**Assertions (machine-checkable):**
```python
assert len(automations) >= 1                                   # at least one automation exists
assert all("last_triggered" in a["attributes"] for a in automations)  # timestamps present for all
assert stale_automations is not None                           # stale list produced (list, may be empty)
```

**Failure modes:**
- 0/3: No HA access (token missing/invalid).
- 1/3: Automations listed (count ≥1), but `last_triggered` not extracted from attributes.
- 2/3: Timestamps present; stale filter (30-day or never-triggered) not applied; third assertion fails.
- 3/3: All automations listed with trigger type, enabled status, last_triggered; stale candidates flagged separately; all 3 assertions pass.

**KB target:** `home-assistant/automation-audit`

---

### T1-Ch.09 — Open Port Audit (All Subnets)

**Goal:** Identify all listening services across 192.168.1.0/24 and 192.168.5.0/24. Flag any unexpected open ports (non-standard, or standard ports on unexpected hosts).

**Discipline:** Security analysis (1.3×)

**Method:** `nmap -sV --top-ports 1000 192.168.1.0/24 192.168.5.0/24` from LUCIFER WSL2.

**Starting state:** Live network. Both subnets reachable from WSL2 mirrored mode. Expected known services: pfSense (80/443/514/22), HA (8123), NAS (2049/445/80/443), LUCIFER (3000/8080/9200/9090/3002).

**Assertions (machine-checkable):**
```python
assert "192.168.1.50" in scan_results                          # pfSense scanned and responded
assert any(8123 in r.get("ports", []) for r in scan_results.values())  # HA port found
assert unexpected_findings is not None                         # unexpected port analysis performed
```

**Failure modes:**
- 0/3: nmap fails or not available in WSL2; no results.
- 1/3: 192.168.1.0/24 scanned, pfSense found; 192.168.5.0/24 not scanned (routing not verified); HA assertion passes but unexpected analysis absent.
- 2/3: Both subnets scanned, known services confirmed; unexpected port analysis not performed.
- 3/3: Both subnets fully scanned, all known services confirmed, unexpected findings flagged with host and port; all 3 assertions pass.

**KB target:** `network-topology/open-port-audit`, `network-topology/security-findings`

---

### T1-Ch.10 — Inter-Subnet Traffic Baseline

**Goal:** Using pfSense interface stats and firewall logs, determine traffic volume between 192.168.1.0/24 and 192.168.5.0/24. Identify top talkers in each direction.

**Discipline:** Performance optimization (1.1×)

**Method:** `GET /api/v2/status/interface` for bytes in/out per interface. Cross-reference with firewall log (`GET /api/v2/status/logs/firewall`) filtered to inter-subnet source/dest pairs.

**Starting state:** Live pfSense REST API (read-only). Interface counters are cumulative since last reboot — report as-is with timestamp; do not require 24h window if uptime is shorter.

**Assertions (machine-checkable):**
```python
assert interface_stats["LAN"]["bytes_in"] > 0                 # LAN bytes_in counter retrieved
assert interface_stats["LAN"]["bytes_out"] > 0                # LAN bytes_out counter retrieved
assert len(top_talkers) >= 1                                   # at least one inter-subnet top talker identified
```

**Failure modes:**
- 0/3: Interface stats not retrieved (API error); no data.
- 1/3: Bytes in/out retrieved for LAN interface; no per-IP breakdown; top talkers not identified.
- 2/3: Interface stats retrieved, top talkers identified; traffic consistency assessment (NAS vs anomalous) not performed.
- 3/3: Interface bytes in/out, top talkers per direction, traffic pattern assessment (expected NAS file access or anomaly flag); all 3 assertions pass.

**KB target:** `network-topology/inter-subnet-traffic-baseline`

---

## Pre-Conditions for T1 Challenges

| Pre-condition | Status | Notes |
|---|---|---|
| WSL2 mirrored networking (`networkingMode=mirrored`) | ❌ pending | One line in `.wslconfig`, then `wsl --shutdown` |
| pfSense API package installed | ❌ not installed | See §pfSense API Bootstrap below |
| HA long-lived access token | ❓ unknown | Create in HA profile → Security |
| QNAP admin credentials (API or SSH) | ❓ unknown | QNAP web UI or SSH on 192.168.5.x |
| pfSense syslog forwarding → LUCIFER:514 | ❌ pending | Requires pfSense API or manual config |
| Syslog collector container on LUCIFER | ❌ pending | Docker container, UDP 514 listener |

---

## pfSense Access Strategy (Plus 26.03.1)

### Primary: pfSense REST API package (pfrest.org)

pfSense Plus 26.03 is explicitly supported by the community REST API package at https://pfrest.org.
This is an unofficial but well-maintained open-source package — 200+ endpoints, Swagger UI, GraphQL.

**Install (one command from pfSense shell — requires SSH):**
```bash
pkg-static -C /dev/null add https://github.com/pfrest/pfSense-pkg-RESTAPI/releases/latest/download/pfSense-26.03-pkg-RESTAPI.pkg
```

**Configure after install:**
- System → REST API → Enable: On
- Authentication: API Key (recommended)
- Allowed interfaces: LAN only
- Create API key → store in LSE valve / `.env`

**Verify from LUCIFER WSL2:**
```bash
curl -sk -H "x-api-key: <key>" https://192.168.1.1/api/v2/system/version
```

**Swagger UI (live on pfSense after install):**
System → REST API → Documentation → `https://192.168.1.1/api/v2/documentation`

**⚠️ Important:** pfSense removes unofficial packages during system updates. Reinstall after every pfSense upgrade.

**Key endpoints for T1 challenges:**

| Endpoint | T1 Challenge |
|---|---|
| `GET /api/v2/dhcp/server/lease` | Ch.01 — LAN device map |
| `GET /api/v2/status/logs/firewall` | Ch.03 — Firewall log baseline |
| `GET /api/v2/firewall/rule` | Ch.06 — Firewall rule map |
| `GET /api/v2/services/unbound/host` | Ch.07 — DNS resolver audit |
| `GET /api/v2/status/interface` | Ch.10 — Interface traffic stats |
| `GET /api/v2/system/version` | Bootstrap verification |

---

### Fallback: SSH + config.xml (always available, no package needed)

If the REST API package is unavailable or after a pfSense upgrade before reinstall:

```bash
# Pull full config from pfSense over SSH
ssh admin@192.168.1.50 cat /cf/conf/config.xml > /tmp/lse/pfsense-config.xml
```

config.xml contains: all firewall rules, DHCP config, DNS overrides, interface config.

| Data needed | SSH command |
|---|---|
| Active DHCP leases | `cat /var/dhcpd/var/db/dhcpd.leases` |
| ARP table (live hosts) | `arp -a` |
| Firewall rule list | `pfctl -sr` |
| Interface stats | `pfctl -si` or `netstat -ibn` |
| DNS resolver stats | `unbound-control stats_noreset` |

---

### Syslog (primary source for log-based challenges)
- pfSense → LUCIFER:514 UDP ✅ confirmed live
- Firewall events, DHCP, auth events all flowing
- T1-Ch.03 and log challenges use syslog stream or replayed corpus snapshot

---

**Pre-condition status:**

| Pre-condition | Status | Action |
|---|---|---|
| WSL2 mirrored networking | ✅ confirmed | `networkingMode=mirrored` in `.wslconfig` |
| pfSense SSH access | ✅ confirmed | `ssh admin@192.168.1.50` |
| pfSense syslog → LUCIFER:514 | ✅ confirmed | Live and flowing |
| pfSense REST API package | ✅ installed + live | v2.8, read-only, LAN+WAN+OPT1+OPT2, key in Vaultwarden, access list: 192.168.1.57/32 only |
| HA long-lived access token | ❓ unknown | HA profile → Security → Long-lived tokens |
| QNAP admin credentials | ❓ unknown | QNAP web UI or SSH on 192.168.5.x |
| Syslog collector container (LUCIFER) | ❌ pending | Docker container, UDP 514 listener (nc is temporary) |
