#!/usr/bin/env python3
"""Contract tests for tools/node_facts.py (spec §6:
docs/SPEC-node-facts-and-profile-matcher-2026-08.md).

Load-bearing tests, called out explicitly in the spec:
  test 2 — deployment differences (e.g. --host) never produce drift
           (Hazard A: --host 0.0.0.0 vs 127.0.0.1 is an operator choice).
  test 6 — an unreachable node yields reachable: False, never zeroed
           hardware (Hazard C: never treat "asleep" as "no GPU").

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_node_facts.py -q
"""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import node_facts  # noqa: E402

PROFILE_DIR = node_facts.DEFAULT_PROFILE_DIR


def _profile(flags: dict, file: str = "synthetic.gguf.md") -> dict:
    return {"file": file, "flags": flags, "source": "documented"}


def _base_flags() -> dict:
    """A representative identity+hardware+deployment flag set, modeled on
    the real canonical files under /mnt/c/Goethe3.0."""
    return {
        "-m": "/home/sy5/models/unsloth/Qwen3.6-27B-UD-Q4_K_XL.gguf",
        "--alias": "Qwen3.6-27B",
        "--ctx-size": "131072",
        "--cache-type-k": "q8_0",
        "--cache-type-v": "q8_0",
        "--spec-type": "ngram-map-k4v",
        "-ngl": "99",
        "--threads": "15",
        "--threads-batch": "15",
        "--host": "0.0.0.0",
        "--port": "8080",
        "--slot-save-path": "/opt/local-se/slot-cache",
    }


class TestFlagClassificationIsTotal:
    """Test 1: every flag in all four real profile files lands in exactly
    one class; an unknown flag defaults to identity (fail loud rather than
    silently ignore a difference that might matter)."""

    def test_all_real_profile_flags_classify(self):
        profiles = node_facts.list_profiles(PROFILE_DIR)
        assert len(profiles) == 4, f"expected the 4 known canonical files, found {len(profiles)}"
        all_flags = set()
        for prof in profiles.values():
            all_flags |= set(prof["flags"].keys())
        assert all_flags, "no flags parsed out of the canonical profile files"
        for flag in all_flags:
            assert node_facts.classify_flag(flag) in ("identity", "hardware", "deployment")

    def test_hazard_a_table_examples(self):
        # spec §3's own examples, pinned so a future refactor can't quietly
        # move --host back into "identity" and start reporting it as drift.
        assert node_facts.classify_flag("-m") == "identity"
        assert node_facts.classify_flag("--alias") == "identity"
        assert node_facts.classify_flag("--ctx-size") == "identity"
        assert node_facts.classify_flag("--cache-type-k") == "identity"
        assert node_facts.classify_flag("--cache-type-v") == "identity"
        assert node_facts.classify_flag("--spec-type") == "identity"
        assert node_facts.classify_flag("--threads") == "hardware"
        assert node_facts.classify_flag("--threads-batch") == "hardware"
        assert node_facts.classify_flag("-ngl") == "hardware"
        assert node_facts.classify_flag("--batch-size") == "hardware"
        assert node_facts.classify_flag("--ubatch-size") == "hardware"
        assert node_facts.classify_flag("--host") == "deployment"
        assert node_facts.classify_flag("--port") == "deployment"
        assert node_facts.classify_flag("--path") == "deployment"
        assert node_facts.classify_flag("--log-file") == "deployment"
        assert node_facts.classify_flag("--slot-save-path") == "deployment"

    def test_unknown_flag_defaults_to_identity(self):
        assert node_facts.classify_flag("--nobody-has-ever-seen-this-flag") == "identity"


class TestDeploymentNeverDrift:
    """Test 2 (LOAD-BEARING, Hazard A): same profile, --host 0.0.0.0 vs
    127.0.0.1, still verdict: exact."""

    def test_host_difference_does_not_break_exact(self):
        canonical = _base_flags()
        live = dict(canonical)
        live["--host"] = "127.0.0.1"  # operator's deliberate choice
        profiles = {"a.gguf.md": _profile(canonical, "a.gguf.md")}
        result = node_facts.match_live(profiles, live_pid=4242, live_flags=live)
        assert result["verdict"] == "exact"
        best = result["ranked"][0]
        assert best["identity_diffs"] == []
        assert any(d["flag"] == "--host" for d in best["deployment_diffs"])


class TestIdentityDiffDowngrades:
    """Test 3: change -m, assert not exact and that the model appears in
    identity_diffs."""

    def test_model_change_downgrades_to_closest(self):
        canonical = _base_flags()
        live = dict(canonical)
        live["-m"] = "/home/sy5/models/some/other-model.gguf"
        profiles = {"a.gguf.md": _profile(canonical, "a.gguf.md")}
        result = node_facts.match_live(profiles, live_pid=4242, live_flags=live)
        assert result["verdict"] != "exact"
        assert result["verdict"] == "closest"
        best = result["ranked"][0]
        assert any(d["flag"] == "-m" for d in best["identity_diffs"])


