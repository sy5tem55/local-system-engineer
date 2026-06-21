#!/usr/bin/env python3
"""
download-monitor.py — LSE download progress tracker (Prometheus-backed)
========================================================================
version: 0.3

Queries the existing Prometheus/Grafana stack for live network speed
instead of tracking file-size deltas. No state file needed.

Changelog:
  0.3 — Bugfix + hardening pass (version aligned with the LSE KB doc
        "Downloading GGUF Models from HuggingFace", which references the metric
        fix below as landing in v0.3). No functional change from the 0.2
        work-in-progress — same fixes, renumbered. Highlights:
        * FIX (adaptive sleep): SLEEP is now allocated dynamically from the
          remaining ETA (a large fraction of it, with margin) so a long download
          converges in a few re-checks instead of dozens of fixed intervals.
          Bounded by [MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS]. NOTE: every emitted
          SLEEP must fit inside one goethe execute_command call, which is killed
          at COMMAND_TIMEOUT (default 30s). To realise 3-5 polls on a multi-minute
          download, raise BOTH MAX_SLEEP_SECONDS here and COMMAND_TIMEOUT in goethe.
        * FIX (wrong query — no speed data): the script queried
          `rate(node_network_receive_bytes_total[1m])` with a `device` label
          (node_exporter convention). This stack's speed metrics come from the
          custom download-speed-exporter (:9838), which exposes
          `network_receive_bytes_per_second{interface="eth0"}`. The mismatched
          query returned no series -> 0.00 MB/s -> false STALLED. Now queries the
          exporter's per-second gauge with the `interface` label, matching the
          lse-net-speed-01 dashboard. (Ground-truthed against the exporter source
          and dashboard JSON, not recall.)
        * FIX (crash): query_prometheus raised UnboundLocalError on every call.
          `import urllib.parse` was inside the function body, making `urllib` a
          function-local name, so the earlier `urllib.parse.urlencode` reference
          hit an unbound local. urllib.parse is now imported once at module top.
        * FIX (false COMPLETE): completion fired at pct >= 99.9, reporting a
          17.6 GB download "done" with ~18 MB still missing. Completion now
          requires current_bytes within COMPLETE_TOLERANCE_BYTES (64 KB) of
          expected, for filesystem rounding only.
        * FIX (elapsed): mtime-ctime could go negative -> "elapsed -1m -3s".
          Clamped to >= 0 and labelled approximate.
        * GUARD: expected_bytes <= 0 now exits 2 with a clear error.
  0.1 — Initial Prometheus-backed monitor (shipped with goethe monitor_download).

Usage:
    python3 /opt/local-se/download-monitor.py <file_path> <expected_bytes> [interface]

    file_path      — absolute path to the file being downloaded
    expected_bytes — total expected size in bytes
    interface      — network interface to query (default: auto-detect highest traffic)

Output (single line):
    DOWNLOADING | 26.3% | 4.21/16.0 GB | 28.3 MB/s | ETA 423s | SLEEP 25
    COMPLETE    | 100%  | 16.0/16.0 GB | elapsed ~10m 17s
    STALLED     | 26.3% | 4.21/16.0 GB | 0.0 MB/s | no traffic on eth0 | SLEEP 25

    ETA is the full estimate to completion. SLEEP is the next re-check interval —
    a fraction of the ETA (adaptive), capped so it always fits one
    execute_command call. The LSE sleeps SLEEP seconds, then re-checks.

Exit codes:
    0 = complete (file size >= expected, within tolerance)
    1 = still in progress
    2 = error / bad arguments
    3 = stalled (Prometheus reachable but speed < 50 KB/s — check Grafana)

Sleep model: SLEEP = clamp(ceil(ETA * SLEEP_FRACTION), MIN_SLEEP, MAX_SLEEP)
Grafana: http://localhost:3002/d/lse-net-speed-01/network-download-speed
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

# ── config ────────────────────────────────────────────────────────────────────
PROMETHEUS_URL = "http://localhost:9090"
STALL_THRESHOLD_BPS = 50 * 1024        # 50 KB/s — below this = stalled
COMPLETE_TOLERANCE_BYTES = 64 * 1024   # treat within 64 KB of expected as done

# ── adaptive sleep model ──────────────────────────────────────────────────────
# SLEEP is how long the LSE waits before the next check. It is allocated from the
# remaining ETA so long downloads converge in a few checks: each check waits
# SLEEP_FRACTION of the time still left, re-checking just before the projected
# finish rather than overshooting. Bounded by [MIN, MAX]_SLEEP_SECONDS.
#
# HARD CONSTRAINT: the LSE runs `sleep N` through goethe's execute_command, which
# is killed at COMMAND_TIMEOUT (default 30s). So MAX_SLEEP_SECONDS must stay under
# that, or the sleep is silently truncated. To get 3-5 polls on a multi-minute
# download, raise BOTH MAX_SLEEP_SECONDS and goethe's COMMAND_TIMEOUT together.
SLEEP_FRACTION = 0.85    # wait 85% of the remaining ETA, re-check before finish
MIN_SLEEP_SECONDS = 5    # floor — avoid hammering on near-done / fast links
MAX_SLEEP_SECONDS = 180  # ceiling — paired with goethe COMMAND_TIMEOUT=200 (>=20s
                         # headroom). ~5 polls for a 10-min download. Keep this
                         # strictly below COMMAND_TIMEOUT or `sleep N` is truncated.

GRAFANA_URL = "http://localhost:3002/d/lse-net-speed-01/network-download-speed"

# ── args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 3:
    print("Usage: download-monitor.py <file_path> <expected_bytes> [interface]", file=sys.stderr)
    sys.exit(2)

file_path = sys.argv[1]
try:
    expected_bytes = int(sys.argv[2])
except ValueError:
    print(f"ERROR: expected_bytes must be integer, got: {sys.argv[2]}", file=sys.stderr)
    sys.exit(2)

if expected_bytes <= 0:
    print(f"ERROR: expected_bytes must be > 0, got: {expected_bytes}", file=sys.stderr)
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
        print(
            f"NOT_FOUND | 0% | 0/{expected_bytes/1e9:.1f} GB | — | — | "
            f"SLEEP {MAX_SLEEP_SECONDS}"
        )
        sys.exit(1)

try:
    current_bytes = os.path.getsize(actual_path)
except OSError as e:
    print(f"ERROR | {e}", file=sys.stderr)
    sys.exit(2)

# ── completion check ──────────────────────────────────────────────────────────
pct = current_bytes / expected_bytes * 100

# Complete only when the file is actually whole. A small absolute tolerance
# (not a 99.9% ratio) covers filesystem rounding without declaring a multi-GB
# download "done" while tens of MB are still missing.
if current_bytes >= expected_bytes - COMPLETE_TOLERANCE_BYTES:
    gb = expected_bytes / 1e9
    # Best-effort elapsed from file mtime. ctime is inode-change time on Linux,
    # not creation — approximate, and clamped to >= 0 so clock/metadata quirks
    # never produce a negative "elapsed -1m -3s".
    try:
        mtime = os.path.getmtime(actual_path)
        ctime = os.path.getctime(actual_path)
        elapsed = max(0, int(mtime - ctime))
        mins, secs = divmod(elapsed, 60)
        elapsed_str = f"elapsed ~{mins}m {secs}s"
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
        req = urllib.request.Request(f"{url}?{params}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "success":
            return []
        return [(r["metric"], float(r["value"][1])) for r in data["data"]["result"]]
    except Exception:
        return []


# Per-interface receive speed (bytes/sec). This stack's metrics come from the
# custom download-speed-exporter (tools/download-speed-exporter.py, scrape job
# "download-speed" :9838), NOT node_exporter — so the series is
# network_receive_bytes_per_second{interface="eth0"}, with an `interface` label
# (not node_network_receive_bytes_total{device=...}). This matches the
# lse-net-speed-01 Grafana dashboard. Using the exporter's per-second gauge
# directly avoids the rate()[1m] warm-up lag that can read 0 at download start.
results = query_prometheus("network_receive_bytes_per_second")

# Filter out loopback and virtual interfaces
EXCLUDE = {"lo", "docker0", "virbr0"}
candidates = [
    (labels.get("interface", ""), bps)
    for labels, bps in results
    if labels.get("interface", "") not in EXCLUDE
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
        f" | check {GRAFANA_URL} | SLEEP {MAX_SLEEP_SECONDS}"
    )
    sys.exit(3)

# ── ETA and adaptive sleep ────────────────────────────────────────────────────
remaining = expected_bytes - current_bytes
cur_gb = current_bytes / 1e9
exp_gb = expected_bytes / 1e9

if speed_bps > STALL_THRESHOLD_BPS:
    eta_s = remaining / speed_bps
    # Adaptive allocation: wait a large fraction of the remaining ETA so the
    # download converges in a handful of checks. Clamped to [MIN, MAX]_SLEEP so
    # it never hammers and never exceeds one execute_command budget.
    sleep_s = math.ceil(eta_s * SLEEP_FRACTION)
    sleep_s = max(MIN_SLEEP_SECONDS, min(sleep_s, MAX_SLEEP_SECONDS))
    eta_str = f"ETA {int(eta_s)}s"
    sleep_str = f"SLEEP {sleep_s}"
elif not results:
    # Prometheus unreachable — fall back to a capped re-check interval
    eta_str = "ETA unknown (Prometheus unreachable)"
    sleep_str = f"SLEEP {MAX_SLEEP_SECONDS}"
    iface = "?"
    speed_mbps = 0.0
else:
    eta_str = "ETA unknown"
    sleep_str = f"SLEEP {MAX_SLEEP_SECONDS}"

print(
    f"DOWNLOADING | {pct:.1f}% | {cur_gb:.2f}/{exp_gb:.1f} GB"
    f" | {speed_mbps:.1f} MB/s ({iface}) | {eta_str} | {sleep_str}"
)
sys.exit(1)
