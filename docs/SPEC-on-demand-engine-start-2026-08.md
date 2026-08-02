# SPEC — start an inference engine on demand, per node, per role

> Design: Opus 5, 2026-08-02. Implementation: Sonnet 5 High. Verification: V3.
> Source of truth is the WSL tree at `/home/sy5/projects/local-system-engineer`.
> Roadmap `docs/ROADMAP-2026-08.md` §1b. Builds on `tools/node_facts.py`
> (`24391cb`), which is what makes this tractable.

---

## 1. The bug this fixes

`tools/wake-node-for-dream.sh` wakes a node and then polls
`http://<node>:8080/health` until it answers or 300s elapse.

**Nothing starts llama-server on boot.** That is deliberate — every node in
this fleet shares one versatile architecture and the LSE starts what a task
needs. Confirmed 2026-08-02: `systemctl is-enabled llama-server` →
`not-found`, `pgrep llama-server` → 0.

Measured consequence, from the live 03:32 run on 2026-08-02:

```
03:32:07  etherwake sent via RUTX50      ← worked
03:32:36  node3090 booted (29s later)    ← worked
03:32→03:37  polled :8080/health, 300s   ← nothing was ever going to answer
03:37:11  "node3090 did not become healthy"   ← FALSE NEGATIVE
```

The wake succeeded and was reported as a failure. The node then sat powered
on and idle for hours, because the false failure meant no wake-marker was
written and `sleep-node-after-dream.sh` correctly declined to power down a
node it did not believe it had woken.

The health probe was the right choice (a node that pings is not a node that
can serve a model). The missing step is between the two.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Wake script | `tools/wake-node-for-dream.sh` — etherwake via RUTX50, polls `/health` |
| Teardown | `tools/sleep-node-after-dream.sh` — acts only if the wake marker exists |
| Marker | `/var/lib/lse-dream/.woke-node3090` |
| **`start-goethe-node3090.sh` starts the AGENT, not an engine** | Goethe MCP on `:9700` |
| Engine port | `:8080` (llama-server) — started manually/by the LSE today |
| Facts/matcher API | `node_facts.py`: `collect_hardware`, `collect_models`, `parse_profile`, `match_live` |
| Canonical profile format | a literal runnable `llama-server` invocation; `<ROLE>-<model>.gguf.md` |
| Existing profiles | 4, under `/mnt/c/Goethe3.0/` — **all authored for node4090/LUCIFER** |
| node4090 | IS LUCIFER, 192.168.1.57, RTX 4090 24 GB, i9-14900KF, 47 GB RAM |
| node3090 | remote, RTX 3090 — **different VRAM and CPU; node4090 profiles do not transfer** |
| Suite baseline | 743 passed (2026-08-02) |

---

## 3. Hazards

### Hazard A — a node4090 profile must never be started on node3090

Every existing profile encodes node4090's hardware: `--threads 14/15` (i9,
20 threads), `-ngl 99`, `--ctx-size 150000` with `q4_0` KV against 24 GB of
4090 VRAM. Applying one to a 3090 is at best wrong and at worst an OOM at
load.

**Profiles must be resolved per node.** Introduce
`profiles/<node>/<ROLE>-<model>.gguf.md`. If no profile exists for the
requested `(node, role)`, that is a **hard stop with a clear message** — never
a fallback to another node's file, and never a synthesised one. Generating or
tuning profiles is Layer 3 and explicitly out of scope here.

### Hazard B — starting must be idempotent

If an engine is already serving `:8080`, do not start a second one. Use
`node_facts.match_live` to identify what is running:

- `verdict: "exact"` against the requested profile → **already correct, do nothing, succeed.**
- an engine running but a *different* profile → **do not kill it.** Report the
  conflict and stop. Something else — plausibly the operator — owns that
  process. Killing an operator's session to run a dream is the wrong trade.
- nothing on `:8080` → start.

### Hazard C — do not repeat the credential mistake

`start-goethe-node3090.sh` carries a hardcoded `NODE3090_TOKEN` literal
(roadmap §1). Do not follow that pattern. Anything secret is read from the
environment or Vaultwarden at call time, exactly as
`tools/pfsense-gateway-tools.sh` documents for `PFSENSE_API_KEY`. **No new
secret literal may appear in any file this task touches.**

### Hazard D — partial start is not success

Node awake + SSH reachable + engine failed to load is a *distinct* outcome
from both success and "did not wake". It must be reported as its own state,
with the remote log tail included. Do not retry blindly — a model that OOMs
will OOM again, and a 300s poll against a dead process is the failure this
whole spec exists to remove.

### Hazard E — teardown must stay symmetric

The marker currently means "this cycle woke the node, so it may power it
down". Once this task also *starts* services, that contract widens: the cycle
now owns processes as well as power state. `sleep-node-after-dream.sh`
already stops containers gracefully before shutdown; extend the same
courtesy to a llama-server this cycle started — and **only** to one it
started.

