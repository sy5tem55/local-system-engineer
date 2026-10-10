"""Active prober for services on node3090 (192.168.5.41).

Feeds the /webSearch dashboard "node3090 remote services" panel. A daemon
thread polls the probe endpoints every PROBE_INTERVAL_S seconds and writes
/opt/local-se/state/node3090_services.json atomically; the gateway's read-only
route /webSearch/nodes serves that file (same pattern as /webSearch/quota).

Stdlib only. No import-time side effects. The prober never auto-wakes
node3090: unreachable => up=False, error recorded, next tick.
"""

import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone

NODE3090_IP = "192.168.5.41"
STATE_FILE = "/opt/local-se/state/node3090_services.json"
PROBE_INTERVAL_S = 30
REQUEST_TIMEOUT_S = 5.0

SERVICES = [
    {"name": "firecrawl (node3090)",
     "url": "http://%s:3002/" % NODE3090_IP},
    {"name": "camofox-browser (node3090)",
     "url": "http://%s:9377/health" % NODE3090_IP},
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Node3090Prober:
    """Background prober; start() launches a single daemon thread."""

    def __init__(self, state_file=STATE_FILE, interval_s=PROBE_INTERVAL_S,
                 services=None):
        self.state_file = state_file
        self.interval_s = interval_s
        self.services = [dict(s) for s in (services or SERVICES)]
        for s in self.services:
            s.update({"up": False, "last_ok_ts": None, "last_check_ts": None,
                      "latency_ms": None, "last_error": "not probed yet"})
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run,
                                        name="node3090-prober", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:  # prober must never kill the gateway
                with self._lock:
                    for s in self.services:
                        s["up"] = False
                        s["last_error"] = "prober tick failed: %s" % e
            self._stop.wait(self.interval_s)

    def _probe_one(self, svc):
        t0 = time.monotonic()
        req = urllib.request.Request(svc["url"], method="GET")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            status = resp.status
            resp.read(0)
        ms = int((time.monotonic() - t0) * 1000)
        if not (200 <= status < 400):
            raise RuntimeError("HTTP %s" % status)
        svc["up"] = True
        svc["last_ok_ts"] = _now_iso()
        svc["latency_ms"] = ms
        svc["last_error"] = None

    def _tick(self):
        now = _now_iso()
        with self._lock:
            for s in self.services:
                s["last_check_ts"] = now
                try:
                    self._probe_one(s)
                except Exception as e:
                    s["up"] = False
                    s["last_error"] = str(e)[:200]
            payload = {
                "node": "node3090 (%s)" % NODE3090_IP,
                "probe_interval_s": self.interval_s,
                "updated_at": now,
                "services": [dict(s) for s in self.services],
            }
        self._write_atomic(payload)

    def _write_atomic(self, payload):
        d = os.path.dirname(self.state_file)
        os.makedirs(d, exist_ok=True)
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, self.state_file)


def snapshot():
    """Current state from the state file (for the /webSearch/nodes route)."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None
