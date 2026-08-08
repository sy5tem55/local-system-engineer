"""Contract tests for tools/goethe_ui.py (Goethe Console, v0.1.0).

Stdlib-only ASGI harness — no starlette/httpx test dependency. Covers the
fail-safe contract (a UI failure must never affect the MCP surface), the
token gate (same normalisation as goethe_mcp._TokenGuard), pass-through of
non-UI paths, and each panel builder against real tmp fixtures (sqlite
ledger, dream day-dirs, episode JSONL). ES-backed panels are exercised with
ES pointed at a dead port — they must answer JSON with an "error" field,
never raise.
"""

import asyncio
import importlib.util
import json
import os
import re
import sqlite3
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_UI_PATH = os.path.join(_HERE, "..", "tools", "goethe_ui.py")

spec = importlib.util.spec_from_file_location("goethe_ui_under_test", _UI_PATH)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


# --------------------------------------------------------------------------
# Minimal ASGI harness
# --------------------------------------------------------------------------

class _Inner:
    """Sentinel inner app — records whether the request fell through."""

    def __init__(self):
        self.called_with = []

    async def __call__(self, scope, receive, send):
        self.called_with.append(scope.get("path"))
        await send({"type": "http.response.start", "status": 299,
                    "headers": []})
        await send({"type": "http.response.body", "body": b"inner"})


def _run(app, path, method="GET", auth=None, payload=None, query="",
         json_body=None):
    # ``payload`` (TRAUM control tests) and ``json_body`` (permission/ledger
    # tests) are the same request body under two historical names.
    scope = {"type": "http", "path": path, "method": method,
             "query_string": query.encode(),
             "headers": ([(b"authorization", auth.encode())] if auth else [])}
    messages = []
    body_value = payload if payload is not None else json_body
    raw_body = (json.dumps(body_value).encode("utf-8")
                if body_value is not None else b"")

    async def receive():
        return {"type": "http.request", "body": raw_body,
                "more_body": False}

    async def send(msg):
        messages.append(msg)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages
                  if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages
                    if m["type"] == "http.response.body")
    return status, body


def _json_of(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


# --------------------------------------------------------------------------
# Routing + token gate
# --------------------------------------------------------------------------

def test_non_ui_path_passes_through_untouched():
    inner = _Inner()
    app = ui.UIRouter(inner, token="sekrit")
    status, body = _run(app, "/mcp", method="POST")
    assert status == 299 and body == b"inner"
    assert inner.called_with == ["/mcp"]


def test_ui_page_served_without_token(tmp_path):
    html = tmp_path / "dash.html"
    html.write_text("<html>console</html>", encoding="utf-8")
    app = ui.UIRouter(_Inner(), token="sekrit", html_path=str(html))
    status, body = _run(app, "/ui")  # no Authorization header at all
    assert status == 200 and b"console" in body


def test_ui_page_missing_html_is_500_not_crash():
    app = ui.UIRouter(_Inner(), token="", html_path="/nonexistent/x.html")
    status, body = _run(app, "/ui")
    assert status == 500 and b"not found" in body


def test_api_requires_token_when_set():
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(app, "/api/ui/overview")
    assert status == 401
    assert _json_of(body)["error"] == "unauthorized"


@pytest.mark.parametrize("auth", ["Bearer sekrit", "sekrit"])
def test_api_accepts_bearer_and_raw_token(auth, monkeypatch):
    # Same normalisation contract as goethe_mcp._TokenGuard (v1.9.3).
    monkeypatch.setenv("GOETHE_ES_URL", "http://127.0.0.1:1")  # dead port
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(app, "/api/ui/overview", auth=auth)
    assert status == 200
    assert _json_of(body)["es_ok"] is False  # ES down != endpoint failure


def test_api_wrong_token_rejected():
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, _ = _run(app, "/api/ui/overview", auth="Bearer wrong")
    assert status == 401


def test_api_open_when_no_token_configured(monkeypatch):
    # Mirrors the MCP endpoint posture: no token → localhost binding is the gate.
    monkeypatch.setenv("GOETHE_ES_URL", "http://127.0.0.1:1")
    app = ui.UIRouter(_Inner(), token="")
    status, _ = _run(app, "/api/ui/overview")
    assert status == 200


def test_traum_get_and_post_require_configured_token(tmp_path):
    class FakeTraum:
        def status(self):
            return {"available": True}

        def start_run(self, _payload):
            return {"run_id": "run_never"}

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    status, body = _run(app, "/api/ui/traum/status")
    assert status == 401 and _json_of(body)["error"] == "unauthorized"
    status, body = _run(
        app, "/api/ui/traum/runs", method="POST",
        payload={"profile": "standard"},
    )
    assert status == 401 and _json_of(body)["error"] == "unauthorized"

    no_token_app = ui.UIRouter(
        _Inner(), token="", traum_controller=FakeTraum())
    status, body = _run(no_token_app, "/api/ui/traum/status")
    assert status == 503
    assert "token not configured" in _json_of(body)["error"]


def test_traum_rejects_raw_command_shaped_payload(tmp_path):
    ctl = ui._traum_control.TraumController(
        dream_dir=str(tmp_path), repo_root=os.path.join(_HERE, ".."),
        python_bin="/fixed/python", auto_revalidate=False,
    )
    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=ctl)
    status, body = _run(
        app, "/api/ui/traum/runs", method="POST", auth="Bearer sekrit",
        payload={"profile": "standard", "command": "rm -rf /"},
    )
    assert status == 400
    assert "unsupported field" in _json_of(body)["error"]
    assert ctl.state.list_runs() == []


