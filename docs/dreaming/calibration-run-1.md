# TRAUM calibration run 1 — retrieval quantification (Thread 2, Prompt 2.8)

> Quantifies the 2026-07-11 first supervised dream (`docs/dreaming/dream-run-2026-07-11.md`)
> against `eval/retrieval-gold-v1.jsonl` (50 query→doc pairs). Run via
> `/home/sy5/owui/bin/python3 rag/eval_retrieval.py` on LUCIFER, live ES + Ollama.

## A note on "before"

`mcp__goethe__run_tests(scope=retrieval)` does **not** produce these numbers —
that scope runs `eval_retrieval.py --self-test` against synthetic fixtures
(no ES/Ollama), confirmed by direct invocation: `recall@1=0.25 / recall@3=0.75
/ MRR=0.458` on a 4-row toy set, unrelated to the real 50-row gold set. The
live numbers below come from running `eval_retrieval.py` directly.

There is no ES snapshot repository configured (`GET /_snapshot` → `{}`), and
`.lse-backups/` only covers a handful of markdown files, not `lse-kb` — so
there is no true pre-dream-apply snapshot to re-run "before" against; the
dream (Prompt 2.7) was already applied by the time this measurement step
ran. "Before" below is the last recorded live-gold-set run, CHANGELOG.md's
**Goethe v0.3.8** entry (2026-07-04, corpus ~200 docs). "After" is a fresh
run against the current, post-dream corpus (368 docs). This is a real gap
this run surfaces: Thread 4's Prompt 4.5 (A/B eval design) should specify an
actual pre-apply ES snapshot step so future calibration runs get a same-day
before/after instead of a stale reference point — noted as a Thread 4 input,
not fixed here.

## Retrieval quality — before vs after

| Mode | Before (v0.3.8, 2026-07-04, ~200 docs) | After (2026-07-11, 368 docs, post-dream) | Δ |
|---|---|---|---|
| **linear (production)** | recall@1=0.76 recall@3=0.84 MRR=0.800 | recall@1=0.76 recall@3=0.84 MRR=0.800 | **0 / 0 / 0 — no regression** |
| rrf | recall@1=0.64 recall@3=0.84 MRR=0.735 | recall@1=0.58 recall@3=0.86 MRR=0.708 | recall@1 −0.06, recall@3 +0.02, MRR −0.027 |
| bm25 | not recorded at v0.3.8 | recall@1=0.72 recall@3=0.84 MRR=0.780 | — |
| knn | not recorded at v0.3.8 | recall@1=0.40 recall@3=0.68 MRR=0.527 | — |

**Production mode (`linear`) is bit-for-bit identical** to the last recorded
baseline — recall@1, recall@3, and MRR all unchanged — despite ~84% corpus
growth (≈200 → 368 docs) since the v0.3.8 sweep and today's 3 dedup
merges/demotions. `rrf` drifted slightly (still not production mode, still
not beating `linear` on recall@1, so this doesn't change the S2.3 decision
already recorded in CHANGELOG.md).

**No regression.** Per Prompt 2.8's own stop condition ("If retrieval
regressed, dream_apply has a bug or the gold set drifted — stop and
diagnose before Thread 3"), this is not triggered — clear to proceed to
Thread 3.

## min_score=4.2 re-sweep (v0.3.8's maintenance rule)

v0.3.8 set `min_score=4.2` after finding the previous 0.72 cutoff was a
no-op (hybrid scores run ~3.5–16, not [0,1]), verified at the time via
`--threshold-report`: "38/38 correct top-1 kept, 3/11 wrong dropped, 0
correct lost." The maintenance rule attached to that finding: **"re-sweep
after major KB growth (BM25 stats drift)."** The corpus has grown ~84%
since then (~200 → 368 docs) — squarely "major growth" — so this run
re-sweeps per Prompt 2.8's instruction.

`--threshold-report --mode linear` today, at the cut nearest 4.2 (4.020,
the actual candidate score just below the 50 gold queries' score
distribution):

```
cut=4.020   kept_correct=38   kept_wrong=11   rejected_correct=0
```

Same shape as the v0.3.8 finding — **all 38 correct top-1 hits still kept,
zero correct results lost at the production cutoff.** `min_score=4.2` still
holds; no re-calibration needed this run.

## lse-kb doc count delta

368 → 368 — **unchanged.** `dream_apply.py`'s dedup pass demotes the
retired side of a merge (`record_outcome(success=False)`); it never
deletes, per the KB-DECAY rule (quarantine and expiry, never deletion —
`docs/traum-dreaming-plan.md` §4 "What we are explicitly NOT doing"). Doc
*count* is the wrong signal to watch for dedup effectiveness under this
design — doc *quality distribution* is (see below).

## Duplicate-pair count remaining

**3 pairs** at cosine 0.96–0.99, re-detected by a fresh dedup dry-run
against the post-apply corpus — but these are the **same 3 pairs already
merged today**, not new duplicates:

| Keep (unchanged) | Retire (now demoted, still present) | Cosine (today's re-run) |
|---|---|---|
| `e4ccd6e3734d2cac` | `de52870fae4bbf80` | 0.9899 |
| `3a8fce016b8e06d7` | `8e78e0e36d3931a4` | 0.9663 |
| `5bdcb7028c158353` | `3f242181b8b7b06d` | 0.9616 |

(Cosine values shifted slightly from the original run's 1.0000/0.9925/0.9848
— the dreamer's embedding call isn't perfectly deterministic run to run,
consistent with `dream-run-2026-07-11.md`'s note about the contradiction
pass; the *pairing* is identical.)

**Root cause:** the dedup pass's candidate-pair query pulls all of `lse-kb`
via `match_all` and doesn't exclude docs already demoted by a prior dedup
merge this run cycle — since `record_outcome` demotes rather than deletes,
the retired doc's content is still embedded and still matches its kept
counterpart at high cosine on every subsequent dedup pass. Left as-is, a
nightly dream would re-propose (and, if a human keeps saying yes, harmlessly
but wastefully re-apply) the same 3 merges indefinitely. **Flagged as a
Thread 2, Prompt 2.9 fix:** the dedup candidate query should exclude docs
with `stale=true` or a recent `record_outcome(success=False)` demotion from
this same dedup role, so a resolved pair stops resurfacing. Not fixed in
this measurement-only prompt.

## Demotions applied

**3** — the retired side of each dedup pair, quality 0.50 → 0.35
(`Kb Entry Es Memory Floor`, `Searxng Config`, `Pfsense Gateway Tools`),
applied and confirmed in `dream-run-2026-07-11.md`. **0** from the
stale-contradiction pass — all 7 `demote` proposals were rejected at the
human gate after verbatim-evidence review found each one a false positive
(see that doc for the per-item breakdown).

## Verdict

No regression on the metric that matters (production `linear` mode,
bit-for-bit identical recall@1/recall@3/MRR) and the `min_score=4.2`
threshold survives an 84%-growth re-sweep with the same "0 correct lost"
property it shipped with. **Clear to proceed to Thread 3** per Prompt 2.8's
own stop condition. Two non-blocking findings carried forward: (1) no ES
snapshot mechanism exists for a true same-day before/after — Thread 4,
Prompt 4.5 should specify one; (2) the dedup pass re-proposes already-merged
pairs because it doesn't exclude prior-demoted retire-side docs — Thread 2,
Prompt 2.9.
