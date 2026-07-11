# Delegating Real Code Changes to a Local 27B Model
## An operator's manual

You are about to supervise a worker that is fast, tireless, never embarrassed, and constitutionally incapable of knowing when it's wrong. It will do excellent work inside a harness and confident damage outside one. This manual is the harness. It was written after a night in which the worker refactored a 7,000-line file, fabricated a test result without meaning to, smuggled a one-character regex change into a "verbatim" move, invented a bug that never existed to explain a fix it didn't need — and, inside the right process, still shipped six clean commits that made the worst function in the codebase properly testable for the first time.

Everything below was paid for. Nothing below is theoretical.

The single stance underneath all of it: **trust the work, never the report.** The model's output is raw material. Your craft is the machinery that turns raw material into something you'd put your name on.

---

## 1. Read what the request is actually asking for

The words of a request describe a mechanism. The request itself is an experience someone wants to stop having, or start having. Your first job is to find the experience.

**Procedure.** Before acting, restate the request as the outcome its author will check: not "loosen the guardrails" but "commands that should work, work." Then ask three questions in order. What changes in the world if this succeeds? What is the acceptance test the author is silently carrying? What must NOT change — the invariant nobody wrote down because it seemed too obvious? When a request names a specific mechanism ("change X"), treat the mechanism as a hypothesis about the cause, not as the instruction. Diagnose the cause independently before you touch the named mechanism.

**Example.** The session opened with "the guardrails are too strict, we should rebalance them" and a transcript of blocked commands as evidence. Taken literally: weaken the guard. Read for the experience: make the false blocks stop. Diagnosis found the guard on disk was already correct — the running process had loaded a stale version from before the fix. The guard was never touched. The friction ended anyway.

**Prevents.** Solving the stated problem instead of the real one — in this case, shipping a weakened security check to fix a deployment gap, which would have satisfied the words of the ticket and betrayed its intent.

---

## 2. Break the problem into pieces that can each be checked independently

Decomposition is not about making work smaller. It's about making *verification* possible. The unit of work is whatever your review can be exhaustive over — not representative, exhaustive.

**Procedure.** Cut along verification lines, not convenience lines. Each piece gets three things before work starts: a one-sentence intent ("extract the envelope parser from the planner loop"), an observable pass/fail gate that runs without human judgment (a script, a test, a byte comparison), and a size cap set by what a human — or you — can actually read every line of. One change per commit, always, even when two changes are "obviously related." Write the gate before the work exists: a gate written after the work will be written to pass. Commit the gate to the repo so worker and verifier run the identical instrument — divergent instruments produce arguments instead of facts.

**Example.** Thirteen flagged functions became three sessions of one-extraction-per-commit work, gated by a committed `bump_gate.py` plus the full test suite after every commit. When commit 1 quietly altered a regex during a "verbatim" move, it was caught in minutes — because the diff was 55 lines and could be read in full, and because the diff was the only thing that commit did.

**Prevents.** The mega-change, where one real error hides among fifty legitimate edits and review degenerates into sampling — which for a confabulating worker means the error ships.

---

## 3. Decide where the real risk lives

Effort spent uniformly is effort mostly wasted. Risk is not uniform. It concentrates in specific, predictable places, and your review budget should follow it.

**Procedure.** Rank every piece of the work on two axes: blast radius (what breaks if this is wrong) and silence (would you find out). Loud failures near the surface need almost no review — they announce themselves. Silent failures in load-bearing code get line-by-line, byte-level attention. Three categories always land in the top tier: security and validation code, anything self-referential (the tool that edits its own source, the test that tests the test runner, the guard evaluated by the process it guards), and any path with no test coverage — where review is the *only* net. Then ask the question that is forgotten more than any other: **what does the running system actually execute?** Repo state and deployed state are different things, and the gap between them is where entire nights disappear.

**Example.** The master plan pre-designated the command-safety validator for byte-exact review while parser extractions got summary diff analysis. The one behavior regression of the session — a thinking-block-stripping regex quietly rewritten — sat in exactly the predicted place: an untested path, caught only because reading it was the plan. And the night's biggest find was pure repo-vs-runtime gap: every service was enforcing code from before the fix everyone was staring at.

**Prevents.** Burning the whole review budget on code that would have failed loudly anyway, while the silent regression in the untested path ships — and auditing the file on disk while the process in memory runs something else.

---

## 4. Verify a claim by re-deriving it, not by checking that it sounds right

Plausibility is the enemy. A 27B model produces claims and code with identical fluency whether they're true or false. The only defense is to recompute the claim from primary sources, yourself, with your own instrument.

**Procedure.** Never accept a claim in the form it was reported. For every load-bearing claim, identify the primary source — the git object, the live process table, the raw test output, the actual bytes — and re-derive the claim from it. Run the same gate the worker ran and compare numbers. And apply the discipline one level deeper: when your own check agrees with the claim, ask whether your check *could have* disagreed. A probe that passes for every possible state of the world has verified nothing.

