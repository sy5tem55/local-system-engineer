#!/usr/bin/env python3
"""
goethe_a2a.py — A2A 1.0 external client boundary (ADR-ORCH-001 Phase 6+)
=========================================================================
Standalone A2A 1.0 service (a2a-sdk 1.1.2) on :9701 that maps ONE external
Goethe agent to internal Runs/Tasks. Decisions D1-D6:
docs/A2A-ORCH-001-discussion-kickoff.md (Decision Log, 2026-09-14).

  D1 SDK:        dedicated a2a-sdk (this service) — NOT a thin adapter on :9700.
  D2 Transport:  standalone on :9701; the :9700 gateway stays a pure MCP surface.
  D3 Auth:       one shared JWT (Ed25519/EdDSA) for :9700 + :9701.
                  token:  Vaultwarden item 'goethe-a2a-token'
                  key:    Vaultwarden item 'goethe-a2a-jwt-key' (Ed25519 priv)
                  only the gateway (issuer) signs; both services verify;
                  public key embedded in the AgentCard auth section;
                  rotation = new keypair in Vault + card version bump.
  D4 Audit:      ToolBroker per-task gate (>=1 search_kb before first
                  research_web); hard-refuse for A2A-mediated runs.
                  A violation fails the task classified 'policy' with a
                  POLICY_VIOLATION event in the final A2A message.
  D5 Mapping:    submitted/working/completed/canceled/failed/rejected map to
                  Run/Task/Attempt records in the orchestrator ledger.
  D6 Card:       generated from the live ToolPolicyRef; the card must never
                  promise what the policy denies. Card version embeds the
                  policy hash - any policy change bumps the version.

Valve (default OFF — rollback to the MCP-only surface):
    GOETHE_A2A_ENABLED=on|1|true|yes

Runtime env:
    GOETHE_A2A_JWT_PUBKEY  Ed25519 public key PEM (required for authenticated
                           endpoints; service fails closed without it).
    GOETHE_A2A_HOST        bind address (default 0.0.0.0)
    GOETHE_A2A_PORT        port (default 9701)
    GOETHE_EXECUTION_BACKEND  orchestrator backend (default "local")
    GOETHE_A2A_EVENTS_DB   event journal path (default: shared
                           /opt/local-se/orch-event-log.db via GOETHE_ORCH_EVENT_LOG)
    GOETHE_A2A_MAX_ATTEMPTS  attempt budget per A2A task (default 2)
    GOETHE_A2A_ATTEMPT_TTL_S  envelope ttl per attempt (default 600)
    GOETHE_A2A_DEFAULT_DEADLINE_S  per-task deadline in seconds (default 300).
                           The deadline outranks the attempt budget (D5a):
                           once it expires, no further attempt starts and the
                           task fails with classification 'deadline'.
    GOETHE_MCP_URL       gateway MCP endpoint (default http://127.0.0.1:9700/mcp)
    GOETHE_MCP_TOKEN     gateway bearer token (search_kb delegation)
    GOETHE_SEARXNG_URL   SearxNG base (default http://localhost:8088)

Scope exclusions (2026-09-14 decision): no GUI control plane, no Kafka event
log, no MCP Tasks, no peer-to-peer A2A, no exposure of internal Ray actors.

STATUS: Phase-6+ steps 1-7 done. The executor maps A2A tasks to
Run/Task/Attempt records (D5) through the local orchestrator: one envelope
per attempt, retries invisible to the client, failed carries classification.
D5a hardening in place: the per-task deadline (GOETHE_A2A_DEFAULT_DEADLINE_S)
outranks the attempt budget, and the A2A surface emits exactly one result per
task, deduplicated by idempotency key task/<task-uuid>/attempt/<n>.
D4 ToolBroker audit gate in place: >=1 search_kb is recorded before the first
research_web of a task; a violation is hard-refused (task fails classified
'policy', POLICY_VIOLATION in the final message).
D6 card generation in place: the AgentCard is a projection of the live
ToolPolicyRef (version embeds the 12-hex policy hash; policy change ->
version bump); streaming + state-transition history, no pushNotifications.
Remaining: step 9 (end-to-end JWT + JSON-RPC lifecycle).
"""

import asyncio
import contextvars
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

import jwt
import requests
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
    AgentExtension,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    HTTPAuthSecurityScheme,
    Message,
    Part,
    Role,
    SecurityRequirement,
    SecurityScheme,
    StringList,
    Task,
    TaskStatusUpdateEvent,
)

# Orchestrator contracts (ADR-ORCH-001 Phases 1-3) — repo root on sys.path.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from goethe_orchestrator.contracts import TaskEnvelope, WorkerRegistration  # noqa: E402
from goethe_orchestrator.event_log import EventLog  # noqa: E402
from goethe_orchestrator.orchestrator import (  # noqa: E402
    LocalOrchestrator,
    NoEligibleWorkerError,
)

# ADR D-B/D-H: shared Ed25519 JWT module (per-node keypairs) + node3090
# peer public key for cross-node verification.
_A2A_DIR = os.environ.get("A2A_MODULE_DIR", "/opt/local-se/a2a")
if _A2A_DIR not in sys.path:
    sys.path.insert(0, _A2A_DIR)
import jwt_auth  # noqa: E402

logger = logging.getLogger("goethe_a2a")

# Provenance channel (task 6fed38ed): the verified JWT issuer, set by
# JwtAuthMiddleware.dispatch before call_next and read by the A2A task
# handlers (planner / plan_step_done / task_status) to stamp tasks.db
# provenance. asyncio.to_thread copies the current context into the
# executor worker thread, so the value set in the middleware's task is
# visible inside the handler. Default "unknown" = no verified issuer
# (public path or misconfiguration) — handlers must surface it visibly.
AUTH_ISS = contextvars.ContextVar("a2a_auth_iss", default="unknown")

