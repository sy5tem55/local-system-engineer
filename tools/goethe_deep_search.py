import os
"""goethe_deep_search.py — DeepSearchMixin for the Goethe gateway.

Defines DeepSearchMixin (an MRO-only mixin; it never defines __init__,
valves or _log) plus _DSAdapterClient, an httpx.Client-compatible adapter
that translates the frozen deep_search_core's model and tool plumbing onto
what Strata and websearch-lb actually speak.  Import surface: stdlib +
httpx + deep_search_core only.  Run with --selftest for the offline test
suite.
"""

import asyncio
import json
import re
import sys

import httpx

import deep_search_core as core

_json = json

_IM_START = "<|im_start|>"
_IM_END = "<|im_end|>\n"
_CHATML_TERM = "." + _IM_END

_HEX32_RE = re.compile(r"[0-9a-f]{32}")


def _oneline(value):
    text = value if isinstance(value, str) else str(value)
    return " ".join(text.split())[:200]


class _FakeResp:
    """Minimal httpx.Response stand-in: status_code, content, headers."""

    def __init__(self, status_code, content, headers=None):
        self.status_code = status_code
        self.content = content if isinstance(content, bytes) else \
            str(content).encode("utf-8")
        self.headers = headers or {}


def _resp_bytes(resp):
    content = getattr(resp, "content", b"") or b""
    return content if isinstance(content, bytes) else str(content).encode(
        "utf-8")


def _resp_text(resp):
    return _resp_bytes(resp).decode("utf-8", "replace")


def _iter_sse(text):
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                obj = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(obj, dict):
                yield obj


def _parse_chatml(prompt):
    messages = []
    if not isinstance(prompt, str) or not prompt.startswith(_IM_START):
        raise ValueError("bad_chatml: missing leading %s" % _IM_START)
    for chunk in prompt.split(_IM_START)[1:]:
        head, sep, rest = chunk.partition("\n")
        if not sep:
            raise ValueError("bad_chatml: role line unterminated")
        if chunk == head + "\n" and head == "assistant":
            break
        if rest == "assistant\n":
            break
        idx = rest.rfind(_CHATML_TERM)
        if idx == -1:
            raise ValueError("bad_chatml: missing terminator")
        content = rest[:idx]
        if content.endswith("."):
            content = content[:-1]
        messages.append({"role": head, "content": content})
    return messages


class _McpAuth(Exception):
    pass


