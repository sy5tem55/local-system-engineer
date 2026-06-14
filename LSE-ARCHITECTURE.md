# LSE Architecture — Technical Design Document
> Version: 2026-06-13 (aligned with Cogitator v1.7.13)
> Audience: coder LLM (node3090 agent) proposing changes + Claude Sonnet 4.6 as senior reviewer
> Read alongside: CURRENT-STATE.md, session-handover.md, ROADMAP.md

---

## 1. What the LSE Is

The **Local System Engineer (LSE)** is a homelab AI agent running inside OpenWebUI on LUCIFER. It manages a self-hosted infrastructure stack via a Python tool plugin. The model (Qwen3.6-27B-Q4_K_M, 64k context) receives a system prompt and has access to a single tool class that exposes shell execution, file I/O, web search, a knowledge base, pfSense API access, and GPU node lifecycle management.

The LSE is **not** a chatbot. It is an autonomous infrastructure operator with bounded, audited permissions. Every action it takes is logged. Privileged operations require human approval via a structured delegation protocol.

---

## 2. Stack Components

```
┌─────────────────────────────────────────────────────────────┐
│  LUCIFER (Win11 + WSL2 Ubuntu 24.04, 192.168.1.x)           │
│                                                             │
│  OpenWebUI (:3000)  ←→  LSE Cogitator (v1.7.13)            │
│       │                        │                           │
│  Qwen3.6-27B-Q4_K_M            ├─ execute_command (WSL2)   │
│  llama-server :8080            ├─ Elasticsearch :9200 (KB) │
│                                ├─ Ollama :11434 (embeddings)│
│                                ├─ SearxNG :8088 (via VPS)  │
│                                └─ pfSense REST API          │
│                                                             │
│  Grafana (:3001) + Prometheus (:9090)                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  node3090 (Ubuntu 24.04, 192.168.5.41)                      │
│  RTX 3090 24GB · driver 595 · CUDA 13.3                     │
│  llama-server :8080 — Qwen3.6-27B Q4_K_M (96k ctx, q8_0 KV)│
│  Hermes gateway :8642 — 0.0.0.0 direct (socat removed P27) │
│  SSH: lse-admin@node3090.home.arpa (FQDN required)          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  pfsense-agent.py  (LUCIFER WSL2, /opt/local-se/)           │
│  Qwen3.6 orchestrator → structured LSE prompt               │
│                                                             │
│  User NL request                                            │
│       ↓                                                     │
│  Qwen3.6-27B @ node3090:8080  (--think or --no-think)       │
│       ↓  _extract_prompt() — DO NOT anchor + step sequence  │
│  LSE prompt (numbered steps, DO NOT block)                  │
│       ↓  [y/N confirm or --auto]                            │
│  OpenWebUI /api/chat/completions                            │
│       tool_ids: [lse_system_admin_terminal,                 │
│                  lse_vaultwarden_tools]                     │
│       ↓                                                     │
│  LSE executes → streamed output                             │
│                                                             │
│  Config: /opt/local-se/pfsense-agent.conf (chmod 600)       │
│  Note: API tool execution gap — OWUI Chat UI uses ReAct     │
│  text-based tool invocation; API path needs native FC JSON  │
│  that local Qwen3.6 does not emit. Dify adopted instead.    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OWUI Pipe Function (lse-qwen-pipe — planned)               │
│  Runs server-side inside OpenWebUI as a pipe/model.         │
│                                                             │
│  User message (OWUI chat)                                   │
│       ↓                                                     │
│  pipe() — HTTP call to LM Studio :1234                      │
│       Qwen3.6: reasoning streamed into chat as text         │
│       _extract_prompt() — DO NOT anchor + step sequence     │
│       ↓                                                     │
│  structured LSE prompt → LSE model (OWUI internal)          │
│       LSE ReAct tool execution fires normally               │
│       ↓                                                     │
│  streamed output in same chat session                       │
│                                                             │
│  Why pipe works: Qwen3.6 is a text generator here,          │
│  not a tool-calling model. FC JSON gap is irrelevant.       │
│  Status: planned — not yet deployed.                        │
│  Dify: DEFERRED.                                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  pfSense Plus 26.03.1 (pfsense.home.arpa)                   │
│  REST API v2.8.0 · base: https://pfsense.home.arpa/api/v2  │
│  Auth: x-api-key header (NOT Authorization: Bearer)         │
│  Read Only mode: Web UI toggle before any POST              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  VPS (external)                                             │
│  SearxNG (Docker) — metasearch proxy, randomised UA         │
│  Reddit engine BLOCKED on VPS IP — use site:reddit.com      │
└─────────────────────────────────────────────────────────────┘
```