# The orchestrator's local backend runs handlers on a ThreadPoolExecutor,
# and its threads do NOT inherit contextvars — AUTH_ISS set in the
# middleware's task is invisible there (2026-09-22 E2E: provenance stayed
# at the 'node4090' default for a node3090 request). Bridge per envelope:
# _run (to_thread context copy, value valid) records the verified issuer
# here; _with_envelope_iss restores it around the handler call.
ISS_BY_ENVELOPE = {}


def _with_envelope_iss(fn):
    """Run fn with AUTH_ISS restored from ISS_BY_ENVELOPE (every local
    handler receives the envelope id as __envelope_id__). No-op-safe: if
    the issuer is missing, the handler sees the contextvar default."""
    def wrapper(*a, **kw):
        env_id = kw.get("__envelope_id__")
        iss = ISS_BY_ENVELOPE.get(env_id) if env_id else None
        token = AUTH_ISS.set(iss) if iss else None
        try:
            return fn(*a, **kw)
        finally:
            if token is not None:
                AUTH_ISS.reset(token)
            if env_id:
                ISS_BY_ENVELOPE.pop(env_id, None)
    return wrapper

A2A_VERSION = "0.1.0"
AGENT_NAME = "goethe"
SKILL_ID = "goethe-researcher-v1"
JSONRPC_URL = "/rpc"
# D-H: TLS is served on :9701; the card must advertise https (overridable
# for local testing via GOETHE_A2A_SCHEME).
CARD_SCHEME = os.environ.get("GOETHE_A2A_SCHEME", "https").strip() or "https"

DEFAULT_MCP_URL = "http://127.0.0.1:9700/mcp"
DEFAULT_SEARXNG_URL = "http://localhost:8088"
LOCAL_WORKER_ID = "node4090:a2a-local"
RESEARCH_TOOLS = ["search_kb", "research_web"]
# Planner delegation (2026-09-21, task 6fed38ed): the A2A surface may also
# create/strike plans in the shared tasks.db ledger. These are read-write
# ledger operations (planner creates a task block; plan_step_done strikes a
# step; task_resume loads a task block) — provenance is stamped from the
# verified JWT issuer (see AUTH_ISS contextvar, JwtAuthMiddleware).
PLANNER_TOOLS = ["planner", "plan_step_done", "task_resume"]
A2A_TOOLS = RESEARCH_TOOLS + PLANNER_TOOLS


# --- D4 ToolBroker audit gate ------------------------------------------------
# Per-task audit gate: >=1 search_kb must be recorded before the first
# research_web of the same task. Hard-refuse for A2A-mediated runs: a
# refused call raises PolicyViolationError and the attempt fails classified
# 'policy', so the final A2A message carries POLICY_VIOLATION.

class PolicyViolationError(RuntimeError):
    """D4: a tool call the per-task ToolBroker audit gate refuses."""


class ToolBrokerGate:
    """Tracks tool calls per A2A task and enforces the KB-first rule.

    record() is called each time a tool call actually executes;
    assert_allowed() gates research_web behind >=1 recorded search_kb for
    the same task_id. Fail-closed: an unknown/unrecorded task cannot reach
    research_web. cleanup() drops the task's record once it is terminal so
    the registry cannot grow unbounded."""

    def __init__(self):
        self._calls = {}  # task_id -> set of tool names
        self._lock = threading.Lock()

    def record(self, task_id, tool):
        with self._lock:
            self._calls.setdefault(task_id, set()).add(tool)

    def assert_allowed(self, task_id, tool):
        if tool != "research_web":
            return
        with self._lock:
            seen = set(self._calls.get(task_id, set()))
        if "search_kb" not in seen:
            raise PolicyViolationError(
                f"POLICY_VIOLATION: research_web called before >=1 search_kb "
                f"(task {task_id})")

    def cleanup(self, task_id):
        with self._lock:
            self._calls.pop(task_id, None)


TOOL_GATE = ToolBrokerGate()


# --- Valve ------------------------------------------------------------------

def a2a_enabled() -> bool:
    """GOETHE_A2A_ENABLED valve (default off). Same convention as
    _a2a_enabled() in tools/goethe_mcp.py — the env var is the single source
    of truth; both services read it independently."""
    return os.environ.get("GOETHE_A2A_ENABLED", "").strip().lower() in (
        "1", "true", "on", "yes")


# --- JWT auth (D3) -----------------------------------------------------------

