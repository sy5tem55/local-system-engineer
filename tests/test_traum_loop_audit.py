"""
Unit tests for scripts/traum-loop-audit.py -- the ground-truth loop-health
check (Part 2B of the 2026-08-12 TRAUM feedback-loop work).

Covers:
  1. Skill retrieval / KB consultation counts respect the lookback window
     and only count the named tool.
  2. Outcome recording splits attempted/succeeded/errored -- and `ok` is
     false when calls happen but none land.               [load-bearing]
  3. Dream-loop completion requires SUCCEEDED *and* passes_good ==
     passes_total; a DEGRADED or partial run is not "ok".
  4. The traum-state.db connection is opened read-only for real -- a write
     attempt through the same connection actually raises.  [load-bearing]
  5. Malformed/partial episode lines are skipped, not fatal.
  6. render_report() surfaces the correct red-check list.

Run:
    /home/sy5/owui/bin/python3 -m pytest tests/test_traum_loop_audit.py -v
"""

import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "traum-loop-audit.py"


@pytest.fixture(scope="module")
def tla():
    spec = importlib.util.spec_from_file_location("traum_loop_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


def _write_session(day_dir: Path, session_id: str, lines: list):
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{session_id}.jsonl"
    with open(path, "w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


def _call(tool: str, ts: datetime, result: str = "ok", **args) -> dict:
    return {
        "ts": ts.isoformat(),
        "session_id": "sess-test",
        "tool": tool,
        "args_redacted": args,
        "result_truncated": result,
        "exit_class": "ok",
    }


# ---------------------------------------------------------------------------
# Q1/Q3 -- retrieval / consultation counting + window respect
# ---------------------------------------------------------------------------

def test_skill_retrieval_counts_only_named_tool_in_window(tla, tmp_path):
    ep = tmp_path / "episodes"
    in_window = NOW - timedelta(days=1)
    out_of_window = NOW - timedelta(days=10)
    day1 = ep / in_window.strftime("%Y-%m-%d")
    day2 = ep / out_of_window.strftime("%Y-%m-%d")
    _write_session(day1, "s1", [
        _call("skill_search", in_window),
        _call("skill_record", in_window),  # different tool, must not count
    ])
    _write_session(day2, "s2", [_call("skill_search", out_of_window)])

    result = tla.check_skill_retrieval(str(ep), since_days=3, now=NOW)
    assert result["count"] == 1
    assert result["ok"] is True


def test_skill_retrieval_zero_when_no_calls(tla, tmp_path):
    ep = tmp_path / "episodes"
    ep.mkdir()
    result = tla.check_skill_retrieval(str(ep), since_days=3, now=NOW)
    assert result["count"] == 0
    assert result["ok"] is False


def test_kb_consultation_counts_search_kb_only(tla, tmp_path):
    ep = tmp_path / "episodes"
    day = ep / NOW.strftime("%Y-%m-%d")
    _write_session(day, "s1", [
        _call("search_kb", NOW),
        _call("search_kb", NOW),
        _call("index_to_kb", NOW),  # different tool, must not count
    ])
    result = tla.check_kb_consultation(str(ep), since_days=3, now=NOW)
    assert result["count"] == 2
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Q2 -- outcome recording: attempted/succeeded/errored split (load-bearing)
# ---------------------------------------------------------------------------

def test_outcome_recording_ok_false_when_all_attempts_error(tla, tmp_path):
    """This is the exact real-world shape found 2026-08-12: the tool is
    called, every call errors, and the naive 'was it called' question would
    say yes when the true answer -- 'did anything land' -- is no."""
    ep = tmp_path / "episodes"
    day = ep / NOW.strftime("%Y-%m-%d")
    _write_session(day, "s1", [
        _call("skill_outcome", NOW,
              result="SKILL outcome error: skill_id 'x/y' not found."),
        _call("skill_outcome", NOW,
              result="SKILL outcome error: skill_id 'a/b' not found."),
    ])
    result = tla.check_outcome_recording(str(ep), since_days=3, now=NOW)
    assert result["attempted"] == 2
    assert result["succeeded"] == 0
    assert result["errored"] == 2
    assert result["ok"] is False
    assert "not found" in result["last_error"]


def test_outcome_recording_ok_true_when_at_least_one_succeeds(tla, tmp_path):
    ep = tmp_path / "episodes"
    day = ep / NOW.strftime("%Y-%m-%d")
    _write_session(day, "s1", [
        _call("skill_outcome", NOW,
              result="SKILL outcome recorded: x/y | quality 0.50 -> 0.60"),
        _call("skill_outcome", NOW,
              result="SKILL outcome error: skill_id 'a/b' not found."),
    ])
    result = tla.check_outcome_recording(str(ep), since_days=3, now=NOW)
    assert result["attempted"] == 2
    assert result["succeeded"] == 1
    assert result["errored"] == 1
    assert result["ok"] is True


def test_outcome_recording_zero_attempts_is_also_not_ok(tla, tmp_path):
    """Zero attempts and all-error attempts must both be 'ok': False -- but
    the caller-visible detail (attempted count) must distinguish them."""
    ep = tmp_path / "episodes"
    ep.mkdir()
    result = tla.check_outcome_recording(str(ep), since_days=3, now=NOW)
    assert result["attempted"] == 0
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Q4 -- dream loop completion
# ---------------------------------------------------------------------------

def _make_traum_db(path: Path, runs: list):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE runs (run_id TEXT, state TEXT, summary_json TEXT, "
        "created_at TEXT, finished_at TEXT)"
    )
    for r in runs:
        conn.execute(
            "INSERT INTO runs (run_id, state, summary_json, created_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (r["run_id"], r["state"], json.dumps(r.get("summary", {})),
             r["created_at"], r.get("finished_at")),
        )
    conn.commit()
    conn.close()


def test_dream_loop_ok_when_latest_run_fully_succeeded(tla, tmp_path):
    db = tmp_path / "traum-state.db"
    _make_traum_db(db, [
        {"run_id": "run_1", "state": "SUCCEEDED",
         "summary": {"passes_good": 6, "passes_total": 6},
         "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%S")},
    ])
    result = tla.check_dream_loop_completion(str(db), since_days=3, now=NOW)
    assert result["ok"] is True
    assert result["runs_in_window"] == 1


