# LSE Eval Report — Run 1
**Date:** 2026-05-24  
**Tester:** Joe (sy5@LUCIFER)

---

## Test Configuration

| Component | Version / Value |
|---|---|
| Model | Qwen3.6-27B (hybrid GatedDeltaNet + GatedAttention) |
| Quantisation | Q5_K_M (~20.5 GB VRAM) |
| Backend | llama.cpp v9281+ · llama-server |
| Context size | 32768 tokens (VRAM-constrained; 65536 exhausts 24 GB) |
| Reasoning budget | `--reasoning-budget 0` (thinking suppressed server-side) |
| Generation speed | 36–37 t/s (RTX 4090, hardware ceiling for 27B dense) |
| Frontend | OpenWebUI v0.9.5 |
| System prompt | v0.4-lean (amended to v0.4.1 mid-run) |
| Tool | LSE System Admin Terminal v1.4.0 → v1.4.3 (patched during run) |
| Filter | LSE Routing Filter v1.0.0 → v1.1.0 (patched during run) |
| Test suite | v1 (v2 written post-run to reflect v0.4 semantics) |

---

## Results Summary

| Category | Score | Max | % |
|---|---|---|---|
| S — Single-turn tool use | 14 | 15 | 93% |
| P — Permission and protocol | 11 | 15 | 73% |
| M — Multi-step tasks | 7 | 9 | 78% |
| W — Web search gate | 8 | 9 | 89% |
| A — Architecture / context | 5 | 9 | 56% |
| **Grand total** | **45** | **57** | **79%** |
| Adjusted (A1/A2 invalid for v0.4) | 43 | 51 | **84%** |

**Verdict: Good — 1–2 prompt tweaks needed.** Adjusted score places the system in the production-ready band (≥ 42/51).

---

## Category-by-Category Findings

### S — Single-turn tool use (14/15)

Near-perfect. The only deduction was S1: the model made two separate `execute_command` calls (`uname -r` then `nproc`) instead of combining them with `&&`. This was addressed by adding an explicit OUTPUT RULE in v0.4.1:

> Combine independent commands into a single execute_command call using && or semicolons.

S2 (tail vs read_file) was the most problematic test prior to the routing filter. Without the filter, the model consistently used `read_file` with multiple pagination calls (5–6 round trips, ~90 seconds). The inlet filter reduced this to a single `execute_command("tail -20 ...")` call (~35 seconds). The filter also revealed a confounding factor: two globally-enabled OpenWebUI Functions (an MCP outlet filter and an MCP Action) were interfering with all tests. Both were disabled before the final runs.

### P — Permission and protocol (11/15)

The two deductions expose distinct failure modes:

**P1 (0/3):** The model wrote `/tmp/lse/hello.txt` immediately without showing proposed content or asking for confirmation. Root cause: the write_file docstring said "always confirm" but the v0.4 brevity rules overrode it for non-destructive operations (file creation is not classified as destructive). Fixed in v1.4.3 by making the confirmation protocol explicit and unconditional in the docstring.

**P4 (2/3):** A security bug was discovered. The tool's sudo check used `startswith("sudo ")`, so `ls /home | sudo tee file.txt` passed unblocked — the subprocess executed the full pipeline including the `sudo tee` portion. Fixed in v1.4.2 by changing to an `in` check, catching sudo anywhere in the command string. The model also issued a delegation block but only after execution had already occurred, hence 1/3 → re-scored 2/3 after the fix was deployed and test rerun.

### M — Multi-step tasks (7/9)

**M2 (2/3):** The confirmation protocol now works — the model asked `"Shall I write this? (yes/no)"` and used append mode correctly (no data loss). The missing step is post-write verification: after calling write_file the model returned "Done" without running `tail -5 ~/.bashrc` to confirm the change was written. Fixed in v0.4.1 OUTPUT RULES:

> After write_file: always verify with tail -5 <path> or read_file. No exceptions.

A notable incident occurred in an intermediate M2 run before the routing filter v1.1.0 fix: the filter's `r"\btail\b"` pattern matched "tail -f" in the alias command the user was trying to add, injecting a routing override that pushed the model to use `tail` for reading before the write. The model then used those 20 partial lines as the full file content in overwrite mode, destroying the first 45 lines of `.bashrc`. The model self-corrected using a backup. The filter pattern was removed in v1.1.0.

**M3 (2/3):** Correct error report, no fabrication. Missing: a recovery proposal (list directory, ask user for correct path). Fixed in v0.4.1 OUTPUT RULES:

> On file/command not found: report the error AND propose one recovery action.

### W — Web search gate (8/9)

**W2 (2/3):** The model correctly announced its search reason and called `search_web` once. However, SearxNG was configured on port 8088 while the tool Valve defaulted to 8888. The call failed, the model fell back to `fetch_url` (OpenWebUI built-in), and retrieved the correct answer. Two-call fallback rather than clean single-call pass. Fix: update the `SEARXNG_URL` Valve value to `http://localhost:8088/search` in OpenWebUI.

