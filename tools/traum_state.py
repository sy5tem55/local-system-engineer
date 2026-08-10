#!/usr/bin/env python3
"""Canonical durable state for TRAUM runs, attempts, proposals, and consumption.

The historical TRAUM implementation inferred lifecycle from a mixture of
date-named directories and append-only JSONL files.  That made a failed and a
successful retry on the same day indistinguishable, and tied session progress
to a later human proposal decision.  This module is the single typed state
boundary shared by the runner, apply gate, cycle controller, and GUI.

The SQLite database contains metadata only.  Reports/logs remain ordinary
artifacts referenced by path.  All mutating methods append an event in the
same transaction as the materialized state change.  Preview/dry-run callers
must not instantiate :class:`TraumState`; merely importing this module has no
filesystem side effects.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence


SCHEMA_VERSION = 2
MAX_LEASE_SECONDS = 24 * 60 * 60
MAX_RECOVERY_GRACE_SECONDS = 60 * 60
DEFAULT_RECOVERY_GRACE_SECONDS = 30

RUN_STATES = {
    "QUEUED", "RUNNING", "SUCCEEDED", "DEGRADED", "FAILED", "BLOCKED",
    "CANCELLED",
}
ATTEMPT_STATES = {
    "QUEUED", "RUNNING", "SUCCEEDED", "NULL", "BLOCKED", "FAILED",
    "CANCELLED",
}
ATTEMPT_TERMINAL_STATES = ATTEMPT_STATES - {"QUEUED", "RUNNING"}
PROPOSAL_STATES = {
    "STAGED", "PENDING", "DEFERRED", "APPLYING", "APPLIED", "REJECTED",
    "SYSTEM_REJECTED", "SUPERSEDED", "EXPIRED", "APPLY_FAILED",
}
PROPOSAL_TERMINAL_STATES = {
    "APPLIED", "REJECTED", "SYSTEM_REJECTED", "SUPERSEDED", "EXPIRED",
}
CONSUMABLE_OUTCOMES = {"SUCCEEDED", "NULL"}


class TraumStateError(RuntimeError):
    """Base class for canonical-state failures."""


class NotFoundError(TraumStateError):
    """Requested canonical entity does not exist."""


class ConflictError(TraumStateError):
    """State or revision changed since the caller read it."""


_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,127}$")


try:
    from redact import redact_sensitive_text as _shared_redact_sensitive_text
except Exception:  # pragma: no cover - package-style imports / partial deploy
    try:
        from tools.redact import redact_sensitive_text as _shared_redact_sensitive_text
    except Exception:  # pragma: no cover - the local fail-closed fallback is tested
        _shared_redact_sensitive_text = None


_FALLBACK_SECRET_RULES = (
    (re.compile(r"(?i)(Bearer\s+)[^\s,;]+"), r"\1[REDACTED:bearer-token]"),
    (re.compile(
        r"(?i)((?:api[_-]?key|token|secret|password|access[_-]?token|"
        r"refresh[_-]?token)\s*[:=]\s*[\"']?)[^\s\"',;}]+"
    ), r"\1[REDACTED:credential]"),
    (re.compile(
        r"(?i)((?:sshpass\s+(?:-p|--password)|--password|--token|"
        r"--api-key|--secret)\s+)[^\s]+"
    ), r"\1[REDACTED:cli-credential]"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|"
                r"AKIA[A-Z0-9]{16})\b"), "[REDACTED:credential-token]"),
    (re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s/@]+(@)"),
     r"\1[REDACTED:password]\2"),
)


def redact_persisted_text(value) -> str | None:
    """Force-redact a string before it crosses a durable TRAUM boundary.

    The shared LSE redactor is preferred and is invoked with ``force=True`` so
    a local logging opt-out can never weaken state/report safety.  A compact
    fail-closed fallback covers the credential shapes most likely to appear in
    exception text if the shared module is unavailable during a partial
    deployment.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if _shared_redact_sensitive_text is not None:
        try:
            text = _shared_redact_sensitive_text(text, force=True)
        except Exception:
            # Redaction must not turn a reporting failure into raw persistence.
            pass
    for pattern, replacement in _FALLBACK_SECRET_RULES:
        text = pattern.sub(replacement, text)
    return text


def redact_persisted_value(value):
    """Recursively redact strings while preserving JSON-compatible shape."""
    if isinstance(value, str):
        return redact_persisted_text(value)
    if isinstance(value, dict):
        return {str(k): redact_persisted_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_persisted_value(v) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_persisted_text(value)


def _validate_id(value: str, label: str) -> str:
    value = str(value)
    if not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"unsafe {label}: {value!r}")
    return value


def utc_now() -> str:
    return _utc_iso(datetime.now(timezone.utc))


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bounded_lease_seconds(value: float | int | None) -> float | None:
    if value is None:
        return None
    seconds = float(value)
    if not 1 <= seconds <= MAX_LEASE_SECONDS:
        raise ValueError(
            f"lease_seconds must be between 1 and {MAX_LEASE_SECONDS}"
        )
    return seconds


def _lease_from_config(config: dict | None) -> float | None:
    config = config or {}
    for key in (
        "remaining_wall_clock_minutes",
        "operation_wall_clock_minutes",
        "budget_max_wall_clock_min",
        "wall_clock_minutes",
    ):
        value = config.get(key)
        if value is None:
            continue
        try:
            return _bounded_lease_seconds(float(value) * 60)
        except (TypeError, ValueError):
            continue
    return None


def default_db_path(dream_dir: str) -> str:
    return os.path.join(os.path.abspath(dream_dir), "traum-state.db")


def re_full_date(value: str) -> bool:
    try:
        return len(value) == 10 and datetime.fromisoformat(value).date().isoformat() == value
    except (TypeError, ValueError):
        return False


def new_id(kind: str) -> str:
    prefixes = {"run": "run", "attempt": "att", "proposal": "prp"}
    prefix = prefixes.get(kind, kind[:3].lower())
    return f"{prefix}_{uuid.uuid4().hex}"


_IDENTITY_IGNORED_KEYS = {
    "proposal_id", "run_id", "attempt_id", "revision", "state",
    "created_at", "updated_at", "expected_target_token",
}


# SPEC-gate-toil-2026-08 Sec2/Sec5.2, Hazard B: `diagnosis` proposals hash
# their full body by default, and that body is mostly model prose
# (args.interpretation, args.resolution, args.anti_response, why) plus
# `evidence`, a session-key list that grows as new episodes join the
# cluster. All of that is reworded/extended every run, so a fresh
# fingerprint is guaranteed by construction and repeat_prior() never fires
# -- fourteen distinct fingerprints for fourteen re-drafts of the same
# handful of errors. The stable identity of a diagnosis is
# `error_text` + `context`: the failure signature and what was being
# attempted, both derived from the cluster rather than invented by the
# model, and what record_error keys on.
#
# Scoped to `diagnosis` ONLY. SPEC-gate-toil-2026-08 Hazard B named
# `skill-candidate` as sharing this shape and due the same narrowing "the
# moment error-cluster emits one again". Re-probed against the two live
# call sites that emit type="skill-candidate" (dream_runner.py's
# error-cluster pass and its insights pass): neither one's `args` has ever
# had `error_text`/`context` keys -- the shape is task/occupation/
# procedure/verification/preconditions/failure_modes/provenance/
# source_tier/quality instead. Narrowing skill-candidate to
# {type, call, args.error_text, args.context} the same way would make
# args.get("error_text") and args.get("context") both resolve to None for
# every skill-candidate proposal ever produced, collapsing all of them
# onto one identical fingerprint regardless of task -- the opposite of
# Hazard A's warning, and worse than the defect this fix closes. Left on
# full-body identity (unchanged) until skill-candidate actually carries a
# stable error_text/context pair of its own.
_NARROW_IDENTITY_TYPES = {"diagnosis"}
_NARROW_IDENTITY_ARG_KEYS = ("error_text", "context")


def canonical_proposal(proposal: dict) -> dict:
    """Return the semantic proposal body used for exact deduplication.

    Most proposal types are identified by their full body (minus the
    volatile bookkeeping keys in _IDENTITY_IGNORED_KEYS). Types in
    _NARROW_IDENTITY_TYPES are identified narrowly instead, by
    {type, call, args.error_text, args.context} alone -- see the comment
    above _NARROW_IDENTITY_TYPES for why.
    """
    if proposal.get("type") in _NARROW_IDENTITY_TYPES:
        args = proposal.get("args") or {}
        return {
            "type": proposal.get("type"),
            "call": proposal.get("call"),
            "args": {k: args.get(k) for k in _NARROW_IDENTITY_ARG_KEYS},
        }
    return {k: v for k, v in proposal.items() if k not in _IDENTITY_IGNORED_KEYS}