---

## 4. What to implement

### 4.1 `tools/start-engine-on-node.sh`

```
start-engine-on-node.sh --node <name> --role <role> [--timeout-s N]
```

1. Resolve `profiles/<node>/<ROLE>-*.gguf.md`. None → exit 2, name the path
   searched.
2. Probe `:8080`. Already-correct → exit 0 (`already-running`). Different
   profile → exit 3 (`conflict`), print both.
3. Verify the model file named in the profile exists **on that node**.
   Missing → exit 4 rather than a confusing llama-server failure.
4. Launch detached (`nohup … & disown`), log to a known remote path.
5. Poll `/health` up to `--timeout-s` (default 300 — model load is >2 min).
6. Exit 0 on healthy; exit 5 on `started-but-unhealthy`, printing the last
   40 log lines from the node.

Exit codes are the interface. Callers must be able to distinguish these
without parsing prose.

### 4.2 Rework `wake-node-for-dream.sh`

Replace the single `/health` poll with three phases, each with its own
timeout and its own log line:

| Phase | Wait for | Default |
|---|---|---|
| 1 · wake | ICMP or SSH answering | 120s |
| 2 · start | `start-engine-on-node.sh --role dream` | 300s |
| 3 · verify | `/health` = 200 | (covered by phase 2) |

Write the wake marker when phase 1 succeeds — **not** phase 3. The marker
means "this cycle changed the node's power state", which is true the moment
it boots. Conflating it with service readiness is precisely what left the
node idling for hours on 2026-08-02.

Record separately in the marker whether phase 2 started an engine, so
teardown knows what it owns.

### 4.3 Extend `sleep-node-after-dream.sh`

If the marker records that this cycle started an engine, stop it gracefully
before the existing container-stop and shutdown sequence. If the marker says
it did not, leave every process alone.

---

## 5. Anti-goals

- Do **not** generate, tune, or infer profile parameters. Layer 3.
- Do **not** kill a running engine to replace it. Report and stop.
- Do **not** fall back to another node's profile, ever.
- Do **not** introduce a secret literal into any file.
- Do **not** change `start-goethe-node3090.sh`'s agent-start behaviour. The
  agent (`:9700`) and the engine (`:8080`) are separate concerns and this task
  owns only the engine.
- Do **not** wake a node that is already awake.

---

## 6. Tests — `tests/test_engine_start.py`

1. **Missing profile is a hard stop** — exit 2, no SSH attempted. Load-bearing (Hazard A).
2. **Never resolves another node's profile** — a `node4090` profile present and `node3090` requested with none of its own still exits 2. Load-bearing (Hazard A).
3. **Already-running-and-matching exits 0 without launching.**
4. **Different profile running exits 3 and launches nothing** (Hazard B).
5. **Missing model file on the node exits 4** before any launch.
6. **Unhealthy after start exits 5** and includes log output (Hazard D).
7. **Marker is written on wake, not on health** — simulate wake-then-engine-failure and assert the marker exists (Hazard E / the 2026-08-02 bug).
8. **No secret literal** — grep the touched files for anything matching a 32-hex token shape; fail if found (Hazard C).

**Break tests 2 and 7, confirm red, restore.** Report what you saw.

---

## 7. Invariants

```bash
cd ~/projects/local-system-engineer
bash -n tools/start-engine-on-node.sh tools/wake-node-for-dream.sh tools/sleep-node-after-dream.sh
/home/sy5/miniforge3/bin/ruff check tests/test_engine_start.py
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **743 passed**.

---

## 8. V3 — runtime proof is mandatory

This spec exists because something passed every test and was still wrong in
production. Tests alone do not close it.

Ask the operator to power node3090 down, then run the wake path by hand and
report the **verbatim** log. Required evidence:

- phase 1 succeeded and the marker was written at wake time;
- phase 2 started an engine and `/health` answered;
- the node is serving the **node3090** profile, not a node4090 one;
- teardown stopped what it started and powered the node down.

If node3090 cannot be taken down, say so and mark this **outstanding** — do
not substitute a test for it.

---

## 9. Report

`docs/reports/YYYY-MM-DD-on-demand-engine-start.md` (committed, not `/tmp`),
ending with an ACCEPTANCE block per `WORKFLOW-thread-handover.md` §1b.
Verify with `python3 scripts/verify-handover.py <report>`.

State plainly which claims are runtime-proven and which are test-only.

---

## 10. Context

- Why it matters: node3090 is intended to dream as a **peer** with its own KB
  and neural search, not merely be a remote GPU. On-demand engine start is
  the prerequisite.
- The facts API: `docs/SPEC-node-facts-and-profile-matcher-2026-08.md`.
- Conventions: `docs/WORKFLOW-thread-handover.md`,
  `docs/WORKFLOW-roadmap-execution.md`.
