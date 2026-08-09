"""Static deployment contracts for the manual TRAUM cycle.

2026-08-08: the timer was retired (SPEC-manual-dreaming-2026-08) and the
units removed from /etc. This file used to assert the repo-owned templates
at scripts/systemd/goethe-dream.{service,timer} were well-formed -- which
meant the suite went green *because* the templates still existed, quietly
enforcing the mechanism we had just deleted.

Worse, the template read `Persistent=true` while the unit actually installed
had `Persistent=false`. They had already drifted, and that drift is part of
why the nightly never fired. Any install step copying scripts/systemd/* would
therefore have reinstated the timer with catch-up runs enabled -- firing
harder than the one that was removed.

The templates are gone. These tests now assert they stay gone.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE = REPO_ROOT / "scripts" / "systemd" / "goethe-dream.service"
TIMER = REPO_ROOT / "scripts" / "systemd" / "goethe-dream.timer"
CYCLE = REPO_ROOT / "tools" / "run-dream-cycle.sh"


def test_timer_units_are_not_reintroduced():
    """Dreaming is manual. A unit template in the repo is a loaded gun."""
    assert not TIMER.exists(), (
        f"{TIMER} is back. Dreaming is manual since 2026-08-08; a systemd "
        "timer template in the repo can be installed by any deploy step and "
        "will resurrect the nightly schedule."
    )
    assert not SERVICE.exists(), f"{SERVICE} is back; see above."


def test_no_systemd_timer_wiring_survives_in_the_cycle_script():
    """run-dream-cycle.sh stays -- as the MANUAL entry point, not a unit."""
    assert CYCLE.exists(), "run-dream-cycle.sh is the manual entry point; do not delete it"
    text = CYCLE.read_text(encoding="utf-8")
    assert "OnCalendar" not in text
    assert "systemctl" not in text


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
    assert "set -uo pipefail" in text
    assert "finalize-cycle" in text
    assert "remaining_seconds" in text
