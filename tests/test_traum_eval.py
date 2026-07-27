"""Offline contract tests for the TRAUM A/B evaluation registry v2."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import traum_eval  # noqa: E402
import traum_eval_registry as ter  # noqa: E402


T0 = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _attestation(condition: str, store: str, gateway: str, filesystem: Path) -> dict:
    return {
        "schema_version": "traum.eval.isolation.v1",
        "condition": condition,
        "store_url": store,
        "gateway_url": gateway,
        "filesystem_root": str(filesystem.resolve()),
        "isolated": True,
        "disposable": True,
        "production_data": False,
        "production_writes": False,
        "auto_apply_enabled": False,
    }


def _make_spec(
    tmp_path: Path,
    *,
    min_elapsed: int = 3600,
    a_store: str = "http://127.0.0.1:19201",
    a_gateway: str = "http://127.0.0.1:19701",
    b_store: str = "http://127.0.0.1:19202",
    b_gateway: str = "http://127.0.0.1:19702",
) -> tuple[Path, Path, dict[str, Path]]:
    inputs = tmp_path / "inputs"
    pins = {
        "prompt": _write_text(inputs / "prompt.md", "system prompt v2\n"),
        "tool_schema": _write_json(inputs / "tools.json", {"tools": ["search_kb"]}),
        "retriever": _write_json(inputs / "retriever.json", {"mode": "linear", "min_score": 4.2}),
        "dataset": _write_text(inputs / "dataset.jsonl", '{"query":"q","expected":"d"}\n'),
    }
    a_fs = (tmp_path / "isolated" / "a").resolve()
    b_fs = (tmp_path / "isolated" / "b").resolve()
    a_attestation = _write_json(inputs / "a-attestation.json", _attestation("A", a_store, a_gateway, a_fs))
    b_attestation = _write_json(inputs / "b-attestation.json", _attestation("B", b_store, b_gateway, b_fs))
    spec = {
        "schema_version": "traum.eval.spec.v2",
        "min_elapsed_seconds": min_elapsed,
        "trial_seeds": [101, 202, 303],
        "pins": {
            "model": {"id": "model-v1", "sha256": "1" * 64},
            "prompt": {"id": "prompt-v2", "path": str(pins["prompt"])},
            "tool_schema": {"id": "tools-v1", "path": str(pins["tool_schema"])},
            "retriever": {"id": "linear-v1", "path": str(pins["retriever"])},
            "embedding": {"id": "embed-v1", "sha256": "2" * 64},
            "dataset": {"id": "gold-v1", "path": str(pins["dataset"])},
        },
        "conditions": {
            "A": {
                "store_url": a_store,
                "gateway_url": a_gateway,
                "filesystem_root": str(a_fs),
                "attestation": str(a_attestation),
            },
            "B": {
                "store_url": b_store,
                "gateway_url": b_gateway,
                "filesystem_root": str(b_fs),
                "attestation": str(b_attestation),
            },
        },
        "gates": {
            "suite_noninferiority_margin": 0,
            "recall_noninferiority_margin": 0.02,
            "mrr_noninferiority_margin": 0.02,
            "minimum_tool_call_reduction": 0.10,
            "maximum_wrong_hit_mean_increase": 0,
            "maximum_wrong_hit_per_trial_increase": 0,
            "maximum_wrong_hit_total_increase": 0,
        },
    }
    return _write_json(inputs / "spec.json", spec), tmp_path / "registry", pins


def _create(tmp_path: Path, **spec_options):
    spec, registry, pins = _make_spec(tmp_path, **spec_options)
    status = ter.create_evaluation(registry, spec, now=T0, nonce="fixed-test-nonce")
    return registry, status["eval_id"], status, pins


def _exports(tmp_path: Path) -> dict[str, Path]:
    """Exports must originate inside each condition's attested sandbox root."""
    mapping = {"mappings": {"properties": {"text": {"type": "text"}}}}
    config = {"retriever": "linear", "version": 1}
    a_root = tmp_path / "isolated" / "a" / "export"
    b_root = tmp_path / "isolated" / "b" / "export"
    return {
        "a_mapping": _write_json(a_root / "mapping.json", mapping),
        "a_docs": _write_text(a_root / "documents.jsonl", '{"_id":"a","_source":{"text":"old"}}\n'),
        "a_config": _write_json(a_root / "config.json", config),
        "b_mapping": _write_json(b_root / "mapping.json", mapping),
        "b_docs": _write_text(
            b_root / "documents.jsonl",
            '{"_id":"a","_source":{"text":"old"}}\n{"_id":"b","_source":{"text":"learned"}}\n',
        ),
        "b_config": _write_json(b_root / "config.json", config),
    }