### Network Topology
```
Internet → pfSense
              ├─ LAN  192.168.1.x  — LUCIFER, HA Pi (.80)
              ├─ OPT1 192.168.5.x  — node3090 (.41), n45 (.44/.45)
              └─ OPT2 192.168.10.x — (IoT/WiFi — topology pending discovery)
```
DNS: `*.home.arpa` via pfSense Unbound. Always use FQDNs.

---

## 3. Tool Plugin Architecture

**File**: `tools/cogitator-vX.X.X.py`
**Class**: `Tools` (single class, OpenWebUI convention)
**Config**: `Tools.Valves` (Pydantic BaseModel — user-configurable in OpenWebUI UI)

### 3.1 Valves (Configuration)

| Valve | Default | Purpose |
|---|---|---|
| `LOG_FILE` | `/opt/local-se/agent_commands.log` | Audit log for all tool calls |
| `DEFAULT_WORKING_DIR` | `/home/sy5` | cwd for execute_command |
| `MAX_OUTPUT_CHARS` | 4000 | Truncation limit for command output |
| `COMMAND_TIMEOUT` | 30 | Subprocess timeout (seconds) |
| `LLAMA_SERVER_URL` | `http://localhost:8080` | Local llama.cpp server |
| `SEARXNG_URL` | `http://localhost:8088/search` | SearxNG JSON endpoint |
| `EXTRA_WRITE_PATHS` | `""` | Colon-separated additional write paths |
| `OWUI_DB_PATH` | `/home/sy5/owui/.../webui.db` | OpenWebUI SQLite DB (compact_context) |
| `ES_URL` | `http://127.0.0.1:9200` | Elasticsearch (KB) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama embeddings |
| `EMBED_MODEL` | `nomic-embed-text` | 768-dim embedding model |
| `PFSENSE_URL` | `https://pfsense.home.arpa` | pfSense base URL |
| `PFSENSE_API_KEY` | `""` | pfSense REST key (read-only default) |
| `PFSENSE_CA_CERT` | `/opt/local-se/cert/pfsense-webgui-ca.crt` | TLS CA cert |

### 3.2 Permission Model

**Read paths** (hardcoded allowlist):
```python
_ALLOWED_READ_PREFIXES = ["/home/", "/etc/", "/var/log/", "/tmp/lse/", "/opt/local-se/"]
```

**Write paths** (hardcoded allowlist):
```python
_ALLOWED_WRITE_PREFIXES = ["/home/", "/tmp/lse/", "/opt/local-se/"]
```

**Blocked commands** (substring match, no exceptions):
```
mkfs, fdisk, parted, sgdisk, wipefs, dd if=, of=/dev/, rm -rf, rm -fr,
:(){ :|, userdel, groupdel, passwd, visudo, iptables -F
```

**Privileged prefixes** (route to sudo_delegation_block):
```
sudo, su, doas
```

**Privileged write paths** (blocked even with valid write prefix):
```
/etc/, /usr/, /boot/, /sys/, /proc/, /mnt/
```

---

## 4. Tool Functions Reference

### 4.1 Shell & File I/O

| Function | Signature | Purpose |
|---|---|---|
| `execute_command` | `(command, working_dir="")` | Runs shell command in WSL2. Blocked list enforced. Output capped at MAX_OUTPUT_CHARS. All calls logged. |
| `read_file` | `(path, max_lines=100, offset_lines=0)` | Reads file within allowed read paths. |
| `write_file` | `(path, content, append=False)` | Writes within allowed write paths. Blocks privileged write paths. |
| `sudo_delegation_block` | `(command, reason, risk_level)` | Structures a sudo request for human approval. Does NOT execute. Prints a formatted block for the human to run manually. |

**SUDO EXEMPTION**: `shutdown_node` and `start_node_agent` run sudo **remotely** via SSH on target nodes. Do NOT call `sudo_delegation_block` for these — the sudo runs on the remote node, not LUCIFER.

### 4.2 pfSense

| Function | Signature | Purpose |
|---|---|---|
| `pfsense_query` | `(method, endpoint, body=None, api_key="")` | pfSense REST API. Auth via `x-api-key` header. Read-only by default. POST requires human to disable Read Only in Web UI first. |
| `pfsense_log_summary` | `(log_type, max_entries=50, filter_str="")` | Compact extraction of firewall/DHCP/system logs. |
| `nmap_summary` | `(target, flags="", max_lines=100)` | Runs nmap, returns structured summary. |

