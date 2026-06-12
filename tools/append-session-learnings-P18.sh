#!/bin/bash
# Run this from WSL: bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/append-session-learnings-P18.sh
set -e
KB=/opt/local-se/kb/session-learnings.md
[ -f "$KB" ] || (mkdir -p /opt/local-se/kb && echo "# LSE Session Learnings" > "$KB")
printf '\n' >> "$KB"
cat >> "$KB" << 'DEBRIEF_EOF'
## Session 2026-06-09 — pfsense-agent _extract_prompt + OWUI API gap

### What worked
- Anchoring on the LAST DO NOT block via `rfind` to find where the final clean output starts
- Walking backwards through step_matches to find the start of the last CONTIGUOUS ASCENDING SEQUENCE (handles thinking traces with multiple draft Step N: sequences)
- Assistant prefill `{"role":"assistant","content":"Step 1: "}` forces --no-think output to start at Step 1 with zero preamble
- Writing large Python files via `cat > /tmp/file.py << 'PYEOF'` heredoc + `python3 -c "import ast; ast.parse(...)"` syntax check + `cp` to workspace

### What failed and why
- **Attempted:** `re.finditer(r"(?m)^\s*Step \d+:", text)` for step detection in multiline mode
  **Failed because:** `^` + `\s*` in multiline mode — `^` anchors at start of the preceding blank line's `\n`, and `\s*` matches `\n       ` (newline + spaces). `match.start()` lands on the `\n`, not the first space of the Step line. After slicing, `splitlines()[0]` is `''`, `indent=0`, dedent is a no-op.
  **Fix:** Replace ALL `^\s*` with `^[ \t]*` in step-matching regexes. Spaces and tabs only — never newlines.
  Confirm the bug: `re.search(r"(?m)^\s*Step \d+:", "foo\n\n       Step 2: bar").start()` → 4 (the \n, not 6)

- **Attempted:** Using `rfind` on DO NOT anchor + `step_matches[-1]` (last step match only)
  **Failed because:** Found Step 6 (last step in last group) but missed Steps 2-5 before it in the same final output block.
  **Fix:** Walk backwards from step_matches[-1] looking for contiguous descending sequence; use group_start_idx as real start.

- **Attempted:** Edit tool to patch pfsense-agent.py (331 lines) on NTFS
  **Failed because:** Edit tool silently truncates large Python files on NTFS at ~2600-3000 chars — no error, file written but incomplete.
  **Fix:** Always use `cat > /tmp/file.py << 'PYEOF'` heredoc for ANY .py file >100 lines. Never use Edit tool on large Python files in the Windows-mounted workspace.

- **Attempted:** OpenWebUI /api/chat/completions with tool_ids to trigger LSE tool execution
  **Failed because:** Local Qwen3.6 generates reasoning text about which tools to call — does NOT emit OpenAI-style tool_calls JSON. OWUI agentic loop only fires on structured FC JSON. Chat UI uses a ReAct text-based pattern that the API path does not share.
  **Decision:** Adopted Dify for multi-agent UI. OWUI pipe function deferred.

### Key facts
- `^[ \t]*` not `^\s*` — in multiline Python regex, `\s*` swallows the preceding newline
- NTFS + Edit tool truncates Python files >100 lines silently — use heredoc always
- OWUI API tool_ids field exists (found in middleware.py) but requires native FC JSON from model — local Qwen3.6 does not emit this
- pfSense auth header: X-API-Key: <key> — NOT Authorization: Bearer <key>
- Vaultwarden tools: pass via tool_ids only when needed — not default-enabled (security boundary)
- pfsense-agent.py: --think -> max_tokens=4096, no prefill; --no-think -> max_tokens=2048, prefill applied
- DO NOT sentinels: FIRST="DO NOT: query __schema or __type (context bomb -- crashes session)", LAST="DO NOT: guess placement index -- read-first always"
- Dify deploy: git clone https://github.com/langgenius/dify && cd dify/docker && cp .env.example .env && docker compose up -d
DEBRIEF_EOF
echo "--- Verifying tail ---"
tail -30 "$KB"
