# 06 — Two-Model Implementation Workflow

**The execution pair:**

- **Qwen3.8** — local, 27B-class via llama-server :8080, free, high-volume, lives inside
  the environment, has the full MCP tool surface (44 tools), KB-native, can read and write
  files and run tests directly.
- **Sonnet5** — cloud, metered, high judgment, better at novel architecture and subtle
  security reasoning, **no local file access**; receives and returns diff bundles.

This analyst engagement is separate from the pair. What follows is *their* system.

---

## 1. Routing rubric

### The principle

Route on **cost of being wrong**, not on difficulty.

Qwen3.8 is free and lives in the environment; its failures are cheap because they are
caught by a test that runs in seconds. Sonnet5 is metered and blind to the filesystem;
its value is on decisions where a wrong answer is *expensive to discover later* — a guard
that silently stops guarding, an architecture that has to be unwound, a claim in a funding
document that a partner disproves in the meeting.

So: **if the acceptance test fully captures correctness, Qwen3.8 owns it.** If correctness
depends on judgment the test cannot encode, Sonnet5 owns it.

### Decision table

| task class | owner | rationale | example from `05` |
|---|---|---|---|
| Mechanical refactor, behaviour-preserving | **Qwen3.8** | contract suite is the oracle | M1-9 hardcoded path |
| Doc generation from code | **Qwen3.8** | source of truth is mechanical | M1-4 docs index |
| Test scaffolding, fixtures | **Qwen3.8** | volume work; failures are loud | M5-2 fixtures |
| CI plumbing, YAML, scripts | **Qwen3.8** | verifiable by running it | M0-6, M2 wiring |
| KB maintenance, tracker upkeep | **Qwen3.8** | KB-native, high frequency | all of `07` |
| Dependency pinning, packaging | **Qwen3.8** | `pip install -e .` is the oracle | M0-5 |
| Log/metric parsers, reports | **Qwen3.8** | output is checkable | M5-3, M5-4 |
| Version/drift detector implementation | **Qwen3.8** | spec is fully written in `03` P0-6 | M2 |
| — | | | |
| **Threat model, security review** | **Sonnet5** | absence of a vulnerability cannot be tested | M3-8 prep |
| **Guard rewrites** (evidence provenance, argv path, KB-FIRST gate) | **Sonnet5** | a guard that passes tests but stops guarding is the worst failure mode | M3-1, M3-2 |
| **Architecture decisions** | **Sonnet5** | expensive to unwind | M0-1, M1-5 |
| **Provenance/canonicalisation decisions** | **Sonnet5** | one-way doors | M0-3, M0-4, M0-10 |
| **Eval methodology, pre-registration** | **Sonnet5** | a badly designed experiment produces a confidently wrong number | M4-6, M4-7 |
| **Funding narrative, positioning** | **Sonnet5** | claims must survive an adversarial reader | M6-* |
| **Precision passes on conditional claims** | **Sonnet5** | requires knowing what a VC will check | M6-4 |

### Escalation path — Qwen3.8 → Sonnet5

Qwen3.8 escalates, and does not retry, when **any** of these fires:

| trigger | why |
|---|---|
| **2 consecutive failed acceptance tests** on the same task | the model is guessing; more iterations make it worse |
| the change would touch a **guard function** — anything in `01` §7.1 | wrong guard edits are silent |
| the change would touch `tools/goethe.py` **core** (not a mixin) or `dream_runner.py` | blast radius |
| a **KB schema** field would be added, renamed or removed | migration risk across two instances |
| the acceptance test would have to be **weakened** to pass | the test is the contract; changing it is a decision |
| the task requires choosing between **two defensible designs** | not a coding task |
| **any security-relevant behaviour** would change | `03` P1-1, P1-2, P1-14 territory |
| **iteration budget exhausted** (see §2) | hard stop |

Escalation is not failure and is not penalised. The escalation message is a filled task
contract with `status=escalated`, the two failing outputs verbatim, and one sentence on
what the model believes the ambiguity is.

**Reverse escalation — Sonnet5 → Qwen3.8.** Once Sonnet5 has made the decision and written
the patch, the *mechanical follow-through* (applying it across N call sites, updating
docs, regenerating fixtures) returns to Qwen3.8. Sonnet5 does not do volume work.

