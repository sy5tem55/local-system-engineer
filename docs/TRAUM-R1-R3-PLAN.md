# TRAUM R1–R3 — implementation plan for Sonnet 5

Design: Opus 5, 2026-07-31. Grounded on a live scan of the running system,
not on the analysis document's summaries. Execute steps **in order**; each is
independently verifiable. Source of truth is the WSL tree at
`/home/sy5/projects/local-system-engineer`.

Goal: make the nightly learning loop actually run. Today it has completed
**zero** cycles and produced **zero** proposals (see
`docs/TRAUM-ANALYSIS-2026-07-31.md`).

---

## Ground truth established for this plan (verify, don't trust)

Measured live on 2026-07-31, ~17:00. Re-check anything you depend on.

| Fact | Value | How it was established |
|---|---|---|
| node3090 boot time | **2026-07-31 13:12:52** | `ssh … uptime -s` |
| The 03:39 blocked run | fired while node3090 was **powered down** | boot time is 9h later |
| Cascade leg 1 | `NODE3090_LLM_URL` → node3090:8080 | `call_dream_llm` docstring + code |
| Cascade leg 2 | `NODE3090_OLLAMA_URL` → node3090:11434 | same |
| **Both real legs are on node3090** | — | so a sleeping node has no fallback |
| Cascade leg 0 | `DREAM_LLM_URL`, health-probed, **silently skipped when down/unset** | `call_dream_llm`, first branch |
| LUCIFER subnet | `192.168.1.57/24` | `ip -4 addr` |
| node3090 address | `192.168.5.41` | `getent hosts` |
| Route to the 5.x segment | `192.168.5.41 via 192.168.1.50` (pfsense.home.arpa) | `ip route get` |
| **Bare `wakeonlan <mac>` from LUCIFER — DOES NOT WAKE** | measured 2026-07-31: no boot after 5 min | live test, node powered down |
| **`wakeonlan -i 192.168.5.255 <mac>` — WAKES** | measured: booted ~20s after packet | live test |
| `wake_node("node3090")` (pfSense POST, `interface: opt1`) | the operator's proven everyday path | LSE tool, used for weeks |
| boot → llama-server `/health`=200 | **>2 min** (model load); pingable much earlier | live test |
| Alternative wake path | pfSense `POST /api/v2/services/wake_on_lan/send`, interface `opt1` | `goethe_node.wake_node` |
| LUCIFER llama-server :8080 | healthy, Qwen3.6-27B, **manually started, no systemd unit** | `curl /health`, `systemctl is-enabled` → not-found |
| LUCIFER Ollama | systemd `enabled`+`active`, but only `llama3.2:3b` chat model | `systemctl`, `/api/tags` |
| Run-level backoff / auto-retry | **does not exist**; `defer_until` is proposals-only | grep over controller + runner |
| `TraumController.status()` | returns counts only — **no notion of "last successful cycle"** | read at line 242 |
| Timer | `OnCalendar=*-*-* 03:30:00`, `Persistent=true` | unit file |

### How the wake facts above were arrived at — read this before touching R1

This section was wrong twice before it was right. The sequence matters more
than the conclusion, because it is the reason the KB is now fixed.

1. **Draft 1** reasoned from `ip addr` that LUCIFER (192.168.1/24) and
   node3090 (192.168.5/24) are on different segments, concluded a local
   `wakeonlan` "cannot work", and named pfSense the only path. Correct
   mechanism, but it was an *inference presented as a measurement*, and it
   contradicted the KB without checking it.
2. **Draft 2**, after the operator pointed at `kb/network-topology.md` and
   weeks of successful wakes, deleted that warning and made bare `wakeonlan`
   the preferred method. Correct deference to ground truth — but the KB
   entry itself was wrong.
3. **Settled by measurement**, with node3090 powered down on purpose:
   bare `wakeonlan` did **not** wake it in 5+ minutes; `wakeonlan -i
   192.168.5.255` woke it in ~20s. The KB has been corrected accordingly.

Why both parties had good grounds: the operator's everyday "power up
node3090" runs the LSE's `wake_node()`, which POSTs to pfSense with
`interface: opt1` — pfSense emits the packet **on the 5.x segment directly**
and never touches the broken local-broadcast path. So the operator's method
always worked *and* the KB's documented command never did.

The trap to avoid: bare `wakeonlan` **fails silently** — it prints
"Sending magic packet" and exits 0 whether or not the packet can reach the
target. Any wake step you write must verify by polling `/health`, never by
trusting the wake command's exit code.

---

