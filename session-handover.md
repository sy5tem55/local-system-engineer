# Session Handover
> Updated: 2026-06-06 (P6 Cowork — SearXNG NVD diagnosis, v0.5.15, hostname fixes, topology series)
> Next session: read ROADMAP.md → CURRENT-STATE.md → this file in that order.

---

## Critical Rules (burn these in)

1. **Edit tool truncates large Python files on the NTFS mount.** Use bash heredoc or
   Python string replacement for ALL Python files >100 lines.
2. **Git commits from Cowork sandbox fail** — commit from WSL terminal only.
3. **NAS IPs are 192.168.5.44 + 192.168.5.45 / n45.home.arpa** — NOT .10.
   Two NICs in failover (switch has no LACP). Both MACs in pfSense static DHCP. DNS returns both A records.
4. **SearXNG config requires sudo** — `/home/sy5/docker/searxng_data/` is root-owned.
   Always: validate YAML → sudo cp → docker compose restart → sleep 8 → verify with
   CATEGORY-SPECIFIC query, not "test".
5. **pfSense REST API auth is `x-api-key` header** — NOT `Authorization: Bearer`.
   Correct: `headers={"x-api-key": key, "Accept": "application/json"}`
   Wrong:   `headers={"Authorization": f"Bearer {key}"}` → 401 AUTH_AUTHENTICATION_FAILED
   See tool v1.5.18 `pfsense_query()` for reference implementation.
6. **pfSense REST API base URL is `https://pfsense.home.arpa/api/v2`** — NOT the bare IP.
   CA cert CN matches hostname only. Using `192.168.1.50` → SSL verify error.
7. **pfSense SSH access is out of scope for LSE** — SSH admin@pfsense = root shell.
   Bypasses the read-only API boundary entirely (can edit config.xml, change rules, restart services).
   For DNS audit: use `dig +short @192.168.1.50 <host>` from LUCIFER — read-only, no credentials.
   For config reads: use REST API read-only endpoints only.
   SSH to pfSense is a human-only operation, never delegated to the model.
8. **pfSense read-only toggle NOT via API** — `/api/v2/system/api` returns 404.
   Web UI only: System → REST API → Read Only toggle.
9. **docker compose restart shows `0/1`** — display quirk, not an error. Check
   `docker logs searxng --tail 20` for actual status.
10. **"test" query shows only 3-4 engines** — this is correct. Use `&categories=science`
   or `&categories=it` to verify category-specific engines are active.
11. **HAOS SSH add-on regenerates sshd_config on every reboot** — `AllowUsers` and
    `PermitRootLogin` changes do NOT survive reboot. Root SSH is not persistent on HAOS.
    Use `ssh sy5@homeassistant.home.arpa sudo <cmd>` for all HA Pi operations.
    Key auth for sy5 works persistently via `/etc/ssh/authorized_keys`.
12. **HA long-lived tokens are JWTs** — `eyJ` prefix is correct. Token must be ~183 chars.
    If token is 55 chars it was truncated on copy — use the Copy button in HA UI, not
    manual text selection. Decode from QR code with OpenCV if needed.
13. **HA API restart (`POST /api/services/homeassistant/restart`) is soft** — clears YAML
    errors in config but HA notification cache persists until full reboot or manual dismiss.
    Config check: Developer Tools → YAML → Check Configuration.

---

## Session 9 Summary (P6 Cowork)

### Completed this session

| Item | Status |
|---|---|
| SearXNG NVD diagnosis — cvedetails.com VPS 403 · removed from config · settings redeployed | ✅ |
| ROADMAP: NVD custom engine (P1) + searxng-error-exporter (P1) — full specs written | ✅ |
| Prompt v0.5.15 — PFSENSE LOG RULE section added · deployed | ✅ |
| NETWORK_CONTEXT in challenge_generator.py — gateway rule + NAS hostname + TV MAC | ✅ |
| `nas.home.arpa` → `n45.home.arpa` — corrected across 7 files | ✅ |
| pfSense API URL: `192.168.1.50` → `pfsense.home.arpa` — all scripts + prompts | ✅ |
| pfSense API auth: `x-api-key` header (not `Authorization: Bearer`) — confirmed + fixed | ✅ |
| Critical rules 5+6 added: x-api-key auth + pfsense.home.arpa URL | ✅ |
| NODE2 documented: Ubuntu 22.04 · 192.168.5.41 · NAS subnet · no static mapping yet | ✅ |
| Network Topology Challenge Series designed — 7 challenges net-t1-013 → net-t3-004 | ✅ |
| Local DNS Architecture added to ROADMAP — known entries + missing + work items | ✅ |
| Samsung TV T4: confirmed firmware noise · lease 7200s normal · static mapping confirmed | ✅ |
| CURRENT-STATE network table expanded with subnet topology detail | ✅ |

