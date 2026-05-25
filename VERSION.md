# LSE Version Registry

Single source of truth for component versions, ship dates, and eval coverage.
Updated by the `lse:version-manager` skill whenever a new version ships.

---

## Current Versions

| Component | Version | Shipped | Changelog |
|---|---|---|---|
| Tool | v1.5.5 | 2026-05-25 | tools/openwebui-tool-v1.5.5.py (header) |
| Prompt | v0.5.2 | 2026-05-25 | prompts/CHANGELOG.md |
| Filter | v1.1.0 | 2026-05-23 | tools/lse-routing-filter-v1.1.0.py |
| Context Monitor | v1.0.0 | 2026-05-23 | tools/lse-context-monitor-v1.0.0.py |

---

## Co-test Matrix

Each row is one eval run. "Co-tested" means a full eval suite was run against that
tool + prompt combination and a report was written.

| Eval Run | Tool | Prompt | Score | Report |
|---|---|---|---|---|
| eval-v1 | v1.4.0 | v0.1-baseline | — | eval/eval-report-v1.md |
| eval-v2 | v1.5.1 | v0.4.1 | 45/57 | eval/eval-report-v2.md |
| eval-v3 | — | — | — | eval/eval-report-v3.md (in progress) |

---

## Unpaired Versions

Tool and prompt versions that have shipped but have no eval run against them.
These should be tested before being considered production-ready.

**Tool:** v1.5.2, v1.5.3, v1.5.4, v1.5.5
**Prompt:** v0.5.0, v0.5.1, v0.5.2

> Next planned eval: tool v1.5.5 + prompt v0.5.2

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

### Prompt versions
| Version | Shipped | Key change |
|---|---|---|
| v0.1-baseline | 2026-05-23 | Initial baseline |
| v0.2-structured | 2026-05-23 | Tool use protocol, sudo delegation |
| v0.3-context-aware | 2026-05-23 | Context budget awareness, compaction |
| v0.5 | 2026-05-24 | CONTEXT HANDOVER section |
| v0.5.1 | 2026-05-24 | LIVE SERVICE RULE |
| v0.5.2 | 2026-05-25 | Remove SUDO DELEGATION FORMAT; DO NOT call again; KB path |
