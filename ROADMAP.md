# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-06-03 (session 2)

---

## ✅ Completed — Prompt v0.5.12 + Tool v1.5.14: three protocol fixes (2026-06-03)

Fix 1: Step milestone headers for 4+ sequential steps · Fix 2: no sudo_delegation_block inside think phase · Fix 3: step_number/total_steps/verify_command params + block format. Deployed and verified.

---

## ✅ Completed — Credential rotation (Grafana admin + SearXNG metrics password) (2026-06-03)

Fixed by LSE. All passwords rotated, Vaultwarden updated, metrics endpoint verified.

---

## Immediate — LSE Challenge Arena: T1 pfSense challenges + HA sandbox

Design consolidated in `docs/lse-challenge-arena.md`. Build order:

- [x] Install pfSense REST API package — v2.8 live, read-only, key in Vaultwarden ✅ (2026-06-03)
- [ ] **Security: BW_PASSWORD → env var** — set in WSL2 shell before OpenWebUI launch, remove from valve. OpenWebUI does not encrypt valves at rest (plaintext SQLite). This is the priority fix.
- [x] Add `PFSENSE_API_KEY` + `PFSENSE_URL` valves to tool v1.5.15 ✅
- [x] **Tool v1.5.16 — pfSense SSL verification** ✅
      `PFSENSE_CA_CERT` valve + `_pfsense_verify()` helper. Cert at
      `/opt/local-se/cert/pfsense-webgui-ca.crt` (sy5:sy5 644, valid → Apr 2036).
      Falls back to `verify=False` with logged warning if cert missing. Deploy pending. (read-only key, acceptable blast radius)

  **WRITE ACCESS PROTOCOL — permanent rule:**
  pfSense REST API is read-only by default. Write access (required for T3+ challenges deploying
  firewall rules) must be treated as a temporary elevation:
  1. Enable write in pfSense UI (System → REST API → disable Read Only) immediately before the task
  2. Complete the task
  3. Re-enable Read Only immediately after — before ending the session
  Leaving write access enabled between sessions is a security violation.
  Write-enabled sessions must be logged in CHANGELOG with timestamp.
- [ ] When NODE2/NODE3 come online: add their /32 to pfSense REST API access list (System → REST API → Access List)
- [ ] Hand-author 10 T1 pfSense insight challenges (assertions + failure modes)
- [ ] Deploy HA Core sandbox container on lse-net
- [ ] Decide VRAM/concurrency strategy (sequential vs round-robin vs CPU offload for 3 models)
- [ ] Seed ChallengeDB (SQLite) with T1 challenges
- [ ] Build LSEChallengeEnv (gymnasium.Env, single-episode)
- [ ] Build EscalationGate (convergence detection + Claude API + KB logging)
- [ ] LeaderboardService (point tracking, episode statistics)

Gate: T1 challenges authored before any harness code. Sandbox gate before any production deploy.

---

## ✅ Reassigned — Network hygiene → LSE Challenge Arena (2026-06-03)

Samsung TV WAN block + static DHCP and syslog collector container reassigned as LSE arena challenges.
These are real T2/T3 problems with known correct solutions — ideal challenge material.

**cisco.lan stale DNS entry** — Fixed 2026-06-03 ✅

---

## Immediate — Run 7 prep: prompt fixes from Run 6 gaps

From eval-report-v5.md Next Steps:

- [ ] **P4 fix** — add to system prompt or execute_command docstring: when sudo appears anywhere in a pipeline, offer to split (run non-sudo portion directly, delegate sudo part)
- [ ] **M3 fix** — on file-not-found, always propose one recovery action (list directory, suggest alternative path)
- [ ] **W1 fix** — do not verify static Linux filesystem paths with tool calls
- [ ] **A3 precondition** — verify open-webui has a systemd unit before running A3; update test suite note
- [ ] Bump tool to v1.5.14 or prompt to v0.5.12 after fixes
- [ ] Run 7 against v3.5 test suite

---

## ✅ Completed — Grafana SearXNG Engine Health Dashboard (2026-06-03)

