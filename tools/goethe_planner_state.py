"""goethe_planner_state.py — persisted planner-backend selection (v1.0.0).

Shared by goethe_ui.py (reads AND writes, from the Console) and goethe.py
(reads, to route planner() calls). Deliberately standalone: it imports
neither of them. goethe_ui.py has never imported goethe.py and this module
must not become the reason that changes — it is the seam between them, not
a bridge.

WHY THIS EXISTS
    Before this, `active` came from the GOETHE_PLANNER_BACKEND env var read
    per-request. The Console could display which backend was active but had
    no way to change it, and any change would not have survived a restart.
    This gives the selection somewhere durable to live that both processes
    agree on.

PRECEDENCE — resolved by selected_backend():
    1. this store  — the operator's Console choice, survives restarts
    2. env default — GOETHE_PLANNER_BACKEND / the PLANNER_BACKEND valve
    3. 'local'     — the free LAN call; the safe floor

DURABILITY
    Writes are atomic (tmp file + os.replace on the same filesystem), so a
    crash mid-write cannot leave a truncated JSON file that would wedge the
    planner on the next read. A corrupt, missing, or unreadable file
    degrades to "no selection recorded" and falls through to the env
    default — it never raises. A planner backend selector must not be able
    to take the planner down.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Optional

__version__ = "1.0.0"

# The four backends _call_planner_backend() dispatches on. Kept here rather
# than imported from goethe.py to preserve this module's zero-coupling
# design; test_planner_backend_state.py asserts the two lists stay in sync.
VALID_BACKENDS = ("local", "chatgpt", "claude", "rest")

_DEFAULT_PATH = "/opt/local-se/state/planner-backend.json"


def state_path() -> str:
    """Absolute path to the selection file. GOETHE_PLANNER_STATE_PATH
    overrides, same GOETHE_<FIELD> convention goethe_mcp.py uses for valve
    overrides, so a test or a second deployment can point elsewhere."""
    return os.environ.get("GOETHE_PLANNER_STATE_PATH", "").strip() or _DEFAULT_PATH


def read_selection() -> Optional[dict]:
    """The recorded selection as a dict, or None if nothing valid is stored.

    Returns None (not an exception) for every failure mode: file absent,
    unreadable, not JSON, not an object, or naming a backend no longer in
    VALID_BACKENDS. That last case matters on downgrade — a store written by
    a newer build must not wedge an older one.
    """
    path = state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    backend = str(data.get("backend", "")).strip().lower()
    if backend not in VALID_BACKENDS:
        return None
    return {
        "backend": backend,
        "selected_at": data.get("selected_at"),
        "selected_by": data.get("selected_by"),
    }


def write_selection(backend: str, actor: str = "console") -> dict:
    """Record `backend` as the active planner backend. Atomic.

    Raises ValueError on an unknown backend — the caller (the Console route)
    turns that into a 400. Raises OSError if the state directory is not
    writable, which the route surfaces as a 503 rather than silently
    pretending the switch took effect.
    """
    backend = (backend or "").strip().lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"unknown backend {backend!r} — must be one of {', '.join(VALID_BACKENDS)}"
        )

    payload = {
        "backend": backend,
        "selected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "selected_by": actor or "console",
        "_note": "written by goethe_planner_state.write_selection; "
                 "read by goethe.py's _resolve_backend_name and the Console",
    }

    path = state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Same directory as the target so os.replace stays a rename, not a
    # cross-filesystem copy (which would not be atomic).
    fd, tmp = tempfile.mkstemp(
        prefix=".planner-backend.", suffix=".tmp",
        dir=os.path.dirname(path),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return payload


def clear_selection() -> bool:
    """Drop the stored selection so resolution falls back to the env default.
    True if a file was removed, False if there was nothing to remove."""
    try:
        os.unlink(state_path())
        return True
    except OSError:
        return False


def selected_backend(env_default: str = "") -> str:
    """Resolve the effective backend name: store → env default → 'local'.

    `env_default` is passed in rather than read here so each caller supplies
    it from its own configuration layer — goethe.py hands over the
    PLANNER_BACKEND valve, goethe_ui.py hands over GOETHE_PLANNER_BACKEND.
    """
    stored = read_selection()
    if stored:
        return stored["backend"]
    name = (env_default or "").strip().lower()
    return name if name in VALID_BACKENDS else "local"


def resolution_source() -> str:
    """Where the effective value came from — 'store' or 'env'. Console-only;
    lets the panel show the operator whether a Console choice is in force or
    it is still running on the deployment default."""
    return "store" if read_selection() else "env"
