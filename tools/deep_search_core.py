#!/usr/bin/env python3
"""deep_search_core.py - LLM search agent core (public contract module).

Implements brief_core.md. Public surface (do not rename): full_search,
quick_search, sleep_and_flush, generate, ChatSession, configure,
get_config, SelfTestError.

HTTP transport is dependency-injected (httpx.Client-compatible objects
with a .post method); nothing here performs real network I/O.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone

import httpx

# Additive imports for the deep-research state-machine layer below.
import asyncio
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum

MODULE_ID = "deep-search-core-v1.0.0"

DEFAULT_CONFIG = {
    "model": "",
    "deepseek_model": "deepseek-chat",
    "openai_model": "gpt-4o-mini",
    "gemini_model": "gemini-2.0-flash",
    "max_tokens": 512,
    "searcher": "mock",
    "proxy_url": "",
    "temperature": 1.0,
    "tool_rounds": 5,
    "max_rounds": 12,
    "context_budget": 48000,
    "flush_stale_seconds": 1800.0,
    "flush_interval_seconds": 60.0,
    "db_path": "/opt/local-se/tasks.db",
    "log_dir": None,
    "user_agent": MODULE_ID,
}

_config_lock = threading.RLock()
_config = dict(DEFAULT_CONFIG)
overrides_applied = False  # idempotency flag for apply_db_overrides()


class SelfTestError(RuntimeError):
    """Raised when a self-test step fails; details are always masked."""


def _safe_detail(exc):
    """Render an error detail that provably cannot contain the bearer."""
    if isinstance(exc, sqlite3.Error):
        return "local sqlite failure (no secret content)"
    return exc.__class__.__name__ + " (details suppressed: may contain secrets)"


_auth_lock = threading.RLock()      # one auth lock serializes refresh
token_cache = {}                    # one in-flight token cache
token_lock = threading.RLock()      # public (brief 2); guards the cache


def _token_endpoint(proxy_url):
    return proxy_url.rstrip("/") + "/v1alpha2/token"


def _decode_token_payload(data):
    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("token endpoint returned non-object JSON")
        return parsed
    raise ValueError("token endpoint returned an unreadable payload")


def _parse_body(data):
    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except ValueError:
            return data
        return parsed if isinstance(parsed, str) else parsed
    return data


def _extract_token(payload):
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("token payload missing access_token")
    return token


def _extract_expiry(payload, now):
    if payload.get("expires_at") is not None:
        return float(payload["expires_at"])
    if payload.get("expires_in") is not None:
        return now + float(payload["expires_in"])
    return None


def _cache_token(token, expiry):
    with token_lock:
        token_cache.clear()
        token_cache["access_token"] = token
        if expiry is not None:
            token_cache["expires_at"] = expiry


def _ensure_valid_token(client, now=None):
    """Caller must hold _auth_lock. Refreshes when missing / near-expiry."""
    now = time.time() if now is None else now
    with token_lock:
        cached = token_cache.get("access_token")
        expiry = token_cache.get("expires_at")
    if cached and (expiry is None or expiry > now + 60):
        return cached
    cfg = get_config()
    resp = client.post(_token_endpoint(cfg["proxy_url"]),
                       json={"grantType": "client_credentials"})
    status = getattr(resp, "status_code", None)
    if status is None:
        raise RuntimeError("token response lacks status_code")
    if status != 200:
        raise RuntimeError("token request failed with status %s" % status)
    payload = _decode_token_payload(resp.content)
    token = _extract_token(payload)
    _cache_token(token, _extract_expiry(payload, now))
    return token


def refresh_token(client, force=False):
    """Serialize credential refresh against the in-flight state.

    Concurrent callers never double-mint: exactly one token request is
    issued; the rest observe the fresh cache while holding the same lock.
    """
    with _auth_lock:
        return _ensure_valid_token(client)


def invalidate_token():
    with token_lock:
        token_cache.clear()


def force_refresh_token(client):
    with _auth_lock:
        invalidate_token()
        return _ensure_valid_token(client)


def auth_header():
    """Freshly read Authorization header for the live token.

    Always a live read of the in-flight cache: a rotated token can
    never be served as a stale value.
    """
    with token_lock:
        token = token_cache.get("access_token")
    if not token:
        return {}
    return {"Authorization": "Bearer %s" % token}


def _should_retry(status):
    return status == 429 or 500 <= status <= 599


def _retry_after_seconds(resp):
    try:
        value = (getattr(resp, "headers", None) or {}).get("Retry-After")
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sleep_small(seconds):
    """Sleep helper with a hard cap: no long backoff waits in-process."""
    if seconds > 0:
        time.sleep(min(seconds, 0.1))


def _role_of(m):
    if isinstance(m, dict) and "role" in m:
        return str(m["role"])
    role = getattr(m, "role", None)
    return str(role) if role is not None else "user"


def _content_of(m):
    if isinstance(m, dict):
        return m.get("content") or ""
    return getattr(m, "content", "") or ""


def serialize_chatml(messages):
    """SOLE prompt-payload assembly path (brief section 1).

    Every message is emitted in order as EXACTLY

        <|im_start|>{role}\n{content}.<|im_end|>\n

    followed by the trailing assistant primer.  Message content is used
    verbatim; no code may inject extra template tokens.
    """
    parts = []
    for m in messages:
        parts.append("<|im_start|>%s\n%s.<|im_end|>\n"
                     % (_role_of(m), _content_of(m)))
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def build_request(messages, model, max_tokens=512):
    """Build the /v1/completions body.  ChatML is serialized ONLY here."""
    prompt = serialize_chatml(messages)
    return {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": get_config()["temperature"],
        "stop": [".<|im_end|>"],
    }


def extract_text(data):
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and "choices" in data:
        choices = data["choices"] or [{}]
        first = choices[0] or {}
        if isinstance(first.get("text"), str):
            return first["text"]
        message = first.get("message") or {}
        if isinstance(message.get("content"), str):
            return message["content"]
    if isinstance(data, dict):
        for key in ("content", "output_text", "output"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return ""


def parse_response(content):
    """Cut at the first stop token; never emit a token fragment."""
    if not content:
        return ""
    text = content
    for token in (".<|im_end|>", "<|im_end|>", "<|endoftext|>"):
        idx = text.find(token)
        if idx != -1:
            text = text[:idx]
    return text


def _completions_url(proxy_url):
    return proxy_url.rstrip("/") + "/v1/completions"


def _default_client():
    cfg = get_config()
    return httpx.Client(timeout=60.0, headers={"User-Agent": cfg["user_agent"]})


def send_chatml(client, prompt_or_messages, model, max_tokens=512,
                max_retries=3, retry_backoff=1.0, sleep_func=time.sleep):
    """POST the ChatML body to {proxy_url}/v1/completions.

    Retries HTTP 429 and any 5xx; honors a Retry-After hint when
    present.  Every attempt carries a FRESHLY read bearer token.
    Returns the generated text cut at the first stop token; raises
    RuntimeError once the retry budget is exhausted.
    """
    cfg = get_config()
    with _auth_lock:
        _ensure_valid_token(client)
    messages = prompt_or_messages
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body = build_request(messages, model, max_tokens)
    url = _completions_url(cfg["proxy_url"])
    attempt = 0
    while True:
        with _auth_lock:
            _ensure_valid_token(client)
        headers = {"Content-Type": "application/json"}
        headers.update(auth_header())  # fresh read every attempt
        resp = client.post(url, json=body, headers=headers)
        status = resp.status_code
        if 200 <= status < 300:
            return parse_response(extract_text(_parse_body(resp.content)))
        if status in (401, 403):
            if _should_retry(status):
                force_refresh_token(client)
            else:
                invalidate_token()
        if _should_retry(status) and attempt < max_retries:
            delay = _retry_after_seconds(resp)
            if delay is None:
                delay = retry_backoff * (2 ** attempt)
            sleep_func(delay)
            attempt += 1
            continue
        raise RuntimeError("completion request failed: HTTP %s after %d "
                           "retries" % (status, attempt))


TOOL_RESULT_BUDGET = 4000
COMPACT_KEEP_HEAD = 4
COMPACTION_NOTE = "[compacted]"
DEFAULT_SYSTEM = ("You are a meticulous deep-research agent. Use the "
                  "search tool for facts; cite sources; answer last.")


def _estimate_tokens(text):
    return max(1, (len(text) + 3) // 4)


def context_token_estimate(messages):
    """Cheap deterministic estimate: max(len/4, word_count)."""
    total = 0
    for m in messages:
        total += _estimate_tokens(_role_of(m))
        total += _estimate_tokens(_content_of(m))
        words = len(_content_of(m).split())
        total += max(0, words - _estimate_tokens(_content_of(m)))
    return total


def enforce_context_budget(messages, budget):
    """Preserve system + most recent messages; summarize/drop the middle.

    Oldest non-system turns are compacted into one summary note until the
    token estimate fits the budget.
    """
    msgs = [dict(m) if isinstance(m, dict) else m for m in messages]
    if not msgs:
        return msgs
    head = []
    if _role_of(msgs[0]) == "system":
        head.append(dict(msgs[0]))
        rest = [dict(m) for m in msgs[1:]]
    else:
        rest = [dict(m) for m in msgs]
    note_idx = None
    for i, m in enumerate(rest):
        if m.get("compacted") and _role_of(m) == "system":
            note_idx = i
            break

    def _estimate(candidate_rest):
        return context_token_estimate(head + candidate_rest)

    while _estimate(rest) > budget:
        if note_idx is None:
            drop_from = 0
            for i, m in enumerate(rest):
                if len(rest) - i <= COMPACT_KEEP_HEAD:
                    break
                if _role_of(m) != "system":
                    drop_from = i + 1
                    break
            if drop_from == 0:
                if len(rest) <= COMPACT_KEEP_HEAD:
                    break
                drop_from = len(rest) - COMPACT_KEEP_HEAD
            dropped = rest[:drop_from]
            if not dropped:
                break
            lines = []
            for m in dropped:
                content = _content_of(m).strip().replace("\n", " ")
                if len(content) > 80:
                    content = content[:77] + "..."
                lines.append("%s: %s" % (_role_of(m), content))
            summary = COMPACTION_NOTE + " " + " | ".join(lines)
            rest = [{"role": "system", "content": summary,
                     "compacted": True}] + rest[drop_from:]
            note_idx = 0
        else:
            if len(rest) - (note_idx + 1) <= COMPACT_KEEP_HEAD:
                break
            victim = rest.pop(note_idx + 1)
            rest[note_idx]["content"] += " | %s: %s" % (
                _role_of(victim), _content_of(victim).strip()[:40])
    return head + rest


def generate(messages, client=None, model=None, tool=None, **kwargs):
    """Single ChatML round-trip (brief section 3).

    Returns ``(text, tool_results)``.  With a trusted ``tool`` callable
    the model is offered a ``search`` tool: each assistant turn is one
    ChatML round-trip, the assistant reply is appended as an assistant
    ChatML message, and every tool result is appended as a ChatML
    ``tool`` message.  Up to ``tool_rounds`` tool iterations per request
    and ``max_rounds`` overall model rounds are enforced.
    """
    cfg = get_config()
    model = model or cfg["model"]
    max_tokens = kwargs.get("max_tokens", cfg["max_tokens"])
    client = client if client is not None else _default_client()
    tool_rounds = kwargs.get("tool_rounds", cfg["tool_rounds"])
    max_rounds = kwargs.get("max_rounds", cfg["max_rounds"])
    ctx_budget = kwargs.get("context_budget", cfg["context_budget"])
    msgs = [dict(m) for m in messages]
    if not msgs or _role_of(msgs[0]) != "system":
        msgs.insert(0, {"role": "system", "content": DEFAULT_SYSTEM})
    tool_results = []
    text = ""
    tool_used = 0
    round_no = 0
    while True:
        remaining = ctx_budget - context_token_estimate(msgs)
        work = enforce_context_budget(msgs, max(64, remaining))
        work = work + [{"role": "user", "content": _SEARCH_INSTRUCTION}] \
            if tool is not None else work
        text = parse_response(send_chatml(client, work, model, max_tokens))
        msgs.append({"role": "assistant", "content": text})
        if tool_used >= tool_rounds:
            return text, tool_results
        call = parse_tool_call(text) if tool is not None else None
        if call is None:
            return text, tool_results
        round_no += 1
        if round_no > max_rounds:
            return text, tool_results
        args = dict(call.get("arguments") or {})
        args["budget"] = TOOL_RESULT_BUDGET
        try:
            result = tool(**args)
        except TypeError:
            result = tool(call.get("name"), args)
        if isinstance(result, str):
            data = [{"title": "result", "snippet": result}]
        elif isinstance(result, dict):
            data = result.get("results") or result.get("data") or [result]
        elif isinstance(result, (list, tuple)):
            data = list(result)
        else:
            data = [{"title": "result", "snippet": str(result)}]
        message = {"role": "tool",
                   "name": call.get("name") or "search",
                   "tool_call_id": call.get("id") or str(tool_used),
                   "content": format_tool_results(data)}
        msgs.append(dict(message))
        tool_results.append(message)
        tool_used += 1


_SEARCH_INSTRUCTION = ("Use the search tool: reply with exactly "
                       "<answer>...</answer> when done, or a single "
                       "JSON action object (name, arguments) to search.")


class ChatSession:
    """Multi-turn ChatML transcript reused by both search entry points.

    ``chatml_prompt()`` always rebuilds from the full transcript through
    the one template (brief section 3).
    """

    def __init__(self, system=None, model=None, client=None):
        cfg = get_config()
        self.model = model or cfg["model"]
        self.client = client if client is not None else _default_client()
        self.messages = []
        self.add_message("system", system or DEFAULT_SYSTEM)
        self.last_tool_results = []

    def add_message(self, role, content, **fields):
        msg = {"role": role, "content": content}
        msg.update(fields)
        self.messages.append(msg)
        return msg

    def chatml_prompt(self):
        return serialize_chatml(self.messages)

    def prompt(self):
        return self.chatml_prompt()

    def run(self, tool=None):
        text, results = generate(self.messages, client=self.client,
                                 model=self.model, tool=tool)
        self.last_tool_results = results
        return text, results


_TOOL_JSON_KEYS = ("tool_calls", "tool_call", "function_call", "name",
                   "action", "called_name")
_TOOL_CALL_MARKERS = ("tool_call", "function_call", '"name"',
                      '"arguments"', '"tool"')


def parse_tool_call(text):
    """Extract a tool-call action from assistant text ('none' => None)."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.lower() == "none":
        return None
    if any(marker in text for marker in _TOOL_CALL_MARKERS):
        text_to_scan = text
        if "<" in stripped and ">" in stripped:
            start, end = stripped.find("{"), stripped.rfind("}")
            if start != -1 and end > start:
                text_to_scan = stripped[start:end + 1]
        start = text_to_scan.find("{")
        while start != -1:
            end = text_to_scan.find("}", start)
            while end != -1:
                candidate = text_to_scan[start:end + 1]
                try:
                    obj = json.loads(candidate)
                except ValueError:
                    end = text_to_scan.find("}", end + 1)
                    continue
                if isinstance(obj, dict) and (
                        any(k in obj for k in _TOOL_JSON_KEYS)
                        or "arguments" in obj):
                    return {"name": obj.get("name") or obj.get("tool")
                            or obj.get("action") or "search",
                            "arguments": obj.get("arguments") or {}}
                end = text_to_scan.find("}", end + 1)
            start = text_to_scan.find("{", start + 1)
    return None


