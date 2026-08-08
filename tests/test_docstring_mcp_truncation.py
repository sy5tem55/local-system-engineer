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

import ast
import glob
import importlib.util
import inspect
import re

# ── Constants — read from goethe_mcp.py, never re-declared here ──────────
# 2026-08-08: this used to hardcode 1024 and drift silently from the gateway.
# Parse the real default so raising the cap cannot leave the gate testing a
# number the gateway no longer uses.
def _mcp_desc_max():
    src = open("tools/goethe_mcp.py", encoding="utf-8").read()
    m = re.search(r'_TOOL_DESC_MAX\s*=\s*int\(\s*os\.environ\.get\(\s*"GOETHE_MCP_TOOL_DESC_MAX"\s*,\s*"(\d+)"', src)
    assert m, "cannot find _TOOL_DESC_MAX default in tools/goethe_mcp.py"
    return int(m.group(1))


MCP_DESC_MAX = _mcp_desc_max()

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
        # 2026-08-08: the old gate required >=1 real parameter here, which
        # silently excluded every zero-arg tool. time_check() takes no args,
        # is exposed by the gateway, and was losing GATE@2037 unnoticed.
        # The gateway does not filter on arity; neither may this gate.
        tools.append(name)
    return inst, tools


# Add-on tool modules registered by goethe_mcp.py alongside goethe.py. The old
# gate read goethe.py only, so pfsense/vaultwarden/net-discovery — 10 tools,
# three of them losing contract keywords — were never checked at all.
_ADDON_GLOBS = (
    "tools/pfsense_tools_v*.py",
    "tools/vaultwarden_tools_v*.py",
    "tools/net_discovery_tools_v*.py",
)


def _addon_docstrings():
    """Return {tool_name: docstring} for every add-on module tool.

    Parsed with ast rather than imported: these modules pull in live
    network/vault dependencies a unit test must not touch. ast (not regex --
    a regex here silently missed net_discovery_scan by over-consuming across
    a def with no docstring) gives exact function boundaries.
    """
    out = {}
    for pattern in _ADDON_GLOBS:
        for path in glob.glob(pattern):
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("_") or node.name in SKIP_TOOLS:
                    continue
                # clean=False is load-bearing: goethe_mcp sends
                # wrapper.__doc__.strip(), which KEEPS the source indentation.
                # ast's default dedents, which shifts every offset left and
                # makes the gate optimistic -- pfsense_graphql's NEVER reads
                # @1104 dedented but @1256 as actually transmitted.
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    out[node.name] = doc.strip()
    return out


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
    addons = _addon_docstrings()
    all_docs = {n: _tool_docstring(inst, n) for n in tool_names}
    all_docs.update(addons)

    failures = []
    for name in sorted(all_docs):
        doc = all_docs[name]
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
    print(f"MCP truncation gate PASSED: {len(all_docs)} tools checked "
          f"({len(tool_names)} core + {len(addons)} add-on), "
          f"all contract keywords within {MCP_DESC_MAX} chars")


# ── Per-tool detail (optional verbose report) ────────────────────────────

def test_docstring_mcp_truncation_per_tool():
    """
    One assertion per tool: each tool's contract keywords survive truncation.
    This produces individual PASS/FAIL lines in pytest -v output for easier
    forensic identification when a new tool or docstring edit breaks the gate.
    """
    inst, tool_names = _load_tools()
    all_docs = {n: _tool_docstring(inst, n) for n in tool_names}
    all_docs.update(_addon_docstrings())

    for name in sorted(all_docs):
        doc = all_docs[name]
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

    print(f"Per-tool MCP truncation gate PASSED: {len(all_docs)} tools")