def _ready_conditions(tmp_path: Path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0)
    ter.open_condition_b(registry, eval_id, now=T0 + timedelta(hours=1))
    status = ter.capture_condition_b(
        registry,
        eval_id,
        exports["b_mapping"],
        exports["b_docs"],
        exports["b_config"],
        now=T0 + timedelta(hours=1),
    )
    return registry, eval_id, status, exports


def _trial_payload(status: dict, condition: str, seed: int, *, wrong_hits: int = 0) -> dict:
    a = condition == "A"
    return {
        "schema_version": "traum.eval.trial.v2",
        "eval_id": status["eval_id"],
        "condition": condition,
        "seed": seed,
        "input_fingerprint": status["invariants"]["input_fingerprint"],
        "condition_export_fingerprint": status["conditions"][condition]["export"]["export_fingerprint"],
        "runtime_fingerprints": {name: value["sha256"] for name, value in status["pins"].items()},
        "side_effects": {
            "isolated": True,
            "production_writes": 0,
            "input_mutations": 0,
            "auto_apply_enabled": False,
        },
        "metrics": {
            "suite_score": 50 if a else 52,
            "max_suite_score": 60,
            "tool_call_count": 100 if a else 85,
            "wrong_kb_hits": wrong_hits,
            "retrieval_recall_at_1": 0.80,
            "retrieval_recall_at_3": 0.90,
            "retrieval_mrr": 0.85,
        },
    }


def _record_all_trials(tmp_path: Path, registry: Path, eval_id: str, status: dict, *, b_wrong_hits: int = 0):
    for seed in status["trials"]["seeds"]:
        for condition in ("A", "B"):
            metrics = _write_json(
                tmp_path / "trial-inputs" / f"{condition}-{seed}.json",
                _trial_payload(status, condition, seed, wrong_hits=b_wrong_hits if condition == "B" else 0),
            )
            raw = _write_text(tmp_path / "trial-inputs" / f"{condition}-{seed}.jsonl", f'{{"seed":{seed},"condition":"{condition}"}}\n')
            ter.record_trial(registry, eval_id, condition, seed, metrics, [raw], now=T0 + timedelta(hours=2))


def test_create_freezes_all_pins_and_exposes_stable_gui_status(tmp_path):
    spec, registry, pins = _make_spec(tmp_path)
    before = {name: path.read_bytes() for name, path in pins.items()}
    status = ter.create_evaluation(registry, spec, now=T0, nonce="fixed-test-nonce")

    assert status["schema_version"] == "traum.eval.status.v2"
    assert status["stage"] == "initialized"
    assert status["next_actions"] == [{"action": "freeze-a", "blocked": False}]
    assert status["invariants"]["auto_apply_enabled"] is False
    assert status["invariants"]["network_calls_permitted"] is False
    assert status["readiness"] == {
        "baseline_frozen": False,
        "condition_b_not_before": None,
        "elapsed_window_satisfied": False,
        "condition_b_open": False,
        "condition_b_captured": False,
        "paired_trials_complete": False,
        "analysis_complete": False,
    }
    assert status["artifacts"][0]["kind"] == "plan"
    assert set(status["pins"]) == {"model", "prompt", "tool_schema", "retriever", "embedding", "dataset"}
    assert (registry / "registry.json").is_file()
    assert {name: path.read_bytes() for name, path in pins.items()} == before


