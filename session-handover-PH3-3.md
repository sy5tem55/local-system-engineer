# PH3-3 → Run 8 — Handoff for a Claude 4.6 session

You are picking up PH3-3, the last item before the summit. The token-expensive
half (rewriting the eval-runner skill) is DONE. Your job is the GPU-bound half —
Run 8 — plus committing and closing the loose threads. Work the steps in order.
This is written explicitly on purpose: follow it, don't improvise.

Project dir: point this session at the `local-system-engineer` folder.

---

## 0. STOP-GATE — verify before you touch anything

Run 8 cannot happen without the goethe MCP. None of the steps below work otherwise.

1. Confirm the goethe MCP is connected: the tools `run_tests`, `execute_command`,
   `assert_state`, `index_to_kb`, `record_error` must be available.
   → If they are NOT present: STOP. Tell Joe the goethe gateway isn't connected
     to this session. Do not attempt workarounds.
2. Confirm the stack is up. Invoke the `lse-stack-health-check` skill, or run
   `run_tests(scope="all")` and expect RUN-TESTS [PASS] (kb + retrieval + harness
   green). A FAIL ABORTS the run — surface it to Joe, don't push past it.
3. Read the procedure skill IN FULL before running anything — it is NOT auto-loaded:
   `skills/lse-eval-runner/SKILL.md`. It is the authority on order and scoring.
   First confirm it's healthy: `file skills/lse-eval-runner/SKILL.md` must say
   "UTF-8 text" (it was NUL-corrupted and repaired; if it says "data", stop).

## What is already done — do NOT redo

- `lse-eval-runner` rewritten for the llama-ui + goethe_mcp stack: OpenWebUI
  retired, `run_tests(scope="all")` wired in as pre-run step 1.
- That file's truncated write left NUL padding; it has been repaired to clean
  UTF-8 (4911 bytes, ends in a single newline).

---

## Your job — finish PH3-3

### Step 1 — Commit the repaired skill (SCOPED)
The working tree is dirty with unrelated session work. **Never `git add -A`.**
Commit ONLY the skill. Sandbox git may be lock-blocked; run git through the
node via `execute_command`:
  `cd <repo> && git add skills/lse-eval-runner/SKILL.md && git commit -m "PH3-3: eval-runner v2 (llama-ui+goethe_mcp) — OWUI retired, run_tests wired, NUL corruption repaired"`
Leave CHANGELOG.md, ROADMAP.md, CURRENT-STATE.md, tools/* and the untracked
files alone — list them for Joe as "review separately", do not fold them in.

### Step 2 — Pre-run checklist (skill §PRE-RUN)
Record the fingerprint for the report header: goethe version, model file + flags
(`--reasoning-budget` MUST be -1 or the run is invalid), system prompt =
`prompts/node4090-v0.6.0.md`, and the gateway tool count. Do not restart the
gateway after this — it snapshots the tool surface.

### Step 3 — Run 8 (AUTOMATED path — recommended for this session)
`run_tests(scope="rules")` — drives the 9 rule scenarios through the live model.
Minutes of GPU time. Do NOT run while Joe is using the model. Do NOT restart the
gateway or llama-server mid-run.
  • Alternative (manual full S/A/W/P suite): skill §RUN MECHANICS drives a suite
    file. The skill pins `eval/test-suite-v2.md`, but newer `test-suite-v3.x`
    files exist in eval/. If v2 looks stale for this stack, STOP and ask Joe —
    do not pick a suite yourself. The automated `rules` path avoids this trap.

### Step 4 — File the report
`ls eval/ | grep report` → highest is currently v6, so the next free is
`eval/eval-report-v7.md`. Use the next free number, but put **"Run 8"** in the
header explicitly (run id ≠ file number). Header = the Step 2 fingerprint; body =
the RAW `run_tests` output as evidence; per-category subtotals; a verdict of ≤10
lines. Do not paraphrase the raw output away.

### Step 5 — Baseline + index
- Update `CURRENT-STATE.md`: Run 8's total is the NEW llama-ui baseline. It
  SUPERSEDES Run 7's 63/63 (which certified the retired OWUI stack and is NOT
  comparable — this is a re-baseline, not a regression).
- `index_to_kb(title="LSE eval Run 8 baseline", topic="lse-operations",
   source_tier="ground_truth", evidence=<subtotals>,
   verified_against=<goethe version + model + prompt version>)`.
- Any test scored 0–1: file each with `record_error(...)` so `check_error_kb`
  surfaces it. List them as next-fix candidates. Do NOT hotfix mid-run.

### Step 6 — Close out
Commit the report + CURRENT-STATE update (scoped again). Optionally write a
session-debrief to `kb/session-learnings.md` via the `lse-session-debrief` skill.

---

## Guardrails (you are the lean model here — stay in your lane)
- The heavy compute is the GPU's, not yours: PROMPT → WAIT → TRANSCRIBE. Never
  summarize model output beyond a score + one-line note.
- When the map disagrees with the territory (skill vs. files, version mismatch,
  suite ambiguity) — STOP and ask Joe. Do not improvise a resolution.
- Never `git add -A`. Scope every commit to named files.
- A partial run is filed as PARTIAL. Never extrapolate a total.
- Do not restart the gateway or llama-server mid-run (invalidates the surface).

## Stop conditions (surface to Joe, don't push through)
goethe MCP absent · stack health FAIL · SKILL.md not UTF-8 · suite/skill version
mismatch · reasoning-budget ≠ -1 · any call that needs a judgment about what
"counts" toward the score.
