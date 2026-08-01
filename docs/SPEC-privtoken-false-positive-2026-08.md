# SPEC — stop the privilege-token gate firing on identifiers

> Design: Opus 5, 2026-08-01. Implementation: Sonnet 5.
> Source of truth is the WSL tree at `/home/sy5/projects/local-system-engineer`.
> Read §3 before designing. The obvious fix reopens a security hole this
> project deliberately closed on 2026-07-31.

---

## 1. The bug

`_PRIVILEGED_TOKEN_RE` (`tools/goethe.py:618`) is
`r"\b(?:sudo|doas|su)\b"`, matched against the whole command string. It
therefore fires when the word appears as **data** rather than as a command.

Measured 2026-08-01 — four separate blocks in one session, all read-only:

```
git log origin/codex/fix-sudo-grants-live..HEAD     → BLOCKED
git status ... (branch named in the command)        → BLOCKED
grep -n "sudo" tools/goethe.py                      → BLOCKED
git rev-list --count origin/<that branch>..HEAD     → BLOCKED
```

The branch `codex/fix-sudo-grants-live` contains `sudo` between two
hyphens, and `\b` treats `-` as a word boundary. So does `/`. An agent
cannot run read-only git commands naming that branch, and cannot grep for
the string at all.

Operational cost: every affected command needs a workaround
(`git log '@{u}..HEAD'`, `grep 's[u]do'`), which is discoverable only by
hitting the wall first.

---

## 2. Ground truth (verify, don't trust)

Read from the live tree 2026-08-01. Re-check anything you depend on.

| Fact | Value |
|---|---|
| File | `tools/goethe.py` |
| The regex | `_PRIVILEGED_TOKEN_RE`, line 618 |
| Older literal list | `_PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")`, line 420 |
| Block site | ~line 772–786, two messages: `'…' detected in command` and `'…' detected in a chained or complex command` |
| Whitespace normalizer | `_normalize_for_scan()`, line 622 |
| Regression suite | `tests/test_safety_gates_adversarial.py` — **21 tests** |
| Full suite baseline | 614 passed (2026-08-01, after `f9379c1`) |

---

## 3. The hazard — why the obvious fix is wrong

The wide word-boundary match is **not an accident**. It was introduced
deliberately on 2026-07-31 as a D5 fix, and the comment at line 611 says why:

> *"privilege tokens matched on WORD BOUNDARIES rather than the old literal
> `"sudo "` / `"su "` / `"doas "` substrings, which required a trailing space
> and so missed every form where sudo is reconstructed or terminal:
> `S=sudo; $S id`, `$(echo sudo) id`, `echo id | xargs sudo`."*

So the tempting fix — "only match at command position" — **reopens all three
of those bypasses**. `S=sudo` has the token at assignment position, not
command position. That regression would be silent: the gate would still exist,
still look correct, and no longer stop a privilege escalation.

**Do not narrow to command position. Do not revert to the literal prefixes.**

---

## 4. What to implement

A **narrow exemption**, not a narrower match.

Keep `\b(?:sudo|doas|su)\b` as the detector. Add one rule: a match is
**exempt** when the token is embedded inside a longer identifier — that is,
when the character immediately before or after the match is one of:

```
-  /  _  .
```

Rationale: those characters make the token part of a path, branch name,
filename or hyphenated identifier. They cannot make it executable on their
own. `sudo` at the start of a command, after `;`/`|`/`&&`/newline, or after
`=`/`$(`/backtick is untouched by this rule and stays blocked.

Worked examples — all must hold:

| Command fragment | Outcome |
|---|---|
| `sudo id` | BLOCKED (unchanged) |
| `S=sudo; $S id` | BLOCKED — preceded by `=`, not in the exempt set |
| `$(echo sudo) id` | BLOCKED — preceded by space |
| `echo id \| xargs sudo` | BLOCKED — preceded by space |
| `codex/fix-sudo-grants-live` | exempt — `-` on both sides |
| `/etc/sudoers` | exempt — `/` before, and `sudo` is inside `sudoers` anyway |
| `goethe-perm sync-sudoers` | exempt |
| `grep sudo file.py` | **still BLOCKED** — see §5 |

### 4.1 Known limitation to document, not fix

