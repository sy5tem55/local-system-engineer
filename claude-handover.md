# Claude Session Handover
**Date:** 2026-05-28  
**Project:** local-system-engineer (LSE)  
**Repo:** C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\

---

## Current component versions (all committed, deployed)

| Component | Version | File |
|---|---|---|
| Tool | v1.5.7 | tools/openwebui-tool-v1.5.7.py |
| Prompt | v0.5.3 | prompts/v0.5.3.md |
| Routing filter | v1.1.0 | tools/lse-routing-filter-v1.1.0.py |
| Context monitor filter | v1.3.0 | tools/lse-context-monitor-v1.3.0.py |
| Launcher | v1.070 | lse-stack-launch-1.070.ps1 |
| Test suite | v3.5 | eval/test-suite-v3.5.md |

All deployed to OpenWebUI. ROADMAP.md and VERSION.md are up to date.

---

## What we decided this session

### Context monitoring: scrap the filter, replace with Grafana alert

The `lse-context-monitor-v1.3.0.py` filter (OpenWebUI inlet filter) has been
the main context monitoring mechanism. After discussion, the user has decided to:

1. **Abandon the filter entirely.** The CONTEXT HANDOVER protocol in the prompt
   has never worked reliably. The model does not consistently initiate autonomous
   handover even with the filter injecting signals.

2. **Replace with Grafana → OpenWebUI Channel Webhook.** The `llama_kv_cache_usage_ratio`
   Prometheus metric (exposed by llama-server `--metrics` at `http://localhost:8080/metrics`)
   is already scraped by Grafana. A Grafana alert on `> 0.8` (80%) will POST to an
   OpenWebUI channel webhook, delivering a visible channel notification to the user.

3. **Simplify the prompt.** Once the filter is gone, the CONTEXT HANDOVER section
   of the prompt should be reduced to a minimal fallback (user manually triggers
   handover), and `get_context_status` can be removed or kept only as an explicit
   user request tool.

### Why this is better

- `llama_kv_cache_usage_ratio` is a pure ratio — alert fires at 80% regardless
  of whether the active profile is 32k or 64k. No valve config per profile.
- Grafana is already running and scraping the endpoint. Marginal setup cost.
- OpenWebUI Channel Webhooks are designed exactly for this: "Post alerts from
  monitoring tools (Prometheus, Grafana) directly into team channels."
- Decouples context monitoring from the model entirely — no model compliance risk.

---

## Immediate next task: set up Grafana → OpenWebUI channel alert

### What the user has already done / confirmed

- Grafana is running (scraping `http://localhost:8080/metrics`)
- A Grafana API key has been generated and stored in Vaultwarden
- The user knows OpenWebUI has a channel webhook feature (confirmed from docs)

### What still needs to happen

**Step A — User does in OpenWebUI UI (cannot be delegated to LSE, no browser access):**
1. Create a channel (suggested name: `lse-alerts`)
2. ⋮ → Edit Channel → Webhooks → Manage → New Webhook
3. Name it `Grafana Context Monitor`, save, copy the webhook URL
4. Provide Claude with: the webhook URL and the Grafana API key from Vaultwarden

**Step B — LSE or Claude sets up Grafana side via API:**
Grafana HTTP API is at `http://localhost:3000` (verify port — may differ).
With the API key, the following can be done via `curl` from WSL2:

1. Create a Webhook contact point:
```bash
curl -X POST http://localhost:3000/api/v1/provisioning/contact-points \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenWebUI LSE Alerts",
    "type": "webhook",
    "settings": {
      "url": "<OPENWEBUI_CHANNEL_WEBHOOK_URL>",
      "httpMethod": "POST",
      "contentType": "application/json",
      "message": "{\"content\": \"⚠ LSE context at {{ index $values \"A\" }}% — start a fresh conversation.\"}"
    }
  }'
```

2. Create an alert rule on `llama_kv_cache_usage_ratio > 0.8`:
   - Datasource: Prometheus (already configured)
   - Metric: `llama_kv_cache_usage_ratio`
   - Condition: `> 0.8`
   - Evaluation interval: 1 minute
   - Contact point: OpenWebUI LSE Alerts

3. Verify alert fires by temporarily lowering threshold to `> 0.1`, confirming
   the channel message appears in OpenWebUI, then restoring to `> 0.8`.

**Step C — Prompt cleanup (after alert is confirmed working):**
- Retire `lse-context-monitor-v1.3.0.py` from OpenWebUI (disable or remove)
- Write prompt v0.5.4: remove CONTEXT HANDOVER section (or reduce to 3 lines),
  simplify `get_context_status` to "call only if user explicitly asks"
- Update VERSION.md: bump Prompt to v0.5.4, mark Context Monitor as decommissioned
- Update ROADMAP.md: move Grafana alert to Completed, note filter retirement

**Step D — Documentation:**
- Add Grafana/Prometheus section to `docs/07-operations-runbook.md` (flagged
  as pending since the Grafana dashboard was built 2026-05-26)
- Optionally update `docs/03-context-management.md` to reflect new architecture

---

## Grafana environment notes (verify at session start)

- Grafana port is likely 3000 but could differ — check with `ss -tlnp | grep grafana`
  or `systemctl status grafana-server`
- Prometheus scrape config is already targeting `localhost:8080/metrics`
- The `llama_kv_cache_usage_ratio` metric is confirmed present (used by v1.3.0 filter)
- llama-server started with `--metrics` flag (added in launcher v1.063)

---

## Other pending items (lower priority)

- **Run 6** — full 21-question eval against corrected stack (tool v1.5.7 + prompt v0.5.3
  + context monitor v1.3.0 + test-suite v3.5). Pre-flight checklist in ROADMAP.md.
  Note: if filter is retired before Run 6, the stack definition changes — Run 6 would
  be tool v1.5.7 + prompt v0.5.4 (no filter). Decide whether to run with v0.5.3 first
  or skip straight to v0.5.4.

- **README.md update** — still references old versions (Gemma 4, v0.3 prompt).

- **docs/07-operations-runbook.md** — Grafana/Prometheus section missing.

---

## Key file paths (WSL2)

```
OpenWebUI tools:   Admin → Tools (UI only, no filesystem path)
OpenWebUI filters: Admin → Functions (UI only)
Launcher:          /mnt/c/Users/SY5/Documents/Claude/Projects/local-system-engineer/
Prompts:           /mnt/c/Users/SY5/Documents/Claude/Projects/local-system-engineer/prompts/
Docs:              /mnt/c/Users/SY5/Documents/Claude/Projects/local-system-engineer/docs/
KB:                /opt/local-se/kb/
Session handover:  /opt/local-se/session-handover.md
llama-server:      /home/sy5/llama.cpp/build/bin/llama-server
Metrics endpoint:  http://localhost:8080/metrics
Grafana:           http://localhost:3000 (verify port)
```

---

## strip-sig workflow (needed before any .ps1 edit)

Always run before editing the launcher:
```powershell
# In PS7 terminal, from the launcher directory:
.\strip-sig.ps1 -Path .\lse-stack-launch-1.070.ps1

# After editing, verify parse is clean:
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path .\lse-stack-launch-1.070.ps1).Path, [ref]$null, [ref]$errors)
$errors   # should be empty

# Then re-sign:
.\certsign.ps1 -Path .\lse-stack-launch-1.070.ps1
```
Note: `$errors = $null` pre-declaration is required before `[ref]$errors` — PS7 throws
`InvalidOperation: [ref] cannot be applied to a variable that does not exist` otherwise.
