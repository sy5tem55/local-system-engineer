# Handover report — the `diagnosis` proposal type

> Implements `docs/SPEC-diagnosis-proposal-type-2026-08.md`. Report format
> per `docs/WORKFLOW-thread-handover.md` §1b/§4. Commit `668bfb1`.

## 1. The task

`error-cluster` emitted `skill-candidate` for every pattern it found, even
when the pattern was a triggered failure signature (a diagnosis) rather
than a repeatable procedure a session would choose to run (a skill). Six
proposals pending 2026-08-03 and one already-recorded skill
(`bd0a122cd97581bb`, the MCP `CancelledError` pattern) were mis-typed this
way. The spec's fix: extend `record_error` with `interpretation` and
`anti_response` fields, add a `diagnosis` proposal type routed by two
tests (§1), and make `error-cluster` route both ways instead of defaulting
every cluster to `skill-candidate`.

## 2. Ground truth — verified, with two corrections

Verified by reading code and querying the live cluster (ES on
`127.0.0.1:9200`, `traum-state.db`), not assumed:

- `record_error(error_text, context, resolution)` — `tools/goethe_kb.py:664`
  (line moved slightly from the spec's `:660` after an unrelated prior edit
  in this session; same function).
- `lse-errors-1024`, 62 docs before this change — confirmed reachable.
- `KNOWN_PROPOSAL_TYPES`, `validate_proposal_shape`, `_SKILL_CANDIDATE_SYSTEM_PROMPT`,
  `_draft_skill_candidate`, `run_pass_error_cluster` all matched the spec's
  description.
- Tool-count invariant: there is no test literally asserting `== 39`.
  `tests/test_docstring_mcp_truncation.py::_load_tools()` derives the count
  dynamically via `inspect.getmembers` over `Tools`'s public methods with
  real params. Since `record_error` keeps its method name and only gains
  optional kwargs, the count is unaffected by construction — nothing to
  assert against 39 specifically, the mechanism itself is the guarantee.

**Two corrections to the spec's ground-truth table:**

1. The spec says the CancelledError skill's `source_tier=verified`. Live
   query of `lse-skills` (`skill_id=Local System Engineer/survive-mcp-
   cancellederror-on-long-running-execute-command-c...`, doc `bd0a122cd97581bb`)
   shows **`source_tier=inferred`**, quality `0.40` (matches). The "despite
   verified tier" framing in spec §1 doesn't hold; "despite quality 0.40 on
   an inferred-tier record that reads like it should have scored higher"
   is what the data actually shows. Doesn't change the implementation.
2. The spec calls the six proposals "pending" as of 2026-08-03. By the time
   this thread started, all six had already been triaged by a prior
   session: state `REJECTED`, reason `"Diagnosis, not a skill — triggered
   rather than initiated. Awaiting the diagnosis proposal type (SPEC-
   diagnosis-proposal-type-2026-08). Payload retained for re-issue"`,
   rejected between `2026-08-03T13:57:22Z` and `13:57:34Z`. They are
   parked, not live-pending, but the disposal instruction is identical:
   leave them, list them, do not auto-migrate (§6 below).

## 3. Hazards — how each was handled

- **Hazard A (smuggling fields into free text).** `interpretation` and
  `anti_response` are real ES fields on the `record_error` doc, never
  concatenated into `resolution`. Verified by
  `test_new_fields_persist_and_are_retrievable`, which asserts the
  interpretation/anti_response text does NOT appear inside `resolution`.