**pfSense rules**:
- Base URL: `https://pfsense.home.arpa/api/v2` (NOT bare IP)
- Auth: `x-api-key` header (NOT `Authorization: Bearer`)
- SSH to pfSense is **human-only** — gives root shell, bypasses all API boundaries
- Read Only toggle: `System → REST API → Read Only` — disable before POST, re-enable immediately after

### 4.3 Web & Research

| Function | Signature | Purpose |
|---|---|---|
| `search_web` | `(query, max_results=5)` | SearxNG metasearch. KB-first rule enforced in docstring. |
| `search_reddit` | `(query, subreddit="", max_results=5)` | Reddit via `site:reddit.com` operator. No OAuth. Routes through SearxNG/Google/Bing. |
| `fetch_url` | `(url, max_chars=3000)` | Fetches and strips HTML from a URL. |
| `get_github_release` | `(repo)` | Gets latest release tag from GitHub API. Preferred over search_web for version lookups. |
| `search_rfc` | `(symptom, protocol="")` | Queries RFC authority KB for protocol-level diagnosis. |

**Critical search_web rules**:
1. **KB-FIRST**: always call `search_kb()` before `search_web()`. KB miss required to proceed.
2. **YEAR INJECTION IS FORBIDDEN**: never append a year to the query string.
3. **DATE-SENSITIVE**: for firmware/CVE/version queries, call `execute_command("date +%Y-%m-%d")` first. Assess KB freshness against actual date (30-day threshold for firmware, 7-day for CVEs).
4. **ANNOUNCE**: write to user before calling ("Searching for X because Y").
5. **INDEX AFTER**: call `index_to_kb()` after finding a good result.

### 4.4 Knowledge Base

Built on **Elasticsearch** (`lse-kb` index) + **Ollama** (`nomic-embed-text` 768-dim embeddings).

| Function | Signature | Purpose |
|---|---|---|
| `search_kb` | `(query, top_k=3)` | Semantic search of KB. Returns results with quality_score. Score ≥ 0.6 = use directly. |
| `index_to_kb` | `(title, content, tags=[])` | Stores to KB. **4000-char cap on content**. Call at most once per task. Do NOT call search_kb after to verify. |
| `record_error` | `(error_text, context, resolution)` | Logs error + resolution to KB for future reference. |
| `check_error_kb` | `(error_text)` | Checks if a seen error has a known resolution. |
| `record_outcome` | `(task, result, lessons)` | Records task outcome. |
| `mentor_correct` | `(wrong_action, correct_action, rule)` | Records a behavioral correction for self-improvement. |

### 4.5 Context Management

| Function | Signature | Purpose |
|---|---|---|
| `get_context_status` | `()` | Returns token usage from llama.cpp `/slots` endpoint. |
| `compact_context` | `(summary, keep_last_n=4)` | Writes summary directly to OpenWebUI SQLite DB, truncates old messages. Used when context is near limit. |
| `monitor_download` | `(file_path, expected_bytes, interface="")` | Polls file growth + network throughput during large downloads. |

### 4.6 GPU Node Lifecycle

`_NODE_REGISTRY` stores all node metadata + startup profiles:

```python
_NODE_REGISTRY = {
    "node3090": {
        "mac":          "0c:9d:92:84:6e:6a",
        "hostname":     "node3090.home.arpa",
        "interface":    "opt1",
        "agent_port":   8080,
        "agent_type":   "llama-cpp",
        "os":           "linux",
        "ssh_user":     "lse-admin",
        "agent_profile": {
            "model":            "/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
            "ctx_size":         96000,
            "gpu_layers":       129,
            "flash_attn":       True,
            "cache_type_k":     "q8_0",
            "cache_type_v":     "q8_0",
            "parallel":         1,
            "threads":          7,
            "threads_batch":    7,
            "reasoning_budget": 3072,
            "n_predict":        8192,
            "jinja":            True,
            "metrics":          True,
        },
    },
    "node5090": { ... }  # WoL/SSH setup deferred
}
```