def test_traum_revalidate_route_is_typed_and_bounded():
    calls = []

    class FakeTraum:
        def revalidate_queue(self, payload):
            calls.append(payload)
            return {"auto_rejected": 2, "still_actionable": 1,
                    "applies_anything": False}

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    status, body = _run(
        app, "/api/ui/traum/proposals/revalidate", method="POST",
        auth="Bearer sekrit", payload={"limit": 25},
    )
    assert status == 200
    assert _json_of(body)["auto_rejected"] == 2
    assert calls == [{"limit": 25}]

    # The sweep is not a decision route: no proposal ID path form exists.
    status, _ = _run(
        app, "/api/ui/traum/proposals/revalidate/apply", method="POST",
        auth="Bearer sekrit", payload={},
    )
    assert status == 404


def test_traum_has_no_timer_mutation_route():
    class FakeTraum:
        pass

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    status, body = _run(
        app, "/api/ui/traum/timer/pause", method="POST",
        auth="Bearer sekrit", payload={},
    )
    assert status == 404
    assert _json_of(body)["error"] == "unknown TRAUM route"


def test_traum_proposal_route_passes_bounded_pagination_fields():
    calls = []

    class FakeTraum:
        def list_proposals(self, **kwargs):
            calls.append(kwargs)
            return {
                "proposals": [], "total_visible": 0,
                "limit": kwargs["limit"], "offset": kwargs["offset"],
            }

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    status, body = _run(
        app, "/api/ui/traum/proposals", auth="Bearer sekrit",
        query="state=PENDING%2CDEFERRED&actionable=true&limit=50&offset=100",
    )
    assert status == 200
    assert _json_of(body)["offset"] == 100
    assert calls == [{
        "state": "PENDING,DEFERRED", "limit": 50, "offset": 100,
        "actionable_only": True,
    }]


# --------------------------------------------------------------------------
# Fail-safe contract: ES down → JSON error field, never an exception/500
# --------------------------------------------------------------------------

def test_kb_panel_with_es_down_answers_json_error(monkeypatch):
    monkeypatch.setenv("GOETHE_ES_URL", "http://127.0.0.1:1")
    app = ui.UIRouter(_Inner(), token="")
    status, body = _run(app, "/api/ui/kb")
    assert status == 200
    data = _json_of(body)
    assert "error" in data and "_elapsed_ms" in data


