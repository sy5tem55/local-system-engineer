# TRAUM — THE DREAM CYCLE AND THE HUMAN GATE

JIT CONTEXT FILE — v0.7.0 (extracted verbatim from v0.6.3 canonical, 2026-09-19, task 1bfb3e45).
Not part of the always-on BASE prompt. Read this file first when: the user asks about the dream cycle, TRAUM, proposals, the Human Gate, or debrief state.

---

TRAUM — THE DREAM CYCLE AND THE HUMAN GATE
  TRAUM is this system's automated memory-consolidation loop: it mines episode
  logs overnight, extracts lessons, and proposes KB changes for human approval.
  It is the largest subsystem here and you will be asked about it.
    Runner:   tools/dream_runner.py   — six passes: dedup, stale-contradiction,
              error-cluster, patterns, insights, digest.
    Cycle:    tools/run-dream-cycle.sh (manual CLI) or the Console's Start
              button. There is NO timer -- goethe-dream.timer was retired
              2026-08-08 and the units are gone. Cycles are started by hand,
              deliberately. Do not offer to re-enable a schedule.
    State:    /opt/local-se/dreams/traum-state.db (runs / attempts / proposals).
    Console:  goethe_mcp serves it at /ui + /api/ui/* (gateway v1.12.0) —
              run table, health verdict, Human Gate, corpus hygiene.
    Manual:   docs/TRAUM-OPERATOR-MANUAL.md.
  Attempt states: QUEUED RUNNING SUCCEEDED NULL BLOCKED FAILED CANCELLED.
    NULL = looked and found nothing (a good outcome). BLOCKED = could not look.
    Never conflate them; a run of all-NULL passes is healthy.
  NEVER apply a proposal yourself. Proposals are adjudicated by the operator
  through the Human Gate. Writing a proposed change directly to the KB bypasses
  the gate and is a protocol violation.
  Read state with sqlite3 against traum-state.db; do not mutate it by hand.
