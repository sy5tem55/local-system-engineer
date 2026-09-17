# TRAUM Thread 4 — Closing the Retrieval-Miss and Code-Drift Blind Spots

**Status:** proposed, not implemented
**Date:** 2026-08-24
**Trigger:** the planner reasoning-runaway defect (KB `c4474ca6d69a5a85`)
**Related:** `DESIGN.md` §2 (invariants), §6.2 (proposal shape), §7 (auto-apply), §8 (prompt-rule merge)

---

## 1. What happened

A defect in `tools/goethe_planner.py` — sending `thinking_budget_tokens: 0`, a
field llama.cpp silently discards — caused every planner call from v0.3.3
onward to run with reasoning enabled, burn its entire 8192-token budget on the
`<think>` trace, and return `finish_reason=length` with `content=""`.

The fix was recorded in the KB on **2026-06-07** (doc `6df1c6812bb08631`),
which states the mechanism, the failure signature, and the correct parameter
verbatim. `tools/dream_runner.py` adopted that fix for its own payload on
2026-08-08. It never reached the planner.

Cost: roughly eleven weeks of intermittent planner failure, two full debugging
sessions spent on clock-drift forensics and socket archaeology, and a proposed
"fix" (`max_tokens` 8192→16384, ceiling 600→900s) that would have added ~700s
of GPU hold to every planner call without addressing the cause.

**TRAUM ran throughout this period and never surfaced it.** This document
explains why that was structurally guaranteed, and what to change.

---

## 2. Why TRAUM could not have caught it

Three independent causes. Each is individually sufficient.

### 2.1 The contradiction pass only inspects KB docs a session already retrieved

`run_pass_stale_contradiction`'s demote sub-pass, per the module's own
catalogue:

> for each undreamed session, doc_ids surfaced via `search_kb` **this session**
> are parsed straight out of search_kb's own return text … and cross-checked
> (model judges) against that session's OTHER tool results

The detector answers *"was the KB doc you used wrong?"*

The failure was *"there was a KB doc you never looked at."*

Doc `6df1c68` was never surfaced by `search_kb` in any planner-timeout session,
because nobody searched for it. It was therefore outside the candidate set of
the only pass that could have flagged it. **TRAUM has a contradiction detector
and no non-retrieval detector.** This is the primary cause.

### 2.2 TRAUM cannot read source code

`DreamConfig`'s corpus is exactly: `episode_dir`, `es_url` (lse-kb), `tasks_db`,
`agent_log`. Nothing else. (The many `tools/goethe.py:NNNN` references inside
`dream_runner.py` are citations in docstrings, not reads.)

The contradiction here was between a **KB fact** and a **line of code**. That
comparison is not expressible over TRAUM's corpus at any coverage level or
sensitivity setting.

### 2.3 Nothing TRAUM proposes ever lands

Measured 2026-08-24:

| metric | value |
|---|---|
| `applied.jsonl` | **0 lines** |
| `rejected.jsonl` | 85 (demote 51, dedup 19, skill-candidate 12, reverify 3) |
| pending at human gate | 11, oldest 2026-08-09 (15 days) |
| `DREAM_AUTO_APPLY` | empty (by design) |

The rejections are mostly **not** human judgment — only 12 are `human
declined`. The largest bucket is the apply-time invariant
`doc_id '<id>' not found in lse-kb at apply time (deleted? renamed?)`.
Proposals are rotting between generation and apply, most likely because
`index_to_kb`'s dedup path *updates* existing entries and re-embedding
backfills reassign `_id`s, invalidating doc_ids captured at generation time.

So even a perfect detection would have produced a proposal that died in the
queue. **This is the multiplier: without it, §4 and §5 ship detectors whose
output goes nowhere.**

### 2.4 Contributing conditions

- `stale-contradiction` has consumed **250 of ~623** sessions (40%) — the
  lowest coverage of any pass, and the one that matters most here.
  (`dedup` 591, `error-cluster` 612, `insights` 562+50, `patterns` 623.)
- `goethe-dream.service` is `not-found`; the timer is inactive. Runs are
  GUI-triggered only, and per KB `c31d93765675fbde` GUI runs skip the R1 wake
  preflight, `finalize-cycle`, and `expire-stale`.
- The last cycle (2026-08-22) ran `dedup` alone and produced zero proposals.

---

## 3. Constraints any fix must respect

