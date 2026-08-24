#!/usr/bin/env python3
# =============================================================================
# llamacpp-metrics-reexporter.py — re-exposes node4090's loopback llama-server /metrics
# =============================================================================
#
# node4090's llama-server binds 127.0.0.1:8080 by design. It is reachable
# from the LAN via WSL2 host-level binding, but NOT from the Docker bridge
# (172.17.0.1:8080 -> connection refused), so the Prometheus job
# "llama-server" is chronically down.
#
# This re-exporter listens on 0.0.0.0:9840 (reachable from the Docker
# bridge at 172.17.0.1:9840 — same pattern as the 9835-9839 exporters)
# and proxies GET /metrics to 127.0.0.1:8080/metrics on every request.
#
# Read-only: never writes to the llama-server. Stdlib only, no deps.
#
# Run:   nohup python3 llamacpp-metrics-reexporter.py > /tmp/lse-exporters/llamacpp-reexporter.log 2>&1 &
# Check: curl -s http://127.0.0.1:9840/metrics | head
# =============================================================================

import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://127.0.0.1:8080/metrics"
UPSTREAM_TIMEOUT_S = 8.0   # keep under Prometheus' 10s scrape timeout
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9840


class MetricsProxy(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        try:
            with urllib.request.urlopen(UPSTREAM, timeout=UPSTREAM_TIMEOUT_S) as r:
                body = r.read()
                ctype = r.headers.get(
                    "Content-Type", "text/plain; version=0.0.4; charset=utf-8"
                )
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # upstream down -> 502, target goes down cleanly
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"reexporter: upstream error: {exc}\n".encode())

    def log_message(self, fmt, *args):
        # Silence per-scrape logging (Prometheus hits every 15s);
        # startup + fatal errors still reach the log via print/traceback.
        pass


def main():
    print(f"llamacpp-metrics-reexporter: {LISTEN_HOST}:{LISTEN_PORT} -> {UPSTREAM}", flush=True)
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), MetricsProxy).serve_forever()


if __name__ == "__main__":
    main()
