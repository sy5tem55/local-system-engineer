# AGENTS.md — read this before touching anything

Two minutes. Everything here cost someone hours to learn.

---

## 1. You are probably in the wrong copy of this repo

There are **two clones**:

| | Path | Role |
|---|---|---|
| **LIVE** | `/home/sy5/projects/local-system-engineer` (WSL, host LUCIFER) | the real tree. All work happens here. |
| stale | `C:\Users\SY5\Claude\Projects\local-system-engineer` | a Windows clone, different branch, months of drift |

Same GitHub remote, different branches. If a file you just wrote "isn't
there", you are looking at the other one.

Working branch: **`codex/fix-sudo-grants-live`**. Check with
`git rev-parse --abbrev-ref HEAD` before you commit — it has changed under a
reviewer mid-session before, and the commit landed on a feature branch.

---

## 2. `tools/goethe_mcp.py` is content-pinned. Do not re-pin it.

`C:\Goethe3.0\...\Scripts\goethe_mcp.py` is a no-replace launcher shim that
SHA-256s `tools/goethe_mcp.py` and **refuses to start on any drift**. Nothing
inside this repo mentions that, which is why it is the first thing in this
file.

On 2026-08-08 an edit to that file broke the HTTP gateway. The refusal
surfaced as:

```
File "<string>", line 15, in <module>
ProcessLookupError: [Errno 3] No such process
[start-goethe-safe] ERROR: launch supervisor degraded before ownership publication
[EXIT] Goethe MCP exited with code 54.
```

That is `os.pidfd_open()` tripping over a supervisor that already died. **Do
not debug the supervisor.** Check the pin.

**The pins belong to the operator.** The GUI depends on specific hashes.
Never edit a shim, never "fix" a mismatch, never re-pin to make a test pass.
Report the mismatch and stop.

`tests/test_gateway_pin.py` exists to surface drift early. It may be **red on
purpose** when backup or dated-staging shims are deliberately pinned to older
hashes. Red here is a signal to ask, not to act.

---

## 3. Running the test suite

```bash
pgrep -af pytest        # MUST be empty first
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

- **Exclusive access is mandatory.** `tests/test_kb_contracts.py` is an
  Elasticsearch integration suite. Overlapping runs corrupt each other's
  counts. A baseline taken during a concurrent run is meaningless, and this
  has already produced two wrong diagnoses in opposite directions.
- **pytest outlives the MCP request timeout** and dies with
  `MCP error -32001`. Background it and poll the log.
- Never report a count you did not watch finish.

Python is `/home/sy5/owui/bin/python3`. ruff is
`/home/sy5/miniforge3/bin/ruff` — **not** `python3 -m ruff`, which is not
installed.

---

## 4. Shell traps

- `execute_command` runs under **`/bin/sh`, not bash**. Process substitution
  `<(...)`, `[[ ]]` and arrays fail with `Syntax error: "(" unexpected`.
  Wrap in `bash -lc`.
- The privilege gate refuses a `git commit` whose **message** quotes a
  privileged command. Write the message to a file and use `git commit -F`.
- Canonical inline Python:
  ```
  cd /home/sy5/projects/local-system-engineer && /home/sy5/owui/bin/python3 - <<'PYEOF'
  <code>
  PYEOF
  ```

---

## 5. Pushing

```bash
./scripts/push-verified.sh          # dry run: shows what would transfer
./scripts/push-verified.sh --push   # push, then PROVE local == remote
```

Exit non-zero means it is not done. Do not read success out of prose; **exit
3 means the push reported success but the remote does not match** —
investigate, never retry blindly, never force.

Never use `@{u}`: a remote branch can exist with no tracking configured, and
`@{u}` then raises a fatal that reads exactly like "nothing is pushed". Use
`origin/$BR`.

Implementers commit; the operator pushes unless told otherwise.

---

## 6. TRAUM in one paragraph

TRAUM mines episode logs, extracts lessons, and proposes KB changes for human
approval. Six passes: `dedup`, `stale-contradiction`, `error-cluster`,
`patterns`, `insights`, `digest`. State lives in
`/opt/local-se/dreams/traum-state.db`. The Console is served by the gateway at
`/ui`.

**Cycles are started by hand.** `goethe-dream.timer` was retired 2026-08-08 and
the unit templates were deleted. Do not offer to re-enable a schedule.

**Never apply a proposal outside the Human Gate.**

Attempt states: `NULL` means looked and found nothing — a good outcome.
`BLOCKED` means could not look. Do not conflate them.

---

## 7. There may be several gateway processes

The launcher does not pattern-kill, so old instances survive restarts. On
2026-08-09 six were alive from five launches. **The process serving your MCP
calls may not be the one listening on `:9700`.** If a code change "isn't
taking effect", find your actual parent before concluding anything:

```bash
ps -o pid=,lstart= -p $PPID
```

---

## 8. Where the state of the work lives

- `docs/ROADMAP-2026-08.md` — the **Status section at the top is the index**.
  Closed items, open items in order, small items. The prose below it is
  history and reasoning, kept because *why* an item exists outlives its state.
- `docs/WORKFLOW-roadmap-execution.md` — model tier, verification depth, the
  four-wave plan, and the allocation rules with the incident behind each.
- `docs/WORKFLOW-thread-handover.md` — the handover prompt template and the
  report/ACCEPTANCE format.
- `docs/SPEC-*.md` — one per work item. §"Ground truth" in each is marked
  **verify, don't trust** for a reason: four specs have shipped with wrong
  rows, and every one was caught by an implementer re-probing.

---

## 9. The one habit that matters

Run the command. Four of five wrong conclusions in the 2026-08-07/09 sessions
came from reasoning about this system instead of querying it — including from
the reviewer, twice. A claim about live state that was not measured this
session is a guess, however confident it sounds.

When challenged, do not restate. Re-run.
