"""
Unit/integration tests for SPEC-auto-adjudication-2026-08 -- content rules
(R1/R2/R3) for `diagnosis` proposals.

Covers the spec's numbered tests (Sec6):
  1. Four reworded CancelledError diagnoses -> one PENDING survivor, three
     SUPERSEDED, each naming it.                                [load-bearing]
  2. Distinct failure texts (different underlying cause) stay separate
     under the calibrated R1 threshold.               [load-bearing -- Hazard C]
  3. An R2-rejected proposal re-offered next run (same narrow identity) is
     not re-drafted into PENDING.                      [load-bearing -- Hazard B]
  4. A 403/404 against a third-party URL is rejected; the same status
     against a local/internal service is not.
  5. No rule can produce APPLIED or STAGED.              [load-bearing -- Hazard D]
  6. dedup/demote/reverify/kb-fact proposals are completely untouched by
     apply_diagnosis_rules, and their fingerprints stay byte-identical to
     the pre-SPEC-auto-adjudication formula.             [load-bearing -- Hazard F]
  7. Each rule is individually disableable; all three disabled restores
     exactly today's (pre-this-spec) behavior.
  8. scripts/dry-run-diagnosis-rules.py writes nothing to the database.

Fake embeddings only (no live Ollama dependency): `_fake_embed` is a
deterministic (md5-hashed) bag-of-words vector over the input text, giving
high cosine similarity for texts sharing most of their vocabulary (a
reworded redraft) and low cosine similarity for texts that don't. This
exercises the RULE LOGIC (threshold comparisons, reason naming, ordering,
enable flags) hermetically; the actual embedding quality was validated
separately against live Ollama during calibration (see
docs/reports/2026-08-11-auto-adjudication.md).

Run:
    /home/sy5/owui/bin/python3 -m pytest tests/test_diagnosis_rules.py -v
"""

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import diagnosis_rules as dgr  # noqa: E402
import dream_runner as dr  # noqa: E402
import traum_state as ts  # noqa: E402

SCRIPT_PATH = REPO_ROOT / "scripts" / "dry-run-diagnosis-rules.py"


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _fake_embed(text: str, dims: int = 96) -> list:
    """Deterministic (no network) stand-in for dream_runner.embed_text:
    a hashed bag-of-words vector. Shares-most-vocabulary text scores near
    1.0; unrelated text scores near 0. Not a real embedding -- just enough
    structure to exercise threshold comparisons hermetically."""
    vec = [0.0] * dims
    for word in text.lower().split():
        idx = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % dims
        vec[idx] += 1.0
    return vec


