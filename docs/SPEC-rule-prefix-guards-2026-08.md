# SPEC — guard the reason-prefix contract

> Design: Opus 5, 2026-08-11. Implementation: Sonnet 5 High. Verification: V2.
> Roadmap §1 (Human Gate legibility). Follows the review of `4a1c549` /
> `f60f343`, which passed.
>
> Reviewer, on why this exists: the Hazard B claim in
> `SPEC-auto-adjudication-2026-08` is **true**, but the test that proved it
> could not have failed if it were false. Four facts came out of that review
> and all four currently live in prose. Prose does not run.

---

## 1. The problem, measured

The review of `4a1c549` confirmed every claim the implementer made — test
count, ruff baseline, restore hashes, the dry-run transcript, both spec §8
calibration targets. It also established four things that exist nowhere in
the suite:

| # | Fact | How it was established |
|---|---|---|
| 1 | An R2-rejected proposal never returns to the inbox across three real runs | scratch DB, three full `apply_diagnosis_rules` → `record_proposals` → `finish_attempt` cycles |
| 2 | The **honored-prefix set** is what decides that — an unhonored prefix sends the redraft straight back to `PENDING` | same, with the reason minted as `rulex:` instead of `rule:` |
| 3 | Row churn is *not* closed — three runs produce three rows, because R2 re-fires and re-stamps `SYSTEM_REJECTED` before the prior branch can apply | same, row count |
| 4 | An R3 rejection is an **absorbing state**: a later run that fixes exactly the defect R3 objected to is `SUPERSEDED` and never reviewed | scratch DB, `resolution == error_text` then a genuinely better resolution |

`tests/test_diagnosis_rules.py` test 3 asserts the honored path only. It
passes whether or not `"rule:"` is load-bearing, because it never exercises
the alternative. That is the gap this spec closes.

**The mechanism behind fact 4, stated once.** R3 judges `args.resolution`.
The fingerprint is `{type, call, args.error_text, args.context}` — narrowed
by `SPEC-gate-toil-2026-08`. So an R3 verdict permanently binds an identity
computed from fields it never read. R2 does not have this property: it reads
`error_text`, which *is* in the fingerprint. This is the first **content**
judgement to become absorbing; `malformed:`, `noop:` and `invariant:` are all
structural.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Honored reason prefixes | `traum_state.py:862-871` — `malformed:`, `noop:`, `invariant:`, `rule:` |
| Prior → `SUPERSEDED` branch | `traum_state.py:936` — fires **only** when `initial_state in {"STAGED","PENDING"}` |
| Narrow identity | `traum_state.py:239-240` — `_NARROW_IDENTITY_TYPES = {"diagnosis"}`, `_NARROW_IDENTITY_ARG_KEYS = ("error_text","context")` |
| R3's judged field | `diagnosis_rules.py:162` — cosine of `args.error_text` vs `args.resolution` |
| Reason prefix constant | `diagnosis_rules.py:56` — `RULE_REASON_PREFIX = "rule:"` |
| Existing test helpers to reuse | `tests/test_diagnosis_rules.py` — `_fake_embed:57`, `_cfg:69`, `_diagnosis:80`, `_store:137`, `_record_one:141` |
| Tests in that file today | **15** (`--collect-only -q`) |
| Suite baseline | **874 passed, 0 skipped** — verified exclusively 2026-08-11. Establish it yourself. |

**Measured outcomes, to reproduce and not assume.** Scratch-DB runs on
2026-08-11 produced: three consecutive R2 cycles → `SYSTEM_REJECTED` ×3, three
rows, never `PENDING`; the `rulex:` control → `PENDING`; the R3 improved
redraft → `SUPERSEDED`. If any of these comes out differently for you, that is
a finding — report it, do not adjust the test until it matches.

---

## 3. Hazards

### Hazard A — a characterization test read as an endorsement
Tests 11 and 12 encode behaviour that is arguably wrong: a fixed diagnosis
that never reaches a human. They are here to make it **visible and stable**,
not to bless it. Each must carry an in-file comment saying so, and naming what
would justify changing it (a decision to exclude `rule:`-rejections from the
honored set, or to add `resolution` to the diagnosis fingerprint). A future
reader must not be able to cite these tests as evidence the behaviour is
intended.

### Hazard B — the fake embedding is not a semantic model
`_fake_embed` is a hashed bag-of-words: cosine tracks raw word-overlap
fraction, which real embeddings do not. Do **not** tune prose to sit just
above or below a threshold — that produces a test that breaks when someone
rewords a fixture. Force determinism instead: for test 11, make `resolution`
**byte-identical** to `error_text` so the cosine is exactly `1.0000`.

### Hazard C — test 3 is not to be modified
It covers the honored path and it is load-bearing for Hazard B in the parent
spec. These tests are strictly **additive**. Do not merge them into test 3, do
not parametrize test 3 to absorb them, do not renumber it.

### Hazard D — never touch the live database
Every test uses `tmp_path`. Do not open `/opt/local-se/dreams/traum-state.db`,
not even `mode=ro`, and do not copy it. The suite must stay runnable on a
machine where that file does not exist.

