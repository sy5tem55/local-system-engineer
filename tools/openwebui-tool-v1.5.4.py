"""
title: LSE System Admin Terminal
author: local-system-engineer
version: 1.5.4
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, read_file, write_file, sudo_delegation_block, search_web,
  and get_context_status. All commands are logged to a persistent audit file. Privileged
  operations are blocked at the code level and routed through a delegation block.

  Changelog:
    v1.4.1: Added explicit routing rules to read_file docstring (tail vs read_file).
    v1.4.2: Fixed sudo check from startswith → 'in' to catch sudo embedded in pipelines
            (e.g. "ls /home | sudo tee file.txt" was previously not blocked).
    v1.4.3: Rewrote write_file docstring to enforce:
              - full file read required before overwrite mode
              - append mode required for single-line additions
              - confirmation required for ALL writes, including new file creation
            Root cause: M2 eval revealed model used tail (partial read) then overwrote
            full file, causing data loss. Filter also tightened (see lse-routing-filter).
    v1.5.0: Promoted two prompt-level rules into docstrings (higher compliance weight):
              - execute_command: added COMBINE RULE — batch independent commands with &&
                or semicolons. Root cause: S1 eval showed model making two separate calls
                for uname -r and nproc despite OUTPUT RULES in the system prompt.
              - search_web: strengthened announcement protocol to a numbered REQUIRED
                SEQUENCE with explicit "protocol violation" language. Root cause: W2 eval
                showed model skipping the announce step and producing verbose synthesis.
            Fixed SEARXNG_URL default from port 8888 → 8088 (matches actual SearxNG port).
    v1.5.1: Two docstring fixes from eval run 2 regressions:
              - read_file: added PRIVILEGED PATH note — if blocked due to /root/ or
                other privileged location, explicitly offer sudo_delegation_block with
                sudo cat <path>. Root cause: S3 showed model reasoning correctly in
                thinking block but not surfacing the delegation offer in output
                (--reasoning-budget 0 suppresses thinking).
              - sudo_delegation_block: strengthened stop instruction — "output nothing
                further after this block." Root cause: P2 showed model continuing with
                post-execution instructions after emitting the delegation block.
    v1.5.4: get_context_status field-name fix + sudo_delegation_block READ-FIRST RULE.
              [get_context_status] Root cause: llama-server build >=9307 exposes
              n_prompt_tokens in /slots, not n_past. Always returned 0%.
              Fix: read n_prompt_tokens, n_prompt_tokens_cache, n_prompt_tokens_processed;
              n_decoded/n_remain/n_predict via next_token[0] and params.
              Added truncation warning when n_decoded >= n_predict and n_remain == 0.
              [sudo_delegation_block] Added READ-FIRST RULE: before delegating a
              privileged file write, read the target file first (read_file or
              execute_command cat). Root cause: P2 eval showed model issuing
              delegation block for /etc/sysctl.conf without reading it first,
              losing one point. Skipping the read when file is readable is now
              explicitly a protocol violation.
              Root cause: llama-server build ≥9307 exposes n_prompt_tokens in /slots,
              not n_past. s.get("n_past", 0) always defaulted to 0, making every
              context check report 0 / 32,768 tokens (0.0%) regardless of actual fill.
              Confirmed via live curl of /slots during A1 test run — slot retained
              n_prompt_tokens: 4264 (13.0% fill) while n_past was absent.
              Fix: read n_prompt_tokens, n_prompt_tokens_cache, n_prompt_tokens_processed
              from slot root; read n_decoded / n_remain / n_predict via next_token[0]
              and params respectively.
              Added truncation warning: flags when n_decoded >= n_predict and n_remain == 0
              (generation hit max_tokens cap). A1 test data showed last response truncated
              at exactly 1024 tokens — user should raise max_tokens in OpenWebUI settings.
    v1.5.3: sudo_delegation_block STOP PROTOCOL update.
              Previous: "output nothing further" — caused S3 partial fail because the
              tool result card in OpenWebUI is collapsed by default, so the command was
              invisible to the user (only "Paste output to continue." appeared in text).
              Fix: model must write exactly one echo line after the block:
              "Please run `<command>` in your terminal and paste the output here."
              This surfaces the command in visible text without reopening P2's
              continuation problem (which was multi-sentence post-execution guidance).
    v1.5.2: Denylist hardening — cross-referenced against earlier LSE supervisor project.
            Eight gaps identified and fixed:
              - Added to _BLOCKED_COMMANDS: shred, blkdiscard, sgdisk, partprobe
                (destructive disk tools missing from original list).
              - Added to _BLOCKED_COMMANDS: userdel, groupdel (account deletion).
              - Added to _BLOCKED_COMMANDS: rm -rf, rm -fr, rm -r -f, rm -f -r
                (recursive forced remove was only partially gated via _WRITE_OPS;
                rm -rf on user-owned paths like /home/sy5/ was not blocked at all).
              - Added to _BLOCKED_COMMANDS: fork bomb pattern ":(){ :|".
              - Added to _BLOCKED_COMMANDS: "> /dev/sd", "> /dev/nvme", "of=/dev/"
                (shell redirection into block devices; "dd of=/dev/sdb" slipped through
                the "dd if=" substring check).
              - Added /mnt/ to _PRIVILEGED_WRITE_PATHS: protects the Windows filesystem
                (/mnt/c, /mnt/d, etc.) from write/delete ops via execute_command.
              - Added "chmod -r " and "chown -r " to _WRITE_OPS: blocks recursive
                permission changes targeting privileged paths (chmod -R on user paths
                remains allowed).
              - fetch_url SSRF gate: not applicable — no fetch_url function exists yet.
                Deferred; gate must be added if fetch_url is ever introduced.
"""

