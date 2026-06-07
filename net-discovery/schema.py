"""
schema.py — SQLite persistence layer for Network Observability
Database: net-discovery/db/netobs.db

7 tables (sqlite_sequence is auto-managed by SQLite for AUTOINCREMENT):
  hosts           — canonical device registry, MAC as natural key
  ip_assignments  — IP ↔ MAC mappings with subnet and timestamps
  ping_history    — ICMP probe results time-series
  mdns_records    — mDNS / Zeroconf service discovery results
  wifi_clients    — WiFi client metadata snapshots
  events          — state-change events (device up/down, new device)
  sqlite_sequence — SQLite internal (AUTOINCREMENT support)

Usage as module:
  from schema import Database
  db = Database()            # uses default path from config
  db = Database("db/netobs.db")

  db.upsert_host(mac, hostname, vendor)
  db.upsert_ip(mac, ip, subnet)
  db.record_ping(ip, alive, rtt_ms)
  db.record_wifi(mac, ap_id, ssid, band, rssi_dbm, tx_rate, rx_rate)
  db.record_event(ip, mac, event_type, detail)
  db.upsert_mdns(ip, service_type, service_name, port, txt)

  devices = db.get_current_devices()   # list[dict] — one row per current IP
  history = db.get_ping_history(ip, limit=100)

Standalone:
  python3 schema.py --init           # create schema only
  python3 schema.py --dump           # dump all table counts as JSON
  python3 schema.py --path db/alt.db # override path

NTFS NOTE: db/ directory is gitignored. Create it before first use:
  mkdir -p net-discovery/db
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

log = logging.getLogger("netobs.schema")

DEFAULT_DB_PATH = Path(__file__).parent / "db" / "netobs.db"

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Canonical device registry — one row per unique MAC address.
-- hostname and vendor may be updated on each probe cycle.
CREATE TABLE IF NOT EXISTS hosts (
    mac          TEXT PRIMARY KEY,
    hostname     TEXT,
    vendor       TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    notes        TEXT DEFAULT ''
);

-- IP to MAC assignments (DHCP leases + static).
-- A host can have multiple IPs over time.
CREATE TABLE IF NOT EXISTS ip_assignments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mac          TEXT NOT NULL REFERENCES hosts(mac) ON DELETE CASCADE,
    ip           TEXT NOT NULL,
    subnet       TEXT NOT NULL,
    binding_type TEXT DEFAULT 'dynamic',
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE(mac, ip)
);
CREATE INDEX IF NOT EXISTS idx_ip_assignments_ip ON ip_assignments(ip);

-- ICMP probe history — one row per probe per IP.
CREATE TABLE IF NOT EXISTS ping_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ip         TEXT NOT NULL,
    alive      INTEGER NOT NULL,
    rtt_ms     REAL,
    probed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ping_history_ip_time ON ping_history(ip, probed_at);

-- mDNS / Zeroconf service records.
CREATE TABLE IF NOT EXISTS mdns_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ip           TEXT NOT NULL,
    service_type TEXT NOT NULL,
    service_name TEXT,
    port         INTEGER,
    txt          TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE(ip, service_type, service_name)
);
CREATE INDEX IF NOT EXISTS idx_mdns_ip ON mdns_records(ip);

-- WiFi client metadata snapshots — one row per (mac, ap) pair.
CREATE TABLE IF NOT EXISTS wifi_clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mac         TEXT NOT NULL,
    ap_id       TEXT NOT NULL,
    ssid        TEXT,
    band        TEXT,
    rssi_dbm    INTEGER,
    tx_rate     INTEGER,
    rx_rate     INTEGER,
    recorded_at TEXT NOT NULL,
    UNIQUE(mac, ap_id)
);
CREATE INDEX IF NOT EXISTS idx_wifi_mac ON wifi_clients(mac);

-- State-change event log.
-- event_type: 'up', 'down', 'new_device', 'ip_change', 'hostname_change'
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip          TEXT,
    mac         TEXT,
    event_type  TEXT NOT NULL,
    detail      TEXT,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_ip   ON events(ip);
"""


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------
class Database:
    def __init__(self, path: Optional[Path | str] = None) -> None:
        if path is None:
            path = DEFAULT_DB_PATH
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
        log.debug("Schema initialised at %s", self.path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # hosts
    # ------------------------------------------------------------------
    def upsert_host(
        self,
        mac: str,
        hostname: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> None:
        mac = mac.upper()
        now = self._now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT mac FROM hosts WHERE mac = ?", (mac,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO hosts (mac, hostname, vendor, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (mac, hostname, vendor, now, now),
                )
                log.info("New host: mac=%s hostname=%s vendor=%s", mac, hostname, vendor)
            else:
                conn.execute(
                    "UPDATE hosts SET hostname=COALESCE(?,hostname), "
                    "vendor=COALESCE(?,vendor), last_seen=? WHERE mac=?",
                    (hostname, vendor, now, mac),
                )

    def get_host(self, mac: str) -> Optional[Dict[str, Any]]:
        mac = mac.upper()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM hosts WHERE mac=?", (mac,)).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # ip_assignments
    # ------------------------------------------------------------------
    def upsert_ip(
        self,
        mac: str,
        ip: str,
        subnet: str,
        binding_type: str = "dynamic",
    ) -> None:
        mac = mac.upper()
        now = self._now()
        with self._conn() as conn:
            if not conn.execute("SELECT 1 FROM hosts WHERE mac=?", (mac,)).fetchone():
                conn.execute(
                    "INSERT INTO hosts (mac, hostname, vendor, first_seen, last_seen) "
                    "VALUES (?, NULL, NULL, ?, ?)",
                    (mac, now, now),
                )
            conn.execute(
                "INSERT INTO ip_assignments (mac, ip, subnet, binding_type, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(mac, ip) DO UPDATE SET last_seen=excluded.last_seen, "
                "binding_type=excluded.binding_type",
                (mac, ip, subnet, binding_type, now, now),
            )

    def get_mac_for_ip(self, ip: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mac FROM ip_assignments WHERE ip=? ORDER BY last_seen DESC LIMIT 1",
                (ip,),
            ).fetchone()
            return row["mac"] if row else None

    # ------------------------------------------------------------------
    # ping_history
    # ------------------------------------------------------------------
    def record_ping(
        self,
        ip: str,
        alive: bool,
        rtt_ms: Optional[float] = None,
        probed_at: Optional[str] = None,
    ) -> None:
        now = probed_at or self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ping_history (ip, alive, rtt_ms, probed_at) VALUES (?, ?, ?, ?)",
                (ip, int(alive), rtt_ms, now),
            )

    def get_ping_history(self, ip: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ip, alive, rtt_ms, probed_at FROM ping_history "
                "WHERE ip=? ORDER BY probed_at DESC LIMIT ?",
                (ip, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def prune_ping_history(self, keep_days: int = 7) -> int:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=keep_days)
        cutoff = cutoff_dt.isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM ping_history WHERE probed_at < ?", (cutoff,)
            )
            deleted = cur.rowcount
        if deleted:
            log.info("Pruned %d ping_history rows older than %d days", deleted, keep_days)
        return deleted

    # ------------------------------------------------------------------
    # mdns_records
    # ------------------------------------------------------------------
    def upsert_mdns(
        self,
        ip: str,
        service_type: str,
        service_name: Optional[str] = None,
        port: Optional[int] = None,
        txt: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = self._now()
        txt_json = json.dumps(txt) if txt else None
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO mdns_records "
                "(ip, service_type, service_name, port, txt, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ip, service_type, service_name) DO UPDATE SET "
                "port=excluded.port, txt=excluded.txt, last_seen=excluded.last_seen",
                (ip, service_type, service_name, port, txt_json, now, now),
            )

    def get_mdns_for_ip(self, ip: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM mdns_records WHERE ip=? ORDER BY service_type",
                (ip,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # wifi_clients
    # ------------------------------------------------------------------
    def record_wifi(
        self,
        mac: str,
        ap_id: str,
        ssid: Optional[str] = None,
        band: Optional[str] = None,
        rssi_dbm: Optional[int] = None,
        tx_rate: Optional[int] = None,
        rx_rate: Optional[int] = None,
    ) -> None:
        mac = mac.upper()
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO wifi_clients "
                "(mac, ap_id, ssid, band, rssi_dbm, tx_rate, rx_rate, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(mac, ap_id) DO UPDATE SET "
                "ssid=excluded.ssid, band=excluded.band, rssi_dbm=excluded.rssi_dbm, "
                "tx_rate=excluded.tx_rate, rx_rate=excluded.rx_rate, "
                "recorded_at=excluded.recorded_at",
                (mac, ap_id, ssid, band, rssi_dbm, tx_rate, rx_rate, now),
            )

    def get_wifi_for_mac(self, mac: str) -> List[Dict[str, Any]]:
        mac = mac.upper()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM wifi_clients WHERE mac=? ORDER BY recorded_at DESC",
                (mac,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def record_event(
        self,
        event_type: str,
        ip: Optional[str] = None,
        mac: Optional[str] = None,
        detail: Optional[Any] = None,
        occurred_at: Optional[str] = None,
    ) -> None:
        now = occurred_at or self._now()
        detail_str = (
            json.dumps(detail)
            if detail is not None and not isinstance(detail, str)
            else detail
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (ip, mac, event_type, detail, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ip, mac.upper() if mac else None, event_type, detail_str, now),
            )
        log.info("Event: %s ip=%s mac=%s", event_type, ip, mac)

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY occurred_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Aggregate query — current state per device
    # ------------------------------------------------------------------
    def get_current_devices(self) -> List[Dict[str, Any]]:
        """
        One row per current IP assignment, joined with host data,
        latest ping result (by MAX rowid), and latest wifi data.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    ia.ip,
                    ia.mac,
                    ia.subnet,
                    ia.binding_type,
                    ia.last_seen    AS ip_last_seen,
                    h.hostname,
                    h.vendor,
                    ph.alive,
                    ph.rtt_ms,
                    ph.probed_at,
                    wc.ap_id,
                    wc.ssid,
                    wc.band,
                    wc.rssi_dbm,
                    wc.tx_rate,
                    wc.rx_rate
                FROM ip_assignments ia
                LEFT JOIN hosts h ON h.mac = ia.mac
                LEFT JOIN (
                    SELECT ip, alive, rtt_ms, probed_at
                    FROM ping_history
                    WHERE id IN (
                        SELECT MAX(id) FROM ping_history GROUP BY ip
                    )
                ) ph ON ph.ip = ia.ip
                LEFT JOIN wifi_clients wc ON wc.mac = ia.mac
                ORDER BY ia.subnet, ia.ip
                """,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_table_counts(self) -> Dict[str, int]:
        tables = [
            "hosts", "ip_assignments", "ping_history",
            "mdns_records", "wifi_clients", "events",
        ]
        with self._conn() as conn:
            return {
                t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables
            }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Network Observability SQLite schema tool")
    parser.add_argument("--path", type=Path, default=DEFAULT_DB_PATH, help="Database path")
    parser.add_argument("--init", action="store_true", help="Create schema and exit")
    parser.add_argument("--dump", action="store_true", help="Dump table row counts as JSON")
    args = parser.parse_args()

    db = Database(args.path)

    if args.init:
        print(f"Schema initialised at {db.path}")
        return

    if args.dump:
        counts = db.get_table_counts()
        print(json.dumps(counts, indent=2))
        return

    print(f"Database: {db.path}")
    for table, count in db.get_table_counts().items():
        print(f"  {table:<20} {count} rows")


if __name__ == "__main__":
    main()
