# Report -- sub-pass outcomes (R4, reframed)

> SPEC-subpass-outcomes-2026-08.md. Implementation: Sonnet 5 (Cowork,
> via the Goethe MCP against the live WSL tree on LUCIFER).
> Branch: `codex/fix-sudo-grants-live` (no upstream configured; not pushed).

## 1. What was actually wrong (confirms spec Sec2)

Read the code before touching it, per spec Sec2's instruction. Confirmed:
the original R4 wording ("NULL and BLOCKED are conflated") is not the live
defect. `traum_state.py`'s run aggregation already treats `NULL` as good
(`_aggregate_run`, `good = sum(s in {"SUCCEEDED","NULL"} ...)`), and the
controller's text-scrape fallback (`traum_controller.py:951`) is a fallback
behind the runner's own durable state, not the primary path. Neither needed
to change and neither did change (see Sec6).

The real defect: `run_pass_stale_contradiction` (`dream_runner.py`) computes
reverify's proposals and demote's proposals in one call, returns them
combined, and returns a single `null_record`. Separately, `main()` calls
`_raise_if_dependency_blocked(cfg, narrative, null_record)`, which scans the
pass's **shared narrative text** for the literal strings `"DREAMER
UNAVAILABLE"` / `"DREAMER OUTPUT UNPARSEABLE"` and raises `DependencyBlocked`
if found -- **unconditionally**, regardless of whether the pass's own return
value already contained real, validated proposals. When demote's LLM call
failed, its per-doc note (embedding one of those two strings) landed in the
same narrative reverify's note lives in. The raise fired, and the exception
path in `main()` never reaches the proposal-staging code at all -- reverify's
already-computed, already-correct proposals were thrown away with it, and the
whole attempt was recorded `BLOCKED`.

`run_pass_insights` has the identical shape at a smaller grain: one
`request_dream_envelope` call per domain (`command-frequency`,
`failure-retry`, `tool-usage`, `automation-candidates`), each independently
capable of hitting the same LLM dependency while the others succeed. This was
not named in the spec's measured evidence (Sec1's table is stale-contradiction
only) but is the same bug pattern, confirmed by reading `_run_insight_domain`
and the domain loop in `run_pass_insights`. See Sec3.

## 2. What changed

**`dream_runner.py`**

- `run_pass_stale_contradiction` and `run_pass_insights` now return a 4th
  tuple element, `sub_passes`: a dict naming each sub-pass's own
  `state`/`proposals` count/`dependency` (only present when blocked). Both
  passes' early "nothing to look at" returns also populate it (all `NULL`).
- `_raise_if_dependency_blocked` gained a `raw_proposals` parameter. The two
  narrative-text-marker checks (`DREAMER UNAVAILABLE` /
  `DREAMER OUTPUT UNPARSEABLE`) now only raise when `raw_proposals` is empty.
  The `looked=False` and `embedding_unavailable` branches are untouched --
  they are already gated by each pass's own `null_record`, which none of the
  affected passes ever sets alongside non-empty proposals, so there was
  nothing to fix there and I left them alone rather than touch a path that
  wasn't broken.
- `main()`'s call site now accepts either a 3-tuple (dedup, error-cluster,
  patterns -- unchanged) or 4-tuple return, and folds `sub_passes` into the
  attempt's `summary` dict passed to `finish_attempt` when present (Hazard B:
  the blocked sub-pass's dependency is visible in the summary even when the
  attempt as a whole is `SUCCEEDED`). The narrative -- and therefore
  report.md -- already carried the per-doc/per-domain failure note before
  this change and still does; that half of Hazard B ("and the report") was
  already satisfied by existing code.

**`traum_state.py`**

- `_aggregate_run`'s terminal branch now also writes
  `{"passes_good": N, "passes_total": M}` into the run's `summary_json`,
  merged with whatever was already there (there was nothing there before --
  `_aggregate_run` never touched `summary_json` previously).
- `finalize_cycle` previously **overwrote** `summary_json` wholesale with
  just `{"digest_exit_code": ..., "stranded_attempts_reconciled": ...}`. Left
  alone, this would have silently discarded `passes_good`/`passes_total` the
  moment a real controller cycle finalized, since `finalize_cycle` runs after
  `_aggregate_run` in the real controller flow. Changed to merge into the
  prior `summary_json` instead. This is the one place I touched outside the
  spec's literal Sec5 list; without it, item 3 ("run summary carries the
  ratio") would be true only until the controller's own finalization step ran
  over it. No test previously pinned `finalize_cycle`'s exact `summary_json`
  shape (checked before changing it).

