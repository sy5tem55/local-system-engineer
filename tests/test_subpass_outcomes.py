"""
Unit tests for SPEC-subpass-outcomes-2026-08 (Roadmap R4, reframed).

The bug: a pass with independent sub-passes over the same pull (reverify +
demote in stale-contradiction; one LLM call per domain in insights) had no
way to report that PART of it succeeded. When one sub-pass hit a dependency
failure, the pass's own already-computed, already-good proposals from the
OTHER sub-pass were discarded by an unguarded narrative text-scrape in
dream_runner.py's `_raise_if_dependency_blocked`, and the whole attempt was
recorded BLOCKED.

The fix is NOT at the NULL/BLOCKED boundary (the spec's Sec2 explains why that
framing was wrong -- see docs/SPEC-subpass-outcomes-2026-08.md). It is one
level down: each pass now returns a 4th value, `sub_passes`, naming each
sub-pass's own state/dependency, and `_raise_if_dependency_blocked` only
raises on a narrative-text match when the pass's own raw_proposals return
value is empty -- i.e. when there is genuinely nothing to keep.

Covers the spec's numbered tests (Sec7):
  1. reverify succeeds + demote blocked -> attempt SUCCEEDED, reverify's
     proposals kept.                                          [load-bearing]
  2. that attempt's summary still names demote as blocked, with its
     dependency (Hazard B: kept proposals must not launder a failure).
                                                                [load-bearing]
  3. both sub-passes find nothing -> NULL, not SUCCEEDED.
  4. neither sub-pass can run (KB unreachable) -> BLOCKED -- this path lives
     entirely in dream_runner.py's main(), outside any pass function, and
     is untouched by this change; asserted here as a non-regression check.
  5. ATTEMPT_STATES is unchanged (Hazard A).
  6. run summary reports passes_good/passes_total; a 5-of-6 run is
     distinguishable from a 1-of-6 run.

Test 7 (Console renders the ratio; node --check on extracted JS) lives in
tests/test_ui_router.py, next to the dashboard's other source-level tests.

Run: python3 -m pytest tests/test_subpass_outcomes.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402
import traum_state as ts  # noqa: E402


def _cfg(**overrides):
    """Same minimal DreamConfig fixture as test_dream_guards.py."""
    base = dict(
        episode_dir="/tmp/episodes-does-not-exist",
        dream_dir="/tmp/dreams-does-not-exist",
        manifest_db="/tmp/episodes-does-not-exist/manifest.db",
        es_url="http://fake-es.invalid:9200",
        tasks_db="/tmp/tasks.db",
        agent_log="/tmp/agent_commands.log",
        dream_llm_url="",
        node3090_llm_url="http://node3090.home.arpa:8080",
        node3090_ollama_url="http://node3090.home.arpa:11434",
        node3090_fallback_model="qwen3:4b",
        ollama_url="http://127.0.0.1:11434",
        embed_model="nomic-embed-text",
        dedup_floor=0.75,
        dedup_threshold=0.92,
        error_cluster_threshold=0.80,
        runner_session_prefix="",
        sessions_limit=50,
        since=None,
        pass_name="stale-contradiction",
        dry_run=True,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


def _reverify_doc():
    """A doc with volatility+verified_against+updated_at old enough to blow
    its CHRONOS TTL ('fast' = 7 days) -- a real, deterministic reverify
    candidate, per find_reverify_candidates."""
    return {
        "_id": "reverify-doc-1",
        "volatility": "fast",
        "verified_against": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "stale": False,
        "quality_score": 0.3,
        "title": "old fast-moving fact",
        "content": "irrelevant",
    }


DEMOTE_DOC_ID = "deadbeef00112233"  # extract_surfaced_doc_ids' regex is hex-only


def _demote_doc():
    """A doc surfaced this session with enough quality to be a demote
    candidate (find_contradiction_candidates), separate from the reverify
    doc so the two sub-passes are genuinely independent in the fixture.
    _id MUST be hex -- _DOC_ID_RE (dream_runner.py) only matches
    doc_id=[0-9a-fA-F]{8,32}, same as search_kb's own real ES doc ids."""
    return {
        "_id": DEMOTE_DOC_ID,
        "quality_score": 0.9,
        "title": "surfaced doc",
        "content": "the service listens on port 8080",
    }


def _session_surfacing(doc_id):
    return [
        {"tool": "search_kb", "exit_class": "ok",
         "result_truncated": f"1 hit: doc_id={doc_id} score=0.9"},
        {"tool": "run_command", "exit_class": "ok",
         "result_truncated": "port 9090 LISTEN"},
    ]


