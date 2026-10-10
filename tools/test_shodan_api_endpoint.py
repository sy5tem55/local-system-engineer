#!/usr/bin/env python3
"""Mock tests for tools/shodan_mcp_server.py GET /api/search endpoint.

No Shodan API key and NO network required: the httpx.AsyncClient used by
shodan_fetch_rows is replaced with a fake via unittest.mock.patch.

Covers:
  - row-building helper groups multiple service banners per ip_str into one row
  - /api/search route returns JSON rows (device/ip/ports/geo/gps/location)
  - missing SHODAN_API_KEY -> graceful 503 JSON error (no crash)
  - bad request params -> 400 JSON error

Run (from the tools/ directory):
    python -m unittest test_shodan_api_endpoint -v
"""

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shodan_mcp_server as server  # noqa: E402


SAMPLE_MATCHES = [
    # three service banners on the same host -> must group into ONE row
    {"ip_str": "1.2.3.4", "port": 21, "product": "vsftpd",
     "location": {"city": "Nuremberg", "country_code": "DE",
                  "country_name": "Germany",
                  "latitude": 49.45, "longitude": 11.08}},
    {"ip_str": "1.2.3.4", "port": 22, "product": "OpenSSH",
     "location": {"city": "Nuremberg", "country_code": "DE",
                  "country_name": "Germany",
                  "latitude": 49.45, "longitude": 11.08}},
    {"ip_str": "1.2.3.4", "port": 80, "hostnames": ["ftp.example.com"],
     "http": {"title": "Apache"},
     "location": {"city": "Nuremberg", "country_code": "DE",
                  "country_name": "Germany",
                  "latitude": 49.45, "longitude": 11.08}},
    # a second host
    {"ip_str": "5.6.7.8", "port": 443, "product": "nginx",
     "location": {"country_code": "NL", "country_name": "Netherlands"}},
]
SAMPLE_PAYLOAD = {"matches": SAMPLE_MATCHES, "total": 4}


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _fake_client_factory(payload, status_code=200):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None):
            return _FakeResponse(payload, status_code)

    return _FakeClient


def _request(params: dict):
    """Minimal stand-in for the Starlette Request (only query_params.get used)."""
    return SimpleNamespace(query_params=params)


def _env_with(key_value=None):
    env = {k: v for k, v in os.environ.items() if k != "SHODAN_API_KEY"}
    if key_value is not None:
        env["SHODAN_API_KEY"] = key_value
    return env


class FetchRowsTests(unittest.IsolatedAsyncioTestCase):
    async def test_groups_banners_per_ip(self):
        with mock.patch.dict(os.environ, _env_with("test-key-not-real"), clear=True), \
                mock.patch.object(server.httpx, "AsyncClient",
                                  _fake_client_factory(SAMPLE_PAYLOAD)):
            total, rows = await server.shodan_fetch_rows("port:21", limit=20)
        self.assertEqual(total, 4)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["ip"], "1.2.3.4")
        self.assertEqual(first["ports"], [21, 22, 80])
        self.assertEqual(first["device"], "vsftpd")  # product has priority
        second = rows[1]
        self.assertEqual(second["ip"], "5.6.7.8")
        self.assertEqual(second["ports"], [443])

    async def test_missing_key_raises_503(self):
        with mock.patch.dict(os.environ, _env_with(), clear=True):
            with self.assertRaises(server.ShodanSearchError) as cm:
                await server.shodan_fetch_rows("port:21")
        self.assertEqual(cm.exception.status, 503)
        self.assertIn("SHODAN_API_KEY", str(cm.exception))

    async def test_limit_caps_rows(self):
        with mock.patch.dict(os.environ, _env_with("test-key-not-real"), clear=True), \
                mock.patch.object(server.httpx, "AsyncClient",
                                  _fake_client_factory(SAMPLE_PAYLOAD)):
            total, rows = await server.shodan_fetch_rows("port:21", limit=1)
        self.assertEqual(total, 4)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ip"], "1.2.3.4")


class ApiSearchRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_returns_json_rows(self):
        req = _request({"query": "port:21", "limit": "10"})
        with mock.patch.dict(os.environ, _env_with("test-key-not-real"), clear=True), \
                mock.patch.object(server.httpx, "AsyncClient",
                                  _fake_client_factory(SAMPLE_PAYLOAD)):
            resp = await server.api_search(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.body)
        self.assertEqual(body["query"], "port:21")
        self.assertEqual(body["total"], 4)
        self.assertEqual(len(body["rows"]), 2)
        row0 = body["rows"][0]
        for key in ("device", "ip", "ports", "geo", "gps", "location"):
            self.assertIn(key, row0)
        self.assertEqual(row0["ip"], "1.2.3.4")
        self.assertEqual(row0["ports"], [21, 22, 80])
        self.assertEqual(row0["geo"], "Nuremberg, DE")
        self.assertEqual(row0["gps"], "49.45, 11.08")

    async def test_route_missing_key_is_graceful_503_json(self):
        req = _request({"query": "port:21"})
        with mock.patch.dict(os.environ, _env_with(), clear=True):
            resp = await server.api_search(req)
        self.assertEqual(resp.status_code, 503)
        body = json.loads(resp.body)
        self.assertIn("error", body)
        self.assertIn("SHODAN_API_KEY", body["error"])
        self.assertNotIn("rows", body)

    async def test_route_missing_query_param_is_400(self):
        resp = await server.api_search(_request({}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.body))

    async def test_route_bad_limit_is_400(self):
        resp = await server.api_search(
            _request({"query": "port:21", "limit": "abc"}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.body))


if __name__ == "__main__":
    unittest.main()
