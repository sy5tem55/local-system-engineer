# SPEC-rule-prefix-guards-2026-08 — implementation report

Commit: `0b82034` (branch `codex/fix-sudo-grants-live`). Design: Opus 5,
2026-08-11. Implementation: Sonnet 5 High, 2026-08-11/12.

## 1. What shipped

Four additive characterization tests in `tests/test_diagnosis_rules.py`
(numbered T-9 through T-12 in the file, in their own classes; tests 1-8
untouched), plus two documentation corrections. No behaviour change
anywhere — `repeat_prior()`, R2, R3, and their thresholds are byte-for-byte
what they were before this change (proven in §5 below, not just asserted).

- **T-9** (`TestRealisticRefirePath`) — the realistic re-fire path.
  `apply_diagnosis_rules` runs on all three consecutive reworded redrafts of
  the same third-party-URL diagnosis (unlike test 3, which deliberately
  skips it to isolate `repeat_prior()` alone). All three land
  `SYSTEM_REJECTED`, never `STAGED`/`PENDING`, reason keeps the
  `rule:third_party_resource_error:` prefix every time, and three distinct
  rows exist in `proposals` — row churn is not closed, only kept off the
  human queue.
- **T-10** (`TestUnhonoredPrefixIsNotHonored`) — the negative control. Same
  structure as test 3, but the first proposal's reason is minted
  `rulex:third_party_resource_error:example.com` — one character off the
  honored set. The redraft reaches `PENDING`. This is what makes test 3
  meaningful: it shows the *prefix string*, not the surrounding machinery,
  is what `repeat_prior()` keys on.
- **T-11** (`TestR3RejectionIsAbsorbing`) — an R3 rejection is an absorbing
  state. Run 1: `resolution` byte-identical to `error_text` (Hazard B:
  forced cosine of exactly `1.0000`, not tuned prose) → R3 fires,
  `SYSTEM_REJECTED`. Run 2: same narrow identity, genuinely informative
  `resolution` sharing no vocabulary with `error_text` → R3 stays silent,
  but the redraft is still `SUPERSEDED` against the run-1 row. Carries the
  Hazard A comment: this characterizes the behavior, it does not endorse
  it, and names what would justify changing it (excluding `rule:` from the
  honored set, or adding `resolution` to the narrow fingerprint — both
  explicit anti-goals here).
- **T-12** (`TestFingerprintIgnoresWhatR3Judges`) — the mechanism behind
  T-11, isolated to two calls, no store or run. Two proposals identical
  except `resolution` produce the same `proposal_fingerprint()` (narrow
  identity ignores `resolution`) while `rule_r3_resolution_redundant()`
  returns a verdict for one and `None` for the other.
- **D-1** — `rule_r3_resolution_redundant`'s docstring
  (`tools/diagnosis_rules.py`) now states it judges `resolution`, which is
  not part of `_NARROW_IDENTITY_ARG_KEYS`, and that its rejection therefore
  binds an identity computed from fields it never read. Cross-references
  T-11/T-12.
- **D-2** — `docs/reports/2026-08-11-auto-adjudication.md` §4's acceptance
  paragraph named the wrong Hazard C pair as evidence (*Permission denied*
  vs *Connection timed out* instead of the spec-named *Permission denied*
  vs **No route to host**). Corrected in place: named the actual row
  (`prp_237da5f542`, `APPLIED`, used by R1 as a prior) and its measured
  cosine against `prp_c6fbb0a811` (**0.6555**, well under the R1=0.92
  threshold) — the acceptance verdict itself (stays separate) was already
  correct; only the cited evidence was substituted.

## 2. §2 ground-truth table — nothing was wrong

Every row in the spec's §2 table was independently re-probed against the
live repo before writing anything, per "verify, don't trust":

- Honored reason prefixes at `traum_state.py:862-871` — confirmed exactly
  (`malformed:`, `noop:`, `invariant:`, `rule:`, with the `rule:` entry on
  line 871).
- The `SUPERSEDED` branch's `initial_state in {"STAGED", "PENDING"}` guard
  at `traum_state.py:936` — confirmed exactly.
