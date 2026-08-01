#!/usr/bin/env python3
"""
episode_index.py — manifest + rotation for the TRAUM episode corpus.
=============================================================================
Companion to goethe_mcp.py's episode journaling (v1.10.0+, TRAUM Thread 1,
docs/dreaming/DESIGN.md). goethe_mcp.py writes one JSONL line per tool call to
$EPISODE_DIR/YYYY-MM-DD/<session>.jsonl. This script is the periodic
maintenance pass over that corpus:

  1. MANIFEST — scan every session file (.jsonl or already-rotated .jsonl.gz),
     summarize it into one row of $EPISODE_DIR/manifest.db (SQLite), so
     Thread 2's dream_runner.py can do `WHERE dreamed_at IS NULL` instead of
     re-parsing the whole corpus on every dream run.
  2. ROTATION — gzip session files in day-dirs older than --rotate-days (7),
     to keep the corpus from growing unbounded on disk.

It does NOT enforce the 500MB day-dir write cap — that's a write-time gate
and lives in goethe_mcp.py's _journal() (checked before every append, since
this script only runs periodically and a day could blow past the cap between
runs). This script is the read-side/rotation half of "size hygiene"; the
refuse-to-journal half is the write-side half.

USAGE
  # One-shot manifest build + rotation (what a systemd timer would run)
  python3 episode_index.py

  # Just report what would happen, touch nothing
  python3 episode_index.py --dry-run

  # Point at a non-default corpus (e.g. for testing)
  python3 episode_index.py --episode-dir /tmp/some-episodes

ENV
  GOETHE_EPISODE_DIR   same variable goethe_mcp.py reads; default matches it
                       (/opt/local-se/episodes) so the two tools agree on the
                       corpus location without separate configuration.

MANIFEST SCHEMA (sessions table in manifest.db)
  session_id   TEXT PRIMARY KEY  — from the filename (also cross-checked
                                    against each line's own session_id field)
  start_ts     TEXT              — min(ts) across the session's lines
  end_ts       TEXT              — max(ts) across the session's lines
  n_calls      INTEGER           — total journaled lines (one per tool call)
  n_errors     INTEGER           — lines with exit_class in (error, timeout)
                                    ("denied" is a gate working as intended,
                                    not counted as an error — see _is_error())
  tools_used   TEXT              — JSON array, sorted, de-duplicated tool names
  bytes        TEXT              — on-disk size of the session file at scan
                                    time (post-rotation size if gzipped)
  dreamed_at   TEXT NULL         — set by Thread 2's dream_apply.py, never by
                                    this script; re-scanning an already-dreamed
                                    session preserves it (UPSERT, not REPLACE)

Empty or fully-unparseable session files are skipped (no manifest row) —
there's nothing for a dream to read, and it would just be a permanent
`dreamed_at IS NULL` row a dream_runner pass could never do anything with.
"""

import argparse
import gzip
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime

__version__ = "1.1.0"
# 1.0.0 — initial release (TRAUM Thread 1, Prompt 1.4).
# 1.1.0 — build_manifest() gains opt-in prune=False param (default off,
#         existing callers unaffected) that removes manifest rows whose
#         backing session file no longer exists. See
#         docs/SPEC-manifest-prune-2026-08.md for the two hazards this
#         guards against (dreamed_at reset on re-insert; a partial scan
#         being mistaken for "everything else is orphaned").

DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SESSION_FILE_RE = re.compile(r"^(?P<session_id>.+)\.jsonl(?P<gz>\.gz)?$")

DEFAULT_ROTATE_DAYS = 7

# exit_class values that count as n_errors. "denied" (a gate refusal, e.g.
# BLOCKED: ...) is deliberately excluded — that's the safety system working,
# not a failure worth surfacing to the error-cluster dream pass the same way
# a genuine error or timeout is (plan Thread 2, Prompt 2.4).
_ERROR_EXIT_CLASSES = {"error", "timeout"}


def _episode_dir_default() -> str:
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _open_session_file(path: str):
    """Open a session file for text reading, transparently handling .gz."""
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