class TestSubPassOutcomes1And2StaleContradiction:
    """Spec tests 1 and 2 -- both load-bearing."""

    def test_1_reverify_succeeds_demote_blocked_attempt_is_succeeded(self, monkeypatch):
        kb_docs = [_reverify_doc(), _demote_doc()]
        sessions = [{"session_id": "s1"}]
        episodes_by_session = {"s1": _session_surfacing(DEMOTE_DOC_ID)}

        monkeypatch.setattr(
            dr, "request_dream_envelope",
            lambda *a, **kw: (None, "DREAMER UNAVAILABLE -- (no reply)"),
        )

        cfg = _cfg(pass_name="stale-contradiction")
        proposals, narrative, null_record, sub_passes = dr.run_pass_stale_contradiction(
            cfg, sessions, episodes_by_session, kb_docs, []
        )

        # reverify's proposal survives even though demote hit the LLM dependency.
        assert len(proposals) == 1
        assert proposals[0]["type"] == "reverify"
        assert proposals[0]["args"]["doc_id"] == "reverify-doc-1"

        # non-null -- the call site's `outcome = "NULL" if null_record is not
        # None else "SUCCEEDED"` (dream_runner.py, unchanged) reads this as
        # SUCCEEDED.
        assert null_record is None

        # and the narrative-scrape that used to discard everything must not
        # fire now that raw_proposals is non-empty -- this IS the call site's
        # other half of "attempt becomes SUCCEEDED".
        dr._raise_if_dependency_blocked(cfg, narrative, null_record, proposals)  # must not raise

    def test_2_summary_still_names_demote_blocked_with_dependency(self, monkeypatch):
        """Hazard B: keeping reverify's proposals must not launder demote's
        failure into silence. sub_passes is what main() folds into the
        attempt's `summary` dict (dream_runner.py, finish_attempt call) --
        replicated here the same way main() builds it."""
        kb_docs = [_reverify_doc(), _demote_doc()]
        sessions = [{"session_id": "s1"}]
        episodes_by_session = {"s1": _session_surfacing(DEMOTE_DOC_ID)}

        monkeypatch.setattr(
            dr, "request_dream_envelope",
            lambda *a, **kw: (None, "DREAMER UNAVAILABLE -- (no reply)"),
        )

        cfg = _cfg(pass_name="stale-contradiction")
        proposals, narrative, null_record, sub_passes = dr.run_pass_stale_contradiction(
            cfg, sessions, episodes_by_session, kb_docs, []
        )

        assert sub_passes["reverify"] == {"state": "SUCCEEDED", "proposals": 1}
        assert sub_passes["demote"] == {
            "state": "BLOCKED", "proposals": 0, "dependency": "dream-llm",
        }
        # the failure is also in the human-readable narrative (report.md) --
        # unchanged existing behaviour, still true after this change.
        assert "DREAMER UNAVAILABLE" in narrative

        # same summary construction dream_runner.py's main() uses at the
        # finish_attempt() call site (SPEC-subpass-outcomes-2026-08 Sec5.1).
        summary = {
            "sessions_selected": len(sessions),
            "sessions_consumed": len(sessions),
            "proposals_pending": len(proposals),
            "null_reason": (null_record or {}).get("reason"),
            "budget_truncated": False,
            **({"sub_passes": sub_passes} if sub_passes else {}),
        }
        assert summary["sub_passes"]["demote"]["dependency"] == "dream-llm"
        assert summary["sub_passes"]["demote"]["state"] == "BLOCKED"


class TestSubPassOutcome3BothNull:
    def test_3_both_subpasses_find_nothing_is_null_not_succeeded(self):
        # no TTL-expired doc, no session evidence -- both sub-passes run
        # clean and find nothing.
        kb_docs = [{
            "_id": "fine-doc", "quality_score": 0.9, "title": "t", "content": "c",
            # no volatility -- find_reverify_candidates skips it (not scored)
        }]
        sessions = [{"session_id": "s1"}]
        episodes_by_session = {"s1": []}  # nothing surfaced, no contradiction candidates

        cfg = _cfg(pass_name="stale-contradiction")
        proposals, narrative, null_record, sub_passes = dr.run_pass_stale_contradiction(
            cfg, sessions, episodes_by_session, kb_docs, []
        )

        assert proposals == []
        assert null_record is not None
        assert null_record["reason"] == "no_reverify_and_no_contradictions"
        assert sub_passes["reverify"]["state"] == "NULL"
        assert sub_passes["demote"]["state"] == "NULL"

        # and the call site would correctly read this as NULL, not SUCCEEDED --
        # _raise_if_dependency_blocked must not raise (there's no dependency
        # marker in this narrative), so outcome falls through to
        # "NULL if null_record is not None else SUCCEEDED" = NULL.
        dr._raise_if_dependency_blocked(cfg, narrative, null_record, proposals)  # must not raise


