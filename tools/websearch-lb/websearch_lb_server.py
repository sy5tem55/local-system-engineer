#!/usr/bin/env python3
"""WebSearch LB - standalone MCP web-search load balancer (node4090).

Routes queries across no-card-required search backends with per-backend
circuit breaking and failover:

    default priority: jina -> firecrawl -> exa -> searxng -> ddg
    override:         WEBSEARCH_LB_PRIORITY="firecrawl,exa,ddg,searxng"

Live-verified 2026-10-07 (ledger ed483269, design /tmp/lse/websearch-lb-design.md):
  jina       GET  https://s.jina.ai/{query}          Bearer key (JINA_API_KEY), ?count=N
  exa        POST https://api.exa.ai/search          x-api-key, metered
  firecrawl  POST https://api.firecrawl.dev/v1/search  KEYLESS
  searxng    GET  http://localhost:8088/search?format=json  local, engines vary
  ddg        ddgs python lib (no key)
  jina reader GET  https://r.jina.ai/{url}            KEYLESS reader, 20 RPM (read_url tool)

MCP tools: web_search_balanced, read_url.  HTTP: /mcp (streamable) + /health + /stats.
Config: env only - never put secrets in this file.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

HOST = os.environ.get("WEBSEARCH_LB_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBSEARCH_LB_PORT", "9703"))
TIMEOUT_S = float(os.environ.get("WEBSEARCH_LB_TIMEOUT_S", "10"))
COOLDOWN_S = float(os.environ.get("WEBSEARCH_LB_COOLDOWN_S", "300"))
EXA_KEY = os.environ.get("EXA_API_KEY", "")
JINA_KEY = os.environ.get("JINA_API_KEY", "")
JINA_READER = os.environ.get("WEBSEARCH_LB_JINA", "https://r.jina.ai")
USAGE_LOG = os.environ.get("WEBSEARCH_LB_USAGE_LOG", "/tmp/lse/websearch-lb/usage.jsonl")
_PRIORITY_DEFAULT = ["jina", "firecrawl", "exa", "searxng", "ddg"]
_priority_env = os.environ.get("WEBSEARCH_LB_PRIORITY", "").strip()
PRIORITY = [p.strip() for p in _priority_env.split(",") if p.strip()] or _PRIORITY_DEFAULT


class BackendError(Exception):
    """Hard failure (network/HTTP/auth/timeout). Soft fail = normal return of []."""


class CircuitBreaker:
    def __init__(self, name: str, fail_threshold: int = 2, cooldown_s: float = COOLDOWN_S,
                 clock=time.monotonic):
        self.name = name
        self.fail_threshold = fail_threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.last_latency_ms: Optional[float] = None

    def allow(self) -> bool:
        return self._clock() >= self.cooldown_until

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.fail_threshold:
            self.cooldown_until = self._clock() + self.cooldown_s
            self.consecutive_failures = 0  # reset count; cooldown now enforces

    def state(self) -> dict:
        return {
            "up": self.allow(),
            "consecutive_failures": self.consecutive_failures,
            "cooldown_until": self.cooldown_until if not self.allow() else None,
            "last_latency_ms": self.last_latency_ms,
        }


def _norm(rows: list[dict], url_keys, title_keys, snip_keys) -> list[dict]:
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        url = next((str(r[k]) for k in url_keys if r.get(k)), "")
        if not url:
            continue
        title = next((str(r[k]) for k in title_keys if r.get(k)), "")
        snip = next((str(r[k]) for k in snip_keys if r.get(k)), "")
        out.append({"title": title, "url": url, "snippet": snip[:300]})
    return out


class JinaBackend:
    name = "jina"
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
    async def search(self, query: str, max_results: int) -> list[dict]:
        if not JINA_KEY:
            raise BackendError("jina: JINA_API_KEY not configured")
        r = await self.client.get(
            f"https://s.jina.ai/{quote(query, safe='')}",
            params={"count": max_results},
            headers={"Authorization": f"Bearer {JINA_KEY}", "Accept": "application/json"},
            timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise BackendError(f"jina HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        rows = d.get("data")
        if d.get("code") != 200 or not isinstance(rows, list):
            raise BackendError(f"jina envelope error: code={d.get('code')} {str(d)[:200]}")
        return _norm(rows, ["url"], ["title"], ["description", "content"])


class ExaBackend:
    name = "exa"
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
    async def search(self, query: str, max_results: int) -> list[dict]:
        r = await self.client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": EXA_KEY} if EXA_KEY else {},
            json={"query": query, "numResults": max_results,
                  "contents": {"text": True}}, timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise BackendError(f"exa HTTP {r.status_code}: {r.text[:200]}")
        return _norm(r.json().get("results", []), ["id", "url"], ["title"], ["text", "snippet"])


class FirecrawlBackend:
    name = "firecrawl"
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
    async def search(self, query: str, max_results: int) -> list[dict]:
        r = await self.client.post(
            "https://api.firecrawl.dev/v1/search",
            json={"query": query, "limit": max_results}, timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise BackendError(f"firecrawl HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        if not d.get("success", True):
            raise BackendError(f"firecrawl success=false: {str(d)[:200]}")
        return _norm(d.get("data", []), ["url"], ["title"], ["description"])


class SearxngBackend:
    name = "searxng"
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
    async def search(self, query: str, max_results: int) -> list[dict]:
        r = await self.client.get(
            "http://localhost:8088/search",
            params={"q": query, "format": "json"}, timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise BackendError(f"searxng HTTP {r.status_code}: {r.text[:200]}")
        rows = r.json().get("results", [])
        rows = [{**row, "url": row.get("url") or row.get("id")} for row in rows]
        return _norm(rows, ["url"], ["title"], ["content", "snippet"])[:max_results]


class DdgBackend:
    name = "ddg"
    async def search(self, query: str, max_results: int) -> list[dict]:
        def _q() -> list[dict]:
            from ddgs import DDGS
            try:
                with DDGS() as d:
                    return d.text(query, max_results=max_results)
            except TypeError:  # newer ddgs without context manager
                return DDGS().text(query, max_results=max_results)
        rows = await asyncio.to_thread(_q)
        return _norm(rows, ["href", "url"], ["title"], ["body", "description"])


class Router:
    def __init__(self, backends: dict[str, Any], priority: list[str],
                 cooldown_s: float = COOLDOWN_S, clock=time.monotonic):
        self.backends = backends
        self.priority = priority
        self.breakers = {n: CircuitBreaker(n, cooldown_s=cooldown_s, clock=clock)
                         for n in backends}

    def ordered(self, override: Optional[list[str]]) -> list[str]:
        base = override if override else self.priority
        known = [b for b in base if b in self.backends]
        for b in self.priority:  # keep known-but-unlisted backends at the tail
            if b not in known:
                known.append(b)
        return known

    async def route(self, query: str, max_results: int = 5,
                    override: Optional[list[str]] = None) -> dict:
        per_backend: dict[str, dict] = {}
        for name in self.ordered(override):
            be = self.backends[name]
            br = self.breakers[name]
            if not br.allow():
                per_backend[name] = {"status": "cooldown", "detail": br.state()}
                continue
            t0 = time.monotonic()
            try:
                rows = await asyncio.wait_for(be.search(query, max_results), TIMEOUT_S)
                ms = round((time.monotonic() - t0) * 1000)
                br.last_latency_ms = ms
                if rows:
                    br.record_success()
                    per_backend[name] = {"status": "ok", "latency_ms": ms, "n_results": len(rows)}
                    results = [{**r, "rank": i + 1, "backend": name, "latency_ms": ms}
                               for i, r in enumerate(rows[:max_results])]
                    return {"ok": True, "results": results, "per_backend": per_backend}
                br.record_failure()
                per_backend[name] = {"status": "ok_no_results", "latency_ms": ms}
            except asyncio.TimeoutError:
                ms = round((time.monotonic() - t0) * 1000)
                br.record_failure()
                per_backend[name] = {"status": "error", "error": f"timeout after {ms}ms"}
            except Exception as e:  # noqa: BLE001 - classify and continue failover
                ms = round((time.monotonic() - t0) * 1000)
                br.record_failure()
                per_backend[name] = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}",
                                     "latency_ms": ms}
        return {"ok": False, "results": [],
                "error": "all_backends_failed", "per_backend": per_backend}

    def health(self) -> dict:
        return {"status": "ok",
                "priority": self.priority,
                "backends": {n: b.state() for n, b in self.breakers.items()}}

    def stats(self) -> dict:
        """Live breaker state (cooldown converted to wall-clock seconds remaining)
        plus usage.jsonl query totals. The log stores ts/query_hash/ok/backends-status
        only (no per-query token count), so usage reports query counts, not tokens."""
        backends = {}
        for n, br in self.breakers.items():
            st = br.state()
            backends[n] = {
                "up": st["up"],
                "consecutive_failures": st["consecutive_failures"],
                "cooldown_remaining_s": _cooldown_remaining(br),
                "last_latency_ms": st["last_latency_ms"],
            }
        return {"status": "ok",
                "generated_at": time.time(),
                "priority": self.priority,
                "backends": backends,
                "usage": _read_usage()}


def _make_router() -> Router:
    client = httpx.AsyncClient(follow_redirects=True)
    backends = {"jina": JinaBackend(client)} if JINA_KEY else {}  # no key -> jina not registered
    backends.update({"exa": ExaBackend(client), "firecrawl": FirecrawlBackend(client),
                     "searxng": SearxngBackend(client), "ddg": DdgBackend()})
    return Router(backends, PRIORITY)


def _log_usage(query: str, res: dict) -> None:
    try:
        os.makedirs(os.path.dirname(USAGE_LOG), exist_ok=True)
        rec = {"ts": time.time(), "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
               "ok": res.get("ok"), "backends": {k: v.get("status") for k, v in res.get("per_backend", {}).items()}}
        with open(USAGE_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def _cooldown_remaining(br: "CircuitBreaker") -> Optional[float]:
    """Monotonic cooldown_until -> wall-clock seconds remaining (>=0); None if up."""
    if br.allow():
        return None
    return max(0.0, round(br.cooldown_until - br._clock(), 3))


def _read_usage() -> dict:
    """Aggregate the usage.jsonl query log. Missing/unreadable file -> zeros."""
    total = ok = failed = 0
    last_ts = None
    try:
        with open(USAGE_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if rec.get("ok"):
                    ok += 1
                else:
                    failed += 1
                ts = rec.get("ts")
                if isinstance(ts, (int, float)) and (last_ts is None or ts > last_ts):
                    last_ts = ts
    except (FileNotFoundError, OSError):
        pass
    return {"total_queries": total, "ok_queries": ok,
            "failed_queries": failed, "last_query_ts": last_ts}


mcp = FastMCP("websearch-lb", host=HOST, port=PORT)
_router: Optional[Router] = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = _make_router()
    return _router


@mcp.tool()
async def web_search_balanced(query: str, max_results: int = 5,
                              backends: Optional[list[str]] = None) -> dict:
    """Search the web via a load-balanced pool of no-card-required backends
    (jina, firecrawl, exa, searxng, ddg) with automatic failover. Returns
    ranked normalized results plus per-backend status; if every backend
    fails the result carries ok=false with per-backend diagnostics."""
    res = await get_router().route(query, max_results, backends)
    _log_usage(query, res)
    return res


@mcp.tool()
async def read_url(url: str) -> dict:
    """Fetch one URL as clean markdown via the keyless Jina reader (20 RPM).
    Use after web_search_balanced to read a result in full."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT_S) as c:
        r = await c.get(f"{JINA_READER}/{url}", headers={"Accept": "text/markdown"})
    if r.status_code == 429:
        return {"ok": False, "error": "jina_rate_limited", "detail": "20 RPM keyless cap; retry later"}
    if r.status_code != 200:
        return {"ok": False, "error": f"jina_http_{r.status_code}", "detail": r.text[:200]}
    return {"ok": True, "url": url, "markdown": r.text}


