"""tools/diagnosis_rules.py — SPEC-auto-adjudication-2026-08.

Content rules for `diagnosis` proposals, evaluated at record time (live, via
dream_runner.py's apply_diagnosis_rules()) or retroactively (offline, via
scripts/dry-run-diagnosis-rules.py against the already-PENDING queue). Every
rule may only REJECT or SUPERSEDE (Hazard D: no rule ever approves/applies)
and every rule only ever looks at `type == "diagnosis"` proposals (Hazard E:
dedup/demote/reverify/kb-fact/prompt-rule are out of scope, untouched).

R1 -- semantic near-duplicate of an existing PENDING/APPLIED diagnosis ->
      SUPERSEDED. The rule that does most of the work (SPEC §1/§4): exact
      fingerprint dedup (SPEC-gate-toil-2026-08's {error_text, context}
      narrowing in traum_state.py) only catches byte-identical repeats;
      this catches the reworded ones.
R2 -- error_text carries an HTTP status against a non-local URL -> that is a
      fact about someone else's website, not a diagnosis of this system ->
      SYSTEM_REJECTED.
R3 -- `resolution` adds nothing over `error_text` (the fix is already
      stated verbatim in the error) -> SYSTEM_REJECTED.

Design notes:
  * Every embedding call is *injected* (`embed_fn: Callable[[str], list]`),
    never imported from dream_runner.py, so this module has no dependency
    on DreamConfig/Ollama/network and stays independently unit-testable —
    tests pass a small deterministic fake; the live caller passes
    `functools.partial(dream_runner.embed_text, cfg)`.
  * Reason-code prefix (Hazard B): traum_state.py's repeat_prior() only
    treats a SYSTEM_REJECTED proposal as a valid "prior" — preventing an
    endless re-draft/re-reject churn of the same content every run — if its
    reason starts with one of a fixed set of prefixes. R2/R3 mint the
    "rule:" prefix; that prefix has been added to repeat_prior()'s honored
    tuple in the same change that introduces this module (see
    traum_state.py). R1 supersedes rather than rejects, and SUPERSEDED is
    *already* unconditionally honored by repeat_prior(), so R1 needs no
    prefix registration.
  * Thresholds are calibrated against the live PENDING `diagnosis` queue,
    not inherited from dream_runner.py's 0.92 KB-dedup floor (Hazard C:
    diagnoses are shorter and more formulaic than KB documents and will
    score higher for the same semantic distance) — see
    docs/reports/2026-08-11-auto-adjudication.md for the calibration
    transcript the defaults below were chosen from. R1's calibrated value
    happens to land on 0.92 too, but that is coincidence, not reuse: it was
    derived from real cosine scores over the live diagnosis queue itself
    (confirmed-duplicate pairs scored 0.9299-1.0, confirmed-distinct pairs
    scored <=0.8439), not copied from dream_runner.py's constant.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------
RULE_REASON_PREFIX = "rule:"
R1_REASON_SEMANTIC_DUPLICATE = "semantic_duplicate"
R2_REASON_THIRD_PARTY = "third_party_resource_error"
R3_REASON_RESOLUTION_REDUNDANT = "resolution_redundant_with_error_text"

# Calibrated 2026-08-11 against the live PENDING `diagnosis` queue on
# LUCIFER via scripts/dry-run-diagnosis-rules.py (spec §4/§8: dry-run first,
# calibrate from its output, then wire live). R1=0.92: confirmed-duplicate
# error_text pairs (reworded CancelledError, node3090 timeout variants,
# reworded SSH-exit-255 text) scored 0.9299-1.0; the highest confirmed-
# distinct pair (SCP Permission-denied vs SSH connect-timed-out) scored
# 0.6607, with a separate ambiguous "bare 'Connection timed out'" cluster at
# 0.8287-0.8439 left conservatively unmerged. R3=0.82: the one real
# redundant-resolution case (pfSense API key) scored 0.8345; five other
# live diagnoses with genuinely-informative resolutions scored 0.6521-0.7704
# — see the report for the full transcript, including the one open gap:
# 16 live PENDING reduce to 5 survivors at these thresholds, not "four or
# fewer" — two of the five are Hazard-C-mandated-separate (Permission
# denied vs Connection timed out) and the other three are novel facts with
# no existing APPLIED prior to supersede against; forcing a merge among
# those three was rejected as unsafe (Hazard A) rather than tuned to hit
# the number.
DIAGNOSIS_DUP_THRESHOLD_DEFAULT = 0.92
DIAGNOSIS_REDUNDANT_THRESHOLD_DEFAULT = 0.82


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _args(proposal: dict) -> dict:
    return proposal.get("args") or {}


def _error_text(proposal: dict) -> str:
    return str(_args(proposal).get("error_text") or "").strip()


# ---------------------------------------------------------------------------
# R2 — third-party resource error
# ---------------------------------------------------------------------------

_PRIVATE_HOST_SUFFIXES = (".home.arpa", ".local", ".localhost", ".lan", ".internal")
_PRIVATE_BARE_HOSTS = {
    "localhost", "lucifer", "node3090", "node4090", "node5090",
    "pfsense", "traum", "goethe",
}
_URL_RE = re.compile(r"https?://[^\s'\"<>)]+")
_HTTP_STATUS_RE = re.compile(r"\b[1-5]\d\d\b")


def is_local_host(hostname: str) -> bool:
    """True only when `hostname` is confidently internal to this system.

    R2 uses this to tell "an HTTP error about someone else's website"
    (SYSTEM_REJECTED) apart from "an HTTP error about our own
    infrastructure" (leave for a human — R2 must not fire). Conservative on
    purpose (Hazard A): an unrecognized host defaults to *not* local, i.e.
    R2 stays silent and the proposal stays reviewable, rather than the
    reverse — a false "this is local" verdict would silently suppress a
    real third-party-error diagnosis.
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host in _PRIVATE_BARE_HOSTS:
        return True
    if host.endswith(_PRIVATE_HOST_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def rule_r2_third_party_resource_error(proposal: dict):
    """R2. Structural/regex only, no embedding needed. Returns
    (initial_state, initial_reason) or None (no opinion)."""
    if proposal.get("type") != "diagnosis":
        return None
    error_text = _error_text(proposal)
    if not error_text or not _HTTP_STATUS_RE.search(error_text):
        return None
    urls = _URL_RE.findall(error_text)
    if not urls:
        return None
    for url in urls:
        host = urlparse(url).hostname or ""
        if not is_local_host(host):
            return (
                "SYSTEM_REJECTED",
                f"{RULE_REASON_PREFIX}{R2_REASON_THIRD_PARTY}:{host}",
            )
    return None


# ---------------------------------------------------------------------------
# R3 — resolution adds nothing over error_text
# ---------------------------------------------------------------------------

def rule_r3_resolution_redundant(proposal: dict, *, embed_fn, threshold: float):
    """R3. The pfSense case: `resolution` restates `error_text` almost
    verbatim. Approximated by embedding distance between the two fields —
    intra-proposal, no priors needed. Deliberately the rule most likely to
    over-fire if miscalibrated (resolution prose naturally echoes
    error_text vocabulary even when it adds real interpretation), so the
    caller must calibrate this threshold conservatively and prefer false
    negatives (spec §4)."""
    if proposal.get("type") != "diagnosis":
        return None
    args = _args(proposal)
    error_text = _error_text(proposal)
    resolution = str(args.get("resolution") or "").strip()
    if not error_text or not resolution:
        return None
    sim = _cosine(embed_fn(error_text), embed_fn(resolution))
    if sim >= threshold:
        return (
            "SYSTEM_REJECTED",
            f"{RULE_REASON_PREFIX}{R3_REASON_RESOLUTION_REDUNDANT}:{sim:.4f}",
        )
    return None


# ---------------------------------------------------------------------------
# R1 — semantic near-duplicate
# ---------------------------------------------------------------------------

def rule_r1_semantic_duplicate(proposal: dict, priors: list, *, embed_fn,
                                threshold: float, embed_cache: dict | None = None):
    """R1. `priors` is an iterable of dicts shaped like
    TraumState.list_proposals()'s output — each with `proposal_id`, `state`,
    and `proposal` (the stored payload, `type`/`args`/... ) — already
    expected to be `type == "diagnosis"` and to exclude `proposal` itself
    (the caller filters; this function re-checks type/id defensively but
    does not re-derive the PENDING/APPLIED state filter). Supersedes by the
    single highest-scoring prior >= threshold, naming its id and state —
    same shape as traum_state.py's existing exact-match supersede reason
    (`exact_already_resolved_or_queued:{id}:{state}`) so Console output
    reads consistently regardless of which mechanism fired.

    `embed_cache`, if passed, is a plain dict the caller reuses across
    multiple calls in one batch (keyed by error_text) so N candidates in
    one run only re-embed each prior once instead of once per candidate.
    """
    if proposal.get("type") != "diagnosis":
        return None
    candidate_text = _error_text(proposal)
    if not candidate_text:
        return None
    if embed_cache is None:
        embed_cache = {}

    def embed_cached(text: str):
        if text not in embed_cache:
            embed_cache[text] = embed_fn(text)
        return embed_cache[text]

    candidate_id = proposal.get("proposal_id")
    candidate_vec = embed_cached(candidate_text)
    best_prior_id = None
    best_prior_state = None
    best_sim = -1.0
    for prior in priors:
        prior_payload = prior.get("proposal") or prior
        if prior_payload.get("type") != "diagnosis":
            continue
        prior_id = prior.get("proposal_id") or prior_payload.get("proposal_id")
        if candidate_id and prior_id == candidate_id:
            continue
        prior_text = _error_text(prior_payload)
        if not prior_text:
            continue
        sim = _cosine(candidate_vec, embed_cached(prior_text))
        if sim > best_sim:
            best_sim = sim
            best_prior_id = prior_id
            best_prior_state = prior.get("state")
    if best_prior_id is not None and best_sim >= threshold:
        return (
            "SUPERSEDED",
            f"{RULE_REASON_PREFIX}{R1_REASON_SEMANTIC_DUPLICATE}:"
            f"{best_prior_id}:{best_prior_state}",
        )
    return None
