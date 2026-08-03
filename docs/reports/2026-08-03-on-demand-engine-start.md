# On-demand engine start, per node per role — 2026-08-03

Implements `docs/SPEC-on-demand-engine-start-2026-08.md`. Commit `9242ae2`.

## 1. The bug, and what changed

`wake-node-for-dream.sh` used to poll `/health` after waking node3090 and
write its wake marker only once `/health` answered. Nothing has ever
started `llama-server` on boot, so that poll was always going to time out
on its own — measured live 2026-08-02: wake succeeded in 29s, the script
then polled a port nothing was going to open for 300s, logged the run as a
failure, and no marker meant `sleep-node-after-dream.sh` correctly refused
to power the node back down. Node3090 sat on and idle for hours.

Three files now do three separate jobs:

- `tools/start-engine-on-node.sh` (new) — starts (or confirms) one engine
  for one role on one node, idempotently.
- `tools/wake-node-for-dream.sh` (reworked) — three phases: wake (ICMP),
  start (delegates to the script above), verify (`/health`). **The wake
  marker is written at the end of phase 1**, the moment the node's power
  state is confirmed changed — not after phase 3. This is the fix.
- `tools/sleep-node-after-dream.sh` (extended) — stops an engine this
  cycle started (tracked by a **separate** marker from the wake marker)
  before its existing container-stop-and-shutdown sequence.

## 2. Ground truth that turned out wrong or incomplete

- **Suite baseline**: the spec's ground-truth table says 743 passed
  (2026-08-02). The task brief that opened this session said 748. Actual
  count at the start of this session was 748 — two commits landed between
  the spec being written and this work starting (`4968d31`, `8177714`)
  that added 5 tests. The spec's number was stale; 748 was current.
- **`node_facts.parse_profile()` cannot handle a documented profile file.**
  It read the whole file and shlex-split it as one continuous command,
  including any prose after the command block. The node3090 profile (as
  authored at `aad0dfe`) intentionally carries measurement rationale after
  a `---` separator. Before a fix, `match_live()` against this exact
  profile spuriously returned `verdict: "closest"` even when the live
  process was byte-for-byte running that profile, because markdown text
  like `` `--fit on` / `-fitt` `` and a stray `-la` from prose was
  shlex-split into garbage pseudo-flags. Fixed `parse_profile()` to stop
  at a line that is exactly `---`, matching the same convention my own
  `start-engine-on-node.sh` already used to extract the launch command.
  The four existing node4090 canonical files have no such line, so this
  is a no-op for them — confirmed by re-running `tests/test_node_facts.py`
  unchanged (15 passed, before and after).

## 3. Binary resolution (node3090, task-required)

The profile's first line was a placeholder — node3090 has two
`llama-server` copies. Resolved to **`/usr/local/bin/llama-server`**.

How confirmed, not guessed:
- `sha256sum` of both copies is identical (`ba785164...c643d72`), and both
  report the same `BuildID[sha1]=8f9ba242...301cb3` — they are the same
  binary today.
- **Kernel ground truth**: `readlink -f /proc/404963/exe` for node3090's
  actual running production `llama-server` process (serving Qwen3.6-35B at
  the time of the check) resolved to `/usr/local/bin/llama-server`, not
  the build tree. This is stronger evidence than `which`, which can lie
  relative to what a long-running process actually loaded (the exact
  failure mode the profile's own note warns about, citing the LUCIFER
  TRAUM-demote incident).
- `which llama-server` (PATH resolution) agrees.
- `start-goethe-node3090.sh`'s existing `NODE3090_PLANNER_LLAMA_BIN` pin
  already uses this same path (verified there 2026-07-01).

If the two copies ever diverge, `/usr/local/bin/llama-server` is the one
that reflects what the node's PATH and its own currently-running process
agree is current.

## 4. Tests

`tests/test_engine_start.py`, 8 tests per spec §6, all passing. No live
network — `ssh`/`curl`/`ping` are replaced by fake executables on `PATH`,
controlled per test via env vars. `node_facts.py`'s real matching logic
IS exercised (not mocked), since Hazard A/B correctness is the thing most
likely to be silently wrong.

