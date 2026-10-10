#!/usr/bin/env python3
"""goethe-executor-v1 — A2A executor skill for node4090's goethe_a2a.py.

PURPOSE
  Turns node4090 into a subagent: a remote caller (node3090) sends
      {"handler": "executor",
       "task":     "<free-form work>",
       "mode":     "read" | "write",
       "max_steps": int (default 10),
       "budget_s":  int (default 300)}
  and this module runs the LOCAL Goethe agent loop on node4090:
      local LLM picks tool calls -> tools executed via the LOCAL gateway
      MCP (127.0.0.1:9700) -> terminal artifact with verbatim evidence.
  Application-level orchestrator/subagent pattern on the existing A2A link
  (KB c12a9c7a78fb): the protocol carries the task, this loop carries the
  execution.

WIRING (v1.3.1 — matches the live goethe_a2a.py architecture, verified
  2026-09-30 against the running file; applied idempotently by
  wire_executor_node4090.py, NOT by hand):
  Two in-function insertions, both made by the wiring script:
    1. Inside create_app(), right after:
         orchestrator.register_handler("task_status", ...)
       the script adds:
         import goethe_a2a_executor_skill as _executor
         orchestrator.register_handler("executor",
             _with_envelope_iss(_executor.handle_executor))
    2. Inside generate_agent_card(), the skills list gains one AgentSkill
       entry (id="goethe-executor-v1").
  The handler follows the house convention: called with unpacked kwargs,
  returns a dict. The gateway token is read lazily from
  os.environ["GOETHE_MCP_TOKEN"] at call time (goethe_a2a.py resolves it
  into the environment at startup, AFTER this module imports — so
  set_token() is optional and only needed for a non-env override).

CONFIG (environment variables; all have lazy fallbacks, none required)
  GOETHE_EXECUTOR_MODEL_URL  OpenAI-compatible /chat/completions endpoint
                             of the LOCAL model. If unset, discovered live
                             from the running llama-server's cmdline
                             (port lives in the cmdline — never assumed).
  GOETHE_EXECUTOR_MODEL      model name override (default: omitted).
  GOETHE_EXECUTOR_GATEWAY    default http://127.0.0.1:9700/mcp

SAFETY
  * mode="read":  only read-only tools (allowlist below).
  * mode="write": + execute_command / write_file / KB writes.
  * ANY sudo-class command (either mode) -> handler returns a PAUSED
    (input-required) artifact and does NOT execute; the operator approves
    on node4090 and the caller resumes via the paused task (A2A
    input-required state) or re-sends the remaining task.
  * max_steps and budget_s are hard caps; breach -> terminal "failed" with
    the evidence collected so far (never silent).
  * This module never imports or touches the A2A transport itself; it is a
    pure handler. Per-caller JWT enforcement stays in the a2a server layer.

CONVENTION MATCH (v1.2)
  Like the other handlers: input = unpacked kwargs, output = dict
  (serialized into the A2A result by the orchestrator). Terminal artifact
  schema (the dict itself):
    {"tool": "executor",
     "status": "completed"|"failed"|"paused",
     "steps_executed": int, "evidence": [str, ...],
     "total_time_s": float, "answer": str,
     "ledger_task_id": str|null, "error": str|null}
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import httpx

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

GATEWAY_URL = os.environ.get("GOETHE_EXECUTOR_GATEWAY",
                             "http://127.0.0.1:9700/mcp")
MODEL_URL = os.environ.get("GOETHE_EXECUTOR_MODEL_URL", "")
MODEL_NAME = os.environ.get("GOETHE_EXECUTOR_MODEL", "")

_TOKEN = ""          # optional override; lazy env fallback in _mcp_call
_EMIT: Optional[Callable[[str], None]] = None  # optional streaming hook

DEFAULT_MAX_STEPS = 10
DEFAULT_BUDGET_S = 300

# mode-gated tool allowlists (MCP tool names on the local gateway)
READ_TOOLS = {
    "read_file", "search_kb", "check_error_kb", "search_web",
    "get_context_status", "time_check", "assert_state", "kb_verify",
    "memory_query", "skill_search", "task_resume", "task_status",
}
WRITE_TOOLS = {
    "execute_command", "write_file", "index_to_kb", "record_error",
    "record_outcome", "skill_record", "skill_outcome", "mentor_correct",
    "planner", "plan_step_done", "ssh_run", "ssh_script",
}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS

# sudo / privileged patterns -> PAUSE, never execute
SUDO_RE = re.compile(
    r"^\s*(sudo|su\s|apt(?:-get)?\s+(?:install|remove|purge|upgrade)"
    r"|dnf\s+(?:install|remove)|yum\s+(?:install|remove)"
    r"|systemctl\s+(?:enable|disable|start|stop|restart|mask)"
    r"|useradd|usermod|userdel|visudo|crontab\s+-|iptables\s"
    r"|rm\s+-rf\s+/(?!tmp|home|opt|var)"
    r"|dd\s+if=|mkfs|fdisk|parted|visudo)\b")

SYSTEM_PROMPT = (
    "You are a Goethe subagent on node4090 (LUCIFER), executing work "
    "delegated over A2A by node3090. Use ONLY the tools you are granted "
    "for this task. Prefer read-only tools. Run verify checks and quote "
    "their output VERBATIM as evidence. Never fabricate command output. "
    "If a step would need sudo or a privileged write, do NOT attempt it; "
    "reply exactly: SUDO_REQUIRED <what is needed>. "
    "When the task is done, reply with a final answer that quotes the key "
    "evidence verbatim.")


# --------------------------------------------------------------------------
# wiring helpers
# --------------------------------------------------------------------------

def set_token(token: str) -> None:
    """Optional override. If not called, the token is read lazily from
    os.environ['GOETHE_MCP_TOKEN'] at call time (the a2a server resolves
    it into the environment at startup)."""
    global _TOKEN
    _TOKEN = token


def set_emitter(fn: Callable[[str], None]) -> None:
    """Optional streaming hook: fn(text) is called with per-step progress
    lines. Unwired by default on node4090 — progress then lives in the
    terminal artifact only (degraded but functional)."""
    global _EMIT
    _EMIT = fn


def register(handlers: Dict[str, Any], skills: List[Dict[str, Any]]) -> None:
    """Back-compat helper (v1.0 wiring contract). The live wiring on
    node4090 uses orchestrator.register_handler() inside create_app() —
    see wire_executor_node4090.py. Kept for unit tests / other hosts."""
    handlers["executor"] = handle_executor
    skills.append({
        "id": "goethe-executor-v1",
        "name": "Goethe Executor (subagent)",
        "description": (
            "Direct executable work to this node's local Goethe agent "
            "loop. Args: {task, mode: 'read'|'write', max_steps, budget_s}. "
            "Streams per-step progress; terminal artifact carries verbatim "
            "evidence. Sudo-class work pauses the task (input-required)."),
        "tags": ["execute", "subagent", "delegate"],
    })


def _emit(line: str) -> None:
    if _EMIT:
        try:
            _EMIT(line)
        except Exception:
            pass  # streaming is best-effort; the artifact is the truth


# --------------------------------------------------------------------------
# transport helpers
# --------------------------------------------------------------------------

def _parse_llama_cmdline(out: str) -> str:
    """Extract a base URL from llama-server cmdline text. Handles both
    forms seen in the wild (verified 2026-09-30 on node4090):
      * inline URL:     llama-server ... http://127.0.0.1:8080 ...
      * Studio-managed: llama-server ... --host 127.0.0.1 --port 44793
    """
    m = re.search(r"https?://[A-Za-z0-9.]+:\d+", out)
    if m:
        return m.group(0)
    port = re.search(r"--port\s+(\d+)", out)
    if port:
        host = re.search(r"--host\s+([\d.]+)", out)
        return (f"http://{host.group(1) if host else '127.0.0.1'}"
                f":{port.group(1)}")
    return ""


def _model_url() -> str:
    """Env override first; else prefer the fixed :9702 engine forwarder if
    it is listening; else discover a running local llama-server LIVE on
    every call (no cache: the Studio-managed port is ephemeral and
    changes across sessions).

    v1.2: the returned URL ALWAYS ends with /chat/completions. Discovery
    yields the bare base URL (host:port) and the OpenAI-compatible
    endpoint lives at <base>/chat/completions (verified 2026-09-30 on
    node4090: POST <base> -> 404 JSON; POST <base>/chat/completions ->
    200). Env values that already carry the path pass through unchanged.
    """
    url = MODEL_URL
    if not url:
        # v1.3 (2026-09-30): prefer the fixed-port engine forwarder :9702
        # when it is listening (it resolves the live engine port per
        # connection); live pgrep discovery stays the last resort only.
        try:
            import socket
            socket.create_connection(("127.0.0.1", 9702), timeout=0.2).close()
            url = "http://127.0.0.1:9702"
        except OSError:
            try:
                import subprocess
                out = subprocess.run(["pgrep", "-a", "llama-server"],
                                     capture_output=True, text=True, timeout=5).stdout
                url = _parse_llama_cmdline(out)
            except Exception:
                url = ""
    if url and not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


_GATEWAY_SESSION = None  # v1.3: cached Mcp-Session-Id (streamable-HTTP)


def _gateway_session(auth_headers):
    """v1.3: MCP streamable-HTTP handshake against the local gateway.

    The gateway runs the MCP python-sdk streamable-HTTP app with session
    tracking enabled: a bare tools/call POST is rejected with HTTP 400 /
    -32600 'Bad Request: Missing session ID'.  Handshake (verified live
    2026-09-30):
      1. POST initialize -> response header Mcp-Session-Id
      2. POST notifications/initialized with that header (202)
    The returned session id must ride on every subsequent POST."""
    init_body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                 "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "goethe-executor",
                                           "version": "1.3"}}}
    r = httpx.post(GATEWAY_URL, json=init_body,
                   headers=auth_headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(
            f"executor: gateway initialize HTTP {r.status_code}: "
            f"{r.text[:300]}")
    sid = r.headers.get("mcp-session-id")
    if not sid:
        raise RuntimeError(
            "executor: gateway initialize returned no Mcp-Session-Id "
            "header - handshake failed")
    h2 = dict(auth_headers)
    h2["Mcp-Session-Id"] = sid
    rn = httpx.post(GATEWAY_URL,
                    json={"jsonrpc": "2.0",
                          "method": "notifications/initialized"},
                    headers=h2, timeout=30)
    if rn.status_code not in (200, 202):
        raise RuntimeError(
            f"executor: gateway notifications/initialized HTTP "
            f"{rn.status_code}: {rn.text[:300]}")
    return sid


def _mcp_call(tool: str, arguments: Dict[str, Any],
              timeout: float = 300.0) -> str:
    """One MCP tools/call against the local gateway (streamable HTTP).
    Returns the tool result text."""
    tok = _TOKEN or os.environ.get("GOETHE_MCP_TOKEN", "").strip()
    if not tok:
        # v1.2: GUI-launched a2a instances carry no executor env vars —
        # A2aControlService sets only GOETHE_A2A_ENABLED and
        # GOETHE_A2A_JWT_PUBKEY (canonical launch, KB 1d7de74591d3c49f).
        # Fall back to the LIVE gateway process env: that is the token
        # actually in force (KB 378f744ca248b9de; /opt/local-se/
        # goethe-mcp.env on disk is stale and must never be trusted).
        import subprocess
        try:
            gpid = subprocess.run(
                ["pgrep", "-f", "goethe_mcp[.]py"],
                capture_output=True, text=True, timeout=5).stdout.split()
            if gpid:
                with open(f"/proc/{gpid[0]}/environ", "rb") as fh:
                    for entry in fh.read().split(b"\0"):
                        if entry.startswith(b"GOETHE_MCP_TOKEN="):
                            tok = entry[len(b"GOETHE_MCP_TOKEN="):].decode().strip()
        except Exception:
            pass
    if not tok:
        # last resort: the file the GUI launcher itself sources
        # (start-goethe-safe.sh: source "$HOME/.lse/secrets")
        try:
            import re as _re
            with open(os.path.expanduser("~/.lse/secrets")) as fh:
                m = _re.search(r"(?:^|\n)(?:export\s+)?GOETHE_MCP_TOKEN=(\S+)",
                               fh.read())
                if m:
                    tok = m.group(1).strip('"').strip("'")
        except Exception:
            pass
    if not tok:
        raise RuntimeError(
            "executor: gateway token not set — GOETHE_MCP_TOKEN is missing "
            "from the a2a process environment, the live gateway process env, "
            "and ~/.lse/secrets (GUI launch path omits executor env vars; "
            "see module v1.2 notes)")
    headers = {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    global _GATEWAY_SESSION
    if _GATEWAY_SESSION is None:
        # v1.3: streamable-HTTP requires the initialize handshake before
        # tools/call (bare call -> HTTP 400 'Missing session ID').
        _GATEWAY_SESSION = _gateway_session(headers)
    headers["Mcp-Session-Id"] = _GATEWAY_SESSION
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}}
    r = httpx.post(GATEWAY_URL, json=body, headers=headers, timeout=timeout)
    if r.status_code == 400 and "Missing session ID" in r.text:
        # Gateway restarted or session expired: re-handshake once, retry.
        _GATEWAY_SESSION = _gateway_session(headers)
        headers["Mcp-Session-Id"] = _GATEWAY_SESSION
        r = httpx.post(GATEWAY_URL, json=body, headers=headers,
                       timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"executor: gateway HTTP {r.status_code}: "
                           f"{r.text[:300]}")
    text = r.text
    payload = None
    if "text/event-stream" in r.headers.get("content-type", "") \
            or text.lstrip().startswith("event:"):
        # streamable-HTTP SSE: take the last data: JSON object
        for line in text.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    try:
                        payload = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
    else:
        payload = json.loads(text)
    if payload is None:
        raise RuntimeError(f"executor: unparseable gateway reply: "
                           f"{text[:300]}")
    if "error" in payload:
        raise RuntimeError(f"executor: MCP error: "
                           f"{json.dumps(payload['error'])[:300]}")
    result = payload.get("result", payload)
    # MCP result: {"content":[{"type":"text","text":...}], ...}
    if isinstance(result, dict):
        for part in result.get("content", []):
            if part.get("type") == "text" and part.get("text"):
                return part["text"]
        if "structuredContent" in result:
            return json.dumps(result["structuredContent"],
                              ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


def _llm_chat(messages: List[Dict[str, Any]],
              tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One chat completion against the local model. Returns the raw
    choice.message dict (may carry tool_calls).
    Retries transport-level connection failures with backoff 2s/5s/9s;
    never retries HTTP status errors."""
    url = _model_url()
    if not url:
        raise RuntimeError(
            "executor: no local model endpoint — set GOETHE_EXECUTOR_MODEL_URL "
            "or start llama-server locally (discovered from its cmdline)")
    payload = {"messages": messages, "tools": tools,
               "temperature": 0, "max_tokens": 4000}
    if MODEL_NAME:
        payload["model"] = MODEL_NAME

    logger = logging.getLogger(__name__)
    _TRANSPORT_EXCEPTIONS = (httpx.RemoteProtocolError, httpx.ConnectError,
                             httpx.ReadError, OSError)
    _RETRY_BACKOFF_S = (2, 5, 9)
    attempt = 0

    while True:
        attempt += 1
        try:
            r = httpx.post(url, json=payload, timeout=600.0)
        except _TRANSPORT_EXCEPTIONS as exc:
            if attempt > len(_RETRY_BACKOFF_S):
                raise
            delay = _RETRY_BACKOFF_S[attempt - 1]
            logger.warning(
                "executor: retry %d after %s (attempt %d failed transport); "
                "sleeping %.1fs",
                attempt, type(exc).__name__, attempt, delay)
            time.sleep(delay)
            continue

        if r.status_code != 200:
            raise RuntimeError(f"executor: model HTTP {r.status_code}: "
                               f"{r.text[:300]}")
        data = r.json()
        return data["choices"][0]["message"]


