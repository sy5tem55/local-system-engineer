#!/usr/bin/env python3
"""A2A web-research server for node3090 (task 58fffd80, ADR D-A..D-F).

Implements the a2a-sdk 1.1.2 server boundary per docs/A2A-WEB-RESEARCH-ADR.md:
  - TLS on :9701 (self-signed CA cert, /opt/local-se/a2a/certs/node3090.*)
  - Ed25519 JWT (EdDSA) bearer auth via /opt/local-se/a2a/jwt_auth.py
    (peer = node4090; public key /opt/local-se/a2a/agent-cards/node4090.pub)
  - static agent card (D-C) loaded from
    /opt/local-se/a2a/agent-cards/agent-card-node3090.json and projected
    onto the protobuf AgentCard (a2a-sdk 1.1.2 types are protobuf, not
    pydantic — build in code, do NOT model_validate the JSON)
  - executor routing (D-A): host contains reddit.com -> camoufox
    (tabs/snapshot API), everything else -> firecrawl (POST /v1/scrape)
  - task lifecycle D-F: submitted -> working -> completed|failed|canceled;
    per-task deadline (valve, default 300s) outranks the per-URL attempt
    budget (default 2); exactly-once terminal result per idempotency key
    task/<task-id>/attempt/<n>
  - append-only JSONL audit log (D-E) at /opt/local-se/a2a/logs/a2a-audit.jsonl

JWT claim convention (shared with a2a_client.py on node4090, step 12, and
the node4090 :9701 gateway fix, step 11):
    node4090 -> node3090:  iss="lse-node4090"  aud="lse-node3090"
    node3090 -> node4090:  iss="lse-node3090"  aud="lse-node4090"

Message text conventions (what the client sends as user input):
    https://...                 (one or more URL lines)  -> fetch each
    reddit:<query>                          -> global reddit search
    reddit:<sub>:<query>                    -> subreddit-scoped search
    (first segment is treated as a subreddit only if it contains neither
     ':' nor whitespace and is non-empty)

Valves (env, defaults in parentheses):
    A2A_HOST (0.0.0.0)  A2A_PORT (9701)
    A2A_CERT  A2A_KEY  A2A_CARD_PATH  A2A_AUDIT_PATH
    FIRECRAWL_URL (http://localhost:3002/v1/scrape)
    CAMOUFOX_URL  (http://localhost:9377)   # base; /tabs + /tabs/<id>/snapshot
    A2A_MAX_URLS (5)  A2A_MAX_ATTEMPTS (2)  A2A_DEADLINE_S (300)
    A2A_EXCERPT_CHARS (2000)

a2a-sdk 1.1.2 API notes (verified against tools/goethe_a2a.py, which runs
on node4090, and the installed 1.1.2 source):
  - AgentCard/AgentSkill/AgentInterface/Part/Artifact/Task are protobuf
    message classes (a2a.types) — construct, never model_validate.
  - AgentCard has NO top-level protocol_version/url/preferredTransport:
    transport lives in supported_interfaces=[AgentInterface(url,
    protocol_binding, protocol_version)].
  - Executor interface: execute(context, event_queue) / cancel(context,
    event_queue); context.get_user_input() / .task_id / .context_id.
  - Routes: add_a2a_routes_to_fastapi(app, agent_card_routes=
    create_agent_card_routes(card), jsonrpc_routes=
    create_jsonrpc_routes(handler, rpc_url="/rpc")) — provides
    message/send, message/stream (SSE), tasks/get, tasks/list,
    tasks/cancel. SendMessageConfiguration in 1.1.2 has NO idempotencyKey
    field, so exactly-once is enforced application-side (self._emitted).
"""

import asyncio
import json
import logging
import os
import re
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Artifact,
    HTTPAuthSecurityScheme,
    Message,
    Part,
    Role,
    SecurityRequirement,
    SecurityScheme,
    StringList,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

_A2A_DIR = os.path.dirname(os.path.abspath(__file__))
if _A2A_DIR not in sys.path:
    sys.path.insert(0, _A2A_DIR)
import jwt_auth  # noqa: E402  (shared module, /opt/local-se/a2a/jwt_auth.py)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("a2a-web-research")

# --- config (valves) ---------------------------------------------------------
NODE = "node3090"
A2A_VERSION = "1.0.0"
JSONRPC_URL = "/rpc"

