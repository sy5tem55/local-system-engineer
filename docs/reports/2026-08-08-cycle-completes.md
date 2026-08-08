# TRAUM dream report — let a cycle finish (SPEC-cycle-completes-2026-08)

Implementer: Sonnet 5 (Cowork), 2026-08-08. Branch `codex/fix-sudo-grants-live`,
starting HEAD `6cf69a1`. Commit only — not pushed, per operator instruction.

---

## 1. What changed

### Defect 1 — error-cluster's envelope key contract (`tools/dream_runner.py`)

`parse_dream_envelope()` gained an opt-in `keys: tuple[str, ...] | None = None`
parameter. When given, it replaces the single-`key` check with an OR contract:
the envelope is accepted if it carries **any** of `keys` as a list (each may be
empty) — Hazard A: validating only one of `diagnoses`/`skill_candidates` would
silently drop the other. `key=` (default `"proposals"`) is completely
unchanged when `keys=` is not passed.

`request_dream_envelope()` forwards `keys` the same way, and the corrective
retry message now names all of `keys` (not just one) when the multi-key form
is in use, so the model sees the same envelope shape it was asked for the
first time.

`_draft_error_cluster_proposals()` is the **only** call site that now passes
`keys=("diagnoses", "skill_candidates")` — opt-in at the call site per Hazard
B. `demote` (stale-contradiction), `dedup`, and `insights` still call with the
plain single-`key` default, unchanged.

Unterminated `<think>` handling (§5/§8 item 4, minor) was added to the same
function: an opening `<think>` that survives the existing strip (i.e. never
got a matching `</think>`) is now named explicitly in the failure message
("reply truncated mid-`<think>` block...") instead of falling through to the
generic "no JSON object in reply", and only the text before the truncation
point is searched for a candidate envelope.

`_build_payload()` gained `"chat_template_kwargs": {"enable_thinking": False}`,
added **additively** next to the existing `/no_think` suffix and
`thinking_budget_tokens: 0` (per-request only — no llama-server flag or node
profile touched, Hazard F).

### Defect 2 — per-pass wall-clock allocation (`tools/run-dream-cycle.sh`)

The pass loop no longer hands every pass the *entire* remaining cycle budget.
Each pass now gets `remaining_seconds / passes_left`, floored at
`GOETHE_DREAM_PASS_FLOOR_S` (default 60s, matching Hazard C's
`timeout --signal=TERM --kill-after=10s`, which is unchanged), and never
inflated above what is genuinely left for the last pass. Because
`remaining_seconds` is recomputed from the wall clock at the top of every
iteration (not decremented by an a-priori allocation), an early finisher's
unused time automatically returns to the pool for the next pass. Digest is
deliberately **outside** this loop and still takes whatever is left, per
spec §8 item 2 — unchanged.

### Defect 3 — budget exhaustion is a deliberate stop, not a dependency failure (`tools/dream_runner.py`)

The pass-level outcome computation in `main()` no longer special-cases
`cfg.budget.truncated` into `"BLOCKED"`. It now uses the *same*
`null_record`-based read as every other outcome:
`outcome = "NULL" if null_record is not None else "SUCCEEDED"`. The
`DependencyBlocked("budget", ...)` construction at the `finish_attempt()`
call site is removed (`error=None` on truncation); `exit_code` stays `3` on
truncation as a process-level signal, orthogonal to `outcome`/`error_type`.
The truncation reason is now carried into the attempt `summary` dict as
`"budget_truncation_reason"` so the operator still sees it stopped early and
why, even though the state no longer reads as breakage.
`_raise_if_dependency_blocked` and `ccbe879`'s sub-pass work are untouched
(Hazard E) — a **real** dependency failure (dreamer unavailable, KB
unreachable, etc.) still raises `DependencyBlocked` and is still recorded
`BLOCKED` via the separate `except DependencyBlocked` handler, unchanged
(Hazard D).

### §8 item 5 — test PATH (`tests/conftest.py`, new file)

`~/.local/bin` (where the `node` symlink lives on this host) was absent from
pytest's inherited `PATH`, so `test_ui_router.py`'s real `node --check`
syntax test (SPEC test 7/12) was skipping instead of running. A new
`tests/conftest.py` prepends it to `os.environ["PATH"]` once at collection
time. Verified: `node --version` via that PATH resolves to `v22.22.3` (spec's
ground-truth claim was accurate), and the previously-skipping test now runs
and passes.