def proposal_fingerprint(proposal: dict) -> str:
    body = json.dumps(
        canonical_proposal(proposal), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


_KB_CAS_FIELDS = {
    "title", "content", "doc_id", "topic", "tags", "quality_score",
    "source_tier", "source_url", "source_path", "volatility", "stale",
    "refinement_count", "consecutive_failures", "success_count",
    "created_at", "updated_at", "verified_against", "version",
}


def document_token(document: dict | None) -> str | None:
    """Content token used for optimistic concurrency against a KB target.

    Elasticsearch sequence metadata is not available in the runner's bulk
    search results, so the token deliberately covers the complete source
    document (excluding transient ``_`` metadata).  Apply-time ``get`` must
    reproduce this token before a semantic write is allowed.
    """
    if document is None:
        return None
    body = {k: document.get(k) for k in sorted(_KB_CAS_FIELDS)}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json(value) -> str:
    return json.dumps(
        redact_persisted_value(value), sort_keys=True, ensure_ascii=False,
        default=str,
    )


def _loads(value, default):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class TraumState:
    """SQLite-backed canonical state store.

    Every public row-returning method returns a plain dict with JSON columns
    decoded.  A short-lived connection per operation makes the class safe for
    the GUI and worker processes to use concurrently.
    """

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def _tx(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            source TEXT NOT NULL,
            state TEXT NOT NULL,
            requested_passes_json TEXT NOT NULL,
            config_json TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            started_at TEXT,
            deadline_at TEXT,
            finished_at TEXT,
            archived_at TEXT,
            archived_by TEXT,
            cancel_requested_at TEXT,
            cancel_requested_by TEXT
        );
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            pass_name TEXT NOT NULL,
            attempt_no INTEGER NOT NULL,
            retry_of TEXT REFERENCES attempts(attempt_id),
            state TEXT NOT NULL,
            config_json TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}',
            artifacts_json TEXT NOT NULL DEFAULT '{}',
            log_path TEXT,
            error_type TEXT,
            error_text TEXT,
            exit_code INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            lease_expires_at TEXT,
            finished_at TEXT,
            acknowledged_at TEXT,
            acknowledged_by TEXT,
            UNIQUE(run_id, pass_name, attempt_no)
        );
        CREATE INDEX IF NOT EXISTS attempts_run_idx
            ON attempts(run_id, created_at);
        CREATE TABLE IF NOT EXISTS proposals (
            proposal_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            run_id TEXT NOT NULL REFERENCES runs(run_id),
            attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
            proposal_type TEXT NOT NULL,
            call_type TEXT NOT NULL,
            pair_id TEXT,
            payload_json TEXT NOT NULL,
            state TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            reason TEXT,
            actor TEXT,
            defer_until TEXT,
            result_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(attempt_id, fingerprint)
        );
        CREATE INDEX IF NOT EXISTS proposals_state_idx
            ON proposals(state, created_at);
        CREATE INDEX IF NOT EXISTS proposals_fingerprint_idx
            ON proposals(fingerprint, created_at);
        CREATE TABLE IF NOT EXISTS session_consumption (
            pass_name TEXT NOT NULL,
            session_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
            outcome TEXT NOT NULL,
            consumed_at TEXT NOT NULL,
            PRIMARY KEY(pass_name, session_id)
        );
        CREATE INDEX IF NOT EXISTS consumption_attempt_idx
            ON session_consumption(attempt_id);
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT UNIQUE
        );
        CREATE INDEX IF NOT EXISTS events_entity_idx
            ON events(entity_kind, entity_id, event_id);
        """
        with self._connect() as conn:
            conn.executescript(schema)
            # CREATE TABLE IF NOT EXISTS does not evolve an already deployed
            # SQLite table.  Keep migrations additive and idempotent so a
            # gateway restart can open the pre-lease v1 database safely.
            run_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "deadline_at" not in run_columns:
                conn.execute("ALTER TABLE runs ADD COLUMN deadline_at TEXT")
            attempt_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(attempts)").fetchall()
            }
            if "lease_expires_at" not in attempt_columns:
                conn.execute("ALTER TABLE attempts ADD COLUMN lease_expires_at TEXT")
            conn.execute(
                "INSERT INTO meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            # Windows ACLs are authoritative there; POSIX deployments get
            # the fail-closed mode even when the parent umask is permissive.
            pass

    @staticmethod
    def _event(conn, kind: str, entity_id: str, event_type: str,
               actor: str = "system", payload=None, idempotency_key=None) -> None:
        actor = (redact_persisted_text(actor) or "system")[:256]
        conn.execute(
            "INSERT OR IGNORE INTO events(entity_kind,entity_id,event_type,actor,"
            "occurred_at,payload_json,idempotency_key) VALUES(?,?,?,?,?,?,?)",
            (kind, entity_id, event_type, actor, utc_now(), _json(payload or {}),
             idempotency_key),
        )

    @staticmethod
    def _run_row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        out = dict(row)
        out["requested_passes"] = _loads(out.pop("requested_passes_json"), [])
        out["config"] = _loads(out.pop("config_json"), {})
        out["summary"] = _loads(out.pop("summary_json"), {})
        out["archived"] = bool(out.get("archived_at"))
        out["cancel_requested"] = bool(out.get("cancel_requested_at"))
        return out

    @staticmethod
    def _attempt_row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        out = dict(row)
        out["config"] = _loads(out.pop("config_json"), {})
        out["summary"] = _loads(out.pop("summary_json"), {})
        out["artifacts"] = _loads(out.pop("artifacts_json"), {})
        out["acknowledged"] = bool(out.get("acknowledged_at"))
        return out

    @staticmethod
    def _proposal_row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        out = dict(row)
        out["proposal"] = _loads(out.pop("payload_json"), {})
        out["result"] = _loads(out.pop("result_json"), None)
        return out

    def create_run(self, profile: str, requested_passes: Sequence[str],
                   config: dict | None = None, source: str = "cli",
                   run_id: str | None = None,
                   lease_seconds: float | int | None = None) -> dict:
        run_id = _validate_id(run_id or new_id("run"), "run_id")
        passes = list(dict.fromkeys(str(p) for p in requested_passes))
        if not passes:
            raise ValueError("requested_passes must not be empty")
        safe_config = redact_persisted_value(config or {})
        lease = _bounded_lease_seconds(lease_seconds)
        if lease is None:
            lease = _lease_from_config(safe_config)
        now = utc_now()
        deadline_at = (
            _utc_iso(_as_utc(now) + timedelta(seconds=lease))
            if lease is not None else None
        )
        with self._tx() as conn:
            existing = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if (existing["profile"] != profile
                        or _loads(existing["requested_passes_json"], []) != passes
                        or _loads(existing["config_json"], {}) != safe_config
                        or existing["source"] != source):
                    raise ConflictError(
                        f"run id collision with different immutable identity: {run_id}"
                    )
                return self._run_row(existing)
            if source in {"gui", "scheduled", "manual"}:
                admission = self._recover_orphaned_controller_work_tx(
                    conn, owned_run_ids=(), now=_as_utc(now),
                    grace_seconds=DEFAULT_RECOVERY_GRACE_SECONDS,
                    actor=f"{source}-admission",
                )
                if admission["unowned_active"]:
                    active = admission["unowned_active"][0]
                    raise ConflictError(
                        "another canonical TRAUM run is active: "
                        f"{active['run_id']} ({active['run_state']})"
                    )
            conn.execute(
                "INSERT INTO runs(run_id,profile,source,state,requested_passes_json,"
                "config_json,created_at,deadline_at) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, profile, source, "QUEUED", _json(passes),
                 _json(safe_config), now, deadline_at),
            )
            self._event(conn, "run", run_id, "CREATED", source,
                        {"profile": profile, "requested_passes": passes,
                         "deadline_at": deadline_at})
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(row)

    def start_attempt(self, run_id: str, pass_name: str,
                      retry_of: str | None = None, config: dict | None = None,
                      log_path: str | None = None,
                      attempt_id: str | None = None,
                      lease_seconds: float | int | None = None) -> dict:
        attempt_id = _validate_id(attempt_id or new_id("attempt"), "attempt_id")
        safe_config = redact_persisted_value(config or {})
        lease = _bounded_lease_seconds(lease_seconds)
        if lease is None:
            lease = _lease_from_config(safe_config)
        now = utc_now()
        with self._tx() as conn:
            run_row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not run_row:
                raise NotFoundError(f"run not found: {run_id}")
            if run_row["archived_at"]:
                raise ConflictError("cannot start an attempt on an archived run")
            if run_row["cancel_requested_at"] or run_row["state"] == "CANCELLED":
                raise ConflictError("cannot start an attempt on a cancelled run")
            existing = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if existing:
                if (existing["run_id"] != run_id or existing["pass_name"] != pass_name
                        or existing["retry_of"] != retry_of):
                    raise ConflictError(f"attempt id already belongs to another operation: {attempt_id}")
                return self._attempt_row(existing)
            if run_row["source"] in {"gui", "scheduled", "manual"}:
                admission = self._recover_orphaned_controller_work_tx(
                    conn, owned_run_ids=(run_id,), now=_as_utc(now),
                    grace_seconds=DEFAULT_RECOVERY_GRACE_SECONDS,
                    actor=f"{run_row['source']}-admission",
                )
                if admission["unowned_active"]:
                    active = admission["unowned_active"][0]
                    raise ConflictError(
                        "another canonical TRAUM run is active: "
                        f"{active['run_id']} ({active['run_state']})"
                    )
                same_run_active = conn.execute(
                    "SELECT attempt_id FROM attempts WHERE run_id=? "
                    "AND state IN ('QUEUED','RUNNING') LIMIT 1", (run_id,),
                ).fetchone()
                if same_run_active:
                    raise ConflictError(
                        "run already has an active attempt: "
                        f"{same_run_active['attempt_id']}"
                    )
            run_deadline = run_row["deadline_at"]
            if lease is not None and run_row["state"] not in {"QUEUED", "RUNNING"}:
                # A human retry is a new bounded operation on the same run.
                run_deadline = _utc_iso(_as_utc(now) + timedelta(seconds=lease))
                conn.execute(
                    "UPDATE runs SET deadline_at=? WHERE run_id=?",
                    (run_deadline, run_id),
                )
            if lease is not None:
                lease_expires_at = _utc_iso(
                    _as_utc(now) + timedelta(seconds=lease)
                )
                if run_deadline:
                    # An attempt can use only the run's remaining budget; a
                    # retry may establish a fresh run-level deadline below.
                    lease_expires_at = _utc_iso(min(
                        _as_utc(lease_expires_at), _as_utc(run_deadline)
                    ))
            else:
                lease_expires_at = run_deadline
            if retry_of:
                prior = conn.execute(
                    "SELECT run_id,pass_name FROM attempts WHERE attempt_id=?",
                    (retry_of,),
                ).fetchone()
                if not prior:
                    raise NotFoundError(f"retry source attempt not found: {retry_of}")
                if prior["run_id"] != run_id or prior["pass_name"] != pass_name:
                    raise ConflictError("retry_of must belong to the same run and pass")
            attempt_no = conn.execute(
                "SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts "
                "WHERE run_id=? AND pass_name=?", (run_id, pass_name),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO attempts(attempt_id,run_id,pass_name,attempt_no,retry_of,state,"
                "config_json,log_path,created_at,started_at,lease_expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, run_id, pass_name, attempt_no, retry_of, "RUNNING",
                 _json(safe_config), log_path, now, now, lease_expires_at),
            )
            conn.execute(
                "UPDATE runs SET state='RUNNING', started_at=COALESCE(started_at,?), "
                "finished_at=NULL WHERE run_id=?", (now, run_id),
            )
            self._event(conn, "attempt", attempt_id, "STARTED", "system",
                        {"run_id": run_id, "pass": pass_name, "attempt_no": attempt_no,
                         "retry_of": retry_of,
                         "lease_expires_at": lease_expires_at})
            row = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        return self._attempt_row(row)

    @staticmethod
    def _aggregate_run(conn: sqlite3.Connection, run_id: str) -> None:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run:
            return
        requested = _loads(run["requested_passes_json"], [])
        rows = conn.execute(
            "SELECT * FROM attempts WHERE run_id=? ORDER BY attempt_no DESC, created_at DESC",
            (run_id,),
        ).fetchall()
        latest = {}
        for row in rows:
            latest.setdefault(row["pass_name"], row)
        summary_update = None
        if any(row["state"] in {"QUEUED", "RUNNING"} for row in latest.values()):
            state, finished = "RUNNING", None
        elif any(p not in latest for p in requested):
            state, finished = "RUNNING", None
        else:
            states = [latest[p]["state"] for p in requested]
            good = sum(s in {"SUCCEEDED", "NULL"} for s in states)
            if good == len(states):
                state = "SUCCEEDED"
            elif good:
                state = "DEGRADED"
            elif states and all(s == "BLOCKED" for s in states):
                state = "BLOCKED"
            elif states and all(s == "CANCELLED" for s in states):
                state = "CANCELLED"
            else:
                state = "FAILED"
            finished = utc_now()
            # SPEC-subpass-outcomes-2026-08 SS5.3: record the ratio so
            # DEGRADED can be read as "5 of 6", not a bare word.
            prior_summary = _loads(run["summary_json"], {})
            summary_update = {**prior_summary, "passes_good": good, "passes_total": len(states)}
        if summary_update is not None:
            conn.execute(
                "UPDATE runs SET state=?, finished_at=?, summary_json=? WHERE run_id=?",
                (state, finished, _json(summary_update), run_id),
            )
        else:
            conn.execute(
                "UPDATE runs SET state=?, finished_at=? WHERE run_id=?",
                (state, finished, run_id),
            )

    def finish_attempt(self, attempt_id: str, state: str,
                       summary: dict | None = None, artifacts: dict | None = None,
                       error: Exception | str | None = None,
                       exit_code: int | None = None,
                       consumed_session_ids: Iterable[str] | None = None) -> dict:
        state = state.upper()
        if state not in ATTEMPT_TERMINAL_STATES:
            raise ValueError(f"attempt terminal state required, got {state!r}")
        now = utc_now()
        safe_summary = redact_persisted_value(summary or {})
        safe_artifacts = redact_persisted_value(artifacts or {})
        error_type = (
            redact_persisted_text(type(error).__name__)
            if isinstance(error, Exception) else None
        )
        error_text = (
            redact_persisted_text(error)[:4000] if error is not None else None
        )
        consumed_ids = list(dict.fromkeys(
            str(s) for s in (consumed_session_ids or []) if s
        ))
        if consumed_ids and state not in CONSUMABLE_OUTCOMES:
            raise ValueError(f"{state} attempts cannot consume sessions")
        with self._tx() as conn:
            current = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if not current:
                raise NotFoundError(f"attempt not found: {attempt_id}")
            if current["state"] in ATTEMPT_TERMINAL_STATES:
                if current["state"] != state:
                    raise ConflictError(
                        f"attempt {attempt_id} is already {current['state']}, not {state}"
                    )
                return self._attempt_row(current)
            if (state in CONSUMABLE_OUTCOMES and current["lease_expires_at"]
                    and _as_utc(now) > _as_utc(current["lease_expires_at"])):
                raise ConflictError(
                    f"attempt {attempt_id} lease expired before successful publication"
                )
            conn.execute(
                "UPDATE attempts SET state=?,summary_json=?,artifacts_json=?,error_type=?,"
                "error_text=?,exit_code=?,finished_at=? WHERE attempt_id=?",
                (state, _json(safe_summary), _json(safe_artifacts), error_type,
                 error_text, exit_code, now, attempt_id),
            )
            proposal_rows = conn.execute(
                "SELECT proposal_id,state FROM proposals WHERE attempt_id=?",
                (attempt_id,),
            ).fetchall()
            if state in CONSUMABLE_OUTCOMES:
                for proposal in proposal_rows:
                    if proposal["state"] != "STAGED":
                        continue
                    conn.execute(
                        "UPDATE proposals SET state='PENDING',revision=revision+1,"
                        "updated_at=? WHERE proposal_id=?",
                        (now, proposal["proposal_id"]),
                    )
                    self._event(conn, "proposal", proposal["proposal_id"],
                                "PENDING", "system",
                                {"reason": "parent_attempt_completed"})
            else:
                for proposal in proposal_rows:
                    if proposal["state"] not in {"STAGED", "PENDING", "DEFERRED"}:
                        continue
                    reject_reason = f"parent_attempt_{state.lower()}"
                    conn.execute(
                        "UPDATE proposals SET state='SYSTEM_REJECTED',"
                        "revision=revision+1,reason=?,actor='system',updated_at=? "
                        "WHERE proposal_id=?",
                        (reject_reason, now, proposal["proposal_id"]),
                    )
                    self._event(conn, "proposal", proposal["proposal_id"],
                                "SYSTEM_REJECTED", "system",
                                {"reason": reject_reason})
            for session_id in consumed_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO session_consumption(pass_name,session_id,"
                    "attempt_id,outcome,consumed_at) VALUES(?,?,?,?,?)",
                    (current["pass_name"], session_id, attempt_id, state, now),
                )
            self._event(conn, "attempt", attempt_id, state, "system",
                        {"summary": safe_summary, "artifacts": safe_artifacts,
                         "error_type": error_type, "error_text": error_text,
                         "exit_code": exit_code,
                         "consumed_sessions": len(consumed_ids)})
            self._aggregate_run(conn, current["run_id"])
            row = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        return self._attempt_row(row)

    def record_proposals(self, run_id: str, attempt_id: str,
                         proposals: Sequence[dict]) -> list[dict]:
        """Persist proposals and auto-supersede exact repeats.

        Callers may set private generation annotations ``_initial_state`` and
        ``_initial_reason`` (used for malformed/system-rejected proposals).
        They are removed from the stored semantic payload.
        """
        now = utc_now()
        out = []
        with self._tx() as conn:
            attempt = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=? AND run_id=?",
                (attempt_id, run_id),
            ).fetchone()
            if not attempt:
                raise NotFoundError(f"attempt {attempt_id} is not part of run {run_id}")
            if attempt["state"] != "RUNNING":
                raise ConflictError(
                    f"attempt {attempt_id} cannot publish proposals from {attempt['state']}"
                )
            if (attempt["lease_expires_at"]
                    and _as_utc(now) > _as_utc(attempt["lease_expires_at"])):
                raise ConflictError(
                    f"attempt {attempt_id} lease expired before proposal publication"
                )
            prepared = []
            for raw in proposals:
                original = dict(raw)
                initial_state = str(original.pop("_initial_state", "STAGED")).upper()
                initial_reason = original.pop("_initial_reason", None)
                if initial_state not in PROPOSAL_STATES:
                    raise ValueError(f"invalid initial proposal state: {initial_state}")
                proposal = redact_persisted_value(original)
                if proposal != original and initial_state in {"STAGED", "PENDING"}:
                    # A proposal that contained credential-shaped material is
                    # preserved only in redacted form and cannot flow into RAG.
                    initial_state = "SYSTEM_REJECTED"
                    initial_reason = "invariant:secret_material_redacted"
                fingerprint = proposal_fingerprint(proposal)
                prepared.append({
                    "proposal": proposal,
                    "fingerprint": fingerprint,
                    "initial_state": initial_state,
                    "initial_reason": redact_persisted_text(initial_reason),
                    "prior": None,
                })

            def repeat_prior(fingerprint: str):
                priors = conn.execute(
                    "SELECT proposal_id,state,reason FROM proposals WHERE fingerprint=? "
                    "ORDER BY created_at ASC", (fingerprint,),
                ).fetchall()
                return next((row for row in priors if (
                    row["state"] in {
                        "STAGED", "PENDING", "DEFERRED", "APPLYING", "APPLIED",
                        "REJECTED", "SUPERSEDED", "APPLY_FAILED",
                    }
                    or (row["state"] == "SYSTEM_REJECTED" and str(
                        row["reason"] or ""
                    ).startswith(("malformed:", "noop:", "invariant:")))
                )), None)

            for item in prepared:
                item["prior"] = repeat_prior(item["fingerprint"])

            # Pair decisions are atomic.  A fully repeated pair is entirely
            # superseded; a partially changed pair remains entirely
            # reviewable.  This prevents a SUPERSEDED + PENDING split that no
            # atomic approve/reject operation could ever claim.
            pair_groups: dict[str, list[dict]] = {}
            for item in prepared:
                pair_id = item["proposal"].get("pair_id")
                if pair_id:
                    pair_groups.setdefault(str(pair_id), []).append(item)
            for pair_id, group in pair_groups.items():
                reviewable = all(
                    item["initial_state"] in {"STAGED", "PENDING"}
                    for item in group
                )
                if reviewable and all(item["prior"] is not None for item in group):
                    # SPEC-gate-toil-2026-08 Sec5.3: name each prior's state
                    # alongside its id so the Console can say "already
                    # applied as prp_..." instead of a bare id the operator
                    # has to go look up.
                    prior_named = sorted({
                        f"{item['prior']['proposal_id']}:{item['prior']['state']}"
                        for item in group
                    })
                    reason = "exact_pair_already_resolved_or_queued:" + ",".join(prior_named)
                    for item in group:
                        item["initial_state"] = "SUPERSEDED"
                        item["initial_reason"] = reason
                elif reviewable:
                    # At least one member changed: suppress member-level exact
                    # dedupe so the new atomic pair remains operable as a unit.
                    for item in group:
                        item["prior"] = None
                elif any(
                    item["initial_state"] == "SYSTEM_REJECTED" for item in group
                ):
                    reasons = sorted({
                        item["initial_reason"] or "invariant:invalid_pair_member"
                        for item in group
                        if item["initial_state"] == "SYSTEM_REJECTED"
                    })
                    for item in group:
                        if item["initial_state"] in {"STAGED", "PENDING"}:
                            item["initial_state"] = "SYSTEM_REJECTED"
                            item["initial_reason"] = "; ".join(reasons)

            for item in prepared:
                proposal = item["proposal"]
                fingerprint = item["fingerprint"]
                initial_state = item["initial_state"]
                initial_reason = item["initial_reason"]
                existing_same_attempt = conn.execute(
                    "SELECT * FROM proposals WHERE attempt_id=? AND fingerprint=?",
                    (attempt_id, fingerprint),
                ).fetchone()
                if existing_same_attempt:
                    out.append(self._proposal_row(existing_same_attempt))
                    continue
                prior = item["prior"]
                if prior and initial_state in {"STAGED", "PENDING"}:
                    initial_state = "SUPERSEDED"
                    # SPEC-gate-toil-2026-08 Sec5.3: name the prior's state
                    # too, not just its id -- "already applied as prp_...",
                    # not a silently dropped proposal the operator has to
                    # chase down.
                    initial_reason = (
                        f"exact_already_resolved_or_queued:"
                        f"{prior['proposal_id']}:{prior['state']}"
                    )
                # IDs are controller-owned. A model/file cannot choose an ID
                # that aliases a different canonical proposal.
                proposal_id = _validate_id(new_id("proposal"), "proposal_id")
                proposal["proposal_id"] = proposal_id
                proposal["run_id"] = run_id
                proposal["attempt_id"] = attempt_id
                conn.execute(
                    "INSERT INTO proposals(proposal_id,fingerprint,run_id,attempt_id,"
                    "proposal_type,call_type,pair_id,payload_json,state,reason,created_at,"
                    "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (proposal_id, fingerprint, run_id, attempt_id,
                     str(proposal.get("type", "unknown")), str(proposal.get("call", "unknown")),
                     proposal.get("pair_id"), _json(proposal), initial_state,
                     initial_reason, now, now),
                )
                self._event(conn, "proposal", proposal_id, "CREATED", "system",
                            {"state": initial_state, "reason": initial_reason,
                             "fingerprint": fingerprint})
                row = conn.execute(
                    "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
                ).fetchone()
                out.append(self._proposal_row(row))
        return out

    def record_consumption(self, attempt_id: str, pass_name: str,
                           session_ids: Iterable[str], outcome: str) -> int:
        outcome = outcome.upper()
        if outcome not in CONSUMABLE_OUTCOMES:
            raise ValueError(
                f"only successful/null attempts consume sessions, got {outcome!r}"
            )
        ids = list(dict.fromkeys(str(s) for s in session_ids if s))
        now = utc_now()
        inserted = 0
        with self._tx() as conn:
            attempt = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if not attempt:
                raise NotFoundError(f"attempt not found: {attempt_id}")
            if attempt["pass_name"] != pass_name:
                raise ConflictError("attempt/pass mismatch while recording consumption")
            if attempt["state"] not in CONSUMABLE_OUTCOMES or attempt["state"] != outcome:
                raise ConflictError(
                    "consumption requires a terminal attempt with the same SUCCEEDED/NULL outcome"
                )
            for session_id in ids:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO session_consumption(pass_name,session_id,"
                    "attempt_id,outcome,consumed_at) VALUES(?,?,?,?,?)",
                    (pass_name, session_id, attempt_id, outcome, now),
                )
                inserted += cur.rowcount
            self._event(conn, "attempt", attempt_id, "SESSIONS_CONSUMED", "system",
                        {"pass": pass_name, "outcome": outcome, "inserted": inserted,
                         "requested": len(ids)})
        return inserted

    def unconsumed_session_ids(self, pass_name: str,
                               session_ids: Iterable[str]) -> set[str]:
        ids = list(dict.fromkeys(str(s) for s in session_ids if s))
        if not ids:
            return set()
        consumed = set()
        with self._connect() as conn:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT session_id FROM session_consumption WHERE pass_name=? "
                    f"AND session_id IN ({marks})", [pass_name, *chunk],
                ).fetchall()
                consumed.update(row[0] for row in rows)
        return set(ids) - consumed

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            return self._run_row(conn.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone())

    def list_runs(self, include_archived: bool = False, limit: int = 100) -> list[dict]:
        where = "" if include_archived else "WHERE archived_at IS NULL"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def get_attempt(self, attempt_id: str) -> dict | None:
        with self._connect() as conn:
            return self._attempt_row(conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone())

    def list_attempts(self, run_id: str | None = None, state: str | None = None,
                      limit: int = 500) -> list[dict]:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if state:
            clauses.append("state=?")
            params.append(state.upper())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM attempts{where} ORDER BY created_at DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [self._attempt_row(row) for row in rows]

    def get_proposal(self, proposal_id: str) -> dict | None:
        with self._connect() as conn:
            return self._proposal_row(conn.execute(
                "SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone())

    def list_proposals(self, state: str | None = None, limit: int = 1000) -> list[dict]:
        params = []
        where = ""
        if state:
            states = [s.strip().upper() for s in state.split(",") if s.strip()]
            marks = ",".join("?" for _ in states)
            where = f"WHERE state IN ({marks})"
            params.extend(states)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM proposals {where} ORDER BY created_at ASC LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [self._proposal_row(row) for row in rows]

    @staticmethod
    def _proposal_state_filter(states: str | Sequence[str] | None):
        if states is None:
            return [], []
        raw = states.split(",") if isinstance(states, str) else list(states)
        normalized = [str(item).strip().upper() for item in raw if str(item).strip()]
        unknown = set(normalized) - PROPOSAL_STATES
        if unknown:
            raise ValueError(f"unknown proposal state(s): {sorted(unknown)}")
        if not normalized:
            return [], []
        marks = ",".join("?" for _ in normalized)
        return [f"state IN ({marks})"], normalized

    def count_proposals(self, states: str | Sequence[str] | None = None) -> int:
        """Return an exact SQL count; never infer totals from a UI page."""
        clauses, params = self._proposal_state_filter(states)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            return int(conn.execute(
                f"SELECT COUNT(*) FROM proposals{where}", params
            ).fetchone()[0])

    def proposal_queue(self, states: str | Sequence[str] | None = None, *,
                       actionable_only: bool = False,
                       due_on: str | None = None, limit: int = 500,
                       offset: int = 0) -> dict:
        """Return an exact-count, SQL-filtered proposal page.

        ``actionable_only`` removes only future DEFERRED rows before LIMIT is
        applied.  A missing or malformed defer date is fail-safe actionable,
        matching the human inbox policy.  Exact totals make it impossible for
        a 1,000-row sample to falsely report an empty queue.
        """
        if not 1 <= int(limit) <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        if int(offset) < 0:
            raise ValueError("offset must be non-negative")
        due_on = due_on or datetime.now(timezone.utc).date().isoformat()
        if not re_full_date(due_on):
            raise ValueError("due_on must be YYYY-MM-DD")
        base_clauses, base_params = self._proposal_state_filter(states)
        base_where = (
            " WHERE " + " AND ".join(base_clauses) if base_clauses else ""
        )
        visible_clauses = list(base_clauses)
        visible_params = list(base_params)
        if actionable_only:
            visible_clauses.append(
                "(state!='DEFERRED' OR defer_until IS NULL "
                "OR date(defer_until) IS NULL OR date(defer_until)<=date(?))"
            )
            visible_params.append(due_on)
        visible_where = (
            " WHERE " + " AND ".join(visible_clauses) if visible_clauses else ""
        )
        future_clauses = list(base_clauses) + [
            "state='DEFERRED'", "date(defer_until) IS NOT NULL",
            "date(defer_until)>date(?)",
        ]
        future_params = [*base_params, due_on]
        future_where = " WHERE " + " AND ".join(future_clauses)
        with self._connect() as conn:
            total_before = int(conn.execute(
                f"SELECT COUNT(*) FROM proposals{base_where}", base_params
            ).fetchone()[0])
            total_matching = int(conn.execute(
                f"SELECT COUNT(*) FROM proposals{visible_where}", visible_params
            ).fetchone()[0])
            hidden_future = int(conn.execute(
                f"SELECT COUNT(*) FROM proposals{future_where}", future_params
            ).fetchone()[0]) if actionable_only else 0
            rows = conn.execute(
                f"SELECT * FROM proposals{visible_where} "
                "ORDER BY created_at ASC, rowid ASC LIMIT ? OFFSET ?",
                [*visible_params, int(limit), int(offset)],
            ).fetchall()
        proposals = [self._proposal_row(row) for row in rows]
        return {
            "proposals": proposals,
            "total_matching": total_matching,
            "total_before_actionability": total_before,
            "hidden_future_deferred": hidden_future,
            "truncated": int(offset) + len(proposals) < total_matching,
            "limit": int(limit),
            "offset": int(offset),
            "due_on": due_on,
        }

    def proposal_queue_summary(self, due_on: str | None = None) -> dict:
        """Return exact proposal-state and due-deferred counts in one read."""
        due_on = due_on or datetime.now(timezone.utc).date().isoformat()
        if not re_full_date(due_on):
            raise ValueError("due_on must be YYYY-MM-DD")
        with self._connect() as conn:
            counts = {
                row["state"]: int(row["n"])
                for row in conn.execute(
                    "SELECT state,COUNT(*) AS n FROM proposals GROUP BY state"
                ).fetchall()
            }
            due_deferred = int(conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE state='DEFERRED' AND "
                "(defer_until IS NULL OR date(defer_until) IS NULL "
                "OR date(defer_until)<=date(?))", (due_on,),
            ).fetchone()[0])
            future_deferred = int(conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE state='DEFERRED' "
                "AND date(defer_until) IS NOT NULL "
                "AND date(defer_until)>date(?)", (due_on,),
            ).fetchone()[0])
        return {
            "counts": counts,
            "due_deferred": due_deferred,
            "future_deferred": future_deferred,
            "human_gate_count": (
                counts.get("PENDING", 0) + due_deferred
                + counts.get("APPLY_FAILED", 0)
            ),
            "due_on": due_on,
        }

    def transition_proposal(self, proposal_id: str, decision: str,
                            actor: str = "local-operator", reason: str | None = None,
                            defer_until: str | None = None,
                            expected_revision: int | None = None) -> dict:
        rows = self.transition_proposals(
            [proposal_id], decision, actor=actor, reason=reason,
            defer_until=defer_until,
            expected_revisions=(
                {proposal_id: expected_revision}
                if expected_revision is not None else None
            ),
        )
        return rows[0]

    def transition_proposals(self, proposal_ids: Sequence[str], decision: str,
                             actor: str = "local-operator",
                             reason: str | None = None,
                             defer_until: str | None = None,
                             expected_revisions: dict[str, int] | None = None) -> list[dict]:
        """Atomically reject/defer/system-resolve a proposal group."""
        ids = list(dict.fromkeys(proposal_ids))
        if not ids:
            raise ValueError("proposal_ids must not be empty")
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        reason = redact_persisted_text(reason)
        defer_until = redact_persisted_text(defer_until)
        mapping = {
            "reject": "REJECTED", "defer": "DEFERRED", "expire": "EXPIRED",
            "system_reject": "SYSTEM_REJECTED", "supersede": "SUPERSEDED",
        }
        target = mapping.get(decision.lower(), decision.upper())
        if target not in PROPOSAL_STATES or target in {"APPLYING", "APPLIED"}:
            raise ValueError("approval must use dream_apply.decide_proposal; invalid transition")
        with self._tx() as conn:
            marks = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
            missing = [pid for pid in ids if pid not in by_id]
            if missing:
                raise NotFoundError(f"proposal(s) not found: {missing}")
            for pid in ids:
                row = by_id[pid]
                if row["state"] == target:
                    continue
                if row["state"] in PROPOSAL_TERMINAL_STATES:
                    raise ConflictError(f"proposal {pid} is already {row['state']}")
                expected = (expected_revisions or {}).get(pid)
                if expected is not None and row["revision"] != expected:
                    raise ConflictError(
                        f"proposal {pid} revision changed: expected {expected}, "
                        f"got {row['revision']}"
                    )
            now = utc_now()
            for pid in ids:
                if by_id[pid]["state"] == target:
                    continue
                conn.execute(
                    "UPDATE proposals SET state=?,revision=revision+1,reason=?,actor=?,"
                    "defer_until=?,updated_at=? WHERE proposal_id=?",
                    (target, reason, actor, defer_until, now, pid),
                )
                self._event(conn, "proposal", pid, target, actor,
                            {"reason": reason, "defer_until": defer_until})
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
        return [self._proposal_row(by_id[pid]) for pid in ids]

    def claim_proposals(self, proposal_ids: Sequence[str], actor: str,
                        expected_revision: int | None = None,
                        expected_revisions: dict[str, int] | None = None) -> list[dict]:
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        ids = list(dict.fromkeys(proposal_ids))
        if not ids:
            raise ValueError("proposal_ids must not be empty")
        with self._tx() as conn:
            marks = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
            missing = [pid for pid in ids if pid not in by_id]
            if missing:
                raise NotFoundError(f"proposal(s) not found: {missing}")
            if all(by_id[pid]["state"] == "APPLIED" for pid in ids):
                return [self._proposal_row(by_id[pid]) for pid in ids]
            for pid in ids:
                row = by_id[pid]
                if row["state"] not in {"PENDING", "DEFERRED"}:
                    raise ConflictError(f"proposal {pid} cannot be claimed from {row['state']}")
                expected = (expected_revisions or {}).get(pid)
                if expected is None and expected_revision is not None and pid == ids[0]:
                    expected = expected_revision
                if expected is not None and row["revision"] != expected:
                    raise ConflictError(
                        f"proposal revision changed: expected {expected}, got {row['revision']}"
                    )
                parent = conn.execute(
                    "SELECT state FROM attempts WHERE attempt_id=?",
                    (row["attempt_id"],),
                ).fetchone()
                if not parent or parent["state"] not in CONSUMABLE_OUTCOMES:
                    raise ConflictError(
                        f"proposal {pid} parent attempt is not successfully complete"
                    )
            now = utc_now()
            for pid in ids:
                conn.execute(
                    "UPDATE proposals SET state='APPLYING',revision=revision+1,actor=?,"
                    "reason=NULL,updated_at=? WHERE proposal_id=?", (actor, now, pid),
                )
                self._event(conn, "proposal", pid, "APPLYING", actor)
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
        return [self._proposal_row(by_id[pid]) for pid in ids]

    def finalize_proposals(self, proposal_ids: Sequence[str], succeeded: bool,
                           actor: str, result=None, reason: str | None = None) -> list[dict]:
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        reason = redact_persisted_text(reason)
        result = redact_persisted_value(result)
        ids = list(dict.fromkeys(proposal_ids))
        target = "APPLIED" if succeeded else "APPLY_FAILED"
        with self._tx() as conn:
            marks = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
            if len(by_id) != len(ids):
                raise NotFoundError("one or more proposals disappeared while finalizing")
            for pid in ids:
                if by_id[pid]["state"] == target:
                    continue
                if by_id[pid]["state"] != "APPLYING":
                    raise ConflictError(
                        f"proposal {pid} cannot finalize from {by_id[pid]['state']}"
                    )
                conn.execute(
                    "UPDATE proposals SET state=?,revision=revision+1,actor=?,reason=?,"
                    "result_json=?,updated_at=? WHERE proposal_id=?",
                    (target, actor, reason, _json(result) if result is not None else None,
                     utc_now(), pid),
                )
                self._event(conn, "proposal", pid, target, actor,
                            {"reason": reason, "result": result})
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE proposal_id IN ({marks})", ids
            ).fetchall()
            by_id = {row["proposal_id"]: row for row in rows}
        return [self._proposal_row(by_id[pid]) for pid in ids]

    def acknowledge_attempt(self, attempt_id: str,
                            actor: str = "local-operator") -> dict:
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if not row:
                raise NotFoundError(f"attempt not found: {attempt_id}")
            if row["state"] not in {"FAILED", "BLOCKED", "CANCELLED"}:
                raise ConflictError("only failed/blocked/cancelled attempts need acknowledgement")
            if not row["acknowledged_at"]:
                now = utc_now()
                conn.execute(
                    "UPDATE attempts SET acknowledged_at=?,acknowledged_by=? WHERE attempt_id=?",
                    (now, actor, attempt_id),
                )
                self._event(conn, "attempt", attempt_id, "ACKNOWLEDGED", actor)
            updated = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
        return self._attempt_row(updated)

    def archive_run(self, run_id: str, actor: str = "local-operator") -> dict:
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise NotFoundError(f"run not found: {run_id}")
            if row["state"] in {"QUEUED", "RUNNING"}:
                raise ConflictError("an active run cannot be archived")
            if not row["archived_at"]:
                now = utc_now()
                conn.execute(
                    "UPDATE runs SET archived_at=?,archived_by=? WHERE run_id=?",
                    (now, actor, run_id),
                )
                self._event(conn, "run", run_id, "ARCHIVED", actor)
            updated = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(updated)

    def request_cancel(self, run_id: str, actor: str = "local-operator") -> dict:
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise NotFoundError(f"run not found: {run_id}")
            if not row["cancel_requested_at"]:
                now = utc_now()
                conn.execute(
                    "UPDATE runs SET cancel_requested_at=?,cancel_requested_by=? WHERE run_id=?",
                    (now, actor, run_id),
                )
                self._event(conn, "run", run_id, "CANCEL_REQUESTED", actor)
            updated = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(updated)

    def finalize_run(self, run_id: str, state: str | None = None,
                     summary: dict | None = None, actor: str = "system") -> dict:
        """Explicitly finalize a controller-owned run.

        ``state=None`` recomputes from attempts.  An explicit terminal state
        is used for controller-only operations such as digest publication,
        whose failure can downgrade an otherwise successful five-pass run.
        """
        actor = (redact_persisted_text(actor) or "system")[:256]
        summary = redact_persisted_value(summary or {})
        if state is not None:
            state = state.upper()
            if state not in RUN_STATES - {"QUEUED", "RUNNING"}:
                raise ValueError(f"terminal run state required, got {state!r}")
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise NotFoundError(f"run not found: {run_id}")
            if state is None:
                self._aggregate_run(conn, run_id)
            else:
                conn.execute(
                    "UPDATE runs SET state=?,summary_json=?,finished_at=? WHERE run_id=?",
                    (state, _json(summary), utc_now(), run_id),
                )
                self._event(conn, "run", run_id, f"FINALIZED_{state}", actor,
                            {"summary": summary})
            updated = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(updated)

    def finalize_cancelled_run(self, run_id: str,
                               actor: str = "local-operator") -> dict:
        """Cancel active attempts and terminate a run even with unstarted passes."""
        actor = (redact_persisted_text(actor) or "local-operator")[:256]
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise NotFoundError(f"run not found: {run_id}")
            now = utc_now()
            active = conn.execute(
                "SELECT attempt_id FROM attempts WHERE run_id=? AND state IN ('QUEUED','RUNNING')",
                (run_id,),
            ).fetchall()
            for attempt in active:
                conn.execute(
                    "UPDATE attempts SET state='CANCELLED',finished_at=?,exit_code=4 "
                    "WHERE attempt_id=?", (now, attempt["attempt_id"]),
                )
                self._event(conn, "attempt", attempt["attempt_id"], "CANCELLED", actor,
                            {"reason": "run_cancelled"})
            conn.execute(
                "UPDATE runs SET state='CANCELLED',cancel_requested_at=COALESCE("
                "cancel_requested_at,?),cancel_requested_by=COALESCE(cancel_requested_by,?),"
                "finished_at=? WHERE run_id=?", (now, actor, now, run_id),
            )
            self._event(conn, "run", run_id, "CANCELLED", actor,
                        {"active_attempts_cancelled": len(active)})
            updated = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(updated)

    def record_operation(self, run_id: str, operation: str, state: str,
                         summary: dict | None = None, actor: str = "system") -> None:
        """Append a typed controller operation event (digest, cleanup, export)."""
        state = state.upper()
        actor = (redact_persisted_text(actor) or "system")[:256]
        summary = redact_persisted_value(summary or {})
        with self._tx() as conn:
            if not conn.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
                raise NotFoundError(f"run not found: {run_id}")
            self._event(conn, "run", run_id, f"OP_{operation.upper()}_{state}", actor,
                        {"operation": operation, "state": state,
                         "summary": summary})

    def finalize_cycle(self, run_id: str, digest_exit_code: int,
                       actor: str = "cycle-controller") -> dict:
        """Record digest publication and preserve/downgrade aggregate status."""
        with self._tx() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise NotFoundError(f"run not found: {run_id}")
            now = utc_now()
            stranded = conn.execute(
                "SELECT attempt_id FROM attempts WHERE run_id=? AND state IN ('QUEUED','RUNNING')",
                (run_id,),
            ).fetchall()
            for attempt in stranded:
                conn.execute(
                    "UPDATE attempts SET state='BLOCKED',finished_at=?,exit_code=124,"
                    "error_type='ControllerDeadline',error_text='cycle ended before attempt "
                    "reported a terminal state' WHERE attempt_id=?",
                    (now, attempt["attempt_id"]),
                )
                self._event(conn, "attempt", attempt["attempt_id"], "BLOCKED", actor,
                            {"reason": "controller_deadline_or_interruption"})
            if stranded:
                self._aggregate_run(conn, run_id)
                row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            digest_state = "SUCCEEDED" if digest_exit_code == 0 else "FAILED"
            self._event(conn, "run", run_id, f"OP_DIGEST_{digest_state}", actor,
                        {"operation": "digest", "exit_code": digest_exit_code})
            current = row["state"]
            if digest_exit_code != 0 and current == "SUCCEEDED":
                current = "DEGRADED"
            elif current in {"QUEUED", "RUNNING"}:
                # Missing requested attempts at controller finalization is an
                # incomplete cycle, never a success.
                current = "DEGRADED" if digest_exit_code == 0 else "FAILED"
            # SPEC-subpass-outcomes-2026-08 SS5.3: merge, do not clobber,
            # so passes_good/passes_total from _aggregate_run survive.
            prior_summary = _loads(row["summary_json"], {})
            conn.execute(
                "UPDATE runs SET state=?,finished_at=COALESCE(finished_at,?),"
                "summary_json=? WHERE run_id=?",
                (current, now, _json({**prior_summary, "digest_exit_code": digest_exit_code,
                                      "stranded_attempts_reconciled": len(stranded)}), run_id),
            )
            updated = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(updated)

    @staticmethod
    def _effective_controller_deadline(run: sqlite3.Row,
                                       attempts: Sequence[sqlite3.Row]) -> datetime | None:
        candidates: list[datetime] = []
        if run["deadline_at"]:
            try:
                candidates.append(_as_utc(run["deadline_at"]))
            except (TypeError, ValueError):
                pass
        if not candidates:
            lease = _lease_from_config(_loads(run["config_json"], {}))
            if lease is not None:
                try:
                    candidates.append(
                        _as_utc(run["created_at"]) + timedelta(seconds=lease)
                    )
                except (TypeError, ValueError):
                    pass
        for attempt in attempts:
            if attempt["lease_expires_at"]:
                try:
                    candidates.append(_as_utc(attempt["lease_expires_at"]))
                    continue
                except (TypeError, ValueError):
                    pass
            lease = _lease_from_config(_loads(attempt["config_json"], {}))
            if lease is not None:
                try:
                    base = attempt["started_at"] or attempt["created_at"]
                    candidates.append(_as_utc(base) + timedelta(seconds=lease))
                except (TypeError, ValueError):
                    pass
        # All attempt leases are bounded by the operation lease.  The
        # earliest known deadline is therefore the conservative fence.
        return min(candidates) if candidates else None

    @classmethod
    def _recover_orphaned_controller_work_tx(
            cls, conn: sqlite3.Connection, *, owned_run_ids: Sequence[str],
            now: datetime, grace_seconds: float,
            actor: str) -> dict:
        owned = {str(run_id) for run_id in owned_run_ids}
        active_runs = conn.execute(
            "SELECT * FROM runs WHERE archived_at IS NULL "
            "AND state IN ('QUEUED','RUNNING') ORDER BY created_at ASC"
        ).fetchall()
        recovered_attempt_ids: list[str] = []
        recovered_run_ids: list[str] = []
        unowned_active: list[dict] = []
        stamp = _utc_iso(now)
        for run in active_runs:
            run_id = run["run_id"]
            if run_id in owned:
                continue
            attempts = conn.execute(
                "SELECT * FROM attempts WHERE run_id=? "
                "AND state IN ('QUEUED','RUNNING') ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
            deadline = cls._effective_controller_deadline(run, attempts)
            grace_deadline = (
                deadline + timedelta(seconds=grace_seconds)
                if deadline is not None else None
            )
            # The source does not establish process ownership after a crash.
            # A known, bounded canonical deadline does.  GUI, scheduled, and
            # expert CLI runs are all fenced the same way once that deadline
            # plus grace has elapsed; no PID is inspected or killed.
            recoverable = grace_deadline is not None and now > grace_deadline
            if not recoverable:
                unowned_active.append({
                    "run_id": run_id,
                    "run_state": run["state"],
                    "source": run["source"],
                    "owner": "unowned",
                    "attempt_ids": [row["attempt_id"] for row in attempts],
                    "deadline_at": _utc_iso(deadline) if deadline else None,
                    "grace_deadline_at": (
                        _utc_iso(grace_deadline) if grace_deadline else None
                    ),
                    "deadline_known": deadline is not None,
                    "within_grace": bool(
                        deadline is not None and now > deadline
                        and grace_deadline is not None and now <= grace_deadline
                    ),
                    "auto_recoverable": deadline is not None,
                })
                continue

            reason = "controller lease expired after ownership was lost"
            for attempt in attempts:
                attempt_id = attempt["attempt_id"]
                conn.execute(
                    "UPDATE attempts SET state='BLOCKED',finished_at=?,exit_code=124,"
                    "error_type='ControllerLeaseExpired',error_text=? "
                    "WHERE attempt_id=? AND state IN ('QUEUED','RUNNING')",
                    (stamp, redact_persisted_text(reason), attempt_id),
                )
                proposal_rows = conn.execute(
                    "SELECT proposal_id FROM proposals WHERE attempt_id=? "
                    "AND state IN ('STAGED','PENDING','DEFERRED')",
                    (attempt_id,),
                ).fetchall()
                for proposal in proposal_rows:
                    proposal_id = proposal["proposal_id"]
                    proposal_reason = "parent_attempt_blocked:controller_lease_expired"
                    conn.execute(
                        "UPDATE proposals SET state='SYSTEM_REJECTED',"
                        "revision=revision+1,reason=?,actor=?,updated_at=? "
                        "WHERE proposal_id=?",
                        (proposal_reason, actor, stamp, proposal_id),
                    )
                    cls._event(
                        conn, "proposal", proposal_id, "SYSTEM_REJECTED", actor,
                        {"reason": proposal_reason},
                    )
                cls._event(
                    conn, "attempt", attempt_id, "BLOCKED", actor,
                    {"reason": "controller_lease_expired",
                     "deadline_at": _utc_iso(deadline)},
                )
                recovered_attempt_ids.append(attempt_id)
            requested_passes = _loads(run["requested_passes_json"], [])
            existing_passes = {
                row["pass_name"] for row in conn.execute(
                    "SELECT pass_name FROM attempts WHERE run_id=?", (run_id,)
                ).fetchall()
            }
            missing_passes = [
                pass_name for pass_name in requested_passes
                if pass_name not in existing_passes
            ]
            for pass_name in missing_passes:
                synthetic_id = new_id("attempt")
                attempt_no = conn.execute(
                    "SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts "
                    "WHERE run_id=? AND pass_name=?", (run_id, pass_name),
                ).fetchone()[0]
                message = "not started before controller lease expired"
                conn.execute(
                    "INSERT INTO attempts(attempt_id,run_id,pass_name,attempt_no,"
                    "retry_of,state,config_json,summary_json,artifacts_json,"
                    "error_type,error_text,exit_code,created_at,started_at,"
                    "lease_expires_at,finished_at) "
                    "VALUES(?,?,?,?,NULL,'BLOCKED','{}',?,'{}',?,?,124,?,NULL,?,?)",
                    (synthetic_id, run_id, pass_name, attempt_no,
                     _json({"message": message, "not_started": True}),
                     "ControllerLeaseExpired", redact_persisted_text(message),
                     stamp, _utc_iso(deadline), stamp),
                )
                cls._event(
                    conn, "attempt", synthetic_id,
                    "SYNTHETIC_BLOCKED_NOT_STARTED", actor,
                    {"reason": "controller_lease_expired",
                     "pass": pass_name, "deadline_at": _utc_iso(deadline)},
                )
                recovered_attempt_ids.append(synthetic_id)
            summary = _loads(run["summary_json"], {})
            summary.update({
                "recovery": "controller_lease_expired",
                "recovered_at": stamp,
                "deadline_at": _utc_iso(deadline),
                "attempts_blocked": len(attempts) + len(missing_passes),
                "not_started_passes": missing_passes,
            })
            conn.execute(
                "UPDATE runs SET state='BLOCKED',summary_json=?,finished_at=? "
                "WHERE run_id=? AND state IN ('QUEUED','RUNNING')",
                (_json(summary), stamp, run_id),
            )
            cls._event(
                conn, "run", run_id, "RECOVERED_BLOCKED", actor,
                {"reason": "controller_lease_expired",
                 "deadline_at": _utc_iso(deadline),
                 "attempts_blocked": len(attempts) + len(missing_passes),
                 "not_started_passes": missing_passes},
            )
            recovered_run_ids.append(run_id)
        return {
            "recovered_attempt_ids": recovered_attempt_ids,
            "recovered_run_ids": recovered_run_ids,
            "unowned_active": unowned_active,
            "checked_at": stamp,
            "grace_seconds": grace_seconds,
        }

    def recover_orphaned_controller_work(
            self, *, owned_run_ids: Sequence[str] = (),
            now: datetime | str | None = None,
            grace_seconds: float = DEFAULT_RECOVERY_GRACE_SECONDS,
            actor: str = "gui-controller-recovery") -> dict:
        """Recover expired controller work and expose still-live unowned leases.

        This method never inspects or kills a PID.  It uses only canonical UTC
        deadlines. Runs inside their deadline/grace remain active and are
        returned as ``unowned_active`` so admission can fail closed. Any run
        with a known deadline older than the grace fence is terminalized;
        deadline-less work remains unowned and requires expert reconciliation.
        """
        grace = float(grace_seconds)
        if not 0 <= grace <= MAX_RECOVERY_GRACE_SECONDS:
            raise ValueError(
                f"grace_seconds must be between 0 and {MAX_RECOVERY_GRACE_SECONDS}"
            )
        current = _as_utc(now or datetime.now(timezone.utc))
        with self._tx() as conn:
            return self._recover_orphaned_controller_work_tx(
                conn, owned_run_ids=owned_run_ids, now=current,
                grace_seconds=grace, actor=redact_persisted_text(actor),
            )

    def recover_stale_applying(self, older_than: str,
                               actor: str = "system-recovery") -> int:
        """Fail closed any abandoned APPLYING claims older than an ISO timestamp.

        TRAUM never guesses whether an external write completed after a worker
        crash.  It surfaces ``APPLY_FAILED`` for operator reconciliation; it
        does not automatically replay a potentially non-idempotent semantic
        write.
        """
        cutoff = _as_utc(older_than)
        actor = (redact_persisted_text(actor) or "system-recovery")[:256]
        with self._tx() as conn:
            candidates = conn.execute(
                "SELECT proposal_id,updated_at FROM proposals WHERE state='APPLYING'"
            ).fetchall()
            rows = []
            for row in candidates:
                try:
                    if _as_utc(row["updated_at"]) < cutoff:
                        rows.append(row)
                except (TypeError, ValueError):
                    # A malformed timestamp is not safe evidence that a live
                    # external write can be replayed or reconciled.
                    continue
            now = utc_now()
            for row in rows:
                pid = row["proposal_id"]
                conn.execute(
                    "UPDATE proposals SET state='APPLY_FAILED',revision=revision+1,"
                    "reason='worker_interrupted_reconcile_before_retry',actor=?,updated_at=? "
                    "WHERE proposal_id=?", (actor, now, pid),
                )
                self._event(conn, "proposal", pid, "APPLY_FAILED", actor,
                            {"reason": "worker_interrupted_reconcile_before_retry"})
        return len(rows)

    def expire_stale_proposals(self, stale_days: int = 14,
                               now: datetime | None = None,
                               actor: str = "system-expiry") -> int:
        """Expire old PENDING/DEFERRED proposals deterministically."""
        if stale_days < 0:
            raise ValueError("stale_days must be non-negative")
        current = _as_utc(now or datetime.now(timezone.utc))
        cutoff_dt = current - timedelta(days=stale_days)
        cutoff = _utc_iso(cutoff_dt)
        actor = (redact_persisted_text(actor) or "system-expiry")[:256]
        with self._tx() as conn:
            candidates = conn.execute(
                "SELECT proposal_id,created_at FROM proposals "
                "WHERE state IN ('PENDING','DEFERRED')"
            ).fetchall()
            rows = []
            for row in candidates:
                try:
                    if _as_utc(row["created_at"]) < cutoff_dt:
                        rows.append(row)
                except (TypeError, ValueError):
                    # Fail closed: malformed metadata is surfaced, not aged
                    # out based on an unsafe lexical guess.
                    continue
            stamp = _utc_iso(current)
            for row in rows:
                pid = row["proposal_id"]
                conn.execute(
                    "UPDATE proposals SET state='EXPIRED',revision=revision+1,"
                    "reason=?,actor=?,updated_at=? WHERE proposal_id=?",
                    (f"stale>{stale_days}d", actor, stamp, pid),
                )
                self._event(conn, "proposal", pid, "EXPIRED", actor,
                            {"reason": f"stale>{stale_days}d", "cutoff": cutoff})
        return len(rows)

    @staticmethod
    def _legacy_jsonl(path: str) -> list[dict]:
        out = []
        try:
            with open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        out.append(value)
        except OSError:
            pass
        return out

    def import_legacy_day(self, day_dir: str) -> dict | None:
        """Import only pre-state records from a date directory.

        Canonical artifacts carry run/attempt IDs and are deliberately ignored
        so this bridge cannot manufacture a duplicate "legacy" run every time
        a modern artifact changes.
        """
        day_dir = os.path.abspath(day_dir)
        day = os.path.basename(day_dir)
        try:
            datetime.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(f"not a TRAUM YYYY-MM-DD day directory: {day_dir}") from exc
        names = sorted(os.listdir(day_dir))
        def is_canonical_record(item: dict) -> bool:
            return bool(item.get("run_id") and item.get("attempt_id"))

        crashes = [
            item for item in self._legacy_jsonl(os.path.join(day_dir, "crashes.jsonl"))
            if not is_canonical_record(item)
        ]
        blocked = [
            item for item in self._legacy_jsonl(os.path.join(day_dir, "blocked.jsonl"))
            if not is_canonical_record(item)
        ]
        nulls = [
            item for item in self._legacy_jsonl(os.path.join(day_dir, "null-results.jsonl"))
            if not is_canonical_record(item)
        ]
        proposals = []
        proposal_names = []
        for name in names:
            if not (name.startswith("proposals") and name.endswith(".jsonl")):
                continue
            eligible = [
                item for item in self._legacy_jsonl(os.path.join(day_dir, name))
                if not is_canonical_record(item) and not item.get("proposal_id")
            ]
            if eligible:
                proposal_names.append(name)
                proposals.extend(eligible)
        report_names = []
        report_texts = []
        for name in names:
            if not (name.startswith("report") and name.endswith(".md")):
                continue
            try:
                with open(os.path.join(day_dir, name), "rt", encoding="utf-8",
                          errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            canonical_header = (
                "Run ID: `run_" in text and "Attempt ID: `att_" in text
            )
            if canonical_header or "-att_" in name:
                continue
            report_names.append(name)
            report_texts.append(text)
        if not any((crashes, blocked, nulls, proposals, report_names)):
            return None

        def legacy_decisions(filename: str) -> list[dict]:
            return [
                item for item in self._legacy_jsonl(os.path.join(day_dir, filename))
                if isinstance(item.get("proposal"), dict)
                and not is_canonical_record(item["proposal"])
                and not item["proposal"].get("proposal_id")
            ]
        applied_entries = [
            item for item in legacy_decisions("applied.jsonl")
            if item.get("dry_run") is False
        ]
        rejected_entries = legacy_decisions("rejected.jsonl")
        expired_entries = legacy_decisions("expired.jsonl")

        path_hash = hashlib.sha256(day_dir.encode("utf-8")).hexdigest()[:12]
        run_id = f"legacy_{day.replace('-', '')}_{path_hash}"
        run = self.create_run("legacy", ["legacy"], {"day": day},
                              source="legacy-import", run_id=run_id)
        snapshot = hashlib.sha256()
        snapshot.update(_json({
            "crashes": crashes, "blocked": blocked, "nulls": nulls,
            "proposals": proposals, "reports": report_texts,
            "applied": applied_entries, "rejected": rejected_entries,
            "expired": expired_entries,
        }).encode("utf-8"))
        attempt_id = f"att_legacy_{snapshot.hexdigest()[:20]}"
        existing = self.get_attempt(attempt_id)
        if existing:
            return {"run": self.get_run(run_id), "attempt": existing, "imported": False}
        attempt = self.start_attempt(
            run_id, "legacy", config={"day": day}, attempt_id=attempt_id
        )
        applied_fp = {proposal_fingerprint(item["proposal"]) for item in applied_entries}
        rejected_fp = {proposal_fingerprint(item["proposal"]) for item in rejected_entries}
        expired_fp = {proposal_fingerprint(item["proposal"]) for item in expired_entries}
        annotated = []
        for proposal in proposals:
            item = dict(proposal)
            fingerprint = proposal_fingerprint(item)
            if fingerprint in applied_fp:
                item.update(_initial_state="APPLIED", _initial_reason="legacy_applied")
            elif fingerprint in rejected_fp:
                item.update(_initial_state="REJECTED", _initial_reason="legacy_rejected")
            elif fingerprint in expired_fp:
                item.update(_initial_state="EXPIRED", _initial_reason="legacy_expired")
            annotated.append(item)
        proposal_rows = self.record_proposals(
            run_id, attempt_id, annotated
        ) if annotated else []
        failed_banner = any("## FAILED" in text[:8192] for text in report_texts)
        if crashes or failed_banner:
            outcome = "FAILED"
        elif blocked:
            outcome = "BLOCKED"
        elif nulls and not proposal_rows:
            outcome = "NULL"
        else:
            outcome = "SUCCEEDED"
        error = None
        if outcome == "FAILED":
            error = "legacy crash/failure artifact"
        elif outcome == "BLOCKED":
            error = "legacy blocked artifact"
        attempt = self.finish_attempt(
            attempt_id, outcome,
            summary={
                "legacy": True, "crashes": len(crashes), "blocked": len(blocked),
                "nulls": len(nulls), "proposals": len(proposal_rows),
                "applied": len(applied_fp), "rejected": len(rejected_fp),
                "expired": len(expired_fp),
            },
            artifacts={
                "day": day, "reports": report_names,
                "proposals": proposal_names,
            }, error=error,
        )
        return {"run": self.get_run(run_id), "attempt": attempt, "imported": True}

    def reconcile_legacy_days(self, dream_dir: str) -> list[dict]:
        """Import every date directory; idempotent by path/content-derived IDs."""
        if not os.path.isdir(dream_dir):
            return []
        results = []
        for name in sorted(os.listdir(dream_dir)):
            if not re_full_date(name):
                continue
            day_dir = os.path.join(dream_dir, name)
            if os.path.isdir(day_dir):
                result = self.import_legacy_day(day_dir)
                if result is not None:
                    results.append(result)
        return results

    def is_cancel_requested(self, run_id: str) -> bool:
        row = self.get_run(run_id)
        return bool(row and row["cancel_requested"])

    def events(self, entity_kind: str | None = None, entity_id: str | None = None,
               after_event_id: int = 0, limit: int = 1000) -> list[dict]:
        clauses, params = ["event_id>?"], [after_event_id]
        if entity_kind:
            clauses.append("entity_kind=?")
            params.append(entity_kind)
        if entity_id:
            clauses.append("entity_id=?")
            params.append(entity_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE " + " AND ".join(clauses) +
                " ORDER BY event_id ASC LIMIT ?", [*params, limit],
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = _loads(item.pop("payload_json"), {})
            out.append(item)
        return out


__all__ = [
    "ATTEMPT_STATES", "ATTEMPT_TERMINAL_STATES", "CONSUMABLE_OUTCOMES",
    "ConflictError", "NotFoundError", "PROPOSAL_STATES",
    "PROPOSAL_TERMINAL_STATES", "RUN_STATES", "TraumState",
    "TraumStateError", "canonical_proposal", "default_db_path",
    "document_token", "new_id", "proposal_fingerprint", "utc_now",
    "redact_persisted_text", "redact_persisted_value",
]


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="traum_state.py")
    sub = parser.add_subparsers(dest="command", required=True)
    finalize = sub.add_parser("finalize-cycle")
    finalize.add_argument("--db", required=True)
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--digest-exit", type=int, required=True)
    cancel = sub.add_parser("cancel-run")
    cancel.add_argument("--db", required=True)
    cancel.add_argument("--run-id", required=True)
    cancel.add_argument("--actor", default="cycle-signal")
    expire = sub.add_parser("expire-stale")
    expire.add_argument("--db", required=True)
    expire.add_argument("--stale-days", type=int, default=14)
    args = parser.parse_args(argv)
    if args.command == "finalize-cycle":
        store = TraumState(args.db)
        run = store.finalize_cycle(args.run_id, args.digest_exit)
        print(_json({"run_id": run["run_id"], "state": run["state"]}))
        return 0
    if args.command == "cancel-run":
        store = TraumState(args.db)
        run = store.finalize_cancelled_run(args.run_id, actor=args.actor)
        print(_json({"run_id": run["run_id"], "state": run["state"]}))
        return 0
    if args.command == "expire-stale":
        store = TraumState(args.db)
        count = store.expire_stale_proposals(args.stale_days)
        print(_json({"expired": count, "stale_days": args.stale_days}))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
