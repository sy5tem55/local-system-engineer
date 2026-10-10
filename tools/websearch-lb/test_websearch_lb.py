#!/usr/bin/env python3
"""Unit tests for websearch_lb_server Router + CircuitBreaker + _norm + /stats."""
import asyncio, json, os, sys, tempfile, types
sys.path.insert(0, "/home/sy5/projects/local-system-engineer/tools/websearch-lb")
import websearch_lb_server as W

class Fake:
    def __init__(self, name, rows=None, exc=None):
        self.name = name; self.rows = rows; self.exc = exc
        self.calls = 0
    async def search(self, query, max_results):
        self.calls += 1
        if self.exc: raise self.exc
        return self.rows

ROWS = [{"title": "T1", "url": "https://a.example/1", "snippet": "s1"}]

def test_breaker():
    t = [0.0]
    br = W.CircuitBreaker("x", fail_threshold=2, cooldown_s=300, clock=lambda: t[0])
    assert br.allow()
    br.record_failure(); assert br.allow(), "1 failure must not open the breaker"
    br.record_failure(); assert not br.allow(), "2 failures must open cooldown"
    t[0] = 299.0; assert not br.allow()
    t[0] = 301.0; assert br.allow(), "cooldown must expire"
    br.record_failure(); br.record_success()
    assert br.allow(), "success must reset the failure count"
    print("PASS breaker")

async def _route(backends, priority, override=None, rows=ROWS):
    r = W.Router(backends, priority, cooldown_s=300, clock=lambda: 0.0)
    return await r.route("q", 5, override)

def test_failover_hard():
    b1, b2 = Fake("a", exc=W.BackendError("boom")), Fake("b", rows=ROWS)
    res = asyncio.run(_route({"a": b1, "b": b2}, ["a", "b"]))
    assert res["ok"] is True and res["results"][0]["backend"] == "b"
    assert res["per_backend"]["a"]["status"] == "error" and res["per_backend"]["b"]["status"] == "ok"
    assert b1.calls == 1 and b2.calls == 1
    print("PASS failover_hard")

def test_failover_soft():
    b1, b2 = Fake("a", rows=[]), Fake("b", rows=ROWS)
    res = asyncio.run(_route({"a": b1, "b": b2}, ["a", "b"]))
    assert res["ok"] is True and res["results"][0]["backend"] == "b"
    assert res["per_backend"]["a"]["status"] == "ok_no_results"
    print("PASS failover_soft")

def test_all_failed():
    res = asyncio.run(_route({"a": Fake("a", exc=RuntimeError("net")), "b": Fake("b", rows=[])}, ["a", "b"]))
    assert res["ok"] is False and res["error"] == "all_backends_failed"
    assert set(res["per_backend"]) == {"a", "b"}
    print("PASS all_failed")

def test_cooldown_skip():
    t = [0.0]
    b1, b2 = Fake("a", exc=W.BackendError("x")), Fake("b", rows=ROWS)
    r = W.Router({"a": b1, "b": b2}, ["a", "b"], cooldown_s=300, clock=lambda: t[0])
    asyncio.run(r.route("q"))          # failure 1
    asyncio.run(r.route("q"))          # failure 2 -> opens breaker a
    res = asyncio.run(r.route("q"))    # a in cooldown, skipped
    assert res["per_backend"]["a"]["status"] == "cooldown" and b1.calls == 2
    print("PASS cooldown_skip")

def test_override_order():
    a, b, c = Fake("a", exc=W.BackendError("x")), Fake("b", exc=W.BackendError("x")), Fake("c", rows=ROWS)
    res = asyncio.run(_route({"a": a, "b": b, "c": c}, ["a", "b", "c"], override=["c", "a"]))
    # c is first in the override and succeeds immediately: a/b must never be touched
    assert res["results"][0]["backend"] == "c" and a.calls == 0 and b.calls == 0
    print("PASS override_order")

