#!/usr/bin/env python3
"""Phase 2 tiering + bridge tests (roadmap item 2, 2026-09).

register() tiering:
  - CORE_TOOLS ∪ ALWAYS_CORE → mcp.add_tool; rest → inst._cold_registry
  - EAGER_TOOLS=1 binds everything, cold registry stays empty
  - cold wrappers keep the FULL docstring (no _TOOL_DESC_MAX cap); bound
    descriptions are still capped

BridgeTools:
  - tool_search: top-3 FULL schemas (untruncated docstrings), vault match,
    no-match lists all cold names
  - tool_invoke: JSON validation, unknown args, missing required, unknown
    tool, dispatch through the original wrapper (ctx gate + episode journal)

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_tiering_bridges.py -q
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe_mcp  # noqa: E402

_POLICY_DOC = ("A cold tool whose docstring carries POLICY TEXT that must "
               "survive untruncated: NEVER truncate this contract line.\n"
               + "padding " * 500)  # > _TOOL_DESC_MAX (3072)


class _FakeMcp:
    def __init__(self):
        self.bound = {}

    def add_tool(self, wrapper, name=None, description=None):
        self.bound[name or wrapper.__name__] = (wrapper, description)


class _FakeTools:
    def core_a(self, x: str) -> str:
        return x + x

    def cold_x(self, query: str) -> str:
        return f"COLD_X:{query}"

    def cold_y(self, endpoint: str, payload: dict = None) -> str:
        return f"COLD_Y:{endpoint}"

    def vault_unlock(self) -> str:
        return "BW_SESSION=abc"

    def vault_peek(self, name: str) -> str:
        return f"secret:{name}"


_FakeTools.core_a.__doc__ = "Core tool A. Doubles x. " + "p" * 4000
_FakeTools.cold_x.__doc__ = _POLICY_DOC
_FakeTools.cold_y.__doc__ = ("Write to the fake REST API. Confirmed gate: "
                             "always dry_run first.")
_FakeTools.vault_unlock.__doc__ = ("Authenticate with Vaultwarden. Returns a "
                                   "BW_SESSION token on success, or an error "
                                   "string starting with ERROR:.")
_FakeTools.vault_peek.__doc__ = ("Read a vault item by name. Requires a "
                                 "BW_SESSION token from vault_unlock.")


def _make(monkeypatch, core=("core_a",)):
    """Register _FakeTools with tiering; return (inst, cold, exposed)."""
    monkeypatch.setattr(goethe_mcp, "EAGER_TOOLS", False)
    monkeypatch.setattr(goethe_mcp, "CORE_TOOLS", frozenset(core))
    inst = _FakeTools()
    exposed = goethe_mcp.register(_FakeMcp(), inst)
    return inst, inst._cold_registry, exposed


# ── register() tiering ────────────────────────────────────────────────

def test_register_tiers_core_vs_cold(monkeypatch):
    inst, cold, exposed = _make(monkeypatch)
    assert "core_a" in exposed
    assert not ({"cold_x", "cold_y", "vault_unlock", "vault_peek"}
                & set(exposed))
    assert set(cold) == {"cold_x", "cold_y", "vault_unlock", "vault_peek"}


def test_register_eager_binds_all(monkeypatch):
    monkeypatch.setattr(goethe_mcp, "EAGER_TOOLS", True)
    inst = _FakeTools()
    exposed = goethe_mcp.register(_FakeMcp(), inst)
    assert set(exposed) == {"core_a", "cold_x", "cold_y",
                            "vault_unlock", "vault_peek"}
    assert inst._cold_registry == {}


def test_bound_docstring_capped_cold_full(monkeypatch):
    inst, cold, _ = _make(monkeypatch)
    mcp = _FakeMcp()
    goethe_mcp.register(mcp, inst)  # second pass to capture bound descriptions
    bound_desc = mcp.bound["core_a"][1]
    assert len(bound_desc) <= goethe_mcp._TOOL_DESC_MAX
    assert len(cold["cold_x"].__doc__) > goethe_mcp._TOOL_DESC_MAX
    assert "POLICY TEXT" in cold["cold_x"].__doc__


# ── tool_search ───────────────────────────────────────────────────────

def test_tool_search_top3_full_schemas(monkeypatch):
    _, cold, _ = _make(monkeypatch)
    out = asyncio.run(goethe_mcp.BridgeTools(cold).tool_search("vault"))
    blocks = [b for b in out.split("\n\n---\n\n") if b.strip().startswith("{")]
    assert 1 <= len(blocks) <= 3
    schemas = [json.loads(b) for b in blocks]
    names = [s["name"] for s in schemas]
    assert "vault_unlock" in names
    top = next(s for s in schemas if s["name"] == "vault_unlock")
    assert top["description"] == cold["vault_unlock"].__doc__  # FULL doc
    assert "tool_invoke(name, args_json)" in out


def test_tool_search_no_match_lists_names(monkeypatch):
    _, cold, _ = _make(monkeypatch)
    out = asyncio.run(goethe_mcp.BridgeTools(cold).tool_search("zzz_no_such_thing"))
    assert out.startswith("No cold tool matches")
    for n in cold:
        assert n in out


# ── tool_invoke ───────────────────────────────────────────────────────

def _bridge(monkeypatch):
    _, cold, _ = _make(monkeypatch)
    return goethe_mcp.BridgeTools(cold)


def test_tool_invoke_bad_json(monkeypatch):
    out = asyncio.run(_bridge(monkeypatch).tool_invoke("vault_unlock", "{not json"))
    assert "not valid JSON" in out


def test_tool_invoke_non_object(monkeypatch):
    out = asyncio.run(_bridge(monkeypatch).tool_invoke("vault_unlock", "[1, 2]"))
    assert "must decode to a JSON object" in out


def test_tool_invoke_unknown_arg(monkeypatch):
    out = asyncio.run(_bridge(monkeypatch).tool_invoke(
        "cold_y", json.dumps({"bogus": 1})))
    assert "unknown args for cold_y: bogus" in out
    assert "Valid parameters" in out


def test_tool_invoke_missing_required(monkeypatch):
    out = asyncio.run(_bridge(monkeypatch).tool_invoke("cold_y", "{}"))
    assert "missing required args for cold_y: endpoint" in out


def test_tool_invoke_unknown_tool(monkeypatch):
    out = asyncio.run(_bridge(monkeypatch).tool_invoke("vault_nope", "{}"))
    assert "unknown cold tool 'vault_nope'" in out
    assert "vault_unlock" in out  # close names via startswith('vaul')


def test_tool_invoke_dispatch_gate_journal(monkeypatch):
    calls = []
    monkeypatch.setattr(goethe_mcp, "_safe_journal",
                        lambda n, kw, r, e, s: calls.append((n, r, e)))
    inst, cold, _ = _make(monkeypatch)
    bridge = goethe_mcp.BridgeTools(cold)

    # 1) ctx-gate refusal short-circuits dispatch (still journaled)
    inst._ctx_gate = lambda tool: "CTX_GATE: projected 90% of n_ctx - stop"
    out = asyncio.run(bridge.tool_invoke("vault_unlock", "{}"))
    assert out.startswith("CTX_GATE")
    assert calls[-1] == ("vault_unlock", None, None)

    # 2) gate clear -> dispatch through original wrapper, result + journal
    inst._ctx_gate = lambda tool: None
    out = asyncio.run(bridge.tool_invoke(
        "cold_y", json.dumps({"endpoint": "/x"})))
    assert out == "COLD_Y:/x"
    assert calls[-1] == ("cold_y", "COLD_Y:/x", None)
