"""
title: LSE System Admin Terminal
author: local-system-engineer
version: 1.5.8
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, read_file, write_file, sudo_delegation_block, search_web,
  get_github_release, get_context_status, and compact_context. All commands are logged
  to a persistent audit file. Privileged operations are blocked at the code level and
  routed through a delegation block.

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
    v1.5.5: sudo_delegation_block STOP PROTOCOL — added RETURN VALUE SEMANTICS to
              break a within-turn retry loop (29 calls observed in production).
              Root cause: model received the tool return value (the ⚠️ block string),
              interpreted it as "not the terminal output I requested", and retried
              the same call repeatedly. The STOP PROTOCOL told the model what to
              WRITE after calling the function but never explained that the return
              value IS the emitted block — the command has not run yet, stop all
              tool calls, yield to user.
              Fix: added RETURN VALUE SEMANTICS block immediately after the
              STOP PROTOCOL. Also removed the conflicting system-prompt rule
              "wrap output in bash code block" (see prompt v0.5.2) and the
              SUDO DELEGATION FORMAT section (format mismatch with actual output).
            read_file: added PRIVILEGED PATH BEHAVIOUR — no workarounds.
              Root cause: model tried cat → python3 → base64 in sequence when
              Docker volume paths returned permission denied. Added explicit
              prohibition: "Do NOT try cat, python3, or base64 as workarounds."
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
    v1.5.8: compact_context — true in-place context compaction tool.
              Truncates OpenWebUI chat message history via the OpenWebUI REST API,
              prepends a summary message to preserve session state, then erases the
              llama.cpp KV cache slot so the model starts fresh with the compacted
              history. Requires OWUI_API_KEY and OWUI_BASE_URL valves.
              New valves: OWUI_API_KEY, OWUI_BASE_URL.
    v1.5.7: execute_command DESTRUCTIVE OPERATION PROTOCOL — confirmation gate
              for rm and other irreversible commands.
              Root cause: Run 5 eval showed P1 and P3 confirmation protocol
              failures. P1 (write_file) has an explicit CONFIRMATION PROTOCOL
              in its docstring and the model follows it (M2 scored 2/3 with
              confirmation present). P3 (execute_command rm) has no equivalent
              gate — the model went straight to rm without warning or asking yes/no.
              Fix: added DESTRUCTIVE OPERATION PROTOCOL to execute_command docstring,
              mirroring the write_file pattern. Required sequence before any rm,
              truncate, or overwrite: warn → name target → ask yes/no → wait for
              explicit yes. Also applies to > redirects that would overwrite files.
    v1.5.6: Three fixes for Run 5 eval preconditions.
              [execute_command] Added POST-DELETE VERIFY RULE — after any rm command
              that succeeds, always follow up with a stat or ls call confirming the
              target no longer exists. Root cause: P3 eval showed model deleting
              /tmp/lse/hello.txt then immediately reporting "Done" without a
              verification call. Partial credit (1/3) — the verify step was skipped.
              [search_web] Added NO YEAR INJECTION rule — do not append a year to
              queries. Root cause: W2 eval showed model searching "llama.cpp latest
              stable release version 2025" despite system date being 2026. The model
              used its training-data estimate of the year rather than the system date,
              producing stale results and making 4 calls instead of 1.
              [get_github_release] New function — read-only GitHub API call that
              returns the latest release tag, name, and date for any public repo.
              Directly solves W2-class lookups (llama.cpp, open-webui version checks)
              without SearxNG and without date-injection risk.
"""

