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


def _run(app, path, method="GET", auth=None, payload=None, query=""):
    scope = {"type": "http", "path": path, "method": method,
             "query_string": query.encode(),
             "headers": ([(b"authorization", auth.encode())] if auth else [])}
    messages = []
    raw_body = (json.dumps(payload).encode("utf-8")
                if payload is not None else b"")

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
        python_bin="/fixed/python",
    )
    app = ui.UIRouter(_Inner(), token="sekrit", traum_controller=ctl)
    status, body = _run(
        app, "/api/ui/traum/runs", method="POST", auth="Bearer sekrit",
        payload={"profile": "standard", "command": "rm -rf /"},
    )
    assert status == 400
    assert "unsupported field" in _json_of(body)["error"]
    assert ctl.state.list_runs() == []


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
