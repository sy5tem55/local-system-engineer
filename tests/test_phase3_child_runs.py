#!/usr/bin/env python3
"""Phase 3 scoped child delegation contract tests (goethe_planner child_runs).

Coverage:
  - _ensure_child_runs_table creates child_runs + indexes (idempotent)
  - delegate_child off-state (CHILD_CAP=0): refuses, inserts nothing
  - argument validation: missing/unknown task_id, empty scope/kind/prompt
  - child_status table contains child_id/scope/status
  - per-parent budget caps: concurrent cap and total cap block dispatch

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_phase3_child_runs.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402


@pytest.fixture()
def tools(tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "audit.log")
    t.valves.TASKS_DB = str(tmp_path / "tasks.db")
    return t


def _add_parent(t, task_id="t-parent-1"):
    conn = t._tasks_db()
    conn.execute(
        "INSERT INTO task_blocks (task_id, goal, status, created_at, updated_at) "
        "VALUES (?, 'test goal', 'open', '2026-01-01', '2026-01-01')",
        (task_id,),
    )
    conn.commit()
    conn.close()


def _seed_children(t, parent, n, status, kind="detached", prefix="c"):
    conn = t._tasks_db()
    for i in range(n):
        conn.execute(
            "INSERT INTO child_runs (child_id, parent_task_id, scope, kind, "
            "status, result, created) VALUES (?,?,?,?,?,?, '2026-01-01')",
            (f"{prefix}{i}", parent, f"s{prefix}{i}", kind, status, "p"),
        )
    conn.commit()
    conn.close()


class TestChildRunsSchema:
    def test_table_and_indexes_created(self, tools):
        conn = tools._tasks_db()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        conn.close()
        assert "child_runs" in tables
        assert "idx_child_runs_parent_status" in indexes
        assert "idx_child_runs_scope" in indexes

    def test_idempotent(self, tools):
        c1 = tools._tasks_db()
        c1.close()
        c2 = tools._tasks_db()  # second open must not raise
        c2.close()


class TestDelegateChildOffState:
    def test_child_cap_zero_refuses_and_inserts_nothing(self, tools):
        _add_parent(tools)
        tools.valves.CHILD_CAP = 0
        r = tools.delegate_child("t-parent-1", "scope-a", "do the thing")
        assert r.startswith("REFUSED")
        assert "OFF" in r
        conn = tools._tasks_db()
        n = conn.execute("SELECT COUNT(*) FROM child_runs").fetchone()[0]
        conn.close()
        assert n == 0


class TestArgumentValidation:
    def test_missing_task_id(self, tools):
        assert tools.delegate_child("", "s", "p").startswith("ERROR")

    def test_unknown_parent(self, tools):
        r = tools.delegate_child("nope", "s", "p")
        assert r.startswith("ERROR")
        assert "not found" in r

    def test_empty_scope(self, tools):
        _add_parent(tools)
        assert tools.delegate_child("t-parent-1", "", "p").startswith("ERROR")

    def test_bad_kind(self, tools):
        _add_parent(tools)
        r = tools.delegate_child("t-parent-1", "s", "p", kind="weird")
        assert "must be" in r

    def test_empty_prompt(self, tools):
        _add_parent(tools)
        assert tools.delegate_child("t-parent-1", "s", "   ").startswith("ERROR")


class TestChildStatus:
    def test_table_shows_child(self, tools, monkeypatch):
        _add_parent(tools)
        def fake_exec(cid):
            # mirror the real worker: replace prompt with result, mark done
            conn = tools._tasks_db()
            conn.execute(
                "UPDATE child_runs SET status='done', result=?, finished='2026-01-01' "
                "WHERE child_id=?",
                ("child output for scope-a", cid),
            )
            conn.commit()
            conn.close()
            return f"child {cid} done (parent=t-parent-1, scope=scope-a, node=local)"

        monkeypatch.setattr(tools, "_exec_child", fake_exec)
        r = tools.delegate_child("t-parent-1", "scope-a", "do the thing")
        assert r.startswith("child")
        cid = r.split()[1]
        t = tools.child_status("t-parent-1")
        assert cid in t
        assert "scope-a" in t
        assert "done" in t

    def test_no_children(self, tools):
        _add_parent(tools)
        assert tools.child_status("t-parent-1") == "no child runs for t-parent-1"


class TestBudgetCaps:
    def test_concurrent_cap_blocks(self, tools):
        _add_parent(tools)
        _seed_children(tools, "t-parent-1", 4, "running")  # CHILD_CAP default = 4
        r = tools.delegate_child("t-parent-1", "scope-new", "do the thing")
        assert r.startswith("REFUSED")
        assert "concurrent" in r

    def test_total_cap_blocks(self, tools):
        _add_parent(tools)
        _seed_children(tools, "t-parent-1", 8, "done", prefix="d")  # TOTAL default = 8
        r = tools.delegate_child("t-parent-1", "scope-new", "do the thing")
        assert r.startswith("REFUSED")
        assert "total" in r

    def test_within_caps_dispatches(self, tools, monkeypatch):
        _add_parent(tools)
        calls = []

        def fake_exec(cid):
            calls.append(cid)
            return f"child {cid} done (local)"

        monkeypatch.setattr(tools, "_exec_child", fake_exec)
        r = tools.delegate_child("t-parent-1", "scope-a", "do the thing")
        assert calls, "dispatch must call _exec_child"
        assert "done" in r