@mcp.custom_route("/health", methods=["GET"])
async def health(request) -> Any:
    from starlette.responses import JSONResponse
    return JSONResponse(get_router().health())


@mcp.custom_route("/stats", methods=["GET"])
async def stats(request) -> Any:
    from starlette.responses import JSONResponse
    return JSONResponse(get_router().stats())


class TokenGate:
    """Minimal Bearer gate; wraps the ASGI app only when WEBSEARCH_LB_TOKEN is set."""
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            auth = ""
            for k, v in scope.get("headers", []):
                if k == b"authorization":
                    auth = v.decode()
            if auth != f"Bearer {self.token}":
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", "application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def main() -> None:
    import uvicorn
    app = mcp.streamable_http_app()
    token = os.environ.get("WEBSEARCH_LB_TOKEN", "")
    if token:
        app = TokenGate(app, token)
    # CORS: the console page is served from :9700 (/webSearch); its
    # cross-origin fetch to this :9703 MCP endpoint needs preflight +
    # simple-request headers. Origins restricted to the page's own URLs.
    from starlette.middleware.cors import CORSMiddleware
    app = CORSMiddleware(
        app,
        allow_origins=["http://localhost:9700", "http://127.0.0.1:9700"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Mcp-Session-Id"],
        expose_headers=["Mcp-Session-Id", "Content-Type"],
    )
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
