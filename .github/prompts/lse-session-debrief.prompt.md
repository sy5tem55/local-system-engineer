---
mode: 'agent'
description: 'Log a session learning to the KB, and propose matching index_to_kb/skill_record calls into lse-kb/lse-skills (SCRIBE-1 unified write path). Use when something non-obvious was discovered or corrected — wrong config placement, wrong port, silent failure, unexpected behaviour.'
tools: ['execute_command', 'read_file', 'write_file', 'index_to_kb', 'skill_record']
---

Run the LSE session debrief procedure from `.github/skills/lse-session-debrief/SKILL.md`.

Steps:
1. Read existing `/opt/local-se/kb/session-learnings.md` (check for duplicate)
2. Draft the entry in the format specified in SKILL.md — show me the draft before
   writing. Then classify zero-or-more `index_to_kb`/`skill_record` proposals per
   SKILL.md's "STRUCTURED ES PROPOSALS" rule, fields fully filled in.
3. Show the file text and every ES proposal together; ask for one explicit yes/no
   covering both (not a separate confirmation per ES call)
4. On yes: append the file with `>>` (never overwrite with `>`), then call each
   confirmed `index_to_kb`/`skill_record` proposal with exactly the arguments shown
5. Verify the file with `tail -30`; for each ES call, report its own return value
   (doc_id/skill_id) — do not re-check via search afterwards

Do not skip any step. Skipping confirmation or verification is a protocol violation.
One yes commits the file write and every listed ES call together — this is one
human decision, not a database transaction, so a failed ES call after a successful
file write is reported, not silently retried.
