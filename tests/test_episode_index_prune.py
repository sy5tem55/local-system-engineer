"""
Tests for the manifest orphan-prune fix (docs/SPEC-manifest-prune-2026-08.md).

build_manifest() in tools/episode_index.py never removed manifest rows for
session files that no longer exist on disk. This adds an opt-in prune=True
path and pins two hazards:

  Hazard A -- dreamed_at is how dream_runner avoids re-analysing a session.
  A prune must never reset a surviving row's dreamed_at back to NULL, and a
  session_id that is re-inserted after being pruned must come back as a
  genuinely fresh (NULL) row, never silently resurrected with stale state.

  Hazard B -- a prune must only run after a *provably complete* scan. Naive
  set-difference-against-the-scan treats an interrupted/partial scan the same
  as "everything else is orphaned", which would delete legitimate history
  (including unrecoverable dreamed_at state) the moment a day-dir read hiccups.

python3 -m pytest tests/test_episode_index_prune.py -q
"""

import gzip
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import episode_index as ei  # noqa: E402


def _write_session(day_dir: Path, session_id: str, ts: str = "2026-01-01T00:00:00Z",
                    tool: str = "read_file", gz: bool = False) -> Path:
    """Write a minimal one-line session file. Returns the path written."""
    day_dir.mkdir(parents=True, exist_ok=True)
    line = (
        '{"ts": "%s", "tool": "%s", "session_id": "%s", "exit_class": "ok"}\n'
        % (ts, tool, session_id)
    )
    if gz:
        path = day_dir / f"{session_id}.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(line)
    else:
        path = day_dir / f"{session_id}.jsonl"
        path.write_text(line)
    return path