---

## 2. Task contract format

Every work item is exactly one of these. It is a KB document (`07` §1), not a chat
message.

```yaml
id:            TASK-M<n>-<k>            # e.g. TASK-M3-1
milestone:     M<n>
title:         <imperative, one line>
owner_model:   qwen3.8 | sonnet5
input_files:                            # EXACT paths, no globs, no "and related"
  - tools/goethe_kb.py
  - tests/test_kb_contracts.py
deliverable:   <one sentence: what exists after this that did not before>
acceptance_test:
  command:     <the exact shell command>
  expect:      <the exact string or regex that must appear>
  expect_exit: 0
evidence_requirement:
  min_chars:   20                       # verbatim tool output, >= 20 chars
  must_include: <substring that proves the right thing ran>
kb_update:     <which KB docs this task must create/update on completion>
max_iterations: 3                       # attempts at the acceptance test
abort_criteria:                         # any one → stop, escalate, do not retry
  - 2 consecutive acceptance-test failures
  - the change would require weakening acceptance_test
  - <task-specific>
blocked_by:    [TASK-M<n>-<j>, ...]
status:        open | in_progress | blocked | done | escalated | abandoned
```

**Rules that make the format load-bearing:**

1. **`input_files` is exhaustive.** If the model needs a file not listed, that is an
   escalation, not an improvisation. This is what keeps Sonnet5's diff bundles small and
   what keeps Qwen3.8 from wandering.
2. **`acceptance_test.command` must be runnable by a fresh session with no context.**
   No "run the tests"; the literal command.
3. **`expect` must fail on the current tree.** A criterion that already passes proves
   nothing. Every contract is written against the *before* state.
4. **`evidence_requirement.must_include` prevents the classic fake-pass**: a test that
   passes because it was skipped, or because it ran against the wrong tree.
5. **`max_iterations` is a hard budget**, not a suggestion.

### Example contract 1 — Qwen3.8

```yaml
id:            TASK-M1-9
milestone:     M1
title:         Replace the hardcoded Windows model-card path in node_facts with a valve
owner_model:   qwen3.8
input_files:
  - tools/node_facts.py
  - tests/test_node_facts.py
deliverable:   node_facts resolves the model-card path from a valve/env var with a
               documented default, and skips cleanly when the file is absent.
acceptance_test:
  command: |
    cd $REPO && python3 -m pytest tests/test_node_facts.py -q --no-header 2>&1 | tail -1
  expect:      '0 failed'
  expect_exit: 0
evidence_requirement:
  min_chars:   20
  must_include: 'passed'
kb_update:     TASK-M1-9 (status, evidence_log); MILESTONE-M1 (last_verified, next_action)
max_iterations: 3
abort_criteria:
  - 2 consecutive failures
  - the fix would require deleting or xfail-ing any of the 4 currently-failing tests
  - the default would point at any path under /mnt/c/
blocked_by:    []
status:        open
```

*Why this one is Qwen's:* the current failure is unambiguous
(`FileNotFoundError: '/mnt/c/Goethe3.0/ACTUAL-Qwen3.6-27B-UD-Q4_K_XL.gguf.md'` at
`tools/node_facts.py:405`), the oracle is four existing tests, and the abort criteria
close the two cheating routes (delete the tests; keep a `/mnt/c/` default).

### Example contract 2 — Sonnet5

