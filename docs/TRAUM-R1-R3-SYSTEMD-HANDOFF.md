# TRAUM R1/R2 — systemd edits for hand-off

Neither of these is applied. Both are `/etc` writes, permanently outside
what the agent can self-apply (`_PRIVILEGED_WRITE_PATHS`). Apply with
`sudo systemctl edit --full <unit>` or by copying the file directly, then
`sudo systemctl daemon-reload`.

---

## R1.3 — goethe-dream.service: no edit required

The plan's Step 1.3 assumed the wake step would need a systemd-level
`After=` dependency declared on the service unit. Having actually read
the live unit, that assumption doesn't hold, and I'm not making an edit
just to check a box:

- The wake step (`tools/wake-node-for-dream.sh`) runs *inside*
  `run-dream-cycle.sh`, which is already `ExecStart`. There is no separate
  systemd unit representing "node3090 is awake" for `After=` to point at
  — node3090 isn't managed by *this* box's systemd at all.
- I checked whether the service's sandboxing would block the wake step
  and confirmed it wouldn't, rather than assuming: `ProtectHome=read-only`
  only affects writes, and the RUTX50 SSH key is only ever read. The one
  real risk — `ssh -o StrictHostKeyChecking=no` normally *writes* a new
  host-key entry to `~/.ssh/known_hosts`, which a read-only `$HOME` would
  block — turned out to be moot: I confirmed via `ssh -v` that the
  RUTX50's key is already trusted (`~/.ssh/config` already has a `rutx50`
  host block from prior manual use), so no write is ever attempted.
- No `RestrictAddressFamilies` or `PrivateNetwork` is set, so the
  script's outbound SSH/HTTP calls are unaffected by the existing
  hardening.

If you still want a documentation-only change (a comment in the unit
noting that node-wake is handled inline, so a future reader doesn't go
looking for a unit dependency that isn't there), say so and I'll prepare
one. I'm not adding it unprompted since Anti-goals says not to touch
things outside R1–R3's stated scope without a reason.

---

## R2.3 — goethe-dream.timer: your call on the trade-off

Current live file:

```ini
[Unit]
Description=Run Goethe TRAUM nightly at 03:30 with jitter

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15m
AccuracySec=1m
Persistent=true
Unit=goethe-dream.service

[Install]
WantedBy=timers.target
```

It already has 15 minutes of jitter — not absent, as the plan's shorthand
implied. The actual problem is `Persistent=true`: on a missed 03:30 (e.g.
node3090 or LUCIFER's own services weren't up), systemd fires the job as
soon as possible after next boot/wake — which was the operator's own
desk, at ~09:45, three of four observed times. `RandomizedDelaySec`
applies to that catch-up firing too, so raising it *reduces* how tightly
runs cluster around wake time but does not eliminate the coincidence —
if you're consistently at your desk within the same 15–30 minute window
each morning, a bigger jitter only spreads that same collision around.

**Option A — keep catch-up, widen the jitter.** A missed night still
runs, just less predictably close to 09:45. Simple, one-line change.

```ini
[Unit]
Description=Run Goethe TRAUM nightly at 03:30 with jitter

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=30m
AccuracySec=1m
Persistent=true
Unit=goethe-dream.service

[Install]
WantedBy=timers.target
```

**Option B — drop catch-up entirely.** A missed night is simply skipped;
the next real trigger is the following 03:30. No more wake-time
collisions, ever, at the cost of occasionally losing a full night's cycle
if the box was down at 03:30 (R2.1/R2.2 now make it far less likely a
*running* cycle self-aborts on session activity, but they don't help a
cycle that never started because the machine itself was asleep).

```ini
[Unit]
Description=Run Goethe TRAUM nightly at 03:30 with jitter

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15m
AccuracySec=1m
Persistent=false
Unit=goethe-dream.service

[Install]
WantedBy=timers.target
```

Given R1 now wakes node3090 for the 03:30 run itself, the main remaining
reason a night gets missed is LUCIFER (this box) being off or the timer
unit itself being disabled — both rarer than "node3090 was asleep," which
R1 already fixes. That tilts me slightly toward B, but it's a genuine
trade-off between "never miss a night" and "never collide with your
morning" — your call, not mine to make unprompted.

Apply either with:

```
sudo systemctl edit --full goethe-dream.timer
# paste the chosen content, save
sudo systemctl daemon-reload
```
