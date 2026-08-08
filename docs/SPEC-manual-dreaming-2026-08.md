# SPEC — dreaming is manual; retire the timer

> Design: Opus 5, 2026-08-08. Implementation: Sonnet 5 High. Verification: V2.
> Operator decision, 2026-08-08: *"make the dreaming starting process fully
> manual and completely scrap the timer."*
>
> This supersedes every earlier proposal to fix the schedule. Do not repair
> `goethe-dream.timer`. Remove it.

---

## 1. Why this is the right call, and what it deletes for free

The timer has fired on 2 of the last 6 nights (`Persistent=false`, and LUCIFER
is a WSL instance that is usually shut down at 03:30). Both times it fired it
produced a failed run. Meanwhile every cycle that has ever completed was
started by hand from the Console.

The important consequence is second-order. **The recent-session-activity
quiet-period guard exists only because runs were unattended.** Its whole job
is to infer "the operator is not working right now". If the operator starts
the run by clicking a button, that inference is redundant — the click *is* the
signal. Retiring the timer therefore also retires:

- the 30-minute quiet window,
- the `n/(n+1)` retry arithmetic that made the guard unsatisfiable (max wait
  `1350s` against an `1800s` window — it could never clear a window that was
  fresh at run start), and
- the pitfall the operator hit on 2026-08-08: `skip_session_guard` is read
  once at run creation and baked into `config_json`, so a run already in
  flight cannot be waived.

That is a large simplification arriving as a deletion, which is the best kind.

---

## 2. Ground truth (verify, don't trust)

| Fact | Value |
|---|---|
| Timer unit | `goethe-dream.timer` — **enabled**, `OnCalendar=*-*-* 03:30:00`, `RandomizedDelaySec=15m`, `Persistent=false` |
| Service unit | `goethe-dream.service` — `static` |
| Timer's entry point | `tools/run-dream-cycle.sh`, `--run-source scheduled` |
| Console's entry point | `tools/traum_controller.py` invokes `dream_runner.py` **directly, per pass**, `--run-source gui` (`traum_controller.py:919`). It does **not** call `run-dream-cycle.sh`. |
| Guard waiver | `traum_controller.py:922` appends `--skip-session-guard` when `config.skip_session_guard` |
| Guard implementation | `dream_runner.py:4655-4700`; retry count `_session_wait_retries()` at `:338` |
| Source enum, validated | `traum_state.py:491` and `:542` — `source in {"gui", "scheduled"}` |
| Historical rows | 7 runs already stored with `source='scheduled'` in `/opt/local-se/dreams/traum-state.db` |
| Suite baseline | **830 passed, 0 skipped** |

Re-probe before implementing. `systemctl is-enabled goethe-dream.timer` and
`sqlite3 <db> "select source, count(*) from runs group by 1"` are the two that
matter most.

---

## 3. Hazards

### Hazard A — `run-dream-cycle.sh` must survive
It is the only place the per-pass wall-clock allocation from `5612f59` lives.
That work is three commits old and was the fix for a real starvation bug.
**Keep the script** as the manual CLI entry point. Retire the *timer*, not the
runner.

### Hazard B — never remove `"scheduled"` from the read path
Seven historical runs carry `source='scheduled'`. Dropping the value from
`traum_state.py`'s validation set would make those rows unreadable and break
the Console's run table retroactively. New runs may stop *producing* the
value; nothing may stop *accepting* it. If you add a `"manual"` source, widen
the set — never narrow it.

### Hazard C — /etc is not yours to write
Removing or masking a systemd unit is a privileged operation. Emit a
`sudo_delegation_block` with the exact commands and stop. Do not attempt
`systemctl` yourself, and do not write to `/etc/systemd/system/`. This is
precisely the case roadmap §2's `propose_file_change` exists for; until that
lands, delegation is the only route.

### Hazard D — do not rip the guard out of `dream_runner.py`
Retiring the timer removes the guard's *justification*, not necessarily its
code. A manual `run-dream-cycle.sh` invocation from a terminal is still
semi-unattended. Change the **default** (see §4.3); leave the mechanism intact
and reachable by flag. Deleting `_recent_session_active` is out of scope.

### Hazard E — one behaviour change at a time
Three of the last four TRAUM sessions produced a wrong diagnosis because two
changes landed together. Timer removal, source rename and guard default are
separable; commit them separately so a bisect means something.

---

## 4. What to implement

### 4.1 Retire the timer (delegated)
Emit a `sudo_delegation_block` containing exactly:

```
sudo systemctl disable --now goethe-dream.timer
sudo systemctl mask goethe-dream.timer
sudo rm /etc/systemd/system/goethe-dream.timer /etc/systemd/system/goethe-dream.service
sudo systemctl daemon-reload
```