A bare `grep sudo <file>` stays blocked: the token is space-delimited and
indistinguishable, without shell parsing, from an attempt to run it. Full
resolution needs real tokenization with quote-context tracking, which is a
much larger change and out of scope here.

Document the workaround in the code comment and the block message is *not*
required to change — but if you touch the message, mention that a
character-class pattern (`grep 's[u]do'`) avoids the gate for genuine
searches.

Do **not** attempt shell parsing in this task.

---

## 5. Tests

Extend `tests/test_safety_gates_adversarial.py` (do not create a new file —
this belongs with its siblings).

Add, at minimum:

1. **All four real-world false positives now pass.** The exact commands from
   §1, asserted to be allowed.
2. **Every D5 bypass still blocked** — `S=sudo; $S id`,
   `$(echo sudo) id`, `echo id | xargs sudo`, plain `sudo id`, and the
   whitespace-padded variants. Several of these already exist in the suite;
   assert them explicitly here too so the intent is local and visible.
3. **Adjacent-character matrix.** For each of `-`, `/`, `_`, `.` before and
   after: exempt. For each of ` `, `=`, `;`, `|`, `&`, `` ` ``, `(`, newline,
   and start-of-string: blocked.
4. **`su` and `doas` behave identically** — the rule must not be sudo-only.
5. **`/etc/sudoers` paths still reach the privileged-write block.** Writing to
   `/etc/sudoers` must remain blocked by the `_PRIVILEGED_WRITE_PATHS` logic;
   confirm this exemption did not accidentally open a write path. This is the
   one place where the two mechanisms interact.

**Prove the guards fail before trusting them to pass.** Break the exemption
(make it always-exempt) and confirm the §5.2 bypass tests go red. Then break
it the other way (remove the exemption) and confirm the §5.1 tests go red.
Report both observations. An exemption that has never been seen to
over-permit has not been shown to be narrow.

---

## 6. Invariants

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/goethe.py
/home/sy5/miniforge3/bin/ruff check tools/goethe.py
```

Full suite, backgrounded (it outlives the MCP request timeout):

```bash
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
# poll /tmp/pt.log in separate calls
```

Baseline **614 passed**. Record the ruff finding count on `goethe.py`
before and after; it must not increase.

Then prove the fix in the **live gateway**, not only in tests: the running
Goethe process loads `goethe.py` from disk, so after the operator restarts it,
a real `git log origin/codex/fix-sudo-grants-live..HEAD` through
`execute_command` should succeed. Note in the report whether you observed this
or whether it remains test-only.

---

## 7. Anti-goals

- Do **not** narrow `_PRIVILEGED_TOKEN_RE` to command position.
- Do **not** restore `_PRIVILEGED_PREFIXES` as the detector.
- Do **not** implement shell tokenization or quote tracking.
- Do **not** touch `_PRIVILEGED_WRITE_PATHS`, `_BLOCKED_COMMAND_NAMES`, or
  `rm -rf` handling.
- Do **not** relax anything to make a test pass. If the exemption cannot be
  made narrow enough, say so and stop — a slightly annoying gate is much better
  than a quietly permissive one.

---

## 8. Report

Write `/tmp/privtoken-fix-report.md`:

- What changed; before/after ruff and test counts.
- The break-and-restore results for both directions (§5).
- Whether the live-gateway check in §6 was performed or is outstanding.
- Anything in §2's ground-truth table that turned out to be wrong.

---

## 9. Housekeeping

- `tools/goethe.py` **is** one of the seven modules watched by
  `scripts/check_goethe_mirror_sync.sh`. Run it and copy the file to
  `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/`.
- Commit on `codex/fix-sudo-grants-live`. Do not `git push`.
- Naming that branch in a shell command trips the very bug you are fixing.
  Until the fix is live, use `git log '@{u}..HEAD'` — note the branch has **no
  upstream configured**, so that form errors with "no upstream"; use
  `git rev-list --count "origin/$(git rev-parse --abbrev-ref HEAD)..HEAD"`,
  which builds the name without writing it literally.

---

## 10. Context

- Where this sits: `docs/ROADMAP-2026-08.md` §1.
- Why the wide match exists: `docs/REFACTOR-REPORT-D1-D8-2026-07-31.md`
  (D5 bypass closure) and the comment at `tools/goethe.py:611`.
- Handover conventions: `docs/WORKFLOW-thread-handover.md`.