class JwtAuthMiddleware(BaseHTTPMiddleware):
    """Bearer JWT (Ed25519/EdDSA) verification (ADR D-H).

    Public (no auth): /health, /.well-known/agent-card.json, OPTIONS
    (preflight). The "browser 401" symptom is resolved by the public
    agent-card path, not by opening auth — no CORSMiddleware is added;
    the card is consumed by A2A client libraries, not browser pages.

    Three accepted verifiers, tried in order:
      A) GOETHE_A2A_JWT_PUBKEY (D3, minted by the node4090 gateway) —
         EdDSA signature check, no iss pinning; attributed to the gateway
         issuer lse-node4090 by verifier identity.
      B) node3090.pub via jwt_auth.verify_ed25519_jwt (cross-node calls):
         iss=lse-node3090, aud=lse-node4090, enforced claims (exp, nbf with
         30s skew, iss, aud, jti); failures carry the R8 classification.
      C) node4090.pub via jwt_auth.verify_ed25519_jwt (local per-node
         clients, added 2026-09-21 task 6fed38ed): iss=lse-node4090,
         aud=lse-node4090, same enforced claims as B. Without C, a
         node4090 client holding the per-node key could not authenticate
         (the D3 path only matches the vault key).

    Provenance: on success the verified issuer is exposed to the handler
    layer via BOTH request.state.auth_iss (per-request) and the module
    contextvar AUTH_ISS (inherited by the executor worker thread through
    asyncio.to_thread's context copy). Default "unknown" when no verifier
    ran (public paths) — handlers must surface "unknown" visibly.

    Fail-closed: with no verification key configured at all, authenticated
    paths return 503 — the service never opens itself by misconfiguration.
    """

    PUBLIC_PATHS = {"/health", "/.well-known/agent-card.json"}
    PEER = "node3090"
    SELF = "node4090"
    PUB_DIR = os.environ.get("A2A_JWT_PUB_DIR", "/opt/local-se/a2a/agent-cards")
    PEER_PUB = os.path.join(PUB_DIR, f"{PEER}.pub")
    SELF_PUB = os.path.join(PUB_DIR, f"{SELF}.pub")
    EXPECTED_ISS = "lse-node3090"
    EXPECTED_AUD = "lse-node4090"
    EXPECTED_ISS_SELF = "lse-node4090"
    EXPECTED_AUD_SELF = "lse-node4090"

    def __init__(self, app, public_key_pem=None):
        super().__init__(app)
        self._pub_pem = public_key_pem.encode() if public_key_pem else None

    def _verify_d3(self, token: str):
        """Verifier A: D3 shared key, EdDSA signature check. Returns the
        decoded claims dict on success, None on failure. The D3 path does
        not pin iss — attribution is by verifier identity (gateway)."""
        if self._pub_pem is None:
            return None
        try:
            return jwt.decode(token, self._pub_pem, algorithms=["EdDSA"])
        except jwt.PyJWTError:
            return None

    def _verify_peer(self, token: str):
        """Verifier B: node3090 cross-node JWT with enforced claims.
        Returns the decoded claims dict on success, None on failure."""
        try:
            return jwt_auth.verify_ed25519_jwt(
                token, expected_iss=self.EXPECTED_ISS,
                expected_aud=self.EXPECTED_AUD, peer=self.PEER)
        except jwt_auth.A2AAuthError as e:  # TEMP step-21 debug
            logger.warning("peer verify failed: %s: %s", e.classification, e)
            return None

    def _verify_self(self, token: str):
        """Verifier C: node4090 local per-node JWT with enforced claims
        (same contract as B, self-pinned). Returns claims dict or None."""
        try:
            return jwt_auth.verify_ed25519_jwt(
                token, expected_iss=self.EXPECTED_ISS_SELF,
                expected_aud=self.EXPECTED_AUD_SELF, peer=self.SELF)
        except jwt_auth.A2AAuthError:
            return None

    @staticmethod
    def _expose(iss: str, request) -> None:
        """Record the verified issuer for the handler layer: per-request
        state AND the contextvar the executor worker thread inherits."""
        request.state.auth_iss = iss
        AUTH_ISS.set(iss)

    async def dispatch(self, request, call_next):
        if request.url.path in self.PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        token = auth[7:].strip()
        try:  # TEMP step-21 debug: log the received token's time claims
            import base64 as _b64, json as _json
            _p = token.split(".")[1]
            _p += "=" * (-len(_p) % 4)
            _c = _json.loads(_b64.urlsafe_b64decode(_p))
            logger.warning("RX token claims: %s server_now=%d",
                           {k: _c.get(k) for k in ("iss", "iat", "nbf", "exp")},
                           int(time.time()))
        except Exception:
            pass
        claims = self._verify_d3(token)
        if claims is not None:
            self._expose("lse-node4090", request)
            return await call_next(request)
        claims = self._verify_peer(token)
        if claims is not None:
            self._expose(claims.get("iss", self.EXPECTED_ISS), request)
            return await call_next(request)
        claims = self._verify_self(token)
        if claims is not None:
            self._expose(claims.get("iss", self.EXPECTED_ISS_SELF), request)
            return await call_next(request)
        if (self._pub_pem is None and not os.path.isfile(self.PEER_PUB)
                and not os.path.isfile(self.SELF_PUB)):
            logger.error("no A2A verification key configured — failing closed")
            return JSONResponse(
                {"error": "server misconfigured: no verification key"},
                status_code=503)
        logger.warning("JWT verification failed (no verifier accepted)")
        return JSONResponse({"error": "unauthorized"}, status_code=401)


# --- Tier-1 research pipeline (the executor's work unit) ---------------------
#
# The A2A service is standalone (D2) and does not duplicate the KB stack:
# search_kb is delegated to the :9700 gateway's MCP surface (the sanctioned
# tool surface, D3 shared credential); research_web goes direct to the local
# SearxNG. Both are module-level so tests can monkeypatch them. Step 7 wraps
# this pipeline with the D4 ToolBroker audit gate (>=1 search_kb before first
# research_web; hard-refuse).