class _DSAdapterClient:
    """httpx.Client-compatible adapter injected into core.deep_search.

    Rewrites the core's token + ChatML-completions calls onto Strata's
    chat-completions API and translates the core's plain-HTTP tool posts
    into websearch-lb's MCP streamable-HTTP dialect.
    """

    def __init__(self, model_base, lb_search, lb_read, model_key,
                 lb_token="", base_client=None):
        self._model_base = model_base
        self._lb_search = str(lb_search or "").rstrip("/")
        self._lb_read = str(lb_read or "").rstrip("/")
        self._model_key = model_key or ""
        self._lb_token = lb_token or ""
        self._sessions = {}
        if base_client is not None:
            self._base = base_client
        else:
            self._base = httpx.Client(timeout=httpx.Timeout(
                connect=10.0, read=480.0, write=60.0, pool=10.0))

    def close(self):
        try:
            self._base.close()
        except AttributeError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def post(self, url, json=None, headers=None, **kw):
        raw = str(url)
        u = raw.rstrip("/")
        if u.endswith("/v1alpha2/token"):
            payload = _json.dumps({"access_token": self._model_key,
                                   "expires_in": 3600})
            return _FakeResp(200, payload.encode("utf-8"))
        if isinstance(json, dict) and "/v1/completions" in raw:
            return self._chat_rewrite(raw, json, headers)
        if isinstance(json, dict):
            if self._lb_search and u == self._lb_search and "query" in json:
                return self._lb(u, "web_search_balanced",
                                {"query": json["query"],
                                 "max_results": json.get("max_results", 5)},
                                True)
            if self._lb_read and u == self._lb_read and "url" in json:
                return self._lb(u, "read_url", {"url": json["url"]}, False)
        return self._base.post(raw, json=json, headers=headers, **kw)

    def _chat_rewrite(self, raw, payload, headers):
        try:
            messages = _parse_chatml(payload.get("prompt"))
        except ValueError:
            return _FakeResp(500, json.dumps({"error": "bad_chatml"})
                             .encode("utf-8"))
        body = {"model": payload.get("model"),
                "messages": messages,
                "max_tokens": payload.get("max_tokens"),
                "temperature": payload.get("temperature", 1.0)}
        resp = self._base.post(
            raw.replace("/v1/completions", "/v1/chat/completions"),
            json=body, headers=dict(headers or {}))
        status = getattr(resp, "status_code", 0)
        if not (200 <= status < 300):
            return _FakeResp(status, _resp_bytes(resp),
                             getattr(resp, "headers", None))
        try:
            data = json.loads(_resp_text(resp))
            choice = (data.get("choices") or [{}])[0] or {}
            text = ((choice.get("message") or {}).get("content")) or ""
            finish = choice.get("finish_reason") or "stop"
        except (ValueError, AttributeError, IndexError, KeyError):
            return _FakeResp(500, json.dumps({"error": "bad_chat_response"})
                             .encode("utf-8"))
        mapped = {"choices": [{"text": text, "finish_reason": finish}]}
        return _FakeResp(200, json.dumps(mapped).encode("utf-8"))

    def _lb(self, endpoint, tool, arguments, is_search):
        try:
            result = self._tool_call(endpoint, tool, arguments)
            if is_search and not isinstance(result, dict):
                result = {"ok": False, "error": "mcp_bad_tool_payload"}
            if not is_search and isinstance(result, dict) \
                    and result.get("ok") is True:
                md = result.get("markdown")
                payload = {"text": md if isinstance(md, str) else ""}
            else:
                payload = result
            return _FakeResp(200, json.dumps(payload).encode("utf-8"))
        except _McpAuth:
            return _FakeResp(200, json.dumps(
                {"ok": False, "error": "mcp_auth"}).encode("utf-8"))
        except Exception as exc:
            return _FakeResp(200, json.dumps(
                {"ok": False, "error": _oneline(exc)}).encode("utf-8"))

    def _mcp_headers(self, session=None):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self._lb_token:
            headers["Authorization"] = "Bearer %s" % self._lb_token
        if session:
            headers["mcp-session-id"] = session
        return headers

    def _mcp_post(self, endpoint, body, headers):
        return self._base.post(endpoint + "/mcp", json=body, headers=headers)

    def _rpc(self, endpoint, body, want_id, session=None):
        resp = self._mcp_post(endpoint, body, self._mcp_headers(session))
        status = getattr(resp, "status_code", 0) or 0
        if status in (401, 403):
            raise _McpAuth()
        if not (200 <= status < 300):
            raise RuntimeError("mcp_http_%s" % status)
        got = None
        for obj in _iter_sse(_resp_text(resp)):
            if obj.get("id") == want_id:
                got = obj
                break
        if got is None:
            raise RuntimeError("mcp_no_response_id_%s" % want_id)
        if got.get("error"):
            raise RuntimeError("mcp_rpc_error")
        hdrs = getattr(resp, "headers", None) or {}
        try:
            session_id = hdrs.get("mcp-session-id")
        except AttributeError:
            session_id = None
        return got, session_id

    def _initialize(self, endpoint):
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18",
                           "capabilities": {},
                           "clientInfo": {"name": "deep-search-mixin",
                                          "version": "1.0.0"}}}
        _resp, session = self._rpc(endpoint, body, 1)
        nstatus = getattr(self._mcp_post(
            endpoint,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            self._mcp_headers(session)), "status_code", 0) or 0
        if nstatus in (401, 403):
            raise _McpAuth()
        if not (200 <= nstatus < 300):
            raise RuntimeError("mcp_notify_%s" % nstatus)
        return session or ""

    def _tool_call(self, endpoint, name, arguments):
        session = self._sessions.get(endpoint)
        if session is None:
            session = self._initialize(endpoint)
            self._sessions[endpoint] = session
        resp, _ = self._rpc(
            endpoint,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": name, "arguments": arguments}},
            2, session=session)
        result = resp.get("result") or {}
        text = ""
        try:
            text = str((result.get("content") or [{}])[0].get("text") or "")
        except (AttributeError, IndexError):
            text = ""
        if result.get("isError"):
            return {"ok": False, "error": _oneline(text)
                    or "mcp_tool_error"}
        try:
            tool = json.loads(text)
        except ValueError:
            raise RuntimeError("mcp_unparseable_tool_text")
        if not isinstance(tool, dict):
            raise RuntimeError("mcp_tool_text_not_object")
        return tool