def _tool_schemas(mode: str) -> List[Dict[str, Any]]:
    """OpenAI tool schema for every allowed tool. Generic schemas: the
    local gateway validates real arguments; the subagent only needs the
    names + descriptions it has already seen in its own KB/sessions."""
    out = []
    for name in sorted(ALL_TOOLS & (READ_TOOLS if mode == "read"
                                    else READ_TOOLS | WRITE_TOOLS)):
        desc = {
            "read_file": "Read a file slice. args: path, max_lines, offset_lines",
            "execute_command": "Run a read-only or safe shell command. args: command",
            "search_kb": "Search the local knowledge base. args: query",
            "check_error_kb": "Look up an error in the error KB. args: error_text",
            "search_web": "Search the web via SearxNG. args: query",
            "get_context_status": "Check context usage. no args",
            "time_check": "NTP-verified time. no args",
            "assert_state": "Read-only check + regex. args: check_command, expected_regex",
            "kb_verify": "Regression-probe a KB doc. args: doc_id, observed",
            "memory_query": "Query memcore. args: q, k",
            "skill_search": "Search skills index. args: task",
            "task_resume": "Load an open task block. args: task_id",
            "task_status": "Read a task block. args: task_id",
            "write_file": "Write a file. args: path, content, mode",
            "index_to_kb": "Index a doc into the KB. args: content, title, topic",
            "record_error": "Record an error + resolution. args: error_text, context, resolution",
            "record_outcome": "Record outcome on a KB doc. args: doc_id, success",
            "skill_record": "Record a proven procedure. args: task, procedure",
            "skill_outcome": "Report a verified skill outcome. args: skill_id, success",
            "mentor_correct": "Human-authorized KB correction. args: doc_id, correction",
            "planner": "Plan a multi-step task. args: task, context",
            "plan_step_done": "Strike a plan step. args: task_id, step_n, evidence",
            "ssh_run": "Single remote command via SSH. args: host, command",
            "ssh_script": "Multi-command remote script. args: host, script",
        }.get(name, "Goethe tool: " + name)
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {"arg": {"type": "string",
                                           "description": "JSON object string of the tool's arguments"}},
                    "required": ["arg"],
                },
            },
        })
    return out


