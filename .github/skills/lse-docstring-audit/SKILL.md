---
name: lse-docstring-audit
description: >
  Audits and rewrites LSE OpenWebUI tool function docstrings for model compliance,
  using the 8-dimension audit framework. Invoke when writing or modifying any
  Cogitator function, reviewing a docstring before staging, or when the user says
  "audit this docstring", "optimize this docstring", "review this tool function",
  "will the model follow this", or "does this docstring look right". Also invoke
  proactively on execute_command, write_file, read_file, sudo_delegation_block, and
  any new tool function before deployment.
---

# LSE Docstring Optimizer

LSE eval history shows that model compliance failures trace almost entirely to
docstring problems: missing stop signals, passive language, absent examples, or
unprohibited failure modes. This skill encodes those patterns into a repeatable
audit so regressions are caught before staging, not during eval.

## How to use

The user pastes a tool function docstring (or full function). You:

1. Run the **8-dimension audit** below — score each dimension PASS/WARN/FAIL/N/A
2. Write a **findings summary** — one sentence per finding, critical first
3. Produce a **rewritten docstring** with all fixes applied

All three in a single response. Do not ask clarifying questions first.

## The 8-Dimension Audit

### 1. Section Headers
Do multi-part docstrings use CAPITALISED headers?

Headers in ALL CAPS are structural landmarks the model can navigate to without reading
the full docstring. Critical for functions with multiple behavioural rules.

- PASS — all major rule blocks have a capitalised header (STOP PROTOCOL, COMBINE RULE, etc.)
- WARN — some blocks unlabelled or mixed case
- FAIL — flat prose; all rules buried in paragraphs
- N/A — single-rule docstring (≤8 lines, one rule)

**Fix:** Add `STOP PROTOCOL:`, `COMBINE RULE:`, `CONFIRMATION PROTOCOL:`, etc.

---

### 2. Compliance Language
Are directives imperative and unambiguous?

Passive/hedged language ("should", "consider", "try to") gives the model permission
to skip the instruction. Imperative language ("must", "never", "always") does not.

- PASS — all directives use imperative forms
- WARN — mix of imperative and hedged; at least one "should" or "consider"
- FAIL — majority of directives are hedged or passive

**Fix:** "should X" → "must X"; "try not to" → "never"

---

### 3. GOOD/BAD Examples
For any rule the model might misapply, is there a concrete GOOD/BAD pair?

The COMBINE RULE case: prose alone → ~50% compliance. Adding GOOD/BAD pairs → ~90%.
Examples disambiguate edge cases prose leaves open.

- PASS — GOOD/BAD examples present for every ambiguous rule
- WARN — examples for some rules but missing for key ones
- FAIL — no examples; rules stated in prose only
- N/A — single unambiguous rule with no plausible misinterpretation

**Fix:**
```
  GOOD: execute_command("cmd1 && cmd2 && cmd3")   ← single call, chained
  BAD:  Three separate execute_command calls       ← protocol violation
```

---

### 4. Stop/Halt Protocol

**First determine category:**
- **User-facing output** — function produces a block or message the user reads and acts on
  (e.g. `sudo_delegation_block`, `diff_file`, delegation functions) → REQUIRES STOP PROTOCOL
- **Internal-data** — function returns data the model processes silently
  (`execute_command`, `read_file`, `search_web`) → mark **N/A** and move on

For user-facing functions:
- PASS — STOP PROTOCOL present; specifies exact echo-line format; prohibits post-execution instructions; uses "protocol violation"
- WARN — stop instruction present but incomplete
- FAIL — no stop instruction

**Fix (user-facing only):**
```
STOP PROTOCOL — mandatory, no exceptions:
  After calling this function, write exactly ONE closing line echoing the command.
  Format: "Please run `<command>` in your terminal and paste the output here."
  After that single line, output nothing further.
  Do NOT add post-execution instructions, hints, or follow-up bash snippets.
  Anything beyond the single echo line before user input is a protocol violation.
```

---

### 5. Failure Mode Prohibitions
Are the most likely model errors explicitly named and forbidden?

The S3 regression: write_file docstring stated the confirmation protocol but never
said "skipping confirmation is a protocol violation" — model treated it as optional.

