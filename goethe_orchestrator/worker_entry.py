#!/usr/bin/env python3
"""
goethe_orchestrator.worker_entry — ADR-ORCH-001 Phase 4: worker-side runner
===========================================================================
Runs ON THE RAY WORKER NODE (shipped there via runtime_env working_dir by
LocalOrchestrator._dispatch_ray). STDLIB ONLY — it must import on a bare
node with no LSE stack installed; do not add sibling-package imports here.

Contract (envelope payload convention v1):
  run_envelope(handler_name, args, envelope_id) -> dict
    {"status": "ok",    "result": <handler return value>, "envelope_id": ...}
    {"status": "error", "error": "<ExcType>: <msg>",      "envelope_id": ...}
  args arrives with "__envelope_id__" injected by the orchestrator; this
  module pops it before calling the handler.

Handler registry: built-ins below + register_handler() for future bundles.
Tiering (ADR-ORCH-001): remote nodes are Tier-1 — only read-only handlers
may be registered here. Echo (smoke) and node_info (affinity verification)
are the v1 built-ins.
"""
from __future__ import annotations

import socket
from typing import Any, Callable, Dict

_registry: Dict[str, Callable[..., Any]] = {}


def register_handler(name: str, fn: Callable[..., Any]) -> None:
    """Register a worker-side handler (future handler bundles use this)."""
    _registry[name] = fn


def _echo(**kw: Any) -> str:
    return "echo:" + str(kw.get("msg", ""))


def _node_info(**kw: Any) -> Dict[str, str]:
    """Identity probe — verifies a dispatch actually landed on the pinned
    node (hostname + node IP + Ray node id)."""
    hostname = socket.gethostname()
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        # UDP connect sends no packets; it selects the outbound interface
        # that would reach the head, so `ip` is this node's cluster IP.
        s.connect(("192.168.1.57", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    ray_node_id = ""
    try:
        from ray import get_runtime_context
        ray_node_id = get_runtime_context().get_node_id()
    except Exception:  # noqa: BLE001 — running outside Ray is fine (tests)
        pass
    return {"hostname": hostname, "ip": ip, "ray_node_id": ray_node_id}


register_handler("echo", _echo)
register_handler("node_info", _node_info)


def run_envelope(handler_name: str, args: Dict[str, Any],
                 envelope_id: str) -> Dict[str, Any]:
    """Execute one envelope on this node. Never raises — errors are data."""
    kwargs = dict(args or {})
    kwargs.pop("__envelope_id__", None)
    handler = _registry.get(handler_name)
    if handler is None:
        return {"status": "error",
                "error": f"no handler {handler_name!r} on this node",
                "envelope_id": envelope_id}
    try:
        result = handler(**kwargs)
    except Exception as exc:  # noqa: BLE001 — handler errors are data
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}",
                "envelope_id": envelope_id}
    return {"status": "ok", "result": result, "envelope_id": envelope_id}
