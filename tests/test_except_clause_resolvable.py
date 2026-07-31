"""D4 guard — every except clause must resolve to a name bound in its scope.

WHY THIS EXISTS (2026-07-31). The D4 except-triage narrowed 47 broad
`except Exception` blocks to specific types. Nine of them named
`requests.RequestException` — but `requests` is never imported at module
scope in goethe.py. Per the sandbox convention it is imported inside method
bodies, frequently aliased (`_req`, `_wol_req`), and two of the nine sites
used urllib, not requests, at all.

An except clause's type expression is evaluated ONLY when an exception
reaches it. So this defect is invisible to py_compile, to import, and to
every test that does not exercise the failure path — all 487 tests passed
over it. In production the first network error would raise
`NameError: name 'requests' is not defined`, REPLACING the original
exception and converting a designed graceful degradation into a crash,
precisely when the system is already degraded.

ruff's F821 caught it statically. This test makes the invariant permanent
and library-agnostic: resolve every except clause against the names actually
bound in module scope, enclosing function scope, and builtins.

Modeled on the bump_gate.py / test_docstring_mcp_truncation.py pattern:
a cheap AST gate that fails loudly at harness time.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
_TARGETS = ["goethe.py", "goethe_kb.py", "goethe_ui.py"]


def _module_scope_names(tree: ast.Module) -> set[str]:
    """Names bound by top-level (col_offset == 0) imports."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.col_offset == 0:
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.col_offset == 0:
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _locally_bound_names(node: ast.AST) -> set[str]:
    """Names bound by imports anywhere inside a function body."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(child, ast.ImportFrom):
            for alias in child.names:
                names.add(alias.asname or alias.name)
    return names


def _unresolvable_handlers(source: str) -> list[tuple[int, str, str]]:
    tree = ast.parse(source)
    module_names = _module_scope_names(tree)
    builtin_names = set(dir(builtins))
    functions = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    failures: list[tuple[int, str, str]] = []
    for handler in [
        n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.type
    ]:
        exc_types = (
            handler.type.elts
            if isinstance(handler.type, ast.Tuple)
            else [handler.type]
        )
        scope = module_names | builtin_names
        for fn in functions:
            if fn.lineno <= handler.lineno <= (fn.end_lineno or fn.lineno):
                scope |= _locally_bound_names(fn)

        for exc in exc_types:
            root = exc
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id not in scope:
                failures.append((handler.lineno, ast.unparse(exc), root.id))
    return failures


@pytest.mark.parametrize("filename", _TARGETS)
def test_every_except_clause_resolves(filename: str) -> None:
    path = _TOOLS / filename
    if not path.is_file():
        pytest.skip(f"{filename} not present")

    failures = _unresolvable_handlers(path.read_text(encoding="utf-8"))
    assert not failures, (
        f"{filename}: except clause(s) reference names not bound in scope. "
        "These raise NameError at exception-handling time and destroy the "
        "intended degradation:\n"
        + "\n".join(
            f"  line {line}: `except {expr}` — '{name}' is not imported here"
            for line, expr, name in failures
        )
    )


def test_guard_detects_a_known_bad_pattern() -> None:
    """The guard must actually fail on the D4 defect shape."""
    bad = (
        "def f():\n"
        "    import requests as _req\n"
        "    try:\n"
        "        _req.get('x')\n"
        "    except requests.RequestException:\n"  # unbound: alias is _req
        "        pass\n"
    )
    failures = _unresolvable_handlers(bad)
    assert failures, "guard failed to detect an unbound except clause"
    assert failures[0][2] == "requests"
