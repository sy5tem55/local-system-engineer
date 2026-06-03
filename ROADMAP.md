# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-06-02

---

## Immediate — Tool v1.5.13: search_web header fix + categories

**Two bugs found during SearXNG deploy:**
1. `search_web` sends no `X-Forwarded-For` header → gets 429 from SearXNG limiter mid-session
2. `search_web` doesn't pass `categories=general,it,science` → misses arxiv, github, stackoverflow, scholar

Both are in the `requests.get()` call in `search_web`:
```python
# Current (broken with limiter):
resp = requests.get(self.valves.SEARXNG_URL, params={...}, timeout=10)

# Fixed:
resp = requests.get(
    self.valves.SEARXNG_URL,
    params={"q": query, "format": "json", "categories": "general,it,science"},
    headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
    timeout=10,
)
```

- [ ] Fix `search_web` in tool v1.5.13
- [ ] Update prompt ENVIRONMENT version to v0.5.11 + tool v1.5.13

---

## Immediate — Network hygiene fixes (real T2 challenges)

Surfaced by first 10 min of syslog data. All require config change on pfSense.

**Samsung TV WAN block + DHCP fix (192.168.1.90)**
- [ ] Create pfSense firewall rule: Source=192.168.1.90, Dest=!RFC1918, Action=Block
- [ ] Create static DHCP mapping for MAC 1c:af:4a:04:5f:b6 with lease=86400
- [ ] Verify TV still reachable on LAN after rule, verify WAN blocked
- Gate: backup config.xml before any change; rollback command documented before deployment

**cisco.lan stale DNS entry**
- [ ] Delete from Services → DNS Resolver → Host Overrides
- [ ] Verify `filterdns: cisco.lan` error stops appearing in syslog

**Syslog collector container**
- [ ] Build persistent Docker container on LUCIFER: UDP 514 listener → structured JSON → SQLite
- [ ] Replace nc with proper collector; integrate with existing lse-net Docker stack

---

## Immediate — ✅ Deploy prompt v0.5.10

`prompts/v0.5.10.md` is written. Hot-swap in OpenWebUI.

- [ ] Deploy prompt v0.5.10 in OpenWebUI Admin → Models

---

## Immediate — Run 6

Full scored eval against the current stack.

**Stack for Run 6:**
- Tool: v1.5.12 ✅ deployed
- Prompt: v0.5.10 (deploy first)
- Filter: lse-routing-filter v1.1.0
- Context monitor: none
- Test suite: v3.5 (21 tests, /60 with P6)
- Profile: 32k · thinking (--reasoning-budget 3072)

**Deploy checklist:**
- [ ] Deploy prompt v0.5.10 in OpenWebUI Admin → Models
- [ ] Verify debug flag OFF
- [ ] Fresh conversation (no prior tool-call history)
- [ ] Run all 21 questions per test-suite-v3.5 using `lse:eval-runner` skill
- [ ] Write `eval/eval-report-v5.md`

**Expected outcome:** Run 3 was 57/57 on v1.5.4/v0.5.1. Major additions since then: RAG layer, MULTI-BLOCK TASK, BACKGROUND PROCESS, WARNING ESCALATION, SIZE SANITY CHECK. Targeting 55+/60; P6 is a new unknown.

---

## ✅ Completed — SearXNG 27-Engine Config Deploy (2026-06-03)

27-engine config prepared 2026-06-01, never deployed. Production running 4 engines only. Brave should be **demoted** (lower weight) not removed — it contributes results despite VPS rate-limiting.

**Config file:** `/home/sy5/docker/searxng_data/settings.yml` — backups at `.backup`, `.backup-v1.0-20260525`, `.bak`

**Target engine set:** arXiv (T1, weight 4), Google Scholar (weight 3), Bing + DDG (weight 2), Brave + Mojeek + Qwant (weight 1, demoted), Wikipedia + Bing News (always-on) + additional engines to 27 total.

**Valkey already deployed** (internal port 6379, lse-net) — check if SearXNG `settings.yml` already has `redis:` section before adding caching task.

