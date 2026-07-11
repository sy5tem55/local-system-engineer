# Bumpy Road master plan — goethe.py, 13 findings, 3 sessions

## Why Phase 1 didn't move this metric — and what changes now

Bumpy Road counts *distinct chunks of ≥2-level nested conditionals per function*. Phase 1 extracted three whole responsibilities; the bumps mostly relocated (two of the new helpers are themselves flagged). The rule that fixes this: **every extraction must land each bump in its own helper, and no helper may itself contain more than one ≥2-level chunk.** Extraction that violates this just moves the finding.

Verification loop per session: LSE inner loop (pytest + gate script per commit) → verifier re-checks the branch → merge → gateway reload → **CodeScene re-scan (http://localhost:3004) is the authoritative gate** — the AST detector under-counts vs CodeScene (e.g. planner: detector 3 merged regions, CodeScene 6 bumps; the big regions contain multiple sub-bumps to split by responsibility).

Line spans below are from master @ f92a667 and WILL DRIFT as commits land — the LSE must re-run the detector (appendix) after every commit instead of trusting these numbers.

## Cluster map

| Session | Functions | CS bumps | Detector spans (start-end@depth) |
|---|---|---|---|
| A — Planner | planner (270L) | 6 | 6806-6837@3, 6844-6878@3, 6890-6918@2 |
| | _call_node_planner (133L) | 3 | 1313-1332@3, 1343-1348@2 |
| B — Exec/guard/tests | execute_command (359L) | 4 | 2559-2659@5, 2664-2690@2 |
| | run_tests (124L) | 4 | 3572-3587@3, 3610-3635@6, 3637-3640@2 |
| | _validate_command_safety (53L) | 2 | 2313-2319@2, 2322-2328@2 |
| | ssh_run (131L) | 2 | 2093-2107@2, 2120-2145@3 |
| C — I/O & parsing | fetch_url (135L) | 3 | 3949-3969@2, 3995-4008@2, 4012-4025@2 |
| | verify_source_claims (127L) | 3 | 4086-4115@2, 4122-4168@3 |
| | _parse_reddit_posts (54L) | 3 | 3216-3248@5 |
| | nmap_summary (157L) | 3 | 5991-6017@3, 6024-6043@4 |
| | assert_state (110L) | 3 | 3722-3746@2 |
| | write_file (115L) | 2 | 2910-2929@2, 2936-2946@2 |
| | record_outcome (122L) | 2 | 5189-5220@3 |

Order rationale: A is the biggest single win and has a pre-verified boundary; B is the highest-risk code (the guard lives there) done while process discipline is fresh; C is volume work on lower-risk parsers.

## Standing rules (identical for every session — included in each kickoff)

1. One extraction per commit. Verbatim code movement modulo parameterization; helper placed above its caller; behavior-preserving only.
2. **Helper budget: each new helper ≤1 bump (no two ≥2-level chunks) and nesting depth ≤2.** Run the detector on your own helpers — if a helper is flagged, split it before committing.
3. After EVERY commit: `pytest tests/` AND the gate script (appendix). Paste RAW output, never summaries. A collection error means stop and fix before anything else.
4. Helper names must state the responsibility (e.g. `_fingerprint_ssh_host`, not `_helper2`). If you can't name it, the boundary is wrong.
5. Do NOT merge, do NOT restart the gateway or reload any runtime. Working tree = gateway live-load source. Hand back for verification.
6. If a command is BLOCKED: the message now names the matched fragment. One rephrase attempt max, then `sudo_delegation_block` or stop and report. Never spend the session probing the guard.
7. New imports (typing etc.) go at module level, and every commit must keep `pytest tests/` collection green — that is the import smoke test.

---

## Session A kickoff — Planner cluster (paste as first message)

We are refactoring `tools/goethe.py` to clear CodeScene Bumpy Road findings. Repo: `~/projects/local-system-engineer`. Create branch `refactor/bumpy-road-planner` off master. One extraction per commit.

Scope:
1. `planner` (6 bumps). FIRST commit: extract `_parse_planner_envelope` (nested inside `_call_planner_backend`) to a class-level method; `_call_planner_backend` calls it — this boundary was verified previously. Then one commit per remaining bump region (~6806-6837, 6844-6878, 6890-6918 at branch time — re-locate with the detector): each region contains multiple sub-bumps; split by responsibility, one named helper each.
2. `_call_node_planner` (3 bumps, ~1313-1332, 1343-1348): extract each into a named helper.

Pass criteria: detector reports ≤1 bump for `planner`, `_call_node_planner`, and every new helper; `pytest tests/` green after every commit; no function longer/deeper than before beyond call-site wiring.

[Standing rules 1-7 from the master plan go here verbatim.]

Done means: commits on the branch, raw test+gate output pasted per commit, branch NOT merged. Hand back for verification.

---

## Session B kickoff — Exec/guard/tests cluster (paste as first message)

Same repo, branch `refactor/bumpy-road-exec` off master (after Session A merges). One extraction per commit.

Scope:
1. `execute_command` (4 bumps). The ~2559-2659 region (depth 5) is the SSH-fingerprint + download handling: extract by responsibility (e.g. `_fingerprint_ssh_host`, `_handle_download_command`). Then ~2664-2690.
2. `run_tests` (4 bumps): ~3610-3635 is a depth-6 chunk — extract per scope-handling responsibility; also ~3572-3587, 3637-3640.
3. `_validate_command_safety` (2 bumps, ~2313-2319, 2322-2328). SECURITY-SENSITIVE: byte-exact movement only, no message or pattern changes. This commit gets line-by-line verifier review.
4. `ssh_run` (2 bumps, ~2093-2107, 2120-2145).

Pass criteria: detector ≤1 bump for all four functions and all new helpers; tests green per commit.

[Standing rules 1-7 verbatim.]

---

## Session C kickoff — I/O & parsing cluster (paste as first message)

Same repo, branch `refactor/bumpy-road-io` off master (after Session B merges). One extraction per commit. Seven functions, all lower-risk parsers/formatters — volume discipline matters more than difficulty.

Scope (bumps, spans at master f92a667 — re-locate first):
`fetch_url` (3: 3949-3969, 3995-4008, 4012-4025) · `verify_source_claims` (3: 4086-4115, 4122-4168) · `_parse_reddit_posts` (3: one deep chunk 3216-3248@5 — split by parse stage) · `nmap_summary` (3: 5991-6017, 6024-6043) · `assert_state` (3: 3722-3746) · `write_file` (2: 2910-2929, 2936-2946) · `record_outcome` (2: 5189-5220).

Also fold in the Phase-1 leftover: dedupe the doubled `import re`/`_sanitize` blocks inside `_extract_text_from_html`.

Pass criteria: detector ≤1 bump for all seven and all helpers; tests green per commit.

[Standing rules 1-7 verbatim.]

---

## Appendix — gate script (LSE runs after every commit)

```python
# bump gate: python3 bump_gate.py  (run from repo root)
import ast
COND = (ast.If, ast.For, ast.While)
src = open('tools/goethe.py').read()
cls = [n for n in ast.walk(ast.parse(src))
       if isinstance(n, ast.ClassDef) and n.name == 'Tools'][0]

def maxd(node, d=0):
    m = d
    for c in ast.iter_child_nodes(node):
        m = max(m, maxd(c, d + 1 if isinstance(c, COND) else d))
    return m

def bumps(fn):
    out = []
    def walk(node, in_cond):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, COND) and not in_cond:
                if maxd(c, 1) >= 2:
                    out.append((c.lineno, c.end_lineno, maxd(c, 1)))
                walk(c, True)
            else:
                walk(c, in_cond or isinstance(c, COND))
    walk(fn, False)
    out.sort()
    merged = []
    for s in out:
        if merged and s[0] - merged[-1][1] <= 1:
            merged[-1] = (merged[-1][0], s[1], max(merged[-1][2], s[2]))
        else:
            merged.append(s)
    return merged

flagged = 0
for it in cls.body:
    if isinstance(it, (ast.FunctionDef, ast.AsyncFunctionDef)):
        b = bumps(it)
        if len(b) >= 2:
            flagged += 1
            spans = ' '.join(f'{a}-{e}@{d}' for a, e, d in b)
            print(f'{len(b):>2} bumps  {it.name:<28} {spans}')
print(f'--- {flagged} functions with >=2 bumps (detector approximates CodeScene; UI scan is authoritative)')
```

## Per-session close-out (operator)

1. Verifier re-checks branch (verbatim diffs, gate, `run_tests(harness)`).
2. Merge to master; working tree ends on master.
3. Reload gateway: `bash ~/projects/local-system-engineer/tools/start-goethe.sh` (v2.1.1 — detached, gated, pidfile).
4. CodeScene re-scan at http://localhost:3004; record Code Health delta and remaining bumpy-road count before starting the next session.
