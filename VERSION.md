# LSE Version Registry

Single source of truth for component versions, ship dates, and eval coverage.
Updated by the `lse:version-manager` skill whenever a new version ships.

---

## Current Versions

| Component | Version | Shipped | Changelog |
|---|---|---|---|
| Tool | v1.5.7 | 2026-05-26 | tools/openwebui-tool-v1.5.7.py (header) |
| Prompt | v0.5.2 | 2026-05-25 | prompts/CHANGELOG.md |
| Filter | v1.1.0 | 2026-05-23 | tools/lse-routing-filter-v1.1.0.py |
| Context Monitor | v1.3.0 | 2026-05-26 | tools/lse-context-monitor-v1.3.0.py |
| Launcher | v1.070 | 2026-05-27 | lse-stack-launch-1.070.ps1 |
| Test Suite | v3.5 | 2026-05-26 | eval/test-suite-v3.5.md |

---

## Co-test Matrix

Each row is one eval run. "Co-tested" means a full eval suite was run against that
tool + prompt combination and a report was written.

| Eval Run | Tool | Prompt | Score | Report |
|---|---|---|---|---|
| eval-v1 | v1.4.0 | v0.1-baseline | — | eval/eval-report-v1.md |
| eval-v2 | v1.5.1 | v0.4.1 | 45/57 | eval/eval-report-v2.md |
| eval-v3 | v1.5.4 | v0.5.1 | 57/57 | eval/eval-report-v3.md |
| eval-v4 | v1.5.5 | v0.5.2 | 49/57 | eval/eval-report-v4.md |
| eval-v5 (partial) | v1.5.6 | v0.5.2 | 15/21 subset | eval/eval-report-v4.md (appended) |

---

## Unpaired Versions

Tool and prompt versions that have shipped but have no eval run against them.
These should be tested before being considered production-ready.

**Tool:** v1.5.2, v1.5.3, v1.5.4 *(all superseded — evaluate v1.5.7 only)*
**Prompt:** v0.5.0 *(superseded)*

> Next planned eval: Run 6 — tool v1.5.7 + prompt v0.5.2 + context monitor v1.3.0 against test-suite-v3.5. Full 21-question scored run.

---

## Version History

### Tool versions
| Version | Shipped | Key change |
|---|---|---|
| v1.4.0 | 2026-05-23 | Initial eval-tracked release |
| v1.4.1 | 2026-05-23 | read_file routing rules |
| v1.4.2 | 2026-05-23 | sudo embedded-in-pipeline fix |
| v1.4.3 | 2026-05-23 | write_file confirmation enforcement |
| v1.5.0 | 2026-05-23 | COMBINE RULE + SearxNG port fix (8888→8088) |
| v1.5.1 | 2026-05-23 | read_file privileged path + sudo stop protocol |
| v1.5.2 | 2026-05-24 | Denylist gap fixes (full audit) |
| v1.5.3 | 2026-05-24 | LIVE SERVICE RULE in execute_command |
| v1.5.4 | 2026-05-24 | get_context_status field-name fix + sudo READ-FIRST RULE |
| v1.5.5 | 2026-05-25 | RETURN VALUE SEMANTICS + privileged path workaround prohibition |
| v1.5.6 | 2026-05-26 | POST-DELETE VERIFY RULE, NO YEAR INJECTION, get_github_release() |
| v1.5.7 | 2026-05-26 | DESTRUCTIVE OPERATION PROTOCOL in execute_command |

### Prompt versions
| Version | Shipped | Key change |
|---|---|---|
| v0.1-baseline | 2026-05-23 | Initial baseline |
| v0.2-structured | 2026-05-23 | Tool use protocol, sudo delegation |
| v0.3-context-aware | 2026-05-23 | Context budget awareness, compaction |
| v0.5 | 2026-05-24 | CONTEXT HANDOVER section |
| v0.5.1 | 2026-05-24 | LIVE SERVICE RULE |
| v0.5.2 | 2026-05-25 | Remove SUDO DELEGATION FORMAT; DO NOT call again; KB path |

### Context Monitor versions
| Version | Shipped | Key change |
|---|---|---|
| v1.0.0 | 2026-05-23 | Initial — system message injection only |
| v1.1.0 | 2026-05-26 | Dual injection: system message + user message prepend |
| v1.2.0 | 2026-05-26 | Structured interrupt block replacing prepend (Step 1 / Step 2 format) — FAILED same root cause |
| v1.3.0 | 2026-05-26 | Self-fetching filter: queries /metrics, injects fill % as fact — no model action required |

### Test Suite versions
| Version | Shipped | Key change |
|---|---|---|
| v3.0 | 2026-05-24 | Baseline redesign with P/M/W/A/L categories |
| v3.4 | 2026-05-26 | Precondition fixes: P2, M2, A2, A3 |
| v3.5 | 2026-05-26 | A1 questions replaced with unfakeable answers (PID, inode, byte count, hash) |

### Launcher versions
| Version | Shipped | Key change |
|---|---|---|
| v1.05 | 2026-05-24 | Initial tracked release |
| v1.06 | 2026-05-25 | Profile menu, colour-coded tabs |
| v1.061 | 2026-05-25 | Minor profile adjustments |
| v1.062 | 2026-05-26 | draft-mtp profiles for Q5_K_M + Q4_K_M; Authenticode signed |
| v1.063 | 2026-05-26 | --metrics flag for Prometheus/Grafana scraping |
| v1.064 | 2026-05-26 | llama-optimus tuning: BatchSize, UBatchSize, OverrideTensor (MoE expert CPU offload), ngl 99→117/129, threads tuned per model |
| v1.065 | 2026-05-27 | Add Q4_K_M 64k profiles (thinking + no-think) for extended-context sessions |
| v1.066 | 2026-05-27 | Revert batch/UBatch/OverrideTensor (regression confirmed via D2>D3 bisect); keep ngl/threads |
| v1.067 | 2026-05-27 | Q5_K_M 64k profile: q8_0→q4_0 KV cache (saves ~1.1 GB; only ~1.1 GB headroom at q8_0) |
| v1.068 | 2026-05-27 | Q5_K_M 64k banner: add KV:q4_0 label so quant is visible at runtime |
| v1.069 | 2026-05-27 | KV quant in all profile names/banners; add [64k · iq4_nl] test profile; revert Q5 64k to q8_0 |
| v1.070 | 2026-05-27 | Remove iq4_nl profile (prefill collapse confirmed); add VRAM limit note to Q5 64k profile |
