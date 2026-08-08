# Report — dreaming becomes manual (SPEC-manual-dreaming-2026-08)

> Implementation: Sonnet 5 High, 2026-08-08. Branch
> `codex/fix-sudo-grants-live`, synced to origin at `ce7dfb7` at session
> start. This report covers everything V2 (code) can verify. §4.1 (the
> actual timer removal) is V-delegated: it requires `sudo systemctl`/`/etc`
> writes this session is not permitted to make, per Hazard C. **Update: the
> operator ran the delegated block during this same session — see §11 for
> the closing, authoritative state.**

---

## 1. What landed

Four separate commits, deliberately (Hazard E — "one behaviour change at a
time"; the spec named this explicitly and a prior TRAUM session had already
been burned by two changes landing together):

| Commit | What | Files |
|---|---|---|
| `b0a2758` | §4.2 — introduce `"manual"` run-source; widen the two admission-control checks and the argparse choices tuple; `run-dream-cycle.sh` now passes `--run-source manual` | `tools/traum_state.py`, `tools/dream_runner.py`, `tools/run-dream-cycle.sh`, `tests/test_manual_dreaming.py` (new) |
| `fb7e3fd` | §4.3 — `--skip-session-guard` on by default for the manual entry point, opt-out via `GOETHE_DREAM_SKIP_SESSION_GUARD=0` | `tools/run-dream-cycle.sh`, `tests/test_manual_dreaming.py` |
| `ddf5580` | §4.5 — operator manual and roadmap now describe manual-only operation | `docs/TRAUM-OPERATOR-MANUAL.md`, `docs/ROADMAP-2026-08.md` |
| `56192e3` | test-coverage fix found during the mandated break/red/restore exercise (see §5) | `tests/test_manual_dreaming.py` |

§4.1 (delegated timer removal) and §4.4 (dead-code removal) are addressed
below without a corresponding commit — §4.1 because it is not mine to run
(closed by the operator, §11), §4.4 because there turned out to be nothing
to delete (§4 below).

Not touched, per the anti-goals: `run-dream-cycle.sh` was not deleted
(Hazard A); `"scheduled"` was not removed from any read/validation path
(Hazard B); `_recent_session_active` and the retry loop are untouched
(Hazard D); the per-pass wall-clock formula (`5612f59`) and
`_raise_if_dependency_blocked`/sub-pass work (`ccbe879`) are untouched; no
`systemctl` command was run and nothing was written under `/etc/` by me —
§4.1's commands were run by the operator, in their own terminal (§11).

`tools/voicebox-tts-proxy.py` remains untracked in the working tree; it
predates this session (also called out untouched in the prior
`2026-08-08-cycle-completes.md` report) and was not touched or committed.

---

## 2. Ground truth from the spec's §2 table — what was re-probed, what turned out wrong

Re-probed live, this session, before implementing:

- `systemctl is-enabled goethe-dream.timer` → **enabled**, and
  `systemctl status` shows it **active (waiting)**, next trigger tonight.
  Confirmed still live, matching the spec, at that point in the session.
- `sqlite3 /opt/local-se/dreams/traum-state.db "select source, count(*) from runs group by 1"`
  → **`gui|13`, `legacy-import|9`, `scheduled|8`**.

Three things in the spec's ground-truth table turned out to be wrong or
incomplete, in ascending order of consequence:

1. **Historical `scheduled` row count.** Spec said "seven historical runs".
   Measured: **8**. Doesn't change anything (Hazard B applies at any count
   ≥ 1), but it's the kind of small thing §2 asks to flag.

2. **Suite baseline.** Spec's own §2 table and §7 say **830 passed**. The
   task prompt that spawned this thread said **833 passed**. Measured,
   fresh, before touching anything: **833 passed, 0 skipped** — the task
   prompt was right, the spec document was stale by 3 tests (most likely
   written a session or two before this one; `ce7dfb7`, the tip this thread
   started from, post-dates whatever state the spec was checked against).