| Function | Signature | Purpose |
|---|---|---|
| `wake_node` | `(node)` | WoL via pfSense REST API. Polls SSH until node responds (boot ~55s). |
| `start_node_agent` | `(node)` | SSHes to node, builds CLI from agent_profile, starts llama-server via nohup. Polls /health for 120s. |
| `stop_node_agent` | `(node)` | SSHes to node, pkill llama-server. |
| `query_node_agent` | `(node, prompt, model="", max_tokens=2000, system_prompt="")` | POSTs to node's OpenAI-compatible /v1/chat/completions. |
| `shutdown_node` | `(node)` | SSH graceful shutdown. Uses subprocess directly (not execute_command — sudo is remote). |

**Lifecycle sequence**: `wake_node` → `start_node_agent` → `query_node_agent` → `stop_node_agent` → `shutdown_node`

---

## 5. Challenge Arena

### 5.1 Infrastructure

| Component | Path |
|---|---|
| ChallengeDB | `/opt/local-se/challenges.db` (SQLite) |
| LeaderboardDB | `/opt/local-se/leaderboard.db` (SQLite) |
| Episode runner | `scripts/run_episode.py` |
| Seeder | `scripts/seed_challengedb.py` |
| KB | Elasticsearch `lse-kb` index |

### 5.2 Challenge Schema (seed_challengedb.py)

**CRITICAL**: all challenges use `dict(` constructor — NOT `Challenge(` (causes NameError).

```python
dict(
    id="net-t3-003",
    title="Network Topology Mapper",
    tier=3,
    discipline_multiplier=1.5,
    max_attempts=2,
    requires_human_approval=0,
    starting_state=json.dumps({ ... }),
    assertions=json.dumps([
        {"id": "a1", "points": 2, "code": "assert device_count >= 5"},
        ...
    ]),
)
```

### 5.3 Tiers & Scoring

| Tier | Base points | Discipline multiplier |
|---|---|---|
| T1 | 10–13 | 1.5× |
| T2 | 13 | 1.5× |
| T3 | 13–20 | 1.5× |

### 5.4 Current Leaderboard (2026-06-07)
| Model | Points | Episodes | Solved | Avg Att |
|---|---|---|---|---|
| qwen3.6-27b-q4-64k | 425.6 | 23 | 22 | 1.09 |

---

## 6. Coding Standards & Hard Constraints

These are non-negotiable. Every proposed change must comply.

### 6.1 File Editing
- **NTFS large file rule**: Python files > 100 lines on the NTFS mount (`C:\Users\SY5\...`) CANNOT be safely edited with the Edit tool — it truncates silently. Use **bash Python string replacement** for all `.py` files > 100 lines:
  ```python
  with open(path) as f: src = f.read()
  src = src.replace(old, new, 1)
  with open(path, "w") as f: f.write(src)
  ```
- Always run `ast.parse(src)` after modification to verify no syntax errors.
- Always verify changes with `grep -n` after writing.

### 6.2 Version Discipline
- One file per version: `openwebui-tool-v1.5.27.py`. Never edit previous versions.
- Update version string, changelog entry, and description line in docstring.
- Update CURRENT-STATE.md after every version.

### 6.3 Git
- Commits from Cowork sandbox fail — always commit from WSL terminal on LUCIFER.

### 6.4 OpenWebUI Tool Constraints
- Only one tool file loaded at a time. Duplicate functions = OpenWebUI warning.
- Tool functions must be methods of the `Tools` class.
- All imports must be inside the function body (OpenWebUI sandboxing).
- `index_to_kb` capped at 4000 chars. Never call `search_kb` after to verify.

### 6.5 pfSense Safety
- Never SSH to pfSense (root shell, out of scope for LSE).
- Never store write-capable pfSense API keys in valves.
- POST calls require human Read Only toggle first.

### 6.6 Sudo
- `sudo_delegation_block` is for LUCIFER-local sudo only.
- Remote sudo via SSH (shutdown_node, start_node_agent) does NOT need delegation block.

---

## 7. Change Proposal Protocol

This section defines how the **coder LLM** (node3090 agent, Qwen3.6-27B) proposes changes, and how **Claude Sonnet 4.6** (senior reviewer) evaluates them.

### 7.1 Coder LLM Role
You are a skilled Python developer with deep knowledge of the LSE codebase. Your job is to:
- Propose specific, bounded changes to the tool plugin
- Write complete replacement code (not diffs) for any function you modify
- Follow all coding standards in section 6
- Explain your reasoning and tradeoffs

### 7.2 Proposal Format