- Dashboard JSON updated: engine filter variable, error panels, dynamic queries
- Deployed via Grafana API (`/api/dashboards/db`)
- Metrics endpoint fixed: `general.open_metrics` added to settings.yml
- Prometheus scrape confirmed working: 15+ engines now in metrics
- Emoji overrides stripped (cleaner without favicons)
- Note: engine metrics only populate after first query per engine — run varied searches to warm all 27

---

## ✅ Completed — SearXNG metrics pipeline fix (2026-06-03)

- Root cause: `general.open_metrics` was missing → `/metrics` returned 404
- Fix: added `general:\n  open_metrics: "metrics-admin-2025"` to settings.yml
- Password aligned with existing Prometheus `basic_auth` config
- Prometheus scrape target now healthy

---

## ✅ Completed — Run 6 eval (2026-06-03)

**Score: 58/63** — `eval/eval-report-v5.md`
Adjusted to 57-pt basis: **52/57** — −5 from Run 3 baseline.
All regressions are 2/3 partials — no safety failures.

---

## ✅ Completed — SearXNG 27-Engine Config Deploy (2026-06-03)

- 27-engine config live in production
- Valkey/Redis section added to settings.yml
- Limiter disabled (single-user local stack)
- search_web headers + categories fix in tool v1.5.13

---

## ✅ Completed — Tool v1.5.13 + Prompt v0.5.11 (2026-06-03)

- search_web X-Forwarded-For header fix
- categories=general,it,science added
- Both deployed to OpenWebUI

---

## Backlog — WSL Gaming Teardown script (NODE3 enabler)

Script written: `wsl-gaming-teardown.ps1`

Brings down the full LSE stack (Docker containers, llama-server, OpenWebUI, Ollama, all exporters),
runs `wsl --shutdown`, kills Windows-side WSL processes, verifies VRAM released via nvidia-smi.

Resolves the gaming performance concern for NODE3 (9800X3D / RTX 5090): WSL installation has
near-zero idle overhead; this script guarantees a pristine system before any gaming session.

- [ ] Test on LUCIFER — verify all 6 steps complete cleanly
- [ ] Test VRAM clears to < 5% after run
- [ ] Pin shortcut to desktop or Windows Terminal profile for quick access
- [ ] After testing: deploy same script on NODE3 once WSL is installed there

---

## Backlog — searxng-logger rewrite (~30 min)

`/opt/local-se/searxng-logger/logger.py` polls Prometheus with wrong logic.
Now that `/metrics` is live with auth, the rewrite path is clear.

**Fix:** scrape SearXNG `/metrics` directly with `Authorization: Basic` header.
Parse OpenMetrics → SQLite → expose via Prometheus exporter on dedicated port.

- [ ] Rewrite logger to scrape `/metrics` with auth header
- [ ] Add new Prometheus scrape job for exporter port
- [ ] Verify `searxng_engines_*` flowing in Grafana

---

## Backlog — KB Retrieval Accuracy Baseline

No baseline exists. Without one, impossible to measure KB value.

- [ ] Write 15-question baseline set (stack-specific operational facts only)
- [ ] Run KB-disabled pass, record scores
- [ ] Run KB-enabled pass, record scores
- [ ] Store `eval-kb-baseline.md`, index into ES
- [ ] Re-run monthly

---

## Backlog — LSE Profile Management Eval Test

New eval category: LSE reads `lse-profiles.xml`, searches community sources,
cross-references RTX 4090 constraints, proposes new `<profile>` block, writes XML.

- [ ] Write eval test spec
- [ ] Add to test suite as new category
- [ ] Run against current stack

---

## Backlog — Docs Update

- [ ] `docs/07-operations-runbook.md` — add metrics endpoint reference + auth header
- [ ] `README.md` — rewrite to reflect current stack (RAG, Grafana, lse-net, Valkey, 27-engine SearXNG)

---

## Tracking Discipline (2026-06-02)

At the **start** of each session:
1. Read `CURRENT-STATE.md` — update version table if anything drifted
2. Read `ROADMAP.md` — pick the top Immediate item

At the **end** of each session (or on context handover):
1. Move completed items to a new dated entry in `CHANGELOG.md`
2. Update `CURRENT-STATE.md` version table
3. Update `active-task.md` with any unfinished block state