def _failed_dict(cls, message, state):
    return {"status": "FAILED", "report": "", "sources": [], "plan": [],
            "state_trace": [], "budgets_used": {},
            "error": {"class": cls, "message": message,
                      "state_at_failure": state}}


class DeepSearchMixin:
    """MRO-only deep-research mixin; host supplies valves + _log + search_kb."""

    _KB_BLOCK_HEAD = (
        "\n\nLocal KB context (verified environment knowledge — prefer "
        "over\nassumptions; cite only URLs from live sources):\n")

    async def deep_search(self, question: str, instructions: str = "",
                          max_steps: int | None = None,
                          target_sources: int | None = None) -> dict:
        """Run one deep-research pass and return a cited research report.

        question is the research question (non-empty string, at most 2000
        characters) and instructions is optional extra guidance (string, at
        most 32000 characters); max_steps and target_sources, when given,
        must be plain ints >= 1 and override the planner's step and source
        budget caps. Best-effort local-KB context from search_kb is appended
        to instructions before planning, and a raised KB lookup is logged by
        exception class name only and otherwise ignored. The returned dict
        mirrors the core DeepSearchResult: status ("DONE" or "FAILED"),
        report (cited markdown, empty when FAILED), sources, plan,
        state_trace, budgets_used and error (None or
        {class, message, state_at_failure}). Failure modes: malformed
        arguments raise ValueError; an empty DEEP_SEARCH_MODEL_API_KEY valve
        returns a FAILED dict whose error.class is ConfigurationError
        instead of raising; and any model/tool transport failure degrades to
        a FAILED dict with the exception class name logged — the model API
        key is never logged, returned, or embedded in an error message.
        """
        if not isinstance(question, str) or not question \
                or len(question) > 2000:
            raise ValueError("question must be a non-empty string of at "
                             "most 2000 chars")
        if not isinstance(instructions, str) or len(instructions) > 32000:
            raise ValueError("instructions must be a string of at most "
                             "32000 chars")
        for name, value in (("max_steps", max_steps),
                            ("target_sources", target_sources)):
            if value is not None and (isinstance(value, bool)
                                      or not isinstance(value, int)
                                      or value < 1):
                raise ValueError("%s must be an int >= 1" % name)

        try:
            kb_text = self.search_kb(question, max_results=3)
        except Exception as exc:
            self._log("deep_search: KB context unavailable: %s"
                      % type(exc).__name__)
        else:
            kb_text = (kb_text if isinstance(kb_text, str)
                       else str(kb_text or ""))[:6000]
            instructions = instructions + self._KB_BLOCK_HEAD + kb_text
            self._log("deep_search: KB context injected (%d chars)"
                      % len(kb_text))

        key = getattr(self.valves, "DEEP_SEARCH_MODEL_API_KEY", "") or os.environ.get("GOETHE_PLANNER_FORCE_API_KEY", "")
        if not key:
            self._log("deep_search: refused — DEEP_SEARCH_MODEL_API_KEY "
                      "empty")
            return _failed_dict(
                "ConfigurationError",
                "DEEP_SEARCH_MODEL_API_KEY valve is empty", "PLANNING")

        model_url = getattr(self.valves, "DEEP_SEARCH_MODEL_URL",
                            "http://node3090.home.arpa:8080")
        model_name = getattr(
            self.valves, "DEEP_SEARCH_MODEL_NAME",
            "qwen3.8-flash-next-unsloth-ud-iq4_xs")
        search_url = getattr(self.valves, "DEEP_SEARCH_SEARCH_URL",
                             "http://127.0.0.1:9703")
        read_url = getattr(self.valves, "DEEP_SEARCH_READ_URL",
                           "http://127.0.0.1:9703")
        lb_token = getattr(self.valves, "DEEP_SEARCH_LB_TOKEN", "")
        log_dir = getattr(self.valves, "DEEP_SEARCH_LOG_DIR", "")

        core.configure(proxy_url=model_url, model=model_name)
        if log_dir:
            core.set_log_dir(log_dir)
        budgets = core.Budgets()
        if max_steps is not None:
            budgets.maxSteps = max_steps
        if target_sources is not None:
            budgets.maxSources = target_sources

        client = _DSAdapterClient(model_base=model_url,
                                  lb_search=search_url,
                                  lb_read=read_url,
                                  model_key=key,
                                  lb_token=lb_token)
        progress = lambda s, n: self._log("deep_search %s: %s" % (s, n))
        try:
            try:
                coro = core.deep_search(
                    question, instructions, budgets=budgets,
                    search_endpoint=search_url, read_endpoint=read_url,
                    on_progress=progress, client=client)
                result = await coro
            except Exception as exc:
                self._log("deep_search FAILED: %s %s"
                          % (type(exc).__name__,
                             _oneline(str(exc))[:200]))
                return _failed_dict(type(exc).__name__, str(exc),
                                    "UNKNOWN")
        finally:
            client.close()

        self._log("deep_search finished status=%s sources=%d trace_len=%d"
                  % (result.status, len(result.sources),
                     len(result.state_trace)))
        return {"status": result.status, "report": result.report,
                "sources": result.sources, "plan": result.plan,
                "state_trace": result.state_trace,
                "budgets_used": result.budgets_used,
                "error": None if result.error is None else result.error}


