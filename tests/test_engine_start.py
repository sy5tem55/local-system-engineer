"""Contract tests for tools/start-engine-on-node.sh and the wake/sleep
marker split (spec §6: docs/SPEC-on-demand-engine-start-2026-08.md).

These are pure shell-script contract tests: no live SSH, no live network,
no live GPU. `ssh`, `curl`, and (for the marker test) `ping` are replaced by
fake executables placed first on PATH; the fakes are controlled entirely
through env vars set per test. The real profile-parsing/matching logic in
tools/node_facts.py IS exercised for real (it is imported by
start-engine-on-node.sh's embedded Python step), because faking that too
would stop testing the thing most likely to be wrong (Hazard A/B).

Numbered to match spec §6 exactly:
  1. Missing profile is a hard stop — exit 2, no SSH attempted.
  2. Never resolves another node's profile — a node4090 profile present and
     node3090 requested with none of its own still exits 2. Load-bearing.
  3. Already-running-and-matching exits 0 without launching.
  4. Different profile running exits 3 and launches nothing.
  5. Missing model file on the node exits 4 before any launch.
  6. Unhealthy after start exits 5 and includes log output.
  7. Marker is written on wake, not on health — simulate wake-then-
     engine-failure and assert the wake marker exists. Load-bearing (the
     2026-08-02 bug this whole spec exists to fix).
  8. No secret literal in any touched file.

Run: /home/sy5/owui/bin/python3 -m pytest tests/test_engine_start.py -q
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
START_ENGINE = REPO_ROOT / "tools" / "start-engine-on-node.sh"
WAKE_SCRIPT = REPO_ROOT / "tools" / "wake-node-for-dream.sh"
SLEEP_SCRIPT = REPO_ROOT / "tools" / "sleep-node-after-dream.sh"
NODE3090_PROFILE = REPO_ROOT / "profiles" / "node3090" / "DREAM-Gemma-4-31B-it-UD-Q4_K_XL.gguf.md"

TOUCHED_FILES = [START_ENGINE, WAKE_SCRIPT, SLEEP_SCRIPT, NODE3090_PROFILE]


# ── fake executables on PATH ─────────────────────────────────────────────

_FAKE_SSH = """#!/usr/bin/env bash
last="${@: -1}"
log="${FAKE_SSH_LOG:-}"
category="other"
case "$last" in
  *"pgrep -fa"*) category="pgrep" ;;
  *"test -f"*) category="test-f" ;;
  *"tail -n 40"*) category="tail" ;;
  *"cat > "*) category="cat-launcher" ;;
  *"nohup "*) category="nohup-launch" ;;
  *"etherwake"*) category="etherwake" ;;
esac
if [[ "$category" == "cat-launcher" ]]; then cat >/dev/null; fi
if [[ -n "$log" ]]; then echo "$category" >> "$log"; fi
case "$category" in
  pgrep)
    if [[ -n "${FAKE_LIVE_LINE:-}" ]]; then echo "$FAKE_LIVE_LINE"; fi
    exit 0 ;;
  test-f)
    if [[ "${FAKE_MODEL_EXISTS:-1}" == "1" ]]; then exit 0; else exit 1; fi ;;
  tail)
    echo "${FAKE_LOG_TAIL:-fake log tail line}"
    exit 0 ;;
  *)
    exit 0 ;;
