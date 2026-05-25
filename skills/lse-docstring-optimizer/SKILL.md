---
name: lse-docstring-optimizer
description: >
  Audits and rewrites LSE OpenWebUI tool function docstrings for model compliance.
  Use this skill whenever a new LSE tool function is written or modified, when a
  docstring is being reviewed before deployment, when an eval regression is traced
  to a docstring ambiguity, or when the user says "optimize this docstring",
  "review this tool function", "does this docstring look right", or "will the
  model follow this". Also use proactively when any execute_command, write_file,
  read_file, sudo_delegation_block, or new tool function is being added to the
  LSE toolset.
---

# LSE Docstring Optimizer

The LSE eval history has revealed a consistent pattern: model compliance failures
trace almost entirely to docstring problems — missing stop signals, passive language,
absent examples, or unprohibited failure modes. This skill encodes those patterns
into a repeatable audit so regressions are caught before eval, not during it.

---

## How to use this skill

The user will paste a tool function docstring (or the full function). You will:

1. Run the **8-dimension audit** below — score each dimension pass/warn/fail
2. Write a **findings summary** — one sentence per finding, most critical first
3. Produce a **rewritten docstring** — applying all fixes inline

Do all three in a single response. Do not ask clarifying questions first.

---

## The 8-Dimension Audit

### 1. Section Headers
**What to check:** Do multi-part docstrings use CAPITALISED headers as structural landmarks?

A docstring with multiple behavioural rules needs headers so the model can navigate to
the right section without reading the whole thing. Headers in ALL CAPS are a reliable
pattern the model uses for structural scanning.

- PASS — all major rule blocks have a capitalised header (e.g. STOP PROTOCOL, COMBINE RULE, CONFIRMATION PROTOCOL)
- WARN — some rule blocks present but unlabelled or in mixed case
- FAIL — flat prose with no headers; all rules buried in paragraphs

**Fix:** Add a short ALL-CAPS label before each distinct behavioural rule block.

---

### 2. Compliance Language
**What to check:** Are directives imperative and unambiguous?

Passive or hedged language ("should", "consider", "it is recommended", "try to")
gives the model permission to skip the instruction. Imperative language ("must",
"never", "always", "do NOT") does not.

- PASS — all directives use imperative forms
- WARN — mix of imperative and hedged; at least one "should" or "consider"
- FAIL — majority of directives are hedged or passive

**Fix:** Replace "should X" → "must X" or "X is required". Replace "try not to" → "never".

---

### 3. GOOD/BAD Examples
**What to check:** For any rule the model might misapply, is there a concrete GOOD/BAD pair?

The LSE COMBINE RULE was the clearest example: stating the rule in prose produced
~50% compliance. Adding four GOOD/BAD examples with `←` annotations pushed
compliance to ~90%. Examples disambiguate edge cases that prose leaves open.

- PASS — GOOD/BAD examples present for every ambiguous rule
- WARN — examples present for some rules but missing for key ambiguous ones
- FAIL — no examples anywhere; rules stated only in prose

**Fix:** For any rule where two different behaviours are both plausible, add:
```
  GOOD: <the correct behaviour>   ← why it's correct
  BAD:  <the incorrect behaviour> ← why it fails
```

---

### 4. Stop/Halt Protocol
**What to check:** If the function produces output the USER receives and acts on,
is there an explicit STOP PROTOCOL?

**First determine which category the function falls into:**

- **User-facing output** — the function produces a block, message, or diff that the
  user reads and responds to (e.g. sudo_delegation_block, diff_file, any delegation
  function). These REQUIRE a STOP PROTOCOL.
- **Internal-data functions** — the function returns data the model processes silently
  (e.g. get_context_status, read_file, execute_command, search_web). These are N/A
  for STOP PROTOCOL — mark N/A and move on.

If the function is internal-data: mark dimension 4 as **N/A** with a one-word note
("read-only", "internal", "data-return"). Do NOT add a STOP PROTOCOL to these functions.

For user-facing output functions:
- PASS — STOP PROTOCOL block present; specifies exact one-liner format; explicitly
  prohibits post-execution instructions and follow-up hints; uses "protocol violation"
- WARN — stop instruction present but incomplete (missing the echo-line format, or
  missing explicit prohibition of follow-ups)
- FAIL — no stop instruction; model expected to infer from context

**Fix (user-facing functions only):** Add:
```
STOP PROTOCOL — mandatory, no exceptions:
  After calling this function, write exactly ONE closing line that echoes the
  command so the user sees it without expanding the tool result card.
  Format: "Please run `<command>` in your terminal and paste the output here."
  After that single line, output nothing further.
  Do NOT add post-execution instructions, hints, or follow-up bash snippets.
  Do NOT suggest what to do after the command succeeds.
  Your next response must begin only after the user pastes terminal output.
  Anything beyond the single echo line before user input is a protocol violation.
```

---

### 5. Failure Mode Prohibitions
**What to check:** Are the most likely model errors explicitly named and forbidden?

A docstring that says what to do often leaves undone the equally important work of
forbidding what NOT to do. The S3 regression was a write_file docstring that stated
the confirmation protocol but never explicitly said "skipping confirmation is a
protocol violation" — the model treated confirmation as optional.

- PASS — the top failure mode for this function is explicitly named and forbidden
  using a "Skipping X is a protocol violation" or "do NOT X" construction
