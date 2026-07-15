# TRAUM A/B Learning-Lift Eval — Design

> Thread 4 (TRAUM-AUTO), Prompt 4.5. Written 2026-07-12. This is a DESIGN
> document — per the prompt ("before running anything"), nothing below has
> been executed yet. Execution is Prompt 4.6.
>
> Status of prerequisites this design depends on, checked against the live
> system while writing this doc: **DATA-3 (dataset freeze) — done for the
> gold set as part of this design, see §3. DATA-4 (trust-field-preserving
> reindex) — still open on ROADMAP.md, not required for this eval since
> Condition A/B do not reindex `lse-kb`, see §2.3. `v35_harness.py` — the
> original was unrecoverable and has been reconstructed and committed, see
> §4.**

---

## 1. What "learning lift" means here, precisely

TRAUM's promise (docs/traum-dreaming-plan.md §1) is that the dreaming loop
makes the LSE *better over time* without a human re-teaching it each time.
"Better" has to be measured, not asserted — this is the SCRIBE-4 / RFC-KB
lesson (a memory system nobody measures is a memory system nobody can trust)
applied to the KB half of the equation, with the highest stakes of any eval
TRAUM has run so far: this is the evidence Prompt 4.8's autonomy-tuning
decision will be made from.

Two conditions, one held constant KB, one live:

- **Condition A — frozen KB.** The `lse-kb` index in the state it was in
  before this eval's dreaming window began. Section 2 explains exactly what
  "before" means and why it cannot mean "before Thread 2" (that data no
  longer exists).
- **Condition B — live dreamed KB.** The current, continuously-dreamed
  `lse-kb` index, at whatever state it's in when Prompt 4.6 runs the suite.

Everything else — model, prompt version, harness, test suite, gold set —
is held **identical** between A and B. The only variable under test is the
KB's content and trust-field state. If A and B differ on suite score or
tool-call count, the KB is the only thing that can explain it.

---

## 2. Condition A — what "pre-dreaming-era" can actually mean now

### 2.1 The literal reading is no longer achievable

The prompt's literal instruction — "current KB snapshotted pre-dreaming-era"
— assumes a snapshot exists from before Thread 2's first supervised dream
(2026-07-11, Prompt 2.7). It does not exist:

- `GET /_snapshot` on the live Elasticsearch cluster returns `{}` — **no
  snapshot repository has ever been registered**, so no ES-native snapshot
  of any vintage exists to restore.
- `docs/dreaming/calibration-run-1.md` (written the same day as the first
  dream, 2026-07-11) already found this and explicitly deferred it to this
  prompt: *"there is no true pre-dream-apply snapshot to re-run 'before'
  against... Thread 4's Prompt 4.5 (A/B eval design) should specify an
  actual pre-apply ES snapshot step."* This design is that step — but it
  can only apply going forward, not retroactively.
- The only survivors of the true pre-dreaming state (2026-07-11, before
  Prompt 2.7) are **prose statistics**, not data: `docs/dreaming/corpus-audit.md`
  records `lse-kb` at 234 docs with a quality-score histogram, and
  `dream-run-2026-07-11.md` records 368 docs immediately after Thread 1's
  backfill but before the first dream's 3 dedup merges. Neither is a
  restorable index — you cannot query, embed-search, or retrieve against a
  paragraph of statistics.
- Since then: 3 dedup merges (Thread 2), 7 stale/contradiction proposals
  rejected (no writes), 1 error-cluster proposal rejected, a full Thread 3
  insights/patterns dream cycle (2026-07-12), and ongoing backfill activity
  have all mutated the live index. Current live count: **373 docs** (checked
  while writing this doc). The pre-dreaming index is not paused somewhere
  waiting to be restored; it was overwritten in place, which is exactly
  what an in-place ES index does absent a snapshot.

**Conclusion:** Condition A cannot be "the KB as it was on 2026-07-11."
That data is gone. Reconstructing it from episode/backfill logs
doc-by-doc was considered and rejected — see §2.2.

### 2.2 Why reconstruction-from-logs was rejected

`lse-kb` documents do carry `created_at`/`updated_at`/`indexed_at` fields
(confirmed via live mapping, `corpus-audit.md` §c), so a
timestamp-filtered rebuild (keep only docs `created_at` < the Thread-2
start boundary) was considered as a way to approximate the old state.
Rejected because:

