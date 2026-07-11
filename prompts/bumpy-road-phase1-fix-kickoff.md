# Kickoff: goethe.py Bumpy Road Phase 1 — FIX session

Paste this as the first message of the LSE fix thread.

---

Independent verification of `refactor/bumpy-road-phase1` returned **FAIL**. Your extractions were structurally correct (verbatim movement confirmed, depths all pass), but the branch has one import regression and misses the line targets. Fix on the SAME branch. Do not merge.

Repo: `~/projects/local-system-engineer` — **use this path in all commands, not `/mnt/c/...`** (same repo via symlink; see Blocked-command rule below).

## Fix 1 — import regression (blocking, do first)

Commit `627d196` added `-> Optional[str]` to `_validate_command_safety`, but goethe.py never imports `Optional` (no `from typing import ...`, no `from __future__ import annotations`). All of `tests/` fails collection with `NameError: name 'Optional' is not defined`. Your "8/8 passing" report was wrong — you tested the stale loaded module, not the branch file.

Add `from typing import Optional` to the module-level imports. One commit. Then run `pytest tests/` and paste the RAW output — collection must pass.

## Fix 2 — close the line-target gaps (AST gate reruns after each)

- `fetch_url`: 148, target < 140. You duplicated `_sanitize` into both `fetch_url` (PDF branch) and `_extract_text_from_html`. Remove the local copy in `fetch_url`: apply one inline `_re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:max_chars]` after the PDF/HTML branch join instead.
- `execute_command`: 360, target < 360 — one line. The 3-line call-site wiring can be 2: `err = self._validate_command_safety(command, cwd)` + `if err: return err` on one conditional, or use `if (err := self._validate_command_safety(command, cwd)):`.
- `verify_source_claims`: 152, target < 145 — remove 8+ lines via one more small verbatim extraction (e.g. the fetch-and-cache block) or equivalent tightening. Propose it in the commit message; behavior-preserving only.

## Fix 3 — BLOCKED-message transparency (new commit)

In `_validate_command_safety`, the privileged-write message must name what matched, so future sessions escalate instead of debugging blind. Replace the write-block return with:

```python
return (
    f"BLOCKED: write targeting a privileged path — matched {_write_to_priv.group(0)!r}. "
    "Use sudo_delegation_block to delegate this to the user, or report a false positive."
)
```

## Rules (additions to the standing rules)

1. After EVERY commit: run `pytest tests/` AND the AST gate; paste raw output, never a summary. Pass criteria: tests collect and pass; execute_command < 360, fetch_url < 140, verify_source_claims < 145; no function deeper than baseline (6/4/5).
2. Do NOT restart the MCP gateway, reload tools, or merge. The working tree is the gateway's live-load source; merge and reload happen only after verification.
3. Blocked commands: the gateway you run under still enforces the OLD pre-`aebaf4b` guard (it blocks any command containing `/mnt/` together with any of `"> "  ">> "  "sed -i"  "rm "  "cp "  "mv "  "tee "  "truncate"`). These are false positives already fixed in git but not yet loaded. Workaround: use `~/projects/local-system-engineer` paths (no `/mnt/` substring) and python heredocs with `open()` for file edits. If a command is still BLOCKED after ONE rephrase, stop — use `sudo_delegation_block` or halt and report. Never spend the session probing the guard.

## Done means

`pytest tests/` green, AST gate green, 2–3 new commits on the branch, branch NOT merged. Hand back for verification.

---

# Operator runbook (Joe — after verification passes)

1. Verifier (Cowork thread) re-checks the branch: verbatim diffs, AST gate, `run_tests(harness)`.
2. Merge: `git checkout master && git merge refactor/bumpy-road-phase1` (working tree must end on master — it's the live-load source).
3. Reload gateway: `bash ~/projects/local-system-engineer/tools/start-goethe.sh` (kills only the `--transport http` instance; stdio bridges for Claude Desktop/Cowork survive but still hold the old code — restart those connections when convenient).
4. Confirm the new guard is live: a command containing `/mnt/` + `> /tmp/x` must now succeed.
5. CodeScene UI re-scan (http://localhost:3004), record Code Health delta for goethe.py.
