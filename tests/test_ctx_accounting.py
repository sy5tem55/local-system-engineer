"""P1 — exact context accounting ((2026-09)).

Mechanism: "complete next-input count" + fixed-envelope
preflight (docs/ROADMAP-mechanisms-2026-09.md Phase 1,
docs/03-context-management.md §7).

Covers:
  _llama_server_url(): valve precedence, dynamic pgrep discovery,
    cache, subprocess-failure fallback to the valve value.
  _ctx_gate(): valve off, high-fill refusal, low-fill pass,
    monitoring-failure pass (never block on a monitoring fault).
  get_context_status(): exact numbers (envelope / projected /
    compact-at / hard-stop) against a mocked /slots response.

No network: /slots is mocked; pgrep is monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402


def _make_tools(monkeypatch):
    monkeypatch.delenv("GOETHE_LLAMA_SERVER_URL", raising=False)
    t = goethe.Tools()
    t._ctx_url_cache = None
    t._ctx_gate_cache = None
    t._ctx_envelope = None
    return t


def _fake_slots(n_prompt=69720, n_ctx=131072):
    return [{
        "id": 0,
        "n_ctx": n_ctx,
        "n_prompt_tokens": n_prompt,
        "n_prompt_tokens_cache": 0,
        "n_prompt_tokens_processed": 0,
        "next_token": [{"n_decoded": 0, "n_remain": -1}],
        "params": {"n_predict": n_ctx - n_prompt},
    }]


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


# ── _llama_server_url ────────────────────────────────────────────────────────

def test_url_valve_wins_when_env_set(monkeypatch):
    monkeypatch.setenv("GOETHE_LLAMA_SERVER_URL", "http://127.0.0.1:9999")
    t = _make_tools(monkeypatch)
    t.valves.LLAMA_SERVER_URL = "http://127.0.0.1:9999"
    assert t._llama_server_url() == "http://127.0.0.1:9999"
    assert t._ctx_url_cache is not None


def test_url_dynamic_discovery(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        class R:
            returncode = 0
            stdout = (b"500894 /home/sy5/.unsloth/llama.cpp/llama-server "
                      b"-m model.gguf --port 46439 --parallel 1\n")
        return R()

    monkeypatch.setattr(goethe.subprocess, "run", fake_run)
    t = _make_tools(monkeypatch)
    assert t._llama_server_url() == "http://127.0.0.1:46439"
    assert t._llama_server_url() == "http://127.0.0.1:46439"
    assert calls["n"] == 1, "second call must hit the cache"


def test_url_fallback_to_valve_on_discovery_failure(monkeypatch):
    def fake_run(cmd, **kw):
        raise goethe.subprocess.SubprocessError("no llama-server")

    monkeypatch.setattr(goethe.subprocess, "run", fake_run)
    t = _make_tools(monkeypatch)
    t.valves.LLAMA_SERVER_URL = "http://localhost:8080"
    assert t._llama_server_url() == "http://localhost:8080"


# ── _ctx_gate ────────────────────────────────────────────────────────────────

def test_gate_off_returns_none(monkeypatch):
    t = _make_tools(monkeypatch)
    t.valves.CTX_HARD_STOP = "0"
    assert t._ctx_gate("execute_command") is None


def test_gate_refuses_at_high_fill(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_fake_slots(n_prompt=120000)))
    t = _make_tools(monkeypatch)
    t.valves.CTX_HARD_STOP = "1"
    out = t._ctx_gate("execute_command")
    assert out is not None
    assert "CTX HARD STOP" in out
    assert "execute_command" in out
    assert "122,000" in out  # 120000 + 0 envelope + 2000 reserve


def test_gate_passes_at_low_fill(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_fake_slots(n_prompt=60000)))
    t = _make_tools(monkeypatch)
    t.valves.CTX_HARD_STOP = "1"
    assert t._ctx_gate("search_kb") is None


def test_gate_passes_on_monitoring_failure(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(requests, "get", boom)
    t = _make_tools(monkeypatch)
    t.valves.CTX_HARD_STOP = "1"
    assert t._ctx_gate("execute_command") is None


# ── get_context_status exact numbers ─────────────────────────────────────────

def test_status_reports_exact_numbers(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(_fake_slots()))
    t = _make_tools(monkeypatch)
    t._ctx_envelope = (12000, 48, "abc123def456")
    out = t.get_context_status()
    assert "Projected next input" in out
    assert "Tool envelope" in out
    assert "48 tools" in out
    assert "compact-at" in out
    assert "HARD-STOP" in out
    # projected = 69720 + 12000 + 2000 = 83720
    assert "83,720" in out
    # compact-at = 0.70 * 131072 = 91750
    assert "91,750" in out
