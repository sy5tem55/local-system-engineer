# SPEC — prune orphaned rows from `manifest.db`

> Design: Opus 5, 2026-08-01. Implementation: Sonnet 5.
> Source of truth is the WSL tree at `/home/sy5/projects/local-system-engineer`.
> Read this whole document before writing code. The two hazards in §3 are the
> reason this task is not as small as it looks.

---

## 1. The bug

`episode_index.build_manifest()` (`tools/episode_index.py:233`) scans every
session file under `episode_dir` and upserts a row per file. It **never
deletes rows whose backing file no longer exists.**

Measured 2026-08-01: after removing 67 contaminated episode files from
`/opt/local-se/episodes`, a full `build_manifest()` rebuild still reported
566 sessions, all 67 ghost rows intact and still citing the removed tool.
The orphans had to be deleted by hand.

Consequence: any corpus deletion silently leaves the manifest wrong, and
every downstream consumer — `dream_runner`'s session selection, the
quiet-period guard, `dream_digest`'s counts — keeps seeing sessions that
do not exist.

---

## 2. Ground truth (verify, don't trust)

Confirmed by reading the live tree 2026-08-01. Re-check anything you depend on.

| Fact | Value |
|---|---|
| File | `tools/episode_index.py` |
| Function to change | `build_manifest()`, line 233 |
| Row writer | `upsert_session()`, line 212 |
| Session file discovery | `iter_session_files()`, line 185 — matches `.jsonl` **and** `.jsonl.gz` |
| `session_id` source | parsed from the **filename** via `SESSION_FILE_RE` (`parse_session_file`, line 103) |
| Schema | `sessions(session_id PK, start_ts, end_ts, n_calls, n_errors, tools_used, bytes, dreamed_at)` |
| `dreamed_at` writer | `dream_apply.py` only — never `episode_index` |
| Rotation | `rotate_old_sessions()` gzips **in place** (`x.jsonl` → `x.jsonl.gz`) in the same day dir; it does not move files out of the corpus |
| Live corpus now | 514 files / 499 manifest rows |
| Test files touching this module | `tests/test_dream_guards.py`, `tests/test_dream_crash_discipline.py` |

There is currently **no dedicated test file for `episode_index`**. Create
`tests/test_episode_index_prune.py`.

---

## 3. The two hazards — read before designing

### Hazard A — `dreamed_at` is how the dreamer avoids re-work

`dream_runner` selects work with `WHERE dreamed_at IS NULL`
(`dream_runner.py:739`). `upsert_session()` already protects this on the
*insert* path — it deliberately writes `NULL` on insert but does **not**
overwrite `dreamed_at` on conflict, and its docstring says why:

> *"A re-scan (e.g. a session file that grew since the last run) must never
> silently reset a session back to 'undreamed'."*

Your prune must extend that same guarantee to the *delete* path. If a row is
deleted and the same `session_id` is later re-inserted by a subsequent scan,
`dreamed_at` comes back NULL and **the dreamer silently re-analyses content it
already consumed** — duplicate proposals, wasted budget, no error anywhere.

### Hazard B — a partial scan must never trigger a prune

The naive implementation is "delete every row whose `session_id` was not seen
in this scan". That is wrong. If `iter_day_dirs`/`iter_session_files` raises
partway, or a day dir is briefly unreadable (permissions, a mount hiccup, an
in-flight rotation), the unseen set balloons and the prune destroys legitimate
history — including `dreamed_at` state that cannot be reconstructed.

Combined, A and B are the real failure: a transient read problem deletes rows,
the next successful scan re-adds them as undreamed, and the dreamer silently
re-processes weeks of corpus with no signal that anything went wrong.

---

## 4. What to implement

Add pruning to `build_manifest()`, **off by default**.

### 4.1 Signature

```python
def build_manifest(episode_dir: str, manifest_db: str, dry_run: bool = False,
                   verbose: bool = False, prune: bool = False) -> dict:
```

`prune=False` must leave today's behaviour byte-for-byte identical. Existing
callers are not to be changed in this task.

### 4.2 Rules

1. **Only prune after a provably complete scan.** Track completion explicitly.
   If any exception escapes the scan loop, or `stats["day_dirs"] == 0`, skip
   pruning entirely and report it. Do not prune on an empty corpus.
2. **Delete by explicit orphan check, not set-difference.** For each candidate
   row, confirm no backing file exists for that `session_id` in any day dir
   (both `.jsonl` and `.jsonl.gz`) before deleting it. Set-difference against
   the scan is exactly the Hazard B shape.
3. **Never delete a row that survives.** Do not implement this as
   delete-all-then-reinsert. Surviving rows keep their existing `dreamed_at`
   untouched, via the existing `upsert_session()` path.
4. **Honour `dry_run`.** With `dry_run=True`, report what would be pruned and
   change nothing.