class TestSubPassOutcome4KbUnreachable:
    """Spec test 4. This is NOT inside any pass function -- kb_docs for
    stale-contradiction is fetched by dream_runner.py's main() BEFORE
    PASS_FUNCS is called (search_index() wrapped in a try/except that
    raises DependencyBlocked("elasticsearch", ...) on any exception). That
    path is untouched by this change; this test pins that it is still
    there and still literal, since nothing exercises it end-to-end without
    a live/faked Elasticsearch and the full main() harness."""

    def test_4_es_fetch_failure_path_is_unchanged(self):
        src = open(dr.__file__, encoding="utf-8").read()
        assert 'raise DependencyBlocked("elasticsearch", str(exc)) from exc' in src


class TestSubPassOutcome5AttemptStatesUnchanged:
    def test_5_attempt_states_is_the_original_seven(self):
        assert ts.ATTEMPT_STATES == {
            "QUEUED", "RUNNING", "SUCCEEDED", "NULL", "BLOCKED", "FAILED", "CANCELLED",
        }
        assert "PARTIAL" not in ts.ATTEMPT_STATES


class TestSubPassOutcome6RunSummaryRatio:
    def _store(self, tmp_path):
        return ts.TraumState(str(tmp_path / "traum-state.db"))

    def test_6_five_of_six_distinguishable_from_one_of_six(self, tmp_path):
        passes = ["dedup", "stale-contradiction", "error-cluster",
                  "patterns", "insights", "dream-digest"]

        store = self._store(tmp_path)
        good_run = store.create_run("full", passes, source="cli")
        for i, p in enumerate(passes):
            attempt = store.start_attempt(good_run["run_id"], p)
            # 5 good (SUCCEEDED/NULL), 1 FAILED
            state = "FAILED" if i == 0 else "SUCCEEDED"
            store.finish_attempt(attempt["attempt_id"], state)
        good_run = store.get_run(good_run["run_id"])

        bad_run = store.create_run("full", passes, source="cli")
        for i, p in enumerate(passes):
            attempt = store.start_attempt(bad_run["run_id"], p)
            # 1 good, 5 FAILED
            state = "SUCCEEDED" if i == 0 else "FAILED"
            store.finish_attempt(attempt["attempt_id"], state)
        bad_run = store.get_run(bad_run["run_id"])

        assert good_run["state"] == "DEGRADED"
        assert bad_run["state"] == "DEGRADED"
        # same bare word today, distinguishable ratio after this change
        assert good_run["summary"]["passes_good"] == 5
        assert good_run["summary"]["passes_total"] == 6
        assert bad_run["summary"]["passes_good"] == 1
        assert bad_run["summary"]["passes_total"] == 6
        assert good_run["summary"] != bad_run["summary"]

    def test_succeeded_run_also_carries_the_ratio(self, tmp_path):
        store = self._store(tmp_path)
        run = store.create_run("single-pass", ["patterns"], source="cli")
        attempt = store.start_attempt(run["run_id"], "patterns")
        store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")
        run = store.get_run(run["run_id"])
        assert run["state"] == "SUCCEEDED"
        assert run["summary"]["passes_good"] == 1
        assert run["summary"]["passes_total"] == 1

    def test_finalize_cycle_preserves_the_ratio_instead_of_clobbering_it(self, tmp_path):
        """SPEC-subpass-outcomes-2026-08 Sec5.3: finalize_cycle used to
        overwrite summary_json wholesale with just digest info, which would
        have discarded passes_good/passes_total the moment _aggregate_run
        had just set them."""
        store = self._store(tmp_path)
        run = store.create_run("full", ["dedup", "patterns"], source="cli")
        for p in ("dedup", "patterns"):
            attempt = store.start_attempt(run["run_id"], p)
            store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")
        updated = store.finalize_cycle(run["run_id"], digest_exit_code=0)
        assert updated["summary"]["passes_good"] == 2
        assert updated["summary"]["passes_total"] == 2
        assert updated["summary"]["digest_exit_code"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