```yaml
id:            TASK-M3-1
milestone:     M3
title:         Bind KB evidence strings to the episode journal (evidence provenance)
owner_model:   sonnet5
input_files:
  - tools/goethe_kb.py                  # :845 record_outcome, :935 gate, :1055 kb_verify, :1132 gate
  - tools/goethe_mcp.py                 # :528 _journal — the evidence source
  - tools/dream_apply.py                # :384 check_evidence_thin
  - tests/test_kb_contracts.py
deliverable:   record_outcome / kb_verify / check_evidence_thin accept evidence only when
               it is a substring of a result the current session actually received, read
               from the episode journal. Behaviour behind valve
               EVIDENCE_PROVENANCE_ENFORCE = warn | block, DEFAULT warn.
acceptance_test:
  command: |
    cd $REPO && EVIDENCE_PROVENANCE_ENFORCE=block \
      python3 -m pytest tests/test_evidence_provenance.py tests/test_kb_contracts.py -q --no-header 2>&1 | tail -1
  expect:      '0 failed'
  expect_exit: 0
evidence_requirement:
  min_chars:   20
  must_include: 'test_fabricated_evidence_is_refused PASSED'
kb_update:     TASK-M3-1; MILESTONE-M3; and a KB procedure doc
               'evidence provenance: how the journal binding works'
max_iterations: 2
abort_criteria:
  - any existing test in tests/test_kb_contracts.py must be modified to pass
  - the default valve value is anything other than 'warn'
  - the journal read adds > 50ms p99 to record_outcome
  - session-id resolution is ambiguous for any code path that calls record_outcome
blocked_by:    [TASK-M2-4]              # drift detector blocking before guards change
status:        open
```

*Why this one is Sonnet's:* it rewrites the system's headline epistemic guard. A version
that passes tests while silently accepting anything is the worst possible outcome, and no
test suite reliably catches that — it needs someone reasoning about what "the current
session" means across five call paths. Note `max_iterations: 2` (metered) and the abort
criterion on the default valve value, which is the one thing a helpful model would
"improve" and must not.

### Example contract 3 — shared (Sonnet decides, Qwen executes)

```yaml
id:            TASK-M0-10
milestone:     M0
title:         Resolve corpus B: clone-from-remote or freeze-as-evidence
owner_model:   sonnet5 → qwen3.8            # two-phase, one contract
phase_1:
  owner:       sonnet5
  deliverable: A decision recorded in PROVENANCE.md choosing exactly one of
               {clone, freeze}, with justification, AND an ordered rescue list of
               files that exist ONLY on node3090 and must reach the repo first.
  acceptance_test:
    command: |
      grep -E '^node3090 \| (canonical-replica|frozen-evidence) \|' PROVENANCE.md
    expect:  'node3090 |'
    expect_exit: 0
  abort_criteria:
    - the rescue list omits run_t0t1_suite.py, t1_feedback_loop.py, t1_mcp_harness.py,
      retrieval-gold-v2.jsonl, retrieval-gold-v2-candidates.jsonl
phase_2:
  owner:       qwen3.8
  blocked_by:  [phase_1, TASK-M0-10-BACKUP]
  deliverable: The decision executed on node3090.
  acceptance_test:
    command: |
      ssh node3090.home.arpa 'git -C /home/lse-admin/projects/local-system-engineer rev-parse HEAD' \
        || python3 scripts/corpus_manifest.py --verify --host node3090
    expect:      '^[0-9a-f]{40}$|MANIFEST OK'
    expect_exit: 0
  abort_criteria:
    - TASK-M0-10-BACKUP has not produced a verified tar of /home/lse-admin/projects
    - any file on the phase_1 rescue list is not yet committed to the canonical repo
evidence_requirement:
  min_chars:   40
  must_include: 'node3090'
kb_update:     TASK-M0-10; MILESTONE-M0; KB fact doc 'corpus B status'
max_iterations: 2 (phase_1) / 3 (phase_2)
status:        open
```

*Why shared:* the decision is a one-way door on a live host holding the only copy of the
behavioural eval suite — Sonnet's call. The execution is mechanical — Qwen's. The abort
criteria encode the thing that would actually go wrong: overwriting node3090 before the
irreplaceable files were rescued.

---

## 3. Sonnet5 diff-bundle protocol

Sonnet5 has no filesystem access. Work crosses the gap as bundles.

### Outbound (local → Sonnet5): the context bundle

Built by `scripts/bundle_out.sh <TASK-ID>`, from the contract's `input_files` and nothing
else:

```
bundle-TASK-M3-1/
  CONTRACT.yaml            # the task contract, verbatim
  MANIFEST.sha256          # sha256 of every file below, + the repo HEAD sha
  files/
    tools/goethe_kb.py     # full file, not an excerpt
    tools/goethe_mcp.py
    tools/dream_apply.py
    tests/test_kb_contracts.py
  BEFORE.txt               # verbatim output of the acceptance command NOW (must fail)
  CONSTRAINTS.md           # the abort_criteria, restated as prose
```

