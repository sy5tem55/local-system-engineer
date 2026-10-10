#!/usr/bin/env python3
"""Keyless Shodan web client (node4090) — scrapes www.shodan.io, no API key.

Replaces the REST API path (api.shodan.io + SHODAN_API_KEY) for the Shodan
MCP backend. The free-tier REST key on this account CANNOT search
(query_credits 0 — live-verified 2026-09-28), so the website is the working
default, not a fallback.

Endpoints (live-verified from node4090 2026-09-28, KB doc c77333d4b696ff3a):
  1. GET https://www.shodan.io/search/facet?query=<urlencoded>&facet=ip
     Server-rendered HTML. Total result count in
     <meta name="twitter:description" content="N results found for search
     query: ..."> (og:description too). Facet rows are anchors with
     href="/search?query=...ip%3A%22<IP%22" each followed by a
     <div class="value">count</div>.
  2. GET https://www.shodan.io/host/<ip>
     ~21MB server-rendered HTML. General info as
     <label>Key</label><div><strong>value</strong></div> pairs (City /
     Country / Organization). One section per open port carrying
     <span data-clipboard="IP:PORT">; banner body in
     <div class="card card-padding banner">. NO latitude/longitude in the
     HTML (the JS map fetches client-side) -> GPS degrades to '—'.

Politeness / safety:
  - host fetches serialized with >= 1.5 s spacing (no parallelism)
  - per-query facet cache + per-IP host cache (in-memory, process lifetime)
  - User-Agent rotated across 9 browser strings
  - Cloudflare challenge pages (grep 'just a moment' / 'cf-chl') raise
    ShodanWebBlocked (status 503) so the backend surfaces a distinct error
  - ToS note: Shodan designates the REST API as the sanctioned interface;
    website scraping is a gray zone — operator's call (stated 2026-09-28)

Row contract (consumed by shodan_mcp_server, preserving the API-era shape):
  {"device", "ip", "ports" (sorted unique ints),
   "location" (dict: city/country_name/country_code/organization),
   "geo" (pre-computed display string), "org", "gps": "—"}
"""

import asyncio
import html as html_mod
import itertools
import re
import time
from html.parser import HTMLParser

import httpx

WEB_BASE = "https://www.shodan.io"
SOURCE = "web"
MIN_SPACING_S = 1.5
GPS_DASH = "—"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_CHALLENGE_RE = re.compile(r"just a moment|cf-chl", re.IGNORECASE)

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:142.0) Gecko/20100101 Firefox/142.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
]
_ua_cycle = itertools.cycle(_UAS)

_facet_cache: dict = {}
_host_cache: dict = {}
_last_request_ts = 0.0