from pydantic import BaseModel, Field
import subprocess
import os
from datetime import datetime


class Tools:

    class Valves(BaseModel):
        LOG_FILE: str = Field(
            default="/home/sy5/.lse/agent_commands.log",
            description="Path to the persistent agent command audit log.",
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
            default="http://localhost:8088/search",
            description="SearxNG JSON search endpoint (for search_web).",
        )
        EXTRA_WRITE_PATHS: str = Field(
            default="",
            description="Colon-separated extra paths the agent may write to.",
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
        # Filesystem destruction — disk/partition tools
        "mkfs", "fdisk", "parted", "sgdisk", "wipefs", "blkdiscard", "partprobe",
        "shred",
        # Block device writes — dd and shell redirection
        "dd if=", "of=/dev/",
        "> /dev/sd", "> /dev/nvme",
        # Recursive forced remove (all common flag orderings)
        "rm -rf", "rm -fr", "rm -r -f", "rm -f -r",
        # Fork bomb
        ":(){ :|",
        # Account deletion
        "userdel", "groupdel",
        # Privilege / credential management
        "passwd", "visudo",
        # Firewall flush
        "iptables -f", "iptables -F",
    )

    # v1.4.2: uses 'in' check (not startswith) to catch sudo in pipelines
    _PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")

    _PRIVILEGED_WRITE_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/", "/mnt/")

    _WRITE_OPS = ("cp ", "mv ", "rm ", "tee ", "> ", ">> ", "sed -i", "truncate", "dd ",
                  "chmod -r ", "chown -r ")

    # ── Initialiser ──────────────────────────────────────────────────────────

    def __init__(self):
        self.valves = self.Valves()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _norm(self, path: str) -> str:
        """Resolve symlinks and normalise path so prefix checks work correctly."""
        return os.path.realpath(os.path.expanduser(path)).rstrip("/") + "/"

    def _is_allowed_read(self, path: str) -> bool:
        normed = self._norm(path)
        return any(normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_READ_PREFIXES)

    def _is_allowed_write(self, path: str) -> bool:
        normed = self._norm(path)
        if any(normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_WRITE_PREFIXES):
            return True
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
            pass

    # ── Tool functions ────────────────────────────────────────────────────────

    def execute_command(self, command: str, working_dir: str = "") -> str:
        """
        Execute a read-only or write-safe shell command in the WSL Ubuntu environment.
        Use for: ls, cat, grep, find, ps, df, uname, systemctl status, apt list,
                 journalctl, tail, head, wc, etc.
        Do NOT use for commands requiring sudo — use sudo_delegation_block instead.
        Output is capped at MAX_OUTPUT_CHARS. Always pipe through grep/head/awk to limit output.

        COMBINE RULE — batch independent commands into a single call:
          GOOD: execute_command("uname -r && nproc")          ← one call, two results
          GOOD: execute_command("hostname; whoami; uptime")   ← one call, three results
          BAD:  execute_command("uname -r")                   ← then separate call for nproc
          BAD:  execute_command("nproc")                      ← should have been combined above
          Use && when the second command depends on the first succeeding.
          Use ; when commands are fully independent.
          Never make two execute_command calls when one combined call will do.

        Output filter examples:
          GOOD: execute_command("journalctl -u nginx -n 20 --no-pager")
          GOOD: execute_command("tail -20 /home/sy5/.bashrc")
          BAD:  execute_command("journalctl -u nginx")   ← no output limit
          BAD:  execute_command("sudo systemctl restart nginx")  ← use sudo_delegation_block
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

        # ── Block privilege escalation anywhere in the command (v1.4.2 fix) ──
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
                    "Re-run with more specific filters.]"
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
        Always read the smallest slice you need.

        CRITICAL ROUTING RULES — choose the right tool:

          • User asks for "last N lines" of any file
            → use execute_command("tail -N <path>")  NOT this function

          • User asks for lines matching a pattern
            → use execute_command("grep 'pattern' <path>")  NOT this function

          • You need to read a file BEFORE editing/overwriting it
            → use THIS function with max_lines large enough to get the ENTIRE file.
               Do NOT use tail or partial reads before an overwrite — partial reads
               cause data loss when the content is used to overwrite the full file.
               Check the line count first: execute_command("wc -l <path>")
               Then read all lines: read_file(path, max_lines=<total_lines>)

          • File is a log: use execute_command("tail -N <path>") or grep.

        Use read_file ONLY when you need a specific line range from the beginning or
        middle of a file where tail/grep do not apply.

        PRIVILEGED PATH BEHAVIOUR:
          If this function returns BLOCKED due to a privileged path (/root/, /proc/,
          /sys/, etc.), do NOT just report the block and stop. Explicitly offer the
          user a delegation block:
            "That path requires elevated access. Shall I read it via sudo?"
          Then call sudo_delegation_block with: sudo cat <path>
          This must appear in your response — do not leave it only in your reasoning.
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

        MODE SELECTION — choose carefully:
          mode='append'    → adds content to the END of the file. Use this for:
                             adding aliases, PATH entries, config lines, cron jobs,
                             or any single addition to an existing file.
                             Safe — does not risk losing existing content.

          mode='overwrite' → REPLACES the entire file. Only use when you have read
                             the COMPLETE file first using read_file (not tail, not
                             partial reads). If you used tail or partial reads,
                             use append mode instead to avoid data loss.

        CONFIRMATION PROTOCOL — mandatory for ALL writes:
          This function must NEVER be called without explicit user confirmation.
          The required sequence before calling write_file is:

          1. Show the user exactly what will be written (a diff or the full content).
          2. State which file will be modified and what mode will be used.
          3. Ask: "Shall I write this? (yes/no)"
          4. Wait for an explicit "yes" before calling this function.
          5. After writing, verify with: execute_command("tail -5 <path>") or read_file.

          This applies to new file creation AND edits to existing files.
          Skipping confirmation is a protocol violation.

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
        Use whenever an operation requires sudo or touches a privileged path
        (/etc/, systemctl enable/start/stop/restart, apt install/remove, etc.).
        Produces a formatted block for the user to run manually in their terminal.
        NEVER attempt to run sudo yourself. Always call this function instead.

        READ-FIRST RULE — mandatory for any privileged file modification:
          Before calling this function to delegate a write or append to a config
          file (e.g. /etc/sysctl.conf, /etc/hosts, /etc/fstab), first read the
          target file using read_file or execute_command('cat <path>'). This:
            - confirms the setting does not already exist
            - lets you compose the exact command correctly (append vs replace)
            - gives the user context for what will change
          If the file is unreadable (e.g. permission denied), note this in the
          reason field and proceed without the read.
          Skipping the read when the file IS readable is a protocol violation.

        STOP PROTOCOL — mandatory, no exceptions:
          After calling this function, write exactly ONE closing line that echoes the
          command so the user sees it without having to expand the tool result card.
          Format: "Please run `<command>` in your terminal and paste the output here."
          After that single line, output nothing further.
          Do NOT add post-execution instructions, hints, or follow-up bash snippets.
          Do NOT suggest what to do after the command succeeds.
          Your next response must begin only after the user pastes terminal output.
          Anything beyond the single echo line before user input is a protocol violation.
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
        Search the web via the local SearxNG instance at localhost:8088.
        GATE: Only call this when you cannot answer from your system prompt knowledge base.

        REQUIRED SEQUENCE — follow this exactly, no exceptions:
          Step 1: Write to the user BEFORE calling this function:
                  "Searching for [topic] because [reason training knowledge is insufficient]."
          Step 2: Call search_web exactly once for this topic.
          Step 3: Synthesise the answer in ≤3 sentences. Do NOT paste raw results verbatim.

        Skipping Step 1 is a protocol violation — do not call this function without
        first announcing what you are searching for and why.
        Do not call search_web more than once for the same topic.
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
        Call this when a session has had 5+ tool calls, or the user asks about context health.
        Do NOT call this for simple single-tool queries.
        Results drive compaction and hard-reset decisions described in the system prompt.
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

            # v1.5.4 fix: llama-server build >=9307 uses n_prompt_tokens, not n_past.
            # n_past does not exist in the /slots response; s.get("n_past", 0) always
            # returned 0, making every context check report 0% fill.
            n_prompt = s.get("n_prompt_tokens", 0)
            n_ctx    = s.get("n_ctx", 65536)
            n_cache  = s.get("n_prompt_tokens_cache", 0)
            n_proc   = s.get("n_prompt_tokens_processed", 0)

            # n_decoded and n_remain live inside next_token[0]; n_predict in params
            next_tok  = s.get("next_token", [{}])
            nt        = next_tok[0] if next_tok else {}
            n_decoded = nt.get("n_decoded", 0)
            n_remain  = nt.get("n_remain", -1)
            n_predict = s.get("params", {}).get("n_predict", 0)

            pct       = round(n_prompt / n_ctx * 100, 1) if n_ctx   else 0.0
            cache_pct = round(n_cache  / n_prompt * 100) if n_prompt else 0

            if pct >= 85:
                status = "🔴 CRITICAL — HARD RESET required before next tool call."
            elif pct >= 70:
                status = "🟠 HIGH — COMPACTION required before next tool call."
            elif pct >= 50:
                status = "🟡 ELEVATED — minimise tool output verbosity."
            else:
                status = "🟢 OK — normal operation."

            # Flag if the last generation was cut off by the max_tokens cap.
            truncation = ""
            if n_predict > 0 and n_remain == 0 and n_decoded >= n_predict:
                truncation = (
                    f"⚠️  Last response truncated at {n_decoded:,} tokens "
                    f"(hit max_tokens={n_predict} cap — raise in OpenWebUI model settings).\n"
                )

            return (
                f"Context: {n_prompt:,} / {n_ctx:,} tokens ({pct}%)\n"
                f"Prefix cache: {n_cache:,} cached / {n_proc:,} processed "
                f"({cache_pct}% hit rate)\n"
                f"Last generation: {n_decoded:,} tokens\n"
                f"{truncation}"
                f"Status: {status}"
            )
        except Exception as e:
            return f"ERROR querying llama.cpp: {str(e)}"
