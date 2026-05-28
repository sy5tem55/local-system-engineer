#!/usr/bin/env python3
"""
download-speed-exporter  v1.0
Prometheus exporter for network interface download/upload speed.
Reads /proc/net/dev every second, exposes per-interface bytes/sec gauges.

Metrics exposed (port 9838):
  network_receive_bytes_per_second{interface="eth0"}   ← download speed
  network_transmit_bytes_per_second{interface="eth0"}  ← upload speed
  network_receive_bytes_total{interface="eth0"}        ← cumulative rx
  network_transmit_bytes_total{interface="eth0"}       ← cumulative tx

Install:
  sudo cp download-speed-exporter.py /opt/local-se/
  sudo systemctl enable --now download-speed-exporter
"""

import time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 9838
PROC_NET_DEV = "/proc/net/dev"

# Interfaces to skip (loopback, docker bridges, etc.)
SKIP_PREFIXES = ("lo", "docker", "br-", "veth", "virbr")


def parse_proc_net_dev():
    """Return dict of {iface: (rx_bytes, tx_bytes)} from /proc/net/dev."""
    stats = {}
    try:
        with open(PROC_NET_DEV) as f:
            lines = f.readlines()
        # Lines 0-1 are headers; data starts at line 2
        for line in lines[2:]:
            parts = line.split()
            if not parts:
                continue
            iface = parts[0].rstrip(":")
            if any(iface.startswith(p) for p in SKIP_PREFIXES):
                continue
            rx_bytes = int(parts[1])
            tx_bytes = int(parts[9])
            stats[iface] = (rx_bytes, tx_bytes)
    except Exception:
        pass
    return stats


# State: previous sample
_prev_stats = {}
_prev_time = time.monotonic()
_rates = {}      # {iface: (rx_bps, tx_bps)}
_totals = {}     # {iface: (rx_bytes, tx_bytes)}


def update():
    """Sample /proc/net/dev and compute per-second rates."""
    global _prev_stats, _prev_time, _rates, _totals

    now = time.monotonic()
    current = parse_proc_net_dev()
    elapsed = now - _prev_time

    new_rates = {}
    if _prev_stats and elapsed > 0:
        for iface, (rx, tx) in current.items():
            if iface in _prev_stats:
                prev_rx, prev_tx = _prev_stats[iface]
                # Guard against counter wrap (unlikely on 64-bit kernels)
                d_rx = max(0, rx - prev_rx)
                d_tx = max(0, tx - prev_tx)
                new_rates[iface] = (d_rx / elapsed, d_tx / elapsed)
            else:
                new_rates[iface] = (0.0, 0.0)
    else:
        for iface in current:
            new_rates[iface] = (0.0, 0.0)

    _rates = new_rates
    _totals = current
    _prev_stats = current
    _prev_time = now


def build_metrics():
    update()
    lines = []

    lines.append("# HELP network_receive_bytes_per_second Network receive speed in bytes/sec")
    lines.append("# TYPE network_receive_bytes_per_second gauge")
    for iface, (rx_bps, _) in sorted(_rates.items()):
        lines.append(f'network_receive_bytes_per_second{{interface="{iface}"}} {rx_bps:.2f}')

    lines.append("# HELP network_transmit_bytes_per_second Network transmit speed in bytes/sec")
    lines.append("# TYPE network_transmit_bytes_per_second gauge")
    for iface, (_, tx_bps) in sorted(_rates.items()):
        lines.append(f'network_transmit_bytes_per_second{{interface="{iface}"}} {tx_bps:.2f}')

    lines.append("# HELP network_receive_bytes_total Cumulative bytes received")
    lines.append("# TYPE network_receive_bytes_total counter")
    for iface, (rx, _) in sorted(_totals.items()):
        lines.append(f'network_receive_bytes_total{{interface="{iface}"}} {rx}')

    lines.append("# HELP network_transmit_bytes_total Cumulative bytes transmitted")
    lines.append("# TYPE network_transmit_bytes_total counter")
    for iface, (_, tx) in sorted(_totals.items()):
        lines.append(f'network_transmit_bytes_total{{interface="{iface}"}} {tx}')

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = build_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # suppress per-request logs


if __name__ == "__main__":
    # Prime the baseline sample so first scrape shows real rates
    _prev_stats = parse_proc_net_dev()
    _prev_time = time.monotonic()
    print(f"download-speed-exporter v1.0 listening on :{PORT}")
    HTTPServer(("", PORT), Handler).serve_forever()