# --------------------------------------------------------------------------
# the handler
# --------------------------------------------------------------------------

def handle_executor(task: str = "", mode: str = "read",
                    max_steps: int = DEFAULT_MAX_STEPS,
                    budget_s: float = DEFAULT_BUDGET_S,
                    **_: Any) -> Dict[str, Any]:
    """A2A handler 'executor' (house convention: unpacked kwargs in,
    dict out). See module docstring for the artifact schema."""
    t0 = time.monotonic()
    task = str(task or "").strip()
    try:
        max_steps = int(max_steps)
    except (TypeError, ValueError):
        max_steps = DEFAULT_MAX_STEPS
    try:
        budget_s = float(budget_s)
    except (TypeError, ValueError):
        budget_s = DEFAULT_BUDGET_S
    if not task:
        return {"tool": "executor", "status": "failed",
                "error": "empty task", "steps_executed": 0, "evidence": [],
                "total_time_s": 0.0, "answer": "", "ledger_task_id": None}
    if mode not in ("read", "write"):
        return {"tool": "executor", "status": "failed",
                "error": "mode must be read|write", "steps_executed": 0,
                "evidence": [], "total_time_s": 0.0, "answer": "",
                "ledger_task_id": None}
    allowed = READ_TOOLS if mode == "read" else READ_TOOLS | WRITE_TOOLS
    deadline = t0 + budget_s
    evidence: List[str] = []
    ledger_task_id = None

    def artifact(status, answer, error=None):
        return {"tool": "executor", "status": status,
                "steps_executed": len(evidence), "evidence": evidence,
                "total_time_s": round(time.monotonic() - t0, 2),
                "answer": answer, "ledger_task_id": ledger_task_id,
                "error": error}

    def paused(what):
        _emit(f"PAUSED input-required: {what}")
        return {"tool": "executor", "status": "paused",
                "pause": "input-required", "what": what,
                "steps_executed": len(evidence), "evidence": evidence,
                "total_time_s": round(time.monotonic() - t0, 2),
                "answer": f"Paused: operator approval needed — {what}",
                "ledger_task_id": ledger_task_id, "error": None}

    _emit(f"executor: start mode={mode} max_steps={max_steps} "
          f"budget_s={int(budget_s)} task={task[:120]}")

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT + (
             f"\nTASK MODE: {mode} (read-only tools only)"
             if mode == "read" else
             f"\nTASK MODE: {mode} (writes allowed; sudo still forbidden)")},
        {"role": "user", "content": task},
    ]
    tools = _tool_schemas(mode)

    try:
        for step in range(1, max_steps + 1):
            if time.monotonic() > deadline:
                return artifact("failed",
                                f"budget_s={budget_s} exhausted at step {step}",
                                error="budget exhausted")
            msg = _llm_chat(messages, tools)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                answer = (msg.get("content") or "").strip()
                if answer.startswith("SUDO_REQUIRED"):
                    return paused(answer)
                _emit(f"executor: done after {step} step(s)")
                return artifact("completed", answer)

            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    raw_args = tc["function"].get("arguments") or "{}"
                    call_args = json.loads(raw_args)
                    if (isinstance(call_args, dict)
                            and set(call_args.keys()) == {"arg"}
                            and isinstance(call_args["arg"], str)):
                        call_args = json.loads(call_args["arg"])
                except json.JSONDecodeError:
                    call_args = {}
                if name not in allowed:
                    out = (f"REFUSED: tool '{name}' not granted in mode "
                           f"'{mode}'. Allowed: {sorted(allowed)}")
                    evidence.append(f"step {step} {name}: REFUSED (mode)")
                else:
                    cmd = str(call_args.get("command") or
                              call_args.get("arg") or "")
                    if name in ("execute_command", "ssh_run", "ssh_script") \
                            and SUDO_RE.search(cmd):
                        return paused(
                            f"step {step}: privileged command: {cmd[:200]}")
                    _emit(f"executor: step {step} -> {name} "
                          f"{json.dumps(call_args)[:120]}")
                    try:
                        out = _mcp_call(name, call_args,
                                        timeout=max(30.0,
                                                    deadline - time.monotonic()))
                    except Exception as e:
                        out = f"TOOL ERROR: {e}"
                    out = str(out)[:4000]
                    evidence.append(f"step {step} {name}: {out}")
                    messages.append({"role": "tool",
                                     "tool_call_id": tc.get("id", str(uuid.uuid4())),
                                     "content": out})
            _emit(f"executor: step {step} done ({len(evidence)} evidence line(s))")

        return artifact("failed",
                        f"max_steps={max_steps} reached without final answer",
                        error="max steps reached")
    except Exception as e:  # noqa: BLE001 — terminal artifact must be returned
        _emit(f"executor: FAILED: {e}")
        return artifact("failed", "", error=str(e)[:500])


if __name__ == "__main__":  # manual smoke test on node4090 (after wiring)
    import sys
    if len(sys.argv) > 1:
        _TOKEN = sys.argv[1]
    print(json.dumps(
        handle_executor(task="echo subagent smoke test", mode="read",
                        max_steps=2, budget_s=30),
        ensure_ascii=False, indent=2))
