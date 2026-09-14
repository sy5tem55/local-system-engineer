#!/usr/bin/env python3
"""
goethe_orchestrator.orchestrator — ADR-ORCH-001 Phase 3: local orchestrator
===========================================================================
Owns worker registration, heartbeat monitoring, and task dispatch. The
ledger (tasks.db) remains the task-of-record; this class is the dispatch
layer between the envelope contract and the execution backend.

Backends (GOETHE_EXECUTION_BACKEND valve, ADR rollback surface):
  "ray"    — dispatch through the Ray cluster (execution substrate).
             Lazy-imports ray so this module imports cleanly without a
             cluster. The head must already be up (Phase 2 substrate).
  "local"  — in-process fallback: handlers run in a worker thread on
             node4090. This is the rollback path: flipping
             GOETHE_EXECUTION_BACKEND=local takes Ray out of the loop
             without touching the contracts or the scheduler.

Envelope payload convention (v1):
  {"handler": "<registered handler name>", "args": {...}}
The payload is otherwise opaque to the orchestrator — it is serialized
to the backend verbatim. The envelope id is injected into args as
"__envelope_id__" so handlers can report back.

NOT in scope here (later phases): event logging (Phase 5, step 8),
MCP integration (Phase 4 wiring, step 7), cluster membership (step 10).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .contracts import TaskEnvelope, WorkerRegistration
from .scheduler import WeightedScheduler

_log = logging.getLogger("goethe_orchestrator")

Handler = Callable[..., Any]


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from goethe_orchestrator.event_log import EventLog


class OrchestratorError(Exception):
    """Base error for orchestrator failures."""


class NoEligibleWorkerError(OrchestratorError):
    """No registered worker matches the envelope's requirements."""


@dataclass
class DispatchResult:
    envelope_id: str
    worker_id: str
    backend: str
    status: str  # "DISPATCHED" | "COMPLETED" | "FAILED"
    ref: Any = None  # ray ObjectRef (ray backend) or future (local)
    result: Any = None  # populated on COMPLETED (local backend)
    error: str = ""