- `_NARROW_IDENTITY_TYPES`/`_NARROW_IDENTITY_ARG_KEYS` at
  `traum_state.py:239-240` — confirmed exactly.
- `rule_r3_resolution_redundant` at `diagnosis_rules.py:162` and
  `RULE_REASON_PREFIX` at `diagnosis_rules.py:56` — both confirmed exactly.
- Test helper line numbers (`_fake_embed:57`, `_cfg:69`, `_diagnosis:80`,
  `_store:137`, `_record_one:141`) — all confirmed exactly via `grep -n`.
- Test count: `pytest tests/test_diagnosis_rules.py --collect-only -q`
  reported **15** before this change, exactly as the table claimed.
- Suite baseline: reproduced exclusively (verified `pgrep -af '[p]ytest'`
  empty first) at **874 passed, 0 skipped**, exactly as the table claimed.
- The "22 pre-existing errors" figure: `ruff check` restricted to whole
  repo (`ruff check .`) reports 232, *not* 22 — but the spec's own
  precedent (`docs/reports/2026-08-11-auto-adjudication.md` §9) scopes that
  number to the same 5 files this work touches
  (`tools/traum_state.py tools/dream_runner.py tools/diagnosis_rules.py
  scripts/dry-run-diagnosis-rules.py tests/test_diagnosis_rules.py`), and
  restricted to that set it is exactly 22. Not a table error once matched
  to that scope — flagged here only because "repo-wide" is a
  misleading label for it and a future reader running bare `ruff check .`
  will otherwise think something regressed.

No other discrepancy found.

## 3. Break / red / restore (spec §6)

`"rule:"` removed from the honored tuple at `traum_state.py:871` via a
targeted Python edit (verified unique match, verified the removed line
number was 871 before proceeding):

```
removed line 871: '                        "rule:",\n'
```

`pytest tests/test_diagnosis_rules.py -v` (exclusive access confirmed via
`pgrep -af '[p]ytest'` empty beforehand) — verbatim failure output:

```
tests/test_diagnosis_rules.py::TestRuleRejectedProposalNotRedrafted::test_3_r2_rejected_proposal_stays_rejected_on_redraft FAILED [ 15%]
tests/test_diagnosis_rules.py::TestUnhonoredPrefixIsNotHonored::test_10_unhonored_prefix_lets_redraft_reach_pending PASSED [ 89%]
tests/test_diagnosis_rules.py::TestR3RejectionIsAbsorbing::test_11_r3_rejected_then_genuinely_improved_redraft_is_superseded FAILED [ 94%]

=================================== FAILURES ===================================
_ TestRuleRejectedProposalNotRedrafted.test_3_r2_rejected_proposal_stays_rejected_on_redraft _
...
        [second] = store.record_proposals(run["run_id"], second_attempt["attempt_id"], [redraft])
>       assert second["state"] not in ("STAGED", "PENDING"), second
E       AssertionError: {'proposal_id': 'prp_a5499a48beff47fda7c7fa070d750f90', 'fingerprint': 'b39ccb1d0213e8465f9ecb11ff4d1533d918c2cdc1026cfe0ca346d66470f43c', 'run_id': 'run_a2d398ba693948c3b2993d320a770a56', 'attempt_id': 'att_832c10faee6c42b3b509d5eed2f9ffaa', ...}
E       assert 'STAGED' not in ('STAGED', 'PENDING')

tests/test_diagnosis_rules.py:254: AssertionError
_ TestR3RejectionIsAbsorbing.test_11_r3_rejected_then_genuinely_improved_redraft_is_superseded _
...
        ))
>       assert second["state"] == "SUPERSEDED", second
E       AssertionError: {'proposal_id': 'prp_866b28b082654e8b8821477040d6d1c3', 'fingerprint': '4a4a7516a1f49a827f4cbec02fa4fe013be3424b0a83252b107f80a0280959f0', 'run_id': 'run_9d6f82ba085e45a98ead229f325bda97', 'attempt_id': 'att_f8f6635379504ccb953d7488191d1086', ...}
E       assert 'PENDING' == 'SUPERSEDED'
E
E         - SUPERSEDED
E         + PENDING

tests/test_diagnosis_rules.py:557: AssertionError
========================= short test summary info ============================
FAILED tests/test_diagnosis_rules.py::TestRuleRejectedProposalNotRedrafted::test_3_r2_rejected_proposal_stays_rejected_on_redraft
FAILED tests/test_diagnosis_rules.py::TestR3RejectionIsAbsorbing::test_11_r3_rejected_then_genuinely_improved_redraft_is_superseded
========================= 2 failed, 17 passed in 2.87s =========================
```

