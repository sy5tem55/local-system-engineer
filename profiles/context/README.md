# profiles/context/ — just-in-time context files (v0.7.0)

These files hold prompt sections that were moved OUT of the always-on BASE
prompt (ablation: section-level failure traceability, task 1bfb3e45, 2026-09-19).
Each file costs 0 tokens until read.

## Trigger table

| File | Read it when |
|------|--------------|
| `pfsense_log_rule.md` | Any pfSense log question: firewall blocks, 'what is the firewall seeing', DHCP/system logs, gateway tooling. |
| `web_search_budget_fallback.md` | `search_web` reports the budget exhausted and the task still needs fetched content (node3090 firecrawl/camoufox/A2A routing). |
| `traum.md` | Any TRAUM / dream-cycle work: cycles, proposals, Human Gate, attempt states, `traum-state.db`, the console. |

## Rules

- Read the file BEFORE acting on the topic; do not answer from memory of the
  moved section.
- The BASE prompt's JIT CONTEXT FILES block lists these triggers; the files
  here are the authoritative content.
- Safety stubs that MUST stay in context regardless of trigger (e.g. 'NEVER
  apply a TRAUM proposal yourself') remain in BASE on purpose.

## Provenance

- Extracted verbatim from `/home/sy5/lse/work/v0.7.0/v0.6.3-canonical.md`
  (live L2 body + L1 header).
- Backup of all pre-v0.7.0 artifacts: `/home/sy5/lse/bkp/v0.7.0-pre-20260919_132657/`.
