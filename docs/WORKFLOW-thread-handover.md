# Workflow — handing work to a new thread

> 2026-08-01. Written after a handover failed on its first message: the
> receiving thread could not find `/home/sy5/...`, reported that it only had
> an isolated sandbox, and stopped. The spec was fine. The prompt omitted the
> single most important fact — **how to reach the machine.**

---

## 0. The failure this document exists to prevent

Cowork threads have two different execution surfaces, and they are easy to
confuse:

| Surface | Tool | What it can see |
|---|---|---|
| Cowork sandbox | `mcp__workspace__bash` | hostname `claude`; only `outputs/` and `uploads/`. **No LUCIFER, no `/home/sy5`, no repo.** |
| Goethe MCP | `mcp__goethe__execute_command`, `read_file`, `write_file`, `ssh_run` | The real WSL host LUCIFER: the live repo, `/opt/local-se`, systemd, node3090 |

**All real work happens through the Goethe MCP tools.** They are *deferred* —
they appear in the tool list by name only and are not callable until loaded:

```
ToolSearch: select:mcp__goethe__execute_command,mcp__goethe__read_file,mcp__goethe__write_file
```

A thread that skips this sees only the sandbox and concludes — reasonably, and
wrongly — that the task describes a machine that does not exist.

**Therefore: every handover prompt must open with the tool-loading
instruction, before anything else.** Not in the middle, not implied by a path.

---

## 1. Prompt template

Copy this shape. The first block is not optional.

```
FIRST: load the Goethe MCP tools before anything else. They are deferred and
not callable until loaded:
  ToolSearch: select:mcp__goethe__execute_command,mcp__goethe__read_file,mcp__goethe__write_file

All filesystem and shell access to the target machine goes through those
tools. Do NOT use the sandbox Bash/Read tools for this task — they run in an
isolated container that cannot see the repo. If a path like /home/sy5/... is
not found, you loaded the wrong tool, not the wrong path.

Verify access before starting:
  mcp__goethe__execute_command("hostname; ls /home/sy5/projects/local-system-engineer")
  → expect: LUCIFER, and a repo listing.

TASK: <one line>

Read first, in order:
  1. <spec path>
  2. <context path> §<section>

Environment:
  - Live tree: /home/sy5/projects/local-system-engineer  (WSL, host LUCIFER)
  - Branch: <branch>  (already checked out)
  - Python: /home/sy5/owui/bin/python3
  - ruff: /home/sy5/miniforge3/bin/ruff   (NOT `python3 -m ruff`)

Hard constraints:
  - Do NOT git push. Commit only; the operator pushes.
  - `pytest tests/` outlives the MCP request timeout and dies with
    MCP error -32001. Run backgrounded and poll:
      nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
    Baseline: <N> passed.
  - Naming a branch containing "sudo" in a shell command trips the safety
    gate's substring match. Use `git log '@{u}..HEAD'`.
  - <task-specific destructive-operation constraints>

Finish with <report path>, including before/after ruff and test counts, and
an explicit note of anything in the spec's ground-truth table that turned out
to be wrong.
```

---

## 2. When to flip the model in-thread vs. start fresh

**Flip in-thread** when the new work *continues* the current work — same
files, same reasoning, and the design was just worked out together. R1–R3 was
this: Opus designed, Sonnet implemented, and the shared context was the point.

**Start a fresh thread** when the work is a discrete, well-specified unit with
a written spec. A long thread carries adjacent-but-different concepts that
invite confident cross-contamination — during TRAUM work the thread held three
different "guards" (quiet-period, lockfile, safety-gate) and a model picking up
a manifest task could easily conflate them. A filtered spec beats inherited
context.

Rule of thumb: **if you had to write a spec, start fresh. If a spec would be
redundant, flip.**

---

## 3. Turn budget

Not a hard limit, but a signal. In practice, a well-specified single-file task
should complete in roughly **15–30 tool-using turns**. Past ~40 with no working
implementation, something is wrong with the spec, not the model — stop and
report the blocker rather than continuing to explore.

Cheap ways to stay inside it:

- **Batch independent reads into one call.** `grep A; echo ---; grep B` beats
  two round-trips. The safety gate permits `;` chaining for read-only commands.
- **Background anything slow.** The MCP request timeout is ~45s. A blocking
  `sleep`/`pytest`/model-load call wastes a full turn AND fails.
- **Never re-run a passing check to feel better.** If ruff was clean at step 3
  and step 4 touched one function, re-run ruff on that file, not the tree.
- **Read the smallest slice.** `sed -n '200,240p'` over reading a 4,500-line
  file.

---

## 4. What a handover document must contain

The spec that failed was *good* — this is not an argument for longer specs.
It is an argument for these six sections, in this order:

1. **The bug/task**, with the evidence that it is real (a measurement, not a
   claim).
2. **Ground truth, marked verify-don't-trust** — file paths, line numbers,
   function names, current counts. Say explicitly that it was compiled by
   reading code, not running it, and ask the implementer to report anything
   that turns out wrong.
3. **Hazards, before design.** Anything where the obvious implementation is
   wrong. If you know a trap, naming it costs three sentences and saves an
   afternoon.
4. **What to implement**, including what must *not* change and what defaults
   must stay untouched.
5. **Tests, named individually**, flagging which are load-bearing — plus an
   instruction to break them first and confirm they go red.
6. **Invariants and how to run them**, with exact binary paths.

Then: anti-goals, and a report instruction.

---

## 5. Verification discipline (carry into every thread)

These are the rules this project keeps re-learning:

- **An inference is not a measurement.** Reasoning from `ip addr` that a WoL
  packet cannot arrive is a hypothesis; powering the node down and watching is
  evidence. State which one you have.
- **Consult the KB before theorizing** — and if the KB contradicts a
  measurement, the KB may be the thing that is wrong. Fix it in the same
  session.
- **Prove a guard fails before trusting it to pass.** Delete the fix, watch the
  test go red, restore. A test that has never failed has not been shown to
  test anything.
- **Check the whole result, not the part you expected.** A `{"error":
  "unauthorized"}` body has no feature keys in it; reading that as "the feature
  is missing" cost four turns.
- **Read config from the running process, not the file on disk.**
  `/proc/<pid>/environ` is ground truth; `*.env` is a hopeful guess.
- **Never claim runtime success on test-only evidence.** Say which is which,
  explicitly, in the report.

---

## 6. Closing a thread cleanly

Before handing off or stopping:

1. `git status --porcelain` → working tree clean, or every remaining file
   explained.
2. Commits made, and the operator told exactly what to push.
3. Mirror synced if any of the seven watched modules changed:
   `bash scripts/check_goethe_mirror_sync.sh`
4. Anything non-obvious learned → append to
   `/opt/local-se/kb/session-learnings.md` (see the `lse-session-debrief`
   skill). A silent failure discovered and not written down will be
   rediscovered at full price.
5. State plainly what was proven at **runtime** versus by test only, and what
   remains unproven.
