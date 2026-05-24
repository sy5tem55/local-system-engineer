# 02 — Terminal Interaction: OpenWebUI Tool Design Deep Dive

## 1. Interaction Model Overview

OpenWebUI allows you to define Python **Tool functions** that the model can call during a conversation. The model decides when to call a tool, supplies structured arguments, and receives the output injected back into its context window. For a system engineering agent this is the primary mechanism for all non-conversational work.

```
User message
    ↓
Model (llama.cpp via OpenWebUI)
    ↓ decides to call tool
Tool function (Python, runs in OpenWebUI server process)
    ↓ executes in WSL/Ubuntu 24.04
Result injected back into context
    ↓
Model continues response
```

**Key constraint**: Every tool result is appended to the context. Verbose output (e.g., `apt list --installed` → 3 000 tokens) bloats context fast. Tool functions must truncate, summarize, or paginate their output. See `docs/03-context-management.md` for policy.

---

## 2. Permission Boundary Design

### 2.1 Allowed Directories

Define a hard-coded allowlist. The agent **never** reads from or writes to paths outside this list. The list lives in the tool configuration, not in the system prompt — a system prompt can be overridden by a sufficiently clever prompt injection; the allowlist in code cannot.

```python
ALLOWED_READ_PATHS = [
    "/home/",          # user home directories
    "/etc/",           # system configuration (read-only recommended)
    "/var/log/",       # logs (read-only)
    "/tmp/lse/",       # agent scratch space
    "/opt/local-se/",  # agent knowledge base and working files
]

ALLOWED_WRITE_PATHS = [
    "/home/",          # dotfiles, user configs
    "/tmp/lse/",       # scratch space
    "/opt/local-se/",  # agent knowledge base
    # NOT /etc/ — edits there go through sudo delegation
]
```

### 2.2 Command Risk Classification

Every shell command executed by the agent is classified before execution:

| Class | Examples | Action |
|---|---|---|
| `READ_ONLY` | `ls`, `cat`, `grep`, `find`, `systemctl status`, `apt list`, `uname`, `df`, `ps` | Execute directly |
| `WRITE_SAFE` | `cp`, `mv`, `mkdir`, `touch`, `tee` within allowed write paths | Execute after path check |
| `WRITE_DESTRUCTIVE` | `rm`, `truncate`, `dd` | Require explicit confirmation token in args |
| `PRIVILEGED` | Any command containing `sudo`, operating on `/etc/`, `/usr/`, `/boot/`, system service start/stop/restart | Block; emit `SUDO_REQUIRED` delegation block |
| `BLOCKED_ALWAYS` | `mkfs`, `fdisk`, `parted`, `iptables -F`, `passwd`, `visudo`, network interface changes | Hard block; never execute |

### 2.3 Sudo Delegation Protocol

When the agent determines an action requires elevated privileges, it **stops execution** and emits a structured delegation block:

```
⚠️  SUDO REQUIRED — Action delegated to user

The following command requires elevated privileges and cannot be
executed by the agent. Please run it in your terminal and paste
the output back to continue.

  sudo systemctl restart nginx

Expected output: Service restart confirmation or error message.
Paste the full terminal output to continue.
```

The agent then **waits** for the user to paste the output before proceeding. It never assumes success.

---

## 3. Tool Function Specifications

All tool functions are defined as Python classes in OpenWebUI's Tools format. Each has a `__doc__` string that the model reads to understand when to call it.

### 3.1 `execute_command`