## Invariants after every step

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/dream_runner.py tools/traum_controller.py tools/goethe_ui.py
/home/sy5/miniforge3/bin/ruff check tools/dream_runner.py tools/traum_controller.py tools/goethe_ui.py
/home/sy5/owui/bin/python3 -m pytest tests/ -q     # currently 590 passed
```

`ruff` is at `/home/sy5/miniforge3/bin/ruff`. It is **not** in the owui venv —
`/home/sy5/owui/bin/python3 -m ruff` fails with "No module named ruff", so a
report claiming a clean run from that interpreter did not make one (D4).

---

# R1 — make a dreamer available at 03:30

**Do not** change the cascade in `call_dream_llm`. Its three legs, health
probes and fallbacks are correct. The bug is that nothing wakes the host both
real legs live on. Fix it *outside* the cascade.

### Step 1.1 — a standalone wake helper
Create `tools/wake-node-for-dream.sh` (executable). Contract:

- exit **0** if node3090 is reachable **and** its llama-server answers `/health`
- if unreachable, wake it. **Use the canonical path** — SSH to the RUTX50 and
  emit on node3090's own L2 segment (KB doc `842595879f70576d`, quality 1.0):

  ```bash
  ssh -i ~/.ssh/id_ed25519_rutx50 -o StrictHostKeyChecking=no root@192.168.5.3 \
      "etherwake -i eth0 0c:9d:92:84:6e:6a"
  ```

  It needs no routing, no broadcast forwarding and no pfSense state. Fall back
  to `wake_node("node3090")` (pfSense POST) if the RUTX50 is unreachable.
  **Do not** use bare `wakeonlan` — measured, it does not wake the node and
  exits 0 anyway. See `kb/network-topology.md` for all four methods.
- then poll **`/health`, not ping**, every 5s up to
  `GOETHE_DREAM_WAKE_TIMEOUT_S` (default **300**). Measured: boot ≈20s after
  the packet, but llama-server needs **>2 min more** to load the model. A
  ping-based or 180s timeout would report failure on a node that was waking
  correctly.
- exit **1** if it never comes up — never hang, never exit non-zero for a
  reason other than "node did not wake"
- log one line per state transition to stdout

`wakeonlan` needs no credentials, which is the main reason to prefer it. Only
if you implement the pfSense fallback: read the API key exactly as
`goethe_node.wake_node` does (`x-api-key` header, **not** Bearer — see
`kb/STACK-MAP.md`). Never invent a secret path or hardcode a key.

**Verify:** run it with node3090 up → exit 0 in under 2s. Then have the
operator power node3090 down and run it again → it either wakes the node and
exits 0, or exits 1 within the timeout. Record which happened.

### Step 1.2 — preflight in the cycle wrapper
In `tools/run-dream-cycle.sh`, before the `for pass_name` loop:

1. Run `wake-node-for-dream.sh`.
2. If it exits 0 → proceed unchanged.
3. If it exits 1 → probe `http://127.0.0.1:8080/health` (LUCIFER llama-server).
   If healthy, `export GOETHE_DREAM_LLM_URL=http://127.0.0.1:8080` so cascade
   **leg 0** picks it up. Log the substitution loudly.
4. If neither is available → proceed anyway and let the passes record their
   real state. A genuinely absent dreamer *is* a legitimate block.

Conditional export is deliberate: leg 0 is tried **first and unconditionally**
when set, so exporting it always would silently demote node3090's larger
model on every healthy night. Set it only when node3090 could not be woken.

**Verify:** with node3090 up, `GOETHE_DREAM_LLM_URL` must remain unset in the
child environment — assert this, do not eyeball it.

### Step 1.3 — declare the dependency in the unit
`/etc/systemd/system/goethe-dream.service` currently has only
`After=network-online.target docker.service ollama.service`. That is a
sudo-delegated edit — prepare the exact file content and hand it to the
operator; do not attempt to write it yourself.

**R1 done when:** a cycle started with node3090 powered down either wakes it
or runs against the local llama-server, and in neither case blocks on
`dream-llm`.

---

# R2 — stop aborting on a transient guard

Two independent defects. Keep them in separate commits.

### Step 2.1 — the guard should defer, not abort
`_recent_session_active()` (dream_runner.py:4011) returns a reason string;
line ~4330 turns that straight into `DependencyBlocked` and the run dies.

Change the **caller**, not the predicate: when the block reason is
`recent-session-activity`, sleep `min(window_remaining, cycle_budget_left)`
and re-check, up to `GOETHE_DREAM_SESSION_WAIT_RETRIES` (default **3**).
Only raise `DependencyBlocked` after the retries are exhausted, and include
how long it waited in the message.

Never let the wait exceed the shared cycle deadline that
`run-dream-cycle.sh` already computes — the whole cycle is bounded at 45
minutes by the systemd `timeout`, and R2 must not silently eat that budget.

