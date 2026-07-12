# TRAUM Thread 2 close — debrief proposal (2026-07-11, Prompt 2.10)

> Not a `dream_runner.py` output (no LLM call produced this) — a
> hand-authored `kb-fact` proposal, in the exact shape `dream_runner.py`
> would emit and `dream_apply.py` consumes, recording Thread 2's own
> closing calibration verdict. Written this way deliberately: the close
> prompt asks for the debrief to go "through the unified write path,"
> and DESIGN.md §6.1 defines that path as structured `index_to_kb`/
> `skill_record` proposals shown at the SCRIBE-1 confirm-gate — the same
> shape whether a human debrief or an offline dream produced them.

## Proposal

`proposals.jsonl` in this directory carries one `kb-fact` proposal. Verified
against the real `tools/dream_apply.py` code (not hand-checked) before being
committed to this file:

```
$ python3 -c "
import sys; sys.path.insert(0, 'tools')
import dream_apply as da, json
p = json.loads(open('docs/dreaming/2026-07-11-thread2-close/proposals.jsonl').readline())
print(da.validate_proposal_for_apply(p, es=None))
"
None
```

`None` = passes every structural check (`dream_runner.validate_proposal_shape`)
and every hard invariant `dream_apply.py` enforces (`check_ground_truth`,
`check_provenance_format`, `check_evidence_thin`) — the doc_id-gated checks
(`check_quarantine`, `check_quality_raise`) don't apply, since this is a
NEW-doc `kb-fact` proposal, not a `mentor_correct`/`record_outcome` on an
existing one.

The exact SCRIBE-1 confirm-gate block this proposal renders as
(`dream_apply.render_group()`, real code, not reconstructed by hand):

```
――― REPORT: docs/dreaming/2026-07-11-thread2-close/report.md (reference) ―――

――― ES PROPOSAL 1/1: index_to_kb ―――
title:             TRAUM Thread 2 calibration verdict (2026-07-11)
topic:             lse-operations
source_tier:       primary
quality_score:     0.75
verified_against:  eval/retrieval-gold-v1.jsonl (50-query gold set)
volatility:        slow
evidence:
  eval_retrieval.py live run, linear mode: recall@1=0.76 recall@3=0.84 MRR=0.800 identical before (v0.3.8, 2026-07-04, ~200 docs) and after (2026-07-11, 368 docs, post-dream); --threshold-report --mode linear at cut=4.020: kept_correct=38 kept_wrong=11 rejected_correct=0
content:
  TRAUM Thread 2 calibration verdict (2026-07-11): the first supervised dream (3 dedup merges applied, 7 stale-contradiction + 1 error-cluster proposal rejected at the human gate) produced NO retrieval regression. Production `linear` search_kb mode is bit-for-bit identical before vs after: recall@1=0.76, recall@3=0.84, MRR=0.800, unchanged across ~84% lse-kb growth (200 -> 368 docs) since the last recorded sweep. min_score=4.2 was re-swept per its own maintenance rule ("re-sweep after major KB growth") and still holds: at cut=4.020, 38/38 correct top-1 hits kept, 0 correct results lost -- same shape as the v0.3.8 finding that set this threshold. See docs/dreaming/calibration-run-1.md for the full before/after table and the min_score re-sweep detail.
why:               Closes TRAUM Thread 2 (Prompt 2.10) by recording the Prompt 2.8 calibration verdict as an independently retrievable fact, not prose buried in a report file -- a future session asking whether dreaming ever hurt retrieval should find this via search_kb.

Commit this kb-fact (1 call)? (yes/no)
```

`source_tier=primary` (not `ground_truth`) is deliberate, not a missed
upgrade: the underlying numbers were verified live against `eval_retrieval.py`
during Prompt 2.8, but by a prior session, not this one — and this proposal
is itself being authored the way a dream would author it (structured,
gated, no live tool call of its own backing it up THIS session), so it is
held to `dream_apply.py`'s own ceiling for that shape of evidence, same as
any other kb-fact proposal reviewed at this gate. `quality_score=0.75`
sits under the `primary` tier's 0.8 ceiling.

## Applied

`tools/dream_apply.py --no-dry-run` requires a live Elasticsearch + Ollama
connection (`GOETHE_ES_URL`/`GOETHE_OLLAMA_URL`), which Cowork has no
network path to — this proposal was prepared and validated in Cowork, then
applied for real on LUCIFER via `/home/sy5/owui/bin/python3` (the owui
venv; bare `python3` has an incompatible `elasticsearch==9.4.1`, per
Prompt 2.7's infra finding):

```bash
/home/sy5/owui/bin/python3 tools/dream_apply.py \
  --proposals docs/dreaming/2026-07-11-thread2-close/proposals.jsonl \
  --no-dry-run
```

Result (2026-07-11, confirmed at the gate):

```
KB updated (refined): doc_id=2253baf1e9df847d | quality 0.90 → 0.90 | refinements=1 | tier=primary
done. applied=1 (auto=0) rejected_invariant=0 rejected_human=0
```

`index_to_kb`'s own dedup path fired (`goethe.py`'s cosine≥0.92 near-
duplicate check) rather than creating a fresh doc — an existing `lse-kb`
entry (`doc_id=2253baf1e9df847d`) was already a close match for this
content, already at `quality_score=0.90` (above this proposal's 0.75), so
`quality_score = max(existing, new)` left it unchanged at 0.90; only
`refinement_count` incremented and the calibration-verdict content merged
in. `dream_apply.py`'s stamp still ran afterward — the updated doc now
carries `origin=dream`, `provenance=dream-2026-07-11`. Logged in
`applied.jsonl` alongside this file.
