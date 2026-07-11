"""
Unit tests for the TRAUM episode corpus (TRAUM Thread 1, Prompts 1.3, 1.4, 1.7, 1.8).

Covers tools/episode_index.py's manifest build against synthetic episode
files (the main ask of Prompt 1.4: parse_session_file, build_manifest's
UPSERT-preserves-dreamed_at behavior, and gzip rotation), goethe_mcp.py's
write-time day-dir size cap (the other half of "size hygiene" from the same
prompt), scripts/distill_learnings.py's provenance format contract (Prompt
1.7), and the Prompt 1.8 contract tests: end-to-end journaling redaction of a
Bearer token + vault-shaped secret in the same call, the 2,000-char result
cap, provenance format validation, and journaling-failure-never-raises
verified at the register() wrapper level (not just _safe_journal in
isolation).

No live gateway, no MCP client, no Elasticsearch — episode files are written
directly as fixtures; goethe_mcp's / episode_index's / distill_learnings's
functions are called directly.

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_dream_corpus.py -q
Wired into run_tests(scope=harness) via plain pytest discovery under tests/ —
verified with actual run_tests output, not assumed (see PROVE-1 discipline).
"""

import asyncio
import gzip
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import episode_index as ei  # noqa: E402
import goethe_mcp as gm  # noqa: E402
import distill_learnings as dl  # noqa: E402


# --- fixtures / helpers ------------------------------------------------------

def _write_session(day_dir: Path, session_id: str, lines: list, gz: bool = False) -> Path:
    day_dir.mkdir(parents=True, exist_ok=True)
    name = f"{session_id}.jsonl" + (".gz" if gz else "")
    path = day_dir / name
    text = "\n".join(json.dumps(l) for l in lines) + "\n"
    if gz:
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def _line(ts, tool, exit_class="ok", session_id="s1"):
    return {
        "ts": ts,
        "session_id": session_id,
        "tool": tool,
        "args_redacted": {},
        "result_truncated": "ok",
        "exit_class": exit_class,
    }


# --- parse_session_file -------------------------------------------------------

def test_parse_session_file_normal(tmp_path):
    day_dir = tmp_path / "2026-07-01"
    lines = [
        _line("2026-07-01T10:00:00.000000+02:00", "execute_command", "ok"),
        _line("2026-07-01T10:00:05.000000+02:00", "read_file", "ok"),
        _line("2026-07-01T10:00:02.000000+02:00", "write_file", "denied"),
        _line("2026-07-01T10:00:03.000000+02:00", "execute_command", "error"),
        _line("2026-07-01T10:00:04.000000+02:00", "ssh_run", "timeout"),
    ]
    path = _write_session(day_dir, "sess-a", lines)

    row = ei.parse_session_file(str(path))
    assert row is not None
    assert row["session_id"] == "sess-a"
    assert row["n_calls"] == 5
    # error + timeout count; denied does not (a gate working as intended)
    assert row["n_errors"] == 2
    assert row["start_ts"] == "2026-07-01T10:00:00.000000+02:00"
    assert row["end_ts"] == "2026-07-01T10:00:05.000000+02:00"
    assert json.loads(row["tools_used"]) == ["execute_command", "read_file", "ssh_run", "write_file"]
    assert row["bytes"] > 0


def test_parse_session_file_empty_returns_none(tmp_path):
    day_dir = tmp_path / "2026-07-01"
    path = _write_session(day_dir, "sess-empty", [])
    assert ei.parse_session_file(str(path)) is None


def test_parse_session_file_skips_malformed_lines(tmp_path):
    day_dir = tmp_path / "2026-07-01"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / "sess-mixed.jsonl"
    good1 = json.dumps(_line("2026-07-01T09:00:00.000000+02:00", "execute_command"))
    good2 = json.dumps(_line("2026-07-01T09:00:01.000000+02:00", "read_file"))
    path.write_text(good1 + "\n" + "{not valid json,,,\n" + "\n" + good2 + "\n", encoding="utf-8")

    row = ei.parse_session_file(str(path), verbose=True)
    assert row is not None
    assert row["n_calls"] == 2  # the malformed line and the blank line don't count


