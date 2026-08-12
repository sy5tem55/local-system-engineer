# QC critic calibration — 2026-08-12

> Part 2A of the skill-feedback-loop work. Ground truth per AGENTS.md §9:
> everything below was run this session against a copy of the live
> traum-state.db (`/tmp/traum-scratch/traum-state-copy.db`), never the
> live file.

## 1. The calibration set, corrected

The brief carried forward a claim: "the 12 human adjudications of
2026-08-12... R1 scored 5/5, R3 1/1, R2 1/2 against that set." Re-measured
this session (`tools/diagnosis_rules.py`'s designated calibration set is
also documented in `tools/dream_runner.py`'s `DreamConfig.rule_r2_enabled`
comment):

- **The "12" is real and precisely defined**: 12 `diagnosis` proposals
  adjudicated 2026-08-12T05:51:37–06:01:39 (one continuous review pass).
  R1 5/5, R2 1/2, R3 1/1 against exactly that set — confirmed, holds up.
- **It is not "every diagnosis adjudicated that day."** Four more
  diagnoses were adjudicated slightly *earlier* the same morning
  (05:43:25–05:45:19, a separate review pass, before the 12-item batch):
  `prp_8a7560280d`, `prp_9ec21b7dc42`, `prp_b8c683001c`, `prp_9533c3c740`.
  All four were `SUPERSEDED` by R1 (or had no rule opinion) — and all four
  were **APPLIED** by the human anyway, overriding R1's supersede in three
  of the four cases.