# --------------------------------------------------------------------------
# Panel builders against tmp fixtures
# --------------------------------------------------------------------------

def test_ledger_stats_reads_task_blocks_readonly(tmp_path, monkeypatch):
    db = tmp_path / "tasks.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_blocks (task_id TEXT PRIMARY KEY, goal TEXT, "
        "status TEXT, plan TEXT, done_steps TEXT, findings TEXT, "
        "unverified TEXT, next_prompt TEXT, checkpoints INTEGER, "
        "created_at TEXT, updated_at TEXT, steps_json TEXT)")
    steps = json.dumps([{"status": "done"}, {"status": "done"},
                        {"status": "pending"}])
    conn.execute(
        "INSERT INTO task_blocks VALUES ('abc12345','fix wifi','open','','',"
        "'','','',2,'2026-07-01','2026-07-02',?)", (steps,))
    conn.commit()
    conn.close()
    monkeypatch.setenv("GOETHE_TASKS_DB", str(db))

    d = ui.ledger_stats()
    assert d["counts"] == {"open": 1}
    t = d["tasks"][0]
    assert (t["goal"], t["steps_done"], t["steps_total"]) == ("fix wifi", 2, 3)


def test_ledger_stats_missing_db_is_empty_not_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GOETHE_TASKS_DB", str(tmp_path / "nope.db"))
    d = ui.ledger_stats()
    assert d["tasks"] == [] and d["counts"] == {}


def test_ledger_stats_returns_every_task_without_display_cap(
        tmp_path, monkeypatch):
    db = tmp_path / "tasks.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_blocks (task_id TEXT PRIMARY KEY, goal TEXT, "
        "status TEXT, checkpoints INTEGER, created_at TEXT, updated_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO task_blocks VALUES (?,?,?,?,?,?)",
        [
            (
                f"task-{i:02d}",
                f"fixture {i}",
                "open",
                0,
                "2026-07-01",
                f"2026-07-{(i % 28) + 1:02d}",
            )
            for i in range(57)
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("GOETHE_TASKS_DB", str(db))

    d = ui.ledger_stats()
    assert len(d["tasks"]) == 57
    assert d["counts"] == {"open": 57}


def test_delete_task_block_archives_complete_row_before_delete(
        tmp_path, monkeypatch):
    db = tmp_path / "tasks.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_blocks (task_id TEXT PRIMARY KEY, goal TEXT, "
        "status TEXT, plan TEXT, done_steps TEXT, findings TEXT, "
        "unverified TEXT, next_prompt TEXT, checkpoints INTEGER, "
        "created_at TEXT, updated_at TEXT, steps_json TEXT, backend TEXT)"
    )
    conn.execute(
        "INSERT INTO task_blocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "stale-task-42",
            "remove stale fixture",
            "open",
            "one,two",
            "one",
            "finding",
            "two",
            "resume",
            3,
            "2026-06-01",
            "2026-06-02",
            '[{"status":"done"}]',
            "local",
        ),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("GOETHE_TASKS_DB", str(db))

    result = ui.delete_task_block("stale-task-42")
    assert result == {
        "status": "deleted",
        "task_id": "stale-task-42",
        "goal": "remove stale fixture",
        "previous_status": "open",
        "archived": True,
    }

    conn = sqlite3.connect(db)
    assert conn.execute(
        "SELECT 1 FROM task_blocks WHERE task_id='stale-task-42'"
    ).fetchone() is None
    archived = conn.execute(
        "SELECT task_id,row_json FROM task_blocks_deleted"
    ).fetchone()
    conn.close()
    assert archived[0] == "stale-task-42"
    snapshot = json.loads(archived[1])
    assert snapshot["goal"] == "remove stale fixture"
    assert snapshot["findings"] == "finding"
    assert snapshot["backend"] == "local"