def _cfg(**overrides):
    base = dict(
        rule_r1_enabled=True, rule_r2_enabled=True, rule_r3_enabled=True,
        diagnosis_dup_threshold=dgr.DIAGNOSIS_DUP_THRESHOLD_DEFAULT,
        diagnosis_redundant_threshold=dgr.DIAGNOSIS_REDUNDANT_THRESHOLD_DEFAULT,
        ollama_url="http://unused.invalid", embed_model="unused",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


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
        "type": "dedup", "call": "index_to_kb", "pair_id": pair_id,
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
    return {"type": "reverify", "call": "kb_verify", "args": {"doc_id": doc_id},
            "why": "TTL expired"}


def _kb_fact(content="the service listens on port 8080"):
    return {
        "type": "kb-fact", "call": "index_to_kb",
        "args": {"title": content, "content": content, "topic": "infra",
                  "source_tier": "inferred", "quality_score": 0.5},
        "why": "observed in session",
    }


@pytest.fixture(autouse=True)
def _fake_embed_text(monkeypatch):
    """Every test in this module runs with embed_text faked -- no live
    Ollama dependency for this test file."""
    monkeypatch.setattr(dr, "embed_text", lambda cfg, text: _fake_embed(text))


def _store(tmp_path):
    return ts.TraumState(str(tmp_path / "traum-state.db"))


def _record_one(store, run_id, cfg, proposal):
    """Run one diagnosis proposal through apply_diagnosis_rules then
    record_proposals in its own attempt -- simulates one dream-cycle run
    drafting/recording a single diagnosis, so cross-run supersede behavior
    (the real-world CancelledError scenario) is exercised, not same-batch.
    Returns the proposal's state AFTER finish_attempt -- record_proposals
    itself returns STAGED for a freshly-accepted proposal; STAGED only
    becomes PENDING once the attempt finishes (traum_state.py), so callers
    that want the resting state must re-fetch, exactly like
    tests/test_gate_toil.py::test_5 does."""
    attempt = store.start_attempt(run_id, "error-cluster")
    dr.apply_diagnosis_rules(cfg, store, [proposal])
    [row] = store.record_proposals(run_id, attempt["attempt_id"], [proposal])
    store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")
    return store.get_proposal(row["proposal_id"])


# ---------------------------------------------------------------------------
# Test 1 -- four reworded CancelledError diagnoses collapse to one survivor
# ---------------------------------------------------------------------------

class TestSemanticDuplicateCollapse:

    def test_1_four_reworded_cancelled_error_collapse_to_one(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg()
        # Long shared preamble, single differing trailing token -- with the
        # hashed bag-of-words fake embedding, cosine similarity for n shared
        # words + 1 differing word is n/(n+1); this needs a comfortable
        # margin over the real calibrated threshold (0.92), which a couple
        # of differing words out of a dozen does NOT clear (real semantic
        # embeddings weight this very differently than raw word-overlap
        # fraction -- see the live-data cosine scores in
        # docs/reports/2026-08-11-auto-adjudication.md, where the true
        # CancelledError rewordings scored ~1.0 despite differing in far
        # more than one token). ~24 shared words / 1 differing word ~= 0.96.
        preamble = (
            "CancelledError Cancelled via cancel scope during asyncio session "
            "teardown while awaiting graceful shutdown of a background task "
            "that had already begun its own cleanup work under the marker "
        )
        texts = [preamble + suffix for suffix in ("alpha", "beta", "gamma", "delta")]
        rows = [
            _record_one(store, run["run_id"], cfg,
                        _diagnosis(error_text=t, context="asyncio session teardown"))
            for t in texts
        ]
        states = [r["state"] for r in rows]
        assert states.count("PENDING") == 1, states
        assert states.count("SUPERSEDED") == 3, states
        survivor = next(r for r in rows if r["state"] == "PENDING")
        for r in rows:
            if r["state"] == "SUPERSEDED":
                assert survivor["proposal_id"] in r["reason"]
                assert r["reason"].startswith("rule:semantic_duplicate:")


# ---------------------------------------------------------------------------
# Test 2 -- distinct failure texts stay separate (Hazard C)
# ---------------------------------------------------------------------------

class TestDistinctFailuresStaySeparate:

    def test_2_permission_denied_vs_connection_timed_out_stay_separate(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg()
        row_a = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="SCP FAILED Permission denied publickey password",
            context="scp to remote host as lse-admin",
        ))
        row_b = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="ssh connect to host port 22 Connection timed out",
            context="ssh_run tool call targeting a remote host",
        ))
        assert row_a["state"] == "PENDING"
        assert row_b["state"] == "PENDING"


# ---------------------------------------------------------------------------
# Test 3 -- a rule-rejected proposal is not re-drafted every run (Hazard B)
# ---------------------------------------------------------------------------