def test_norm_shapes():
    exa = W._norm([{"id": "https://x/1", "title": "E", "text": "long text here"}], ["id", "url"], ["title"], ["text", "snippet"])
    fc = W._norm([{"url": "https://x/2", "title": "F", "description": "d"}], ["url"], ["title"], ["description"])
    ddg = W._norm([{"href": "https://x/3", "title": "D", "body": "b"}], ["href", "url"], ["title"], ["body", "description"])
    assert [r["url"] for r in exa + fc + ddg] == ["https://x/1", "https://x/2", "https://x/3"]
    assert exa[0]["snippet"].startswith("long text")
    assert W._norm([{"no": "url"}], ["url"], ["title"], ["snippet"]) == [], "rows without url are dropped"
    print("PASS norm_shapes")

def test_health():
    r = W.Router({"a": Fake("a", rows=ROWS)}, ["a"])
    h = asyncio.run(r.route("q"))
    h = r.health()
    assert h["status"] == "ok" and h["backends"]["a"]["up"] is True and h["priority"] == ["a"]
    print("PASS health")

# ---- Jina search backend tests (live-verified contract 2026-10-07:
#      GET https://s.jina.ai/{query}?count=N, Bearer auth, Accept: application/json,
#      response {"code":200,"status":20000,"data":[{title,url,description,content}]}) ----

class _JinaCap:
    """Captures the httpx GET call and returns a canned s.jina.ai response."""
    def __init__(self, resp):
        self.resp = resp; self.calls = []
    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.resp

def _jina_resp(rows=None, code=200):
    class R:
        status_code = 200
        text = str({"code": code, "status": 20000, "data": rows})
        def json(self):
            return {"code": code, "status": 20000, "data": rows}
    return R()

def test_jina_backend():
    cap = _JinaCap(_jina_resp([{"title": "J", "url": "https://j.example/1",
                                "description": "short d", "content": "full content text here"}]))
    saved = W.JINA_KEY
    W.JINA_KEY = "test-key"
    try:
        be = W.JinaBackend(cap)
        rows = asyncio.run(be.search("Fast MCP  test", 3))
        assert rows == [{"title": "J", "url": "https://j.example/1", "snippet": "short d"}], rows
        c = cap.calls[0]
        assert c["url"] == "https://s.jina.ai/Fast%20MCP%20%20test", c["url"]
        assert c["params"] == {"count": 3}
        assert c["headers"]["Authorization"] == "Bearer test-key"
        assert c["headers"]["Accept"] == "application/json"
    finally:
        W.JINA_KEY = saved
    print("PASS jina_backend")

def test_jina_no_key():
    saved = W.JINA_KEY
    W.JINA_KEY = ""
    try:
        be = W.JinaBackend(_JinaCap(_jina_resp([ROWS[0]])))
        try:
            asyncio.run(be.search("q", 3))
            assert False, "must raise BackendError without a key"
        except W.BackendError:
            pass
    finally:
        W.JINA_KEY = saved
    print("PASS jina_no_key")

def test_jina_envelope_error():
    # query-in-body style usage-hint envelope (data is a dict, not a list) must raise hard
    class R:
        status_code = 200
        text = '{"code":200,"status":20000,"data":{"usage2":"https://s.jina.ai/YOUR_SEARCH_QUERY"}}'
        def json(self):
            return {"code": 200, "status": 20000, "data": {"usage2": "x"}}
    saved = W.JINA_KEY
    W.JINA_KEY = "test-key"
    try:
        be = W.JinaBackend(_JinaCap(R()))
        try:
            asyncio.run(be.search("q", 3))
            assert False, "envelope with non-list data must raise BackendError"
        except W.BackendError:
            pass
    finally:
        W.JINA_KEY = saved
    print("PASS jina_envelope_error")

def test_exa_402_failover():
    # exa HTTP 402 (payment required) -> BackendError -> router fails over to next backend
    exa = Fake("exa", exc=W.BackendError("exa HTTP 402: Payment required to access this resource"))
    fc = Fake("firecrawl", rows=ROWS)
    res = asyncio.run(_route({"exa": exa, "firecrawl": fc}, ["exa", "firecrawl"]))
    assert res["ok"] is True and res["results"][0]["backend"] == "firecrawl"
    assert "402" in res["per_backend"]["exa"]["error"]
    print("PASS exa_402_failover")