ALL_LOGS = []
PRINTED = []


def _emit(line):
    PRINTED.append(line)
    print(line)


class _FakeBase:
    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])
        self.closed = False

    def post(self, url, json=None, headers=None, **kw):
        self.requests.append({"url": str(url), "json": json,
                              "headers": dict(headers or {})})
        if self.responses:
            resp = self.responses.pop(0)
            if callable(resp):
                return resp(str(url), json, headers)
            return resp
        return _FakeResp(200, b"{}")

    def close(self):
        self.closed = True


class _RecAdapter:
    instances = []

    def __init__(self, **kw):
        self.kw = kw
        self.closed = False
        _RecAdapter.instances.append(self)

    def post(self, url, json=None, headers=None, **kw):
        return _FakeResp(200, b"{}")

    def close(self):
        self.closed = True


class _Valves:
    pass


def _mk_valves(**over):
    v = _Valves()
    v.DEEP_SEARCH_SEARCH_URL = "http://lb.test:9703"
    v.DEEP_SEARCH_READ_URL = "http://lb.test:9703"
    v.DEEP_SEARCH_MODEL_URL = "http://model.test:8080"
    v.DEEP_SEARCH_MODEL_NAME = "testmodel"
    v.DEEP_SEARCH_MODEL_API_KEY = "selftest-key"
    v.DEEP_SEARCH_LB_TOKEN = ""
    v.DEEP_SEARCH_LOG_DIR = ""
    for k, val in over.items():
        setattr(v, k, val)
    return v


