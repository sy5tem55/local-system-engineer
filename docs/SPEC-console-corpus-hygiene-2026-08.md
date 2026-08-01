# SPEC — corpus hygiene as a Console operation

> Design: Opus 5, 2026-08-01. Implementation: Sonnet 5.
> Source of truth is the WSL tree at `/home/sy5/projects/local-system-engineer`.
> Read §3 before designing. This adds a **destructive-looking** operation to a
> Console that has, until now, deliberately had only two write surfaces.

---

## 1. Why

On 2026-07-31 the `error-cluster` pass produced a false positive built from 67
synthetic episode files that a test had written into the live corpus. Removing
them took a manual shell session: identify, verify none were mixed with real
calls, move to quarantine, rebuild the manifest, then delete 67 orphaned
manifest rows by hand because `build_manifest()` did not prune.

That is now half-solved: `f9379c1` added `build_manifest(..., prune=True)`,
verified safe. The remaining half is that an operator cannot do any of it from
the Console, and the operation is exactly the kind that should never be
improvised at a shell prompt at midnight.

Full background: `docs/TRAUM-R1-R3-REPORT.md` § *Corpus hygiene performed*.

---

## 2. Ground truth (verify, don't trust)

Read from the live tree 2026-08-01. Re-check anything you depend on.

| Fact | Value |
|---|---|
| Console router | `tools/goethe_ui.py` |
| Read panels registry | `_PANELS`, line 643 — already contains `/api/ui/episodes` → `episode_stats()` |
| Existing episodes panel | `episode_stats()`, line 551 |
| Write-surface precedent | `_perm_action()`, line 659 — "one of the two deliberate write surfaces" |
| POST route precedent | `/api/ui/traum/runs`, line 1066 |
| Auth | every `/api/ui/*` route is behind the same bearer token; see `_authorized()` |
| Pruning API | `episode_index.build_manifest(episode_dir, manifest_db, dry_run=False, verbose=False, prune=False)` |
| Episode root | `_episode_dir()` in `goethe_ui.py`; live value `/opt/local-se/episodes` |
| Manifest | `/opt/local-se/episodes/manifest.db`, table `sessions` |
| Prior quarantine dir | `/opt/local-se/episodes-quarantine-method_raises-20260801/` (67 files + `MOVED-FILES.txt`) |
| Live corpus | ~516 session files, 499 manifest rows |
| Suite baseline | 718 passed (2026-08-01, after `4ef18c7`) |

---

## 3. Hazards — read before designing

### Hazard A — the corpus is the system's memory, and there is no snapshot

There is no backup mechanism for `/opt/local-se/episodes`. A wrong purge is
unrecoverable. Therefore:

**Never delete. Always move.** The operation quarantines files into a
timestamped sibling directory with a manifest of what moved, exactly as the
manual purge did. `rm` must not appear anywhere in this feature. Deletion of a
quarantine directory stays a human action at a shell.

### Hazard B — a pattern is not a selection

The manual purge selected by content (`"tool": "method_raises"`). Exposing a
free-text pattern as the purge input means a typo — or a pattern that matches
more than the operator expects — silently destroys history.

**Two-step, and the destructive step takes explicit IDs, never a pattern.**
Preview accepts a selector and returns the exact session list. Purge accepts
*that list of session_ids* and refuses anything not currently matching. An
operator who previews 67 and purges 67 IDs cannot accidentally purge 5,000.

### Hazard C — mixed files

Every one of the 67 was a single-line synthetic session, entirely
contaminated. That will not always hold. A session file containing **both**
the offending tool and real operational calls must never be moved wholesale —
that destroys real history to remove a synthetic line.

Preview must classify each candidate as `entirely-matching` or `mixed`, and
**purge must refuse to move `mixed` files**, reporting them for manual
handling. Line-level surgery inside a session file is out of scope.

### Hazard D — `dreamed_at`

Covered by `f9379c1`, but relevant here: purge must call
`build_manifest(..., prune=True)` afterwards, not a bare rebuild, or the
manifest keeps ghost rows. Surviving sessions must retain `dreamed_at`; the
pruning implementation already guarantees this, so **do not reimplement
pruning** — call it.

---

## 4. What to implement

### 4.1 Preview — read-only

```
GET /api/ui/episodes/purge-preview?tool=<name>
```

- Scans the corpus for session files containing `"tool": "<name>"`.
- Returns per file: `session_id`, `day`, `matching_lines`, `total_lines`,
  `classification` ("entire" | "mixed"), and whether the manifest has a row.
- Returns totals, and a `purgeable_session_ids` list containing **only** the
  `entire` ones.
- Side-effect free. Changes nothing. Safe to call repeatedly.
- Cap the response (e.g. 500 files) and report truncation rather than
  streaming the whole corpus into a web response.

The `tool` parameter is a selector for *preview only*. It never reaches the
purge step.

### 4.2 Purge — the write surface