def _mcp_tools_call(tool, arguments, url=None, token=None, timeout=30):
    """One tools/call round-trip against the gateway's streamable-HTTP MCP
    endpoint (initialize -> initialized -> tools/call). Returns the
    JSON-RPC result object. Handles both JSON and SSE response encodings."""
    url = url or os.environ.get("GOETHE_MCP_URL", "").strip() or DEFAULT_MCP_URL
    token = token or os.environ.get("GOETHE_MCP_TOKEN", "").strip()
    base_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def _post(payload, session_id=None):
        headers = dict(base_headers)
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        try:  # TEMP step-21 debug: per-POST trace for the empty-body diagnosis
            with open("/tmp/a2a_mcp_debug.log", "a") as _df:
                _df.write("%s method=%s id=%s status=%s ct=%s len=%d head=%r\n" % (
                    time.strftime("%H:%M:%S"), payload.get("method"),
                    payload.get("id"), r.status_code,
                    r.headers.get("content-type"), len(r.content),
                    r.text[:160]))
        except OSError:
            pass
        r.raise_for_status()
        if not r.content:
            # MCP streamable-HTTP: notifications (no response id) get
            # 202 Accepted with an EMPTY body — r.json() on "" raises
            # JSONDecodeError (2026-09-22 E2E: failed[handler-error]).
            return None, r.headers
        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            for line in r.text.splitlines():
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:].strip())
                if isinstance(data, dict) and ("result" in data or "error" in data):
                    return data, r.headers
            raise RuntimeError("no JSON-RPC response in SSE stream")
        return r.json(), r.headers

    data, hdrs = _post({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "goethe-a2a", "version": A2A_VERSION},
        },
    })
    if "error" in data:
        raise RuntimeError(f"MCP initialize rejected: {data['error']}")
    session_id = hdrs.get("Mcp-Session-Id")
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    data, _ = _post({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }, session_id)
    if "error" in data:
        raise RuntimeError(f"MCP tools/call {tool} rejected: {data['error']}")
    return data["result"]


def kb_search(query, max_results=3):
    """search_kb via the :9700 gateway MCP surface.
    Returns {"hit": bool, "text": str}."""
    result = _mcp_tools_call("search_kb", {"query": query,
                                           "max_results": max_results})
    texts = [c.get("text", "") for c in result.get("content", [])
             if c.get("type") == "text"]
    text = "\n".join(texts)
    hit = (bool(text.strip()) and "KB miss" not in text
           and "no results" not in text.lower())
    return {"hit": hit, "text": text}