class TestRankingPicksRightFile:
    """Test 4: ranking picks the right file among several similar profiles."""

    def test_zero_diff_profile_ranks_first(self):
        live = _base_flags()
        zero_diff = dict(live)
        one_diff = dict(live)
        one_diff["-m"] = "/home/sy5/models/other.gguf"
        two_diff = dict(one_diff)
        two_diff["--ctx-size"] = "65536"

        # Deliberately inserted out of best-to-worst order.
        profiles = {
            "two_diff.gguf.md": _profile(two_diff, "two_diff.gguf.md"),
            "one_diff.gguf.md": _profile(one_diff, "one_diff.gguf.md"),
            "zero_diff.gguf.md": _profile(zero_diff, "zero_diff.gguf.md"),
        }
        result = node_facts.match_live(profiles, live_pid=7, live_flags=live)
        assert result["verdict"] == "exact"
        assert result["best_match"]["file"] == "zero_diff.gguf.md"
        assert [r["file"] for r in result["ranked"]] == [
            "zero_diff.gguf.md", "one_diff.gguf.md", "two_diff.gguf.md",
        ]


class TestBomPrefixedFileParses:
    """Test 5: BOM-prefixed file parses — ACTUAL-...gguf.md has one."""

    def test_actual_file_bom_stripped(self):
        path = str(Path(PROFILE_DIR) / "ACTUAL-Qwen3.6-27B-UD-Q4_K_XL.gguf.md")
        prof = node_facts.parse_profile(path)
        assert prof["source"] == "documented"
        assert "-m" in prof["flags"]
        assert not prof["flags"]["-m"].startswith("﻿")
        assert prof["flags"]["-m"] == "/home/sy5/models/unsloth/Qwen3.6-27B-UD-Q4_K_XL.gguf"


class TestUnreachableNodeNeverZeroed:
    """Test 6 (LOAD-BEARING, Hazard C): unreachable node yields
    reachable: False, never zeroed hardware."""

    def test_ssh_failure_yields_null_hardware_not_zeros(self, monkeypatch):
        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=5)

        monkeypatch.setattr(node_facts.subprocess, "run", fake_run)
        result = node_facts.collect_hardware("node3090")
        assert result["host"]["reachable"] is False
        assert result["source"] == "unreachable"
        assert result["gpu"] is None
        assert result["cpu"] is None
        assert result["ram"] is None

    def test_ssh_nonzero_exit_also_yields_unreachable(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 255, stdout="", stderr="Connection refused")

        monkeypatch.setattr(node_facts.subprocess, "run", fake_run)
        result = node_facts.collect_hardware("node3090")
        assert result["host"]["reachable"] is False
        assert result["gpu"] is None
        assert result["cpu"] is None
        assert result["ram"] is None


class TestMissingModelRootNotException:
    """Test 7: missing model root is reachable: false, not an exception."""

    def test_missing_root(self):
        result = node_facts.collect_models(roots=["/definitely/does/not/exist/node-facts-test"])
        assert result["roots"][0]["reachable"] is False
        assert result["roots"][0]["files"] == []


class TestEveryFactCarriesSource:
    """Test 8: every fact carries its source
    (local-probe / ssh / documented / unreachable / local-scan)."""

    def test_local_hardware_source(self):
        result = node_facts.collect_hardware("node4090")
        assert result["source"] == "local-probe"

    def test_profile_source(self):
        profiles = node_facts.list_profiles(PROFILE_DIR)
        assert profiles
        for prof in profiles.values():
            assert prof["source"] == "documented"

    def test_ssh_source_on_simulated_success(self, monkeypatch):
        fake_stdout = "\n".join([
            "__HOST__", "node3090",
            "__KERNEL__", "6.8.0-136-generic",
            "__GPU__", "NVIDIA GeForce RTX 3090, 24576, 610.43.02",
            "__CUDA__", "CUDA UMD Version: 13.3",
            "__CPU__",
            "Model name: Intel(R) Core(TM) i9-9900K CPU @ 3.60GHz",
            "Socket(s): 1",
            "Core(s) per socket: 8",
            "CPU(s): 16",
            "Flags: fpu avx avx2",
            "__RAM__", "Mem: 33000000000 1 2 3 4 20000000000",
        ])

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=fake_stdout, stderr="")

        monkeypatch.setattr(node_facts.subprocess, "run", fake_run)
        result = node_facts.collect_hardware("node3090")
        assert result["source"] == "ssh"
        assert result["host"]["reachable"] is True
        assert result["gpu"][0]["name"] == "NVIDIA GeForce RTX 3090"

    def test_unreachable_source(self, monkeypatch):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 255, stdout="", stderr="")

        monkeypatch.setattr(node_facts.subprocess, "run", fake_run)
        result = node_facts.collect_hardware("node3090")
        assert result["source"] == "unreachable"

    def test_model_scan_source(self):
        result = node_facts.collect_models(roots=["/home/sy5/models"])
        assert result["roots"][0]["source"] == "local-scan"
        result_missing = node_facts.collect_models(roots=["/nope/not/here/node-facts-test"])
        assert result_missing["roots"][0]["source"] == "unreachable"