with `verify_command`:

```
systemctl list-unit-files | grep -i goethe-dream || echo "no goethe-dream units remain"
```

Mask first, then remove, so a stray `daemon-reload` cannot resurrect it.

### 4.2 Make the manual entry point say so
`run-dream-cycle.sh` currently passes `--run-source scheduled`. Introduce
`"manual"` and pass it. Widen `traum_state.py`'s validation set at `:491` and
`:542` to `{"gui", "scheduled", "manual"}` — **widen, never replace**
(Hazard B). Check whether the Console's run-table filter or health verdict
special-cases `scheduled`; if so, teach it `manual` too.

### 4.3 Flip the guard default for operator-initiated runs
An operator-initiated run should waive the quiet period by default. In the
Console this means `skip_session_guard` defaults to checked; in
`run-dream-cycle.sh` it means passing `--skip-session-guard` unless an
explicit opt-out is given. The flag and the underlying check stay (Hazard D).

### 4.4 Remove the scheduling machinery that now has no caller
Once 4.1 lands, `run-dream-cycle.sh`'s `--run-source scheduled` branch and any
timer-specific preamble are dead. Delete what is genuinely unreachable; leave
anything the manual path still uses. If you are unsure whether something is
reachable, leave it and say so in the report.

### 4.5 Documentation
Update `docs/TRAUM-OPERATOR-MANUAL.md` and `docs/ROADMAP-2026-08.md` §0 to
state that cycles are started by hand. §0's "run a standard cycle at the end
of each session" becomes the actual, supported workflow rather than a wish.

---

## 5. Anti-goals

- Do **not** repair, reschedule or re-enable `goethe-dream.timer`.
- Do **not** delete `run-dream-cycle.sh`.
- Do **not** remove `"scheduled"` from any validation or read path.
- Do **not** delete `_recent_session_active` or the retry loop.
- Do **not** touch `_raise_if_dependency_blocked`, the sub-pass work
  (`ccbe879`), or the per-pass budget (`5612f59`).
- Do **not** run `systemctl` or write under `/etc/` directly.

---

## 6. Tests

1. `traum_state.py` accepts `source="manual"`. **Load-bearing.**
2. `traum_state.py` still accepts `source="scheduled"`, and a pre-existing
   `scheduled` row still reads back through the run-table path.
   **Load-bearing — Hazard B.**
3. `run-dream-cycle.sh` passes `--run-source manual` (assert on the argv it
   builds, not on a live run).
4. `run-dream-cycle.sh` passes `--skip-session-guard` by default, and omits it
   when the opt-out is given.
5. Per-pass wall-clock allocation from `5612f59` is unchanged — its existing
   tests still pass. **Load-bearing — Hazard A.**
6. No test, fixture or doc references `goethe-dream.timer` as a live
   mechanism.

**Break tests 2 and 5, confirm red, restore.** Report the exact failure text
and diff against the pre-break state.

---

## 7. Invariants

```bash
/home/sy5/owui/bin/python3 -m py_compile tools/traum_state.py tools/traum_controller.py
bash -n tools/run-dream-cycle.sh
/home/sy5/miniforge3/bin/ruff check tools/traum_state.py tools/traum_controller.py
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **830 passed, 0 skipped**. Pre-existing ruff counts must not increase.

---

## 8. Verification — V2

Code changes are V2. The delegated `/etc` step is **not yours to verify**:
emit the block, and record in the report that it is pending operator action.
Do not claim the timer is gone until `systemctl list-unit-files` says so.

After the operator runs the block, one manual cycle from the Console should
complete with `source='manual'` (or `'gui'` from the Console path) and no
`recent-session-activity` block in any attempt.

---

## 9. Report

`docs/reports/2026-08-DD-manual-dreaming.md`, committed, with an ACCEPTANCE
block, then `scripts/verify-handover.py --run-tests`. State plainly which
steps are runtime-proven and which await the delegated privileged step.

---

## 10. Context

- Operator decision, 2026-08-08.
- Timer evidence: fired 2 of 6 nights; both firings failed
  (`run_20260803T014313Z`, `run_20260806T014134Z`).
- Guard arithmetic: `dream_runner.py:4674`,
  `slice = window/(max_retries+1)` → total wait is always `n/(n+1)` of the
  window, so a window fresh at start can never be waited out.
- Do not disturb: `ccbe879` (sub-pass outcomes), `5612f59` (cycle-completes).
- Conventions: `docs/WORKFLOW-thread-handover.md`,
  `docs/WORKFLOW-roadmap-execution.md`.
