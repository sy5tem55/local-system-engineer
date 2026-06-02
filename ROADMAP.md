# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-06-02

---

## Immediate — Deploy prompt v0.5.10

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

## Immediate — SearXNG Engine Config Deploy + Redis Cache

Engine config prepared 2026-06-01 but not deployed. Brave removed; arXiv Tier 1.

- [ ] Deploy updated `settings.yml` to `/home/sy5/docker/searxng_data/settings.yml`
- [ ] Restart SearXNG: `cd /home/sy5/docker && docker compose restart searxng`
- [ ] Add Redis to `lse-net` Docker stack for 5-minute result caching
- [ ] Update `search_web` docstring — add SEARCH-THEN-FETCH protocol (tool v1.5.12)
- [ ] Update `search_kb` to check `lse-search-cache` ES index before hitting upstream engines

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