Carried from `DESIGN.md` §2. These are not negotiable and the work below is
shaped around them.

1. **Dreams propose; gates apply.** No new pass may write to ES or to a source
   file. `dream_runner.py` stays read-only, full stop.
2. **Never raise quality, never write `source_tier=ground_truth`, never touch
   quarantined docs** except to propose deletion.
3. **Verbatim-quote validation is code-enforced**, not prompted for. Any new
   proposal type carrying evidence must re-check that each quote is a real
   substring of its claimed source and ≥20 chars.
4. **Null-result discipline (PH3-2).** Every `run_pass_*()` returns
   `(proposals, narrative, null_record)` and must distinguish `looked=True`
   ("nothing there") from `looked=False` ("didn't look").
5. **No dream-of-dreams.** Episode selection excludes the dreamer's own
   sessions.
6. **`prompt-rule` may only ever target `prompts/learned-rules.md`**
   (`LEARNED_RULES_TARGET`), which is a staging area, never a live prompt.

---

## 4. P1 — `retrieval-miss` pass

The smallest change that would have caught this exact defect.

### Detection

For each undreamed session:

1. **Establish a failure signature.** Sources, all already in corpus:
   - episodes with `exit_class in {error, timeout}` (measured: 41 timeouts /
     11 errors in the last three days alone),
   - `tasks_db` rows with `status in {abandoned, failed}`,
   - repeated near-identical `execute_command` retries in `agent_log`.
2. **Collect what the session actually retrieved** — parse `doc_id=` out of
   `result_truncated` for episodes where `tool == "search_kb"`. This is the
   same extraction `stale-contradiction` already performs; reuse it.
3. **Ask the KB what it would have offered.** Run the failure signature
   through the live retrieval path at the production `min_score`.
4. **Diff.** A doc at `quality >= CONTRADICTION_MIN_QUALITY` (0.6) that the
   retrieval returns but the session never surfaced is a candidate.
5. **Judge relevance.** One LLM call per candidate: *"would this doc have
   shortened or prevented this failure?"* Requires a verbatim quote from the
   doc and a verbatim quote from the failure evidence, both validated per §3.3.

### Output

Type `retrieval-miss`. Two shapes, chosen by the judge:

- `call: record_outcome` on the *session's* narrative is wrong — the doc was
  fine, so do not demote it. Instead the default carrier is
  `call: index_to_kb` on a short cross-reference note linking the failure
  signature to the doc, raising the chance the next search finds it.
- Where the pattern recurs across ≥2 sessions, escalate to
  `call: skill_record` (a retrieval habit) or `type: prompt-rule` targeting
  `LEARNED_RULES_TARGET` — e.g. *"before diagnosing an LLM-call failure,
  `search_kb` the exact failure signature."*

### Acceptance test (the important one)

Replay the real session `sess-1164260-7e0e1e420bc0` (today's failing planner
run, task `ce101736`) through the pass and assert it emits a `retrieval-miss`
naming doc `6df1c6812bb08631`. This is a regression test against real
historical data, not a synthetic fixture. If it does not fire, the pass does
not ship.

### Registration checklist

`KNOWN_PROPOSAL_TYPES` += `retrieval-miss` · `PASS_FUNCS` += the new pass ·
`dream_apply.py` dispatch branch · null-record wiring · digest rendering.

### Risk

False positives — the KB will almost always contain *something* tangentially
related to any failure. Mitigation: the ≥0.6 quality bar, the mandatory
verbatim-quote pair, and starting the judge prompt biased toward rejection.
Calibrate on a backfill before enabling in the standard cycle.

---

## 5. P2 — `code-drift` pass

Highest value, highest noise risk. Ships last.

### Detection

1. **Extend the corpus** with a repo root in `DreamConfig` (read-only).
2. **Extract negative facts from lse-kb** — claims of the form *"X does not
   work"*, *"never use X"*, *"X is silently ignored"*, *"use Y instead"*.
   Scope tightly to **API-parameter and config-key claims** in the first
   version; broader natural-language negatives are a later increment.
   Each extracted fact yields a concrete **forbidden token** (`X`) and a
   **replacement token** (`Y`).
3. **Grep the tree** for the forbidden token. Deterministic, no LLM.
4. A hit in live code (excluding `.backups/`, comments, and docstrings) is a
   proposal.

