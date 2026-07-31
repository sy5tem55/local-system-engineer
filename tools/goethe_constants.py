#!/usr/bin/env python3
"""
goethe_constants.py — single source of truth for shared topology literals.
============================================================================
D7 Step 9 (2026-07-31): extracted from goethe.py, where these two constants
were defined at module scope by the D6 topology-literal sweep (2026-07-31,
docs/D6... / kb/STACK-MAP.md). D6's whole point was collapsing scattered
hardcoded "127.0.0.1" / "/opt/local-se" literals into one definition each.

That single definition became a problem the moment goethe.py's code started
splitting into mixins: PlannerMixin's moved methods reference these bare
names directly (not via self.), and a mixin must never import goethe.py
(docs/D7-MIXIN-EXTRACTION-PLAN.md hazard #2 — that would be a cycle). Leaving
the constants in goethe.py and importing them from a mixin would violate that
rule; duplicating the literal string in goethe_planner.py would silently
reintroduce the exact scattered-constant problem D6 fixed, one file later.

This module has ZERO dependencies (not even on goethe.py), so both goethe.py
and every mixin can import it without creating a cycle. It is the actual
single source of truth now; goethe.py imports these names rather than
defining them.

tests/test_topology_literals.py's ALLOWED_EXACT list already treats these two
literal strings as "the config home, working correctly" wherever they are
defined — that exemption now applies here instead of in goethe.py.
"""

_LSE_BASE_PATH = "/opt/local-se"
_LOOPBACK = "127.0.0.1"
