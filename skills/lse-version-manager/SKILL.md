---
name: lse-version-manager
description: >
  Manages LSE component versions and changelog entries. Use when the user says
  "log this version", "add a changelog entry", "what changed in vX.Y.Z",
  "update the changelog", "which versions haven't been tested", or when a new
  tool or prompt version has just been written. Also use to check co-test status
  (which tool+prompt pairings have eval coverage).
---

# LSE Version Manager

Maintains the version registry and changelog so the relationship between tool
versions, prompt versions, and eval runs is always explicit — not reconstructed
from memory after the fact.

---

## VERSION REGISTRY

Single source of truth lives at:
  `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\VERSION.md`

This file tracks:
- Current canonical versions (tool, prompt, filter, context-monitor)
- Co-test matrix: which (tool, prompt) pairs have eval coverage
- Unpaired versions: shipped but not yet eval-tested

Prompt changelog: `prompts/CHANGELOG.md`
Tool changelog: embedded in each tool file's header docstring (`version` field + `Changelog:` block)

---

## THREE OPERATIONS

### Operation A — Log a new version

Trigger: "log this version" / "add a changelog entry" / "we just shipped vX.Y.Z"

**Step 1 — READ**
Read the VERSION.md registry and the relevant changelog:
- For a prompt version: `Read prompts/CHANGELOG.md`
- For a tool version: `Read tools/openwebui-tool-vX.Y.Z.py` (first 60 lines — header only)

Check: does an entry for this version already exist? If yes, say so and stop.

**Step 2 — DRAFT**
Write the full entry in chat using the format below. Do not write to disk yet.

For `prompts/CHANGELOG.md` entries:
```
## vX.Y.Z — YYYY-MM-DD
**Changes from vX.Y.Z-1:**
- <one bullet per change — concrete, not vague>
- <name the root cause if the change fixes a bug>
- <name what was removed and why if removing a section>
```

For `VERSION.md` updates, draft:
1. Updated "Current Versions" row (new version, date)
2. New row in "Version History" table (version, date, one-line key change)
3. Updated "Unpaired Versions" block (add new version to unpaired list)

**Step 3 — CONFIRM**
Ask exactly: "Write these entries? (yes/no)"
Wait for an explicit yes. Do not proceed on ambiguous responses.

**Step 4 — WRITE**
On confirmation:
- Append to `prompts/CHANGELOG.md` using Edit (prepend before the first `##` heading so newest is at top)
- Update `VERSION.md` — edit the three relevant sections (Current Versions row, Version History row, Unpaired block)

**Step 5 — VERIFY**
Read back the top of `prompts/CHANGELOG.md` and the updated sections of `VERSION.md`.
Confirm both look correct before reporting done.

---

### Operation B — Check co-test status

Trigger: "which versions haven't been tested" / "what's unpaired" / "is vX.Y.Z tested"

**Step 1 — READ**
Read `VERSION.md` — specifically the "Unpaired Versions" and "Co-test Matrix" sections.

**Step 2 — REPORT**
Produce a short status:
```
Unpaired tool versions:    v1.5.2, v1.5.3, v1.5.4, v1.5.5
Unpaired prompt versions:  v0.5.0, v0.5.1, v0.5.2
Next recommended eval:     tool v1.5.5 + prompt v0.5.2
Last eval run:             eval-v2 (tool v1.5.1 + prompt v0.4.1, score 45/57)
```

No writes. Read-only operation.

---

### Operation C — What changed in vX.Y.Z

Trigger: "what changed in vX.Y.Z" / "what's in v0.5.2"

**Step 1 — CLASSIFY**
Determine from the version string whether it's a tool version (v1.x.x) or prompt version (v0.x.x).

**Step 2 — READ**
- Prompt version: `Read prompts/CHANGELOG.md` — find and return the matching `## vX.Y.Z` block.
- Tool version: `Read tools/openwebui-tool-vX.Y.Z.py` (first 80 lines) — find and return the matching `vX.Y.Z:` line in the `Changelog:` block.

**Step 3 — RETURN**
Quote the changelog entry verbatim. Add one sentence summary if the entry is long.
No writes.

---

## AFTER AN EVAL RUN

When a new eval report is written, update the Co-test Matrix in `VERSION.md`:
1. Add a new row: eval name, tool version, prompt version, score, report path
2. Remove the tested versions from "Unpaired Versions"
3. Update "Next planned eval" if relevant

Trigger: "log the eval results" / "eval run complete" / "update the co-test matrix"

---

## VERSION NAMING RULES

- Tool versions: `v1.MINOR.PATCH` — minor bump for new features/functions, patch for docstring fixes
- Prompt versions: `v0.MINOR.PATCH` — minor bump for structural changes, patch for wording fixes
- Filter versions: `v1.MINOR.PATCH` — same as tool
- Context monitor: `v1.MINOR.PATCH` — same as tool

A version "ships" when its file is committed to git. Until then it is a draft.

---

## WHAT NOT TO DO

- Do not generate a changelog entry for in-progress changes — only for committed versions
- Do not mark a version as "co-tested" without a corresponding eval report file
- Do not overwrite `prompts/CHANGELOG.md` — always prepend (newest at top)
- Do not guess what changed — ask the user if the change set is unclear
