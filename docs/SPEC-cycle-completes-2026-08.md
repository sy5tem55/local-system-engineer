# SPEC — let a cycle finish

> Design: Opus 5, 2026-08-08. Implementation: Sonnet 5 High. Verification: V2,
> with one V3 claim (§10). Roadmap §0 — the premise R5, R6 and half of §1b are
> gated on.
>
> Three independent defects, all proven from three consecutive runs on
> 2026-08-08. Specified together because no one of them alone lets a cycle
> finish, and all three are small.

---

## 1. The bug, measured

Three runs, same night, same machine, nothing else changed but the fixes
between them:

| Run | Result | Killed by |
|---|---|---|
| `run_1d29bdc0` 00:04Z | BLOCKED, 2 of 6 passes attempted | session guard slept 45 min |
| `run_63614781` 01:32Z | DEGRADED, 2 of 6 attempted | stale-contradiction took 36.8 min, SIGTERM |
| `run_1c8331e0` 03:04Z | DEGRADED 5/6, all 6 attempted | — first complete cycle since 08-02 |

The third run is the useful one: it is what the system does when nothing is
broken. It still produced **zero** proposals from `error-cluster`, and its
`stale-contradiction` still reported `BLOCKED` for a reason that is not a
block.

---

## 2. Defect 1 — `error-cluster` asks for one envelope and validates another

**This is the highest-value item in this spec.** `error-cluster` has been
structurally incapable of emitting a proposal since 2026-08-03.

`_ERROR_CLUSTER_SYSTEM_PROMPT` (`dream_runner.py:2048`) instructs the model:

```
Return ONLY this JSON object -- no prose, no thinking, no code fences:
{"diagnoses": [ ... ], "skill_candidates": [ ... ]}
```

The code then reads exactly those two keys — `env.get("diagnoses")` at 2099,
`env.get("skill_candidates")` at 2128.

But the call at `dream_runner.py:2091` is:

```python
env, err = request_dream_envelope(_ERROR_CLUSTER_SYSTEM_PROMPT, user_content, cfg)
```

with **no `key=` argument**, so `parse_dream_envelope` defaults to
`key="proposals"` and rejects any envelope lacking a `proposals` array — which
is every envelope the prompt asks for. The insights pass at 3533 passes its
key correctly; error-cluster does not.

Measured on `run_1c8331e0`: 14 LLM calls, **7 rejections, all
`envelope has no 'proposals' array`** — 7 clusters x 2 attempts, every one
discarded. The pass recorded `SUCCEEDED` having produced nothing.

Consequence: `668bfb1` (the `diagnosis` proposal type, 2026-08-03) has never
emitted a single proposal in production. Not because the nightly was down —
because of one missing argument.