CERT = os.environ.get("A2A_CERT", "/opt/local-se/a2a/certs/node3090.crt")
KEY = os.environ.get("A2A_KEY", "/opt/local-se/a2a/certs/node3090.key")
CARD_PATH = os.environ.get(
    "A2A_CARD_PATH", "/opt/local-se/a2a/agent-cards/agent-card-node3090.json")
AUDIT_PATH = os.environ.get(
    "A2A_AUDIT_PATH", "/opt/local-se/a2a/logs/a2a-audit.jsonl")
FIRECRAWL_URL = os.environ.get("FIRECRAWL_URL", "http://localhost:3002/v1/scrape")
CAMOUFOX_URL = os.environ.get("CAMOUFOX_URL", "http://localhost:9377").rstrip("/")
HOST = os.environ.get("A2A_HOST", "0.0.0.0")
PORT = int(os.environ.get("A2A_PORT", "9701"))

# JWT convention (see module docstring): this node verifies node4090's JWTs.
EXPECTED_ISS = "lse-node4090"
EXPECTED_AUD = "lse-node3090"
PEER = "node4090"
PEER_PUB = os.path.join(
    jwt_auth.PUB_DIR, f"{PEER}.pub")  # /opt/local-se/a2a/agent-cards/node4090.pub

MAX_URLS = int(os.environ.get("A2A_MAX_URLS", "5"))
MAX_ATTEMPTS = max(1, int(os.environ.get("A2A_MAX_ATTEMPTS", "2")))
DEADLINE_S = int(os.environ.get("A2A_DEADLINE_S", "300"))
EXCERPT_CHARS = int(os.environ.get("A2A_EXCERPT_CHARS", "2000"))
CAMOUFOX_WAIT_S = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(rec: dict) -> None:
    """Append one D-E audit line. Fields: ts, node, direction, task_id, jti,
    endpoint, routing, status, latency_ms, error, client_iss (nulls where
    unknown for the event kind). Opened O_APPEND per write; never truncated."""
    line = {"ts": _now_iso(), "node": NODE,
            "direction": rec.pop("direction", "inbound"),
            "task_id": rec.pop("task_id", None),
            "jti": rec.pop("jti", None),
            "endpoint": rec.pop("endpoint", None),
            "routing": rec.pop("routing", None),
            "status": rec.pop("status", None),
            "latency_ms": rec.pop("latency_ms", None),
            "error": rec.pop("error", None),
            "client_iss": rec.pop("client_iss", None),
            **rec}
    try:
        with open(AUDIT_PATH, "a") as f:
            f.write(json.dumps(line) + "\n")
    except OSError as e:
        log.error("audit write failed (disk pressure?): %s", e)


# --- Auth middleware (D-B) ---------------------------------------------------
class JwtAuthMiddleware(BaseHTTPMiddleware):
    """Bearer JWT (EdDSA) verification against node4090's public key.

    Public (no auth): /health, /.well-known/agent-card.json, OPTIONS.
    Fail-closed: no peer pubkey on disk -> 503 on protected paths.
    Every auth event is audit-logged with the R8 classification token
    (expired|clock-skew|wrong-iss|wrong-aud|missing-claim|bad-token|
    key-not-found|no-pyjwt)."""

    PUBLIC_PATHS = {"/health", "/.well-known/agent-card.json"}

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path in self.PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        if not os.path.isfile(PEER_PUB):
            log.error("peer pubkey %s missing — failing closed", PEER_PUB)
            audit({"endpoint": path, "status": "503",
                   "error": "key-not-found", "client_iss": None})
            return JSONResponse(
                {"error": "server misconfigured: no verification key"},
                status_code=503)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            audit({"endpoint": path, "status": "401",
                   "error": "no-bearer", "client_iss": None})
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        token = auth[7:].strip()
        try:
            claims = jwt_auth.verify_ed25519_jwt(
                token, expected_iss=EXPECTED_ISS, expected_aud=EXPECTED_AUD,
                peer=PEER)
        except jwt_auth.A2AAuthError as e:
            audit({"endpoint": path, "status": "401",
                   "error": e.classification, "jti": None,
                   "client_iss": None})
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        request.state.a2a_claims = claims
        return await call_next(request)


# --- executor routing (D-A) --------------------------------------------------
def route_for(url: str) -> str:
    """reddit.com / old.reddit.com -> camoufox (JS render, anti-bot);
    everything else -> firecrawl."""
    return "camoufox" if "reddit.com" in url else "firecrawl"