def parse_session_file(path: str, verbose: bool = False) -> dict | None:
    """Parse one session JSONL(.gz) file into a manifest row dict, or None if
    the file has no usable lines (empty, or every line fails to parse).

    Malformed individual lines (partial writes from a concurrently-appending
    gateway, truncated trailing line mid-write) are skipped, not fatal — the
    rest of the file is still summarized.
    """
    m = SESSION_FILE_RE.match(os.path.basename(path))
    if not m:
        return None
    session_id = m.group("session_id")

    n_calls = 0
    n_errors = 0
    tools = set()
    timestamps = []
    n_bad_lines = 0

    try:
        with _open_session_file(path) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    n_bad_lines += 1
                    if verbose:
                        print(f"[episode_index] {path}:{lineno}: unparseable line, skipped",
                              file=sys.stderr)
                    continue
                if not isinstance(obj, dict):
                    n_bad_lines += 1
                    continue

                n_calls += 1
                ts = obj.get("ts")
                if isinstance(ts, str):
                    timestamps.append(ts)
                tool = obj.get("tool")
                if isinstance(tool, str):
                    tools.add(tool)
                if obj.get("exit_class") in _ERROR_EXIT_CLASSES:
                    n_errors += 1
    except OSError as e:
        print(f"[episode_index] WARNING: could not read {path}: {e}", file=sys.stderr)
        return None

    if n_calls == 0:
        if verbose:
            print(f"[episode_index] {path}: no usable lines, skipped ({n_bad_lines} bad)",
                  file=sys.stderr)
        return None

    # ISO-8601 timestamps sort correctly as plain strings (fixed-width,
    # zero-padded, consistent offset format from goethe_mcp.py's _iso_now()).
    timestamps.sort()
    start_ts = timestamps[0]
    end_ts = timestamps[-1]

    try:
        size_bytes = os.path.getsize(path)
    except OSError:
        size_bytes = 0

    return {
        "session_id": session_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "n_calls": n_calls,
        "n_errors": n_errors,
        "tools_used": json.dumps(sorted(tools)),
        "bytes": size_bytes,
    }


def iter_day_dirs(episode_dir: str):
    """Yield (date_str, full_path) for each YYYY-MM-DD subdirectory, sorted
    oldest-first."""
    if not os.path.isdir(episode_dir):
        return
    for name in sorted(os.listdir(episode_dir)):
        if DAY_DIR_RE.match(name):
            full = os.path.join(episode_dir, name)
            if os.path.isdir(full):
                yield name, full


def iter_session_files(day_dir: str):
    """Yield full paths to session files (.jsonl or .jsonl.gz) in a day-dir."""
    for name in sorted(os.listdir(day_dir)):
        if name.endswith(".jsonl") or name.endswith(".jsonl.gz"):
            yield os.path.join(day_dir, name)


# --- manifest.db -------------------------------------------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            start_ts    TEXT NOT NULL,
            end_ts      TEXT NOT NULL,
            n_calls     INTEGER NOT NULL,
            n_errors    INTEGER NOT NULL,
            tools_used  TEXT NOT NULL,
            bytes       INTEGER NOT NULL,
            dreamed_at  TEXT
        )
        """
    )
    conn.commit()


def upsert_session(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or refresh a session's stats WITHOUT disturbing dreamed_at —
    Thread 2's dream_apply.py is the only writer of that column. A re-scan
    (e.g. a session file that grew since the last run) must never silently
    reset a session back to 'undreamed'."""
    conn.execute(
        """
        INSERT INTO sessions (session_id, start_ts, end_ts, n_calls, n_errors, tools_used, bytes, dreamed_at)
        VALUES (:session_id, :start_ts, :end_ts, :n_calls, :n_errors, :tools_used, :bytes, NULL)
        ON CONFLICT(session_id) DO UPDATE SET
            start_ts   = excluded.start_ts,
            end_ts     = excluded.end_ts,
            n_calls    = excluded.n_calls,
            n_errors   = excluded.n_errors,
            tools_used = excluded.tools_used,
            bytes      = excluded.bytes
        """,
        row,
    )


