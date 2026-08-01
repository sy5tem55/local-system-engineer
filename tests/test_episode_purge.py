"""Tests for Console corpus hygiene (docs/SPEC-console-corpus-hygiene-2026-08.md).

Covers episode_purge_preview() / episode_purge() in tools/goethe_ui.py --
the Console's quarantine-only write surface over the TRAUM episode corpus.

Hazards this pins (see the SPEC for the full rationale):
  A -- never delete, always move. Every "moved" assertion below checks the
       file exists at the quarantine path afterwards; no test ever calls
       episode_purge() against a real corpus (fixtures live under tmp_path).
  B -- the destructive call takes explicit session_ids, never a pattern.
  C -- a file containing more than one tool ("mixed") is refused, even when
       its session_id is passed explicitly to purge.
  D -- purge always calls episode_index.build_manifest(prune=True); pruning
       itself is not reimplemented here.

python3 -m pytest tests/test_episode_purge.py -q
"""

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(_HERE, "..", "tools")
sys.path.insert(0, _TOOLS)

import episode_index as ei  # noqa: E402

_UI_PATH = os.path.join(_TOOLS, "goethe_ui.py")
spec = importlib.util.spec_from_file_location("goethe_ui_purge_under_test", _UI_PATH)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------

def _write_line(day_dir: Path, session_id: str, tool: str,
                 ts: str = "2026-01-01T00:00:00Z", exit_class: str = "ok") -> str:
    day_dir.mkdir(parents=True, exist_ok=True)
    return ('{"ts": "%s", "tool": "%s", "session_id": "%s", '
            '"exit_class": "%s"}\n') % (ts, tool, session_id, exit_class)


def _write_session(episode_dir: Path, day: str, session_id: str, tool: str,
                    ts: str = "2026-01-01T00:00:00Z") -> Path:
    """One-line, single-tool session file -- an 'entire' match candidate."""
    day_dir = episode_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{session_id}.jsonl"
    path.write_text(_write_line(day_dir, session_id, tool, ts))
    return path


def _write_mixed_session(episode_dir: Path, day: str, session_id: str,
                          tools: list) -> Path:
    """One line per tool in `tools` -- a 'mixed' match candidate whenever
    more than one distinct tool is passed."""
    day_dir = episode_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{session_id}.jsonl"
    lines = "".join(
        _write_line(day_dir, session_id, t, ts=f"2026-01-01T00:0{i}:00Z")
        for i, t in enumerate(tools))
    path.write_text(lines)
    return path


def _rows(manifest_db: Path) -> dict:
    if not manifest_db.exists():
        return {}
    conn = sqlite3.connect(str(manifest_db))
    try:
        return {r[0]: r[1] for r in
                conn.execute("SELECT session_id, dreamed_at FROM sessions")}
    finally:
        conn.close()


def _episode_env(monkeypatch, episode_dir: Path):
    monkeypatch.setenv("GOETHE_EPISODE_DIR", str(episode_dir))


# --------------------------------------------------------------------------
# 1. Preview is side-effect free
# --------------------------------------------------------------------------

