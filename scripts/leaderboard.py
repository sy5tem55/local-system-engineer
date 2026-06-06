"""
LeaderboardService — SQLite-backed episode log and points tracker.

Receives result dicts from run_episode() (or equivalent), writes rows to
/opt/local-se/leaderboard.db, and exposes standings / history queries.

Schema
------
episodes(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at     TEXT NOT NULL,        -- ISO-8601 UTC
    challenge_id    TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    outcome         TEXT NOT NULL,        -- SOLVED | ESCALATED | TRUNCATED
    attempts        INTEGER NOT NULL,
    raw_reward      REAL NOT NULL,
    discipline      TEXT NOT NULL,
    discipline_mult REAL NOT NULL,
    final_points    REAL NOT NULL,        -- raw_reward * discipline_mult
    kb_assisted     INTEGER NOT NULL,     -- 0/1
    escalated       INTEGER NOT NULL,     -- 0/1
    esc_quality     TEXT,                 -- good | poor | NULL
    wall_time_s     REAL,
    notes           TEXT                  -- free text, optional
)

standings(view) — cumulative points per model:
    model_id, total_points, episodes_played, solved, escalated, avg_attempts
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = "/opt/local-se/leaderboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at     TEXT    NOT NULL,
    challenge_id    TEXT    NOT NULL,
    model_id        TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,
    attempts        INTEGER NOT NULL,
    raw_reward      REAL    NOT NULL,
    discipline      TEXT    NOT NULL,
    discipline_mult REAL    NOT NULL,
    final_points    REAL    NOT NULL,
    kb_assisted     INTEGER NOT NULL DEFAULT 0,
    escalated       INTEGER NOT NULL DEFAULT 0,
    esc_quality     TEXT,
    wall_time_s     REAL,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_ep_model    ON episodes (model_id);
CREATE INDEX IF NOT EXISTS idx_ep_challenge ON episodes (challenge_id);
CREATE INDEX IF NOT EXISTS idx_ep_outcome  ON episodes (outcome);
"""


