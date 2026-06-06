#!/usr/bin/env python3
"""
SearXNG Error Log Exporter
Tails the searxng container log via Docker socket and exports per-engine
error counters to Prometheus.

Metric exported:
  searxng_engine_errors_total{engine_name, error_type}

error_type values:
  timeout        — httpx.TimeoutException  (slow response, hit timeout ceiling)
  read_timeout   — httpx.ReadTimeout       (connected but no data — active throttling)
  rate_limited   — HTTP 429 / TooManyRequests
  access_denied  — HTTP 403 / AccessDenied
  http_error     — other HTTP error codes
"""

import re
import os
import sys
import time
import threading
import docker
from prometheus_client import start_http_server, Counter, REGISTRY
from prometheus_client.core import CollectorRegistry

# ── Config ─────────────────────────────────────────────────────────────────────
CONTAINER_NAME = os.getenv("SEARXNG_CONTAINER", "searxng")
EXPORTER_PORT  = int(os.getenv("EXPORTER_PORT", "9837"))

# ── Error patterns — order matters: more specific first ───────────────────────
# Each tuple: (compiled regex, error_type label value)
# Only ERROR-level log lines are matched to avoid double-counting WARNING dupes.
PATTERNS = [
    # Timeout: engine contacted but exceeded timeout ceiling
    (re.compile(r"ERROR:searx\.engines\.(\w+):.*TimeoutException"),          "timeout"),
    # Read timeout: connected, zero/minimal data returned — classic throttle signal
    (re.compile(r"ERROR:searx\.engines\.(\w+):.*ReadTimeout"),               "read_timeout"),
    # Rate limited: explicit HTTP 429 or SearXNG exception name
    (re.compile(r"ERROR:searx\.engines\.(\w+):.*(?:429|TooManyRequests)"),   "rate_limited"),
    # Access denied: HTTP 403 or SearXNG exception name
    (re.compile(r"ERROR:searx\.engines\.(\w+):.*(?:403|AccessDenied)"),      "access_denied"),
    # Generic HTTP error — catch-all for other 4xx/5xx
    (re.compile(r"ERROR:searx\.engines\.(\w+):.*HTTP \d+ error"),            "http_error"),
]

# ── Prometheus counter ─────────────────────────────────────────────────────────
error_counter = Counter(
    "searxng_engine_errors_total",
    "SearXNG per-engine error counts by type, parsed from container logs",
    ["engine_name", "error_type"],
)


def parse_line(line: str) -> tuple[str, str] | None:
    """
    Match a log line against error patterns.
    Returns (engine_name, error_type) or None if no match.
    """
    for pattern, error_type in PATTERNS:
        m = pattern.search(line)
        if m:
            return m.group(1), error_type
    return None


def tail_logs(container_name: str):
    """Stream logs from the named container and increment counters on matches."""
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")

    while True:
        try:
            container = client.containers.get(container_name)
            print(f"[INFO] Connected to container '{container_name}', streaming logs...",
                  flush=True)

            # tail=0: only new lines from now on (don't replay history on reconnect)
            for raw in container.logs(stream=True, follow=True, tail=0, stderr=True, stdout=True):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                result = parse_line(line)
                if result:
                    engine_name, error_type = result
                    error_counter.labels(engine_name=engine_name, error_type=error_type).inc()
                    print(f"[{error_type}] {engine_name}: {line[-120:]}", flush=True)

        except docker.errors.NotFound:
            print(f"[WARN] Container '{container_name}' not found, retrying in 15s...",
                  flush=True)
        except Exception as e:
            print(f"[ERROR] Log stream interrupted: {e} — retrying in 15s...",
                  file=sys.stderr, flush=True)

        time.sleep(15)


def main():
    print(f"[INFO] SearXNG Error Log Exporter starting")
    print(f"[INFO] Container:  {CONTAINER_NAME}")
    print(f"[INFO] Exporter:   http://0.0.0.0:{EXPORTER_PORT}/metrics")

    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)
    print(f"[INFO] Prometheus metrics server listening on :{EXPORTER_PORT}")

    # Tail logs in the main thread (reconnects automatically on failure)
    tail_logs(CONTAINER_NAME)


if __name__ == "__main__":
    main()