**Design care required.** This is not a one-word fix. `parse_dream_envelope`
validates a *single* list key, and this envelope has *two* arrays, either of
which may legitimately be empty (the prompt says so explicitly: *"Zero
proposals in both arrays is a valid, expected outcome"*). Accepting an
envelope that carries `diagnoses` OR `skill_candidates` — and rejecting one
that carries neither key at all — is the actual contract. Do not settle for
`key="diagnoses"`; that silently drops a cluster that produced only a
skill-candidate.

---

## 3. Defect 2 — no per-pass wall-clock allocation

`tools/run-dream-cycle.sh:100`:

```sh
--budget-max-wall-clock-s "$remaining_seconds"
```

Every pass is handed **all** remaining cycle time. There is no allocation. A
pass that legitimately uses its budget starves every pass behind it, and the
loop's own guard at line 84 (`remaining_seconds <= 5`) then skips the rest.

On `run_63614781`, `stale-contradiction` consumed 36.8 of 45 minutes and was
SIGTERMed (`exit -15`); `error-cluster`, `patterns`, `insights` and `digest`
each got ~11 ms and were recorded `BLOCKED` with empty `error_text`, because
nothing ran.

This did not bite on `run_1c8331e0` only because `stale-contradiction`
self-limited on its 50-session budget first. That is luck, not design.

---

## 4. Defect 3 — a deliberate stop recorded as a dependency block

On `run_1c8331e0`, `stale-contradiction` finished with:

```
state=BLOCKED  error_type=DependencyBlocked
error_text="budget: session budget exhausted (50 >= 50)"
```

Budget exhaustion is not a dependency failure. `call_dream_llm`'s own
docstring already says so — *"a deliberate stop, not a failure … so a
deliberate stop is never reported to the operator as 'the dreamer failed' —
it didn't; we chose not to ask it."* `request_dream_envelope` honours that for
the `BUDGET_EXHAUSTED:` prefix; the pass-level path does not, and the operator
sees a `BLOCKED` that reads as breakage.

A pass that examined part of the corpus and stopped on budget produced a
partial-but-real result. It is `SUCCEEDED` if it emitted proposals, `NULL` if
it looked and found nothing. It is not `BLOCKED`.

---

## 5. What changed under this spec while it was being written

On 2026-08-08 the operator set llama-server to `--reasoning-format deepseek`.
This fixed a fourth defect that an earlier draft of this spec treated as its
centrepiece: the model's `<think>` block was landing unparsed in
`message.content`, running past `max_tokens`, and arriving with no closing tag
that `parse_dream_envelope`'s `<think>.*?</think>` strip could match.

Measured before: 13 of 43 calls rejected, 10 with `RAW: '<think>`.
Measured after: `think-RAW = 0` on every pass; `stale-contradiction` 1 of 22.

**Do not re-fix this.** Two hardening items remain, and they are minor:

- The three in-code suppression mechanisms (`/no_think` appended to content,
  `thinking_budget_tokens: 0`, the `<think>` strip) were all ineffective on
  this model. Probe result, 2026-08-08: only
  `chat_template_kwargs: {"enable_thinking": false}` worked. Cascade legs 1
  and 2 (node3090 llama-server, Ollama) are still unprofiled — add the field
  additively, keep the others (they may be load-bearing on those legs).
- `parse_dream_envelope` still cannot survive an *unterminated* `<think>`.
  Any model truncated mid-thought reproduces the original failure. Handle the
  unclosed case, and when it happens say so — do not report it as the generic
  `no JSON object in reply`.

---

## 6. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| error-cluster prompt keys | `diagnoses`, `skill_candidates` — `dream_runner.py:2048` |
| error-cluster envelope call | `dream_runner.py:2091`, no `key=` |
| Consumers of the envelope | `dream_runner.py:2099`, `2128` |
| Correct comparator | insights at `dream_runner.py:3533` passes its key |
| Envelope parser | `dream_runner.py:1511` `parse_dream_envelope(reply, key=...)` |
| Cycle budget line | `tools/run-dream-cycle.sh:100` |
| Pass order | dedup, stale-contradiction, error-cluster, patterns, insights, then digest |
| Cycle max | `GOETHE_DREAM_CYCLE_MAX_SECONDS`, default 2700 |
| Budget stop prefix | `BUDGET_EXHAUSTED:` — `dream_runner.py:1564` |
| Attempt states | `QUEUED RUNNING SUCCEEDED NULL BLOCKED FAILED CANCELLED` |
| Suite baseline | **806 passed, 1 skipped** |
| The 1 skip | `shutil.which("node")` misses `~/.local/bin`. node v22.22.3 IS installed; the test passes with it on PATH. Fix here — target 807/0. |

Re-probe before implementing. Three facts in the previous spec's table were
overtaken within twelve hours.

---

## 7. Hazards

### Hazard A — the two-array envelope must not become a one-array envelope
Both `diagnoses` and `skill_candidates` are real outputs and either may be
empty. A fix that accepts only one key trades a total failure for a silent
partial one, which is worse — it will look like it works.

### Hazard B — do not widen the parser for everyone
Four other callers rely on strict single-key validation. Whatever multi-key
tolerance you add must be opt-in at the call site, not the new default.

### Hazard C — per-pass budget must not SIGTERM mid-LLM-call
Keep `timeout --signal=TERM --kill-after=10s`. Apply a floor. Let a pass that
finishes early return unused time to the pool. A slice so tight that a pass
dies mid-write is worse than the starvation it replaces.

### Hazard D — reclassifying budget stops must not launder real blocks
Only the budget-exhaustion path changes. `DependencyBlocked` for dream-llm,
embedding-service, agent-command-log and incomplete-evidence stays exactly as
it is. If in doubt, leave it `BLOCKED`.

### Hazard E — do not touch what just landed
`ccbe879` (sub-pass outcomes) and `_raise_if_dependency_blocked` are three
days old and working — `run_1c8331e0` shows a BLOCKED `stale-contradiction`
that still recorded four proposals, which is that fix earning its keep. Leave
it alone.

### Hazard F — do not change llama-server flags or any node profile
The dreamer shares LUCIFER's server with interactive chat. Per-request only.

---

## 8. What to implement

1. **Fix the error-cluster envelope contract.** The call site must validate
   what the prompt asks for: an object carrying `diagnoses` and/or
   `skill_candidates`. Opt-in at the call site (Hazard B).
2. **Allocate wall clock per pass** in `run-dream-cycle.sh`: a share derived
   from passes remaining, with a floor, unused time returned to the pool.
   Digest keeps taking what is left.
3. **Reclassify budget exhaustion** at pass level: `SUCCEEDED` if proposals
   were produced, `NULL` if none, never `BLOCKED`. Carry the truncation reason
   into the summary so the operator still sees it stopped early.
4. **Hardening (§5):** add `chat_template_kwargs: {"enable_thinking": false}`
   additively in `_build_payload`; handle an unterminated `<think>` in
   `parse_dream_envelope` with a failure message that names truncation.
5. **Put `~/.local/bin` on the test PATH** so the JS syntax check runs.

---

## 9. Anti-goals

- Do **not** make `key="diagnoses"` the fix.
- Do **not** change the default validation for the other four callers.
- Do **not** touch the session-activity guard, its retry arithmetic, or
  `goethe-dream.timer` — deprioritised by the operator 2026-08-08.
- Do **not** touch `call_dream_llm`'s cascade, the breaker, or
  `_raise_if_dependency_blocked`.
- Do **not** remove `/no_think` or `thinking_budget_tokens`.
- Do **not** change llama-server launch flags or node profiles.
- Do **not** raise `max_tokens` as a thinking fix.

---

## 10. Tests

1. An envelope with only `diagnoses` populated → accepted, diagnoses staged.
   **Load-bearing.**
2. An envelope with only `skill_candidates` populated → accepted.
   **Load-bearing — Hazard A.**
3. An envelope with both keys present but both empty → accepted as a valid
   zero-result, not a parse failure.
4. An envelope with neither key → rejected, with a message naming the keys
   that were expected.
5. The other four callers still reject an envelope lacking their own key.
   **Load-bearing — Hazard B.**
6. Per-pass budget: with N passes and a known cycle length, pass 1 gets
   ~`cycle/N`, not the whole cycle; an early finisher returns its remainder.
   **Load-bearing.**
7. Per-pass slice never falls below the floor; the last pass still gets what
   is genuinely left.
8. Budget exhaustion with proposals → `SUCCEEDED`; without → `NULL`; neither
   is `BLOCKED`, and the truncation reason survives into the summary.
9. A real dependency failure is still `BLOCKED` (Hazard D).
10. `_build_payload(no_think=True)` carries the new field **and** still
    carries `/no_think` and `thinking_budget_tokens`.
11. `parse_dream_envelope` handles an unterminated `<think>`; the failure
    message names truncation, not "no JSON object".
12. The JS syntax check runs rather than skipping.

**Break tests 1, 6 and 8, confirm red, restore.** Report the exact failure
text, and diff against the pre-break state to prove the restore is clean.

---

## 11. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py
bash -n tools/run-dream-cycle.sh
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **806 passed, 1 skipped** → target **807 passed, 0 skipped**.
Pre-existing ruff on `dream_runner.py` is **18**; it must not increase.

---

## 12. Verification — V2, plus one V3 claim

V2 for the code. **V3 on the claim this spec exists to make:** run a real
standard cycle and paste, verbatim:

- the per-pass table (pass, state, started, finished, exit code), and
- `error-cluster`'s rejection count —
  `grep -c "attempt . rejected"` against `grep -c "DREAM_LLM_URL healthy"`
  on its attempt log, and
- the proposal types the run produced, from `traum-state.db`.

**Acceptance is behavioural:** all six passes attempted, and **at least one
`diagnosis` proposal reaching the Human Gate** — the first in production since
the type shipped on 2026-08-03. If the cycle still cannot finish, say so
plainly and report what consumed it. A partial result honestly reported beats
a green suite.

---

## 13. Report

`docs/reports/2026-08-DD-cycle-completes.md`, committed, with an ACCEPTANCE
block, then `scripts/verify-handover.py --run-tests`. State which claims are
runtime-proven and which are test-only.

---

## 14. Context

- Runs this spec is built on: `run_1d29bdc0`, `run_63614781`, `run_1c8331e0`
  (all 2026-08-08, `/opt/local-se/dreams/traum-state.db`).
- The type that has never fired: `668bfb1`.
- Prior envelope fix, same function: `41bcc3e`.
- Just landed, do not disturb: `ccbe879`.
- Roadmap: `docs/ROADMAP-2026-08.md` §0, §3 (R4).
- Conventions: `docs/WORKFLOW-thread-handover.md`,
  `docs/WORKFLOW-roadmap-execution.md`.
