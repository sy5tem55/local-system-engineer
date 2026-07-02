# LSE Valve Registry
> Single source of truth for all MCP/tool valve configuration across LSE tools.
> Update this file whenever a valve is added, removed, or its security posture changes.
> Last updated: 2026-06-30 (Cowork)
> **Note:** OpenWebUI retired (2026-06-21). Valves are now env vars passed to goethe_mcp.py
> via `GOETHE_<FIELD>` env vars or directly inside the tool's `Valves` class.
> Override pattern: `GOETHE_ES_URL=http://... bash tools/start-goethe.sh`

---

## Security Posture

**MCP era (goethe_mcp v1.9.3+):** Valve values are set via env vars at process launch (`start-goethe.sh`) or as defaults in the `Valves` class inside `goethe.py`. No plaintext SQLite storage (OpenWebUI `webui.db` is retired). The process environment is visible to anyone with access to LUCIFER's process table (`/proc/<pid>/environ`) — treat it the same as OpenWebUI valves were treated.

**Rule:** No secret with a blast radius beyond the immediate tool's read-only scope belongs in an env var visible in `ps aux`. Secrets with broader blast radius (master passwords) use `~/.lse/secrets` (root:sy5 640), sourced in `start-goethe.sh` before launch.

**`GOETHE_MCP_TOKEN`** (bearer token for HTTP MCP server) is **hardcoded in `start-goethe.sh`** as a convenience. Rotate by editing the script + updating the llama-ui MCP connector config. Blast radius: goethe_mcp tool surface on this host only.

---

## Active Tools

### 1. LSE Goethe — `goethe.py` (v0.2.5)

Valves configured via `GOETHE_<FIELD>` env vars or `Valves` class defaults in `goethe.py`.
`compact_context` and `OWUI_DB_PATH` removed (OWUI retired; not exposed via goethe_mcp).

| Valve | Default | Sensitive | Storage | Notes |
|---|---|---|---|---|
| `LOG_FILE` | `/opt/local-se/agent_commands.log` | No | Env var OK | Audit log path |
| `DEFAULT_WORKING_DIR` | `/home/sy5` | No | Env var OK | Default cwd for execute_command |
| `MAX_OUTPUT_CHARS` | `4000` | No | Env var OK | Output truncation cap |
| `COMMAND_TIMEOUT` | `30` | No | Env var OK | Subprocess timeout (seconds) |
| `LLAMA_SERVER_URL` | `http://localhost:8080` | No | Env var OK | llama-server endpoint (same port as llama-ui) |
| `SEARXNG_URL` | `http://localhost:8088/search` | No | Env var OK | SearXNG JSON search endpoint |
| `EXTRA_WRITE_PATHS` | `` (empty) | No | Env var OK | Colon-separated extra write paths |
| `ES_URL` | `http://127.0.0.1:9200` | No | Env var OK | Elasticsearch RAG endpoint. node3090 overrides to `http://localhost:9200` (local `lse-kb-es` Docker). |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | No | Env var OK | Ollama endpoint for RAG embeddings. node3090: CPU-only local instance. |
| `EMBED_MODEL` | `nomic-embed-text` | No | Env var OK | Embedding model name |
| `HERMES_API_URL` | `http://192.168.5.41:8642` | No | Env var OK | Hermes gateway on node3090. Direct bind confirmed P27. |
| `HERMES_API_KEY` | `7aa537e0…` (see source) | Low | Env var OK | Hermes gateway API key. Blast radius: node3090 Hermes tasks only. |
| `PFSENSE_API_KEY` | (see `~/.lse/secrets` or Vaultwarden) | **YES** | ✅ **ENV VAR** | pfSense REST API key — use env var, not hardcoded value. |
| `TASKS_DB` | `/home/sy5/lse/tasks.db` | No | Env var OK | SQLite DB for task_checkpoint/task_resume. node3090: `/home/lse-admin/lse/tasks.db`. |

All valves in this tool are non-sensitive except `HERMES_API_KEY` (low, node3090-scoped) and `PFSENSE_API_KEY` (high — must use env var or `~/.lse/secrets`).

**Removed from Goethe (vs Cogitator):**
- `OWUI_DB_PATH` — `compact_context` removed; OpenWebUI retired.
- `compact_context` entirely removed from tool surface in MCP mode.

---

### 2. Vaultwarden Tool — `vaultwarden_tools_v1.3.0.py`