### Incidental fix — 5 pre-existing test fixtures (`tests/test_diagnosis_proposal_type.py`)

Five `fake_envelope(system_prompt, user_content, cfg)` monkeypatch fixtures
broke the moment `_draft_error_cluster_proposals` started calling
`request_dream_envelope(..., keys=(...))` — they had fixed 3-parameter
signatures with no `**kwargs`. Widened to
`fake_envelope(system_prompt, user_content, cfg, **_kwargs)`; no assertions
changed. This was a real regression introduced by the Defect 1 fix, caught
by the full-suite run, and is fixed here rather than left for a later pass.

---

## 2. Before / after

| | ruff (`tools/dream_runner.py`) | pytest (`tests/`) |
|---|---|---|
| Before | 18 errors | 806 passed, 1 skipped (807 total) |
| After | **18 errors (unchanged)** | **828 passed, 0 skipped (828 total)** |

828 = 807 (baseline total) + 21 new tests in `tests/test_cycle_completes.py`,
with the one previously-skipping test now passing (item 5) and zero
regressions elsewhere. `py_compile tools/dream_runner.py` and
`bash -n tools/run-dream-cycle.sh` both clean.

21 new tests cover spec §10 items 1–5 (envelope contract, including a
call-site regression guard and an end-to-end `_draft_error_cluster_proposals`
check), 6–7 (wall-clock share/floor, executed against the **actual shipped**
formula extracted from `run-dream-cycle.sh`, not a reimplementation), 8–9
(budget reclassification and the real-dependency non-regression, both through
a real `dr.main()` + real `TraumState` round trip — same fault-injection
pattern as `test_dream_crash_discipline.py`), and 10–11 (payload hardening,
unterminated `<think>`). Item 12 (JS syntax check running, not skipping) is
covered by the existing `test_ui_router.py` test now passing under the new
conftest, not duplicated.

**Break/red/restore, as required (§10, "confirm red, restore"):** tests 1,
6, and 8 were each broken by reverting the corresponding fix in isolation,
confirmed red, then restored from a pre-break snapshot with `diff -q`
proving a byte-identical restore. Full failure text for each:

- **Test 1 (envelope):** reverting the multi-key OR branch back to the
  original single-key check failed 5 tests, e.g.
  `AssertionError: DREAMER OUTPUT UNPARSEABLE — envelope has no 'proposals'
  array (after retry).`
- **Test 6 (wall clock):** reverting the loop to the original
  whole-remaining-budget form failed 4 tests with
  `AssertionError: budget-share formula block not found in run-dream-cycle.sh`
  (the test's own formula-extraction regex correctly stopped matching once
  the real formula was gone).
- **Test 8 (budget reclassification):** reverting `outcome`/`error` back to
  `"BLOCKED" if cfg.budget.truncated ... DependencyBlocked("budget", ...)`
  failed 2 tests: `AssertionError: assert 'BLOCKED' == 'NULL'`.

All three restores were verified `diff`-clean against the fully-patched file
before continuing.

---

## 3. Ground truth — what the spec got right, what it didn't

Re-probed per §6's own instruction ("verify, don't trust... three facts in
the previous spec's table were overtaken within twelve hours"):

**Confirmed exactly correct:** error-cluster prompt keys and their line
(`dream_runner.py:2048`); the no-`key=` envelope call
(`dream_runner.py:2091`); the two consumers
(`dream_runner.py:2099`, `2128`); insights' correct comparator
(`dream_runner.py:3533`); the budget stop prefix and its check line
(`dream_runner.py:1564`); the cycle budget line
(`run-dream-cycle.sh:100`, exact); `GOETHE_DREAM_CYCLE_MAX_SECONDS` default
2700; the pass order (dedup, stale-contradiction, error-cluster, patterns,
insights, **then digest** — digest is confirmed structurally separate from
the `passes[]` array/loop, exactly as the table implies); the suite baseline
(806 passed, 1 skipped, exact); and the node-skip root cause, including the
specific claim "node v22.22.3 IS installed" (confirmed via
`~/.local/bin/node --version`).

