# Handover report — node facts, model inventory, profile matcher

> Task: `docs/SPEC-node-facts-and-profile-matcher-2026-08.md` (Layer 0+1).
> Implementer: Sonnet 5 High. Reviewer: Opus 5 High (independent, V2).
> 2026-08-02.

## What shipped

`tools/node_facts.py` and `tests/test_node_facts.py` — hardware/model/profile
fact collection, a Hazard-A-aware three-class flag classifier, and a
Hazard-B-aware live-profile matcher. Read-only throughout; no changes to
`_NODE_REGISTRY` or `goethe_node.py`.

## Results

- Suite 728 → **743 passed**, zero regressions.
- ruff clean on both new files (229 pre-existing tree findings, none from this work).
- Load-bearing tests 2 and 6 each broken, confirmed red, restored to green.

## Real run against LUCIFER

- node4090 (local RTX 4090) and node3090 (SSH, awake this session) both resolved.
- node5090 correctly reported `reachable: false` with **null** hardware, not zeros.
- Live llama-server (pid 335865) matched **no** canonical profile: matcher
  returned `verdict: "closest"` rather than a false `exact`, with `--host`
  differences classified as deployment (never drift) across every ranked profile.

Verbatim JSON: `/tmp/node-facts-real-run.json`.

## Corrections to the spec's ground-truth table

1. **The n45 model share is `/opt/local-se/nas/Models`**, not
   `//n45.home.arpa/Models`. Reviewer confirmed: the path exists and holds 25
   GGUFs. This was a spec error.
2. node3090 was **awake** this session; the spec's table said asleep as of
   2026-07-29.
3. This WSL host's `nvidia-smi` reports `CUDA UMD Version` rather than the
   classic CUDA line.

## Independent verification (reviewer, V2)

Probe written **without reading `tests/test_node_facts.py`**, to avoid
inheriting its assumptions. All 16 real flags classified correctly across
identity / hardware-derived / deployment, and an unknown flag correctly
defaults to *identity* (fail loud rather than silently ignore a difference
that matters). `collect_hardware`, `collect_models`, `match_live` all present.
**Result: PASS, 0 failures.**

<!-- ACCEPTANCE
task: node-facts
commit: 24391cb
tests_before: 728
tests_after: 743
files_changed: tools/node_facts.py, tests/test_node_facts.py
ruff_clean: tools/node_facts.py, tests/test_node_facts.py
runtime_verified: true
-->