@pytest.mark.parametrize(
    ("field", "url"),
    [
        ("a_store", "http://localhost:9200"),
        ("a_store", "http://127.0.0.1:9200"),
        ("a_store", "http://[::1]:9200"),
        ("a_gateway", "http://localhost:9700"),
        ("a_gateway", "http://127.0.0.1:9700"),
        ("a_gateway", "http://[::1]:9700"),
    ],
)
def test_rejects_production_ports_for_all_loopback_spellings(tmp_path, field, url):
    spec, registry, _ = _make_spec(tmp_path, **{field: url})
    with pytest.raises(ter.EvalError, match="hard-rejected production port") as caught:
        ter.create_evaluation(registry, spec, now=T0)
    assert caught.value.code == "production_endpoint"
    assert not (registry / "evaluations").exists()


def test_rejects_short_window_and_overlapping_condition_filesystems(tmp_path):
    spec, registry, _ = _make_spec(tmp_path, min_elapsed=3599)
    with pytest.raises(ter.EvalError) as caught:
        ter.create_evaluation(registry, spec, now=T0)
    assert caught.value.code == "elapsed_window_too_short"

    spec, registry, _ = _make_spec(tmp_path / "second")
    value = json.loads(spec.read_text(encoding="utf-8"))
    value["conditions"]["B"]["filesystem_root"] = value["conditions"]["A"]["filesystem_root"]
    b_attestation = Path(value["conditions"]["B"]["attestation"])
    attestation = json.loads(b_attestation.read_text(encoding="utf-8"))
    attestation["filesystem_root"] = value["conditions"]["A"]["filesystem_root"]
    _write_json(b_attestation, attestation)
    _write_json(spec, value)
    with pytest.raises(ter.EvalError) as caught:
        ter.create_evaluation(registry, spec, now=T0)
    assert caught.value.code == "unsafe_filesystem"


def test_real_elapsed_gate_and_separate_versioned_exports_preserve_inputs(tmp_path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    before = {name: path.read_bytes() for name, path in exports.items()}

    status = ter.freeze_condition_a(
        registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0
    )
    assert status["stage"] == "baseline_wait"
    a_manifest = Path(registry) / "evaluations" / eval_id / status["conditions"]["A"]["export"]["manifest"]
    assert "/A/v1/" in a_manifest.as_posix()
    with pytest.raises(ter.EvalError) as caught:
        ter.open_condition_b(registry, eval_id, now=T0 + timedelta(seconds=3599))
    assert caught.value.code == "elapsed_window"

    status = ter.open_condition_b(registry, eval_id, now=T0 + timedelta(hours=1))
    assert status["stage"] == "b_window_open"
    status = ter.capture_condition_b(
        registry, eval_id, exports["b_mapping"], exports["b_docs"], exports["b_config"], now=T0 + timedelta(hours=1)
    )
    assert status["stage"] == "trials_running"
    b_manifest = Path(registry) / "evaluations" / eval_id / status["conditions"]["B"]["export"]["manifest"]
    assert "/B/v1/" in b_manifest.as_posix()
    assert status["conditions"]["A"]["export"]["export_fingerprint"] != status["conditions"]["B"]["export"]["export_fingerprint"]
    assert {name: path.read_bytes() for name, path in exports.items()} == before


def test_b_mapping_or_config_drift_fails_before_any_b_export_is_written(tmp_path):
    second_root = tmp_path / "drift"
    registry, eval_id, _, _ = _create(second_root)
    exports = _exports(second_root)
    ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0)
    ter.open_condition_b(registry, eval_id, now=T0 + timedelta(hours=1))
    drifted = _write_json(second_root / "isolated" / "b" / "export" / "drifted-config.json", {"retriever": "rrf", "version": 2})
    with pytest.raises(ter.EvalError) as caught:
        ter.capture_condition_b(
            registry, eval_id, exports["b_mapping"], exports["b_docs"], drifted, now=T0 + timedelta(hours=1)
        )
    assert caught.value.code == "input_drift"
    assert not (registry / "evaluations" / eval_id / "conditions" / "B" / "v1" / "export").exists()


def test_identical_b_corpus_is_refused_as_causally_uninformative(tmp_path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0)
    ter.open_condition_b(registry, eval_id, now=T0 + timedelta(hours=1))
    unchanged = _write_text(
        tmp_path / "isolated" / "b" / "export" / "unchanged.jsonl",
        exports["a_docs"].read_text(encoding="utf-8"),
    )
    with pytest.raises(ter.EvalError) as caught:
        ter.capture_condition_b(
            registry, eval_id, exports["b_mapping"], unchanged, exports["b_config"], now=T0 + timedelta(hours=1)
        )
    assert caught.value.code == "no_learning_delta"
    assert not (registry / "evaluations" / eval_id / "conditions" / "B" / "v1" / "export").exists()


