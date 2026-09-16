#!/usr/bin/env python3
"""
goethe_orchestrator/contracts.py — ADR-ORCH-001 normative contract models
==========================================================================
Phase 1 of ADR-ORCH-001 (Goethe distributed task contracts + Ray execution
substrate). This module defines the two data contracts that are the
task-of-record for the orchestrator; Ray is an execution substrate only and
must never be treated as the record (the SQLite WAL ledger is).

Contracts (versioned, additive-only evolution):
  goethe.task-envelope/v1          — TaskEnvelope
  worker-registration+heartbeat/v1 — WorkerRegistration

Design constraints (ADR-ORCH-001):
  * Stdlib only — no third-party deps at import time (matches the rest of
    tools/; the ledger persists these as JSON TEXT columns, same convention
    as task_blocks.steps_json in goethe_planner.py).
  * No import direction into goethe.py / goethe_mcp.py — this module is a
    leaf. The orchestrator imports it, never the reverse.
  * Timestamps are ISO-8601 UTC strings ("2026-09-13T17:05:00+00:00") so
    they round-trip through JSON without tz-object fragility.

Contract-version constants are part of the on-wire format: bumping them is a
breaking change and requires the GOETHE_ORCHESTRATOR_ENABLED rollback path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# ── Contract version identifiers (on-wire; do not rename) ──────────────────
TASK_ENVELOPE_V1 = "goethe.task-envelope/v1"
WORKER_REGISTRATION_V1 = "worker-registration+heartbeat/v1"

# ── TaskEnvelope status vocabulary (v1) ─────────────────────────────────────
# PENDING     — accepted into the ledger, not yet dispatched
# DISPATCHED  — handed to a worker (Ray actor) by the scheduler
# RUNNING     — worker acknowledged execution
# SUCCEEDED   — worker reported success (terminal)
# FAILED      — worker reported failure or raised (terminal)
# EXPIRED     — ttl elapsed before completion (terminal)
TASK_STATUSES = ("PENDING", "DISPATCHED", "RUNNING", "SUCCEEDED", "FAILED", "EXPIRED")

# ── WorkerRegistration status vocabulary (v1) ───────────────────────────────
# ACTIVE  — registered and heartbeating within ttl
# EXPIRED — heartbeat ttl elapsed; scheduler must not assign new work
# DRAINED — voluntarily stopped (graceful shutdown); in-flight work may finish
WORKER_STATUSES = ("ACTIVE", "EXPIRED", "DRAINED")


def _utcnow_iso() -> str:
    """Current UTC time as ISO-8601 with explicit offset (ledger convention)."""
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not valid ISO-8601: {value!r}") from exc
    if dt.tzinfo is None:
        # Naive timestamps are a contract violation — the ledger is UTC-only.
        raise ValueError(f"{field_name} must carry a UTC offset: {value!r}")
    return dt


@dataclass
class TaskEnvelope:
    """goethe.task-envelope/v1 — the task-of-record unit.

    One envelope per unit of work. The envelope is what the ledger stores,
    what the scheduler scores, and what the event log references by id.
    Payload is opaque to the orchestrator: it is the task spec the target
    worker's tool surface understands.

    Fields:
      id         — unique task id (uuid4 hex unless supplied)
      payload    — opaque task specification (dict), worker-side contract
      priority   — integer weight for the weighted-v1 scheduler (higher =
                   more urgent); 0 is the default
      ttl        — time-to-live in seconds from created_at; expiry marks the
                   envelope EXPIRED and frees any dispatch hold
      created_at — ISO-8601 UTC creation timestamp
      status     — one of TASK_STATUSES; PENDING on creation
    """

    payload: Dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    priority: int = 0
    ttl: int = 3600
    created_at: str = field(default_factory=_utcnow_iso)
    status: str = "PENDING"
    contract: str = TASK_ENVELOPE_V1

    def __post_init__(self) -> None:
        if self.contract != TASK_ENVELOPE_V1:
            raise ValueError(
                f"unsupported task contract: {self.contract!r} "
                f"(expected {TASK_ENVELOPE_V1!r})"
            )
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict (opaque task spec)")
        if self.priority < 0:
            raise ValueError(f"priority must be >= 0, got {self.priority}")
        if self.ttl <= 0:
            raise ValueError(f"ttl must be > 0 seconds, got {self.ttl}")
        if self.status not in TASK_STATUSES:
            raise ValueError(f"invalid status {self.status!r}; expected one of {TASK_STATUSES}")
        _parse_iso(self.created_at, "created_at")

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """True if created_at + ttl is in the past."""
        now = now or datetime.now(timezone.utc)
        deadline = _parse_iso(self.created_at, "created_at") + timedelta(seconds=self.ttl)
        return now >= deadline

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract": self.contract,
            "id": self.id,
            "payload": self.payload,
            "priority": self.priority,
            "ttl": self.ttl,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEnvelope":
        known = {"contract", "id", "payload", "priority", "ttl", "created_at", "status"}
        unknown = set(data) - known
        if unknown:
            # Forward-compat: newer fields are preserved in payload-side
            # metadata, not silently dropped — but v1 refuses to construct
            # from a future contract version.
            raise ValueError(f"unknown fields for {TASK_ENVELOPE_V1}: {sorted(unknown)}")
        return cls(**data)


@dataclass
class WorkerRegistration:
    """worker-registration+heartbeat/v1 — a registered execution worker.

    A worker (local process or remote node) registers once with its
    capability profile and then heartbeats. The scheduler only assigns work
    to workers whose last_heartbeat is within heartbeat_ttl; anything older
    is EXPIRED and must not receive new dispatches.

    Heartbeats do NOT change the registration record's identity — they
    update last_heartbeat (and refresh status). The registration row is the
    stable record; heartbeats are events on it (see event_log).

    Fields:
      worker_id        — stable unique id (e.g. "node3090:llama" or
                         "node4090:local"); assigned by the registering side
      capabilities     — capability profile dict, e.g.
                         {"vram_gb": 24, "ram_gb": 32, "tier": 1,
                          "tools": ["read_file", "execute_command"]}
                         Tier semantics (ADR-ORCH-001): remote workers are
                         Tier-1 (read-only tool surface only); the local
                         worker may be Tier-0 (full surface).
      heartbeat_ttl    — seconds; a worker silent for longer than this is
                         EXPIRED and drained from scheduling
      last_heartbeat   — ISO-8601 UTC of the most recent heartbeat
      status           — one of WORKER_STATUSES; ACTIVE on registration
      ray_node_id      — optional Ray node id (hex) for the ray backend:
                         when set, LocalOrchestrator pins the dispatch to
                         that node (NodeAffinity). None = no pin (local
                         backend / unmanaged workers).
    """

    worker_id: str
    capabilities: Dict[str, Any]
    heartbeat_ttl: int = 30
    last_heartbeat: str = field(default_factory=_utcnow_iso)
    status: str = "ACTIVE"
    contract: str = WORKER_REGISTRATION_V1
    ray_node_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.contract != WORKER_REGISTRATION_V1:
            raise ValueError(
                f"unsupported worker contract: {self.contract!r} "
                f"(expected {WORKER_REGISTRATION_V1!r})"
            )
        if not self.worker_id or not isinstance(self.worker_id, str):
            raise ValueError("worker_id must be a non-empty string")
        if not isinstance(self.capabilities, dict):
            raise ValueError("capabilities must be a dict")
        if self.heartbeat_ttl <= 0:
            raise ValueError(f"heartbeat_ttl must be > 0 seconds, got {self.heartbeat_ttl}")
        if self.ray_node_id is not None and (
                not isinstance(self.ray_node_id, str) or not self.ray_node_id):
            raise ValueError("ray_node_id must be a non-empty string or None")
        if self.status not in WORKER_STATUSES:
            raise ValueError(f"invalid status {self.status!r}; expected one of {WORKER_STATUSES}")
        _parse_iso(self.last_heartbeat, "last_heartbeat")

    def heartbeat(self, now: Optional[datetime] = None) -> None:
        """Record a heartbeat: refresh last_heartbeat, restore ACTIVE.

        A DRAINED worker does not revive on heartbeat — draining is
        voluntary and sticky until re-registration.
        """
        if self.status == "DRAINED":
            return
        self.last_heartbeat = (now or datetime.now(timezone.utc)).isoformat()
        self.status = "ACTIVE"

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """True if last_heartbeat + heartbeat_ttl is in the past."""
        now = now or datetime.now(timezone.utc)
        if self.status == "DRAINED":
            return True
        deadline = _parse_iso(self.last_heartbeat, "last_heartbeat") + timedelta(
            seconds=self.heartbeat_ttl
        )
        return now >= deadline

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract": self.contract,
            "worker_id": self.worker_id,
            "capabilities": self.capabilities,
            "heartbeat_ttl": self.heartbeat_ttl,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerRegistration":
        known = {
            "contract", "worker_id", "capabilities",
            "heartbeat_ttl", "last_heartbeat", "status",
        }
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"unknown fields for {WORKER_REGISTRATION_V1}: {sorted(unknown)}"
            )
        return cls(**data)


