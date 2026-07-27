"""Focused contracts for TRAUM's canonical state and recovery boundary."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import traum_state as ts  # noqa: E402


def _store(tmp_path):
    return ts.TraumState(str(tmp_path / "traum-state.db"))


def _proposal(*, why="evidence", pair_id=None, content="stable fact"):
    value = {
        "type": "kb-fact",
        "call": "index_to_kb",
        "args": {
            "title": content,
            "content": content,
            "quality_score": 0.5,
            "source_tier": "inferred",
        },
        "why": why,
    }
    if pair_id:
        value["pair_id"] = pair_id
    return value


def test_document_token_is_stable_across_transient_embedding_fields():
    generation_doc = {
        "doc_id": "doc-1", "title": "DNS", "content": "Use the resolver.",
        "quality_score": 0.6, "source_tier": "inferred",
    }
    apply_doc = {
        **generation_doc,
        "embedding": [0.1, 0.2], "_index": "lse-kb", "_score": 0.99,
        "search_highlights": ["resolver"],
    }
    assert ts.document_token(generation_doc) == ts.document_token(apply_doc)
    assert ts.document_token(generation_doc) != ts.document_token({
        **apply_doc, "content": "Use a different resolver."
    })


def test_attempt_publication_consumption_and_retry_are_atomic(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="cli")
    failed = store.start_attempt(run["run_id"], "patterns")
    first = store.record_proposals(
        run["run_id"], failed["attempt_id"], [_proposal()]
    )[0]
    assert first["state"] == "STAGED"
    assert store.list_proposals(state="PENDING") == []

    store.finish_attempt(failed["attempt_id"], "FAILED", error="dependency crash")
    assert store.get_proposal(first["proposal_id"])["state"] == "SYSTEM_REJECTED"
    assert store.unconsumed_session_ids("patterns", ["sess-1"]) == {"sess-1"}

    retry = store.start_attempt(
        run["run_id"], "patterns", retry_of=failed["attempt_id"]
    )
    second = store.record_proposals(
        run["run_id"], retry["attempt_id"], [_proposal()]
    )[0]
    assert second["state"] == "STAGED"  # infra failure never suppresses retry
    store.finish_attempt(
        retry["attempt_id"], "SUCCEEDED", consumed_session_ids=["sess-1"]
    )
    assert store.get_proposal(second["proposal_id"])["state"] == "PENDING"
    assert store.unconsumed_session_ids("patterns", ["sess-1"]) == set()


def test_partial_pair_repeat_never_creates_mixed_unreviewable_state(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["dedup"], source="cli")
    first_attempt = store.start_attempt(run["run_id"], "dedup")
    original = [
        _proposal(pair_id="doc-a::doc-b", content="keep doc"),
        _proposal(pair_id="doc-a::doc-b", content="retire doc"),
    ]
    store.record_proposals(run["run_id"], first_attempt["attempt_id"], original)
    store.finish_attempt(first_attempt["attempt_id"], "SUCCEEDED")

    changed_attempt = store.start_attempt(run["run_id"], "dedup")
    changed = [original[0], _proposal(
        pair_id="doc-a::doc-b", content="retire doc with new evidence"
    )]
    changed_rows = store.record_proposals(
        run["run_id"], changed_attempt["attempt_id"], changed
    )
    assert {row["state"] for row in changed_rows} == {"STAGED"}
    store.finish_attempt(changed_attempt["attempt_id"], "SUCCEEDED")
    assert {
        store.get_proposal(row["proposal_id"])["state"] for row in changed_rows
    } == {"PENDING"}

    repeated_attempt = store.start_attempt(run["run_id"], "dedup")
    repeated_rows = store.record_proposals(
        run["run_id"], repeated_attempt["attempt_id"], changed
    )
    assert {row["state"] for row in repeated_rows} == {"SUPERSEDED"}


def test_exact_queue_counts_and_due_filter_are_applied_before_limit(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["insights"], source="cli")
    attempt = store.start_attempt(run["run_id"], "insights")
    rows = store.record_proposals(run["run_id"], attempt["attempt_id"], [
        _proposal(content="future"),
        _proposal(content="due"),
        _proposal(content="pending"),
    ])
    store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")
    store.transition_proposal(rows[0]["proposal_id"], "defer", defer_until="2099-01-01")
    store.transition_proposal(rows[1]["proposal_id"], "defer", defer_until="2020-01-01")

    page = store.proposal_queue(
        "PENDING,DEFERRED,APPLY_FAILED", actionable_only=True,
        due_on="2026-07-27", limit=1,
    )
    assert page["total_before_actionability"] == 3
    assert page["total_matching"] == 2
    assert page["hidden_future_deferred"] == 1
    assert page["truncated"] is True
    summary = store.proposal_queue_summary("2026-07-27")
    assert summary["counts"]["PENDING"] == 1
    assert summary["due_deferred"] == 1
    assert summary["future_deferred"] == 1
    assert summary["human_gate_count"] == 2


def test_unexpired_foreign_run_blocks_new_start_and_retry(tmp_path):
    store = _store(tmp_path)
    retry_run = store.create_run(
        "single-pass", ["patterns"], source="gui", lease_seconds=300
    )
    failed = store.start_attempt(retry_run["run_id"], "patterns")
    store.finish_attempt(failed["attempt_id"], "FAILED")

    foreign = store.create_run(
        "single-pass", ["dedup"], source="gui", lease_seconds=300
    )
    store.start_attempt(foreign["run_id"], "dedup")
    with pytest.raises(ts.ConflictError, match="another canonical TRAUM run"):
        store.start_attempt(
            retry_run["run_id"], "patterns", retry_of=failed["attempt_id"],
            lease_seconds=300,
        )
    with pytest.raises(ts.ConflictError, match="another canonical TRAUM run"):
        store.create_run(
            "single-pass", ["insights"], source="gui", lease_seconds=300
        )


def test_expired_scheduled_run_recovers_without_pid_action(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        "single-pass", ["patterns"], source="scheduled", lease_seconds=60
    )
    attempt = store.start_attempt(run["run_id"], "patterns")
    future = datetime.now(timezone.utc) + timedelta(minutes=2)
    result = store.recover_orphaned_controller_work(
        now=future, grace_seconds=0
    )
    assert result["recovered_run_ids"] == [run["run_id"]]
    assert result["recovered_attempt_ids"] == [attempt["attempt_id"]]
    assert result["unowned_active"] == []
    assert store.get_attempt(attempt["attempt_id"])["state"] == "BLOCKED"
    assert store.get_run(run["run_id"])["state"] == "BLOCKED"


def test_expired_standard_run_synthesizes_missing_pass_attempts_for_retry(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        "standard", ["dedup", "patterns", "digest"],
        source="gui", lease_seconds=60,
    )
    active = store.start_attempt(run["run_id"], "dedup")
    result = store.recover_orphaned_controller_work(
        now=datetime.now(timezone.utc) + timedelta(minutes=2), grace_seconds=0
    )
    attempts = store.list_attempts(run_id=run["run_id"])
    assert {row["pass_name"] for row in attempts} == {"dedup", "patterns", "digest"}
    assert {row["state"] for row in attempts} == {"BLOCKED"}
    synthetic = [row for row in attempts if row["attempt_id"] != active["attempt_id"]]
    assert all(row["summary"]["not_started"] is True for row in synthetic)
    assert len(result["recovered_attempt_ids"]) == 3

    for prior in sorted(attempts, key=lambda row: row["pass_name"]):
        retry = store.start_attempt(
            run["run_id"], prior["pass_name"], retry_of=prior["attempt_id"],
            lease_seconds=60,
        )
        store.finish_attempt(retry["attempt_id"], "SUCCEEDED")
        assert store.get_run(run["run_id"])["state"] != "RUNNING"
    assert store.get_run(run["run_id"])["state"] == "SUCCEEDED"


def test_deadline_less_unowned_run_remains_blocking(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="gui")
    attempt = store.start_attempt(run["run_id"], "patterns")
    result = store.recover_orphaned_controller_work(
        now="2099-01-01T00:00:00Z", grace_seconds=0
    )
    assert result["recovered_run_ids"] == []
    assert result["unowned_active"][0]["run_id"] == run["run_id"]
    assert result["unowned_active"][0]["deadline_known"] is False
    assert store.get_attempt(attempt["attempt_id"])["state"] == "RUNNING"
    with pytest.raises(ts.ConflictError, match="another canonical TRAUM run"):
        store.create_run(
            "single-pass", ["dedup"], source="gui", lease_seconds=60
        )


def test_recovery_fences_late_proposal_and_success_publication(tmp_path):
    store = _store(tmp_path)
    run = store.create_run(
        "single-pass", ["insights"], source="gui", lease_seconds=60
    )
    attempt = store.start_attempt(run["run_id"], "insights")
    staged = store.record_proposals(
        run["run_id"], attempt["attempt_id"], [_proposal()]
    )[0]
    store.recover_orphaned_controller_work(
        now=datetime.now(timezone.utc) + timedelta(minutes=2), grace_seconds=0
    )
    assert store.get_proposal(staged["proposal_id"])["state"] == "SYSTEM_REJECTED"
    with pytest.raises(ts.ConflictError, match="cannot publish proposals"):
        store.record_proposals(run["run_id"], attempt["attempt_id"], [_proposal(content="late")])
    with pytest.raises(ts.ConflictError, match="already BLOCKED"):
        store.finish_attempt(attempt["attempt_id"], "SUCCEEDED")


def test_errors_events_and_proposals_are_force_redacted_at_rest(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="cli")
    attempt = store.start_attempt(run["run_id"], "patterns")
    secret = "supersecretcredentialvalue"
    proposal = _proposal(why=f"api_key={secret}")
    row = store.record_proposals(run["run_id"], attempt["attempt_id"], [proposal])[0]
    assert row["state"] == "SYSTEM_REJECTED"
    store.finish_attempt(
        attempt["attempt_id"], "FAILED",
        error=RuntimeError(f"password={secret}"),
        summary={"controller_error": f"Bearer {secret}"},
    )
    loaded = store.get_attempt(attempt["attempt_id"])
    assert secret not in loaded["error_text"]
    assert secret not in str(loaded["summary"])
    assert secret not in str(store.events())
    assert secret.encode() not in Path(store.db_path).read_bytes()
    assert ts.utc_now().endswith("Z")
