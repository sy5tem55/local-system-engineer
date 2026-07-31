# Tech Debt Audit — LSE / Goethe

> Date: 2026-07-31 · Scope: full repo corpus (audited on the Windows mirror; note the mirror lags the live WSL tree — see D1)
> Method: static analysis (AST, LOC, duplication ratio), live-session evidence from 2026-07-30, prioritized by `(Impact + Risk) × (6 − Effort)`, each dimension 1–5.

## Corpus snapshot

~71k Python LOC on disk, of which only ~25k are live code — the rest is `.backups/`, duplicate trees, and `.bak_*` files. Core: `tools/goethe.py` (6,565 lines, one `Tools` class, 78 methods, 42 valves), `tools/dream_runner.py` (4,550), TRAUM cluster (~5,100), `goethe_kb.py` (1,636), `goethe_ui.py` (1,080). Alongside: two Node/TS subprojects (`Faust/` 183 MB, `coding-gauntlet/` 51 MB, `node_modules` on disk, git-ignored). 19 test files with a strong contract-test culture — but concentrated on dream/TRAUM/KB, not the tool surface. Git is active and healthy; the `.bak` habit predates it and now duplicates it.

## Prioritized findings

| # | Item | Impact | Risk | Effort | Score |
|---|------|--------|------|--------|-------|
| D1 | Divergent copies of the core | 4 | 5 | 2 | 36 |
| D2 | 77 KB changelog inside `goethe.py`'s module docstring | 4 | 2 | 1 | 30 |
| D3 | Docstring contract vs. the 1024-char MCP window | 3 | 4 | 2 | 28 |
| D4 | 70 × `except Exception` | 3 | 4 | 2 | 28 |
| D5 | Untested safety surface | 4 | 5 | 3 | 27 |
| D6 | Hardcoded topology & literals | 3 | 3 | 2 | 24 |
| D7 | `Tools` monolith (78 methods, one class) | 5 | 3 | 4 | 16 |
| D8 | Repo boundary bloat (Faust, coding-gauntlet) | 2 | 2 | 3 | 12 |

### D1 — Divergent copies of the core (score 36) — URGENT
Four copies of goethe.py exist: `tools/goethe.py` (live, WSL), `lse/goethe/goethe.py` (83.8% similar — a stale fork, not a backup), `.backups/*/goethe-v0.*.py`, and this Windows mirror (missing the 2026-07-30 `PLANNER_CLI_TIMEOUT_S` patch, i.e. already stale one day later). 21 `.bak_*` files sit next to sources. This is the exact failure mode that produced plan e264ed19's step-1 defect: a planner grounded on the wrong copy. **Fix:** declare `tools/goethe.py` the single source of truth; delete or README-tombstone `lse/goethe/`; replace the `.bak` habit with git (`git stash`/commits — the repo is already active); add a sync check or cron for the Windows mirror. Effort: hours.

### D2 — Changelog-as-docstring (score 30) — trivial fix, large payoff
The module docstring is 76,781 chars — 23% of the file is version history, duplicating the already-existing 2,895-line `CHANGELOG.md`. Every maintainer — and on this project the maintainers are LLMs — pays that context cost on every read; every `importlib` load parses it. **Fix:** move entries v0.1–v0.4.x into `CHANGELOG.md`, keep a 10-line pointer docstring. One session, zero behavior change, shrinks the file ~1,500 lines.

### D3 — Docstring contract vs. MCP truncation (score 28)
`goethe_mcp.py` registers tools with `description=doc[:1024]`. The v0.4.7 incident proved this is behavior-critical: the planner's MANDATORY TRIGGER block was silently cut and the model violated a rule it never saw. The fix then was manual reordering — fragile; any future docstring edit can silently push a contract past the window again. **Fix:** split each tool docstring into SPEC (contract, must fit 1024) and NOTES (history/rationale below the cut), and add a unit test asserting every registered tool's trigger/gate keywords appear within the first 1024 chars. The `bump_gate.py` pattern shows this kind of gate is already accepted practice here.

