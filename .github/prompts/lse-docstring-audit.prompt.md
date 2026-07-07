---
mode: 'agent'
description: 'Audit an LSE tool function docstring against the 8-dimension framework. Use when writing or modifying any Cogitator or goethe.py function, or before staging.'
---

Run the LSE 8-dimension docstring audit from `.github/skills/lse-docstring-audit/SKILL.md`.

The user will paste the tool function (or just the docstring). You will:
1. Score all 8 dimensions: PASS / WARN / FAIL / N/A
2. Write a findings summary (most critical first)
3. Produce the fully rewritten docstring with all fixes applied

All three in one response. Do not ask clarifying questions first.

Dimensions: Section Headers, Compliance Language, GOOD/BAD Examples, Stop Protocol,
Failure Mode Prohibitions, Output Format, Trigger Gate, Verification Requirement.