```python
class Tools:
    def execute_command(self, command: str, working_dir: str = "/tmp/lse") -> str:
        """
        Execute a read-only or write-safe shell command in the Ubuntu environment.
        Use for: ls, cat, grep, find, systemctl status, apt list, ps, df, uname, etc.
        Do NOT use for commands requiring sudo — use sudo_delegation_block instead.
        Output is truncated to 4000 characters. Request specific fields if you need less.
        """
        import subprocess, shlex, os

        MAX_OUTPUT = 4000
        BLOCKED_PREFIXES = ("sudo", "su ", "mkfs", "fdisk", "parted", "passwd")
        PRIVILEGED_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/")

        cmd_lower = command.lower().strip()
        if any(cmd_lower.startswith(p) for p in BLOCKED_PREFIXES):
            return "BLOCKED: This command requires elevation. Use sudo_delegation_block."

        # Detect writes to privileged paths
        if any(p in command for p in PRIVILEGED_PATHS):
            write_ops = ("cp ", "mv ", "rm ", "tee ", "echo ", "cat >", ">>", "sed -i")
            if any(op in command for op in write_ops):
                return "BLOCKED: Write to privileged path. Use sudo_delegation_block."

        # Validate working directory
        if not self._is_allowed_path(working_dir, read=True):
            return f"BLOCKED: Working directory {working_dir} is outside allowed paths."

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=working_dir,
            )
            output = result.stdout or result.stderr or "(no output)"
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + f"\n... [TRUNCATED — {len(output)} chars total. Re-run with more specific filters.]"
            return output
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 30 seconds."
        except Exception as e:
            return f"ERROR: {str(e)}"

    def _is_allowed_path(self, path: str, read: bool = True) -> bool:
        import os
        allowed = ALLOWED_READ_PATHS if read else ALLOWED_WRITE_PATHS
        resolved = os.path.realpath(path)
        return any(resolved.startswith(p) for p in allowed)
```

### 3.2 `read_file`

```python
    def read_file(self, path: str, max_lines: int = 100, offset_lines: int = 0) -> str:
        """
        Read a file from the filesystem. Supports pagination via offset_lines and max_lines.
        Default: first 100 lines. Increase max_lines only if necessary — large reads bloat context.
        Always specify the smallest slice you need.
        """
        import os

        if not self._is_allowed_path(path, read=True):
            return f"BLOCKED: {path} is outside allowed read paths."

        resolved = os.path.realpath(path)
        if not os.path.isfile(resolved):
            return f"ERROR: File not found: {path}"

        try:
            with open(resolved, "r", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            slice_ = lines[offset_lines : offset_lines + max_lines]
            content = "".join(slice_)
            footer = f"\n--- Lines {offset_lines+1}–{offset_lines+len(slice_)} of {total} total ---"
            return content + footer
        except Exception as e:
            return f"ERROR: {str(e)}"
```

### 3.3 `write_file`

```python
    def write_file(self, path: str, content: str, mode: str = "overwrite") -> str:
        """
        Write content to a file. mode='overwrite' replaces the file; mode='append' adds to it.
        Only works within allowed write paths. For /etc/ files, use sudo_delegation_block.
        ALWAYS read the file first and show the diff to the user before writing.
        """
        import os

        if not self._is_allowed_path(path, read=False):
            return f"BLOCKED: {path} is outside allowed write paths."

        resolved = os.path.realpath(path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)

        try:
            file_mode = "a" if mode == "append" else "w"
            with open(resolved, file_mode) as f:
                f.write(content)
            return f"OK: Written {len(content)} characters to {path} (mode={mode})."
        except Exception as e:
            return f"ERROR: {str(e)}"
```

### 3.4 `sudo_delegation_block`

```python
    def sudo_delegation_block(self, command: str, reason: str, expected_output_hint: str = "") -> str:
        """
        Use this whenever an action requires sudo or touches a privileged path.
        Produces a formatted delegation block for the user to run manually.
        Never attempt to run sudo yourself. Always use this function instead.
        """
        block = f"""
⚠️  SUDO REQUIRED — Action delegated to user
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reason: {reason}

Run this in your terminal:

  {command}

{f"Expected output: {expected_output_hint}" if expected_output_hint else ""}
Paste the full terminal output here to continue.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        return block.strip()
```

### 3.5 `search_web`

