# Goethe / LSE — Tech-Debt Remediation Report, D1–D8

> Programme date: 2026-07-31 (single day, multi-session)
> Audit of record: `docs/TECH-DEBT-AUDIT-2026-07-31.md`
> Branch: `codex/fix-sudo-grants-live` · 20 commits · **not yet pushed**
> Verification: independent re-check of all eight findings against the live
> WSL tree at `/home/sy5/projects/local-system-engineer`, not against the
> completion reports.

---

## 1. Executive summary

All eight audit findings are delivered and verified against the audit's own
acceptance criteria. The headline number is `tools/goethe.py`: **6,565 → 2,109
lines, a 68% reduction**, with the public tool surface unchanged at 39
throughout and the test suite growing 548 → 560 passing.

The more durable outcome is not the line count. It is that four permanent AST
guard tests now make the fixed defects *unrepeatable*, a linter gate exists
where none did, and the product's safety wedge went from zero adversarial tests
to 55 — having had a live vulnerability found and fixed in the process.

One caveat governs everything below: **the refactor is not live.** The running
gateway is serving pre-D7 code from memory. See §6.

---

## 2. Finding-by-finding outcome

| # | Finding | Score | Status | Evidence |
|---|---|---|---|---|
| D1 | Divergent copies of the core | 36 | **Done** | 1 `goethe.py` in repo; `lse/goethe/` fork deleted; `.bak_*` 21 → 0 beside sources; sync guard extended to all 7 modules and proven in 2 failure modes |
| D2 | 77 KB changelog-as-docstring | 30 | **Done** | Module docstring 76,781 → 1,470 chars (−98%); history in `CHANGELOG.md` (2,965 lines) |
| D3 | Docstring vs 1024-char MCP window | 28 | **Done** | `test_docstring_mcp_truncation.py` green; MRO-aware, covers all 36 arg-taking tools across all 5 mixins |
| D4 | 70 × `except Exception` | 28 | **Done** | 74 triaged → 28 survivors, **every one** carrying `# noqa: BLE001` + written justification; ruff config created (none existed) |
| D5 | Untested safety surface | 27 | **Done** | 55 adversarial tests; **1 live vulnerability found and fixed**; 4 further bypasses pinned `xfail(strict=True)` pending an operator decision |
| D6 | Hardcoded topology literals | 24 | **Done** | 22 outside-Valves literals routed; 2 endpoint conflicts probed live and documented; `test_topology_literals.py` AST gate |
| D7 | `Tools` monolith | 16 | **Done** | 4 mixins extracted; 5,692 → 2,109 lines; 39 tools unchanged; per-step runtime proofs |
| D8 | Repo boundary bloat | 12 | **Partial** | Siblings created and gitignored, but copied not moved — see §5 |

---

## 3. Metrics

### `tools/goethe.py` trajectory

| Commit | Lines | Step |
|---|---|---|
| `a5589d2` | 6,565 | audit baseline |
| `b2fe3b4` | 6,051 | D2 changelog extraction |
| `766182a` | 5,820 | D4 except-triage |
| `e271ff0` | 5,835 | D6 topology sweep |
| `feb7911` | 5,692 | D5 + `search_rfc` removal |
| `10b6b50` | 5,251 | D7 NetSecMixin |
| `dd315c4` | 4,624 | D7 NodeLifecycleMixin |
| `a841ad5` | 2,987 | D7 PlannerMixin |
| `ec0ee9a` | **2,109** | D7 WebMixin |

### Structure

`Tools` MRO: `Tools → KBMixin → NetSecMixin → NodeLifecycleMixin →
PlannerMixin → WebMixin → object`

| Module | Lines | Owns |
|---|---|---|
| `goethe.py` | 2,109 | safety wedge + shared/uncategorised |
| `goethe_planner.py` | 1,691 | planner, ledger, backend dispatch |
| `goethe_kb.py` | 1,624 | KB/skills (pre-existing precedent) |
| `goethe_web.py` | 995 | search, fetch, download monitoring |
| `goethe_node.py` | 692 | node lifecycle, `_NODE_REGISTRY` |
| `goethe_netsec.py` | 483 | ssh, nmap |
| `goethe_constants.py` | 29 | shared literals, zero-dependency |

### Quality gates

| Metric | Before | After |
|---|---|---|
| Tests passing | 548 | 560 |
| Test files | 19 | 23 |
| Permanent AST guards | 1 (`bump_gate.py`) | 5 |
| Linter config | none | `ruff` + BLE001 |
| Adversarial safety tests | 0 | 55 |
| Public tool surface | 39 | 39 (invariant) |

---

## 4. Hard-won improvements

These are the findings that were not in the audit and that cost real effort to
discover. They are the actual value of the programme.

