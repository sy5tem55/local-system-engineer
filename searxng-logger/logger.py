#!/usr/bin/env python3
"""SearXNG Query Logger — scrapes /metrics directly and persists to SQLite."""

import sqlite3
import time
import urllib.request
import urllib.error
import base64
import os
import sys
from datetime import datetime, timezone

SEARXNG_URL      = os.getenv("SEARXNG_URL",              "http://searxng:8080")
METRICS_USER     = os.getenv("SEARXNG_METRICS_USER",     "")
METRICS_PASSWORD = os.getenv("SEARXNG_METRICS_PASSWORD", "metrics-admin-2025")
POLL_INTERVAL    = int(os.getenv("POLL_INTERVAL",        "15"))
DB_PATH          = os.getenv("DB_PATH",                  "/data/searxng.db")

METRICS_URL = f"{SEARXNG_URL}/metrics"

# Metrics we care about — keyed by column name, matched by line prefix
METRIC_PREFIXES = {
    "requests":      "searxng_engines_request_count_total",
    "results":       "searxng_engines_result_count_total",
    "response_time": "searxng_engines_response_time_total_seconds",
    "reliability":   "searxng_engines_reliability_total",
    # "errors": "searxng_engines_error_count_total" — not exported by this SearXNG version.
    # Re-enable if a future version adds it, or implement Docker log parsing instead.
}

# When searxng_engines_error_count_total gains an error_type label,
# set this to the label name (e.g. "error_type") and the logger will
# automatically populate engine_errors_by_type without any other changes.
# To check: curl /metrics | grep error_count — if lines look like
#   searxng_engines_error_count_total{engine_name="arxiv",error_type="timeout"} 3
# then set this to "error_type".
ERROR_TYPE_LABEL = None


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            engine         TEXT    NOT NULL,
            request_count  INTEGER NOT NULL DEFAULT 0,
            result_count   INTEGER NOT NULL DEFAULT 0,
            response_time  REAL    NOT NULL DEFAULT 0.0,
            reliability    REAL    NOT NULL DEFAULT 0.0,
            error_count    INTEGER NOT NULL DEFAULT 0,
            timestamp      TEXT    NOT NULL,
            UNIQUE(engine, timestamp)
        )
    """)

    # Populated only when ERROR_TYPE_LABEL is set and the metric has that label
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_errors_by_type (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            engine      TEXT    NOT NULL,
            error_type  TEXT    NOT NULL,
            count       INTEGER NOT NULL DEFAULT 0,
            timestamp   TEXT    NOT NULL,
            UNIQUE(engine, error_type, timestamp)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Migrate existing databases that pre-date the error_count column
    try:
        conn.execute("ALTER TABLE query_log ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("[INFO] Migrated query_log: added error_count column")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    return conn


def _auth_header():
    token = base64.b64encode(f"{METRICS_USER}:{METRICS_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def scrape_metrics():
    """
    Fetch /metrics and parse Prometheus text format.

    Returns:
        main    — { engine: { requests, results, response_time, reliability, errors } }
        by_type — { engine: { error_type: count } }  (empty unless ERROR_TYPE_LABEL is set)
    """
    req = urllib.request.Request(METRICS_URL, headers=_auth_header())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code} fetching {METRICS_URL}", file=sys.stderr)
        return {}, {}
    except urllib.error.URLError as e:
        print(f"[ERROR] Could not reach {METRICS_URL}: {e.reason}", file=sys.stderr)
        return {}, {}

    main    = {}
    by_type = {}

    for line in body.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        for col, prefix in METRIC_PREFIXES.items():
            if not line.startswith(prefix + "{"):
                continue
            try:
                labels_part, value_part = line.split("}", 1)
                value  = float(value_part.strip())
                labels = {}
                for kv in labels_part.split("{", 1)[1].split(","):
                    k, _, v = kv.partition("=")
                    labels[k.strip()] = v.strip().strip('"')

                engine = labels.get("engine_name", "unknown")
                main.setdefault(engine, {})[col] = value

                # Capture per-type breakdown if label is present
                if col == "errors" and ERROR_TYPE_LABEL and ERROR_TYPE_LABEL in labels:
                    etype = labels[ERROR_TYPE_LABEL]
                    by_type.setdefault(engine, {})[etype] = int(value)

            except (ValueError, IndexError):
                pass

    return main, by_type


def upsert_log(conn, engine, values, timestamp):
    conn.execute("""
        INSERT INTO query_log
            (engine, request_count, result_count, response_time, reliability, error_count, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(engine, timestamp) DO UPDATE SET
            request_count = excluded.request_count,
            result_count  = excluded.result_count,
            response_time = excluded.response_time,
            reliability   = excluded.reliability,
            error_count   = excluded.error_count
    """, (
        engine,
        int(values.get("requests",      0)),
        int(values.get("results",       0)),
        values.get("response_time",     0.0),
        values.get("reliability",       0.0),
        int(values.get("errors",        0)),
        timestamp,
    ))


def upsert_error_type(conn, engine, etype, count, timestamp):
    conn.execute("""
        INSERT INTO engine_errors_by_type (engine, error_type, count, timestamp)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(engine, error_type, timestamp) DO UPDATE SET
            count = excluded.count
    """, (engine, etype, count, timestamp))


def main():
    print(f"[INFO] SearXNG Query Logger starting")
    print(f"[INFO] Metrics URL:    {METRICS_URL}")
    print(f"[INFO] DB path:        {DB_PATH}")
    print(f"[INFO] Poll interval:  {POLL_INTERVAL}s")
    print(f"[INFO] Error type label: {ERROR_TYPE_LABEL or 'not set — error totals only'}")

    conn = init_db(DB_PATH)
    print(f"[INFO] Database ready: {DB_PATH}")

    while True:
        try:
            metrics, by_type = scrape_metrics()
            if metrics:
                timestamp = datetime.now(timezone.utc).isoformat()
                for engine, values in metrics.items():
                    upsert_log(conn, engine, values, timestamp)
                for engine, types in by_type.items():
                    for etype, count in types.items():
                        upsert_error_type(conn, engine, etype, count, timestamp)
                conn.execute(
                    "INSERT OR REPLACE INTO scrape_meta VALUES ('last_scrape', ?)",
                    (timestamp,)
                )
                conn.commit()
                total_errors = sum(int(v.get("errors", 0)) for v in metrics.values())
                print(f"[{timestamp}] Logged {len(metrics)} engines | errors: {total_errors}")
            else:
                print(f"[{datetime.now(timezone.utc).isoformat()}] [WARN] No metrics returned")
        except Exception as e:
            print(f"[{datetime.now(timezone.utc).isoformat()}] [ERROR] {e}", file=sys.stderr)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
