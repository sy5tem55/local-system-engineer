#!/usr/bin/env python3
"""
goethe_orchestrator.cluster_config — ADR-ORCH-001 Phase 4: cluster topology
============================================================================
Pure config module — it does NOT start anything (step 10 STOP-AFTER). It
encodes the 2-node topology and the exact `ray start` argument sets:

  HEAD    node4090 (LUCIFER, 192.168.1.57) — the Goethe gateway +
          LocalOrchestrator run here; Ray head lives here.
  WORKER  node3090 (192.168.5.41, Ubuntu 22.04, 9900K, 32GB RAM,
          RTX 3090 24GB) — joins as a Ray worker.

Security posture: reuses ray_config.get_secure_ray_config (token auth via
RAY_AUTH_TOKEN_PATH, dashboard loopback-only). The head generates the
token; the worker must receive the SAME token file before `ray start`
(ensure_token(generate_token=False) on the worker side enforces this).

VLAN NOTE (KB c296b8146fc89fd1, quality 0.90): node3090 sits on the
192.168.5.x segment behind the RUTX50 router (192.168.5.3); LUCIFER is on
192.168.1.x. Cross-VLAN reachability for GCS (6379) and the Ray worker
gRPC ports is a Phase-4 PREREQUISITE — verify it before starting the
cluster (steps 11/12 territory). Do not assume it.

Node facts come from the KB network map, not from memory; the SSH key
path is deliberately NOT hardcoded — ssh access goes through the
~/.ssh/config alias so key rotation never touches this file.
"""
from __future__ import annotations

from typing import Dict, List

from goethe_orchestrator.ray_config import (
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_GCS_PORT,
    DEFAULT_TOKEN_PATH,
    get_secure_ray_config,
)

HEAD: Dict[str, str] = {
    "name": "node4090",
    "hostname": "node4090.home.arpa",
    "ip": "192.168.1.57",
    "role": "head",
}

WORKERS: List[Dict[str, str]] = [
    {
        "name": "node3090",
        "hostname": "node3090.home.arpa",
        "ip": "192.168.5.41",
        "role": "worker",
        "ssh_user": "lse-admin",
        "platform": "linux",
    },
]


def get_cluster_config(
    token_path: str = DEFAULT_TOKEN_PATH,
    gcs_port: int = DEFAULT_GCS_PORT,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    generate_token: bool = True,
) -> Dict[str, object]:
    """Build the head + per-worker launch config for the 2-node cluster.

    Args:
        token_path: shared auth token file (head writes it, worker must
            receive the identical file before joining).
        gcs_port / dashboard_port: as in ray_config.
        generate_token: True = head generates the token if missing (the
            head-side call). Worker-side provisioning calls with False so
            a missing token is a hard error, not a silent new cluster.

    Returns:
        {
          "head":      {"name", "hostname", "ip", "env", "start_args"},
          "workers":   [{"name", "hostname", "ip", "ssh_user", "env",
                         "start_args"}],
          "token_path": str,
          "prerequisites": [str, ...],
        }
    """
    head_cfg = get_secure_ray_config(
        token_path=token_path, gcs_port=gcs_port,
        dashboard_port=dashboard_port, generate_token=generate_token,
    )
    head_address = f"{HEAD['ip']}:{gcs_port}"
    worker_cfg = get_secure_ray_config(
        token_path=token_path, gcs_port=gcs_port,
        dashboard_port=dashboard_port, head_address=head_address,
        generate_token=False,
    )
    return {
        "head": {
            "name": HEAD["name"],
            "hostname": HEAD["hostname"],
            "ip": HEAD["ip"],
            "env": head_cfg["env"],
            "start_args": head_cfg["head_args"],
        },
        "workers": [
            {
                **w,
                "env": worker_cfg["env"],
                "start_args": worker_cfg["worker_args"],
            }
            for w in WORKERS
        ],
        "token_path": head_cfg["token_path"],
        "prerequisites": [
            f"cross-VLAN reachability: {WORKERS[0]['ip']} to "
            f"{HEAD['ip']}:{gcs_port} (GCS) verified — node3090 is on the "
            "192.168.5.x segment behind RUTX50, LUCIFER on 192.168.1.x",
            f"token file copied to {WORKERS[0]['hostname']} (0600, "
            "generate_token=False enforced there)",
            f"ray {_ray_version_note()} installed on "
            f"{WORKERS[0]['hostname']} (head env has 2.58.0; worker must "
            "match major.minor)",
            "worker node awake (WoL via RUTX50 etherwake — see KB "
            "842595879f70576d; LUCIFER-side wakeonlan does NOT reach it)",
        ],
    }


def _ray_version_note() -> str:
    """Ray version pin for the worker install (single source of truth)."""
    import ray
    return ray.__version__


def worker_provision_commands(worker: Dict[str, str],
                              token_path: str = DEFAULT_TOKEN_PATH,
                              gcs_port: int = DEFAULT_GCS_PORT) -> List[str]:
    """Shell command sequence to provision one worker (DATA, not executed).

    A later step runs these via ssh_script (never as one-liners — the
    token copy and ray start are a multi-command sequence). The ssh
    target is the ~/.ssh/config alias; the key path is config's job.
    Commands are deliberately split so each is an independent,
    idempotent-safe step (no shell chaining in the data).
    """
    head_address = f"{HEAD['ip']}:{gcs_port}"
    return [
        f"scp {token_path} {worker['ssh_user']}@{worker['hostname']}:/tmp/ray_auth_token",
        f"ssh {worker['hostname']} 'chmod 600 /tmp/ray_auth_token'",
        f"ssh {worker['hostname']} 'RAY_AUTH_MODE=token "
        "RAY_AUTH_TOKEN_PATH=/tmp/ray_auth_token ray start --address "
        f"{head_address} --dashboard-host 127.0.0.1'",
        f"ssh {worker['hostname']} 'ray status'",
    ]
