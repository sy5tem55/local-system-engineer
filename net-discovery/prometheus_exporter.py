"""
prometheus_exporter.py — Network Observability Prometheus exporter
Exposes per-device up/down metrics from snapshot.json on :9120.

PRE-INSTALL RULE: prometheus_client==0.25.0 is ALREADY installed.
  Check: pip show prometheus_client
  DO NOT reinstall.

Metrics exposed:
  netobs_device_up{ip, mac, hostname, subnet, type}  — 1=up, 0=down
  netobs_device_icmp_rtt_ms{ip, mac, hostname}       — last ICMP RTT in ms (-1 if unavailable)
  netobs_device_wifi_rssi_dbm{ip, mac, hostname, ssid, band} — WiFi RSSI (-100 if unavailable)
  netobs_snapshot_age_seconds                        — seconds since snapshot was generated
  netobs_devices_total{subnet}                       — device count per subnet
  netobs_devices_up_total{subnet}                    — up device count per subnet

Usage:
  python3 prometheus_exporter.py [--config config.json] [--port 9120]

Grafana scrape target (prometheus.yml):
  - job_name: 'netobs'
    static_configs:
      - targets: ['host.docker.internal:9120']
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Dependency guard — prometheus_client is already installed, but fail clearly
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        Gauge,
        CollectorRegistry,
        REGISTRY,
        start_http_server,
        PROCESS_COLLECTOR,
        PLATFORM_COLLECTOR,
        GC_COLLECTOR,
    )
    from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
    from prometheus_client.registry import Collector
except ImportError:
    print(
        "ERROR: prometheus_client not importable.\n"
        "Check first: pip show prometheus_client\n"
        "Install only if missing: pip install prometheus_client==0.25.0 --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("netobs.exporter")

# ---------------------------------------------------------------------------
# Default paths / ports — overridden by config.json or CLI args
# ---------------------------------------------------------------------------
DEFAULT_SNAPSHOT = Path(__file__).parent / "snapshot.json"
DEFAULT_PORT = 9120


# ---------------------------------------------------------------------------
# Custom collector — re-reads snapshot on every scrape so Prometheus always
# sees the freshest data without us needing a background thread.
# ---------------------------------------------------------------------------
class SnapshotCollector(Collector):
    """Reads snapshot.json at scrape time and yields Prometheus metrics."""

    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path

    # ------------------------------------------------------------------
    def collect(self):
        snapshot = self._load_snapshot()
        if snapshot is None:
            # Yield a sentinel so Prometheus knows the exporter is alive
            # but snapshot is unreadable.
            g = GaugeMetricFamily(
                "netobs_snapshot_readable",
                "1 if snapshot.json was read successfully, 0 otherwise",
            )
            g.add_metric([], 0)
            yield g
            return

        devices: list[Dict[str, Any]] = snapshot.get("devices", [])
        generated_at: Optional[str] = snapshot.get("generated_at")
        age_s = self._snapshot_age(generated_at)

        # ── netobs_snapshot_readable ────────────────────────────────────
        readable = GaugeMetricFamily(
            "netobs_snapshot_readable",
            "1 if snapshot.json was read successfully, 0 otherwise",
        )
        readable.add_metric([], 1)
        yield readable

        # ── netobs_snapshot_age_seconds ─────────────────────────────────
        age_metric = GaugeMetricFamily(
            "netobs_snapshot_age_seconds",
            "Seconds since snapshot.json was generated",
        )
        age_metric.add_metric([], age_s if age_s is not None else -1)
        yield age_metric

        # ── Per-device metrics ──────────────────────────────────────────
        device_up = GaugeMetricFamily(
            "netobs_device_up",
            "1 if device responded to last ICMP probe, 0 if down",
            labels=["ip", "mac", "hostname", "subnet", "type"],
        )
        icmp_rtt = GaugeMetricFamily(
            "netobs_device_icmp_rtt_ms",
            "Last ICMP round-trip time in milliseconds (-1 if unavailable)",
            labels=["ip", "mac", "hostname"],
        )
        wifi_rssi = GaugeMetricFamily(
            "netobs_device_wifi_rssi_dbm",
            "WiFi RSSI in dBm for wireless clients (-100 if unavailable)",
            labels=["ip", "mac", "hostname", "ssid", "band"],
        )

        # Aggregation counters per subnet
        subnet_total: Dict[str, int] = {}
        subnet_up: Dict[str, int] = {}

        for dev in devices:
            ip = str(dev.get("ip", ""))
            mac = str(dev.get("mac", ""))
            hostname = str(dev.get("hostname", ""))
            subnet = str(dev.get("subnet", "unknown"))
            dev_type = str(dev.get("type", "unknown"))

            # up/down from icmp.alive field; fall back to presence in snapshot
            icmp = dev.get("icmp") or {}
            alive = icmp.get("alive")
            if alive is None:
                # Device in snapshot but never pinged — treat as unknown (0.5)
                # Prometheus Gauge is float; use 0 for unknown to avoid false-up.
                up_val = 0.0
            else:
                up_val = 1.0 if alive else 0.0

            device_up.add_metric([ip, mac, hostname, subnet, dev_type], up_val)

            # ICMP RTT
            rtt = icmp.get("rtt_ms")
            icmp_rtt.add_metric([ip, mac, hostname], float(rtt) if rtt is not None else -1.0)

            # WiFi RSSI (only for devices that have wifi data)
            wifi = dev.get("wifi")
            if wifi:
                rssi = wifi.get("rssi_dbm")
                ssid = str(wifi.get("ssid", ""))
                band = str(wifi.get("band", ""))
                wifi_rssi.add_metric(
                    [ip, mac, hostname, ssid, band],
                    float(rssi) if rssi is not None else -100.0,
                )

            # Aggregation
            subnet_total[subnet] = subnet_total.get(subnet, 0) + 1
            if up_val > 0:
                subnet_up[subnet] = subnet_up.get(subnet, 0) + 1

        yield device_up
        yield icmp_rtt
        yield wifi_rssi

        # ── Subnet aggregate counts ─────────────────────────────────────
        total_metric = GaugeMetricFamily(
            "netobs_devices_total",
            "Total number of devices discovered per subnet",
            labels=["subnet"],
        )
        up_total_metric = GaugeMetricFamily(
            "netobs_devices_up_total",
            "Number of devices currently up per subnet",
            labels=["subnet"],
        )
        for sn, count in subnet_total.items():
            total_metric.add_metric([sn], float(count))
            up_total_metric.add_metric([sn], float(subnet_up.get(sn, 0)))

        yield total_metric
        yield up_total_metric

    # ------------------------------------------------------------------
    def _load_snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.snapshot_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            log.warning("snapshot.json not found at %s — waiting for first discovery run", self.snapshot_path)
            return None
        except json.JSONDecodeError as exc:
            log.error("snapshot.json is not valid JSON: %s", exc)
            return None

    # ------------------------------------------------------------------
    @staticmethod
    def _snapshot_age(generated_at: Optional[str]) -> Optional[float]:
        if not generated_at:
            return None
        try:
            import datetime
            # Accept ISO 8601 with or without timezone
            ts = generated_at.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(ts)
            now = datetime.datetime.now(datetime.timezone.utc)
            return (now - dt).total_seconds()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _load_config(config_path: Path) -> Dict[str, Any]:
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not load config.json (%s) — using defaults", exc)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Network Observability Prometheus exporter (reads snapshot.json)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.json",
        help="Path to config.json (default: config.json alongside this script)",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Path to snapshot.json (overrides config output.snapshot_file)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP port to serve /metrics on (overrides config services.prometheus_exporter_port)",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)

    # Resolve snapshot path: CLI > config > default
    if args.snapshot:
        snapshot_path = args.snapshot
    else:
        output_cfg = cfg.get("output", {})
        snap_rel = output_cfg.get("snapshot_file", "snapshot.json")
        snapshot_path = args.config.parent / snap_rel

    # Resolve port: CLI > config > default
    if args.port:
        port = args.port
    else:
        port = cfg.get("services", {}).get("prometheus_exporter_port", DEFAULT_PORT)

    log.info("snapshot.json path : %s", snapshot_path)
    log.info("metrics port       : %d", port)

    # Use a clean registry — avoids double-registering default collectors
    # if this module is imported by a larger app that already has them.
    registry = CollectorRegistry()
    registry.register(SnapshotCollector(snapshot_path))

    start_http_server(port, registry=registry)
    log.info("Prometheus exporter running on :%d/metrics — Ctrl+C to stop", port)

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Exporter stopped.")


if __name__ == "__main__":
    main()
