#!/usr/bin/env python3
"""deep_search_test_harness.py — live-HTTP harness for the Goethe MCP
gateway's deep_search tool (runs on node4090 against
http://127.0.0.1:9700). Pure external client: imports stdlib + httpx only,
never imports any file from this repo, never prints the gateway token.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import httpx

GATEWAY_URL = "http://127.0.0.1:9700"
MCP_URL = GATEWAY_URL + "/mcp"
RESULTS_PATH = "/tmp/lse/deep_search_test_results.json"
TOKEN_ENV_KEY = "GOETHE_MCP_TOKEN"
GATEWAY_PROC = "goethe_mcp.py"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "deep-search-http-test", "version": "1.0.0"}
MAX_STEPS = 16
TARGET_SOURCES = 8
REPORT_HEAD_CHARS = 4000

QUESTIONS = [
    {
        "id": "mc1",
        "kind": "multi-hop",
        "question": "The first website was created at CERN, in the city of "
                    "Geneva. Which river flows through Geneva? In which "
                    "country is the source of that river located?",
        "expected_key_facts": ["Rhône", "Switzerland"],
        "pass_rule": "DONE and both facts present",
    },
    {
        "id": "mc2",
        "kind": "multi-hop",
        "question": "Dolly the sheep, the first mammal cloned from an adult "
                    "somatic cell, was publicly announced on 22 February "
                    "1997. Who was awarded the Nobel Prize in Physics in "
                    "that same year, 1997?",
        "expected_key_facts": ["Steven Chu"],
        "pass_rule": "DONE and fact present",
    },
    {
        "id": "mc3",
        "kind": "multi-hop",
        "question": "Which company released the Atari 2600 home video game "
                    "console in 1977, and who was its co-founder?",
        "expected_key_facts": ["Atari", "Nolan Bushnell"],
        "pass_rule": "DONE and both facts present",
    },
    {
        "id": "kb1",
        "kind": "kb-heavy",
        "question": "The SearxNG Docker image and the Open WebUI Docker "
                    "image each document a default port. What are the two "
                    "default ports?",
        "expected_key_facts": ["8080", "3000"],
        "pass_rule": "DONE and both ports present",
    },
    {
        "id": "base1",
        "kind": "baseline",
        "question": "Who wrote the play Romeo and Juliet?",
        "expected_key_facts": ["Shakespeare"],
        "pass_rule": "DONE and fact present",
    },
]


# --------------------------------------------------------------------------
# Section 2 -- token acquisition (never printed, never hardcoded)
# --------------------------------------------------------------------------

def _read_proc_environ(pid):
    with open("/proc/%d/environ" % pid, "rb") as fh:
        return fh.read()


def _cmdline_contains(pid, needle):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return needle.encode("utf-8") in fh.read()
    except OSError:
        return False


def find_gateway_pids(proc_name=GATEWAY_PROC):
    try:
        proc = subprocess.run(["pgrep", "-f", proc_name],
                              capture_output=True, text=True, check=False)
    except OSError:
        return []
    pids = []
    for word in proc.stdout.split():
        try:
            pids.append(int(word))
        except ValueError:
            continue
    verified = [p for p in pids if _cmdline_contains(p, proc_name)]
    return verified or pids


def parse_environ(raw):
    env = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key_b, _, val_b = entry.partition(b"=")
        env[key_b.decode("utf-8", errors="replace")] = \
            val_b.decode("utf-8", errors="replace")
    return env


def get_gateway_token(pids=None, environ_reader=None):
    reader = environ_reader or _read_proc_environ
    if pids is None:
        pids = find_gateway_pids()
    for pid in pids:
        try:
            raw = reader(pid)
        except OSError:
            continue
        value = parse_environ(raw).get(TOKEN_ENV_KEY)
        if value:
            return value
    raise RuntimeError(
        "GOETHE_MCP_TOKEN not found in any goethe_mcp.py "
        "/proc/<pid>/environ — gateway not running?")


# --------------------------------------------------------------------------
# Section 3 -- minimal streamable-HTTP MCP client (one handshake per process)
# --------------------------------------------------------------------------

class McpError(Exception):
    pass


class McpAuthError(McpError):
    pass


class HttpTransport:
    def __init__(self):
        self._timeout = httpx.Timeout(1900.0, connect=10.0)

    def post(self, url, headers, payload):
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            return resp.status_code, dict(resp.headers), resp.text


def _get_header(headers, name):
    want = name.lower()
    for key, value in headers.items():
        if str(key).lower() == want:
            return value
    return None


def _sse_messages(body):
    messages = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            parsed = json.loads(data)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            messages.append(parsed)
    if not messages and body.strip():
        try:
            parsed = json.loads(body.strip())
        except ValueError:
            return messages
        if isinstance(parsed, dict):
            messages.append(parsed)
    return messages


def _pick_response(messages, expected_id):
    for msg in messages:
        if msg.get("id") == expected_id:
            return msg
    return None


def _unwrap_tool_result(result):
    content = result.get("content") or []
    text = ""
    if content and isinstance(content[0], dict):
        text = str(content[0].get("text", ""))
    if result.get("isError"):
        raise McpError("tool error: %s" % text[:500])
    try:
        return json.loads(text)
    except ValueError as exc:
        raise McpError("tool result is not JSON (%s): %r"
                       % (exc, text[:200]))


class McpClient:
    def __init__(self, token, transport=None, url=MCP_URL):
        self._token = token
        self._url = url
        self._transport = transport or HttpTransport()
        self._session_id = None
        self._next_id = 0

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self._token,
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    def _post(self, payload):
        status, headers, body = self._transport.post(self._url,
                                                     self._headers(), payload)
        if status in (401, 403):
            raise McpAuthError("gateway auth failed (%d) — token stale or "
                               "wrong env var" % status)
        if status >= 400:
            raise McpError("gateway HTTP %d for %s"
                           % (status, payload.get("method", "?")))
        session = _get_header(headers, "mcp-session-id")
        if session:
            self._session_id = session
        return body

    def _request(self, method, params):
        self._next_id += 1
        rid = self._next_id
        payload = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            payload["params"] = params
        msg = _pick_response(_sse_messages(self._post(payload)), rid)
        if msg is None:
            raise McpError("%s: no matching response in gateway reply"
                           % method)
        if "error" in msg:
            raise McpError("%s failed: %s"
                           % (method, json.dumps(msg["error"])[:300]))
        result = msg.get("result")
        return result if isinstance(result, dict) else {}

    def start(self):
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        if not result.get("protocolVersion") and not result.get("serverInfo"):
            raise McpError("initialize returned unexpected result: %r"
                           % (list(result)[:8],))
        self._post({"jsonrpc": "2.0",
                    "method": "notifications/initialized"})

    def list_tool_names(self):
        result = self._request("tools/list", {})
        names = []
        for tool in result.get("tools") or []:
            if isinstance(tool, dict) and tool.get("name"):
                names.append(str(tool["name"]))
        return names

    def call_tool(self, name, arguments):
        result = self._request("tools/call",
                               {"name": name, "arguments": arguments})
        return _unwrap_tool_result(result)


# --------------------------------------------------------------------------
# Sections 4/5 -- test set, pass rule, runner, atomic results writer
# --------------------------------------------------------------------------

def facts_present(report, expected_key_facts):
    lowered = report.lower()
    return [str(fact).lower() in lowered for fact in expected_key_facts]


def evaluate_pass(status, facts_found):
    return status == "DONE" and bool(facts_found) and all(facts_found)


def summarize(records):
    total = len(records)
    passed = sum(1 for r in records if r.get("passed"))
    done = sum(1 for r in records if r.get("status") == "DONE")
    return {"total": total, "done": done, "pass": passed,
            "fail": total - passed}


def progress_payload(records):
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "gateway": GATEWAY_URL,
        "results": records,
        "summary": summarize(records),
    }


def write_results(path, payload):
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=folder,
                                    prefix=".deep_search_results.",
                                    suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _preflight_deep_search(client):
    """Confirm deep_search is reachable as a COLD tool via the tool_search
    bridge. tool_search returns prose plus full JSON schemas (not a bare
    JSON document), so read the raw content frame. Returns
    (schema_dict_or_None, raw_text)."""
    result = client._request("tools/call",
                             {"name": "tool_search",
                              "arguments": {"query": "deep_search"}})
    if result.get("isError"):
        raise McpError("tool_search preflight failed: %s"
                       % json.dumps(result)[:300])
    content = result.get("content") or []
    text = ""
    if content and isinstance(content[0], dict):
        text = str(content[0].get("text", ""))
    schema = None
    for block in re.split(r"\n\n---\n\n", text):
        start = block.find("{")
        if start < 0:
            continue
        try:
            parsed = json.loads(block[start:].strip())
        except ValueError:
            continue
        if isinstance(parsed, dict) and parsed.get("name") == "deep_search":
            schema = parsed
            break
    return schema, text


def _call_deep_search(client, question, max_steps, target_sources):
    """Invoke deep_search through the MCP cold-tier bridge: it is not in
    tools/list, so it must be dispatched via tool_invoke(name, args_json).
    tool_invoke json.dumps the cold tool's dict result into a text frame;
    we call the raw _request and apply the single _unwrap_tool_result here
    (McpClient.call_tool would unwrap a second time and fail)."""
    result = client._request("tools/call", {
        "name": "tool_invoke",
        "arguments": {
            "name": "deep_search",
            "args_json": json.dumps({
                "question": question,
                "max_steps": max_steps,
                "target_sources": target_sources,
            }),
        },
    })
    return _unwrap_tool_result(result)

def run_question(client, entry):
    t0 = time.monotonic()
    expected = entry["expected_key_facts"]

    def elapsed():
        return round(time.monotonic() - t0, 1)

    try:
        result = _call_deep_search(client, entry["question"],
                                   entry.get("max_steps", MAX_STEPS),
                                   TARGET_SOURCES)
        if not isinstance(result, dict):
            raise McpError("deep_search returned %s, expected dict"
                           % type(result).__name__)
        report = result.get("report") or ""
        status = result.get("status")
        facts = facts_present(report, expected)
        error = result.get("error")
        return {
            "id": entry["id"],
            "kind": entry["kind"],
            "question": entry["question"],
            "status": status,
            "report_head": report[:REPORT_HEAD_CHARS],
            "report_chars": len(report),
            "sources_count": len(result.get("sources") or []),
            "state_trace_len": len(result.get("state_trace") or []),
            "facts_found": facts,
            "passed": evaluate_pass(status, facts),
            "elapsed_s": elapsed(),
            "error": error if isinstance(error, dict) else None,
        }
    except Exception as exc:
        return {
            "id": entry["id"],
            "kind": entry["kind"],
            "question": entry["question"],
            "status": "HARNESS_ERROR",
            "report_head": "",
            "report_chars": 0,
            "sources_count": 0,
            "state_trace_len": 0,
            "facts_found": [False] * len(expected),
            "passed": False,
            "elapsed_s": elapsed(),
            "error": {"class": type(exc).__name__,
                      "message": str(exc)[:300]},
        }


def run_all(client, questions, results_path=RESULTS_PATH):
    records = []
    for entry in questions:
        record = run_question(client, entry)
        records.append(record)
        write_results(results_path, progress_payload(records))
        print("%s status=%s %s elapsed_s=%s"
              % (record["id"], record["status"],
                 "pass" if record["passed"] else "fail",
                 record["elapsed_s"]), flush=True)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Live-HTTP harness for the Goethe MCP deep_search tool.")
    parser.add_argument("--selftest", action="store_true",
                        help="run fully-offline selftest and exit")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    try:
        token = get_gateway_token()
    except RuntimeError as exc:
        write_results(RESULTS_PATH, {"error": str(exc)})
        print("HARNESS BAIL: %s" % exc, flush=True)
        return 2

    print("gateway %s token=<REDACTED len=%d>"
          % (GATEWAY_URL, len(token)), flush=True)

    client = McpClient(token)
    try:
        client.start()
        schema, search_text = _preflight_deep_search(client)
    except McpAuthError as exc:
        write_results(RESULTS_PATH, {"error": str(exc)})
        print("HARNESS BAIL: %s" % exc, flush=True)
        return 2
    except McpError as exc:
        write_results(RESULTS_PATH, {"error": str(exc)})
        print("HARNESS BAIL: pre-flight failed: %s" % exc, flush=True)
        return 2

    if schema is None:
        write_results(RESULTS_PATH, {
            "error": "deep_search cold-registry schema not reachable via "
                     "tool_search — gateway not restarted with "
                     "DeepSearchMixin?",
            "tool_search_text": search_text[:1000]})
        print("HARNESS BAIL: deep_search not in tool_search (cold registry)",
              flush=True)
        return 3

    records = run_all(client, QUESTIONS, RESULTS_PATH)
    summary = summarize(records)
    print("HARNESS DONE pass=%d/%d" % (summary["pass"], summary["total"]),
          flush=True)
    return 0 if summary["pass"] == summary["total"] else 4


# --------------------------------------------------------------------------
# Section 6 -- fully-offline selftest (no network, no /proc, no token)
# --------------------------------------------------------------------------

class _FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, headers, payload):
        self.requests.append({"url": url, "headers": dict(headers),
                              "payload": json.loads(json.dumps(payload))})
        if not self.responses:
            raise AssertionError("fake transport: no canned response left")
        status, resp_headers, body = self.responses.pop(0)
        return status, dict(resp_headers), body


def _data_frame(obj):
    return "event: message\r\ndata: %s\r\n\r\n" % json.dumps(obj)


def _init_response(rid=1):
    return _data_frame({"jsonrpc": "2.0", "id": rid, "result": {
        "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
        "serverInfo": {"name": "goethe", "version": "test"}}})


def _st_question_set():
    ids = [q["id"] for q in QUESTIONS]
    assert ids == ["mc1", "mc2", "mc3", "kb1", "base1"], ids
    kinds = [q["kind"] for q in QUESTIONS]
    assert kinds == ["multi-hop", "multi-hop", "multi-hop", "kb-heavy",
                     "baseline"], kinds
    assert QUESTIONS[0]["expected_key_facts"] == ["Rhône", "Switzerland"]
    assert QUESTIONS[1]["expected_key_facts"] == ["Steven Chu"]
    assert QUESTIONS[2]["expected_key_facts"] == ["Atari", "Nolan Bushnell"]
    assert QUESTIONS[3]["expected_key_facts"] == ["8080", "3000"]
    assert QUESTIONS[4]["expected_key_facts"] == ["Shakespeare"]
    for q in QUESTIONS:
        assert "\n" not in q["question"], q["id"]
        assert "  " not in q["question"], q["id"]


def _st_token_parser():
    raw = ("LANG=C\0"
           "MCP_TOKEN=decoy-key-should-not-match\0"
           "GOETHE_MCP_TOKEN=tok=with=equals-and-ünïcødé-value\0"
           "HOME=/root\0").encode("utf-8")

    def reader(pid):
        if pid == 4242:
            return raw
        raise OSError(2, "no such process", str(pid))

    value = get_gateway_token(pids=[4321, 4242], environ_reader=reader)
    assert value == "tok=with=equals-and-ünïcødé-value", repr(value)
    env = parse_environ(b"PATH=/bin\0NOPE=1\0")
    try:
        get_gateway_token(pids=[1], environ_reader=lambda pid: b"PATH=/bin\0")
    except RuntimeError as exc:
        assert "GOETHE_MCP_TOKEN not found" in str(exc), str(exc)
    else:
        raise AssertionError("missing key must raise RuntimeError")
    assert env.get("PATH") == "/bin"


def _st_sse_client():
    tool_payload = {"status": "DONE", "report": "Rh\u00f4ne / Switzerland",
                    "sources": ["a", "b"], "plan": [], "state_trace": [],
                    "budgets_used": {}, "error": None}
    search_text = ("Top cold-tool matches \u2014 FULL schemas. Invoke via "
                   "tool_invoke(name, args_json) with args_json a JSON "
                   "object of the parameters above.\n\n"
                   + json.dumps({"name": "deep_search",
                                 "description": "cold deep search tool",
                                 "parameters": [
                                     {"name": "question", "type": "str",
                                      "required": True},
                                     {"name": "instructions",
                                      "type": "str", "required": False}]},
                                indent=2))
    responses = [
        (200, {"mcp-session-id": "sess-xyz"}, _init_response()),
        (202, {}, ""),
        (200, {}, _data_frame({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": search_text}],
            "isError": False}})),
        (200, {}, _data_frame({"jsonrpc": "2.0", "id": 3, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(tool_payload)}],
            "isError": False}})),
    ]
    fake = _FakeTransport(responses)
    client = McpClient("t0k-en0", transport=fake)
    client.start()
    assert client._session_id == "sess-xyz", client._session_id
    assert fake.requests[0]["payload"]["method"] == "initialize"
    assert fake.requests[0]["headers"]["Authorization"] == "Bearer t0k-en0"
    assert "text/event-stream" in \
        fake.requests[0]["headers"]["Accept"]
    assert fake.requests[1]["payload"] == {
        "jsonrpc": "2.0", "method": "notifications/initialized"}
    assert fake.requests[1]["headers"].get("mcp-session-id") == "sess-xyz"
    schema, text = _preflight_deep_search(client)
    assert schema is not None and schema["name"] == "deep_search", schema
    assert "cold deep search tool" in text, text[:200]
    assert fake.requests[2]["payload"]["method"] == "tools/call"
    assert fake.requests[2]["payload"]["params"] == {
        "name": "tool_search",
        "arguments": {"query": "deep_search"}}, fake.requests[2]["payload"]
    assert fake.requests[2]["headers"].get("mcp-session-id") == "sess-xyz"
    result = _call_deep_search(client, "x", MAX_STEPS, TARGET_SOURCES)
    assert result == tool_payload, list(result)
    assert fake.requests[3]["payload"]["method"] == "tools/call"
    invoke_params = fake.requests[3]["payload"]["params"]
    assert invoke_params["name"] == "tool_invoke", invoke_params
    bridge_args = json.loads(invoke_params["arguments"]["args_json"])
    assert bridge_args == {"question": "x", "max_steps": MAX_STEPS,
                           "target_sources": TARGET_SOURCES}, bridge_args

    err_fake = _FakeTransport([
        (200, {"mcp-session-id": "s2"}, _init_response()),
        (202, {}, ""),
        (200, {}, _data_frame({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": "boom: kb exhausted"}],
            "isError": True}})),
    ])
    err_client = McpClient("tk", transport=err_fake)
    err_client.start()
    try:
        _call_deep_search(err_client, "x", 1, 1)
    except McpError as exc:
        assert "boom: kb exhausted" in str(exc), str(exc)
    else:
        raise AssertionError("isError must raise")

    auth_fake = _FakeTransport([(401, {}, "")])
    auth_client = McpClient("bad", transport=auth_fake)
    try:
        auth_client.start()
    except McpAuthError as exc:
        assert str(exc) == ("gateway auth failed (401) \u2014 token stale or "
                            "wrong env var"), str(exc)
    else:
        raise AssertionError("401 must raise McpAuthError")


def _st_pass_rule():
    cases = [
        ("DONE", [True, True], True),
        ("DONE", [True, False], False),
        ("FAILED", [True, True], False),
        ("HARNESS_ERROR", [False], False),
        ("DONE", [True], True),
        ("DONE", [], False),
    ]
    for status, facts, want in cases:
        got = evaluate_pass(status, facts)
        assert got is want, (status, facts, got, want)
    mc1 = QUESTIONS[0]
    report = "The Rhône flows through Geneva, in Switzerland."
    assert facts_present(report, mc1["expected_key_facts"]) == [True, True]
    assert facts_present("the rhone valley", mc1["expected_key_facts"]) == \
        [False, False]


def _st_results_writer():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nested-ok", "results.json")
        records1 = [
            {"id": "mc1", "status": "DONE", "passed": True},
            {"id": "mc2", "status": "FAILED", "passed": False},
        ]
        write_results(path, progress_payload(records1))
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["gateway"] == GATEWAY_URL
        assert data["host"] == socket.gethostname()
        assert data["summary"] == {"total": 2, "done": 1, "pass": 1,
                                   "fail": 1}, data["summary"]
        assert len(data["results"]) == 2
        write_results(path, progress_payload(records1 + [
            {"id": "mc3", "status": "DONE", "passed": False}]))
        with open(path, "r", encoding="utf-8") as fh:
            data2 = json.load(fh)
        assert data2["summary"] == {"total": 3, "done": 2, "pass": 1,
                                    "fail": 2}, data2["summary"]
        leftovers = sorted(os.listdir(os.path.dirname(path)))
        assert leftovers == ["results.json"], leftovers


def selftest():
    checks = [
        ("question-set", _st_question_set),
        ("token-parser", _st_token_parser),
        ("sse-client", _st_sse_client),
        ("pass-rule", _st_pass_rule),
        ("results-writer", _st_results_writer),
    ]
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:
            print("SELFTEST FAIL %s: %s" % (name, exc))
            return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