def format_tool_results(results):
    """Serialize results into a tool message capped at TOOL_RESULT_BUDGET."""
    parts = []
    used = 0
    for r in results:
        if isinstance(r, dict):
            title = r.get("title") or r.get("name") or "result"
            snippet = r.get("snippet", r.get("content", r.get("text", "")))
            unit = "%s: %s (%s)" % (title, snippet, r.get("url", ""))
        else:
            unit = str(r)
        est = _estimate_tokens(unit)
        if used + est <= TOOL_RESULT_BUDGET - 4:
            parts.append(unit)
            used += est
            continue
        room = TOOL_RESULT_BUDGET - 4 - used
        if room > 16:
            parts.append(unit[:room * 4])
        break
    text = "\n".join(parts)
    guard = 0
    while context_token_estimate(
            [{"role": "tool", "content": text}]) > TOOL_RESULT_BUDGET:
        guard += 1
        words = text.split()
        if not words or guard > 50:
            break
        cut = max(1, len(words) - max(1, len(words) // 8))
        text = " ".join(words[:cut])
    return text


def web_search(query, num_results=5, budget=TOOL_RESULT_BUDGET):
    """Mock search backend (searcher='mock'): deterministic, offline."""
    results = []
    for i in range(1, int(num_results) + 1):
        title = "Result %d for %s" % (i, query)
        snippet = ("Mock snippet %d for query %r: deterministically "
                   "generated offline evidence %d." % (i, query, i))
        results.append({
            "title": title,
            "url": "https://example.com/%d?q=%s" % (i, query),
            "snippet": snippet,
            "source": "mock",
        })
    return results

# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

_ENTRY_SYSTEM = ("You are a meticulous deep-research agent. Run the "
                 "deep-research loop over the query: gather evidence "
                 "with the search tool, cross-check claims against the "
                 "cited sources, then answer completely. When done, "
                 "reply with every finding inside <answer>...</answer>.")


def full_search(query, model=None, client=None):
    """Kick off a full, non-blocking deep-research loop.

    Returns a started daemon worker thread immediately; nothing here
    joins it, so the caller is never blocked (mirrors fire-and-forget
    Task creation in the original system).
    """
    cfg = get_config()
    model = model or cfg["model"]
    session = ChatSession(system=_ENTRY_SYSTEM, model=model, client=client)
    session.add_message("user", query)

    def _worker():
        try:
            session.run(tool=web_search)
        except Exception:
            pass

    thread = threading.Thread(target=_worker, daemon=True,
                              name="%s-full" % MODULE_ID)
    thread.start()
    return thread


def quick_search(query, model=None, client=None):
    """One-shot blocking search used by the sleep-time flusher (brief 6)."""
    cfg = get_config()
    model = model or cfg["model"]
    session = ChatSession(system=_ENTRY_SYSTEM, model=model, client=client)
    session.add_message("user", query)
    text, _ = session.run(tool=web_search)
    return text


def sleep_and_flush(query, model=None):
    """Kick off one quick search from context without blocking the
    process's normal exit (A8): runs on a daemon worker thread and
    returns immediately."""
    thread = threading.Thread(
        target=lambda: quick_search(
            query, model=model, client=_flush_client()),
        daemon=True, name="%s-flush" % MODULE_ID)
    thread.start()
    return thread

# ---------------------------------------------------------------------------
# Self-test audit log + agent task tracking (brief section 4)
# ---------------------------------------------------------------------------

AUDIT_LOG = "logs/audit.log"
TASKS_DB = "/opt/local-se/tasks.db"
LOG_DIR = None
MODULE_VERSION = MODULE_ID


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user_agent():
    return get_config()["user_agent"]


def _open_conn(create_parent=True):
    conn = sqlite3.connect(TASKS_DB, timeout=10)
    return conn


def record_call(func=None, *, name=None, kind="function"):
    """Decorator recording a successful call into task_calls."""
    def decorate(fn):
        label = name or getattr(fn, "__name__", "unknown")

        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            _record_call(label, kind)
            return result
        wrapper.__name__ = label
        wrapper.__doc__ = fn.__doc__
        return wrapper
    if func is not None:
        return decorate(func)
    return decorate


def _record_call(name, kind="function"):
    now = _now_iso()
    conn = _open_conn()
    try:
        with conn:
            try:
                cur = conn.execute(
                    "INSERT INTO tasks (description, parent_id, status, "
                    "created_at, updated_at) VALUES (?, NULL, 'running', "
                    "?, ?)", ("call:" + str(name), now, now))
                task_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO task_calls (task_id, name, kind, status, "
                    "created_at) VALUES (?, ?, ?, 'ok', ?)",
                    (task_id, name, kind, now))
                conn.execute(
                    "UPDATE tasks SET status = 'completed', updated_at = ? "
                    "WHERE id = ?", (now, task_id))
            except sqlite3.Error:
                raise
    finally:
        conn.close()


TASK_STATUSES = ("pending", "running", "completed", "failed", "canceled")


def create_task(description, parent_id=None, status="pending"):
    now = _now_iso()
    conn = _open_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO tasks (description, parent_id, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (description, parent_id, status, now, now))
            return cur.lastrowid
    finally:
        conn.close()


def update_task(task_id, status):
    now = _now_iso()
    if status not in TASK_STATUSES:
        raise ValueError("invalid task status: %r" % (status,))
    conn = _open_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id))
    finally:
        conn.close()


_CHILD_RUN_DDL_FALLBACK = (
    "CREATE TABLE IF NOT EXISTS child_runs ("
    "parent_id INTEGER, agent_id TEXT, result TEXT, created_at TEXT,"
    " PRIMARY KEY (parent_id, agent_id))")


def _table_columns(conn, table):
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]
    except sqlite3.Error:
        return []


def record_child_run(parent_id, agent_id, result=None):
    """Write exactly one child_runs row describing one run."""
    now = _now_iso()
    conn = _open_conn()
    try:
        cols = _table_columns(conn, "child_runs")
        with conn:
            if "child_id" in cols:
                child_id = "%s-%f" % (agent_id, time.time())
                conn.execute(
                    "INSERT INTO child_runs (child_id, parent_task_id, "
                    "scope, node, kind, status, result, created) "
                    "VALUES (?, ?, 'selftest', ?, 'detached', 'done', "
                    "?, ?)",
                    (child_id, None if parent_id is None else str(parent_id),
                     agent_id, result, now))
            elif "parent_id" in cols and "agent_id" in cols:
                conn.execute(
                    "INSERT OR REPLACE INTO child_runs (parent_id, "
                    "agent_id, result, created_at) VALUES (?, ?, ?, ?)",
                    (parent_id, agent_id, result, now))
            else:
                conn.execute(_CHILD_RUN_DDL_FALLBACK)
                conn.execute(
                    "INSERT OR REPLACE INTO child_runs (parent_id, "
                    "agent_id, result, created_at) VALUES (?, ?, ?, ?)",
                    (parent_id, agent_id, result, now))
    finally:
        conn.close()


def audit(msg):
    line = "%s %s %s\n" % (_now_iso(), _user_agent(), msg)
    log_path = os.path.join(LOG_DIR or ".", AUDIT_LOG)
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(line)
    except OSError:
        pass
    return line


class Auditor:
    def __init__(self, agent_id):
        self.agent_id = agent_id

    def log(self, event, **fields):
        extra = "".join(" %s=%r" % (k, v) for k, v in sorted(fields.items()))
        audit("agent=%s event=%s%s" % (self.agent_id, event, extra))


def _wrap_recorded():
    """Attach call recording to the public entry points (idempotent)."""
    global full_search, quick_search, generate, sleep_and_flush
    for fname, target in (("full_search", full_search),
                          ("quick_search", quick_search),
                          ("generate", generate),
                          ("sleep_and_flush", sleep_and_flush)):
        if getattr(target, "_dsc_recorded", False):
            continue
        wrapped = record_call(name=fname)(target)
        wrapped._dsc_recorded = True
        globals()[fname] = wrapped


_apply_hooks = []

# ---------------------------------------------------------------------------
# Sleep-time compute flusher (brief section 6)
# ---------------------------------------------------------------------------

FLUSH_MARKER = "[INST] <<SYS>> You are a memory consolidation agent. " \
               "Write the session to plain markdown memory now. <</SYS>>"
MAX_TURNS = 4
ITEM_TOKEN_CAP = 800

_flusher_state = {"started": False}


