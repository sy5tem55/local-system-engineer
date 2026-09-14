#!/usr/bin/env python3
"""
goethe_orchestrator.ray_config — ADR-ORCH-001 Phase 2: secure Ray substrate config
==================================================================================
Pure config module: builds the environment + `ray start` argument sets for a
token-authenticated, loopback-dashboard Ray cluster. It does NOT start Ray —
the orchestrator (Phase 3) owns the process lifecycle.

Security posture (verified against ray-project/ray docs + advisories,
2026-09-13, KB doc 2ef82c34997d6084):
  * RAY_AUTH_MODE=token — built-in token auth (Ray >= 2.52.0; disabled by
    default upstream, we enable it). Token stored 0600 at
    /opt/local-se/ray/auth_token (LSE write boundary), referenced via
    RAY_AUTH_TOKEN_PATH — never via RAY_AUTH_TOKEN env var (docs recommend
    the file path so the secret is not visible to other env readers).
  * Dashboard bound to 127.0.0.1 only. Rationale: GHSA-q279-jhrf-cc6v
    (Critical, DNS-rebinding RCE via browser) and GHSA-q5fh-2hc8-f6rq
    (Moderate, unauthenticated DELETE DoS) — the dashboard must never be
    reachable from the LAN, let alone the internet. Local operators use an
    SSH tunnel / local browser.
  * GCS (6379) and worker ports bind to the node address for intra-cluster
    gRPC on the trusted LAN. Per Ray's own security model, isolation is
    enforced OUTSIDE Ray (pfSense / LAN boundary) — token auth is
    defense-in-depth, not a substitute.
"""
from __future__ import annotations

import os
import secrets
import stat
from typing import Dict, List, Optional

DEFAULT_TOKEN_PATH = "/opt/local-se/ray/auth_token"
DEFAULT_GCS_PORT = 6379
DEFAULT_DASHBOARD_PORT = 8265


def ensure_token(path: str = DEFAULT_TOKEN_PATH) -> str:
    """Return the auth token at *path*, generating one if absent.

    Creates parent dirs 0700, writes 0600. An existing file is reused
    (Ray clusters use the same token for their lifetime; tokens do not
    expire upstream). Refuses symlinks and group/world-readable files.
    """
    if os.path.islink(path):
        raise RuntimeError(f"refusing symlinked token path: {path}")
    if os.path.exists(path):
        st = os.stat(path)
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise RuntimeError(
                f"token file {path} is group/world accessible "
                f"({oct(stat.S_IMODE(st.st_mode))}); chmod 600 it and retry"
            )
        with open(path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if not token:
            raise RuntimeError(f"token file {path} is empty")
        return token

    token = secrets.token_hex(32)
    parent = os.path.dirname(path)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token + "\n")
    return token


def get_secure_ray_config(
    token_path: str = DEFAULT_TOKEN_PATH,
    gcs_port: int = DEFAULT_GCS_PORT,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    head_address: Optional[str] = None,
    generate_token: bool = True,
) -> Dict[str, object]:
    """Build the secure Ray launch configuration.

    Args:
        token_path: where the cluster auth token lives (0600 file).
        gcs_port: GCS port (6379 upstream default).
        dashboard_port: dashboard port (8265 upstream default) — bound to
            127.0.0.1 only.
        head_address: for worker args, the address workers connect to
            ("<head_ip>:<gcs_port>"). None → loopback (single node).
        generate_token: create the token file if missing (False = require
            an existing token; used by worker nodes that must reuse the
            head's token).

    Returns:
        dict with keys:
          env          — env vars for every `ray start` / client process
          head_args    — argv tail for `ray start` on the head node
          worker_args  — argv tail for `ray start` on worker nodes
          token_path   — resolved token file path
    """
    if generate_token:
        ensure_token(token_path)
    elif not os.path.exists(token_path):
        raise RuntimeError(
            f"token file missing and generate_token=False: {token_path} "
            "(copy the head's token to this path first)"
        )

    env: Dict[str, str] = {
        "RAY_AUTH_MODE": "token",
        "RAY_AUTH_TOKEN_PATH": token_path,
    }

    head_args: List[str] = [
        "--head",
        "--port", str(gcs_port),
        "--dashboard-host", "127.0.0.1",
        "--dashboard-port", str(dashboard_port),
    ]

    address = head_address or f"127.0.0.1:{gcs_port}"
    worker_args: List[str] = [
        "--address", address,
        "--dashboard-host", "127.0.0.1",
    ]

    return {
        "env": env,
        "head_args": head_args,
        "worker_args": worker_args,
        "token_path": token_path,
    }