from pydantic import BaseModel, Field
import subprocess
import os
import json
import urllib.request
import urllib.error
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
        OWUI_API_KEY: str = Field(
            default="",
            description="OpenWebUI API key for compact_context (Bearer token). "
                        "Create in OpenWebUI → Settings → Account → API Keys.",
        )
        OWUI_BASE_URL: str = Field(
            default="http://localhost:3000",
            description="OpenWebUI base URL for compact_context API calls.",
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

        DESTRUCTIVE OPERATION PROTOCOL — mandatory before rm, truncate, or overwrite:
          Before executing any command that irreversibly deletes or overwrites data:
          1. Name the exact target in your response (file path or pattern).
          2. Warn the user: "This will permanently delete/overwrite <target>."
          3. Ask: "Shall I proceed? (yes/no)"
          4. Wait for an explicit "yes" before calling this function.
          This applies to: rm <file>, truncate, > (shell overwrite redirect),
          and any command whose primary effect is data destruction.
          It does NOT apply to: read-only commands, append (>>), or temp-file cleanup
          where the file was created in the same session by this agent.
          Proceeding without confirmation is a protocol violation.

        POST-DELETE VERIFY RULE — mandatory after any deletion:
          After any rm command that succeeds, immediately make a follow-up call to
          confirm the target no longer exists before reporting completion:
            GOOD: execute_command("rm /tmp/lse/file.txt && stat /tmp/lse/file.txt")
            GOOD: execute_command("ls /tmp/lse/")   ← follow-up call after rm succeeds
            BAD:  execute_command("rm /tmp/lse/file.txt")  ← then report "Done" with no verify
          Reporting the file as deleted without a verification call is a protocol violation.

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
          /sys/, etc.) or a permission denied error on any path:
          1. Do NOT try alternative commands. Do NOT attempt:
               execute_command("cat <path>")
               execute_command("python3 -c \"open('<path>').read()\"")
               execute_command("base64 <path>")
             These will also fail and cause a retry loop. Stop immediately.
          2. Explicitly offer the user a delegation block:
               "That path requires elevated access. Shall I read it via sudo?"
          3. Call sudo_delegation_block with: sudo cat <path>
          This must appear in your response — do not leave it only in your reasoning.
          Trying workarounds before delegating is a protocol violation.
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

        RETURN VALUE SEMANTICS — read this before calling:
          This function returns the formatted delegation block as a string.
          The return value IS the block that has been shown to the user.
          It is NOT the terminal output you are waiting for — the command
          has not run yet. It is now in the user's hands.
          Do NOT call this function again for the same command.
          Do NOT make any further tool calls in this turn after calling this function.
          Calling this function more than once for the same command before the user
          responds is a protocol violation.

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

        NO YEAR INJECTION — do not append a year to the query:
          WRONG: search_web("llama.cpp latest release 2025")
          RIGHT: search_web("llama.cpp latest release")
          The current date is in your system prompt. Use it if recency matters.
          Do not use your training-data estimate of the year — it may be stale.
          For version lookups of GitHub projects, prefer get_github_release instead.
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

    def get_github_release(self, repo: str) -> str:
        """
        Return the latest release tag, name, and publish date for a public GitHub repository.
        Use this for version lookups — it is faster and more reliable than search_web
        and avoids date-injection problems.

        WHEN TO USE:
          - Checking the latest llama.cpp release:   get_github_release("ggerganov/llama.cpp")
          - Checking the latest open-webui release:  get_github_release("open-webui/open-webui")
          - Any public GitHub project where you need the current version number.

        WHEN NOT TO USE:
          - Projects not hosted on GitHub (use search_web instead).
          - Package versions managed by apt/pip (use execute_command with apt-cache or pip index).

        Do NOT append a year or any date to the repo string.
        The repo parameter must be in "owner/name" format, e.g. "ggerganov/llama.cpp".
        """
        import requests  # noqa: PLC0415

        repo = repo.strip().strip("/")
        if "/" not in repo or len(repo.split("/")) != 2:
            return f"ERROR: Invalid repo format '{repo}'. Expected 'owner/name'."

        url = f"https://api.github.com/repos/{repo}/releases/latest"
        self._log(f"GITHUB-RELEASE: {repo}")
        try:
            resp = requests.get(
                url,
                headers={"Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"},
                timeout=10,
            )
            if resp.status_code == 404:
                return f"No releases found for '{repo}' (repo may not exist or have no releases)."
            resp.raise_for_status()
            data = resp.json()
            tag        = data.get("tag_name", "unknown")
            name       = data.get("name", tag)
            published  = data.get("published_at", "unknown date")[:10]  # YYYY-MM-DD
            prerelease = data.get("prerelease", False)
            draft      = data.get("draft", False)
            html_url   = data.get("html_url", "")

            flags = []
            if prerelease:
                flags.append("pre-release")
            if draft:
                flags.append("draft")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            return (
                f"Latest release: {tag}{flag_str}\n"
                f"Name:           {name}\n"
                f"Published:      {published}\n"
                f"URL:            {html_url}"
            )
        except Exception as e:
            return f"ERROR querying GitHub API: {str(e)}"

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

    def compact_context(
        self,
        summary: str,
        __chat_id__: str = "",
    ) -> str:
        """
        Truncate OpenWebUI chat history and flush the KV cache to reclaim context.

        WHEN TO CALL:
          Call this when get_context_status reports >= 70% fill, or when the user
          asks to "compact", "clear", or "reset" the context.

        REQUIRED ARGUMENT:
          summary — a concise plain-text paragraph (3–8 sentences) capturing every
          fact, file path, command outcome, decision, and pending task from this
          session that must survive the compaction. Write it in third person as if
          briefing the next agent. DO NOT omit anything the user will need to
          reference. Example:
            "Session: user is on LUCIFER (WSL2, RTX 4090, Ubuntu 24.04).
             Rebuilt llama.cpp at b9316 with -DCMAKE_CUDA_ARCHITECTURES=89.
             Deployed llamacpp-slots-exporter on port 9839 (systemd, running).
             Grafana panel 9 updated to use llamacpp_slot_fill_ratio.
             Pending: run eval suite v3.5 against tool v1.5.8 + prompt v0.5.4."

        WHAT THIS FUNCTION DOES:
          1. Fetches the full OpenWebUI chat history for this chat.
          2. Traverses the active message branch (root → currentId).
          3. Keeps only the last 4 messages (2 user + 2 assistant turns).
          4. Prepends a system-role summary message so the model retains session state.
          5. Writes the truncated history back via POST /api/v1/chats/{id}.
          6. Erases the llama.cpp KV cache slot via POST /slots/0 {"action":"erase"}.
          7. Returns a confirmation string for the model to echo to the user.

        AFTER CALLING:
          Emit exactly this line to the user (do not add anything else):
          "Context compacted. Session state preserved in summary. KV cache cleared."
          The next message will begin with a fresh context window.
        """
        if not self.valves.OWUI_API_KEY:
            return "ERROR: OWUI_API_KEY valve is not set. Configure it in OpenWebUI tool settings."

        if not __chat_id__:
            return "ERROR: __chat_id__ not injected. This tool must be called from within an OpenWebUI chat."

        api_base = self.valves.OWUI_BASE_URL.rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.valves.OWUI_API_KEY}",
            "Content-Type": "application/json",
        }

        def owui_get(path: str):
            req = urllib.request.Request(f"{api_base}{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

        def owui_post(path: str, payload: dict):
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{api_base}{path}", data=data, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

        try:
            # ── 1. Fetch the chat ─────────────────────────────────────────────
            chat = owui_get(f"/api/v1/chats/{__chat_id__}")

            history = chat.get("chat", {}).get("history", {})
            messages_map = history.get("messages", {})
            current_id = history.get("currentId", "")

            if not messages_map or not current_id:
                return "ERROR: Chat history is empty or malformed — nothing to compact."

            # ── 2. Traverse the active branch from leaf to root ───────────────
            branch = []
            node_id = current_id
            visited = set()
            while node_id and node_id not in visited:
                visited.add(node_id)
                msg = messages_map.get(node_id)
                if not msg:
                    break
                branch.append(msg)
                node_id = msg.get("parentId") or ""
            branch.reverse()  # now root → leaf (chronological)

            total_before = len(branch)

            # ── 3. Keep last 4 messages ───────────────────────────────────────
            KEEP = 4
            kept = branch[-KEEP:] if len(branch) > KEEP else branch

            # ── 4. Build summary node (system role, no parent) ────────────────
            import uuid as _uuid
            summary_id = str(_uuid.uuid4())
            summary_msg = {
                "id": summary_id,
                "parentId": None,
                "childrenIds": [kept[0]["id"]] if kept else [],
                "role": "system",
                "content": (
                    f"[CONTEXT COMPACTION SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n"
                    f"{summary}\n\n"
                    f"(History truncated from {total_before} → {len(kept)} messages. "
                    f"Resume from this point.)"
                ),
                "timestamp": int(datetime.now().timestamp()),
            }

            # Patch the first kept message to point back to the summary node
            if kept:
                kept[0] = dict(kept[0])
                kept[0]["parentId"] = summary_id

            # ── 5. Rebuild history dict ───────────────────────────────────────
            new_messages = {summary_msg["id"]: summary_msg}
            for msg in kept:
                new_messages[msg["id"]] = msg

            new_history = {
                "currentId": kept[-1]["id"] if kept else summary_id,
                "messages": new_messages,
            }

            # ── 6. Write truncated history back ───────────────────────────────
            # Preserve the full chat object, only replace history
            chat_body = chat.get("chat", {})
            chat_body["history"] = new_history
            owui_post(f"/api/v1/chats/{__chat_id__}", {"chat": chat_body})

            # ── 7. Erase KV cache slot ────────────────────────────────────────
            kv_status = "KV cache erase skipped"
            try:
                slots_url = self.valves.LLAMA_SERVER_URL.rstrip("/") + "/slots/0"
                erase_payload = json.dumps({"action": "erase"}).encode()
                kv_req = urllib.request.Request(
                    slots_url,
                    data=erase_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(kv_req, timeout=5) as resp:
                    kv_status = f"KV cache erased (slot 0, HTTP {resp.status})"
            except Exception as kv_err:
                kv_status = f"KV cache erase failed: {kv_err}"

            return (
                f"Compacted: {total_before} → {len(kept) + 1} messages "
                f"({total_before - len(kept)} dropped). "
                f"Summary node prepended. {kv_status}."
            )

        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return f"ERROR: OpenWebUI API returned HTTP {e.code}: {body[:300]}"
        except Exception as e:
            return f"ERROR during compact_context: {str(e)}"
   