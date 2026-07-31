# TRAUM — operability analysis and refactoring plan

> 2026-07-31 · Evidence: `/opt/local-se/dreams/traum-state.db` (13 runs, 32
> attempts, 68 proposals, 163 events), `/opt/local-se/episodes/manifest.db`,
> systemd timer state, and the 12k lines of `traum_*.py` / `dream_*.py`.
> Every number below is measured, not estimated.

---

## 1. The finding that matters

**TRAUM has never completed a cycle in production. Not once.**

| Measure | Value |
|---|---|
| Scheduled runs since go-live (2026-07-28) | 4 |
| Scheduled runs reaching `SUCCEEDED` | **0** |
| Attempts blocked | **21 of 32 (66%)** |
| Passes that have *never* succeeded | **3 of 5** (`dedup`, `stale-contradiction`, `error-cluster`) |
| Proposals produced by scheduled runs | **0** |
| Proposals in the database | 68 — **all dated 2026-07-27, all from the legacy backfill import** |

Every one of the 21 blocks is `DependencyBlocked`. The system is not crashing
and not buggy in the ordinary sense. It is refusing to start, every night, for
reasons that are individually defensible and collectively fatal.

This is why it feels unintuitive to operate: **the failure is silent and looks
like health.** The Console shows "1 needs decision" (a proposal from 27 July),
runs show `DEGRADED`/`BLOCKED` rather than red, and nothing anywhere says *"the
learning loop has produced nothing for four days."*

---

## 2. Root causes, in order of impact

### 2.1 The nightly run depends on a machine that is asleep at night

`insights` blocks with:

```
dream-llm: … command-frequency: DREAMER UNAVAILABLE —
  (ERROR: <urlopen error [Errno 113] No route to host>)
```

The dreamer LLM is `node3090.home.arpa:8080`. node3090 is a wake-on-LAN node.
The timer fires at 03:30. **Nothing wakes node3090 first** — `dream_runner.py`
contains zero references to WoL or `wake_node`, and
`goethe-dream.service` declares only `After=network-online.target
docker.service ollama.service`.

So the nightly learning cycle is architecturally dependent on a host that is,
by design, powered down at the hour the cycle runs. `no route to host` is not
a transient network blip; it is the expected state at 03:30.

### 2.2 The quiet-period guard cannot be satisfied on a machine in use

`_recent_session_active()` (dream_runner.py:4011) blocks the run if the most
recent episode session ended less than `session_active_window_min` (default
**30**) minutes ago. Measured reality:

```
run fired          2026-07-31T03:39:51
last session ended 2026-07-31T03:39:49   ← 2 seconds earlier
```

That session (`sess-225720-…`) ran 03:19→04:20 with 151 tool calls —
`planner`, `run_tests`, `plan_step_done`. It was the agent doing D6 work. The
guard was *correct*; the assumption behind it was not. The premise is "at
03:30 nobody is working", and on this machine that premise is simply false.

### 2.3 `Persistent=true` aims the timer directly at the operator

`goethe-dream.timer` is `OnCalendar=*-*-* 03:30:00` with `Persistent=true`. If
the box is asleep at 03:30, systemd runs the job **at next wake** — which is
exactly when the operator sits down and starts a session. Observed fire times:
09:51, 09:41, 09:41, 03:39. Three of four were catch-up firings straight into
active use, guaranteeing the 2.2 block.

The two mechanisms compound: catch-up aims at the busiest moment; the guard
then refuses; nothing retries.

### 2.4 Blocked means stopped, permanently, until a human notices

Only 3 of 32 attempts are retries, and `Retry` is a manual Console button. A
`DependencyBlocked` run does not back off and try again in twenty minutes; it
sits `BLOCKED` until someone opens the GUI. For a dependency that is *known to
be transient* — a busy session, a sleeping node — this is the wrong response.

### 2.5 `NULL` and `BLOCKED` are conflated at the boundary

The manual is emphatic and correct that these must differ: *"'Nothing was
found' must never be used to conceal 'the corpus was not examined.'"* But the
`insights` failure text contains **both** in one attempt:

```
20 session summary(ies) considered across 4 domain(s);
0 insight(s) accepted total, 0 converted to a proposal
…
Null result (PH3-2): no domain produced an insight that cleared the bar
```

— that is a textbook `NULL` — while *also* reporting three sub-passes as
`DREAMER UNAVAILABLE`, which is a genuine block. One attempt, two truths, one
state field. The recorded state is `BLOCKED`, so the real finding (the corpus
*was* examined and yielded nothing) is discarded.

---

## 3. Why it is hard to operate

The documentation is not the problem. `docs/TRAUM-OPERATOR-MANUAL.md` is 455
lines, precise, and better than most commercial runbooks. The difficulty is
structural.

**The state space is large and the operator must hold all of it.** Three
independent state machines: 7 run states, 7 attempt states, **10 proposal
states**. Plus leases, deadlines, a recovery grace fence, ownership that is
deliberately *not* PID-based, and rules like "`STAGED`/`PENDING`/`DEFERRED`
from an expired parent become `SYSTEM_REJECTED`". Every rule is defensible.
Nobody can hold 24 states and a fencing protocol in their head at 9am.

**Nothing tells you the one thing you need to know.** There is no "healthy /
not healthy" verdict anywhere. To learn that the loop has been dead for four
days you must notice that four consecutive runs are `DEGRADED`/`BLOCKED`,
open each, read `error_type`, and know that `DependencyBlocked` on
`recent-session-activity` means "this will never self-resolve".

