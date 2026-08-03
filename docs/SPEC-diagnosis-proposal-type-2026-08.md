# SPEC — the `diagnosis` proposal type

> Design: Opus 5, 2026-08-02/03. Implementation: Sonnet 5 High. Verification: V1.
> Roadmap `docs/ROADMAP-2026-08.md` §1. Supersedes the vaguer "error-remedy"
> entry recorded on 2026-08-02.

---

## 1. Why — a definition problem, not a plumbing problem

`error-cluster` emits `skill-candidate` for everything it finds. The operator
raised this three times, and the third time supplied the definition the system
was missing:

> *An agent skill is a series of actions the agent learns to concatenate
> together for a specific and repeatable deterministic outcome. These
> proposals are different — they are errors.*

That is correct, and the codebase already polices the *other* boundary.
`skill_record`'s own docstring rejects facts:

> GOOD: `task="free disk space by removing duplicates"` — steps with safety gates
> BAD: `task="llama-server port"`, procedure `"8080"` — that is a fact: use `index_to_kb`

So **fact vs skill** is enforced. **Skill vs diagnosis** is not, and everything
`error-cluster` produces lands on the wrong side of it.

### The taxonomy

| Type | Call | Is | Initiated by |
|---|---|---|---|
| fact | `index_to_kb` | a true statement | — |
| rule | `append_learned_rule` | a constraint on behaviour | — |
| skill | `skill_record` | ordered actions for a sought outcome | **you, deliberately** |
| **diagnosis** | `record_error` | a failure signature, what it means, what to do | **an event you did not choose** |

### Definition

> A **diagnosis** records a recognisable failure signature, what it actually
> means, and the correct response — including what *not* to do. It is
> triggered, not initiated.

### Two routing tests

1. **Can I decide to do this?** Yes → skill. It happens to me → diagnosis.
2. **Is the value in the steps, or in "it is not what it looks like"?**
   Steps → skill. Interpretation → diagnosis.

By both tests, all six proposals pending on 2026-08-03 are diagnoses. So is
the skill recorded on 2026-08-02 for the MCP `CancelledError` pattern — the
skills index scored it **0.40** despite `source_tier=verified`, which now
reads as the index correctly rejecting a genre it was not built for.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Existing tool | `record_error(error_text, context, resolution)` — `goethe_kb.py:660` |
| Target index | `lse-errors-1024`, **62 docs** |
| Existing fields | `error_text`, `context`, `resolution`, `error_hash`, `occurrence_count`, `first_seen`, `last_seen` |
| Emitter to change | `run_pass_error_cluster`, `dream_runner.py:~1959` |
| Current emitted type | `skill-candidate` → `skill_record` |
| Index is walled off | `lse-errors-1024` is "never touched by any pass function" (`dream_runner.py:837`) — reserved for dream-infra crash reports |
| Tool-count invariant | D7 pinned the public tool surface at **39**; adding a tool breaks tests. **Extend `record_error`, do not add a new tool.** |
| Suite baseline | 770 passed (2026-08-03) |

---

## 3. Hazards

### Hazard A — do not smuggle fields into free text

`interpretation` and `anti_response` have no column today. The tempting fix is
to concatenate them into `resolution`. **That is the exact mistake this spec
exists to correct.** `dream_runner.py:1953` already concedes doing it once:

> *"skill_record's real signature has no 'trigger' parameter — fold it into
> procedure's own text"*

A schema that needs a field it does not have is the wrong schema. Add
`interpretation` and `anti_response` as real fields (ES dynamic mapping makes
this additive and safe for the existing 62 docs).

### Hazard B — `anti_response` is the load-bearing field

Three of the six pending proposals are wrong *because* they prescribe the
intuitive action. The MCP one says "retry the failed command immediately" —
which reproduces the failure, because the cause is a request timeout, not
flakiness. A type without a place to say **"do not do the obvious thing"**
will keep producing confidently wrong advice.

### Hazard C — opening the error index to pass functions

`lse-errors-1024` is currently reserved for dream-infra's own crash reports,
with provenance `dream-infra`. Opening it to `error-cluster` must preserve
that boundary: pass-written diagnoses carry their own provenance and must
never be mistaken for infra crash records. Do not remove the existing
restriction wholesale — widen it deliberately, under Human Gate control.

### Hazard D — do not auto-migrate what already exists

Six `skill-candidate` proposals are pending and one mis-typed skill is already
recorded. Leave them. Re-typing them automatically means guessing intent for
records a human has not reviewed. Report them for manual disposal.

---

## 4. What to implement

1. **Extend `record_error`** with two optional keyword params,
   `interpretation: str = ""` and `anti_response: str = ""`, written as their
   own ES fields. Existing three-arg callers must be unaffected.
2. **New proposal type `diagnosis`** in `dream_runner`, `call="record_error"`,
   args: `error_text` (the signature), `context`, `interpretation`,
   `resolution` (the response), `anti_response`.
3. **`run_pass_error_cluster` emits `diagnosis`**, not `skill-candidate`. Its
   LLM prompt must ask for the five fields explicitly — in particular for
   `anti_response`, which the model will not volunteer.
4. **`dream_apply`** validates and applies the new type through the existing
   Human Gate path.
5. **Console** renders it via the `proposalAction()` map added in `22d3528`:
   `record_error` → `["Record diagnosis", <error_text first line>]`.
6. **`error-cluster` may still emit `skill-candidate`** when a genuine
   repeatable procedure exists — routed by §1's two tests, stated in the
   prompt. This is not a wholesale replacement.

---

## 5. Anti-goals

- Do **not** add a new tool. The 39-tool surface is a pinned invariant.
- Do **not** concatenate `interpretation`/`anti_response` into `resolution`.
- Do **not** auto-migrate existing skill-candidates or the recorded skill.
- Do **not** change `skill_record` or the skills index.
- Do **not** remove `lse-errors-1024`'s dream-infra provenance boundary.

---

## 6. Tests

1. `record_error` with three positional args behaves exactly as before.
2. New fields persist and are retrievable.
3. `error-cluster` emits `diagnosis` for a triggered-failure cluster.
4. A cluster with a genuine repeatable procedure can still emit
   `skill-candidate` — routing works both ways. **Load-bearing.**
5. A `diagnosis` proposal missing `anti_response` is still valid (the model
   may legitimately have none) but one missing `interpretation` is rejected as
   an incomplete draft — the interpretation *is* the value. **Load-bearing.**
6. Applying a `diagnosis` writes to `lse-errors-1024`, not `lse-kb`.
7. Pass-written diagnoses are distinguishable from dream-infra crash records.
8. The Console renders `record_error` with a readable action line.

**Break tests 4 and 5, confirm red, restore.** Report what you saw.

---

## 7. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/goethe_kb.py tools/dream_apply.py
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/goethe_kb.py tools/dream_apply.py
node --check /tmp/d.js    # extracted dashboard JS
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **770 passed**. The tool-count test must still pass at 39.

---

## 8. Report

`docs/reports/YYYY-MM-DD-diagnosis-type.md`, ACCEPTANCE block per
`WORKFLOW-thread-handover.md` §1b, then `scripts/verify-handover.py`.

List the six pending mis-typed proposals and the one mis-typed skill for
manual disposal — do not act on them.

---

## 9. Context

- The operator's definition and the two routing tests: this document §1.
- Where the mis-typing shows: `docs/ROADMAP-2026-08.md` §1.
- Console action map to extend: `tools/goethe_dashboard.html`, `22d3528`.
