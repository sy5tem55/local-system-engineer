"""
Unit tests for SPEC-gate-toil-2026-08 -- stop spending the Human Gate on
things already known.

Two independent defects, same file(s):

  Defect 1 (dream_runner.py): a BLOCKED attempt's summary carried only
  {"dependency": ...}, discarding any sub_passes telemetry that had
  already been computed -- the exact NULL/BLOCKED ambiguity R4 was
  reframed to fix, resurfacing one level down. Fix: initialise
  sub_passes = None before the try (Hazard D -- an unbound reference in
  the except clause would turn a clean BLOCKED into a NameError), and
  fold it into the BLOCKED summary the same way the success path already
  does.

  Defect 2 (traum_state.py): `diagnosis` proposals fingerprinted their
  full body, including reworded-every-run model prose and a growing
  evidence list, so repeat_prior() never fired and the same handful of
  errors kept re-proposing themselves against the Human Gate. Fix:
  `diagnosis` proposals are identified narrowly, by
  {type, call, args.error_text, args.context} -- the cluster-derived,
  stable part of the payload -- so a reworded re-draft collides with the
  applied original and is auto-superseded before it reaches the gate.
  Scoped to `diagnosis` only (see the comment above
  `_NARROW_IDENTITY_TYPES` in traum_state.py for why this spec's Hazard B
  claim that `skill-candidate` "has the same shape" does not hold against
  the actual live payload shape, and was not applied to it).

Covers the spec's numbered tests (Sec7):
  1. A blocked pass with sub_passes bound records them in the attempt
     summary alongside dependency.                            [load-bearing]
  2. A blocked pass where the pass function itself never got to assign
     sub_passes (the elasticsearch dependency check upstream of it fails
     first) still records BLOCKED cleanly, no NameError.
                                                     [load-bearing -- Hazard D]
  3. Two diagnosis proposals, identical error_text+context but different
     interpretation/why/evidence, produce the same fingerprint.
                                                                [load-bearing]
  4. Two diagnosis proposals differing in error_text produce different
     fingerprints.
  5. A diagnosis whose fingerprint matches an APPLIED prior is
     superseded, not left PENDING, and its reason names the prior id
     (and, per Sec5.3, its state).                             [load-bearing]
  6. dedup, demote, reverify and kb-fact fingerprints are byte-identical
     to today's (full-body-minus-ignored-keys) for the same payloads.
                                                     [load-bearing -- Hazard B]
  7. Pair atomicity for dedup still holds.

Run:
    /home/sy5/owui/bin/python3 -m pytest tests/test_gate_toil.py -v
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402
import traum_state as ts  # noqa: E402


# ---------------------------------------------------------------------------
# Tests 1 & 2 -- dream_runner.py main(), real fault injection through the
# BLOCKED except-clause. Same fixture convention as
# tests/test_dream_crash_discipline.py::TestMainFaultInjection.
# ---------------------------------------------------------------------------

class TestBlockedSummaryCarriesSubPasses:

    def _run_blocked(self, tmp_path, monkeypatch, *, pass_name, search_index_fn,
                      pass_func=None):
        episode_dir = tmp_path / "episodes"
        dream_dir = tmp_path / "dreams"
        episode_dir.mkdir()
        dream_dir.mkdir()

        monkeypatch.setattr(dr, "search_index", search_index_fn)
        monkeypatch.setattr(dr._epidx, "build_manifest", lambda *a, **k: {"scanned": 0})
        monkeypatch.setattr(dr.dream_digest, "refresh_digest", lambda **k: None)
        if pass_func is not None:
            monkeypatch.setitem(dr.PASS_FUNCS, pass_name, pass_func)

        argv = [
            "--pass", pass_name,
            "--episode-dir", str(episode_dir),
            "--dream-dir", str(dream_dir),
            "--agent-log", str(tmp_path / "agent.log"),
            "--no-dry-run",
        ]
        rc = dr.main(argv)

        state = ts.TraumState(ts.default_db_path(str(dream_dir)))
        attempts = state.list_attempts(state="BLOCKED", limit=1)
        assert attempts, "expected exactly one BLOCKED attempt to have been recorded"
        return rc, attempts[0]

    def test_1_bound_sub_passes_recorded_in_blocked_summary(self, tmp_path, monkeypatch):
        """Test 1, load-bearing: sub_passes already computed by the pass
        (e.g. both stale-contradiction sub-passes blocked on the same
        dreamer outage) must survive into the BLOCKED attempt summary
        alongside `dependency`, not be discarded."""
        sub_passes = {
            "reverify": {"state": "BLOCKED", "proposals": 0, "dependency": "dream-llm"},
            "demote": {"state": "BLOCKED", "proposals": 0, "dependency": "dream-llm"},
        }

        def blocked_pass(cfg, sessions, episodes_by_session, kb_docs, error_docs):
            return [], "DREAMER UNAVAILABLE -- (no reply)", None, sub_passes

        rc, attempt = self._run_blocked(
            tmp_path, monkeypatch,
            pass_name="stale-contradiction",
            search_index_fn=lambda cfg, index, body: [],
            pass_func=blocked_pass,
        )

        assert rc == 3
        assert attempt["summary"]["dependency"] == "dream-llm"
        assert attempt["summary"]["sub_passes"] == sub_passes

    def test_2_unbound_sub_passes_no_name_error(self, tmp_path, monkeypatch):
        """Test 2, load-bearing -- Hazard D: the ES dependency check that
        runs BEFORE the pass function is ever called (cfg.pass_name in
        ("dedup", "stale-contradiction")) fails here, so the pass function
        never runs and sub_passes is never assigned by the
        `raw_proposals, narrative, null_record, sub_passes = pass_result`
        line. Before this fix, referencing `sub_passes` in the except
        clause under this exact condition was a NameError that replaced a
        clean BLOCKED with a crash. It must not raise, and the summary
        must have no sub_passes key at all (nothing was ever bound)."""

        def raise_es_failure(cfg, index, body):
            raise RuntimeError("elasticsearch unreachable in test")

        rc, attempt = self._run_blocked(
            tmp_path, monkeypatch,
            pass_name="dedup",
            search_index_fn=raise_es_failure,
        )

        assert rc == 3
        assert attempt["summary"]["dependency"] == "elasticsearch"
        assert "sub_passes" not in attempt["summary"]


# ---------------------------------------------------------------------------
# Tests 3, 4, 6 -- traum_state.proposal_fingerprint, pure-function level.
# ---------------------------------------------------------------------------

def _diagnosis(*, error_text="TypeError: 'NoneType' object is not subscriptable",
              context="dream-runner insights pass, patterns domain",
              interpretation="v1 interpretation", resolution="v1 resolution",
              anti_response="", why="v1 why", evidence=("ep-1", "ep-2")):
    return {
        "type": "diagnosis",
        "call": "record_error",
        "args": {
            "error_text": error_text,
            "context": context,
            "interpretation": interpretation,
            "resolution": resolution,
            "anti_response": anti_response,
        },
        "evidence": list(evidence),
        "why": why,
    }


def _dedup_pair(content, pair_id="doc-a::doc-b"):
    return {
        "type": "dedup",
        "call": "index_to_kb",
        "pair_id": pair_id,
        "args": {"title": content, "content": content, "quality_score": 0.5,
                 "source_tier": "inferred"},
        "why": "duplicate content",
    }


def _demote(doc_id="deadbeef00112233"):
    return {
        "type": "demote", "call": "mentor_demote",
        "args": {"doc_id": doc_id, "reason": "contradicted by session evidence"},
        "why": "contradiction observed",
    }


def _reverify(doc_id="reverify-doc-1"):
    return {
        "type": "reverify", "call": "kb_verify",
        "args": {"doc_id": doc_id},
        "why": "TTL expired",
    }


def _kb_fact(content="the service listens on port 8080"):
    return {
        "type": "kb-fact", "call": "index_to_kb",
        "args": {"title": content, "content": content, "topic": "infra",
                 "source_tier": "inferred", "quality_score": 0.5},
        "why": "observed in session",
    }


class TestDiagnosisFingerprintIdentity:

    def test_3_same_error_text_and_context_same_fingerprint(self):
        """Test 3, load-bearing: interpretation/resolution/why/evidence all
        differ (as a reworded re-draft would), but error_text and context
        -- the cluster-derived, stable identity -- match, so the
        fingerprint must match too."""
        a = _diagnosis(interpretation="first draft", why="reasoning A",
                       evidence=("ep-1",))
        b = _diagnosis(interpretation="second, richer draft", resolution="better fix",
                       anti_response="now filled in", why="reasoning B",
                       evidence=("ep-1", "ep-2", "ep-3"))
        assert ts.proposal_fingerprint(a) == ts.proposal_fingerprint(b)

    def test_4_different_error_text_different_fingerprint(self):
        """Test 4: a genuinely different failure signature must not
        collide."""
        a = _diagnosis(error_text="TypeError: 'NoneType' object is not subscriptable")
        b = _diagnosis(error_text="ConnectionError: dream-llm unreachable")
        assert ts.proposal_fingerprint(a) != ts.proposal_fingerprint(b)

    def test_4b_different_context_same_error_text_different_fingerprint(self):
        a = _diagnosis(context="dream-runner insights pass, patterns domain")
        b = _diagnosis(context="dream-runner insights pass, trends domain")
        assert ts.proposal_fingerprint(a) != ts.proposal_fingerprint(b)


class TestOtherProposalTypesFingerprintUnchanged:
    """Test 6, load-bearing -- Hazard B: dedup/demote/reverify/kb-fact must
    keep hashing their full body (minus _IDENTITY_IGNORED_KEYS), exactly as
    before this change. Proven directly against the pre-fix formula, not
    just "still passes today's tests"."""

    def _pre_fix_fingerprint(self, proposal):
        body = {k: v for k, v in proposal.items() if k not in ts._IDENTITY_IGNORED_KEYS}
        import hashlib
        import json
        canonical = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @pytest.mark.parametrize("proposal", [
        _dedup_pair("keep doc"),
        _demote(),
        _reverify(),
        _kb_fact(),
    ], ids=["dedup", "demote", "reverify", "kb-fact"])
    def test_6_fingerprint_byte_identical_to_pre_fix_formula(self, proposal):
        assert ts.proposal_fingerprint(proposal) == self._pre_fix_fingerprint(proposal)

    def test_6b_reworded_why_still_changes_fingerprint_for_these_types(self):
        """Unlike diagnosis, these types are NOT narrowed -- a reworded
        `why` must still produce a different fingerprint, proving the
        narrowing genuinely did not leak onto them."""
        a = _demote()
        b = {**_demote(), "why": "a differently-worded reason"}
        assert ts.proposal_fingerprint(a) != ts.proposal_fingerprint(b)


# ---------------------------------------------------------------------------
# Test 5 -- store-level: a diagnosis colliding with an APPLIED prior is
# superseded, and the reason names the prior's id and state.
# ---------------------------------------------------------------------------

def _store(tmp_path):
    return ts.TraumState(str(tmp_path / "traum-state.db"))


class TestDiagnosisSupersedesAppliedPrior:

    def test_5_reworded_diagnosis_superseded_names_prior_id_and_state(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")

        first_attempt = store.start_attempt(run["run_id"], "error-cluster")
        original = _diagnosis(interpretation="first draft", why="reasoning A")
        [first_row] = store.record_proposals(
            run["run_id"], first_attempt["attempt_id"], [original]
        )
        assert first_row["state"] == "STAGED"
        store.finish_attempt(first_attempt["attempt_id"], "SUCCEEDED")
        assert store.get_proposal(first_row["proposal_id"])["state"] == "PENDING"

        store.claim_proposals([first_row["proposal_id"]], actor="test-operator")
        store.finalize_proposals(
            [first_row["proposal_id"]], succeeded=True, actor="test-operator"
        )
        applied = store.get_proposal(first_row["proposal_id"])
        assert applied["state"] == "APPLIED"

        # A later run re-drafts the SAME error/context with richer prose --
        # exactly the run_e5b5132c scenario from SPEC-gate-toil-2026-08.
        second_attempt = store.start_attempt(run["run_id"], "error-cluster")
        redraft = _diagnosis(
            interpretation="second, richer draft with more detail",
            resolution="an improved fix", anti_response="now filled in",
            why="reasoning B", evidence=("ep-9", "ep-10"),
        )
        [second_row] = store.record_proposals(
            run["run_id"], second_attempt["attempt_id"], [redraft]
        )

        assert second_row["state"] == "SUPERSEDED"
        reason = second_row["reason"]
        assert applied["proposal_id"] in reason
        assert "APPLIED" in reason
        # never left PENDING alongside the applied original
        assert store.list_proposals(state="PENDING") == []


# ---------------------------------------------------------------------------
# Test 7 -- dedup pair atomicity still holds (unaffected by the diagnosis-
# only narrowing).
# ---------------------------------------------------------------------------

class TestDedupPairAtomicityUnaffected:

    def test_7_partial_pair_repeat_stays_reviewable_full_repeat_supersedes(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["dedup"], source="cli")

        first_attempt = store.start_attempt(run["run_id"], "dedup")
        original = [
            _dedup_pair("keep doc"),
            _dedup_pair("retire doc"),
        ]
        store.record_proposals(run["run_id"], first_attempt["attempt_id"], original)
        store.finish_attempt(first_attempt["attempt_id"], "SUCCEEDED")

        # one member changes -> pair stays fully reviewable, not superseded.
        changed_attempt = store.start_attempt(run["run_id"], "dedup")
        changed = [original[0], _dedup_pair("retire doc with new evidence")]
        changed_rows = store.record_proposals(
            run["run_id"], changed_attempt["attempt_id"], changed
        )
        assert {row["state"] for row in changed_rows} == {"STAGED"}
        store.finish_attempt(changed_attempt["attempt_id"], "SUCCEEDED")
        assert {
            store.get_proposal(row["proposal_id"])["state"] for row in changed_rows
        } == {"PENDING"}

        # exact repeat of that same pair -> both members superseded together,
        # never a SUPERSEDED+PENDING split.
        repeat_attempt = store.start_attempt(run["run_id"], "dedup")
        repeat_rows = store.record_proposals(
            run["run_id"], repeat_attempt["attempt_id"], changed
        )
        assert {row["state"] for row in repeat_rows} == {"SUPERSEDED"}
        for row in repeat_rows:
            assert "exact_pair_already_resolved_or_queued:" in row["reason"]