def test_dream_loop_not_ok_when_latest_run_degraded(tla, tmp_path):
    db = tmp_path / "traum-state.db"
    _make_traum_db(db, [
        {"run_id": "run_1", "state": "DEGRADED",
         "summary": {"passes_good": 3, "passes_total": 6},
         "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%S")},
    ])
    result = tla.check_dream_loop_completion(str(db), since_days=3, now=NOW)
    assert result["ok"] is False


def test_dream_loop_not_ok_when_no_runs_in_window(tla, tmp_path):
    db = tmp_path / "traum-state.db"
    _make_traum_db(db, [
        {"run_id": "run_1", "state": "SUCCEEDED",
         "summary": {"passes_good": 6, "passes_total": 6},
         "created_at": (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")},
    ])
    result = tla.check_dream_loop_completion(str(db), since_days=3, now=NOW)
    assert result["ok"] is False
    assert result["runs_in_window"] == 0


def test_dream_loop_db_is_opened_read_only(tla, tmp_path):
    """Load-bearing: prove the mode=ro claim, don't just trust the comment.
    A write attempt through the exact same connection style must raise."""
    db = tmp_path / "traum-state.db"
    _make_traum_db(db, [
        {"run_id": "run_1", "state": "SUCCEEDED",
         "summary": {"passes_good": 1, "passes_total": 1},
         "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%S")},
    ])
    # exercise the real function first (must not raise)
    tla.check_dream_loop_completion(str(db), since_days=3, now=NOW)

    uri = f"file:{db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO runs (run_id, state, summary_json, created_at, finished_at) "
                     "VALUES ('x', 'SUCCEEDED', '{}', '2026-01-01', NULL)")
        conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Robustness -- malformed lines, gz files
# ---------------------------------------------------------------------------