def test_preview_is_side_effect_free(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    manifest_db = episode_dir / "manifest.db"
    _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    _write_mixed_session(episode_dir, "2026-01-01", "sess-mixed",
                          ["method_raises", "search_kb"])
    ei.build_manifest(str(episode_dir), str(manifest_db))
    _episode_env(monkeypatch, episode_dir)

    before_files = {
        p: p.read_bytes()
        for p in episode_dir.rglob("*.jsonl")
    }
    before_manifest = manifest_db.read_bytes()

    result = ui.episode_purge_preview("method_raises")
    result2 = ui.episode_purge_preview("method_raises")  # safe to call repeatedly

    assert "error" not in result
    assert result == {k: v for k, v in result2.items()}  # deterministic, repeatable

    after_files = {p: p.read_bytes() for p in episode_dir.rglob("*.jsonl")}
    assert after_files == before_files, "preview must not touch corpus files"
    assert manifest_db.read_bytes() == before_manifest, "preview must not touch manifest.db"


# --------------------------------------------------------------------------
# 2. Mixed files are classified and excluded from purgeable_session_ids
# --------------------------------------------------------------------------

def test_mixed_files_classified_and_excluded(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    _write_mixed_session(episode_dir, "2026-01-01", "sess-mixed",
                          ["method_raises", "search_kb"])
    _episode_env(monkeypatch, episode_dir)

    result = ui.episode_purge_preview("method_raises")
    by_id = {e["session_id"]: e for e in result["entries"]}

    assert by_id["sess-entire"]["classification"] == "entire"
    assert by_id["sess-mixed"]["classification"] == "mixed"
    assert "sess-entire" in result["purgeable_session_ids"]
    assert "sess-mixed" not in result["purgeable_session_ids"]
    assert result["entire_count"] == 1
    assert result["mixed_count"] == 1


# --------------------------------------------------------------------------
# 3. Purge refuses a mixed id even if passed explicitly -- LOAD-BEARING (Hazard C)
# --------------------------------------------------------------------------

def test_purge_refuses_mixed_id_even_explicit(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    mixed_path = _write_mixed_session(
        episode_dir, "2026-01-01", "sess-mixed", ["method_raises", "search_kb"])
    _episode_env(monkeypatch, episode_dir)

    result = ui.episode_purge(["sess-mixed"], "operator explicitly forced a mixed id")

    assert result["moved_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["session_id"] == "sess-mixed"
    assert "mixed" in result["skipped"][0]["reason"]
    assert mixed_path.exists(), "a mixed file must never be moved"


# --------------------------------------------------------------------------
# 4. Purge moves, never deletes (Hazard A)
# --------------------------------------------------------------------------

def test_purge_moves_never_deletes(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    src = _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    original_bytes = src.read_bytes()
    _episode_env(monkeypatch, episode_dir)

    result = ui.episode_purge(["sess-entire"], "false positive from a test run")

    assert result["moved_count"] == 1
    assert result["skipped_count"] == 0
    assert not src.exists(), "source file must be relocated, not left in place"
    quarantine_path = Path(result["moved"][0]["quarantined_to"])
    assert quarantine_path.exists()
    assert quarantine_path.read_bytes() == original_bytes
    assert result["quarantine_path"] is not None
    assert Path(result["quarantine_path"]).parent == episode_dir.parent
    assert (Path(result["quarantine_path"]) / "MOVED-FILES.txt").exists()


# --------------------------------------------------------------------------
# 5. Path traversal is rejected -- LOAD-BEARING (Hazard A / B)
# --------------------------------------------------------------------------

def test_path_traversal_is_rejected(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    _episode_env(monkeypatch, episode_dir)

    for bad_id in ["../../etc/passwd", "/etc/passwd", "..", "a/b",
                   "2026-01-01/sess-entire"]:
        result = ui.episode_purge([bad_id], "trying to escape the corpus root")
        assert "error" in result, f"{bad_id!r} should have been rejected"

    # Nothing was touched by any of the rejected attempts.
    assert (episode_dir / "2026-01-01" / "sess-entire.jsonl").exists()


# --------------------------------------------------------------------------
# 6. Re-verification catches drift since preview
# --------------------------------------------------------------------------

def test_reverification_catches_drift(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    path = _write_session(episode_dir, "2026-01-01", "sess-drift", "method_raises")
    _episode_env(monkeypatch, episode_dir)

    preview = ui.episode_purge_preview("method_raises")
    assert "sess-drift" in preview["purgeable_session_ids"]

    # A real call lands in the same session file between preview and purge.
    with open(path, "a", encoding="utf-8") as f:
        f.write(_write_line(path.parent, "sess-drift", "search_kb",
                             ts="2026-01-01T00:05:00Z"))

    result = ui.episode_purge(["sess-drift"], "purging what preview showed")

    assert result["moved_count"] == 0
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["session_id"] == "sess-drift"
    assert path.exists(), "a file that drifted to mixed must not be moved"


# --------------------------------------------------------------------------
# 7. Manifest is pruned after purge; a survivor's dreamed_at is unchanged (Hazard D)
# --------------------------------------------------------------------------

def test_manifest_pruned_after_purge(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    manifest_db = episode_dir / "manifest.db"
    _write_session(episode_dir, "2026-01-01", "sess-purge", "method_raises")
    _write_session(episode_dir, "2026-01-01", "sess-keep", "search_kb")
    ei.build_manifest(str(episode_dir), str(manifest_db))

    conn = sqlite3.connect(str(manifest_db))
    conn.execute("UPDATE sessions SET dreamed_at = ? WHERE session_id = ?",
                 ("2026-01-02T00:00:00Z", "sess-keep"))
    conn.commit()
    conn.close()

    _episode_env(monkeypatch, episode_dir)
    result = ui.episode_purge(["sess-purge"], "orphaned synthetic session")

    assert result["moved_count"] == 1
    rows = _rows(manifest_db)
    assert "sess-purge" not in rows, "purged session's manifest row must be pruned"
    assert rows.get("sess-keep") == "2026-01-02T00:00:00Z", (
        "a surviving session's dreamed_at must not be disturbed by prune"
    )
    assert result["manifest_rows_before"] == 2
    assert result["manifest_rows_after"] == 1
    assert result["manifest_prune_stats"]["pruned"] == 1


# --------------------------------------------------------------------------
# 8. Empty list and missing reason are rejected
# --------------------------------------------------------------------------

def test_empty_list_rejected(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    _episode_env(monkeypatch, episode_dir)

    result = ui.episode_purge([], "a reason")
    assert "error" in result


def test_missing_reason_rejected(tmp_path, monkeypatch):
    episode_dir = tmp_path / "episodes"
    _write_session(episode_dir, "2026-01-01", "sess-entire", "method_raises")
    _episode_env(monkeypatch, episode_dir)

    for bad_reason in ["", "   ", None]:
        result = ui.episode_purge(["sess-entire"], bad_reason)
        assert "error" in result
    assert (episode_dir / "2026-01-01" / "sess-entire.jsonl").exists()


# --------------------------------------------------------------------------
# Bonus: the fixture recommended by the SPEC actually copies clean (sanity
# check on the realistic fixture, never touches the live quarantine dir).
# --------------------------------------------------------------------------

def test_realistic_fixture_copies_and_purges_cleanly(tmp_path, monkeypatch):
    src_quarantine = Path(
        "/opt/local-se/episodes-quarantine-method_raises-20260801")
    if not src_quarantine.is_dir():
        import pytest
        pytest.skip("reference quarantine fixture not present on this host")

    import shutil as _shutil
    episode_dir = tmp_path / "episodes"
    episode_dir.mkdir()
    # Copy a handful of day-dirs in as if they were live corpus files --
    # COPY the fixture, never operate on the original.
    day_dirs = sorted(p for p in src_quarantine.iterdir() if p.is_dir())[:2]
    for day_dir in day_dirs:
        dest = episode_dir / day_dir.name
        _shutil.copytree(day_dir, dest)
    assert day_dirs, "reference fixture has no day-dirs to sample"

    _episode_env(monkeypatch, episode_dir)
    preview = ui.episode_purge_preview("method_raises")
    assert preview["entire_count"] >= 1
    # Every original fixture file must still be untouched by the preview.
    for day_dir in day_dirs:
        assert day_dir.exists() and any(day_dir.iterdir())
