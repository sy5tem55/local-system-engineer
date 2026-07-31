# Tech Debt Audit D1 — Divergent Copies of the Core

**Date:** 2026-07-31  
**Score:** 36 (Impact 4 × Risk 5 × (6 − Effort 2))  
**Status:** RESOLVED

---

## Canonical Source

**tools/goethe.py** is the single, authoritative copy of the Goethe Tools class.

- Imported by `tools/goethe_mcp.py` via `--goethe` CLI argument (loaded with `importlib.util.spec_from_file_location`).
- Live startup: `tools/start-goethe.sh` line 71: `--goethe "$LSE_DIR/goethe.py"` where `LSE_DIR=~/projects/local-system-engineer/tools`.
- Actively maintained: recent git commits confirm this is the live development target.

No other copy of goethe.py should be considered authoritative.

---

## lse/goethe/ Fork — REMOVED

`lse/goethe/` was a stale fork of the core, not a backup:

- **Similarity:** 83.8% to tools/goethe.py
- **Size:** 5,022 lines vs 7,026 lines in the live copy
- **Unique code:** 22 methods existed only in lse/goethe/goethe.py (hermes_plan, _embed, _es, _pfsense_verify, etc.) — all legacy, none referenced by any live code in the repo.
- **References:** Zero imports or script invocations of lse/goethe/goethe.py anywhere in the codebase.
- **Resolution:** Directory removed 2026-07-31. Filesystem backup preserved at `/home/sy5/tda_d1_backups/lse_goethe_20260731_020702/`.
- **Commit:** a276dad

---

## .backups/ Archive — RETAINED

`.backups/` is an **intentional version archive**, not clutter. Contains historical goethe.py snapshots:

| File | mtime | size | lines |
|---|---|---|---|
| `.backups/pre-pfsense-confirmation-gate-20260706/goethe-v0.3.8.py` | 2026-07-06 | 368 KB | 7,277 |
| `.backups/pre-purge-20260702/goethe-v0.2.1.py` | 2026-06-25 | 248 KB | 5,022 |
| `.backups/pre-purge-20260702/goethe-v0.2.2.py` | 2026-06-26 | 255 KB | 5,126 |

Also contains other historical snapshots (pre-1.6.2-removal, pre-purge-*). The directory is git-ignored (`.backups/` in `.gitignore`) and should be left as-is.

---

## .bak_ Policy

Manual `.bak_*` files are **discouraged**. Use git instead:

- `.gitignore` rules (added 2026-07-31):
  - `.bak_*`
  - `*.bak_*`
  - `*.bak`
- For temporary work: `git stash`
- For preserving versions: `git commit` or `git tag`
- For rollback: `git restore` or `git checkout <commit>`

**Cleanup performed:** 22 untracked `.bak_*` files removed from the working tree (outside `.backups/`). Filesystem backup at `/home/sy5/tda_d1_backups/bak_files_20260731_021124/`.

Commit: ad09681 (cleanup), b255db0 (policy)

---

## Windows Mirror Sync-Check

The Windows-side mirror at `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/` is known to lag the live WSL repo.

**Sync-check script:** `scripts/check_goethe_mirror_sync.sh`

- Compares sha256 of live `tools/goethe.py` against the mirror copy.
- Prints `IN SYNC` (exit 0) or `STALE` with dates and delta (exit 1).
- **Current status:** STALE — mirror is behind by several days.

**Optional weekly crontab entry** (Monday 9am):

```
0 9 * * 1 bash /home/sy5/projects/local-system-engineer/scripts/check_goethe_mirror_sync.sh
```

Commit: e1ed254

---

## Summary of Changes

| Item | Action | Commit |
|---|---|---|
| lse/goethe/ fork | Removed | a276dad |
| .bak_* files | Cleaned (22 removed) | ad09681 |
| .gitignore policy | Added .bak_ rules | b255db0 |
| README.md | Added D1 Audit section | b255db0 |
| Sync-check script | Created | e1ed254 |
| This document | Created | (this commit) |