class ShodanWebError(RuntimeError):
    """A Shodan web-scrape failure. .status is the HTTP status for /api/search."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class ShodanWebBlocked(ShodanWebError):
    """Cloudflare challenge / block page — retry later, distinct from API errors."""

    def __init__(self, message: str = (
            "Shodan web source is showing a Cloudflare challenge page. "
            "Wait a few minutes and retry.")):
        super().__init__(message, status=503)


# ---------------------------------------------------------------- plumbing

def _next_ua() -> str:
    return next(_ua_cycle)


def _headers() -> dict:
    return {
        "User-Agent": _next_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


async def _throttle() -> None:
    """Enforce >= MIN_SPACING_S between any two outgoing requests."""
    global _last_request_ts
    wait = MIN_SPACING_S - (time.monotonic() - _last_request_ts)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request_ts = time.monotonic()


def _check_challenge(resp: httpx.Response, body_head: str) -> None:
    if resp.status_code != 200:
        raise ShodanWebError(
            f"www.shodan.io returned HTTP {resp.status_code}", status=502)
    if _CHALLENGE_RE.search(body_head):
        raise ShodanWebBlocked()


def clear_caches() -> None:
    _facet_cache.clear()
    _host_cache.clear()


# ---------------------------------------------------------------- facet

def _parse_total(body: str) -> int:
    """Total result count from a meta description tag, e.g.
    content="13,533,810 results found for search query: apache"."""
    for m in re.finditer(r"<meta[^>]*>", body, re.IGNORECASE):
        tag = m.group(0)
        if "description" not in tag.lower():
            continue
        n = re.search(r"(\d[\d,]*)\s+results?\s+found", tag, re.IGNORECASE)
        if n:
            return int(n.group(1).replace(",", ""))
    n = re.search(r"(\d[\d,]*)\s+results?\s+found", body, re.IGNORECASE)
    return int(n.group(1).replace(",", "")) if n else 0


_IP_HREF_RE = re.compile(r"ip(?:%3A|:)(?:%22|\")([\d.]+)")


class _FacetParser(HTMLParser):
    """Pairs facet anchors (href ... ip%3A%22<IP%22) with the following
    <div class="value">count</div>, in document order (rank order)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list = []
        self._pending_ip = None
        self._in_value_div = False
        self._value_text = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            m = _IP_HREF_RE.search(a.get("href", ""))
            if m:
                self._pending_ip = m.group(1)
        elif tag == "div" and "value" in (a.get("class") or "").split():
            self._in_value_div = True
            self._value_text = ""

    def handle_endtag(self, tag):
        if tag == "a":
            if self._pending_ip is not None and not self._in_value_div:
                # anchor never got a value div — keep it, a later one may be
                # its count (defensive; document order normally pairs 1:1)
                pass
        elif tag == "div" and self._in_value_div:
            self._in_value_div = False
            count = int(re.sub(r"[^\d]", "", self._value_text) or 0)
            if self._pending_ip:
                self.items.append({"ip": self._pending_ip, "count": count})
                self._pending_ip = None

    def handle_data(self, data):
        if self._in_value_div:
            self._value_text += data


async def fetch_facet(query: str, limit: int | None = None):
    """Keyless search via the facet page.

    GET https://www.shodan.io/search/facet?query=<urlencoded>&facet=ip
    Returns (total, rows) where rows = [{"ip", "count"}, ...] in descending
    banner-count order. Cached per query. Optional limit caps the rows.
    """
    qkey = query.strip()
    if not qkey:
        raise ShodanWebError("query is empty")
    if qkey in _facet_cache:
        total, rows = _facet_cache[qkey]
    else:
        await _throttle()
        async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                f"{WEB_BASE}/search/facet",
                params={"query": qkey, "facet": "ip"},
                headers=_headers())
        body = resp.text
        _check_challenge(resp, body[:200000])
        parser = _FacetParser()
        parser.feed(body)
        total = _parse_total(body)
        rows = parser.items
        if len(_facet_cache) > 256:
            _facet_cache.clear()
        _facet_cache[qkey] = (total, rows)
    if limit is not None:
        try:
            limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            raise ShodanWebError(f"limit must be an integer 1-100, got {limit!r}")
        rows = rows[:limit]
    return total, rows


# ---------------------------------------------------------------- host

_COUNTRY_CODE = {
    "United States": "US", "United Kingdom": "GB", "Germany": "DE",
    "France": "FR", "Netherlands": "NL", "Brazil": "BR", "India": "IN",
    "China": "CN", "Russia": "RU", "Indonesia": "ID", "Singapore": "SG",
    "Japan": "JP", "South Korea": "KR", "Australia": "AU", "Canada": "CA",
    "Mexico": "MX", "Turkey": "TR", "South Africa": "ZA", "United Arab Emirates": "AE",
    "Israel": "IL", "Poland": "PL", "Italy": "IT", "Spain": "ES",
    "Sweden": "SE", "Norway": "NO", "Denmark": "DK", "Finland": "FI",
    "Switzerland": "CH", "Austria": "AT", "Belgium": "BE", "Ireland": "IE",
    "Portugal": "PT", "Czech Republic": "CZ", "Romania": "RO", "Hungary": "HU",
    "Egypt": "EG", "Argentina": "AR", "Chile": "CL", "Colombia": "CO",
    "Philippines": "PH", "Thailand": "TH", "Vietnam": "VN", "Malaysia": "MY",
    "New Zealand": "NZ", "Nigeria": "NG", "Kenya": "KE", "Saudi Arabia": "SA",
    "Pakistan": "PK", "Bangladesh": "BD", "Morocco": "MA",
}


