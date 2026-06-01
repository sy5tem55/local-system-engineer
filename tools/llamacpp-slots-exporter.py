#!/usr/bin/env python3
"""
llamacpp-slots-exporter  v1.0
Prometheus exporter for llama.cpp active slot context usage.
Polls the /slots endpoint every POLL_INTERVAL seconds and exposes
per-slot gauges so Grafana can show real-time KV cache fill.

Metrics exposed (port 9839):
  llamacpp_slot_tokens_used{slot="0"}   ← tokens currently in the slot
  llamacpp_slot_n_ctx{slot="0"}         ← slot's max context size
  llamacpp_slot_fill_ratio{slot="0"}    ← tokens_used / n_ctx (0.0–1.0)
  llamacpp_slot_is_processing{slot="0"} ← 1 if slot is actively generating

Install:
  sudo cp llamacpp-slots-exporter.py /opt/local-se/
  sudo systemctl enable --now llamacpp-slots-exporter
"""

import json
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 9839
LLAMA_SLOTS_URL = "http://localhost:8080/slots"
POLL_INTERVAL = 3  # seconds between /slots polls

# Cached metric state
_slots_data = []
_last_poll = 0.0
_poll_error = False


def fetch_slots():
    """Fetch /slots and return list of slot dicts. Returns [] on error."""
    try:
        req = urllib.request.Request(LLAMA_SLOTS_URL,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return []


def maybe_poll():
    """Re-poll /slots if POLL_INTERVAL has elapsed."""
    global _slots_data, _last_poll, _poll_error
    now = time.monotonic()
    if now - _last_poll >= POLL_INTERVAL:
        result = fetch_slots()
        _poll_error = (result == [])
        if not _poll_error:
            _slots_data = result
        _last_poll = now


def build_metrics():
    maybe_poll()
    lines = []

    lines.append("# HELP llamacpp_slot_tokens_used Tokens currently occupying the KV cache slot")
    lines.append("# TYPE llamacpp_slot_tokens_used gauge")

    lines.append("# HELP llamacpp_slot_n_ctx Maximum context size for this slot")
    lines.append("# TYPE llamacpp_slot_n_ctx gauge")

    lines.append("# HELP llamacpp_slot_fill_ratio KV cache fill ratio (0.0–1.0)")
    lines.append("# TYPE llamacpp_slot_fill_ratio gauge")

    lines.append("# HELP llamacpp_slot_is_processing 1 if slot is actively generating tokens")
    lines.append("# TYPE llamacpp_slot_is_processing gauge")

    if _poll_error or not _slots_data:
        # Expose a single NaN-equivalent (0) so Grafana shows a gap rather than stale data
        lines.append('llamacpp_slot_tokens_used{slot="0"} 0')
        lines.append('llamacpp_slot_n_ctx{slot="0"} 0')
        lines.append('llamacpp_slot_fill_ratio{slot="0"} 0')
        lines.append('llamacpp_slot_is_processing{slot="0"} 0')
        return "\n".join(lines) + "\n"

    for slot in _slots_data:
        sid = str(slot.get("id", 0))
        # n_prompt_tokens = total prompt tokens for current/last request (build >=9307)
        # n_past does not exist in this build — see LSE tool v1.5.4 fix notes.
        n_past = slot.get("n_prompt_tokens", 0)
        # n_ctx = slot's context window size
        n_ctx = slot.get("n_ctx", 0)
        fill = (n_past / n_ctx) if n_ctx > 0 else 0.0
        # is_processing: true when the slot is actively generating
        processing = 1 if slot.get("is_processing", False) else 0

        lines.append(f'llamacpp_slot_tokens_used{{slot="{sid}"}} {n_past}')
        lines.append(f'llamacpp_slot_n_ctx{{slot="{sid}"}} {n_ctx}')
        lines.append(f'llamacpp_slot_fill_ratio{{slot="{sid}"}} {fill:.4f}')
        lines.append(f'llamacpp_slot_is_processing{{slot="{sid}"}} {processing}')

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
    # Prime the cache on startup
    _slots_data = fetch_slots()
    _last_poll = time.monotonic()
    print(f"llamacpp-slots-exporter v1.0 listening on :{PORT}")
    print(f"Polling {LLAMA_SLOTS_URL} every {POLL_INTERVAL}s")
    HTTPServer(("", PORT), Handler).serve_forever()