**Three changes in one deploy — all go into settings.yml together:**
1. 27-engine config (Brave demoted, arXiv/Scholar/Mojeek/Qwant/Bing added)
2. Valkey/Redis section (env var already wired, settings.yml missing the block)
3. Verify rate limiter backend switches from in-memory to Valkey

```yaml
# Add to settings.yml:
redis:
  url: valkey://valkey:6379/0
```

- [ ] `cat /home/sy5/docker/searxng_data/settings.yml` — read current state
- [ ] Diff against prepared 27-engine config; confirm Brave is demoted not removed
- [ ] Add `redis:` section + 27-engine changes to settings.yml
- [ ] Backup: `cp settings.yml settings.yml.backup-v2-$(date +%Y%m%d)`
- [ ] `cd /home/sy5/docker && docker compose restart searxng`
- [ ] Verify: `curl -s http://localhost:8088/search?q=test&format=json | python3 -m json.tool | head -20`
- [ ] Verify Grafana shows new engine set in `searxng_engines_*` metrics
- [ ] Update `search_web` docstring — SEARCH-THEN-FETCH protocol (tool v1.5.13)

---

## Backlog — searxng-logger rewrite (~30 min)

`/opt/local-se/searxng-logger/logger.py` polls Prometheus for metrics that were never populated (logged "No metrics returned" every minute since deployment).

**Fastest fix:** update logger to scrape SearXNG `/metrics` directly with `Authorization: Basic metrics-admin-2025` header. Parse OpenMetrics → write to SQLite → expose via Prometheus exporter on a dedicated port. Add scrape job to `prometheus.yml`.

- [ ] Rewrite logger to scrape `/metrics` with auth header directly
- [ ] Add new Prometheus scrape job for exporter port
- [ ] Verify `searxng_engines_*` metrics flowing in Grafana

---

## Backlog — KB Retrieval Accuracy Baseline

RAG stack has no baseline. Without one, impossible to tell if KB improves LSE or just adds latency.

**Procedure:**
1. Write 15 questions answerable only from stack-specific operational facts (ports, recovery commands, failure modes, paths)
2. Run each twice: KB disabled (`min_score=1.1`) vs KB enabled
3. Score: correct / partial / wrong
4. Store in `/opt/local-se/kb/eval-kb-baseline.md`; index into ES

**Ongoing:** re-run monthly. KB-enabled delta vs baseline = KB value signal.

- [ ] Write 15-question baseline set
- [ ] Run KB-disabled pass, record scores
- [ ] Run KB-enabled pass, record scores
- [ ] Store `eval-kb-baseline.md`, index into ES

---

## Backlog — Grafana SearXNG Engine Health Dashboard

Current dashboard legend is unreadable with multiple active engines. Needs:
- Legend updated (remove Brave, add Mojeek/Qwant/arXiv)
- Engine favicons in graph legend
- Panel annotation for engine config change date

Deferred until SearXNG engine config is stable in production.

- [ ] Edit Grafana panel JSON for updated engine set

---

## Backlog — LSE Profile Management Eval Test

New eval category: LSE reads `lse-profiles.xml`, searches community sources, cross-references against RTX 4090 hardware constraints, proposes a new `<profile>` block, writes the updated XML (size sanity check must pass).

Tests the full loop: `search_web` → `read_file` → hardware-aware reasoning → `write_file`.

- [ ] Write eval test spec
- [ ] Add to test suite as new category
- [ ] Run against current stack

---

## Backlog — Docs Update

- [ ] `docs/07-operations-runbook.md` — add metrics endpoint reference (Grafana alert pipeline)
- [ ] `README.md` — severely out of date; rewrite to reflect current stack (RAG, Grafana, lse-net, active-task.md)

---

## Tracking Discipline (new — 2026-06-02)

At the **start** of each session:
1. Read `CURRENT-STATE.md` — update version table from actual file headers if anything drifted
2. Read `ROADMAP.md` — pick the top Immediate item

At the **end** of each session (or on context handover):
1. Move completed items from ROADMAP to a new dated entry in `CHANGELOG.md`
2. Update `CURRENT-STATE.md` version table
3. Update `active-task.md` with any unfinished block state
