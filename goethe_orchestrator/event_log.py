"""goethe_orchestrator.event_log — task state-transition journal (ADR-ORCH-001).

The ledger (tasks.db) is the task-of-record for planner work. This is the
orchestrator's own append-only journal: one row per status transition of a
task envelope, so the event log (Phase 5) can answer "what happened to
envelope X, on which worker, when" without touching the ledger.

Storage: SQLite, WAL mode, one connection per EventLog instance. The default
path is /opt/local-se/orch-event-log.db; override with GOETHE_ORCH_EVENT_LOG.

record() NEVER raises into the dispatch path — a journal failure prints a
WARNING to stderr and the transition proceeds. The journal is observability,
not a correctness dependency.
"""

import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = "/opt/local-se/orch-event-log.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    """Append-only SQLite journal of envelope status transitions."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = (
            db_path
            or os.environ.get("GOETHE_ORCH_EVENT_LOG", "").strip()
            or DEFAULT_DB_PATH
        )
        self._lock = threading.Lock()
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS events (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       ts          TEXT NOT NULL,
                       envelope_id TEXT NOT NULL,
                       worker_id   TEXT,
                       from_status TEXT,
                       to_status   TEXT NOT NULL,
                       backend     TEXT,
                       detail      TEXT
                   )"""
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_envelope "
                "ON events(envelope_id)"
            )
            self._conn.commit()

    def record(
        self,
        envelope_id: str,
        to_status: str,
        worker_id: Optional[str] = None,
        from_status: Optional[str] = None,
        backend: Optional[str] = None,
        detail: str = "",
    ) -> None:
        """Append one transition row. Never raises (journal is best-effort)."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO events (ts, envelope_id, worker_id, from_status,"
                    " to_status, backend, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (_utcnow_iso(), envelope_id, worker_id, from_status,
                     to_status, backend, detail),
                )
                self._conn.commit()
        except Exception as e:  # noqa: BLE001 — observability must not break dispatch
            print(f"[goethe_orchestrator.event_log] WARNING: record failed "
                  f"({type(e).__name__}: {e})", file=sys.stderr)

    def events_for(self, envelope_id: str) -> List[Dict[str, Any]]:
        """All transitions for one envelope, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, envelope_id, worker_id, from_status, to_status,"
                " backend, detail FROM events WHERE envelope_id = ? ORDER BY id",
                (envelope_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        """The most recent n transitions, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, envelope_id, worker_id, from_status, to_status,"
                " backend, detail FROM events ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
