# SPEC — sub-pass outcomes: stop discarding work that succeeded

> Design: Opus 5, 2026-08-03. Implementation: Sonnet 5 High. Verification: V1.
> Roadmap R4. **Reframed from the original R4 wording** — see §2, which the
> evidence contradicts in one important way.

---

## 1. The bug, measured

`run_pass_stale_contradiction` has **two independent sub-passes** over the
same KB pull (`dream_runner.py:2441`):

- **(a) reverify** — deterministic CHRONOS TTL check. **No LLM call at all.**
- **(b) demote** — cross-checks docs against session outcomes. Needs the LLM.

When (b) fails, the whole attempt is recorded `BLOCKED` and **(a)'s already-
computed proposals are thrown away**.

Measured across four consecutive runs (2026-08-02/03):

| Run | stale-contradiction | reverify proposals lost |
|---|---|---|
| 2026-08-01 20:46 | SUCCEEDED | — (1 reverify kept) |
| 2026-08-02 20:44 | BLOCKED 2244s | yes |
| 2026-08-03 02:41 | BLOCKED 2081s | yes |
| 2026-08-03 03:42 | BLOCKED 1692s | yes |

Three runs computed a deterministic, LLM-free result and discarded it because
an unrelated sub-pass could not reach a model. The reverify work was correct,
complete, and free.

---

## 2. Where the original R4 framing was wrong

The analysis (`docs/TRAUM-ANALYSIS-2026-07-31.md` §R4) described this as
*"NULL and BLOCKED are conflated"* and proposed splitting them at the
boundary. Reading the code, **that specific conflation is not the live
defect**:

- Run-level aggregation already treats `NULL` as good
  (`traum_state.py:635`: `good = sum(s in {"SUCCEEDED","NULL"} ...)`).
- The controller already lets the runner's durable state win when the runner
  used the canonical IDs; the text-scrape of stdout
  (`traum_controller.py:951`) is a **fallback**, not the primary path.

So do not "fix" the NULL/BLOCKED boundary. The real defect is one level down:
**a pass has no way to report that part of it succeeded.** Its outcome is a
single verdict over work that was never single.

A second, smaller gap follows from it: **`DEGRADED` has no gradient.** A run
with 5 of 6 passes good and a run with 1 of 6 both read `DEGRADED`. Six of
eleven non-legacy runs are `DEGRADED`, and an operator cannot tell a near-miss
from a near-total failure at a glance.

---

## 3. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Sub-pass structure | `run_pass_stale_contradiction`, `dream_runner.py:2441` — reverify (no LLM) + demote (LLM) |
| Attempt state set at | `dream_runner.py:4796` — `NULL if null_record is not None else SUCCEEDED` |
| Controller fallback | `traum_controller.py:951-955` — text-scrapes `"SKIPPING run"` / `"null_result="` |
| Run aggregation | `traum_state.py:634-639` — `NULL` already counts as good |
| Attempt states | `QUEUED RUNNING SUCCEEDED NULL BLOCKED FAILED CANCELLED` (`traum_state.py:40`) |
| Suite baseline | 793 passed (2026-08-03) |

---

## 4. Hazards

### Hazard A — do not invent a new attempt state

`ATTEMPT_STATES` is a closed set consumed by the controller, the aggregator,
the Console and the health verdict. Adding `PARTIAL` means touching every one
and re-teaching the operator a vocabulary. **Express partial completion in the
summary, not the state.** A pass that produced usable proposals is
`SUCCEEDED`; one that produced none is `NULL`; one that could not look is
`BLOCKED`.

### Hazard B — keeping proposals must not launder a failure

If reverify succeeds and demote fails, the attempt keeps reverify's proposals
**and must still record that demote was blocked**, with its dependency. The
failure has to remain visible in the summary and the report, or this trades
one bad signal for a worse one: silent partial results that look complete.

### Hazard C — the health verdict reads run states

`_health_verdict` counts `SUCCEEDED` runs. Making partial runs succeed more
often will move that number. That is legitimate *only* if the run genuinely
produced its deterministic output. Do not relax the aggregator to make runs
look better.

### Hazard D — this is not the envelope fix

Commit `41bcc3e` fixed the *cause* of those three blocks (a Python-repr decoy
defeating envelope parsing) and **has not yet run in production**. This spec
addresses the *blast radius* — that a dependency failure discards unrelated
completed work. Both are wanted; do not conflate them, and do not assume this
makes the other unnecessary.

---

## 5. What to implement

1. **Sub-pass results in the summary.** Each pass reports per-sub-pass
   outcome, e.g.:

   ```
   "sub_passes": {
     "reverify": {"state": "SUCCEEDED", "proposals": 1},
     "demote":   {"state": "BLOCKED", "dependency": "dream-llm"}
   }
   ```

2. **`run_pass_stale_contradiction` keeps reverify's proposals** when demote
   raises `DependencyBlocked`. Attempt state becomes `SUCCEEDED` if any
   sub-pass produced proposals, `NULL` if all ran and found nothing, `BLOCKED`
   only if nothing could run at all.

3. **Run summary carries the ratio.** Record `passes_good` / `passes_total` so
   `DEGRADED` can be read as "5 of 6" rather than a bare word.

4. **Console shows it.** In the run table, `DEGRADED` gains the ratio. Reuse
   the existing `.chip` styling; no new CSS.

Apply the same treatment to any other pass with independent sub-passes —
survey them first and report which qualify. Do **not** restructure passes that
have only one.

---

## 6. Anti-goals

- Do **not** add an attempt state.
- Do **not** change the NULL/BLOCKED boundary in the controller or aggregator.
- Do **not** suppress or soften a sub-pass failure to make a run look better.
- Do **not** touch `call_dream_llm`, the cascade, or the circuit breaker.
- Do **not** make a pass succeed when it produced nothing usable.

---

## 7. Tests

1. reverify succeeds + demote raises `DependencyBlocked` → attempt
   `SUCCEEDED`, reverify's proposals present. **Load-bearing.**
2. That same attempt's summary still names demote as blocked with its
   dependency. **Load-bearing — Hazard B.**
3. Both sub-passes find nothing → `NULL`, not `SUCCEEDED`.
4. Neither sub-pass can run (KB unreachable) → `BLOCKED`.
5. `ATTEMPT_STATES` is unchanged.
6. Run summary reports `passes_good`/`passes_total`, and a 5-of-6 run is
   distinguishable from a 1-of-6 run.
7. Console renders the ratio; `node --check` on extracted JS passes.

**Break tests 1 and 2, confirm red, restore.** Report what you saw.

---

## 8. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/traum_state.py tools/traum_controller.py
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/traum_state.py tools/traum_controller.py
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **793 passed**.

---

## 9. Report

`docs/reports/YYYY-MM-DD-subpass-outcomes.md` with an ACCEPTANCE block, then
`scripts/verify-handover.py`. State plainly whether any claim is
runtime-proven; V1 means test-only is acceptable here, but say so.

---

## 10. Context

- Original R4 wording (superseded in part): `docs/TRAUM-ANALYSIS-2026-07-31.md` §R4.
- The cause fix this complements: commit `41bcc3e`.
- Conventions: `docs/WORKFLOW-thread-handover.md`, `docs/WORKFLOW-roadmap-execution.md`.
