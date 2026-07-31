#!/usr/bin/env python3
"""Typed TRAUM control plane used by the Goethe Console.

This module is intentionally *not* a web shell.  Browser input selects from
fixed operations and bounded numeric settings; executable paths, filesystem
paths, environment variables and command-line fragments are never accepted.
The controller owns every process it can cancel and invokes fixed argv arrays
with ``shell=False``.

The durable lifecycle/proposal model lives in :mod:`traum_state`.  This file
only orchestrates those typed state transitions, child processes, bounded
redacted logs, and the read-only timer probe.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import traum_state
except Exception as exc:  # pragma: no cover - exercised through unavailable()
    traum_state = None
    _STATE_IMPORT_ERROR = exc
else:
    _STATE_IMPORT_ERROR = None

try:
    from redact import redact_sensitive_text
except Exception as exc:  # pragma: no cover - partial deployment
    redact_sensitive_text = None
    _REDACT_IMPORT_ERROR = exc
else:
    _REDACT_IMPORT_ERROR = None


DREAM_PASSES = (
    "dedup",
    "stale-contradiction",
    "error-cluster",
    "patterns",
    "insights",
)
CONTROLLER_OPERATIONS = DREAM_PASSES + ("digest",)
RUN_PROFILES = ("standard", "single-pass")
RETRYABLE_ATTEMPT_STATES = frozenset({"FAILED", "BLOCKED"})
TERMINAL_RUN_STATES = frozenset(
    {"SUCCEEDED", "DEGRADED", "FAILED", "CANCELLED", "BLOCKED"}
)
ACTIVE_RUN_STATES = frozenset({"QUEUED", "RUNNING"})
DECISIONS = frozenset({"approve", "reject", "defer"})

_HISTORICAL_V1_EVALUATION = {
    "evaluation_id": "eval-report-traum-1",
    "executed_on": "2026-07-12",
    "protocol_verdict": "LOSS",
    "causal_interpretation": "INCONCLUSIVE",
    "artifact": "eval-report-traum-1.md",
    "scope": "historical v1; not evidence from the isolated v2 registry",
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_LOG_BYTES = 512 * 1024
_MAX_REASON_CHARS = 1000
_SWEEP_LIMIT = 200
_PROPOSAL_FALLBACK_SCAN_LIMIT = 100000


class TraumControlError(RuntimeError):
    """Expected API error with an HTTP-friendly status code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _strict_object(payload: Any, allowed: set[str]) -> dict:
    if not isinstance(payload, dict):
        raise TraumControlError("request body must be a JSON object")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise TraumControlError(
            "unsupported field(s): " + ", ".join(unknown), status=400
        )
    return payload


def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraumControlError(f"{name} must be an integer")
    if not low <= value <= high:
        raise TraumControlError(f"{name} must be between {low} and {high}")
    return value


def _bounded_number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraumControlError(f"{name} must be a number")
    value = float(value)
    if not low <= value <= high:
        raise TraumControlError(f"{name} must be between {low:g} and {high:g}")
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise TraumControlError(f"invalid {label}", status=400)
    return value


