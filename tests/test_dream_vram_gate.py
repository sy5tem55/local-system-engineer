"""
Unit tests for the node3090 VRAM gate added in TRAUM Thread 4, Prompt 4.1
(TRAUM-AUTO) -- tools/dream_runner.py's `_node3090_free_vram_mb` and its use
inside `call_dream_llm`'s endpoint cascade.

Covers:
  - `_node3090_free_vram_mb` parses `nvidia-smi --query-gpu=memory.free`
    output correctly over a (mocked) SSH subprocess call, and fails CLOSED
    (returns 0, "treat as busy") on any subprocess error, timeout, or
    unparseable output -- never fails open toward "assume the GPU is free".
  - `call_dream_llm`'s cascade skips the llama-server leg and goes straight
    to Ollama when free VRAM is below `node3090_vram_gate_mb`, without ever
    probing or calling llama-server at all (Prompt 4.1: "fall back to the
    Ollama/CPU path rather than skipping" -- dreams are latency-insensitive,
    so this is a redirect, never a hard failure).
  - the llama-server leg still runs normally when free VRAM clears the gate
    and the health probe succeeds (the pre-4.1 cascade behavior, unchanged).
  - the DREAM_LLM_URL forced-endpoint leg (checked before node3090 at all)
    is untouched by the new gate -- it has its own health probe and never
    calls the VRAM check.

No live SSH, no live nvidia-smi, no live HTTP -- everything is driven
through monkeypatched module-level functions (`_node3090_free_vram_mb`,
`_health_probe`, `_post_chat_completion`), and `subprocess.run` is mocked
directly for the probe-parsing tests. Zero external dependencies.

    python3 -m pytest tests/test_dream_vram_gate.py -q
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import dream_runner as dr  # noqa: E402


def _cfg(**overrides):
    """Minimal DreamConfig for cascade tests -- only the fields
    call_dream_llm actually reads are meaningful; everything else is a
    throwaway placeholder (mirrors the fixture style in test_dream_engine.py
    / test_dream_insights.py)."""
    base = dict(
        episode_dir="/tmp/episodes",
        dream_dir="/tmp/dreams",
        manifest_db="/tmp/manifest.db",
        es_url="http://fake-es.invalid:9200",
        tasks_db="/tmp/tasks.db",
        agent_log="/tmp/agent_commands.log",
        dream_llm_url="",
        node3090_llm_url="http://node3090.home.arpa:8080",
        node3090_ollama_url="http://node3090.home.arpa:11434",
        node3090_fallback_model="qwen3:4b",
        ollama_url="http://127.0.0.1:11434",
        embed_model="nomic-embed-text",
        dedup_floor=0.75,
        dedup_threshold=0.92,
        error_cluster_threshold=0.80,
        runner_session_prefix="",
        sessions_limit=50,
        since=None,
        pass_name="dedup",
        dry_run=True,
        node3090_vram_gate_mb=2000,
    )
    base.update(overrides)
    return dr.DreamConfig(**base)


class TestNode3090FreeVramMb:
    def test_parses_single_gpu_output(self):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="18234\n", stderr="")
        with patch.object(subprocess, "run", return_value=fake) as m:
            free = dr._node3090_free_vram_mb("node3090.home.arpa", "lse-admin", 22)
        assert free == 18234
        # SSH must be BatchMode (no password-prompt hang) and hit the right host.
        args = m.call_args[0][0]
        assert "ssh" in args
        assert "lse-admin@node3090.home.arpa" in args
        assert "BatchMode=yes" in args

    def test_parses_multi_gpu_output_takes_max(self):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="512\n21000\n", stderr="")
        with patch.object(subprocess, "run", return_value=fake):
            free = dr._node3090_free_vram_mb("node3090.home.arpa", "lse-admin", 22)
        assert free == 21000

    def test_returns_zero_on_ssh_exception(self):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 8)):
            free = dr._node3090_free_vram_mb("node3090.home.arpa", "lse-admin", 22)
        assert free == 0

    def test_returns_zero_on_empty_output(self):
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="no route to host")
        with patch.object(subprocess, "run", return_value=fake):
            free = dr._node3090_free_vram_mb("node3090.home.arpa", "lse-admin", 22)
        assert free == 0

    def test_returns_zero_on_unparseable_output(self):
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="permission denied\n", stderr="")
        with patch.object(subprocess, "run", return_value=fake):
            free = dr._node3090_free_vram_mb("node3090.home.arpa", "lse-admin", 22)
        assert free == 0


class TestCallDreamLlmVramGate:
    def test_gpu_busy_skips_llama_server_falls_to_ollama(self, monkeypatch):
        """free_vram below the gate -> llama-server is never probed or
        called; Ollama is called directly (the 'fall back, don't skip'
        behavior Prompt 4.1 asks for)."""
        calls = {"health_probe": 0, "chat": []}

        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 500)  # under gate

        def fake_health_probe(url, timeout=3):
            calls["health_probe"] += 1
            return True  # even if it WOULD be reachable, gate must win

        def fake_post(base_url, payload, timeout):
            calls["chat"].append(base_url)
            return "ok-from-ollama"

        monkeypatch.setattr(dr, "_health_probe", fake_health_probe)
        monkeypatch.setattr(dr, "_post_chat_completion", fake_post)

        cfg = _cfg(node3090_vram_gate_mb=2000)
        result = dr.call_dream_llm("sys prompt", "user content", cfg)

        assert result == "ok-from-ollama"
        assert calls["health_probe"] == 0, "llama-server must not even be probed when GPU is busy"
        assert calls["chat"] == ["http://node3090.home.arpa:11434"]

    def test_gpu_free_uses_llama_server_as_before(self, monkeypatch):
        """free_vram at/above the gate + healthy probe -> llama-server leg
        runs exactly as it did before this gate existed."""
        calls = {"health_probe": [], "chat": []}

        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 21000)  # clears gate

        def fake_health_probe(url, timeout=3):
            calls["health_probe"].append(url)
            return True

        def fake_post(base_url, payload, timeout):
            calls["chat"].append(base_url)
            return "ok-from-llama-server"

        monkeypatch.setattr(dr, "_health_probe", fake_health_probe)
        monkeypatch.setattr(dr, "_post_chat_completion", fake_post)

        cfg = _cfg(node3090_vram_gate_mb=2000)
        result = dr.call_dream_llm("sys prompt", "user content", cfg)

        assert result == "ok-from-llama-server"
        assert calls["health_probe"] == ["http://node3090.home.arpa:8080"]
        assert calls["chat"] == ["http://node3090.home.arpa:8080"]

    def test_gpu_free_but_llama_server_call_fails_still_falls_to_ollama(self, monkeypatch):
        """Gate clears and probe succeeds, but the actual generate call
        errors -- pre-existing fallback-on-failure behavior must survive
        the gate being added in front of it."""
        monkeypatch.setattr(dr, "_node3090_free_vram_mb", lambda *a, **k: 21000)
        monkeypatch.setattr(dr, "_health_probe", lambda url, timeout=3: True)

        calls = []

        def fake_post(base_url, payload, timeout):
            calls.append(base_url)
            if base_url == "http://node3090.home.arpa:8080":
                return "ERROR: connection reset"
            return "ok-from-ollama"

        monkeypatch.setattr(dr, "_post_chat_completion", fake_post)

        cfg = _cfg(node3090_vram_gate_mb=2000)
        result = dr.call_dream_llm("sys prompt", "user content", cfg)

        assert result == "ok-from-ollama"
        assert calls == ["http://node3090.home.arpa:8080", "http://node3090.home.arpa:11434"]

    def test_forced_dream_llm_url_leg_never_touches_vram_gate(self, monkeypatch):
        """DREAM_LLM_URL, when healthy, short-circuits the whole cascade --
        the VRAM probe must never even be called."""
        probe_calls = {"vram": 0}

        def fail_if_called(*a, **k):
            probe_calls["vram"] += 1
            return 0

        monkeypatch.setattr(dr, "_node3090_free_vram_mb", fail_if_called)
        monkeypatch.setattr(dr, "_health_probe", lambda url, timeout=3: True)
        monkeypatch.setattr(dr, "_post_chat_completion", lambda base_url, payload, timeout: "ok-forced")

        cfg = _cfg(dream_llm_url="http://forced.invalid:9999", node3090_vram_gate_mb=2000)
        result = dr.call_dream_llm("sys prompt", "user content", cfg)

        assert result == "ok-forced"
        assert probe_calls["vram"] == 0, "forced-endpoint success must short-circuit before the VRAM gate"

    def test_default_vram_gate_is_2000_mb(self):
        assert dr._node3090_vram_gate_mb_default() == 2000
