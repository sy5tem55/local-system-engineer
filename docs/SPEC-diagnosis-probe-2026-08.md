# SPEC — a diagnosis must be falsifiable

> Design: Opus 5, 2026-08-09. Implementation: Sonnet 5 High. Verification: V2,
> one V3 claim (§9). Roadmap §1 (`diagnosis` type), §1b (ML root-cause).
>
> Raised by the operator: *"Right now I am approving the discovery of the
> error while I should approve its solution."* That is the correct complaint,
> and the data below shows it is sharper than it first appears.

---

## 1. The problem, measured

Six `diagnosis` proposals are pending for one error signature,
`[SSH FAILURE] exit 255`. Their `context` and `resolution` fields:

```
"...wrapper has already attempted to clear a stale multiplexed connection"
    -> "Read the specific ssh stderr line to classify the failure."
"...after the wrapper has already cleared the stale mux and retried once."
    -> "Check the username and key configuration."
"...underlying SSH reports 'Permission denied' for root or lse-admin."
    -> "Verify the username and private key configuration."
"...underlying SSH reports 'No route to host' on port 22."
    -> "Verify the host is online and reachable via ping."
```

Two of them **contradict each other**. One says verify the private key; the
other's `anti_response` says *"checking SSH keys ... the failure is
network-level, not authentication."* Approving both writes a
self-contradiction into `lse-errors-1024`, and `check_error_kb` will return
whichever ranks higher.

**`[SSH FAILURE] exit 255` is not a diagnosis. It is a symptom with a
differential.** `Permission denied` and `No route to host` are different root
causes of the same exit code, and collapsing them would be wrong.

So the gate is asking the one question that cannot be answered from a
proposal: *which of these is true here?* The information is not in the logs.
No amount of model quality fixes that.

### Why the duplicate fix does not solve this

`SPEC-gate-toil-2026-08` narrowed diagnosis identity to
`error_text` + `context`, asserting both are "derived from the cluster, not
invented by the model". **That premise was wrong** — the `context` strings
above are plainly model prose, reworded per run. Measured: six proposals
collapse to **five** fingerprints, not one.

And partly that is *correct*: two of those five encode a real distinction. The
narrowing is still worth having, but it is a partial fix, and the remaining
duplication is not noise — it is an unadjudicated differential.

---

## 2. The reframing

**Do not ask the model to propose the solution. Ask it to propose the
experiment that would confirm or refute its own interpretation.**

- Generating a differential is what generative models are good at. Six
  candidate causes for exit 255 is a feature.
- Choosing between them from logs is not a model weakness; the evidence is
  absent.
- A discriminating probe is cheap, **read-only**, and mechanical —
  `nc -z host 22` separates network from auth in one command.

`assert_state(check_command, expected_regex)` already exists and already
describes itself as *"the PREFERRED producer for evidence= fields"*. This
spec wires the diagnosis flow into a tool the codebase already has.

The gate then asks two answerable questions instead of one unanswerable one:

1. *Is this error class real and worth remembering?* — evidence already there.
2. *Should I run this read-only probe?* — concrete and bounded.

And `lse-errors` entries become tiered by evidence, the way the skills index
already is: `skill_record`'s gate says *"only call after the procedure was
executed AND its outcome verified"*. The errors index has no such gate. That
asymmetry is the underlying defect.

---

## 3. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| `lse-errors-1024` doc fields | `error_hash, error_text, context, resolution, interpretation, anti_response, occurrence_count, first_seen, last_seen` |
| `record_error` signature | `goethe_kb.py:660` — `(error_text, context, resolution, interpretation="", anti_response="")` |
| Probe runner | `goethe.py:1837` `assert_state(check_command, expected_regex)` |
| Proposal states | 10, `traum_state.py:45`. **Do not add one.** |
| Console proposal routes | `goethe_ui.py:1418-1419` — `/preview`, `/decision` |
| Diagnosis drafting | `_ERROR_CLUSTER_SYSTEM_PROMPT` `dream_runner.py:2048`; `_draft_error_cluster_proposals` `:2071` |
| Tool-description cap | `_TOOL_DESC_MAX` = 3072 (`goethe_mcp.py`). `record_error`'s docstring is ~1036 chars; adding a parameter grows it |
| Suite baseline | **establish it yourself, exclusively.** Last verified: 843 on `codex/fix-sudo-grants-live` pre-merge, 855 on `codex/gate-toil-2026-08` |

**Verify `assert_state` actually enforces read-only.** The docstring claims
it; the spec's entire safety argument rests on it. If it does not enforce,
say so and stop — an allowlist becomes a prerequisite, not an afterthought.

---

## 4. Hazards

### Hazard A — not every diagnosis is probeable
`CancelledError: Cancelled via cancel scope` has no live read-only command
that would confirm it. Making the field mandatory guarantees the model
invents plausible nonsense to satisfy the schema. **The field is optional**,
and the prompt must say explicitly: leave it empty when no read-only command
could distinguish this cause from its alternatives.

### Hazard B — a probe run now tests a failure from the past
The diagnosis is drafted from historical episodes; the probe runs today. A
probe that finds nothing wrong has **not** refuted the diagnosis — the
condition may simply not be present. Three outcomes are required:
`CONFIRMED`, `REFUTED`, `INCONCLUSIVE`. Collapsing the third into the second
will reject correct diagnoses.

