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
