# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-06-05 (P3 Cowork)

---

## Immediate — Claude L2 Setup

- [x] **Create Claude Opus L2 preset in OpenWebUI** ✅ — deployed (2026-06-05)
- [x] **Create Claude Sonnet Research preset in OpenWebUI** ✅ — deployed (2026-06-05)
- [x] **Write `prompts/claude-l2-system-prompt.md`** ✅ (2026-06-05)
- [x] **Routing filter stays v1.1.0** ✅ — Global OFF · Qwen3 preset only · v1.2.0 not needed
- [x] **Apply SearXNG settings v3** ✅ — bing news + google news + NVD active (2026-06-05)
- [x] **Run SearXNG diagnostic v2** ✅ — NVD fires on CVE queries, news gap confirmed fixed (2026-06-05)

- [x] **Grafana engine health panels** ✅ — 6 tuning-signal panels deployed (P3 Cowork 2026-06-05)
  - Response time ranking, result yield ranking, reliability rate, error rate table, dead-engine detector, response time trend
  - `searxng_engine_errors_total` (Panel 24) wired but empty — P4 (error-exporter) still open

---

## Immediate — Arena T2/T3 remaining

- [x] nas-t2-001 NAS Unexpected Port Investigation ✅ SOLVED · 19.5 pts
- [x] nas-t3-001 NAS Anonymous Access Hardening Verification ✅ SOLVED · 19.5 pts
- [x] net-t2-011 Samsung TV Traffic Analysis ✅ SOLVED · 19.5 pts
- [x] net-t3-002 Samsung TV WAN Isolation ✅ SOLVED · 19.5 pts (a3 assertion fixed post-run)

- [ ] **net-t3-002 re-run** (optional) — a3 was patched after the solve. Re-run to confirm
  `write_access_verified_inactive` assertion works correctly with the API probe approach.

- [ ] **Samsung TV DHCP hammer** — WAN blocked but DHCP rate still high (every 1-2 min)
  Needs T2.5 investigation: is the DHCP hammer causing network issues or just noise?

---

## Immediate — Eval

- [ ] All 63/63 confirmed ✅ (Run 7, v0.5.14 + v1.5.18)
- [ ] No new prompt/tool changes pending — Run 8 only after new gaps identified

---

## Immediate — Documentation Cleanup

- [ ] Delete `docs/searxng-settings-patch-v2.yml` — superseded by `docker/searxng_data/settings.yml`
- [ ] Archive `docs/searxng-config.md` — superseded by `docs/searxng-operations.md`
- [ ] Move `mesh_builder.py` + `portrait_3d_pifuhd.py` from root to `tools/` or delete
- [ ] Write `docs/claude-l2-system-prompt.md` — document the L2 escalation role

---

## Backlog — SearXNG

- [ ] **URL redirect leak fix** — google.com/search?q= URLs appearing in results
  Root cause: SearXNG parser issue, not config. Requires `docker pull searxng/searxng:latest`
  + test in staging before applying. Check current version: `docker exec searxng searxng --version`

- [ ] **Reddit engine** — blocked on VPS IPs for anonymous access
  Options: (a) Reddit OAuth app + bearer token, (b) site:reddit.com via Google (current workaround)
  "Velvet gloves" approach: OAuth with proper User-Agent, respect rate limits (60 req/min)

- [ ] **Google Scholar** — 0% reliability, VPS IP blocked
  Debug: `docker exec searxng curl -sA "Mozilla/5.0" "https://scholar.google.com/scholar?q=test" | head -3`
  Re-enable checklist in `docs/searxng-operations.md`

- [ ] **searxng-logger rewrite** — scrape /metrics directly with Authorization: Basic header

---

## Backlog — Arena

