---
name: lse-session-debrief
description: >
  Appends a structured learning entry to /opt/local-se/kb/session-learnings.md after
  a session where something non-obvious was discovered or corrected. Trigger when the
  user says "log this session", "debrief", "update the KB", "write up what went wrong",
  or "add that to the KB". Also trigger proactively when a config error, wrong port/path,
  or silent failure was corrected mid-session — especially if it cost significant time.
  Goal: next session starts with hard-won knowledge already grounded, not rediscovered.
---

# LSE Session Debrief

Captures non-obvious learnings and appends them to the session KB so the same
mistakes aren't repeated. The canonical example: `suspended_times` placed under
`outgoing:` (silently ignored) instead of `search:` — diagnosed after an hour of
confusion. That entry now prevents repeating it in future sessions.

## WHAT TO CAPTURE

**Worth capturing:**
- Config key placed in the wrong YAML section (silently ignored by parser)
- Wrong port, path, or key name that looked plausible but was incorrect
- Command or sequence that failed non-obviously, plus the fix
- Correct behaviour that contradicts training knowledge or documentation

**Not worth capturing:**
- Straight-line work with no surprises
- Things already in the KB (read first to check)
- Generic Linux/bash knowledge with no LSE-specific angle

If nothing non-obvious happened, say so. A vague entry ("config was wrong") is
worse than no entry — it wastes future read budget without preventing anything.

## ENTRY FORMAT

```
## Session YYYY-MM-DD — <one-line topic, ≤60 chars>

### What worked
- <reusable pattern or command — concrete enough to copy-paste>

### What failed and why
- **Attempted:** <what was tried>
  **Failed because:** <specific root cause — which key, which section, exact reason>
  **Fix:** <exact command, config change, or correct value>

### Key facts
- <one fact per line: correct path / port / key name / placement rule>
```

Multiple failure/fix pairs allowed. If only a discovery (no failure), omit "What failed"
and use "What worked" + "Key facts" only.

**Example entry:**
```
## Session 2026-05-24 — SearxNG suspended_times placement

### What worked
- Placing `suspended_times` under `search:` with Python exception class name keys

### What failed and why
- **Attempted:** `suspended_times` under `outgoing:` section
  **Failed because:** SearxNG parser silently ignores it outside `search:` — no error, no warning
  **Fix:** Move to `search:` and restart: `cd /home/sy5/searxng-docker && docker compose restart searxng`

### Key facts
- `suspended_times` lives under `search:`, not `outgoing:` or top-level
- Keys are Python exception class names: `SearxEngineTooManyRequests`, `SearxEngineCaptcha`
- NOT string literals like `"HTTP error [429]"` — silently ignored
- Port rule: SearxNG=8088, llama-server=8080. Never swap.
```

## WRITE SEQUENCE

Follow all steps in order. Skipping any step is a protocol violation.

**Step 1 — READ existing KB**
```bash
execute_command("cat /opt/local-se/kb/session-learnings.md 2>/dev/null || echo '(file does not exist yet)'")
```
If today's date + topic already present → skip write (no duplicates).

**Step 2 — DRAFT**
Write the full entry in the chat first. Do not write to disk yet.
The user must be able to read and correct it before it's committed.

**Step 3 — CONFIRM**
Ask exactly: `"Write this entry to /opt/local-se/kb/session-learnings.md? (yes/no)"`
Wait for explicit yes. Do not proceed on ambiguous responses.
Skipping confirmation is a protocol violation.

**Step 4 — WRITE (on yes)**
```bash
execute_command("printf '\\n' >> /opt/local-se/kb/session-learnings.md")
# Then append the entry content with heredoc or cat >>
```
Use `>>` only. NEVER use `>` — that overwrites the entire file.
If file doesn't exist, create with header first:
```bash
execute_command("printf '# LSE Session Learnings\\n\\nCumulative KB entries from post-session debriefs.\\n' > /opt/local-se/kb/session-learnings.md")
```

**Step 5 — VERIFY**
```bash
execute_command("tail -30 /opt/local-se/kb/session-learnings.md")
```
Confirm entry is present and correctly formatted.
Skipping verification is a protocol violation.

## GATE

Trigger on explicit request OR proactively when a non-obvious error was corrected.
Do NOT trigger on routine sessions. Quality over volume.