**Wrong or imprecise, worth flagging:**

1. **§6 table, "Envelope parser" row.** States
   `dream_runner.py:1511 parse_dream_envelope(reply, key=...)`. Line 1511
   (pre-patch) falls inside the function's docstring, not on a
   `parse_dream_envelope(reply, key=...)` call. The function definition
   itself is at line 1499 (pre-patch); the actual internal call
   `parse_dream_envelope(reply, key=key)` is at line 1575 (pre-patch). Not
   load-bearing for the fix, but the line pointer as written doesn't resolve
   to what the row describes.

2. **Hazard B text** ("Four other callers rely on strict single-key
   validation") is off by one and outside §6 proper, but worth flagging
   under the same verify-don't-trust discipline: `request_dream_envelope` has
   exactly **four** call sites total (`demote` at 1854, `error-cluster` at
   2091, `dedup` at 2241, `insights` at 3533) — so **three**, not four,
   *other* callers remain on the strict single-key default after
   error-cluster opts in. The `patterns` pass never calls the LLM at all
   (confirmed at `dream_runner.py:2311`'s comment and by grep), so it was
   never a fifth candidate either. Immaterial to the fix (Hazard B's actual
   constraint — don't change the shared default — was honoured regardless of
   the exact count), but the arithmetic in the spec doesn't add up against
   the code as it stands today.

---

## 4. Live cycle run — V3, partial

Per §12, a real standard cycle was run (not `--dry-run`) against the live
production paths: `/opt/local-se/dreams` / `/opt/local-se/episodes`,
`traum-state.db`, real Elasticsearch (`http://127.0.0.1:9200`, status
`yellow`, reachable), and the real node3090 dreamer (already serving a
different profile than the dreamer's own — see below — but healthy and
reachable, so the cascade used it as intended). Launched directly
(`bash tools/run-dream-cycle.sh`) with the same environment the
`goethe-dream.service` unit sets, **run ID `run_20260808T070930Z_1436902`**,
started 07:09:30Z. Verbatim log as observed through 07:30Z kept at
`docs/reports/2026-08-08-cycle-completes.traum-cycle.log` next to this
report; the underlying process (PID 1436902, launched via `nohup ... &
disown`) was left running independently of this session and may have
progressed further by the time this is read — check
`run_20260808T070930Z_1436902` in `traum-state.db` for the true final state.

**Result as observed through this report's cutoff (07:30Z, ~21 minutes into
the 45-minute budget): 3 of 6 passes attempted (dedup, stale-contradiction,
error-cluster), all three BLOCKED before doing any pass-specific work; the
run had not reached patterns/insights/digest or produced a diagnosis
proposal by cutoff.** Reporting this plainly, per §12 ("if the cycle still
cannot finish, say so plainly and report what consumed it. A partial result
honestly reported beats a green suite.") — and per the operator's own
verify-don't-trust discipline (§5 of the workflow doc: "an inference is not
a measurement").

**What actually consumed it, measured, not guessed:** the
recent-session-activity guard (`dream_runner.py`'s
`_recent_session_active`, explicitly **untouched** here per the spec's own
anti-goals) blocked `dedup` after 535s across 2 retries
(`session 'sess-1462919-...' was active 0.4 min ago`), then `stale-
contradiction` the same way after 536s, then `error-cluster` began the same
450s first-retry wait, each time against a **new** session id. Each new
session id in that log line corresponds to one of *this verifying agent's
own* `mcp__goethe__execute_command` calls against LUCIFER while checking on
the run's progress — the same channel this implementation was done through
is indexed as session activity by the very guard being verified around.
Every status check this thread made to observe the cycle therefore reset
the 30-minute quiet window the guard requires, for every subsequent pass,
for as long as the thread kept checking. This thread deliberately stopped
polling after 3 passes' worth of this pattern (rather than continuing to
perturb the system for the full 45 minutes) once the wall-clock-allocation
formula had been confirmed live across three independent pass transitions.

This is a real, structural limitation of verifying a same-host,
activity-gated background job from an agent that has no channel to observe
it *without* generating activity on that same host — not a defect in any of
the three things this spec asked to fix, and explicitly out of scope to fix
(anti-goal: "do not touch the session-activity guard, its retry arithmetic").
It is being reported because it is the honest answer to "did the cycle
finish", not because it's part of the deliverable.

**What the partial run DID prove, live, about the actual defects:**

- **Defect 2 (wall-clock allocation) — confirmed live across THREE
  consecutive pass transitions, exactly matching the formula every time:**
  `dedup` started with `budget 540s of 2700s remaining, 5 pass(es) left`
  (2700÷5=540, exact). `stale-contradiction` then started with
  `budget 541s of 2164s remaining, 4 pass(es) left` (2164÷4=541, exact).
  `error-cluster` then started with `budget 542s of 1628s remaining,
  3 pass(es) left` (1628÷3=542.67→542, exact, floor division). Each is a
  genuinely different, freshly wall-clock-derived share, not the whole
  remaining cycle — this is the defect measured as broken in spec §3
  (every pass used to get handed the *entire* remaining budget); here it
  visibly did not, three times in a row, on the real production script.
- **Defect 3 scope discipline (Hazard D) — confirmed live, by a negative
  result:** all three guard blocks (`dedup`, `stale-contradiction`,
  `error-cluster`) are a **real** dependency condition
  (recent-session-activity), not a budget exhaustion. Each was correctly
  recorded `BLOCKED` (`rc=3`, `"pass ended non-successfully: <pass>"`), i.e.
  the reclassification fix did **not** leak into a real block — proving the
  narrow scope (Hazard D: "only the budget-exhaustion path changes") holds
  under a live, non-synthetic dependency failure, not just in the mocked
  regression test.
- **Defect 1 (error-cluster envelope)** was not exercised live — `error-
  cluster` was reached and started (visible as a `RUNNING` attempt in
  `traum-state.db`, budget correctly allocated per above), but the guard
  blocks a pass before any pass-specific work — including the first
  `call_dream_llm`/`request_dream_envelope` call — so the envelope-key code
  path itself was never reached this session. It is exercised, including the
  exact production prompt/parse path, by `test_cycle_completes.py`'s
  `test_draft_error_cluster_proposals_stages_a_diagnosis_only_reply` and the
  four envelope-contract tests, all passing, plus the break/red/restore
  above.

**Runtime-proven vs. test-only, stated explicitly per WORKFLOW §5:**
Defect 2 is runtime-proven (live log evidence above). Defect 3's outcome
reclassification is test-only for the SUCCEEDED/NULL paths (proven via a
real `dr.main()` + real `TraumState` db in the test suite, not via the live
run, which only reached a real-BLOCKED case); its narrow-scope claim (Hazard
D) is both test-proven and live-proven (the negative result above). Defect 1
is test-only. The spec's top-line acceptance claim — "all six passes
attempted, and at least one diagnosis proposal reaching the Human Gate" — is
**not proven this session**; the goethe-dream.timer's regularly scheduled
run (next trigger the following night) will be the next opportunity to
observe it without an actively-polling verifier competing for the same quiet
window, and is the recommended way to close this out at V3.

---

## 5. Files changed

- `tools/dream_runner.py` — Defects 1 & 3, plus §5/§8 item 4 hardening.
- `tools/run-dream-cycle.sh` — Defect 2.
- `tests/conftest.py` (new) — §8 item 5.
- `tests/test_cycle_completes.py` (new) — spec §10 tests.
- `tests/test_diagnosis_proposal_type.py` — 5-fixture regression fix caused
  by Defect 1's call-site signature change.

`tools/voicebox-tts-proxy.py` remains untracked in the working tree; it
predates this session and was not touched or committed.

---

<!-- ACCEPTANCE
task: cycle-completes
commit: 5612f59ecd7c31f94024fd61450ab5f620ded701
tests_before: 806 passed, 1 skipped (807 total)
tests_after: 828 passed, 0 skipped (828 total)
files_changed: tools/dream_runner.py, tools/run-dream-cycle.sh, tests/conftest.py, tests/test_cycle_completes.py, tests/test_diagnosis_proposal_type.py
ruff_clean: tests/conftest.py, tests/test_cycle_completes.py, tests/test_diagnosis_proposal_type.py
runtime_verified: partial
-->