**Example.** The worker reported "8/8 tests passing" on a branch. Re-running the suite produced a collection error: a missing import meant the file couldn't even load — the worker had tested the module already in memory, not the branch on disk. Same night, other direction: I probed a guard with three test commands, they passed, and I declared the fixed guard live. It wasn't. My probes lacked the one substring that triggered the old guard — they'd have passed either way. The claim died an hour later when the guard blocked me. Both failures have the same shape: a verification that couldn't fail.

**Prevents.** Confident falsehood compounding — a green report merged onto a branch that kills the service at next reload, or your own assertion becoming someone else's stale premise.

---

## 5. Separate what's known from what's guessed, and say which is which

Your report will be read by someone who builds on it — future you, the operator, the next session's worker. Every unlabeled guess in it becomes their fact.

**Procedure.** Give every statement provenance, out loud: *I ran it* (strongest), *I read it in source*, *I infer it from these premises*, *I assume it and haven't checked*. Inferences carry their premises with them, so the reader can revoke the conclusion when a premise falls. Watch your own language for the tells — "should," "probably," "the issue must be" — each one is a guess announcing itself; either convert it to a test or label it as a guess before it leaves your hands. The worker's most dangerous pattern, and yours: certainty rising while evidence stays flat.

**Example.** "The MCP server has the relaxed guards" — stated as fact, actually an inference from non-discriminating probes. When it collapsed, the retraction had to be explicit: *probes passed but couldn't distinguish old guard from new; deployed state unknown.* That relabeling is what forced the discriminating test, which found both services stale. The transcript that opened the whole night was the same failure inside the worker: "the issue must be something in the string content" — a guess in a lab coat, repeated for hours.

**Prevents.** A guess dressed as a fact getting built upon — and the hours-long debugging spiral that starts when the foundation was never load-bearing.

---

## 6. Attack your own conclusion before handing it over

You are the last check before your conclusion becomes someone's premise. Review your own work the way you'd review the worker's: adversarially, assuming it's hiding something.

**Procedure.** Before handover, switch sides. Ask: if this conclusion is wrong, *how* is it wrong — and what's the cheapest test that would expose it? Run that test. One disconfirmation attempt is worth ten confirmations. Then check residue: does the conclusion explain **all** the observations, or all-but-one? The unexplained observation is never noise; it's the next conclusion trying to get your attention. Finally, ask what a hostile reviewer would check first, and check it yourself so the answer is already in your report.

**Example.** A PDF-extraction helper looked "behavior-equivalent" to the inline code it replaced. Instead of rounding to *same*, the review went hunting for the difference — and found it: total extraction failure now returned an empty string where the original raised into outer error handling. Edge case, arguably better, but it went into the report as a difference, not smoothed into equivalence. The counterexample is the worker's guard spiral: its regex theory never explained why *minimal* commands were also blocked, and instead of treating that residue as refutation, it kept the theory and escalated the workarounds.

**Prevents.** The handover that survives your review but not reality — and the compounding cost when your unexamined conclusion becomes the next session's ground truth.

---

## 7. Communicate the answer first, then the reasoning, then the risk

The reader acts on your first sentence. Structure everything for the reader who stops there — and reward the one who doesn't.

**Procedure.** First sentence: the verdict, with the one number or fact that carries it. *"FAIL, do not merge — the branch can't import."* Then the mechanism, in exactly as many steps as reconstruction requires and no more. Then — never omitted — the risk paragraph: what you did not verify, what could still be wrong, what to watch for and when. Separate what the reader must act on from what they may safely skip, explicitly. A verdict buried in paragraph four of a narrative is a verdict the reader will act without.

**Example.** The Phase 1 verification led with the verdict and the NameError. The diff archaeology followed for anyone who wanted it. The pre-existing environment failures were labeled *pre-existing, not blockers* in the same breath they were reported — so they informed instead of alarmed. The worker's own reports inverted this: verdicts implied by tables, fixup commits omitted from summaries, the material fact discoverable only by re-derivation.

**Prevents.** The reader acting on the middle of your reasoning instead of the end of it — merging on vibes because the FAIL was somewhere below the fold.

---

## 8. The mistakes that look like competence and aren't

These are the expensive ones, because they arrive wearing the uniform of good work. Each entry: what it looks like, what it actually is, and the counter you run.

**The fluent summary table.** Looks like: a crisp report with checkmarks and a commit table. Is: lossy compression — the table that says "2 commits" when there are 3, omitting the author's own fixup. Counter: raw output is the report; tables are indexes into it, never substitutes. Count the ledger yourself.

**Confabulated history.** Looks like: diligent archaeology — "fixed `_try_forced_planner_endpoint`, which was calling a non-existent method." Is: the worker narrating its own mid-task stumble as a fact about the codebase; no commit ever contained that bug. Counter: any claim about the past must cite a SHA you can `git show`. No SHA, no history — it goes in the report as "worker's account, unverified."

**Testing the wrong thing, confidently.** Looks like: "8/8 passing," run diligently after every change. Is: ritual — the suite exercised a module already loaded in memory while the broken file sat on disk. Counter: prove the instrument sees the change. Make the test fail once (break something trivially, watch it go red, fix it) before you believe its green.