### Additional completed (late session)

| Item | Status |
|---|---|
| DNS audit via `dig` — pfsense/homeassistant/n45 confirmed · lucifer/node2 NXDOMAIN | ✅ |
| n45 dual NIC documented — 192.168.5.44 + .45, failover, both in pfSense static DHCP | ✅ |
| GPU-based DNS aliases planned — 4090/3090/5090.home.arpa as additive DNS entries | ✅ |
| SSH COMMAND= PROTOCOL documented in ROADMAP — scoped read-only SSH escalation pattern | ✅ |
| pfSense SSH boundary reinforced — critical rule 7 + ROADMAP note | ✅ |
| openwebui-tool-v1.5.18.py — unbound host endpoint flagged as 404 on Plus 26.03.1 | ✅ |

### Key findings
- pfSense DNS host overrides: REST API endpoint 404s on Plus 26.03.1 — use `dig +short @192.168.1.50 <host>`
- n45.home.arpa returns two A records (.44 + .45) — correct, dual NIC failover setup
- NVD/cvedetails blocked at VPS level (403) — same as Scholar/Reddit
- Grafana "Failing engines" panel = 0 is a known gap (error-exporter not yet built)
- pfSense REST API auth: `x-api-key` header (not `Authorization: Bearer`)

---

## Session 8 Summary (P5 Cowork)

### Completed this session

| Item | Status |
|---|---|
| ha-t1-004 HA Inventory — SOLVED a1 · 15.0 pts | ✅ |
| ha-t1-008 HA Automation Audit — SOLVED a1 · 15.0 pts · 2 stale automations found | ✅ |
| ha-t2-002 HA Template Sensor Audit — SOLVED a1 · 19.5 pts · 2 sensors + migration YAML | ✅ |
| infra-t2-001 SSH Posture Audit HA Pi — SOLVED a1 · 19.5 pts | ✅ |
| infra-t3-002 SSH Key Hardening LUCIFER→Pi — SOLVED a1 · 22.5 pts | ✅ |
| ha-t3-001 HA Template Sensor Migration — SOLVED a1 · 22.5 pts · YAML confirmed fixed | ✅ |
| tool v1.5.18 safety patch — `_BLOCKED_WRITE_FILENAMES` blocks .bashrc + shell configs | ✅ |
| LSE wrote `-e` to ~/.bashrc — found + removed (line 32) | ✅ |
| HA token: JWT format confirmed correct · token was truncated (55 chars) · QR decode used | ✅ |
| HA Pi IP resolved: homeassistant.home.arpa:8123 · Pi IP: 192.168.1.80 | ✅ |
| SSH key auth LUCIFER→Pi (sy5) — working via /etc/ssh/authorized_keys | ✅ |
| HAOS sshd_config quirks documented (see Critical Rules below) | ✅ |
| model identifier standardised: qwen3.6-27b → qwen3.6-27b-q4-64k · ep 16 merged | ✅ |
| infra-t2-001 + infra-t3-002 challenges added to seed_challengedb.py | ✅ |

### Leaderboard
`qwen3.6-27b-q4-64k` — **373.1 pts · 21 eps · 20 solved · 0 esc · avg 1.10 att · 21/21 KB hits**

---

## Session 7 Summary (P4 Cowork)

### Completed this session

| Item | Status |
|---|---|
| Grafana P3 panels — confirmed complete (done previous session) | ✅ |
| HA long-lived token — created in HA UI | ✅ |
| ha-t2-002 (HA Template Sensor Audit) — designed + added to seed_challengedb.py | ✅ |
| ha-t3-001 (HA Template Sensor Migration) — designed + added, requires_human_approval=1 | ✅ |
| ROADMAP / CURRENT-STATE / session-handover updated | ✅ |