class _Host:
    def __init__(self, valves=None, kb=None, kb_exc=None):
        self.valves = valves if valves is not None else _mk_valves()
        self.logs = []
        self._kb = kb
        self._kb_exc = kb_exc

    def _log(self, entry):
        self.logs.append(entry)
        ALL_LOGS.append(entry)

    def search_kb(self, question, max_results=3):
        if self._kb_exc is not None:
            raise self._kb_exc
        return self._kb


class _Stub2(_Host, DeepSearchMixin):
    pass


def _st_import():
    assert core.deep_search is not None


def _st_token():
    base = _FakeBase()
    ad = _DSAdapterClient("http://model.test:8080", "http://lb.test:9703",
                          "http://lb.test:9703", "selftest-key",
                          base_client=base)
    resp = ad.post("http://model.test:8080/v1alpha2/token",
                   json={"grantType": "client_credentials"})
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data.get("access_token") == "selftest-key", data
    assert data.get("expires_in") == 3600, data
    assert base.requests == [], "token request must not hit the base"


def _st_chatml():
    msgs2 = [{"role": "user", "content": "hello world"},
             {"role": "assistant", "content": "hi there"}]
    assert _parse_chatml(core.serialize_chatml(msgs2)) == msgs2
    msgs_empty = [{"role": "system", "content": ""}]
    assert _parse_chatml(core.serialize_chatml(msgs_empty)) == msgs_empty
    tricky = [{"role": "user",
               "content": "line one\nsub.< not a terminator\nline three"}]
    assert _parse_chatml(core.serialize_chatml(tricky)) == tricky
    try:
        _parse_chatml(_IM_START + "user\nno terminator here")
    except ValueError:
        return
    raise AssertionError("malformed chatml must raise ValueError")


def _sse(body_obj):
    return ("event: message\ndata: %s\n\n" % json.dumps(body_obj)
            ).encode("utf-8")


def _tool_sse(tool_obj, is_error=False):
    result = {"content": [{"type": "text", "text": json.dumps(tool_obj)}]}
    if is_error:
        result["isError"] = True
    return _sse({"jsonrpc": "2.0", "id": 2, "result": result})


def _st_mcp():
    init = _FakeResp(200, _sse({"jsonrpc": "2.0", "id": 1,
                                "result": {"protocolVersion": "2025-06-18",
                                           "capabilities": {},
                                           "serverInfo": {
                                               "name": "websearch-lb",
                                               "version": "1"}}}),
                    headers={"mcp-session-id": "sess-1"})
    found = {"ok": True, "results": [{"rank": 1, "title": "t", "url": "u",
                                      "snippet": "s", "backend": "b",
                                      "latency_ms": 1}]}
    base = _FakeBase([
        init,
        _FakeResp(202, b""),
        _FakeResp(200, _tool_sse(found)),
        _FakeResp(200, _tool_sse({"ok": True, "url": "u", "markdown": "M"})),
        _FakeResp(200, _tool_sse({"ok": False,
                                  "error": "jina_rate_limited"})),
    ])
    ad = _DSAdapterClient("http://model.test:8080", "http://lb.test:9703",
                          "http://lb.test:9703", "selftest-key",
                          base_client=base)
    r1 = ad.post("http://lb.test:9703", json={"query": "q", "max_results": 5})
    assert r1.status_code == 200
    d1 = json.loads(r1.content)
    assert d1.get("ok") is True and d1.get("results") == found["results"], d1
    r2 = ad.post("http://lb.test:9703", json={"url": "u"})
    assert r2.status_code == 200
    assert json.loads(r2.content) == {"text": "M"}
    r3 = ad.post("http://lb.test:9703", json={"url": "u"})
    assert r3.status_code == 200, r3.status_code
    assert json.loads(r3.content) == {"ok": False,
                                      "error": "jina_rate_limited"}
    assert len(base.requests) == 5, len(base.requests)
    for i, req in enumerate(base.requests):
        assert req["url"] == "http://lb.test:9703/mcp", req["url"]
        assert req["headers"].get(
            "Accept") == "application/json, text/event-stream", req
        if i >= 1:
            assert req["headers"].get("mcp-session-id") == "sess-1", \
                "session id not echoed on request %d" % i
    assert base.requests[1]["json"].get("method") == \
        "notifications/initialized"
    assert base.requests[2]["json"].get("method") == "tools/call"