def web_search(query, max_results=3):
    """research_web via local SearxNG (jsonformat). Returns a list of
    {"title", "url", "snippet"} (max_results entries)."""
    base = os.environ.get("GOETHE_SEARXNG_URL", "").strip() or DEFAULT_SEARXNG_URL
    r = requests.get(f"{base}/search",
                     params={"q": query, "format": "json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return [
        {"title": x.get("title", ""), "url": x.get("url", ""),
         "snippet": (x.get("content") or "")[:300]}
        for x in data.get("results", [])[:max_results]
    ]


def _research(query, max_results=3, task_id=None, **_):
    """Tier-1 read-only research handler (KB-first). The D4 ToolBroker
    audit gate (TOOL_GATE) enforces >=1 search_kb before the first
    research_web per task — hard-refuse: a violation raises
    PolicyViolationError and the task fails classified 'policy'. Raises on
    zero sources so the attempt fails classified instead of returning an
    empty answer."""
    kb = kb_search(query, max_results=max_results)
    TOOL_GATE.record(task_id, "search_kb")
    if kb["hit"]:
        return {"source": "kb", "query": query, "kb": kb["text"]}
    TOOL_GATE.assert_allowed(task_id, "research_web")
    TOOL_GATE.record(task_id, "research_web")
    web = web_search(query, max_results=max_results)
    if not web:
        raise RuntimeError("no-source: KB miss and SearxNG returned zero results")
    return {"source": "web", "query": query, "results": web}


# --- Tier-1 ledger handlers (tasks.db via the :9700 gateway) -----------------
#
# Step 5 policy change (read_only=False, A2A_TOOLS): the A2A surface can now
# drive the shared tasks.db ledger. All three handlers delegate to the
# :9700 gateway's MCP surface (the sanctioned tool surface, D3) — the A2A
# service never re-implements planner logic. _planner additionally stamps
# the created block's provenance with the verified JWT issuer (AUTH_ISS
# contextvar set by JwtAuthMiddleware, step 7) via a direct sqlite3 UPDATE.
# The provenance column is added to the schema in a later step — the stamp
# is defensive: a missing column or row is a no-op, never an error, because
# the planner result itself is authoritative. These handlers do NOT go
# through TOOL_GATE (the D4 gate is research_web-only).

TASKS_DB_PATH = os.environ.get("GOETHE_TASKS_DB", "/opt/local-se/tasks.db")


def _ledger_text(result):
    """Flatten an MCP tools/call result object to its text payload."""
    parts = [item.get("text", "") for item in result.get("content", [])
             if isinstance(item, dict) and item.get("type") == "text"]
    return "\n".join(parts)


def _extract_task_id(text):
    """Pull the ledger task_id out of planner/task output: matches the
    'task_id=<hex>', 'task_id: <hex>' and 'TASK BLOCK <hex>' forms."""
    m = re.search(r"task[_\s]*id[=:\s]+([0-9a-f]{6,})", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"TASK BLOCK ([0-9a-f]{6,})", text)
    return m.group(1) if m else None


def _stamp_provenance(task_id, iss):
    """Stamp task_blocks.provenance for task_id with the node name derived
    from the verified JWT issuer ('lse-node3090' -> 'node3090', matching
    the column's 'node4090' default convention). Returns True when the row
    was stamped; False (no error) when the column or row is missing."""
    if not task_id or iss in ("", "unknown"):
        return False
    node = iss[4:] if iss.startswith("lse-") else iss
    try:
        conn = sqlite3.connect(TASKS_DB_PATH, timeout=10)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(task_blocks)")}
            if "provenance" not in cols:
                return False
            cur = conn.execute(
                "UPDATE task_blocks SET provenance = ? WHERE task_id = ?",
                (node, task_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("provenance stamp failed for %s: %s", task_id, exc)
        return False


def _planner(task, context="", **_):
    """Create an atomized plan in the shared tasks.db ledger via the :9700
    gateway planner tool, then stamp the created block's provenance with
    the verified JWT issuer (AUTH_ISS). Returns the gateway text verbatim
    plus the extracted task_id."""
    args = {"task": task}
    if context:
        args["context"] = context
    result = _mcp_tools_call("planner", args, timeout=240)
    text = _ledger_text(result)
    task_id = _extract_task_id(text)
    if task_id:
        _stamp_provenance(task_id, AUTH_ISS.get())
    return {"tool": "planner", "task_id": task_id, "text": text}


def _plan_step_done(task_id, step_n, evidence, failed=False, **_):
    """Strike a completed plan step via the :9700 gateway. The block's
    provenance is preserved (the gateway does not re-stamp it)."""
    result = _mcp_tools_call("plan_step_done", {
        "task_id": task_id, "step_n": int(step_n),
        "evidence": evidence, "failed": bool(failed),
    }, timeout=120)
    return {"tool": "plan_step_done", "task_id": task_id,
            "step_n": int(step_n), "text": _ledger_text(result)}


def _task_status(task_id="", **_):
    """Read the current state of a tasks.db ledger task via the :9700
    gateway (task_resume). Empty task_id = most recently updated open
    block."""
    args = {"task_id": task_id} if task_id else {}
    result = _mcp_tools_call("task_resume", args, timeout=60)
    return {"tool": "task_status", "task_id": task_id,
            "text": _ledger_text(result)}

# --- Step 9 routing -----------------------------------------------------------
#
# An A2A text part carrying JSON {"handler": "planner" | "plan_step_done" |
# "task_status", ...} routes to the matching ledger handler registered in
# create_app; anything that is not such a JSON object (plain text, unknown
# handler, malformed JSON) keeps the existing research behavior. args are
# the JSON fields minus 'handler' and reach the handler as kwargs (the
# local backend calls handler(**args)).

_HANDLER_TOOLS = {
    "planner": ["planner"],
    "plan_step_done": ["plan_step_done"],
    "task_status": ["task_resume"],
}


def _parse_routing(query):
    """Return (handler, args) when the A2A message is a JSON object whose
    'handler' field names a ledger handler; otherwise (None, None)."""
    if not isinstance(query, str):
        return None, None
    stripped = query.strip()
    if not stripped.startswith("{"):
        return None, None
    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    handler = payload.get("handler")
    if handler not in _HANDLER_TOOLS:
        return None, None
    args = {k: v for k, v in payload.items() if k != "handler"}
    return handler, args

# --- D5 state mapping --------------------------------------------------------
# A2A state        orchestrator record (A2A task = Run; envelope = Task;
#                  one dispatch = Attempt; journal = orch-event-log.db)
#   submitted      -> TaskEnvelope PENDING (created at execute start)
#   working        -> DISPATCHED; retries are NEW envelopes, invisible to the
#                     client (the client sees one working state)
#   completed      -> COMPLETED + result; the A2A surface emits exactly one
#                     result per task, deduped by idempotency key
#                     task/<task-uuid>/attempt/<n> (D5a)
#   (deadline)     -> the per-task deadline outranks the attempt budget (D5a):
#                     once it expires, no further attempt starts; the task
#                     fails with classification 'deadline'
#   failed         -> attempts exhausted; final message carries classification
#   canceled       -> CANCELED, TERMINAL, no auto-retry (cooperative: an
#                     in-flight attempt may finish; its result is discarded)
#   (policy)       -> D4 ToolBroker gate violation (research_web attempted
#                     before >=1 search_kb in the same task): hard-refuse,
#                     task fails classified 'policy' with POLICY_VIOLATION
#                     in the final message
#   input-required -> unused in v1 (Tier-2 stays operator/GUI-only)

class GoetheResearcherExecutor(AgentExecutor):
    """Maps A2A tasks onto Run/Task/Attempt records in the orchestrator
    ledger (D5). Blocking dispatch/collect runs in a worker thread so the
    event loop stays responsive."""

    def __init__(self, orchestrator, max_attempts=2, attempt_ttl=600,
                 deadline_s=300, event_log=None):
        self.orchestrator = orchestrator
        self.max_attempts = max(1, int(max_attempts))
        self.attempt_ttl = int(attempt_ttl)
        # D5a: per-task deadline. Outranks the attempt budget — when it
        # expires, _run stops starting new attempts and the task fails
        # classified 'deadline'.
        self.deadline_s = int(deadline_s)
        self._event_log = event_log
        # task_id -> {"envelope_id","worker_id","canceled","terminal"}
        # Tracks the in-flight attempt so cancel() can (a) mark it CANCELED
        # in the journal, (b) stop the retry loop (D5: canceled is TERMINAL,
        # no auto-retry), and (c) discard the in-flight result.
        self._inflight = {}
        # D5a exactly-once: idempotency keys already emitted to the A2A
        # surface. A duplicate final result for the same key is suppressed.
        self._emitted = set()
        self._lock = threading.Lock()

    # -- runs in a worker thread (via asyncio.to_thread) --
    def _run(self, task_id, query, handler=None, args=None):
        last_error, classification = "", "unknown"
        attempts = 0
        # D5a: the task deadline is fixed at start and outranks the attempt
        # budget — each attempt also gets the shorter of its own ttl and the
        # time left on the deadline, so a slow attempt cannot silently eat
        # the whole budget window.
        deadline = time.monotonic() + self.deadline_s
        for attempt in range(1, self.max_attempts + 1):
            idem_key = f"task/{task_id}/attempt/{attempt}"
            # D5: canceled is TERMINAL — never start a new attempt after
            # cancel (no auto-retry; the client resubmits as a NEW task).
            with self._lock:
                if self._inflight[task_id]["canceled"]:
                    return {"status": "CANCELED", "attempts": attempt - 1,
                            "idempotency_key":
                                f"task/{task_id}/attempt/{attempt - 1}"}
            # D5a: deadline outranks budget — no new attempt once expired.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"status": "FAILED",
                        "error": (f"deadline exceeded ({self.deadline_s}s) "
                                  f"before attempt {attempt} of "
                                  f"{self.max_attempts}"),
                        "classification": "deadline",
                        "attempts": attempt - 1,
                        "idempotency_key":
                            f"task/{task_id}/attempt/{attempt - 1}"}
            attempts = attempt
            if handler is None:
                env_payload = {"handler": "research",
                               "args": {"query": query,
                                        "task_id": task_id},
                               "requires": {"tools": RESEARCH_TOOLS}}
            else:
                # Step 9 routing: JSON {"handler": ...} A2A message -> the
                # matching ledger handler; requires.tools is the gateway
                # tool the handler delegates to (subset of A2A_TOOLS, so
                # the local worker stays eligible).
                env_payload = {"handler": handler,
                               "args": args,
                               "requires": {"tools":
                                             _HANDLER_TOOLS[handler]}}
            env = TaskEnvelope(payload=env_payload, ttl=self.attempt_ttl)
            ISS_BY_ENVELOPE[env.id] = AUTH_ISS.get()
            with self._lock:
                self._inflight[task_id]["envelope_id"] = env.id
            try:
                res = self.orchestrator.dispatch(env)
                with self._lock:
                    self._inflight[task_id]["worker_id"] = res.worker_id
                res = self.orchestrator.collect(
                    res, timeout=min(self.attempt_ttl, remaining))
                # D5: an in-flight attempt may finish after cancel; its
                # result is discarded.
                with self._lock:
                    if self._inflight[task_id]["canceled"]:
                        return {"status": "CANCELED", "attempts": attempt}
                if res.status == "COMPLETED":
                    return {"status": "COMPLETED", "result": res.result,
                            "attempts": attempt,
                            "idempotency_key": idem_key}
                last_error = res.error or "unknown error"
                classification = self._classify(last_error)
            except NoEligibleWorkerError as exc:
                last_error, classification = str(exc), "no-eligible-worker"
            except PolicyViolationError as exc:
                last_error, classification = str(exc), "policy"
            except Exception as exc:  # noqa: BLE001 — attempt errors are data
                last_error = f"{type(exc).__name__}: {exc}"
                classification = "orchestrator-error"
                # D5a: a collect timeout is a deadline breach, not a generic
                # orchestrator error (TimeoutError carries no message).
                if "timeout" in type(exc).__name__.lower():
                    classification = "deadline"
            finally:
                ISS_BY_ENVELOPE.pop(env.id, None)
        return {"status": "FAILED", "error": last_error,
                "classification": classification, "attempts": attempts,
                "idempotency_key": f"task/{task_id}/attempt/{attempts}"}

    @staticmethod
    def _classify(error):
        e = (error or "").lower()
        if "no eligible worker" in e:
            return "no-eligible-worker"
        if "policy violation" in e or "policy_violation" in e:
            return "policy"
        if "timed out" in e or "timeout" in e:
            return "deadline"
        if "no handler" in e:
            return "unknown-handler"
        if "no-source" in e:
            return "no-source"
        return "handler-error"

    async def execute(self, context, event_queue):
        query = context.get_user_input()
        task_id, context_id = context.task_id, context.context_id
        with self._lock:
            self._inflight[task_id] = {"envelope_id": None, "worker_id": None,
                                       "canceled": False, "terminal": False}
        # D5: submitted -> Run PENDING (the A2A task IS the Run; it enters
        # PENDING at submit, before any envelope/attempt exists).
        if self._event_log is not None:
            self._event_log.record(
                task_id, "PENDING",
                backend=self.orchestrator.backend,
                detail="a2a-submitted: task created")
        # submitted -> working (the first Task event unblocks a blocking
        # client when return_immediately is not set)
        await event_queue.enqueue_event(Task(
            id=task_id, context_id=context_id,
            status={"state": "TASK_STATE_SUBMITTED"}))
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id, context_id=context_id,
            status={"state": "TASK_STATE_WORKING"}))
        handler, args = _parse_routing(query)
        outcome = await asyncio.to_thread(self._run, task_id, query,
                                          handler=handler, args=args)
        with self._lock:
            self._inflight[task_id]["terminal"] = True
            canceled = self._inflight[task_id]["canceled"]
        TOOL_GATE.cleanup(task_id)  # D4: terminal tasks leave no gate state
        if canceled or outcome["status"] == "CANCELED":
            return  # cancel() already emitted TASK_STATE_CANCELED
        # D5a exactly-once: the A2A surface emits exactly one result per
        # task; a duplicate final result for the same idempotency key is
        # suppressed, so only the first successful (or final failed) result
        # reaches the client.
        if outcome["status"] == "COMPLETED":
            await self._emit_final(
                task_id, context_id, outcome, event_queue,
                state="TASK_STATE_COMPLETED",
                text=json.dumps(outcome["result"]))
        else:
            await self._emit_final(
                task_id, context_id, outcome, event_queue,
                state="TASK_STATE_FAILED",
                text=(f"failed[{outcome['classification']}] "
                      f"after {outcome['attempts']} attempt(s): "
                      f"{outcome['error']}"))

    async def _emit_final(self, task_id, context_id, outcome, event_queue,
                          state, text):
        """Emit the single terminal result event for a task, deduped by the
        outcome's idempotency key (D5a exactly-once). Returns True if the
        event was enqueued, False if it was suppressed as a duplicate."""
        key = outcome.get("idempotency_key")
        with self._lock:
            if key is not None and key in self._emitted:
                logger.warning("exactly-once: duplicate result %s suppressed",
                               key)
                return False
            if key is not None:
                self._emitted.add(key)
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id, context_id=context_id,
            status={"state": state,
                    "message": Message(
                        message_id=f"{task_id}-msg-1",
                        role=Role.ROLE_AGENT,
                        parts=[Part(text=text)])}))
        return True

    async def cancel(self, context, event_queue):
        # D5: canceled = attempt CANCELED, TERMINAL, no auto-retry (the
        # client may resubmit as a NEW task). Cooperative: an in-flight
        # attempt may still finish in its thread; its result is discarded.
        # The local backend holds no lease to release (thread pool); on the
        # Ray backend the cluster lease expires with the envelope ttl.
        task_id = context.task_id
        with self._lock:
            info = self._inflight.get(task_id)
            journal_cancel = (
                info is not None and not info["terminal"]
                and info["envelope_id"] is not None)
            if info is not None and not info["terminal"]:
                info["canceled"] = True
            env_id = info["envelope_id"] if info else None
            worker_id = info["worker_id"] if info else None
        if journal_cancel and self._event_log is not None:
            # A late CANCELED row after a terminal COMPLETED/FAILED row is a
            # documented race (the attempt finished microseconds before
            # cancel landed); the detail text disambiguates in the journal.
            self._event_log.record(
                env_id, "CANCELED", worker_id=worker_id,
                from_status="DISPATCHED",
                backend=self.orchestrator.backend,
                detail="a2a-canceled: client requested cancel; result discarded")
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id, context_id=context.context_id,
            status={"state": "TASK_STATE_CANCELED"}))


