# 03 — Context Management: Bloat Observability and Remediation

## 1. Why Context Management Is a First-Class Concern

System engineering sessions generate context at an unusually high rate:

| Source | Typical tokens per event |
|---|---|
| `apt list --installed` output | 2 000–5 000 |
| `systemctl list-units` | 1 500–3 000 |
| Reading a 200-line config file | 500–1 500 |
| `find / -name "*.conf" 2>/dev/null` | 500–2 000 |
| SearxNG search result (5 × 300 chars) | ~400 |
| A single step-by-step plan + execution | 300–800 |

A realistic 10-step system engineering session can accumulate 15 000–30 000 tokens before the core task is even complete. With both Gemma 4 models degrading noticeably above 30 000 tokens, context management is not optional — it is the primary reliability mechanism.

---

## 2. Observability: Measuring Token Usage

### 2.1 llama.cpp Server Endpoints

`llama-server` exposes several endpoints you can poll programmatically:

```bash
# Health check
curl http://localhost:8080/health

# Slot status (includes token counts per active session)
curl http://localhost:8080/slots | python3 -m json.tool

# Prometheus-format metrics (if --metrics flag is set on server launch)
curl http://localhost:8080/metrics
```

**Key fields in `/slots` response:**
```json
{
  "id": 0,
  "state": 1,
  "n_ctx": 32768,          // total context window size
  "n_past": 18432,         // tokens consumed so far
  "kv_cache_usage_ratio": 0.562,  // n_past / n_ctx
  "n_predict": -1,
  "model": "gemma-4-31B-it-Q5_K_M.gguf"
}
```

`n_past / n_ctx × 100` gives you the fill percentage. A simple monitoring rule:
- **< 50 %** — green, no action needed
- **50–70 %** — yellow, watch and minimise tool output verbosity
- **70–85 %** — orange, trigger a compaction summarisation pass
- **> 85 %** — red, hard compaction or session reset required

### 2.2 Enable Prometheus Metrics

Start `llama-server` with the `--metrics` flag:
```bash
llama-server --model ./gemma-4-31B-it-Q5_K_M.gguf \
  --ctx-size 32768 \
  --metrics \
  ...
```

Then query:
```bash
curl http://localhost:8080/metrics | grep llamacpp_kv_cache_usage_ratio
# llamacpp_kv_cache_usage_ratio{slot_id="0"} 0.562
```

This integrates with Prometheus + Grafana if you want a dashboard, or you can poll it with the `tools/context_monitor.py` script.

---

## 3. Context Bloat Sources and Mitigations

### 3.1 Verbose Tool Output (Primary Source)

**Problem**: Tools like `execute_command` return raw shell output. A single `apt list` call can inject 3 000+ tokens.

**Mitigations**:
- Truncate all tool outputs at the source (enforced in tool code — see `docs/02-terminal-interaction.md` Section 4).
- Instruct the model in the system prompt to request targeted outputs: `grep`, `head`, `awk`, `jq` filters before reading.
- For file reads, always paginate: never read more than 100 lines at a time.

### 3.2 Repeated Re-Stating of Plans and History

**Problem**: The model tends to re-summarise prior steps at each turn, doubling the token cost of completed work.

**Mitigation**: System prompt instruction (see `prompts/v0.3`) — "Do not repeat completed steps. Reference them by number only."

### 3.3 Search Result Injection

**Problem**: Each `search_web` call injects ~400–600 tokens. Multiple searches compound quickly.

**Mitigation**: The agent must explicitly justify each search call and prefer a single well-targeted query over multiple broad ones.

### 3.4 Multi-Turn Error Recovery

**Problem**: When a command fails, the model re-states the error, the original command, the context of why it ran the command, and the proposed fix — often duplicating 800–1 200 tokens.

**Mitigation**: Compact error context. System prompt instruction: "On error, state: [STEP N FAILED] <one-line reason> then the corrected action. No re-preamble."

---

## 4. Remediation Strategies

### 4.1 Pre-Compaction Summarisation (Triggered at 70 % fill)

At 70 % context fill, the agent pauses and performs a **compaction pass** before the next tool call:

