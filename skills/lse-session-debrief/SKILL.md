---
name: lse-session-debrief
description: >
  Writes a structured learning entry to /opt/local-se/kb/session-learnings.md
  at the end of a session where something non-obvious was discovered or corrected.
  Use when the user says "log this session", "update the KB with what we learned",
  "write up what went wrong", "debrief", or "add that to the KB". Also use
  proactively when a config error, silent failure, or wrong path/port was
  corrected mid-session — especially if hours were spent on it. The goal is that
  the next session starts with hard-won knowledge already grounded, not rediscovered.
---

# LSE Session Debrief

Captures non-obvious learnings and appends them to the session KB so the LSE
doesn't repeat the same mistakes in future sessions. The SearxNG `suspended_times`
placement mistake — silently ignored when placed under `outgoing:` instead of
`search:` — is the canonical example of what this skill exists to prevent repeating.

---

## WHAT TO CAPTURE

Capture only things that are non-obvious and would prevent a future mistake.

**Worth capturing:**
- Config key placed in the wrong section (silently ignored by the parser)
- Wrong path, port, or key name that looked plausible but was incorrect
- A command or sequence that failed in a non-obvious way, and the fix
- A correct behaviour that contradicts what you'd assume from documentation or training

**Not worth capturing:**
- Straight-line work that succeeded without surprises
- Things already in the KB (`read_file /opt/local-se/kb/` to check before writing)
- Generic Linux/bash knowledge with no LSE-specific angle

If nothing non-obvious happened, say so — do not write an empty or vague entry.
A vague entry ("config was wrong") is worse than no entry — it wastes future read budget
without preventing anything.

---

## ENTRY FORMAT

Every entry must follow this structure exactly:

```
## Session YYYY-MM-DD — <one-line topic, ≤60 chars>

### What worked
- <reusable pattern or command — concrete enough to copy-paste>

### What failed and why
- **Attempted:** <what was tried>
  **Failed because:** <specific root cause — not "config was wrong" but which key, which section, why>
  **Fix:** <exact command, config change, or correct value>

### Key facts
- <one fact per line: correct path / port / key name / placement rule>
```

Multiple failure/fix pairs are allowed under "What failed and why" — one block per failure.
If a session had only a discovery with no failure (e.g. learning a new correct path),
omit "What failed and why" and use "What worked" + "Key facts" only.

**Example entry (the SearxNG incident):**

```
## Session 2026-05-24 — SearxNG suspended_times placement

### What worked
- Placing `suspended_times` under `search:` with Python exception class name keys

### What failed and why
- **Attempted:** `suspended_times` under `outgoing:` section
  **Failed because:** SearxNG parser silently ignores `suspended_times` outside `search:` — no error, no warning, just no effect
  **Fix:** Move the block to `search:` in settings.yml and restart: `cd /home/sy5/searxng-docker && docker compose restart searxng`

### Key facts
- `suspended_times` lives under `search:`, not `outgoing:` or top-level
- Keys are Python exception class names: `SearxEngineTooManyRequests`, `SearxEngineCaptcha`, etc.
- Not string literals like `"HTTP error [429]"` — those are silently ignored
- SearxNG port: 8088. llama-server port: 8080. Never swap them.
- Verify after restart: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/` → 200
```

---

## WRITE SEQUENCE

Follow these steps in order. Skipping any step is a protocol violation.

**Step 1 — READ existing KB**
```
execute_command("cat /opt/local-se/kb/session-learnings.md 2>/dev/null || echo '(file does not exist yet)'")
```
Check: is an entry for today's date + topic already present? If yes, skip writing (no duplicates).

**Step 2 — DRAFT the entry**
Write the full entry in the chat using the format above. Do not write to disk yet.
The user must be able to read and correct it before it's committed.

**Step 3 — CONFIRM**
Ask exactly: "Write this entry to `/opt/local-se/kb/session-learnings.md`? (yes/no)"
Wait for an explicit yes. Do not proceed on ambiguous responses.
Skipping confirmation is a protocol violation.

**Step 4 — WRITE**
On confirmation, append the entry:
```
execute_command("printf '\n' >> /opt/local-se/kb/session-learnings.md && cat >> /opt/local-se/kb/session-learnings.md << 'DEBRIEF_EOF'\n<entry text>\nDEBRIEF_EOF")
```
Use `>>` to append. Never use `>` — that overwrites the entire file.
If the file doesn't exist yet, create it first with a header:
```
execute_command("echo '# LSE Session Learnings\n\nCumulative KB entries from post-session debriefs.\n' > /opt/local-se/kb/session-learnings.md")
```

**Step 5 — VERIFY**
```
execute_command("tail -30 /opt/local-se/kb/session-learnings.md")
```
Confirm the entry is present and correctly formatted.
Skipping verification is a protocol violation.

---

## GATE

Trigger on:
- Explicit user request ("log this", "debrief", "add that to the KB")
- Any session where a non-obvious config error, silent failure, or wrong assumption was corrected

Do NOT trigger on routine sessions where everything worked as expected.
Do NOT write an entry just to fill the KB — quality over volume.