def _dreamed_at(manifest_db: Path, session_id: str):
    conn = sqlite3.connect(str(manifest_db))
    try:
        row = conn.execute(
            "SELECT dreamed_at FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _session_ids(manifest_db: Path) -> set:
    conn = sqlite3.connect(str(manifest_db))
    try:
        return {r[0] for r in conn.execute("SELECT session_id FROM sessions")}
    finally:
        conn.close()


class TestPruneDreamedAtSurvives:
    """Hazard A -- the load-bearing test. Written FIRST, before the prune
    implementation existed, per SPEC §5.3 / §5 preamble ('Write it first')."""

    def test_dreamed_at_survives_a_prune(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        _write_session(day_dir, "sess-survivor")
        victim_path = _write_session(day_dir, "sess-victim")

        # Initial scan: both rows created, dreamed_at NULL on both.
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _dreamed_at(manifest_db, "sess-survivor") is None
        assert _dreamed_at(manifest_db, "sess-victim") is None

        # Simulate dream_apply.py having already dreamed the survivor.
        conn = sqlite3.connect(str(manifest_db))
        conn.execute(
            "UPDATE sessions SET dreamed_at = ? WHERE session_id = ?",
            ("2026-01-02T00:00:00Z", "sess-survivor"),
        )
        conn.commit()
        conn.close()
        assert _dreamed_at(manifest_db, "sess-survivor") == "2026-01-02T00:00:00Z"

        # Remove the victim's backing file and prune.
        victim_path.unlink()
        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["pruned"] == 1
        assert stats["prune_skipped_reason"] is None
        assert _dreamed_at(manifest_db, "sess-survivor") == "2026-01-02T00:00:00Z", (
            "prune must not disturb dreamed_at on a surviving row"
        )
        assert _session_ids(manifest_db) == {"sess-survivor"}

    def test_pruned_session_reinserted_later_comes_back_null(self, tmp_path):
        """A pruned row must not be silently resurrected with stale
        dreamed_at if the same session_id is ever seen again -- it must
        read back as a genuinely fresh (NULL) row, per the spec's framing
        of what a *wrong* prune would produce."""
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        path = _write_session(day_dir, "sess-a")
        ei.build_manifest(str(episode_dir), str(manifest_db))

        conn = sqlite3.connect(str(manifest_db))
        conn.execute(
            "UPDATE sessions SET dreamed_at = ? WHERE session_id = ?",
            ("2026-01-02T00:00:00Z", "sess-a"),
        )
        conn.commit()
        conn.close()

        path.unlink()
        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)
        assert stats["pruned"] == 1
        assert _session_ids(manifest_db) == set()

        # File comes back (e.g. a mistaken delete, restored from backup).
        _write_session(day_dir, "sess-a")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _dreamed_at(manifest_db, "sess-a") is None


class TestPruneDefaultInert:
    """SPEC §5.1 -- prune=False (and the current 4-arg call shape) leaves
    orphaned rows in place. Pins backwards compatibility for existing
    callers, including the 4-arg call dream_runner's guard-time refresh
    uses today."""

    def test_default_prune_false_leaves_orphan_in_place(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        victim_path = _write_session(day_dir, "sess-a")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _session_ids(manifest_db) == {"sess-a"}

        victim_path.unlink()
        # 4-arg call shape (episode_dir, manifest_db, dry_run, verbose) --
        # exactly what existing callers use, no `prune` kwarg at all.
        stats = ei.build_manifest(str(episode_dir), str(manifest_db), False, False)

        assert stats.get("pruned", 0) == 0
        assert _session_ids(manifest_db) == {"sess-a"}, (
            "orphan must survive when prune is not requested"
        )

    def test_prune_kwarg_defaults_to_false(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        victim_path = _write_session(day_dir, "sess-a")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        victim_path.unlink()

        stats = ei.build_manifest(str(episode_dir), str(manifest_db))
        assert stats["pruned"] == 0
        assert _session_ids(manifest_db) == {"sess-a"}


class TestPruneRemovesOrphans:
    """SPEC §5.2 -- two session files, both indexed; delete one file from
    disk; build_manifest(prune=True) removes exactly that row and leaves
    the other."""

    def test_orphan_removed_survivor_kept(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        keep_path = _write_session(day_dir, "sess-keep")
        gone_path = _write_session(day_dir, "sess-gone")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _session_ids(manifest_db) == {"sess-keep", "sess-gone"}

        gone_path.unlink()
        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["pruned"] == 1
        assert stats["prune_skipped_reason"] is None
        assert _session_ids(manifest_db) == {"sess-keep"}
        assert keep_path.exists()


class TestPruneGzipRotationSafe:
    """SPEC §5.4 -- gzipped (rotated) files are not orphans. rotate_old_sessions
    renames x.jsonl -> x.jsonl.gz in place; a prune must not treat that as a
    deletion, or it would silently delete the oldest history first."""

    def test_rotated_session_survives_prune(self, tmp_path):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        jsonl_path = _write_session(day_dir, "sess-old")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _session_ids(manifest_db) == {"sess-old"}

        # Simulate what rotate_old_sessions() does: gzip in place, remove
        # the original .jsonl.
        gz_path = day_dir / "sess-old.jsonl.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f_out:
            f_out.write(jsonl_path.read_text())
        jsonl_path.unlink()

        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["pruned"] == 0
        assert _session_ids(manifest_db) == {"sess-old"}, (
            "a rotated (.jsonl -> .jsonl.gz) session must not be pruned"
        )


class TestPruneIncompleteScan:
    """SPEC §5.5 -- Hazard B. Simulate a scan failure (monkeypatch
    iter_day_dirs or iter_session_files to raise) and assert nothing is
    deleted and prune_skipped_reason is set."""

    def test_iter_session_files_raising_skips_prune(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        survivor_path = _write_session(day_dir, "sess-survivor")
        other_path = _write_session(day_dir, "sess-other")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _session_ids(manifest_db) == {"sess-survivor", "sess-other"}

        # Remove one file for real, so a naive set-difference implementation
        # would (correctly) want to prune it -- but the scan itself is about
        # to fail, so nothing should be pruned regardless.
        other_path.unlink()

        def _boom(_day_dir):
            raise OSError("simulated permission error mid-scan")
            yield  # pragma: no cover -- make this a generator function

        monkeypatch.setattr(ei, "iter_session_files", _boom)

        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["pruned"] == 0
        assert stats["prune_skipped_reason"] is not None
        assert _session_ids(manifest_db) == {"sess-survivor", "sess-other"}, (
            "an interrupted scan must never be treated as everything-else-is-orphaned"
        )
        assert survivor_path.exists() and not other_path.exists()

    def test_iter_day_dirs_raising_skips_prune(self, tmp_path, monkeypatch):
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"

        _write_session(day_dir, "sess-a")
        ei.build_manifest(str(episode_dir), str(manifest_db))
        assert _session_ids(manifest_db) == {"sess-a"}

        def _boom(_episode_dir):
            raise OSError("simulated mount hiccup")
            yield  # pragma: no cover

        monkeypatch.setattr(ei, "iter_day_dirs", _boom)

        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["pruned"] == 0
        assert stats["prune_skipped_reason"] is not None
        assert _session_ids(manifest_db) == {"sess-a"}

    def test_prune_false_still_propagates_scan_exception(self, tmp_path, monkeypatch):
        """The exception-catching added for the prune path must not change
        prune=False's behaviour -- an exception must still propagate exactly
        like it always did."""
        episode_dir = tmp_path / "episodes"
        day_dir = episode_dir / "2026-01-01"
        manifest_db = episode_dir / "manifest.db"
        _write_session(day_dir, "sess-a")

        def _boom(_day_dir):
            raise OSError("simulated permission error mid-scan")
            yield  # pragma: no cover

        monkeypatch.setattr(ei, "iter_session_files", _boom)

        with pytest.raises(OSError):
            ei.build_manifest(str(episode_dir), str(manifest_db))


class TestPruneEmptyCorpus:
    """SPEC §5.6 -- point at a directory with no day dirs and assert the
    manifest is untouched."""

    def test_no_day_dirs_skips_prune(self, tmp_path):
        episode_dir = tmp_path / "episodes-empty"
        episode_dir.mkdir()
        manifest_db = episode_dir / "manifest.db"

        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["day_dirs"] == 0
        assert stats["pruned"] == 0
        assert stats["prune_skipped_reason"] is not None

    def test_nonexistent_episode_dir_skips_prune(self, tmp_path):
        episode_dir = tmp_path / "does-not-exist"
        manifest_db = tmp_path / "manifest.db"

        stats = ei.build_manifest(str(episode_dir), str(manifest_db), prune=True)

        assert stats["day_dirs"] == 0
        assert stats["pruned"] == 0
        assert stats["prune_skipped_reason"] is not None
