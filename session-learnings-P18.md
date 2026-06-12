# Session Learnings — P18 (2026-06-09)

## 1. `_extract_prompt` — DO NOT block anchor + contiguous step sequence

**Problem:** Qwen3.6-27B outputs untagged thinking (no `<think>` tags in some modes). The thinking trace contains multiple draft Step N: sequences. Using the last `Step 1:` in the raw stream returns the thinking draft, not the final clean output.

**Solution:** Anchor on the LAST occurrence of the DO NOT block sentinel (use `rfind`, not `find`). Walk backwards through all `Step N:` matches before the DO NOT block to find the START of the LAST CONTIGUOUS ASCENDING SEQUENCE. This correctly identifies Step 2 (or Step 1) even when the thinking trace has its own Step 2 earlier.

**Key logic:**
```python
last_do_not_start = raw.rfind(FIRST_DO_NOT)
step_matches = list(re.finditer(r"(?m)^[ \t]*Step (\d+):", before))
group_start_idx = len(step_matches) - 1
prev_num = int(step_matches[group_start_idx].group(1))
for i in range(len(step_matches) - 2, -1, -1):
    num = int(step_matches[i].group(1))
    if num == prev_num - 1:
        prev_num = num
        group_start_idx = i
    else:
        break
```

## 2. `^\s*` vs `^[ \t]*` in multiline Python regex — CRITICAL

**Problem:** `re.finditer(r"(?m)^\s*Step \d+:", text)` — when text is `"foo\n\n       Step 2: ..."`, the regex `^` anchors at start of the second `\n` (the blank line), and `\s*` matches `\n       ` (newline + spaces). So `match.start()` lands on the `\n` before the blank line, NOT on the first space of the Step line. After `before[match.start():]`, `splitlines()[0]` is `''` (the blank line), `indent=0`, and dedent is a no-op.

**Fix:** Always use `^[ \t]*` instead of `^\s*` in multiline step-matching regexes. Spaces and tabs only — never newline.

**Confirm with:**
```python
import re
m = re.search(r"(?m)^\s*Step \d+:", "foo\n\n       Step 2: bar")
print(m.start())  # 4 — the \n, not 6 (the space)
```

## 3. OpenWebUI API tool execution gap

**Problem:** When calling OpenWebUI `/api/chat/completions` with `tool_ids`, the local Qwen3.6 model generates reasoning text about which tools to call — it does NOT emit OpenAI-style `tool_calls` JSON. OpenWebUI's tool execution loop only fires on structured function-call JSON, not on ReAct-style text. The Chat UI works because OpenWebUI parses the text pattern differently in that code path.

**Root cause:** Local LMs (even instruction-tuned) do not reliably emit OpenAI function-call JSON format via the completion API. Chat UI uses a text-based ReAct loop; API path assumes native FC format.

**Decision:** Adopted Dify as multi-agent UI. OWUI pipe function for Qwen3.6 → LSE handoff is deferred.

## 4. NTFS file truncation — recurring failure mode

**Rule (permanent):** NEVER use Edit tool on Python files >100 lines on NTFS. The Edit tool silently truncates at ~2600-3000 chars. Always use:
```bash
cat > /tmp/file.py << 'PYEOF'
... full content ...
PYEOF
python3 -c "import ast; ast.parse(open('/tmp/file.py').read()); print('OK')"
cp /tmp/file.py /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/file.py
```

## 5. pfsense-agent.py — key design decisions

- **Assistant prefill** (`{"role":"assistant","content":"Step 1: "}`) forces `--no-think` output to start at Step 1 with zero preamble
- **`--think`:** `max_tokens=4096`, no prefill, full thinking trace, `_extract_prompt` anchors on DO NOT block
- **`--no-think`:** `max_tokens=2048`, prefill applied, output starts at Step 2 (Step 1 is pre-written in prompt)
- **tool_ids:** `["lse_system_admin_terminal", "lse_vaultwarden_tools"]` — passed in payload, not always-on
- **Vaultwarden tools on-demand:** Security requirement — Vaultwarden tools are NOT default-enabled. Pass via `tool_ids` only when pfSense work requires them. This prevents unnecessary vault exposure in regular LSE sessions.

## 6. pfSense auth header

`X-API-Key: <key>` — NOT `Authorization: Bearer <key>`. Use `pfsense_query` with correct header; `pfsense_graphql` handles this internally. Never confuse with OWUI/OpenAI-style Bearer auth.

## 7. Dify — architecture decision rationale

Chosen over OWUI pipe function because:
- Persistent chat context (PostgreSQL) — pfSense work spans sessions
- Human-in-the-loop node built-in (no custom code)
- Visual workflow builder — easy to modify orchestrator prompt
- Both LM Studio instances connectable as OpenAI-compatible providers
- On-demand deploy (not persistent) — Docker Compose up/down
- Does not require local Qwen3.6 to emit native function-call JSON
