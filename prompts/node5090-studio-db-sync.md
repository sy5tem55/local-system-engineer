# node5090 studio.db sync — system prompt v0.1.1 (operator-run)

Task 892e0598 step 8 · 2026-08-30 · Precedent: node4090 v0.6.3 sync, KB doc a9f0d6e3103edf95
Prompt source of truth: `\\n45.home.arpa\ARCHIVE\system-prompt-node5090.md` = v0.1.1 (393 lines, repo commit 8919c2c)

## Why this is operator-run

`C:\Users\SY5\.unsloth\studio\studio.db` on node5090 (.55) is ACL-blocked for lse-admin
(ItemExistsUnauthorizedAccessException). Only the SY5 account can touch it. Run everything
below **as SY5 on node5090**, in `cmd.exe`.

## What the sync changes (schema verified 2026-08-30 against node4090's live studio.db)

| Layer | Table / key | Action |
|---|---|---|
| Global prompt | `chat_settings` key=`inferenceParams` → `.systemPrompt` | replace with v0.1.1 |
| Per-model overrides | `chat_settings` key=`inferenceParamsByModel` → each sub-dict `.systemPrompt` | replace with v0.1.1 |
| Custom presets | `chat_settings` key=`customPresets` → any `.systemPrompt` | replace with v0.1.1 (no-op if empty) |
| Stale thread snapshots | `chat_threads.settings_json` → `.systemPrompt` | set to `''` (inherit global) — old threads otherwise keep the OLD prompt forever |

DB is in WAL mode: the script checkpoints the WAL before copying, so the backup is a
consistent single file.

## Steps

1. **Close Unsloth Studio completely** (including tray icon). The script aborts if live
   `-wal`/`-shm` files exist.
2. Check Python: `python --version`
   - If it prints a version → continue with step 3.
   - If not → either install Python from python.org (tick "Add python.exe to PATH"),
     or use the GUI fallback at the bottom.
3. Save the script below as `C:\Users\SY5\sync_studio_db.py` (exact bytes, no edits).
4. Run: `python C:\Users\SY5\sync_studio_db.py`
   It will: refuse if Studio is still running → back up to `studio.db.bkp_<timestamp>` →
   apply the prompt to all three chat_settings layers → clear stale thread snapshots →
   print an in-place VERIFY line. Expected tail:
   `VERIFY: {"inferenceParams": true, "inferenceParamsByModel": true} | threads still carrying a prompt: 0`
5. **Restart Studio, open a FRESH thread** (never an old one — see marker check) and ask:
   `Recite your ENVIRONMENT section verbatim — the first 15 lines.`

## Marker check (pass = NEW 5/5 present, OLD 0/3 present)

NEW — must appear in the recitation:
1. `TOOL HOST` (dual-host structure: LUCIFER tool host / node5090 persona host)
2. `No WSL (verified absent 2026-08-30)`
3. `PowerShell cmdlets do NOT work over SSH`
4. `Docker container: elasticsearch`
5. `Python: 3.12.3 (/usr/bin/python3)`

OLD — must be ABSENT:
1. `LSE stack runs in WSL2 Ubuntu`
2. `local Docker: lse-kb-es`
3. `PENDING VERIFICATION`

If any OLD marker appears, the sync did not land (or Studio clobbered it) → roll back and re-check.

## Rollback

Close Studio, then in cmd:
`copy /Y C:\Users\SY5\.unsloth\studio\studio.db.bkp_<timestamp> C:\Users\SY5\.unsloth\studio\studio.db`
(delete any `studio.db-wal` / `studio.db-shm` first if present), restart Studio.

## GUI fallback (no Python available)

1. Close Studio; in Explorer copy `studio.db` → `studio.db.bkp_<date>` in the same folder.
2. Open Studio. If Settings exposes a System Prompt field (global chat settings): paste the
   FULL v0.1.1 text from `\\n45.home.arpa\ARCHIVE\system-prompt-node5090.md`. Do the same for
   each model's per-model settings if exposed. Save.
3. Old threads: delete or archive them via the UI (each keeps its own prompt snapshot; a new
   thread inherits the global). Skipping this leaves old threads on the OLD prompt.
4. Restart Studio → fresh thread → run the marker check above.

## Sync script