```
POST /api/ui/episodes/purge
body: {"session_ids": [...], "reason": "<operator text>"}
```

- Rejects an empty list, and any `session_id` failing a strict id pattern.
- Re-verifies each id at execution time: the file must still exist, still
  match, and still be `entire`. Anything that changed since preview is
  **skipped and reported**, not moved.
- Moves each file to
  `/opt/local-se/episodes-quarantine-<slug>-<UTC timestamp>/<day>/<file>`,
  preserving the day-dir structure, and writes `MOVED-FILES.txt` plus the
  operator's `reason`.
- Then calls `build_manifest(episode_dir, manifest_db, prune=True)`.
- Returns: moved count, skipped list with per-item reason, quarantine path,
  and the manifest row count before/after.
- `reason` is required and non-empty. It goes in the quarantine manifest and
  the log line.

### 4.3 Console UI

Extend the existing Episodes panel. Minimum viable, in the idiom of the
existing panels:

- An input for the tool selector and a **Preview** button.
- A table of what would be purged, with `mixed` rows visually distinct and
  clearly marked *not purgeable here*.
- A **Purge** button, disabled until a preview has run, that sends the
  previewed `purgeable_session_ids`.
- A required reason field.
- Plain-language result: "moved N files to <path>; manifest 499 → 432".

Reuse existing `.chip` / `.dot` / `.abtn` classes. No new CSS framework.

---

## 5. Anti-goals

- Do **not** delete anything, ever. No `rm`, no `unlink`, no `shutil.rmtree`.
- Do **not** accept a pattern on the POST route.
- Do **not** do line-level editing inside session files.
- Do **not** reimplement manifest pruning — call `build_manifest(prune=True)`.
- Do **not** touch `_perm_action` or the permissions plane. These are separate
  control planes and the existing separation notice in the TRAUM panel applies.
- Do **not** expose a purge path outside `_episode_dir()`. Every resolved path
  must be verified to be inside it after `os.path.realpath`.
- Do **not** widen the auth model. Same bearer token, same gate.

---

## 6. Tests

New file `tests/test_episode_purge.py`. At minimum:

1. **Preview is side-effect free** — corpus and manifest byte-identical after.
2. **Mixed files are classified and excluded** from `purgeable_session_ids`.
3. **Purge refuses a mixed id** even if passed explicitly. Load-bearing:
   this is Hazard C.
4. **Purge moves, never deletes** — asserts the file exists at the quarantine
   path afterwards.
5. **Path traversal is rejected** — a `session_id` like `../../etc/passwd` or
   an absolute path is refused. Load-bearing: Hazard A.
6. **Re-verification catches drift** — preview, then mutate a file so it no
   longer matches, then purge: that id is skipped and reported, not moved.
7. **Manifest is pruned after purge** — no orphan rows remain, and a surviving
   session's `dreamed_at` is unchanged. Ties to Hazard D.
8. **Empty list and missing reason are rejected.**

**Prove the guards fail before trusting them to pass.** For tests 3 and 5,
disable the check, confirm red, restore. Report what you saw.

---

## 7. Invariants

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/goethe_ui.py tools/episode_index.py
/home/sy5/miniforge3/bin/ruff check tools/goethe_ui.py
```

Dashboard JS must parse:

```bash
python3 -c "import re;h=open('tools/goethe_dashboard.html').read();open('/tmp/d.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))"
node --check /tmp/d.js
```

Full suite backgrounded (it outlives the MCP request timeout):

```bash
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
```

Baseline **718 passed**. Record ruff counts before/after; must not increase.

**Never run purge against `/opt/local-se/episodes` as a test.** Use `tmp_path`.
If you want a realistic fixture, copy
`/opt/local-se/episodes-quarantine-method_raises-20260801/` — copy it, do not
consume it.

---

## 8. Report

Write `/tmp/corpus-hygiene-report.md`: what changed, before/after ruff and test
counts, the break-and-restore results for tests 3 and 5, whether the Console UI
was exercised against a running gateway or is test-only, and anything in §2's
ground-truth table that turned out wrong.

---

## 9. Housekeeping

- `tools/goethe_ui.py` and `tools/goethe_dashboard.html` are **not** among the
  seven modules watched by `scripts/check_goethe_mirror_sync.sh`, but the mirror
  is a full repo copy — copy both to
  `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/`.
- Commit on `codex/fix-sudo-grants-live`. Do not `git push`.
- Console changes need an operator restart of Goethe to take effect; the
  running process holds the old module in memory. Say so in the report rather
  than assuming the operator knows.

---

## 10. Context

- Roadmap position: `docs/ROADMAP-2026-08.md` §1.
- Why this exists: `docs/TRAUM-R1-R3-REPORT.md` § *Corpus hygiene performed*.
- The pruning API this builds on: `docs/SPEC-manifest-prune-2026-08.md`.
- Handover conventions: `docs/WORKFLOW-thread-handover.md`.