---

## Session 6 Summary

### Completed this session

| Item | Status |
|---|---|
| SearXNG v3 config applied (bing/google news, NVD) | ✅ |
| SSL fix: SSL_CERT_FILE → host CA bundle | ✅ |
| NVD engine — CVEs with CVSS scores | ✅ |
| Semantic Scholar — papers with metadata | ✅ |
| searxng-docker legacy dir removed | ✅ |
| entrypoint-wrapper.sh removed | ✅ |
| OpenWebUI filter architecture confirmed (Global OFF, Qwen3-only) | ✅ |
| Routing filter stays v1.1.0 — v1.2.0 built but not needed | ✅ |
| `prompts/claude-l2-system-prompt.md` written | ✅ |
| `LSE L2 — Claude Opus` preset deployed in OpenWebUI | ✅ |
| `LSE Research — Claude Sonnet` preset deployed in OpenWebUI | ✅ |
| **P3 (Cowork):** Grafana `searxng-engine-health` — 6 tuning-signal panels added | ✅ |
| Prometheus labels verified: all metrics use `engine_name` · 18 active engines | ✅ |
| `searxng_engine_errors_total` — zero series confirmed, Panel 24 wired+waiting | ✅ |
| Dashboard provisioner behaviour documented (edit file, not UI) | ✅ |

---

## Session 5 Summary

### Completed this session

| Item | Status |
|---|---|
| v0.5.13 + v1.5.18 confirmed built (prev session) | ✅ |
| Deployed v0.5.13 + v1.5.18 to OpenWebUI | ✅ |
| Eval Run 7 — P4, M3, W1, A3 all 3/3 | ✅ |
| v0.5.14 — Docker NAT topology fix — A1 → 3/3 | ✅ |
| **63/63 achieved** (eval-report-v6.md) | ✅ |
| nas-t2-001 NAS Unexpected Port Investigation | ✅ SOLVED 19.5 pts |
| nas-t3-001 NAS Anonymous Access Hardening | ✅ SOLVED 19.5 pts |
| net-t2-011 Samsung TV Traffic Analysis | ✅ SOLVED 19.5 pts |
| net-t3-002 Samsung TV WAN Isolation | ✅ SOLVED 19.5 pts |
| net-t3-002 a3 assertion patched (write_access probe) | ✅ |
| QNAP anonymous access fixed (human-applied) | ✅ KB indexed quality 1.0 |
| Samsung TV WAN block rule live in pfSense | ✅ verified |
| SearXNG diagnostic v1 (Claude Sonnet 4.6) | ✅ |
| SearXNG settings v2 applied (arxiv fix, scholar disabled) | ✅ |
| SearXNG settings v3 written (news gap, NVD) | ✅ pending apply |
| docs/searxng-operations.md written | ✅ |
| ROADMAP, CURRENT-STATE, CHANGELOG, VERSION updated | ✅ |

### Leaderboard
`qwen3.6-27b-q4-64k` — **259.1 pts · 15 eps · 14 solved · 0 esc · avg 1.13 att · 15/15 KB hits**

### Challenge DB state (15 total)
- T1: 10 active (all previously run, all solved)
- T2: nas-t2-001 ✅, net-t2-011 ✅, auto-pf-t1-002 (rejected)
- T3: nas-t3-001 ✅, net-t3-002 ✅

---

## First Actions Next Session

```bash
# 1. Commit P6 work
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
git add -A && git commit -m "P6: v0.5.15, pfsense hostname+auth fixes, n45 DNS, topology series, NVD diagnosis"

# 2. DNS audit (get key from Vaultwarden first: export PFSENSE_KEY=<key>)
python3 -c "
import os, requests, json, urllib3; urllib3.disable_warnings()
key = os.getenv('PFSENSE_KEY','')
r = requests.get('https://pfsense.home.arpa/api/v2/services/unbound/host',
    headers={'x-api-key': key, 'Accept': 'application/json'},
    verify='/opt/local-se/cert/pfsense-webgui-ca.crt', timeout=10)
print(r.status_code, json.dumps(r.json(), indent=2))
"

# 3. Get NODE2 MAC for static DHCP mapping
python3 -c "
import os, requests, json, urllib3; urllib3.disable_warnings()
key = os.getenv('PFSENSE_KEY','')
r = requests.get('https://pfsense.home.arpa/api/v2/dhcp/server/lease',
    headers={'x-api-key': key, 'Accept': 'application/json'},
    verify='/opt/local-se/cert/pfsense-webgui-ca.crt', timeout=10)
leases = r.json().get('data', [])
node2 = [l for l in leases if '192.168.5.41' in str(l)]
print(node2)
"
```