Rules:
- **Full files, never excerpts.** Excerpts are how a cloud model invents a function that
  already exists ten lines below the cut.
- `MANIFEST.sha256` includes `git rev-parse HEAD`. A bundle built against a HEAD that has
  since moved is rejected on return.
- `BEFORE.txt` must show the acceptance test **failing**. If it passes, the contract is
  wrong and the task does not start.
- **Secrets never cross.** `bundle_out.sh` runs `redact.redact_sensitive_text()` over every
  file and refuses to build if `gitleaks` flags the bundle. This reuses the project's own
  517-line redaction module rather than inventing a second one.

### Inbound (Sonnet5 → local): the patch bundle

```
patch-TASK-M3-1/
  CONTRACT.yaml            # echoed back with status
  PATCH.diff               # unified diff, git-apply-able, against the manifest's HEAD
  RATIONALE.md             # why this design; what was rejected and why
  SELF-TEST.txt            # Sonnet's reasoning about what the test does NOT cover
  BASE.sha                 # the HEAD the patch was built against
```

There is no cryptographic signature — a single-operator system with an authenticated API
channel does not need one, and pretending otherwise is security theatre. **`BASE.sha` is
the integrity control**, and it is the one that actually matters.

### Application — `scripts/bundle_in.sh`, fail-closed at every step

```bash
# 1. base check — refuse to apply against a moved tree
[ "$(git rev-parse HEAD)" = "$(cat BASE.sha)" ] || { echo "REFUSED: base moved"; exit 1; }

# 2. clean tree
git diff --quiet && git diff --cached --quiet || { echo "REFUSED: dirty tree"; exit 1; }

# 3. isolated branch — never apply to the working branch
git checkout -b "apply/$TASK_ID"

# 4. dry run first
git apply --check PATCH.diff || { echo "REFUSED: patch does not apply"; exit 1; }
git apply PATCH.diff

# 5. blast-radius check — the patch may not touch files outside input_files
python3 scripts/check_patch_scope.py PATCH.diff CONTRACT.yaml || exit 1

# 6. the acceptance test, verbatim, output captured
bash -c "$(yq .acceptance_test.command CONTRACT.yaml)" | tee AFTER.txt

# 7. the FULL suite, not just the task's test
python3 -m pytest tests/ -q --no-header | tee SUITE.txt

# 8. drift detector (from M2)
python3 scripts/check_version_drift.py --strict

# 9. only now, merge
```

Step 5 is the one people skip and the one that catches a cloud model helpfully
"fixing" an unrelated file it saw in passing. Step 7 is what catches a change that passes
its own test and breaks two others — with 925 tests available, running only the task's
test is negligence.

**Verbatim evidence rule:** `AFTER.txt` and `SUITE.txt` are raw captured output. They go
into the task's `evidence_log` in the KB unmodified. A paraphrase is not evidence.

---

## 4. Concurrency and ordering

### May run in parallel

| set | why safe |
|---|---|
| Any two tasks whose `input_files` are disjoint **and** neither touches `tools/goethe.py` core | no shared surface |
| Doc tasks (M1-2, M1-4, M1-5, M1-6) | independent files |
| CI/script tasks (M0-6, M0-7, M0-8) | new files only |
| Per-mixin work: `goethe_kb.py` ∥ `goethe_web.py` ∥ `goethe_node.py` ∥ `goethe_netsec.py` | the mixins are genuinely independent — verified: the import graph is acyclic and mixins do not import each other (`01` §0.4.8) |
| Fixture generation (M5-2) alongside anything | additive |

### Must serialise

