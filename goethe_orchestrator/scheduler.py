#!/usr/bin/env python3
"""
goethe_orchestrator/scheduler.py — weighted-v1 scheduler (ADR-ORCH-001 Phase 1)
================================================================================
Scores registered workers for a task envelope and picks the best eligible
one. Pure decision logic: it holds no I/O, talks to no Ray, and persists
nothing — the orchestrator owns registration state persistence and dispatch.
Keeping this module side-effect-free is what makes it unit-testable without a
cluster (see tests/test_orchestrator.py) and swappable behind the
GOETHE_SCHEDULER_POLICY valve.

Scoring model (weighted-v1)
---------------------------
A worker is ELIGIBLE for an envelope only if it passes the hard gates:
  1. status is ACTIVE (EXPIRED/DRAINED never receive new work)
  2. heartbeat fresh: last_heartbeat within heartbeat_ttl
  3. capability match: every requirement in envelope.payload["requires"]
     is satisfied by worker.capabilities:
       - "tools": required list must be a subset of the worker's tools
       - numeric values: worker capability >= required value (headroom ok)
       - other values: exact match

Eligible workers are scored in [0, 1]:
  score = W_CAPABILITY * capability_score + W_FRESHNESS * freshness_score

  capability_score — 0.9 base for meeting every requirement, plus
                    0.1 * headroom_ratio (mean of (have-required)/required
                    over numeric requirements, each capped at 1.0) →
                    [0.9, 1.0]. Workers with no requirements to check
                    score 1.0. Headroom is a tie-breaker, not a gate.
  freshness_score  — 1 - (heartbeat_age / heartbeat_ttl), clipped to [0, 1].
                    A worker at the expiry edge scores 0 but is still
                    eligible (the gate is >=, not >).

Default weights: W_CAPABILITY=0.6, W_FRESHNESS=0.4. Ties break on
worker_id (lexicographic) so scheduling is deterministic for a given
state — important for replay and tests.

The envelope's `priority` does NOT enter the worker score: priority orders
the TASK QUEUE (which envelope is dispatched next), weighted-v1 scores
WORKERS for a given envelope. Mixing the two would let a high-priority task
starve low-priority ones of good workers — the ADR keeps them orthogonal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from goethe_orchestrator.contracts import TaskEnvelope, WorkerRegistration

DEFAULT_WEIGHTS = {"capability": 0.6, "freshness": 0.4}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _heartbeat_age_seconds(w: WorkerRegistration, now: datetime) -> float:
    from goethe_orchestrator.contracts import _parse_iso
    return max(0.0, (now - _parse_iso(w.last_heartbeat, "last_heartbeat")).total_seconds())


def _extract_requirements(envelope: TaskEnvelope) -> Dict[str, Any]:
    """Requirements live in the payload under 'requires' (worker-side contract)."""
    req = envelope.payload.get("requires", {})
    if not isinstance(req, dict):
        raise ValueError(
            f"envelope {envelope.id}: payload['requires'] must be a dict, "
            f"got {type(req).__name__}"
        )
    return req


def capability_satisfied(worker: WorkerRegistration, req: Dict[str, Any]) -> bool:
    """Hard gate: does the worker's capability profile meet every requirement?"""
    caps = worker.capabilities
    for key, required in req.items():
        if key == "tools":
            if not isinstance(required, (list, tuple)):
                raise ValueError(f"requirement 'tools' must be a list, got {type(required).__name__}")
            have = set(caps.get("tools", []))
            if not set(required) <= have:
                return False
        elif isinstance(required, (int, float)) and not isinstance(required, bool):
            have = caps.get(key)
            if not isinstance(have, (int, float)) or isinstance(have, bool):
                return False
            if have < required:
                return False
        else:
            if caps.get(key) != required:
                return False
    return True


def capability_score(worker: WorkerRegistration, req: Dict[str, Any]) -> float:
    """[0.9,1.0] when requirements exist (1.0 when none): headroom tie-breaker."""
    if not req:
        return 1.0
    caps = worker.capabilities
    ratios = []
    for key, required in req.items():
        if key == "tools" or not isinstance(required, (int, float)) or isinstance(required, bool):
            continue
        if required <= 0:
            continue
        have = caps.get(key)
        if isinstance(have, (int, float)) and not isinstance(have, bool) and have >= required:
            ratios.append(min(1.0, (have - required) / required))
    headroom = sum(ratios) / len(ratios) if ratios else 0.0
    return round(0.9 + 0.1 * headroom, 6)