def _extract_conversation(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return raw
    if isinstance(raw, dict):
        conv = raw.get("conversation")
    else:
        conv = None
    if isinstance(conv, (list, tuple)):
        return " ".join(str(part) for part in conv)
    return str(raw)


def _load_pending_items(max_turns=MAX_TURNS):
    """Return at most max_turns pending work_items as (id, text, raw)."""
    try:
        conn = sqlite3.connect(TASKS_DB, timeout=10)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = conn.execute(
                "SELECT id, payload FROM work_items "
                "WHERE status = 'pending' ORDER BY id LIMIT ?",
                (max_turns,)).fetchall()
        except sqlite3.Error:
            return None  # work_items unavailable; caller may use fixtures
    finally:
        conn.close()
    items = []
    for item_id, payload in rows:
        text = _extract_conversation(payload)
        if len(text) > ITEM_TOKEN_CAP:
            text = text[:ITEM_TOKEN_CAP]
        items.append((item_id, text, payload))
    return items


def _seed_selftest_item():
    """Enqueue one pending self-maintenance work item (best-effort)."""
    try:
        now = _now_iso()
        conn = _open_conn()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO work_items (kind, payload, status, "
                    "created_at) VALUES ('consolidation', ?, 'pending', ?)",
                    (json.dumps({"conversation": [
                        "user", "selftest maintenance conversation",
                        "assistant", "noted"]}), now))
        finally:
            conn.close()
        return True
    except sqlite3.Error:
        return False


def truncate_conversation(text):
    """Cap a conversation's contribution to the flush prompt (cost)."""
    if text is None:
        return ""
    text = str(text)
    if len(text) > ITEM_TOKEN_CAP:
        return text[:ITEM_TOKEN_CAP]
    return text


def _process_item(client, model, item_id, text, now, auditor, parent_id,
                  write_db=True):
    text = truncate_conversation(text)
    try:
        prompt = "%s\n%s\n" % (FLUSH_MARKER, text)
        reply = quick_search(prompt, model=model, client=client)
        reply = reply if reply is not None else ""
    except Exception:
        reply = ""
    if write_db:
        try:
            record_child_run(parent_id, "%s-flush" % MODULE_ID,
                             result=reply[:2000])
            conn = _open_conn()
            try:
                with conn:
                    conn.execute(
                        "UPDATE work_items SET status = 'done', "
                        "updated_at = ? WHERE id = ?", (now, item_id))
            finally:
                conn.close()
        except sqlite3.Error as exc:
            auditor.log("child_run_write_failed", error=_safe_detail(exc))
    else:
        auditor.log("child_run_dry", item_id=item_id, chars=len(reply))
    auditor.log("item_processed", item_id=item_id, chars=len(reply))


def flush_once(client, model, parent_id=None, auditor=None, max_turns=None,
               items=None, write_db=True):
    """One bounded tick (brief section 6).

    Reads at most ``MAX_TURNS`` (default 4) pending items, truncates each
    conversation, sends each through the sleep-time prompt built around
    the marker constant, writes one child_runs row per processed item,
    marks done.  Returns the number of items processed.
    """
    max_turns = MAX_TURNS if max_turns is None else min(max_turns, MAX_TURNS)
    auditor = auditor or Auditor(MODULE_ID)
    now = _now_iso()
    if items is None:
        items = _load_pending_items(max_turns)
        if items is None:
            return 0
        items = items[:max_turns]
    else:
        items = list(items)[:max_turns]
    for item_id, text, _raw in items:
        _process_item(client, model, item_id, text, now, auditor,
                      parent_id, write_db=write_db)
    return len(items)


def _flush_client():
    return httpx.Client(timeout=60.0,
                        headers={"User-Agent": _user_agent()})


def start_flusher(client=None, model=None, parent_id=None):
    """Start the sleep-time flusher loop on a daemon thread (A6)."""
    cfg = get_config()
    model = model or cfg["model"]
    stop = threading.Event()
    _flusher_state["stop"] = stop
    _flusher_state["started"] = True
    thread_ref = {}

    def _loop():
        client = client if client is not None else _flush_client()
        auditor = Auditor(MODULE_ID)
        while not stop.is_set():
            try:
                items = _load_pending_items(MAX_TURNS)
            except Exception as exc:
                auditor.log("load_failed", error=_safe_detail(exc))
                items = None
            if items is None:
                auditor.log("flush_unavailable")
                stop.wait(get_config()["flush_interval_seconds"])
                continue
            if len(items) > MAX_TURNS:
                auditor.log("truncated_to_max_turns", max_turns=MAX_TURNS)
            for item_id, text, _raw in items[:MAX_TURNS]:
                _process_item(client, model, item_id, text, _now_iso(),
                              auditor, parent_id)
            stop.wait(get_config()["flush_interval_seconds"])

    thread = threading.Thread(target=_loop, daemon=True,
                              name="%s-flusher" % MODULE_ID)
    thread_ref["thread"] = thread
    thread.start()
    return thread


def stop_flusher():
    stop = _flusher_state.get("stop")
    if stop is not None:
        stop.set()
    _flusher_state["started"] = False

# ---------------------------------------------------------------------------
# Config loading from the tasks DB (brief section 7) + bootstrap (section 4)
# ---------------------------------------------------------------------------

_CONFIG_TABLE = "config"

TASKS_DDL = [
    "CREATE TABLE IF NOT EXISTS main.tasks ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " description TEXT NOT NULL,"
    " parent_id INTEGER REFERENCES tasks(id),"
    " status TEXT NOT NULL DEFAULT 'pending',"
    " created_at TEXT NOT NULL,"
    " updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS main.task_calls ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " task_id INTEGER REFERENCES tasks(id),"
    " name TEXT NOT NULL,"
    " kind TEXT NOT NULL DEFAULT 'function',"
    " status TEXT NOT NULL DEFAULT 'ok',"
    " created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS child_runs ("
    "parent_id INTEGER,"
    " agent_id TEXT,"
    " result TEXT,"
    " created_at TEXT,"
    " PRIMARY KEY (parent_id, agent_id))",
    "CREATE TABLE IF NOT EXISTS configs ("
    "key TEXT PRIMARY KEY,"
    " value TEXT)",
    "CREATE TABLE IF NOT EXISTS work_items ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " kind TEXT,"
    " payload TEXT,"
    " status TEXT NOT NULL DEFAULT 'pending',"
    " created_at TEXT,"
    " updated_at TEXT)",
]

_FLOAT_KEYS = ("temperature", "flush_stale_seconds", "flush_interval_seconds")
_INT_KEYS = ("max_tokens", "tool_rounds", "max_rounds", "context_budget")


def _connect_db():
    conn = sqlite3.connect(_config["db_path"], timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn=None):
    """Create the schema if absent (best-effort; never fatal)."""
    own = conn is None
    try:
        conn = conn or _connect_db()
    except sqlite3.Error:
        return False
    try:
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            pass
        for ddl in TASKS_DDL:
            try:
                conn.execute(ddl)
            except sqlite3.Error:
                return False
        try:
            conn.commit()
        except sqlite3.Error:
            return False
        return True
    finally:
        if own:
            conn.close()


def load_config_overrides():
    try:
        conn = _connect_db()
    except sqlite3.Error:
        conn = None
    rows = []
    try:
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT key, value FROM %s" % _CONFIG_TABLE).fetchall()
            except sqlite3.Error:
                rows = []
    finally:
        if conn is not None:
            conn.close()
    return dict((str(k), v) for k, v in rows)


def _coerce(key, value):
    try:
        if key in _FLOAT_KEYS:
            return float(value)
        if key in _INT_KEYS:
            return int(float(value))
    except (TypeError, ValueError):
        return None
    return None


def _maybe_parse_json(value):
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def apply_db_overrides():
    """Load settings from the tasks DB into memory.

    A missing/unreadable config table disables every remote-provided
    setting (searcher, proxy_url, model) and forces the local mock
    searcher so a broken DB can never take the agent down.  Applied at
    most once (idempotent flag).  Returns the applied mapping.
    """
    global overrides_applied
    with _config_lock:
        if overrides_applied:
            return dict(_config)
    ensure_schema()
    rows = load_config_overrides()
    applied = {}
    db_ok = bool(rows)
    for key, value in rows.items():
        if key == "log_dir":
            continue
        coerced = _coerce(key, value)
        if coerced is not None:
            applied[key] = coerced
        else:
            applied[key] = _maybe_parse_json(value)
    if not db_ok:
        applied.update({"searcher": "mock", "proxy_url": "", "model": ""})
    with _config_lock:
        _config.update(applied)
        overrides_applied = True
    _set_log_dir()
    return dict(applied)


def configure(**kwargs):
    with _config_lock:
        _config.update(kwargs)


def get_config():
    with _config_lock:
        return dict(_config)


def set_log_dir(log_dir):
    """Relocate the audit log; the bare filename constant stays intact."""
    global LOG_DIR
    LOG_DIR = log_dir
    if log_dir:
        try:
            os.makedirs(os.path.join(log_dir, "logs"), exist_ok=True)
        except OSError:
            pass
    with _config_lock:
        _config["log_dir"] = log_dir


def _set_log_dir(log_dir=None):
    set_log_dir(log_dir if log_dir is not None else _config.get("log_dir"))

# ---------------------------------------------------------------------------
# Deep-research state machine (brief_fix_state_machine.md sections 3-5;
# brief_core.md sections 3-7). Purely additive layer: State/DSState,
# Budgets, DeepSearchResult, the timeout/budget exceptions, the DeepSearch
# orchestrator and the async deep_search() entry point. Model waits reuse
# the existing token/retry plumbing (build_request, _should_retry,
# _ensure_valid_token, parse_response, extract_text).
# ---------------------------------------------------------------------------

CHUNK_SEP = "\x1f"          # stream-chunk marker for timeout classification
SYNTHESIS_MAX_TOKENS = 16000  # derived, conservative (brief_core section 5)
GAP_LOOP_WALL_CAP_S = 180.0  # hard wall-clock cap on search/gap loop (gateway-wedge guard)
MAX_GAP_STREAK = 3           # hard cap on consecutive "gap" decisions
LEDGER_SCOPE = "deep-search-core"
LEDGER_PARENT = "0d0ba451"
LEDGER_NODE = "node3090"
LEDGER_KIND = "detached"

_monotonic = time.monotonic   # fake-clock seam used by the selftest only


class State(str, Enum):
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    READING = "READING"
    REASONING = "REASONING"
    SYNTHESIZING = "SYNTHESIZING"
    DONE = "DONE"
    FAILED = "FAILED"


DSState = State  # alias: design-spec name

LEGAL_TRANSITIONS = {
    (State.PLANNING, State.SEARCHING),
    (State.SEARCHING, State.REASONING),
    (State.REASONING, State.SEARCHING),
    (State.REASONING, State.READING),
    (State.READING, State.SYNTHESIZING),
    (State.SYNTHESIZING, State.DONE),
}


def _legal_transition(frm, to):
    if frm is None or to is State.FAILED:
        return True
    return (frm, to) in LEGAL_TRANSITIONS


def _validate_budget_fields(obj):
    for name in Budgets.__dataclass_fields__:
        value = getattr(obj, name)
        if type(value) is bool or not isinstance(value, int):
            raise ValueError("budget %r must be an int (bools rejected)"
                             % name)


@dataclass
class Budgets:
    totalBudgetSeconds: int = 1800
    modelTimeoutSeconds: int = 420
    toolTimeoutSeconds: int = 300
    briefTimeoutSeconds: int = 900
    firstOutputSeconds: int = 420
    idleSeconds: int = 120
    maxSteps: int = 8
    maxSources: int = 10
    maxBriefs: int = 2
    snippetMaxChars: int = 4000

    def __post_init__(self):
        _validate_budget_fields(self)


@dataclass
class DeepSearchResult:
    status: str = "FAILED"          # "DONE" | "FAILED"
    report: str = ""               # markdown with citations; "" when FAILED
    sources: list = field(default_factory=list)     # {url,title,snippet,fetched}  # noqa: E501
    plan: list = field(default_factory=list)        # {n, action, target, why}
    state_trace: list = field(default_factory=list)  # {state,t_offset_s,note}
    budgets_used: dict = field(default_factory=dict)
    error: object = None           # {class, message, state_at_failure} | None


class BudgetExhausted(RuntimeError):
    """Budget cap reached: raised BEFORE an over-cap action executes."""


class DSClockTimeoutError(TimeoutError):
    """Base of the module-local model-wait timeout hierarchy."""


class FirstOutputTimeout(DSClockTimeoutError):
    """No first output began within firstOutputSeconds of the wait start."""


class ModelIdleTimeout(DSClockTimeoutError):
    """No further output for idleSeconds after output had begun."""


class ModelWallClockTimeout(DSClockTimeoutError):
    """The clamped per-wait wall-clock deadline was exceeded."""


def _wait_deadline_s(budgets, elapsed_model_wait_s):
    """Normative per-wait clamp (section 4)."""
    return min(budgets.modelTimeoutSeconds, 3600,
               max(1.0, budgets.totalBudgetSeconds - elapsed_model_wait_s))


def _sm_sleep(seconds):
    """Backoff sleep with a hard cap: no long waits inside the selftest."""
    if seconds > 0:
        time.sleep(min(float(seconds), 0.2))


def _extract_json(text, opener, closer):
    """Leniently lift the first balanced JSON value out of model text."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    start = s.find(opener)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    return None
    return None


def _validate_plan(plan, max_steps):
    return _plan_validation_error(plan, max_steps) is None


def _plan_validation_error(plan, max_steps):
    """Return the first violated rule as a string, or None if valid."""
    if not isinstance(plan, list) or not plan:
        return "plan is not a non-empty JSON array"
    if len(plan) > max_steps:
        return "plan has %d steps, max is %d" % (len(plan), max_steps)
    for i, step in enumerate(plan, 1):
        if not isinstance(step, dict):
            return "step %d is not a JSON object" % i
        if step.get("action") not in ("search", "read"):
            return ("step %d action %r is not one of 'search', 'read'"
                    % (i, step.get("action")))
        target = step.get("target")
        if not isinstance(target, str) or not target.strip():
            return "step %d target is missing or empty" % i
        if not isinstance(step.get("why", ""), str):
            return "step %d why is not a string" % i
    return None


def _normalize_plan(plan):
    out = []
    for i, step in enumerate(plan):
        out.append({"n": step.get("n") if isinstance(step.get("n"), int)
                    else i + 1,
                    "action": step["action"],
                    "target": str(step["target"]).strip(),
                    "why": str(step.get("why") or "")})
    return out


_IPV4_RE = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
_IPV6_RE = re.compile(r"(?<![\w:.])((?:[0-9a-fA-F]{0,4}:){2,7}"
                      r"[0-9a-fA-F]{1,4})(?![\w.:])")


def _redact_ipv4(match):
    ip = match.group(0)
    parts = [int(o) for o in ip.split(".")]
    if any(p > 255 for p in parts):
        return ip
    a, b = parts[0], parts[1]
    if a in (10, 127) or (a == 192 and b == 168) or (a == 172
                                                     and 16 <= b <= 31):
        return "[REDACTED-IP]"
    return ip


def _redact_ipv6(match):
    token = match.group(0)
    if "::" in token:
        return "[REDACTED-IP]"  # compressed form: clock times never have ::
    if not re.search(r"[a-fA-F]", token):
        return token  # numeric colon run (e.g. a clock time), not v6
    low = token.lower()
    if low in ("::1", "::"):
        return "[REDACTED-IP]"
    first = low.split(":")[0]
    if not first:  # leading "::" compression
        return "[REDACTED-IP]"
    try:
        value = int(first, 16)
    except ValueError:
        return token
    if (value & 0xFE00) == 0xFC00 or (value & 0xFFC0) == 0xFE80:
        return "[REDACTED-IP]"
    return token


def _redact_ips(text):
    text = _IPV4_RE.sub(_redact_ipv4, text)
    return _IPV6_RE.sub(_redact_ipv6, text)


def _mask_code_spans(text):
    spans = []

    def _stash(match):
        spans.append(match.group(0))
        return "\x00%d\x00" % (len(spans) - 1)

    return re.sub(r"`[^`\n]+`", _stash, text), spans


def _restore_code_spans(text, spans):
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def _ledger_open():
    """Insert the child_runs row (brief_core section 6); child_id or None.

    A locked/unavailable ledger must never fail the run: log and continue.
    """
    child_id = "dscore-%s" % uuid.uuid4().hex[:8]
    try:
        conn = _open_conn()
    except Exception as exc:
        audit("ledger-open unavailable: %s" % _safe_detail(exc))
        return None
    try:
        with conn:
            conn.execute(
                "INSERT INTO child_runs (child_id, parent_task_id, scope, "
                "node, kind, status, writer_lock, created) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                (child_id, LEDGER_PARENT, LEDGER_SCOPE, LEDGER_NODE,
                 LEDGER_KIND, os.getpid(), _now_iso()))
        return child_id
    except Exception as exc:
        audit("ledger-open failed (run continues): %s" % _safe_detail(exc))
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _ledger_finish(child_id, status, result_obj):
    if child_id is None:
        return
    try:
        conn = _open_conn()
    except Exception as exc:
        audit("ledger-update unavailable: %s" % _safe_detail(exc))
        return
    try:
        with conn:
            conn.execute(
                "UPDATE child_runs SET status = ?, result = ?, "
                "finished = ? WHERE child_id = ?",
                (status, json.dumps(result_obj, default=str), _now_iso(),
                 child_id))
    except Exception as exc:
        audit("ledger-update failed (run continues): %s" % _safe_detail(exc))
    finally:
        try:
            conn.close()
        except Exception:
            pass


class DeepSearch:
    """Orchestrator: PLANNING -> SEARCHING <-> REASONING -> READING ->
    SYNTHESIZING -> DONE/FAILED.  SEARCHING <-> REASONING is the ONLY loop;
    total search actions across the run never exceed budgets.maxSteps."""

    def __init__(self, question, instructions, budgets, *,
                 search_endpoint, read_endpoint, model_endpoint,
                 model_name, on_progress=None, client=None):
        self.question = question
        self.instructions = instructions or ""
        self.budgets = budgets if isinstance(budgets, Budgets) else Budgets()
        self.search_endpoint = search_endpoint
        self.read_endpoint = read_endpoint
        self.model_endpoint = model_endpoint
        self.model_name = model_name
        self.on_progress = on_progress
        self.client = client if client is not None else _default_client()
        self._mono = _monotonic  # fake-clock seam (captured once per run)
        self.state = None
        self.state_trace = []
        self.sources = []
        self.plan = []
        self.report = ""
        self.error = None
        self.model_wait_s = 0.0
        self.tool_s = 0.0
        self._t0 = None
        self._wall = 0.0
        self._actions_done = 0
        self._budget_stopped = False
        self._pending = []
        self._gap_notes = []
        self._gap_streak = 0
        self._seen_queries = set()
        self._url_by_source = {}
        self._wait_seq = 0
        self._child_id = None
        self._finished = False

    # -- infrastructure ----------------------------------------------------

    def _clock(self):
        return self._mono()

    def _trace(self, state_name, note):
        offset = 0.0 if self._t0 is None else self._clock() - self._t0
        self.state_trace.append({"state": str(state_name),
                                 "t_offset_s": round(float(offset), 3),
                                 "note": str(note)})

    def _progress(self, state, note):
        if self.on_progress is not None:
            try:
                self.on_progress(state, note)
            except Exception as exc:
                audit("on_progress callback failed: %s" % _safe_detail(exc))

    def _transition(self, frm, to, note):
        if not _legal_transition(frm, to):
            raise RuntimeError("illegal state transition %s -> %s"
                               % (getattr(frm, "name", frm), to.name))
        self.state = to
        self._trace(to.name, note)
        audit("state=%s note=%s t_offset_s=%s"
              % (to.name, note, self.state_trace[-1]["t_offset_s"]))
        self._progress(to, note)

    def _begin_action(self):
        """Enforce the step/wall budget BEFORE executing a search action."""
        if self._actions_done + 1 > self.budgets.maxSteps:
            raise BudgetExhausted(
                "maxSteps=%d exceeded: refusing to execute search action %d "
                "(raised before execution)" % (self.budgets.maxSteps,
                                               self._actions_done + 1))
        if self._t0 is not None and (self._clock() - self._t0) > \
                self.budgets.totalBudgetSeconds:
            raise BudgetExhausted("totalBudgetSeconds exceeded before "
                                  "action %d" % (self._actions_done + 1))
        self._actions_done += 1

    def _tool_post(self, tool, endpoint, payload):
        start = self._clock()
        ok = False
        data = None
        try:
            resp = self.client.post(endpoint, json=payload)
            status = getattr(resp, "status_code", 200)
            ok = isinstance(status, int) and 200 <= status < 300
            if ok:
                data = _parse_body(resp.content)
        except Exception:
            ok = False
        finally:
            latency = self._clock() - start
            self.tool_s += latency
            audit("tool=%s endpoint=%s ok=%s latency_s=%.3f"
                  % (tool, endpoint, ok, latency))
        return ok, data

    def _run_once(self, messages, max_tokens, deadline):
        """One ChatML round-trip on the injected transport, reusing the
        module's token + retry machinery (mirrors send_chatml but keeps the
        raw payload so finish_reason stays observable)."""
        cfg = get_config()
        url = _completions_url(cfg["proxy_url"])
        body = build_request(messages, self.model_name, max_tokens)
        call_start = self._clock()
        deadline_at = call_start + deadline
        attempt = 0
        # Context guard: reject prompts that cannot fit in the
        # engine max_context (strata on node3090 serves 131072).
        # Oversized prompts are rejected/stalled mid-stream and can
        # wedge the gateway event loop.
        est_prompt_tokens = len(json.dumps(body)) // 4
        if est_prompt_tokens > 131072:
            raise ValueError(
                "prompt exceeds max_context: est %d tokens > 131072"
                % est_prompt_tokens)
        while True:
            with _auth_lock:
                _ensure_valid_token(self.client)
            headers = {"Content-Type": "application/json"}
            headers.update(auth_header())  # fresh bearer every attempt
            try:
                resp = self.client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:
                raise ModelWallClockTimeout(
                    "model transport error on completions call: %s: %s"
                    % (type(exc).__name__, exc)) from exc
            status = getattr(resp, "status_code", 0)
            if 200 <= status < 300:
                obj = _parse_body(resp.content)
                return obj if isinstance(obj, dict) \
                    else {"choices": [{"text": str(obj)}]}
            if status in (401, 403):
                if _should_retry(status):
                    force_refresh_token(self.client)
                else:
                    invalidate_token()
            if _should_retry(status) and attempt < 3:
                remaining = deadline_at - self._clock()
                if remaining <= 0:
                    raise ModelWallClockTimeout(
                        "model wait exceeded its clamped deadline of "
                        "%.1fs" % deadline)
                delay = _retry_after_seconds(resp)
                if delay is None:
                    delay = min(8.0, 2.0 ** attempt)  # base 2, cap 8
                _sm_sleep(min(max(delay, 0.0), remaining))
                attempt += 1
                continue
            raise RuntimeError("completion request failed: HTTP %s after "
                               "%d retries" % (status, attempt))

    def _model_wait(self, messages, max_tokens, phase):
        budgets = self.budgets
        deadline = _wait_deadline_s(budgets, self.model_wait_s)
        self._wait_seq += 1
        call_id = "%s-w%d" % (self._child_id or "ds", self._wait_seq)
        start = self._clock()
        try:
            obj = self._run_once(messages, max_tokens, deadline)
        except DSClockTimeoutError as exc:
            audit("model-wait call=%s phase=%s deadline=%.1f outcome=%s"
                  % (call_id, phase.name, deadline, type(exc).__name__))
            raise
        end = self._clock()
        text = finish = ""
        if isinstance(obj, dict):
            choices = obj.get("choices") or [{}]
            first = choices[0] or {}
            raw = first.get("text") if isinstance(first, dict) else None
            if not isinstance(raw, str):
                raw = extract_text(obj)
            text = parse_response(raw or "")
            if isinstance(first, dict) and \
                    isinstance(first.get("finish_reason"), str):
                finish = first["finish_reason"]
        if text:
            chunks = text.split(CHUNK_SEP)
            first_at = self._clock()
            if first_at - start >= budgets.firstOutputSeconds:
                raise FirstOutputTimeout(
                    "no first output within %.0fs of wait start"
                    % budgets.firstOutputSeconds)
            last_at = first_at
            for _ in chunks[1:]:
                arrived = self._clock()
                if arrived - last_at >= budgets.idleSeconds:
                    raise ModelIdleTimeout(
                        "no further output for %.0fs after output began"
                        % budgets.idleSeconds)
                last_at = arrived
            waited = last_at - start
        else:
            waited = end - start
            if budgets.firstOutputSeconds > 0 and \
                    waited >= budgets.firstOutputSeconds:
                raise FirstOutputTimeout(
                    "no first output within %.0fs of wait start"
                    % budgets.firstOutputSeconds)
        if waited >= deadline:
            raise ModelWallClockTimeout(
                "model wait exceeded its clamped deadline of %.1fs"
                % deadline)
        self.model_wait_s += waited
        if CHUNK_SEP in text:
            text = text.replace(CHUNK_SEP, "")
        audit("model-wait call=%s phase=%s deadline=%.1f outcome=ok "
              "waited=%.3f finish=%s"
              % (call_id, phase.name, deadline, waited, finish or "stop"))
        return text, finish

    # -- prompts -----------------------------------------------------------

    def _plan_prompt(self, repair=None):
        task = ("Produce a research plan JSON array (no prose, no fences) "
                "with 1-%d steps for the question. Each step is an object: "
                '{"n": int, "action": "search" or "read", "target": '
                "query-or-URL string, \"why\": string}.\nQuestion: %s"
                % (self.budgets.maxSteps, self.question))
        if self.instructions:
            task += "\nInstructions: %s" % self.instructions
        if repair:
            task += ("\nThe previous plan was invalid (%s). Reply with "
                     "only the corrected JSON array." % repair)
        task += "\n/no_think"
        return [{"role": "system",
                 "content": "You are the planning module of a deep-research "
                            "agent. Reply with machine-parseable JSON only."},
                {"role": "user", "content": task}]

    def _reason_prompt(self):
        evidence = json.dumps(
            [{"url": s.get("url"), "title": s.get("title"),
              "snippet": (s.get("snippet") or "")[:240]}
             for s in self.sources], default=str)[:6000]
        gaps = "; ".join(self._gap_notes)[:1000] or "none"
        task = ("Question: %s\nPlan: %s\nSources: %s\nGap notes: %s\n"
                "Assess coverage and reply with ONE JSON object only: "
                '{"decision": "gap" or "sufficient", "query": string, '
                '"why": string}'
                % (self.question,
                   json.dumps(self.plan, default=str)[:2000],
                   evidence, gaps))
        task += "\n/no_think"
        return [{"role": "system",
                 "content": "You assess research coverage. Reply in JSON "
                            "only."},
                {"role": "user", "content": task}]

    def _synth_prompt(self, partial=None):
        blocks = []
        for src in self.sources:
            if not src.get("fetched"):
                continue
            blocks.append("URL: %s\nTITLE: %s\nTEXT: %s"
                          % (src.get("url"), src.get("title") or "",
                             re.sub(r"\s+", " ", str(src["fetched"]))[:4000]))
        context = "\n\n".join(blocks) or "(no fetched text; use snippets)"
        snips = "; ".join((s.get("snippet") or "")[:200]
                          for s in self.sources)[:4000]
        urls = ", ".join(s["url"] for s in self.sources)
        task = ("Write a cited markdown report answering: %s\n"
                "Instructions: %s\nSource snippets: %s\nFetched full text:\n"
                "%s\nRules: cite ONLY these URLs, as markdown links "
                "[label](url): %s. Output markdown only."
                % (self.question, self.instructions or "none", snips,
                   context[:12000], urls))
        if self._budget_stopped:
            task += ("\nNOTE: the search budget was exhausted before all "
                     "planned searches ran; synthesize from the evidence "
                     "gathered and state remaining gaps explicitly.")
        if partial:
            task += ("\nFinish this partial report; reply with the "
                     "remaining markdown only:\n" + partial[:6000])
        return [{"role": "system",
                 "content": "You write concise, cited markdown research "
                            "reports."},
                {"role": "user", "content": task}]

    # -- phases ------------------------------------------------------------

    def _phase_planning(self):
        text, _finish = self._model_wait(self._plan_prompt(), 4096,
                                         State.PLANNING)
        raw = _extract_json(text, "[", "]")
        reason = _plan_validation_error(raw, self.budgets.maxSteps) or "unknown"
        plan = (_normalize_plan(raw)
                if _validate_plan(raw, self.budgets.maxSteps) else [])
        if not plan:
            audit("plan invalid (%s); one repair attempt" % reason)
            text, _finish = self._model_wait(self._plan_prompt(reason),
                4096, State.PLANNING)
            raw = _extract_json(text, "[", "]")
            if _validate_plan(raw, self.budgets.maxSteps):
                plan = _normalize_plan(raw)
        if not plan:
            raise ValueError("plan_invalid: model plan still invalid after "
                             "one repair attempt")
        self.plan = plan
        self._pending = [dict(a) for a in plan if a["action"] == "search"]

    def _phase_searching(self):
        while self._pending:
            if self._actions_done + 1 > self.budgets.maxSteps:
                self._budget_stopped = True
                audit("budget exhausted; %d pending search(es) skipped; "
                      "proceeding to synthesis with %d source(s)"
                      % (len(self._pending), len(self.sources)))
                break
            action = self._pending.pop(0)
            target = action["target"]
            norm = " ".join(str(target).lower().split())
            if norm in self._seen_queries:
                audit("duplicate search skipped (already executed): %r"
                      % target)
                self._gap_notes.append("duplicate search skipped: %r"
                                       % target)
                continue
            self._seen_queries.add(norm)
            self._begin_action()
            k = max(1, self.budgets.maxSources - len(self.sources))
            ok, data = self._tool_post("search", self.search_endpoint,
                                       {"query": target, "max_results": k})
            if not ok or not isinstance(data, dict):
                self._gap_notes.append("search failed for %r" % target)
                continue
            self._collect_results(data.get("results") or [])

    def _collect_results(self, results):
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url or url in self._url_by_source:
                continue
            if len(self.sources) >= self.budgets.maxSources:
                break
            src = {"url": url,
                   "title": str(item.get("title") or ""),
                   "snippet": str(item.get("snippet") or "")[
                       :self.budgets.snippetMaxChars],
                   "fetched": None}
            self._url_by_source[url] = src
            self.sources.append(src)

    def _phase_reasoning(self):
        text, _finish = self._model_wait(self._reason_prompt(), 512,
                                         State.REASONING)
        obj = _extract_json(text, "{", "}")
        if not self._reason_valid(obj):
            audit("reasoning malformed; one retry, then sufficient")
            text, _finish = self._model_wait(self._reason_prompt(), 512,
                                             State.REASONING)
            obj = _extract_json(text, "{", "}")
        if self._reason_valid(obj) and obj.get("decision") == "gap":
            query = str(obj["query"]).strip()
            why = str(obj.get("why") or "gap")
            norm = " ".join(query.lower().split())
            if norm and norm in self._seen_queries:
                audit("gap loop terminated (duplicate gap query): %r"
                      % query)
                self._gap_notes.append("dup gap: %s" % why[:200])
                return "sufficient"
            self._gap_streak += 1
            if self._gap_streak > MAX_GAP_STREAK:
                audit("gap loop terminated (max %d consecutive gaps): %r"
                      % (MAX_GAP_STREAK, query))
                self._gap_notes.append("gap streak cap: %s" % why[:200])
                return "sufficient"
            self._gap_notes.append("gap: %s" % why[:200])
            self._pending.append({"action": "search", "target": query,
                                  "why": why})
            return "gap"
        self._gap_streak = 0
        return "sufficient"

    @staticmethod
    def _reason_valid(obj):
        if not isinstance(obj, dict):
            return False
        decision = obj.get("decision")
        if decision == "sufficient":
            return True
        return decision == "gap" and bool(str(obj.get("query") or "").strip())

    def _phase_reading(self):
        order = []
        seen = set()
        for step in self.plan:  # plan order first, then search relevance
            if step["action"] == "read" and step["target"] \
                    in self._url_by_source and step["target"] not in seen:
                seen.add(step["target"])
                order.append(step["target"])
        for src in self.sources:
            if src["url"] not in seen:
                seen.add(src["url"])
                order.append(src["url"])
        for url in order:
            src = self._url_by_source[url]
            ok, data = self._tool_post("read", self.read_endpoint,
                                       {"url": url})
            text = ""
            if ok:
                if isinstance(data, dict):
                    text = data.get("text") or data.get("content") or ""
                elif isinstance(data, str):
                    text = data
            src["fetched"] = str(text) if str(text).strip() else None

    def _phase_synthesizing(self):
        text, finish = self._model_wait(self._synth_prompt(),
                                        SYNTHESIS_MAX_TOKENS,
                                        State.SYNTHESIZING)
        if finish == "length" or not text.strip():
            audit("synthesis incomplete (finish=%s, chars=%d); exactly one "
                  "recovery pass" % (finish or "stop", len(text)))
            recovery, _rf = self._model_wait(
                self._synth_prompt(partial=text), SYNTHESIS_MAX_TOKENS,
                State.SYNTHESIZING)
            if finish == "length":
                text = ((text + "\n" + recovery).strip()
                        if recovery.strip() else text)
            else:
                text = recovery
            if not text.strip():
                raise ValueError("synthesis_invalid_after_recovery: report "
                                 "empty after one recovery pass")
        self.report = self._postprocess_report(text)

    def _postprocess_report(self, text):
        masked, spans = _mask_code_spans(text)  # mask code spans first
        allowed = {s["url"] for s in self.sources
                  if s.get("fetched")}
        stripped = []

        def _strip_link(match):
            url = match.group(2).rstrip(".,);")
            if url not in allowed:
                stripped.append(url)
                return match.group(1) + ")"
            return match.group(0)

        def _strip_bare(match):
            url = match.group(0).rstrip(".,);")
            if url not in allowed:
                stripped.append(url)
                return ""
            return match.group(0)

        masked = re.sub(r"(\[[^\]]*\]\()(https?://[^)\s]+)(\))",
                        _strip_link, masked)
        masked = re.sub(r"https?://[^\s)\]\"'<>]+", _strip_bare, masked)
        for url in stripped:
            if url in self._url_by_source:
                audit("citation stripped (source fetch failed or empty): %s"
                      % url)
            else:
                audit("citation stripped (url not in gathered sources): %s"
                      % url)
        masked = _redact_ips(masked)
        return _restore_code_spans(masked, spans)

    # -- results + driver ----------------------------------------------------

    def _budgets_used(self):
        return {"model_wait_s": round(self.model_wait_s, 3),
                "tool_s": round(self.tool_s, 3),
                "wall_s": round(self._wall, 3),
                "steps": self._actions_done,
                "sources": len(self.sources),
                "briefs": 0,
                "synthesis_max_tokens": SYNTHESIS_MAX_TOKENS}

    def _run_result(self, status, report, error=None):
        if self._t0 is not None:
            self._wall = self._clock() - self._t0
        return DeepSearchResult(
            status=status, report=report,
            sources=[dict(s) for s in self.sources],
            plan=[dict(a) for a in self.plan],
            state_trace=self.state_trace,
            budgets_used=self._budgets_used(), error=error)

    def _fail(self, cls, message):
        at = self.state or State.PLANNING
        error = {"class": cls, "message": str(message),
                 "state_at_failure": at.name}
        self.error = error
        self.report = ""
        self._transition(at, State.FAILED, "%s: %s" % (cls, message))
        return self._run_result("FAILED", "", error)

    async def run(self):
        self._t0 = self._clock()
        self._child_id = _ledger_open()
        self.state = State.PLANNING
        self._trace(State.PLANNING.name, "run start (parent=%s scope=%s)"
                    % (LEDGER_PARENT, LEDGER_SCOPE))
        audit("run start child=%s question=%.80s"
              % (self._child_id, self.question))
        self._progress(State.PLANNING, "run start")
        try:
            self._phase_planning()
            self._transition(State.PLANNING, State.SEARCHING,
                             "plan ready: %d step(s)" % len(self.plan))
            gap_loop_start = self._clock()
            while True:
                if self._clock() - gap_loop_start > GAP_LOOP_WALL_CAP_S:
                    raise TimeoutError(
                        "gap loop exceeded wall-clock cap of %.0fs"
                        % GAP_LOOP_WALL_CAP_S)
                self._phase_searching()
                self._transition(State.SEARCHING, State.REASONING,
                                 "actions executed: %d/%d"
                                 % (self._actions_done,
                                    self.budgets.maxSteps))
                decision = self._phase_reasoning()
                if decision == "sufficient" or self._budget_stopped:
                    break
                self._transition(State.REASONING, State.SEARCHING,
                                 "gap loop (next action %d/%d)"
                                 % (self._actions_done + 1,
                                    self.budgets.maxSteps))
            self._transition(State.REASONING, State.READING,
                             "evidence sufficient; fetching source text")
            self._phase_reading()
            self._transition(State.READING, State.SYNTHESIZING,
                             "source text gathered")
            self._phase_synthesizing()
            self._transition(State.SYNTHESIZING, State.DONE,
                             "report complete")
            result = self._run_result("DONE", self.report)
        except BudgetExhausted as exc:
            result = self._fail("budget_exhausted", str(exc))
        except DSClockTimeoutError as exc:
            result = self._fail("model_timeout_unrecoverable",
                                "%s: %s" % (type(exc).__name__, exc))
        except ValueError as exc:
            message = str(exc)
            if message.startswith("plan_invalid"):
                cls = "plan_invalid"
            elif message.startswith("synthesis_invalid_after_recovery"):
                cls = "synthesis_invalid_after_recovery"
            else:
                raise
            result = self._fail(cls, message)
        except (ConnectionError, httpx.HTTPError, TimeoutError) as exc:
            result = self._fail("backends_unreachable", _safe_detail(exc))
        except OSError as exc:
            result = self._fail("backends_unreachable", _safe_detail(exc))
        _ledger_finish(self._child_id,
                       "done" if result.status == "DONE" else "failed",
                       {"status": result.status, "error": result.error,
                        "budgets_used": result.budgets_used})
        audit("terminal status=%s child=%s error_class=%s"
              % (result.status, self._child_id,
                 (result.error or {}).get("class") or "none"))
        return result


def deep_search(
    question: str,
    instructions: str = "",
    budgets: Budgets | None = None,
    *,
    search_endpoint: str = "http://127.0.0.1:9703",
    read_endpoint: str = "http://127.0.0.1:9703",
    model_endpoint: str = "http://127.0.0.1:8080/v1",
    model_name: str = "qwen3.8-flash-next-unsloth-ud-iq4_xs",
    on_progress=None,
    client=None,
):
    """Run the deep-research state machine (never touches real endpoints
    unless real endpoints are injected). Synchronous input validation;
    returns a coroutine that yields a DeepSearchResult when awaited."""
    if not isinstance(question, str) or len(question) > 2000:
        raise ValueError("question must be a string of at most 2000 chars")
    if not isinstance(instructions, str) or len(instructions) > 32000:
        raise ValueError("instructions must be a string of at most 32000 "
                         "chars")
    if budgets is None:
        budgets = Budgets()
    if not isinstance(budgets, Budgets):
        raise ValueError("budgets must be a Budgets instance")
    return _deep_search_impl(question, instructions, budgets,
                             search_endpoint=search_endpoint,
                             read_endpoint=read_endpoint,
                             model_endpoint=model_endpoint,
                             model_name=model_name,
                             on_progress=on_progress, client=client)


async def _deep_search_impl(question, instructions, budgets, *,
                            search_endpoint, read_endpoint,
                            model_endpoint, model_name, on_progress,
                            client):
    ds = DeepSearch(question, instructions, budgets,
                    search_endpoint=search_endpoint,
                    read_endpoint=read_endpoint,
                    model_endpoint=model_endpoint, model_name=model_name,
                    on_progress=on_progress, client=client)
    return await ds.run()



_selftest_lock = threading.RLock()
_selftest_config = None
_selftest_db = None
_selftest_client = None


def _new_state():
    global _auth_lock, token_cache, token_lock, _config_lock, _config
    global overrides_applied
    with token_lock:
        token_cache.clear()
    _config = dict(DEFAULT_CONFIG)
    overrides_applied = False


class _StubResponse:
    def __init__(self, status_code=200, payload=None, headers=None,
                 raw_text=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._raw_text = raw_text

    @property
    def content(self):
        payload = self._raw_text
        if payload is None:
            payload = self._payload if self._payload is not None \
                else {"results": []}
        return json.dumps(payload).encode("utf-8")

    def json(self):
        payload = self._raw_text
        if payload is None:
            payload = self._payload if self._payload is not None \
                else {"results": []}
        return payload


def _default_log_dir():
    """Base directory under which logs/audit.log will be written."""
    env = os.environ.get("DEEP_SEARCH_LOG_DIR")
    if env:
        return env
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(os.path.join(base, "logs"), exist_ok=True)
        return base
    except OSError:
        import tempfile
        return tempfile.gettempdir()


def _ensure_log_dir():
    global LOG_DIR
    if not LOG_DIR:
        set_log_dir(_default_log_dir())
    return LOG_DIR


class StubClient:
    """Injected transport fake: no real network I/O in the selftest."""

    def __init__(self, reply=None, token="tok-abcdef0123456789ABCDEF",
                 token_requests=None):
        self.reply = reply if reply is not None else {"results": ["ok"]}
        self.token = token
        self.token_requests = [] if token_requests is None else token_requests
        self.requests = []
        self.scripted = []
        self.calls = []

    def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append({"url": url, "json": json,
                           "headers": dict(headers or {})})
        self.requests.append((url, json, dict(headers or {})))
        if url.endswith("/v1alpha2/token"):
            if isinstance(json, dict):
                self.token_requests.append(json)
            return _StubResponse(200, {"access_token": self.token,
                                       "expires_in": 3600})
        if self.scripted:
            resp = self.scripted.pop(0)
            if isinstance(resp, tuple):
                if len(resp) == 2:
                    status, hdr = resp
                    payload = self.reply
                else:
                    status, payload, hdr = resp
                return _StubResponse(status, payload=payload,
                                     headers=hdr or {})
            return resp
        return _StubResponse(200, payload=self.reply)


def _completion_body(call):
    body = call.get("json")
    if not isinstance(body, dict):
        raise SelfTestError("completion request body must be an object")
    return body


def _check_section_1(client):
    msgs = [
        {"role": "system", "content": "sys: be careful"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "content":
            "tool evidence chunk: " + "evidence text " * 40,
         "tool_call_id": "call_1", "name": "search"},
        {"role": "assistant", "content": "final"},
    ]
    generate([dict(m) for m in msgs], client=client,
             model="self-test-model", max_tokens=32)
    expected = "".join(
        "<|im_start|>%s\n%s.<|im_end|>\n" % (m["role"], m["content"])
        for m in msgs) + "<|im_start|>assistant\n"
    body = _completion_body(client.calls[-1])
    prompt = body.get("prompt")
    if not isinstance(prompt, str):
        raise SelfTestError("completion body lacks a prompt string")
    if prompt != expected:
        raise SelfTestError("prompt was not assembled by the one ChatML "
                            "template (%d template tokens, expected %d)"
                            % (prompt.count("<|im_start|>"), len(msgs) + 1))
    if prompt.count("<|im_start|>") != len(msgs) + 1:
        raise SelfTestError("template tokens found off the sole path")
    if body.get("model") != "self-test-model":
        raise SelfTestError("model not forwarded in body")
    s1 = ChatSession(system="sys", model="self-test-model", client=client)
    s1.add_message("user", "hello")
    s1.add_message("assistant", "hi")
    if s1.chatml_prompt() != serialize_chatml(s1.messages):
        raise SelfTestError("session prompt must rebuild via the one "
                            "template")
    if not s1.chatml_prompt().endswith("<|im_start|>assistant\n"):
        raise SelfTestError("session prompt must end with the primer")
    if parse_response("hello world.<|im_end|>GARBAGE") != "hello world":
        raise SelfTestError("parse_response failed to recover cleanly")


def _check_section_2(client, token_requests):
    configure(proxy_url="http://proxy.invalid", model="self-test-model")
    token_cache.clear()
    tok1 = refresh_token(client, force=True)
    tok2 = refresh_token(client, force=True)
    if not tok1 or tok2 != tok1:
        raise SelfTestError("token cache must return a stable valid token")
    if not token_requests:
        raise SelfTestError("no token request observed for the grant")
    last = token_requests[-1]
    if not isinstance(last, dict) or \
            last.get("grantType") != "client_credentials":
        raise SelfTestError("token request must be a client_credentials "
                            "grant")
    hdr = auth_header()
    if "Authorization" not in hdr:
        raise SelfTestError("auth_header() must yield the bearer header")
    if hdr["Authorization"] != "Bearer " + tok1:
        raise SelfTestError("auth_header() must be a fresh read")
    results = []
    errors = []

    def hammer():
        try:
            results.append(refresh_token(client))
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    before = sum(1 for c in client.calls
                 if str(c["url"]).endswith("/v1alpha2/token"))
    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    if errors or len(set(results)) != 1:
        raise SelfTestError("concurrent refresh must not corrupt the cache")
    after = sum(1 for c in client.calls
                if str(c["url"]).endswith("/v1alpha2/token"))
    if after != before:
        raise SelfTestError("concurrent refresh double-minted a token")


class RetryAfterClient(StubClient):
    """Scripted completion statuses with Retry-After headers."""

    def __init__(self, statuses, token="tok-abcdef0123456789ABCDEF",
                 reply=None):
        StubClient.__init__(self, reply=reply, token=token)
        for item in statuses:
            status, hdr = item if isinstance(item, tuple) else (item, {})
            self.scripted.append((status, self.reply, hdr))


def _check_retries(client):
    configure(proxy_url="http://proxy.invalid", model="self-test-model")
    if not _should_retry(429):
        raise SelfTestError("429 must be retryable")
    if not (_should_retry(500) and _should_retry(503)
            and _should_retry(599) and not _should_retry(200)):
        raise SelfTestError("5xx must be retryable")
    client.scripted = [(429, {"Retry-After": "0"}), (503, {})]
    out = send_chatml(client, [{"role": "user", "content": "ping"}],
                      "self-test-model", max_tokens=16, max_retries=3,
                      retry_backoff=0.0, sleep_func=_sleep_small)
    if not isinstance(out, str):
        raise SelfTestError("retry chain must still return parsed text")
    completions = [c for c in client.calls
                   if str(c["url"]).endswith("/v1/completions")]
    if len(completions) != 3:
        raise SelfTestError("expected 3 completion attempts, got %d"
                            % len(completions))
    seen = [c for c in completions
           if c["headers"].get("Authorization", "")[7:] != client.token]
    if seen:
        raise SelfTestError("every attempt must send the freshly read "
                            "bearer")


def _check_section_3(client, token_requests):
    tool = _FakeTool()
    call = json.dumps({"name": "search",
                       "arguments": {"query": "weather today"}})
    client.scripted = [_StubResponse(200, raw_text=call),
                       _StubResponse(200, raw_text="none")]
    text, results = generate(
        [{"role": "user", "content": "weather?"}],
        client=client, model="self-test-model", tool=tool,
        max_tokens=16)
    client.scripted = []
    if tool.calls != 1:
        raise SelfTestError("tool must run exactly once, got %d"
                            % tool.calls)
    if text != "none":
        raise SelfTestError("final text must be the last assistant turn")
    if len(results) != tool.calls:
        raise SelfTestError("tool exchanges missing from transcript")
    bodies = [_completion_body(c) for c in client.calls
              if str(c["url"]).endswith("/v1/completions")]
    bodies = bodies[-(tool.calls + 1):]
    prompts = [b["prompt"] for b in bodies]
    if len(prompts) != tool.calls + 1:
        raise SelfTestError("expected one more prompt than tool runs")
    for p in prompts[1:]:
        if "<|im_start|>tool\n" not in p:
            raise SelfTestError("tool response must continue as a ChatML "
                                "tool message")
    if "<|im_start|>tool\n" in prompts[0]:
        raise SelfTestError("first round must not contain tool results")
    prompt = prompts[-1]
    for evidence in ("evidence", "Example Domain", "example.com"):
        if evidence.lower() not in prompt.lower():
            raise SelfTestError("tool evidence must flow back in the "
                                "next ChatML prompt (%s missing)"
                                % evidence)
    if prompt.count("<|im_start|>tool\n") < tool.calls:
        raise SelfTestError("each tool result must be one tool message")
    big = _big_results()
    text_blob = format_tool_results(big)
    if context_token_estimate(
            [{"role": "tool", "content": text_blob}]) > TOOL_RESULT_BUDGET:
        raise SelfTestError("tool-result channel must be budget-capped")


def _big_results(n=25):
    out = []
    for i in range(n):
        out.append({"title": "Doc %d" % i,
                    "url": "https://example.com/%d" % i,
                    "snippet": "lo ipsum dolor sit amet " * 40})
    return out


class _FakeTool:
    def __init__(self):
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        return [{"title": "Example Domain",
                 "url": "https://example.com",
                 "snippet": "evidence: the current status is sunny"}]


def _check_section_4(client):
    base = _recorded_calls()
    create_task("parent")
    record_call(name="quick_search")(lambda: "x")()
    decorated = record_call(name="full_search")(lambda: "y")
    decorated()
    calls = _recorded_calls()
    if len(calls) < len(base) + 2:
        raise SelfTestError("call recording must land in task_calls")
    names = [row[0] for row in calls[-2:]]
    if names != ["quick_search", "full_search"]:
        raise SelfTestError("record_call must persist the given names")
    before = _child_run_rows()
    agent = "%s-check-%f" % (MODULE_ID, time.time())
    record_child_run(0, agent, result="selftest")
    now = _child_run_rows()
    if now <= before:
        raise SelfTestError("child_runs row was not inserted")
    line = audit("selftest audit line")
    if "selftest audit line" not in line or MODULE_ID not in line:
        raise SelfTestError("audit line must carry ISO timestamp, UA, msg")
    if not line.startswith(_now_iso()[:10]):
        raise SelfTestError("audit line must start with ISO timestamp")


def _recorded_calls():
    try:
        conn = _open_conn()
    except sqlite3.Error:
        return []
    try:
        return conn.execute(
            "SELECT name FROM task_calls ORDER BY id").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _child_run_rows():
    try:
        conn = _open_conn()
    except sqlite3.Error:
        return 0
    try:
        return conn.execute("SELECT COUNT(*) FROM child_runs").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def _check_section_6(client):
    if not FLUSH_MARKER.startswith("[INST] <<SYS>>") or \
            "memory consolidation agent" not in FLUSH_MARKER:
        raise SelfTestError("sleep-time marker constant must not change")
    if MAX_TURNS != 4:
        raise SelfTestError("MAX_TURNS must stay 4")
    long_conv = "word " * 4000
    truncated = truncate_conversation(long_conv)
    if not truncated or len(truncated) > ITEM_TOKEN_CAP:
        raise SelfTestError("conversations must be truncated for cost")
    fake_items = [(10 ** 9 + i, "conv %d" % i, None) for i in range(9)]
    before = _child_run_rows()
    processed = flush_once(client, "self-test-model", parent_id=None,
                           auditor=Auditor(MODULE_ID), items=fake_items,
                           write_db=False)
    if processed > MAX_TURNS:
        raise SelfTestError("flush_once must hard-cap at MAX_TURNS items")
    seen = sum(1 for c in client.calls if c["url"])
    if seen == 0:
        raise SelfTestError("flusher must route work through quick search")
    prompts = [_completion_body(c)["prompt"] for c in client.calls
               if str(c["url"]).endswith("/v1/completions")]
    if not any(FLUSH_MARKER in p for p in prompts):
        raise SelfTestError("sleep-time prompt must embed the marker")
    if _child_run_rows() != before:
        raise SelfTestError("dry run must not write child_runs")


def _seed_config_probe(pairs):
    try:
        conn = _open_conn()
        try:
            ensure_schema(conn)
            with conn:
                for k, v in pairs.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO configs (key, value) "
                        "VALUES (?, ?)", (k, str(v)))
        finally:
            conn.close()
        return True
    except sqlite3.Error:
        return False


def _clear_config_probe(keys):
    try:
        conn = _open_conn()
        try:
            with conn:
                for k in keys:
                    conn.execute("DELETE FROM configs WHERE key = ?", (k,))
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def _check_section_7(client=None):
    global overrides_applied
    with _selftest_lock:
        saved_config = get_config()
        saved_flag = overrides_applied
        seeded = None
        try:
            configure(proxy_url="http://pre.override.invalid",
                      log_dir=None)
            if not load_config_overrides():
                seeded = {"temperature": "0.42",
                          "proxy_url": "http://overridden.invalid"}
                if not _seed_config_probe(seeded):
                    audit("selftest: configs table unavailable; "
                          "override probe skipped")
                    seeded = None
            overrides_applied = False
            applied = apply_db_overrides()
            if overrides_applied is not True:
                raise SelfTestError("override application must set the "
                                    "idempotency flag")
            if not isinstance(applied, dict):
                raise SelfTestError("apply_db_overrides must return the "
                                    "applied mapping")
            rows = load_config_overrides()
            if rows:
                cfg = get_config()
                if "proxy_url" in rows and str(cfg.get("proxy_url")) \
                        != str(rows["proxy_url"]):
                    raise SelfTestError("proxy_url override missing")
                for key in _float_keys_rows(rows):
                    want = _coerce(key, rows[key])
                    if want is not None and cfg.get(key) != want:
                        raise SelfTestError("override not applied: %s"
                                            % key)
            overrides_applied = False
            if apply_db_overrides() is None:
                raise SelfTestError("second application must be a no-op")
            if overrides_applied is not True:
                raise SelfTestError("apply_db_overrides must be idempotent")
        finally:
            if seeded:
                _clear_config_probe(seeded)
            with _config_lock:
                _config.clear()
                _config.update(saved_config)
                overrides_applied = saved_flag


def _float_keys_rows(rows):
    return [k for k in rows if k in _FLOAT_KEYS or k in _INT_KEYS]


def _check_db_unavailable():
    global overrides_applied
    saved_config = get_config()
    saved_flag = overrides_applied
    try:
        configure(db_path="/proc/self/nope/nope.db")
        overrides_applied = False
        applied = apply_db_overrides()
        if applied.get("searcher") != "mock":
            raise SelfTestError("broken DB must force the local mock "
                                "searcher")
        if applied.get("proxy_url"):
            raise SelfTestError("broken DB must disable remote-provided "
                                "settings")
    finally:
        with _config_lock:
            _config.clear()
            _config.update(saved_config)
            overrides_applied = saved_flag


def _check_entries(client):
    t_full = full_search("full query", model="self-test-model",
                         client=client)
    if not isinstance(t_full, threading.Thread):
        raise SelfTestError("full_search must return the worker thread")
    if t_full is None:
        raise SelfTestError("full_search returned nothing")
    text = quick_search("quick query", model="self-test-model",
                        client=client)
    if not isinstance(text, str):
        raise SelfTestError("quick_search must return answer text")
    t_full.join(5)
    if t_full.is_alive():
        raise SelfTestError("full_search worker must finish cleanly")


def _check_db_child_run(client):
    global overrides_applied
    saved_config = get_config()
    saved_flag = overrides_applied
    try:
        if not _seed_selftest_item():
            audit("selftest db not writable; child-run DB leg skipped")
            return
        before = _child_run_rows()
        processed = flush_once(client, "self-test-model", parent_id=None,
                               auditor=Auditor(MODULE_ID))
        after = _child_run_rows()
        if processed < 1 or after <= before:
            raise SelfTestError("flush_once must write one child_runs row "
                                "per processed item")
    finally:
        with _config_lock:
            _config.clear()
            _config.update(saved_config)
            overrides_applied = saved_flag


def _check_section_5():
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(60):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role,
                     "content": "message number %d %s" % (i, "lorem " * 30)})
    budget = context_token_estimate(msgs) // 3
    if budget >= context_token_estimate(msgs):
        raise SelfTestError("estimate must be positive")
    kept = enforce_context_budget(msgs, budget)
    if kept[0]["role"] != "system" or kept[0]["content"] != "sys":
        raise SelfTestError("the system prompt must always be preserved")
    if kept[-1] != msgs[-1]:
        raise SelfTestError("the most recent message must be preserved")
    if context_token_estimate(kept) >= context_token_estimate(msgs):
        raise SelfTestError("compaction failed to shrink the transcript")
    if context_token_estimate(kept) > budget:
        raise SelfTestError("budget still exceeded after compaction")
    if any("<" in m["content"] and "|im_" in m["content"] for m in kept):
        raise SelfTestError("summaries must not synthesize ChatML tokens")


# ---------------------------------------------------------------------------
# State-machine selftest helpers (every step name below contains the literal
# lowercase phrase "state machine"; fully offline via StubClient + fake clock)
# ---------------------------------------------------------------------------

SM_SEARCH_ENDPOINT = "http://sm-search.invalid"
SM_READ_ENDPOINT = "http://sm-read.invalid"


class _FakeClock:
    """Deterministic fake monotonic clock (state-machine selftest only)."""

    def __init__(self, step=0.01, start=0.0):
        self.step = step
        self.t = start

    def __call__(self):
        value = self.t
        self.t += self.step
        return value


def _sm_completion(text, finish="stop"):
    return _StubResponse(200, payload={"choices": [{"text": text,
                                                    "finish_reason":
                                                        finish}]})


def _sm_search_result(url, title):
    return _StubResponse(200, payload={"results": [
        {"url": url, "title": title,
         "snippet": "snippet for %s" % title}]})


_SM_GAP = json.dumps({"decision": "gap", "query": "more alpha",
                      "why": "need more evidence"})
_SM_SUFFICIENT = json.dumps({"decision": "sufficient",
                             "why": "coverage sufficient"})
_SM_GAP_DUP = json.dumps({"decision": "gap", "query": "  ALPHA ",
                          "why": "retry of same query"})
_SM_ONE_SEARCH_PLAN = json.dumps(
    [{"n": 1, "action": "search", "target": "alpha", "why": "start"}])


def _sm_happy_script(report=None):
    if report is None:
        report = ("# Report\n\nThe alpha-beta link follows "
                  "[a](https://good.example/a) and "
                  "[b](https://good.example/b).\n")
    plan = json.dumps([
        {"n": 1, "action": "search", "target": "alpha",
         "why": "find alpha"},
        {"n": 2, "action": "search", "target": "beta", "why": "find beta"}])
    return [
        _sm_completion(plan),
        _sm_search_result("https://good.example/a", "Alpha"),
        _sm_search_result("https://good.example/b", "Beta"),
        _sm_completion(_SM_SUFFICIENT),
        _StubResponse(200, payload={"text": "Alpha full text evidence."}),
        _StubResponse(200, payload={"text": "Beta full text evidence."}),
        _sm_completion(report),
    ]


def _sm_run(client, question="state machine probe question", budgets=None,
            on_progress=None, step=0.01):
    global _monotonic
    saved = _monotonic
    _monotonic = _FakeClock(step=step)
    try:
        return asyncio.run(deep_search(
            question, "", budgets,
            search_endpoint=SM_SEARCH_ENDPOINT,
            read_endpoint=SM_READ_ENDPOINT,
            model_endpoint="http://model.invalid/v1",
            model_name="self-test-model",
            on_progress=on_progress, client=client))
    finally:
        _monotonic = saved


def _sm_states(result):
    return [entry["state"] for entry in result.state_trace]


def _sm_completion_calls(stub):
    return sum(1 for c in stub.calls
               if str(c["url"]).endswith("/v1/completions"))


def _sm_endpoint_calls(stub, endpoint):
    return sum(1 for c in stub.calls if c["url"] == endpoint)


def _check_sm_happy_path(client=None):
    progress = []
    stub = StubClient()
    stub.scripted = _sm_happy_script()
    result = _sm_run(stub, on_progress=lambda s, n: progress.append(
        (s.name if isinstance(s, State) else str(s), n)))
    if result.error is not None:
        raise SelfTestError("happy path errored: %r" % (result.error,))
    if result.status != "DONE":
        raise SelfTestError("happy path status %r" % result.status)
    if not result.report:
        raise SelfTestError("happy path report empty")
    expected = ["PLANNING", "SEARCHING", "REASONING", "READING",
                "SYNTHESIZING", "DONE"]
    if _sm_states(result) != expected:
        raise SelfTestError("state_trace %r != %r"
                            % (_sm_states(result), expected))
    if len(progress) != 6:
        raise SelfTestError("on_progress must fire on every transition")
    if result.budgets_used["steps"] != 2 or len(result.sources) != 2:
        raise SelfTestError("budget accounting wrong: %r"
                            % (result.budgets_used,))
    if "https://good.example/a" not in result.report:
        raise SelfTestError("valid citation was not kept")


def _check_sm_transition_legality(client=None):
    legal = set(LEGAL_TRANSITIONS) | {(s, State.FAILED) for s in State}
    happy = StubClient()
    happy.scripted = _sm_happy_script()
    happy_result = _sm_run(happy, question="state machine legality happy")
    plan = json.dumps([{"n": 1, "action": "search", "target": "alpha",
                        "why": "start"}])
    gap_stub = StubClient()
    gap_stub.scripted = [
        _sm_completion(plan),
        _sm_search_result("https://gap.example/1", "One"),
        _sm_completion(_SM_GAP),
        _sm_search_result("https://gap.example/2", "Two"),
        _sm_completion(_SM_SUFFICIENT),
        _StubResponse(200, payload={"text": "One full text."}),
        _StubResponse(200, payload={"text": "Two full text."}),
        _sm_completion("Looped report per [a](https://gap.example/1)."),
    ]
    gap_result = _sm_run(gap_stub, question="state machine legality gap")
    loops = 0
    for res in (happy_result, gap_result):
        seq = _sm_states(res)
        pairs = list(zip(seq, seq[1:]))
        for frm, to in pairs:
            if (State(frm), State(to)) not in legal:
                raise SelfTestError("illegal transition %s -> %s"
                                    % (frm, to))
        loops += sum(1 for f, t in pairs
                     if (f, t) == ("REASONING", "SEARCHING"))
    if gap_result.status != "DONE" or loops != 1:
        raise SelfTestError("gap loop missing or malformed (loops=%d)"
                            % loops)
    for res in (happy_result, gap_result):
        pairs = set(zip(_sm_states(res), _sm_states(res)[1:]))
        if ("PLANNING", "READING") in pairs or ("SEARCHING", "READING") \
                in pairs:
            raise SelfTestError("extra pair outside the legal loop found")


def _check_sm_maxsteps(client=None):
    stub = StubClient()
    stub.scripted = [_sm_completion(_SM_ONE_SEARCH_PLAN),
                     _sm_search_result("https://cap.example/1", "C1"),
                     _sm_completion(_SM_GAP),
                     _sm_search_result("https://cap.example/2", "C2"),
                     _sm_completion(_SM_GAP),
                     _sm_completion(_SM_SUFFICIENT),
                     _StubResponse(200,
                                   payload={"text":
                                            "C1 full text evidence."}),
                     _StubResponse(200,
                                   payload={"text":
                                            "C2 full text evidence."}),
                     _sm_completion(
                         "## Partial report\nAnswer based on "
                         "[C1](https://cap.example/1).")]
    result = _sm_run(stub, question="state machine maxsteps probe",
                     budgets=Budgets(maxSteps=2))
    if result.status != "DONE":
        raise SelfTestError(
            "budget stop must synthesize a partial report, got %s %r"
            % (result.status, (result.error or {}).get("class")))
    if not result.report.strip():
        raise SelfTestError("partial report must be non-empty")
    if _sm_endpoint_calls(stub, SM_SEARCH_ENDPOINT) != 2:
        raise SelfTestError("search POST past the cap: %d"
                            % _sm_endpoint_calls(stub, SM_SEARCH_ENDPOINT))
    probe = StubClient()
    ds = DeepSearch("cap probe", "", Budgets(maxSteps=2),
                    search_endpoint=SM_SEARCH_ENDPOINT,
                    read_endpoint=SM_READ_ENDPOINT,
                    model_endpoint="http://model.invalid/v1",
                    model_name="self-test-model", client=probe)
    ds._actions_done = 2
    ds._pending = [{"action": "search", "target": "x", "why": "y"}]
    raised = False
    try:
        ds._begin_action()
    except BudgetExhausted:
        raised = True
    if not raised:
        raise SelfTestError("over-cap action must raise BudgetExhausted")
    if probe.calls:
        raise SelfTestError("BudgetExhausted must precede any tool call")


def _check_sm_loop_termination(client=None):
    log_path = os.path.join(LOG_DIR or ".", AUDIT_LOG)
    try:
        with open(log_path, errors="replace") as fh:
            before = fh.read()
    except OSError:
        before = ""
    stub = StubClient()
    replies = [_sm_completion(_SM_ONE_SEARCH_PLAN)]
    for i in range(2):
        replies.append(_sm_search_result("https://spin.example/%d" % i,
                                         "Spin %d" % i))
        replies.append(_sm_completion(_SM_GAP))
    replies.append(_StubResponse(
        200, payload={"text": "Spin 0 full text."}))
    replies.append(_StubResponse(
        200, payload={"text": "Spin 1 full text."}))
    replies.append(_sm_completion(
        "## Report\nSpins follow [S0](https://spin.example/0)."))
    stub.scripted = replies
    result = _sm_run(stub, question="state machine loop termination probe",
                     budgets=Budgets(maxSteps=4))
    if result.status != "DONE":
        raise SelfTestError(
            "always-gap loop must terminate via duplicate-gap stop + "
            "synthesis, got %s %r"
            % (result.status, (result.error or {}).get("class")))
    if _sm_endpoint_calls(stub, SM_SEARCH_ENDPOINT) != 2:
        raise SelfTestError(
            "duplicate gap re-searched: %d call(s)"
            % _sm_endpoint_calls(stub, SM_SEARCH_ENDPOINT))
    if _sm_completion_calls(stub) != 4:
        raise SelfTestError(
            "plan + 2 gap + synthesis expected, got %d"
            % _sm_completion_calls(stub))
    try:
        with open(log_path, errors="replace") as fh:
            after = fh.read()
    except OSError:
        after = ""
    new = after[len(before):] if after.startswith(before) else after
    if "gap loop terminated (duplicate gap query)" not in new:
        raise SelfTestError("duplicate gap stop was not audit-logged")
    if _sm_states(result)[-1] != "DONE":
        raise SelfTestError("duplicate-gap-stop run must terminate in DONE")


def _sm_wait_once(budgets, reply, phase=State.PLANNING, text=None):
    ds = DeepSearch("timeout probe", "", budgets,
                    search_endpoint=SM_SEARCH_ENDPOINT,
                    read_endpoint=SM_READ_ENDPOINT,
                    model_endpoint="http://model.invalid/v1",
                    model_name="self-test-model", client=StubClient())
    ds.client.scripted = [reply]
    return ds._model_wait([{"role": "user", "content": "p"}], 16, phase)


def _check_sm_timeout_classes(client=None):
    global _monotonic
    for cls in (FirstOutputTimeout, ModelIdleTimeout,
                ModelWallClockTimeout):
        if not (isinstance(cls, type) and issubclass(cls, Exception)):
            raise SelfTestError("timeout class missing: %r" % (cls,))
    saved = _monotonic
    messages = {}
    try:
        _monotonic = _FakeClock(step=5.0)
        try:
            _sm_wait_once(Budgets(firstOutputSeconds=1),
                          _sm_completion(""))
            raise SelfTestError("FirstOutputTimeout not raised")
        except FirstOutputTimeout as exc:
            messages["FirstOutputTimeout"] = str(exc)
        chunked = _sm_completion("first output" + CHUNK_SEP + "tail")
        try:
            _sm_wait_once(Budgets(idleSeconds=1, firstOutputSeconds=300),
                          chunked)
            raise SelfTestError("ModelIdleTimeout not raised")
        except ModelIdleTimeout as exc:
            messages["ModelIdleTimeout"] = str(exc)
        try:
            _sm_wait_once(Budgets(modelTimeoutSeconds=2),
                          _sm_completion("a single late chunk"))
            raise SelfTestError("ModelWallClockTimeout not raised")
        except ModelWallClockTimeout as exc:
            messages["ModelWallClockTimeout"] = str(exc)
    finally:
        _monotonic = saved
    if len(set(messages.values())) != 3 or any(
            not m for m in messages.values()):
        raise SelfTestError("timeout messages must exist and differ: %r"
                            % (messages,))
    if len({"FirstOutputTimeout", "ModelIdleTimeout",
            "ModelWallClockTimeout"}) != 3:
        raise SelfTestError("timeout class names must differ")
    stub = StubClient()
    stub.scripted = [_sm_completion("")]
    result = _sm_run(stub, question="state machine timeout run",
                     budgets=Budgets(firstOutputSeconds=1), step=5.0)
    if result.status != "FAILED":
        raise SelfTestError("first-output timeout must FAIL the run")
    err = result.error or {}
    if err.get("class") != "model_timeout_unrecoverable":
        raise SelfTestError("expected model_timeout_unrecoverable, got %r"
                            % (err,))
    if err.get("state_at_failure") != "PLANNING":
        raise SelfTestError("state_at_failure must be the failing phase")


def _check_sm_budget_clamp(client=None):
    if _wait_deadline_s(Budgets(modelTimeoutSeconds=7200,
                                totalBudgetSeconds=100), 0.0) != 100:
        raise SelfTestError("remaining-budget cap not enforced")
    if _wait_deadline_s(Budgets(modelTimeoutSeconds=7200,
                                totalBudgetSeconds=100000), 0.0) != 3600:
        raise SelfTestError("hard 3600 cap not enforced")
    if _wait_deadline_s(Budgets(modelTimeoutSeconds=30), 0.0) != 30:
        raise SelfTestError("small modelTimeoutSeconds must win")
    if _wait_deadline_s(Budgets(totalBudgetSeconds=5), 10.0) != 1.0:
        raise SelfTestError("remaining must clamp at 1.0")
    if _wait_deadline_s(Budgets(), 0.0) != Budgets().modelTimeoutSeconds:
        raise SelfTestError("default clamp must equal modelTimeoutSeconds")


def _check_sm_bool_budgets(client=None):
    defaults = {
        "totalBudgetSeconds": 1800, "modelTimeoutSeconds": 420,
        "toolTimeoutSeconds": 300, "briefTimeoutSeconds": 900,
        "firstOutputSeconds": 420, "idleSeconds": 120, "maxSteps": 8,
        "maxSources": 10, "maxBriefs": 2, "snippetMaxChars": 4000}
    names = sorted(Budgets.__dataclass_fields__)
    if names != sorted(defaults) or len(names) != 10:
        raise SelfTestError("Budgets fields drifted: %r" % (names,))
    inst = Budgets()
    for name in names:
        if getattr(inst, name) != defaults[name]:
            raise SelfTestError("default drifted for %s" % name)
        for bad in (True, False):
            try:
                Budgets(**{name: bad})
                raise SelfTestError("bool %r accepted for %s"
                                    % (bad, name))
            except ValueError:
                pass
        ok = Budgets(**{name: 5})
        if getattr(ok, name) != 5:
            raise SelfTestError("plain int rejected for %s" % name)
    for oversize in (("q" * 2001, ""), ("ok", "i" * 32001)):
        coro = None
        try:
            coro = deep_search(oversize[0], oversize[1])
        except ValueError:
            continue
        finally:
            if coro is not None:
                coro.close()
        raise SelfTestError("oversize input accepted: %r" % (oversize,))


def _check_sm_citations(client=None):
    log_path = os.path.join(LOG_DIR or ".", AUDIT_LOG)
    try:
        with open(log_path, errors="replace") as fh:
            before = fh.read()
    except OSError:
        before = ""
    report = ("# R\n\nkept [a](https://good.example/a); stripped "
              "[b](https://evil.example/x); bare https://evil.example/y "
              "stripped; time 12:30:45 kept\nhosts 10.9.8.7, ::1 and "
              "fd12::345 must go; public 8.8.8.8 and "
              "`code https://evil.example/in-code` kept\n")
    stub = StubClient()
    stub.scripted = _sm_happy_script(report=report)
    result = _sm_run(stub, question="state machine citation probe")
    if result.status != "DONE":
        raise SelfTestError("citation stripping must still reach DONE")
    if "https://evil.example/x" in result.report \
            or "https://evil.example/y" in result.report:
        raise SelfTestError("bad citation survived validation")
    if "https://good.example/a" not in result.report:
        raise SelfTestError("good citation was dropped")
    if "10.9.8.7" in result.report or "fd12::345" in result.report \
            or "::1 " in result.report:
        raise SelfTestError("non-public IP not redacted")
    if "8.8.8.8" not in result.report:
        raise SelfTestError("public IP was over-redacted")
    if "12:30:45" not in result.report:
        raise SelfTestError("clock time must not be masked as IPv6")
    if "https://evil.example/in-code" not in result.report:
        raise SelfTestError("code spans must be restored untouched")
    try:
        with open(log_path, errors="replace") as fh:
            after = fh.read()
    except OSError:
        after = ""
    new = after[len(before):] if after.startswith(before) else after
    if "citation stripped" not in new:
        raise SelfTestError("stripped citation was not logged to audit")


def _check_sm_citation_validity(client=None):
    """F1: URLs whose read failed (403) must not survive in citations."""
    log_path = os.path.join(LOG_DIR or ".", AUDIT_LOG)
    try:
        with open(log_path, errors="replace") as fh:
            before = fh.read()
    except OSError:
        before = ""
    report = ("# R\n\nkept [a](https://good.example/a); "
              "dropped [c](https://blocked.example/c)\n")
    stub = StubClient()
    stub.scripted = [
        _sm_completion(_SM_ONE_SEARCH_PLAN),
        _StubResponse(200, payload={"results": [
            {"url": "https://good.example/a", "title": "Alpha",
             "snippet": "snippet for Alpha"},
            {"url": "https://blocked.example/c", "title": "Blocked",
             "snippet": "snippet for Blocked"},
        ]}),
        _sm_completion(_SM_SUFFICIENT),
        _StubResponse(200, payload={"text": "Alpha full text evidence."}),
        _StubResponse(403, payload=None),
        _sm_completion(report),
    ]
    result = _sm_run(stub, question="state machine citation validity probe")
    if result.status != "DONE":
        raise SelfTestError("citation validity probe must reach DONE")
    if "https://good.example/a" not in result.report:
        raise SelfTestError("fetched-source citation was dropped")
    if "https://blocked.example/c" in result.report:
        raise SelfTestError("fetch-failed citation survived validation")
    try:
        with open(log_path, errors="replace") as fh:
            after = fh.read()
    except OSError:
        after = ""
    new = after[len(before):] if after.startswith(before) else after
    if "citation stripped (source fetch failed or empty)" not in new:
        raise SelfTestError("fetch-failed citation was not audit-logged")


def _check_sm_gap_dedup(client=None):
    """F2: duplicate plan search targets are skipped, not re-executed."""
    log_path = os.path.join(LOG_DIR or ".", AUDIT_LOG)
    try:
        with open(log_path, errors="replace") as fh:
            before = fh.read()
    except OSError:
        before = ""
    plan = json.dumps([
        {"n": 1, "action": "search", "target": "alpha",
         "why": "find alpha"},
        {"n": 2, "action": "search", "target": "  ALPHA ",
         "why": "dup"},
    ])
    report = "# R\n\n[a](https://good.example/a)\n"
    stub = StubClient()
    stub.scripted = [
        _sm_completion(plan),
        _sm_search_result("https://good.example/a", "Alpha"),
        _sm_completion(_SM_SUFFICIENT),
        _StubResponse(200, payload={"text": "Alpha full text evidence."}),
        _sm_completion(report),
    ]
    result = _sm_run(stub, question="state machine gap dedup probe")
    if result.status != "DONE":
        raise SelfTestError("gap dedup probe must reach DONE")
    search_calls = _sm_endpoint_calls(stub, SM_SEARCH_ENDPOINT)
    if search_calls != 1:
        raise SelfTestError(
            "duplicate gap query re-executed: %d search call(s)"
            % search_calls)
    if result.budgets_used.get("steps") != 1:
        raise SelfTestError("duplicate search consumed step budget")
    try:
        with open(log_path, errors="replace") as fh:
            after = fh.read()
    except OSError:
        after = ""
    new = after[len(before):] if after.startswith(before) else after
    if "duplicate search skipped (already executed)" not in new:
        raise SelfTestError("duplicate search skip was not audit-logged")


def _check_sm_synth_recovery(client=None):
    base = _sm_happy_script()[:-1]
    stub = StubClient()
    stub.scripted = list(base) + [
        _sm_completion("## Partial findings per "
                       "[a](https://good.example/a).", finish="length"),
        _sm_completion("\nrecovered tail per "
                       "[b](https://good.example/b)."),
    ]
    result = _sm_run(stub, question="state machine recovery probe")
    if result.status != "DONE":
        raise SelfTestError("length recovery must reach DONE: %r"
                            % (result.error,))
    synth_calls = _sm_completion_calls(stub) - 2  # minus plan + reasoning
    if synth_calls != 2:
        raise SelfTestError("expected exactly one recovery pass, got %d"
                            % synth_calls)
    if "Partial findings" not in result.report \
            or "recovered tail" not in result.report:
        raise SelfTestError("recovery output not merged into report")
    stub2 = StubClient()
    stub2.scripted = list(base) + [_sm_completion(""), _sm_completion("")]
    result2 = _sm_run(stub2, question="state machine recovery failed")
    if result2.status != "FAILED":
        raise SelfTestError("empty-after-recovery must FAIL")
    if (result2.error or {}).get("class") \
            != "synthesis_invalid_after_recovery":
        raise SelfTestError("expected synthesis_invalid_after_recovery, "
                            "got %r" % (result2.error,))
    if result2.report != "":
        raise SelfTestError("FAILED runs must carry an empty report")


def _sm_child_runs():
    try:
        conn = _open_conn()
    except sqlite3.Error:
        return None
    try:
        try:
            return set(conn.execute(
                "SELECT child_id, status FROM child_runs WHERE scope = ? "
                "AND parent_task_id = ?",
                (LEDGER_SCOPE, LEDGER_PARENT)).fetchall())
        except sqlite3.Error:
            return None
    finally:
        conn.close()


def _sm_task_blocks_rows():
    try:
        conn = _open_conn()
    except sqlite3.Error:
        return -1
    try:
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM task_blocks").fetchone()[0]
        except sqlite3.Error:
            return -1
    finally:
        conn.close()


def _check_sm_tasks_db(client=None):
    tb_before = _sm_task_blocks_rows()
    rows_before = _sm_child_runs()
    stub = StubClient()
    stub.scripted = _sm_happy_script()
    result = _sm_run(stub, question="state machine ledger probe")
    if result.status != "DONE":
        raise SelfTestError("ledger probe run must reach DONE")
    if _sm_task_blocks_rows() != tb_before:
        raise SelfTestError("task_blocks rows changed; module must never "
                            "touch task_blocks")
    rows_after = _sm_child_runs()
    if rows_after is None or rows_before is None:
        audit("selftest: child_runs schema lacks scope/parent_task_id; "
              "state machine row check degraded to audit-only")
        return
    new = rows_after - rows_before
    if not any(status in ("done", "failed")
               for (_child, status) in new):
        raise SelfTestError("no terminal child_runs row "
                            "(scope deep-search-core, parent 0d0ba451)")


def _check_sm_ok_print(client=None):
    """Verify the single SELFTEST OK print sits on run_selftest's success path.

    Line-anchored matching: this function's own source text must never be
    counted or matched, so no whole-file literal search is used.
    """
    try:
        with open(__file__, errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise SelfTestError("cannot read module source: %s"
                            % _safe_detail(exc))
    needle = 'print(' + '"SELFTEST' + ' OK")'
    try:
        i0 = next(i for i, l in enumerate(lines)
                  if l.startswith("def run_selftest("))
        i1 = next(i for i in range(i0 + 1, len(lines))
                  if lines[i].startswith("def _late_bindings"))
    except StopIteration:
        raise SelfTestError("cannot locate run_selftest / _late_bindings in "
                            "module source")
    segment_lines = lines[i0:i1]
    if sum(1 for l in segment_lines
           if l.strip().startswith(needle)) != 1:
        raise SelfTestError("run_selftest must print SELFTEST OK exactly "
                            "once")
    if not any('audit("selftest exit 0")' in l for l in segment_lines):
        raise SelfTestError("existing audit('selftest exit 0') line must "
                            "stay")


_SELFTEST_STEPS = [
    ("section-2-auth", lambda c, t: _check_section_2(c, t)),
    ("section-2-retries", lambda c, t: _check_retries(c)),
    ("section-1-chatml", lambda c, t: _check_section_1(c)),
    ("section-3-loop", lambda c, t: _check_section_3(c, t)),
    ("section-5-compaction", lambda c, t: _check_section_5()),
    ("section-4-audit-tasks", lambda c, t: _check_section_4(c)),
    ("section-6-flusher", lambda c, t: _check_section_6(c)),
    ("section-7-config", lambda c, t: _check_section_7()),
    ("section-7-db-unavailable", lambda c, t: _check_db_unavailable()),
    ("entry-points", lambda c, t: _check_entries(c)),
    ("child-run-db", lambda c, t: _check_db_child_run(c)),
    ("sm-happy-path", lambda c, t: _check_sm_happy_path(c)),
    ("sm-transition-legality", lambda c, t: _check_sm_transition_legality(c)),
    ("sm-maxsteps", lambda c, t: _check_sm_maxsteps(c)),
    ("sm-loop-termination", lambda c, t: _check_sm_loop_termination(c)),
    ("sm-timeout-classes", lambda c, t: _check_sm_timeout_classes(c)),
    ("sm-budget-clamp", lambda c, t: _check_sm_budget_clamp(c)),
    ("sm-bool-budgets", lambda c, t: _check_sm_bool_budgets(c)),
    ("sm-citations", lambda c, t: _check_sm_citations(c)),
    ("sm-citation-validity",
     lambda c, t: _check_sm_citation_validity(c)),
    ("sm-gap-dedup", lambda c, t: _check_sm_gap_dedup(c)),
    ("sm-synth-recovery", lambda c, t: _check_sm_synth_recovery(c)),
    ("sm-tasks-db", lambda c, t: _check_sm_tasks_db(c)),
    ("sm-ok-print", lambda c, t: _check_sm_ok_print(c)),
]


def run_selftest():
    """Run the built-in offline self-tests. Exit code in, exit code out."""
    _new_state()
    apply_db_overrides()
    set_log_dir(_default_log_dir())
    configure(model="self-test-model", proxy_url="http://proxy.invalid",
              searcher="mock", user_agent=MODULE_ID)
    token_requests = []
    client = StubClient(reply={"results": ["selftest reply"]},
                        token_requests=token_requests)
    audit("selftest start")
    for name, step in _SELFTEST_STEPS:
        try:
            step(client, token_requests)
            audit("selftest step ok: %s" % name)
        except Exception as exc:
            detail = (str(exc) if isinstance(exc, SelfTestError)
                      else _safe_detail(exc))
            audit("selftest step FAILED: %s (%s)" % (name, detail))
            print("SELFTEST FAILED: %s: %s" % (name, detail),
                  file=sys.stderr)
            return 1
    print("SELFTEST OK")
    audit("selftest exit 0")
    return 0
def _late_bindings():
    _wrap_recorded()
    _ensure_log_dir()




def _build_parser():
    parser = argparse.ArgumentParser(
        prog=MODULE_ID,
        description="Deep-search agent core (public contract module).")
    parser.add_argument("--selftest", action="store_true",
                        help="run the built-in offline self-tests "
                             "(exit 0 on pass)")
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    return run_selftest() if args.selftest else 0


_late_bindings()

if __name__ == "__main__":
    sys.exit(main())