### Hazard E — the row-count assertion will look like a bug
Test 9 asserts three rows after three runs. That is a **measurement** of
current behaviour, not a target. If it fails, row churn changed — which is a
thing to ask about, not to relax the assertion over. Same rule as
`test_gateway_pin.py`: red here is a signal to ask.

---

## 4. What to implement

Four tests appended to `tests/test_diagnosis_rules.py`, plus two documentation
corrections. No behaviour change anywhere.

**T-9 — the realistic re-fire path.** Three consecutive runs of the same
third-party-URL diagnosis, reworded prose each time, `apply_diagnosis_rules`
run every time (unlike test 3, which deliberately skips it). Assert the state
is `SYSTEM_REJECTED` on all three and **never** `STAGED`/`PENDING`; assert the
reason keeps the `rule:third_party_resource_error:` prefix; assert three rows
exist in `proposals` (Hazard E).

**T-10 — the negative control.** Identical flow, but the first proposal is
recorded with `_initial_reason` minted as `rulex:third_party_resource_error:…`
— one character off the honored set. Assert the redraft lands in `PENDING`.
This is the test that makes test 3 mean something: it shows the prefix, not
the surrounding machinery, is what keeps the proposal out of the inbox.

**T-11 — R3 is an absorbing state.** Run 1: `resolution` byte-identical to
`error_text` → R3 fires, `SYSTEM_REJECTED`, reason
`rule:resolution_redundant_with_error_text:1.0000`. Run 2: same
`error_text`/`context`, genuinely informative `interpretation` and
`resolution` → R3 stays silent. Assert the outcome is `SUPERSEDED`, assert it
is **not** `PENDING`/`STAGED`, and assert the reason names the prior and its
`SYSTEM_REJECTED` state. Carry the Hazard A comment.

**T-12 — the field mismatch, stated in one assertion.** Two proposals
identical except `resolution`. Assert `ts.proposal_fingerprint()` returns the
**same** hash for both, while `dgr.rule_r3_resolution_redundant()` returns a
verdict for one and `None` for the other. No store, no runs — this is the
mechanism behind T-11 isolated to two calls.

**D-1 — R3 docstring.** Add to `rule_r3_resolution_redundant`'s docstring that
it judges `resolution`, which is not part of the narrow fingerprint, and that
its rejection therefore binds an identity computed from fields it did not
read. Cross-reference T-11/T-12.

**D-2 — report correction.** In `docs/reports/2026-08-11-auto-adjudication.md`
§4, the acceptance paragraph claims spec §8's Hazard C pair was verified. The
pair verified was *Permission denied* vs *Connection timed out*; the pair §8
and Hazard C name is *Permission denied* vs **No route to host**. That row
exists — `prp_237da5f542`, `APPLIED`, and R1 does use it as a prior. Measured
cosine against `prp_c6fbb0a811` is **0.6555**, so the target holds; only the
evidence was substituted. State the substitution, name the row, record the
number.

---

## 5. Anti-goals

- Do **not** change `repeat_prior()`'s honored set. If `rule:` should come
  out, that is a different spec with a different blast radius.
- Do **not** add `resolution` to `_NARROW_IDENTITY_ARG_KEYS`. Same reason —
  and it would re-open the churn `SPEC-gate-toil` closed.
- Do **not** change R2, R3 or their thresholds.
- Do **not** modify, renumber or absorb tests 1–8.
- Do **not** touch the backfill question. The 16 live `PENDING` rows are a
  separate decision and are not affected by anything here.
- Do **not** re-run or re-calibrate the dry-run. It was reproduced verbatim
  on 2026-08-11.

---

## 6. Tests

The four above, numbered 9–12 in the file's existing comment-banner style, in
their own classes alongside the existing ones.

**Break the guard, confirm red, restore.** Remove `"rule:"` from the honored
tuple at `traum_state.py:871` and run
`pytest tests/test_diagnosis_rules.py -q`. Expected, and all three parts are
load-bearing:

- existing **test 3** → red
- **T-11** → red
- **T-10** → **green** — it uses an unhonored prefix, so removing another one
  cannot change its outcome

That third line is the point: it proves T-10 is a control rather than a
duplicate of test 3. Paste the verbatim failure text. Restore, and prove the
restore with `sha256sum tools/traum_state.py` before-break and after-restore,
not "tests pass again".

---

## 7. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/traum_state.py tools/diagnosis_rules.py tests/test_diagnosis_rules.py
/home/sy5/miniforge3/bin/ruff check tests/test_diagnosis_rules.py tools/diagnosis_rules.py
pgrep -af '[p]ytest'      # MUST be empty — plain `pgrep -af pytest` self-matches its own /bin/sh -c wrapper
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

`tests/test_diagnosis_rules.py` and `tools/diagnosis_rules.py` are ruff-clean
today (0 errors). They must stay at 0. The repo-wide baseline of 22 pre-existing
errors must not increase.

---

## 8. Verification — V2

Exclusive run. **874 → 878 passed, 0 skipped** — four new test functions, none
parametrized. Any other delta means something outside this change moved; say
so rather than reporting the number.