**A dead safety guard, live for months (D5).** `_BLOCKED_WRITE_FILENAMES` —
protecting `.bashrc`, `.ssh/authorized_keys`, private keys — had **never fired
since it was written**. `_norm()` returns a trailing-slash path, so
`os.path.basename("/home/u/.bashrc/")` returns `""` and no entry ever matched.
Every shell rc file and SSH key was writable by the agent: a textbook
persistence vector sitting inside the feature sold as the safety model. Found
only because D5 wrote adversarial tests instead of trusting the code's shape.
Fixed and pinned by regression test.

**A green linter run that proved nothing (D4).** D4 reported
`ruff --select BLE001 → 0 violations`. True, and irrelevant: the full ruleset
found **9 × F821 undefined-name** errors the narrowing itself had introduced —
`except requests.RequestException` where `requests` was only ever imported
inside method bodies under an alias. Each would have raised `NameError` *while
handling an error*, converting designed graceful degradation into a crash
exactly when the system was already degraded. Invisible to `py_compile`, to
import, and to all 487 tests then passing. Compounded by a second trap: `ruff`
is not in the `owui` venv, so `python3 -m ruff` fails with "No module named
ruff" — a report claiming a clean run from that interpreter never ran one.
**Rule adopted:** run the whole ruleset, from the verified binary path.

**Plans that undercount, three times running (D7).** The D7 plan estimated
PlannerMixin at 18 methods from a keyword-prefix scan. Manual gap-inspection
found 8 more (26). A rigorous call-graph closure from the four public entry
points — following both `self.foo()` calls *and* bare `self.foo` references —
found 3 more still. Truth: **29 methods + 5 class attributes**, 61% above the
estimate. Name-based grouping is not a membership test. **Rule adopted:**
compute the closure, then reverse-check that nothing outside it calls in.

**The comment-absorption bug, and why the recovery mattered (D7 Step 9).** The
deletion script used a fixed 4-line lookback to sweep each element's header
comment. Two bugs: an off-by-one across a blank line, and a lookback too short
to see a *second* stacked header. Result: three orphaned comment fragments
pointing at code that was gone. The fix was **not** to patch the damage — it
was `git checkout -- tools/goethe.py`, full discard to the last clean commit,
then a corrected algorithm walking upward through any mixture of blank and
comment lines. Patching a botched mechanical edit produces a file no reviewer
can certify; redoing it produces one they can.

**Editing the wrong copy of the file (D7 Step 3-7).** An early edit went to the
Windows mirror instead of the live WSL tree. Caught before any test ran, by
checking the live file and finding it unmodified. This is D1's failure mode
biting *during the work to fix D1* — and it recurred once more in this final
pass, when the rewritten sync script was first written to the mirror. Both were
caught and corrected. **The live WSL path is the only source of truth.**

**Success that breaks the ground truth (this pass).** D7 worked — and in
working, silently invalidated `kb/STACK-MAP.md`, the file auto-attached to
*every* `planner()` call as PINNED GROUND TRUTH. It still said the tool surface
was `tools/goethe.py`; after D7 that is wrong for 33 of 39 tools. A planner
asked to modify `search_web` would have been authoritatively pointed at a file
that no longer contains it. The grounding mechanism added earlier in the same
programme had itself gone stale. **Rule adopted:** a refactor is not complete
until the documents that ground the agents are updated with it.

**Guards that quietly stop guarding (this pass).** The D1 mirror-sync script
watched one file. After D7 the tool surface is seven modules, so it was
watching 1/7 of its remit — and reported "IN SYNC" for a mirror holding a
`goethe.py` whose five imports were absent, i.e. one that would raise
`ModuleNotFoundError` on load. Worse than lagging: unloadable, while the guard
said fine. Same class of defect as the dead write-blocklist. **Rule adopted:**
when the thing being guarded changes shape, re-derive the guard's scope; and
prove a guard fails before trusting it to pass. The rewritten script was tested
in both failure modes (missing module, perturbed module) before being accepted.

**Backend timeouts strand ledger tasks (this pass).** Ledger block `23c00a76`
sat `open` for hours as a phantom D6 duplicate. Cause: the ledger writes the
task row *before* the planner backend returns, so a timeout leaves an orphan
with `steps_json = NULL` and no plan — indistinguishable from real work by
status alone. Closed as `abandoned` with full provenance. The underlying
timeout was itself fixed earlier in the programme (`PLANNER_CLI_TIMEOUT_S`
valve, plus `start-goethe.sh` importing `GOETHE_PLANNER_*` on the GUI path,
which only systemd had done).

**Deleting code needs usage evidence, not grep (`search_rfc`).** 149 lines
removed after mining the episode corpus by `.tool` field: **0 invocations in
6,967 tool calls** since v1.5.18. Grep would have shown matches in docs and
backups and argued for keeping it. The Elasticsearch index (1,490 chunks) was
deliberately left dormant rather than dropped — cheap to keep, expensive to
rebuild if the decision reverses.

---

