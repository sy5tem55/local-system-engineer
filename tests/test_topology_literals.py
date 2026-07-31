"""D6 guard — no new hardcoded topology literals outside Valves/_NODE_REGISTRY.

WHY THIS EXISTS (2026-07-31). The D6 sweep routed 22 hardcoded topology
literals in tools/goethe.py to Valves fields, _NODE_REGISTRY, or module-level
constants. This test pins the result so they cannot silently come back.

The scan:
  - Parses tools/goethe.py with ast.
  - Walks all string constants.
  - Skips anything inside the Valves class body (those are the config
    mechanism working correctly, not defects).
  - Flags remaining strings matching topology patterns: /opt/local-se,
    /home/sy5, 127.0.0.1, localhost, .home.arpa, or explicit host:port URLs.
  - Asserts the flagged set is a subset of an embedded allowlist seeded
    from the D6 AST scan output (/tmp/d6_allowlist.txt).

To ADD a new allowed literal:
  - Prefer routing it to a Valves field, _NODE_REGISTRY, or a module constant.
  - Only widen the allowlist if the literal is genuinely not topology
    (e.g. docstring text, third-party API URL, user-facing message).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
# D7 (2026-07-31): extended from a single _TARGET to a list when
# goethe_netsec.py was extracted as the first mixin. New mixin files must be
# added here in the same step that creates them, per
# docs/D7-MIXIN-EXTRACTION-PLAN.md hazard #5 - a mixin absent from this list
# is unguarded code, even though it lives under tools/.
_TARGETS = [_TOOLS / "goethe.py", _TOOLS / "goethe_netsec.py"]

# Topology patterns: strings matching these are candidates for routing.
_TOPO_RE = re.compile(
    r'(?:/opt/local-se|/home/sy5|127\.0\.0\.1|localhost|\.home\.arpa|http://[^/]+:\d+)'
)

# Allowlist: substrings that, when found in a flagged literal, mark it as allowed.
# Anchored on text content so ordinary edits above don't break it.
# Updated from /tmp/d6_allowlist.txt (2026-07-31).
ALLOWLIST_SNIPPETS: frozenset[str] = frozenset({
    # Module-level constants (the config homes themselves)
    '_LSE_BASE_PATH = "/opt/local-se"',
    '_LOOPBACK = "127.0.0.1"',

    # _NODE_REGISTRY hostnames (canonical source of truth)
    'node3090.home.arpa',
    'node5090.home.arpa',

    # Conflict A: Ollama embedding endpoint (KEEP-AND-DOCUMENT)
    'http://127.0.0.1:11434',

    # Conflict B: Elasticsearch fallback (KEEP-AND-DOCUMENT)
    'http://127.0.0.1:9200',

    # download-monitor: miniforge interpreter (JUSTIFIED KEEP)
    '/home/sy5/miniforge3/bin/python3',

    # download-monitor: user-facing error message (JUSTIFIED KEEP)
    'SETUP_REQUIRED | download-monitor.py not found at /opt/local-se/.',

    # Docstrings (informational, not executable)
    'Spawn a transient llama-server on 127.0.0.1:<port>',
    'local SearxNG instance at localhost:8088',
    'node3090 → local Firecrawl at localhost:3002',
    'POST url to Firecrawl',
    'Prometheus network metrics',
    'pfsense.home.arpa',  # example in plan_step_done docstring
    'http://node4090.home.arpa',  # example in docstrings
    'LUCIFER:  pings node3090, then uses Firecrawl at node3090:3002',  # docstring example

    # Third-party API endpoints (not local topology)
    'https://api.openai.com',
    'https://www.reddit.com',
    'https://www.cloudflare.com',
    'https://www.google.com',
    'https://api.github.com/repos/',

    # Generic scheme prefixes used in URL assembly (EXACT match only — not substring)
    # These are handled by ALLOWED_EXACT below, not here.
})

# Exact-match allowed strings (module-level constants and bare scheme prefixes).
# These must match the ENTIRE literal value.
ALLOWED_EXACT: frozenset[str] = frozenset({
    '/opt/local-se',
    '127.0.0.1',
    'http://',       # bare scheme prefix used in URL assembly, not a full URL
    'https://',     # bare scheme prefix used in URL assembly
})


def _in_valves_class(tree: ast.Module, line: int) -> bool:
    """True if this line is inside the Valves class body."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Valves":
            end = node.end_lineno or node.lineno
            if node.lineno <= line <= end:
                return True
    return False