- WARN — some prohibitions present but key failure mode not explicitly called out
- FAIL — docstring states what to do but never prohibits the failure mode

**Fix:** For each behavioural rule, add one explicit prohibition:
- After confirmation protocol → "Skipping confirmation is a protocol violation."
- After STOP PROTOCOL → "Do NOT add post-execution instructions."
- After READ-FIRST RULE → "Skipping the read when the file IS readable is a protocol violation."

---

### 6. Output Format Specification
**What to check:** Where the function requires a specific output format from the model,
is that format specified exactly — with a quoted example if needed?

If a function expects the model to produce a specific string (an echo line, a diff
format, a confirmation question), leaving the format unspecified causes drift between
runs. The model produces something approximately right — which may or may not match
what downstream eval tests expect.

- PASS — exact format quoted inline (e.g. `Format: "Please run \`<cmd>\` ..."`)
- WARN — format described but not quoted or exemplified
- FAIL — output format left entirely implicit

**Fix:** Quote the exact expected string. Use `Format:` followed by the literal template.

---

### 7. Trigger Gate
**What to check:** Is the trigger condition for calling this function clear and specific?

A function called too eagerly (get_context_status on turn 1) or too lazily
(never calling sudo_delegation_block) usually has a vague or absent gate condition.

- PASS — explicit numeric or conditional trigger: "Call after your 5th tool call",
  "Only when you cannot answer from training knowledge", "NEVER call this yourself"
- WARN — trigger stated informally: "Use for privileged operations" (too broad),
  "Call when needed" (no criteria)
- FAIL — no trigger condition; function description only covers what it does, not when

**Fix:** Add a one-line gate. Examples:
- `GATE: Only call when you cannot answer from your system prompt knowledge base.`
- `Call after your 5th tool call in a session, before responding on that turn.`
- `NEVER run sudo yourself — always call this function instead.`

---

### 8. Verification Requirement
**What to check:** If the function writes or modifies state, does the docstring require
a verification step after the write?

Write-without-verify failures are caught by the W-class eval tests. The pattern is:
write_file succeeds, model reports success, but never confirms with tail or read_file.
Adding an explicit verify requirement catches this.

- PASS — "After writing, verify with: execute_command('tail -5 <path>') or read_file"
  or equivalent; stated as mandatory
- WARN — verification mentioned but framed as optional
- FAIL — no verification requirement; model expected to infer

**Fix:** Add to any write/modify function:
```
After writing, verify with: execute_command("tail -5 <path>") or read_file.
Skipping verification is a protocol violation.
```

---

## Proportionality

Before auditing, assess the docstring's scope:

- **Short / single-purpose** (≤8 lines, one behavioural rule): Apply the 8 dimensions
  but expect most to be N/A. A 4-line docstring with a clear DO NOT and a trigger
  condition is well-formed — do not add headers, GOOD/BAD examples, or STOP PROTOCOL
  just to fill the audit table. If it works, say so.
- **Medium / multi-rule** (8–25 lines, 2–3 behavioural rules): Full audit applies.
  GOOD/BAD examples and section headers add real value here.
- **Large / complex** (25+ lines, multiple protocols): Full audit applies. Missing
  headers and examples at this scale are high-probability failure modes.

A finding that says "this short docstring is already well-formed; two minor WARNs worth
monitoring" is as valuable as finding five FAILs. Over-engineering a simple docstring
adds noise and can introduce new compliance issues.

---

## Output Format

Always produce output in exactly this structure:

```
## Audit — <function name>

| Dimension              | Score | Notes                          |
|------------------------|-------|--------------------------------|
| 1. Section headers     | PASS  |                                |
| 2. Compliance language | WARN  | "should" on line 4             |
| 3. GOOD/BAD examples   | FAIL  | No examples for mode selection |
| 4. Stop protocol       | PASS  |                                |
| 5. Failure prohibitions| WARN  | Confirmation protocol unlocked |
| 6. Output format       | FAIL  | Echo line format not quoted    |
| 7. Trigger gate        | PASS  |                                |
| 8. Verification        | PASS  |                                |

**Critical findings:**
- [FAIL] <dimension>: <one sentence on what's missing and why it causes failures>
- [WARN] <dimension>: <one sentence>

**Rewritten docstring:**
\```python
def <function_name>(...) -> str:
    """
    <full rewritten docstring with all fixes applied>
    """
\```
```

Score every dimension. Never skip a dimension. If a dimension doesn't apply
(e.g. no write operation → verification N/A), mark it N/A with a note.

If the docstring is already well-formed, say so and highlight what it does right —
this is as useful as finding problems.

---

## LSE Failure History Reference

Use this when writing findings to give the user context on why each gap matters:

| Pattern missing         | Eval class affected | Example failure                              |
|-------------------------|---------------------|----------------------------------------------|
| STOP PROTOCOL           | P2, P3              | Model adds "After running that..." after sudo block |
| COMBINE RULE examples   | A2                  | Model issues commands one at a time          |
| Confirmation protocol   | W1, W3              | Model writes without asking yes/no           |
| READ-FIRST RULE         | W2, S3              | Model overwrites file from partial read      |
| GOOD/BAD examples       | A2, A3              | Model interprets ambiguous parameter wrong   |
| Verification requirement| W3                  | Model reports write success without checking |
| Trigger gate (too broad)| S1                  | Model calls get_context_status on turn 1     |
| Passive language        | Any                 | Model treats rule as advisory, skips it      |