def _record_id(value: Any, field: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get(field):
        return str(value[field])
    raise TraumControlError(f"state store did not return {field}", status=500)


class TraumController:
    """Server-owned orchestration for the TRAUM GUI.

    One controller instance belongs to one long-lived gateway process.  It
    allows at most one active run/retry at a time.  Durable state survives a
    gateway restart; process ownership deliberately does not, so a restarted
    gateway cannot kill a PID it did not itself create.
    """

    def __init__(
        self,
        *,
        dream_dir: str | None = None,
        repo_root: str | None = None,
        python_bin: str | None = None,
        state: Any = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        command_runner: Callable[..., Any] = subprocess.run,
        apply_module: Any = None,
        auto_revalidate: bool = True,
    ) -> None:
        if traum_state is None and state is None:
            raise TraumControlError(
                f"TRAUM state module unavailable: {_STATE_IMPORT_ERROR}", status=503
            )
        if redact_sensitive_text is None:
            # A missing redactor disables the control plane.  Returning raw
            # child output would turn a partial deployment into a secret leak.
            raise TraumControlError(
                f"TRAUM log redactor unavailable: {_REDACT_IMPORT_ERROR}",
                status=503,
            )

        self.dream_dir = os.path.abspath(
            dream_dir
            or os.environ.get("GOETHE_DREAM_DIR")
            or "/opt/local-se/dreams"
        )
        self.repo_root = os.path.abspath(
            repo_root or os.path.join(_HERE, os.pardir)
        )
        self.python_bin = (
            python_bin
            or os.environ.get("GOETHE_DREAM_PYTHON")
            or sys.executable
        )
        state_path = (
            traum_state.default_db_path(self.dream_dir)
            if traum_state is not None
            else os.path.join(self.dream_dir, "traum-state.db")
        )
        self.state = state or traum_state.TraumState(state_path)
        self._popen = popen_factory
        self._run_command = command_runner
        self._apply_module = apply_module

        # These paths are server-owned constants.  They are never derived
        # from a request body.
        self._runner_path = os.path.join(self.repo_root, "tools", "dream_runner.py")
        self._digest_path = os.path.join(self.repo_root, "tools", "dream_digest.py")
        self._log_root = os.path.join(self.dream_dir, ".control", "logs")

        self._lock = threading.RLock()
        self._decision_lock = threading.Lock()
        self._workers: dict[str, threading.Thread] = {}
        self._processes: dict[str, Any] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._owned_attempt_ids: dict[str, set[str]] = {}
        self._worker_created_run: dict[str, bool] = {}
        self._legacy_warning: str | None = None
        self._recovery_warning: str | None = None
        self._last_sweep: dict | None = None
        self._sweep_thread: threading.Thread | None = None
        try:
            self.state.reconcile_legacy_days(self.dream_dir)
        except Exception as exc:
            # Migration is metadata-only and resumable on the next gateway
            # start.  New canonical operations remain available meanwhile.
            self._legacy_warning = (
                f"legacy reconciliation incomplete: {type(exc).__name__}: {exc}"
            )
        self._recover_orphaned_work()
        self._auto_revalidate = bool(auto_revalidate) and (
            os.environ.get("GOETHE_TRAUM_AUTO_REVALIDATE", "on").strip().lower()
            not in {"off", "0", "false", "no"}
        )
        if self._auto_revalidate:
            # Legacy-imported and newly published proposals have never been
            # validated against the live corpus.  Sweeping at start keeps
            # unapplicable items out of the human inbox without adding an
            # Elasticsearch round trip to any read request.
            self._schedule_sweep()

    # ------------------------------------------------------------------
    # State/status reads
    # ------------------------------------------------------------------

    @classmethod
    def unavailable(cls, exc: Exception) -> dict:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "capabilities": {
                "typed_operations_only": True,
                "shell_commands": False,
                "timer_mutation": False,
                "permissions_plane": False,
            },
        }

    @staticmethod
    def _parse_run_timestamp(value: str | None) -> "_dt.datetime | None":
        """Runs table timestamps are UTC ISO-8601 with a trailing 'Z'
        (traum_state._utc_iso), which datetime.fromisoformat only accepts
        without translation on Python 3.11+. Normalize defensively rather
        than assume the interpreter version, matching the same Z-handling
        traum_state.py's own _as_utc already does for the identical
        format."""
        if not value:
            return None
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return parsed

    def _health_verdict(self) -> dict:
        """R3 (docs/TRAUM-R1-R3-PLAN.md, Step 3.1). status() used to
        return counts only -- no notion of "last successful cycle" -- so
        an operator glancing at the panel could not tell quiet success
        from the loop having been dead for days. This is read-only,
        derived entirely from `runs`; no schema change.

        Excludes source == 'legacy-import' throughout, which is the
        single most important and easiest-to-miss detail here: all 9
        legacy-backfill runs are recorded SUCCEEDED (confirmed live,
        2026-07-31 -- see docs/TRAUM-ANALYSIS-2026-07-31.md) and would
        otherwise report the loop healthy forever regardless of whether a
        single real cycle has ever completed since.
        """
        rows = self.state.list_runs(include_archived=True, limit=5000)
        non_legacy = [r for r in rows if str(r.get("source", "")) != "legacy-import"]
        non_legacy.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

        last_success_at: str | None = None
        for row in non_legacy:
            if str(row.get("state", "")).upper() == "SUCCEEDED":
                last_success_at = row.get("finished_at") or row.get("created_at")
                break

        hours_since_success: float | None = None
        parsed_success = self._parse_run_timestamp(last_success_at)
        if parsed_success is not None:
            now = _dt.datetime.now(_dt.timezone.utc)
            hours_since_success = max(0.0, (now - parsed_success).total_seconds() / 3600.0)

        # How many of the most recent non-legacy runs, walking back from
        # newest, failed to succeed before the first success is hit.
        # QUEUED/RUNNING rows are still unresolved -- they count as
        # neither a success nor a failure, so they're skipped rather than
        # breaking or extending the streak.
        consecutive_unsuccessful = 0
        for row in non_legacy:
            state = str(row.get("state", "")).upper()
            if state in ("QUEUED", "RUNNING"):
                continue
            if state == "SUCCEEDED":
                break
            consecutive_unsuccessful += 1

        if last_success_at is None:
            verdict = "critical"
            reason = "the learning loop has never completed a real (non-legacy) cycle"
        elif hours_since_success is not None and hours_since_success > 48:
            verdict = "critical"
            reason = f"last success was {hours_since_success:.0f}h ago (>48h)"
        elif consecutive_unsuccessful >= 3:
            verdict = "critical"
            reason = (
                f"{consecutive_unsuccessful} run(s) since the last success have not "
                "succeeded"
            )
        elif hours_since_success is not None and hours_since_success > 24:
            verdict = "warn"
            reason = f"last success was {hours_since_success:.0f}h ago (>24h)"
        else:
            verdict = "ok"
            reason = (
                f"last success {hours_since_success:.1f}h ago"
                if hours_since_success is not None else "healthy"
            )

        return {
            "last_success_at": last_success_at,
            "hours_since_success": (
                round(hours_since_success, 1) if hours_since_success is not None else None
            ),
            "consecutive_unsuccessful_runs": consecutive_unsuccessful,
            "verdict": verdict,
            "reason": reason,
        }

    def status(self) -> dict:
        recovery = self._recover_orphaned_work()
        run_rows = self.state.list_runs(include_archived=False, limit=201)
        run_inventory_truncated = len(run_rows) > 200
        runs = run_rows[:200]
        run_counts: dict[str, int] = {}
        for row in runs:
            self._annotate_run_ownership(row)
            key = str(row.get("state", "UNKNOWN")).upper()
            run_counts[key] = run_counts.get(key, 0) + 1
        proposal_summary = self._proposal_summary(_dt.date.today())
        proposal_counts = proposal_summary["counts"]
        due_deferred = proposal_summary["due_deferred"]
        future_deferred = proposal_summary["future_deferred"]
        with self._lock:
            owned_active = [
                run_id for run_id, worker in self._workers.items()
                if worker.is_alive()
            ]
        unowned_active = [
            str(row.get("run_id")) for row in runs
            if row.get("control_ownership") == "unowned-active-state"
        ]
        return {
            "available": True,
            "active_controller_run_id": owned_active[0] if owned_active else None,
            "unowned_active_run_ids": unowned_active[:20],
            "unowned_active_run_count": len(unowned_active),
            "run_inventory_truncated": run_inventory_truncated,
            "run_counts": run_counts,
            "proposal_counts": proposal_counts,
            "human_gate_count": (
                proposal_summary["human_gate_count"]
            ),
            "human_gate_count_exact": proposal_summary["counts_exact"],
            "pending_count": proposal_counts.get("PENDING", 0),
            "due_deferred_count": due_deferred,
            "future_deferred_count": future_deferred,
            "reconcile_count": proposal_counts.get("APPLY_FAILED", 0),
            "timer": self.timer_status(),
            "health": self._health_verdict(),
            "evaluation": self.evaluation_status(),
            "invariant_sweep": self._last_sweep or {
                "swept_at": None,
                "checked": 0,
                "auto_rejected": 0,
                "still_actionable": 0,
                "skipped": 0,
                "blocked": False,
                "reason": "no sweep has run in this gateway process",
                "applies_anything": False,
            },
            "recovery": recovery,
            "warnings": [
                warning for warning in
                (self._legacy_warning, self._recovery_warning) if warning
            ],
            "capabilities": {
                "typed_operations_only": True,
                "shell_commands": False,
                "timer_mutation": False,
                "permissions_plane": False,
                "cancel_owned_process_only": True,
            },
        }

    def list_runs(self, *, include_archived: bool = False, limit: int = 50) -> dict:
        self._recover_orphaned_work()
        limit = _bounded_int(limit, "limit", 1, 200)
        rows = self.state.list_runs(
            include_archived=bool(include_archived), limit=limit
        )
        for row in rows:
            run_id = row.get("run_id")
            if run_id:
                row["attempts"] = self.state.list_attempts(
                    run_id=str(run_id), limit=100
                )
                self._annotate_run_ownership(row)
        return {"runs": rows, "include_archived": bool(include_archived)}

    def get_run(self, run_id: str) -> dict:
        run_id = _safe_id(run_id, "run id")
        self._recover_orphaned_work()
        row = self.state.get_run(run_id)
        if not row:
            raise TraumControlError(f"run {run_id!r} not found", status=404)
        row["attempts"] = self.state.list_attempts(run_id=run_id, limit=200)
        self._annotate_run_ownership(row)
        return row

    def _annotate_run_ownership(self, row: dict) -> None:
        """Describe controller ownership without guessing from a stored PID.

        Durable RUNNING/QUEUED state can outlive the gateway process that
        created it.  After a restart we report that uncertainty explicitly,
        but never attach a cancel action to an unowned process.
        """
        run_id = str(row.get("run_id") or "")
        with self._lock:
            worker = self._workers.get(run_id)
            owned = bool(worker and worker.is_alive())
        state = str(row.get("state") or "UNKNOWN").upper()
        row["controller_owned"] = owned
        if owned:
            row["control_ownership"] = "controller-owned"
            row["control_note"] = "owned by this gateway process"
        elif state in ACTIVE_RUN_STATES:
            row["control_ownership"] = "unowned-active-state"
            row["control_note"] = (
                "durable active state is not owned by this gateway; "
                "process status is unknown and no PID action is available"
            )
        else:
            row["control_ownership"] = "inactive"

    def _proposal_summary(self, today: _dt.date) -> dict:
        helper = getattr(self.state, "proposal_queue_summary", None)
        if callable(helper):
            summary = helper(due_on=today.isoformat())
            return {
                "counts": dict(summary.get("counts") or {}),
                "due_deferred": int(summary.get("due_deferred", 0) or 0),
                "future_deferred": int(summary.get("future_deferred", 0) or 0),
                "human_gate_count": int(summary.get("human_gate_count", 0) or 0),
                "counts_exact": True,
            }

        # Compatibility with a not-yet-migrated state module.  The extra row
        # is a truncation probe; if it is present, every count is explicitly a
        # lower bound and the GUI must not claim that the human gate is clear.
        rows = self.state.list_proposals(
            state=None, limit=_PROPOSAL_FALLBACK_SCAN_LIMIT + 1
        )
        truncated = len(rows) > _PROPOSAL_FALLBACK_SCAN_LIMIT
        rows = rows[:_PROPOSAL_FALLBACK_SCAN_LIMIT]
        counts: dict[str, int] = {}
        due_deferred = 0
        future_deferred = 0
        for row in rows:
            key = str(row.get("state", "UNKNOWN")).upper()
            counts[key] = counts.get(key, 0) + 1
            if key != "DEFERRED":
                continue
            try:
                is_due = _dt.date.fromisoformat(
                    str(row.get("defer_until"))) <= today
            except (TypeError, ValueError):
                is_due = True
            if is_due:
                due_deferred += 1
            else:
                future_deferred += 1
        return {
            "counts": counts,
            "due_deferred": due_deferred,
            "future_deferred": future_deferred,
            "human_gate_count": (
                counts.get("PENDING", 0)
                + due_deferred
                + counts.get("APPLY_FAILED", 0)
            ),
            "counts_exact": not truncated,
        }

    def list_proposals(self, *, state: str | None = None, limit: int = 200,
                       actionable_only: bool = False, offset: int = 0) -> dict:
        limit = _bounded_int(limit, "limit", 1, 500)
        offset = _bounded_int(offset, "offset", 0, 1000000)
        normalized = state.upper() if state else None
        requested_states = {
            item.strip() for item in (normalized or "").split(",") if item.strip()
        }
        allowed_states = {
            "PENDING", "DEFERRED", "APPLYING", "APPLIED", "REJECTED",
            "SYSTEM_REJECTED", "SUPERSEDED", "EXPIRED", "APPLY_FAILED",
        }
        if requested_states - allowed_states:
            raise TraumControlError("unknown proposal state")

        today = _dt.date.today()
        helper = getattr(self.state, "proposal_queue", None)
        if callable(helper):
            result = helper(
                states=normalized,
                actionable_only=bool(actionable_only),
                due_on=today.isoformat(),
                limit=limit,
                offset=offset,
            )
            rows = list(result.get("proposals") or [])
            total_visible = int(result.get("total_matching", len(rows)) or 0)
            total_before = int(
                result.get("total_before_actionability", total_visible) or 0
            )
            hidden = int(result.get("hidden_future_deferred", 0) or 0)
            return {
                "proposals": rows,
                "actionable_only": bool(actionable_only),
                "hidden_future_deferred": hidden,
                "returned_count": len(rows),
                "total_visible": total_visible,
                "total_matching": total_before,
                "limit": limit,
                "offset": offset,
                "truncated": bool(result.get("truncated", False)),
                "inventory_truncated": False,
                "counts_exact": True,
            }

        # Compatibility fallback for older state modules.  Fetch enough rows
        # to avoid ordinary starvation, but advertise a lower bound if the
        # explicit safety ceiling is reached.
        fetch_limit = max(_PROPOSAL_FALLBACK_SCAN_LIMIT, offset + limit)
        fetch_limit = min(fetch_limit, _PROPOSAL_FALLBACK_SCAN_LIMIT) + 1
        rows = self.state.list_proposals(state=normalized, limit=fetch_limit)
        inventory_truncated = len(rows) > _PROPOSAL_FALLBACK_SCAN_LIMIT
        rows = rows[:_PROPOSAL_FALLBACK_SCAN_LIMIT]
        total_before = len(rows)
        hidden = 0
        if actionable_only:
            visible = []
            for row in rows:
                if str(row.get("state", "")).upper() != "DEFERRED":
                    visible.append(row)
                    continue
                try:
                    future = _dt.date.fromisoformat(
                        str(row.get("defer_until"))) > today
                except ValueError:
                    future = False
                if future:
                    hidden += 1
                else:
                    visible.append(row)
            rows = visible
        total_visible = len(rows)
        page = rows[offset:offset + limit]
        return {
            "proposals": page,
            "actionable_only": bool(actionable_only),
            "hidden_future_deferred": hidden,
            "returned_count": len(page),
            "total_visible": total_visible,
            "total_matching": total_before,
            "limit": limit,
            "offset": offset,
            "truncated": (
                inventory_truncated or offset + len(page) < total_visible
            ),
            "inventory_truncated": inventory_truncated,
            "counts_exact": not inventory_truncated,
        }

    # ------------------------------------------------------------------
    # Fixed process orchestration
    # ------------------------------------------------------------------

    def start_run(self, payload: dict) -> dict:
        payload = _strict_object(
            payload, {"profile", "pass", "sessions", "wall_clock_minutes"}
        )
        profile = payload.get("profile", "standard")
        if profile not in RUN_PROFILES:
            raise TraumControlError(
                "profile must be 'standard' or 'single-pass'"
            )

        pass_name = payload.get("pass")
        if profile == "single-pass":
            if pass_name not in DREAM_PASSES:
                raise TraumControlError(
                    "single-pass profile requires one fixed TRAUM pass"
                )
            passes = [pass_name]
        else:
            if pass_name is not None:
                raise TraumControlError("standard profile does not accept pass")
            passes = list(DREAM_PASSES)

        sessions = _bounded_int(payload.get("sessions", 50), "sessions", 1, 100)
        wall_clock = _bounded_number(
            payload.get("wall_clock_minutes", 45),
            "wall_clock_minutes", 5, 45,
        )
        config = {
            "sessions": sessions,
            "operation_wall_clock_minutes": wall_clock,
            "guards": "required",
            "dry_run": False,
        }
        requested_passes = passes + (["digest"] if profile == "standard" else [])
        with self._lock:
            self._assert_idle()
            created = self.state.create_run(
                profile=profile,
                requested_passes=requested_passes,
                config=config,
                source="gui",
            )
            run_id = _record_id(created, "run_id")
            try:
                self._launch_worker(
                    run_id, passes, config=config, retry_of={}, created_run=True
                )
            except Exception as exc:
                if hasattr(self.state, "finalize_run"):
                    self.state.finalize_run(
                        run_id, "FAILED",
                        summary={"controller_error": f"worker start failed: {exc}"},
                        actor="gui-controller",
                    )
                raise
        return self.get_run(run_id)

    def retry(self, run_id: str, payload: dict) -> dict:
        run_id = _safe_id(run_id, "run id")
        payload = _strict_object(payload, {"attempt_id"})
        attempt_id = _safe_id(payload.get("attempt_id"), "attempt id")
        attempt = self.state.get_attempt(attempt_id)
        if not attempt or str(attempt.get("run_id")) != run_id:
            raise TraumControlError("attempt not found for this run", status=404)
        attempt_state = str(attempt.get("state", "")).upper()
        if attempt_state not in RETRYABLE_ATTEMPT_STATES:
            raise TraumControlError(
                "only FAILED or BLOCKED attempts can be retried", status=409
            )
        pass_name = str(attempt.get("pass_name", ""))
        if pass_name not in CONTROLLER_OPERATIONS:
            raise TraumControlError("this attempt is not a retryable TRAUM pass", status=409)
        run = self.state.get_run(run_id)
        if not run:
            raise TraumControlError("run not found", status=404)
        if run.get("cancel_requested") or str(run.get("state", "")).upper() == "CANCELLED":
            raise TraumControlError(
                "cancelled runs cannot be retried; start a new run", status=409
            )
        if run.get("archived_at") or run.get("archived"):
            raise TraumControlError("archived runs cannot be retried", status=409)

        previous_config = attempt.get("config") or run.get("config") or {}
        config = {
            "sessions": int(previous_config.get("sessions", 50)),
            "operation_wall_clock_minutes": float(
                previous_config.get(
                    "operation_wall_clock_minutes",
                    previous_config.get("wall_clock_minutes", 45),
                )
            ),
            "guards": "required",
            "dry_run": False,
        }
        config["sessions"] = max(1, min(config["sessions"], 100))
        config["operation_wall_clock_minutes"] = max(
            5.0, min(config["operation_wall_clock_minutes"], 45.0)
        )
        with self._lock:
            self._assert_idle()
            self._launch_worker(
                run_id, [pass_name], config=config,
                retry_of={pass_name: attempt_id}, created_run=False,
            )
        return self.get_run(run_id)

    def cancel(self, run_id: str, payload: dict) -> dict:
        run_id = _safe_id(run_id, "run id")
        _strict_object(payload, set())
        with self._lock:
            worker = self._workers.get(run_id)
            event = self._cancel_events.get(run_id)
            proc = self._processes.get(run_id)
            if worker is None or event is None:
                raise TraumControlError(
                    "run is not owned by this controller process", status=409
                )
            self.state.request_cancel(run_id, actor="gui:local-operator")
            event.set()
            # The PID comes only from the Popen object stored by this
            # controller.  No PID or process name is accepted from the API.
            if proc is not None and proc.poll() is None:
                proc.terminate()
                self._schedule_kill_escalation(run_id, proc)
        return {"run_id": run_id, "cancel_requested": True}

    def _assert_idle(self) -> None:
        with self._lock:
            active = [rid for rid, thread in self._workers.items() if thread.is_alive()]
            if active:
                raise TraumControlError(
                    f"TRAUM operation already active: {active[0]}", status=409
                )
        recovery = self._recover_orphaned_work()
        unowned = (recovery or {}).get("unowned_active") or []
        if unowned:
            first = unowned[0]
            raise TraumControlError(
                "another canonical TRAUM run is active but is not owned by "
                f"this gateway: {first.get('run_id')} "
                f"({first.get('run_state')}); wait for its deadline/recovery",
                status=409,
            )

    def _recover_orphaned_work(self) -> dict | None:
        """Fence expired durable work without ever acting on a stored PID."""
        helper = getattr(self.state, "recover_orphaned_controller_work", None)
        if not callable(helper):
            return None
        with self._lock:
            owned = tuple(
                run_id for run_id, worker in self._workers.items()
                if worker.is_alive()
            )
        try:
            result = helper(owned_run_ids=owned)
        except Exception as exc:
            self._recovery_warning = (
                "controller lease reconciliation incomplete: "
                f"{type(exc).__name__}: {exc}"
            )
            return None
        self._recovery_warning = None
        return result

    def _launch_worker(
        self,
        run_id: str,
        passes: list[str],
        *,
        config: dict,
        retry_of: dict[str, str],
        created_run: bool = False,
    ) -> None:
        event = threading.Event()
        thread = threading.Thread(
            target=self._execute_run,
            name=f"traum-{run_id[:24]}",
            args=(run_id, tuple(passes), dict(config), dict(retry_of), event),
            daemon=True,
        )
        with self._lock:
            if any(t.is_alive() for t in self._workers.values()):
                raise TraumControlError("TRAUM operation already active", status=409)
            self._workers[run_id] = thread
            self._cancel_events[run_id] = event
            self._owned_attempt_ids[run_id] = set()
            self._worker_created_run[run_id] = bool(created_run)
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._workers.pop(run_id, None)
                self._cancel_events.pop(run_id, None)
                self._owned_attempt_ids.pop(run_id, None)
                self._worker_created_run.pop(run_id, None)
            raise

    def _execute_run(
        self,
        run_id: str,
        passes: tuple[str, ...],
        config: dict,
        retry_of: dict[str, str],
        cancel_event: threading.Event,
    ) -> None:
        deadline = time.monotonic() + (
            float(config.get("operation_wall_clock_minutes", 45)) * 60
        )
        try:
            for index, pass_name in enumerate(passes):
                if cancel_event.is_set() or self.state.is_cancel_requested(run_id):
                    break
                if time.monotonic() >= deadline:
                    self._finish_unstarted(
                        run_id, passes[index:], "BLOCKED",
                        "whole-operation wall-clock budget exhausted",
                    )
                    break
                if pass_name == "digest":
                    self._execute_digest(
                        run_id, cancel_event, retry_of=retry_of.get(pass_name),
                        deadline=deadline,
                    )
                else:
                    outcome = self._execute_pass(
                        run_id,
                        pass_name,
                        config=config,
                        retry_of=retry_of.get(pass_name),
                        cancel_event=cancel_event,
                        deadline=deadline,
                    )
                    if outcome == "BLOCKED" and time.monotonic() >= deadline:
                        self._finish_unstarted(
                            run_id, passes[index + 1:] + (("digest",) if len(passes) > 1 else ()),
                            "BLOCKED", "whole-operation wall-clock budget exhausted",
                        )
                        break
            else:
                if not cancel_event.is_set() and len(passes) > 1:
                    if time.monotonic() < deadline:
                        self._execute_digest(run_id, cancel_event, deadline=deadline)
                    else:
                        self._finish_unstarted(
                            run_id, ("digest",), "BLOCKED",
                            "whole-operation wall-clock budget exhausted",
                        )
        except Exception as exc:
            self._terminalize_controller_failure(run_id, exc)
        finally:
            if cancel_event.is_set() or self.state.is_cancel_requested(run_id):
                self._finalize_cancelled_run(run_id)
            with self._lock:
                self._processes.pop(run_id, None)
                self._workers.pop(run_id, None)
                self._cancel_events.pop(run_id, None)
                self._owned_attempt_ids.pop(run_id, None)
                self._worker_created_run.pop(run_id, None)
            if self._auto_revalidate:
                # Newly published proposals are validated once here, so the
                # inbox the operator opens next holds only real decisions.
                self._schedule_sweep()

    def _execute_pass(
        self,
        run_id: str,
        pass_name: str,
        *,
        config: dict,
        retry_of: str | None,
        cancel_event: threading.Event,
        deadline: float,
    ) -> str:
        remaining_minutes = max(0.05, (deadline - time.monotonic()) / 60)
        attempt_config = dict(config)
        attempt_config["remaining_wall_clock_minutes"] = remaining_minutes
        attempt_id_hint = (
            traum_state.new_id("attempt") if traum_state is not None
            else f"att_{os.urandom(16).hex()}"
        )
        log_path = self._attempt_log_path(attempt_id_hint)
        attempt_rec = self.state.start_attempt(
            run_id=run_id,
            pass_name=pass_name,
            retry_of=retry_of,
            config=attempt_config,
            log_path=log_path,
            attempt_id=attempt_id_hint,
        )
        attempt_id = _record_id(attempt_rec, "attempt_id")
        with self._lock:
            self._owned_attempt_ids.setdefault(run_id, set()).add(attempt_id)
        # Normalize if an injected test/state implementation ignored the ID
        # hint while preserving its explicitly returned log path.
        log_path = attempt_rec.get("log_path") or self._attempt_log_path(attempt_id)
        # Persist the controller-owned log path after the ID exists.  State
        # implementations accepting log_path on start get it on subsequent
        # retries; finish artifacts retain it for all implementations.
        argv = [
            self.python_bin,
            self._runner_path,
            "--pass", pass_name,
            "--sessions", str(config["sessions"]),
            "--budget-max-wall-clock-min", str(remaining_minutes),
            "--state-db", self.state.db_path,
            "--run-id", run_id,
            "--attempt-id", attempt_id,
            "--run-profile", str(self.state.get_run(run_id).get("profile", "single-pass")),
            "--requested-passes", ",".join(
                self.state.get_run(run_id).get("requested_passes", [pass_name])
            ),
            "--run-source", "gui",
            "--no-dry-run",
        ]
        if retry_of:
            argv[2:2] = ["--retry-of", retry_of]
        result, timed_out = self._run_child(
            run_id, argv, log_path, cancel_event, deadline=deadline
        )
        text_tail = self._read_log_text(log_path, limit=80)["text"]
        if cancel_event.is_set():
            state = "CANCELLED"
            summary = "cancelled by local operator"
        elif timed_out:
            state = "BLOCKED"
            summary = "whole-operation wall-clock budget exhausted"
        elif result < 0:
            state = "CANCELLED"
            summary = "controller-owned process was terminated"
        elif result == 3:
            state = "BLOCKED"
            summary = "runner reported a typed blocked dependency/guard"
        elif result == 4:
            state = "CANCELLED"
            summary = "runner reported typed cancellation"
        elif result != 0:
            state = "FAILED"
            summary = f"runner exited {result}"
        elif "SKIPPING run" in text_tail:
            state = "BLOCKED"
            summary = "runner guard blocked this attempt"
        elif "null_result=" in text_tail:
            state = "NULL"
            summary = "pass completed with an explicit null result"
        else:
            state = "SUCCEEDED"
            summary = "pass completed"
        current = self.state.get_attempt(attempt_id)
        if current and str(current.get("state", "")).upper() in {"QUEUED", "RUNNING"}:
            self.state.finish_attempt(
                attempt_id,
                state,
                summary={"message": summary},
                artifacts={"log_path": log_path},
                exit_code=result,
            )
        else:
            # The runner is authoritative when it used the canonical IDs we
            # passed.  Reconcile to its durable terminal result instead of
            # reclassifying the same exit from log text.
            state = str((current or {}).get("state") or state).upper()
        return state

    def _execute_digest(self, run_id: str, cancel_event: threading.Event,
                        retry_of: str | None = None,
                        deadline: float | None = None) -> str:
        if cancel_event.is_set():
            return "CANCELLED"
        # Digest refresh is a first-class attempt so a successful set of
        # passes cannot hide a failed operator-summary refresh.
        attempt_id_hint = (
            traum_state.new_id("attempt") if traum_state is not None
            else f"att_{os.urandom(16).hex()}"
        )
        log_path = self._attempt_log_path(attempt_id_hint)
        rec = self.state.start_attempt(
            run_id=run_id, pass_name="digest", config={}, retry_of=retry_of,
            log_path=log_path, attempt_id=attempt_id_hint,
        )
        attempt_id = _record_id(rec, "attempt_id")
        with self._lock:
            self._owned_attempt_ids.setdefault(run_id, set()).add(attempt_id)
        log_path = rec.get("log_path") or self._attempt_log_path(attempt_id)
        result, timed_out = self._run_child(
            run_id,
            [self.python_bin, self._digest_path, "--no-dry-run"],
            log_path,
            cancel_event,
            deadline=deadline,
        )
        if cancel_event.is_set():
            state, summary = "CANCELLED", "digest refresh cancelled"
        elif timed_out:
            state, summary = "BLOCKED", "whole-operation wall-clock budget exhausted"
        elif result < 0:
            state, summary = "CANCELLED", "digest refresh terminated"
        elif result:
            state, summary = "FAILED", f"digest refresh exited {result}"
        else:
            state, summary = "SUCCEEDED", "operator digest refreshed"
        self.state.finish_attempt(
            attempt_id,
            state,
            summary={"message": summary},
            artifacts={"log_path": log_path},
            exit_code=result,
        )
        return state

    def _run_child(
        self,
        run_id: str,
        argv: list[str],
        log_path: str,
        cancel_event: threading.Event,
        deadline: float | None = None,
    ) -> tuple[int, bool]:
        os.makedirs(os.path.dirname(log_path), mode=0o700, exist_ok=True)
        try:
            os.chmod(os.path.dirname(log_path), 0o700)
        except OSError:
            pass
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(log_path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "a", encoding="utf-8") as log:
            log.write(
                f"[{_dt.datetime.now().astimezone().isoformat()}] "
                "TRAUM controller started fixed operation\n"
            )
            log.flush()
            try:
                proc = self._popen(
                    argv,
                    cwd=self.repo_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    shell=False,
                )
            except Exception as exc:
                log.write(
                    redact_sensitive_text(
                        f"controller spawn failed: {type(exc).__name__}: {exc}\n",
                        force=True,
                    )
                )
                return 127, False
            with self._lock:
                self._processes[run_id] = proc
            timed_out = threading.Event()
            watchdog = None
            if deadline is not None:
                def _deadline_stop():
                    if proc.poll() is None:
                        timed_out.set()
                        proc.terminate()
                        self._schedule_kill_escalation(run_id, proc)
                watchdog = threading.Timer(
                    max(0.0, deadline - time.monotonic()), _deadline_stop
                )
                watchdog.daemon = True
                watchdog.start()
            try:
                stream = getattr(proc, "stdout", None)
                if stream is not None:
                    for line in stream:
                        log.write(redact_sensitive_text(line, force=True))
                        log.flush()
                        if cancel_event.is_set() and proc.poll() is None:
                            proc.terminate()
                return int(proc.wait()), timed_out.is_set()
            finally:
                if watchdog is not None:
                    watchdog.cancel()
                with self._lock:
                    if self._processes.get(run_id) is proc:
                        self._processes.pop(run_id, None)

    def _finish_unstarted(
        self, run_id: str, pass_names, state: str, message: str
    ) -> None:
        existing = {
            row.get("pass_name") for row in
            self.state.list_attempts(run_id=run_id, limit=500)
        }
        for pass_name in pass_names:
            if pass_name in existing:
                continue
            rec = self.state.start_attempt(
                run_id=run_id, pass_name=pass_name,
                config={"not_started": True},
            )
            with self._lock:
                self._owned_attempt_ids.setdefault(run_id, set()).add(
                    rec["attempt_id"]
                )
            self.state.finish_attempt(
                rec["attempt_id"], state,
                summary={"message": message, "not_started": True},
            )

    def _finalize_cancelled_run(self, run_id: str) -> None:
        if hasattr(self.state, "finalize_cancelled_run"):
            self.state.finalize_cancelled_run(
                run_id, actor="gui:local-operator"
            )
            return
        run = self.state.get_run(run_id) or {}
        self._finish_unstarted(
            run_id, run.get("requested_passes", []), "CANCELLED",
            "not started because the run was cancelled",
        )

    def _schedule_kill_escalation(self, run_id: str, proc: Any) -> None:
        """Escalate TERM only for the exact still-owned Popen object."""
        def _escalate():
            for _ in range(20):
                if proc.poll() is not None:
                    return
                time.sleep(0.1)
            with self._lock:
                if self._processes.get(run_id) is proc and proc.poll() is None:
                    try:
                        proc.kill()
                    except (AttributeError, OSError):
                        pass
        threading.Thread(
            target=_escalate, name=f"traum-kill-{run_id[:16]}", daemon=True
        ).start()

    def _terminalize_controller_failure(self, run_id: str, exc: Exception) -> None:
        """Fail only work this controller instance durably created.

        A competing gateway can lose the atomic start_attempt race for a
        retry.  In that case this worker owns no canonical attempt and must
        not terminalize the winning gateway's active attempt or whole run.
        """
        with self._lock:
            proc = self._processes.get(run_id)
            owned_attempt_ids = set(self._owned_attempt_ids.get(run_id, set()))
            created_run = bool(self._worker_created_run.get(run_id, False))
            if proc is not None and proc.poll() is None:
                proc.terminate()
                self._schedule_kill_escalation(run_id, proc)
        message = f"controller failure: {type(exc).__name__}: {exc}"
        for attempt_id in sorted(owned_attempt_ids):
            attempt = self.state.get_attempt(attempt_id)
            if not attempt:
                continue
            if str(attempt.get("state", "")).upper() in {"QUEUED", "RUNNING"}:
                try:
                    self.state.finish_attempt(
                        attempt_id, "FAILED",
                        summary={"message": message}, error=exc,
                    )
                except Exception:
                    pass
        if created_run:
            run = self.state.get_run(run_id) or {}
            self._finish_unstarted(
                run_id, run.get("requested_passes", []), "FAILED", message
            )
            if hasattr(self.state, "finalize_run"):
                self.state.finalize_run(
                    run_id, "FAILED", summary={"controller_error": message},
                    actor="gui-controller",
                )

    # ------------------------------------------------------------------
    # Logs and timer (read-only)
    # ------------------------------------------------------------------

    def logs(
        self, run_id: str, *, attempt_id: str | None = None, limit: int = 200
    ) -> dict:
        run_id = _safe_id(run_id, "run id")
        limit = _bounded_int(limit, "limit", 1, 1000)
        if not self.state.get_run(run_id):
            raise TraumControlError("run not found", status=404)
        if attempt_id:
            attempt_id = _safe_id(attempt_id, "attempt id")
            attempt = self.state.get_attempt(attempt_id)
            if not attempt or str(attempt.get("run_id")) != run_id:
                raise TraumControlError("attempt not found for this run", status=404)
        else:
            attempts = self.state.list_attempts(run_id=run_id, limit=100)
            if not attempts:
                return {"run_id": run_id, "attempt_id": None, "text": "", "lines": 0}
            attempt = attempts[0]
            attempt_id = str(attempt["attempt_id"])

        log_path = attempt.get("log_path")
        if not log_path:
            artifacts = attempt.get("artifacts") or {}
            log_path = artifacts.get("log_path") if isinstance(artifacts, dict) else None
        if not log_path:
            log_path = self._attempt_log_path(attempt_id)
        self._assert_owned_log_path(log_path)
        data = self._read_log_text(log_path, limit=limit)
        data.update({"run_id": run_id, "attempt_id": attempt_id})
        return data

    def _attempt_log_path(self, attempt_id: str) -> str:
        safe = _safe_id(str(attempt_id), "attempt id")
        return os.path.join(self._log_root, safe + ".log")

    def _assert_owned_log_path(self, path: Any) -> None:
        if not isinstance(path, str):
            raise TraumControlError("attempt has no readable controller log", status=404)
        resolved = os.path.realpath(path)
        root = os.path.realpath(self._log_root)
        try:
            inside = os.path.commonpath([root, resolved]) == root
        except ValueError:
            inside = False
        if not inside:
            raise TraumControlError(
                "refusing non-controller log path", status=409
            )

    def _read_log_text(self, path: str, *, limit: int) -> dict:
        if not os.path.isfile(path):
            return {"text": "", "lines": 0, "truncated": False}
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > _MAX_LOG_BYTES:
                fh.seek(-_MAX_LOG_BYTES, os.SEEK_END)
            raw = fh.read(_MAX_LOG_BYTES)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        truncated = size > len(raw) or len(lines) > limit
        selected = lines[-limit:]
        safe = redact_sensitive_text("\n".join(selected), force=True)
        return {"text": safe, "lines": len(selected), "truncated": truncated}

    def timer_status(self) -> dict:
        """Read fixed properties of the one TRAUM timer; never mutate it."""
        argv = [
            "systemctl", "show", "goethe-dream.timer", "--no-pager",
            "--property=LoadState,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec",
        ]
        try:
            result = self._run_command(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=4,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        if result.returncode != 0:
            err = redact_sensitive_text((result.stderr or "").strip(), force=True)
            return {"available": False, "error": err or f"systemctl exited {result.returncode}"}
        props = {}
        for line in (result.stdout or "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                props[key] = value or None
        return {
            "available": True,
            "active_state": props.get("ActiveState"),
            "sub_state": props.get("SubState"),
            "unit_file_state": props.get("UnitFileState"),
            "load_state": props.get("LoadState"),
            "next_run": props.get("NextElapseUSecRealtime"),
            "last_trigger": props.get("LastTriggerUSec"),
            "read_only": True,
        }

    def evaluation_status(self) -> dict:
        """Adapter for the isolated A/B registry.

        The GUI exposes evidence/readiness only.  It deliberately has no
        generic "run eval" endpoint. Evaluation capture/execution remains an
        offline, typed operator workflow even when the isolated harness reports
        that all prerequisites are safe.
        """
        try:
            import traum_eval
        except Exception:
            return {
                "available": False,
                "ready": False,
                "analysis_available": False,
                "analysis_complete": False,
                "analysis_label": "analysis pending",
                "promotion_eligible": False,
                "blocked_reason": "isolated A/B registry is not installed",
                "historical_v1": dict(_HISTORICAL_V1_EVALUATION),
                "execution_exposed": False,
            }
        try:
            data = traum_eval.list_statuses(traum_eval.DEFAULT_REGISTRY)
        except Exception as exc:
            return {
                "available": True,
                "ready": False,
                "analysis_available": False,
                "analysis_complete": False,
                "analysis_label": "analysis pending",
                "promotion_eligible": False,
                "blocked_reason": f"{type(exc).__name__}: {exc}",
                "historical_v1": dict(_HISTORICAL_V1_EVALUATION),
                "execution_exposed": False,
            }
        try:
            raw_evidence = traum_eval.evidence_summary(traum_eval.DEFAULT_REGISTRY)
        except Exception as exc:
            continuous = {
                "populated": False,
                "event_count": 0,
                "proposal_types": {},
                "decision_wiring": "not_connected",
                "error": f"{type(exc).__name__}: {exc}",
            }
        else:
            raw_types = raw_evidence.get("proposal_types", {})
            safe_types = {}
            for proposal_type, summary in raw_types.items():
                eligibility = summary.get("auto_apply_eligibility") or {}
                safe_types[str(proposal_type)] = {
                    "event_count": int(summary.get("event_count", 0) or 0),
                    "retrieval": summary.get("retrieval") or {},
                    "eligible_for_policy_review": bool(
                        eligibility.get("eligible_for_policy_review", False)
                    ),
                    "ineligibility_reasons": eligibility.get("reasons") or [],
                }
            event_count = sum(row["event_count"] for row in safe_types.values())
            continuous = {
                "populated": event_count > 0,
                "event_count": event_count,
                "proposal_types": safe_types,
                "auto_apply_enabled": False,
                # Decision→evidence recording has not yet been wired into the
                # live apply path.  Never imply an empty registry was observed.
                "decision_wiring": "not_connected",
            }
        evaluations = data.get("evaluations", []) if isinstance(data, dict) else []
        if not evaluations:
            return {
                "available": True,
                "ready": False,
                "analysis_available": False,
                "analysis_complete": False,
                "analysis_label": "analysis pending",
                "promotion_eligible": False,
                "latest_evidence": None,
                "blocked_reason": "no isolated A/B evaluation is registered",
                "next_actions": [],
                "continuous_evidence": continuous,
                "historical_v1": dict(_HISTORICAL_V1_EVALUATION),
                "execution_exposed": False,
            }
        latest = max(
            evaluations,
            key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
        )
        stage = str(latest.get("stage") or "unknown")
        actions = []
        for action in latest.get("next_actions") or []:
            # Deliberately omit condition endpoints, registry/filesystem paths,
            # and raw artifacts from the web response.
            item = {
                key: action.get(key) for key in
                ("action", "blocked", "not_before", "reason")
                if action.get(key) is not None
            }
            if action.get("missing") is not None:
                item["missing_count"] = len(action.get("missing") or [])
            actions.append(item)
        blocked_action = next((a for a in actions if a.get("blocked")), None)
        ready = stage == "analyzed"
        if blocked_action:
            blocked_reason = blocked_action.get("reason") or "next evaluation stage is blocked"
        elif not ready:
            blocked_reason = f"evaluation stage {stage!r} has not produced analyzed evidence"
        else:
            blocked_reason = None
        analysis = latest.get("analysis")
        evidence = None
        promotion_eligible = bool(latest.get("promotion_eligible", False))
        if isinstance(analysis, dict):
            evidence = {
                key: analysis.get(key) for key in
                ("outcome", "sha256", "gate_results", "lift_results")
                if key in analysis
            }
            delta = analysis.get("corpus_delta")
            if isinstance(delta, dict):
                # Counts only: the operator needs to see that the learning
                # window actually changed the corpus, not the document IDs.
                if delta.get("comparable"):
                    evidence["learning_delta"] = {
                        key: delta.get(key) for key in
                        ("baseline_documents", "candidate_documents",
                         "added", "removed", "modified")
                        if isinstance(delta.get(key), int)
                    }
                else:
                    evidence["learning_delta"] = {"comparable": False}
            if analysis.get("artifact"):
                # A basename is useful as an audit reference without exposing
                # the registry or filesystem root in the web response.
                evidence["artifact"] = os.path.basename(str(analysis["artifact"]))
            promotion = analysis.get("promotion")
            if isinstance(promotion, dict):
                promotion_eligible = bool(
                    promotion.get("eligible_for_policy_review", False)
                )
            elif "promotion_eligible" in analysis:
                promotion_eligible = bool(analysis.get("promotion_eligible"))
        return {
            "available": True,
            "ready": ready,
            "analysis_available": ready,
            "analysis_complete": ready,
            "analysis_label": "analysis available" if ready else "analysis pending",
            "promotion_eligible": promotion_eligible,
            "evaluation_id": latest.get("eval_id"),
            "stage": stage,
            "updated_at": latest.get("updated_at"),
            "latest_evidence": evidence,
            "next_actions": actions,
            "blocked_reason": blocked_reason,
            "continuous_evidence": continuous,
            "execution_exposed": False,
        }

    # ------------------------------------------------------------------
    # Human-gated proposal and evidence-retention actions
    # ------------------------------------------------------------------

    def revalidate_queue(self, payload: dict | None = None) -> dict:
        """Run the read-only invariant sweep over PENDING proposals.

        This is the automated half of the human gate: it resolves what the
        approve path would resolve anyway, so a person only sees decisions
        that need judgement.  It cannot apply, approve, or defer anything.
        """
        payload = _strict_object(payload or {}, {"limit"})
        limit = _bounded_int(
            payload.get("limit", _SWEEP_LIMIT), "limit", 1, 500
        )
        module = self._dream_apply()
        revalidate = getattr(module, "revalidate_pending", None)
        if not callable(revalidate):
            raise TraumControlError(
                "deployed dream_apply has no invariant sweep", status=503
            )
        # The decision lock keeps a sweep and a human decision from resolving
        # the same proposal concurrently.
        with self._decision_lock:
            try:
                result = revalidate(self.state, limit=limit, actor="system-invariant")
            except Exception as exc:
                raise TraumControlError(
                    f"invariant sweep failed: {exc}", status=409
                ) from exc
        summary = self._sweep_summary(result)
        self._last_sweep = summary
        return summary

    @staticmethod
    def _sweep_summary(result: Any) -> dict:
        result = result if isinstance(result, dict) else {}
        return {
            "swept_at": result.get("swept_at"),
            "checked": int(result.get("checked", 0) or 0),
            "auto_rejected": int(result.get("system_rejected", 0) or 0),
            "still_actionable": int(result.get("valid", 0) or 0),
            "skipped": int(result.get("skipped", 0) or 0),
            "blocked": bool(result.get("blocked", False)),
            "reason": result.get("reason"),
            "applies_anything": False,
        }

    def _schedule_sweep(self) -> None:
        """Sweep off the request path; a read must never trigger a write."""
        with self._lock:
            existing = self._sweep_thread
            if existing is not None and existing.is_alive():
                return
            thread = threading.Thread(
                target=self._sweep_body, name="traum-invariant-sweep", daemon=True
            )
            self._sweep_thread = thread
        try:
            thread.start()
        except Exception as exc:
            self._last_sweep = self._sweep_summary({
                "blocked": True,
                "reason": f"sweep could not start: {type(exc).__name__}",
            })

    def _sweep_body(self) -> None:
        try:
            self.revalidate_queue({})
        except Exception as exc:
            # A background hygiene pass must never destabilize the gateway.
            self._last_sweep = self._sweep_summary({
                "blocked": True,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    def preview_proposal(self, proposal_id: str, payload: dict) -> dict:
        proposal_id = _safe_id(proposal_id, "proposal id")
        payload = _strict_object(payload, {"expected_revision"})
        expected = payload.get("expected_revision")
        if expected is not None:
            expected = _bounded_int(expected, "expected_revision", 0, 2**31 - 1)
        module = self._dream_apply()
        try:
            result = module.preview_proposal(
                self.state, proposal_id, expected_revision=expected
            )
        except Exception as exc:
            raise TraumControlError(f"preview failed: {exc}", status=409) from exc
        if not isinstance(result, dict):
            result = {"preview": str(result)}
        result["side_effect_free"] = True
        return result

    def decide_proposal(self, proposal_id: str, payload: dict) -> dict:
        proposal_id = _safe_id(proposal_id, "proposal id")
        payload = _strict_object(
            payload, {"decision", "reason", "defer_until", "expected_revision"}
        )
        decision = payload.get("decision")
        if decision not in DECISIONS:
            raise TraumControlError("decision must be approve, reject, or defer")
        expected = _bounded_int(
            payload.get("expected_revision"),
            "expected_revision", 0, 2**31 - 1,
        )
        reason = payload.get("reason")
        if reason is not None:
            if not isinstance(reason, str) or len(reason.strip()) > _MAX_REASON_CHARS:
                raise TraumControlError(
                    f"reason must be at most {_MAX_REASON_CHARS} characters"
                )
            reason = reason.strip() or None
        if decision == "reject" and not reason:
            raise TraumControlError("reject requires a reason")

        defer_until = payload.get("defer_until")
        if decision == "defer":
            defer_until = self._validate_defer_until(defer_until)
        elif defer_until is not None:
            raise TraumControlError("defer_until is only valid for defer")

        module = self._dream_apply()
        with self._decision_lock:
            try:
                result = module.decide_proposal(
                    self.state,
                    proposal_id,
                    decision,
                    expected_revision=expected,
                    reason=reason,
                    defer_until=defer_until,
                    actor="gui:local-operator",
                )
            except Exception as exc:
                raise TraumControlError(f"proposal decision failed: {exc}", status=409) from exc
        return result if isinstance(result, dict) else {"result": str(result)}

    def acknowledge_attempt(self, attempt_id: str, payload: dict) -> dict:
        attempt_id = _safe_id(attempt_id, "attempt id")
        _strict_object(payload, set())
        attempt = self.state.get_attempt(attempt_id)
        if not attempt:
            raise TraumControlError("attempt not found", status=404)
        if str(attempt.get("state", "")).upper() not in {"FAILED", "BLOCKED"}:
            raise TraumControlError(
                "only FAILED or BLOCKED attempts need acknowledgement", status=409
            )
        result = self.state.acknowledge_attempt(
            attempt_id, actor="gui:local-operator"
        )
        return result if isinstance(result, dict) else self.state.get_attempt(attempt_id)

    def archive_run(self, run_id: str, payload: dict) -> dict:
        run_id = _safe_id(run_id, "run id")
        _strict_object(payload, set())
        run = self.state.get_run(run_id)
        if not run:
            raise TraumControlError("run not found", status=404)
        if str(run.get("state", "")).upper() not in TERMINAL_RUN_STATES:
            raise TraumControlError("only terminal runs can be archived", status=409)
        with self._lock:
            if run_id in self._workers:
                raise TraumControlError("active controller run cannot be archived", status=409)
        result = self.state.archive_run(run_id, actor="gui:local-operator")
        return result if isinstance(result, dict) else self.state.get_run(run_id)

    def _dream_apply(self):
        if self._apply_module is not None:
            return self._apply_module
        try:
            import dream_apply
        except Exception as exc:
            raise TraumControlError(
                f"dream_apply module unavailable: {exc}", status=503
            ) from exc
        self._apply_module = dream_apply
        return dream_apply

    @staticmethod
    def _validate_defer_until(value: Any) -> str:
        if not isinstance(value, str):
            raise TraumControlError("defer_until must be an ISO date")
        try:
            parsed = _dt.date.fromisoformat(value)
        except ValueError as exc:
            raise TraumControlError("defer_until must be YYYY-MM-DD") from exc
        today = _dt.date.today()
        if not today < parsed <= today + _dt.timedelta(days=365):
            raise TraumControlError(
                "defer_until must be within the next 365 days"
            )
        return parsed.isoformat()


__all__ = [
    "DECISIONS",
    "DREAM_PASSES",
    "RUN_PROFILES",
    "TraumControlError",
    "TraumController",
]