def _expect_raises(exc_type, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc_type:
        return
    except Exception as exc:
        raise AssertionError("expected %s, got %r"
                             % (exc_type.__name__, exc))
    raise AssertionError("expected %s, nothing raised" % exc_type.__name__)


def _st_mixin():
    canned = core.DeepSearchResult(
        status="DONE", report="r",
        sources=[{"url": "u", "title": "t", "snippet": "s", "fetched": None}],
        plan=[{"n": 1, "action": "search", "target": "x", "why": "y"}],
        state_trace=[{"state": "DONE", "t_offset_s": 1.0, "note": "n"}],
        budgets_used={"model_s": 1.0}, error=None)
    rec = {}
    orig = (core.configure, core.deep_search, _DSAdapterClient)
    _RecAdapter.instances = []

    def fake_configure(**kw):
        rec["configure"] = kw

    def fake_deep_search(question, instructions, budgets=None, *,
                         search_endpoint=None, read_endpoint=None,
                         on_progress=None, client=None, **kw2):
        rec["deep_search"] = {"question": question,
                              "instructions": instructions,
                              "budgets": budgets,
                              "search_endpoint": search_endpoint,
                              "read_endpoint": read_endpoint,
                              "client": client}

        async def _coro():
            return canned
        return _coro()

    core.configure = fake_configure
    core.deep_search = fake_deep_search
    globals()["_DSAdapterClient"] = _RecAdapter
    try:
        stub = _Stub2()
        _expect_raises(ValueError, asyncio.run, stub.deep_search(""))
        _expect_raises(ValueError, asyncio.run,
                       stub.deep_search("Q", max_steps=True))
        _expect_raises(ValueError, asyncio.run,
                       stub.deep_search("Q", target_sources=0))

        stub = _Stub2(kb_exc=RuntimeError("boom-secret-msg"))
        out = asyncio.run(stub.deep_search("Q?", instructions="I1"))
        got = rec["deep_search"]["instructions"]
        assert got == "I1", "instructions must be unchanged after KB error"
        assert any("KB context unavailable" in l and "RuntimeError" in l
                   for l in stub.logs), stub.logs
        assert not any("boom-secret-msg" in l for l in stub.logs)

        stub = _Stub2(kb="HIT1\nHIT2")
        asyncio.run(stub.deep_search("Q?", instructions="I1",
                                     max_steps=3, target_sources=4))
        got = rec["deep_search"]["instructions"]
        assert "Local KB context" in got and "HIT1" in got and "HIT2" in got
        assert any("KB context injected" in l for l in stub.logs)

        stub = _Stub2(valves=_mk_valves(DEEP_SEARCH_MODEL_API_KEY=""), kb="")
        out = asyncio.run(stub.deep_search("Q?"))
        assert out["status"] == "FAILED"
        assert out["error"]["class"] == "ConfigurationError", out["error"]
        assert out["report"] == "" and out["sources"] == []
        assert out["plan"] == [] and out["state_trace"] == []
        assert out["budgets_used"] == {}

        stub = _Stub2(kb="")
        out = asyncio.run(stub.deep_search("Q?", instructions="keep",
                                           max_steps=3, target_sources=4))
        ds = rec["deep_search"]
        assert out["status"] == "DONE" and out["report"] == "r"
        assert out["sources"] == canned.sources
        assert rec["configure"] == {"proxy_url": "http://model.test:8080",
                                    "model": "testmodel"}, rec["configure"]
        assert ds["search_endpoint"] == "http://lb.test:9703"
        assert ds["read_endpoint"] == "http://lb.test:9703"
        assert ds["budgets"].maxSteps == 3
        assert ds["budgets"].maxSources == 4
        assert ds["instructions"].startswith("keep")
        adapter = _RecAdapter.instances[-1]
        assert adapter is ds["client"] and adapter.closed is True
        assert adapter.kw["model_key"] == "selftest-key"
        assert "deep_search: KB context injected (0 chars)" in stub.logs
    finally:
        core.configure, core.deep_search, ad_cls = orig
        globals()["_DSAdapterClient"] = ad_cls


def _st_hygiene():
    key = "selftest-key"
    for line in ALL_LOGS + PRINTED:
        assert key not in line, "secret leaked into log/print line"
    with open(__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "stra" + "ta-unsloth" not in src
    assert "api_key" + "=" not in src
    assert _HEX32_RE.search(src) is None, "32+ char hex in source"


def _selftest():
    checks = [("import", _st_import), ("token", _st_token),
              ("chatml", _st_chatml), ("chat", _st_chat_rewrite_check),
              ("mcp", _st_mcp), ("mixin", _st_mixin),
              ("hygiene", _st_hygiene)]
    for name, fn in checks:
        try:
            fn()
        except SystemExit:
            raise
        except Exception as exc:
            print("SELFTEST FAIL %s: %s" % (name, _oneline(repr(exc))))
            sys.exit(1)
        _emit("PASS %s" % name)
    _emit("SELFTEST OK")
    sys.exit(0)


def _st_chat_rewrite_check():
    chat = _FakeResp(200, json.dumps(
        {"choices": [{"message": {"content": "OK"},
                      "finish_reason": "stop"}]}).encode())
    base = _FakeBase([chat])
    ad = _DSAdapterClient("http://model.test:8080", "http://lb.test:9703",
                          "http://lb.test:9703", "selftest-key",
                          base_client=base)
    msgs = [{"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"}]
    body = {"model": "m", "prompt": core.serialize_chatml(msgs),
            "max_tokens": 111, "temperature": 1.0,
            "stop": [".<|im_end|>"]}
    resp = ad.post("http://model.test:8080/v1/completions", json=body,
                   headers={"Content-Type": "application/json",
                            "Authorization": "Bearer selftest-key"})
    assert resp.status_code == 200
    mapped = json.loads(resp.content)
    assert mapped["choices"][0]["text"] == "OK"
    assert mapped["choices"][0]["finish_reason"] == "stop"
    req = base.requests[-1]
    assert req["url"] == "http://model.test:8080/v1/chat/completions", \
        req["url"]
    assert req["json"]["messages"] == msgs
    assert "stop" not in req["json"]
    assert req["json"]["max_tokens"] == 111
    assert req["headers"].get("Authorization") == "Bearer selftest-key"
    passthru = _FakeResp(200, b'{"ok": 1}')
    base = _FakeBase([passthru])
    ad = _DSAdapterClient("http://model.test:8080", "", "", "",
                          base_client=base)
    rp = ad.post("http://elsewhere.test/v1/anything", json={"x": 1})
    assert rp is passthru and base.requests[-1]["url"] == \
        "http://elsewhere.test/v1/anything"
    bad = _FakeBase([_FakeResp(401, b'{"error":{"type":"auth"}}')])
    ad = _DSAdapterClient("http://model.test:8080", "", "", "selftest-key",
                          base_client=bad)
    r401 = ad.post("http://model.test:8080/v1/completions",
                   json={"model": "m", "prompt": core.serialize_chatml(msgs),
                         "max_tokens": 5},
                   headers={"Authorization": "Bearer selftest-key"})
    assert r401.status_code == 401
    assert json.loads(r401.content) == {"error": {"type": "auth"}}
    malformed = _FakeBase([])
    ad = _DSAdapterClient("http://model.test:8080", "", "", "",
                          base_client=malformed)
    rbad = ad.post("http://model.test:8080/v1/completions",
                   json={"model": "m", "prompt": "not-chatml",
                         "max_tokens": 5})
    assert rbad.status_code == 500
    assert json.loads(rbad.content) == {"error": "bad_chatml"}


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__.strip())
        sys.exit(2)