def test_reordered_b_corpus_without_any_document_change_is_refused(tmp_path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    baseline = _write_text(
        tmp_path / "isolated" / "a" / "export" / "two-docs.jsonl",
        '{"_id":"a","_source":{"text":"old"}}\n{"_id":"b","_source":{"text":"old"}}\n',
    )
    ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], baseline, exports["a_config"], now=T0)
    ter.open_condition_b(registry, eval_id, now=T0 + timedelta(hours=1))
    reordered = _write_text(
        tmp_path / "isolated" / "b" / "export" / "reordered.jsonl",
        '{"_id":"b","_source":{"text":"old"}}\n{"_id":"a","_source":{"text":"old"}}\n',
    )
    assert _sha(reordered) != _sha(baseline)
    with pytest.raises(ter.EvalError) as caught:
        ter.capture_condition_b(
            registry, eval_id, exports["b_mapping"], reordered, exports["b_config"], now=T0 + timedelta(hours=1)
        )
    assert caught.value.code == "no_learning_delta"


def test_capture_refuses_sources_outside_the_attested_condition_root(tmp_path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    outside = _write_text(tmp_path / "elsewhere" / "documents.jsonl", '{"_id":"a","_source":{"text":"old"}}\n')
    with pytest.raises(ter.EvalError) as caught:
        ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], outside, exports["a_config"], now=T0)
    assert caught.value.code == "unsafe_path"

    # A condition may not be frozen from the other condition's sandbox either.
    with pytest.raises(ter.EvalError) as second:
        ter.freeze_condition_a(registry, eval_id, exports["b_mapping"], exports["b_docs"], exports["b_config"], now=T0)
    assert second.value.code == "unsafe_path"
    assert not (registry / "evaluations" / eval_id / "conditions" / "A" / "v1" / "export").exists()


def test_capture_refuses_symlink_escape_into_production_root(tmp_path):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    outside = _write_text(tmp_path / "elsewhere" / "documents.jsonl", '{"_id":"a","_source":{"text":"old"}}\n')
    link = tmp_path / "isolated" / "a" / "export" / "linked.jsonl"
    link.symlink_to(outside)
    with pytest.raises(ter.EvalError) as caught:
        ter.freeze_condition_a(registry, eval_id, exports["a_mapping"], link, exports["a_config"], now=T0)
    assert caught.value.code == "unsafe_path"


def test_analysis_records_the_corpus_delta_that_justifies_the_comparison(tmp_path):
    registry, eval_id, status, exports = _ready_conditions(tmp_path)
    _record_all_trials(tmp_path, registry, eval_id, status)
    analyzed = ter.analyze_evaluation(registry, eval_id, now=T0 + timedelta(hours=3))
    summary = json.loads(
        (Path(registry) / "evaluations" / eval_id / "analysis" / "v1" / "summary.json").read_text(encoding="utf-8")
    )
    delta = summary["corpus_delta"]
    assert delta["comparable"] is True
    assert delta["added"] == 1 and delta["removed"] == 0 and delta["modified"] == 0
    assert analyzed["stage"] == "analyzed"


