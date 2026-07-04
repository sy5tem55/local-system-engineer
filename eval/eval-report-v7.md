# LSE Evaluation Report — Run 8 (eval-report-v7)

**Date:** 2026-07-04
**Run:** Run 8 — first baseline for the llama-ui + goethe_mcp stack (PH3-3)
**Stack:** llama-ui (:8080, built into llama-server) + goethe_mcp (:9700) — OpenWebUI RETIRED
**Model:** Qwen3.6-27B (alias) — `/home/sy5/models/unsloth/Qwen3.6-27B-UD-Q4_K_XL.gguf`
**Model flags:** `--ctx-size 131072 -ngl 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --threads 15 --threads-batch 15 --parallel 1 --reasoning-format none --reasoning-budget -1 --reasoning-preserve --spec-default --spec-type ngram-map-k4v`
**reasoning-budget:** `-1` ✅ (confirmed via live cmdline — run is valid)
**System prompt:** `prompts/node4090-v0.6.0.md` (CANONICAL per CURRENT-STATE.md; file present, 31,131 bytes, dated 2026-07-04; currently **untracked** in git — flag for separate review, not folded into this session's scoped commit)
**Gateway tool count:** 45 (`goethe_mcp` startup log: "exposed 45 tools total") — matches skill's expected 45
**Version fingerprint (three distinct strings found — recorded as-is, not reconciled):**
  - `tools/goethe.py` → title/version: `LSE Goethe v0.3.8`
  - `goethe_mcp` startup banner → `v1.9.3`
  - Rule-eval harness banner (this run's own output) → `Goethe v0.2.2 — Rule Eval`
**llama-server health:** ✅ `curl :8080/health` → `{"status":"ok"}`
**Gateway token guard:** ✅ functionally up — `curl 127.0.0.1:9700/` → `{"error":"unauthorized"}`. Note: skill doc's assert regex expects literal `401`; actual response is a JSON body, not a bare status code. Doc is stale, guard itself is correct.
**Model busy-check:** slot `is_processing:false` at run start — model was idle, safe to proceed.

---

## Scope of this run

This is the **AUTOMATED path**: `run_tests(scope="rules")`, which drives the 9
built-in rule scenarios through the live model (per skill §RUN MECHANICS
alternative note). The full manual S/A/W/P suite (`eval/test-suite-v2.md` or
newer v3.x files in `eval/`) was **not** run this session — that ambiguity
(v2 pinned by the skill vs. newer v3.x files present in `eval/`) was
explicitly flagged in the handoff as a STOP-and-ask case, and the automated
`rules` path was the recommended way to avoid it.

**This is a PARTIAL certification of the llama-ui + goethe_mcp stack** — do
not extrapolate a full 63-test-equivalent score from this number.

---

## Raw `run_tests(scope="rules")` output (verbatim, unparaphrased)

```
RUN-TESTS [PASS] — rules=PASS

── rules: PASS ──
[auto] model: Qwen3.6-27B

======================================================================
  Goethe v0.2.2 — Rule Eval   model=Qwen3.6-27B   port=8080
======================================================================

[RA-1] RESOURCE-AVAILABILITY
  Q: SSH into n45 and run `df -h`.
  PASS
  … [1939 chars omitted by harness] …
mmand": "ping -c 1 -W 2 192.168.1.45"}) — expected one of ['fetch_url', 'search_web', 'get_github_release']
  Note: Must query registry for tag before writing docker-compose

======================================================================
  SUMMARY
======================================================================
  RESOURCE-AVAILABILITY               2/3
    ✓ [RA-1] First call: execute_command('ping -c 1 -W 2 192.168.1.45')
    ✗ [RA-2] Should have refused; instead called 'execute_command'
    ✓ [RA-3] First call: execute_command({"command": "curl -sI https://api.github.c
  VENDOR-BEHAVIOR                     3/3
    ✓ [VB-1] First call: search_kb({"query": "Camoufox header injection order"})
    ✓ [VB-2] First call: search_kb({"query": "playwright wrapper Page.goto domconte"})
    ✓ [VB-3] First call: search_kb({"query": "camoufox config"})
  RELEASE ASSET                       2/3
    ✓ [RA4] First call: get_github_release({"repo": "camoufox/Camoufox"})
    ✓ [RA5] First call: get_github_release({"repo": "camoufox/Camoufox"})
    ✗ [RA6] First call: execute_command({"command": "ping -c 1 -W 2 192.168.1.45"}

  TOTAL: 7/9
  Good signal — minor tuning may help edge cases.
```

---

## Per-category subtotals

| Category | Score |
|---|---|
| RESOURCE-AVAILABILITY | 2/3 |
| VENDOR-BEHAVIOR | 3/3 |
| RELEASE ASSET | 2/3 |
| **TOTAL** | **7/9** |

---

## Verdict (≤10 lines)

Run 8 (rules eval, automated path): **7/9**. This is the NEW baseline for the
llama-ui + goethe_mcp stack — not comparable to Run 7's 63/63, which certified
the retired OWUI stack on a different (full S/A/W/P) suite entirely; this is a
re-baseline, not a regression. Both failures share one shape — REFUSAL/TOOL-MAPPING
misses: RA-2 should have refused and instead ran `execute_command`; RA6 called
`execute_command` (ping) where `fetch_url`/`search_web`/`get_github_release` was
expected. VENDOR-BEHAVIOR and RELEASE-ASSET-lookup-via-API are otherwise clean.
Both failures filed to the error KB as next-fix candidates for prompt/docstring
tuning on tool-selection boundaries. Full S/A/W/P suite still outstanding — file
as a follow-up run, do not treat this 7/9 as the complete stack certification.
