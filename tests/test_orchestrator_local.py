"""Local-orchestrator contract tests (ADR-ORCH-001, Phase 3).

Covers the local backend end-to-end without a Ray cluster: mock worker
registration, weighted scheduling, dispatch/collect lifecycle, and the
SQLite event journal (state transitions, failure paths, best-effort
guarantees). No live network, no GPU, no Ray init.

Run: /home/sy5/owui/bin/python3 -m pytest tests/test_orchestrator_local.py -q
"""

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from goethe_orchestrator.contracts import TaskEnvelope, WorkerRegistration  # noqa: E402
from goethe_orchestrator.event_log import EventLog  # noqa: E402
from goethe_orchestrator.orchestrator import (  # noqa: E402
    LocalOrchestrator,
    NoEligibleWorkerError,
    OrchestratorError,
)


def _boom(**_):
    raise RuntimeError("handler blew up")


def _make_orch(tmp_path, **kw):
    log = EventLog(str(tmp_path / "events.db"))
    orch = LocalOrchestrator(backend="local", event_log=log, **kw)
    orch.register_handler("echo", lambda **kw: "echo:" + str(kw.get("msg", "")))
    orch.register_handler("boom", _boom)
    return orch, log


def _worker(oid, vram=24, ttl=30):
    return WorkerRegistration(
        worker_id=oid, capabilities={"vram_gb": vram}, heartbeat_ttl=ttl
    )


# ── registration ───────────────────────────────────────────────────────────

def test_register_worker_becomes_active(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    assert [w.worker_id for w in orch.active_workers()] == ["w1"]


def test_duplicate_registration_replaces(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1", vram=24))
    orch.register_worker(_worker("w1", vram=8))
    actives = orch.active_workers()
    assert len(actives) == 1
    assert actives[0].capabilities["vram_gb"] == 8


# ── dispatch / collect lifecycle ───────────────────────────────────────────

def test_dispatch_echo_completes(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "echo", "args": {"msg": "hi"}})
    res = orch.dispatch(env)
    assert res.status == "DISPATCHED" and res.worker_id == "w1"
    res = orch.collect(res, timeout=5)
    assert res.status == "COMPLETED" and res.result == "echo:hi"
    assert env.status == "COMPLETED"


def test_dispatch_without_eligible_worker_stays_pending(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1", vram=4))
    env = TaskEnvelope(
        payload={"handler": "echo", "args": {"msg": "x"}, "requires": {"vram_gb": 12}}
    )
    with pytest.raises(NoEligibleWorkerError):
        orch.dispatch(env)
    assert env.status == "PENDING"  # retryable


def test_unknown_handler_fails_envelope(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "nope", "args": {}})
    with pytest.raises(OrchestratorError):
        orch.dispatch(env)
    assert env.status == "FAILED"


def test_handler_exception_marks_failed(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "boom", "args": {}})
    res = orch.dispatch(env)
    res = orch.collect(res, timeout=5)
    assert res.status == "FAILED"
    assert "handler blew up" in res.error


def test_completed_envelope_cannot_redispatch(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "echo", "args": {"msg": "a"}})
    orch.collect(orch.dispatch(env), timeout=5)
    with pytest.raises(OrchestratorError):
        orch.dispatch(env)


# ── scheduling ─────────────────────────────────────────────────────────────

def test_scheduler_excludes_worker_below_hard_gate(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("small", vram=4))
    orch.register_worker(_worker("big", vram=24))
    env = TaskEnvelope(
        payload={"handler": "echo", "args": {}, "requires": {"vram_gb": 12}}
    )
    res = orch.dispatch(env)
    assert res.worker_id == "big"


def test_scheduler_prefers_fresher_worker(tmp_path):
    orch, _ = _make_orch(tmp_path)
    a = _worker("stale", vram=24)
    b = _worker("fresh", vram=24)
    orch.register_worker(a)
    orch.register_worker(b)
    time.sleep(0.02)
    b.heartbeat()  # b is now strictly fresher than a
    env = TaskEnvelope(payload={"handler": "echo", "args": {}})
    res = orch.dispatch(env)
    assert res.worker_id == "fresh"