class LocalOrchestrator:
    """Dispatch layer: envelopes in, backend execution out.

    Args:
        scheduler: weighted-v1 scheduler (default: fresh instance).
        backend: "ray" | "local" (GOETHE_EXECUTION_BACKEND value).
        ray_address: for the ray backend, address of a running cluster
            (None → ray.init() local fallback; the Phase-2 substrate
            should already be running, so pass the head address).
        max_workers: thread pool size for the local backend.
    """

    def __init__(
        self,
        scheduler: Optional[WeightedScheduler] = None,
        backend: str = "local",
        ray_address: Optional[str] = None,
        max_workers: int = 4,
        event_log: Optional["EventLog"] = None,
    ) -> None:
        if backend not in ("ray", "local"):
            raise ValueError(f"unknown backend: {backend!r} (want 'ray' | 'local')")
        self.scheduler = scheduler or WeightedScheduler()
        self.backend = backend
        self.ray_address = ray_address
        self._workers: Dict[str, WorkerRegistration] = {}
        self._envelopes: Dict[str, TaskEnvelope] = {}
        self._handlers: Dict[str, Handler] = {}
        self._event_log = event_log
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="goethe-orch"
        )
        self._lock = threading.RLock()

    def _emit(self, envelope, to_status, worker_id=None, detail=""):
        """Journal a status transition (no-op when no event_log is wired).
        from_status is read BEFORE the caller mutates envelope.status."""
        if self._event_log is not None:
            self._event_log.record(
                envelope.id, to_status, worker_id=worker_id,
                from_status=envelope.status, backend=self.backend,
                detail=detail)

    # ── worker lifecycle ──────────────────────────────────────────────────
    def register_worker(self, worker: WorkerRegistration) -> None:
        with self._lock:
            self._workers[worker.worker_id] = worker
            self.scheduler.register(worker)

    def unregister_worker(self, worker_id: str) -> None:
        with self._lock:
            self._workers.pop(worker_id, None)
            self.scheduler.unregister(worker_id)

    def heartbeat(self, worker_id: str) -> bool:
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.heartbeat()
            self.scheduler.heartbeat(worker_id)
            return True

    def tick(self, now=None) -> List[str]:
        """Expire stale workers. Returns the worker_ids that flipped."""
        with self._lock:
            return self.scheduler.tick(now)

    def active_workers(self) -> List[WorkerRegistration]:
        with self._lock:
            return [
                w for w in self._workers.values()
                if w.status == "ACTIVE" and not w.is_expired()
            ]

    # ── handlers (local backend) ──────────────────────────────────────────
    def register_handler(self, name: str, fn: Handler) -> None:
        with self._lock:
            self._handlers[name] = fn

    # ── dispatch ──────────────────────────────────────────────────────────
    def dispatch(self, envelope: TaskEnvelope) -> DispatchResult:
        """Validate, schedule, and hand the envelope to the backend.

        Status transitions: PENDING → DISPATCHED → COMPLETED/FAILED.
        Raises NoEligibleWorkerError when no worker matches — the
        envelope stays PENDING so a later dispatch can retry.
        """
        if envelope.status not in ("PENDING", "FAILED"):
            raise OrchestratorError(
                f"envelope {envelope.id} is {envelope.status}; "
                "only PENDING/FAILED envelopes dispatch"
            )
        with self._lock:
            worker = self.scheduler.pick_worker(envelope)
            if worker is None:
                raise NoEligibleWorkerError(
                    f"no eligible worker for envelope {envelope.id} "
                    f"(requires={envelope.payload.get('requires')!r}, "
                    f"registered={sorted(self._workers)})"
                )
            self._envelopes[envelope.id] = envelope
            self._emit(envelope, "DISPATCHED", worker.worker_id)
            envelope.status = "DISPATCHED"

        if self.backend == "ray":
            ref = self._dispatch_ray(envelope, worker)
        else:
            ref = self._dispatch_local(envelope, worker)

        return DispatchResult(
            envelope_id=envelope.id,
            worker_id=worker.worker_id,
            backend=self.backend,
            status="DISPATCHED",
            ref=ref,
        )

    def _dispatch_local(self, envelope: TaskEnvelope, worker: WorkerRegistration):
        with self._lock:
            handler = self._handlers.get(envelope.payload.get("handler", ""))
        if handler is None:
            self._emit(envelope, "FAILED", worker.worker_id,
                       detail=f"no handler for {envelope.payload.get('handler')!r}")
            envelope.status = "FAILED"
            raise OrchestratorError(
                f"no handler registered for {envelope.payload.get('handler')!r} "
                f"(envelope {envelope.id})"
            )
        args = dict(envelope.payload.get("args", {}))
        args["__envelope_id__"] = envelope.id

        def _run():
            try:
                result = handler(**args)
                self._emit(envelope, "COMPLETED", worker.worker_id)
                envelope.status = "COMPLETED"
                return ("ok", result)
            except Exception as exc:  # noqa: BLE001 — handler errors are data
                self._emit(envelope, "FAILED", worker.worker_id,
                           detail=f"{type(exc).__name__}: {exc}")
                envelope.status = "FAILED"
                return ("err", f"{type(exc).__name__}: {exc}")

        return self._pool.submit(_run)

    def _dispatch_ray(self, envelope: TaskEnvelope, worker: WorkerRegistration):
        import ray  # lazy: ray is a 78MB install; do not import at module load

        if self.ray_address:
            ray.init(address=self.ray_address, ignore_reinit_error=True)
        else:
            ray.init(ignore_reinit_error=True)

        @ray.remote
        def _remote_handler(handler_name, args, envelope_id):
            # Worker-side dispatch: on the Ray side the handler registry
            # is per-node; Phase 4 (cluster) ships handler bundles via the
            # runtime env. v1: the remote task executes the payload
            # through the registered Goethe worker entrypoint.
            from goethe_orchestrator.worker_entry import run_envelope
            return run_envelope(handler_name, args, envelope_id)

        args = dict(envelope.payload.get("args", {}))
        ref = _remote_handler.remote(
            envelope.payload.get("handler", ""), args, envelope.id
        )
        return ref

    # ── result collection (local backend) ─────────────────────────────────
    def collect(self, dispatch: DispatchResult, timeout: Optional[float] = None) -> DispatchResult:
        """Block on a local-backend dispatch and update its status."""
        if dispatch.backend != "local" or dispatch.ref is None:
            return dispatch
        kind, value = dispatch.ref.result(timeout=timeout)
        if kind == "ok":
            dispatch.status = "COMPLETED"
            dispatch.result = value
        else:
            dispatch.status = "FAILED"
            dispatch.error = value
        return dispatch