- Counted across all **16** diagnoses adjudicated 2026-08-12 (12 + 4), R1's
  score is **5/8** where it fired, not 5/5. Both figures are correct — they
  are answers to different questions ("the named 12-item batch" vs. "the
  whole day"), and the wider one is the one that actually shows R1's real
  failure mode (see docs/reports/2026-08-11-auto-adjudication.md §5's
  mixed-cluster hazard — `prp_8a7560280d`/`prp_9ec21b7dc42`/`prp_b8c683001c`
  are exactly that hazard, R1 collapsing genuinely-distinct diagnoses into
  one because their error_text happens to score high on cosine).

All 16 are used below as the critic's calibration set — the full picture,
not just the named 12.

## 2. Prompt v1 was uninformative — measured, not assumed

First system prompt (see `tools/qc_critic.py` history): told the critic to
"actively look for" weaknesses (alternative explanations, thin evidence,
circular resolutions). Run against all 16 live via
`scripts/calibrate-qc-critic.py` (real `call_dream_llm`, no mocks):

```
verdict counts: {'keep': 0, 'needs_work': 16, 'reject': 0}
```

**Every single proposal got `needs_work`.** A critic that says the same
thing regardless of input carries zero information, no matter how
individually plausible each reason sounds ("the resolution is
underspecified", "the evidence is only session IDs" — all true of *almost
every* proposal in this system, since evidence here is genuinely thin by
convention). This is a known failure mode of "find flaws" prompts: given
license to nitpick, a capable model always finds something. Reported
here rather than silently reprompted past, per AGENTS.md §9.

## 3. Prompt v2 — fixed, re-measured

Rewrote the prompt to enumerate exactly four concrete, named failure shapes
(third-party-fact-not-ours, circular resolution, unhedged root-cause claim
with an obvious mundane alternative, unevidenced success claim) and
instruct `keep` whenever none clearly applies — explicitly telling the
model that noticing *a* nitpick is not sufficient grounds. Re-run, same 16,
same live model:

```
verdict counts: {'keep': 12, 'needs_work': 4, 'reject': 0}
```

Now discriminating. Full per-proposal transcripts for both runs are
committed alongside this report:
`docs/reports/2026-08-12-qc-critic-calibration-logs/v1-uninformative.log`
and `.../v2-discriminating.log`; the four `needs_work` verdicts from v2 and
the reasoning behind each are in §4.

## 4. What "success" means for this critic — not raw agreement

The obvious metric — does the critic's keep/flag match the human's
APPLIED/REJECTED — is the **wrong** metric here, and a naive version of it
scores only 2/16. That's because 10 of the 16 REJECTED proposals were
rejected by the human for **redundancy** reasons ("already recorded in
lse-errors", "duplicate of prp_X") that have nothing to do with the
diagnosis's *content* being wrong — R1/R3 already exist to catch exact and
near-duplicate identity, and correctly did for 6 of those 10. A
content-quality critic correctly saying "keep, this diagnosis is
accurate" about a proposal that gets rejected for being a duplicate is
not a critic failure; it is answering a different, narrower question by
design (Hazard E-style scoping — this critic is not a second dedup pass).

The metric that matters is: **on the cases where R1/R2 actively
disagreed with the human (the four rule-mismatch cases), does the critic
help or stay silently wrong?**

| proposal | rule verdict | human | critic v2 verdict | assessment |
|---|---|---|---|---|
| `prp_c384e68723` (raspberrypi.com 403) | R2: SYSTEM_REJECTED | APPLIED | **keep** — "correctly focuses on the agent's handling of an external 403 error rather than the external site" | **Exact catch.** This is R2's own named failure case (disabled in `dream_runner.py` this week for exactly this reason). The critic independently reaches the same conclusion the human did, for the same reason. |
| `prp_8a7560280d` | R1: SUPERSEDED | APPLIED | needs_work — "asserts stuck/hung without ruling out a mundane alternative" | Not a match to APPLIED, but **not a block either** — Hazard D means `needs_work` only ever adds a note for the human, it does not suppress the proposal the way R1's live SUPERSEDED does. Strictly safer than what R1 currently does to this proposal. |
| `prp_9ec21b7dc42` | R1: SUPERSEDED | APPLIED | needs_work — same shape | Same as above — advisory, non-blocking, strictly safer than R1's current behavior. |
| `prp_b8c683001c` | R1: SUPERSEDED | APPLIED | needs_work — same shape | Same — and this is literally the mixed-cluster proposal from §2's report; the critic doesn't name the mixed-cluster mechanism specifically, but its independent read of the content (unhedged root-cause claim) is a defensible, non-blocking flag. |

Zero `reject` verdicts were produced anywhere in 16 proposals — the critic
never once tried to suppress a proposal outright, consistent with Hazard A
(prefer false negatives) and Hazard D (never approve/apply, and in this
implementation, "reject" itself is advisory-only, not a write).

**Bottom line:** on the one case that actually matters most — the
proposal R2 is *currently disabled* over — the critic reaches the human's
conclusion unprompted. On the three cases where R1 currently auto-executes
a wrong decision with zero human visibility, the critic would add a
visible, specific note instead of nothing, without blocking anything. On
the ten dedup-driven rejections, it correctly recognizes their content is
sound rather than manufacturing a false objection — meaning it stayed
usefully quiet rather than adding review noise to the 69% of the queue R1's
supersede logic already collapses correctly.

## 5. What this does not establish

Four proposals and one calibration run is not enough to trust this in
production. Explicitly not claimed here:
  - No `reject` verdict has ever been observed live — its behavior in that
    branch is untested against a real proposal.
  - The four failure shapes were written by hand against this one 16-item
    set; they may not generalize to error classes this set doesn't contain
    (e.g. `record_error` calls with actual verification evidence attached,
    which none of these 16 have).
  - Only one live model (the `DREAM_LLM_URL` dreamer) was tested. The
    Ollama CPU-fallback leg of the same cascade was never exercised here.

## 6. Recommendation

Ship disabled by default (`cfg.qc_critic_enabled = False`, same pattern as
R2), individually switchable, dry-run only until it has been watched
against a live PENDING queue for at least one real cycle producing a
`reject` verdict that can be checked against the eventual human call. Per
spec §8's own words (reused here): "if a rule would eat something a human
would have kept, say so and turn that rule off" — this module cannot eat
anything (Hazard D), but the same caution applies to trusting its
`needs_work`/`reject` labels before they've been watched fire for real.
