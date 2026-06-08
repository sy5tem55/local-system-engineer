#!/usr/bin/env python3
"""
nvidia-gpu-exporter  v1.0
Prometheus exporter for NVIDIA GPU metrics via nvidia-smi.

Metrics exposed (port 9835):
  nvidia_gpu_memory_used_mib{gpu="0",name="..."}
  nvidia_gpu_memory_free_mib{gpu="0",name="..."}
  nvidia_gpu_memory_total_mib{gpu="0",name="..."}
  nvidia_gpu_utilization_percent{gpu="0",name="..."}
  nvidia_gpu_temperature_celsius{gpu="0",name="..."}
  nvidia_gpu_power_draw_watts{gpu="0",name="..."}

Install:
  sudo cp nvidia-gpu-exporter.py /opt/local-se/
  # Then add to restart_exporters.sh (already referenced at /opt/local-se/nvidia-gpu-exporter.py)

Requires: nvidia-smi in PATH, prometheus_client
  pip install prometheus_client==0.25.0 --break-system-packages
"""

import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 9835
POLL_INTERVAL = 15   # seconds between nvidia-smi polls

# ── State ─────────────────────────────────────────────────────────────────────
_last_metrics: str = ""
_last_poll: float = 0.0


def query_nvidia_smi() -> str:
    """Run nvidia-smi and return Prometheus-format text."""
    fields = [
        "index",
        "name",
        "memory.used",
        "memory.free",
        "memory.total",
        "utilization.gpu",
        "temperature.gpu",
        "power.draw",
    ]
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"# ERROR: nvidia-smi failed: {e}\n"

    lines = []
    for row in result.stdout.strip().splitlines():
        parts = [p.strip() for p in row.split(",")]
        if len(parts) < len(fields):
            continue

        idx, name, mem_used, mem_free, mem_total, util, temp, power = parts
        labels = f'gpu="{idx}",name="{name}"'

        def gauge(metric, value, help_text):
            try:
                v = float(value.replace("N/A", "nan").replace("[N/A]", "nan"))
            except ValueError:
                return ""
            return (
                f"# HELP {metric} {help_text}\n"
                f"# TYPE {metric} gauge\n"
                f"{metric}{{{labels}}} {v}\n"
            )

        lines.append(gauge("nvidia_gpu_memory_used_mib",    mem_used,  "GPU memory used MiB"))
        lines.append(gauge("nvidia_gpu_memory_free_mib",    mem_free,  "GPU memory free MiB"))
        lines.append(gauge("nvidia_gpu_memory_total_mib",   mem_total, "GPU memory total MiB"))
        lines.append(gauge("nvidia_gpu_utilization_percent", util,     "GPU utilization percent"))
        lines.append(gauge("nvidia_gpu_temperature_celsius", temp,     "GPU temperature Celsius"))
        lines.append(gauge("nvidia_gpu_power_draw_watts",   power,     "GPU power draw Watts"))

    return "".join(l for l in lines if l)


# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # suppress per-request access logs

    def do_GET(self):
        global _last_metrics, _last_poll
        if self.path not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return

        now = time.time()
        if now - _last_poll >= POLL_INTERVAL:
            _last_metrics = query_nvidia_smi()
            _last_poll = now

        body = _last_metrics.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Pre-warm
    _last_metrics = query_nvidia_smi()
    _last_poll = time.time()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"nvidia-gpu-exporter listening on :{PORT}")
    print(f"  Metrics: http://localhost:{PORT}/metrics")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nnvidia-gpu-exporter stopped")
