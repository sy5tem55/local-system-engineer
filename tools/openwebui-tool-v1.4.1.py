"""
title: LSE System Admin Terminal
author: local-system-engineer
version: 1.4.2
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, read_file, write_file, sudo_delegation_block, search_web,
  and get_context_status. All commands are logged to a persistent audit file. Privileged
  operations are blocked at the code level and routed through a delegation block.
  Fixes: trailing-slash path comparison bug from v1.3.0.
  v1.4.1: Added explicit routing rules to read_file docstring to prevent model from
  using read_file when tail/grep would suffice (fixes S2 eval regression).
"""

from pydantic import BaseModel, Field
import subprocess
import os
from datetime import datetime


class Tools:

    class Valves(BaseModel):
        LOG_FILE: str = Field(
            default="/home/sy5/.lse/agent_commands.log",
            description="Path to the persistent agent command audit log (tailed by lse-monitor.sh).",
        )
        DEFAULT_WORKING_DIR: str = Field(
            default="/home/sy5",
            description="Default cwd for execute_command when no working_dir is supplied.",
        )
        MAX_OUTPUT_CHARS: int = Field(
            default=4000,
            description="Maximum characters returned by execute_command before truncation.",
        )
        COMMAND_TIMEOUT: int = Field(
            default=30,
            description="Subprocess timeout in seconds.",
        )
        LLAMA_SERVER_URL: str = Field(
            default="http://localhost:8080",
            description="Base URL of the llama.cpp server (for get_context_status).",
        )
        SEARXNG_URL: str = Field(
            default="http://localhost:8888/search",
            description="SearxNG JSON search endpoint (for search_web).",
        )
        EXTRA_WRITE_PATHS: str = Field(
            default="",
            description="Colon-separated extra paths the agent may write to (e.g. /opt/local-se/).",
        )

    # ── Hard-coded permission lists ───────────────────────────────────────────

    _ALLOWED_READ_PREFIXES = [
        "/home/",
        "/etc/",
        "/var/log/",
        "/tmp/lse/",
        "/opt/local-se/",
    ]

    _ALLOWED_WRITE_PREFIXES = [
        "/home/",
        "/tmp/lse/",
        "/opt/local-se/",
    ]

    _BLOCKED_COMMANDS = (
        "mkfs", "fdisk", "parted", "wipefs",
        "iptables -f", "iptables -F",
        "passwd", "visudo",
        "dd if=",
    )

    _PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")

    _PRIVILEGED_WRITE_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/")

    _WRITE_OPS = ("cp ", "mv ", "rm ", "tee ", "> ", ">> ", "sed -i", "truncate", "dd ")

    # ── Initialiser ──────────────────────────────────────────────────────────

    def __init__(self):
        self.valves = self.Valves()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _norm(self, path: str) -> str:
        """Resolve symlinks and normalise trailing slash so prefix checks work."""
        return os.path.realpath(os.path.expanduser(path)).rstrip("/") + "/"

    def _is_allowed_read(self, path: str) -> bool:
        normed = self._norm(path)
        return any(normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_READ_PREFIXES)

    def _is_allowed_write(self, path: str) -> bool:
        normed = self._norm(path)
        base_ok = any(normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_WRITE_PREFIXES)
        if base_ok:
            return True
        # Check extra paths from Valve
        if self.valves.EXTRA_WRITE_PATHS:
            for extra in self.valves.EXTRA_WRITE_PATHS.split(":"):
                extra = extra.strip()
                if extra and normed.startswith(extra.rstrip("/") + "/"):
                    return True
        return False

    def _log(self, entry: str) -> None:
        """Append a timestamped line to the audit log (best-effort)."""
        try:
            log_path = self.valves.LOG_FILE
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a") as f:
                f.write(f"[{ts}] {entry}\n")
        except Exception:
            pass  # Never let logging failure break a tool call

    # ── Tool functions ────────────────────────────────────────────────────────

    def execute_command(self, command: str, working_dir: str = "") -> str:
        """
        Execute a read-only or write-safe shell command in the WSL Ubuntu environment.
        Use for: ls, cat, grep, find, ps, df, uname, systemctl status, apt list, journalctl, etc.
        Do NOT use for commands requiring sudo — use sudo_delegation_block instead.
        Output is capped at MAX_OUTPUT_CHARS. Always pipe through grep/head/awk to limit output.
        Example good call: execute_command("journalctl -u nginx -n 20 --no-pager")
        Example bad call:  execute_command("journalctl -u nginx")
        """
        cwd = working_dir.strip() or self.valves.DEFAULT_WORKING_DIR

        # ── Block permanently forbidden commands ──────────────────────────────
        cmd_lower = command.lower().strip()
        for blocked in self._BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                self._log(f"HARD-BLOCKED: {command}")
                return (
                    f"BLOCKED: '{blocked}' is permanently forbidden. "
                    "This operation cannot be performed by the agent under any circumstances."
                )

        # ── Block privilege escalation (anywhere in command, not just prefix) ──
        # Fixes v1.4.1 bug: startswith missed sudo embedded in pipelines,
        # e.g. "ls /home | sudo tee file.txt" would have passed the old check.
        for priv in self._PRIVILEGED_PREFIXES:
            if priv in cmd_lower:
                self._log(f"PRIV-BLOCKED: {command}")
                return (
                    f"BLOCKED: '{priv.strip()}' detected in command. "
                    "Use sudo_delegation_block instead."
                )

        # ── Block writes to privileged system paths ───────────────────────────
        if any(p in command for p in self._PRIVILEGED_WRITE_PATHS):
            if any(op in command for op in self._WRITE_OPS):
                self._log(f"WRITE-BLOCKED: {command}")
                return (
                    "BLOCKED: Write to a privileged system path detected. "
                    "Use sudo_delegation_block to delegate this to the user."
                )

        # ── Validate working directory ────────────────────────────────────────
        if not self._is_allowed_read(cwd):
            return f"BLOCKED: working_dir '{cwd}' is outside allowed read paths."

        # ── Execute ───────────────────────────────────────────────────────────
        self._log(f"CMD: {command}  (cwd={cwd})")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.valves.COMMAND_TIMEOUT,
                cwd=cwd,
            )
            output = result.stdout or result.stderr or "(no output)"
            rc = result.returncode
            if len(output) > self.valves.MAX_OUTPUT_CHARS:
                output = (
                    output[: self.valves.MAX_OUTPUT_CHARS]
                    + f"\n... [TRUNCATED — {len(output)} chars total. "
                    "Re-run with more specific filters (grep/head/awk).]"
                )
            self._log(f"DONE rc={rc} len={len(output)}")
            return output if rc == 0 else f"[exit {rc}]\n{output}"
        except subprocess.TimeoutExpired:
            self._log(f"TIMEOUT: {command}")
            return f"ERROR: Command timed out after {self.valves.COMMAND_TIMEOUT} seconds."
        except Exception as e:
            self._log(f"ERROR: {e}")
            return f"ERROR: {str(e)}"

    def read_file(self, path: str, max_lines: int = 100, offset_lines: int = 0) -> str:
        """
        Read a file from the filesystem with optional pagination.
        Default: first 100 lines. Use offset_lines to page through large files.
        Always read the smallest slice you need — large reads bloat context fast.

        CRITICAL ROUTING RULE — do NOT use this function when:
          • User asks for "last N lines" of ANY file → use execute_command("tail -N <path>") instead.
          • User asks for lines matching a pattern → use execute_command("grep '...' <path>") instead.
          • File is a log file → use execute_command("tail -N <path>") or grep.

        Use read_file ONLY when you need a specific line range from the beginning or middle of a
        file and tail/grep are not applicable (e.g. reading a config block at a known line offset).
        """
        if not self._is_allowed_read(path):
            return f"BLOCKED: '{path}' is outside allowed read paths."

        resolved = os.path.realpath(os.path.expanduser(path))
        if not os.path.isfile(resolved):
            return f"ERROR: File not found: {path}"

        self._log(f"READ: {path} lines={offset_lines}..{offset_lines + max_lines}")
        try:
            with open(resolved, "r", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            sliced = lines[offset_lines: offset_lines + max_lines]
            content = "".join(sliced)
            footer = (
                f"\n--- Lines {offset_lines + 1}–{offset_lines + len(sliced)} "
                f"of {total} total ---"
            )
            return content + footer
        except Exception as e:
            return f"ERROR: {str(e)}"

    def write_file(self, path: str, content: str, mode: str = "overwrite") -> str:
        """
        Write content to a file within allowed write paths.
        mode='overwrite' replaces the file entirely; mode='append' adds to the end.
        IMPORTANT: Always read the file first and show the proposed diff to the user
        before calling this function. Never write without confirming the change.
        For files under /etc/ or other privileged paths, use sudo_delegation_block.
        """
        if not self._is_allowed_write(path):
            return (
                f"BLOCKED: '{path}' is outside allowed write paths. "
                "Use sudo_delegation_block for privileged paths."
            )

        resolved = os.path.realpath(os.path.expanduser(path))
        parent = os.path.dirname(resolved)

        self._log(f"WRITE: {path} mode={mode} len={len(content)}")
        try:
            os.makedirs(parent, exist_ok=True)
            file_mode = "a" if mode == "append" else "w"
            with open(resolved, file_mode) as f:
                f.write(content)
            return f"OK: {len(content)} characters written to {path} (mode={mode})."
        except Exception as e:
            return f"ERROR: {str(e)}"

    def sudo_delegation_block(
        self, command: str, reason: str, expected_output_hint: str = ""
    ) -> str:
        """
        Use whenever an operation requires sudo or touches a privileged path (/etc/, systemctl, apt install, etc.).
        This produces a formatted block for the user to run manually in their terminal.
        NEVER attempt to run sudo yourself. Always call this function instead.
        After calling this function, STOP and wait for the user to paste the output.
        """
        self._log(f"SUDO-DELEGATE: {command}  reason={reason}")
        hint_line = f"Expected output: {expected_output_hint}\n" if expected_output_hint else ""
        block = (
            "⚠️  SUDO REQUIRED — Action delegated to user\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Reason: {reason}\n\n"
            "Run this in your terminal:\n\n"
            f"  {command}\n\n"
            f"{hint_line}"
            "Paste the full terminal output here to continue.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return block

    def search_web(self, query: str, max_results: int = 5) -> str:
        """
        Search the web via the local SearxNG instance at localhost:8888.
        GATE: Only call this when you cannot answer from your system prompt knowledge base.
        Before calling, announce to the user: "I need to search for [X] because [Y]."
        Call only once per topic. Synthesise the result in 3 sentences or fewer.
        Do NOT inject raw search results verbatim into your response.
        """
        import requests  # noqa: PLC0415

        self._log(f"SEARCH: {query} max={max_results}")
        try:
            resp = requests.get(
                self.valves.SEARXNG_URL,
                params={"q": query, "format": "json", "categories": "general"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:max_results]
            if not results:
                return "No results found."
            lines = []
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("content", "")[:300]
                lines.append(f"**{title}**\n{url}\n{snippet}")
            return "\n---\n".join(lines)
        except Exception as e:
            return f"ERROR searching SearxNG: {str(e)}"

    def get_context_status(self) -> str:
        """
        Query the llama.cpp server to get the current token usage and context fill percentage.
        Call this at the start of every turn and whenever the conversation feels long.
        Results drive the compaction and hard-reset decisions described in the system prompt.
        """
        import requests  # noqa: PLC0415

        self._log("CTX-STATUS: querying /slots")
        try:
            resp = requests.get(
                f"{self.valves.LLAMA_SERVER_URL}/slots", timeout=5
            )
            slots = resp.json()
            if not slots:
                return "No active slots found on llama.cpp server."
            s = slots[0]
            n_past = s.get("n_past", 0)
            n_ctx = s.get("n_ctx", 65536)
            pct = round(n_past / n_ctx * 100, 1) if n_ctx else 0.0
            kv = s.get("kv_cache_usage_ratio")
            kv_str = f"{kv * 100:.1f}%" if kv is not None else "N/A"

            if pct >= 85:
                status = "🔴 CRITICAL — HARD RESET required before next tool call."
            elif pct >= 70:
                status = "🟠 HIGH — COMPACTION required before next tool call."
            elif pct >= 50:
                status = "🟡 ELEVATED — minimise tool output verbosity."
            else:
                status = "🟢 OK — normal operation."

            return (
                f"Context: {n_past:,} / {n_ctx:,} tokens ({pct}%)\n"
                f"KV cache fill: {kv_str}\n"
                f"Status: {status}"
            )
        except Exception as e:
            return f"ERROR querying llama.cpp: {str(e)}"