def test_heartbeat_expiry_via_tick(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1", ttl=1))
    assert orch.active_workers()
    time.sleep(1.1)
    flipped = orch.tick()
    assert flipped == ["w1"]
    assert orch.active_workers() == []


def test_heartbeat_refreshes_expiry(tmp_path):
    orch, _ = _make_orch(tmp_path)
    orch.register_worker(_worker("w1", ttl=1))
    time.sleep(1.1)
    assert orch.heartbeat("w1") is True
    assert orch.tick() == []
    assert [w.worker_id for w in orch.active_workers()] == ["w1"]


def test_heartbeat_unknown_worker_returns_false(tmp_path):
    orch, _ = _make_orch(tmp_path)
    assert orch.heartbeat("ghost") is False


# ── event journal ──────────────────────────────────────────────────────────

def test_event_log_records_success_transitions(tmp_path):
    orch, log = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "echo", "args": {"msg": "j"}})
    orch.collect(orch.dispatch(env), timeout=5)
    rows = log.events_for(env.id)
    seq = [(r["from_status"], r["to_status"]) for r in rows]
    assert seq == [("PENDING", "DISPATCHED"), ("DISPATCHED", "COMPLETED")]
    assert all(r["worker_id"] == "w1" for r in rows)
    assert all(r["backend"] == "local" for r in rows)


def test_event_log_records_failure_with_detail(tmp_path):
    orch, log = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "boom", "args": {}})
    res = orch.dispatch(env)
    orch.collect(res, timeout=5)
    rows = log.events_for(env.id)
    assert rows[-1]["to_status"] == "FAILED"
    assert "handler blew up" in rows[-1]["detail"]


def test_event_log_records_unknown_handler(tmp_path):
    orch, log = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "nope", "args": {}})
    with pytest.raises(OrchestratorError):
        orch.dispatch(env)
    rows = log.events_for(env.id)
    assert rows[-1]["to_status"] == "FAILED"
    assert "no handler" in rows[-1]["detail"]


def test_event_log_tail_and_ordering(tmp_path):
    orch, log = _make_orch(tmp_path)
    orch.register_worker(_worker("w1"))
    ids = []
    for i in range(3):
        env = TaskEnvelope(payload={"handler": "echo", "args": {"msg": str(i)}})
        orch.collect(orch.dispatch(env), timeout=5)
        ids.append(env.id)
    tail = log.tail(50)
    assert len(tail) == 6  # 2 transitions x 3 envelopes
    assert [r["envelope_id"] for r in tail[:2]] == [ids[0], ids[0]]
    assert tail[0]["id"] < tail[-1]["id"]  # oldest first


def test_event_log_record_never_raises(tmp_path):
    log = EventLog(str(tmp_path / "e.db"))
    log.close()  # closed connection — record must swallow the error
    log.record("abc", "COMPLETED")  # no raise
    log2 = EventLog(str(tmp_path / "nested" / "deep" / "e.db"))
    log2.record("abc", "DISPATCHED")  # missing parent dir — no raise


def test_orchestrator_works_without_event_log(tmp_path):
    orch = LocalOrchestrator(backend="local")  # event_log=None → no journal
    orch.register_handler("echo", lambda **kw: "echo:" + str(kw.get("msg", "")))
    orch.register_worker(_worker("w1"))
    env = TaskEnvelope(payload={"handler": "echo", "args": {"msg": "plain"}})
    res = orch.collect(orch.dispatch(env), timeout=5)
    assert res.status == "COMPLETED"


def test_event_log_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GOETHE_ORCH_EVENT_LOG", str(tmp_path / "env.db"))
    log = EventLog()
    log.record("x", "PENDING")
    assert (tmp_path / "env.db").exists()
    assert log.events_for("x")[0]["to_status"] == "PENDING"