@pytest.mark.parametrize(
    "task_id",
    [None, "", "x" * 129, "bad\nid"],
)
def test_delete_task_block_rejects_invalid_exact_id(
        task_id, tmp_path, monkeypatch):
    db = tmp_path / "tasks.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_blocks (task_id TEXT PRIMARY KEY, goal TEXT)"
    )
    conn.execute("INSERT INTO task_blocks VALUES ('safe-id','keep me')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("GOETHE_TASKS_DB", str(db))

    assert "error" in ui.delete_task_block(task_id)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM task_blocks").fetchone()[0] == 1
    conn.close()


def test_task_delete_route_is_authenticated_and_exact(
        tmp_path, monkeypatch):
    db = tmp_path / "tasks.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE task_blocks (task_id TEXT PRIMARY KEY, goal TEXT, "
        "status TEXT)"
    )
    conn.execute(
        "INSERT INTO task_blocks VALUES ('exact-task','stale','open')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("GOETHE_TASKS_DB", str(db))
    app = ui.UIRouter(_Inner(), token="sekrit")

    status, _body = _run(
        app,
        "/api/ui/ledger/delete",
        method="POST",
        json_body={"task_id": "exact-task"},
    )
    assert status == 401

    status, body = _run(
        app,
        "/api/ui/ledger/delete",
        method="POST",
        auth="Bearer sekrit",
        json_body={"task_id": "exact-task"},
    )
    assert status == 200
    assert _json_of(body)["archived"] is True

    status, body = _run(
        app,
        "/api/ui/ledger/delete",
        method="POST",
        auth="Bearer sekrit",
        json_body={"task_id": "exact-task"},
    )
    assert status == 409
    assert "no task block" in _json_of(body)["error"]


def test_dream_stats_reads_digest_and_day_dirs(tmp_path, monkeypatch):
    (tmp_path / "latest-digest.md").write_text(
        "# TRAUM dream digest — generated 2026-07-19\n- applied: 3 merges\n",
        encoding="utf-8")
    day = tmp_path / "2026-07-18"
    day.mkdir()
    (day / "proposals-dedup.jsonl").write_text(
        '{"status":"pending","kind":"merge"}\n'
        '{"status":"applied","kind":"merge"}\n', encoding="utf-8")
    (day / "crashes.jsonl").write_text('{"err":"boom"}\n', encoding="utf-8")
    (day / "report-dedup.md").write_text("all good\n", encoding="utf-8")
    monkeypatch.setenv("GOETHE_DREAM_DIR", str(tmp_path))

    d = ui.dream_stats()
    assert "TRAUM dream digest" in d["digest"]
    day_out = d["days"][0]
    assert day_out["date"] == "2026-07-18"
    assert day_out["proposals"] == 2
    assert day_out["status_counts"] == {"pending": 1, "applied": 1}
    assert day_out["crashes"] == 1
    assert day_out["failed_banner"] is False
    assert day_out["passes"] == [{"pass": "dedup", "proposals": 2}]


def test_dream_stats_failed_banner_detected(tmp_path, monkeypatch):
    day = tmp_path / "2026-07-17"
    day.mkdir()
    (day / "report-patterns.md").write_text(
        "# FAILED — dream cycle crashed\n", encoding="utf-8")
    monkeypatch.setenv("GOETHE_DREAM_DIR", str(tmp_path))
    assert ui.dream_stats()["days"][0]["failed_banner"] is True


def test_episode_stats_counts_exit_classes(tmp_path, monkeypatch):
    day = tmp_path / "2026-07-19"
    day.mkdir()
    lines = [
        {"ts": "t", "session_id": "s1", "tool": "search_kb",
         "args_redacted": {}, "result_truncated": "ok", "exit_class": "ok"},
        {"ts": "t", "session_id": "s1", "tool": "execute_command",
         "args_redacted": {}, "result_truncated": "BLOCKED: sudo",
         "exit_class": "denied"},
        {"ts": "t", "session_id": "s1", "tool": "search_kb",
         "args_redacted": {}, "result_truncated": "boom",
         "exit_class": "error"},
    ]
    (day / "sess-1.jsonl").write_text(
        "".join(json.dumps(rec) + "\n" for rec in lines), encoding="utf-8")
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(tmp_path))

    d = ui.episode_stats()
    day_out = d["days"][-1]
    assert day_out["total"] == 3 and day_out["sessions"] == 1
    assert day_out["exit"]["ok"] == 1
    assert day_out["exit"]["denied"] == 1
    assert day_out["exit"]["error"] == 1
    assert d["top_tools"][0] == {"tool": "search_kb", "count": 2}