### D4 — Broad exception swallowing (score 28)
70 `except Exception` blocks in `goethe.py` alone. Several documented incidents trace to silent degradation (valve-override failure prints and continues; KB enrichment abandons silently; episode logging swallows errors). Deliberate degrade-don't-crash design in a few places is sound — 70 instances is a culture. **Fix:** triage each into (a) intentional degrade → keep but require a `self._log` call, (b) narrow to the actual exception type, (c) let it raise. Add `ruff` with `BLE001` to make regressions visible (no linter config exists today).

### D5 — Untested safety surface (score 27)
The test suite (19 files, good contract style) covers dream/TRAUM/KB/perms/planner-ledger — but there are no tests for `execute_command` (174 body lines, shell boundary), `ssh_run`/`ssh_script`, `sudo_delegation_block`, or pfSense writes. `sudo_delegation_block` is the product wedge in the productization plan ("safe, auditable write access") and the single most security-sensitive path in the codebase; it is currently verified only by field use. **Fix:** contract tests in the existing PROVE style: injection attempts, grant-scope escapes, fail-closed behavior (v0.4.9 fixed a fail-closed bug — that regression has no test), delegation-block bypass attempts. This is also a fundability artifact: "our safety model has an adversarial test suite" belongs in the pitch.

### D6 — Hardcoded topology (score 24)
25+ literal `localhost`/port references, 17 `/opt/local-se`, 8 `/home/sy5` in `goethe.py`; yesterday's hardcoded `timeout=180` and the Grafana :3001/:3002 drift are the recurring symptom. Valves exist as the config mechanism but coverage is partial. **Fix:** sweep literals into valves or one `_topology` constants block, cross-checked against `kb/STACK-MAP.md` (now the pinned ground truth) by a small test.

### D7 — The `Tools` monolith (score 16, structural, not urgent)
One class, 78 methods, 42 valve fields, 6.5k lines. Mitigating: median method is 44 lines, `bump_gate.py` polices complexity, and half of every big method is documentation (`execute_command` = 184 doc / 174 code). The `KBMixin` + `--also` module pattern (vaultwarden/pfsense/net_discovery already external) proves the seam works. **Fix (incremental, alongside features):** extract cohesive mixins in this order — PlannerMixin (~1,200 lines incl. backends/envelope/ledger), NodeLifecycleMixin (wake/shutdown/agents), NetSecMixin (nmap/ssh), WebMixin (search/fetch/reddit). Do D2 first; the file shrinks 25% before any code moves. Do not do this as a big-bang rewrite — the v0.4.5→0.4.8 planner saga shows this codebase's own history punishing structure changes that outrun end-to-end testing.

### D8 — Repo boundaries (score 12)
`Faust/` (183 MB, 49 MB of it an internal `archive/`) and `coding-gauntlet/` (51 MB) are unrelated experiments living in the production LSE repo with `node_modules` on disk. Git-ignored, so history is clean — but they inflate every backup, sync, and search surface (2,132 TS files dominate any repo-wide grep). **Fix:** move to sibling repos or prune `node_modules`/`archive`; low urgency.

## Phased remediation (compatible with the e264ed19 product plan)

**Phase A — this week, no behavior change:** D2 (changelog extraction), D1 (delete stale forks, mirror-sync check), D8-lite (prune `node_modules` + `Faust/archive`). Net: goethe.py −25% size, one source of truth, repo −150 MB.

**Phase B — next 2–3 sessions, gates before growth:** D3 (SPEC/NOTES split + 1024-window test), D4 (ruff + BLE001 triage), D6 (topology sweep + STACK-MAP cross-check test). These are prerequisites for the product plan's Phase 0 tool additions — every new tool inherits the docstring window and config discipline.

**Phase C — alongside product plan steps 13–26:** D5 (adversarial tests for the safety wedge — schedule before beta customers touch the gateway), then D7 mixin extractions one at a time, each behind a green test run.

**Explicit non-recommendations:** no big-bang rewrite of `Tools`; no async planner revival (tried, reverted, documented); no framework migration. The codebase's discipline features — empirical changelog, bump_gate, contract tests, degrade-don't-crash — are assets to extend, not replace.