```
[CONTEXT COMPACTION — 70% fill reached]

Summary of completed work:
- Step 1–3: Audited /etc/nginx/nginx.conf. Found worker_processes set to 1.
- Step 4: Confirmed nginx version 1.24.0 (Ubuntu 24.04 default).
- Step 5: Delegated `sudo nginx -t` to user — result: config test OK.

Pending:
- Step 6: Write updated nginx.conf with worker_processes auto.
- Step 7: Delegate `sudo systemctl reload nginx` to user.

[Continuing with step 6…]
```

This summary replaces the verbose history. The model then proceeds from the summary. This is implemented as an instruction in `prompts/v0.3` (the model performs the compaction when triggered by `get_context_status` reaching the threshold).

### 4.2 Tool Output Compression Directives

Include in the system prompt a standing instruction for the model to compress tool outputs as they arrive:

```
When you receive tool output longer than 50 lines, immediately extract only 
the relevant information and discard the raw output from your working memory.
State what you extracted in one paragraph before proceeding.
```

This reduces the effective token cost of verbose outputs because the model's generation re-states only the compressed version, not the full raw text.

### 4.3 Sliding Window Session Design

For very long tasks, split the work into **bounded sub-sessions**:

1. Each sub-session starts with the system prompt + a compact "state file" (< 500 tokens) describing what was accomplished in prior sessions.
2. The state file lives at `/opt/local-se/session-state.md` and is updated at the end of each sub-session by the agent.
3. When starting a new sub-session, the agent reads the state file first.

State file format:
```markdown
# LSE Session State — Updated 2026-05-23 14:32

## Completed
- [x] Audited nginx config — worker_processes set to auto (needs reload)
- [x] Verified PHP-FPM 8.3 is installed and enabled

## Pending
- [ ] Reload nginx after config change (requires sudo)
- [ ] Set up logrotate for /var/log/app/

## Known constraints
- Do not touch /etc/hosts — it is managed by Ansible
- /home/joe/projects/ is in scope; /home/joe/personal/ is out of scope
```

### 4.4 Hard Context Reset

If context reaches 85 %+, perform a hard reset:

1. Write the full session state to `/opt/local-se/session-state.md`.
2. Start a new OpenWebUI conversation.
3. First message in the new conversation: "Resume from state file" — the agent reads the file and continues.

This is the nuclear option but avoids hallucination entirely.

---

## 5. Context Monitoring Integration in OpenWebUI

### 5.1 Automatic Context Status Checks

In `prompts/v0.3-context-aware.md`, the agent is instructed to call `get_context_status` at the start of each turn. This adds ~5 tokens overhead but means the agent always knows its fill percentage before deciding how verbose to be.

### 5.2 Warning Injections

Add a lightweight middleware to the OpenWebUI pipeline (or implement as a Tool) that injects a context warning into the prompt when fill exceeds 70 %:

```python
# In OpenWebUI pipeline (Pipelines feature)
def inlet(self, body, user=None):
    fill = get_context_fill_pct()  # poll /slots
    if fill > 85:
        body["messages"].insert(1, {
            "role": "system",
            "content": f"⚠️ CONTEXT CRITICAL: {fill:.0f}% fill. Perform compaction immediately before next tool call."
        })
    elif fill > 70:
        body["messages"].insert(1, {
            "role": "system", 
            "content": f"⚠️ CONTEXT HIGH: {fill:.0f}% fill. Compress outputs and minimize new tool calls."
        })
    return body
```

### 5.3 Token Budget Accounting per Step

Teach the model to budget tokens explicitly in its plan:

```
Plan (estimated token cost):
1. Read nginx.conf first 50 lines — ~200 tokens
2. Propose config change — ~100 tokens
3. Write updated section — ~150 tokens
4. Delegate sudo reload — ~100 tokens
Total estimated: ~550 tokens. Current available: ~8 000. OK to proceed.
```

This self-accounting behaviour is taught via few-shot examples in the system prompt (see `prompts/v0.3`).

---

## 6. WSL-Specific Context Considerations

WSL2 on Windows adds one extra context pressure: the agent may need to distinguish between Windows paths (`C:\Users\...`) and Linux paths (`/mnt/c/Users/...`). Every time a path translation is needed, the reasoning chain gets longer. Establish a rule in the system prompt:

```
All file operations use Linux paths exclusively. Windows paths are 
translated on first mention: C:\Users\joe → /mnt/c/Users/joe, then 
referenced as the Linux path for the remainder of the session.
```

This prevents repeated path translation reasoning from bloating context.
