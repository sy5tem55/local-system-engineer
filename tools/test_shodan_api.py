#!/usr/bin/env python3
"""End-to-end tests for the /api/search JSON endpoint (mock Shodan API: no
real key, no real network). Proves the thin endpoint + shared code path:
grouping, JSON shape, error paths, and that the MCP markdown tool still
renders from the same shodan_fetch_rows result.

Run: /home/sy5/miniforge3/bin/python /home/sy5/projects/local-system-engineer/tools/test_shodan_api.py
Exits non-zero on any failure.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))

# --- mock Shodan API ---------------------------------------------------------

MOCK_MATCHES = {
    "total": 2,
    "matches": [
        {"ip": 1616761883, "ip_str": "96.93.212.27", "port": 443,
         "product": "nginx", "version": "1.18.0", "os": None,
         "hostnames": ["three.webapplify.net"], "http": {"title": "Welcome"},
         "location": {"city": "Denver", "region_code": "CO",
                      "longitude": -104.9078, "latitude": 39.7301,
                      "country_code": "US", "country_name": "United States"}},
        {"ip": 1616761883, "ip_str": "96.93.212.27", "port": 80,
         "product": "nginx", "version": None, "os": None,
         "hostnames": ["three.webapplify.net"], "http": {},
         "location": {"city": "Denver", "region_code": "CO",
                      "longitude": -104.9078, "latitude": 39.7301,
                      "country_code": "US", "country_name": "United States"}},
        {"ip": 3104568883, "ip_str": "185.11.246.51", "port": 8080,
         "product": None, "version": None, "os": None, "hostnames": [],
         "http": {}, "location": None},
    ],
}

SEEN = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/shodan/host/search"):
            SEEN.update(parse_qs(urlparse(self.path).query))
            body = json.dumps(MOCK_MATCHES).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


_srv = HTTPServer(("127.0.0.1", 0), _Handler)
_port = _srv.server_address[1]
threading.Thread(target=_srv.serve_forever, daemon=True).start()

os.environ["SHODAN_API_BASE"] = f"http://127.0.0.1:{_port}"
os.environ["SHODAN_API_KEY"] = "test-key-123"

sys.path.insert(0, HERE)
import shodan_mcp_server as S  # noqa: E402
from shodan_mcp_server import (  # noqa: E402
    ShodanSearchError, api_search, build_http_app, mcp, shodan_search_impl,
)
from starlette.requests import Request  # noqa: E402

import httpx  # noqa: E402

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name} {detail}")
        failures.append(name)


def make_request(query_str: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/search",
                    "query_string": query_str.encode(), "headers": []})


async def main():
    # 1. happy path: grouping + JSON shape
    resp = await api_search(make_request("query=port%3A21&limit=5"))
    check("api: 200", resp.status_code == 200, resp.status_code)
    body = json.loads(resp.body)
    check("api: query echoed", body.get("query") == "port:21", body)
    check("api: total", body.get("total") == 2, body)
    rows = body.get("rows", [])
    check("api: 3 matches grouped -> 2 host rows", len(rows) == 2, rows)
    r0 = rows[0]
    check("api: row0 ip", r0.get("ip") == "96.93.212.27", r0)
    check("api: row0 merged+sorted ports", r0.get("ports") == [80, 443], r0)
    check("api: row0 device", r0.get("device") == "nginx", r0)
    check("api: row0 geo", r0.get("geo") == "Denver, US", r0)
    check("api: row0 gps", r0.get("gps") == "39.7301, -104.9078", r0)
    r1 = rows[1]
    check("api: row1 sparse geo placeholder", r1.get("geo") == "\u2014", r1)
    check("api: row1 sparse gps placeholder", r1.get("gps") == "\u2014", r1)
    check("api: row1 ports", r1.get("ports") == [8080], r1)
    check("api: location dict passthrough",
          (r0.get("location") or {}).get("city") == "Denver", r0)
    check("api: upstream key passed", SEEN.get("key") == ["test-key-123"], SEEN)
    check("api: upstream query passed", SEEN.get("query") == ["port:21"], SEEN)
    check("api: upstream page pinned 1", SEEN.get("page") == ["1"], SEEN)

    # 2. error paths
    resp = await api_search(make_request("query=port%3A21&limit=abc"))
    check("api: bad limit -> 400", resp.status_code == 400, resp.status_code)
    resp = await api_search(make_request("query="))
    check("api: empty query -> 400", resp.status_code == 400, resp.status_code)

    saved_key = os.environ["SHODAN_API_KEY"]
    os.environ["SHODAN_API_KEY"] = ""
    try:
        resp = await api_search(make_request("query=port%3A21"))
        check("api: missing key -> 500", resp.status_code == 500, resp.status_code)
        err = json.loads(resp.body).get("error", "")
        check("api: missing key message",
              "SHODAN_API_KEY is not set" in err, resp.body)
    finally:
        os.environ["SHODAN_API_KEY"] = saved_key

    saved_base = S.SHODAN_API_BASE
    S.SHODAN_API_BASE = "http://127.0.0.1:1"  # closed port
    try:
        resp = await api_search(make_request("query=port%3A21"))
        check("api: unreachable upstream -> 502", resp.status_code == 502,
              resp.status_code)
    finally:
        S.SHODAN_API_BASE = saved_base

    check("err: ShodanSearchError default status 500",
          ShodanSearchError("x").status == 500)

    # 3. markdown tool renders from the SAME code path
    md = await shodan_search_impl("port:21", 5)
    check("tool: markdown row from shared path",
          "| nginx | 96.93.212.27 | 80, 443 | Denver, US | 39.7301, -104.9078 |"
          in md, md)
    check("tool: header intact",
          "| Device | IP | Ports | Geo Location | GPS Coordinates |" in md, md)

    # 4. route wiring: /health sibling reachable through the wrapped ASGI app
    app = build_http_app(mcp, "", "*")
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
        check("app: /health via wrapped ASGI",
              r.status_code == 200 and "shodan-mcp" in r.text,
              f"{r.status_code} {r.text[:120]}")


if failures:
    print(f"RESULT: {len(failures)} FAILED: {failures}")
    sys.exit(1)
print("RESULT: ALL TESTS PASSED")
