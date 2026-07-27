"""Security and lifecycle contracts for the typed TRAUM GUI controller."""

import importlib.util
import io
import os
import sys
import threading
import time
import types
from datetime import date, timedelta

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.abspath(os.path.join(_HERE, "..", "tools"))
_PATH = os.path.join(_TOOLS, "traum_controller.py")

spec = importlib.util.spec_from_file_location("traum_controller_under_test", _PATH)
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)


class _ImmediateProcess:
    def __init__(self, argv, capture, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.stdout = io.StringIO("[dream_runner] done. n_proposals=0\n")
        self._returncode = None
        capture.append(self)

    def poll(self):
        return self._returncode

    def wait(self):
        self._returncode = 0
        return 0

    def terminate(self):
        self._returncode = -15


class _BlockingStream:
    def __init__(self, stopped):
        self.stopped = stopped

    def __iter__(self):
        return self

    def __next__(self):
        if self.stopped.wait(0.01):
            raise StopIteration
        return "still running\n"


class _BlockingProcess:
    def __init__(self, argv, capture, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.stopped = threading.Event()
        self.stdout = _BlockingStream(self.stopped)
        self._returncode = None
        capture.append(self)

    def poll(self):
        return self._returncode

    def wait(self):
        self.stopped.wait(2)
        return self._returncode if self._returncode is not None else 0

    def terminate(self):
        self._returncode = -15
        self.stopped.set()


def _controller(tmp_path, process_type=_ImmediateProcess, command_runner=None):
    captured = []

    def popen(argv, **kwargs):
        return process_type(argv, captured, **kwargs)

    if command_runner is None:
        def command_runner(*_args, **_kwargs):
            return type("Result", (), {
                "returncode": 1, "stdout": "", "stderr": "no systemd"
            })()

    ctl = tc.TraumController(
        dream_dir=str(tmp_path),
        repo_root=os.path.abspath(os.path.join(_HERE, "..")),
        python_bin="/fixed/python3",
        popen_factory=popen,
        command_runner=command_runner,
    )
    return ctl, captured


def _wait_idle(ctl, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with ctl._lock:
            if not ctl._workers:
                return
        time.sleep(0.01)
    raise AssertionError("TRAUM worker did not become idle")


def test_raw_command_path_env_and_argv_fields_are_rejected(tmp_path):
    ctl, captured = _controller(tmp_path)
    for field in ("command", "path", "env", "argv"):
        with pytest.raises(tc.TraumControlError, match="unsupported field"):
            ctl.start_run({"profile": "standard", field: "anything"})
    assert captured == []
    assert ctl.state.list_runs() == []


def test_single_pass_uses_fixed_shell_false_argv_and_canonical_ids(tmp_path):
    ctl, captured = _controller(tmp_path)
    run = ctl.start_run({
        "profile": "single-pass", "pass": "patterns",
        "sessions": 12, "wall_clock_minutes": 5,
    })
    _wait_idle(ctl)

    assert len(captured) == 1
    child = captured[0]
    assert child.kwargs["shell"] is False
    assert child.argv[:2] == ["/fixed/python3", ctl._runner_path]
    assert child.argv[child.argv.index("--pass") + 1] == "patterns"
    assert child.argv[child.argv.index("--sessions") + 1] == "12"
    assert child.argv[child.argv.index("--run-id") + 1] == run["run_id"]
    attempt = ctl.state.list_attempts(run_id=run["run_id"])[0]
    assert child.argv[child.argv.index("--attempt-id") + 1] == attempt["attempt_id"]
    assert child.argv[child.argv.index("--state-db") + 1] == ctl.state.db_path
    assert ctl.state.get_run(run["run_id"])["state"] == "SUCCEEDED"
    if os.name == "posix":
        log_path = attempt["artifacts"]["log_path"]
        assert os.stat(log_path).st_mode & 0o777 == 0o600
        assert os.stat(os.path.dirname(log_path)).st_mode & 0o777 == 0o700


def test_cancel_rejects_unowned_process_and_terminates_only_owned_child(tmp_path):
    ctl, captured = _controller(tmp_path, process_type=_BlockingProcess)
    external = ctl.state.create_run("single-pass", ["dedup"], source="test")
    ctl.state.start_attempt(external["run_id"], "dedup")
    with pytest.raises(tc.TraumControlError, match="not owned"):
        ctl.cancel(external["run_id"], {})
    external_attempt = ctl.state.list_attempts(run_id=external["run_id"])[0]
    ctl.state.finish_attempt(external_attempt["attempt_id"], "FAILED")

    owned = ctl.start_run({
        "profile": "single-pass", "pass": "dedup",
        "sessions": 1, "wall_clock_minutes": 5,
    })
    deadline = time.monotonic() + 2
    while not captured and time.monotonic() < deadline:
        time.sleep(0.01)
    assert captured
    ctl.cancel(owned["run_id"], {})
    _wait_idle(ctl)
    assert captured[0].stopped.is_set()
    assert ctl.state.get_run(owned["run_id"])["state"] == "CANCELLED"

    cancelled = ctl.state.create_run("single-pass", ["patterns"], source="test")
    failed = ctl.state.start_attempt(cancelled["run_id"], "patterns")
    ctl.state.finish_attempt(failed["attempt_id"], "FAILED")
    ctl.state.request_cancel(cancelled["run_id"])
    ctl.state.finalize_cancelled_run(cancelled["run_id"])
    with pytest.raises(tc.TraumControlError, match="cannot be retried"):
        ctl.retry(cancelled["run_id"], {"attempt_id": failed["attempt_id"]})


def test_post_restart_active_state_is_reported_unowned_without_pid_action(tmp_path):
    ctl, _ = _controller(tmp_path)
    run = ctl.state.create_run("single-pass", ["patterns"], source="test")
    ctl.state.start_attempt(run["run_id"], "patterns")

    row = ctl.get_run(run["run_id"])
    assert row["state"] == "RUNNING"
    assert row["controller_owned"] is False
    assert row["control_ownership"] == "unowned-active-state"
    assert "no PID action" in row["control_note"]
    status = ctl.status()
    assert status["unowned_active_run_count"] == 1
    assert status["unowned_active_run_ids"] == [run["run_id"]]
    with pytest.raises(tc.TraumControlError, match="not owned"):
        ctl.cancel(run["run_id"], {})


@pytest.mark.parametrize("exit_code, expected", [(3, "BLOCKED"), (4, "CANCELLED")])
def test_typed_runner_exit_codes_are_not_misreported_as_failed(
        tmp_path, exit_code, expected):
    captured = []

    class TypedExit(_ImmediateProcess):
        def wait(self):
            self._returncode = exit_code
            return exit_code

    def popen(argv, **kwargs):
        return TypedExit(argv, captured, **kwargs)

    ctl = tc.TraumController(
        dream_dir=str(tmp_path),
        repo_root=os.path.abspath(os.path.join(_HERE, "..")),
        python_bin="/fixed/python3", popen_factory=popen,
    )
    run = ctl.start_run({
        "profile": "single-pass", "pass": "patterns",
        "sessions": 1, "wall_clock_minutes": 5,
    })
    _wait_idle(ctl)
    attempt = ctl.state.list_attempts(run_id=run["run_id"])[0]
    assert attempt["state"] == expected
    assert ctl.state.get_run(run["run_id"])["state"] == expected


def test_spawn_failure_terminalizes_attempt_and_run(tmp_path):
    def broken_popen(*_args, **_kwargs):
        raise OSError("spawn unavailable")

    ctl = tc.TraumController(
        dream_dir=str(tmp_path),
        repo_root=os.path.abspath(os.path.join(_HERE, "..")),
        python_bin="/fixed/python3", popen_factory=broken_popen,
    )
    run = ctl.start_run({
        "profile": "single-pass", "pass": "insights",
        "sessions": 1, "wall_clock_minutes": 5,
    })
    _wait_idle(ctl)
    assert ctl.state.get_run(run["run_id"])["state"] == "FAILED"
    assert ctl.state.list_attempts(run_id=run["run_id"])[0]["state"] == "FAILED"


def test_unexpected_controller_exception_terminalizes_missing_attempts(tmp_path):
    ctl, _ = _controller(tmp_path)

    def explode(*_args, **_kwargs):
        raise RuntimeError("controller bug")

    ctl._execute_pass = explode
    run = ctl.start_run({
        "profile": "single-pass", "pass": "patterns",
        "sessions": 1, "wall_clock_minutes": 5,
    })
    _wait_idle(ctl)
    current = ctl.state.get_run(run["run_id"])
    attempts = ctl.state.list_attempts(run_id=run["run_id"])
    assert current["state"] == "FAILED"
    assert len(attempts) == 1 and attempts[0]["state"] == "FAILED"
    assert "controller failure" in attempts[0]["summary"]["message"]


def test_concurrent_start_admission_does_not_leave_queued_orphan(tmp_path):
    ctl, captured = _controller(tmp_path, process_type=_BlockingProcess)
    barrier = threading.Barrier(3)
    outcomes = []

    def start():
        barrier.wait()
        try:
            outcomes.append(ctl.start_run({
                "profile": "single-pass", "pass": "dedup",
                "sessions": 1, "wall_clock_minutes": 5,
            }))
        except tc.TraumControlError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(2)
    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert sum(isinstance(item, tc.TraumControlError) for item in outcomes) == 1
    runs = ctl.state.list_runs(include_archived=True)
    assert len(runs) == 1
    deadline = time.monotonic() + 2
    while ctl.state.get_run(runs[0]["run_id"])["state"] == "QUEUED" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ctl.state.get_run(runs[0]["run_id"])["state"] != "QUEUED"
    winner = next(item for item in outcomes if isinstance(item, dict))
    ctl.cancel(winner["run_id"], {})
    _wait_idle(ctl)


def test_two_gateways_losing_retry_race_cannot_fail_winner_attempt(tmp_path):
    captured = []

    def popen(argv, **kwargs):
        return _BlockingProcess(argv, captured, **kwargs)

    ctl1 = tc.TraumController(
        dream_dir=str(tmp_path),
        repo_root=os.path.abspath(os.path.join(_HERE, "..")),
        python_bin="/fixed/python3", popen_factory=popen,
    )
    ctl2 = tc.TraumController(
        dream_dir=str(tmp_path),
        repo_root=os.path.abspath(os.path.join(_HERE, "..")),
        python_bin="/fixed/python3", popen_factory=popen,
    )
    run = ctl1.state.create_run(
        "single-pass", ["dedup"], source="gui", lease_seconds=300
    )
    failed = ctl1.state.start_attempt(run["run_id"], "dedup")
    ctl1.state.finish_attempt(failed["attempt_id"], "FAILED")

    barrier = threading.Barrier(3)
    original1 = ctl1._execute_pass
    original2 = ctl2._execute_pass

    def gated1(*args, **kwargs):
        barrier.wait(timeout=2)
        return original1(*args, **kwargs)

    def gated2(*args, **kwargs):
        barrier.wait(timeout=2)
        return original2(*args, **kwargs)

    ctl1._execute_pass = gated1
    ctl2._execute_pass = gated2
    ctl1.retry(run["run_id"], {"attempt_id": failed["attempt_id"]})
    ctl2.retry(run["run_id"], {"attempt_id": failed["attempt_id"]})
    barrier.wait(timeout=2)

    deadline = time.monotonic() + 2
    while not captured and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(captured) == 1
    # Let the losing worker run its controller-failure cleanup.  It owns no
    # canonical attempt, so the winner must remain RUNNING.
    time.sleep(0.1)
    attempts = ctl1.state.list_attempts(run_id=run["run_id"])
    active = [row for row in attempts if row["state"] == "RUNNING"]
    assert len(active) == 1
    owner = ctl1 if run["run_id"] in ctl1._processes else ctl2
    loser = ctl2 if owner is ctl1 else ctl1
    _wait_idle(loser)
    assert ctl1.state.get_attempt(active[0]["attempt_id"])["state"] == "RUNNING"

    owner.cancel(run["run_id"], {})
    _wait_idle(owner)


def test_logs_choose_newest_attempt_are_bounded_and_redacted(tmp_path):
    ctl, _ = _controller(tmp_path)
    run = ctl.state.create_run("single-pass", ["dedup"], source="test")

    old = ctl.state.start_attempt(run["run_id"], "dedup")
    old_path = ctl._attempt_log_path(old["attempt_id"])
    os.makedirs(os.path.dirname(old_path), exist_ok=True)
    with open(old_path, "w", encoding="utf-8") as fh:
        fh.write("old log\n")
    ctl.state.finish_attempt(
        old["attempt_id"], "FAILED", artifacts={"log_path": old_path})

    new = ctl.state.start_attempt(
        run["run_id"], "dedup", retry_of=old["attempt_id"])
    new_path = ctl._attempt_log_path(new["attempt_id"])
    with open(new_path, "w", encoding="utf-8") as fh:
        fh.write("first\nsecond\nsk-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n")
    ctl.state.finish_attempt(
        new["attempt_id"], "SUCCEEDED", artifacts={"log_path": new_path})

    result = ctl.logs(run["run_id"], limit=2)
    assert result["attempt_id"] == new["attempt_id"]
    assert "old log" not in result["text"]
    assert "first" not in result["text"]
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890" not in result["text"]
    assert result["truncated"] is True


def test_timer_probe_is_read_only_fixed_unit_and_fixed_argv(tmp_path):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Result", (), {
            "returncode": 0,
            "stdout": "ActiveState=active\nSubState=waiting\nUnitFileState=enabled\n",
            "stderr": "",
        })()

    ctl, _ = _controller(tmp_path, command_runner=runner)
    result = ctl.timer_status()
    assert result["active_state"] == "active"
    assert result["read_only"] is True
    argv, kwargs = calls[0]
    assert argv[:3] == ["systemctl", "show", "goethe-dream.timer"]
    assert kwargs["shell"] is False
    assert not any(word in argv for word in ("start", "stop", "enable", "disable"))


def test_empty_v2_registry_reports_historical_v1_without_reframing(
        tmp_path, monkeypatch):
    fake_eval = types.SimpleNamespace(
        DEFAULT_REGISTRY="/not-exposed",
        list_statuses=lambda _root: {"evaluations": []},
        evidence_summary=lambda _root: {"proposal_types": {}},
    )
    monkeypatch.setitem(sys.modules, "traum_eval", fake_eval)
    ctl, _ = _controller(tmp_path)

    result = ctl.evaluation_status()
    assert result["analysis_available"] is False
    assert result["analysis_complete"] is False
    assert result["promotion_eligible"] is False
    assert result["analysis_label"] == "analysis pending"
    assert result["latest_evidence"] is None
    assert result["historical_v1"] == {
        "evaluation_id": "eval-report-traum-1",
        "executed_on": "2026-07-12",
        "protocol_verdict": "LOSS",
        "causal_interpretation": "INCONCLUSIVE",
        "artifact": "eval-report-traum-1.md",
        "scope": "historical v1; not evidence from the isolated v2 registry",
    }
    assert "/not-exposed" not in str(result)


def test_analyzed_v2_registry_exposes_gates_and_lift_as_analysis_not_win(
        tmp_path, monkeypatch):
    fake_eval = types.SimpleNamespace(
        DEFAULT_REGISTRY="/not-exposed",
        list_statuses=lambda _root: {"evaluations": [{
            "eval_id": "eval_20260727_example",
            "stage": "analyzed",
            "updated_at": "2026-07-27T12:00:00Z",
            "analysis": {
                "artifact": "analysis/v1/summary.json",
                "sha256": "a" * 64,
                "outcome": "NULL",
                "corpus_delta": {
                    "comparable": True,
                    "baseline_documents": 10,
                    "candidate_documents": 12,
                    "added": 2,
                    "removed": 0,
                    "modified": 1,
                    "changed_document_ids": ["kb-101", "kb-102", "kb-7"],
                },
                "gate_results": {"suite_noninferiority": True},
                "lift_results": {"suite_superiority": False},
                "promotion": {
                    "eligible_for_policy_review": False,
                    "auto_apply_enabled": False,
                },
            },
            "next_actions": [],
        }]},
        evidence_summary=lambda _root: {"proposal_types": {}},
    )
    monkeypatch.setitem(sys.modules, "traum_eval", fake_eval)
    ctl, _ = _controller(tmp_path)

    result = ctl.evaluation_status()
    assert result["analysis_available"] is True
    assert result["analysis_complete"] is True
    assert result["analysis_label"] == "analysis available"
    assert result["promotion_eligible"] is False
    assert result["latest_evidence"]["outcome"] == "NULL"
    assert result["latest_evidence"]["gate_results"] == {
        "suite_noninferiority": True,
    }
    assert result["latest_evidence"]["lift_results"] == {
        "suite_superiority": False,
    }
    assert result["latest_evidence"]["learning_delta"] == {
        "baseline_documents": 10,
        "candidate_documents": 12,
        "added": 2,
        "removed": 0,
        "modified": 1,
    }
    # Document identifiers stay in the offline registry, not the web response.
    assert "kb-101" not in str(result)
    assert "historical_v1" not in result


def test_actionable_inbox_hides_future_deferred_and_resurfaces_due(tmp_path):
    ctl, _ = _controller(tmp_path)
    run = ctl.state.create_run("single-pass", ["patterns"], source="test")
    attempt = ctl.state.start_attempt(run["run_id"], "patterns")
    proposals = ctl.state.record_proposals(run["run_id"], attempt["attempt_id"], [
        {"type": "kb-fact", "call": "index_to_kb", "args": {"title": "future"}, "why": "future"},
        {"type": "kb-fact", "call": "index_to_kb", "args": {"title": "due"}, "why": "due"},
        {"type": "kb-fact", "call": "index_to_kb", "args": {"title": "pending"}, "why": "pending"},
    ])
    ctl.state.finish_attempt(attempt["attempt_id"], "SUCCEEDED")
    future, due, pending = proposals
    ctl.state.transition_proposal(
        future["proposal_id"], "defer",
        defer_until=(date.today() + timedelta(days=10)).isoformat(),
    )
    ctl.state.transition_proposal(
        due["proposal_id"], "defer",
        defer_until=(date.today() - timedelta(days=1)).isoformat(),
    )

    actionable = ctl.list_proposals(
        state="PENDING,DEFERRED,APPLY_FAILED", actionable_only=True, limit=2,
    )
    ids = {row["proposal_id"] for row in actionable["proposals"]}
    assert due["proposal_id"] in ids
    assert pending["proposal_id"] in ids
    assert future["proposal_id"] not in ids
    assert actionable["hidden_future_deferred"] == 1
    assert actionable["returned_count"] == 2
    assert actionable["total_visible"] == 2
    assert actionable["total_matching"] == 3
    assert actionable["counts_exact"] is True
    assert actionable["truncated"] is False
    status = ctl.status()
    assert status["due_deferred_count"] == 1
    assert status["future_deferred_count"] == 1
    assert status["human_gate_count"] == 2
    assert status["human_gate_count_exact"] is True


def test_proposal_queue_reports_exact_total_and_offset_page(tmp_path):
    ctl, _ = _controller(tmp_path)
    run = ctl.state.create_run("single-pass", ["patterns"], source="test")
    attempt = ctl.state.start_attempt(run["run_id"], "patterns")
    proposals = ctl.state.record_proposals(
        run["run_id"], attempt["attempt_id"], [
            {
                "type": "kb-fact",
                "call": "index_to_kb",
                "args": {"title": f"proposal {index}"},
                "why": f"reason {index}",
            }
            for index in range(7)
        ],
    )
    ctl.state.finish_attempt(attempt["attempt_id"], "SUCCEEDED")

    page = ctl.list_proposals(
        state="PENDING", actionable_only=True, limit=3, offset=3,
    )
    assert [row["proposal_id"] for row in page["proposals"]] == [
        row["proposal_id"] for row in proposals[3:6]
    ]
    assert page["returned_count"] == 3
    assert page["total_visible"] == 7
    assert page["total_matching"] == 7
    assert page["offset"] == 3
    assert page["truncated"] is True
    assert page["counts_exact"] is True


def test_real_dream_apply_preview_honors_revision_and_is_side_effect_free(tmp_path):
    ctl, _ = _controller(tmp_path)
    run = ctl.state.create_run("single-pass", ["insights"], source="test")
    attempt = ctl.state.start_attempt(run["run_id"], "insights")
    proposal = ctl.state.record_proposals(run["run_id"], attempt["attempt_id"], [{
        "type": "prompt-rule",
        "call": "append_learned_rule",
        "args": {
            "target_file": "prompts/learned-rules.md",
            "rule": "Verify the active target before making a change.",
            "rationale": "Prevents a recurring wrong-target failure.",
            "section_hint": "ground-truth-before-action",
            "provenance": "dream-2026-07-27",
            "source_tier": "inferred",
        },
        "why": "The same target-selection mistake occurred in several sessions.",
    }])[0]
    ctl.state.finish_attempt(attempt["attempt_id"], "SUCCEEDED")

    class ReadOnlyTools:
        @staticmethod
        def _es():
            return object()

    import dream_apply
    original = dream_apply.preview_proposal

    def with_read_only_tools(*args, **kwargs):
        kwargs["tools"] = ReadOnlyTools()
        return original(*args, **kwargs)

    ctl._apply_module = type("ApplyAdapter", (), {
        "preview_proposal": staticmethod(with_read_only_tools),
    })()
    before = ctl.state.get_proposal(proposal["proposal_id"])
    preview = ctl.preview_proposal(
        proposal["proposal_id"], {"expected_revision": before["revision"]}
    )
    after = ctl.state.get_proposal(proposal["proposal_id"])
    assert preview["valid"] is True
    assert preview["side_effect_free"] is True
    assert (after["state"], after["revision"]) == (before["state"], before["revision"])

    with pytest.raises(tc.TraumControlError, match="revision changed"):
        ctl.preview_proposal(
            proposal["proposal_id"], {"expected_revision": before["revision"] - 1}
        )


def test_legacy_failure_reconciliation_is_stable_acknowledgeable_and_archivable(tmp_path):
    day = tmp_path / "2026-07-17"
    day.mkdir()
    (day / "crashes.jsonl").write_text(
        '{"pass":"error-cluster","error_text":"legacy boom"}\n',
        encoding="utf-8",
    )
    (day / "report-error-cluster.md").write_text(
        "# TRAUM report\n## FAILED\n", encoding="utf-8")

    ctl, _ = _controller(tmp_path)
    runs = ctl.list_runs()["runs"]
    legacy = next(row for row in runs if row["run_id"].startswith("legacy_20260717_"))
    assert legacy["state"] == "FAILED"
    attempt = legacy["attempts"][0]
    ack = ctl.acknowledge_attempt(attempt["attempt_id"], {})
    assert ack["acknowledged"] is True
    ctl.archive_run(legacy["run_id"], {})
    assert all(
        row["run_id"] != legacy["run_id"] for row in ctl.list_runs()["runs"]
    )
    archived = ctl.list_runs(include_archived=True)["runs"]
    assert next(row for row in archived if row["run_id"] == legacy["run_id"])["archived"]
    assert (day / "crashes.jsonl").exists()  # archive never deletes evidence