**Tests 2 and 7 broken and confirmed red, then restored, as required:**

- **Test 2** (never resolves another node's profile): temporarily widened
  `start-engine-on-node.sh`'s profile glob from `profiles/${NODE}/` to
  `profiles/*/`. A decoy `profiles/node4090/TESTROLE-decoy.gguf.md` was
  then picked up for a `node3090` request that had no profile of its own.
  Result: `returncode 5` (attempted a launch against the decoy) instead of
  the required `2`. Confirmed red, reverted, file diffed identical to the
  backup, re-ran: 8/8 pass again.
- **Test 7** (marker written on wake, not on health): moved the wake-marker
  write out of phase 1 and into phase 3's `if health_ok` branch. Re-ran
  with a scenario where phase 1 succeeds but phase 2/3 fail (no profile
  for the requested test role, health never comes up) — this is a direct
  simulation of the 2026-08-02 production incident. Result: **the marker
  was never written at all**, reproducing the exact bug this spec exists
  to fix. Verbatim failure:

  ```
  AssertionError: wake marker missing -- log:
  ... phase 1 (wake): node3090 reachable after 0s -- awake (BROKEN-FOR-TEST...)
  ... phase 2 (start): RESULT=missing-profile
  ... phase 3 (verify): /health not answering ... -- node3090 is awake but not serving
  ```

  Confirmed red, reverted, file diffed identical to the backup, re-ran:
  8/8 pass again.

Invariants:

```
bash -n tools/start-engine-on-node.sh tools/wake-node-for-dream.sh tools/sleep-node-after-dream.sh   # OK
/home/sy5/miniforge3/bin/ruff check tests/test_engine_start.py    # All checks passed
/home/sy5/miniforge3/bin/ruff check tools/node_facts.py           # All checks passed
```

Full suite: **748 → 756 passed** (8 new, zero regressions), 78.99s.

## 5. V3 — runtime proof (not test-only)

node3090 was up at session start, serving a live Qwen3.6-35B engine on
:8080 (pid 404963) — unrelated to this task, plausibly the operator's own
session. `start-engine-on-node.sh` correctly identified this as a conflict
(Hazard B) and would have refused to touch it. **This was never killed by
any automated logic in this task.** The operator was asked, confirmed they
had already stopped containers, and explicitly authorized a full node
shutdown via `shutdown_node('node3090', confirmed=True)` (two-step
confirmation protocol, both steps run, operator said "yes"). This is a
deliberate human-authorized full power-down for the purpose of this test,
categorically different from the on-demand script silently killing a
conflicting engine.

Sequence, verbatim (UTC, from `/tmp/v3-wake.log`):

```
02:25:25Z phase 1 (wake): node3090 not reachable -- attempting wake
02:25:25Z phase 1 (wake): sending etherwake via RUTX50 (192.168.5.3)
02:25:25Z phase 1 (wake): etherwake command sent via RUTX50
02:25:32Z .. 02:26:14Z phase 1 (wake): waiting for ping ... 5s..35s/120s
02:26:14Z phase 1 (wake): node3090 reachable after 35s -- awake
02:26:14Z phase 1 (wake): wrote wake marker /var/lib/lse-dream/.woke-node3090
           -- this cycle owns the node's power state and may power it down
02:26:14Z phase 2 (start): invoking start-engine-on-node.sh --node node3090 --role dream --timeout-s 300
02:26:15Z [start-engine-on-node] resolved profile: profiles/node3090/DREAM-Gemma-4-31B-it-UD-Q4_K_XL.gguf.md
02:26:15Z [start-engine-on-node] nothing serving node3090:8080 -- proceeding to launch
02:26:15Z [start-engine-on-node] model file confirmed present on node3090
02:26:16Z [start-engine-on-node] launch dispatched on node3090 (role=dream); polling /health
02:26:21Z .. 02:26:31Z [start-engine-on-node] waiting for /health ... 5s..15s/300s
02:26:31Z [start-engine-on-node] RESULT=started
02:26:31Z phase 2 (start): wrote engine marker /var/lib/lse-dream/.engine-started-node3090
           -- this cycle owns the engine and may stop it
02:26:31Z phase 3 (verify): /health OK -- node3090 up and serving
```

Post-hoc confirmation the *right* profile was actually serving (not a
node4090 one, not a coincidental match):

```
$ pgrep -fa 'llama[-]server'   (on node3090)
5282 /usr/local/bin/llama-server -m /opt/models/unsloth/Gemma-4-31B-it-UD-Q4_K_XL.gguf
  --alias Gemma-4-31B-it-dream --ctx-size 32768 -ngl 99 --flash-attn on ... --host 0.0.0.0 --port 8080 ...
$ curl -sf http://localhost:8080/health
{"status":"ok"}
```

**Measured VRAM at ctx-size 32768** (the profile's own flagged
lowest-confidence guess — reported per the task's constraint not to tune
it): `20802 MiB used / 24576 MiB total / 3314 MiB free`. More headroom than
the profile's stated ~1–2 GiB target, meaning 32768 likely has room to grow
— left untouched, as instructed; this is a measurement for whoever tunes
the profile next, not a change made here.

Teardown, verbatim (`/tmp/v3-sleep.log`):

```
02:27:15Z this cycle started an engine on node3090 -- stopping it before power actions
02:27:15Z engine stop signal sent
02:27:15Z this cycle woke node3090 -- returning it to standby
02:27:15Z containers stopped gracefully
02:27:15Z shutdown accepted by node3090 (ssh rc=0)
```

Confirmed after teardown: both `/var/lib/lse-dream/.woke-node3090` and
`.engine-started-node3090` removed; node3090 unreachable by ping within one
3s-spaced check.

All four pieces of required evidence from spec §8 are runtime-proven, not
test-only:
- phase 1 succeeded and the marker was written at wake time — yes, shown above.
- phase 2 started an engine and `/health` answered — yes, `RESULT=started` after 15s.
- the node served the node3090 profile, not a node4090 one — yes, confirmed via live `pgrep`.
- teardown stopped what it started and powered the node down — yes, both markers cleared, node unreachable.

## 6. What remains test-only vs. runtime-proven

- **Runtime-proven**: the full happy path (wake → start → verify → stop →
  shutdown) on real node3090 hardware, end to end, this session.
- **Test-only** (fake ssh/curl/ping, never run live): missing-profile hard
  stop, cross-node profile isolation, conflict detection against a
  *different* running profile, missing-model-file detection,
  started-but-unhealthy handling with log tail. These are exercised by
  `tests/test_engine_start.py` and, for 2 and 7, break/red/restore-verified
  as load-bearing, but not observed against real hardware in a failure
  state this session (the one real conflict encountered — the live
  Qwen3.6-35B process — was correctly *avoided*, not deliberately
  triggered through the conflict path with a mismatched profile).

## 7. Anti-goals honored

- No profile parameter tuned (ctx-size 32768 left as-is; VRAM measurement
  reported above, not acted on).
- No engine killed to replace it (the live Qwen3.6-35B process was never
  touched by any script; the node3090 shutdown was a separate,
  operator-authorized action for this test, not automated conflict
  resolution).
- No fallback to another node's profile (test 2, load-bearing, verified red/green).
- No new secret literal (test 8; `start-engine-on-node.sh` reads no
  credential at all — SSH key-based auth only, same as the two scripts it
  extends).
- `start-goethe-node3090.sh` untouched.
- No node woken that was already awake (node3090 was down for this test;
  the "already reachable" branch is unit-tested but not re-exercised live
  this session since the node had to be down to prove phase 1 at all).

<!-- ACCEPTANCE
task: on-demand-engine-start
commit: 9242ae2
tests_before: 748
tests_after: 756
files_changed: profiles/node3090/DREAM-Gemma-4-31B-it-UD-Q4_K_XL.gguf.md, tests/test_engine_start.py, tools/node_facts.py, tools/sleep-node-after-dream.sh, tools/start-engine-on-node.sh, tools/wake-node-for-dream.sh
ruff_clean: tests/test_engine_start.py, tools/node_facts.py
runtime_verified: true
-->
