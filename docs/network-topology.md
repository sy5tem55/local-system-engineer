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

**Method:** pfSense DHCP lease table (API or UI export) + ARP scan from LUCIFER.

**Assertions:**
- pfSense found at 192.168.1.1
- LUCIFER Windows host found
- HA Pi found
- At least one entry per known device class (workstation, SBC, IoT)

**KB target:** `network-topology/lan-device-inventory` (quality 0.9 — live data)

**Sandbox:** Not applicable (read-only ARP scan). Direct production run safe.

**Escalation candidate:** If pfSense API not reachable from WSL2, this is the first test of the WSL2 networking solution.

---

### T1-Ch.02 — NAS Subnet Map

**Goal:** Enumerate 192.168.5.0/24. Confirm TS-419P II presence, identify any unexpected devices.

**Method:** nmap or ping sweep from LUCIFER (requires routing via pfSense).

**Assertions:**
- TS-419P II found at known IP
- No unexpected open ports beyond NFS (2049), SMB (445), QNAP web (8080/443)
- Subnet reachable from LUCIFER WSL2

**KB target:** `network-topology/nas-subnet-inventory`

**Blocker:** Requires WSL2 → 192.168.5.0/24 routing to work (pfSense must allow it). Tests Option A/B WSL2 networking.

---

### T1-Ch.03 — pfSense Firewall Log Baseline

**Goal:** Parse the last 24h of pfSense firewall logs. Produce: top 10 blocked source IPs, top blocked destination ports, pass/block ratio per interface.

**Method:** pfSense syslog → LUCIFER collector → parse.

**Assertions:**
- At least 100 log entries parsed
- Block events present
- Source IPs are parseable (not all private — some external traffic expected)

**KB target:** `pfsense/log-baseline-YYYY-MM-DD`

**Sandbox:** Syslog collector container must be running first (infrastructure pre-req, not part of challenge).

---

### T1-Ch.04 — Home Assistant Inventory

**Goal:** Enumerate HA entities, devices, integrations, and add-ons. Identify Pi model and available RAM.

**Method:** HA REST API (`/api/states`, `/api/config`, Supervisor API for add-ons and system info).

**Assertions:**
- At least 10 entities found
- HA version retrieved
- Pi model and memory identified
- Add-on list retrieved

**KB target:** `home-assistant/entity-inventory`, `home-assistant/system-baseline`

---

### T1-Ch.05 — NAS Service Inventory

**Goal:** Enumerate running QTS services and NFS/SMB shares on TS-419P II.

**Method:** QNAP QTS API or nmap service scan + manual NFS showmount.

**Assertions:**
- At least one NFS export found
- SMB shares listed
- Available disk space retrieved
- Confirm no Container Station (expected given ARMv5)

**KB target:** `nas/service-inventory`, `nas/storage-baseline`

---

### T1-Ch.06 — pfSense Firewall Rule Map

**Goal:** Retrieve all firewall rules. Map rules governing 192.168.1.0/24 ↔ 192.168.5.0/24 routing. Identify any rules with `any/any` source/destination (security risk).

**Method:** pfSense API (`/api/v1/firewall/rule`).

**Assertions:**
- Rules retrieved for LAN and NAS interfaces
- Inter-subnet rules identified and listed
- Any/any rules flagged

**KB target:** `pfsense/firewall-rule-map`, `pfsense/security-findings-01`

---

### T1-Ch.07 — pfSense DNS Resolver Audit

**Goal:** Retrieve DNS resolver configuration. List custom host overrides and domain overrides. Identify any entries pointing to unexpected IPs.

**Method:** pfSense API (`/api/v1/services/unbound`).

**Assertions:**
- DNS resolver confirmed running
- Host overrides listed
- No entries pointing outside 192.168.1.0/24 or 192.168.5.0/24 without justification

**KB target:** `pfsense/dns-resolver-config`

---

### T1-Ch.08 — HA Automation Audit

**Goal:** List all automations. For each: trigger type, last triggered timestamp, enabled/disabled status. Flag automations that haven't fired in 30 days (stale candidates).

**Method:** HA REST API (`/api/states` filtering `automation.*`).

**Assertions:**
- All automations listed with last_triggered
- Stale automations (>30 days) identified and listed separately

**KB target:** `home-assistant/automation-audit`

---

### T1-Ch.09 — Open Port Audit (All Subnets)

**Goal:** Identify all listening services across 192.168.1.0/24 and 192.168.5.0/24. Flag any unexpected open ports (non-standard, or standard ports on unexpected hosts).

**Method:** nmap top-1000 ports across both subnets from LUCIFER.

**Assertions:**
- Scan completes on both subnets
- Known services confirmed (pfSense 80/443/514, HA 8123, NAS 2049/445/80)
- Any unexpected findings flagged

**KB target:** `network-topology/open-port-audit`, `network-topology/security-findings`

---

### T1-Ch.10 — Inter-Subnet Traffic Baseline

**Goal:** Using pfSense logs and interface stats, determine the traffic volume between 192.168.1.0/24 and 192.168.5.0/24. Identify top talkers in each direction.

**Method:** pfSense API interface stats + firewall log analysis.

**Assertions:**
- Bytes in/out per interface over last 24h retrieved
- Top source IPs for inter-subnet traffic identified
- Traffic pattern is consistent with expected use (NAS file access, not anomalous)

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