```markdown
## Proposal: [short title] — v1.5.XX

### Problem
[What is broken or missing. Be specific. Include error output if applicable.]

### Root Cause
[Why it happens. Reference the specific code location: function name + line range.]

### Proposed Change
[What to change and why this approach over alternatives.]

### Code
```python
# Full replacement function (not a diff)
def function_name(self, ...) -> str:
    ...
```

### Constraints Checked
- [ ] No Edit tool on file > 100 lines (use bash string replacement)
- [ ] ast.parse passes after change
- [ ] Imports are inside function body
- [ ] Version string + changelog updated
- [ ] No sudo_delegation_block for remote SSH sudo
- [ ] index_to_kb content ≤ 4000 chars (if applicable)

### Risks
[What could go wrong. What to test after deploy.]
```

### 7.3 Senior Reviewer Checklist (Claude Sonnet 4.6)

When evaluating a proposal, check in order:

1. **Correctness** — does the code do what it claims? Any logic errors?
2. **Constraint compliance** — all items in 7.2 checked?
3. **Docstring quality** — does the docstring enforce the right behavioral rules on the model? Would a junior LLM misuse this function based on the docstring?
4. **Security** — does it open any new attack surface? Can it be used to bypass the permission model?
5. **Regression risk** — what existing behavior could break?
6. **Simplicity** — is there a simpler implementation that achieves the same result?

**Teaching mode**: when rejecting or revising, always explain WHY with a specific rule reference (e.g. "Rule 6.1: NTFS large file rule violated — use bash string replacement"). The goal is the coder LLM internalising the rule, not just fixing this instance.

---

## 8. Pending Work (as of 2026-06-07)

| Priority | Item | Notes |
|---|---|---|
| P0 | Ground-truth assertion verifier | Add `verify_ssh` to challenge assertions — framework SSHes independently after episode to override model-reported vars. Design in ROADMAP.md. |
| P1 | net-t3-003 topology challenge | Probes: pfSense ARP, DHCP leases, interfaces, nmap sweeps, mDNS, MAC OUI. Needs subnet map from user first. |
| P1 | Network topology visualization | vis.js force-directed graph, per-device green/red LED, live status polling. |
| P1 | searxng-error-exporter | Grafana Panel 24 shows 0. |
| P2 | node-t3-001 run | requires_human_approval=1 — pfSense Read Only toggle is human gate. |
| P2 | node-t3-002 re-run | Re-run with llama-server verified running before episode. |
| P2 | DHCP option 119 | Add `home.arpa` search domain so `ssh node3090` resolves without FQDN. |
| P3 | node5090 setup | WoL + SSH deferred. |
| P3 | RTX 2080Ti install | Watercooling loop prep required (human). |

---

## 9. Key Lessons Learned

These are non-obvious — don't repeat these mistakes.

| Lesson | Detail |
|---|---|
| pfSense WoL needs `/send` suffix | `POST /api/v2/services/wake_on_lan/send` — bare endpoint returns 404 |
| pfSense auth is `x-api-key` | NOT `Authorization: Bearer` |
| Edit tool truncates large NTFS files | Use bash Python string replacement for files > 100 lines |
| seed_challengedb.py uses `dict(` | NOT `Challenge(` — causes NameError |
| node3090 FQDN required | `ssh node3090` fails, `ssh node3090.home.arpa` works (DHCP option 119 pending) |
| `nvidia-smi` CUDA Version = driver max | Not the installed toolkit version |
| `/opt/models` is a REAL directory | Since 2026-06-11 P21 reconciliation (was a symlink → `~/.lmstudio/models/` — caused the model-deletion incident). `.gguf` files are `chattr +i` immutable; `sudo chattr -i` before any replace. sha256 records in `/opt/models/SHA256SUMS` |
| CUDA 13.3 `cuda_fp4.hpp` warnings | Benign — Blackwell-only code paths, not relevant for RTX 3090 (Ampere SM 8.6) |
| Build flag for RTX 3090 | `-DCMAKE_CUDA_ARCHITECTURES=86` skips Blackwell warnings |
| reddit engine blocked on VPS IP | Use `site:reddit.com` via Google/Bing instead |
| search_web timeout needs tuple | `timeout=(5, 10)` not `timeout=10` — covers connection + read separately |
| docker compose restart shows 0/1 | Display quirk, not an error — check `docker logs searxng` |
| HA sshd_config regenerates on reboot | AllowUsers/PermitRootLogin don't survive — use `ssh sy5@homeassistant.home.arpa sudo <cmd>` |
| compact_context uses SQLite directly | HTTP endpoint deadlocks single-worker uvicorn — writes to webui.db instead |