def freshness_score(worker: WorkerRegistration, now: Optional[datetime] = None) -> float:
    """[0,1]: 1.0 just after a heartbeat, 0.0 at the expiry edge."""
    now = now or _utcnow()
    age = _heartbeat_age_seconds(worker, now)
    return max(0.0, min(1.0, 1.0 - age / worker.heartbeat_ttl))


class WeightedScheduler:
    """weighted-v1: deterministic best-worker selection over registered workers.

    The scheduler keeps an in-memory registry (worker_id -> WorkerRegistration).
    The orchestrator mirrors it into the ledger; this class is the pure
    decision core and is safe to instantiate per-decision or long-lived.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            for key in self.weights:
                if key in weights:
                    self.weights[key] = float(weights[key])
            unknown = set(weights) - set(self.weights)
            if unknown:
                raise ValueError(f"unknown weight keys: {sorted(unknown)}")
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("weights must sum to > 0")
        self._workers: Dict[str, WorkerRegistration] = {}

    # ── registry maintenance (orchestrator calls these) ──────────────────
    def register(self, worker: WorkerRegistration) -> None:
        self._workers[worker.worker_id] = worker

    def unregister(self, worker_id: str) -> None:
        self._workers.pop(worker_id, None)

    def heartbeat(self, worker_id: str) -> bool:
        w = self._workers.get(worker_id)
        if w is None:
            return False
        w.heartbeat()
        return True

    def get(self, worker_id: str) -> Optional[WorkerRegistration]:
        return self._workers.get(worker_id)

    def all_workers(self) -> List[WorkerRegistration]:
        return list(self._workers.values())

    def tick(self, now: Optional[datetime] = None) -> List[str]:
        """Expire stale workers in place; returns the ids that flipped to EXPIRED."""
        now = now or _utcnow()
        flipped = []
        for w in self._workers.values():
            if w.status == "ACTIVE" and w.is_expired(now=now):
                w.status = "EXPIRED"
                flipped.append(w.worker_id)
        return flipped

    # ── scoring / selection ───────────────────────────────────────────────
    def eligible_workers(self, envelope: TaskEnvelope,
                         now: Optional[datetime] = None) -> List[WorkerRegistration]:
        now = now or _utcnow()
        req = _extract_requirements(envelope)
        out = []
        for w in self._workers.values():
            if w.status != "ACTIVE":
                continue
            if w.is_expired(now=now):
                continue
            if not capability_satisfied(w, req):
                continue
            out.append(w)
        return out

    def score(self, worker: WorkerRegistration, envelope: TaskEnvelope,
              now: Optional[datetime] = None) -> Optional[float]:
        """Score in [0,1], or None if the worker is not eligible."""
        now = now or _utcnow()
        if worker.status != "ACTIVE" or worker.is_expired(now=now):
            return None
        req = _extract_requirements(envelope)
        if not capability_satisfied(worker, req):
            return None
        s = (self.weights["capability"] * capability_score(worker, req)
             + self.weights["freshness"] * freshness_score(worker, now=now))
        return round(s, 6)

    def rank(self, envelope: TaskEnvelope,
             now: Optional[datetime] = None) -> List[Tuple[WorkerRegistration, float]]:
        """All eligible workers, best first (deterministic tie-break on worker_id)."""
        now = now or _utcnow()
        scored = [(w, self.score(w, envelope, now=now)) for w in self.eligible_workers(envelope, now=now)]
        scored = [(w, s) for w, s in scored if s is not None]
        scored.sort(key=lambda pair: (-pair[1], pair[0].worker_id))
        return scored

    def pick_worker(self, envelope: TaskEnvelope,
                    now: Optional[datetime] = None) -> Optional[WorkerRegistration]:
        """Best eligible worker, or None when nobody qualifies."""
        ranked = self.rank(envelope, now=now)
        return ranked[0][0] if ranked else None