def _enclosing_function(tree: ast.Module, line: int) -> str | None:
    """Name of the function/method enclosing this line, or None."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            if node.lineno <= line <= end:
                if best is None or node.lineno > best.lineno:
                    best = node
    return best.name if best else None


def _is_docstring_node(tree: ast.Module, node: ast.Constant) -> bool:
    """True if this constant is a docstring (first statement in a module/class/function)."""
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (parent.body and
                isinstance(parent.body[0], ast.Expr) and
                isinstance(parent.body[0].value, ast.Constant) and
                parent.body[0].value is node):
                return True
    return False


def _topology_literals(source: str) -> list[tuple[int, str, str | None, bool]]:
    """Return (line, literal, enclosing_func, is_docstring) for each topology-like string outside Valves."""
    tree = ast.parse(source)
    results: list[tuple[int, str, str | None, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if _TOPO_RE.search(s) and not _in_valves_class(tree, node.lineno):
                func = _enclosing_function(tree, node.lineno)
                is_doc = _is_docstring_node(tree, node)
                results.append((node.lineno, s, func, is_doc))
    return results


def _allowed(literal: str, is_docstring: bool) -> bool:
    """Check if this literal is covered by the allowlist."""
    # Exact match for module-level constants and bare scheme prefixes
    if literal in ALLOWED_EXACT:
        return True
    # Substring match against allowlist snippets
    for allowed in ALLOWLIST_SNIPPETS:
        if allowed in literal:
            return True
    return False


@pytest.mark.parametrize("target", _TARGETS, ids=lambda p: p.name)
def test_no_new_topology_literals(target):
    """Assert no new hardcoded topology literals outside Valves/_NODE_REGISTRY.

    If this fails, route the offending literal to a Valves field, _NODE_REGISTRY,
    or a module-level constant. Only widen ALLOWLIST_SNIPPETS for genuinely
    non-topology strings (docstrings, third-party URLs, user-facing messages).
    """
    source = target.read_text(encoding="utf-8")
    flagged = _topology_literals(source)

    violations = [
        (line, lit, func, is_doc)
        for line, lit, func, is_doc in flagged
        if not _allowed(lit, is_doc)
    ]

    if violations:
        msg_lines = [
            f"New hardcoded topology literal(s) found in {target.name} outside Valves/_NODE_REGISTRY:",
        ]
        for line, lit, func, is_doc in violations:
            snippet = lit[:100] + "..." if len(lit) > 100 else lit
            kind = "docstring" if is_doc else (func or "module")
            msg_lines.append(
                f"  L{line} ({kind}): {snippet!r}"
            )
        msg_lines.append(
            "Fix: route to a Valves field, _NODE_REGISTRY, or a module-level constant."
        )
        pytest.fail("\n".join(msg_lines))


@pytest.mark.parametrize("target", _TARGETS, ids=lambda p: p.name)
def test_gate_detects_new_literal(target):
    """Negative test: prove the gate actually bites, per scanned file.

    Temporarily inject a fake literal, assert the scan catches it, then restore.
    """
    source = target.read_text(encoding="utf-8")
    # Use a unique hostname:port that cannot be in the allowlist
    fake = "\n# D6-GATE-TEST\n_fake_test_literal = 'http://fake-node.home.arpa:54321'\n"
    modified = source + fake

    flagged = _topology_literals(modified)
    violations = [
        (line, lit, func, is_doc)
        for line, lit, func, is_doc in flagged
        if not _allowed(lit, is_doc)
    ]

    # Must catch the injected literal
    fake_hits = [v for v in violations if "54321" in v[1]]
    assert len(fake_hits) == 1, (
        f"Gate should catch the fake literal but found {len(fake_hits)} hits: {fake_hits}"
    )