class LeaderboardService:
    """
    Lightweight leaderboard backed by SQLite.

    Usage on LUCIFER:
        lb = LeaderboardService()          # default /opt/local-se/leaderboard.db
        lb.record_episode(result_dict)     # result dict from run_episode()
        lb.standings()                     # -> list[dict], sorted by total_points desc
        lb.model_stats("qwen3.6-27b")     # -> dict
        lb.recent_episodes(n=20)          # -> list[dict]
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Write ─────────────────────────────────────────────────────────────────

    def record_episode(self, result: dict, notes: str = "") -> int:
        """
        Insert one episode result.  Returns the new row id.

        Accepts the dict returned by run_episode():
          challenge_id, model_id, outcome, attempts, raw_reward,
          discipline, discipline_multiplier, final_points,
          kb_assisted, escalated, escalation_context_quality, wall_time_s
        """
        raw   = float(result.get("raw_reward", 0.0))
        mult  = float(result.get("discipline_multiplier", 1.0))
        # final_points may already be computed; recompute for safety
        pts   = raw * mult

        row = (
            _now_iso(),
            result.get("challenge_id", "unknown"),
            result.get("model_id",     "unknown"),
            result.get("outcome",      "UNKNOWN"),
            int(result.get("attempts", 0)),
            raw,
            result.get("discipline",   "sysadmin"),
            mult,
            pts,
            1 if result.get("kb_assisted") else 0,
            1 if result.get("escalated")   else 0,
            result.get("escalation_context_quality"),
            result.get("wall_time_s"),
            notes or None,
        )

        con = self._connect()
        try:
            cur = con.execute(
                """INSERT INTO episodes
                   (recorded_at, challenge_id, model_id, outcome, attempts,
                    raw_reward, discipline, discipline_mult, final_points,
                    kb_assisted, escalated, esc_quality, wall_time_s, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

    # ── Read ──────────────────────────────────────────────────────────────────

    def standings(self) -> list[dict]:
        """
        Cumulative leaderboard — one row per model, sorted by total_points desc.
        """
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT
                    model_id,
                    ROUND(SUM(final_points), 2)                     AS total_points,
                    COUNT(*)                                         AS episodes_played,
                    SUM(CASE WHEN outcome = 'SOLVED'    THEN 1 ELSE 0 END) AS solved,
                    SUM(CASE WHEN outcome = 'ESCALATED' THEN 1 ELSE 0 END) AS escalated,
                    SUM(CASE WHEN outcome = 'TRUNCATED' THEN 1 ELSE 0 END) AS truncated,
                    ROUND(AVG(attempts), 2)                          AS avg_attempts,
                    SUM(CASE WHEN kb_assisted = 1 THEN 1 ELSE 0 END) AS kb_hits
                FROM episodes
                GROUP BY model_id
                ORDER BY total_points DESC
            """).fetchall()
            cols = ["model_id","total_points","episodes_played","solved",
                    "escalated","truncated","avg_attempts","kb_hits"]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            con.close()

    def model_stats(self, model_id: str) -> Optional[dict]:
        """Per-discipline breakdown for one model."""
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT
                    discipline,
                    ROUND(SUM(final_points), 2)  AS discipline_points,
                    COUNT(*)                      AS episodes,
                    SUM(CASE WHEN outcome='SOLVED' THEN 1 ELSE 0 END) AS solved,
                    ROUND(AVG(attempts), 2)       AS avg_attempts
                FROM episodes
                WHERE model_id = ?
                GROUP BY discipline
                ORDER BY discipline_points DESC
            """, (model_id,)).fetchall()

            if not rows:
                return None

            cols = ["discipline","discipline_points","episodes","solved","avg_attempts"]
            return {
                "model_id": model_id,
                "by_discipline": [dict(zip(cols, r)) for r in rows],
            }
        finally:
            con.close()

    def recent_episodes(self, n: int = 20, model_id: Optional[str] = None) -> list[dict]:
        """Most recent N episodes, optionally filtered by model."""
        con = self._connect()
        try:
            if model_id:
                rows = con.execute("""
                    SELECT id, recorded_at, challenge_id, model_id, outcome,
                           attempts, raw_reward, discipline_mult, final_points,
                           kb_assisted, escalated, wall_time_s
                    FROM episodes WHERE model_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (model_id, n)).fetchall()
            else:
                rows = con.execute("""
                    SELECT id, recorded_at, challenge_id, model_id, outcome,
                           attempts, raw_reward, discipline_mult, final_points,
                           kb_assisted, escalated, wall_time_s
                    FROM episodes
                    ORDER BY id DESC LIMIT ?
                """, (n,)).fetchall()

            cols = ["id","recorded_at","challenge_id","model_id","outcome",
                    "attempts","raw_reward","discipline_mult","final_points",
                    "kb_assisted","escalated","wall_time_s"]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            con.close()

    def challenge_history(self, challenge_id: str) -> list[dict]:
        """All episodes for a specific challenge, oldest first."""
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT id, recorded_at, model_id, outcome, attempts,
                       final_points, kb_assisted, escalated, wall_time_s
                FROM episodes WHERE challenge_id = ?
                ORDER BY id ASC
            """, (challenge_id,)).fetchall()
            cols = ["id","recorded_at","model_id","outcome","attempts",
                    "final_points","kb_assisted","escalated","wall_time_s"]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            con.close()

    def print_standings(self):
        """Pretty-print the leaderboard to stdout."""
        rows = self.standings()
        if not rows:
            print("  (no episodes recorded yet)")
            return
        header = f"  {'Model':<22} {'Points':>8}  {'Eps':>4}  {'Solved':>6}  " \
                 f"{'Esc':>4}  {'Avg att':>7}  {'KB hits':>7}"
        print(f"\n{'─'*len(header)}")
        print(header)
        print(f"{'─'*len(header)}")
        for r in rows:
            print(
                f"  {r['model_id']:<22} {r['total_points']:>8.1f}  "
                f"{r['episodes_played']:>4}  {r['solved']:>6}  "
                f"{r['escalated']:>4}  {r['avg_attempts']:>7.2f}  "
                f"{r['kb_hits']:>7}"
            )
        print(f"{'─'*len(header)}\n")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _init_schema(self):
        con = self._connect()
        try:
            con.executescript(SCHEMA)
            con.commit()
        finally:
            con.close()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL")
        return con


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
