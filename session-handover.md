# Session Handover — 2026-06-03 (LSE Stack Session)

## Stack Versions at Close
| Component | Version |
|-----------|---------|
| Tool | v1.5.13 |
| Prompt | v0.5.11 (deployed ✅) |
| Routing filter | v1.1.0 |
| Context monitor | retired |
| llama-server | Qwen3.6-27B-Q4_K_M · build b9464 · 64k · KV q8_0 · budget 3072 |
| Test suite | v3.5 (A1 redesigned — port collision test) |

## What Was Completed This Session
- Run 6 eval: **58/63** (52/57 adjusted) — eval-report-v5.md written
- SearXNG 27-engine config live in production
- SearXNG metrics pipeline fixed: `general.open_metrics` added, Prometheus scrape healthy
- Grafana dashboard updated and deployed (engine filter variable, error panels)
- Limiter disabled, Valkey redis section confirmed present
- ROADMAP, CURRENT-STATE, test-suite-v3.5 all updated

## What Needs Doing Next (Priority Order)

### 1. Credential Rotation (URGENT — passwords exposed this session)
Use this LSE prompt in a fresh conversation:
```
Rotate the Grafana admin password and the SearXNG metrics scrape password. Full sequence:
1. Generate two strong random passwords (use openssl rand -base64 24)
2. Update Grafana admin password via the API: POST /api/user/password
3. Update open_metrics password in /home/sy5/docker/searxng_data/settings.yml
4. Update the basic_auth password in the Prometheus config (find the file first)
5. Restart both searxng and prometheus containers
6. Verify: curl the /metrics endpoint with the new password, curl the Prometheus targets API and confirm searxng health is "up"
7. Report all new passwords clearly at the end so I can update Vaultwarden
8. Index the full procedure into the KB via index_to_kb: title "Grafana + SearXNG metrics password rotation procedure", topic "infrastructure", include the exact commands used

Stop and wait for me after each sudo delegation block.
```

### 2. Prompt v0.5.12 + Tool v1.5.14 — three protocol fixes
- MULTI-BLOCK TASK: emit `── Step N/Total: [description] ──` before each step
- sudo_delegation_block must never be called inside the thinking phase (gets buried in collapsed think block in OpenWebUI)
- sudo_delegation_block presentation: add step indicator, surface verify command explicitly
See ROADMAP for full spec.

### 3. Network hygiene — pfSense
- Samsung TV (192.168.1.90): WAN block + static DHCP mapping
- Backup config.xml before any changes

### 4. Run 7 prep
Fix these gaps from Run 6 before running:
- P4: pipeline-position sudo explanation + split offer
- M3: file-not-found recovery proposal
- W1: no tool calls for static Linux knowledge
Bump prompt to v0.5.12 after fixes, then run full v3.5 suite.

## Key Paths
- Settings: `/home/sy5/docker/searxng_data/settings.yml`
- Prometheus config: find via `find /home/sy5 -name "prometheus.yml"`
- Project root: `C:\Users\SY5\Claude\Projects\local-system-engineer\`
- Grafana: `http://localhost:3002` (port 3002 on host)
- SearXNG: `http://localhost:8088`
- Grafana service account: `lse-sync` (needs Editor role upgrade)

## Known Issues
- Grafana `lse-sync` service account has Viewer role — cannot deploy dashboards via API key. Upgrade to Editor in Admin → Service accounts.
- searxng-logger still broken (polls Prometheus with wrong logic) — backlog item
- open-webui has no systemd unit — A3 eval test journalctl always empty

## Session Start Checklist
1. Read CURRENT-STATE.md — reconcile versions
2. Read ROADMAP.md — credential rotation is top priority
3. Confirm llama-server running: `curl -s localhost:8080/health`
4. Confirm SearXNG metrics live: `curl -s -u ":metrics-admin-2025" http://localhost:8088/metrics | head -3`
   (note: password may have been rotated — check Vaultwarden first)