# --- D6 AgentCard generation (from the live ToolPolicyRef) ------------------
# The card is generated, not written: it is a projection of the live
# ToolPolicyRef, so the card must never promise what the policy denies and
# any policy change alters the policy hash — which is embedded in the card
# version, so policy change -> card change + version bump (D6).

@dataclass(frozen=True)
class ToolPolicyRef:
    """Immutable tool policy reference (ADR-ORCH-001): the tool permissions
    the A2A surface is allowed to promise. ref_id names the policy
    generation; tier/tools/read_only/audit_gate are the effective policy.
    policy_hash() is a SHA-256 over the canonical form — the single source
    for the card version's policy component."""

    ref_id: str
    tier: int
    tools: tuple
    read_only: bool
    audit_gate: str

    def policy_hash(self) -> str:
        canon = json.dumps(
            {"ref_id": self.ref_id, "tier": self.tier,
             "tools": sorted(self.tools), "read_only": self.read_only,
             "audit_gate": self.audit_gate},
            sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()


def live_tool_policy() -> ToolPolicyRef:
    """The LIVE ToolPolicyRef for this service. Built from the same
    constants that drive the executor and the D4 gate (RESEARCH_TOOLS,
    Tier-1 worker capabilities, kb-first audit gate) — change the policy
    here and the card version changes with it. Only Tier-1/read-only tools
    are eligible for the external surface (ADR-ORCH-001); Tier-2 stays an
    orchestrator-held approval workflow, Tier-3 is never delegated."""
    return ToolPolicyRef(
        ref_id="toolpolicy-goethe-a2a-v1",
        tier=1,
        tools=tuple(A2A_TOOLS),
        read_only=False,
        audit_gate="kb-first",
    )


def generate_agent_card(tool_policy_ref: ToolPolicyRef, jwt_pubkey_pem,
                        host, port) -> AgentCard:
    """Build the AgentCard as a projection of the live ToolPolicyRef (D6).

    version = <service version>+policy.<12-hex policy hash> — the hash is
    computed at card-build time from the policy actually in effect, so a
    policy change always bumps the card version. Capabilities: streaming +
    state-transition history (declared via the A2A extensions mechanism —
    a2a-sdk 1.1.2's AgentCapabilities has no stateTransitionHistory field),
    no pushNotifications. Auth: bearer JWT (Ed25519/EdDSA) with the public
    key embedded; without a key the card carries no auth scheme and the
    service fails closed (D3)."""
    pol = tool_policy_ref
    policy_hash = pol.policy_hash()
    schemes = {}
    if jwt_pubkey_pem:
        schemes["bearer"] = SecurityScheme(
            http_auth_security_scheme=HTTPAuthSecurityScheme(
                scheme="bearer",
                description="Ed25519-signed JWT (EdDSA). Issued by the Goethe "
                            "gateway (:9700) only; both services verify. "
                            "Verification key below.",
                bearer_format=jwt_pubkey_pem.strip(),
            ))
    return AgentCard(
        name=AGENT_NAME,
        description=(
            f"Goethe external research agent (Tier-{pol.tier} "
            f"{'read-only' if pol.read_only else 'read-write'}). "
            f"Policy {pol.ref_id}: tools {', '.join(pol.tools)}; audit gate "
            f"'{pol.audit_gate}' enforced per task. Generated from the live "
            f"ToolPolicyRef — the card never promises what the policy denies."),
        version=f"{A2A_VERSION}+policy.{policy_hash[:12]}",
        supported_interfaces=[AgentInterface(
            url=f"{CARD_SCHEME}://{host}:{port}{JSONRPC_URL}",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )],
        provider=AgentProvider(organization="LSE",
                               url="http://node4090.home.arpa"),
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extensions=[AgentExtension(
                uri="goethe.lse/state-transition-history",
                description=("The service emits the full task state "
                             "transition history (submitted -> working -> "
                             "terminal) as TaskStatusUpdateEvents; terminal "
                             "results are exactly-once per idempotency key."),
                required=False,
            )],
        ),
        security_schemes=schemes,
        security_requirements=([SecurityRequirement(schemes={"bearer": StringList()})]
                               if schemes else []),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[AgentSkill(
            id=SKILL_ID,
            name="Goethe Researcher",
            description=(
                f"Tier-{pol.tier} {'read-only ' if pol.read_only else ''}"
                f"research: {', '.join(pol.tools)} with the '{pol.audit_gate}' "
                f"audit gate enforced per task. No writes, no shell."),
            tags=["research"],
            input_modes=["text"],
            output_modes=["text"],
        ), AgentSkill(
            id="goethe-planner-v1",
            name="Goethe Planner",
            description=(
                "Create an atomized execution plan in the shared tasks.db "
                "ledger. Input: a text part carrying JSON "
                '{"handler": "planner", "task": "<task>", '
                '"context": "<verbatim findings>"}. Returns the ledger '
                "task_id plus step 1's packaged prompt. The created task "
                "block is stamped with the authenticated node's provenance "
                "(verified JWT iss)."),
            tags=["planning", "ledger"],
            input_modes=["text"],
            output_modes=["text"],
        ), AgentSkill(
            id="goethe-plan-step-done-v1",
            name="Goethe Plan Step Done",
            description=(
                "Strike a completed plan step in the tasks.db ledger. Input: "
                "a text part carrying JSON {\"handler\": \"plan_step_done\", "
                "\"task_id\": \"<id>\", \"step_n\": <N>, \"evidence\": "
                "\"<verify output>\", \"failed\": false}. Returns the "
                "packaged prompt for the next step, or closes the ledger "
                "when all steps are done. Provenance of the block is "
                "preserved (not re-stamped)."),
            tags=["planning", "ledger"],
            input_modes=["text"],
            output_modes=["text"],
        ), AgentSkill(
            id="goethe-task-status-v1",
            name="Goethe Task Status",
            description=(
                "Read the current state of a tasks.db ledger task. Input: "
                'a text part carrying JSON {"handler": "task_status", '
                '"task_id": "<id>"} (empty task_id = most recently updated '
                "open block). Returns goal, status, done/remaining steps, "
                "and the node provenance stamped on the block."),
            tags=["planning", "ledger"],
            input_modes=["text"],
            output_modes=["text"],
        )],
    )


