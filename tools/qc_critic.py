"""tools/qc_critic.py — adversarial quality-control critic for `diagnosis`
proposals (Part 2A of the 2026-08-12 TRAUM feedback-loop work).

Complements R1/R2/R3 (tools/diagnosis_rules.py), which are mechanical
(cosine similarity, regex, host allowlists) and cannot make a *content*
judgement. Measured this session (see
docs/reports/2026-08-12-qc-critic-calibration.md): the designated 12-item
calibration set (dream_runner.py's DreamConfig comment, operator
adjudications 2026-08-12T05:51-06:01) does confirm R1 5/5, R2 1/2, R3 1/1 —
that figure holds up. But it is a narrower set than "every diagnosis
adjudicated that day": four more diagnoses were adjudicated slightly
earlier (05:43-05:45, outside the named window) where R1 fired and was
overridden by the human three times. Counted across all 16 same-day
diagnosis adjudications, R1 is 5/8, not 5/5 — the narrow 12-item set simply
didn't include those three cases. The critic exists specifically to catch
what that wider look shows the rules miss:
  - R1 false positives: a near-duplicate by error_text cosine that the
    human judged a genuinely separate diagnosis and applied anyway
    (prp_8a7560280d, prp_9ec21b7dc42, prp_b8c683001c — the same
    mixed-cluster hazard flagged in docs/reports/2026-08-11-auto-adjudication.md §5).
  - R2 false positives: an HTTP error against a third-party host that is
    *still* a real diagnosis of this system (our agent's handling of the
    block, not the remote site) — prp_c384e68723, R2's own known failure
    this week.
  - Cases no rule even looks at: "novel" proposals (no R1/R2/R3 opinion)
    that a human still rejected as duplicates of the general lse-errors KB
    (not just other diagnosis proposals, which is all R1 compares against)
    or as one-off deployment-day transients.

HAZARD D (SPEC-auto-adjudication-2026-08 §3): this module NEVER approves or
applies. Its only three possible verdicts are `keep`, `needs_work`, and
`reject` — and `reject` here means "flag for the human with a reason
attached", never a write to proposal state. No function in this file calls
TraumState.record_proposals or any KB-write path. Grep for it: this module
imports nothing from traum_state.py and has no sqlite/ES write calls at all.

ADVERSARIAL + VERIFY PATTERN (brief, Part 2A): the system prompt instructs
the critic to actively try to REFUTE the proposal's diagnosis — find the
alternative explanation, find the missing evidence — and to default to
`keep` whenever it cannot construct a specific, concrete objection. A critic
that defaults to suspicion produces exactly the "eats a true diagnosis"
failure Hazard A already warns about for R1-R3; false negatives (an
overcautious `keep` on something that should have been flagged) are the
safe failure direction here, not false positives.

CALIBRATION HISTORY (docs/reports/2026-08-12-qc-critic-calibration.md): the
first prompt tried was too permissive about what counts as a flaw — told to
"actively look for" weaknesses, the live model found *something* to nitpick
in all 16/16 calibration proposals and returned needs_work uniformly (0
keep, 0 reject), which is no better than a coin that always says "maybe".
The prompt below is the fixed version: it enumerates exactly four concrete
failure shapes and instructs "keep" whenever none clearly applies, even if
something is technically imprecise. Re-measure before trusting any future
edit to this prompt the same way — a critic that always says the same thing
provides zero information no matter how each individual verdict reads.

Design notes (same shape as diagnosis_rules.py):
  * The LLM call is *injected* (`call_llm_fn: Callable[[str, str], str]`,
    system_prompt then user_content, returning the raw reply string) —
    never imported from dream_runner.py — so this module is independently
    unit-testable with a deterministic fake and has no import-time network
    dependency. The live caller passes
    `functools.partial(dream_runner.call_dream_llm, cfg=cfg)`.
  * Parsing tolerates the same `<think>...</think>` + code-fence noise as
    dream_runner.parse_dream_envelope, duplicated rather than imported
    (this module's envelope shape — a single {verdict, reason} object, not
    a list-under-a-key — doesn't fit that function's contract, and
    duplicating ~10 lines of regex is cheaper than bending its API).
  * On ANY parse failure, network error, or an LLM reply that doesn't name
    one of the three known verdicts, the result is `keep` with a `reason`
    that says why parsing failed — never silently dropped, never treated
    as `reject`. A broken critic must fail toward "give the human
    everything", not toward "quietly approve nothing was said."
"""
from __future__ import annotations