def test_parse_session_file_gzip_matches_plain(tmp_path):
    day_dir = tmp_path / "2026-07-01"
    lines = [
        _line("2026-07-01T10:00:00.000000+02:00", "execute_command", "ok"),
        _line("2026-07-01T10:00:01.000000+02:00", "search_kb", "ok"),
    ]
    plain = ei.parse_session_file(str(_write_session(day_dir, "sess-plain", lines)))
    gz = ei.parse_session_file(str(_write_session(day_dir / "gz", "sess-plain", lines, gz=True)))
    assert plain["n_calls"] == gz["n_calls"] == 2
    assert plain["tools_used"] == gz["tools_used"]
    assert plain["start_ts"] == gz["start_ts"]


def test_parse_session_file_missing_file_returns_none(tmp_path):
    assert ei.parse_session_file(str(tmp_path / "does-not-exist.jsonl")) is None


# --- build_manifest ------------------------------------------------------------

def test_build_manifest_writes_expected_rows(tmp_path):
    ep_dir = tmp_path / "episodes"
    _write_session(ep_dir / "2026-07-01", "sess-a", [
        _line("2026-07-01T10:00:00.000000+02:00", "execute_command", "ok"),
        _line("2026-07-01T10:00:01.000000+02:00", "read_file", "error"),
    ])
    _write_session(ep_dir / "2026-07-02", "sess-b", [
        _line("2026-07-02T08:00:00.000000+02:00", "search_kb", "ok"),
    ])
    _write_session(ep_dir / "2026-07-02", "sess-empty", [])  # should be skipped

    manifest_db = str(ep_dir / "manifest.db")
    stats = ei.build_manifest(str(ep_dir), manifest_db)

    assert stats["day_dirs"] == 2
    assert stats["scanned"] == 3
    assert stats["written"] == 2
    assert stats["skipped_empty"] == 1

    conn = sqlite3.connect(manifest_db)
    rows = {r[0]: r for r in conn.execute(
        "SELECT session_id, n_calls, n_errors, dreamed_at FROM sessions ORDER BY session_id"
    )}
    conn.close()

    assert set(rows) == {"sess-a", "sess-b"}
    assert rows["sess-a"][1] == 2  # n_calls
    assert rows["sess-a"][2] == 1  # n_errors
    assert rows["sess-a"][3] is None  # dreamed_at starts NULL
    assert rows["sess-b"][1] == 1