def test_episode_stats_disabled_dir_is_empty(monkeypatch):
    monkeypatch.setenv("GOETHE_EPISODE_DIR", "")
    d = ui.episode_stats()
    assert d["days"] == []


def test_console_surfaces_sudo_validation_errors(monkeypatch):
    class UnsafePerms:
        @staticmethod
        def resolve_request(_rid, approve, once=False):
            assert approve is True
            raise ValueError("sudo grant cannot contain shell control operators")

    monkeypatch.setattr(ui, "_perms", UnsafePerms)
    data = ui._perm_action("approve", 6, once=False)
    assert data == {
        "error": "ValueError: sudo grant cannot contain shell control operators"
    }


def test_console_deletes_only_unapprovable_request(monkeypatch):
    calls = []

    class FakePerms:
        @staticmethod
        def delete_unapprovable_request(rid):
            calls.append(rid)
            return True

    monkeypatch.setattr(ui, "_perms", FakePerms)
    data = ui._perm_action("delete", 17, once=False)
    assert data == {"status": "deleted"}
    assert calls == [17]


def test_delete_request_route_requires_auth_and_integer_id(monkeypatch):
    class FakePerms:
        @staticmethod
        def delete_unapprovable_request(rid):
            assert rid == 17
            return True

    monkeypatch.setattr(ui, "_perms", FakePerms)
    app = ui.UIRouter(_Inner(), token="sekrit")

    status, _body = _run(
        app,
        "/api/ui/perms/delete",
        method="POST",
        json_body={"id": 17},
    )
    assert status == 401

    status, body = _run(
        app,
        "/api/ui/perms/delete",
        method="POST",
        auth="Bearer sekrit",
        json_body={"id": 17},
    )
    assert status == 200
    assert _json_of(body)["status"] == "deleted"


def test_bulk_delete_route_reports_deleted_count(monkeypatch):
    class FakePerms:
        @staticmethod
        def delete_all_unapprovable_requests():
            return 12

    monkeypatch.setattr(ui, "_perms", FakePerms)
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(
        app,
        "/api/ui/perms/delete-invalid",
        method="POST",
        auth="Bearer sekrit",
        json_body={},
    )
    assert status == 200
    assert _json_of(body) == {"status": "deleted", "deleted": 12}


def test_dashboard_marks_unsafe_legacy_sudo_grants_not_installable():
    with open(
        os.path.join(_HERE, "..", "tools", "goethe_dashboard.html"),
        encoding="utf-8",
    ) as dashboard:
        html = dashboard.read()
    assert "not installable" in html
    assert "sudoers_valid === false" in html
    assert "Unsafe legacy grants" in html
    assert "Delete all" in html
    assert 'permAction(\\"delete\\"' in html
    assert "/api/ui/perms/delete-invalid" in html