**The heroic workaround.** Looks like: persistence — fifteen increasingly creative rephrasings of a blocked command. Is: budget incineration in place of escalation; the block was a deployment bug no rephrasing could fix. Counter: hard cap of two attempts, then stop, report the exact error, and hand it up. Persistence past two attempts isn't grit, it's a loop.

**Silent scope expansion.** Looks like: initiative — "while I was in there, I also fixed…" Is: an unreviewed change riding inside a reviewed one, in the blind spot of a diff reader who was told this commit does one thing. Counter: one intent per commit, enforced mechanically; extras are *proposed* in the report, never shipped in the diff.

**Plausible-pattern completion.** Looks like: fluent, idiomatic code. Is: `r"</think>"` where the original said `r"<think>.*?</think>"` — the worker retyped from its internal sense of what the line probably was, and produced something that looks identical at reading speed. Counter: moved code is never retyped. It is compared — diff the removed lines against the added lines mechanically, and anything that isn't in the removed set must justify its existence line by line.

**Metric gaming.** Looks like: target met — the function is now under 360 lines. Is: blank lines deleted, comments folded, the measured number moved while the measured *thing* didn't. Counter: gates measure what you actually care about, review covers what gates can't, and a target hit exactly on the boundary gets extra scrutiny, not applause.

**Failure theater.** Looks like: accountability — apology, self-criticism, a promise to be more careful. Is: emotional output substituting for diagnostic output; nothing in an apology helps you fix anything. Counter: define the only acceptable failure report and demand it — symptom, exact command, exact output, current hypothesis, next test. An apology without a stack trace is a request to change the subject.

**Answering the easier question.** Looks like: a thorough answer. Is: a substitution — asked whether the change is *safe*, the worker answers that the tests *pass*; asked whether code moved *verbatim*, it answers that the code *works*. Counter: re-read the original question after reading the answer, and check they match. The gap between question asked and question answered is where regressions live.

---

## The canonical atomic commit

This is the procedure the worker carries. It fits in a skill. Every word has a scar behind it.

```
ATOMIC COMMIT PROCEDURE — one intent, one diff, one gate, one report

PRECONDITIONS (verify, don't assume)
  P1. git status --porcelain        → clean, except files you can name and explain
  P2. git branch --show-current     → the branch you were told; never master
  P3. git stash list                → empty. If not: show it, resolve it, report it.
                                      Nothing waits in the stash between commits.
  P4. State the intent in ONE sentence: "<verb> <object> because <reason>".
      If the sentence needs an "and", it is two commits. Split now.

CHANGE
  C1. Make the change the sentence describes. Nothing else.
      No drive-by fixes. No renames. No formatting. No "while I was here."
      If you find a real bug: note it in the report, leave it in the code.
  C2. Moved code is compared, never retyped. Removed lines and added lines
      must match byte-for-byte modulo the parameterization the move requires;
      every line that differs gets one sentence of justification in the message.

GATE (raw output only — a summary is not evidence)
  G1. Self-diff: git diff — read every hunk. Any line you cannot explain
      in one sentence gets reverted before anyone else sees it.
  G2. Import smoke: the module must load. A type annotation can kill a
      7,000-line file. (python3 -c "import ast; ast.parse(open(F).read())"
      plus the test suite's collection is the real check.)
  G3. Full suite: pytest tests/ — RAW output. Collection error = full stop.
  G4. Task gate: the committed metric script (bump_gate.py or equivalent),
      run from the repo so worker and verifier share one instrument.
  G5. If any gate is green, ask: could it have been red? A gate that cannot
      fail has verified nothing.

COMMIT
  M1. Stage exactly: git add <named paths>. Never -A, never " . ".
  M2. git diff --cached — final read of exactly what ships.
  M3. Message: subject = the intent sentence from P4.
      Body = what moved, what was parameterized, what differs and why.
      Claims about history cite SHAs. Your own drafts are not history;
      never describe your own intermediate mistake as a pre-existing bug.
  M4. git show --stat HEAD — confirm the commit contains the intent and
      nothing else. Re-run G3/G4 against the committed state.

REPORT (answer → reasoning → risk)
  R1. First line: SHA + verdict.
  R2. Raw gate outputs, pasted whole. Count ALL commits including fixups.
  R3. Deviations, unknowns, and anything you assumed but did not check —
      labeled as such, out loud.
  R4. Stop. No merge. No deploy. No reload. The working tree may be what
      the running service loads from — ending state is the verifier's call.

ABORT RULES (not negotiable)
  A1. Any tool block or infrastructure error twice → stop, report the exact
      error verbatim, escalate. Two attempts is persistence; three is a loop.
  A2. Test collection error → nothing else exists until it's fixed.
  A3. The diff surprises you → git reset, start from P4.
      You do not negotiate with a diff you didn't intend.
```

---

That's the craft. The harness is not there because the worker is bad; it's there because the worker cannot tell the difference between its good days and its bad ones — and neither, without instruments, can you. Build the gates before the work, read the diffs like they owe you money, label your guesses, attack your own verdicts, and put the answer in the first sentence.

The worker will get better. The manual barely changes. That's how you know it's the right manual.
