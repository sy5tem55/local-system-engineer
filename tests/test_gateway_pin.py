# Gateway source-pin gate: pytest tests/test_gateway_pin.py -v
#
# Regression test for the 2026-08-08 incident.
#
# C:\Goethe3.0\...\Scripts\goethe_mcp.py is a "pinned, no-replace entrypoint":
# before executing tools/goethe_mcp.py it SHA-256s the file and refuses to
# launch on any drift. That is a deliberate supply-chain guard and it works.
#
# The problem is that the coupling is invisible from inside this repo. Commit
# 594ccc9 edited tools/goethe_mcp.py -- reviewed, tested, full suite green,
# gateway deliberately not restarted per the LIVE SERVICE RULE -- and the
# HTTP gateway then refused to start, surfacing as:
#
#     File "<string>", line 15, in <module>
#     ProcessLookupError: [Errno 3] No such process
#     [start-goethe-safe] ERROR: launch supervisor degraded before ownership
#                                publication
#     [EXIT] Goethe MCP exited with code 54.
#
# That traceback is os.pidfd_open() in inspect_launch_state_python failing on
# an already-dead supervisor. The refusal reason itself was discarded: the
# coproc in start-goethe-safe.sh ends `9<&- >/dev/null 2>&1`. So a precise
# "source hash mismatch" was reported as a corpse lookup, one layer too low.
#
# This gate makes the drift visible here, at test time, instead of at launch
# time on a different operating system.
#
# ANTI-RESPONSE (the intuitive wrong move): when the gateway will not start
# and the traceback points at the supervisor, do NOT debug the supervisor.
# Check this pin first.

import hashlib
import os
import pathlib
import re

import pytest

# The repo file that the Windows launcher pins.
UPSTREAM = pathlib.Path("tools/goethe_mcp.py")

# Where the shims live when this repo is checked out on the WSL side of the
# Goethe host. Absent on any other machine -> the whole module skips.
GOETHE_ROOT = pathlib.Path("/mnt/c/Goethe3.0")

# 2026-08-11: this used to be a BLOCKLIST of directory names, which meant
# every new deploy-staging dir, backup and build output was gated by default.
# The machine currently carries 15 shims; the GUI launches from exactly one.
# The test was therefore permanently red over 12 shims nobody will ever run,
# and a permanently red gate is one people learn to ignore -- the failure mode
# this file exists to prevent.
#
# Now an ALLOWLIST: the deploy directory the GUI actually launches from, plus
# the canonical project source that propagates into future builds. Same env
# var as scripts/pin-check.sh so the two cannot drift apart.
#
# The pins themselves belong to the operator (AGENTS.md sec2). This test
# reports drift; it never suggests editing a shim.
_DEPLOY_DIR = pathlib.Path(os.environ.get(
    "GOETHE_GUI_DEPLOY_DIR",
    "/mnt/c/Goethe3.0/.deploy-staging/Goethe.App-20260801-safe-03/win-x64",
))
_GATED_SHIMS = (
    _DEPLOY_DIR / "Scripts" / "goethe_mcp.py",
    GOETHE_ROOT / "Goethe.App" / "Scripts" / "goethe_mcp.py",
)

PIN_RE = re.compile(r"UPSTREAM_SHA256[^\"']*[\"']([0-9a-f]{64})[\"']", re.S)


def _live_shims():
    """The shims that can actually reach a launch. Nothing else."""
    return [p for p in _GATED_SHIMS if p.is_file()]


def _expected_sha():
    return hashlib.sha256(UPSTREAM.read_bytes()).hexdigest()


def test_gateway_shims_pin_the_current_source():
    """Every launchable shim must pin the current tools/goethe_mcp.py.

    If this fails after you edited tools/goethe_mcp.py, the edit is probably
    fine -- the pin just has to be re-reviewed and updated. Do that
    deliberately: the pin is a review checkpoint, so the person who reviews
    the diff should be the one who signs it.
    """
    shims = _live_shims()
    if not shims:
        pytest.skip(f"no Goethe launcher shims under {GOETHE_ROOT} on this host")

    expected = _expected_sha()
    stale = []
    for shim in shims:
        match = PIN_RE.search(shim.read_text(encoding="utf-8", errors="replace"))
        if not match:
            stale.append(f"{shim}: no UPSTREAM_SHA256 pin found")
        elif match.group(1) != expected:
            stale.append(f"{shim}\n      pinned {match.group(1)}\n      actual {expected}")

    assert not stale, (
        f"{len(stale)} launcher shim(s) pin a stale hash for {UPSTREAM}.\n"
        "The HTTP gateway will refuse to start with ProcessLookupError / exit 54.\n"
        "Re-pin after reviewing the diff:\n  "
        + "\n  ".join(stale)
    )


def test_pin_regex_matches_the_real_shim_format():
    """Guard the guard.

    A silently non-matching regex would make the gate above pass vacuously,
    which is precisely the failure mode of the docstring-truncation gate it
    is modelled on -- that one checked 36 of 48 tools and looked green.
    """
    shims = _live_shims()
    if not shims:
        pytest.skip(f"no Goethe launcher shims under {GOETHE_ROOT} on this host")

    for shim in shims:
        text = shim.read_text(encoding="utf-8", errors="replace")
        assert "UPSTREAM_SHA256" in text, f"{shim} is not a pinning shim"
        assert PIN_RE.search(text), (
            f"{shim} declares UPSTREAM_SHA256 but the gate's regex did not "
            "match it -- the pin format changed and this gate is now blind"
        )