def test_dashboard_renders_complete_scrollable_deletable_ledger():
    with open(
        os.path.join(_HERE, "..", "tools", "goethe_dashboard.html"),
        encoding="utf-8",
    ) as dashboard:
        html = dashboard.read()
    assert ".slice(0,12)" not in html
    assert 'class="ledger-scroll"' in html
    assert "scrollbar-width:none" in html
    assert "overscroll-behavior:contain" in html
    assert "/api/ui/ledger/delete" in html
    assert "deleteLedgerTask" in html
    assert "task will disappear from the active ledger" in html


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --------------------------------------------------------------------------
# Validation-error propagation (F821 regression, 2026-07-31)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "query", "method", "payload"),
    [
        ("/api/ui/traum/runs", "archived=maybe", "GET", None),
        ("/api/ui/traum/runs", "limit=notanumber", "GET", None),
        ("/api/ui/traum/proposals", "actionable=perhaps", "GET", None),
        ("/api/ui/traum/proposals", "limit=xyz", "GET", None),
        ("/api/ui/traum/runs/r1/logs", "limit=xyz", "GET", None),
    ],
)
def test_bad_query_params_return_400_with_the_real_message(
        path, query, method, payload):
    """CONTRACT PIN: a malformed query parameter answers 400 with the real
    validation message, never 503.

    These handlers re-raise a caught validation error inside _traum_response
    via a lambda, so that _traum_response's status mapping (ValueError -> 400)
    applies rather than the generic 503 branch.

    HONEST SCOPE NOTE (2026-07-31). ruff flags the seven lambdas as F821
    because `exc` is unbound once the `except` block exits. That warning is
    legitimate but the code was NOT broken: each `await _traum_response(...)`
    happens INSIDE its except block, so `exc` is still bound when the worker
    thread invokes the lambda. Verified by reverting the fix and re-running
    this file — all tests still passed. The lambdas were nevertheless changed
    to bind the exception as a default argument (`lambda e=exc:`), which is
    equivalent today and stays correct if anyone later defers the call past
    the block; in that shape the old form really does yield
    `503 NameError` and lose the original error.

    So: this test pins the 400-vs-503 contract, which is real and worth
    holding. It does NOT discriminate between the two lambda forms, and is
    not claimed to.
    """
    class FakeTraum:
        def list_runs(self, **_kw):
            return {"runs": []}

        def list_proposals(self, **_kw):
            return {"proposals": []}

        def logs(self, _run_id, **_kw):
            return {"logs": []}

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    status, body = _run(app, path, method=method, query=query,
                        payload=payload, auth="Bearer sekrit")
    parsed = _json_of(body)

    assert status == 400, (
        f"expected 400 for {path}?{query}, got {status}: {parsed}")
    assert "NameError" not in parsed.get("error", ""), (
        "the exc-closure bug is back: the handler's own error masked the "
        f"validation error -> {parsed}")
    assert parsed.get("error", "").startswith("bad request:"), parsed


def test_malformed_json_body_returns_400_not_503():
    """Same contract on the POST paths, which catch json.JSONDecodeError."""
    class FakeTraum:
        def start_run(self, _payload):
            return {"run_id": "r1"}

    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=FakeTraum())
    scope = {"type": "http", "path": "/api/ui/traum/runs", "method": "POST",
             "query_string": b"",
             "headers": [(b"authorization", b"Bearer sekrit")]}
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"{not valid json",
                "more_body": False}

    async def send(msg):
        messages.append(msg)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages
                  if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages
                    if m["type"] == "http.response.body")
    parsed = _json_of(body)
    assert status == 400, f"expected 400, got {status}: {parsed}"
    assert "NameError" not in parsed.get("error", ""), parsed


# --------------------------------------------------------------------------
# sync-sudoers terminal launcher (2026-07-31)
# --------------------------------------------------------------------------

def test_sync_terminal_requires_token():
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(app, "/api/ui/perms/sync-terminal", method="POST")
    assert status == 401 and _json_of(body)["error"] == "unauthorized"


def test_sync_terminal_never_runs_the_sync_itself(monkeypatch):
    """CONTRACT. The Console must never perform the sudoers install.

    The endpoint may only spawn an interactive terminal. It must not invoke
    goethe-perm, sudo, or install directly — the human confirms in the
    terminal and sudo still prompts. This test inspects the argv actually
    handed to Popen.
    """
    spawned = []

    class FakePopen:
        def __init__(self, argv, **kw):
            spawned.append(argv)

    monkeypatch.setattr(ui.os.environ, "get",
                        lambda k, d=None: "Ubuntu-24.04"
                        if k == "WSL_DISTRO_NAME" else (d or ""))
    monkeypatch.setattr(ui.os.path, "exists", lambda p: "wsl.exe" in p)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(app, "/api/ui/perms/sync-terminal", method="POST",
                        auth="Bearer sekrit")
    assert status == 200, _json_of(body)
    assert len(spawned) == 1, spawned
    argv = spawned[0]

    # It launches a terminal, not the sync.
    assert argv[0].endswith("wsl.exe"), argv
    joined = " ".join(argv)
    # The command appears as PRE-FILLED TEXT for `read -e -i`, never as an
    # executed argv element.
    assert "read -e -i" in joined, joined
    assert not any(a in ("sudo", "install", "goethe-perm") for a in argv), argv