import json
import re
from typing import Callable

VERDICT_KEEP = "keep"
VERDICT_NEEDS_WORK = "needs_work"
VERDICT_REJECT = "reject"
_KNOWN_VERDICTS = {VERDICT_KEEP, VERDICT_NEEDS_WORK, VERDICT_REJECT}

CRITIC_SYSTEM_PROMPT = """You are an adversarial quality-control reviewer for a \
system-diagnosis proposal about to be shown to a human for approval. Your job \
is to try to REFUTE the proposal, not to confirm it — but "keep" must be your \
most common answer. Almost every diagnosis can be nitpicked (evidence could \
always be more detailed, an alternative cause can almost always be imagined); \
noticing that is NOT grounds for "needs_work" or "reject". Only flag \
something you would tell a human reviewer, in one sentence, as a reason NOT \
to click approve as-is.

Ask yourself first: "If I were the human, would this specific issue change \
my decision?" If the honest answer is no, the verdict is "keep" — full stop, \
even if you can name something that is technically imperfect.

Only "reject" or "needs_work" when you can point to ONE of these SPECIFIC \
failure shapes — nothing else qualifies:
  1. The proposal is entirely about a fact on someone else's system/website \
(e.g. "site X returned a 403") with NO indication the proposal is really \
about how *this system's own agent* handled that condition.
  2. `resolution` is circular — it literally restates `error_text` back as \
the fix, adding no new action.
  3. `interpretation` asserts a specific root cause (e.g. "the process is \
hung", "this is a stuck deadlock") that the given `error_text`/`evidence` \
could equally be explained by an ordinary, mundane alternative (e.g. plain \
network latency, a slow but eventually-completing operation) which the \
proposal never rules out AND never hedges about.
  4. A `success`/verification claim is made with zero evidence to back it, \
where evidence is required for the claim's kind (not just "could have more \
detail" — literally no verification output at all).

Thin evidence, a resolution you'd word differently, a diagnosis that names a \
plausible-but-not-proven cause without overreaching — these are normal and \
must be "keep". You are not grading writing quality; you are looking for a \
concrete, name-able reason a human would refuse to approve this.

You may NOT approve, apply, or edit anything. Your only output is a verdict \
for a human reviewer:
  - "reject": failure shape 1 or 2 above, clearly present — name which one.
  - "needs_work": failure shape 3 or 4 above, clearly present — name which \
one and what evidence/hedge is missing.
  - "keep": none of the four failure shapes clearly apply. This is the \
default and the correct answer whenever you are uncertain — do not guess \
toward "reject" or "needs_work". A missed flag costs a few extra seconds of \
human review; a wrongful flag can suppress a true diagnosis, which is worse.

Reply with ONLY a JSON object, no other text:
{"verdict": "keep" | "needs_work" | "reject", "reason": "<name the specific failure shape (1-4) and why, one or two sentences>"}
"""


def format_proposal_for_critique(payload: dict, prior_rule_verdict: str | None = None) -> str:
    """Build the user_content shown to the critic for one `diagnosis`
    proposal. `payload` is the proposal's stored dict (same shape
    diagnosis_rules.py reads: `payload["args"]` holds error_text/context/
    interpretation/resolution/anti_response).

    `prior_rule_verdict`, if given, is a short string describing what
    R1/R2/R3 already decided (e.g. "R1: SUPERSEDED by prp_xxx (APPLIED)")
    — included so the critic can specifically weigh in on a mechanical
    rule's call rather than just re-deriving the whole judgement blind.
    None means no rule fired (a "novel" proposal reaching the critic
    un-touched).
    """
    args = payload.get("args") or {}
    lines = [
        f"error_text: {args.get('error_text', '') or '(none given)'}",
        f"context: {args.get('context', '') or '(none given)'}",
        f"interpretation: {args.get('interpretation', '') or '(none given)'}",
        f"resolution: {args.get('resolution', '') or '(none given)'}",
    ]
    evidence = payload.get("evidence")
    if evidence:
        ev_text = "; ".join(str(e) for e in evidence) if isinstance(evidence, list) else str(evidence)
        lines.append(f"evidence: {ev_text}")
    if prior_rule_verdict:
        lines.append(f"mechanical rule verdict (R1/R2/R3): {prior_rule_verdict}")
    else:
        lines.append("mechanical rule verdict (R1/R2/R3): none fired (novel)")
    return "\n".join(lines)


