# LSE Skills Planning

**Date:** 2026-05-24  
**Context:** Cowork skills are installable bundles that extend Claude's capabilities.
The LSE project has two categories of skill need: (1) off-the-shelf engineering skills
that are already useful as-is, and (2) custom LSE-specific skills worth building.

---

## 1. Off-the-shelf skills — use now

### `engineering:code-review`
**Trigger:** "review this before I merge" / diff / PR  
**LSE use:** Every tool version ships with docstring changes that directly control model
behaviour. A code review pass before deploying to OpenWebUI catches logic gaps, ambiguous
phrasing, or instructions that contradict each other — before the eval reveals them.

Specific value:
- Review `sudo_delegation_block` stop protocol wording for ambiguity
- Catch docstring edge cases (e.g. S3 regression was a docstring omission)
- Review routing filter regex changes before deploy

**Frequency:** Each tool version bump (v1.x.x → v1.x+1.x)

---

### `engineering:testing-strategy`
**Trigger:** "test strategy for" / "what tests do we need"  
**LSE use:** The test suite has evolved organically (v1 → v2 → v3). A structured testing
strategy would formalize:
- What each category is actually testing (unit vs integration vs regression)
- How to write A-category tests that don't break due to architecture mismatches (A1 in v2)
- How to score "partial" consistently across testers
- When to add a new test vs extend an existing one

Use when planning v4 test suite or when adding a new capability (e.g. a new tool function).

---

### `engineering:documentation`
**Trigger:** "write docs for" / "create a runbook"  
**LSE use:** The `docs/` folder covers model evaluation, terminal interaction, context
management, and knowledge base — but is missing an operational runbook for running the
full stack (start order, health checks, recovery steps). Also missing: contributor guide
for adding new tool functions.

**Immediate gap:** A `06-operations-runbook.md` covering:
- Stack start sequence (llama-server → open-webui → playwright → open-terminal)
- Health check commands for each service
- What to do when llama-server OOMs (check VRAM, reduce ctx-size)
- How to safely hot-swap a tool version in OpenWebUI

---

### `engineering:debug`
**Trigger:** error message / "this works in staging but not prod"  
**LSE use:** When a test regresses unexpectedly or a tool function behaves differently
across runs, the debug skill provides a structured reproduce → isolate → fix workflow.

Most useful for:
- Routing filter false positives/negatives (regex behaviour hard to predict)
- Tool call JSON errors (A3-class failures)
- Model stops at wrong point in multi-step protocol

---

### `engineering:architecture`
**Trigger:** "design a system" / "choosing between"  
**LSE use:** Useful when making architectural decisions about the LSE system itself:
- Should context monitoring move into the tool rather than a filter?
- Should sudo_delegation_block be a separate tool function or inline behaviour?
- What's the right design for adding a `diff_file` function?

Use before committing to a structural change — produces an ADR with trade-offs.

---

## 2. Custom LSE skills — worth building

These are skills that don't exist yet but have a clear, repeatable use case in the LSE project.

---

### `lse:eval-runner`
**What it does:** Structured guide for running an LSE eval session.

The current test suite requires the tester to:
1. Open OpenWebUI in the right configuration
2. Run 19 tests in a specific order (P3 depends on P1, A1 is multi-turn, etc.)
3. Score consistently using the rubric
4. Paste results back in the right format

A skill for this would encode:
- Pre-run checklist (correct tool version, prompt version, filters enabled)
- Test execution order and inter-test dependencies
- Scoring rubric applied consistently (what counts as partial vs fail)
- Post-run: where to write the score sheet, how to format notes

**Trigger:** "run the LSE eval" / "let's do a test run"  
**Build priority:** High — used every version bump

---

### `lse:docstring-optimizer`
**What it does:** Reviews a tool function's docstring and suggests improvements for
model compliance, based on the LSE failure history.

LSE has accumulated a clear pattern of what makes docstrings work:
- Capitalised section headers (STOP PROTOCOL, COMBINE RULE, PRIVILEGED PATH BEHAVIOUR)
- Direct imperative language ("output nothing further", "must appear in your response")
- Concrete examples for ambiguous cases
- Explicit prohibition of the failure mode ("do NOT add post-execution instructions")

A skill encoding these patterns would let Claude audit any new docstring before it ships
and flag likely compliance gaps — without having to discover them via eval regression.

**Trigger:** "optimize this docstring" / "review this tool function"  
**Build priority:** High — each new function needs this

---

### `lse:version-manager`
**What it does:** Tracks what changed between prompt and tool versions and generates
structured changelog entries.

The CHANGELOG.md in `prompts/` tracks prompt versions. But the relationship between
prompt version and tool version isn't formally tracked anywhere — when you look at
eval-report-v2.md you have to mentally reconstruct which tool version matched which
prompt version.

A skill for this would:
- Generate a changelog entry when a new version ships
- Enforce the version table in the eval report (Component | Version | Value)
- Flag when a tool version and prompt version haven't been co-tested

**Trigger:** "log this version" / "what changed in v1.5.1"  
**Build priority:** Medium

---

### `lse:stack-health-check`
**What it does:** Guides running a pre-session stack health check from WSL.

Before each LSE session, a quick health check should verify:
- llama-server is responding (`curl -s localhost:8080/health`)
- open-webui is reachable (`curl -s localhost:3000`)
- SearxNG is up on port 8088
- VRAM is within expected range (`nvidia-smi --query-gpu=memory.used,memory.free --format=csv`)

This is currently done ad-hoc. A skill would make it a consistent pre-session ritual,
and catch issues before they cause confusing eval failures (like the W2 port regression).

**Trigger:** "check the stack" / "is everything running"  
**Build priority:** Medium

---

## 3. Skills to defer

### `engineering:incident-response`
Not applicable — LSE is a personal dev environment, not a production service. If the
stack goes down, the recovery is just restarting the launcher.

### `engineering:deploy-checklist`
Could be adapted for "deploying" a new tool version to OpenWebUI, but the overhead of
a formal checklist for a single-user system is probably too high. The eval-runner skill
would cover this implicitly.

### `engineering:standup`
Not applicable — solo project.

---

## Build order recommendation

| Priority | Skill | Rationale |
|---|---|---|
| 1 | `lse:eval-runner` | Used every version; removes friction from the eval ritual |
| 2 | `lse:docstring-optimizer` | Catches regressions before they hit eval |
| 3 | `engineering:code-review` | Use immediately — no build needed |
| 4 | `lse:stack-health-check` | Prevents confusing failures like the W2 port miss |
| 5 | `lse:version-manager` | Nice to have; lower ROI than 1–4 |
| 6 | `engineering:documentation` | Use when writing the operations runbook |