async def scrape_firecrawl(url: str, client: httpx.AsyncClient) -> str:
    r = await client.post(
        FIRECRAWL_URL, json={"url": url, "formats": ["markdown"]}, timeout=90)
    r.raise_for_status()
    data = r.json()
    d = data.get("data") or {}
    md = d.get("markdown") or d.get("content") or ""
    if not md:
        raise RuntimeError(
            f"firecrawl returned no markdown (status={d.get('status')})")
    return md


async def scrape_camoufox(url: str, client: httpx.AsyncClient) -> str:
    """Camoufox browser API (same contract as goethe_web._camoufox_scrape):
    POST /tabs -> tabId, wait, GET /tabs/<id>/snapshot -> accessibility
    tree text, DELETE tab (best effort)."""
    r = await client.post(
        f"{CAMOUFOX_URL}/tabs",
        json={"userId": "lse", "sessionKey": "lse", "url": url}, timeout=30)
    r.raise_for_status()
    tab = (r.json() or {}).get("tabId")
    if not tab:
        raise RuntimeError("camoufox: no tabId in /tabs response")
    try:
        await asyncio.sleep(CAMOUFOX_WAIT_S)
        s = await client.get(
            f"{CAMOUFOX_URL}/tabs/{tab}/snapshot",
            params={"userId": "lse", "sessionKey": "lse"}, timeout=30)
        s.raise_for_status()
        snap = (s.json() or {}).get("snapshot", "")
        if not snap:
            raise RuntimeError("camoufox: empty snapshot")
        return snap
    finally:
        try:
            await client.delete(
                f"{CAMOUFOX_URL}/tabs/{tab}",
                params={"userId": "lse", "sessionKey": "lse"}, timeout=10)
        except Exception:  # noqa: BLE001 — tab cleanup is best-effort
            pass


def parse_reddit_posts(snapshot: str) -> list:
    """Extract Reddit posts from a Camoufox accessibility tree.
    Ported from goethe_web._parse_reddit_posts (proven on node3090).
    Returns [{title, url, votes, comments, time}]."""
    posts = []
    lines = snapshot.split("\n")
    for i, line in enumerate(lines):
        if 'heading "' not in line or "[level=2]" not in line:
            continue
        m = re.search(r'heading "([^"]+)"', line)
        if not m:
            continue
        post = {"title": m.group(1), "url": "", "votes": "",
                "comments": "", "time": ""}
        for j in range(i + 1, min(len(lines), i + 15)):
            url_m = re.search(
                r'/url: (https?://www\.reddit\.com/r/[^\s]+)', lines[j])
            if url_m:
                post["url"] = url_m.group(1)
                break
        for j in range(i + 1, min(len(lines), i + 20)):
            time_m = re.search(r'time: (.+)', lines[j])
            if time_m:
                post["time"] = time_m.group(1).strip()
                break
        for j in range(i + 1, min(len(lines), i + 25)):
            vc_m = re.search(r'(\d+) votes·(\d+) comments', lines[j])
            if vc_m:
                post["votes"] = vc_m.group(1)
                post["comments"] = vc_m.group(2)
                break
        posts.append(post)
    return posts


def parse_targets(query: str):
    """Message text -> [(url, mode)]. mode: 'fetch' | 'reddit-search'."""
    q = (query or "").strip()
    if q.startswith("reddit:"):
        rest = q[7:].strip()
        sub, query_part = "", rest
        if ":" in rest:
            first, _, tail = rest.partition(":")
            if first and " " not in first and tail.strip():
                sub, query_part = first, tail.strip()
        if not query_part:
            return []
        url = (f"https://www.reddit.com/r/{sub}/search/?q="
               if sub else "https://www.reddit.com/search/?q=")
        url += quote_plus(query_part) + "&sort=hot"
        return [(url, "reddit-search")]
    urls = [l.strip() for l in q.splitlines() if l.strip().startswith("http")]
    if urls:
        return [(u, "fetch") for u in urls]
    if q.startswith("http"):
        return [(q, "fetch")]
    return []