1. **In-place mutation breaks it.** Dream `demote` and future `reverify`
   proposals update `quality`/`stale` fields on *existing* docs without
   changing `created_at`. A timestamp filter would include a doc whose
   trust fields have already been dream-modified, silently contaminating
   the "control" condition with dreamed changes. This directly violates
   the eval's own premise.
2. **Dedup merges are destructive to the merged-away side's identity**, not
   to content (KB-DECAY: dedup demotes, never deletes — see
   `dream-run-2026-07-11.md`), but reconstructing which of a merged pair
   was "the original" from logs alone is exactly the kind of fragile,
   easy-to-get-quietly-wrong step DATA-3's whole point is to prevent.
3. Silently fabricating a "close enough" Condition A and presenting its
   score as if it were the real pre-dreaming baseline would produce a
   number that *looks* rigorous and isn't — worse than admitting the gap.

### 2.3 What Condition A means for this eval, going forward

**Condition A = `lse-kb` frozen immediately before Prompt 4.6 begins,
via a real ES snapshot, held static for the duration of the eval.**
This reframes the comparison from "pre-dreaming vs. dreamed" (impossible
to recover) to **"KB frozen at eval-start vs. KB that continues dreaming
during the eval window"** — the same causal question TRAUM's plan asks
(does continued dreaming help), just anchored at a date the data actually
exists for. Every future TRAUM eval inherits a real baseline from this
point on, closing the calibration-run-1.md gap for good.

Concretely, as **prerequisites for Prompt 4.6, not this prompt**:

```
# 1. Register a filesystem snapshot repository (one-time, ES-native)
PUT /_snapshot/lse-eval-snapshots
{
  "type": "fs",
  "settings": { "location": "/opt/local-se/es-snapshots" }
}

# 2. Snapshot lse-kb at eval start (repeatable, cheap — one index, ~373 docs)
PUT /_snapshot/lse-eval-snapshots/traum-ab-condition-a-2026-07-12
{ "indices": "lse-kb", "include_global_state": false }

# 3. Restore into an isolated index name for Condition A runs
POST /_snapshot/lse-eval-snapshots/traum-ab-condition-a-2026-07-12/_restore
{
  "indices": "lse-kb",
  "rename_pattern": "lse-kb",
  "rename_replacement": "lse-kb-a"
}
```

DATA-4 (trust-field preservation on reindex) does **not** block this: DATA-4
is about `03-kb-seed.py --reindex` resetting earned trust on a *reseed*.
An ES-native snapshot/restore is a byte-for-byte copy — quality/stale/
volatility/every field travel with it unchanged. DATA-4 stays open on
ROADMAP.md for its own reason; it is out of scope here.

**Isolation, not index-name juggling:** `goethe.py` hardcodes the index
name `"lse-kb"` in ~15 call sites (`Tools._es_client`/search/index/update
paths) — there is no index-name valve to point a single gateway at
`lse-kb-a` vs `lse-kb` by config. Rather than add one (the plan's own
PH5-2 tripwire: avoid growing `goethe.py`'s edit surface for TRAUM unless
forced), Condition A instead runs against **a second, disposable ES
instance** on a free local port, restored from the same snapshot repo,
with the *same* index name `lse-kb` inside it. Condition A's gateway
process then only needs `GOETHE_ES_URL` pointed at that second instance —
already a supported valve (`os.environ.get("GOETHE_ES_URL", ...)`,
confirmed at `dream_apply.py:198`, `dream_digest.py:112`,
`dream_runner.py:278`, and `goethe.py:6279`). Zero `goethe.py` code changes
required. `lse-errors` and `lse-skills` are snapshotted alongside `lse-kb`
in the same call (both feed `search_kb`-adjacent tools) so Condition A is a
fully self-consistent frozen world, not just one index.

---

## 3. The frozen gold set (DATA-3)