- [ ] **Samsung TV T4** — verify DHCP hammer frequency; determine if pfSense DHCP lease time needs adjustment
- [x] **ha-t1-004** ✅ SOLVED 15.0 pts (2026-06-05)
- [x] **ha-t1-008** ✅ SOLVED 15.0 pts · 2 stale automations found (2026-06-05)
- [x] **ha-t2-002** ✅ SOLVED 19.5 pts · template sensors identified (2026-06-05)
- [x] **ha-t3-001** ✅ SOLVED 22.5 pts · YAML fixed + confirmed (2026-06-05)
- [x] **infra-t2-001** ✅ SOLVED 19.5 pts · SSH posture audited (2026-06-05)
- [x] **infra-t3-002** ✅ SOLVED 22.5 pts · key auth live, password auth disabled (2026-06-05)
- [ ] **ChallengeGenerator quality** — llama3.2:3b produces broken assertions (a2 bug in Samsung T2 proposal)
  Consider: validate assertions with AST parse before inserting to DB

---

## Backlog — Infrastructure

- [ ] NODE2 — LM Studio server mode on RTX 3090, expose :8081, add to pfSense API access list
- [ ] NODE3 — WSL2 install, llama-server deploy, test `wsl-gaming-teardown.ps1`
- [x] HA long-lived token — ✅ created (2026-06-05) · stored in Vaultwarden as HA_TOKEN

---

## Deferred — Zero-Persistence Trust (ZPT) Architecture

> **Definition:** A session-scoped secret architecture where no operational secret persists
> on disk between sessions. A physical USB key is the session gate — present to start,
> removed to terminate all secret access. Extends Zero Trust with a physical persistence
> boundary: even a fully compromised host cannot access secrets after USB removal.

### Design Principles

1. **Single physical gate** — USB presence is the only requirement to start a session.
   No USB = no secrets = no session. Removes the "always-on credential" attack surface.

2. **Load-once, session-scoped** — Secrets are read from USB once at launch into tmpfs
   (`/run/lse-secrets/` or similar). tmpfs is wiped on unmount/reboot. No disk writes.

3. **Secret tiering by access frequency:**
   - `HIGH FREQ` (pfSense API key, HA token, HF_TOKEN) → USB → tmpfs → `.lse/secrets`
     ~50 tokens per read, no Vaultwarden roundtrip needed
   - `LOW FREQ` (user passwords, OAuth tokens) → Vaultwarden only
     Vault roundtrip acceptable for rare operations
   - `GATE KEY` (Vaultwarden master password) → USB only, never written to disk

4. **Vaultwarden role narrows** — becomes the store for secrets requiring human-level
   protection or rare access. High-frequency operational keys bypass it entirely.
   Token cost of vault unlock is paid at most once per session.

5. **HF_TOKEN and other env var secrets removed from `.bashrc`** — currently exposed
   in plaintext. Must move to USB → tmpfs load before ZPT can be considered complete.

### Implementation Tasks (deferred)

- [ ] Audit all plaintext secrets currently in `.bashrc`, `.lse/secrets`, env vars
- [ ] Design USB filesystem layout (encrypted LUKS partition recommended)
- [ ] Modify `lse-stack-launch-1.078.ps1` — add USB presence check + secrets load to tmpfs
- [ ] Replace `.bashrc` `export HF_TOKEN=...` with tmpfs-loaded env injection at launch
- [ ] Write shutdown hook — wipe tmpfs on session end / USB removal
- [ ] Design as arena challenge: `infra-t3-003` ZPT Bootstrap (T3, security, 1.5×)
- [ ] Test: disconnect USB mid-session → verify new secret fetches fail gracefully

---

## WRITE ACCESS PROTOCOL — permanent rule

pfSense REST API is read-only by default. For T3+ write challenges:
1. Enable write in pfSense UI (System → REST API → disable Read Only) immediately before task
2. Complete task and verify
3. Re-enable Read Only before ending the session
4. Log in CHANGELOG: timestamp + what was changed

Verify re-enabled: `pfsense_query('/api/v2/firewall/rule', method='PATCH', payload={})` should return 403.
**NOTE:** `/api/v2/system/api` returns 404 — read-only toggle NOT available via REST API, web UI only.