5. **Report it.** Add to the returned stats dict:
   `pruned` (int), `prune_skipped_reason` (str|None). A caller must be able to
   tell "pruned 0 because nothing was orphaned" from "did not prune because the
   scan was incomplete".

### 4.3 Anti-goals

- Do **not** change `upsert_session()`. It is already correct.
- Do **not** change `rotate_old_sessions()`.
- Do **not** make `prune=True` the default, and do not wire it into
  `dream_runner`'s guard-time refresh call
  (`_recent_session_active` → `build_manifest`). That call runs on every
  scheduled pass; giving it delete authority is out of scope and risky.
- Do **not** add a CLI flag or Console button in this task.

---

## 5. Tests — `tests/test_episode_index_prune.py`

Cover at minimum:

1. **Default is inert.** `prune=False` (and the current 4-arg call shape)
   leaves orphaned rows in place. Pins backwards compatibility.
2. **Orphans are removed.** Two session files, both indexed; delete one file
   from disk; `build_manifest(prune=True)` removes exactly that row and leaves
   the other.
3. **`dreamed_at` survives a prune — the load-bearing test.** Seed two
   sessions, set `dreamed_at` on the survivor, delete the *other* file, prune,
   and assert the survivor's `dreamed_at` is byte-identical afterwards. This is
   Hazard A. Write it first.
4. **Gzipped files are not treated as orphans.** Index a session, rename its
   file `x.jsonl` → `x.jsonl.gz` (what `rotate_old_sessions` does), prune, and
   assert the row survives. A prune that deletes rotated sessions would silently
   delete the oldest history first.
5. **Incomplete scan does not prune.** Simulate a scan failure (monkeypatch
   `iter_day_dirs` or `iter_session_files` to raise) and assert nothing is
   deleted and `prune_skipped_reason` is set. This is Hazard B.
6. **Empty corpus does not prune.** Point at a directory with no day dirs and
   assert the manifest is untouched.

**Prove the guards fail before trusting them to pass.** For tests 3 and 5,
temporarily break the protection, confirm the test goes red, then restore. Say
in the final report that you did this and what you saw. A test that has never
failed has not been shown to test anything.

---

## 6. Invariants — run after each step

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/episode_index.py
/home/sy5/miniforge3/bin/ruff check tools/episode_index.py
/home/sy5/owui/bin/python3 -m pytest tests/ -q      # 603 passed as of 2026-08-01
```

`ruff` lives at `/home/sy5/miniforge3/bin/ruff`. It is **not** in the owui
venv — `/home/sy5/owui/bin/python3 -m ruff` fails with "No module named ruff",
so a report claiming a clean run from that interpreter did not make one.

The finding count on `episode_index.py` must not increase. Record the
before/after numbers rather than asserting "clean".

**Long commands:** `pytest tests/` exceeds the MCP request timeout and dies
with `MCP error -32001`. Run it as
`nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown`
and poll `/tmp/pt.log` in separate calls.

---

## 7. Verification against reality

Do **not** run `prune=True` against `/opt/local-se/episodes` as a test. Verify
on a `tmp_path` copy. The live corpus is the system's memory and there is no
snapshot mechanism.

When the tests are green, demonstrate on a throwaway copy:

```bash
cp -r /opt/local-se/episodes /tmp/episodes-prune-check
# delete one known file from the copy, then run build_manifest(prune=True)
# against /tmp/episodes-prune-check with its own manifest.db
```

Report: rows before, rows after, `pruned` count, and confirmation that a
session with `dreamed_at` set retained it.

---

## 8. Report

Write `/tmp/manifest-prune-report.md` stating plainly:

- What changed, and the before/after ruff + test counts.
- Which claims are backed by a **runtime** observation versus by test only.
- The result of deliberately breaking tests 3 and 5 to confirm they fail.
- Anything in §2's ground-truth table you found to be wrong. That table was
  compiled by reading the code, not by running it; if it misled you, say so
  explicitly rather than quietly working around it.

---

## 9. Housekeeping

- `tools/episode_index.py` is **not** one of the seven modules watched by
  `scripts/check_goethe_mirror_sync.sh`, so no mirror step is required for it.
  If you touch anything under `tools/goethe*.py`, run that script and copy the
  file to `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/` as well.
- Commit on `codex/fix-sudo-grants-live`. Do not `git push` — the operator does
  that. Note that naming the branch inside a shell command trips the safety
  gate's `sudo` substring match; use `git log '@{u}..HEAD'` instead.

---

## 10. Context you may want

- Why this bug was found: `docs/TRAUM-R1-R3-REPORT.md` § *Corpus hygiene*.
- Where it sits in priority: `docs/ROADMAP-2026-08.md` §1.
- The purge that exposed it moved 67 files to
  `/opt/local-se/episodes-quarantine-method_raises-20260801/` — a useful
  realistic fixture if you want one, but copy it, do not consume it.