def test_jina_in_router_when_key():
    saved = W.JINA_KEY
    W.JINA_KEY = "test-key"
    try:
        r = W._make_router()
        assert "jina" in r.backends, "jina must be registered when key present"
        assert r.health()["priority"] == ["jina", "firecrawl", "exa", "searxng", "ddg"]
        W.JINA_KEY = ""
        r2 = W._make_router()
        assert "jina" not in r2.backends, "jina must be absent without a key"
    finally:
        W.JINA_KEY = saved
    print("PASS jina_in_router_when_key")

# ---- /stats endpoint tests (usage.jsonl aggregation + monotonic->wall cooldown) ----

def test_stats_usage_counts():
    # redirect the usage log to a temp file, write known lines, check aggregation
    saved = W.USAGE_LOG
    tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    tmp.close()
    W.USAGE_LOG = tmp.name
    try:
        with open(tmp.name, "w") as f:
            f.write(json.dumps({"ts": 1000.0, "query_hash": "a", "ok": True,  "backends": {"jina": "ok"}}) + "\n")
            f.write(json.dumps({"ts": 1001.0, "query_hash": "b", "ok": True,  "backends": {"firecrawl": "ok"}}) + "\n")
            f.write(json.dumps({"ts": 1002.0, "query_hash": "c", "ok": False, "backends": {"ddg": "error"}}) + "\n")
        u = W._read_usage()
        assert u == {"total_queries": 3, "ok_queries": 2, "failed_queries": 1, "last_query_ts": 1002.0}, u
        r = W.Router({"a": Fake("a", rows=ROWS)}, ["a"])
        s = r.stats()
        assert s["usage"]["total_queries"] == 3 and s["usage"]["ok_queries"] == 2 and s["usage"]["failed_queries"] == 1
    finally:
        W.USAGE_LOG = saved
        os.unlink(tmp.name)
    print("PASS stats_usage_counts")

def test_stats_usage_missing_file():
    # missing/unreadable usage log must aggregate to zeros, not raise
    saved = W.USAGE_LOG
    W.USAGE_LOG = "/tmp/lse/definitely-not-here-xyz/usage.jsonl"
    try:
        u = W._read_usage()
        assert u == {"total_queries": 0, "ok_queries": 0, "failed_queries": 0, "last_query_ts": None}, u
    finally:
        W.USAGE_LOG = saved
    print("PASS stats_usage_missing_file")

def test_stats_cooldown_wall_seconds():
    # breaker cooldown is time.monotonic; /stats must expose wall-clock seconds remaining
    t = [1000.0]
    r = W.Router({"x": Fake("x", rows=ROWS)}, ["x"], cooldown_s=300.0, clock=lambda: t[0])
    br = r.breakers["x"]
    br.record_failure(); br.record_failure()  # open cooldown -> until = 1000 + 300
    s = r.stats()
    assert s["backends"]["x"]["up"] is False
    assert abs(s["backends"]["x"]["cooldown_remaining_s"] - 300.0) < 1e-6, s
    t[0] = 1120.0  # 180s left (1300 - 1120 = 180)
    assert abs(r.stats()["backends"]["x"]["cooldown_remaining_s"] - 180.0) < 1e-6
    t[0] = 1400.0  # past cooldown -> up, no remaining
    s2 = r.stats()
    assert s2["backends"]["x"]["up"] is True and s2["backends"]["x"]["cooldown_remaining_s"] is None
    print("PASS stats_cooldown_wall_seconds")

def test_stats_structure():
    r = W.Router({"a": Fake("a", rows=ROWS)}, ["a", "b"])
    s = r.stats()
    assert s["status"] == "ok" and s["priority"] == ["a", "b"]
    assert set(s["backends"]) == {"a"}  # only registered backends appear
    assert {"up", "consecutive_failures", "cooldown_remaining_s", "last_latency_ms"} <= set(s["backends"]["a"])
    assert "generated_at" in s and "usage" in s
    print("PASS stats_structure")

if __name__ == "__main__":
    test_breaker(); test_failover_hard(); test_failover_soft(); test_all_failed()
    test_cooldown_skip(); test_override_order(); test_norm_shapes(); test_health()
    test_jina_backend(); test_jina_no_key(); test_jina_envelope_error()
    test_exa_402_failover(); test_jina_in_router_when_key()
    test_stats_usage_counts(); test_stats_usage_missing_file()
    test_stats_cooldown_wall_seconds(); test_stats_structure()
    print("ALL 17 TESTS PASSED")
