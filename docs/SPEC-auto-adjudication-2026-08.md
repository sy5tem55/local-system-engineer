# SPEC — give the machine stage rules

> Design: Opus 5, 2026-08-09. Implementation: Sonnet 5 High. Verification: V2,
> one V3 claim (§9). Roadmap §1 (Human Gate legibility).
>
> Operator, after being handed a manual triage of 18 proposals: *"This is too
> much work. There must be a stage where a reviewer approves and rejects
> programmatically."* Correct. The stage exists and was never given rules.

---

## 1. The problem, measured

```
human adjudications : 147
machine             :  30
```

The machine handles 17%, and all three rules it has are **structural** —
`incomplete_budget_truncation` (23), a malformed-skill check (4),
`target_changed_since_generation` (3). Not one looks at content. Every
content judgement, all 147, lands on a person.

The 18 diagnoses pending on 2026-08-09 are what that costs. They are not
duplicates by fingerprint — 15 of them resolved to 15 distinct identities even
after the `SPEC-gate-toil` narrowing — but by *content* they are roughly six
facts:

| Count | Class | Why the machine could have decided |
|---|---|---|
| 4 | `CancelledError` session teardown | reworded restatements of one fact |
| 4 | `[TIMEOUT] ssh_run/ssh_script` | one class, four hosts |
| 3 | SSH/SCP `Permission denied` | one confirmed cause (`root` vs `lse-admin`) |
| 2 | 403/404 on third-party sites | not system diagnoses at all |
| 1 | pfSense API key | the error text already contains its own fix |

Exact-fingerprint dedup cannot catch any of this, because the model rewords
every run. **That was the flaw in `SPEC-gate-toil`'s narrowing** — identity
built from text was always going to lose to paraphrase. Embeddings do not
care about wording, and `lse-errors-1024` already carries
`embedding: dense_vector dims=1024`.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Machine-rejection path | `traum_state.py:838` — `initial_state="SYSTEM_REJECTED"` + `initial_reason`, already used for `invariant:secret_material_redacted` |
| Reason prefixes counted as priors | `traum_state.py:859` — `malformed:`, `noop:`, `invariant:` |
| Errors index embeddings | `lse-errors-1024`, `dense_vector`, 1024 dims |
| Existing cosine machinery | `dream_runner.py` dedup pass — `_dedup_floor_default()` `:460`, `_dedup_threshold_default()` `:490`, threshold 0.92 |
| Cluster bars | `ERROR_CLUSTER_MIN_OCCURRENCES = 3`, `ERROR_CLUSTER_MIN_SESSIONS = 2` (`:1952`), applied at `:2679` to the cluster |
| Suite baseline | **859 passed, 0 skipped** — establish it yourself, exclusively |

**A finding to confirm, not assume.** `prp_b8c68300` justifies itself with
*"Although only one occurrence."* The `>=3 occurrences / >=2 sessions` bar is
applied to the **cluster**, and clusters are built by embedding similarity —
so a single `192.168.5.41` timeout can ride into a cluster of `node3090`
timeouts and be written up as its own per-host diagnosis. If that is what
happened, the mixed-cluster behaviour is a separate defect worth its own
entry; **do not fix it here**, just report what you find.

---

## 3. Hazards

### Hazard A — an over-eager rule silently eats a true diagnosis
This is the failure mode of the whole spec, and this codebase has been bitten
by silent mechanisms five times in one session. Every rule must therefore be
**individually switchable**, must **name itself and its prior in the reason**,
and must be **counted per run and surfaced**. A rule you cannot see firing is
a rule you cannot trust.

### Hazard B — the reason prefix decides whether the proposal comes back
`repeat_prior()` treats only `malformed:`, `noop:` and `invariant:` prefixes
as priors. A rule-rejection whose prefix is not in that set will be re-drafted
and re-rejected **every single run** — churn instead of relief. New reason
codes must be added to that set deliberately, and the test must prove a
rejected proposal does not return.

### Hazard C — 0.92 is not a free number
The dedup threshold was set by an explicit labelling exercise
(`--sample-labels`) against **KB documents**. Diagnoses are shorter, more
formulaic, and share boilerplate, so they will score higher for the same
semantic distance. Do not inherit 0.92. Calibrate against the 18 live
proposals — the target is that the four `CancelledError` entries collapse and
the two `Permission denied` / `No route to host` entries **do not**, because
those are genuinely different causes.

### Hazard D — rules may reject and supersede, never approve
No rule writes to the KB. Approval stays human, always. A rule that
auto-applies is a rule that writes unreviewed content into the index the whole
system trusts.

