# LSE Session Handover — P19 Start Prompt
> Generated: 2026-06-09 (end of P18 Cowork session)
> Paste this at the start of a new Cowork session.

---

You are resuming work on the **Local System Engineer (LSE)** — a homelab AI agent running inside OpenWebUI on LUCIFER. Read this handover before doing anything.

## Workspace

- Project folder: `C:\Users\SY5\Claude\Projects\local-system-engineer\`
- Deployed config: `/opt/local-se/` (WSL2 on LUCIFER)
- KB: `/opt/local-se/kb/session-learnings.md` — READ THIS before any non-trivial work

## Current Deployed Versions (as of 2026-06-09)

| Component | Version | Notes |
|---|---|---|
| OpenWebUI Tool | **v1.6.1** | `tools/openwebui-tool-v1.6.1.py` — pfSense three-tool arch |
| System Prompt | v0.5.15 | `prompts/v0.5.15.md` |
| Routing Filter | v1.1.0 | Global OFF · Qwen3 preset only |
| Vaultwarden Tool | v1.3.0 | env var wins over valve |
| Launch Script (GUI) | v1.5 | PS7 DispatcherTimer fix |
| pfsense-agent | **v1.0** | `pfsense-agent.py` + `/opt/local-se/pfsense-agent.conf` |
| llama.cpp | b9553 | WSL `/usr/local/bin/llama-server` |

## Architecture

```
LUCIFER (Win11 + WSL2 Ubuntu 24.04, 192.168.1.x)
  OpenWebUI :3000  ←→  LSE Tool Plugin v1.6.1
  llama-server :8080 — Qwen3.6-27B Q4_K_M (64k ctx)

node3090 (Ubuntu 24.04, 192.168.5.41)
  LM Studio :1234 — Qwen3.6-27B Q4_K_M (pfsense-agent target)

pfSense Plus 26.03.1 (pfsense.home.arpa / 192.168.1.50)
  REST API v2.8.0  Auth: X-API-Key header (NOT Bearer)
  Read-only mode ON by default. Toggle in Web UI before writes.

pfsense-agent.py pipeline:
  User NL → Qwen3.6 @node3090:1234 (--think/--no-think)
           → _extract_prompt() [DO NOT block anchor + contiguous step sequence]
           → [y/N confirm] → OpenWebUI /api/chat/completions
           → tool_ids: [lse_system_admin_terminal, lse_vaultwarden_tools]
           → LSE executes → streamed output

OWUI Pipe Function (lse-qwen-pipe) — PLANNED, not yet deployed.
  pipe() → HTTP call to LM Studio :1234 (Qwen3.6 as text generator)
         → stream reasoning into OWUI chat
         → _extract_prompt() → structured LSE prompt
         → LSE model (OWUI internal) → ReAct tool execution fires normally
  Why this works: Qwen3.6 generates text (not FC JSON); LSE handles tools via Chat UI ReAct path.
  Dify: DEFERRED.
```

## Network

```
pfSense
  ├─ LAN  192.168.1.0/24 — LUCIFER, HA Pi (.80), ASUS AP (.1)
  ├─ OPT1 192.168.5.0/24 — node3090 (.41), n45 NAS (.44/.45), Teltonika (.3)
  └─ OPT2 192.168.10.0/24 — failover WAN (disconnected)
DNS: *.home.arpa via pfSense Unbound
```

## pfSense Tool Routing (EXACT — never invent variants)

```
pfsense_graphql(query, api_key)                   → ALL reads
pfsense_query(endpoint, method, payload, api_key) → writes only (POST/PATCH/PUT/DELETE)
pfsense_log_summary(hours, mode, api_key)         → firewall logs only

GraphQL resource names (exact):
  FirewallRule · DHCPServerLease · ARPTable · NetworkInterface · Route · Gateway
  NEVER: firewallRules / getFirewallRules / rules{} / __schema / __type

Step 1 always: vault_unlock() → get_vault_secret("pfsense-api-key") → store as api_key
```

## Critical Rules (permanent — never override)

1. **NTFS + Edit tool truncates Python files >100 lines silently.** Always use:
   ```bash
   cat > /tmp/file.py << 'PYEOF'
   ...
   PYEOF
   python3 -c "import ast; ast.parse(open('/tmp/file.py').read()); print('OK')"
   cp /tmp/file.py /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/file.py
   ```

2. **pfSense SSH is human-only.** `ssh admin@pfsense` = root shell. Never delegate to LSE.

3. **pfSense auth:** `X-API-Key: <key>` — NOT `Authorization: Bearer`.

4. **Elasticsearch is a CORE LSE service.** Never stop or remove it.

5. **No secrets on disk.** LSE retrieves pfSense API key via `vault_unlock()` → `get_vault_secret("pfsense-api-key")` every time.

6. **`^[ \t]*` not `^\s*`** in multiline Python regex — `\s*` swallows preceding newline, breaks step detection. See KB for details.

7. **Vaultwarden tools not always-on.** Pass via `tool_ids` only for pfSense sessions.

## Open Items (priority order)

1. **OWUI pipe function** — `tools/lse-qwen-pipe-v0.1.py`; Valves: LMSTUDIO_URL, LSE_MODEL_ID, THINKING_MODE, CONFIRM_BEFORE_SUBMIT
2. **pfSense DNS audit** (`net-t2-012`) — still needs end-to-end run (OWUI pipe function will be execution path once built)
3. **Grafana :3002 server error** — `docker logs grafana --tail 50`
4. **16-tool-call limit** — investigate OpenWebUI `Max Tool Calls` setting
5. **searxng-error-exporter [P1]** — Panel 24 shows 0; failing engines invisible
6. **NVD custom SearXNG engine** — cvedetails.com VPS blocked, NVD REST API workaround
7. **net-t1-013 Subnet Host Enumeration** / **net-t1-014 pfSense Interface Inventory**
8. **Ground-truth assertion verifier [P0]** — SSH verify_ssh to prevent hallucination in infra challenges
9. **llama.cpp b9555 upgrade** — low risk, minor improvement
10. **Confirm session-learnings.md entry for PS7 DispatcherTimer** — `ls -la /opt/local-se/kb/session-learnings.md` + verify content

## Key Files

```
pfsense-agent.py                        — orchestrator CLI (331 lines)
tools/openwebui-tool-v1.6.1.py          — deployed LSE tool
prompts/v0.5.15.md                      — LSE system prompt
LSEStack_gui/lse-stack-launch-gui.ps1   — GUI launcher v1.5
net-discovery/                          — network observability project (all written, not deployed end-to-end)
scripts/lse_challenge_env.py            — arena challenge runner
CHANGELOG.md                            — full session history
CURRENT-STATE.md                        — deployed versions (source of truth)
ROADMAP.md                              — open items
LSE-ARCHITECTURE.md                     — stack design
/opt/local-se/kb/session-learnings.md  — non-obvious lessons (READ FIRST)
```

## Start-of-Session Checklist

```bash
# In WSL:
cat /opt/local-se/kb/session-learnings.md | tail -60   # recent lessons
ls /opt/local-se/                                       # confirm deployed files
systemctl --user status ollama                          # embeddings
curl -s http://localhost:9200/_cluster/health           # Elasticsearch
curl -s http://localhost:3000/health                    # OpenWebUI
```