On this defect: doc `6df1c68` yields forbidden `reasoning_budget` /
`/no_think`, replacement `chat_template_kwargs`. The grep finds
`goethe_planner.py:188`, `:278`, and the three `/no_think` sites.

### Output

Type `code-drift`, `call: record_error` or a new advisory carrier. **It must
not propose a patch.** The deliverable is a flagged divergence with file, line,
the KB quote, and the doc_id — a human writes the fix. This keeps invariant
§3.1 intact.

### Known false-positive class, already observed

A naive grep flags `tools/goethe_node.py:141`
`"reasoning_budget": "--reasoning-budget"` — which is a **legitimate
llama-server CLI launch flag**, not a request body key. The extractor must
therefore carry the *context* in which a token is forbidden (request payload vs
process argv), or the pass will cry wolf on its first run. This single example
should become a fixture in `tests/test_dream_code_drift.py`.

### Acceptance test

Against the pre-fix commit (`925561b5…`, backup retained at
`/tmp/lse/backups/goethe_planner.py.pre-nothink-20260824`), the pass must flag
`goethe_planner.py` and must NOT flag `goethe_node.py`.

---

## 6. P3 — Repair the delivery pipeline

Do this **first**. It gates everything above.

1. **Root-cause the stale-`doc_id` invariant failures.** Confirm the
   `index_to_kb` dedup-update / re-embed hypothesis by checking whether the
   rejected doc_ids exist under different `_id`s with matching content.
   Then either (a) re-resolve targets at apply time by content hash or title,
   or (b) shorten generate→apply latency so drift has no window, or (c) make
   `check_target_cas` degrade to a re-resolve rather than a hard reject.
2. **Make the gate queue visible.** Surface pending count *and oldest-age* in
   `latest-digest.md`. Eleven items aging fifteen days should be loud.
3. **Earn the first auto-apply.** `reverify` is already treated as
   `safe_probe` in `dream_apply.py` and is a read-only `kb_verify` probe.
   Run the `DESIGN.md` §2 row-2 protocol — two consecutive weeks,
   zero rejected-in-hindsight — then add it to `DREAM_AUTO_APPLY`.

Acceptance: `applied.jsonl` is non-empty and the invariant-failure bucket in
`rejected.jsonl` stops growing.

---

## 7. P4 — Coverage and scheduling

- Backfill `stale-contradiction` from 250/623 to parity with the other passes.
- Install the systemd service + timer running the **full** pass set, so cycles
  stop skipping preflight/finalize/expire-stale. `tests/test_dream_service_units.py`
  already exists — extend it rather than writing new unit-file tests.

---

## 8. Phasing, effort, and ETA

Sequenced so the highest-leverage work lands first and each phase is
independently shippable.

| Phase | Work | Est. sessions | Cumulative |
|---|---|---|---|
| **1** | P3 pipeline repair — diagnose stale doc_ids, fix re-resolution, digest queue age | 1–1.5 | 1.5 |
| **2** | P4 scheduling + `stale-contradiction` backfill | 0.5–1 | 2.5 |
| **3** | P1 `retrieval-miss` — pass, validator, dispatch, replay test | 1.5–2 | 4.5 |
| **4** | P1 calibration on backfill; tune judge bias; enable in cycle | 0.5–1 | 5.5 |
| **5** | P2 `code-drift` — corpus extension, extractor, grep engine, tests | 2–3 | 8.5 |
| **6** | `reverify` auto-apply earn-in (2 calendar weeks, unattended) | 0 active | 8.5 |

**Full deliverable: 6–9 working sessions.** At one session per day, **7–10
calendar days**; the `reverify` earn-in in phase 6 runs in parallel and
completes two weeks after phase 1 lands.

**The part that would have caught this specific defect — phases 1 and 3 —
is 3–3.5 sessions, or roughly 4 days.**

These are estimates on unfamiliar-but-well-documented code with an existing
test harness and clear extension points (`PASS_FUNCS`, `KNOWN_PROPOSAL_TYPES`,
a per-pass test file convention). The largest uncertainty is P2's extractor
precision, which is why it is last and why its noise budget is called out
explicitly in §5.

## 9. Non-goals

- TRAUM proposing code patches. It flags divergence; humans fix.
- Loading `learned-rules.md` into a live prompt. It stays a staging area.
- Widening `DREAM_AUTO_APPLY` beyond `reverify` in this thread.
- Retro-dreaming the 560-session backlog wholesale — the passes are calibrated
  on samples first.