- **Hazard B (`anti_response` won't be volunteered).** The error-cluster
  prompt (`_ERROR_CLUSTER_SYSTEM_PROMPT`) states this explicitly: *"the
  model will not volunteer it unless asked directly"*, and asks for the
  wrong/tempting response by name. Verified by
  `TestErrorClusterPromptAsksForAntiResponse`.
- **Hazard C (dream-infra provenance boundary on `lse-errors-1024`).**
  Turned out to be satisfied **structurally, with no new code needed**:
  `record_crash_error` (dream_runner.py) never writes an `embedding` field
  on its crash docs — by its own docstring, it "deliberately skips
  goethe.py's embedding-based KNN near-duplicate check." `record_error`'s
  duplicate search is a **kNN** search on the `embedding` field. A
  document with no `embedding` field cannot surface as a kNN hit, so
  `record_error` can never find, and therefore never merge into, a
  dream-infra crash doc — regardless of text similarity. Proven (not just
  argued) in `TestDreamInfraBoundary::test_record_error_diagnosis_never_
  carries_dream_infra_provenance`: a crash doc and a diagnosis doc are
  created against the *same* fake ES store, and both land as two
  independent documents; the diagnosis doc never carries
  `provenance="dream-infra"` because that literal only exists inside
  `record_crash_error`, a function `record_error` never calls.
- **Hazard D (auto-migration).** Not touched. See §6.

## 4. What was implemented

1. `tools/goethe_kb.py` — `record_error` gains `interpretation: str = ""`,
   `anti_response: str = ""`. New-doc path always writes both fields
   (empty string default, additive/dynamic-mapping-safe for the existing
   62 docs). Repeat-hit (kNN dedup) path only overwrites a field if the
   call actually supplied a non-empty value, so an old-style 3-arg call
   re-hitting an existing diagnosis cannot blank its interpretation.
2. `tools/dream_runner.py`:
   - `KNOWN_PROPOSAL_TYPES` gains `"diagnosis"`.
   - `validate_proposal_shape` rejects a `diagnosis` proposal whose
     `args.interpretation` is missing/blank; does **not** require
     `anti_response`.
   - `_SKILL_CANDIDATE_SYSTEM_PROMPT` → `_ERROR_CLUSTER_SYSTEM_PROMPT`:
     states both routing tests from spec §1, asks for `anti_response`
     explicitly with the reasoning spelled out, and returns two arrays
     (`diagnoses`, `skill_candidates`) instead of one.
   - `_draft_skill_candidate` → `_draft_error_cluster_proposals`: same one
     `request_dream_envelope()` call, now builds both proposal types from
     the same response, each independently filtered for completeness
     (diagnosis requires error_text/context/interpretation/resolution/why;
     anti_response optional).
   - `run_pass_error_cluster` calls the renamed function per qualifying
     cluster and extends `proposals` with both lists; narrative reports
     diagnosis and skill-candidate counts separately.
3. `tools/dream_apply.py`:
   - `_checked_result` gains a `record_error` success predicate
     (`"Error KB created"` / `"Error KB updated"` prefix).
   - `apply_group` dispatches `call == "record_error"` to
     `tools.record_error(...)` with all five kwargs. No `doc_id`, no
     lse-kb/lse-skills dream-field stamp (not applicable to this index;
     `record_error`'s own `occurrence_count`/`last_seen` already serve
     that role).
   - `render_group` gains a confirm-gate block for `record_error` showing
     `error_text` / `interpretation` / `resolution` / `anti_response`
     (rendered even when empty, so a reviewer sees it was considered and
     left blank, not silently dropped).
4. `tools/goethe_dashboard.html` — `proposalAction()` gains
   `record_error -> ["Record diagnosis", <error_text first line>]`, placed
   ahead of the generic fallback, matching the map added in `22d3528`.

No new tool: `record_error`'s method name is unchanged; only its optional
kwargs grew. `Tools.__mro__` and every other method are untouched.

## 5. Tests

`tests/test_diagnosis_proposal_type.py` (19 tests, no live ES — a `FakeES`
double local to this file, same one-fixture-per-file convention as
`test_dream_crash_discipline.py`):

- **Test 3** — `TestDiagnosisEmission`: `_draft_error_cluster_proposals`
  emits a well-formed `diagnosis` proposal from a triggered-failure
  cluster; `run_pass_error_cluster` end-to-end produces a `diagnosis`-typed
  proposal.
- **Test 4 (LOAD-BEARING)** — `TestSkillCandidateStillRoutable`: a cluster
  whose evidence yields a genuine repeatable procedure still emits
  `skill-candidate`; a single envelope can emit both types at once.
  **Broken, confirmed red, restored** — see below.
- **Test 5 (LOAD-BEARING)** — `TestDiagnosisStructuralValidation`: a valid
  diagnosis passes; missing `anti_response` passes; missing (or
  whitespace-only) `interpretation` is rejected with a reason string
  naming the field; the drafting filter also drops an incomplete diagnosis
  before it ever reaches the validator. **Broken, confirmed red,
  restored** — see below.
- **Test 7** — `TestDreamInfraBoundary`: proven per Hazard C above.
- **Test 8** — `TestConsoleRendering`: the dashboard's `proposalAction()`
  source contains the `record_error` branch and its literal action label;
  `dream_apply.render_group`'s source contains the `record_error` block.
- Plus: `TestErrorClusterPromptAsksForAntiResponse` (Hazard B, prompt
  text asserted directly) and `TestAntiGoals` (signature backward
  compatibility, no new tool, `skill_record` untouched).

`tests/test_kb_contracts.py::TestRecordErrorDiagnosisFields` (4 tests,
**real** Elasticsearch against a throwaway `lse-errors-test` index — the
`es` fixture now also provisions this index via a new
`ERRORS_TEST_MAPPING`, closing a gap the file's own docstring already
claimed was covered but the fixture never actually created):

- **Test 1** — three-positional-arg call behaves exactly as before
  (message format, `interpretation`/`anti_response` default to `""`).
- **Test 2** — new fields persist and are retrievable, and are
  independently confirmed absent from `resolution`'s text (Hazard A).
- **Test 6** — a diagnosis write lands in `lse-errors-1024`, `lse-kb`'s doc
  count is unchanged.
- One additional case beyond the spec's own list: a repeat 3-arg call
  hitting an existing diagnosis does not blank its interpretation/
  anti_response.

### Breaking tests 4 and 5 (spec's explicit instruction)

**Test 4.** Patched `_draft_error_cluster_proposals` to iterate `for item
in []` instead of `env.get("skill_candidates", [])`. Ran
`TestSkillCandidateStillRoutable` — both tests **FAILED**
(`assert 0 == 1` / `assert (1 == 1 and 0 == 1)`), i.e. routing collapsed to
diagnosis-only exactly as expected. Reverted via the untouched backup;
`git diff --stat` on `dream_runner.py` matched pre-break byte-for-byte
(140 lines changed, same as before the break), confirming a clean restore.

**Test 5.** Patched the `if p.get("type") == "diagnosis":` guard in
`validate_proposal_shape` to `if p.get("type") == "diagnosis" and False:`.
Ran `TestDiagnosisStructuralValidation` — the three tests that depend on
the guard firing **FAILED** (`test_missing_interpretation_is_rejected`,
`test_whitespace_only_interpretation_is_also_rejected`,
`test_prove_the_guard_actually_fires`, each `assert None is not None`);
the four tests that don't depend on it (valid diagnosis, missing
anti_response allowed, type-known, draft-filter) still passed, confirming
the break was narrow and specific to the guard, not a wider breakage.
Reverted; diff stat matched pre-break.