Confirm `--collect-only -q` on the file reports **19**, so the delta is fully
attributable and nobody has to diff two full-suite runs to see it.

---

## 9. Report

`docs/reports/YYYY-MM-DD-rule-prefix-guards.md`, committed, with the
break/red/restore transcript, the sha256 restore proof, before/after test and
ruff counts, an explicit note of anything in §2's ground-truth table that
turned out to be wrong, and a closing ACCEPTANCE block. Do not push.

---

## 10. Context

- Review thread, 2026-08-11: `4a1c549` and `f60f343` reviewed and passed.
  Four findings, all reproduced on scratch databases; this spec turns the
  three durable ones into guards.
- `SPEC-auto-adjudication-2026-08` §3 Hazard B — the claim these tests make
  falsifiable.
- `SPEC-gate-toil-2026-08` §5.2 — where the narrow diagnosis identity comes
  from, and why `resolution` is not in it.
- `tests/test_gate_toil.py::test_6` — the house standard for proving a claim
  by independent recomputation rather than by suite colour.
- `docs/WORKFLOW-thread-handover.md` §0a — the tool-prefix drift found while
  writing this spec's handover prompt, and §5's "a test that cannot fail
  proves nothing", which this spec is an instance of.
- Settled, do not re-litigate: the SSH failures are `root` auth, not network.
  node3090 up, port 22 open, `lse-admin` authenticates, `root` gives
  `Permission denied (publickey,password)`.

---

## Appendix — handover prompt

Paste verbatim into the implementer thread. Per
`docs/WORKFLOW-thread-handover.md` §0a/§1, the first block is not optional and
the tool prefix must not be assumed.

```
FIRST: load the Goethe MCP tools before anything else. They are deferred and
not callable until loaded. The server's tool PREFIX varies by session — try
the documented name first:
  ToolSearch: select:mcp__goethe__execute_command,mcp__goethe__read_file,mcp__goethe__write_file

If that returns "No matching deferred tools found", it is mounted under a
different prefix. Discover it by keyword instead:
  ToolSearch: goethe execute_command read_file
and use the fully-qualified names that come back. On 2026-08-11 they were
mcp__remote-devices__goethe__*. Load everything you need in ONE call.

A name that does not resolve means the wrong prefix, NOT a missing machine.

All filesystem and shell access to the target machine goes through those
tools. Do NOT use the sandbox Bash/Read tools for this task — they run in an
isolated container that cannot see the repo. If a path like /home/sy5/... is
not found, you loaded the wrong tool, not the wrong path.

Verify access before starting:
  <goethe>__execute_command("hostname; ls /home/sy5/projects/local-system-engineer")
  → expect: LUCIFER, and a repo listing.

TASK: add four characterization tests that make the reason-prefix contract
falsifiable, plus two documentation corrections. No behaviour change.

Read first, in order:
  1. docs/SPEC-rule-prefix-guards-2026-08.md   (all of it — it is short)
  2. AGENTS.md                                  (§3 test running, §4 shell traps)
  3. tests/test_diagnosis_rules.py              (tests 1-8, for house style)

Environment:
  - Live tree: /home/sy5/projects/local-system-engineer  (WSL, host LUCIFER)
  - Branch: already checked out. Capture it rather than typing it:
      BR=$(git rev-parse --abbrev-ref HEAD)
    The name contains a substring that trips the privilege gate's match, so
    never type it literally in a shell command. Use "origin/$BR", never "@{u}"
    — a remote branch can exist with no tracking configured and @{u} then
    raises a fatal that reads exactly like "nothing is pushed".
  - Python: /home/sy5/owui/bin/python3
  - ruff: /home/sy5/miniforge3/bin/ruff   (NOT `python3 -m ruff`)

Hard constraints:
  - Do NOT git push. Commit only; the operator pushes.
  - Exclusive test access is mandatory. `pgrep -af pytest` SELF-MATCHES its
    own /bin/sh -c wrapper and will look non-empty when nothing is running —
    use `pgrep -af '[p]ytest'` and expect exit 1. tests/test_kb_contracts.py
    is an Elasticsearch integration suite; overlapping runs corrupt counts.
  - pytest outlives the MCP request timeout and dies with MCP error -32001.
    Background it and poll:
      nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
    Baseline: 874 passed, 0 skipped. Expected after: 878.
  - execute_command runs under /bin/sh, not bash. Wrap [[ ]], arrays and
    process substitution in `bash -lc`.
  - The privilege gate refuses a git commit whose MESSAGE quotes a privileged
    command. Write the message to a file and use `git commit -F`.
  - Never open /opt/local-se/dreams/traum-state.db from a test, not even
    read-only. tmp_path only.
  - Do not modify repeat_prior(), R2, R3, their thresholds, or tests 1-8.

Finish with docs/reports/YYYY-MM-DD-rule-prefix-guards.md (committed, NOT
/tmp), including the break/red/restore transcript, the sha256 restore proof,
before/after ruff and test counts, an explicit note of anything in the spec's
§2 ground-truth table that turned out to be wrong, and a closing ACCEPTANCE
block.
```
