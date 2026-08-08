"""Tests for SPEC-manual-dreaming-2026-08: dreaming becomes manual.

Covers spec §6 tests 1-4:
  1. traum_state.py accepts source="manual". Load-bearing.
  2. traum_state.py still accepts source="scheduled", and a pre-existing
     "scheduled" row still reads back through the run-table path.
     Load-bearing -- Hazard B.
  3. run-dream-cycle.sh passes --run-source manual (assert on the argv it
     builds, not on a live run).
  4. run-dream-cycle.sh passes --skip-session-guard by default, and omits
     it when the opt-out is given.

Test 5 (per-pass wall-clock allocation unchanged) is not repeated here --
it is already covered, against the actual shipped script, by
TestPerPassWallClockAllocation in tests/test_cycle_completes.py, and this
change does not touch that code region.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402
import traum_state as ts  # noqa: E402

CYCLE = REPO_ROOT / "tools" / "run-dream-cycle.sh"


def _store(tmp_path):
    return ts.TraumState(str(tmp_path / "traum-state.db"))


# --- Test 1 (load-bearing): "manual" source is accepted --------------------

def test_manual_source_is_accepted(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="manual")
    assert run["source"] == "manual"


def test_manual_source_gets_admission_control_like_gui_and_scheduled(tmp_path):
    """Widening the source set is meaningless if it does not also widen the
    same-run-active protection that gui/scheduled already get."""
    store = _store(tmp_path)
    store.create_run("single-pass", ["patterns"], source="manual", lease_seconds=300)
    with pytest.raises(ts.ConflictError):
        store.create_run("single-pass", ["dedup"], source="manual", lease_seconds=300)


def test_dream_runner_accepts_manual_run_source():
    """--run-source is an argparse choices= tuple (dream_runner.py:4024) --
    a location the spec's ground-truth table did not name. Widening only
    traum_state.py's two checks is not enough: an unwidened choices tuple
    would reject --run-source manual before traum_state.py ever saw it."""
    args = dr.parse_args(["--pass", "patterns", "--run-source", "manual"])
    assert args.run_source == "manual"


# --- Test 2 (load-bearing, Hazard B): "scheduled" must still work ----------

def test_scheduled_source_is_still_accepted(tmp_path):
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="scheduled")
    assert run["source"] == "scheduled"


def test_preexisting_scheduled_row_reads_back_through_run_table_path(tmp_path):
    """Simulates one of the historical rows carrying source='scheduled':
    created, then read back through get_run exactly as the Console's
    run-table path would."""
    store = _store(tmp_path)
    run = store.create_run("single-pass", ["patterns"], source="scheduled")
    reread = store.get_run(run["run_id"])
    assert reread is not None
    assert reread["source"] == "scheduled"


def test_legacy_import_source_is_unaffected_by_the_widened_set(tmp_path):
    """legacy-import bypasses the admission-control set entirely (it is not
    in {gui, scheduled, manual}) -- confirm widening that set did not
    accidentally start gating it."""
    store = _store(tmp_path)
    run = store.create_run("legacy", ["legacy"], {"day": "2026-08-08"},
                            source="legacy-import", run_id="legacy_test_row")
    assert run["source"] == "legacy-import"
    second = store.create_run("legacy", ["legacy"], {"day": "2026-08-09"},
                               source="legacy-import", run_id="legacy_test_row_2")
    assert second["source"] == "legacy-import"


# --- Test 3: run-dream-cycle.sh passes --run-source manual ------------------

def test_cycle_script_passes_run_source_manual():
    text = CYCLE.read_text(encoding="utf-8")
    assert "--run-source manual" in text
    assert "--run-source scheduled" not in text


# --- Test 4: --skip-session-guard defaults on, opt-out omits it ------------

class TestGuardDefaultOnManualEntryPoint:
    """Runs the real script (not a reimplementation) with a stub
    dream_runner.py/dream_digest.py/traum_state.py that just record the argv
    they were called with, so these assertions are against the actual
    shipped conditional, the same technique test_cycle_completes.py uses for
    the wall-clock formula."""

    @staticmethod
    def _run_cycle(tmp_path, env_overrides=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        capture = tmp_path / "argv.log"

        stub = (
            "#!/usr/bin/env bash\n"
            f"echo \"$0 $*\" >> \"{capture}\"\n"
            "exit 0\n"
        )
        python_stub = bin_dir / "python3-stub.sh"
        python_stub.write_text(stub)
        python_stub.chmod(0o755)

        env = {
            "PATH": "/usr/bin:/bin",
            "GOETHE_DREAM_PYTHON": str(python_stub),
            "GOETHE_DREAM_DIR": str(tmp_path / "dreams"),
            "GOETHE_EPISODE_DIR": str(tmp_path / "episodes"),
            "GOETHE_TRAUM_STATE_DB": str(tmp_path / "state.db"),
            "GOETHE_TRAUM_RUN_ID": "run_test_guard_default",
            "GOETHE_DREAM_CYCLE_MAX_SECONDS": "120",
        }
        if env_overrides:
            env.update(env_overrides)

        subprocess.run(
            ["bash", str(CYCLE)], env=env, capture_output=True, text=True, timeout=30,
        )
        if capture.exists():
            return capture.read_text()
        return ""

    def test_skip_session_guard_present_by_default(self, tmp_path):
        argv_log = self._run_cycle(tmp_path)
        pass_invocations = [
            line for line in argv_log.splitlines() if "dream_runner.py" in line
        ]
        assert pass_invocations, "expected at least one dream_runner.py invocation"
        assert all("--skip-session-guard" in line for line in pass_invocations)

    def test_skip_session_guard_omitted_with_explicit_opt_out(self, tmp_path):
        argv_log = self._run_cycle(
            tmp_path, env_overrides={"GOETHE_DREAM_SKIP_SESSION_GUARD": "0"}
        )
        pass_invocations = [
            line for line in argv_log.splitlines() if "dream_runner.py" in line
        ]
        assert pass_invocations, "expected at least one dream_runner.py invocation"
        assert all("--skip-session-guard" not in line for line in pass_invocations)


# --- Test 6: no test/fixture/doc this change touches treats the timer as
# a live mechanism (pre-existing tests/test_dream_service_units.py and
# traum_controller.py's read-only timer_status() are pre-existing, out of
# this spec's enumerated §4 scope, and are called out separately in the
# handover report rather than silently touched here) -------------------

def test_run_dream_cycle_no_longer_calls_out_run_source_as_scheduled_in_help_text():
    text = CYCLE.read_text(encoding="utf-8")
    assert not re.search(r"--run-source\s+scheduled", text)
