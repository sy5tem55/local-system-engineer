# STACK MAP — pinned planner ground truth
> Auto-attached to every planner() call (goethe.py `_augment_context_with_kb_inner`).
> Keep ≤60 lines. Update on every stack change.
> Last verified: 2026-07-31 (live probes, session debrief same date)

## DECOMMISSIONED — never reference in plans
- OpenWebUI (:3000) — decommissioned 2026-07-17. No `openwebui-tool-v*.py` exists anywhere.
- Ollama planner fallback — removed v0.4.5 (dead CPU path, valves kept but unused)
- Gemma local planner fallback — /opt/models/lmstudio-community does not exist; path is dead by decision 2026-07-30 (leave documented-dead)

## LIVE
- Goethe tool surface: /home/sy5/projects/local-system-engineer/tools/goethe.py
  served via goethe_mcp.py (MCP). Env file: /opt/local-se/goethe-mcp.env
- Console/gateway: :9700 (goethe_ui, python). Task ledger: /opt/local-se/tasks.db
- llama-server LUCIFER :8080 (Qwen3.6-27B, 131k ctx)
- node3090 llama-server :8080 = planner local primary (240s budget); SSH lse-admin@node3090.home.arpa
- node5090 llama-server :8081 (STALE — LM Studio not yet migrated; verify via check_node_agent_drift when awake)
- Planner backends: `local | chatgpt | claude | rest` only. claude → claude-opus-5
  via Claude Code CLI, timeout valve PLANNER_CLI_TIMEOUT_S=900. Selection persists
  in /opt/local-se/state/planner-backend.json (Console beats env).
- Prometheus :9090 · Grafana LUCIFER:3002 (v13) · Firecrawl node3090:3002 (browser rendering, reddit fallback) — same port, different hosts; use FIRECRAWL_URL / FIRECRAWL_REMOTE_URL valves · Elasticsearch :9200 · SearxNG :8088
- pfSense Plus REST API v2 @ pfsense.home.arpa (x-api-key header, not Bearer)
- KB: /opt/local-se/kb/ · learnings: /opt/local-se/kb/session-learnings.md · state: /opt/local-se/state/ · backups: /opt/local-se/bkp/

## RULES FOR PLANNERS
- If this file conflicts with LSE-ARCHITECTURE.md, this file wins (arch doc partially predates the OWUI decommission).
- Tool-file edits: backup to /opt/local-se/bkp/ first, py_compile after, restart goethe-mcp to load.
- MCP transport ceiling ≈60s: long planner runs still land in the ledger; recover via task_resume().