### Hazard E — scope to `diagnosis`
`dedup`, `demote`, `reverify`, `kb-fact`, `prompt-rule` are not in evidence
here. Do not extend the rules to them without data showing they need it —
that is exactly the over-reach `SPEC-gate-toil` Hazard B warned about and
that its implementer correctly refused.

### Hazard F — the existing three rules must not change behaviour
`incomplete_budget_truncation`, the malformed-skill check and
`target_changed_since_generation` account for 30 live decisions. Adding rules
must leave those byte-identical. Prove it the way `test_gate_toil.py` test 6
did: recompute the pre-change outcome independently, do not merely assert the
suite is still green.

---

## 4. What to implement

A rules layer at proposal-record time, reusing `initial_state` /
`initial_reason` (`traum_state.py:838`). Not a new stage, not a new state.

**R1 — semantic near-duplicate → `SUPERSEDED`.** A `diagnosis` whose embedding
is within the calibrated threshold of an existing `PENDING` or `APPLIED`
diagnosis is superseded, and the reason names the prior's `proposal_id` and
state. This is the rule that does most of the work.

**R2 — third-party resource error → `SYSTEM_REJECTED`.** An `error_text`
carrying an HTTP status against a non-local URL is a fact about someone else's
website, not a diagnosis of this system. Reason must say so.

**R3 — resolution adds nothing over error_text → `SYSTEM_REJECTED`.** The
pfSense case: the error message already contains the remedy verbatim.
Approximate by embedding distance between `error_text` and `resolution`;
calibrate conservatively, and prefer false negatives.

**Observability, not optional.** Each run reports per-rule counts, the Console
shows them, and a `--dry-run` mode lists what each rule *would* do without
writing. Ship the dry-run first and paste its output over the current 18
before enabling anything.

---

## 5. Anti-goals

- Do **not** add a proposal state or a proposal type.
- Do **not** let any rule approve or apply.
- Do **not** extend rules beyond `diagnosis`.
- Do **not** reuse 0.92 without calibrating.
- Do **not** change the three existing rules.
- Do **not** fix the mixed-cluster behaviour from §2 here.
- Do **not** touch the probe work (`SPEC-diagnosis-probe-2026-08`) — it
  adjudicates the residue this spec leaves behind, and lands after.

---

## 6. Tests

1. Four reworded `CancelledError` diagnoses → one survives, three
   `SUPERSEDED`, each naming the survivor. **Load-bearing.**
2. `Permission denied` and `No route to host` for the same `error_text` stay
   **separate** — different causes must not collapse. **Load-bearing —
   Hazard C.**
3. A rule-rejected proposal re-offered next run is not re-drafted into
   `PENDING`. **Load-bearing — Hazard B.**
4. A 403/404 against a third-party URL is rejected; the same status against a
   local service is **not**.
5. No rule can produce `APPLIED` or `STAGED`. **Load-bearing — Hazard D.**
6. `dedup`/`demote`/`reverify`/`kb-fact` outcomes are byte-identical to
   pre-change for the same payloads. **Load-bearing — Hazard F.**
7. Each rule can be disabled individually, and disabling all of them restores
   exactly today's behaviour.
8. `--dry-run` writes nothing.

**Break tests 2 and 6, confirm red, restore.** Report exact failure text and
prove the restore with a diff.

---

## 7. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/traum_state.py tools/dream_runner.py
/home/sy5/miniforge3/bin/ruff check tools/traum_state.py tools/dream_runner.py
pgrep -af pytest          # MUST be empty first
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Pre-existing ruff counts must not increase.

---

## 8. Verification — V2, plus one V3 claim

**V3, and it is the whole point:** run `--dry-run` against the 18 real pending
proposals and paste the verbatim per-rule output. Acceptance is that it
reduces them to **four or fewer** survivors while leaving the
`Permission denied` / `No route to host` pair intact as two.

If a rule would eat something a human would have kept, say so and turn that
rule off. A conservative rule set that halves the gate beats an aggressive one
that loses a true diagnosis.

---

## 9. Report

`docs/reports/2026-08-DD-auto-adjudication.md`, committed, with an ACCEPTANCE
block, then `scripts/verify-handover.py --run-tests`. State the calibrated
threshold and how it was chosen, and report the §2 mixed-cluster finding.

---

## 10. Context

- The 18 pending proposals, 2026-08-09.
- Adjudicated by hand that night: SSH failures are `root` auth, not network —
  `lse-admin` authenticates, `root` gives `Permission denied
  (publickey,password)`, node3090 up with port 22 open.
- Partial predecessor whose text-identity premise this supersedes:
  `SPEC-gate-toil-2026-08`.
- Lands before: `SPEC-diagnosis-probe-2026-08`.