| constraint | why |
|---|---|
| **Anything touching `tools/goethe.py` core (outside a mixin)** | it is 2,396 lines and the host class for all five mixins; two concurrent edits conflict semantically even when they merge cleanly |
| **Any two KB-schema changes** | one field at a time; a partial migration across two ES instances is unrecoverable without the M0-9 snapshots |
| **TRAUM subsystem changes vs. the live dream timer** | ⚠️ **the sharp edge.** `goethe-dream.timer` fires at 03:30 with jitter and a 45-minute outer timeout. A `dream_runner.py` or `traum_state.py` change landing mid-run corrupts `traum-state.db` state transitions. **Rule: `systemctl stop goethe-dream.timer` before any TRAUM task starts; restart only after the full suite is green.** Add a pre-flight assertion to the contract: `systemctl is-active goethe-dream.timer` must return `inactive`. The lockfile and 30-minute session guard protect against *concurrent runs*, not against *code changing under a run*. |
| **Guard changes (M3-1, M3-2, M3-3, M3-4)** | one per week, each in `warn` mode first, each read out of the audit log before the next. Never two guards in flight. |
| **M2 before any M3 guard change** | you cannot change guards safely while version drift can go unnoticed |
| **Anything on node3090 vs. the rsync in `start-goethe-node3090.sh`** | the sync overwrites `tools/`; a local edit there is lost silently |

### Conflict handling

1. **The KB tracker is the lock.** A task moves to `in_progress` in the KB *before* work
   starts. Two tasks with overlapping `input_files` cannot both be `in_progress` — the
   tracker refuses (`07` §2). This is cheap and it is the only lock the system needs.
2. **Sonnet5 bundles are base-pinned.** If HEAD moved, `bundle_in.sh` refuses at step 1
   and the task is re-bundled. No rebasing of a cloud model's patch by hand.
3. **Qwen3.8 works on `work/<TASK-ID>` branches**, merged only after the full suite passes.
4. **Merge conflicts are an escalation, not a merge.** Qwen3.8 does not resolve semantic
   conflicts in guard code; it re-bundles for Sonnet5 with both sides.

---

## 5. Definition of Done

A task is `done` when **all six** hold:

1. The `acceptance_test.command` was run and produced `expect`, exit `expect_exit`.
2. The **full** suite (`pytest tests/ -q`) is green — not only the task's test.
3. `scripts/check_version_drift.py --strict` exits 0 (from M2 onward).
4. The patch touched only files in `input_files` (`check_patch_scope.py`).
5. The change is merged to the canonical branch and CI is green on it.
6. **The verbatim output of (1) and (2) is in the task's `evidence_log` in the KB.**

### The rule

> **No task is done until its evidence is in the KB — not in chat.**

Chat is not durable, not searchable, not verifiable by a session that was not there, and
not something a funding reviewer can be shown. The KB is all four.

Concretely, this means:

- A model that reports "tests pass" without pasting the output into `evidence_log` has an
  **incomplete** task, regardless of whether the tests actually pass.
- `status` flips to `done` only *after* the `evidence_log` write returns success. Order
  matters: **evidence first, status second.** If the KB write fails, the task stays
  `in_progress` and the failure is a blocker.
- The evidence must satisfy the same gate the agent's own KB imposes on itself — ≥20 chars
  of verbatim tool output, and (after M3-1) provably from a real tool result. **The
  execution system is held to the standard the product enforces.** That is not tidiness;
  it is the strongest possible dogfooding argument, and it is worth a paragraph in the
  funding narrative.
- **A milestone may only be `done` when a fresh session can re-verify every one of its
  exit criteria from the KB alone, with no chat history.** That is the acid test, and it
  is specified in `07` §5.

### Anti-patterns, explicitly forbidden

| anti-pattern | why it is forbidden |
|---|---|
| "Tests pass ✅" with no output | unverifiable; this is the exact failure `assert_state` exists to prevent |
| Weakening an acceptance test to close a task | the test is the contract |
| Marking `done` after a partial run (`pytest tests/test_foo.py` only) | 925 tests exist; use them |
| Recording a summary instead of raw output | violates the project's own verbatim-evidence rule |
| Carrying context between tasks in chat | tasks must be independently re-runnable from the KB |
| Two `in_progress` tasks sharing an `input_file` | silent conflict |
| Editing `tools/` on node3090 | the rsync will eat it |
| Any TRAUM change with `goethe-dream.timer` active | state-machine corruption |