def _session_file_exists(episode_dir: str, session_id: str) -> bool:
    """Check whether a backing file for session_id still exists anywhere
    under episode_dir, as either .jsonl or .jsonl.gz, in any day dir.

    Used by build_manifest's prune path for its per-row orphan check. This
    is deliberately a direct filesystem existence check keyed on session_id
    — not a lookup against whatever this scan happened to enumerate — so
    that a file which exists but is empty/unparseable (parse_session_file
    returns None for it, so it never makes it into `rows`) is correctly
    treated as NOT orphaned. Set-difference against `rows` alone cannot make
    that distinction, and collapsing it would delete a row for a file that
    is still sitting right there on disk.
    """
    for _day, day_dir in iter_day_dirs(episode_dir):
        jsonl = os.path.join(day_dir, f"{session_id}.jsonl")
        if os.path.exists(jsonl) or os.path.exists(jsonl + ".gz"):
            return True
    return False


def _existing_session_ids(manifest_db: str) -> set:
    """Read the session_ids currently in manifest_db without creating the
    file (or its schema) if it doesn't already exist. Needed so the
    dry_run=True prune-preview path can report what it WOULD prune without
    the side effect of materializing an empty manifest.db just by asking."""
    if not os.path.exists(manifest_db):
        return set()
    conn = sqlite3.connect(manifest_db, timeout=10)
    try:
        return {r[0] for r in conn.execute("SELECT session_id FROM sessions")}
    except sqlite3.OperationalError:
        # File exists but has no sessions table yet (e.g. 0-byte or
        # freshly-touched) — nothing to prune against.
        return set()
    finally:
        conn.close()


def build_manifest(episode_dir: str, manifest_db: str, dry_run: bool = False,
                    verbose: bool = False, prune: bool = False) -> dict:
    """Scan every session file under episode_dir and upsert manifest.db.
    Returns a summary dict for logging/tests.

    prune=False (the default) is byte-for-byte the original behaviour: scan,
    upsert, never delete. Existing callers that don't pass `prune` are
    unaffected — this includes dream_runner's guard-time refresh call, which
    deliberately keeps calling this with prune's default (see
    docs/SPEC-manifest-prune-2026-08.md §4.3).

    prune=True additionally removes manifest rows whose backing session file
    no longer exists anywhere under episode_dir, subject to two guarantees
    (docs/SPEC-manifest-prune-2026-08.md §3):

      Hazard A — a surviving row's dreamed_at is never touched by a prune.
      Rows for session_ids seen in this scan go through the normal
      upsert_session() ON CONFLICT path, which already preserves
      dreamed_at; pruning only ever considers session_ids that are NOT in
      this scan's live set, so a survivor is never even a delete candidate.

      Hazard B — pruning only proceeds after a *provably complete* scan. If
      any exception escapes the scan loop, or no day dirs were found at
      all, pruning is skipped entirely and `prune_skipped_reason` records
      why. An interrupted or partial scan must never be treated as
      "everything else is orphaned" — that is exactly the shape of bug that
      would silently delete unrecoverable dreamed_at state.

    Even once pruning proceeds, a candidate row (a manifest session_id not
    seen in this scan) is only actually deleted after an explicit
    filesystem check confirms no backing .jsonl or .jsonl.gz exists for
    that session_id in ANY day dir — not by trusting set-difference against
    the scan alone. See _session_file_exists().
    """
    stats = {"scanned": 0, "written": 0, "skipped_empty": 0, "day_dirs": 0,
              "pruned": 0, "prune_skipped_reason": None}

    rows = []
    scan_complete = True
    scan_error = None
    try:
        for day, day_dir in iter_day_dirs(episode_dir):
            stats["day_dirs"] += 1
            for path in iter_session_files(day_dir):
                stats["scanned"] += 1
                row = parse_session_file(path, verbose=verbose)
                if row is None:
                    stats["skipped_empty"] += 1
                    continue
                rows.append(row)
    except Exception as exc:
        if not prune:
            # prune=False must be byte-for-byte identical to the original
            # behaviour: an exception here always propagated out of
            # build_manifest, so it still does.
            raise
        scan_complete = False
        scan_error = exc

    pruned_ids = []
    if prune:
        if not scan_complete:
            stats["prune_skipped_reason"] = (
                f"scan did not complete ({scan_error!r}); corpus may be "
                "incompletely enumerated, refusing to prune"
            )
        elif stats["day_dirs"] == 0:
            stats["prune_skipped_reason"] = (
                "no day dirs found under episode_dir; refusing to prune an "
                "apparently-empty corpus"
            )
        else:
            seen_ids = {row["session_id"] for row in rows}
            candidates = _existing_session_ids(manifest_db) - seen_ids
            for session_id in sorted(candidates):
                if not _session_file_exists(episode_dir, session_id):
                    pruned_ids.append(session_id)

    if dry_run:
        stats["written"] = len(rows)
        stats["pruned"] = len(pruned_ids)
        return stats

    os.makedirs(os.path.dirname(manifest_db) or ".", exist_ok=True)
    conn = sqlite3.connect(manifest_db, timeout=10)
    try:
        ensure_schema(conn)
        for row in rows:
            upsert_session(conn, row)
        for session_id in pruned_ids:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
    stats["written"] = len(rows)
    stats["pruned"] = len(pruned_ids)
    return stats