class TestRuleRejectedProposalNotRedrafted:

    def test_3_r2_rejected_proposal_stays_rejected_on_redraft(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg()
        proposal = _diagnosis(
            error_text="403 Client Error: Forbidden for url: https://example.com/some/page",
            context="fetch_url tool call against a public website",
        )
        first = _record_one(store, run["run_id"], cfg, proposal)
        assert first["state"] == "SYSTEM_REJECTED"
        assert first["reason"].startswith("rule:third_party_resource_error:")

        # Next run redrafts the SAME error_text+context (narrow identity
        # match, SPEC-gate-toil-2026-08) with different prose -- exactly
        # what would churn forever if repeat_prior() didn't honor the
        # "rule:" prefix.
        redraft = _diagnosis(
            error_text=proposal["args"]["error_text"],
            context=proposal["args"]["context"],
            interpretation="reworded interpretation", why="reworded why",
        )
        second_attempt = store.start_attempt(run["run_id"], "error-cluster")
        # Deliberately do NOT re-run apply_diagnosis_rules here -- this
        # isolates repeat_prior()'s prefix-honoring behavior (traum_state.py)
        # from the rule logic itself (already proven by test 4/the R2 unit
        # test below).
        [second] = store.record_proposals(run["run_id"], second_attempt["attempt_id"], [redraft])
        assert second["state"] not in ("STAGED", "PENDING"), second
        assert second["state"] == "SUPERSEDED"
        assert first["proposal_id"] in second["reason"]


# ---------------------------------------------------------------------------
# Test 4 -- R2: third-party vs local/internal host
# ---------------------------------------------------------------------------

class TestR2ThirdPartyVsLocal:

    def test_4_third_party_url_rejected_local_url_not(self):
        third_party = _diagnosis(
            error_text="403 Client Error: Forbidden for url: https://www.raspberrypi.com/software/",
        )
        verdict = dgr.rule_r2_third_party_resource_error(third_party)
        assert verdict is not None
        state, reason = verdict
        assert state == "SYSTEM_REJECTED"
        assert reason.startswith("rule:third_party_resource_error:")

        local = _diagnosis(
            error_text="404 Client Error: Not Found for url: http://node3090.home.arpa:8080/health",
        )
        assert dgr.rule_r2_third_party_resource_error(local) is None

        local_ip = _diagnosis(
            error_text="500 Server Error for url: http://192.168.5.41:9377/status",
        )
        assert dgr.rule_r2_third_party_resource_error(local_ip) is None


# ---------------------------------------------------------------------------
# Test 5 -- no rule can ever produce APPLIED or STAGED (Hazard D)
# ---------------------------------------------------------------------------

class TestNoRuleEverApprovesOrApplies:

    def test_5_no_rule_produces_applied_or_staged(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg()
        candidates = [
            _diagnosis(error_text="CancelledError: Cancelled via cancel scope 0xAAAA by Task pending name x"),
            _diagnosis(error_text="403 Client Error: Forbidden for url: https://example.com/x"),
            _diagnosis(
                error_text="ERROR: No pfSense API key. Call vault_unlock() then get_vault_secret",
                resolution="Call vault_unlock() then get_vault_secret to retrieve the pfSense API key",
            ),
            _diagnosis(error_text="a genuinely novel failure never seen before, keep for a human"),
        ]
        allowed = {"STAGED", "PENDING", "SUPERSEDED", "SYSTEM_REJECTED"}
        for c in candidates:
            row = _record_one(store, run["run_id"], cfg, c)
            assert row["state"] in allowed
            assert row["state"] not in ("APPLIED", "APPLYING")


# ---------------------------------------------------------------------------
# Test 6 -- other proposal types completely untouched (Hazard F)
# ---------------------------------------------------------------------------

class TestOtherProposalTypesUntouched:

    def _pre_spec_fingerprint(self, proposal):
        """Independently recomputed, exactly the way
        tests/test_gate_toil.py::test_6 proves Hazard B/F claims -- not
        "the suite is still green"."""
        import hashlib as _hashlib
        import json as _json
        body = {k: v for k, v in proposal.items() if k not in ts._IDENTITY_IGNORED_KEYS}
        canonical = _json.dumps(body, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, default=str)
        return _hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @pytest.mark.parametrize("proposal", [
        _dedup_pair("keep doc"), _demote(), _reverify(), _kb_fact(),
    ], ids=["dedup", "demote", "reverify", "kb-fact"])
    def test_6_fingerprint_byte_identical_to_pre_spec_formula(self, proposal):
        assert ts.proposal_fingerprint(proposal) == self._pre_spec_fingerprint(proposal)

    def test_6b_apply_diagnosis_rules_ignores_non_diagnosis_proposals(self, tmp_path):
        store = _store(tmp_path)
        store.create_run("single-pass", ["dedup"], source="cli")
        cfg = _cfg()
        proposals = [_dedup_pair("x"), _demote(), _reverify(), _kb_fact()]
        before = [dict(p) for p in proposals]
        counts = dr.apply_diagnosis_rules(cfg, store, proposals)
        assert counts["diagnoses_seen"] == 0
        assert proposals == before
        for p in proposals:
            assert "_initial_state" not in p
            assert "_initial_reason" not in p


# ---------------------------------------------------------------------------
# Test 7 -- each rule individually disableable
# ---------------------------------------------------------------------------

class TestRulesIndividuallyDisableable:

    def test_7_disabling_r1_leaves_duplicates_pending(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg(rule_r1_enabled=False)
        a = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="CancelledError: Cancelled via cancel scope 0x1 by Task pending name p",
        ))
        b = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="CancelledError: Cancelled via cancel scope 0x2 by Task pending name q",
        ))
        assert a["state"] == "PENDING"
        assert b["state"] == "PENDING"  # would have been SUPERSEDED with R1 on

    def test_7_disabling_r2_leaves_third_party_url_pending(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg(rule_r2_enabled=False)
        row = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="403 Client Error: Forbidden for url: https://example.com/x",
        ))
        assert row["state"] == "PENDING"

    def test_7_disabling_r3_leaves_redundant_resolution_pending(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg(rule_r3_enabled=False)
        row = _record_one(store, run["run_id"], cfg, _diagnosis(
            error_text="ERROR: No pfSense API key. Call vault_unlock() then get_vault_secret",
            resolution="Call vault_unlock() then get_vault_secret to retrieve the pfSense API key",
        ))
        assert row["state"] == "PENDING"

    def test_7_all_three_disabled_restores_pre_spec_behavior(self, tmp_path):
        store = _store(tmp_path)
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        cfg = _cfg(rule_r1_enabled=False, rule_r2_enabled=False, rule_r3_enabled=False)
        proposals = [
            _diagnosis(error_text="CancelledError: Cancelled via cancel scope 0x9 by Task pending name z"),
            _diagnosis(error_text="403 Client Error: Forbidden for url: https://example.com/y"),
        ]
        for p in proposals:
            row = _record_one(store, run["run_id"], cfg, p)
            assert row["state"] == "PENDING"


# ---------------------------------------------------------------------------
# Test 8 -- the dry-run script writes nothing
# ---------------------------------------------------------------------------

class TestDryRunWritesNothing:

    def _load_script(self):
        spec = importlib.util.spec_from_file_location("dry_run_diagnosis_rules", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_8_dry_run_writes_nothing(self, tmp_path, monkeypatch, capsys):
        db_path = tmp_path / "traum-state.db"
        store = ts.TraumState(str(db_path))
        run = store.create_run("single-pass", ["error-cluster"], source="cli")
        attempt = store.start_attempt(run["run_id"], "error-cluster")
        store.record_proposals(run["run_id"], attempt["attempt_id"], [
            _diagnosis(error_text="X tool call timed out after 200 seconds", context="c1"),
            _diagnosis(error_text="Y tool call timed out after 200 seconds", context="c2"),
        ])
        store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")

        before = db_path.read_bytes()

        module = self._load_script()
        monkeypatch.setattr(module.dream_runner, "embed_text", lambda cfg, text: _fake_embed(text))
        rc = module.main(["--db", str(db_path)])
        assert rc == 0

        after = db_path.read_bytes()
        assert before == after, "dry-run script must never mutate the database"
        out = capsys.readouterr().out
        assert "wrote nothing" in out
