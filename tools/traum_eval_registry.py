#!/usr/bin/env python3
"""Offline registry and safety gates for TRAUM learning-lift evaluations.

This module deliberately has no HTTP client and no subprocess integration.  It
records immutable evaluation inputs, copies exports produced by isolated
workers, and computes paired statistics.  It cannot invoke TRAUM, Elasticsearch,
Goethe, or an auto-apply path.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import shutil
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


SPEC_SCHEMA = "traum.eval.spec.v2"
PLAN_SCHEMA = "traum.eval.plan.v2"
STATE_SCHEMA = "traum.eval.state.v2"
STATUS_SCHEMA = "traum.eval.status.v2"
REGISTRY_SCHEMA = "traum.eval.registry.v2"
CAPTURE_SCHEMA = "traum.eval.condition-export.v2"
TRIAL_SCHEMA = "traum.eval.trial.v2"
TRIAL_MANIFEST_SCHEMA = "traum.eval.trial-manifest.v2"
ANALYSIS_SCHEMA = "traum.eval.analysis.v2"
ATTESTATION_SCHEMA = "traum.eval.isolation.v1"
EVIDENCE_SCHEMA = "traum.continuous-evidence.v1"
EVIDENCE_SUMMARY_SCHEMA = "traum.continuous-evidence.summary.v1"

MIN_ELAPSED_FLOOR_SECONDS = 3600
DEFAULT_MIN_ELAPSED_SECONDS = 24 * 60 * 60
PRODUCTION_PORTS = frozenset({9200, 9700})
PRODUCTION_ROOTS = (
    "/opt",
    "/var/lib/elasticsearch",
    "/var/lib/docker",
)
PIN_NAMES = ("model", "prompt", "tool_schema", "retriever", "embedding", "dataset")
FILE_PIN_NAMES = ("prompt", "tool_schema", "retriever", "dataset")
METRIC_NAMES = (
    "suite_score",
    "max_suite_score",
    "tool_call_count",
    "wrong_kb_hits",
    "retrieval_recall_at_1",
    "retrieval_recall_at_3",
    "retrieval_mrr",
)
FUTURE_AUTO_APPLY_CANDIDATES = frozenset({"dedup-exact", "reverify"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVAL_ID_RE = re.compile(r"^traum-v2-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
_PROPOSAL_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class EvalError(RuntimeError):
    """Expected, machine-reportable workflow failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvalPaths:
    registry: Path
    eval_id: str

    @property
    def eval_dir(self) -> Path:
        return self.registry / "evaluations" / self.eval_id

    @property
    def plan(self) -> Path:
        return self.eval_dir / "plan.json"

    @property
    def identity(self) -> Path:
        return self.eval_dir / "identity.json"

    @property
    def state(self) -> Path:
        return self.eval_dir / "state.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    value = value or _now_utc()
    if value.tzinfo is None:
        raise EvalError("invalid_time", "timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EvalError("invalid_time", f"invalid UTC timestamp: {value!r}") from exc
    return _as_utc(parsed)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise EvalError("missing_file", f"required file does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError("invalid_json", f"cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvalError("invalid_json", f"expected a JSON object in {path}")
    return value


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{secrets.token_hex(6)}")
    try:
        with open(temp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write_bytes(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")


def _copy_stable(source: Path, destination: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if not source.is_file():
        raise EvalError("invalid_input", f"input is not a regular file: {source}")
    before = sha256_file(source)
    before_size = source.stat().st_size
    if destination.exists():
        existing = sha256_file(destination)
        if existing != before:
            raise EvalError("immutable_conflict", f"immutable destination already differs: {destination}")
        return {"path": str(destination), "sha256": existing, "size": destination.stat().st_size}

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.tmp-{secrets.token_hex(6)}")
    try:
        with open(source, "rb") as src, open(temp, "xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        after = sha256_file(source)
        copied = sha256_file(temp)
        if before != after or before != copied or source.stat().st_size != before_size:
            raise EvalError("input_changed", f"input changed while it was being frozen: {source}")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    return {"path": str(destination), "sha256": before, "size": before_size}


def _normalise_digest(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise EvalError("invalid_spec", f"{label} sha256 must be a string")
    digest = value.lower().removeprefix("sha256:")
    if not _SHA256_RE.fullmatch(digest):
        raise EvalError("invalid_spec", f"{label} sha256 must contain 64 hexadecimal characters")
    return digest


def _require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvalError("invalid_spec", f"{label} must be a non-empty string")
    return value.strip()


def _resolve_from(base: Path, value: Any, label: str) -> Path:
    raw = Path(_require_nonempty(value, label))
    if not raw.is_absolute():
        raw = base / raw
    try:
        return raw.resolve(strict=True)
    except OSError as exc:
        raise EvalError("missing_file", f"{label} cannot be resolved: {raw}") from exc


def _canonical_url(value: Any, label: str) -> str:
    raw = _require_nonempty(value, label)
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EvalError("unsafe_endpoint", f"{label} must be an explicit http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EvalError("unsafe_endpoint", f"{label} must not contain credentials, query parameters, or fragments")
    try:
        port = parsed.port
    except ValueError as exc:
        raise EvalError("unsafe_endpoint", f"{label} has an invalid port") from exc
    if port is None:
        raise EvalError("unsafe_endpoint", f"{label} must use an explicit, isolated port")
    if port in PRODUCTION_PORTS:
        raise EvalError(
            "production_endpoint",
            f"{label} uses hard-rejected production port {port}; an attestation cannot override this",
        )
    host = parsed.hostname.lower().rstrip(".")
    if host in {"0.0.0.0", "::"}:
        raise EvalError("unsafe_endpoint", f"{label} cannot target an unspecified/listen-all address")
    try:
        host_text = f"[{ipaddress.ip_address(host).compressed}]" if ":" in host else host
    except ValueError:
        host_text = host
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, f"{host_text}:{port}", path, "", ""))


def _canonical_root(value: Any, label: str) -> Path:
    root = Path(_require_nonempty(value, label))
    if not root.is_absolute():
        raise EvalError("unsafe_filesystem", f"{label} must be an absolute path")
    resolved = root.resolve(strict=False)
    normalised = str(resolved).replace("\\", "/").rstrip("/").casefold()
    if any(normalised == item or normalised.startswith(item + "/") for item in PRODUCTION_ROOTS):
        raise EvalError("production_filesystem", f"{label} overlaps a known production data root: {resolved}")
    if resolved == Path(resolved.anchor):
        raise EvalError("unsafe_filesystem", f"{label} cannot be a filesystem root")
    return resolved


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve(strict=False)
    right = right.resolve(strict=False)
    return left == right or left in right.parents or right in left.parents


def _resolve_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    if candidate != root.resolve(strict=False) and root.resolve(strict=False) not in candidate.parents:
        raise EvalError("unsafe_path", f"registry artifact escapes its evaluation directory: {relative}")
    return candidate


def _canonical_source(value: Any, label: str, condition_root: Path) -> Path:
    """Resolve an export source that must originate inside the attested sandbox.

    A capture is only causally meaningful if the bytes came from the disposable
    condition environment the attestation describes.  An unconstrained path lets
    an operator freeze production data (or another condition's data) while the
    manifest still claims isolation, so containment is enforced here rather than
    trusted.
    """
    if isinstance(value, Path):
        raw = value
    elif isinstance(value, str) and value.strip():
        raw = Path(value)
    else:
        raise EvalError("invalid_input", f"{label} must be a non-empty filesystem path")
    if not raw.is_absolute():
        raise EvalError("unsafe_path", f"{label} must be an absolute path")
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise EvalError("missing_file", f"{label} does not exist: {raw}") from exc
    if not resolved.is_file():
        raise EvalError("invalid_input", f"{label} is not a regular file: {resolved}")
    normalised = str(resolved).replace("\\", "/").casefold()
    if any(normalised == item or normalised.startswith(item + "/") for item in PRODUCTION_ROOTS):
        raise EvalError("production_filesystem", f"{label} reads from a production data root: {resolved}")
    root = condition_root.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise EvalError(
            "unsafe_path",
            f"{label} must live under the attested condition filesystem root {root}; got {resolved}",
        )
    return resolved


def _jsonl_ids(path: Path) -> dict[str, str] | None:
    """Best-effort ``_id`` -> line digest map for a corpus export."""
    mapped: dict[str, str] = {}
    try:
        with open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                if not isinstance(record, dict):
                    return None
                identifier = record.get("_id") or record.get("id")
                if not isinstance(identifier, str) or not identifier:
                    return None
                mapped[identifier] = _sha256_bytes(_canonical_bytes(record))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return mapped


def _corpus_delta(baseline: Path, candidate: Path) -> dict[str, Any]:
    """Describe what the learning window actually changed in the corpus."""
    before = _jsonl_ids(baseline)
    after = _jsonl_ids(candidate)
    if before is None or after is None:
        return {"comparable": False, "reason": "corpus exports are not id-keyed JSONL"}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(key for key in set(before) & set(after) if before[key] != after[key])
    return {
        "comparable": True,
        "baseline_documents": len(before),
        "candidate_documents": len(after),
        "added": len(added),
        "removed": len(removed),
        "modified": len(modified),
        "changed_document_ids": (added + removed + modified)[:100],
    }


def _validate_attestation(
    path: Path,
    condition: str,
    store_url: str,
    gateway_url: str,
    filesystem_root: Path,
) -> dict[str, Any]:
    value = _load_json(path)
    if value.get("schema_version") != ATTESTATION_SCHEMA:
        raise EvalError("invalid_attestation", f"{path} must use {ATTESTATION_SCHEMA}")
    expected = {
        "condition": condition,
        "store_url": store_url,
        "gateway_url": gateway_url,
        "filesystem_root": str(filesystem_root),
        "isolated": True,
        "disposable": True,
        "production_data": False,
        "production_writes": False,
        "auto_apply_enabled": False,
    }
    if set(value) != {"schema_version", *expected}:
        raise EvalError("invalid_attestation", f"attestation {path} contains missing or unregistered fields")
    for key, wanted in expected.items():
        actual = value.get(key)
        if key == "store_url" and isinstance(actual, str):
            actual = _canonical_url(actual, f"attestation {condition}.store_url")
        elif key == "gateway_url" and isinstance(actual, str):
            actual = _canonical_url(actual, f"attestation {condition}.gateway_url")
        elif key == "filesystem_root" and isinstance(actual, str):
            actual = str(_canonical_root(actual, f"attestation {condition}.filesystem_root"))
        if actual != wanted:
            raise EvalError("invalid_attestation", f"attestation {path} has {key}={actual!r}; expected {wanted!r}")
    return value


def _validate_spec(spec: dict[str, Any], spec_dir: Path, registry: Path) -> dict[str, Any]:
    if spec.get("schema_version") != SPEC_SCHEMA:
        raise EvalError("invalid_spec", f"spec must use schema_version={SPEC_SCHEMA!r}")
    if not set(spec) <= {"schema_version", "min_elapsed_seconds", "trial_seeds", "pins", "conditions", "gates"}:
        raise EvalError("invalid_spec", "spec contains unregistered top-level fields")

    min_elapsed = spec.get("min_elapsed_seconds", DEFAULT_MIN_ELAPSED_SECONDS)
    if isinstance(min_elapsed, bool) or not isinstance(min_elapsed, int):
        raise EvalError("invalid_spec", "min_elapsed_seconds must be an integer")
    if min_elapsed < MIN_ELAPSED_FLOOR_SECONDS:
        raise EvalError(
            "elapsed_window_too_short",
            f"min_elapsed_seconds must be at least {MIN_ELAPSED_FLOOR_SECONDS}; zero/minute-scale A/B runs are invalid",
        )

    seeds = spec.get("trial_seeds")
    if not isinstance(seeds, list) or len(seeds) < 3:
        raise EvalError("invalid_spec", "trial_seeds must contain at least three paired trial seeds")
    if any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seeds):
        raise EvalError("invalid_spec", "trial seeds must be non-negative integers")
    if len(set(seeds)) != len(seeds):
        raise EvalError("invalid_spec", "trial seeds must be unique")

    raw_pins = spec.get("pins")
    if not isinstance(raw_pins, dict) or set(raw_pins) != set(PIN_NAMES):
        raise EvalError("invalid_spec", f"pins must define exactly the required inputs: {', '.join(PIN_NAMES)}")
    pins: dict[str, Any] = {}
    for name in ("model", "embedding"):
        raw = raw_pins.get(name)
        if not isinstance(raw, dict) or set(raw) != {"id", "sha256"}:
            raise EvalError("invalid_spec", f"pins.{name} must be an object")
        pins[name] = {
            "id": _require_nonempty(raw.get("id"), f"pins.{name}.id"),
            "sha256": _normalise_digest(raw.get("sha256"), f"pins.{name}"),
        }
    for name in FILE_PIN_NAMES:
        raw = raw_pins.get(name)
        if not isinstance(raw, dict) or set(raw) != {"id", "path"}:
            raise EvalError("invalid_spec", f"pins.{name} must be an object")
        source = _resolve_from(spec_dir, raw.get("path"), f"pins.{name}.path")
        pins[name] = {
            "id": _require_nonempty(raw.get("id"), f"pins.{name}.id"),
            "source": source,
            "sha256": sha256_file(source),
        }

    raw_conditions = spec.get("conditions")
    if not isinstance(raw_conditions, dict) or set(raw_conditions) != {"A", "B"}:
        raise EvalError("invalid_spec", "conditions must contain exactly A and B")
    conditions: dict[str, Any] = {}
    for condition in ("A", "B"):
        raw = raw_conditions[condition]
        if not isinstance(raw, dict) or set(raw) != {"store_url", "gateway_url", "filesystem_root", "attestation"}:
            raise EvalError("invalid_spec", f"conditions.{condition} must be an object")
        store_url = _canonical_url(raw.get("store_url"), f"conditions.{condition}.store_url")
        gateway_url = _canonical_url(raw.get("gateway_url"), f"conditions.{condition}.gateway_url")
        if store_url == gateway_url:
            raise EvalError("unsafe_endpoint", f"condition {condition} store and gateway endpoints must differ")
        filesystem_root = _canonical_root(raw.get("filesystem_root"), f"conditions.{condition}.filesystem_root")
        attestation = _resolve_from(spec_dir, raw.get("attestation"), f"conditions.{condition}.attestation")
        _validate_attestation(attestation, condition, store_url, gateway_url, filesystem_root)
        conditions[condition] = {
            "store_url": store_url,
            "gateway_url": gateway_url,
            "filesystem_root": filesystem_root,
            "attestation": attestation,
        }

    if conditions["A"]["store_url"] == conditions["B"]["store_url"]:
        raise EvalError("unsafe_endpoint", "A and B stores must be separate")
    if conditions["A"]["gateway_url"] == conditions["B"]["gateway_url"]:
        raise EvalError("unsafe_endpoint", "A and B gateways must be separate")
    if _paths_overlap(conditions["A"]["filesystem_root"], conditions["B"]["filesystem_root"]):
        raise EvalError("unsafe_filesystem", "A and B filesystem roots must be disjoint")
    for condition in ("A", "B"):
        if _paths_overlap(registry, conditions[condition]["filesystem_root"]):
            raise EvalError("unsafe_filesystem", f"condition {condition} filesystem root must not overlap the registry")

    raw_gates = spec.get("gates", {})
    if not isinstance(raw_gates, dict):
        raise EvalError("invalid_spec", "gates must be an object")
    allowed_gate_names = {
        "suite_noninferiority_margin",
        "recall_noninferiority_margin",
        "mrr_noninferiority_margin",
        "minimum_tool_call_reduction",
        "maximum_wrong_hit_mean_increase",
        "maximum_wrong_hit_per_trial_increase",
        "maximum_wrong_hit_total_increase",
    }
    if not set(raw_gates) <= allowed_gate_names:
        raise EvalError("invalid_spec", "gates contains unregistered fields")
    for name, value in raw_gates.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise EvalError("invalid_spec", f"gates.{name} must be a finite number")
    for name in ("maximum_wrong_hit_per_trial_increase", "maximum_wrong_hit_total_increase"):
        if name in raw_gates and not isinstance(raw_gates[name], int):
            raise EvalError("invalid_spec", f"gates.{name} must be an integer")
    gates = {
        "confidence_level": 0.95,
        "suite_noninferiority_margin": float(raw_gates.get("suite_noninferiority_margin", 0.0)),
        "recall_noninferiority_margin": float(raw_gates.get("recall_noninferiority_margin", 0.02)),
        "mrr_noninferiority_margin": float(raw_gates.get("mrr_noninferiority_margin", 0.02)),
        "minimum_tool_call_reduction": float(raw_gates.get("minimum_tool_call_reduction", 0.10)),
        "maximum_wrong_hit_mean_increase": float(raw_gates.get("maximum_wrong_hit_mean_increase", 0.0)),
        "maximum_wrong_hit_per_trial_increase": int(raw_gates.get("maximum_wrong_hit_per_trial_increase", 0)),
        "maximum_wrong_hit_total_increase": int(raw_gates.get("maximum_wrong_hit_total_increase", 0)),
    }
    if gates["suite_noninferiority_margin"] < 0 or gates["recall_noninferiority_margin"] < 0 or gates["mrr_noninferiority_margin"] < 0:
        raise EvalError("invalid_spec", "noninferiority margins must be non-negative")
    if not 0 <= gates["minimum_tool_call_reduction"] <= 1:
        raise EvalError("invalid_spec", "minimum_tool_call_reduction must be in [0, 1]")
    if gates["maximum_wrong_hit_mean_increase"] < 0 or gates["maximum_wrong_hit_per_trial_increase"] < 0 or gates["maximum_wrong_hit_total_increase"] < 0:
        raise EvalError("invalid_spec", "wrong-hit allowances must be non-negative")

    return {
        "min_elapsed_seconds": min_elapsed,
        "trial_seeds": seeds,
        "pins": pins,
        "conditions": conditions,
        "gates": gates,
    }


def _new_state(eval_id: str, now: datetime) -> dict[str, Any]:
    stamp = _iso(now)
    return {
        "schema_version": STATE_SCHEMA,
        "eval_id": eval_id,
        "revision": 1,
        "created_at": stamp,
        "updated_at": stamp,
        "condition_exports": {"A": None, "B": None},
        "b_window_opened_at": None,
        "trials": {},
        "analysis": None,
    }


def create_evaluation(
    registry_root: str | Path,
    spec_path: str | Path,
    *,
    now: datetime | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Create an immutable plan and return its machine-readable status."""
    registry = Path(registry_root).resolve(strict=False)
    source_spec = Path(spec_path).resolve(strict=True)
    parsed_spec = _load_json(source_spec)
    validated = _validate_spec(parsed_spec, source_spec.parent, registry)
    stamp = _as_utc(now)
    nonce = nonce or secrets.token_hex(16)
    identity_digest = _sha256_bytes(_canonical_bytes({
        "created_at": _iso(stamp),
        "nonce": nonce,
        "spec_sha256": sha256_file(source_spec),
    }))
    eval_id = f"traum-v2-{stamp.strftime('%Y%m%dT%H%M%SZ')}-{identity_digest[:12]}"
    paths = EvalPaths(registry, eval_id)
    if paths.eval_dir.exists():
        raise EvalError("id_conflict", f"evaluation ID already exists: {eval_id}")

    evaluations_dir = registry / "evaluations"
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = evaluations_dir / f".{eval_id}.tmp-{secrets.token_hex(6)}"
    temp_dir.mkdir()
    try:
        spec_copy = _copy_stable(source_spec, temp_dir / "inputs" / "v1" / "spec.json")
        pins: dict[str, Any] = {}
        for name in PIN_NAMES:
            pin = validated["pins"][name]
            if name in FILE_PIN_NAMES:
                copied = _copy_stable(pin["source"], temp_dir / "inputs" / "v1" / "pins" / name / "payload")
                pins[name] = {
                    "id": pin["id"],
                    "sha256": pin["sha256"],
                    "artifact": str(Path("inputs") / "v1" / "pins" / name / "payload"),
                    "size": copied["size"],
                }
            else:
                pins[name] = dict(pin)

        conditions: dict[str, Any] = {}
        for condition in ("A", "B"):
            source = validated["conditions"][condition]
            attestation_copy = _copy_stable(
                source["attestation"],
                temp_dir / "inputs" / "v1" / "attestations" / f"condition-{condition}.json",
            )
            conditions[condition] = {
                "store_url": source["store_url"],
                "gateway_url": source["gateway_url"],
                "filesystem_root": str(source["filesystem_root"]),
                "attestation": {
                    "artifact": str(Path("inputs") / "v1" / "attestations" / f"condition-{condition}.json"),
                    "sha256": attestation_copy["sha256"],
                },
            }

        input_fingerprint = _sha256_bytes(_canonical_bytes({
            "pins": {name: {"id": pins[name]["id"], "sha256": pins[name]["sha256"]} for name in PIN_NAMES},
            "trial_seeds": validated["trial_seeds"],
        }))
        plan = {
            "schema_version": PLAN_SCHEMA,
            "eval_id": eval_id,
            "created_at": _iso(stamp),
            "spec": {"artifact": str(Path("inputs") / "v1" / "spec.json"), "sha256": spec_copy["sha256"]},
            "min_elapsed_seconds": validated["min_elapsed_seconds"],
            "trial_seeds": validated["trial_seeds"],
            "pins": pins,
            "input_fingerprint": input_fingerprint,
            "conditions": conditions,
            "gates": validated["gates"],
            "safety": {
                "network_calls_permitted": False,
                "production_writes_permitted": False,
                "auto_apply_enabled": False,
                "input_mutation_permitted": False,
            },
        }
        plan_path = temp_dir / "plan.json"
        _atomic_write_json(plan_path, plan)
        plan_hash = sha256_file(plan_path)
        _atomic_write_json(temp_dir / "identity.json", {
            "schema_version": "traum.eval.identity.v2",
            "eval_id": eval_id,
            "created_at": _iso(stamp),
            "plan_sha256": plan_hash,
        })
        _atomic_write_json(temp_dir / "state.json", _new_state(eval_id, stamp))
        os.replace(temp_dir, paths.eval_dir)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    _rebuild_registry(registry)
    return get_status(registry, eval_id, now=stamp)


def _load_context(registry_root: str | Path, eval_id: str) -> tuple[EvalPaths, dict[str, Any], dict[str, Any]]:
    if not _EVAL_ID_RE.fullmatch(eval_id):
        raise EvalError("invalid_id", f"invalid immutable evaluation ID: {eval_id!r}")
    paths = EvalPaths(Path(registry_root).resolve(strict=False), eval_id)
    identity = _load_json(paths.identity)
    plan = _load_json(paths.plan)
    state = _load_json(paths.state)
    if identity.get("eval_id") != eval_id or plan.get("eval_id") != eval_id or state.get("eval_id") != eval_id:
        raise EvalError("registry_corrupt", f"evaluation identity mismatch for {eval_id}")
    if plan.get("schema_version") != PLAN_SCHEMA or state.get("schema_version") != STATE_SCHEMA:
        raise EvalError("registry_corrupt", f"unsupported registry schema for {eval_id}")
    actual_plan_hash = sha256_file(paths.plan)
    if identity.get("plan_sha256") != actual_plan_hash:
        raise EvalError("immutable_plan_changed", f"immutable plan hash mismatch for {eval_id}")
    return paths, plan, _reconcile_state(paths, state)


def _verified_manifest(paths: EvalPaths, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if manifest.get("eval_id") != paths.eval_id:
        raise EvalError("registry_corrupt", f"manifest identity mismatch: {manifest_path}")
    artifacts: list[dict[str, Any]] = []
    raw_artifacts = manifest.get("artifacts", {})
    if isinstance(raw_artifacts, dict):
        artifacts.extend(item for item in raw_artifacts.values() if isinstance(item, dict))
    elif isinstance(raw_artifacts, list):
        artifacts.extend(item for item in raw_artifacts if isinstance(item, dict))
    metrics_artifact = manifest.get("metrics_artifact")
    if isinstance(metrics_artifact, dict):
        artifacts.append(metrics_artifact)
    for artifact in artifacts:
        rel = artifact.get("artifact")
        digest = artifact.get("sha256")
        if not isinstance(rel, str) or not isinstance(digest, str):
            raise EvalError("registry_corrupt", f"invalid artifact entry in {manifest_path}")
        target = _resolve_relative(paths.eval_dir, rel)
        if not target.is_file() or sha256_file(target) != digest:
            raise EvalError("artifact_changed", f"immutable artifact hash mismatch: {target}")
    return manifest


def _reconcile_state(paths: EvalPaths, state: dict[str, Any]) -> dict[str, Any]:
    """Rebuild state references from completed manifests after interruption."""
    reconciled = json.loads(json.dumps(state))
    reconciled.setdefault("condition_exports", {"A": None, "B": None})
    reconciled.setdefault("trials", {})
    for condition in ("A", "B"):
        manifest_path = paths.eval_dir / "conditions" / condition / "v1" / "manifest.json"
        if manifest_path.is_file():
            manifest = _verified_manifest(paths, manifest_path)
            reconciled["condition_exports"][condition] = {
                "manifest": str(manifest_path.relative_to(paths.eval_dir)),
                "captured_at": manifest["captured_at"],
                "export_fingerprint": manifest["export_fingerprint"],
                "corpus_delta": manifest.get("corpus_delta"),
            }
    trials_dir = paths.eval_dir / "trials"
    if trials_dir.is_dir():
        for manifest_path in trials_dir.glob("seed-*/[AB]/v1/manifest.json"):
            manifest = _verified_manifest(paths, manifest_path)
            seed_key = str(manifest["seed"])
            reconciled["trials"].setdefault(seed_key, {})[manifest["condition"]] = {
                "manifest": str(manifest_path.relative_to(paths.eval_dir)),
                "trial_fingerprint": manifest["trial_fingerprint"],
                "recorded_at": manifest["recorded_at"],
            }
    analysis_path = paths.eval_dir / "analysis" / "v1" / "summary.json"
    if analysis_path.is_file():
        analysis = _load_json(analysis_path)
        if analysis.get("eval_id") != paths.eval_id or analysis.get("schema_version") != ANALYSIS_SCHEMA:
            raise EvalError("registry_corrupt", f"analysis identity/schema mismatch: {analysis_path}")
        analysis_sha256 = sha256_file(analysis_path)
        prior_analysis = reconciled.get("analysis")
        if (
            isinstance(prior_analysis, dict)
            and prior_analysis.get("sha256")
            and prior_analysis["sha256"] != analysis_sha256
        ):
            raise EvalError(
                "artifact_changed",
                f"immutable analysis hash mismatch: {analysis_path}",
            )
        reconciled["analysis"] = {
            "artifact": str(analysis_path.relative_to(paths.eval_dir)),
            "sha256": analysis_sha256,
            "outcome": analysis["outcome"],
        }
    return reconciled


def _write_state(paths: EvalPaths, state: dict[str, Any], now: datetime) -> None:
    stored = json.loads(json.dumps(state))
    stored["revision"] = int(stored.get("revision", 0)) + 1
    stored["updated_at"] = _iso(now)
    _atomic_write_json(paths.state, stored)
    _rebuild_registry(paths.registry)


def _capture_condition(
    registry_root: str | Path,
    eval_id: str,
    condition: str,
    mapping_path: str | Path,
    documents_path: str | Path,
    config_path: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    stamp = _as_utc(now)
    paths, plan, state = _load_context(registry_root, eval_id)
    if condition == "B":
        if not state.get("b_window_opened_at"):
            raise EvalError("stage_blocked", "Condition B cannot start until open-b passes the real elapsed-window gate")
        baseline = state["condition_exports"].get("A")
        if not baseline:
            raise EvalError("stage_blocked", "Condition A must be frozen before Condition B")
        not_before = _parse_iso(baseline["captured_at"]) + timedelta(seconds=plan["min_elapsed_seconds"])
        if stamp < not_before:
            raise EvalError("elapsed_window", f"Condition B is blocked until {_iso(not_before)}")
    elif condition != "A":
        raise EvalError("invalid_condition", f"unsupported condition: {condition}")

    condition_root = Path(plan["conditions"][condition]["filesystem_root"])
    sources = {
        "mapping": _canonical_source(mapping_path, f"conditions.{condition}.mapping", condition_root),
        "documents": _canonical_source(documents_path, f"conditions.{condition}.documents", condition_root),
        "config": _canonical_source(config_path, f"conditions.{condition}.config", condition_root),
    }
    manifest_path = paths.eval_dir / "conditions" / condition / "v1" / "manifest.json"
    if manifest_path.is_file():
        manifest = _verified_manifest(paths, manifest_path)
        for name, source in sources.items():
            if sha256_file(source) != manifest["artifacts"][name]["sha256"]:
                raise EvalError("immutable_conflict", f"condition {condition} was already captured from different {name} bytes")
        state = _reconcile_state(paths, state)
        _write_state(paths, state, stamp)
        return get_status(paths.registry, eval_id, now=stamp)

    corpus_delta: dict[str, Any] | None = None
    if condition == "B":
        a_manifest_path = paths.eval_dir / state["condition_exports"]["A"]["manifest"]
        a_manifest = _verified_manifest(paths, a_manifest_path)
        for name in ("mapping", "config"):
            if sha256_file(sources[name]) != a_manifest["artifacts"][name]["sha256"]:
                raise EvalError(
                    "input_drift",
                    f"Condition B {name} differs from frozen A; only corpus documents may vary across the learning window",
                )
        a_documents = paths.eval_dir / a_manifest["artifacts"]["documents"]["artifact"]
        if sha256_file(sources["documents"]) == a_manifest["artifacts"]["documents"]["sha256"]:
            raise EvalError(
                "no_learning_delta",
                "Condition B corpus is byte-identical to frozen A; the learning window produced no KB change, "
                "so the comparison cannot be causally informative",
            )
        corpus_delta = _corpus_delta(a_documents, sources["documents"])
        if corpus_delta.get("comparable") and not (
            corpus_delta["added"] or corpus_delta["removed"] or corpus_delta["modified"]
        ):
            raise EvalError(
                "no_learning_delta",
                "Condition B corpus differs from A only in serialization; no document was added, removed, or changed",
            )

    target_dir = manifest_path.parent / "export"
    artifacts: dict[str, Any] = {}
    target_names = {"mapping": "mapping.json", "documents": "documents.jsonl", "config": "config.json"}
    for name, source in sources.items():
        copied = _copy_stable(source, target_dir / target_names[name])
        artifacts[name] = {
            "artifact": str((target_dir / target_names[name]).relative_to(paths.eval_dir)),
            "sha256": copied["sha256"],
            "size": copied["size"],
        }

    export_fingerprint = _sha256_bytes(_canonical_bytes({name: artifacts[name]["sha256"] for name in sorted(artifacts)}))
    manifest = {
        "schema_version": CAPTURE_SCHEMA,
        "eval_id": eval_id,
        "condition": condition,
        "export_version": 1,
        "captured_at": _iso(stamp),
        "input_fingerprint": plan["input_fingerprint"],
        "source_preserved": True,
        "artifacts": artifacts,
        "export_fingerprint": export_fingerprint,
    }
    if corpus_delta is not None:
        manifest["corpus_delta"] = corpus_delta
    _atomic_write_json(manifest_path, manifest)
    state = _reconcile_state(paths, state)
    _write_state(paths, state, stamp)
    return get_status(paths.registry, eval_id, now=stamp)


def freeze_condition_a(
    registry_root: str | Path,
    eval_id: str,
    mapping_path: str | Path,
    documents_path: str | Path,
    config_path: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _capture_condition(registry_root, eval_id, "A", mapping_path, documents_path, config_path, now=now)


def open_condition_b(registry_root: str | Path, eval_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    stamp = _as_utc(now)
    paths, plan, state = _load_context(registry_root, eval_id)
    baseline = state["condition_exports"].get("A")
    if not baseline:
        raise EvalError("stage_blocked", "Condition A must be frozen before the learning window can be opened")
    not_before = _parse_iso(baseline["captured_at"]) + timedelta(seconds=plan["min_elapsed_seconds"])
    if stamp < not_before:
        remaining = math.ceil((not_before - stamp).total_seconds())
        raise EvalError("elapsed_window", f"Condition B is blocked for another {remaining} seconds, until {_iso(not_before)}")
    if not state.get("b_window_opened_at"):
        state["b_window_opened_at"] = _iso(stamp)
        _write_state(paths, state, stamp)
    return get_status(paths.registry, eval_id, now=stamp)


def capture_condition_b(
    registry_root: str | Path,
    eval_id: str,
    mapping_path: str | Path,
    documents_path: str | Path,
    config_path: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return _capture_condition(registry_root, eval_id, "B", mapping_path, documents_path, config_path, now=now)


def _runtime_fingerprints(plan: Mapping[str, Any]) -> dict[str, str]:
    return {name: plan["pins"][name]["sha256"] for name in PIN_NAMES}


def _validate_metrics(value: dict[str, Any], plan: dict[str, Any], condition: str, seed: int, export_fingerprint: str) -> None:
    required_top_level = {
        "schema_version", "eval_id", "condition", "seed", "input_fingerprint",
        "condition_export_fingerprint", "runtime_fingerprints", "side_effects", "metrics",
    }
    if set(value) != required_top_level:
        raise EvalError("invalid_trial", "trial contains missing or unregistered top-level fields")
    expected = {
        "schema_version": TRIAL_SCHEMA,
        "eval_id": plan["eval_id"],
        "condition": condition,
        "seed": seed,
        "input_fingerprint": plan["input_fingerprint"],
        "condition_export_fingerprint": export_fingerprint,
        "runtime_fingerprints": _runtime_fingerprints(plan),
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise EvalError("trial_mismatch", f"trial {key} does not match the immutable plan/export")
    side_effects = value.get("side_effects")
    if side_effects != {
        "isolated": True,
        "production_writes": 0,
        "input_mutations": 0,
        "auto_apply_enabled": False,
    }:
        raise EvalError("unsafe_trial", "trial must attest zero production writes/input mutations and auto_apply_enabled=false")
    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(METRIC_NAMES):
        raise EvalError("invalid_trial", f"metrics must define: {', '.join(METRIC_NAMES)}")
    for name in METRIC_NAMES:
        metric = metrics[name]
        if isinstance(metric, bool) or not isinstance(metric, (int, float)) or not math.isfinite(float(metric)):
            raise EvalError("invalid_trial", f"metric {name} must be a finite number")
    if metrics["max_suite_score"] <= 0 or not 0 <= metrics["suite_score"] <= metrics["max_suite_score"]:
        raise EvalError("invalid_trial", "suite_score must be in [0, max_suite_score]")
    if int(metrics["tool_call_count"]) != metrics["tool_call_count"] or metrics["tool_call_count"] < 1:
        raise EvalError("invalid_trial", "tool_call_count must be a positive integer")
    if int(metrics["wrong_kb_hits"]) != metrics["wrong_kb_hits"] or metrics["wrong_kb_hits"] < 0:
        raise EvalError("invalid_trial", "wrong_kb_hits must be a non-negative integer")
    for name in ("retrieval_recall_at_1", "retrieval_recall_at_3", "retrieval_mrr"):
        if not 0 <= metrics[name] <= 1:
            raise EvalError("invalid_trial", f"{name} must be in [0, 1]")
    if metrics["retrieval_recall_at_1"] > metrics["retrieval_recall_at_3"]:
        raise EvalError("invalid_trial", "retrieval_recall_at_1 cannot exceed retrieval_recall_at_3")


def record_trial(
    registry_root: str | Path,
    eval_id: str,
    condition: str,
    seed: int,
    metrics_path: str | Path,
    raw_artifacts: Sequence[str | Path],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    stamp = _as_utc(now)
    paths, plan, state = _load_context(registry_root, eval_id)
    condition = condition.upper()
    if condition not in {"A", "B"}:
        raise EvalError("invalid_condition", "trial condition must be A or B")
    if seed not in plan["trial_seeds"]:
        raise EvalError("invalid_seed", f"seed {seed} is not pinned in the immutable plan")
    capture = state["condition_exports"].get(condition)
    if not capture:
        raise EvalError("stage_blocked", f"condition {condition} export must be captured before its trials")
    if condition == "B" and not state.get("b_window_opened_at"):
        raise EvalError("stage_blocked", "Condition B trials cannot start before the elapsed-window gate")
    if not raw_artifacts:
        raise EvalError("invalid_trial", "at least one raw transcript/retrieval artifact is required")

    metrics_source = Path(metrics_path).resolve(strict=True)
    raw_sources = [Path(item).resolve(strict=True) for item in raw_artifacts]
    if len({str(item) for item in raw_sources}) != len(raw_sources):
        raise EvalError("invalid_trial", "raw artifact paths must be unique")
    metrics = _load_json(metrics_source)
    _validate_metrics(metrics, plan, condition, seed, capture["export_fingerprint"])

    trial_dir = paths.eval_dir / "trials" / f"seed-{seed}" / condition / "v1"
    manifest_path = trial_dir / "manifest.json"
    source_signature = {
        "metrics": sha256_file(metrics_source),
        "artifacts": [sha256_file(item) for item in raw_sources],
    }
    if manifest_path.is_file():
        manifest = _verified_manifest(paths, manifest_path)
        if manifest.get("source_signature") != source_signature:
            raise EvalError("immutable_conflict", f"trial seed={seed} condition={condition} already contains different bytes")
        state = _reconcile_state(paths, state)
        _write_state(paths, state, stamp)
        return get_status(paths.registry, eval_id, now=stamp)

    copied_metrics = _copy_stable(metrics_source, trial_dir / "metrics.json")
    artifact_entries: list[dict[str, Any]] = []
    for index, source in enumerate(raw_sources):
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", source.name) or "artifact"
        destination = trial_dir / "raw" / f"{index:03d}-{safe_name}"
        copied = _copy_stable(source, destination)
        artifact_entries.append({
            "artifact": str(destination.relative_to(paths.eval_dir)),
            "sha256": copied["sha256"],
            "size": copied["size"],
        })
    trial_fingerprint = _sha256_bytes(_canonical_bytes({
        "metrics": copied_metrics["sha256"],
        "artifacts": [item["sha256"] for item in artifact_entries],
    }))
    manifest = {
        "schema_version": TRIAL_MANIFEST_SCHEMA,
        "eval_id": eval_id,
        "condition": condition,
        "seed": seed,
        "recorded_at": _iso(stamp),
        "metrics_artifact": {
            "artifact": str((trial_dir / "metrics.json").relative_to(paths.eval_dir)),
            "sha256": copied_metrics["sha256"],
            "size": copied_metrics["size"],
        },
        "artifacts": artifact_entries,
        "source_signature": source_signature,
        "trial_fingerprint": trial_fingerprint,
    }
    _atomic_write_json(manifest_path, manifest)
    state = _reconcile_state(paths, state)
    _write_state(paths, state, stamp)
    return get_status(paths.registry, eval_id, now=stamp)


_T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
    7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
    13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
    19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
    25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _t_critical_975(degrees_of_freedom: int) -> float:
    """Return the two-sided 95% Student-t critical value.

    The exact small-sample values are tabled because those are the runs where
    the distinction matters most.  Above 30 degrees of freedom, a standard
    Cornish-Fisher expansion approaches the normal critical value without the
    unsafe discontinuity of treating every larger finite sample as infinite.
    """
    if degrees_of_freedom < 1:
        raise ValueError("degrees_of_freedom must be positive")
    if degrees_of_freedom in _T_975:
        return _T_975[degrees_of_freedom]
    z = 1.959963984540054
    df = float(degrees_of_freedom)
    return (
        z
        + (z**3 + z) / (4 * df)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
        + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
    )


def _paired_ci(values: Sequence[float]) -> dict[str, Any]:
    if len(values) < 3:
        raise EvalError("insufficient_trials", "at least three paired trials are required")
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values)
    critical = _t_critical_975(len(values) - 1)
    half_width = critical * stdev / math.sqrt(len(values))
    return {
        "n": len(values),
        "mean": mean,
        "standard_deviation": stdev,
        "confidence_level": 0.95,
        "lower": mean - half_width,
        "upper": mean + half_width,
        "method": "paired_student_t",
        "values": list(values),
    }


def _trial_metrics(paths: EvalPaths, manifest_ref: str) -> dict[str, Any]:
    manifest = _verified_manifest(paths, paths.eval_dir / manifest_ref)
    metrics_path = _resolve_relative(paths.eval_dir, manifest["metrics_artifact"]["artifact"])
    return _load_json(metrics_path)["metrics"]


def _analysis_corpus_delta(paths: EvalPaths, state: Mapping[str, Any]) -> dict[str, Any]:
    """Re-check at analysis time that A and B are not the same corpus.

    The capture stage already refuses an identical Condition B, but an
    evaluation frozen before that guard existed (or reconciled from manifests on
    disk) must not be scored as if it measured learning.
    """
    exports = state.get("condition_exports") or {}
    manifests: dict[str, Any] = {}
    for condition in ("A", "B"):
        entry = exports.get(condition)
        if not entry:
            raise EvalError("stage_blocked", f"condition {condition} must be captured before analysis")
        manifests[condition] = _verified_manifest(paths, paths.eval_dir / entry["manifest"])
    if manifests["A"]["export_fingerprint"] == manifests["B"]["export_fingerprint"]:
        raise EvalError(
            "no_learning_delta",
            "Conditions A and B froze identical exports; the result would measure sampling variance, not learning",
        )
    recorded = manifests["B"].get("corpus_delta")
    if isinstance(recorded, dict):
        return recorded
    return _corpus_delta(
        paths.eval_dir / manifests["A"]["artifacts"]["documents"]["artifact"],
        paths.eval_dir / manifests["B"]["artifacts"]["documents"]["artifact"],
    )


def analyze_evaluation(registry_root: str | Path, eval_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    stamp = _as_utc(now)
    paths, plan, state = _load_context(registry_root, eval_id)
    corpus_delta = _analysis_corpus_delta(paths, state)
    missing: list[str] = []
    paired: list[dict[str, Any]] = []
    for seed in plan["trial_seeds"]:
        entries = state["trials"].get(str(seed), {})
        if "A" not in entries or "B" not in entries:
            missing.extend(f"{condition}:{seed}" for condition in ("A", "B") if condition not in entries)
            continue
        a = _trial_metrics(paths, entries["A"]["manifest"])
        b = _trial_metrics(paths, entries["B"]["manifest"])
        if a["max_suite_score"] != b["max_suite_score"]:
            raise EvalError("input_drift", f"max_suite_score differs within paired seed {seed}")
        paired.append({"seed": seed, "A": a, "B": b})
    if missing:
        raise EvalError("incomplete_trials", "missing pinned condition/seed trials: " + ", ".join(missing))

    suite_delta = [row["B"]["suite_score"] - row["A"]["suite_score"] for row in paired]
    tool_reduction = [
        (row["A"]["tool_call_count"] - row["B"]["tool_call_count"]) / row["A"]["tool_call_count"]
        for row in paired
    ]
    wrong_delta = [row["B"]["wrong_kb_hits"] - row["A"]["wrong_kb_hits"] for row in paired]
    recall_delta = [row["B"]["retrieval_recall_at_3"] - row["A"]["retrieval_recall_at_3"] for row in paired]
    mrr_delta = [row["B"]["retrieval_mrr"] - row["A"]["retrieval_mrr"] for row in paired]
    cis = {
        "suite_score_delta": _paired_ci(suite_delta),
        "tool_call_reduction_fraction": _paired_ci(tool_reduction),
        "wrong_kb_hit_delta": _paired_ci(wrong_delta),
        "retrieval_recall_at_3_delta": _paired_ci(recall_delta),
        "retrieval_mrr_delta": _paired_ci(mrr_delta),
    }
    gates = plan["gates"]
    gate_results = {
        "suite_noninferiority": cis["suite_score_delta"]["lower"] >= -gates["suite_noninferiority_margin"],
        "recall_noninferiority": cis["retrieval_recall_at_3_delta"]["lower"] >= -gates["recall_noninferiority_margin"],
        "mrr_noninferiority": cis["retrieval_mrr_delta"]["lower"] >= -gates["mrr_noninferiority_margin"],
        "wrong_hit_mean": cis["wrong_kb_hit_delta"]["upper"] <= gates["maximum_wrong_hit_mean_increase"],
        "wrong_hit_each_trial": max(wrong_delta) <= gates["maximum_wrong_hit_per_trial_increase"],
        "wrong_hit_total": sum(wrong_delta) <= gates["maximum_wrong_hit_total_increase"],
    }
    lift = {
        "suite_superiority": cis["suite_score_delta"]["lower"] > 0,
        "tool_call_reduction": cis["tool_call_reduction_fraction"]["lower"] >= gates["minimum_tool_call_reduction"],
    }
    demonstrated_harm = (
        cis["suite_score_delta"]["upper"] < -gates["suite_noninferiority_margin"]
        or cis["retrieval_recall_at_3_delta"]["upper"] < -gates["recall_noninferiority_margin"]
        or cis["retrieval_mrr_delta"]["upper"] < -gates["mrr_noninferiority_margin"]
        or not gate_results["wrong_hit_each_trial"]
        or not gate_results["wrong_hit_total"]
    )
    all_safety_gates = all(gate_results.values())
    if demonstrated_harm:
        outcome = "LOSS"
    elif all_safety_gates and any(lift.values()):
        outcome = "WIN"
    elif all_safety_gates:
        outcome = "NULL"
    else:
        outcome = "INCONCLUSIVE"

    analysis_path = paths.eval_dir / "analysis" / "v1" / "summary.json"
    summary = {
        "schema_version": ANALYSIS_SCHEMA,
        "eval_id": eval_id,
        "analyzed_at": _iso(stamp),
        "plan_sha256": sha256_file(paths.plan),
        "corpus_delta": corpus_delta,
        "trial_seeds": plan["trial_seeds"],
        "paired_trials": paired,
        "confidence_intervals": cis,
        "gate_results": gate_results,
        "lift_results": lift,
        "outcome": outcome,
        "promotion": {
            "eligible_for_policy_review": outcome == "WIN" and all_safety_gates,
            "auto_apply_enabled": False,
            "note": "An eval may nominate a policy review; this tool has no path that enables auto-apply.",
        },
    }
    if analysis_path.is_file():
        existing = _load_json(analysis_path)
        comparable_existing = dict(existing)
        comparable_new = dict(summary)
        comparable_existing.pop("analyzed_at", None)
        comparable_new.pop("analyzed_at", None)
        if comparable_existing != comparable_new:
            raise EvalError("immutable_conflict", "analysis already exists with different inputs/results")
    else:
        _atomic_write_json(analysis_path, summary)
    state = _reconcile_state(paths, state)
    _write_state(paths, state, stamp)
    return get_status(paths.registry, eval_id, now=stamp)


def _status_stage(plan: dict[str, Any], state: dict[str, Any], now: datetime) -> tuple[str, list[dict[str, Any]]]:
    a = state["condition_exports"].get("A")
    b = state["condition_exports"].get("B")
    if state.get("analysis"):
        return "analyzed", []
    if not a:
        return "initialized", [{"action": "freeze-a", "blocked": False}]
    not_before = _parse_iso(a["captured_at"]) + timedelta(seconds=plan["min_elapsed_seconds"])
    if not state.get("b_window_opened_at"):
        blocked = now < not_before
        return ("baseline_wait" if blocked else "b_window_ready"), [{
            "action": "open-b",
            "blocked": blocked,
            "not_before": _iso(not_before),
            "reason": "minimum elapsed learning window has not completed" if blocked else None,
        }]
    if not b:
        return "b_window_open", [{"action": "capture-b", "blocked": False}]
    missing: list[dict[str, Any]] = []
    for seed in plan["trial_seeds"]:
        entries = state["trials"].get(str(seed), {})
        for condition in ("A", "B"):
            if condition not in entries:
                missing.append({"condition": condition, "seed": seed})
    if missing:
        return "trials_running", [{"action": "record-trial", "blocked": False, "missing": missing}]
    return "trials_complete", [{"action": "analyze", "blocked": False}]


def _artifact_index(paths: EvalPaths, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return contained artifact paths and hashes for typed GUI/audit consumers."""
    artifacts: list[dict[str, Any]] = [{
        "kind": "plan",
        "artifact": "plan.json",
        "sha256": sha256_file(paths.plan),
        "size": paths.plan.stat().st_size,
    }]
    for condition in ("A", "B"):
        capture = state["condition_exports"].get(condition)
        if not capture:
            continue
        manifest_path = _resolve_relative(paths.eval_dir, capture["manifest"])
        manifest = _verified_manifest(paths, manifest_path)
        artifacts.append({
            "kind": "condition-manifest",
            "condition": condition,
            "artifact": capture["manifest"],
            "sha256": sha256_file(manifest_path),
            "size": manifest_path.stat().st_size,
        })
        for name, item in sorted(manifest["artifacts"].items()):
            artifacts.append({
                "kind": f"condition-{name}",
                "condition": condition,
                "artifact": item["artifact"],
                "sha256": item["sha256"],
                "size": item["size"],
            })
    for seed, conditions in sorted(state["trials"].items(), key=lambda item: int(item[0])):
        for condition in ("A", "B"):
            entry = conditions.get(condition)
            if not entry:
                continue
            manifest_path = _resolve_relative(paths.eval_dir, entry["manifest"])
            manifest = _verified_manifest(paths, manifest_path)
            artifacts.append({
                "kind": "trial-manifest",
                "condition": condition,
                "seed": int(seed),
                "artifact": entry["manifest"],
                "sha256": sha256_file(manifest_path),
                "size": manifest_path.stat().st_size,
            })
            metrics = manifest["metrics_artifact"]
            artifacts.append({
                "kind": "trial-metrics",
                "condition": condition,
                "seed": int(seed),
                "artifact": metrics["artifact"],
                "sha256": metrics["sha256"],
                "size": metrics["size"],
            })
            for item in manifest["artifacts"]:
                artifacts.append({
                    "kind": "trial-raw",
                    "condition": condition,
                    "seed": int(seed),
                    "artifact": item["artifact"],
                    "sha256": item["sha256"],
                    "size": item["size"],
                })
    if state.get("analysis"):
        analysis_path = _resolve_relative(paths.eval_dir, state["analysis"]["artifact"])
        artifacts.append({
            "kind": "analysis",
            "artifact": state["analysis"]["artifact"],
            "sha256": sha256_file(analysis_path),
            "size": analysis_path.stat().st_size,
        })
    return artifacts


def get_status(
    registry_root: str | Path,
    eval_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    stamp = _as_utc(now)
    paths, plan, state = _load_context(registry_root, eval_id)
    stage, next_actions = _status_stage(plan, state, stamp)
    recorded = {
        condition: sum(condition in state["trials"].get(str(seed), {}) for seed in plan["trial_seeds"])
        for condition in ("A", "B")
    }
    baseline = state["condition_exports"].get("A")
    not_before = (
        _parse_iso(baseline["captured_at"]) + timedelta(seconds=plan["min_elapsed_seconds"])
        if baseline else None
    )
    trials_complete = all(recorded[condition] == len(plan["trial_seeds"]) for condition in ("A", "B"))
    analysis_status = None
    if state.get("analysis"):
        analysis_ref = state["analysis"]
        analysis_path = _resolve_relative(paths.eval_dir, analysis_ref["artifact"])
        analysis_summary = _load_json(analysis_path)
        if sha256_file(analysis_path) != analysis_ref["sha256"]:
            raise EvalError(
                "artifact_changed",
                f"immutable analysis hash mismatch: {analysis_path}",
            )
        # Preserve the contained artifact reference while exposing the
        # decision-bearing analysis fields through the stable status schema.
        # Consumers no longer need to open a raw artifact merely to learn
        # whether safety gates passed, and an analyzed LOSS cannot be mistaken
        # for a promotion-ready result.
        analysis_status = {
            "artifact": analysis_ref["artifact"],
            "sha256": analysis_ref["sha256"],
            "analyzed_at": analysis_summary["analyzed_at"],
            "outcome": analysis_summary["outcome"],
            "corpus_delta": analysis_summary.get("corpus_delta"),
            "confidence_intervals": analysis_summary["confidence_intervals"],
            "gate_results": analysis_summary["gate_results"],
            "lift_results": analysis_summary["lift_results"],
            "promotion": analysis_summary["promotion"],
        }
    return {
        "schema_version": STATUS_SCHEMA,
        "registry_path": str(paths.registry),
        "eval_id": eval_id,
        "plan_sha256": sha256_file(paths.plan),
        "state_revision": state["revision"],
        "stage": stage,
        "created_at": state["created_at"],
        "updated_at": state["updated_at"],
        "min_elapsed_seconds": plan["min_elapsed_seconds"],
        "readiness": {
            "baseline_frozen": baseline is not None,
            "condition_b_not_before": _iso(not_before) if not_before else None,
            "elapsed_window_satisfied": bool(not_before and stamp >= not_before),
            "condition_b_open": state.get("b_window_opened_at") is not None,
            "condition_b_captured": state["condition_exports"].get("B") is not None,
            "paired_trials_complete": trials_complete,
            "analysis_complete": state.get("analysis") is not None,
        },
        "next_actions": next_actions,
        "invariants": {
            "input_fingerprint": plan["input_fingerprint"],
            "network_calls_permitted": False,
            "production_writes_permitted": False,
            "auto_apply_enabled": False,
            "condition_endpoints_separate": True,
            "condition_filesystems_separate": True,
        },
        "pins": {name: {"id": plan["pins"][name]["id"], "sha256": plan["pins"][name]["sha256"]} for name in PIN_NAMES},
        "conditions": {
            condition: {
                "store_url": plan["conditions"][condition]["store_url"],
                "gateway_url": plan["conditions"][condition]["gateway_url"],
                "filesystem_root": plan["conditions"][condition]["filesystem_root"],
                "export": state["condition_exports"].get(condition),
            }
            for condition in ("A", "B")
        },
        "trials": {
            "required_per_condition": len(plan["trial_seeds"]),
            "seeds": plan["trial_seeds"],
            "recorded": recorded,
            "entries": state["trials"],
        },
        "analysis": analysis_status,
        "artifacts": _artifact_index(paths, state),
    }


def list_statuses(registry_root: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    registry = Path(registry_root).resolve(strict=False)
    statuses: list[dict[str, Any]] = []
    evaluations = registry / "evaluations"
    if evaluations.is_dir():
        for candidate in sorted(evaluations.iterdir()):
            if candidate.is_dir() and _EVAL_ID_RE.fullmatch(candidate.name):
                statuses.append(get_status(registry, candidate.name, now=now))
    return {
        "schema_version": REGISTRY_SCHEMA,
        "registry_path": str(registry),
        "evaluations": statuses,
    }


def _rebuild_registry(registry: Path) -> None:
    """Refresh the GUI-facing index; evaluation directories remain authoritative."""
    _atomic_write_json(registry / "registry.json", list_statuses(registry))


def _validate_evidence(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != EVIDENCE_SCHEMA:
        raise EvalError("invalid_evidence", f"evidence must use schema_version={EVIDENCE_SCHEMA!r}")
    required_fields = {
        "schema_version", "proposal_id", "proposal_type", "observed_at", "decision",
        "reversal", "retrieval", "usefulness", "source_artifacts", "auto_apply",
    }
    if not required_fields <= set(value) or not set(value) <= required_fields | {"event_id"}:
        raise EvalError("invalid_evidence", "evidence contains missing or unregistered top-level fields")
    proposal_id = _require_nonempty(value.get("proposal_id"), "proposal_id")
    proposal_type = _require_nonempty(value.get("proposal_type"), "proposal_type")
    if not _PROPOSAL_TYPE_RE.fullmatch(proposal_type):
        raise EvalError("invalid_evidence", "proposal_type must be a stable lowercase identifier")
    _parse_iso(_require_nonempty(value.get("observed_at"), "observed_at"))
    decision = value.get("decision")
    if not isinstance(decision, dict) or set(decision) != {"outcome", "decided_by"} or decision.get("outcome") not in {"accepted", "rejected", "expired", "superseded"}:
        raise EvalError("invalid_evidence", "decision.outcome must be accepted/rejected/expired/superseded")
    if decision.get("decided_by") not in {"human", "invariant", "staleness", "supersession"}:
        raise EvalError("invalid_evidence", "decision.decided_by is invalid")
    reversal = value.get("reversal")
    if not isinstance(reversal, dict) or set(reversal) != {"status"} or reversal.get("status") not in {
        "not_observed", "reversed", "confirmed_not_reversed", "not_applicable",
    }:
        raise EvalError("invalid_evidence", "reversal.status is invalid")
    retrieval = value.get("retrieval")
    usefulness = value.get("usefulness")
    if not isinstance(retrieval, dict) or not isinstance(usefulness, dict):
        raise EvalError("invalid_evidence", "retrieval and usefulness must be objects")
    if set(retrieval) != {"opportunities", "retrieved", "used"} or set(usefulness) != {"observations", "positive", "negative"}:
        raise EvalError("invalid_evidence", "retrieval/usefulness contain missing or unregistered fields")
    for parent, fields in ((retrieval, ("opportunities", "retrieved", "used")), (usefulness, ("observations", "positive", "negative"))):
        for field in fields:
            item = parent.get(field)
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise EvalError("invalid_evidence", f"{field} must be a non-negative integer")
    if retrieval["used"] > retrieval["retrieved"] or retrieval["retrieved"] > retrieval["opportunities"]:
        raise EvalError("invalid_evidence", "retrieval counts must satisfy used <= retrieved <= opportunities")
    if usefulness["positive"] + usefulness["negative"] > usefulness["observations"]:
        raise EvalError("invalid_evidence", "usefulness outcomes exceed observations")
    artifacts = value.get("source_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise EvalError("invalid_evidence", "source_artifacts must contain at least one hash")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"sha256"}:
            raise EvalError("invalid_evidence", "source artifact entries must be objects")
        _normalise_digest(artifact.get("sha256"), "source_artifacts")
    auto_apply = value.get("auto_apply")
    if auto_apply != {"enabled": False}:
        raise EvalError("unsafe_evidence", "continuous evidence must state auto_apply.enabled=false")
    cleaned = json.loads(json.dumps(value))
    cleaned["proposal_id"] = proposal_id
    cleaned["proposal_type"] = proposal_type
    return cleaned


def record_evidence(registry_root: str | Path, event_path: str | Path) -> dict[str, Any]:
    registry = Path(registry_root).resolve(strict=False)
    source = Path(event_path).resolve(strict=True)
    event = _validate_evidence(_load_json(source))
    supplied_id = event.pop("event_id", None)
    event_id = "evidence-" + _sha256_bytes(_canonical_bytes(event))[:24]
    if supplied_id not in {None, event_id}:
        raise EvalError("invalid_evidence", f"event_id must be omitted or equal content ID {event_id}")
    event["event_id"] = event_id
    destination = registry / "continuous-evidence" / "v1" / "events" / f"{event_id}.json"
    if destination.is_file():
        if _load_json(destination) != event:
            raise EvalError("immutable_conflict", f"evidence ID collision: {event_id}")
    else:
        _atomic_write_json(destination, event)
    return {
        "schema_version": "traum.continuous-evidence.record-result.v1",
        "registry_path": str(registry),
        "event_id": event_id,
        "event_sha256": sha256_file(destination),
        "auto_apply_enabled": False,
    }


def _wilson(successes: int, total: int) -> dict[str, Any] | None:
    if total == 0:
        return None
    z = 1.96
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return {"successes": successes, "total": total, "rate": proportion, "lower": centre - half, "upper": centre + half, "method": "wilson_95"}


def evidence_summary(registry_root: str | Path) -> dict[str, Any]:
    registry = Path(registry_root).resolve(strict=False)
    event_dir = registry / "continuous-evidence" / "v1" / "events"
    groups: dict[str, list[dict[str, Any]]] = {}
    if event_dir.is_dir():
        for path in sorted(event_dir.glob("evidence-*.json")):
            event = _validate_evidence(_load_json(path))
            groups.setdefault(event["proposal_type"], []).append(event)
    summaries: dict[str, Any] = {}
    for proposal_type, events in groups.items():
        # Events are immutable cumulative snapshots for a stable proposal ID.
        # Retain every event for audit, but aggregate only the latest snapshot
        # per proposal so a later reversal/usefulness observation cannot count
        # its original decision or retrieval totals twice.
        latest_by_proposal: dict[str, dict[str, Any]] = {}
        for event in events:
            prior = latest_by_proposal.get(event["proposal_id"])
            if prior is None or _parse_iso(event["observed_at"]) > _parse_iso(prior["observed_at"]):
                latest_by_proposal[event["proposal_id"]] = event
        snapshots = list(latest_by_proposal.values())
        decisions = [event for event in snapshots if event["decision"]["outcome"] in {"accepted", "rejected"}]
        accepted = sum(event["decision"]["outcome"] == "accepted" for event in decisions)
        reversal_observations = [
            event for event in snapshots
            if event["decision"]["outcome"] == "accepted"
            and event["reversal"]["status"] in {"reversed", "confirmed_not_reversed"}
        ]
        reversals = sum(event["reversal"]["status"] == "reversed" for event in reversal_observations)
        opportunities = sum(event["retrieval"]["opportunities"] for event in snapshots)
        retrieved = sum(event["retrieval"]["retrieved"] for event in snapshots)
        used = sum(event["retrieval"]["used"] for event in snapshots)
        usefulness_observations = sum(event["usefulness"]["positive"] + event["usefulness"]["negative"] for event in snapshots)
        usefulness_positive = sum(event["usefulness"]["positive"] for event in snapshots)
        acceptance_ci = _wilson(accepted, len(decisions))
        reversal_ci = _wilson(reversals, len(reversal_observations))
        usefulness_ci = _wilson(usefulness_positive, usefulness_observations)
        reasons: list[str] = []
        if proposal_type not in FUTURE_AUTO_APPLY_CANDIDATES:
            reasons.append("proposal type is permanently human-gated")
        if len(decisions) < 20:
            reasons.append("fewer than 20 acceptance decisions")
        if not acceptance_ci or acceptance_ci["lower"] < 0.80:
            reasons.append("acceptance lower confidence bound is below 0.80")
        if not reversal_ci or reversal_ci["upper"] > 0.05:
            reasons.append("reversal upper confidence bound exceeds 0.05 or is unknown")
        if used < 10:
            reasons.append("fewer than 10 retrieved-and-used observations")
        if not usefulness_ci or usefulness_ci["lower"] < 0.70:
            reasons.append("usefulness lower confidence bound is below 0.70")
        summaries[proposal_type] = {
            "event_count": len(events),
            "acceptance": acceptance_ci,
            "reversal": reversal_ci,
            "retrieval": {"opportunities": opportunities, "retrieved": retrieved, "used": used},
            "usefulness": usefulness_ci,
            "auto_apply_eligibility": {
                "eligible_for_policy_review": not reasons,
                "reasons": reasons,
                "auto_apply_enabled": False,
            },
        }
    return {
        "schema_version": EVIDENCE_SUMMARY_SCHEMA,
        "registry_path": str(registry),
        "proposal_types": summaries,
        "auto_apply_enabled": False,
    }