class WebResearchExecutor(AgentExecutor):
    """Routes each target URL to camoufox (reddit) or firecrawl (rest),
    with per-URL attempt budget and a per-task deadline that outranks it
    (D-F). Terminal result is exactly-once per idempotency key."""

    def __init__(self):
        self._canceled = {}
        self._emitted = set()
        self._lock = threading.Lock()

    def _run(self, task_id: str, targets: list):
        """Blocking scrape loop (runs in a worker thread). Returns the
        outcome dict: status, sources, posts, failures, classification."""
        sources, failures = [], []
        posts = []
        deadline = time.monotonic() + DEADLINE_S
        for url, mode in targets[:MAX_URLS]:
            with self._lock:
                if self._canceled.get(task_id):
                    return {"status": "CANCELED", "sources": sources,
                            "posts": posts, "failures": failures,
                            "classification": None}
            if time.monotonic() >= deadline:
                return {"status": "FAILED", "sources": sources,
                        "posts": posts, "failures": failures,
                        "classification": "deadline"}
            tool = ("camoufox"
                    if mode == "reddit-search" or route_for(url) == "camoufox"
                    else "firecrawl")
            scraped = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                t0 = time.monotonic()
                try:
                    if tool == "camoufox":
                        scraped = asyncio.run(scrape_camoufox(url,
                                                              _new_client()))
                    else:
                        scraped = asyncio.run(scrape_firecrawl(url,
                                                               _new_client()))
                except Exception as e:  # noqa: BLE001 — attempt errors are data
                    failures.append({"url": url, "attempt": attempt,
                                     "error": f"{type(e).__name__}: {e}"})
                    audit({"task_id": task_id, "routing": tool,
                           "status": "scrape-fail",
                           "latency_ms": int((time.monotonic() - t0) * 1000),
                           "error": str(e)[:300], "url": url})
                    continue
                audit({"task_id": task_id, "routing": tool,
                       "status": "scrape-ok",
                       "latency_ms": int((time.monotonic() - t0) * 1000),
                       "error": None, "url": url})
                break
            if scraped is None:
                audit({"task_id": task_id, "routing": tool,
                       "status": "url-failed", "error": "backend-down",
                       "url": url})
                continue
            if mode == "reddit-search":
                parsed = parse_reddit_posts(scraped)
                posts.extend(parsed)
            sources.append({"url": url, "tool": tool, "timestamp": _now_iso(),
                            "excerpt": scraped[:EXCERPT_CHARS]})
        if not sources:
            classification = ("backend-down" if failures else "no-target")
            return {"status": "FAILED", "sources": sources, "posts": posts,
                    "failures": failures, "classification": classification}
        return {"status": "COMPLETED", "sources": sources, "posts": posts,
                "failures": failures, "classification": None}

    async def execute(self, context, event_queue):
        task_id, context_id = context.task_id, context.context_id
        query = context.get_user_input()
        targets = parse_targets(query)
        with self._lock:
            self._canceled[task_id] = False
        await event_queue.enqueue_event(Task(
            id=task_id, context_id=context_id,
            status={"state": "TASK_STATE_SUBMITTED"}))
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id, context_id=context_id,
            status={"state": "TASK_STATE_WORKING"}))
        t0 = time.monotonic()
        outcome = await asyncio.to_thread(self._run, task_id, targets)
        latency_ms = int((time.monotonic() - t0) * 1000)
        with self._lock:
            canceled = self._canceled.get(task_id, False)
        if canceled or outcome["status"] == "CANCELED":
            return  # cancel() already emitted TASK_STATE_CANCELED
        idem_key = f"task/{task_id}/attempt/1"
        with self._lock:
            if idem_key in self._emitted:
                log.warning("exactly-once: duplicate result %s suppressed",
                            idem_key)
                return
            self._emitted.add(idem_key)
        result_obj = {"sources": outcome["sources"],
                      "posts": outcome["posts"],
                      "failures": outcome["failures"]}
        if outcome["status"] == "COMPLETED":
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                task_id=task_id, context_id=context_id,
                artifact=Artifact(
                    artifact_id="research-1", name="web-research",
                    parts=[Part(text=json.dumps(result_obj))]),
                append=False, last_chunk=True))
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                task_id=task_id, context_id=context_id,
                status={"state": "TASK_STATE_COMPLETED",
                        "message": Message(
                            message_id=f"{task_id}-msg-1",
                            role=Role.ROLE_AGENT,
                            parts=[Part(text=json.dumps(result_obj))])}))
            audit({"task_id": task_id,
                   "routing": ",".join(sorted({s["tool"]
                                               for s in outcome["sources"]})),
                   "status": "completed", "latency_ms": latency_ms,
                   "error": None})
        else:
            text = (f"failed[{outcome['classification']}] "
                    f"{len(outcome['failures'])} scrape failure(s): "
                    + "; ".join(f["error"][:120]
                                for f in outcome["failures"][:3]))
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                task_id=task_id, context_id=context_id,
                status={"state": "TASK_STATE_FAILED",
                        "message": Message(
                            message_id=f"{task_id}-msg-1",
                            role=Role.ROLE_AGENT,
                            parts=[Part(text=text)])}))
            audit({"task_id": task_id, "routing": None,
                   "status": f"failed[{outcome['classification']}]",
                   "latency_ms": latency_ms,
                   "error": outcome["classification"]})

    async def cancel(self, context, event_queue):
        task_id = context.task_id
        with self._lock:
            self._canceled[task_id] = True
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id, context_id=context.context_id,
            status={"state": "TASK_STATE_CANCELED"}))
        audit({"task_id": task_id, "status": "canceled", "error": None})