esac
"""

_FAKE_CURL = """#!/usr/bin/env bash
url="${@: -1}"
if [[ -n "${FAKE_HEALTH_LOG:-}" ]]; then echo "curl $url" >> "$FAKE_HEALTH_LOG"; fi
if [[ "${FAKE_HEALTH_OK:-0}" == "1" ]]; then exit 0; else exit 1; fi
"""

_FAKE_PING = """#!/usr/bin/env bash
counter_file="${FAKE_PING_COUNTER_FILE:-/tmp/fake_ping_counter_default}"
n=0
[[ -f "$counter_file" ]] && n=$(cat "$counter_file")
n=$((n+1))
echo "$n" > "$counter_file"
threshold="${FAKE_PING_SUCCEED_AFTER:-1}"
if (( n >= threshold )); then exit 0; else exit 1; fi
"""


@pytest.fixture()
def fake_bin(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, content in (("ssh", _FAKE_SSH), ("curl", _FAKE_CURL), ("ping", _FAKE_PING)):
        path = bindir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return bindir


def _base_env(tmp_path, extra=None):
    env = dict(os.environ)
    env["GOETHE_START_ENGINE_POLL_INTERVAL_S"] = "1"
    env["FAKE_SSH_LOG"] = str(tmp_path / "ssh.log")
    if extra:
        env.update(extra)
    return env


def _run_start_engine(env, node="node3090", role="dream", timeout_s="3"):
    return subprocess.run(
        ["bash", str(START_ENGINE), "--node", node, "--role", role, "--timeout-s", timeout_s],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _ssh_categories(tmp_path):
    log = tmp_path / "ssh.log"
    if not log.exists():
        return []
    return [line.strip() for line in log.read_text().splitlines() if line.strip()]


# ── 1. Missing profile is a hard stop ────────────────────────────────────

def test_1_missing_profile_is_hard_stop_no_ssh(fake_bin, tmp_path):
    env = _base_env(tmp_path)
    result = _run_start_engine(env, node="node3090", role="no-such-role")
    assert result.returncode == 2
    assert "RESULT=missing-profile" in result.stdout
    assert "profiles/node3090/NO-SUCH-ROLE-*.gguf.md" in result.stdout
    assert _ssh_categories(tmp_path) == [], "no SSH call should be made before a profile is resolved"


# ── 2. Never resolves another node's profile ─────────────────────────────

def test_2_never_resolves_another_nodes_profile(fake_bin, tmp_path):
    other_dir = REPO_ROOT / "profiles" / "node4090"
    other_dir.mkdir(exist_ok=True)
    decoy = other_dir / "TESTROLE-decoy.gguf.md"
    decoy.write_text("/usr/local/bin/llama-server \\\n  -m /decoy.gguf\n", encoding="utf-8")
    try:
        env = _base_env(tmp_path)
        result = _run_start_engine(env, node="node3090", role="testrole")
        assert result.returncode == 2
        assert "RESULT=missing-profile" in result.stdout
        assert "profiles/node3090/TESTROLE-*.gguf.md" in result.stdout
        assert "node4090" not in result.stdout
        assert "decoy" not in result.stdout
    finally:
        decoy.unlink(missing_ok=True)
        try:
            other_dir.rmdir()
        except OSError:
            pass


# ── 3. Already-running-and-matching exits 0 without launching ───────────

def _profile_as_live_cmdline(profile_path: Path, pid: int = 404963) -> str:
    """Build a realistic 'ps -o pid,cmd' style line for a process that is
    literally running this profile's command verbatim -- i.e. what a real
    already-correct engine's pgrep output looks like. Using the real
    profile (rather than a hand-picked flag subset) is deliberate: classify_flag
    defaults unlisted flags to identity (node_facts.py's own documented
    fail-loud policy), so a partial live cmdline is NOT a faithful stand-in
    for "this profile is actually running" and under-tests the match.
    """
    lines = []
    for line in profile_path.read_text(encoding="utf-8").split("\n"):
        if line.strip() == "---":
            break
        lines.append(line)
    text = " ".join(lines)
    text = text.replace("\\", " ")
    text = " ".join(text.split())
    return f"{pid} {text}"


def test_3_already_running_matching_exits_0_no_launch(fake_bin, tmp_path):
    live = _profile_as_live_cmdline(NODE3090_PROFILE)
    env = _base_env(tmp_path, {"FAKE_LIVE_LINE": live})
    result = _run_start_engine(env)
    assert result.returncode == 0
    assert "RESULT=already-running" in result.stdout
    cats = _ssh_categories(tmp_path)
    assert "cat-launcher" not in cats
    assert "nohup-launch" not in cats


# ── 4. Different profile running exits 3, launches nothing ──────────────

def test_4_conflict_exits_3_no_launch(fake_bin, tmp_path):
    live = "12345 /usr/local/bin/llama-server -m /opt/models/some/other-model.gguf --alias other --ctx-size 4096"
    env = _base_env(tmp_path, {"FAKE_LIVE_LINE": live})
    result = _run_start_engine(env)
    assert result.returncode == 3
    assert "RESULT=conflict" in result.stdout
    assert "not killing it" in result.stdout
    cats = _ssh_categories(tmp_path)
    assert "cat-launcher" not in cats
    assert "nohup-launch" not in cats


# ── 5. Missing model file exits 4 before any launch ──────────────────────

def test_5_missing_model_exits_4_no_launch(fake_bin, tmp_path):
    env = _base_env(tmp_path, {"FAKE_MODEL_EXISTS": "0"})
    result = _run_start_engine(env)
    assert result.returncode == 4
    assert "RESULT=missing-model" in result.stdout
    cats = _ssh_categories(tmp_path)
    assert "cat-launcher" not in cats
    assert "nohup-launch" not in cats


# ── 6. Unhealthy after start exits 5, includes log output ───────────────

def test_6_unhealthy_after_start_exits_5_with_log(fake_bin, tmp_path):
    env = _base_env(
        tmp_path,
        {"FAKE_MODEL_EXISTS": "1", "FAKE_HEALTH_OK": "0", "FAKE_LOG_TAIL": "CUDA out of memory at load"},
    )
    result = _run_start_engine(env, timeout_s="2")
    assert result.returncode == 5
    assert "RESULT=started-but-unhealthy" in result.stdout
    assert "CUDA out of memory at load" in result.stdout
    cats = _ssh_categories(tmp_path)
    assert "cat-launcher" in cats
    assert "nohup-launch" in cats


# ── 7. Marker is written on wake, not on health ──────────────────────────

def test_7_marker_written_on_wake_not_on_health(fake_bin, tmp_path):
    woke_marker = tmp_path / "woke-node3090"
    engine_marker = tmp_path / "engine-started-node3090"
    ping_counter = tmp_path / "ping-counter"
    rutx50_key = tmp_path / "fake_rutx50_key"
    rutx50_key.write_text("fake", encoding="utf-8")

    env = _base_env(
        tmp_path,
        {
            "GOETHE_DREAM_WOKE_MARKER": str(woke_marker),
            "GOETHE_DREAM_ENGINE_MARKER": str(engine_marker),
            "GOETHE_RUTX50_KEY": str(rutx50_key),
            "FAKE_PING_COUNTER_FILE": str(ping_counter),
            "FAKE_PING_SUCCEED_AFTER": "2",
            # A role with no profile for node3090 -> phase 2 fails fast
            # (exit 2, missing-profile) so the engine never comes up.
            "GOETHE_DREAM_ROLE": "no-such-role-for-wake-test",
            "GOETHE_DREAM_WAKE_TIMEOUT_S": "10",
            "GOETHE_DREAM_START_TIMEOUT_S": "3",
            "FAKE_HEALTH_OK": "0",
        },
    )
    result = subprocess.run(
        ["bash", str(WAKE_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Phase 1 succeeded (marker must exist) even though phase 2/3 failed and
    # the script's own exit code is therefore non-zero. This is exactly the
    # 2026-08-02 bug: conflating "did we change power state" (yes) with "is
    # the service ready" (no) must NOT suppress the wake marker.
    assert woke_marker.exists(), f"wake marker missing -- log:\n{result.stdout}"
    assert not engine_marker.exists(), "no engine was started this cycle -- engine marker must not exist"
    assert result.returncode == 1  # phase 3 legitimately failed -- health never came up


# ── 8. No secret literal in any touched file ─────────────────────────────

_TOKEN_SHAPE = re.compile(r"\b[0-9a-fA-F]{32}\b")


def test_8_no_secret_literal_in_touched_files():
    offenders = {}
    for f in TOUCHED_FILES:
        text = f.read_text(encoding="utf-8")
        hits = _TOKEN_SHAPE.findall(text)
        if hits:
            offenders[str(f)] = hits
    assert not offenders, f"32-hex-char token-shaped literal(s) found: {offenders}"