def parse_critic_reply(reply: str) -> dict:
    """Parse the critic's raw LLM reply into {"verdict", "reason"}.

    Fails open toward `keep` (see module docstring) on any of: an empty
    reply, unparseable JSON, missing `verdict` key, or a `verdict` value
    outside the three known ones. The returned dict always has a `reason`
    explaining what happened, including on the fail-open path, so a
    silent-keep is always visible to whoever reads the run's output.
    """
    if not reply or not reply.strip():
        return {"verdict": VERDICT_KEEP, "reason": "empty reply from critic — defaulting to keep"}

    clean = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
    clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean).rstrip("`").strip()

    if clean.startswith("<think>"):
        # unterminated <think> (truncated reply) — nothing usable survived
        return {"verdict": VERDICT_KEEP,
                "reason": "critic reply truncated mid-<think> — defaulting to keep"}

    # tolerate leading/trailing prose around the JSON object
    match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
    if not match:
        return {"verdict": VERDICT_KEEP,
                "reason": f"no JSON object in critic reply — defaulting to keep (raw: {clean[:120]!r})"}

    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {"verdict": VERDICT_KEEP,
                "reason": f"critic reply JSON did not parse ({exc}) — defaulting to keep"}

    verdict = obj.get("verdict")
    reason = str(obj.get("reason") or "").strip()
    if verdict not in _KNOWN_VERDICTS:
        return {"verdict": VERDICT_KEEP,
                "reason": f"critic returned unknown verdict {verdict!r} — defaulting to keep"}
    if not reason:
        return {"verdict": VERDICT_KEEP,
                "reason": "critic gave a verdict with no reason attached — defaulting to keep "
                          "(a verdict without a reason cannot be audited)"}
    return {"verdict": verdict, "reason": reason}


def critique_proposal(payload: dict, call_llm_fn: Callable[[str, str], str],
                       prior_rule_verdict: str | None = None) -> dict:
    """Run the critic on one proposal. Never writes anything — the caller
    (a dry-run script or, later, a dream_runner pass) is responsible for
    whatever it does with the returned verdict, and Hazard D means that can
    never be `record_proposals` with an approve/apply state."""
    user_content = format_proposal_for_critique(payload, prior_rule_verdict)
    try:
        reply = call_llm_fn(CRITIC_SYSTEM_PROMPT, user_content)
    except Exception as exc:  # noqa: BLE001 — a broken critic must not crash the run
        return {"verdict": VERDICT_KEEP,
                "reason": f"critic call raised {exc!r} — defaulting to keep"}
    if isinstance(reply, str) and reply.startswith(("ERROR:", "BUDGET_EXHAUSTED:")):
        return {"verdict": VERDICT_KEEP, "reason": f"critic call failed ({reply}) — defaulting to keep"}
    return parse_critic_reply(reply)


def run_qc_critic(proposals: list[dict], call_llm_fn: Callable[[str, str], str],
                   rule_verdicts: dict | None = None) -> list[dict]:
    """Run the critic over a batch of `diagnosis` proposals. Read-only /
    write-nothing (Hazard D) — this returns a list of verdicts for a human
    or a dry-run report to consume, full stop.

    `proposals`: list of raw proposal dicts (`proposal_id`, `type`,
    `args`/payload fields at top level or nested under `payload` —
    both shapes accepted, matching how diagnosis_rules.py's `_args()`
    tolerates either).
    `rule_verdicts`: optional {proposal_id: descriptive string} from a
    prior R1/R2/R3 pass, threaded through to `format_proposal_for_critique`
    so the critic sees what the mechanical rules already decided.
    """
    rule_verdicts = rule_verdicts or {}
    results = []
    counts = {VERDICT_KEEP: 0, VERDICT_NEEDS_WORK: 0, VERDICT_REJECT: 0}
    for proposal in proposals:
        if proposal.get("type") not in (None, "diagnosis"):
            continue  # Hazard E — scope to diagnosis, same as R1-R3
        proposal_id = proposal.get("proposal_id")
        payload = proposal.get("payload") or proposal
        verdict = critique_proposal(payload, call_llm_fn, rule_verdicts.get(proposal_id))
        counts[verdict["verdict"]] += 1
        results.append({"proposal_id": proposal_id, **verdict})
    return results, counts
