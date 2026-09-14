"""A2A adapter tests — ADR-ORCH-001 acceptance items 6 + 8 (D3/D4/D5/D5a/D6).

  item 6  — ToolBroker audit gate (D4): >=1 search_kb before the first
            research_web per task; a violation fails the task classified
            'policy' with POLICY_VIOLATION in the final A2A message.
  item 8  — A2A state mapping (D5/D5a): submitted->Run PENDING,
            working->DISPATCHED, completed->Run COMPLETED + result,
            per-task deadline outranks the attempt budget (classification
            'deadline'), and exactly-once result emission per idempotency
            key.
  D3      — JWT auth fail-closed: no token / bad token / wrong key -> 401;
            valid Ed25519 JWT passes; /health stays public.
  D6      — AgentCard is a projection of the live ToolPolicyRef: skill id,
            capabilities, embedded verification key, and a card version
            that bumps when the policy changes.

No network: kb_search / web_search are monkeypatched; the gateway (:9700)
and SearxNG are never contacted. The service module is imported once with
an isolated event journal and a test Ed25519 keypair.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
import uuid

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
for _p in (REPO_ROOT, TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _gen_keypair():
    priv = ed25519.Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


PRIV_PEM, PUB_PEM = _gen_keypair()


def _make_token(priv_pem: str = PRIV_PEM, exp_delta: int = 600) -> str:
    return pyjwt.encode(
        {"iss": "goethe-gateway", "sub": "a2a-test",
         "exp": int(time.time()) + exp_delta},
        priv_pem, algorithm="EdDSA")


@pytest.fixture(scope="session")
def a2a_mod(tmp_path_factory):
    """Import goethe_a2a once, with an isolated journal + test pubkey."""
    tmp = tmp_path_factory.mktemp("a2a")
    os.environ["GOETHE_A2A_ENABLED"] = "on"
    os.environ["GOETHE_A2A_JWT_PUBKEY"] = PUB_PEM
    os.environ["GOETHE_A2A_HOST"] = "127.0.0.1"
    os.environ["GOETHE_A2A_PORT"] = "9701"
    os.environ["GOETHE_A2A_EVENTS_DB"] = str(tmp / "events.db")
    os.environ["GOETHE_EXECUTION_BACKEND"] = "local"
    if "goethe_a2a" in sys.modules:
        return sys.modules["goethe_a2a"]
    return importlib.import_module("goethe_a2a")


@pytest.fixture(scope="session")
def client(a2a_mod):
    from fastapi.testclient import TestClient
    with TestClient(a2a_mod.app) as c:
        yield c


@pytest.fixture(scope="session")
def token():
    return _make_token()


# --- in-process executor harness (D5/D5a state mapping) ----------------------

class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class _FakeContext:
    def __init__(self, task_id, context_id, query):
        self.task_id = task_id
        self.context_id = context_id
        self._query = query

    def get_user_input(self):
        return self._query


def _make_executor(mod, tmp_path, monkeypatch, kb_result,
                   max_attempts=2, attempt_ttl=600, deadline_s=300):
    from goethe_orchestrator.contracts import WorkerRegistration
    from goethe_orchestrator.event_log import EventLog
    from goethe_orchestrator.orchestrator import LocalOrchestrator
    event_log = EventLog(str(tmp_path / f"events-{uuid.uuid4().hex[:8]}.db"))
    orch = LocalOrchestrator(backend="local", event_log=event_log)
    orch.register_worker(WorkerRegistration(
        worker_id="test-worker",
        capabilities={"tier": 1, "tools": mod.RESEARCH_TOOLS},
        heartbeat_ttl=30))
    orch.register_handler("research", mod._research)
    monkeypatch.setattr(
        mod, "kb_search",
        lambda query, max_results=3: kb_result)
    monkeypatch.setattr(
        mod, "web_search",
        lambda query, max_results=3: [
            {"title": "t", "url": "http://example", "snippet": "s"}])
    executor = mod.GoetheResearcherExecutor(
        orch, max_attempts=max_attempts, attempt_ttl=attempt_ttl,
        deadline_s=deadline_s, event_log=event_log)
    return executor, orch, event_log


def _drive(mod, executor, query="test query"):
    task_id = uuid.uuid4().hex
    queue = _FakeQueue()
    ctx = _FakeContext(task_id, uuid.uuid4().hex, query)
    asyncio.run(executor.execute(ctx, queue))
    return task_id, queue


def _final_event(queue):
    return queue.events[-1]


def _final_text(queue):
    return _final_event(queue).status.message.parts[0].text


def _state_of(event):
    from a2a.types import TaskState
    return TaskState.Name(event.status.state)


# --- item 8 (D5): state mapping ----------------------------------------------

def test_submit_creates_pending_run(a2a_mod, tmp_path, monkeypatch):
    executor, _, event_log = _make_executor(
        a2a_mod, tmp_path, monkeypatch, {"hit": True, "text": "kb answer"})
    task_id, _ = _drive(a2a_mod, executor)
    rows = event_log.events_for(task_id)
    assert any(r["to_status"] == "PENDING"
               and "a2a-submitted" in (r["detail"] or "")
               for r in rows), rows


def test_working_maps_to_dispatched(a2a_mod, tmp_path, monkeypatch):
    executor, _, event_log = _make_executor(
        a2a_mod, tmp_path, monkeypatch, {"hit": True, "text": "kb answer"})
    task_id, queue = _drive(a2a_mod, executor)
    states = [_state_of(e) for e in queue.events]
    assert "TASK_STATE_SUBMITTED" in states
    assert "TASK_STATE_WORKING" in states
    env_id = executor._inflight[task_id]["envelope_id"]
    assert env_id is not None
    row_statuses = [r["to_status"] for r in event_log.events_for(env_id)]
    assert row_statuses[0] == "DISPATCHED"


def test_completed_run_and_result(a2a_mod, tmp_path, monkeypatch):
    executor, _, event_log = _make_executor(
        a2a_mod, tmp_path, monkeypatch, {"hit": True, "text": "kb answer"})
    task_id, queue = _drive(a2a_mod, executor)
    assert _state_of(_final_event(queue)) == "TASK_STATE_COMPLETED"
    payload = json.loads(_final_text(queue))
    assert payload["source"] == "kb"
    env_id = executor._inflight[task_id]["envelope_id"]
    assert [r["to_status"] for r in event_log.events_for(env_id)] == \
        ["DISPATCHED", "COMPLETED"]


# --- item 8 (D5a): deadline + exactly-once ------------------------------------

def test_d5a_deadline_outranks_attempt_budget(a2a_mod, tmp_path, monkeypatch):
    def slow_kb(query, max_results=3):
        time.sleep(2.0)
        return {"hit": True, "text": "late"}

    executor, _, _ = _make_executor(
        a2a_mod, tmp_path, monkeypatch, None,
        max_attempts=3, attempt_ttl=600, deadline_s=1)
    monkeypatch.setattr(a2a_mod, "kb_search", slow_kb)
    _, queue = _drive(a2a_mod, executor)
    assert _state_of(_final_event(queue)) == "TASK_STATE_FAILED"
    text = _final_text(queue)
    assert "failed[deadline]" in text, text


def test_d5a_exactly_once_result(a2a_mod):
    executor = a2a_mod.GoetheResearcherExecutor(
        None, max_attempts=1, attempt_ttl=600, deadline_s=300,
        event_log=None)
    queue = _FakeQueue()
    outcome = {"status": "COMPLETED", "result": {"source": "kb"},
               "attempts": 1, "idempotency_key": "task/abc/attempt/1"}
    first = asyncio.run(executor._emit_final(
        "t1", "c1", outcome, queue, "TASK_STATE_COMPLETED", "{}"))
    dup = asyncio.run(executor._emit_final(
        "t1", "c1", outcome, queue, "TASK_STATE_COMPLETED", "{}"))
    assert first is True
    assert dup is False
    assert len(queue.events) == 1


# --- item 6 (D4): ToolBroker audit gate ---------------------------------------

def test_d4_gate_fail_closed_and_kb_first(a2a_mod):
    gate = a2a_mod.TOOL_GATE
    with pytest.raises(a2a_mod.PolicyViolationError):
        gate.assert_allowed(uuid.uuid4().hex, "research_web")
    tid = uuid.uuid4().hex
    gate.record(tid, "search_kb")
    gate.assert_allowed(tid, "research_web")  # allowed after >=1 search_kb
    gate.cleanup(tid)


def test_d4_violation_fails_task_classified_policy(a2a_mod, tmp_path,
                                                   monkeypatch):
    from goethe_orchestrator.contracts import WorkerRegistration
    from goethe_orchestrator.event_log import EventLog
    from goethe_orchestrator.orchestrator import LocalOrchestrator
    event_log = EventLog(str(tmp_path / "events-policy.db"))
    orch = LocalOrchestrator(backend="local", event_log=event_log)
    orch.register_worker(WorkerRegistration(
        worker_id="test-worker",
        capabilities={"tier": 1, "tools": a2a_mod.RESEARCH_TOOLS},
        heartbeat_ttl=30))

    def violating_research(query, max_results=3, task_id=None, **_):
        # Handler that reaches research_web with no recorded search_kb:
        # the gate must hard-refuse and the task must fail 'policy'.
        a2a_mod.TOOL_GATE.assert_allowed(task_id, "research_web")
        a2a_mod.TOOL_GATE.record(task_id, "research_web")
        return {"source": "web", "query": query,
                "results": a2a_mod.web_search(query, max_results=max_results)}

    orch.register_handler("research", violating_research)
    executor = a2a_mod.GoetheResearcherExecutor(
        orch, max_attempts=1, attempt_ttl=600, deadline_s=300,
        event_log=event_log)
    _, queue = _drive(a2a_mod, executor)
    assert _state_of(_final_event(queue)) == "TASK_STATE_FAILED"
    text = _final_text(queue)
    assert "failed[policy]" in text, text
    assert "POLICY_VIOLATION" in text, text


# --- D6: AgentCard as a projection of the live ToolPolicyRef ------------------

def test_agentcard_reflects_live_policy(a2a_mod):
    pol = a2a_mod.live_tool_policy()
    card = a2a_mod.generate_agent_card(pol, PUB_PEM, "127.0.0.1", 9701)
    assert card.name == "goethe"
    assert card.skills[0].id == "goethe-researcher-v1"
    assert card.version == \
        f"{a2a_mod.A2A_VERSION}+policy.{pol.policy_hash()[:12]}"
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    scheme = card.security_schemes["bearer"]
    assert scheme.http_auth_security_scheme.bearer_format == PUB_PEM.strip()


def test_agentcard_version_bumps_on_policy_change(a2a_mod):
    base = a2a_mod.live_tool_policy()
    changed = a2a_mod.ToolPolicyRef(
        ref_id=base.ref_id, tier=base.tier,
        tools=base.tools + ("extra_tool",), read_only=base.read_only,
        audit_gate=base.audit_gate)
    c1 = a2a_mod.generate_agent_card(base, PUB_PEM, "127.0.0.1", 9701)
    c2 = a2a_mod.generate_agent_card(changed, PUB_PEM, "127.0.0.1", 9701)
    assert c1.version != c2.version


def test_agentcard_http_endpoint(client, a2a_mod, token):
    r = client.get("/.well-known/agent-card.json",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "goethe"
    pol = a2a_mod.live_tool_policy()
    assert body["version"] == \
        f"{a2a_mod.A2A_VERSION}+policy.{pol.policy_hash()[:12]}"


# --- D3: JWT auth (fail-closed) ------------------------------------------------

def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_jwt_missing_token_401(client):
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "GetTask",
           "params": {"id": "x"}}
    assert client.post("/rpc", json=rpc).status_code == 401
    assert client.get("/.well-known/agent-card.json").status_code == 401


def test_jwt_malformed_token_401(client):
    rpc = {"jsonrpc": "2.0", "id": 2, "method": "GetTask",
           "params": {"id": "x"}}
    r = client.post("/rpc", json=rpc,
                    headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_jwt_wrong_key_401(client):
    other_priv, _ = _gen_keypair()
    bad = _make_token(priv_pem=other_priv)
    rpc = {"jsonrpc": "2.0", "id": 3, "method": "GetTask",
           "params": {"id": "x"}}
    r = client.post("/rpc", json=rpc,
                    headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_jwt_valid_token_passes(client, token):
    r = client.get("/.well-known/agent-card.json",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


# --- end-to-end over the wire: SendMessage -> completed -----------------------

def test_message_send_full_lifecycle(client, a2a_mod, token, monkeypatch):
    monkeypatch.setattr(
        a2a_mod, "kb_search",
        lambda query, max_results=3: {
            "hit": True, "text": "kb answer over the wire"})
    msg_id = uuid.uuid4().hex
    payload = {
        "jsonrpc": "2.0", "id": 42, "method": "SendMessage",
        "params": {"message": {
            "messageId": msg_id, "role": "ROLE_USER",
            "parts": [{"text": "what is the kb-first rule"}]}},
    }
    # A2A 1.0 version negotiation: without A2A-Version the handler treats
    # the request as 0.3 and rejects it (VERSION_NOT_SUPPORTED).
    hdrs = {"Authorization": f"Bearer {token}", "A2A-Version": "1.0"}
    r = client.post("/rpc", json=payload, headers=hdrs)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "error" not in body, body
    task = body["result"]["task"]
    # A blocking SendMessage may return at WORKING; poll GetTask to terminal.
    deadline = time.time() + 30
    while task["status"]["state"] in ("TASK_STATE_SUBMITTED",
                                      "TASK_STATE_WORKING") \
            and time.time() < deadline:
        time.sleep(0.3)
        r2 = client.post("/rpc", json={
            "jsonrpc": "2.0", "id": 43, "method": "GetTask",
            "params": {"id": task["id"]}}, headers=hdrs)
        assert r2.status_code == 200, r2.text
        task = r2.json()["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task
    text = task["status"]["message"]["parts"][0]["text"]
    assert json.loads(text)["source"] == "kb"