def test_sync_terminal_reports_failure_instead_of_raising(monkeypatch):
    """Without WSL interop the endpoint must answer with the command, so the
    UI can fall back to copy-to-clipboard rather than leaving the operator
    stuck."""
    monkeypatch.setattr(ui.os.environ, "get", lambda k, d=None: d or "")
    app = ui.UIRouter(_Inner(), token="sekrit")
    status, body = _run(app, "/api/ui/perms/sync-terminal", method="POST",
                        auth="Bearer sekrit")
    parsed = _json_of(body)
    assert status == 503
    assert parsed["ok"] is False
    assert parsed["command"] == "goethe-perm sync-sudoers"
    assert "error" in parsed


def test_sync_command_is_a_fixed_constant_with_no_interpolation():
    """No part of the command may come from request data — the argv is built
    from _SYNC_CMD only, so there is no injection surface."""
    app = ui.UIRouter(_Inner(), token="sekrit")
    assert app._SYNC_CMD == "goethe-perm sync-sudoers"
    import inspect
    src = inspect.getsource(type(app)._open_sync_terminal)
    # the payload string must be built from the constant, not from a parameter
    assert "self._SYNC_CMD" in src
    assert "payload" not in src and "receive" not in src


# --- SPEC-subpass-outcomes-2026-08 SS5.4: Console shows the DEGRADED ratio ---

def _dashboard_script_text():
    with open(
        os.path.join(_HERE, "..", "tools", "goethe_dashboard.html"),
        encoding="utf-8",
    ) as dashboard:
        html = dashboard.read()
    import re
    chunks = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert chunks, "goethe_dashboard.html has no inline <script> block"
    return "\n".join(chunks)


def test_state_badge_takes_a_ratio_and_only_suffixes_when_given_one():
    js = _dashboard_script_text()
    assert "function stateBadge(state, ratio){" in js
    assert "const suffix = ratio ? ' ('+esc(ratio)+')' : '';" in js
    assert "esc(s)+suffix+'</span>'" in js


def test_run_table_computes_ratio_from_run_summary_only_for_degraded():
    js = _dashboard_script_text()
    assert 'const rsum = run.summary || {};' in js
    assert 'run.state==="DEGRADED"' in js
    assert "rsum.passes_good" in js and "rsum.passes_total" in js
    # wired into the actual badge call for the run-table row, not left unused
    assert "stateBadge(run.state,ratio)" in js