`eval/retrieval-gold-v1.jsonl` — 50 query→expected-doc pairs (`wc -l` = 50,
matching the prompt's "@50"). Frozen as of this design:

```
sha256sum eval/retrieval-gold-v1.jsonl
a5fe13806c7fb4df1f5d552b71c9a5f0e30d5c8d932e7bcff042e7a39d1379be
```

This hash is the DATA-3 fingerprint for this eval. `scripts/freeze_bench.py`
already establishes the pattern (challenge-set manifest with per-item
sha256, `--verify` drift check) for `bench/`; DATA-3 itself ("extend to
gold sets") remains open as a general ROADMAP item, but this eval does not
wait on the generalized tooling — the hash above is recorded here and MUST
be re-checked at the top of Prompt 4.6 (`sha256sum` before each run of both
conditions). If it doesn't match, the gold set drifted since this design
and every number below is void until re-frozen and this doc is updated.

---

## 4. Harness — `v35_harness.py`

The plan names `v35_harness.py` as "the harness," last used for
`eval-report-v8.md` (Run 9, 2026-07-06), and instructs committing it to the
repo before running anything, since it lived only in `/tmp/lse/`.

**That file no longer exists.** `/tmp/lse/` on both LUCIFER and node3090
was checked directly while writing this doc — gone on both hosts. Its loss
was already documented in the repo before this prompt: `eval/t1_feedback_loop.py`'s
module docstring (2026-07-07) and `CURRENT-STATE.md`'s "Outstanding" note
both record that the `/tmp/lse/` copy was cleared and the original was
never committed. `eval-report-v8.md` is the only surviving description of
its behavior.

**Action taken:** `eval/v35_harness.py` has been reconstructed from that
description and committed (see the file's own "RECONSTRUCTION NOTE"
docstring for full provenance). It is not a recovered original — treat any
numeric comparison against `eval-report-v8.md`'s Run 9 score as
directional, not exact, since the harness implementation is new even
though the described behavior (real MCP tool execution against
`goethe_mcp`, real `llama-server` chat-completions calls, no simulation)
matches. It reuses the already-proven MCP-driving-a-model wiring from
`eval/t1_mcp_harness.py` (built 2026-07-07, confirmed live) rather than
re-deriving that part from scratch.

Capabilities relevant to this eval's metrics:
- Parses `eval/test-suite-v3.5.md`'s existing markdown structure directly —
  no separate scenario-definition file to keep in sync.
- Correctly detects and replays multi-turn chains (verified live against
  the real suite while building this doc: 20 scenarios group into 19
  chains, with A1→A2 correctly linked via the suite's own "continuing in
  the same conversation as A1" prose — the one non-fresh-conversation case
  in v3.5).
- Logs, per scenario: full transcript, every tool call (name, args, result,
  truncated at 4000 chars), `tool_call_count`, wall-clock seconds,
  `hit_tool_round_cap`. This is what makes the tool-call-count and
  wrong-KB-hit metrics (§5) possible after the fact without re-running
  anything.
- Does **not** score pass/fail itself — v3.5 is human-graded against a
  0/2/3 rubric per scenario (`test-suite-v3.5.md`'s own "Pass/Partial/Fail"
  criteria), same as every prior run in `eval/eval-report-v*.md`. The
  harness's output feeds that same manual (or LLM-assisted) grading step,
  it does not replace it.

`v35_harness.py --suite eval/test-suite-v3.5.md --list` is the smoke test
to re-run at the top of Prompt 4.6, before spending GPU time, to confirm
the suite still parses the same 19 chains / 20 scenarios.

---

## 5. Metrics

All four computed identically for Condition A and Condition B, from the
same harness output format, so a diff is a straight subtraction.

### 5.1 Suite score

`test-suite-v3.5.md`, 20 tests across categories S/P/M/W/A/L, max 60 pts
(same categories the prompt calls "S/A/W/P" — the suite itself also has M
and L; all six run, all six count, consistent with how every prior
`eval-report-v*.md` has scored it). Graded by the existing 0/2/3 rubric
per scenario, from the harness's transcript output — same manual-grading
process `eval-report-v8.md` used, not automated, so a human (or an
LLM-assisted grading pass, cross-checked) applies the suite's own
Pass/Partial/Fail criteria to each transcript.

### 5.2 Retrieval recall / MRR on the frozen gold set

`rag/eval_retrieval.py` run directly against each condition's ES instance
(not `run_tests(scope=retrieval)` — that scope runs the self-test fixture,
confirmed a red herring by `calibration-run-1.md`). Recall@1, recall@3, MRR,
`linear` mode (production) as primary, `bm25`/`rrf`/`knn` recorded
alongside for the same trend-visibility `calibration-run-1.md` established.
`min_score=4.2` threshold re-checked per the v0.3.8 re-sweep rule
(doc count differs between A and B by construction — that's exactly the
condition the re-sweep rule exists for).

### 5.3 Tool-call count to completion, per scenario

Directly from `v35_harness.py`'s `tool_call_count` field, per scenario, for
both conditions. This is the metric that tests the plan's "faster
verification" claim (docs/traum-dreaming-plan.md §1 frames dreaming's
payoff partly as fewer wasted lookups). Reported per-scenario and as a
suite-wide total; the pre-registered criterion (§6) uses the suite-wide
percentage delta.

### 5.4 Wrong-KB-hit count

Defined as: a `search_kb` tool call in the transcript whose returned
top-ranked document was **not** the document the scenario's grader judges
the model actually needed, AND the model's answer shows evidence of using
that wrong document (quotes it, acts on a fact only it contains, etc.) —
distinguished from the model correctly ignoring a bad hit and searching
again, which is not counted (that's the system self-correcting, not
failing). This requires a grader reading the `tool_calls` log
`v35_harness.py` already captures per scenario (search_kb name/args/result,
in order) alongside the transcript — not automatable purely from the JSON,
since "was this hit actually used" requires reading the final answer.
Counted per condition, suite-wide total. A rise in wrong-KB-hits in
Condition B versus A is a direct signal of the poisoning-via-dreaming risk
the plan's §2 invariants and the Prompt 4.7 threat-model addendum both
exist to prevent — this metric is this eval's empirical check on whether
those invariants are holding in practice, not just in code.

---

## 6. Pre-registered success criterion

Fixed **before** Prompt 4.6 runs anything, per the prompt's own
instruction — this section is not to be edited after seeing results.

**B wins if EITHER:**
- B's suite score (§5.1) is strictly greater than A's, **OR**
- B's suite-wide tool-call count (§5.3) is ≥10% lower than A's, **with no
  suite-score loss** (B's score ≥ A's score).

**Anything else is a null or a loss, and gets recorded as such — not
reframed, not re-run with different conditions post hoc.** Specifically:
- B score < A score, regardless of tool-call count → **loss**.
- B score == A score AND tool-call reduction < 10% → **null** (no
  detectable lift either direction).
- B score == A score AND tool-call reduction ≥10% → **win** (per the OR
  clause above).

Retrieval recall/MRR (§5.2) and wrong-KB-hit count (§5.4) are **not** part
of the win/loss/null gate itself — they are diagnostic. A "win" on the
gate with a wrong-KB-hit increase is a contradictory result that must be
called out explicitly in `eval/eval-report-traum-1.md` (Prompt 4.6), not
averaged away. Per Prompt 4.6's own instruction: a loss means the plan's
§2 invariants are suspect — file the specific bad KB writes to
`lse-errors` and do not enable any `DREAM_AUTO_APPLY` type off the back of
this eval.

---

## 7. Fixed variables (must match exactly between A and B)

| Variable | Pinned value | Source |
|---|---|---|
| Model | Whatever `llama-server` reports via `/v1/models` at Condition A's snapshot moment — recorded in Prompt 4.6's report header, then held fixed for B's run in the same session | live check at run time |
| Prompt version | `prompts/node4090-v0.6.0.md` (current canonical, per `CURRENT-STATE.md`) | `--system-prompt-file` arg to `v35_harness.py`, same file both runs |
| Harness | `eval/v35_harness.py` v0.1.0 (this commit) | §4 |
| Suite | `eval/test-suite-v3.5.md`, sha256 re-checked at Prompt 4.6 start (not yet frozen under DATA-3 — TODO, out of scope for this design) | §4 |
| Gold set | `eval/retrieval-gold-v1.jsonl`, sha256 `a5fe1380...1379be` (§3) | §3 |
| Conversation state | Fresh threads per chain, per the prompt's instruction — `v35_harness.py` starts a new `messages` list per `ConversationChain`, never reuses history across chains | §4, verified via `--list` |
| Tool surface | Live 48-tool schema pulled from `goethe_mcp` at run start for each condition (goethe_mcp v1.11.1 currently) — expected identical between A and B since only `lse-kb` content differs, not the gateway code, but recorded per run as a sanity check | `list_tools_schema()` |

---

## 8. Open items carried to Prompt 4.6

1. Register the ES snapshot repository and take the Condition-A snapshot
   (§2.3 commands) — infrastructure setup, deliberately not done in this
   design-only prompt.
2. Stand up the second, disposable ES instance for Condition A and restore
   into it.
3. Freeze `eval/test-suite-v3.5.md` itself under DATA-3 (sha256 + manifest)
   — noted as a gap in §7, not blocking (the suite is graded by a human
   reading transcripts either way, so drift would be caught, just not as
   loudly as the gold set's hash check).
4. Confirm which model is actually loaded on `:8080` at run time and record
   it verbatim in `eval/eval-report-traum-1.md` — do not assume from this
   doc, which was written without a live model check for that specific
   value.
