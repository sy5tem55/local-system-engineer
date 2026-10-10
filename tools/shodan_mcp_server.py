#!/usr/bin/env python3
"""Standalone Shodan MCP server (node4090) — keyless.

Exposes a single MCP tool, shodan_search(query, limit), over streamable HTTP.
It scrapes the public Shodan website (www.shodan.io — /search/facet + /host)
via tools/shodan_web_client.py (no API key; the free-tier REST key on this
account has 0 query credits — live-verified 2026-09-28) and returns a markdown
table:

    | Device | IP | Ports | Geo Location | GPS Coordinates |

It also exposes GET /api/search — a thin JSON endpoint with the SAME code
path (shodan_fetch_rows) for the shodan-web UI, whose tRPC backend is a typed
proxy to it. No Shodan logic lives outside shodan_mcp_server.py +
shodan_web_client.py.

Design notes (see KB doc c77333d4b696ff3a for live-verified endpoint facts):
  - Facet search returns IPs ranked by matching-banner count; host detail
    pages supply ports (data-clipboard spans), geo (grid-table labels), org,
    and device (first banner line).
  - GPS is unavailable keyless (host-page lat/lon are fetched client-side by
    the JS map) — the GPS Coordinates column shows '—'.
  - Host fetches are serialized with >= 1.5 s spacing, results are cached per
    query/IP, and UAs rotate across 9 browser strings (shodan_web_client.py).
  - Cloudflare challenge pages are detected ('just a moment' / 'cf-chl') and
    surfaced as a distinct 503 error, not a generic failure.

Valves (env, defaults in parentheses):
  SHODAN_MCP_HOST       (127.0.0.1)
  SHODAN_MCP_PORT       (9702)
  SHODAN_MCP_TOKEN      ("" = no auth, warning printed; when set, guards
                        both /mcp and /api/search — the web UI must send it)
  SHODAN_MCP_CORS_ORIGIN (*)

Pattern source: tools/goethe_mcp.py build_http_app/_TokenGuard (ASGI direct
wrap, no Starlette Mount) + FastMCP.custom_route for /health and /api/search
(verified present in installed mcp 1.28.1; custom routes bypass FastMCP auth,
and the local TokenGuard exempts /health so `curl -sf .../health` works
unauthenticated; /api/search is NOT exempt).
"""

import os
import sys

from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

try:  # imported as part of the tools package (repo root on sys.path)
    from . import shodan_web_client
except ImportError:  # run as a script, or tests with tools/ on sys.path
    import shodan_web_client

VERSION = "0.3.0"
SHODAN_MCP_HOST = os.environ.get("SHODAN_MCP_HOST", "127.0.0.1")
SHODAN_MCP_PORT = int(os.environ.get("SHODAN_MCP_PORT", "9702"))
SHODAN_MCP_TOKEN = os.environ.get("SHODAN_MCP_TOKEN", "")
SHODAN_MCP_CORS_ORIGIN = os.environ.get("SHODAN_MCP_CORS_ORIGIN", "*")
MAX_PORTS_SHOWN = 8


