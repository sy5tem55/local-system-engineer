#!/usr/bin/env python3
"""
test_hermes_inbox.py — stage test the Hermes -> LSE inbound channel (v1.7.0-b).

The "Warhol phone": LSE can now pick up calls FROM Hermes. Hermes holds an
outbox and attaches `hermes_messages` to any gateway reply; check_hermes_inbox()
surfaces them. Hermes's call_lse/outbox isn't built yet, so this harness:

  TEST 1  unit     — _format_hermes_messages renders a sample envelope (no net).
  TEST 2  mock     — a local HTTP server returns a chat-completions JSON WITH a
                     hermes_messages[] field; point the tool at it and confirm
                     check_hermes_inbox() surfaces the message. Proves the entire
                     LSE handset end-to-end without waiting on Hermes.
  TEST 3  live     — dial the REAL gateway (:8642). Until Hermes attaches
                     hermes_messages, expect "INBOX EMPTY" — that alone proves
                     transport + auth + parse against production.

Run from project root on LUCIFER:  python3 scripts/test_hermes_inbox.py
"""
import http.server
import json
import socket
import sys
import threading
import types
from pathlib import Path

# Stub elasticsearch (only needed at import; not used by the inbox methods).
if "elasticsearch" not in sys.modules:
    try:
        import elasticsearch  # noqa: F401
    except ImportError:
        m = types.ModuleType("elasticsearch")
        m.Elasticsearch = object
        sys.modules["elasticsearch"] = m

import importlib.util

TOOL = Path(__file__).parent.parent / "tools" / "cogitator-v1.7.15.py"
spec = importlib.util.spec_from_file_location("cog", TOOL)
cog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cog)

SAMPLE = [
    {"correlation_id": "hz-20260613-0001", "kind": "ask", "priority": "urgent",
     "body": "node3090 llama-server OOM at 14:02; restart requested", "want_reply": True},
    {"correlation_id": "hz-20260613-0002", "kind": "notify", "priority": "info",
     "body": "nightly backup completed"},
]

passed = failed = 0
def ok(label, cond):
    global passed, failed
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    passed += cond; failed += (not cond)


def test_unit(t):
    print("\nTEST 1 — _format_hermes_messages (unit, no network):")
    ok("empty -> ''", t._format_hermes_messages({}) == "")
    ok("malformed -> ''", t._format_hermes_messages({"hermes_messages": "x"}) == "")
    out = t._format_hermes_messages({"hermes_messages": SAMPLE})
    ok("renders correlation_id hz-...0001", "hz-20260613-0001" in out)
    ok("renders kind/priority (ask/urgent)", "(ask/urgent)" in out)
    ok("flags reply requested", "[reply requested]" in out)
    ok("includes reply instruction", "context='correlation_id=" in out)
    print("  ---- rendered ----")
    print("  " + out.replace("\n", "\n  "))


class _MockGateway(http.server.BaseHTTPRequestHandler):
    payload = {"choices": [{"message": {"content": ""}}], "hermes_messages": SAMPLE}
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); self.rfile.read(n)
        body = json.dumps(self.payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *a):  # silence
        pass


def test_mock(t):
    print("\nTEST 2 — mock gateway returns hermes_messages (end-to-end LSE handset):")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = http.server.HTTPServer(("127.0.0.1", port), _MockGateway)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    saved = t.valves.HERMES_API_URL
    try:
        t.valves.HERMES_API_URL = f"http://127.0.0.1:{port}"
        res = t.check_hermes_inbox()
        ok("not an ERROR", not res.startswith("ERROR:"))
        ok("not empty", "INBOX EMPTY" not in res)
        ok("surfaces urgent ask", "hz-20260613-0001" in res and "(ask/urgent)" in res)
        print("  ---- check_hermes_inbox() returned ----")
        print("  " + res.replace("\n", "\n  "))
    finally:
        t.valves.HERMES_API_URL = saved
        srv.shutdown()


def test_live(t):
    print(f"\nTEST 3 — live gateway {t.valves.HERMES_API_URL} (real connectivity):")
    res = t.check_hermes_inbox()
    print("  result:", res[:160].replace("\n", " | "))
    if res.startswith("ERROR:"):
        ok("gateway reachable", False)
        print("  (gateway unreachable — check :8642 / key / network)")
    else:
        ok("gateway reachable + parsed", True)
        print("  NOTE: 'INBOX EMPTY' is EXPECTED until Hermes attaches hermes_messages.")


if __name__ == "__main__":
    t = cog.Tools()
    test_unit(t)
    test_mock(t)
    if "--no-live" not in sys.argv:
        test_live(t)
    print(f"\n{'ALL LOCAL TESTS PASS' if failed == 0 else str(failed)+' FAILURES'} "
          f"({passed} passed)")
    sys.exit(1 if failed else 0)