### Hazard C — a probe that cannot run is not a refutation
node3090 may be asleep; a host may be down; the vault may be locked. "Probe
errored" and "probe returned a negative" are different facts and must not
share a code path.

### Hazard D — do not add a proposal state
Ten already exist and R5 exists to *reduce* them. The probe result is a field
on the proposal, not a lifecycle stage. A proposal stays `PENDING` until a
human decides; the probe result is decision *support*, not a decision.

### Hazard E — read-only is the safety boundary, and it is load-bearing
The SCP/publickey case tempts a remedy touching `authorized_keys`. Writing
remedies are out of scope. Anything that mutates goes through §2's
`propose_file_change` or a `sudo_delegation_block` — never this path. If you
find yourself widening the probe to "just this one write", stop.

### Hazard F — prompt and docstring budget
`_ERROR_CLUSTER_SYSTEM_PROMPT` already asks for two arrays and five fields per
diagnosis. Adding a sixth risks the model dropping others. Check the emitted
envelopes before and after; if field-drop rate rises, the prompt needs
restructuring rather than another line.

### Hazard G — do not re-fix the fingerprint
`SPEC-gate-toil-2026-08` is landing separately. Its premise about `context`
was wrong (§1), but correcting that is **not this spec's job**. Note it in
the report; do not touch `_NARROW_IDENTITY_TYPES`.

---

## 5. What to implement

1. **`discriminating_probe` on the diagnosis proposal** — optional, two
   fields: a read-only `check_command` and an `expected_regex` that would hold
   **if this interpretation is correct**. Same shape `assert_state` takes, so
   it can be executed without translation.
2. **Prompt change** — `_ERROR_CLUSTER_SYSTEM_PROMPT` asks for it, states it
   must be read-only, and states plainly that empty is correct when no such
   command exists (Hazard A).
3. **A probe action in the Console**, alongside `/preview` and `/decision`:
   run the proposal's probe via `assert_state`, store the outcome
   (`CONFIRMED` / `REFUTED` / `INCONCLUSIVE`), the verbatim output, and a
   timestamp on the proposal. No state change (Hazard D).
4. **Carry the result through apply.** When a probed diagnosis is approved,
   `record_error` records that it was probe-confirmed and when. An entry
   confirmed by a live probe must be distinguishable from an unverified
   hypothesis — that distinction is the whole point.
5. **Surface it in `check_error_kb`**, so a future session can tell "confirmed
   2026-08-09 by `nc -z node3090 22`" from "the dreamer thought so".

---

## 6. Anti-goals

- Do **not** add a proposal state or a proposal type.
- Do **not** allow a probe to write, restart, delete, or authenticate.
- Do **not** auto-approve on `CONFIRMED`. The human still decides; the probe
  informs.
- Do **not** auto-reject on `REFUTED` — see Hazard B.
- Do **not** make the probe mandatory.
- Do **not** touch the gate-toil fingerprint work.
- Do **not** attempt automated remediation. Different spec, later, gated on §2.

---

## 7. Tests

1. A diagnosis with no `discriminating_probe` is still valid and applies
   exactly as today. **Load-bearing — Hazard A.**
2. A probe whose regex matches records `CONFIRMED` with verbatim output.
3. A probe whose regex does not match records `REFUTED`.
4. A probe whose command fails to execute records `INCONCLUSIVE`, never
   `REFUTED`. **Load-bearing — Hazard C.**
5. Running a probe does not change the proposal's state. **Load-bearing —
   Hazard D.**
6. An approved probe-confirmed diagnosis carries the confirmation and
   timestamp into `lse-errors`; an approved unprobed one does not claim
   confirmation. **Load-bearing.**
7. A probe containing a write/restart/delete verb is refused before
   execution. **Load-bearing — Hazard E.**
8. `check_error_kb` output distinguishes confirmed from unverified.

**Break tests 4 and 7, confirm red, restore.** Report exact failure text and
prove the restore with a diff.

---

## 8. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/goethe_kb.py tools/goethe_ui.py
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/goethe_kb.py tools/goethe_ui.py
pgrep -af pytest          # MUST be empty first
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Pre-existing ruff counts must not increase. `tests/test_kb_contracts.py` is an
ES integration suite — a count taken during an overlapping run is meaningless.

---

## 9. Verification — V2, plus one V3 claim

**V3:** take one real pending `[SSH FAILURE] exit 255` proposal, run its
probe, and paste the verbatim outcome. Then state which of the competing
pending diagnoses for that signature the result supports and which it
refutes. That is the behaviour this spec exists to produce: a differential
adjudicated by evidence rather than by reading.

---

## 10. Report

`docs/reports/2026-08-DD-diagnosis-probe.md`, committed, with an ACCEPTANCE
block, then `scripts/verify-handover.py --run-tests`. State explicitly whether
`assert_state` enforces read-only, since §4 Hazard E depends on it.

---

## 11. Context

- The six competing proposals, live in the gate 2026-08-09.
- Partial predecessor: `SPEC-gate-toil-2026-08` (`81d9fb8`), implemented as
  `2558013`, unmerged at time of writing.
- The evidence-gate precedent this mirrors: `skill_record` / `skill_outcome`.
- Conventions: `docs/WORKFLOW-thread-handover.md`,
  `docs/WORKFLOW-roadmap-execution.md` §5–6.
