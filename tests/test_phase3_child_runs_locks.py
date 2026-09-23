#!/usr/bin/env python3
"""Phase 3 writer-lock contention + required-child gate tests.

Coverage:
  - exact-scope writer lock: active required child on scope S
      * second required delegate_child on S -> REFUSED, no active row left
      * second detached delegate_child on S  -> queued row, writer_lock NULL
  - _required_children_gate: pending required child blocks; done child
    returns its result verbatim with child_id marker
  - plan_step_done: refused while a required child is pending; after the
    child is done the step strikes and the next packaged prompt carries the
    child result verbatim

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_phase3_child_runs_locks.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402

PARENT = "t-parent-1"


@pytest.fixture()
def tools(tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "audit.log")
    t.valves.TASKS_DB = str(tmp_path / "tasks.db")
    return t


def _add_parent(t, steps=None):
    conn = t._tasks_db()
    conn.execute(
        "INSERT INTO task_blocks (task_id, goal, status, steps_json, "
        "created_at, updated_at) VALUES (?, 'test goal', 'open', ?, "
        "'2026-01-01', '2026-01-01')",
        (PARENT, json.dumps(steps) if steps else None),
    )
    conn.commit()
    conn.close()


def _seed_child(t, child_id, scope, kind, status, writer_lock=None,
                depends_on=None, result="p"):
    conn = t._tasks_db()
    conn.execute(
        "INSERT INTO child_runs (child_id, parent_task_id, scope, node, kind, "
        "status, result, depends_on, writer_lock, created) "
        "VALUES (?,?,?,?,?,?,?,?,?, '2026-01-01')",
        (child_id, PARENT, scope, "", kind, status, result,
         depends_on, writer_lock),
    )
    conn.commit()
    conn.close()


def _active_on_scope(t, scope):
    conn = t._tasks_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM child_runs WHERE scope=? AND "
        "status IN ('queued','running')", (scope,),
    ).fetchone()[0]
    conn.close()
    return n


class TestWriterLockContention:
    def test_required_conflict_refused_no_active_row(self, tools):
        _add_parent(tools)
        _seed_child(tools, "req1", "scope-S", "required", "running",
                    writer_lock="scope-S")
        r = tools.delegate_child(PARENT, "scope-S", "second required",
                                 kind="required")
        assert r.startswith("REFUSED")
        assert _active_on_scope(tools, "scope-S") == 1  # only req1 remains
        conn = tools._tasks_db()
        rows = conn.execute(
            "SELECT status FROM child_runs WHERE scope='scope-S' "
            "AND child_id != 'req1'"
        ).fetchall()
        conn.close()
        # the refused required child may remain as a cancelled forensic row,
        # never as an active one
        assert all(r2[0] not in ("running", "queued") for r2 in rows)

    def test_detached_conflict_queues(self, tools):
        _add_parent(tools)
        _seed_child(tools, "req1", "scope-S", "required", "running",
                    writer_lock="scope-S")
        r = tools.delegate_child(PARENT, "scope-S", "second detached",
                                 kind="detached")
        assert "queued" in r
        conn = tools._tasks_db()
        row = conn.execute(
            "SELECT status, writer_lock FROM child_runs "
            "WHERE scope='scope-S' AND kind='detached'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "queued"
        assert row[1] is None  # lock held until promoted

    def test_promote_after_lock_frees(self, tools, monkeypatch):
        # no network in unit tests: stub the local completion path
        monkeypatch.setattr(
            tools, "_local_child_completion",
            lambda prompt: f"local child output for: {prompt[:40]}",
        )
        _add_parent(tools)
        _seed_child(tools, "req1", "scope-S", "required", "running",
                    writer_lock="scope-S")
        tools.delegate_child(PARENT, "scope-S", "second detached",
                             kind="detached")
        # lock frees: req1 finishes
        conn = tools._tasks_db()
        conn.execute(
            "UPDATE child_runs SET status='done', writer_lock=NULL, "
            "finished='2026-01-01' WHERE child_id='req1'")
        conn.commit()
        conn.close()
        promoted = tools._promote_queued_children(PARENT)
        assert len(promoted) == 1
        conn = tools._tasks_db()
        st = conn.execute(
            "SELECT status FROM child_runs WHERE child_id=?",
            (promoted[0],),
        ).fetchone()[0]
        conn.close()
        assert st in ("done", "failed")  # executed, not still queued


class TestRequiredChildrenGate:
    def test_pending_blocks(self, tools):
        _add_parent(tools)
        _seed_child(tools, "req1", "scope-S", "required", "running",
                    depends_on="3")
        blocked, text = tools._required_children_gate(PARENT, 3)
        assert blocked is True
        assert "req1" in text
        assert "running" in text

    def test_done_returns_verbatim_results(self, tools):
        _add_parent(tools)
        _seed_child(tools, "req1", "scope-S", "required", "done",
                    depends_on="3",
                    result="MEASURED: 42.0 GB free on /dev/nvme0n1")
        blocked, text = tools._required_children_gate(PARENT, 3)
        assert blocked is False
        assert "MEASURED: 42.0 GB free on /dev/nvme0n1" in text
        assert "req1" in text

    def test_no_required_children_passes(self, tools):
        _add_parent(tools)
        blocked, text = tools._required_children_gate(PARENT, 3)
        assert blocked is False
        assert text == ""


STEPS = [
    {"n": 1, "what": "prep", "status": "done", "evidence": "ok ok ok ok ok"},
    {"n": 2, "what": "probe", "status": "done", "evidence": "ok ok ok ok ok"},
    {"n": 3, "what": "measure", "status": "pending",
     "packaged_prompt": "STEP 3 PROMPT: measure disk free space"},
    {"n": 4, "what": "finalize", "status": "pending",
     "packaged_prompt": "STEP 4 PROMPT: finalize the report"},
]


class TestPlanStepDoneGate:
    def test_refused_while_child_pending(self, tools):
        _add_parent(tools, STEPS)
        _seed_child(tools, "req1", "scope-m", "required", "queued",
                    depends_on="3")
        r = tools.plan_step_done(PARENT, 3,
                                 "verify output line one 1234567890")
        assert "REFUSED" in r
        conn = tools._tasks_db()
        st = conn.execute(
            "SELECT steps_json FROM task_blocks WHERE task_id=?", (PARENT,)
        ).fetchone()[0]
        conn.close()
        steps = json.loads(st)
        assert next(s for s in steps if s["n"] == 3)["status"] == "pending"

    def test_strike_and_verbatim_rejoin(self, tools, monkeypatch):
        _add_parent(tools, STEPS)
        _seed_child(tools, "req1", "scope-m", "required", "done",
                    depends_on="3",
                    result="MEASURED: 42.0 GB free on /dev/nvme0n1")
        r = tools.plan_step_done(PARENT, 3,
                                 "verify output line one 1234567890")
        assert "struck" in r
        assert "MEASURED: 42.0 GB free on /dev/nvme0n1" in r  # verbatim rejoin
        assert "child req1" in r
        conn = tools._tasks_db()
        st = conn.execute(
            "SELECT steps_json, next_prompt FROM task_blocks "
            "WHERE task_id=?", (PARENT,),
        ).fetchone()
        conn.close()
        steps = json.loads(st[0])
        assert next(s for s in steps if s["n"] == 3)["status"] == "done"
        assert "MEASURED: 42.0 GB free on /dev/nvme0n1" in st[1]
