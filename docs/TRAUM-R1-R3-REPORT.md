# TRAUM R1–R3 — completion report

> 2026-08-01 · Implemented against `docs/TRAUM-R1-R3-PLAN.md`.
> Commits `1f74c02` (R1), `220dc11`+`02c4464` (R2), `24ce7c2` (systemd
> hand-off), `101880a` (R3), `cbfe735` (operator-initiated runs).
> All pushed to `codex/fix-sudo-grants-live`.

---

## The headline

**TRAUM produced its first non-legacy proposals on 2026-07-31.** Before
that date the loop had completed zero cycles and produced zero proposals
in production since go-live (`docs/TRAUM-ANALYSIS-2026-07-31.md`).

An operator-triggered GUI run (`run_2a314ec70b2d…`, 19:09→19:51) ended
DEGRADED but produced real output:

| Pass | Result | Note |
|---|---|---|
| `dedup` | BLOCKED | recent-session-activity — waited 22.5 min first |
| `stale-contradiction` | **SUCCEEDED** | first time ever · 1 proposal |
| `error-cluster` | **SUCCEEDED** | first time ever · 2 proposals |
| `patterns` | SUCCEEDED | mechanical pass, no LLM |
| `insights` | BLOCKED | `dream-llm` — llama-server slot busy with interactive work |
| `digest` | SUCCEEDED | operator digest refreshed |

Three of five passes succeeded; two of them had never succeeded once.

The run is still recorded DEGRADED, and the health verdict still reads
`critical` — correctly. "Produced useful output" and "completed a clean
cycle" are different claims, and the panel should not conflate them.

---

## What shipped

**R1 — a dreamer is available.** `tools/wake-node-for-dream.sh` wakes
node3090 via SSH-to-RUTX50 `etherwake` (canonical; no routing, broadcast
or pfSense dependency) and polls `/health`, never ping — boot is ~20s but
model load takes >2 min more. `run-dream-cycle.sh` runs it as a preflight
and, only if the node cannot be woken, exports `GOETHE_DREAM_LLM_URL` to
LUCIFER's local llama-server. Conditional by design: cascade leg 0 is
tried first and unconditionally when set, so exporting it always would
silently demote node3090's larger model every healthy night.

**R2 — the quiet-period guard no longer kills a run.** It now waits and
re-checks (default 3 retries, bounded by the pass's wall-clock budget)
instead of aborting on first sight of recent activity. It also excludes
the launching gateway's own fallback-shaped session id (`gw-<ppid>-*`).

**R3 — one health verdict.** `TraumController.status()` returns a
`health` block; the Console shows one line above the run table. Excludes
`source='legacy-import'` — all 9 legacy runs are SUCCEEDED and would
otherwise report the loop healthy forever.

**Operator-initiated runs.** `--skip-session-guard` waives *only* the
quiet-period wait, keeping the lockfile guard intact — deliberately
narrower than the pre-existing `--ignore-guards`, which also disables
the lockfile and would permit two concurrent runners over the same corpus.
Exposed as a default-off Console checkbox.

---

## Verified at runtime, not only by test

- **The 22.5-minute wait is real, and was measured unintentionally.** The
  19:09 GUI run's `dedup` pass ran 19:09:24 → 19:31:55 — 22.5 minutes of
  waiting, then BLOCKED anyway. That is exactly the predicted
  `3 × 450s` and exactly the failure mode `--skip-session-guard` exists
  to prevent. An unplanned live confirmation.
- Controlled repeat of the same scenario: a session ending 0 minutes ago
  made an unflagged run wait 595s and return BLOCKED; the identical run
  with `--skip-session-guard` started in 0.6s and completed.
- R2.2's exclusion: three sqlite fixtures — own-ppid session excluded, an
  unrelated real session still blocks, and with both present the
  exclusion falls through to the next-newest row rather than clearing.
- R3 against the **live production DB** before any test existed:
  `critical` / "never completed a real (non-legacy) cycle".
- The R3 legacy-exclusion guard was proven adversarially: the exclusion
  line was deleted, the suite re-run, and the verdict flipped
  `critical`→`ok` exactly as warned, then restored.

**Still unproven:** a full cycle through the systemd unit with R1–R3 all
engaged. The 19:09 run was GUI-triggered, and GUI runs call
`dream_runner.py` directly — they never touch `run-dream-cycle.sh`, so
**R1's wake preflight has still never executed in anger.** Only
`systemctl start goethe-dream.service` or the 03:30 timer exercises it.

---

## Operating model (changed 2026-08-01)

Primary is now **operator-initiated at end of session**: tick "I'm done
for the day", run a standard cycle, leave the machine. This dissolves
three root causes at once — no quiet-period collision, no catch-up firing
at the desk, and node3090 is already awake from the session just ended.

The 03:30 timer is kept as a backstop with `Persistent=false`, so a
missed night is skipped rather than fired at 09:45 while the operator is
working. It is also the only path that exercises R1.

Expected duration: **15–30 min**, hard-capped at 45. Based on thin data —
the only substantive observed pass is `insights` at ~3.4 min, and three
passes had never run at all until 2026-07-31.

---

## Corpus hygiene performed

`error-cluster`'s first-ever output included a false positive: a
"100% failure rate, broken tool" cluster for `method_raises` — which was
never a production tool. It is a test fixture whose test failed to
monkeypatch `GOETHE_EPISODE_DIR` and wrote synthetic failure episodes
into the live corpus. This exact false positive had already been
diagnosed and rejected on 2026-07-11
(`docs/dreaming/dream-run-2026-07-11.md`) — it recurred because the
residue was never purged.

Measured and cleaned: 67 contaminated files, every one a single-line
synthetic session named `gw-<pid>-<ts>`, spanning 2026-07-11 → 07-20
(the leak stopped when the offending test was removed). All 67 moved —
not deleted — to
`/opt/local-se/episodes-quarantine-method_raises-20260801/` with a
manifest. Corpus 581 → 514 files; `method_raises` occurrences 67 → 0.

**Latent bug found doing this:** `episode_index.build_manifest()` is
purely additive — it never prunes rows whose backing file has been
removed. After the purge it still reported 566 sessions with all 67 stale
rows intact. The orphans were deleted separately, each verified absent
from disk first (0 wrongly targeted). Any future corpus deletion must
prune the manifest explicitly or the analysis keeps seeing ghosts.

---

## First-run signal quality

| Proposal | Verdict |
|---|---|
| 2 × `reverify` (TTL exceeded) | Good — deterministic, no LLM, action is "go verify". **Approved.** |
| `skill-candidate` — method_raises | False positive from corpus contamination. **Reject.** |
| `skill-candidate` — MCP CancelledError | Real pattern, wrong remedy ("retry immediately" reproduces it). **Reject**; corrected version recorded via `skill_record` as `survive-mcp-cancellederror-on-long-running-execute-command-c`. |

Two good, one contamination artifact, one right-signal-wrong-fix. A
respectable first run, and both failures are informative rather than
random.

Note the Human Gate has **no edit action** — only Preview, Approve,
Defer, Reject. A proposal with a correct diagnosis but a poor procedure
cannot be amended; it must be rejected and rewritten out-of-band.
