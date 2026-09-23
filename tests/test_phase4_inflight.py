#!/usr/bin/env python3
"""Phase 4 restart-recovery contract tests (goethe_planner step stamps + child requeue).

Coverage:
  - _set_step_in_progress: sets in_progress_at (UTC ISO), removes interrupted_at
  - task_resume: stamps the next pending step when its prompt is issued
  - task_resume: exact interrupted banner for a step carrying interrupted_at,
    and NO re-stamp of that step
  - mark_interrupted_on_startup: old in_progress steps become interrupted
    (in_progress_at preserved); fresh in_progress steps untouched
  - requeue_interrupted_children: running children without a result are
    re-queued (writer_lock cleared, created preserved); children WITH a
    result are never touched; fresh running children untouched

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_phase4_inflight.py -q
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402

OLD = "2026-09-17T20:00:00+00:00"  # unambiguously before any process start


def _fresh():
    return datetime.now(timezone.utc).isoformat()


BANNER_N2 = (
    "Step 2 was interrupted after its prompt was issued. Re-verify current "
    "state before re-executing. READ-ONLY steps: resume directly. "
    "MUTATING steps: verify side effect first via assert_state, then either "
    "plan_step_done with existing evidence or re-execute."
)


@pytest.fixture()
def tools(tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "audit.log")
    t.valves.TASKS_DB = str(tmp_path / "tasks.db")
    return t


def _add_block(t, task_id, steps, status="open"):
    conn = t._tasks_db()
    conn.execute(
        "INSERT INTO task_blocks (task_id, goal, status, plan, done_steps, "
        "findings, unverified, next_prompt, checkpoints, created_at, "
        "updated_at, steps_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, "goal", status, "plan", "done", "f", "u", "np", 1,
         "2026-01-01", "2026-01-01", json.dumps(steps)),
    )
    conn.commit()
    conn.close()


def _steps_of(t, task_id):
    conn = t._tasks_db()
    raw = conn.execute(
        "SELECT steps_json FROM task_blocks WHERE task_id=?", (task_id,)
    ).fetchone()[0]
    conn.close()
    return json.loads(raw)


def _add_child(t, child_id, status, created, result=None, lock=None):
    conn = t._tasks_db()
    conn.execute(
        "INSERT INTO child_runs (child_id, parent_task_id, scope, kind, "
        "status, result, writer_lock, created) VALUES (?,?,?,?,?,?,?,?)",
        (child_id, "t-parent", "s" + child_id, "detached",
         status, result, lock, created),
    )
    conn.commit()
    conn.close()


def _child_of(t, child_id):
    conn = t._tasks_db()
    row = conn.execute(
        "SELECT status, result, writer_lock, created FROM child_runs "
        "WHERE child_id=?", (child_id,)
    ).fetchone()
    conn.close()
    return row


class TestSetStepInProgress:
    def test_sets_in_progress_and_clears_interrupted(self, tools):
        _add_block(tools, "s1", [
            {"n": 1, "what": "a", "status": "pending",
             "interrupted_at": OLD, "in_progress_at": OLD},
        ])
        assert tools._set_step_in_progress("s1", 1) is True
        s = _steps_of(tools, "s1")[0]
        assert "interrupted_at" not in s
        datetime.fromisoformat(s["in_progress_at"])  # parseable UTC ISO
        assert s["status"] == "pending"  # stamp, not a status change

    def test_missing_step_returns_false(self, tools):
        _add_block(tools, "s2", [{"n": 1, "what": "a", "status": "pending"}])
        assert tools._set_step_in_progress("s2", 99) is False
        assert "in_progress_at" not in _steps_of(tools, "s2")[0]


class TestTaskResume:
    def test_pending_step_stamped_before_prompt(self, tools):
        _add_block(tools, "r1", [
            {"n": 1, "what": "a", "status": "done", "evidence": "e" * 30},
            {"n": 2, "what": "b", "status": "pending"},
        ])
        out = tools.task_resume("r1")
        assert "TASK BLOCK r1" in out
        s2 = _steps_of(tools, "r1")[1]
        assert s2.get("in_progress_at")
        assert "interrupted_at" not in s2

    def test_interrupted_banner_exact_and_no_restamp(self, tools):
        in_prog_before = OLD
        _add_block(tools, "r2", [
            {"n": 1, "what": "a", "status": "done", "evidence": "e" * 30},
            {"n": 2, "what": "b", "status": "pending",
             "in_progress_at": in_prog_before, "interrupted_at": OLD},
            {"n": 3, "what": "c", "status": "pending"},
        ])
        out = tools.task_resume("r2")
        assert out.startswith(BANNER_N2)
        s2 = _steps_of(tools, "r2")[1]
        assert s2["in_progress_at"] == in_prog_before  # NOT refreshed
        assert s2["interrupted_at"] == OLD             # preserved


class TestStartupSweep:
    def test_old_in_progress_becomes_interrupted(self, tools):
        _add_block(tools, "w1", [
            {"n": 1, "what": "a", "status": "pending", "in_progress_at": OLD},
        ])
        rc = tools.mark_interrupted_on_startup(_fresh())
        assert rc == 1
        s = _steps_of(tools, "w1")[0]
        assert s.get("interrupted_at")
        assert s["in_progress_at"] == OLD  # preserved for forensics

    def test_fresh_in_progress_untouched(self, tools):
        start = _fresh()  # process start captured BEFORE the stamp
        _add_block(tools, "w2", [
            {"n": 1, "what": "a", "status": "pending",
             "in_progress_at": _fresh()},
        ])
        rc = tools.mark_interrupted_on_startup(start)
        assert rc == 0
        assert "interrupted_at" not in _steps_of(tools, "w2")[0]

    def test_bad_reference_returns_minus_one(self, tools):
        assert tools.mark_interrupted_on_startup("not-a-ts") == -1


class TestChildRequeue:
    def test_running_without_result_requeued(self, tools):
        _add_child(tools, "c1", "running", OLD, result=None, lock="scope1")
        rc = tools.requeue_interrupted_children(_fresh())
        assert rc == 1
        status, result, lock, created = _child_of(tools, "c1")
        assert status == "queued"
        assert result is None
        assert lock is None          # stale lock cleared
        assert created == OLD        # preserved

    def test_child_with_result_untouched(self, tools):
        _add_child(tools, "c2", "running", OLD, result="done-102")
        rc = tools.requeue_interrupted_children(_fresh())
        assert rc == 0
        status, result, lock, created = _child_of(tools, "c2")
        assert status == "running"
        assert result == "done-102"

    def test_fresh_running_untouched(self, tools):
        start = _fresh()  # process start captured BEFORE the stamp
        _add_child(tools, "c3", "running", _fresh(), result=None)
        rc = tools.requeue_interrupted_children(start)
        assert rc == 0
        status, *_ = _child_of(tools, "c3")
        assert status == "running"

    def test_bad_reference_returns_minus_one(self, tools):
        assert tools.requeue_interrupted_children("nope") == -1
