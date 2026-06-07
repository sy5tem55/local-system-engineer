#!/usr/bin/env python3
"""Lightweight HTTP API serving ECharts topology data from snapshot.json."""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Allow overriding the snapshot path via env
SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH", str(Path(__file__).parent / "snapshot.json"))
PORT = int(os.environ.get("TOPOLOGY_API_PORT", "8766"))


class TopologyHandler(BaseHTTPRequestHandler):
    """Serve topology data as JSON for Grafana Infinity datasource."""

    def do_GET(self):
        if self.path == "/topology":
            try:
                with open(SNAPSHOT_PATH) as f:
                    snapshot = json.load(f)

                # Import and run the conversion
                sys.path.insert(0, str(Path(__file__).parent))
                from echarts_topology import build_echarts_data
                data = build_echarts_data()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging to keep output clean."""
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), TopologyHandler)
    print(f"Topology API listening on port {PORT}")
    sys.stdout.flush()
    server.serve_forever()