## 6. Manual disposal — NOT acted on

Per Hazard D, these are listed for a human to review and re-issue by hand;
nothing here was auto-migrated, re-typed, or deleted.

**Six rejected `skill-candidate` proposals, payload retained for re-issue**
(`traum-state.db`, all `state=REJECTED`, `reason` starts `"Diagnosis, not a
skill — triggered rather than initiated..."`):

| proposal_id | task | created_at |
|---|---|---|
| `prp_9266fafd5892426eb0a59c2b8427416e` | Diagnose and resolve SSH connection failures (exit 255) to remote hosts | 2026-08-03T03:25:55Z |
| `prp_c8b11e52fc774632a4cfefaa99e70465` | recognize and handle MCP server session cancellation errors | 2026-08-03T03:25:55Z |
| `prp_4322aaf7f6434245ade0c3c53e814b82` | Diagnose and resolve persistent SSH connection failures after mux retry | 2026-08-03T04:20:46Z |
| `prp_4b0c03c973f74af396a70a786a4ee082` | diagnose MCP server session receive-loop cancellations | 2026-08-03T04:20:46Z |
| `prp_4c290e3c555a4ef7942e285067d698ca` | Retrieve correct pfSense API key from vault for pfsense_graphql authentication | 2026-08-03T04:20:46Z |
| `prp_ef24f5bcff424ca0bc0d1065df297487` | handle search_kb timeouts to localhost:11434 | 2026-08-03T04:20:46Z |

**One mis-typed recorded skill** (`lse-skills`, doc `bd0a122cd97581bb`,
`skill_id=Local System Engineer/survive-mcp-cancellederror-on-long-
running-execute-command-c...`, `source_tier=inferred`, `quality=0.40`) —
the MCP `CancelledError` pattern. Left exactly as recorded; not retyped,
not re-scored.

## 7. Invariants

```
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/goethe_kb.py tools/dream_apply.py   # OK
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/goethe_kb.py tools/dream_apply.py         # 46 errors, IDENTICAL count before/after this diff (confirmed via git stash), none in touched lines
/home/sy5/miniforge3/bin/ruff check tests/test_diagnosis_proposal_type.py tests/test_kb_contracts.py      # All checks passed!
node --check /tmp/d.js   # extracted goethe_dashboard.html <script> block — OK
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

**770 → 793 passed** (23 new tests, all added by this change: 19 in
`test_diagnosis_proposal_type.py` + 4 in
`TestRecordErrorDiagnosisFields`). Zero failures, zero regressions.

## 8. What's runtime-verified vs. test-only

Per WORKFLOW §5, stated explicitly:

- **Runtime-verified**: `record_error`'s new fields, against a real
  (throwaway) Elasticsearch index — `TestRecordErrorDiagnosisFields`'s 4
  tests actually write and read back from `127.0.0.1:9200`. Hazard C's
  provenance boundary is verified against real code paths
  (`record_crash_error`, `goethe.Tools.record_error`) with a FakeES double
  standing in for ES itself.
- **Test-only** (mocked `request_dream_envelope`, not a live LLM call):
  whether `error-cluster`'s actual prompt, run against node3090's real
  model, produces well-formed diagnoses and correctly routes a genuine
  repeatable-procedure cluster to `skill-candidate`. The prompt text itself
  is asserted to contain the right instructions
  (`TestErrorClusterPromptAsksForAntiResponse`), but a live dream run
  against real session data has not been performed as part of this change.
  Recommend watching the next `error-cluster` pass's real output before
  trusting its diagnosis/skill-candidate split unsupervised.
- Console rendering (test 8) is verified by source inspection
  (`proposalAction()`'s code contains the right branch) and `node --check`
  syntax validation, not by rendering the page in a browser and clicking
  approve.

<!-- ACCEPTANCE
task: diagnosis-proposal-type
commit: 668bfb1
tests_before: 770
tests_after: 793
files_changed: tests/test_diagnosis_proposal_type.py, tests/test_kb_contracts.py, tools/dream_apply.py, tools/dream_runner.py, tools/goethe_dashboard.html, tools/goethe_kb.py
ruff_clean: tests/test_diagnosis_proposal_type.py, tests/test_kb_contracts.py
runtime_verified: false
-->