def test_malformed_lines_are_skipped_not_fatal(tla, tmp_path):
    ep = tmp_path / "episodes"
    day = ep / NOW.strftime("%Y-%m-%d")
    day.mkdir(parents=True)
    path = day / "sess-bad.jsonl"
    with open(path, "w") as f:
        f.write(json.dumps(_call("skill_search", NOW)) + "\n")
        f.write("{not valid json\n")
        f.write("\n")  # blank line
        f.write(json.dumps(_call("skill_search", NOW)) + "\n")

    result = tla.check_skill_retrieval(str(ep), since_days=3, now=NOW)
    assert result["count"] == 2


def test_gz_session_files_are_read(tla, tmp_path):
    import gzip
    ep = tmp_path / "episodes"
    day = ep / NOW.strftime("%Y-%m-%d")
    day.mkdir(parents=True)
    path = day / "sess-rotated.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(_call("skill_search", NOW)) + "\n")

    result = tla.check_skill_retrieval(str(ep), since_days=3, now=NOW)
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------

def test_render_report_lists_only_red_checks(tla, tmp_path):
    audit = {
        "generated_at": NOW.isoformat(),
        "lookback_days": 3,
        "skill_retrieval": {"ok": True, "count": 5, "last_ts": NOW.isoformat()},
        "outcome_recording": {"ok": False, "attempted": 2, "succeeded": 0,
                               "errored": 2, "last_error": "not found"},
        "kb_consultation": {"ok": True, "count": 10, "last_ts": NOW.isoformat()},
        "dream_loop": {"ok": True, "runs_in_window": 1,
                        "latest_run": {"run_id": "r1", "state": "SUCCEEDED",
                                       "passes_good": 6, "passes_total": 6}},
        "lse_skills_index": {"reachable": True, "skills": 25,
                              "total_recorded_successes": 0,
                              "total_recorded_failures": 0,
                              "skills_with_any_outcome": 0},
    }
    report = tla.render_report(audit)
    assert "1 check(s) red:" in report
    assert "outcome recording" in report.rsplit("\n", 1)[-1]
    assert "Skill retrieval" in report
    assert "❌" in report and "✅" in report


def test_render_report_all_green(tla):
    audit = {
        "generated_at": NOW.isoformat(),
        "lookback_days": 3,
        "skill_retrieval": {"ok": True, "count": 5, "last_ts": NOW.isoformat()},
        "outcome_recording": {"ok": True, "attempted": 1, "succeeded": 1,
                               "errored": 0, "last_error": None},
        "kb_consultation": {"ok": True, "count": 10, "last_ts": NOW.isoformat()},
        "dream_loop": {"ok": True, "runs_in_window": 1,
                        "latest_run": {"run_id": "r1", "state": "SUCCEEDED",
                                       "passes_good": 6, "passes_total": 6}},
        "lse_skills_index": {"reachable": True, "skills": 25,
                              "total_recorded_successes": 1,
                              "total_recorded_failures": 0,
                              "skills_with_any_outcome": 1},
    }
    report = tla.render_report(audit)
    assert "Loop is alive." in report


# ---------------------------------------------------------------------------
# lse-skills index check -- ES reachability handled gracefully
# ---------------------------------------------------------------------------

def test_lse_skills_index_unreachable_is_reported_not_raised(tla, monkeypatch):
    def _boom(url, timeout=10):
        raise OSError("connection refused")
    monkeypatch.setattr(tla, "_es_get", _boom)
    result = tla.check_lse_skills_index("http://127.0.0.1:9200")
    assert result["reachable"] is False
    assert "connection refused" in result["error"]


def test_lse_skills_index_totals_computed_correctly(tla, monkeypatch):
    def _fake(url, timeout=10):
        return {"hits": {"hits": [
            {"_source": {"stats": {"episode_successes": 2, "episode_failures": 1}}},
            {"_source": {"stats": {"episode_successes": 0, "episode_failures": 0}}},
        ]}}
    monkeypatch.setattr(tla, "_es_get", _fake)
    result = tla.check_lse_skills_index("http://127.0.0.1:9200")
    assert result["reachable"] is True
    assert result["skills"] == 2
    assert result["total_recorded_successes"] == 2
    assert result["total_recorded_failures"] == 1
    assert result["skills_with_any_outcome"] == 1
