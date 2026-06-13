# LSE Valve Registry
> Single source of truth for all OpenWebUI valve configuration across LSE tools.
> Update this file whenever a valve is added, removed, or its security posture changes.
> Last updated: 2026-06-13 (P27 Cowork)

---

## Security Posture

OpenWebUI **does not encrypt valve values at rest**. All valve values are stored as plaintext JSON
in `webui.db` (SQLite). Anyone with filesystem access to LUCIFER or OpenWebUI admin credentials
can read every valve value.

**Rule:** No secret with a blast radius beyond the immediate tool's read-only scope belongs in a valve.
Secrets that unlock broader access (master passwords, write-capable API keys) must use env vars instead.

---

## Active Tools

### 1. LSE Cogitator — `cogitator-v1.7.14.py`

| Valve | Default | Sensitive | Storage | Notes |
|---|---|---|---|---|
| `LOG_FILE` | `/opt/local-se/agent_commands.log` | No | Valve OK | Audit log — moved from `~/.lse/` (root-owned, inaccessible to sy5) to /opt/local-se/ |
| `DEFAULT_WORKING_DIR` | `/home/sy5` | No | Valve OK | Default cwd for execute_command |
| `MAX_OUTPUT_CHARS` | `4000` | No | Valve OK | Output truncation cap |
| `COMMAND_TIMEOUT` | `30` | No | Valve OK | Subprocess timeout (seconds) |
| `LLAMA_SERVER_URL` | `http://localhost:8080` | No | Valve OK | llama-server endpoint |
| `SEARXNG_URL` | `http://localhost:8088/search` | No | Valve OK | SearXNG JSON search endpoint |
| `EXTRA_WRITE_PATHS` | `` (empty) | No | Valve OK | Colon-separated extra write paths |
| `OWUI_DB_PATH` | `/home/sy5/owui/lib/...webui.db` | No | Valve OK | OpenWebUI SQLite path for compact_context |
| `ES_URL` | `http://127.0.0.1:9200` | No | Valve OK | Elasticsearch RAG endpoint |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | No | Valve OK | Ollama endpoint — used for RAG embeddings AND pfsense_log_summary anomaly narrative (llama3.2:3b) |
| `EMBED_MODEL` | `nomic-embed-text` | No | Valve OK | Embedding model name |
| `HERMES_API_URL` | `http://192.168.5.41:8642` | No | Valve OK | Hermes gateway on node3090. Binds 0.0.0.0:8642 directly (confirmed P27: `ss -tlnp` + HTTP 200 from LUCIFER). socat :8643→:8642 workaround eliminated in v1.7.14. |
| `HERMES_API_KEY` | `7aa537e0…` (see source) | Low | Valve OK | Hermes gateway API key. Blast radius: node3090 Hermes tasks only. Key validated P27 (HTTP 200). Second key `PFIStFD_yp…` in Vaultwarden — likely stale; reconcile before retiring. |

All valves in this tool are non-sensitive (localhost URLs, paths, integers) except HERMES_API_KEY which is low-sensitivity (node3090-scoped). No action required.

**Audit log path change:** default updated from `/home/sy5/.lse/agent_commands.log` to `/opt/local-se/agent_commands.log`. The `.lse` directory is now root:sy5 710 — sy5 can traverse it to read the secrets file but cannot write new files into it. The audit log (written every tool call) must live in a sy5-writable path. Update the `LOG_FILE` valve in OpenWebUI to match if not yet redeployed.

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