## 5. Open items

Reported rather than fixed — each needs an operator decision.

**1. The refactor is not live.** *(highest priority)*
The `:9700` gateway (PID 1126049) started 05:30:49; the first D7 commit landed
06:10:32. It is serving the pre-D7 monolith from memory. Disk is refactored,
committed, and green; runtime is not. **A restart is required.** Additionally
three `goethe_mcp` processes are running from three vintages (04:35, 05:30,
06:33) where there should be one.

**2. D8 copied rather than moved.**
`Faust/` (183 MB) and `coding-gauntlet/` (70 MB) still sit in the production
repo — gitignored, so history is clean, but duplicating the extracted siblings
(153 MB / 21 MB). `node_modules` and `Faust/archive` were never pruned. ~253 MB
of duplicate on disk. This is D1's "divergent copies" hazard in a new location.

**3. `Faust`'s sibling repo has a broken remote.**
`/home/sy5/projects/Faust` has `origin` pointing at
`/mnt/c/.../local-system-engineer/Faust` — a path inside the *old* location
that is not a git repository. `git ls-remote origin` fails fatally, so it can
neither push nor pull. `coding-gauntlet` correctly points at GitHub.

**4. Four safety bypasses remain open by design (D5).**
Pinned `xfail(strict=True)`, so they announce themselves (XPASS) the moment
anyone fixes them: heredoc-feeding-an-interpreter, whitespace evasion of
`_BLOCKED_COMMANDS`, and shell indirection reconstructing `sudo`. Fixing them
changes scan semantics and risks false-positives on legitimate work — an
operator decision, deliberately not slipped in behind a test.

**5. 161 pre-existing ruff findings** in `tools/` files D1–D8 never touched
(`traum_state.py`, `goethe_mcp.py`, `goethe_perms.py`, `goethe_ui.py`,
`dream_*.py`, and others). Out of scope throughout; the six D7-scoped modules
are clean.

**6. `_call_hermes` / `_kanban_create_card`** remain as RETIRED stubs returning
error strings. Harmless, removable whenever convenient.

**7. Nothing is pushed.** All 20 commits are local on
`codex/fix-sudo-grants-live`.

---

## 6. Verification method — and its limits

**Runtime-verified** (executed live through the real production loader
`goethe_mcp.load_goethe` + `make_instance`, not a naive import):
MRO resolution across all five mixins · 39-tool surface via real
`inspect.getmembers` · `_NODE_REGISTRY["node3090"]["hostname"]` ·
`_augment_context_with_kb()` returning `PINNED GROUND TRUTH` **and** the new
mixin map · `_consume_time_banner()` end-to-end across the mixin boundary ·
`test_planner_ledger.py` monkeypatch-by-name under the new MRO ·
`test_safety_gates_adversarial.py` unchanged after `_active_download_guard`
moved out from under `_validate_command_safety` · mirror guard in both failure
modes.

**Verified only by import + existing suite:** the network- and hardware-facing
bodies — `ssh_run`/`ssh_script`/`nmap_summary`, `wake_node`/`shutdown_node`
(need live nodes), live LLM backend calls, and
`search_web`/`fetch_url`/`monitor_download` (hit SearxNG, Reddit, Firecrawl).
These were exercised at "resolves via MRO and is callable", not at "actually
talks to node3090". Coverage of these paths is neither better nor worse than
before D7 — the code moved unchanged.

This distinction is itself a D4 lesson: a green suite proves absence of
regression **in covered paths only**. Stating which is which is part of the
deliverable.

---

## 7. Anti-goals held

- Safety wedge never extracted — `execute_command`, `write_file`, `read_file`,
  `sudo_delegation_block`, `_validate_command_safety`, `_is_allowed_*`, `_norm`
  all remain on `Tools`, byte-unchanged since D5.
- No method body, signature, or docstring edited during any move — every
  extraction AST-diffed byte-identical against source before deletion.
- The four D5 xfail holes untouched (10 xfailed, constant across all commits).
- No mixin imports `goethe.py`; import direction one-way throughout.
- No step proceeded while an invariant was red.

---

## 8. Commit index

`b2fe3b4` D2 · `403f75a` D8 · `7fdba10` D3 · `766182a` D4 ·
`e271ff0` `3496137` `1a07c94` D6 · `5dceaff` search_rfc · `feb7911` D5 ·
`23f73f9` D7 plan · `10b6b50` `dd315c4` `a841ad5` `ec0ee9a` `6165317` D7 ·
`2fd3acc` final verification · plus D1 and supporting infrastructure commits.

Ledger: D1 `8e55bde2` · D2 `edb8aa94` · D3 `fd19ffaf` · D4 `6ed8ef46` ·
D6 `f0b3d98a` · D8 `5d864176` — all `done`. `23c00a76` `abandoned`
(duplicate). D5 and D7 were executed directly without ledger blocks.
