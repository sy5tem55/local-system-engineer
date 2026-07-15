# LSE Valve Registry
> Single source of truth for all MCP/tool valve configuration across LSE tools.
> Update this file whenever a valve is added, removed, or its security posture changes.
> Last updated: 2026-07-15 (Cowork) — TRAUM Thread 4 close: added earn path + queue expiry valves
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

### 4. TRAUM dreaming — `goethe_mcp.py` journaling + `tools/dream_runner.py` + `tools/dream_apply.py`

TRAUM Threads 1-4 complete (`docs/traum-dreaming-plan.md`, `docs/dreaming/DESIGN.md`).
No secrets — every valve here is a path, URL, or numeric threshold. All use
the same `GOETHE_<FIELD>` env-var convention as the rest of the stack.

| Valve | Default | Sensitive | Storage | Notes |
|---|---|---|---|---|
| `EPISODE_DIR` | `/opt/local-se/episodes` | No | Env var OK | `goethe_mcp.py`'s own journaling root (v1.10.0+) — every tool call appends a redacted, 2,000-char-capped JSONL line to `$EPISODE_DIR/YYYY-MM-DD/<session>.jsonl`. **ON by default.** Set `GOETHE_EPISODE_DIR=""` to disable entirely (mirrors the `GOETHE_MCP_TOKEN` empty-disables convention). Also read by `dream_runner.py` (same env var, same directory — it's the corpus the dreamer scans). |
| `DREAM_DIR` | `/opt/local-se/dreams` | No | Env var OK | `dream_runner.py` output root — `$DREAM_DIR/YYYY-MM-DD/{report.md,proposals.jsonl}`, then `dream_apply.py`'s `applied.jsonl`/`rejected.jsonl` alongside them. |
| `TASKS_DB` (dream) | `/opt/local-se/tasks.db` | No | Env var OK | `dream_runner.py`'s own read of the planner ledger. Same variable name as `goethe.py`'s `TASKS_DB` valve (VALVES.md §1) but a distinct env var (`GOETHE_TASKS_DB`) — don't conflate the two paths if they ever diverge per-host. |
| `AGENT_COMMANDS_LOG` | `/opt/local-se/agent_commands.log` | No | Env var OK | `dream_runner.py`'s read of the audit log (Thread 3's audit-log-miner pass will use this too). |
| `DREAM_LLM_URL` | `` (empty) | No | Env var OK | Forced dreamer endpoint, `PLANNER_FORCE_URL`-style — health-probed first; falls through to `NODE3090_LLM_URL` → `NODE3090_OLLAMA_URL` on failure or when unset. Empty = always use the normal cascade. |
| `NODE3090_LLM_URL` (dream) | `http://node3090.home.arpa:8080` | No | Env var OK | Primary llama-server the dreamer drives — same host as the cross-family planner backend, different env var (`GOETHE_NODE3090_LLM_URL`) from `goethe.py`'s own planner valve. |
| `NODE3090_OLLAMA_URL` (dream) | `http://node3090.home.arpa:11434` | No | Env var OK | Ollama CPU fallback for the dreamer cascade. |
| `NODE3090_PLANNER_FALLBACK_MODEL` | `qwen3:4b` | No | Env var OK | Ollama fallback model when both llama-server and any forced `DREAM_LLM_URL` are down. |
| `DREAM_RUNNER_SESSION_PREFIX` | `` (empty) | No | Env var OK | If set, sessions whose `session_id` starts with this are excluded from selection — DESIGN.md §2 invariant 3(e), "no dream-of-dreams." Empty = no filter (the dreamer doesn't run through the MCP gateway today, so it has no `session_id` of its own yet). |
| `DREAM_DEDUP_FLOOR` | `0.75` | No | Env var OK | Candidate-pair cosine floor for the dedup pass — deliberately below the merge threshold so `--sample-labels` has real borderline pairs to show. Provisional pending a full-corpus `--sample-labels` run (see `dream_runner.py`'s own calibration note). |
| `DREAM_DEDUP_THRESHOLD` | `0.92` | No | Env var OK | Merge cosine cutoff for real (non-labeling) dedup runs. Matches `index_to_kb`'s live dedup threshold as a placeholder. |
| `DREAM_ERROR_CLUSTER_THRESHOLD` | `0.80` | No | Env var OK | Cosine floor for grouping error/timeout occurrences into one cluster (error-cluster pass). |
| `DREAM_DIGEST_PATH` | `/opt/local-se/dreams/latest-digest.md` | No | Env var OK | **`goethe.py`'s own valve** (v0.4.0-a, Prompt 3.5) — NOT read by `dream_runner.py`/`dream_apply.py`/`dream_digest.py` (those write the file; this only reads it back). Read once per session, on the first of EITHER `time_check()` or `search_kb`/`search_web` (Thread 3 close fix, 2026-07-12 — `time_check()` previously shared the once-per-session gate without ever reading this valve, silently dropping the `[DREAM]` line for any session that called `time_check()` first). Empty = `[DREAM]` banner disabled. Missing/unreadable/unparseable file = banner silently omitted, never an error. **Live-verified 2026-07-12** against LUCIFER's real gateway and a real digest (6 pending proposals) — confirmed banner text exactly matches the documented format. |
| `DREAM_AUTO_APPLY` | `` (empty) | No | Env var OK | Comma-separated proposal `type`s allowed to skip `dream_apply.py`'s interactive confirm prompt. **Still empty as of TRAUM Thread 2's close (2026-07-11)** — see `docs/dreaming/DESIGN.md` §7 for the full eligibility table and the 2-consecutive-week zero-rejected-in-hindsight promotion bar (Thread 4's to earn, not set by hand). |

**Thread 4 hardcoded values (not env-var gated — change in source if needed):**
- `PROPOSAL_EXPIRY_DAYS = 14` (`dream_apply.py`) — proposals auto-expire after 14 days in `--queue` mode
- `AUTO_APPLY_DB = /opt/local-se/dreams/auto-apply-eval.db` — SQLite eval DB for earn path tracking
- Secret redaction: 3 patterns in `dream_runner.py` (`vault_*`, `get_vault_secret`, `set_vault_secret`) — hardcoded, not configurable

| `PATH` (dream_apply) | alongside `dream_apply.py` | No | Env var OK | `GOETHE_PATH` — where `dream_apply.py` dynamically loads `goethe.py`'s `Tools` class from (same mechanism `goethe_mcp.py` uses). |
| `REPO_ROOT` | current working directory | No | Env var OK | `GOETHE_REPO_ROOT` (Prompt 3.6) — repo root `dream_apply.py`'s `append_learned_rule()` resolves `prompts/learned-rules.md` against. Run `dream_apply.py` from the repo root (same assumption its own usage examples already make with relative `--proposals` paths) or set this explicitly. |

`ES_URL` / `OLLAMA_URL` / `EMBED_MODEL` are shared with `goethe.py`'s own
valves (§1 above) — `dream_runner.py` and `dream_apply.py` read the same
`GOETHE_ES_URL`/`GOETHE_OLLAMA_URL`/`GOETHE_EMBED_MODEL` env vars, not
separate dream-specific copies.

No action required for any valve in this section — none carry secrets.

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
