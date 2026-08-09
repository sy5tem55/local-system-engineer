# SPEC — stop spending the Human Gate on things already known

> Design: Opus 5, 2026-08-09. Implementation: Sonnet 5 High. Verification: V2,
> one V3 claim (§9). Both defects are consequences of earlier reviews by this
> author; §2's hazard reasoning in SPEC-subpass-outcomes was already found
> wrong once, so treat §5 as claims to re-probe, not facts.

Two defects from `run_e5b5132c` (2026-08-09T05:46, DEGRADED 5/6). Small,
independent, same file.

---

## 1. Defect 1 — a blocked pass throws away the telemetry explaining why

`ccbe879` gave `run_pass_insights` per-domain `sub_passes` so a partial
failure would be legible. It is attached to the attempt summary at
`dream_runner.py:4875`, on the success path only.

When the pass is blocked, `dream_runner.py:4961` runs instead:

```python
except DependencyBlocked as exc:
    ...
    state.finish_attempt(
        cfg.attempt_id, "BLOCKED", summary={"dependency": exc.dependency},
        artifacts={...}, error=exc, exit_code=3,
    )
```

The whole summary for the 05:46 insights attempt is therefore:

```json
{"dependency": "dream-llm"}
```

Four domains ran. Which one lost the dreamer is not recorded anywhere the
Console can reach. The narrative says *"20 session summary(ies) considered
across 4 domain(s); 0 insight(s) accepted total"* — so we cannot distinguish
**all four looked and found nothing** (a `NULL`) from **one could not look**
(a `BLOCKED`). That is the exact NULL/BLOCKED ambiguity R4 was reframed to
fix, resurfacing one level down, in the case that matters most.

`SPEC-subpass-outcomes-2026-08` Hazard B says the failure "has to remain
visible in the summary". On the blocked path it does not.

**Care required:** `sub_passes` is bound inside the `try`. If the pass
function itself raised, the name is unbound and referencing it in the
`except` is a `NameError` that would convert a clean BLOCKED into a crash.
Initialise before the `try`.

---

## 2. Defect 2 — the same diagnoses are re-proposed every run

Fourteen `diagnosis` proposals across three runs, **every one with a distinct
fingerprint**, so nothing dedupes them. Five are sitting `PENDING r2` right
now, and the Console's apply-preview correctly labels all five `DUPLICATE`.

The data is not corrupted — `lse-errors-1024` holds 67 docs with zero
repeated `error_text`; it went 62 → 67 across nine applies, so four merged at
write time. Write-time dedup works. **What is being consumed is the Human
Gate**, which is the scarce resource this entire loop exists to feed, and the
cost grows with every recurring error class.

### The machinery already exists

`traum_state.py:804` `repeat_prior()` already looks up a fingerprint and
auto-supersedes a repeat, explicitly including `APPLIED` priors. Nothing new
needs building. It never fires for diagnoses because of what gets hashed:

```python
_IDENTITY_IGNORED_KEYS = {"proposal_id", "run_id", "attempt_id", "revision",
                          "state", "created_at", "updated_at",
                          "expected_target_token"}
canonical_proposal = {k: v for k, v in proposal.items()
                      if k not in _IDENTITY_IGNORED_KEYS}
```

Everything else is hashed — including `args.interpretation`,
`args.resolution`, `args.anti_response`, `why` (all model prose, reworded
every run) and `evidence` (a list of session keys that **grows** as new
episodes join the cluster). A fresh fingerprint every run is guaranteed by
construction.

### The stable identity of a diagnosis

`error_text` + `context` — the failure signature and what was being attempted.
Both are derived from the cluster, not invented by the model, and they are
what `record_error` keys on. Fingerprinting a diagnosis over
`{type, call, args.error_text, args.context}` makes a reworded re-draft
collide with the applied original, and `repeat_prior` supersedes it before it
reaches the gate.

---

## 3. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Blocked-path close | `dream_runner.py:4961-4972` — `state.finish_attempt(..., summary={"dependency": exc.dependency})`. **Not** `_finish_attempt_best_effort` |
| Success-path summary | `dream_runner.py:4875` — `**({"sub_passes": sub_passes} if sub_passes else {})` |
| `sub_passes` binding | assigned ~`dream_runner.py:4781`, inside the `try` |
| Fingerprint | `traum_state.py:217 proposal_fingerprint` over `canonical_proposal` (`:212`) |
| Ignored keys | `traum_state.py:206 _IDENTITY_IGNORED_KEYS` (8 keys) |
| Existing supersede path | `traum_state.py:804 repeat_prior()` — already covers `APPLIED` |
| Live diagnosis payload | `type`, `call="record_error"`, `evidence[]`, `why`, `args{error_text, context, interpretation, resolution, anti_response}` |
| Live counts | 14 diagnoses / 3 runs / 14 distinct fingerprints; `lse-errors-1024` = 67 docs, 0 repeated `error_text` |
| Suite baseline | **843 passed, 0 skipped** |

Re-probe all of it. Two rows of the previous spec's ground-truth table were
wrong, and one of its hazards named the wrong mechanism.

---

## 4. Hazards