def test_extracted_dashboard_js_is_syntactically_valid():
    """Best-effort real parse, not just string matching -- SPEC test 7.
    Skips (does not fail) when node is not installed on this host; a
    missing interpreter is an environment gap, not a code defect. See the
    2026-08 subpass-outcomes report for whether this ran for real here.
    """
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node is not installed in this environment")
    js = _dashboard_script_text()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(js)
        tmp_path = fh.name
    try:
        result = subprocess.run(
            [node, "--check", tmp_path], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
    finally:
        os.unlink(tmp_path)


def _kb_badge_cell_expression():
    """Pull the KB panel's badge ternary out of the dashboard, verbatim.

    Anchored on the literal `"<td>"+(` ... `)+"</td></tr>"` that wraps it, so
    the test evaluates the SHIPPED expression rather than a copy that can
    drift away from it.
    """
    js = _dashboard_script_text()
    m = re.search(r'"<td>"\+\((w\.mentor_demoted_at.*?)\)\+"</td></tr>"', js, re.S)
    assert m, "could not locate the KB badge ternary in goethe_dashboard.html"
    return m.group(1)


def _render_kb_badge(fixtures):
    """Evaluate the real ternary in node against `fixtures`; return rendered cells."""
    import json
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node is not installed in this environment")

    esc_src = (
        'const esc = s => String(s ?? "").replace(/[&<>"\']/g, '
        'c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));'
    )
    harness = (
        esc_src
        + "\nfunction cell(w){ return (" + _kb_badge_cell_expression() + "); }\n"
        + "const out = " + json.dumps(fixtures) + ".map(cell);\n"
        + "console.log(JSON.stringify(out));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(harness)
        path = fh.name
    try:
        r = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, f"node failed: {r.stderr}"
        return json.loads(r.stdout.strip())
    finally:
        os.unlink(path)


def test_kb_panel_superseded_vs_quarantined_badge_branch():
    """Console KB panel must distinguish mentor-demoted (SUPERSEDED) from
    kb_verify-decayed (QUARANTINED).

    BEHAVIOURAL, deliberately. The first version of this test asserted only
    that the strings "SUPERSEDED" and "QUARANTINED" appeared in the source in
    that order. Mutating the branch condition from `===0` to `!==0` -- exactly
    inverting it -- left that test green (47 passed, 2026-08-08). A gate that
    cannot fail for the reason it exists is not a gate. Same anti-pattern as
    the docstring-truncation gate that checked 36 of 48 tools, and the
    source-text match ccbe879 replaced.
    """
    a, b, c, d = _render_kb_badge([
        # a. mentor-demoted, failure_count 0 -> SUPERSEDED
        {"mentor_demoted_at": "2026-07-22T09:07:32Z", "failure_count": 0,
         "stale": True, "demote_reason": "Superseded by definitive doc 842595879f70576d"},
        # b. mentor-demoted, failure_count MISSING -> still SUPERSEDED.
        #    Live data has this: 'node3090 Model Store (part 2)' carries
        #    mentor_demoted_at with no failure_count at all. A strict `=== 0`
        #    without the `||0` guard renders QUARANTINED here and is wrong.
        {"mentor_demoted_at": "2026-07-20T05:08:38Z",
         "stale": True, "demote_reason": "Redundant — merged into doc 116550382e3854cf"},
        # c. stale by failure decay, never demoted -> QUARANTINED
        {"stale": True, "failure_count": 3},
        # d. healthy -> empty cell
        {"stale": False, "failure_count": 0},
    ])

    assert "SUPERSEDED" in a and "QUARANTINED" not in a, a
    assert "SUPERSEDED" in b and "QUARANTINED" not in b, b
    assert "QUARANTINED" in c and "SUPERSEDED" not in c, c
    assert d == "", f"healthy doc must render an empty cell, got {d!r}"

    # the reason travels as an escaped tooltip, not as body text
    assert 'title="Superseded by definitive doc 842595879f70576d"' in a, a
    assert ">SUPERSEDED<" in a, a


def test_kb_panel_badge_tooltip_is_escaped():
    """demote_reason is operator-authored free text and reaches the DOM."""
    (cell,) = _render_kb_badge([
        {"mentor_demoted_at": "2026-07-22T09:07:32Z", "failure_count": 0,
         "stale": True, "demote_reason": '<script>alert("x")</script>'},
    ])
    assert "<script>" not in cell, cell
    assert "&lt;script&gt;" in cell, cell


def test_kb_panel_api_exposes_the_fields_the_badge_needs():
    """goethe_ui.py must actually send what the branch reads.

    The roadmap claimed this fix was display-only because 'the data needed
    already exists'. It exists in Elasticsearch; it was NOT in the API
    payload. Without these three fields every doc renders QUARANTINED again.
    """
    with open(_UI_PATH, encoding="utf-8") as f:
        ui_source = f.read()
    for field in ("mentor_demoted_at", "failure_count", "demote_reason"):
        assert f'"{field}"' in ui_source, \
            f"goethe_ui.py doc_fields missing field: {field}"