def test_manifest_reconciliation_resumes_after_interruption(tmp_path, monkeypatch):
    registry, eval_id, _, _ = _create(tmp_path)
    exports = _exports(tmp_path)
    real_write_state = ter._write_state

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("simulated interruption after manifest commit")

    monkeypatch.setattr(ter, "_write_state", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        ter.freeze_condition_a(
            registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0
        )
    monkeypatch.setattr(ter, "_write_state", real_write_state)

    # Status reconstructs the completed capture from its immutable manifest.
    assert ter.get_status(registry, eval_id, now=T0)["stage"] == "baseline_wait"
    resumed = ter.freeze_condition_a(
        registry, eval_id, exports["a_mapping"], exports["a_docs"], exports["a_config"], now=T0
    )
    assert resumed["conditions"]["A"]["export"] is not None


def test_repeated_paired_trials_hash_raw_artifacts_and_require_pinned_runtime(tmp_path):
    registry, eval_id, status, _ = _ready_conditions(tmp_path)
    bad = _trial_payload(status, "A", 101)
    bad["runtime_fingerprints"]["model"] = "f" * 64
    bad_metrics = _write_json(tmp_path / "bad.json", bad)
    raw = _write_text(tmp_path / "bad.raw", "raw")
    with pytest.raises(ter.EvalError) as caught:
        ter.record_trial(registry, eval_id, "A", 101, bad_metrics, [raw], now=T0 + timedelta(hours=2))
    assert caught.value.code == "trial_mismatch"

    _record_all_trials(tmp_path, registry, eval_id, status)
    complete = ter.get_status(registry, eval_id, now=T0 + timedelta(hours=2))
    assert complete["stage"] == "trials_complete"
    manifest_ref = complete["trials"]["entries"]["101"]["A"]["manifest"]
    manifest = json.loads((registry / "evaluations" / eval_id / manifest_ref).read_text(encoding="utf-8"))
    assert len(manifest["artifacts"]) == 1
    raw_target = registry / "evaluations" / eval_id / manifest["artifacts"][0]["artifact"]
    assert _sha(raw_target) == manifest["artifacts"][0]["sha256"]
    raw_index = [item for item in complete["artifacts"] if item["kind"] == "trial-raw"]
    assert len(raw_index) == 6
    assert all(_sha(registry / "evaluations" / eval_id / item["artifact"]) == item["sha256"] for item in raw_index)


def test_analysis_uses_paired_confidence_intervals_noninferiority_and_wrong_hit_gates(tmp_path):
    registry, eval_id, status, _ = _ready_conditions(tmp_path)
    _record_all_trials(tmp_path, registry, eval_id, status)
    analyzed = ter.analyze_evaluation(registry, eval_id, now=T0 + timedelta(hours=3))
    assert analyzed["stage"] == "analyzed"
    assert analyzed["analysis"]["outcome"] == "WIN"
    assert all(analyzed["analysis"]["gate_results"].values())
    assert analyzed["analysis"]["lift_results"]["suite_superiority"] is True
    assert analyzed["analysis"]["promotion"]["eligible_for_policy_review"] is True
    assert analyzed["analysis"]["promotion"]["auto_apply_enabled"] is False
    summary_path = registry / "evaluations" / eval_id / analyzed["analysis"]["artifact"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "WIN"
    assert summary["confidence_intervals"]["suite_score_delta"]["method"] == "paired_student_t"
    assert summary["confidence_intervals"]["suite_score_delta"]["lower"] > 0
    assert all(summary["gate_results"].values())
    assert summary["promotion"]["auto_apply_enabled"] is False

    loss_root = tmp_path / "wrong-hit-loss"
    registry, eval_id, status, _ = _ready_conditions(loss_root)
    _record_all_trials(loss_root, registry, eval_id, status, b_wrong_hits=1)
    analyzed = ter.analyze_evaluation(registry, eval_id, now=T0 + timedelta(hours=3))
    assert analyzed["analysis"]["outcome"] == "LOSS"
    assert analyzed["analysis"]["promotion"]["eligible_for_policy_review"] is False
    summary_path = registry / "evaluations" / eval_id / analyzed["analysis"]["artifact"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "LOSS"
    assert summary["gate_results"]["wrong_hit_each_trial"] is False
    assert summary["gate_results"]["wrong_hit_total"] is False


def test_analysis_artifact_is_immutable_after_state_records_its_hash(tmp_path):
    registry, eval_id, status, _ = _ready_conditions(tmp_path)
    _record_all_trials(tmp_path, registry, eval_id, status)
    analyzed = ter.analyze_evaluation(registry, eval_id, now=T0 + timedelta(hours=3))
    summary_path = registry / "evaluations" / eval_id / analyzed["analysis"]["artifact"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["outcome"] = "NULL"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ter.EvalError, match="immutable analysis hash mismatch"):
        ter.get_status(registry, eval_id, now=T0 + timedelta(hours=4))


def test_large_finite_samples_keep_student_t_critical_value():
    critical = ter._t_critical_975(31)
    assert 1.96 < critical < 2.05
    assert ter._t_critical_975(10) == 2.228


def test_continuous_evidence_tracks_outcomes_but_cannot_enable_auto_apply(tmp_path):
    registry = tmp_path / "registry"
    event = {
        "schema_version": "traum.continuous-evidence.v1",
        "proposal_id": "proposal-1",
        "proposal_type": "dedup-exact",
        "observed_at": "2026-07-27T12:00:00Z",
        "decision": {"outcome": "accepted", "decided_by": "human"},
        "reversal": {"status": "not_observed"},
        "retrieval": {"opportunities": 3, "retrieved": 2, "used": 1},
        "usefulness": {"observations": 1, "positive": 1, "negative": 0},
        "source_artifacts": [{"sha256": "a" * 64}],
        "auto_apply": {"enabled": False},
    }
    event_path = _write_json(tmp_path / "event.json", event)
    result = ter.record_evidence(registry, event_path)
    assert result["event_id"].startswith("evidence-")
    assert result["auto_apply_enabled"] is False
    summary = ter.evidence_summary(registry)
    evidence = summary["proposal_types"]["dedup-exact"]
    assert evidence["acceptance"]["rate"] == 1
    assert evidence["reversal"] is None
    assert evidence["retrieval"]["used"] == 1
    assert evidence["auto_apply_eligibility"]["eligible_for_policy_review"] is False
    assert evidence["auto_apply_eligibility"]["auto_apply_enabled"] is False

    event["proposal_id"] = "unsafe"
    event["auto_apply"]["enabled"] = True
    unsafe_path = _write_json(tmp_path / "unsafe-event.json", event)
    with pytest.raises(ter.EvalError) as caught:
        ter.record_evidence(registry, unsafe_path)
    assert caught.value.code == "unsafe_evidence"


def test_continuous_evidence_uses_latest_snapshot_per_proposal(tmp_path):
    registry = tmp_path / "registry"
    event = {
        "schema_version": "traum.continuous-evidence.v1",
        "proposal_id": "proposal-1",
        "proposal_type": "dedup-exact",
        "observed_at": "2026-07-27T12:00:00Z",
        "decision": {"outcome": "accepted", "decided_by": "human"},
        "reversal": {"status": "not_observed"},
        "retrieval": {"opportunities": 3, "retrieved": 2, "used": 1},
        "usefulness": {"observations": 1, "positive": 1, "negative": 0},
        "source_artifacts": [{"sha256": "a" * 64}],
        "auto_apply": {"enabled": False},
    }
    ter.record_evidence(registry, _write_json(tmp_path / "first.json", event))
    later = json.loads(json.dumps(event))
    later["observed_at"] = "2026-07-28T12:00:00Z"
    later["reversal"] = {"status": "confirmed_not_reversed"}
    later["retrieval"] = {"opportunities": 5, "retrieved": 4, "used": 3}
    later["usefulness"] = {"observations": 3, "positive": 2, "negative": 1}
    ter.record_evidence(registry, _write_json(tmp_path / "later.json", later))

    evidence = ter.evidence_summary(registry)["proposal_types"]["dedup-exact"]
    assert evidence["event_count"] == 2
    assert evidence["acceptance"]["total"] == 1
    assert evidence["reversal"]["total"] == 1
    assert evidence["retrieval"] == {"opportunities": 5, "retrieved": 4, "used": 3}
    assert evidence["usefulness"]["total"] == 3


def test_cli_status_is_typed_json_and_schemas_are_valid_json(tmp_path, capsys):
    registry, eval_id, _, _ = _create(tmp_path)
    assert traum_eval.main(["--registry", str(registry), "--compact", "status", "--eval-id", eval_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "traum.eval.status.v2"
    assert payload["registry_path"] == str(registry.resolve())

    for name in (
        "traum-isolation-attestation-v1.schema.json",
        "traum-eval-spec-v2.schema.json",
        "traum-eval-trial-v2.schema.json",
        "traum-eval-status-v2.schema.json",
        "traum-eval-registry-v2.schema.json",
        "traum-continuous-evidence-v1.schema.json",
        "traum-evidence-summary-v1.schema.json",
    ):
        schema = json.loads((REPO_ROOT / "eval" / name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