def test_build_manifest_dry_run_writes_nothing(tmp_path):
    ep_dir = tmp_path / "episodes"
    _write_session(ep_dir / "2026-07-01", "sess-a", [
        _line("2026-07-01T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    manifest_db = str(ep_dir / "manifest.db")
    stats = ei.build_manifest(str(ep_dir), manifest_db, dry_run=True)
    assert stats["written"] == 1
    assert not Path(manifest_db).exists()


def test_build_manifest_rescan_preserves_dreamed_at(tmp_path):
    """The whole point of ON CONFLICT ... DO UPDATE excluding dreamed_at:
    Thread 2's dream_apply.py marks a session dreamed; a later manifest
    rebuild (e.g. because the session file grew, or just a routine re-run)
    must not silently reset it back to undreamed."""
    ep_dir = tmp_path / "episodes"
    path = _write_session(ep_dir / "2026-07-01", "sess-a", [
        _line("2026-07-01T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    manifest_db = str(ep_dir / "manifest.db")
    ei.build_manifest(str(ep_dir), manifest_db)

    # Simulate dream_apply.py marking this session dreamed.
    conn = sqlite3.connect(manifest_db)
    conn.execute("UPDATE sessions SET dreamed_at = ? WHERE session_id = ?",
                 ("2026-07-05T00:00:00+02:00", "sess-a"))
    conn.commit()
    conn.close()

    # The session file grows (a stale scenario, but exercises the same path);
    # rebuild the manifest again.
    path.write_text(
        path.read_text(encoding="utf-8") +
        json.dumps(_line("2026-07-01T10:05:00.000000+02:00", "search_kb", "ok")) + "\n",
        encoding="utf-8",
    )
    ei.build_manifest(str(ep_dir), manifest_db)

    conn = sqlite3.connect(manifest_db)
    row = conn.execute(
        "SELECT n_calls, dreamed_at FROM sessions WHERE session_id = ?", ("sess-a",)
    ).fetchone()
    conn.close()
    assert row[0] == 2  # stats picked up the new line
    assert row[1] == "2026-07-05T00:00:00+02:00"  # but dreamed_at survived the rescan


def test_build_manifest_handles_gzipped_sessions(tmp_path):
    ep_dir = tmp_path / "episodes"
    _write_session(ep_dir / "2026-06-01", "sess-old", [
        _line("2026-06-01T10:00:00.000000+02:00", "execute_command", "ok"),
    ], gz=True)
    manifest_db = str(ep_dir / "manifest.db")
    stats = ei.build_manifest(str(ep_dir), manifest_db)
    assert stats["written"] == 1

    conn = sqlite3.connect(manifest_db)
    row = conn.execute("SELECT n_calls FROM sessions WHERE session_id = ?", ("sess-old",)).fetchone()
    conn.close()
    assert row[0] == 1


# --- rotation ------------------------------------------------------------------

def test_rotate_old_sessions_gzips_files_older_than_threshold(tmp_path):
    ep_dir = tmp_path / "episodes"
    old_day = (date.today() - timedelta(days=10)).isoformat()
    recent_day = (date.today() - timedelta(days=1)).isoformat()

    old_path = _write_session(ep_dir / old_day, "sess-old", [
        _line(f"{old_day}T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    recent_path = _write_session(ep_dir / recent_day, "sess-recent", [
        _line(f"{recent_day}T10:00:00.000000+02:00", "execute_command", "ok"),
    ])

    rotated = ei.rotate_old_sessions(str(ep_dir), older_than_days=7)

    assert str(old_path) in rotated
    assert not old_path.exists()
    assert (ep_dir / old_day / "sess-old.jsonl.gz").exists()

    # recent day untouched
    assert recent_path.exists()
    assert not (ep_dir / recent_day / "sess-recent.jsonl.gz").exists()

    # content survives the round trip
    with gzip.open(ep_dir / old_day / "sess-old.jsonl.gz", "rt", encoding="utf-8") as f:
        restored = json.loads(f.readline())
    assert restored["tool"] == "execute_command"


def test_rotate_old_sessions_boundary_exactly_at_threshold_is_not_rotated(tmp_path):
    ep_dir = tmp_path / "episodes"
    boundary_day = (date.today() - timedelta(days=7)).isoformat()
    path = _write_session(ep_dir / boundary_day, "sess-boundary", [
        _line(f"{boundary_day}T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    rotated = ei.rotate_old_sessions(str(ep_dir), older_than_days=7)
    assert rotated == []
    assert path.exists()


def test_rotate_old_sessions_dry_run_touches_nothing(tmp_path):
    ep_dir = tmp_path / "episodes"
    old_day = (date.today() - timedelta(days=10)).isoformat()
    path = _write_session(ep_dir / old_day, "sess-old", [
        _line(f"{old_day}T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    rotated = ei.rotate_old_sessions(str(ep_dir), older_than_days=7, dry_run=True)
    assert rotated == [str(path)]
    assert path.exists()  # nothing actually touched
    assert not (ep_dir / old_day / "sess-old.jsonl.gz").exists()


def test_rotate_old_sessions_cleans_up_stale_original_after_prior_partial_rotation(tmp_path):
    """If a prior run gzipped the file but crashed before removing the
    original, the next run should finish the job rather than double-write."""
    ep_dir = tmp_path / "episodes"
    old_day = (date.today() - timedelta(days=10)).isoformat()
    path = _write_session(ep_dir / old_day, "sess-old", [
        _line(f"{old_day}T10:00:00.000000+02:00", "execute_command", "ok"),
    ])
    # Pre-create the .gz to simulate the crash-after-gzip-before-remove case.
    with open(path, "rb") as f_in, gzip.open(str(path) + ".gz", "wb") as f_out:
        f_out.write(f_in.read())

    ei.rotate_old_sessions(str(ep_dir), older_than_days=7)
    assert not path.exists()
    assert (ep_dir / old_day / "sess-old.jsonl.gz").exists()


# --- goethe_mcp.py: write-time day-dir cap (Prompt 1.4, other half) ------------

def test_journal_refuses_when_day_dir_over_cap(tmp_path, monkeypatch):
    ep_dir = tmp_path / "episodes"
    ep_dir.mkdir()
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    # Force the cap down to something a couple small files can exceed, and
    # clear goethe_mcp's own size cache so the lowered cap takes effect.
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 100)
    gm._day_size_cache.clear()

    day = date.today().isoformat()
    day_dir = ep_dir / day
    day_dir.mkdir()
    (day_dir / "filler.jsonl").write_text("x" * 500, encoding="utf-8")

    gm._journal("execute_command", {"command": "echo hi"}, "hi", None, set())

    session_files = [p for p in day_dir.iterdir() if p.name != "filler.jsonl"]
    assert session_files == []  # refused — no new session file was created


def test_journal_writes_normally_under_cap(tmp_path, monkeypatch):
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    gm._journal("execute_command", {"command": "echo hi"}, "hi there", None, set())

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert line["tool"] == "execute_command"
    assert line["exit_class"] == "ok"


# --- goethe_mcp.py: redaction helpers feeding this corpus (Prompt 1.3 regression) --

def test_redact_text_covers_valve_secret_and_bearer_and_pattern():
    secret_values = {"sk-fake-pfsense-abcdef123456"}
    text = "curl -H 'Authorization: Bearer abc123XYZ' key=sk-fake-pfsense-abcdef123456"
    redacted = gm._redact_text(text, secret_values)
    assert "sk-fake-pfsense-abcdef123456" not in redacted
    assert "abc123XYZ" not in redacted
    assert "[REDACTED:valve-secret]" in redacted
    assert "[REDACTED:bearer-token]" in redacted


def test_redact_args_blanket_redacts_vault_tools():
    args = gm._redact_args("get_vault_secret", {"name": "pfsense-root"}, set())
    assert args == {"name": "[REDACTED:vault-tool-arg]"}


@pytest.mark.parametrize("text,expected", [
    ("BLOCKED: '/etc/shadow' is outside allowed write paths.", "denied"),
    ("[TIMEOUT] ssh_run to host exceeded 30s", "timeout"),
    ("ERROR: Command timed out after 200 seconds.", "timeout"),
    ("ERROR: something else went wrong", "error"),
    ("just a normal result", "ok"),
])
def test_classify_exit_string_conventions(text, expected):
    assert gm._classify_exit(text, None) == expected


def test_classify_exit_exception_is_error():
    assert gm._classify_exit(None, RuntimeError("boom")) == "error"


# --- Prompt 1.8(a): end-to-end journaling redaction ---------------------------
# Distinct from test_redact_text_covers_valve_secret_and_bearer_and_pattern
# above (Prompt 1.3, unit-tests _redact_text in isolation): this goes through
# the real _journal() write path and inspects the actual persisted JSONL
# line, with a Bearer token AND a vault-shaped secret in the SAME call.

def test_journal_redacts_bearer_token_and_vault_secret_end_to_end(tmp_path, monkeypatch):
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    fake_pfsense_key = "sk-fake-pfsense-9f8e7d6c5b4a"
    secret_values = {fake_pfsense_key}
    bearer_token = "abcXYZ123fakeBearerToken"
    args = {"command": f"curl -H 'Authorization: Bearer {bearer_token}' "
                        f"-d key={fake_pfsense_key} https://pfsense.home.arpa/api"}
    result = f"200 OK — sent Bearer {bearer_token} and key={fake_pfsense_key}"

    gm._journal("execute_command", args, result, None, secret_values)

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    raw = json.dumps(line)

    # Neither raw secret survives anywhere in the persisted line...
    assert bearer_token not in raw
    assert fake_pfsense_key not in raw
    # ...and both redaction markers are present in BOTH the args and the result,
    # since the same two secrets appear in both.
    for field in (line["args_redacted"]["command"], line["result_truncated"]):
        assert "[REDACTED:bearer-token]" in field
        assert "[REDACTED:valve-secret]" in field


def test_journal_redacts_vault_tool_call_entirely(tmp_path, monkeypatch):
    """A call to a vault-secret tool is blanket-redacted (DESIGN.md §4 rule 1)
    — the secret VALUE never has to be named/matched to be caught, unlike the
    valve-value/Bearer paths above."""
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    gm._journal("get_vault_secret", {"name": "pfsense-root"},
                "whatever-the-live-secret-value-actually-is", None, set())

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert line["args_redacted"] == {"name": "[REDACTED:vault-tool-arg]"}
    assert "whatever-the-live-secret-value-actually-is" not in json.dumps(line)


# --- Prompt 1.8(b): 2,000-char result cap enforcement --------------------------

def test_journal_caps_result_at_2000_chars(tmp_path, monkeypatch):
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    long_result = "y" * 5000
    gm._journal("execute_command", {}, long_result, None, set())

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    suffix = "…[truncated]"
    assert len(line["result_truncated"]) == gm.EPISODE_MAX_RESULT_CHARS + len(suffix)
    assert line["result_truncated"].endswith(suffix)
    assert line["result_truncated"].startswith("y" * 100)  # real content survived, not just the marker


def test_journal_does_not_truncate_short_result(tmp_path, monkeypatch):
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    gm._journal("execute_command", {}, "short result", None, set())

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert line["result_truncated"] == "short result"


def test_journal_caps_result_at_exactly_2000_boundary(tmp_path, monkeypatch):
    """A result exactly at the cap must NOT be truncated — the cap is
    "longer than 2000", not "2000 or more" (goethe_mcp.py: `if len(...) >
    EPISODE_MAX_RESULT_CHARS`)."""
    ep_dir = tmp_path / "episodes"
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(ep_dir))
    monkeypatch.setattr(gm, "_DAY_CAP_BYTES", 500 * 1024 * 1024)
    gm._day_size_cache.clear()

    exact_result = "z" * gm.EPISODE_MAX_RESULT_CHARS
    gm._journal("execute_command", {}, exact_result, None, set())

    day = date.today().isoformat()
    files = list((ep_dir / day).glob("*.jsonl"))
    line = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert line["result_truncated"] == exact_result
    assert not line["result_truncated"].endswith("…[truncated]")


# --- Prompt 1.8(c): provenance format validation for debrief/backfill proposals --

def test_backfill_provenance_matches_documented_format():
    text = ("## Session 2026-06-07 — topic\n\n### Key facts\n"
            "- some standalone fact worth capturing here\n")
    entries = dl.parse_entries(text)
    assert len(entries) == 1
    candidates = dl.build_proposals(entries[0])
    assert candidates  # the one Key facts bullet
    proposals = [dl.make_proposal(entries[0], c, i + 1) for i, c in enumerate(candidates)]
    for p in proposals:
        assert dl.is_valid_provenance(p["provenance"], kind="backfill"), p["provenance"]
        assert p["provenance"] == "debrief-backfill-2026-06-07"
        # skill_record actually accepts provenance as a real call arg (unlike
        # index_to_kb — see DESIGN.md §6.2); when present it must match exactly.
        if p["type"] == "skill-candidate":
            assert p["args"]["provenance"] == p["provenance"]


@pytest.mark.parametrize("value,kind,expected", [
    ("debrief-backfill-2026-07-11", "backfill", True),
    ("debrief-backfill-2026-7-11", "backfill", False),      # not zero-padded
    ("debrief-backfill-2026-07-11 ", "backfill", False),    # trailing space
    ("DEBRIEF-BACKFILL-2026-07-11", "backfill", False),     # case-sensitive
    ("debrief 2026-07-11", "live-debrief", True),
    ("debrief-2026-07-11", "live-debrief", False),          # wrong separator (hyphen not space)
    ("debrief  2026-07-11", "live-debrief", False),         # double space
    ("dream-2026-07-11", "dream", True),
    ("dream 2026-07-11", "dream", False),                   # wrong separator (space not hyphen)
    ("debrief-backfill-2026-07-11", "any", True),
    ("debrief 2026-07-11", "any", True),
    ("dream-2026-07-11", "any", True),
    ("random-string", "any", False),
    ("debrief-backfill-2026-07-11", "live-debrief", False),  # cross-kind must not match
])
def test_provenance_format_validator(value, kind, expected):
    assert dl.is_valid_provenance(value, kind=kind) is expected


def test_provenance_validator_rejects_unknown_kind():
    with pytest.raises(ValueError):
        dl.is_valid_provenance("debrief 2026-07-11", kind="not-a-real-kind")


# --- Prompt 1.8(d): journaling failure never raises into the tool call path ---
# Distinct from the day-dir-cap tests above (which exercise _safe_journal
# indirectly via a real _journal call that returns early): this forces
# _journal itself to raise, and asserts the guarantee at the level that
# actually matters — a real tool call wrapped by register(), the same
# wrapper every MCP tool call goes through in production.

class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def add_tool(self, fn, name, description):
        self.tools[name] = fn


class _FakeInstNoValves:
    def method_ok(self, x=1):
        return f"got {x}"

    async def async_method_ok(self, x=1):
        return f"async got {x}"


def _boom_journal(*args, **kwargs):
    raise RuntimeError("simulated journal failure")


def test_journal_failure_never_raises_into_sync_tool_call(monkeypatch, capsys):
    monkeypatch.setattr(gm, "_journal", _boom_journal)

    mcp = _FakeMCP()
    names = gm.register(mcp, _FakeInstNoValves(), set())
    assert "method_ok" in names

    result = asyncio.run(mcp.tools["method_ok"](x=42))
    assert result == "got 42"  # the tool call succeeded despite journaling blowing up

    captured = capsys.readouterr()
    assert "episode journal failed" in captured.err


def test_journal_failure_never_raises_into_async_tool_call(monkeypatch, capsys):
    monkeypatch.setattr(gm, "_journal", _boom_journal)

    mcp = _FakeMCP()
    gm.register(mcp, _FakeInstNoValves(), set())

    result = asyncio.run(mcp.tools["async_method_ok"](x=7))
    assert result == "async got 7"

    captured = capsys.readouterr()
    assert "episode journal failed" in captured.err


def test_tool_exception_still_propagates_after_journaling(monkeypatch):
    """The failure-safety guarantee is one-directional: journaling errors must
    never break the tool call, but the tool's OWN errors must still propagate
    normally — _safe_journal must not accidentally swallow those instead."""
    class _FakeInstRaises:
        def method_raises(self):
            raise ValueError("the tool itself failed, not journaling")

    mcp = _FakeMCP()
    gm.register(mcp, _FakeInstRaises(), set())

    with pytest.raises(ValueError, match="the tool itself failed"):
        asyncio.run(mcp.tools["method_raises"]())