def _new_client() -> httpx.AsyncClient:
    """Fresh client per scrape (runs inside asyncio.run in a worker thread;
    one loop per scrape, no cross-thread sharing)."""
    return httpx.AsyncClient(follow_redirects=True)


# --- AgentCard (D-C: static JSON -> protobuf) --------------------------------
def build_card(card_data: dict) -> AgentCard:
    """Project the static card JSON (version/ETag source of truth) onto the
    protobuf AgentCard. a2a-sdk 1.1.2 AgentCard has no top-level url /
    preferredTransport / protocolVersion — those map onto
    supported_interfaces[0]."""
    schemes = {}
    for name, scheme in (card_data.get("securitySchemes") or {}).items():
        h = scheme.get("httpAuthSecurityScheme") or {}
        schemes[name] = SecurityScheme(
            http_auth_security_scheme=HTTPAuthSecurityScheme(
                scheme=h.get("scheme", "bearer"),
                bearer_format=(h.get("bearerFormat") or "").strip(),
                description=h.get("description", ""),
            ))
    caps = card_data.get("capabilities") or {}
    iface = AgentInterface(
        url=card_data.get("url", ""),
        protocol_binding=card_data.get("preferredTransport", "JSONRPC"),
        protocol_version=card_data.get("protocolVersion", "1.0"),
    )
    skills = [
        AgentSkill(
            id=s.get("id", ""), name=s.get("name", ""),
            description=s.get("description", ""),
            tags=s.get("tags", []),
            examples=s.get("examples", []),
            input_modes=s.get("inputModes", ["text"]),
            output_modes=s.get("outputModes", ["text"]),
        ) for s in (card_data.get("skills") or [])
    ]
    return AgentCard(
        name=card_data.get("name", "web-research"),
        description=card_data.get("description", ""),
        version=card_data.get("version", A2A_VERSION),
        supported_interfaces=[iface],
        capabilities=AgentCapabilities(
            streaming=bool(caps.get("streaming", True)),
            push_notifications=bool(caps.get("pushNotifications", False)),
        ),
        security_schemes=schemes,
        security_requirements=([
            SecurityRequirement(schemes={"bearer": StringList()})
        ] if schemes else []),
        default_input_modes=card_data.get("defaultInputModes", ["text"]),
        default_output_modes=card_data.get("defaultOutputModes", ["text"]),
        skills=skills,
    )


# --- App ---------------------------------------------------------------------
def create_app() -> FastAPI:
    with open(CARD_PATH) as f:
        card = build_card(json.load(f))
    handler = DefaultRequestHandler(
        agent_executor=WebResearchExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
        queue_manager=InMemoryQueueManager(),
    )
    app = FastAPI(title="LSE A2A web-research", version=A2A_VERSION)
    app.add_middleware(JwtAuthMiddleware)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=JSONRPC_URL),
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "web-research-a2a",
                "node": NODE, "version": A2A_VERSION}

    return app


app = create_app()


if __name__ == "__main__":
    if not (os.path.isfile(CERT) and os.path.isfile(KEY)):
        raise SystemExit(f"TLS cert/key missing: {CERT} / {KEY}")
    uvicorn.run(app, host=HOST, port=PORT,
                ssl_certfile=CERT, ssl_keyfile=KEY, log_level="info")
