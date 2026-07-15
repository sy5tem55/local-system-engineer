"""Static deployment contracts for the repository-owned TRAUM timer."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE = REPO_ROOT / "scripts" / "systemd" / "goethe-dream.service"
TIMER = REPO_ROOT / "scripts" / "systemd" / "goethe-dream.timer"
CYCLE = REPO_ROOT / "tools" / "run-dream-cycle.sh"


def test_service_uses_authoritative_checkout_and_surfaces_failures():
    text = SERVICE.read_text(encoding="utf-8")
    assert "/home/sy5/projects/local-system-engineer/tools/run-dream-cycle.sh" in text
    assert "ConditionFileIsExecutable=" in text
    assert "ConditionPathIsExecutable=" not in text
    assert "ExecStart=-" not in text
    assert "ExecStart=/usr/bin/timeout --foreground 45m " in text
    assert "Restart=no" in text
    assert "GOETHE_EMBED_MODEL=qwen3-embedding:0.6b" in text


def test_service_sandbox_allows_only_required_state_writes():
    text = SERVICE.read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=read-only" in text
    assert "ReadWritePaths=/opt/local-se/dreams /opt/local-se/episodes /var/lib/lse-dream" in text
    assert "ReadOnlyPaths=/home/sy5/projects/local-system-engineer" in text


def test_cycle_runs_every_registered_production_pass_and_digest():
    text = CYCLE.read_text(encoding="utf-8")
    for pass_name in (
        "dedup",
        "stale-contradiction",
        "error-cluster",
        "patterns",
        "insights",
    ):
        assert pass_name in text
    assert "quarantine-delete-request" not in text
    assert "ledger-mining" not in text
    assert "dream_digest.py" in text
    assert "--no-dry-run" in text
    assert "set -euo pipefail" in text


def test_timer_is_persistent_and_jittered():
    text = TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 03:30:00" in text
    assert "RandomizedDelaySec=15m" in text
    assert "Persistent=true" in text