- PASS — top failure mode explicitly named and forbidden ("Skipping X is a protocol violation")
- WARN — some prohibitions present but key failure mode not called out
- FAIL — docstring states what to do but never prohibits the failure mode

**Fix:** For each rule, add one explicit prohibition:
```
Skipping confirmation is a protocol violation.
Skipping the read when the file is readable is a protocol violation.
Do NOT add post-execution instructions — this is a protocol violation.
```

---

### 6. Output Format Specification
Where the function requires a specific string output, is that format quoted exactly?

Unspecified format → drift between runs. Model produces "approximately right" output
that may not match eval test expectations.

- PASS — exact format quoted inline with a `Format:` prefix
- WARN — format described but not quoted or exemplified
- FAIL — format left entirely implicit

**Fix:** `Format: "Please run \`<command>\` in your terminal and paste the output here."`

---

### 7. Trigger Gate
Is the trigger condition for calling this function clear and specific?

Functions called too eagerly or too lazily usually have vague or absent gates.

- PASS — explicit numeric or conditional trigger stated
- WARN — trigger stated informally: "use for privileged operations" (too broad)
- FAIL — no trigger condition; description only covers what it does, not when

**Fix examples:**
```
GATE: Only call when you cannot answer from system prompt knowledge.
GATE: NEVER run sudo yourself — always call this function instead.
GATE: Call after your 5th tool call in a session.
```

---

### 8. Verification Requirement
If the function writes or modifies state, does the docstring require a verification step?

Write-without-verify failures are caught by W-class eval tests. Model writes, reports
success, never confirms with `tail` or `read_file`.

- PASS — "After writing, verify with: execute_command('tail -5 <path>') or read_file" — stated as mandatory
- WARN — verification mentioned but framed as optional
- FAIL — no verification requirement
- N/A — read-only or data-return function

**Fix:**
```
After writing, verify with: execute_command("tail -5 <path>") or read_file.
Skipping verification is a protocol violation.
```

---

## Proportionality

- **Short / single-purpose** (≤8 lines, 1 rule): Most dimensions N/A. A clear DO NOT plus
  a trigger condition is well-formed. Do not add headers or GOOD/BAD just to fill the table.
- **Medium / multi-rule** (8–25 lines, 2–3 rules): Full audit. Headers and examples add real value.
- **Large / complex** (25+ lines, multiple protocols): Full audit. Missing headers here are
  high-probability failure modes.

A finding that says "well-formed; two minor WARNs worth monitoring" is as valuable as five FAILs.

---

## Output Format

```
## Audit — <function name>

| Dimension                | Score | Notes                             |
|--------------------------|-------|-----------------------------------|
| 1. Section headers       | PASS  |                                   |
| 2. Compliance language   | WARN  | "should" on line 4                |
| 3. GOOD/BAD examples     | FAIL  | No examples for COMBINE RULE      |
| 4. Stop protocol         | N/A   | internal data-return function     |
| 5. Failure prohibitions  | WARN  | Confirmation not explicitly locked|
| 6. Output format         | FAIL  | Echo line format not quoted       |
| 7. Trigger gate          | PASS  |                                   |
| 8. Verification          | PASS  |                                   |

**Critical findings:**
- [FAIL] Dimension 3: ...
- [WARN] Dimension 2: ...

**Rewritten docstring:**
```python
def <function_name>(...) -> str:
    """
    <full rewritten docstring with all fixes applied>
    """
```
```

Score every dimension. Never skip one. If N/A, state the reason.

---

## LSE Failure History

| Missing pattern         | Eval class | Example failure                                       |
|-------------------------|------------|-------------------------------------------------------|
| STOP PROTOCOL           | P2, P3     | Model adds "After running that..." after sudo block   |
| COMBINE RULE examples   | A2         | Model issues commands one at a time                   |
| Confirmation protocol   | W1, W3     | Model writes without asking yes/no                    |
| READ-FIRST RULE         | W2, S3     | Model overwrites file from partial read               |
| GOOD/BAD examples       | A2, A3     | Model misinterprets ambiguous parameter               |
| Verification            | W3         | Model reports write success without checking          |
| Trigger gate too broad  | S1         | Model calls get_context_status on turn 1              |
| Passive language        | Any        | Model treats rule as advisory, skips it               |