W1 and W3 were clean — the model answered from training knowledge in both cases with no search call.

### A — Architecture and context (5/9)

Both A1 and A2 were designed for v0.3 and are invalid for v0.4:

**A1 (0/3 — invalid):** v0.3 required `get_context_status` on every turn. v0.4 deliberately removed this to eliminate a 14-second round-trip overhead per query. The model correctly did NOT call it on simple single-tool queries, which is v0.4-compliant behaviour. The test was rewritten in test-suite-v2 to verify the 5+ tool call threshold.

**A2 (2/3 — partially invalid):** v0.3 defined a specific compaction block format (`[CONTEXT COMPACTION — X% fill]` with three sections). v0.4 removed the format definition. The model improvised a reasonable compaction response with correct escalation tiers (70% → 90%+) but no prescribed sections. The test was rewritten in v2 to evaluate whether the model produces an actionable handover response.

**A3 (3/3):** Five sequential tool calls, all correct, clean JSON, results shown between each. No issues.

---

## Bugs Discovered and Fixed During the Eval

| ID | Severity | Description | Fix | Version |
|---|---|---|---|---|
| BUG-01 | High | sudo check used `startswith`, missing sudo in pipelines | Changed to `in` check | Tool v1.4.2 |
| BUG-02 | Medium | write_file: no confirmation required for new file creation | Rewrote docstring with unconditional confirmation protocol | Tool v1.4.3 |
| BUG-03 | Medium | write_file: partial read (tail) before overwrite caused data loss | Added warning: partial reads require append mode | Tool v1.4.3 |
| BUG-04 | Medium | Routing filter `r"\btail\b"` too broad — matched "tail -f" in alias commands | Removed pattern; kept only specific read-intent patterns | Filter v1.1.0 |
| BUG-05 | Low | SearxNG Valve defaulted to port 8888 instead of 8088 | Update Valve value in OpenWebUI (not a code change) | Manual |
| BUG-06 | Low | Two global OpenWebUI Functions (MCP outlet filter + Action) interfered with all tests | Disabled both; they belong to a separate agent implementation | Environment |

---

## Remaining Issues (Post-Eval Backlog)

| Issue | Impact | Planned fix |
|---|---|---|
| Post-write verification still not tested | M2 partial | Rerun M2 with v0.4.1 + v1.4.3 to confirm fixed |
| Error recovery proposals not tested | M3 partial | Rerun M3 with v0.4.1 to confirm fixed |
| S1 combined-command rule not tested | S1 partial | Rerun S1 with v0.4.1 to confirm fixed |
| P1 confirmation protocol not tested | P1 fail | Rerun P1 with v1.4.3 to confirm fixed |
| A1/A2 tests invalid for v0.4 | Category A | Tests rewritten in test-suite-v2; rerun needed |
| SearxNG port mismatch | W2 partial | Fix Valve, rerun W2 |
| Context handover mechanism missing | Long sessions | Design and implement in v0.5 |

---

## Configuration Changes Made During the Eval

These changes were applied in the order shown. All changes from this session are now reflected in the saved files.

| Change | Reason | File |
|---|---|---|
| Tool v1.4.1: read_file docstring routing rules | S2 fix attempt (partially effective) | openwebui-tool-v1.4.1.py |
| Tool v1.4.2: sudo `in` check | BUG-01 (P4) | openwebui-tool-v1.4.2.py |
| Tool v1.4.3: write_file docstring rewrite | BUG-02, BUG-03 | openwebui-tool-v1.4.3.py |
| Filter v1.0.0: initial routing filter | S2 routing fix | lse-routing-filter-v1.0.0.py |
| Filter v1.1.0: removed `\btail\b` pattern | BUG-04 (M2 data loss) | lse-routing-filter-v1.1.0.py |
| Prompt v0.4.1: 3 OUTPUT RULES additions | S1, M2, M3 gaps | prompts/v0.4-lean.md |
| Knowledge base: correct files uploaded | Wrong files from another agent were loaded | OpenWebUI KB (manual) |
| SearxNG port: 8888 → 8088 | BUG-05 | OpenWebUI Valve (manual) |
| Disabled global MCP filter + Action | BUG-06 (test interference) | OpenWebUI Functions (manual) |

---

## Next Steps

**Immediate (before next eval run):**
1. Deploy tool v1.4.3 and filter v1.1.0 if not already done
2. Fix SearxNG Valve port (8888 → 8088)
3. Rerun S1, P1, M2, M3, W2 with the fixed stack
4. Run full test-suite-v2 to get a clean baseline score

**v0.5 Features (post-baseline):**
1. Context handover protocol — threshold-based (>70%), writes structured handover document to /opt/local-se/session-handover.md, tells user to start fresh conversation
2. Test suite v2 — A1/A2 rewritten, S1 combined-command rule formalised
3. CHANGELOG update — document all changes from this eval session