### Step 2.2 — exclude the runner's own session
`_recent_session_active` takes the newest `end_ts` from `sessions` in
`manifest.db`. The gateway journals episodes continuously, so the runner can
observe activity generated by the very process tree that launched it.

Add an exclusion for the current session id / gateway pid if one is derivable.
**Honest scope note:** on the night measured, the blocking session was
`sess-225720-…` running 03:19→04:20 with `planner`/`run_tests` — that was the
agent doing real work, *not* self-blocking. So this step is hygiene; **2.1 is
the load-bearing fix.** Do not claim 2.2 fixes the observed failure.

### Step 2.3 — stop aiming catch-up runs at the operator
`Persistent=true` re-fires a missed 03:30 job at next wake — which is exactly
when the operator starts working, guaranteeing 2.1's block. 3 of 4 observed
runs fired at ~09:45 for this reason.

Recommend to the operator (sudo-delegated, prepare don't apply):
`RandomizedDelaySec=1800`, and either drop `Persistent=true` or accept that a
missed night is skipped rather than run at 09:45. State the trade-off; let
them choose.

**R2 done when:** a run started during active session use waits and retries
rather than dying, and the wait is provably bounded by the cycle deadline.

---

# R3 — one health verdict, front and centre

The operator currently cannot tell "quiet success" from "dead for four days".
`status()` returns counts, never a verdict.

### Step 3.1 — compute it in the controller
Add to `TraumController.status()` (traum_controller.py:242) a `health` block:

```
health: {
  last_success_at: ISO8601 | null,   # newest run with state SUCCEEDED,
                                     # source != 'legacy-import'
  hours_since_success: float | null,
  consecutive_unsuccessful_runs: int,
  verdict: "ok" | "warn" | "critical",
  reason: str                        # one operator-readable sentence
}
```

Rules: `critical` if there has never been a non-legacy success, or none in
>48h, or ≥3 consecutive unsuccessful runs. `warn` if none in >24h. Else `ok`.

**Exclude `source='legacy-import'`.** All 9 legacy runs are `SUCCEEDED` and
would otherwise report the loop healthy forever — this is the single most
important detail in R3 and the easiest to get wrong.

Read-only, derived from `runs` alone. No schema change.

### Step 3.2 — one line at the top of the panel
In `tools/goethe_dashboard.html`, above the TRAUM run table:

- `critical` → red: *"Learning loop: NEVER completed a cycle — 4 runs blocked since 28 Jul"*
- `ok` → green: *"Learning loop: last success 6h ago · 3 proposals awaiting decision"*

Reuse the existing `.chip`/`.dot ok|bad` classes.

### Step 3.3 — tests
Extend `tests/test_traum_controller.py` with a fixture DB covering: only
legacy successes → `critical`; a recent real success → `ok`; 3 consecutive
blocked runs → `critical`.

**Prove the guard fails before trusting it to pass** — assert the
legacy-exclusion case explicitly, because if that regresses the verdict is
permanently green and the panel becomes worse than no panel at all.

**R3 done when:** with today's data the panel reads `critical`, naming the
real reason.

---

## Step 4 — verify against reality, then report

1. Full invariants green.
2. Trigger one cycle manually: `systemctl start goethe-dream.service`
   (sudo-delegated — hand the command over).
3. Re-run the analysis queries from `docs/TRAUM-ANALYSIS-2026-07-31.md` §1 and
   report the same table: runs, attempts by state, passes that succeeded,
   proposals produced by non-legacy runs.
4. Write `/tmp/traum_r1r3_report.md` stating plainly what changed, what was
   verified **at runtime** versus by test only, and — if the loop still does
   not complete — what the *next* blocker is. A cycle that gets further and
   fails somewhere new is a successful outcome for this work; say so.

---

## Anti-goals

- Do **not** touch the `call_dream_llm` cascade, the lease/fence protocol, or
  proposal state transitions. R1–R3 are about *availability and visibility*.
- Do **not** start R4 (NULL/BLOCKED conflation) or R6 (splitting
  `dream_runner.py`). R6 in particular stays last: D7's lesson is not to
  restructure code whose runtime behaviour you cannot observe, and TRAUM has
  produced none yet. R1–R3 exist to *create* that runtime.
- Do **not** widen `session_active_window_min` to zero to force a pass. The
  guard protects against analysing a corpus that is actively being written.
- Do **not** edit files under `/etc` yourself. Prepare exact content and hand
  it to the operator.
- Do **not** report a step complete on a green test alone where the claim is
  about live behaviour — R1 in particular is only proven with node3090 down.
