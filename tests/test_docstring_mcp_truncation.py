# docstring MCP truncation gate: pytest tests/test_docstring_mcp_truncation.py -v
#
# Regression test for the v0.4.7 incident: planner's MANDATORY TRIGGER block
# was silently dropped by goethe_mcp.py's description[:1024] truncation,
# causing the model to violate a rule it never saw.
#
# This test asserts that every tool's behavior-critical keywords
# (MUST/MANDATORY/NEVER/GATE/RULE/REQUIRED) appear within the first
# 1024 characters of the docstring — the portion actually visible to the
# MCP client. If a keyword is present in the full docstring but falls
# beyond 1024, the test FAILS: that is a silent contract drop.
#
# Pattern: modeled on bump_gate.py — loads goethe.py via importlib,
# inspects the Tools class, asserts on structural properties.

import importlib.util
import inspect

# ── Constants from goethe_mcp.py line 638 ────────────────────────────────
MCP_DESC_MAX = 1024  # description=wrapper.__doc__[:1024]

# Keywords that signal behavior-critical contracts. If any of these appear
# in a tool's docstring, they MUST survive the MCP truncation.
CONTRACT_KEYWORDS = ("MUST", "MANDATORY", "NEVER", "GATE", "RULE", "REQUIRED")

# Methods that are internal or skipped from tool exposure.
SKIP_TOOLS = {"compact_context"}

# Frontend-injected parameters — methods with only these are helpers, not tools.
INJECTED = {
    "__event_emitter__", "__event_call__", "__chat_id__", "__user__",
    "__request__", "__metadata__", "__model__", "__messages__",
    "__files__", "__id__", "__task__", "__tools__",
}


def _load_tools():
    """Load the Tools class from goethe.py and return (instance, list of tool names)."""
    spec = importlib.util.spec_from_file_location(
        "goethe_mod", "tools/goethe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    inst = mod.Tools()

    tools = []
    for name, meth in inspect.getmembers(inst, predicate=inspect.ismethod):
        if name.startswith("_") or name in SKIP_TOOLS:
            continue
        sig = inspect.signature(meth)
        params = [
            p.name for p in sig.parameters.values()
            if p.name not in INJECTED
        ]
        if params:  # has real tool args → exposed as MCP tool
            tools.append(name)
    return inst, tools


def _tool_docstring(inst, name):
    """Return the full docstring of a tool method, stripped."""
    meth = getattr(inst, name)
    return (meth.__doc__ or "").strip()


def _keywords_in_doc(doc):
    """Return the set of CONTRACT_KEYWORDS that appear in doc."""
    return {kw for kw in CONTRACT_KEYWORDS if kw in doc}


def _all_keywords_survive_truncation(doc, max_chars=MCP_DESC_MAX):
    """Check that every contract keyword in doc appears within max_chars."""
    full_keywords = _keywords_in_doc(doc)
    truncated = doc[:max_chars]
    truncated_keywords = _keywords_in_doc(truncated)
    missing = full_keywords - truncated_keywords
    return len(missing) == 0, missing


def test_docstring_mcp_truncation_gate():
    """
    Every tool whose docstring contains MUST/MANDATORY/NEVER/GATE/RULE/REQUIRED
    must have ALL such keywords within the first 1024 chars (MCP truncation limit).
    """
    inst, tool_names = _load_tools()

    failures = []
    for name in sorted(tool_names):
        doc = _tool_docstring(inst, name)
        if not doc:
            continue  # no docstring → nothing to check

        survives, missing = _all_keywords_survive_truncation(doc)
        if not survives:
            # Report where the missing keywords first appear
            details = []
            for kw in sorted(missing):
                pos = doc.find(kw)
                details.append(f"{kw}@{pos}")
            failures.append(
                f"{name}: keywords past MCP truncation ({MCP_DESC_MAX} chars): "
                + ", ".join(details)
            )

    if failures:
        msg = "\n".join(failures)
        raise AssertionError(
            f"Docstring MCP truncation gate FAILED ({len(failures)} tools):\n{msg}"
        )

    # Info line for verbose output
    print(f"MCP truncation gate PASSED: {len(tool_names)} tools checked, "
          f"all contract keywords within {MCP_DESC_MAX} chars")


# ── Per-tool detail (optional verbose report) ────────────────────────────

def test_docstring_mcp_truncation_per_tool():
    """
    One assertion per tool: each tool's contract keywords survive truncation.
    This produces individual PASS/FAIL lines in pytest -v output for easier
    forensic identification when a new tool or docstring edit breaks the gate.
    """
    inst, tool_names = _load_tools()

    for name in sorted(tool_names):
        doc = _tool_docstring(inst, name)
        if not doc:
            continue

        survives, missing = _all_keywords_survive_truncation(doc)

        if missing:
            details = ", ".join(f"{kw}@{doc.find(kw)}" for kw in sorted(missing))
            detail_msg = f" ({details})"
        else:
            detail_msg = ""

        assert survives, (
            f"{name} has contract keywords beyond {MCP_DESC_MAX} chars{detail_msg}"
        )

    print(f"Per-tool MCP truncation gate PASSED: {len(tool_names)} tools")