def _grid_info(body: str) -> dict:
    """Parse the host-page grid-table label/value pairs (City / Country /
    Organization). Country 'Name (XX)' style is split into name + ISO code;
    otherwise the code comes from a small name map (best effort, '' if unknown).
    """
    info = {"city": "", "country_name": "", "country_code": "", "organization": ""}
    for key, field in (("City", "city"), ("Country", "country_name"),
                       ("Organization", "organization")):
        m = re.search(
            rf"<label[^>]*>\s*{key}\s*</label>\s*<div[^>]*>"
            rf"(?:\s*<strong[^>]*>)?\s*([^<]+)",
            body, re.IGNORECASE)
        if not m:
            continue
        val = html_mod.unescape(m.group(1)).strip()
        if field == "country_name":
            name, sep, rest = val.rpartition("(")
            code = rest.rstrip(")").strip()
            if sep and re.fullmatch(r"[A-Z]{2}", code):
                info["country_name"] = name.strip()
                info["country_code"] = code
            else:
                info["country_name"] = val
        else:
            info[field] = val
    if not info["country_code"] and info["country_name"]:
        info["country_code"] = _COUNTRY_CODE.get(info["country_name"], "")
    return info


def _device_from_banner(body: str) -> str:
    """Best device label from the first port's banner text (product/version
    strings appear verbatim in banner bodies). 'unknown' when none parseable."""
    m = re.search(
        r"<div[^>]*class=\"[^\"]*card-padding banner[^\"]*\"[^>]*>(.*?)</div>",
        body, re.DOTALL | re.IGNORECASE)
    if not m:
        return "unknown"
    text = html_mod.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            return line[:120]
    return "unknown"


async def fetch_host(ip: str):
    """Keyless host detail via https://www.shodan.io/host/<ip>.

    Returns {"ip", "ports" (sorted unique ints), "device", "location",
    "org", "gps": "—"}. Cached per IP; >= 1.5 s spacing enforced.
    """
    if ip in _host_cache:
        return _host_cache[ip]
    await _throttle()
    async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{WEB_BASE}/host/{ip}", headers=_headers())
    body = resp.text
    _check_challenge(resp, body[:200000])
    info = _grid_info(body)
    ports = sorted({int(p) for p in re.findall(
        r"data-clipboard=\"[^\"]*?:(\d+)\"", body)})
    row = {
        "ip": ip,
        "ports": ports,
        "device": _device_from_banner(body),
        "location": info,
        "org": info.get("organization", ""),
        "gps": GPS_DASH,
    }
    if len(_host_cache) > 512:
        _host_cache.clear()
    _host_cache[ip] = row
    return row


# ---------------------------------------------------------------- search

def _geo_str(location: dict) -> str:
    """Display geo, same rule as the API-era backend:
    'City, CC' -> 'Country (CC)' -> country/CC -> '—'."""
    city = location.get("city") or ""
    cc = location.get("country_code") or ""
    cname = location.get("country_name") or ""
    if city:
        return f"{city}, {cc}" if cc else city
    if cname and cc and cname != cc:
        return f"{cname} ({cc})"
    return cname or cc or GPS_DASH


async def search(query: str, limit: int = 20):
    """Keyless end-to-end search mirroring shodan_fetch_rows' contract:
    returns (total, rows).

    rows = [{"device", "ip", "ports" (sorted unique ints), "location" (dict),
             "geo" (display string), "org", "gps": "—"}]
    Facet results are cached per query; host fetches are spaced >= 1.5 s.
    """
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        raise ShodanWebError(f"limit must be an integer 1-100, got {limit!r}")
    total, facet_rows = await fetch_facet(query)
    rows = []
    for fr in facet_rows[:limit]:
        host = await fetch_host(fr["ip"])
        rows.append({
            "device": host["device"],
            "ip": host["ip"],
            "ports": host["ports"],
            "location": host["location"],
            "geo": _geo_str(host["location"]),
            "org": host["org"],
            "gps": GPS_DASH,
        })
    return total, rows