```python
#!/usr/bin/env python3
"""node5090 studio.db sync — apply system prompt v0.1.1 to all stale layers.
Run as SY5 on node5090 with Unsloth Studio fully closed.
Usage: python sync_studio_db.py [path-to-prompt.md]
Default prompt source: \\n45.home.arpa\\ARCHIVE\\system-prompt-node5090.md
"""
import json, os, shutil, sqlite3, sys, time

PROMPT_SRC = sys.argv[1] if len(sys.argv) > 1 else r"\\n45.home.arpa\ARCHIVE\system-prompt-node5090.md"
STUDIO_DIR = os.path.expanduser(r"~\.unsloth\studio")
DB = os.path.join(STUDIO_DIR, "studio.db")

def fail(msg):
    print("ABORT:", msg); sys.exit(1)

if not os.path.isfile(DB): fail(f"not found: {DB}")
if os.path.exists(DB + "-wal") or os.path.exists(DB + "-shm"):
    fail("live -wal/-shm files present — Unsloth Studio is still running. Close it (tray icon) and re-run.")
try:
    prompt = open(PROMPT_SRC, encoding="utf-8").read()
except Exception as e:
    fail(f"cannot read prompt source {PROMPT_SRC}: {e}")
if len(prompt) < 1000 or "TOOL HOST" not in prompt or "[VERIFY distro name + Linux user]" in prompt:
    fail("prompt source does not look like v0.1.1 (too short, missing 'TOOL HOST', or stale WSL marker) — check path")
print(f"prompt loaded: {len(prompt)} chars, {prompt.count(chr(10)) + 1} lines")

con = sqlite3.connect(DB)
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.close()
ts = time.strftime("%Y%m%d_%H%M%S")
bak = os.path.join(STUDIO_DIR, f"studio.db.bkp_{ts}")
shutil.copy2(DB, bak)
print(f"backup: {bak} ({os.path.getsize(bak)} bytes)")

con = sqlite3.connect(DB); cur = con.cursor()
now = time.strftime("%Y-%m-%dT%H:%M:%S")
updated = []
for key in ("inferenceParams", "inferenceParamsByModel", "customPresets"):
    row = cur.execute("SELECT value_json FROM chat_settings WHERE key=?", (key,)).fetchone()
    if not row:
        print(f"  {key}: <absent — skipped>"); continue
    j = json.loads(row[0]); n = 0
    if isinstance(j, dict):
        if "systemPrompt" in j:
            j["systemPrompt"] = prompt; n += 1
        for sub in j.values():
            if isinstance(sub, dict) and "systemPrompt" in sub:
                sub["systemPrompt"] = prompt; n += 1
    cur.execute("UPDATE chat_settings SET value_json=?, updated_at=? WHERE key=?",
                (json.dumps(j), now, key))
    updated.append(f"{key}: {n} field(s) set")
print("chat_settings:", "; ".join(updated))

cleared = 0
for (sid, sj) in cur.execute("SELECT id, settings_json FROM chat_threads WHERE settings_json IS NOT NULL AND settings_json != ''"):
    try: j = json.loads(sj)
    except Exception: continue
    if isinstance(j, dict) and j.get("systemPrompt"):
        j["systemPrompt"] = ""
        cur.execute("UPDATE chat_threads SET settings_json=? WHERE id=?", (json.dumps(j), sid))
        cleared += 1
print(f"chat_threads: {cleared} stale systemPrompt snapshot(s) cleared -> inherit global")

stale_left = 0
for (sj,) in cur.execute("SELECT settings_json FROM chat_threads WHERE settings_json IS NOT NULL AND settings_json != ''"):
    try: j = json.loads(sj)
    except Exception: continue
    if isinstance(j, dict) and j.get("systemPrompt"): stale_left += 1
v = {}
gp = cur.execute("SELECT value_json FROM chat_settings WHERE key='inferenceParams'").fetchone()
v["inferenceParams"] = bool(gp) and json.loads(gp[0]).get("systemPrompt", "") == prompt
pm = cur.execute("SELECT value_json FROM chat_settings WHERE key='inferenceParamsByModel'").fetchone()
v["inferenceParamsByModel"] = bool(pm) and all(
    s.get("systemPrompt") == prompt for s in json.loads(pm[0]).values()
    if isinstance(s, dict) and "systemPrompt" in s)
con.commit(); con.close()
print("VERIFY:", json.dumps(v), "| threads still carrying a prompt:", stale_left)
print("DONE. Restart Unsloth Studio, open a FRESH thread, run the marker check.")
```