class ShodanSearchError(RuntimeError):
    """A Shodan search failure (keyless web source). .status is the HTTP
    status for /api/search (503 = Cloudflare challenge, 502 = unreachable)."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def _device_label(matches: list) -> str:
    """Best device label for a host's matches (formatting helper kept for
    the test contract):
    product -> http.title -> hostnames[0] -> os -> 'unknown'."""
    for m in matches:
        if m.get("product"):
            return str(m["product"])
    for m in matches:
        title = (m.get("http") or {}).get("title")
        if title:
            return str(title)
    for m in matches:
        hostnames = m.get("hostnames") or []
        if hostnames:
            return str(hostnames[0])
    for m in matches:
        if m.get("os"):
            return str(m["os"])
    return "unknown"


def _format_ports(ports: list) -> str:
    ports = sorted(ports)
    shown = ", ".join(str(p) for p in ports[:MAX_PORTS_SHOWN])
    extra = len(ports) - MAX_PORTS_SHOWN
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def _geo_str(location: dict) -> str:
    """Display geo for a row: 'City, CC' -> 'Country (CC)' -> country/CC -> '—'."""
    city = location.get("city")
    cc = location.get("country_code")
    cname = location.get("country_name")
    if city:
        return f"{city}, {cc}" if cc else str(city)
    if cname and cc and cname != cc:
        return f"{cname} ({cc})"
    return cname or cc or "—"


def _gps_str(location: dict) -> str:
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is not None and lon is not None:
        return f"{lat}, {lon}"
    return "—"


def _build_table(query: str, total: int, rows: list) -> str:
    lines = [
        f"# Shodan search: {query}",
        f"Total matches: {total} | Hosts shown: {len(rows)}",
        "",
        "| Device | IP | Ports | Geo Location | GPS Coordinates |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['device']} | {r['ip']} | {r['ports']} | "
            f"{_geo_str(r['location'])} | {_gps_str(r['location'])} |"
        )
    if not rows:
        lines.append("| (no results) | — | — | — | — |")
    return "\n".join(lines)


async def shodan_fetch_rows(query: str, limit: int = 20):
    """Call the keyless Shodan web source and return (total, rows).

    The single Shodan code path: both the MCP tool (markdown) and the
    /api/search JSON endpoint build their output from this result.
    Delegates to tools/shodan_web_client.py (www.shodan.io /search/facet +
    /host — no API key, >= 1.5 s spacing, per-query cache, Cloudflare
    challenge detection).

    rows: [{"device", "ip", "ports" (sorted unique ints), "location" (dict),
            "geo", "org", "gps" ('—')}]
    Raises ShodanSearchError on web failure (Cloudflare -> 503, else 502).
    """
    try:
        return await shodan_web_client.search(query, limit)
    except shodan_web_client.ShodanWebError as e:
        raise ShodanSearchError(str(e), status=e.status)


async def shodan_search_impl(query: str, limit: int = 20) -> str:
    """Run the Shodan search and return the markdown table string."""
    try:
        total, rows = await shodan_fetch_rows(query, limit)
    except ShodanSearchError as e:
        return f"ERROR: {e}"
    table_rows = [
        {"device": r["device"], "ip": r["ip"],
         "ports": _format_ports(r["ports"]), "location": r["location"]}
        for r in rows
    ]
    return _build_table(query, total, table_rows)


# ---------------------------------------------------------------- MCP wiring

mcp = FastMCP("Shodan MCP", host=SHODAN_MCP_HOST, port=SHODAN_MCP_PORT)
mcp._mcp_server.version = VERSION


@mcp.tool()
async def shodan_search(query: str, limit: int = 20) -> str:
    """Search Shodan (public internet device/port database) and return a
    markdown table with columns: Device, IP, Ports, Geo Location, GPS
    Coordinates. One row per host (top hosts by matching-banner count; Ports
    lists the open ports Shodan found on it). query uses Shodan's
    'filter:value' syntax, e.g. 'port:21', 'product:cisco', 'webcam
    country:DE'. limit (1-100, default 20) caps the number of host rows.
    Keyless — uses the www.shodan.io web source; the GPS Coordinates column
    shows '—' (coordinates are client-side only). Returns an ERROR string if
    the web source fails or serves a Cloudflare challenge page."""
    return await shodan_search_impl(query, limit)


@mcp.custom_route("/health", methods=["GET"])
async def health(request) -> Response:
    return JSONResponse({
        "status": "ok",
        "service": "shodan-mcp",
        "version": VERSION,
        "source": "web",
        "keyless": True,
        "web_base": shodan_web_client.WEB_BASE,
    })


@mcp.custom_route("/api/search", methods=["GET"])
async def api_search(request) -> Response:
    """Thin JSON endpoint for the shodan-web UI (whose tRPC backend is a
    typed proxy to this route). Same code path as the MCP tool.

    GET /api/search?query=port:21&limit=20
      200  {"query","total","rows":[{"device","ip","ports","geo","gps","org","location"}]}
      400  missing/bad query or limit param
      503  Cloudflare challenge page from www.shodan.io
      502  web source unreachable / non-200
    """
    query = request.query_params.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "query parameter is required"},
                            status_code=400)
    limit_raw = request.query_params.get("limit", "20")
    try:
        limit = int(limit_raw)
    except ValueError:
        return JSONResponse(
            {"error": f"limit must be an integer, got {limit_raw!r}"},
            status_code=400)
    try:
        total, rows = await shodan_fetch_rows(query, limit)
    except ShodanSearchError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    return JSONResponse({
        "query": query,
        "total": total,
        "rows": [
            {"device": r["device"], "ip": r["ip"], "ports": r["ports"],
             "geo": r.get("geo") or _geo_str(r["location"]),
             "gps": r.get("gps", "—"),
             "org": r.get("org", ""),
             "location": r["location"]}
            for r in rows
        ],
    })


def build_http_app(mcp, token: str, cors_origin: str):
    """CORSMiddleware -> _TokenGuard (if token set) -> FastMCP ASGI app.

    Wraps the ASGI callable directly (no Starlette Mount — Mount strips the
    leading '/' and 404s /mcp). /health is exempt from the token guard so a
    plain `curl -sf http://host:port/health` works for liveness checks.
    /api/search is NOT exempt: when SHODAN_MCP_TOKEN is set, the web UI must
    send the same Bearer token.
    """
    inner = mcp.streamable_http_app()
    origins = [cors_origin] if (cors_origin and cors_origin != "*") else ["*"]
    app = inner

    if token:
        _bearer = f"Bearer {token}"

        class _TokenGuard:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if (scope["type"] == "http"
                        and scope.get("method") != "OPTIONS"
                        and scope.get("path") != "/health"):
                    headers = dict(scope.get("headers", []))
                    auth = headers.get(b"authorization", b"").decode().strip()
                    received = auth[7:] if auth.lower().startswith("bearer ") else auth
                    if received != token and auth != _bearer:
                        resp = Response(
                            '{"error":"unauthorized"}',
                            status_code=401,
                            media_type="application/json",
                        )
                        await resp(scope, receive, send)
                        return
                await self.app(scope, receive, send)

        app = _TokenGuard(app)

    return CORSMiddleware(
        app,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def main() -> None:
    if SHODAN_MCP_HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"[shodan_mcp] WARNING: binding {SHODAN_MCP_HOST} exposes the MCP "
              "endpoint to the network. Use 127.0.0.1.", file=sys.stderr)
    if not SHODAN_MCP_TOKEN:
        print("[shodan_mcp] WARNING: no SHODAN_MCP_TOKEN set - HTTP endpoint has "
              "NO auth (relying on localhost binding only).", file=sys.stderr)

    import uvicorn

    app = build_http_app(mcp, SHODAN_MCP_TOKEN, SHODAN_MCP_CORS_ORIGIN)
    print(f"[shodan_mcp] serving streamable-HTTP on "
          f"http://{SHODAN_MCP_HOST}:{SHODAN_MCP_PORT}/mcp "
          f"(token={'on' if SHODAN_MCP_TOKEN else 'OFF'}, "
          f"source=web keyless=True, web_base={shodan_web_client.WEB_BASE})",
          file=sys.stderr)
    uvicorn.run(app, host=SHODAN_MCP_HOST, port=SHODAN_MCP_PORT, log_level="info")


if __name__ == "__main__":
    main()