### Hazard A — a narrower fingerprint suppresses genuine improvements
Once identity is `error_text` + `context`, a *better* second draft — richer
interpretation, an `anti_response` the first lacked — is also suppressed as a
repeat. That is the cost of the fix and it must be deliberate, not accidental.
The superseded row must record which prior it collided with, so the operator
can find the original rather than wondering where the proposal went.

### Hazard B — do not change dedup for the other proposal types
`dedup`, `demote`, `reverify`, `kb-fact`, `prompt-rule` fingerprint correctly
today. Scope the identity change to `diagnosis` (and `skill-candidate`, which
has the same shape and will hit this the moment error-cluster emits one
again). A global change to `_IDENTITY_IGNORED_KEYS` is the wrong fix and will
break pair-atomicity for `dedup`.

### Hazard C — `repeat_prior` also matches `REJECTED`
A diagnosis the operator rejected will, after this change, never be re-offered
even if a later run drafts a materially better one. Decide this deliberately
and say which you chose in the report. Defensible either way; silently
inheriting it is not.

### Hazard D — `sub_passes` may be unbound in the `except`
See §1. Initialise before the `try` or a blocked pass becomes a `NameError`.

### Hazard E — do not touch the guard itself
`_raise_if_dependency_blocked` is correct. This spec changes what is
*recorded* when it raises, not when it raises.

### Hazard F — this is not the write-time dedup
`record_error` already merges duplicates into `lse-errors-1024`, and that is
working (67 docs, 0 repeats). Do not "fix" it. The defect is upstream, at the
gate.

---

## 5. What to implement

1. **Carry `sub_passes` into the blocked summary.** Initialise
   `sub_passes = None` before the `try`; include it in the `except
   DependencyBlocked` summary when bound, alongside `dependency`.
2. **Give diagnosis proposals a stable identity.** Fingerprint over
   `{type, call, args.error_text, args.context}` rather than the full body.
   Scope to `diagnosis` and `skill-candidate` (Hazard B). Keep the change in
   `traum_state.py` next to `canonical_proposal`, not scattered at call sites.
3. **Make the supersede legible.** When a repeat is superseded, the reason
   must name the prior `proposal_id` and its state, so the Console can say
   "already applied as prp_… " rather than silently dropping it.

---

## 6. Anti-goals

- Do **not** widen `_IDENTITY_IGNORED_KEYS` globally.
- Do **not** modify `record_error`'s write-time dedup.
- Do **not** change `_raise_if_dependency_blocked`'s raise conditions.
- Do **not** add a new proposal state; `SUPERSEDED` already exists.
- Do **not** suppress a diagnosis by skipping the LLM call — the cluster must
  still be examined, so that a genuinely new failure mode in the same cluster
  is still found.

---

## 7. Tests

1. A blocked pass with `sub_passes` bound records them in the attempt summary
   alongside `dependency`. **Load-bearing.**
2. A blocked pass where the pass function itself raised (so `sub_passes` is
   unbound) still records `BLOCKED` cleanly, no `NameError`.
   **Load-bearing — Hazard D.**
3. Two diagnosis proposals with identical `error_text` + `context` but
   different `interpretation`, `why` and `evidence` produce the **same**
   fingerprint. **Load-bearing.**
4. Two diagnosis proposals differing in `error_text` produce different
   fingerprints.
5. A diagnosis whose fingerprint matches an `APPLIED` prior is superseded, not
   left `PENDING`, and its reason names the prior id. **Load-bearing.**
6. `dedup`, `demote`, `reverify` and `kb-fact` fingerprints are byte-identical
   to today's for the same payloads. **Load-bearing — Hazard B.**
7. Pair atomicity for `dedup` still holds.

**Break tests 3 and 6, confirm red, restore.** Report the exact failure text
and prove the restore with a diff.

---

## 8. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/traum_state.py
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/traum_state.py
pgrep -af pytest          # MUST be empty before the next line
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **843 passed, 0 skipped**. Pre-existing ruff on those two files is
**36 combined with traum_controller.py**; it must not increase.

`tests/test_kb_contracts.py` is an Elasticsearch integration suite. A count
taken while another pytest run is live is meaningless — check `pgrep` first.

---

## 9. Verification — V2, plus one V3 claim

**V3:** run a manual cycle and show, verbatim, that the five known diagnoses
do **not** reappear as `PENDING`. Query:

```sql
SELECT proposal_type, state, COUNT(*) FROM proposals
WHERE created_at >= '<run start>' GROUP BY 1,2;
```

Acceptance: no new `PENDING` diagnosis whose `error_text` already exists in
`lse-errors-1024`, and any collision recorded as `SUPERSEDED` with the prior
named. If `insights` blocks again, its summary must now say which domain.

---

## 10. Report

`docs/reports/2026-08-DD-gate-toil.md`, committed, with an ACCEPTANCE block,
then `scripts/verify-handover.py --run-tests`. State which claims are
runtime-proven, and state your Hazard C decision explicitly.

---

## 11. Context

- Run: `run_e5b5132c` 2026-08-09T05:46, DEGRADED 5/6.
- The five duplicates: `prp_cad17f36`, `prp_50f883fe`, `prp_1b3fc12b`,
  `prp_359fb30e`, `prp_eb3873ee` — all `PENDING r2`.
- The nine already applied: 2026-08-08 08:10 (5) and 21:25 (4).
- Sub-pass work being completed here: `ccbe879`.
- Console apply-preview that caught this: `22d3528`.
