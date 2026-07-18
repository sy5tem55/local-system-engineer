---
name: lse:eval-runner
description: Run an LSE evaluation session — structured guide for executing the LSE test suite on the llama-ui + goethe_mcp stack, scoring results consistently, and writing the eval report. Use this skill whenever the user says "run the LSE eval", "Run 8", "let's do a test run", "run the test suite", "score the model", "re-baseline the LSE", or wants to test a new tool or prompt version. Also trigger when the user asks which tests to run first, how to score a partial, or whether a result is a pass. This skill is the authoritative source for LSE eval procedure — always use it rather than improvising the test order or scoring rubric.
---

# LSE Eval Runner — v2 (llama-ui + goethe_mcp stack, PH3-3)

> v2 (2026-07-04): OpenWebUI is RETIRED. Everything below targets llama-ui
> (:8080, built into llama-server) + goethe_mcp (:9700). Run 7's 63/63
> certified the OWUI stack and is NOT comparable — the next run (Run 8)
> establishes a NEW baseline; deviations from Run 7 are re-baselining,
> not regressions.

## TOKEN BUDGET DISCIPLINE

An eval run is long. The runner's job is PROMPT → WAIT → GRADE — nothing else:
- Do NOT summarize model responses beyond the score + one-line note.
- Do NOT debug failures mid-run — record score, note symptom, move on.
- Grade against the printed pass criteria verbatim; no re-derivation.
- The heavy compute is the local GPU's, not yours. Keep it that way.

## PRE-RUN CHECKLIST (all via the goethe MCP gateway — no admin panels)

1. Stack health: `run_tests(scope="all")` → expect RUN-TESTS [PASS]
   (kb + retrieval + harness green). A FAIL aborts the run — fix first.
2. Version fingerprint (record in the report header):
   - `execute_command("grep -m2 '^title\\|^version' ~/projects/local-system-engineer/tools/goethe.py")`
   - `assert_state("curl -s http://localhost:8080/health", "ok")` — llama-server up
   - `assert_state("curl -s http://127.0.0.1:9700/", "401")` — gateway token guard up
   - Model + flags: `execute_command("tr '\\0' ' ' < /proc/$(pgrep -f 'llama[-]server' | head -1)/cmdline")`
     — record model file, ctx-size, reasoning flags.
     NOTE: --reasoning-budget must be -1 for a fair run (a finite budget
     truncates thinking mid-test → false "Reasoning Cancelled" failures).
3. System prompt: confirm llama-ui carries the CANONICAL prompt
   (`prompts/node4090-v0.6.0.md` or later — see CURRENT-STATE.md). Record its
   version. A mismatched prompt invalidates the run.
4. FRESH TOOL SURFACE: llama-ui snapshots the tool schema per conversation.
   Do NOT restart the gateway mid-run. Record the tool count from
   `/tmp/goethe-gateway.log` (expect 47 on LUCIFER: goethe.py 37 + vaultwarden/pfsense/net-discovery
   add-ons; node3090 gateway loads goethe.py only = 37. As of Goethe v0.4.4 / goethe_mcp
   v1.11.2 — search_rfc retired PH4-3, KB surface refactored to goethe_kb.py
   PH5-2 with tool-list parity verified; count changes = investigate first).

## RUN MECHANICS

1. Suite: `eval/test-suite-v2.md` (categories S/A/W/P, 0–3 per test, score
   sheet template at the bottom). The suite header still names OWUI-era
   versions — IGNORE the header stack line; prompts and pass criteria stand.
2. ONE FRESH llama-ui CONVERSATION PER TEST (new chat at :8080), unless a
   test explicitly says continue. Paste the "Send this" block exactly.
3. Score 3/2/1/0 against the printed pass criteria, with two adjudication
   rules for the current stack:
   - Criterion references retired machinery (OWUI panels, routing-filter
     behaviors, compaction block formats)? Score the CURRENT-stack equivalent
     (ledger/task_checkpoint instead of compaction blocks; llama-ui instead of
     OWUI) and mark the test id with an asterisk + one-line note.
   - REQUEST-SHAPE COMPLIANCE now counts: a prompt containing "plan" must
     route through planner(); "prove it"-shaped prompts must produce
     run_tests/assert_state output. Prose where a mapping exists caps the
     score at 1.
4. Record each score in the score-sheet template IMMEDIATELY after grading
   (context-loss insurance). One line per test.

## POST-RUN

1. File the report: `eval/eval-report-v8.md` (or next free number):
   header = date + goethe/gateway/prompt/model/flags fingerprint from the
   pre-run checklist; completed score sheet; per-category subtotals;
   asterisked adjudications; ≤10-line verdict.
2. Update CURRENT-STATE.md: this run's total is the NEW BASELINE for the
   llama-ui stack (supersedes Run 7's 63/63, which certified retired OWUI).
3. Index the verdict:
   `index_to_kb(title="LSE eval Run N baseline", topic="lse-operations",
    source_tier="ground_truth", evidence=<subtotals>,
    verified_against=<goethe version + model + prompt version>)`
4. Any test scored 0–1: file each as `record_error(...)` so check_error_kb
   surfaces it; list them as candidates for the next prompt/docstring fix.
   Do NOT hotfix mid-run.

## GATE

- Do not run while the user is actively using the model (the eval owns the GPU).
- Do not restart the gateway or llama-server mid-run (invalidates the surface).
- A partial run is filed as PARTIAL — never extrapolate a total.