**The vocabulary is internal, not operational.** `DependencyBlocked`,
`ControllerLeaseExpired`, `SYSTEM_REJECTED`, `PH3-2` describe the
implementation. The operator's question is "did it learn anything last night,
and if not, what do I do?" No surface answers that.

**Recovery is expert-only by construction.** The manual's own section 12 is
titled *Expert recovery rules*, and legacy active state "requires expert
reconciliation". A nightly automation whose failure mode routinely requires
expert reconciliation will be abandoned.

---

## 4. What worked

Worth keeping and building on — this design got hard things right:

- **Evidence survives.** Every attempt, artifact, log path and state
  transition is retained; retries never overwrite the failed attempt. The
  entire post-mortem above was reconstructed from the canonical DB alone,
  days later, with no guesswork. That is rare and valuable.
- **Ownership is not PID-based.** Leases + deadlines + a recovery fence,
  explicitly refusing to kill a stored PID. This is the correct answer to a
  genuinely hard problem, and it survived a real gateway restart.
- **The `NULL` concept itself.** Distinguishing "looked, found nothing" from
  "did not look" is exactly right. The bug is that the boundary code does not
  honour its own distinction (2.5).
- **The control-plane separation.** TRAUM cannot touch Permissions or grants,
  and the GUI exposes no command box, PID field, or systemd mutation. The
  blast radius is small and legible.
- **Guards fail closed and say why.** `recent-session-activity: session 'X'
  was active 1.6 min ago (< 30min window)` names the session, the age and the
  threshold. The guard was wrong about the world, but it told the truth about
  itself.
- **The legacy backfill.** Importing 9 historical day-dirs into canonical
  state means the analysis above had a baseline to compare against.

## 5. What didn't

- Scheduling that assumes an idle machine, on a machine that is not idle.
- A hard dependency on a host nothing wakes.
- No backoff for dependencies that are transient by nature.
- State semantics that collapse two different truths into one field.
- No health verdict; failure is indistinguishable from quiet success at a glance.
- 12k lines across 7 modules for a loop that has produced zero proposals in
  production. `dream_runner.py` alone is 4,550 lines and mixes scheduling,
  guards, LLM calls, and five analysis passes.

---

## 6. Refactoring plan

Ordered by value per unit of risk. The first three are small and would have
prevented every observed failure.

### R1 — Wake the dreamer, or don't require it *(hours)*
Before the LLM legs run, either `wake_node("node3090")` and wait for the
health endpoint, or fall back to a local model, or record the pass as `NULL`
with reason "dreamer unavailable" instead of `BLOCKED`. Add
`Wants=`/`After=` or an `ExecStartPre=` wake step to `goethe-dream.service`.
**Fixes the single largest cause of the 21 blocks.**

### R2 — Make the quiet-period guard adaptive, and retry *(hours)*
The guard should defer, not abort: on `recent-session-activity`, schedule a
retry in `window_min` and try again, up to a bounded number of attempts within
the cycle budget. Also exclude the runner's own session from the activity
query — and reconsider `Persistent=true`, which aims catch-up runs straight at
the operator. A `RandomizedDelaySec` plus a wider acceptable window (e.g.
02:00–06:00, first quiet 30 minutes wins) fits actual usage far better than a
single instant.

### R3 — One health verdict, front and centre *(hours)*
A single line at the top of the TRAUM panel: **"Last successful cycle: never
(4 blocked runs since 28 Jul)"** in red, or **"Last successful cycle: 6h ago,
3 proposals awaiting decision"** in green. Derived from canonical state that
already exists. This alone converts a silent four-day outage into something
noticed the next morning.

### R4 — Honour the NULL/BLOCKED distinction at the boundary *(1 session)*
A pass that examined the corpus and found nothing is `NULL` even if an
optional sub-leg was unavailable; a pass that could not examine the corpus is
`BLOCKED`. Split the compound result: per-sub-pass states, with the attempt
state derived. Pin it with a test — the manual already specifies the
semantics, so this is making the code match its own documented contract.

### R5 — Collapse the proposal state machine *(1–2 sessions)*
Ten states, of which production has ever used four (`PENDING`, `APPLIED`,
`REJECTED`, `SYSTEM_REJECTED`). `STAGED`/`SUPERSEDED`/`EXPIRED`/`DEFERRED`/
`APPLYING`/`APPLY_FAILED` carry real edge-case meaning but cost every operator
and every reader permanently. Either fold them into a `state` + `sub_reason`
pair, or document a "you only ever see these four" front door and treat the
rest as internal. Do this **after** the loop actually runs — do not restructure
a state machine whose production behaviour you have never observed.

### R6 — Split `dream_runner.py` (4,550 lines) *(later)*
Same D7 method that took `goethe.py` from 6,565 to 2,109: call-graph closure,
one seam at a time, guard tests extended in the same commit. Natural seams:
scheduling/guards, the five analysis passes, LLM transport, artifact writing.
**Explicitly last.** R1–R4 are worth more, and D7's lesson applies — do not
restructure code whose runtime behaviour you cannot yet observe, and TRAUM has
produced no production runtime to observe.

---

## 7. Recommended immediate action

Do R1 + R2 + R3 together — perhaps a day's work — then let the loop run for a
week and re-read this table. Every conclusion in sections 4 and 5 is drawn
from a system that has never successfully completed a cycle; the most valuable
next artifact is the same analysis run against a TRAUM that actually works.

Then reassess R4–R6 with real data, rather than acting now on a design whose
production behaviour is still entirely unobserved.