# --- App ---------------------------------------------------------------------

def create_app() -> FastAPI:
    host = os.environ.get("GOETHE_A2A_HOST", "0.0.0.0")
    port = int(os.environ.get("GOETHE_A2A_PORT", "9701"))
    pub_pem = os.environ.get("GOETHE_A2A_JWT_PUBKEY", "").strip() or None

    # Orchestrator wiring (D5): local backend by default; the event journal
    # is the shared orchestrator journal (no new task database — A2A tasks
    # map onto existing Run/Task records).
    backend = os.environ.get("GOETHE_EXECUTION_BACKEND", "local").strip() or "local"
    event_log = EventLog(os.environ.get("GOETHE_A2A_EVENTS_DB", "").strip() or None)
    orchestrator = LocalOrchestrator(backend=backend, event_log=event_log)
    orchestrator.register_worker(WorkerRegistration(
        worker_id=LOCAL_WORKER_ID,
        capabilities={"tier": 1, "tools": A2A_TOOLS},
        heartbeat_ttl=30))
    orchestrator.register_handler("research", _with_envelope_iss(_research))
    orchestrator.register_handler("planner", _with_envelope_iss(_planner))
    orchestrator.register_handler("plan_step_done", _with_envelope_iss(_plan_step_done))
    orchestrator.register_handler("task_status", _with_envelope_iss(_task_status))
    executor = GoetheResearcherExecutor(
        orchestrator,
        max_attempts=int(os.environ.get("GOETHE_A2A_MAX_ATTEMPTS", "2")),
        attempt_ttl=int(os.environ.get("GOETHE_A2A_ATTEMPT_TTL_S", "600")),
        deadline_s=int(os.environ.get("GOETHE_A2A_DEFAULT_DEADLINE_S", "300")),
        event_log=event_log)

    card = generate_agent_card(live_tool_policy(), pub_pem, host, port)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
        queue_manager=InMemoryQueueManager(),
    )
    async def _heartbeat_loop():
        # Step 21 fix (see /opt/local-se/a2a/a2a_e2e_failure_diagnosis.txt):
        # the scheduler only assigns work to workers whose last_heartbeat is
        # within heartbeat_ttl=30; refresh every 10s (3x margin) so the local
        # worker stays ACTIVE for the whole server lifetime.
        while True:
            await asyncio.sleep(10)
            orchestrator.heartbeat(LOCAL_WORKER_ID)

    @asynccontextmanager
    async def _lifespan(_app):
        hb = asyncio.create_task(_heartbeat_loop())
        try:
            yield
        finally:
            hb.cancel()

    app = FastAPI(title="Goethe A2A", version=A2A_VERSION, lifespan=_lifespan)
    app.add_middleware(JwtAuthMiddleware, public_key_pem=pub_pem)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=JSONRPC_URL),
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "goethe-a2a", "version": A2A_VERSION}

    return app


app = create_app()


if __name__ == "__main__":
    if not a2a_enabled():
        raise SystemExit(
            "GOETHE_A2A_ENABLED is off (default). Set GOETHE_A2A_ENABLED=on "
            "to start the A2A service; otherwise the MCP-only surface on "
            ":9700 is unchanged.")
    import uvicorn
    host = os.environ.get("GOETHE_A2A_HOST", "0.0.0.0")
    port = int(os.environ.get("GOETHE_A2A_PORT", "9701"))
    cert = os.environ.get("GOETHE_A2A_CERT",
                          "/opt/local-se/a2a/certs/node4090.crt")
    key = os.environ.get("GOETHE_A2A_KEY",
                         "/opt/local-se/a2a/certs/node4090.key")
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        raise SystemExit(f"TLS cert/key missing: {cert} / {key}")
    uvicorn.run(app, host=host, port=port,
                ssl_certfile=cert, ssl_keyfile=key, log_level="info")
