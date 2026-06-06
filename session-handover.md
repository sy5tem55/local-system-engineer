# Session Handover
> Updated: 2026-06-05 (P5 Cowork — 6 arena solves, SSH hardening, HA template fixed)
> Next session: read ROADMAP.md → CURRENT-STATE.md → this file in that order.

---

## Critical Rules (burn these in)

1. **Edit tool truncates large Python files on the NTFS mount.** Use bash heredoc or
   Python string replacement for ALL Python files >100 lines.
2. **Git commits from Cowork sandbox fail** — commit from WSL terminal only.
3. **NAS IP is 192.168.5.45 / nas.home.arpa** — NOT .10.
4. **SearXNG config requires sudo** — `/home/sy5/docker/searxng_data/` is root-owned.
   Always: validate YAML → sudo cp → docker compose restart → sleep 8 → verify with
   CATEGORY-SPECIFIC query, not "test".
5. **pfSense read-only toggle NOT via API** — `/api/v2/system/api` returns 404.
   Web UI only: System → REST API → Read Only toggle.
6. **docker compose restart shows `0/1`** — display quirk, not an error. Check
   `docker logs searxng --tail 20` for actual status.
7. **"test" query shows only 3-4 engines** — this is correct. Use `&categories=science`
   or `&categories=it` to verify category-specific engines are active.
8. **HAOS SSH add-on regenerates sshd_config on every reboot** — `AllowUsers` and
   `PermitRootLogin` changes do NOT survive reboot. Root SSH is not persistent on HAOS.
   Use `ssh sy5@homeassistant.home.arpa sudo <cmd>` for all HA Pi operations.
   Key auth for sy5 works persistently via `/etc/ssh/authorized_keys`.
9. **HA long-lived tokens are JWTs** — `eyJ` prefix is correct. Token must be ~183 chars.
   If token is 55 chars it was truncated on copy — use the Copy button in HA UI, not
   manual text selection. Decode from QR code with OpenCV if needed.
10. **HA API restart (`POST /api/services/homeassistant/restart`) is soft** — clears YAML
    errors in config but HA notification cache persists until full reboot or manual dismiss.
    Config check: Developer Tools → YAML → Check Configuration.

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
# 1. SearXNG quick health check
curl -s "http://localhost:8088/search?q=CVE+critical+2026&format=json" \
  | python3 -m json.tool | grep '"engine"' | sort -u
# Expected: nvd in results

# 2. Check for auto-generated challenge candidates from ha-t1-008 (2 stale automations found)
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
python3 scripts/challenge_generator.py --list-pending

# 3. Commit everything from this session
git add -A && git commit -m "P5: 6 arena solves, SSH hardening, HA template fix, tool safety patch"
```

**Arena priority order next session:**
1. Samsung TV T4 — DHCP hammer investigation
2. Stale HA automation challenge (from ha-t1-008 findings — 2 automations never fired)
3. NODE2 setup — LM Studio server mode :8081

**TODO next session:**
- Index KB doc: via LSE `index_to_kb(path="docs/kb/ha-long-lived-token-format.md", tag="home-assistant/auth")`
- Update SSH user in ha-t3-001 + infra-t3-002 starting_state: `root` → `sy5` (HAOS root not persistent across reboots)
- Verify HA template error is fully gone after reboot (confirmed this session)

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
| v3 applied (bing news wt3, google news wt3, NVD wt3) | ✅ live (2026-06-05) |
| NVD engine | ✅ returns CVEs with CVSS scores |
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
| RFC KB | ES index `lse-rfc-kb` (707 chunks tagged) |
| pfSense CA cert | `/opt/local-se/cert/pfsense-webgui-ca.crt` |
| NAS hostname | `nas.home.arpa` / `192.168.5.45` |
| QNAP anonymous fix KB | doc_id `7ac7c02c1d118662` (quality 1.0) |
| pfSense API endpoint doc | `docs/searxng-operations.md` (WRITE ACCESS PROTOCOL) |
