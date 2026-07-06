#!/usr/bin/env python3
"""Contract tests for the PROVE-IT surface (Goethe v0.3.6, PH3-1).

run_tests: scope validation, hardcoded-allowlist behavior, SKIP on missing
assets, kb scope against live ES (read-only).
assert_state: read-only argv allowlist, mutating-verb and metacharacter
rejection, curl GET-only guard, regex PASS/FAIL with verbatim output.

Run on LUCIFER: /home/sy5/owui/bin/python3 -m pytest tests/test_prove_it.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import goethe  # noqa: E402


@pytest.fixture()
def tools(tmp_path):
    t = goethe.Tools()
    t.valves.LOG_FILE = str(tmp_path / "audit.log")
    return t


class TestAssertStateAllowlist:
    def test_allowlisted_pass(self, tools):
        r = tools.assert_state("df -h /", r"Filesystem")
        assert r.startswith("ASSERT PASS ✅")
        assert "--- df -h / ---" in r  # verbatim output block present

    def test_regex_fail_reported_verbatim(self, tools):
        r = tools.assert_state("df -h /", r"THIS_WILL_NEVER_MATCH_9x9")
        assert r.startswith("ASSERT FAIL ❌")
        assert "Filesystem" in r  # output still shown as evidence

    def test_non_allowlisted_rejected(self, tools):
        r = tools.assert_state("rm -rf /tmp/x", ".")
        assert "rejected" in r
        assert "allowlist" in r

    def test_metacharacters_rejected(self, tools):
        r = tools.assert_state("df -h; ls /", ".")
        assert "rejected" in r and "metacharacters" in r
        r2 = tools.assert_state("df -h | wc -l", ".")
        assert "rejected" in r2

    def test_systemctl_mutating_verb_rejected(self, tools):
        r = tools.assert_state("systemctl restart ollama", "active")
        assert "rejected" in r
        assert "is-active" in r  # tells the model the allowed verbs

    def test_curl_write_flags_rejected(self, tools):
        r = tools.assert_state(
            "curl -s -X POST http://127.0.0.1:9200/lse-kb/_doc", "created"
        )
        assert "rejected" in r and "GET-only" in r

    def test_curl_get_probe_allowed(self, tools):
        # live read-only probe against local ES (always up on LUCIFER)
        r = tools.assert_state("curl http://127.0.0.1:9200/_cluster/health", '"status"')
        assert r.startswith("ASSERT PASS ✅")

    def test_ip_mutation_rejected(self, tools):
        r = tools.assert_state("ip addr add 10.0.0.1/24 dev lo", ".")
        assert "rejected" in r

    def test_invalid_regex_rejected(self, tools):
        r = tools.assert_state("df -h", "(unclosed")
        assert "invalid regex" in r

    def test_unknown_binary_clean_failure(self, tools):
        # allowlisted name but absent binary must fail cleanly, not raise
        r = tools.assert_state("nvidia-smi --list-gpus", "GPU")
        assert r.startswith(("ASSERT PASS ✅", "ASSERT FAIL ❌"))


class TestSshGuards:
    """v0.3.7 — post-mortem hardening (string-logic paths, no live SSH)."""

    def test_unbracketed_pkill_f_blocked(self, tools):
        r = tools.ssh_run("node3090.home.arpa", "pkill -f llama-server")
        assert "[PKILL_SELF_MATCH_GUARD]" in r
        assert "bracket" in r.lower()
        r2 = tools.ssh_run("node3090.home.arpa", "pkill -9 -f goethe_mcp.py")
        assert "[PKILL_SELF_MATCH_GUARD]" in r2

    def test_bracketed_pkill_passes_guard(self, tools):
        # unreachable TLD → immediate exit 255; must NOT be the pkill guard
        r = tools.ssh_run("host.invalid", "pkill -f 'llama[-]server'", timeout=15)
        assert "[PKILL_SELF_MATCH_GUARD]" not in r

    def test_pkill_by_name_allowed(self, tools):
        # no -f → matches process NAME only, no self-match risk
        r = tools.ssh_run("host.invalid", "pkill llama-server", timeout=15)
        assert "[PKILL_SELF_MATCH_GUARD]" not in r

    def test_exit_255_message_mentions_auto_clear(self, tools):
        r = tools.ssh_run("host.invalid", "echo hi", timeout=15)
        assert "[SSH FAILURE]" in r
        assert "mux already auto-cleared" in r

    def test_complexity_guard_still_first_class(self, tools):
        r = tools.ssh_run("host.invalid", "PID=$(pgrep x)")
        assert "[SSH_COMPLEXITY_GUARD]" in r


class TestRunTests:
    def test_unknown_scope_rejected(self, tools):
        r = tools.run_tests("everything")
        assert "unknown scope" in r

    def test_kb_scope_probes_live_indices(self, tools):
        r = tools.run_tests("kb")
        assert r.startswith("RUN-TESTS [")
        assert "lse-kb: EXISTS" in r
        assert "docs" in r

    def test_missing_assets_skip_not_error(self, tools, tmp_path):
        tools.valves.REPO_DIR = str(tmp_path)  # empty dir — no test assets
        r = tools.run_tests("retrieval")
        assert "retrieval=SKIP" in r
        assert "not present on this node" in r

    def test_retrieval_self_test_runs(self, tools):
        r = tools.run_tests("retrieval")
        assert "retrieval=" in r
        # self-test needs no ES/Ollama; PASS expected on a full repo checkout
        assert ("retrieval=PASS" in r) or ("retrieval=SKIP" in r)