All three load-bearing lines from spec §6 held exactly: test 3 → red, T-11
→ red, T-10 → green (the control — an unhonored prefix, so removing another
prefix from the set cannot change its outcome).

**Restore.** The `"rule:"` entry was re-inserted immediately after the
Hazard B comment block (its original position).

```
sha256sum tools/traum_state.py
before-break and after-restore:
d41d46af96b96e288bd8a3cde3be3dd45435449a4f212d89988e717aaa168d76
d41d46af96b96e288bd8a3cde3be3dd45435449a4f212d89988e717aaa168d76
```

Byte-identical — not "tests pass again," the file content itself matches.
`pytest tests/test_diagnosis_rules.py -q` after restore: `19 passed in
2.91s`.

## 4. Invariants

```
/home/sy5/owui/bin/python3 -m py_compile tools/traum_state.py tools/diagnosis_rules.py tests/test_diagnosis_rules.py
# -> clean

/home/sy5/miniforge3/bin/ruff check tests/test_diagnosis_rules.py tools/diagnosis_rules.py
# before: All checks passed! (0 errors)
# after:  All checks passed! (0 errors)

/home/sy5/miniforge3/bin/ruff check tools/traum_state.py tools/dream_runner.py tools/diagnosis_rules.py scripts/dry-run-diagnosis-rules.py tests/test_diagnosis_rules.py
# before: 22 errors
# after:  22 errors (unchanged -- same pre-existing set in traum_state.py/dream_runner.py)

pgrep -af '[p]ytest'   # empty before every exclusive run
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
# baseline (before this change): 874 passed, 0 skipped, 126.42s
# after (with this change):      878 passed, 0 skipped, 127.05s
```

`--collect-only -q` on `tests/test_diagnosis_rules.py`: **15 → 19**, four
new test functions, none parametrized — the full-suite delta (874→878) is
fully attributable to this file alone.

## 5. Anti-goals honored

`repeat_prior()`'s honored set, R2, R3, and their thresholds
(`DIAGNOSIS_DUP_THRESHOLD_DEFAULT`, `DIAGNOSIS_REDUNDANT_THRESHOLD_DEFAULT`)
are unmodified outside the break/restore cycle in §3, which round-tripped
back to a byte-identical file. `_NARROW_IDENTITY_ARG_KEYS` unmodified —
`resolution` was not added to it. Tests 1-8 unmodified, unrenamed, not
absorbed into the new tests. No test opened
`/opt/local-se/dreams/traum-state.db`; every new test uses `tmp_path` (T-12
uses no store at all). The backfill question and the 16 live `PENDING` rows
were not touched. The dry-run script was not re-run or re-calibrated.

## 6. Not pushed

Per AGENTS.md §5, implementers commit and the operator pushes. This work is
committed (`0b82034`) on `codex/fix-sudo-grants-live` and not pushed.

<!-- ACCEPTANCE
task: rule-prefix-guards
commit: 0b82034
tests_before: 874
tests_after: 878
tests_in_file_before: 15
tests_in_file_after: 19
files_changed: tests/test_diagnosis_rules.py, tools/diagnosis_rules.py, docs/reports/2026-08-11-auto-adjudication.md, docs/SPEC-rule-prefix-guards-2026-08.md
ruff_clean: tests/test_diagnosis_rules.py, tools/diagnosis_rules.py
ruff_baseline_5file_scope: 22 (unchanged before/after)
break_red_restore: verified (test 3 red, T-11 red, T-10 green as control; sha256 restore proof identical)
ground_truth_table_errors_found: none
behaviour_change: none
pushed: false
-->