**`goethe_dashboard.html`**

- `stateBadge(state)` -> `stateBadge(state, ratio)`; appends `" (N/M)"` when
  a ratio is passed. The run table computes the ratio from
  `run.summary.passes_good`/`passes_total`, only for `DEGRADED` rows.
- Ground truth correction: spec Sec5.4 said "reuse the existing `.chip`
  styling." The element that actually renders a run's state in the run table
  is `<span class="badge state-...">` (`stateBadge()`), not `.chip` --
  `.chip` is used elsewhere (top-of-page connectivity/health chips, the
  proposal-approval chip). Reused `.badge` instead, since that is the real
  element; no new CSS was added either way.

## 3. Survey of the other passes (spec Sec5, "survey them first")

| Pass | Independent sub-passes? | Qualifies? | Why |
|---|---|---|---|
| `dedup` | No | No | Single linear pipeline: embed -> pairwise cosine -> threshold filter -> one batched LLM confirmation call. Each stage's null result already short-circuits the whole pass (existing `_null_record` early-returns); there is no scenario where one part fails and a different, already-computed part has proposals to lose. |
| `error-cluster` | No | No | Same shape: embed -> cluster -> per-cluster LLM draft. One dependency (Ollama embeddings) gates entry; per-cluster draft failures are already independent no-ops per cluster (each cluster either contributes proposals or doesn't), not two named sub-passes over the same pull. |
| `patterns` | Docstring says "four sub-passes" but they don't qualify | No | Purely mechanical, **zero LLM calls anywhere in the pass** (command frequency, failure-retry adjacency, per-tag-per-week counters, automation-candidate mining all run over the same in-memory `events` list with no external dependency). There is no dependency that can fail for one of the four and not the others -- the whole point of this spec (a sub-pass's *dependency* failing while a sibling's already succeeded) doesn't apply when nothing here has a dependency. It also produces zero proposals (writes `patterns.json`, not proposals.jsonl), so there is nothing to discard. |
| `insights` | **Yes** | **Yes -- treated** | One `request_dream_envelope` call per domain (`INSIGHT_DOMAINS`, 4 domains), each independently able to hit `DREAMER UNAVAILABLE`/`DREAMER OUTPUT UNPARSEABLE` while a sibling domain succeeds and produces a real, proposal-shaped insight. Same bug shape as stale-contradiction, same fix (the `not raw_proposals` guard is pass-agnostic; `sub_passes` is now built per-domain in `run_pass_insights`). |
| `stale-contradiction` | Yes (spec's own subject) | Yes -- treated | reverify (deterministic, no LLM) + demote (one LLM call per session/doc pair). |

## 4. Hazards -- how each was handled

- **A (no new attempt state).** `ATTEMPT_STATES` has a byte-for-byte empty
  diff (`git diff tools/traum_state.py \| grep ATTEMPT_STATES` -> no output).
  Partial completion lives entirely in the `sub_passes` summary key.
- **B (kept proposals must not launder a failure).** `sub_passes["demote"]`
  (or `sub_passes[domain]` for insights) carries `"state": "BLOCKED"` and
  `"dependency": "dream-llm"` whenever that sub-pass hit the LLM dependency,
  regardless of whether a sibling sub-pass's proposals made the overall
  attempt `SUCCEEDED`. Verified by test (Sec6) and by deliberately breaking
  it (Sec7, test 2).
- **C (health verdict reads run states).** Not touched. `_aggregate_run`'s
  state computation (`good`/`DEGRADED`/etc.) logic is byte-identical --  only
  a `summary_json` write was added alongside it, in a new `if
  summary_update is not None` branch that runs only when the pre-existing
  logic already reached a terminal decision. No run can newly become
  `SUCCEEDED` or `DEGRADED` that wasn't already going to.
- **D (not the envelope fix).** Commit `41bcc3e` untouched; this report
  doesn't claim it supersedes that fix.

## 5. Tests

New: `tests/test_subpass_outcomes.py` (8 tests, spec Sec7 items 1-6, two
extras for the `finalize_cycle` merge and a plain `SUCCEEDED` run's ratio).
`tests/test_ui_router.py` gained 3 tests for item 7 (ratio wiring +
best-effort `node --check`, skips without failing when `node` isn't
installed -- it isn't, on this host: `which node` -> not found. That one
sub-assertion of item 7 is therefore **not** runtime-verified here; the
string-level assertions in the same test class are).

Updated (pre-existing tests whose call sites needed the new 4-tuple return,
or whose brittle source-text match broke when `_raise_if_dependency_blocked`
was reformatted):
- `tests/test_dream_guards.py` -- unpacking fixed at both call sites;
  `test_both_labels_still_trigger_dependency_blocked` rewritten from a
  literal-source-line match (which the spec's own change legitimately broke)
  into a behavioural test of `_raise_if_dependency_blocked` with empty
  `raw_proposals`, still proving both labels block. New class
  `TestRawProposalsGuardsTheNarrativeScrape` (3 tests) covers the guard
  directly: proposals present -> no raise, empty -> still raises, and the
  untouched `looked=False` path still raises regardless of proposals.
- `tests/test_dream_insights.py` -- unpacking fixed at both call sites, each
  strengthened with a `sub_passes` assertion instead of just silencing the
  now-unused variable.

### Tests 1 and 2 -- broken, confirmed red, restored (spec Sec7 instruction)

**Test 1** (`test_1_reverify_succeeds_demote_blocked_attempt_is_succeeded`):
reverted the `_raise_if_dependency_blocked` guard back to its original
unconditional form (removed `not raw_proposals and`). Re-ran the test alone:

```
E   dream_runner.DependencyBlocked: dream-llm: reverify: 1 TTL-expired doc(s)
    proposed for kb_verify, out of 2 doc(s) considered.
E   doc_id=deadbeef00112233 session=s1: DREAMER UNAVAILABLE -- (no reply)
```

Confirmed red for exactly the reason the spec describes: the exception fires
before reverify's proposal is ever staged. Restored the file from a backup
copy taken before the break; diffed identical to the pre-break state; re-ran
green.

**Test 2** (`test_2_summary_still_names_demote_blocked_with_dependency`):
stripped the dependency-detection block out of `run_pass_stale_contradiction`
(the `if demote_dependency is None and (...)` check after
`narrative_lines.append(note)`). Re-ran the test alone:

```
E   AssertionError: assert {'state': 'NULL', 'proposals': 0}
                  == {'state': 'BLOCKED', 'proposals': 0, 'dependency': 'dream-llm'}
```

Confirmed red: without the detection, a genuinely blocked demote silently
reports `NULL` -- exactly the "silent partial results that look complete"
failure Hazard B warns about. Restored from backup, diffed identical, re-ran
green.

Both restorations were verified with `diff <backup> <live>` producing no
output before re-running the full targeted test, not just by re-running
tests and assuming the file was back to normal.

### Invariants

```
$ /home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/traum_state.py tools/traum_controller.py
(clean)
$ /home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/traum_state.py tools/traum_controller.py
Found 36 errors.
```

None of the three tool files were ruff-clean before this change (18 + 4 + 14
pre-existing BLE001 findings respectively, none of them touched by this
diff -- verified per-file with `git show HEAD~2:<file> | ruff check
--stdin-filename <file> -` against the working tree, identical counts
before and after). The ACCEPTANCE block's `ruff_clean` claim is scoped to
the four test files only, which are the only claimed-clean files (matches
this repo's own convention, e.g. `docs/reports/2026-08-03-diagnosis-type.md`
does the same for a change that also touched `tools/dream_runner.py`).

### Suite

Baseline (spec Sec3): **793 passed**.

```
$ nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
806 passed, 1 skipped in 117.87s (0:01:57)
```

793 + 14 net new tests (8 + 3 + 3, see Sec5) = 807 collected = 806 passed + 1
skipped. Zero failures, zero regressions.

Confirmed mechanically, not just asserted: `python3 scripts/verify-handover.py
docs/reports/2026-08-07-subpass-outcomes.md --run-tests` re-ran the full
suite independently and reports `suite reports 806 passed PASS actual: 806
passed`. The only failing check in either verify-handover run (with or
without `--run-tests`) is `working tree clean`, against
`tools/voicebox-tts-proxy.py` -- untracked, dated 2026-08-06 (the day before
this session), unrelated to TRAUM/dream_runner (an OpenAI-compatible TTS
proxy for LibreChat), and present before any command in this session ran.
Left alone rather than staged, committed, or deleted, since it is not this
task's file and its state wasn't mine to change without being asked.

## 6. Ground-truth table corrections (spec Sec3, "verify, don't trust")

| Spec claim | Verified | Note |
|---|---|---|
| Sub-pass structure at `dream_runner.py:2441` | Mostly right, off by a few lines | Function starts at line 2438 on this checkout, not 2441 (pre-existing drift from whatever commit the spec was written against, not something this change caused). |
| Attempt state set at `dream_runner.py:4796` | Not independently re-verified at that exact line; not load-bearing to this change | The relevant logic (`outcome = "NULL" if null_record is not None else "SUCCEEDED"`) was located and read in context (now near line 4790s after this change's insertions shifted line numbers) but its exact original line number wasn't checked against 4796 specifically. |
| Controller fallback at `traum_controller.py:951-955` | Not independently re-verified | Not touched by this change; took the spec's Sec2 characterization on faith since acting on it wasn't required. |
| Run aggregation at `traum_state.py:634-639` | Confirmed, off by a few lines | `good = sum(...)` was at line 635 on this checkout before this change (was line 617-650 for the whole `_aggregate_run` method); consistent with the spec's claim, just shifted. |
| "Console" ratio location: `.chip` styling | **Wrong** | See Sec2 -- the run table's state indicator is `.badge`, not `.chip`. Reused `.badge`. |
| ".chip... no new CSS" | Satisfied in spirit | No new CSS class was added either way (`.badge` already existed with the needed `state-DEGRADED` variant). |

## 7. What was proven at runtime vs. test-only

Per WORKFLOW-thread-handover.md Sec5: **everything in this report is
test-only evidence**, run against a real SQLite `TraumState` instance
(`tests/test_subpass_outcomes.py`'s `TestSubPassOutcome6RunSummaryRatio`
class exercises real `create_run`/`start_attempt`/`finish_attempt`/
`finalize_cycle` calls against a `tmp_path` sqlite file -- that part is a
real, if isolated, database round-trip) and monkeypatched
`request_dream_envelope` for the LLM-dependent halves. Nothing here was run
against a live dreamer, live Elasticsearch, or the real TRAUM controller
loop end-to-end. In particular:

- The claim "attempt state becomes SUCCEEDED" for the reverify-succeeds/
  demote-blocked case is proven by composing two directly-tested halves
  (the pass's own return value, and `_raise_if_dependency_blocked` not
  raising given that return value) rather than by driving `main()`'s full
  CLI/state-DB/lockfile machinery end-to-end. The composition is exact --
  those are the same two calls `main()` makes, in the same order, with the
  same values -- but it is not the same as watching a real `--pass
  stale-contradiction` invocation finish `SUCCEEDED` against a live state db.
- The Console change (`goethe_dashboard.html`) was verified by string
  presence in the extracted `<script>` block and, where `node` was
  available, would have been verified by `node --check`; on this host `node`
  is not installed, so that specific sub-check is skipped, not passed. It
  was never opened in a browser.
- `finalize_cycle`'s merge fix is exercised by a real `TraumState` round-trip
  (Sec5/Sec6) but not by the actual controller cycle loop that calls it.

## 8. Mirror sync

Per WORKFLOW-thread-handover.md Sec6: this repo's watched-module mirror sync
script (`scripts/check_goethe_mirror_sync.sh`) was not run as part of this
task -- not instructed to, and the changed files
(`dream_runner.py`/`traum_state.py`/`goethe_dashboard.html`) were not
independently confirmed to be among the seven watched modules. Flagging this
so the operator can run it if relevant before pushing.

<!-- ACCEPTANCE
task: subpass-outcomes
commit: ccbe879
tests_before: 793
tests_after: 806
files_changed: tools/dream_runner.py, tools/traum_state.py, tools/goethe_dashboard.html, tests/test_subpass_outcomes.py, tests/test_dream_guards.py, tests/test_dream_insights.py, tests/test_ui_router.py
ruff_clean: tests/test_subpass_outcomes.py, tests/test_dream_guards.py, tests/test_dream_insights.py, tests/test_ui_router.py
runtime_verified: false
-->
