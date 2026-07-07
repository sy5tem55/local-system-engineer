---
mode: 'agent'
description: 'Log a session learning to the KB. Use when something non-obvious was discovered or corrected — wrong config placement, wrong port, silent failure, unexpected behaviour.'
tools: ['execute_command', 'read_file', 'write_file']
---

Run the LSE session debrief procedure from `.github/skills/lse-session-debrief/SKILL.md`.

Steps:
1. Read existing `/opt/local-se/kb/session-learnings.md` (check for duplicate)
2. Draft the entry in the format specified in SKILL.md — show me the draft before writing
3. Ask for explicit yes/no confirmation
4. On yes: append with `>>` (never overwrite with `>`)
5. Verify with `tail -30`

Do not skip any step. Skipping confirmation or verification is a protocol violation.