3. **The validation set the spec named is not the only one, and isn't
   what Hazard B says it is.** Spec §2 lists exactly two locations:
   `traum_state.py:491` and `:542`, both `if source in {"gui", "scheduled"}`.
   There is a **third location the spec's table never mentions**:
   `dream_runner.py:4024` —
   `ap.add_argument("--run-source", choices=("cli", "scheduled", "gui"), ...)`.
   This is a hard `argparse` choices constraint. Had I widened only the two
   named locations, `--run-source manual` would have failed at argument
   parsing — a `SystemExit(2)` from argparse — before `traum_state.py` was
   ever reached. Widened it too (commit `b0a2758`), and added
   `test_dream_runner_accepts_manual_run_source` to catch a regression here
   specifically, since the spec's own table would not have caught it.

   Separately, and more interesting: **Hazard B's stated failure mode does
   not match the code.** Hazard B says narrowing the set "would make those
   rows unreadable." I built the break/red/restore exercise (spec §6, last
   line) around that literal claim first, narrowed the set back to
   `{"gui", "manual"}`, and every "does scheduled still work" test I had
   **stayed green** — including a fresh `create_run(source="scheduled")` +
   `get_run()` round trip. Read the code: `TraumState._run_row` (line 432)
   does no source filtering at all, on any path. The `{"gui", "scheduled"}`
   check at `:491`/`:542` gates one thing only — whether
   `_recover_orphaned_controller_work_tx` runs at creation time, i.e.
   same-run-active admission control (`ConflictError` on a second
   concurrent run of that source). Narrowing the set doesn't touch
   readability at all; it silently drops that protection for
   scheduled-sourced runs. Measured directly (see §5) — this is not a
   theory. I added the test that actually catches it
   (`test_scheduled_source_still_gets_admission_control`, commit `56192e3`)
   and left a note in its docstring for the next thread that reads Hazard B
   literally.

One more thing found, not in the spec's table at all and not fixed here
(deliberately, see §4): `traum_controller.py:1258`'s `timer_status()` method
and the `GET /api/ui/traum/timer` route it backs (documented in
`docs/TRAUM-OPERATOR-MANUAL.md` §8, and covered by
`tests/test_traum_controller.py:401`) issue a live, read-only
`systemctl show goethe-dream.timer` call from the Console. Also,
`tests/test_dream_service_units.py` is a "static deployment contracts"
suite that asserts properties of `scripts/systemd/goethe-dream.timer`
including `Persistent=true` — which already contradicts the live unit's
`Persistent=false` (a pre-existing repo/deploy drift, unrelated to this
change, and plausibly part of *why* the timer has been unreliable — see §3).

---

## 3. Why retiring the timer is right (unchanged from spec, confirmed)

`goethe-dream.timer` fired 2 of the last 6 nights and both firings failed;
every cycle that has ever completed was started by hand. `Persistent=false`
combined with LUCIFER (WSL) usually being down at 03:30 explains the miss
rate. This is exactly what §1 of the spec argued and nothing measured this
session contradicts it.

---

## 4. §4.4 — "remove the scheduling machinery that now has no caller"

Looked for a `--run-source scheduled` branch or timer-specific preamble in
`tools/run-dream-cycle.sh` to delete. There isn't one to find: the script
never branched on the source value — it is, and always was, one linear
sequence with `--run-source <literal>` as a single argument. Renaming the
literal (commit `b0a2758`) *is* the entire "scheduled machinery" in this
file. Also checked `tools/wake-node-for-dream.sh`, `tools/sleep-node-after-dream.sh`,
`tools/dream_digest.py`, and `dream_runner.py`'s use of `cfg.run_source`
(exactly two call sites: the dataclass field and the pass-through to
`create_run`) — no branching on `"scheduled"` anywhere outside the three
locations already widened.

