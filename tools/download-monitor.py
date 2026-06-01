#!/usr/bin/env python3
"""
download-monitor.py — LSE download progress tracker (Prometheus-backed)
========================================================================
Queries the existing Prometheus/Grafana stack for live network speed
instead of tracking file-size deltas. No state file needed.

Usage:
    python3 /opt/local-se/download-monitor.py <file_path> <expected_bytes> [interface]

    file_path      — absolute path to the file being downloaded
    expected_bytes — total expected size in bytes
    interface      — network interface to query (default: auto-detect highest traffic)

Output (single line):
    DOWNLOADING | 26.3% | 4.21/16.0 GB | 28.3 MB/s | ETA 423s | SLEEP 472
    COMPLETE    | 100%  | 16.0/16.0 GB | avg 26.1 MB/s | elapsed 10m 17s
    STALLED     | 26.3% | 4.21/16.0 GB | 0.0 MB/s | no traffic on eth0 | SLEEP 30

Exit codes:
    0 = complete (file size >= expected)
    1 = still in progress
    2 = error / file not found
    3 = stalled (speed < 50 KB/s for >60s — check Grafana manually)

Buffer: SLEEP = ceil(ETA * 1.08 + 15)  — 8% overhead + 15s fixed floor
Grafana: http://localhost:3002/d/lse-net-speed-01/network-download-speed
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

# ── config ────────────────────────────────────────────────────────────────────
PROMETHEUS_URL = "http://localhost:9090"
STALL_THRESHOLD_BPS = 50 * 1024   # 50 KB/s — below this = stalled
GRAFANA_URL = "http://localhost:3002/d/lse-net-speed-01/network-download-speed"

# ── args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 3:
    print("Usage: download-monitor.py <file_path> <expected_bytes> [interface]", file=sys.stderr)
    sys.exit(2)

file_path      = sys.argv[1]
try:
    expected_bytes = int(sys.argv[2])
except ValueError:
    print(f"ERROR: expected_bytes must be integer, got: {sys.argv[2]}", file=sys.stderr)
    sys.exit(2)

interface_hint = sys.argv[3] if len(sys.argv) > 3 else None

# ── resolve file (handle .part / .incomplete suffixes) ───────────────────────
actual_path = file_path
if not os.path.exists(file_path):
    for suffix in [".part", ".incomplete", ".tmp"]:
        candidate = file_path + suffix
        if os.path.exists(candidate):
            actual_path = candidate
            break
    else:
        print(f"NOT_FOUND | 0% | 0/{expected_bytes/1e9:.1f} GB | — | — | SLEEP 30")
        sys.exit(1)

try:
    current_bytes = os.path.getsize(actual_path)
except OSError as e:
    print(f"ERROR | {e}", file=sys.stderr)
    sys.exit(2)

# ── completion check ──────────────────────────────────────────────────────────
pct = current_bytes / expected_bytes * 100 if expected_bytes > 0 else 0

if current_bytes >= expected_bytes or pct >= 99.9:
    gb = expected_bytes / 1e9
    # Best-effort elapsed from file mtime
    try:
        mtime = os.path.getmtime(actual_path)
        ctime = os.path.getctime(actual_path)
        elapsed = int(mtime - ctime)
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"elapsed {mins}m {secs}s"
    except Exception:
        elapsed_str = "elapsed unknown"
    print(f"COMPLETE | 100% | {gb:.1f}/{gb:.1f} GB | {elapsed_str}")
    sys.exit(0)

# ── query Prometheus for network speed ───────────────────────────────────────
def query_prometheus(promql):
    """Run an instant PromQL query. Returns list of (labels, value) tuples."""
    url = f"{PROMETHEUS_URL}/api/v1/query"
    params = urllib.parse.urlencode({"query": promql})
    try:
        import urllib.parse
        req = urllib.request.Request(f"{url}?{params}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "success":
            return []
        return [(r["metric"], float(r["value"][1])) for r in data["data"]["result"]]
    except Exception:
        return []

import urllib.parse

# 1-minute rate of receive bytes across all interfaces
results = query_prometheus(
    'rate(node_network_receive_bytes_total[1m])'
)

# Filter out loopback and virtual interfaces
EXCLUDE = {"lo", "docker0", "virbr0"}
candidates = [
    (labels.get("device", ""), bps)
    for labels, bps in results
    if labels.get("device", "") not in EXCLUDE
]

if interface_hint:
    # User specified interface — use it directly
    iface_results = [(dev, bps) for dev, bps in candidates if dev == interface_hint]
    if iface_results:
        _, speed_bps = iface_results[0]
        iface = interface_hint
    else:
        speed_bps = 0.0
        iface = interface_hint
else:
    # Auto-select highest-traffic interface
    if candidates:
        iface, speed_bps = max(candidates, key=lambda x: x[1])
    else:
        speed_bps = 0.0
        iface = "unknown"

speed_mbps = speed_bps / 1e6

# ── stall detection ───────────────────────────────────────────────────────────
if speed_bps < STALL_THRESHOLD_BPS and results:
    # Prometheus is reachable but speed is near-zero
    cur_gb = current_bytes / 1e9
    exp_gb = expected_bytes / 1e9
    print(
        f"STALLED | {pct:.1f}% | {cur_gb:.2f}/{exp_gb:.1f} GB"
        f" | {speed_mbps:.2f} MB/s | no traffic on {iface}"
        f" | check {GRAFANA_URL} | SLEEP 30"
    )
    sys.exit(3)

# ── ETA and sleep ─────────────────────────────────────────────────────────────
remaining = expected_bytes - current_bytes
cur_gb = current_bytes / 1e9
exp_gb = expected_bytes / 1e9

if speed_bps > STALL_THRESHOLD_BPS:
    eta_s     = remaining / speed_bps
    sleep_s   = math.ceil(eta_s * 1.08 + 15)
    eta_str   = f"ETA {int(eta_s)}s"
    sleep_str = f"SLEEP {sleep_s}"
elif not results:
    # Prometheus unreachable — fall back to conservative sleep
    eta_str   = "ETA unknown (Prometheus unreachable)"
    sleep_str = "SLEEP 60"
    iface     = "?"
    speed_mbps = 0.0
else:
    eta_str   = "ETA unknown"
    sleep_str = "SLEEP 60"

print(
    f"DOWNLOADING | {pct:.1f}% | {cur_gb:.2f}/{exp_gb:.1f} GB"
    f" | {speed_mbps:.1f} MB/s ({iface}) | {eta_str} | {sleep_str}"
)
sys.exit(1)