```python
    def search_web(self, query: str, max_results: int = 5) -> str:
        """
        Search the web via the local SearxNG instance. 
        ONLY call this when you cannot answer from your system prompt knowledge or 
        the knowledge base. Announce to the user that you are searching and why 
        before calling this function.
        """
        import requests, json

        SEARXNG_URL = "http://localhost:8888/search"  # adjust to your SearxNG port
        try:
            resp = requests.get(
                SEARXNG_URL,
                params={"q": query, "format": "json", "categories": "general"},
                timeout=10,
            )
            data = resp.json()
            results = data.get("results", [])[:max_results]
            if not results:
                return "No results found."
            lines = []
            for r in results:
                lines.append(f"**{r.get('title', '?')}**\n{r.get('url', '')}\n{r.get('content', '')[:300]}\n")
            return "\n---\n".join(lines)
        except Exception as e:
            return f"ERROR searching SearxNG: {str(e)}"
```

### 3.6 `get_context_status`

```python
    def get_context_status(self) -> str:
        """
        Query the llama.cpp server to get current token usage and context fill percentage.
        Call this proactively when you feel the conversation is getting long, or when 
        instructed to check context health.
        """
        import requests

        LLAMA_SERVER = "http://localhost:8080"
        try:
            slots = requests.get(f"{LLAMA_SERVER}/slots", timeout=5).json()
            if slots:
                s = slots[0]
                n_past = s.get("n_past", 0)
                n_ctx = s.get("n_ctx", 32768)
                pct = round(n_past / n_ctx * 100, 1)
                return (
                    f"Context: {n_past}/{n_ctx} tokens used ({pct}%)\n"
                    f"KV cache: {s.get('kv_cache_usage_ratio', 'N/A')}\n"
                    f"Status: {'⚠️ HIGH — consider compacting' if pct > 75 else '✅ OK'}"
                )
            return "No active slots found."
        except Exception as e:
            return f"ERROR: {str(e)}"
```

---

## 4. Tool Output Size Budget

Set a target maximum for each tool's output before it gets injected into context. These are guidelines; enforce them in code via truncation.

| Tool | Target max output (chars) | Notes |
|---|---|---|
| `execute_command` | 4 000 | Pipe through `head`, `grep`, or `cut` first when possible |
| `read_file` | 6 000 (100 lines) | Always paginate; never read an entire log file |
| `write_file` | Echo only a confirmation line | Content is already known; no need to repeat it |
| `sudo_delegation_block` | ~400 | Fixed-format; always compact |
| `search_web` | 300 chars per result, 5 results max | Strip boilerplate aggressively |
| `get_context_status` | < 200 | Single status line |

---

## 5. Step-by-Step Execution Protocol

The agent must **never execute silently**. Before any non-trivial action sequence, it emits a numbered plan:

```
Plan:
1. Read ~/.bashrc to understand current PATH entries
2. Identify if the target directory is already present
3. If not present: write a PATH append block to ~/.bashrc
4. Verify the change by re-reading the modified lines
5. Advise user to run: source ~/.bashrc

Proceeding with step 1…
```

After each step it announces the result and what comes next. If a step fails or produces unexpected output, it **stops** and describes the situation before continuing.

---

## 6. Error Handling Patterns

| Situation | Agent behaviour |
|---|---|
| File not found | Report the exact path attempted, suggest alternatives (`find / -name <file>`) |
| Command times out (> 30 s) | Report timeout, suggest breaking the command into smaller pieces |
| Unexpected tool output structure | Show the raw output, ask user to clarify before proceeding |
| Sudo required mid-sequence | Pause, emit delegation block, explicitly state "I am waiting for your output before continuing with step N" |
| Context at > 75 % | Call `get_context_status`, announce percentage, suggest compaction before proceeding |
| SearxNG unreachable | Report the error, proceed from training knowledge with explicit caveat that it may be stale |

---

## 7. OpenWebUI Integration Notes

- Tools are added under **Workspace → Tools** in OpenWebUI. Each tool function becomes callable.
- Set the model's default system prompt to reference the tool names explicitly (see `prompts/v0.3-context-aware.md`).
- Enable **"Show tool calls"** in model settings so you can audit every call the agent makes.
- Pipe the OpenWebUI server logs to a file so you have a full audit trail of all tool invocations:
  ```bash
  # In your WSL session
  python open-webui/main.py 2>&1 | tee ~/lse-audit.log
  ```