# --- rotation ------------------------------------------------------------

def _day_dir_age_days(day_str: str, today: date = None) -> int:
    today = today or date.today()
    try:
        d = datetime.strptime(day_str, "%Y-%m-%d").date()
    except ValueError:
        return -1
    return (today - d).days


def rotate_old_sessions(episode_dir: str, older_than_days: int = DEFAULT_ROTATE_DAYS,
                         dry_run: bool = False, verbose: bool = False) -> list:
    """Gzip every .jsonl file in a day-dir older than older_than_days. Already
    -.gz files are left alone. Returns the list of paths rotated (pre-gzip
    names) for logging/tests."""
    rotated = []
    for day, day_dir in iter_day_dirs(episode_dir):
        if _day_dir_age_days(day) <= older_than_days:
            continue
        for name in sorted(os.listdir(day_dir)):
            if not name.endswith(".jsonl"):
                continue
            src = os.path.join(day_dir, name)
            dst = src + ".gz"
            if os.path.exists(dst):
                # Already rotated in a prior run but the original wasn't removed
                # (e.g. a crash mid-rotation) — clean up the stale original.
                os.remove(src)
                continue
            if dry_run:
                rotated.append(src)
                continue
            try:
                with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(src)
                rotated.append(src)
                if verbose:
                    print(f"[episode_index] rotated {src} -> {dst}", file=sys.stderr)
            except OSError as e:
                print(f"[episode_index] WARNING: rotation failed for {src}: {e}", file=sys.stderr)
    return rotated


def main():
    ap = argparse.ArgumentParser(description="TRAUM episode manifest + rotation.")
    ap.add_argument("--episode-dir", default=_episode_dir_default(),
                    help="root of the episode corpus (default: $GOETHE_EPISODE_DIR "
                    "or /opt/local-se/episodes)")
    ap.add_argument("--manifest-db", default=None,
                    help="path to manifest.db (default: <episode-dir>/manifest.db)")
    ap.add_argument("--rotate-days", type=int, default=DEFAULT_ROTATE_DAYS,
                    help=f"gzip day-dirs older than this many days (default: {DEFAULT_ROTATE_DAYS})")
    ap.add_argument("--no-rotate", action="store_true", help="skip rotation, manifest only")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen, write/gzip nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    manifest_db = args.manifest_db or os.path.join(args.episode_dir, "manifest.db")

    if not os.path.isdir(args.episode_dir):
        print(f"[episode_index] episode dir does not exist yet: {args.episode_dir} "
              "(nothing to do)", file=sys.stderr)
        return

    rotated = []
    if not args.no_rotate:
        rotated = rotate_old_sessions(args.episode_dir, args.rotate_days,
                                       dry_run=args.dry_run, verbose=args.verbose)

    stats = build_manifest(args.episode_dir, manifest_db, dry_run=args.dry_run,
                            verbose=args.verbose)

    mode = "[dry-run] " if args.dry_run else ""
    print(f"[episode_index] {mode}day-dirs={stats['day_dirs']} "
          f"scanned={stats['scanned']} manifest-rows-written={stats['written']} "
          f"skipped-empty={stats['skipped_empty']} rotated={len(rotated)} "
          f"-> {manifest_db}", file=sys.stderr)


if __name__ == "__main__":
    main()