**Priority order next session:**
1. **DNS audit** — confirm pfsense/homeassistant/n45 · discover any unknowns (needs PFSENSE_KEY)
2. **NODE2 static DHCP + DNS** — get MAC from lease table · add mapping · add `node2.home.arpa`
3. **Samsung TV T4 challenge** — author and seed challenge (firmware noise confirmed, design ready)
4. **Net topology series** — begin seeding net-t1-013 (subnet host enumeration)

**TODO carry-over from P5:**
- Index KB doc: `index_to_kb(path="docs/kb/ha-long-lived-token-format.md", tag="home-assistant/auth")`
- Update SSH user in ha-t3-001 + infra-t3-002 starting_state: `root` → `sy5`

---

## OpenWebUI Setup In Progress

### Routing Filter — v1.1.0 · FINAL
- Global toggle **OFF** — filter applies to Qwen3 preset only ✅
- v1.2.0 built as reference (`tools/lse-routing-filter-v1.2.0.py`) but not deployed — not needed given Global OFF architecture

### Claude Presets — DEPLOYED ✅
See `prompts/claude-l2-system-prompt.md` for system prompts.

| Preset | Base Model | Status |
|---|---|---|
| `LSE L2 — Claude Opus` | `claude-opus-4-6` | ✅ deployed |
| `LSE Research — Claude Sonnet` | `claude-sonnet-4-6` | ✅ deployed |

---

## SearXNG State

| Config | Status |
|---|---|
| v3 applied (bing news wt3, google news wt3) | ✅ live · NVD/cvedetails removed (VPS 403) |
| NVD engine | ❌ cvedetails.com VPS 403 · custom NVD API engine pending (ROADMAP P1) |
| Semantic Scholar | ✅ returns papers with metadata |
| SSL fix | ✅ SSL_CERT_FILE → host CA bundle · entrypoint-wrapper.sh removed |
| searxng-docker legacy dir | ✅ removed — only /home/sy5/docker/ remains |
| URL redirect leak (google.com/search?q= in results) | ⚠️ known bug, needs SearXNG version update |
| Google Scholar | disabled (0% reliability, VPS blocked) |
| Brave | active but auto-suspended on rate limits (expected) |
| Reddit | excluded (VPS blocked) — workaround: site:reddit.com via Google |

### Key metrics passwords (rotate later)
- Metrics auth: `metrics-admin-2025:<SEARXNG_METRICS_PASSWORD>` (in Vaultwarden)
- Metrics endpoint: `http://localhost:8088/metrics`

---

## Sanity Check Findings

### Stale files to clean up (do in next session)
- `docs/searxng-settings-patch-v2.yml` — superseded by `docker/searxng_data/settings.yml`
- `docs/searxng-config.md` — superseded by `docs/searxng-operations.md`
- `mesh_builder.py` + `portrait_3d_pifuhd.py` in root — WAN2.1 artifacts, move to tools/ or delete
- `claude-handover.md` — old 2026-06-02 handover, historical only

### Missing tool version
- `openwebui-tool-v1.5.10.py` — intentionally missing. It was saved as v1.5.11 due to filename mismatch (documented in CHANGELOG 2026-06-01). Not a problem.

### Everything else
- All 9 arena scripts present ✅
- All eval reports v1-v6 present ✅
- All prompt versions v0.1–v0.5.14 present ✅
- Tool versions v1.4.0–v1.5.18 present (minus explained v1.5.10) ✅

---

## Key Paths

| Purpose | Path |
|---|---|
| SearXNG config (source of truth) | `docker/searxng_data/settings.yml` |
| SearXNG operations guide | `docs/searxng-operations.md` |
| Challenge DB | `/opt/local-se/challenges.db` |
| Leaderboard DB | `/opt/local-se/leaderboard.db` |
| RFC KB 