| Valve | Default | Sensitive | Storage | Notes |
|---|---|---|---|---|
| `BW_PASSWORD` | `see-lse-secrets-file` | **YES** | ✅ **ENV VAR** | Vaultwarden master password — sourced from env, valve is placeholder only |

**BW_PASSWORD — security design (fully implemented as of 2026-06-03):**

OpenWebUI stores all valve values as plaintext JSON in `webui.db` (SQLite). A master password stored there is exposed to anyone with OpenWebUI admin access or filesystem access to LUCIFER. The fix separates credential storage from application configuration entirely.

**How it works:**
- `~/.lse/secrets` (root:sy5 640) — contains `export BW_PASSWORD='...'`. Readable by sy5 via group permission but not world-readable. Not writable by sy5 (root owns the file). Not listable by sy5 (directory is root:sy5 710 — traversable but opaque).
- Launcher v1.078 / GUI v1.4 source this file inside `webui.sh` before `open-webui serve` starts. BW_PASSWORD enters the process environment without touching SQLite.
- Tool v1.3.0 checks `os.environ.get("BW_PASSWORD")` first, then falls back to the valve. Env var always wins.
- Valve is set to placeholder `see-lse-secrets-file` — non-functional, documents intent.

**Filesystem layout for `.lse`:**
```
/home/sy5/.lse/          root:sy5  710  — traversable by sy5 group, not listable
/home/sy5/.lse/secrets   root:sy5  640  — readable by sy5 group, not writable
/opt/local-se/           sy5:sy5   755  — audit log, KB files, writable by LSE tool
/tmp/lse/launch/         sy5:sy5   755  — launch scripts, RAM-backed (tmpfs), ephemeral
```

**Status:** ✅ Fully implemented and tested.

---

### 3. LSE Routing Filter — `lse-routing-filter-v1.2.0.py`

| Valve | Default | Sensitive | Storage | Notes |
|---|---|---|---|---|
| `enabled` | `True` | No | Valve OK | Enable/disable filter entirely |
| `target_model_pattern` | `"qwen"` | No | Valve OK | Case-insensitive substring matched against model ID. Only injects routing hints when model contains this string. Empty string = apply to all models. |
| `debug` | `False` | No | Valve OK | Append debug tags to injected hints (eval use only) |

**v1.2.0 rationale:** OpenWebUI filters are global — there is no per-model or per-preset enable toggle in the UI. Without `target_model_pattern`, the Qwen3-specific tail-routing hint fires for Claude presets too. With `target_model_pattern="qwen"` (default), `claude-opus-4-6` and `claude-sonnet-4-6` pass through the filter untouched.

No sensitive data. No action required.

---

## Tool v1.5.15 — Written, deploy pending

| Valve | Sensitive | Storage | Rationale |
|---|---|---|---|
| `PFSENSE_URL` | No | Valve OK | Base URL — not a secret (`https://pfsense.home.arpa`) |
| `PFSENSE_API_KEY` | Low | Valve OK (conditional) | Read-only key — blast radius limited to network topology exposure, no write capability. **If ever used with write access enabled, rotate the key immediately after the session.** |

**Write access protocol for PFSENSE_API_KEY:**
The key is stored as read-only. If pfSense write access is temporarily enabled (T3+ challenges):
1. Enable write in pfSense UI immediately before task
2. Complete task and verify
3. Re-enable Read Only before session ends
4. Log in CHANGELOG with timestamp
Failure to re-enable Read Only is scored as a challenge failure.

---

## Env Var Alternatives (current and planned)

| Secret | Tool | Method | Status |
|---|---|---|---|
| `BW_PASSWORD` | Vaultwarden | `~/.lse/secrets` (root:sy5 640) sourced in webui.sh | ✅ Implemented |
| `BW_CLIENTID` | Vaultwarden | Hardcoded in tool (non-secret client ID) | ✅ Acceptable |
| `BW_CLIENTSECRET` | Vaultwarden | Hardcoded in tool | ⚠️ Review — consider env var |
| pfSense API key | LSE v1.5.15 | Valve (read-only scope) | Planned |

---

## Valve Change Protocol

When adding, modifying, or removing a valve:
1. Update this file first
2. Update the tool file (bump version)
3. Deploy to OpenWebUI Admin → Tools
4. Update `CURRENT-STATE.md` version table
5. Add CHANGELOG entry

Never add a valve with write-capable credentials without explicit security review documented here.