Updated the top-of-file comment (previously "Canonical **unattended** TRAUM
cycle. The outer **systemd timeout** bounds the complete cycle") to describe
the script as the manual CLI entry point, since leaving stale "unattended
via systemd" framing in the file's own header felt like exactly the kind of
inaccuracy §4.5 is about — bundled into commit `b0a2758` since it travels
with the rename, not as separate scheduling-machinery deletion.

Per the instruction ("if unsure whether something is reachable, leave it and
say so"): `traum_controller.py`'s `timer_status()`/`GET /api/ui/traum/timer`
and `tests/test_dream_service_units.py` were left alone. They are not named
in the spec's enumerated §4 items, and gutting a Console-facing read-only
status feature wasn't asked for. Now that §4.1 has landed (§11),
`timer_status()` will report `LoadState=not-found`/similar rather than a
schedule — which the existing code already handles gracefully (returns
`available: False` or empty properties, doesn't raise) — but the feature
itself, and whether it should be removed, is a follow-up decision for the
operator, not something I judged in scope here. Flagged in
`docs/TRAUM-OPERATOR-MANUAL.md` §8 (commit `ddf5580`).

---

## 5. Break/red/restore (spec §6, mandatory)

**Test 2 (Hazard B) — first attempt did NOT go red**, which is itself the
finding in §2 above. Narrowed `traum_state.py:491`/`:542` from
`{"gui", "scheduled", "manual"}` back to `{"gui", "manual"}` and ran the
existing "scheduled still works" tests: all green. That's because those
tests only checked creation and read-back, neither of which the set gates.
Wrote a test that checks the thing the set actually gates
(same-run-active admission control), confirmed it red under the same break,
confirmed green after restore. Transcript:

```
$ pytest tests/test_manual_dreaming.py::test_scheduled_source_still_gets_admission_control -v
FAILED tests/test_manual_dreaming.py::test_scheduled_source_still_gets_admission_control
E       Failed: DID NOT RAISE ConflictError
1 failed in 0.20s
```

Restored (`sed` back to the three-value set), reran: `11 passed in 1.06s`.
`git diff --stat tools/traum_state.py` against the committed state was
empty after restore — confirmed byte-for-byte, not just "tests pass."

**Test 5 (Hazard A, `5612f59`'s wall-clock formula)** — changed
`pass_budget=$(( remaining_seconds / passes_left ))` to
`$(( remaining_seconds / (passes_left + 1) ))` in the shipped script (kept a
full pre-break copy at `/tmp/run-dream-cycle.pre-break5.sh` first).
Transcript:

```
$ pytest tests/test_cycle_completes.py::TestPerPassWallClockAllocation -v
FAILED test_6_first_pass_gets_a_share_not_the_whole_cycle
E       assert 450 == 540
1 failed, 5 passed in 0.04s
```

Restored via `diff`+`cp` from the pre-break copy (confirmed identical to the
committed version via `git diff --stat`, empty). Reran:
`TestPerPassWallClockAllocation` + `tests/test_manual_dreaming.py` together
→ `17 passed in 1.14s`.

---

## 6. Invariants (spec §7)

```
$ python3 -m py_compile tools/traum_state.py tools/traum_controller.py tools/dream_runner.py
py_compile OK
$ bash -n tools/run-dream-cycle.sh
bash -n OK
$ ruff check tools/traum_state.py tools/traum_controller.py tools/dream_runner.py
Found 36 errors.        # before AND after -- identical count, see below
$ ruff check tests/test_manual_dreaming.py
All checks passed!
```

Ruff, before/after, same three-file set the spec's baseline used:

| | before | after |
|---|---|---|
| `tools/traum_state.py` + `tools/traum_controller.py` + `tools/dream_runner.py` (combined) | 36 | 36 |
| `tools/traum_state.py` alone | (not measured alone) | 4 |
| `tools/dream_runner.py` alone | (not measured alone) | 18 |
| `tools/traum_controller.py` alone (untouched this session) | (not measured alone) | 14 |

All 36 are pre-existing (mostly `F841`/style, e.g. the `legacy-import` call
site's unused `run` local at `traum_state.py:1841` — untouched by this
change). Pre-existing count did not increase. `tests/test_manual_dreaming.py`
is the only new file and is ruff-clean.

Pytest, full suite, backgrounded per the MCP-timeout workaround (no
concurrent run — confirmed via `pgrep -af pytest` before both the baseline
and final runs):

| | count |
|---|---|
| Baseline (session start, `ce7dfb7`) | **833 passed, 0 skipped**, 132.17s |
| Final (this report's HEAD, `56192e3`) | **844 passed, 0 skipped**, 132.69s |

Delta: **+11** — 10 new tests in `tests/test_manual_dreaming.py` at commit
`b0a2758`/`fb7e3fd`, +1 more at `56192e3` (the Hazard B coverage fix from
§5). No existing test file's count changed; no test was deleted or skipped.

---

## 7. §4.1 — delegated (superseded by §11)

*As originally written, before the operator's run:* "Not run. Emitted
separately as a `sudo_delegation_block` in this session's chat response,
containing exactly the four commands and the `verify_command` from spec
§4.1. Do not treat the timer as gone until the operator runs that block and
`systemctl list-unit-files | grep -i goethe-dream` comes back empty."

That happened later in the same session. See §11 for the closing,
authoritative state — left this section as-is rather than rewriting history,
per the same "don't silently overwrite the trail" instinct as the rest of
this report.

---

## 8. Runtime-proven vs. test-only (WORKFLOW §5, stated explicitly)

**Test-only, for everything in §1–§6.** No real dream cycle was run against
live `dream_runner.py`/node3090/the real state db. The guard-default tests
(`TestGuardDefaultOnManualEntryPoint`) run the *actual shipped*
`run-dream-cycle.sh` under `bash`, but against a stub `python3` that only
records argv — real script, real conditional logic, fake payload. That
proves the script *builds the right command line*; it does not prove a real
cycle completes with `source='manual'` end to end.

**§4.1 itself is now runtime-proven** (§11): the operator ran the real
commands on the real host and this session independently re-verified the
real systemd state afterward. That is the one part of this report that
moved from test-only to runtime-proven.

Still outstanding, still test-only/unproven: a real dream cycle completing
end-to-end with `source='manual'` and no `recent-session-activity` block.
Spec §8 is explicit that this proof comes from the operator running one
real cycle after §4.1 lands, not from this session.

---

## 9. What the operator does next

1. Review this report and the four commits (`git log --oneline
   ce7dfb7..HEAD`, `git diff --stat ce7dfb7..HEAD`).
2. ~~Run the `sudo_delegation_block` emitted alongside this report
   (§4.1).~~ **Done — see §11.**
3. ~~Confirm with `systemctl list-unit-files | grep -i goethe-dream`
   (expect no output).~~ **Done — see §11.**
4. Run one manual cycle from the Console or `tools/run-dream-cycle.sh`
   directly; confirm the run's `source` is `manual` (CLI) or `gui`
   (Console) and that no attempt is `BLOCKED` on
   `recent-session-activity`. **Still outstanding.**
5. `git push` — not done here, per the hard constraint. **Still
   outstanding.**
6. Decide, separately, whether `traum_controller.py`'s `timer_status()` /
   `GET /api/ui/traum/timer` and `tests/test_dream_service_units.py` should
   be retired now that the timer itself is gone (§4 above) — out of this
   spec's scope, flagged as a follow-up, not actioned. **Still
   outstanding.**
7. Optionally close the masking gap noted in §11:
   `systemctl mask goethe-dream.timer` (would now succeed — no file in the
   way — and protects against a stray file resurrecting the unit later).
   **Still outstanding, still privileged, still not mine to run.**

---

<!-- ACCEPTANCE
task: manual-dreaming
commit: 56192e3
tests_before: 833
tests_after: 844
files_changed: docs/ROADMAP-2026-08.md, docs/TRAUM-OPERATOR-MANUAL.md, tests/test_manual_dreaming.py, tools/dream_runner.py, tools/run-dream-cycle.sh, tools/traum_state.py
ruff_clean: tests/test_manual_dreaming.py
runtime_verified: false
-->

Note on the ACCEPTANCE block's `commit` field: this handover is
**four commits**, not one (`b0a2758`, `fb7e3fd`, `ddf5580`, `56192e3`), by
design (Hazard E). `verify-handover.py`'s `files_changed matches commit`
check diffs a single ref, so pointing it at `56192e3` (HEAD) alone will
report the files touched by every commit *except* that one as "in commit
but not claimed" — that is a limitation of the tool against a
multi-commit handover, not a discrepancy in the actual change set. The
authoritative file list is `git diff --stat ce7dfb7..HEAD`, reproduced in
§1's commit table and matching `files_changed` above exactly. See §10 for
the actual `verify-handover.py` run and its output.

`runtime_verified: false` describes the code/test claims in this
ACCEPTANCE block (§1–§6), which is what `verify-handover.py` checks. §11's
systemd-level proof is real but is outside what this block's schema
represents — read §11 directly rather than inferring it from this flag.

---

## 10. `verify-handover.py --run-tests` transcript

```
$ python3 scripts/verify-handover.py docs/reports/2026-08-08-manual-dreaming.md --run-tests
handover verification: docs/reports/2026-08-08-manual-dreaming.md
----------------------------------------------------------------------------
  commit exists                  PASS  56192e3e263145c181e7ebfec7f1486437381f44
  files_changed matches commit   FAIL  claimed but not in commit: ['docs/ROADMAP-2026-08.md', 'docs/TRAUM-OPERATOR-MANUAL.md', 'tools/run-dream-cycle.sh', 'tools/traum_state.py']
  working tree clean             FAIL  ?? docs/reports/2026-08-08-manual-dreaming.md
?? tools/voicebox-tts-proxy.py
  ruff clean on claimed files    PASS  All checks passed!
  suite reports 844 passed       PASS  actual: 844 passed

2 mechanical claim(s) failed.
NOTE: runtime_verified is not true -- treat behavioural claims as test-only evidence.
This checks mechanical claims only. Design correctness, guard narrowness and
hazard handling still need a reviewer.
```

Both FAILs are accounted for, not live problems:

- **`files_changed matches commit`** — the multi-commit limitation from §1's
  note, exactly as predicted before this was run: `56192e3` alone only
  touched `tests/test_manual_dreaming.py`, so the tool reports the other
  three files (touched by `b0a2758`/`fb7e3fd`) as unclaimed-by-that-commit.
  `git diff --stat ce7dfb7..HEAD` is the correct four-commit picture and
  matches `files_changed` in the ACCEPTANCE block exactly.
- **`working tree clean`** — this report file itself was, at the moment the
  check ran, not yet committed (chicken-and-egg: the report has to exist
  before it can be committed, and this transcript has to exist before the
  report is complete). `tools/voicebox-tts-proxy.py` is the pre-existing
  untracked file noted in §1 and in the prior `2026-08-08-cycle-completes.md`
  report — not mine, not touched. This report is committed immediately
  after this section is written; from that point the only remaining
  untracked entry is `voicebox-tts-proxy.py`.
- **`suite reports 844 passed` — PASS**, authoritative (`--run-tests`
  actually ran the suite, not the cached §6 number).

**`ruff clean on claimed files` — PASS**, authoritative for
`tests/test_manual_dreaming.py`, the only file this ACCEPTANCE block claims
as ruff-clean.

---

## 11. §4.1 closed — operator ran the delegated block

Operator ran the four commands from the `sudo_delegation_block`. Their
terminal output, pasted back verbatim:

```
$ systemctl disable --now goethe-dream.timer   [run with sudo]
Removed "/etc/systemd/system/timers.target.wants/goethe-dream.timer".
$ systemctl mask goethe-dream.timer   [run with sudo]
Failed to mask unit: File /etc/systemd/system/goethe-dream.timer already exists.
$ rm /etc/systemd/system/goethe-dream.timer /etc/systemd/system/goethe-dream.service   [run with sudo]
(no output)
$ systemctl daemon-reload   [run with sudo]
(no output)
$ systemctl list-unit-files | grep -i goethe-dream || echo "no goethe-dream units remain"
no goethe-dream units remain
```

**The mask step failed.** `systemctl mask` creates a symlink to
`/dev/null` at the unit's path and refuses to do that over an existing real
file — and at that point in the four-line sequence the real
`goethe-dream.timer` file was still there; `rm` was the *next* line, not
yet run. The spec's stated ordering intent ("mask first, then remove, so a
stray daemon-reload cannot resurrect it") was therefore not achieved as
designed. `rm` removing the real files directly got to the same *current*
end state regardless, but the two paths differ in what protects that state
going forward: a masked unit stays inert even if a file reappears at that
path later (a stray deploy script, a package reinstall, manual error); a
unit that is merely absent does not — if
`/etc/systemd/system/goethe-dream.timer` is ever recreated, systemd will
pick it up again on the next `daemon-reload`, live and enabled, exactly as
before. This is a real residual, flagged for the operator (§9 item 7), not
fixed here — masking now (with no file in the way) is itself another
privileged `/etc/` operation.

**Independently re-verified**, this session, read-only, after the
operator's run — not just trusting the pasted terminal output (WORKFLOW §5:
"an inference is not a measurement"; this is the measurement):

```
$ systemctl list-unit-files | grep -i goethe-dream
(no output)
$ ls /etc/systemd/system/goethe-dream*
(no output — file does not exist)
$ systemctl status goethe-dream.timer
Unit goethe-dream.timer could not be found.
$ systemctl is-enabled goethe-dream.timer
not-found
```

§4.1 is done. `goethe-dream.timer` and `goethe-dream.service` are gone from
`/etc/systemd/system/` and from every systemd view checked, on both the
operator's transcript and this session's independent re-probe. Per spec §8,
this report can now say so on the strength of `systemctl list-unit-files`
saying so — confirmed twice, by two different actors, not asserted from the
delegation block having been emitted.

The remaining item from §9's operator checklist — running one real manual
cycle and confirming `source='manual'` with no `recent-session-activity`
block — is still outstanding and still the operator's to do; nothing in
this session ran a live dream cycle.
