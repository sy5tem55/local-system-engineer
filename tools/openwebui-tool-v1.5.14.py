"""
title: LSE System Admin Terminal
author: local-system-engineer
version: 1.5.14
requirements: elasticsearch==8.19.3, requests
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, read_file, write_file, sudo_delegation_block, search_web,
  get_github_release, get_context_status, compact_context, search_kb, index_to_kb,
  record_error, check_error_kb, record_outcome, and mentor_correct. All commands are logged
  to a persistent audit file. Privileged operations are blocked at the code level and
  routed through a delegation block.

  Changelog:
    v1.5.14: sudo_delegation_block presentation improvements (Fix 3 — Run 6 gaps).
              [sudo_delegation_block] Added step_number, total_steps, verify_command params.
              When step_number > 0, the block header reads "Step N of Total".
              verify_command surfaced as labelled "Verify with:" step in block body.
              expected_output_hint retained for backward compatibility (secondary).
              THINKING PHASE RULE added: never call inside a reasoning/thinking block.
              [LOG_FILE] Default moved from ~/.lse/ to /opt/local-se/.
    v1.5.13: search_web header fix + categories fix.
              Root cause: SearXNG limiter (limiter: true) rejects requests without
              X-Forwarded-For/X-Real-IP headers with HTTP 429. LSE was sending no
              headers, causing silent failures mid-session.
              Fix 1: added X-Forwarded-For and X-Real-IP headers to requests.get().
              Fix 2: changed categories from "general,it" to "general,it,science" —
              confirmed during SearXNG deploy that arxiv, github, google scholar,
              stackoverflow, semantic scholar only fire on science category.
              Verified: 11 engines active, 108 results on q=llama.cpp.
    v1.5.12: write_file SIZE SANITY CHECK + record_outcome + mentor_correct.
              [write_file] Added SIZE SANITY CHECK: if mode='overwrite' and new content
              is <25% of existing file's line count, function returns an error requiring
              explicit user confirmation before proceeding. Override with force=True
              after user confirms intentional truncation.
              Root cause: LSE destroyed a 323-line GUI PowerShell file by calling
              write_file in overwrite mode with a 5-line snippet. The docstring required
              read + confirmation but compliance was zero under recovery-loop pressure.
              The code-level gate is the only reliable enforcement.
              [record_outcome] New RAG function: records success/failure outcome against
              an existing KB doc. Increments empirical_runs, success_count, failure_count.
              Surfaces whether documented procedures actually work in production.
              [mentor_correct] New RAG function: applies a human-authored correction to
              a KB doc. Re-embeds corrected content, raises quality_score (never lowers),
              increments refinement_count. Used when user identifies an error in the KB.
              Both functions were referenced in prompt v0.5.9 TOOLS section but missing
              from tool v1.5.11. Gap identified during 2026-06-02 tracking restructure.
    v1.5.11: fetch_url — HTML-stripped full-page fetch for SEARCH-THEN-FETCH protocol.
              monitor_download — Prometheus-backed download progress monitor.
              (Note: both were added without changelog entries — reconstructed 2026-06-02.)
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
    v1.5.9: RAG layer — Elasticsearch + nomic-embed-text knowledge base.
              Four new tool functions: search_kb, index_to_kb, record_error, check_error_kb.
              New valves: ES_URL, OLLAMA_URL, EMBED_MODEL.
              KB-FIRST RULE added to search_web: always query search_kb before SearxNG.
              index_to_kb deduplicates (cosine > 0.92 → refine, not duplicate).
              Error KB: record_error logs mistakes + resolution; check_error_kb prevents recurrence.
              Infrastructure: elasticsearch:8.17.0 on docker_searxng_net, Ollama nomic-embed-text
              CPU-only on 127.0.0.1:11434. 12 docs / 32 chunks seeded at quality 0.3–0.6.
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
            default="/opt/local-se/agent_commands.log",
            description="Path to the persistent agent command audit log. "
                        "Moved from ~/.lse/ (root-owned, privileged) to /opt/local-se/ "
                        "(sy5-writable). Update valve if path differs.",
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
        OWUI_DB_PATH: str = Field(
            default="/home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db",
            description="Absolute path to the OpenWebUI SQLite database (webui.db). "
                        "Used by compact_context to write chat history directly, "
                        "bypassing the HTTP deadlock caused by single-worker uvicorn.",
        )
        ES_URL: str = Field(
            default="http://127.0.0.1:9200",
            description="Elasticsearch base URL for the RAG knowledge base (lse-kb index).",
        )
        OLLAMA_URL: str = Field(
            default="http://127.0.0.1:11434",
            description="Ollama base URL for nomic-embed-text embeddings (CPU-only, no GPU).",
        )
        EMBED_MODEL: str = Field(
            default="nomic-embed-text",
            description="Ollama embedding model (768-dim). Must be pulled via 01-ollama-setup.sh.",
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

    def write_file(
        self, path: str, content: str, mode: str = "overwrite", force: bool = False
    ) -> str:
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

        SIZE SANITY CHECK — automatic guard on overwrite:
          If mode='overwrite' and the new content has fewer than 25% of the lines
          in the existing file, this function returns an error. This prevents
          accidentally destroying a large file by writing a short snippet.

          When the check fires:
          1. Show the user the line count discrepancy.
          2. Ask explicitly: "The new content is N lines vs M existing. Intentional?"
          3. Wait for explicit "yes".
          4. Call write_file again with force=True to bypass the check.

          force=True ONLY after explicit user confirmation of intentional truncation.
          Passing force=True without user confirmation is a protocol violation.

        For files under /etc/ or other privileged paths, use sudo_delegation_block.
        """
        if not self._is_allowed_write(path):
            return (
                f"BLOCKED: '{path}' is outside allowed write paths. "
                "Use sudo_delegation_block for privileged paths."
            )

        resolved = os.path.realpath(os.path.expanduser(path))
        parent = os.path.dirname(resolved)

        # ── SIZE SANITY CHECK (v1.5.12) ───────────────────────────────────────
        if mode == "overwrite" and not force and os.path.isfile(resolved):
            try:
                with open(resolved, "r", errors="replace") as f:
                    existing_lines = len(f.readlines())
                new_lines = max(len(content.splitlines()), 1)
                if existing_lines > 0 and new_lines < existing_lines * 0.25:
                    pct = new_lines * 100 // existing_lines
                    self._log(
                        f"SIZE-CHECK-BLOCKED: {path} existing={existing_lines} new={new_lines}"
                    )
                    return (
                        f"SIZE SANITY CHECK FAILED: '{path}' currently has {existing_lines} lines. "
                        f"New content has {new_lines} lines ({pct}% of current size). "
                        f"Writing this would truncate the file to less than 25% of its current size. "
                        f"Show the user this discrepancy and ask for explicit confirmation. "
                        f"Once the user confirms the truncation is intentional, call write_file "
                        f"again with force=True."
                    )
            except Exception:
                pass  # If comparison fails, proceed — don't block on a check error

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
        self,
        command: str,
        reason: str,
        expected_output_hint: str = "",
        step_number: int = 0,
        total_steps: int = 0,
        verify_command: str = "",
    ) -> str:
        """
        Use whenever an operation requires sudo or touches a privileged path
        (/etc/, systemctl enable/start/stop/restart, apt install/remove, etc.).
        Produces a formatted block for the user to run manually in their terminal.
        NEVER attempt to run sudo yourself. Always call this function instead.

        ARGS:
          command           — The exact command the user must run.
          reason            — One sentence explaining why this delegation is needed.
          expected_output_hint — (secondary) Free-text hint about success. Prefer verify_command.
          step_number       — Position in a multi-step sequence (1-based). When > 0, block
                              header reads "Step N of Total". Pass 0 for standalone blocks.
          total_steps       — Total delegation blocks in sequence. Required when step_number > 0.
          verify_command    — Explicit follow-up command to confirm success. Surfaced as a
                              labelled "Verify with:" step — not buried in expected_output_hint.

        THINKING PHASE RULE — never call inside a reasoning block:
          This function must only be called in the response phase, after thinking has closed.
          A delegation block inside a <think> block is collapsed in OpenWebUI — the user must
          expand it to find the command. Complete all reasoning first, then call this function.
          Calling sudo_delegation_block during thinking is a protocol violation.

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

        if step_number > 0 and total_steps > 0:
            step_line = f"Step {step_number} of {total_steps}\n"
        else:
            step_line = ""

        if verify_command:
            verify_line = f"Verify with:\n\n  {verify_command}\n\n"
        elif expected_output_hint:
            verify_line = f"Expected output: {expected_output_hint}\n\n"
        else:
            verify_line = ""

        block = (
            f"⚠️  SUDO REQUIRED — Action delegated to user\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{step_line}"
            f"Reason: {reason}\n\n"
            f"Run this in your terminal:\n\n"
            f"  {command}\n\n"
            f"{verify_line}"
            f"Paste the full terminal output here to continue.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        return block

    def search_web(self, query: str, max_results: int = 5) -> str:
        """
        Search the web via the local SearxNG instance at localhost:8088.

        KB-FIRST RULE — mandatory, no exceptions:
          ALWAYS call search_kb() before calling this function.
          If search_kb() returns results with quality_score >= 0.6, use those directly.
          Only call search_web() when search_kb() returns "KB miss" or quality < 0.6.
          After finding a good result here, call index_to_kb() to store it for next time.
          Skipping search_kb() before search_web() is a protocol violation.

        GATE: Only call this when search_kb() has been called first and returned a miss.

        REQUIRED SEQUENCE — follow this exactly, no exceptions:
          Step 1: Write to the user BEFORE calling this function:
                  "Searching for [topic] because [reason training knowledge is insufficient]."
          Step 2: Call search_web exactly once for this topic.
          Step 3: SEARCH-THEN-FETCH — if the snippet (≤300 chars) is too short to answer
                  the question fully, call fetch_url() on the top result URL to get the
                  full page content before synthesising. Skip fetch if snippet is sufficient.
          Step 4: Synthesise the answer in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

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
                params={"q": query, "format": "json", "categories": "general,it,science"},
                headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
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

    def fetch_url(self, url: str, max_chars: int = 3000) -> str:
        """
        Fetch the full text content of a URL. Use as Step 3 of the SEARCH-THEN-FETCH
        protocol when search_web returns a snippet too short to answer the question.

        WHEN TO CALL:
          After search_web, if the snippet (≤300 chars) is truncated or insufficient.
          Call on the top result URL only — do not fetch multiple URLs per search.

        WHEN NOT TO CALL:
          If the search_web snippet already answers the question fully.
          Do not use as a substitute for search_web — always search first.

        Returns plain text with HTML tags stripped, capped at max_chars characters.
        """
        import requests  # noqa: PLC0415
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._text = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip and data.strip():
                    self._text.append(data.strip())

            def get_text(self):
                return " ".join(self._text)

        self._log(f"FETCH: {url}")
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            parser = _TextExtractor()
            parser.feed(resp.text)
            text = parser.get_text()[:max_chars]
            return text or "No text content extracted."
        except Exception as e:
            return f"ERROR fetching {url}: {e}"

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
            n_prompt = s.get("n_prompt_tokens", 0)
            n_ctx    = s.get("n_ctx", 65536)
            n_cache  = s.get("n_prompt_tokens_cache", 0)
            n_proc   = s.get("n_prompt_tokens_processed", 0)

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

    def monitor_download(self, file_path: str, expected_bytes: int, interface: str = "") -> str:
        """
        Check download progress using Prometheus network metrics + file size.
        Returns a single status line with completion %, speed, ETA, and SLEEP N.

        PROTOCOL (zero-polling — one call, one sleep, one check):
          1. result = monitor_download(path, size)
          2. COMPLETE  → proceed to next block, call record_outcome()
          3. STALLED   → alert user immediately, do not sleep-loop
          4. Otherwise → parse SLEEP N from result → execute_command("sleep N") → goto 1

        OUTPUT:
          DOWNLOADING | 26.3% | 4.21/16.0 GB | 28.3 MB/s (eth0) | ETA 423s | SLEEP 472
          COMPLETE    | 100%  | 16.0/16.0 GB | elapsed 10m 17s
          STALLED     | 26.3% | 4.21/16.0 GB | 0.0 MB/s | no traffic on eth0 | SLEEP 30

        Speed source: Prometheus localhost:9090 — same data as Grafana Network Download
          Speed dashboard at http://localhost:3002/d/lse-net-speed-01/network-download-speed
        Sleep buffer: SLEEP = ceil(ETA * 1.08 + 15)
        Script: /opt/local-se/download-monitor.py — deploy once if not present.
        """
        import subprocess  # noqa: PLC0415
        import shutil      # noqa: PLC0415
        import os as _os   # noqa: PLC0415

        monitor_script = "/opt/local-se/download-monitor.py"
        python_bin = "/home/sy5/miniforge3/bin/python3"
        if not shutil.which("python3"):
            python_bin = "python3"

        if not _os.path.exists(monitor_script):
            return (
                "SETUP_REQUIRED | download-monitor.py not found at /opt/local-se/. "
                "Deploy: write_file /opt/local-se/download-monitor.py from "
                "tools/download-monitor.py in the LSE repo, then chmod +x."
            )

        cmd = [python_bin, monitor_script, file_path, str(expected_bytes)]
        if interface:
            cmd.append(interface)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip()
            if not output and result.stderr:
                return f"ERROR | {result.stderr.strip()}"
            return output if output else "ERROR | no output from monitor script"
        except subprocess.TimeoutExpired:
            return "ERROR | monitor script timed out (Prometheus unreachable)"
        except Exception as exc:
            return f"ERROR | {exc}"

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
          reference.

        WHAT THIS FUNCTION DOES:
          1. Fetches the full OpenWebUI chat history for this chat.
          2. Traverses the active message branch (root → currentId).
          3. Keeps only the last 4 messages (2 user + 2 assistant turns).
          4. Prepends a system-role summary message so the model retains session state.
          5. Writes the truncated history back directly to the OpenWebUI SQLite DB.
          6. Erases the llama.cpp KV cache slot via POST /slots/0 {"action":"erase"}.
          7. Returns a confirmation string for the model to echo to the user.

        AFTER CALLING:
          Emit exactly this line to the user (do not add anything else):
          "Context compacted. Session state preserved in summary. KV cache cleared."
          The next message will begin with a fresh context window.
        """
        if not __chat_id__:
            return "ERROR: __chat_id__ not injected. This tool must be called from within an OpenWebUI chat."

        import sqlite3
        import uuid as _uuid

        DB_PATH = self.valves.OWUI_DB_PATH

        try:
            con = sqlite3.connect(DB_PATH, timeout=10)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT chat FROM chat WHERE id = ?", (__chat_id__,))
            row = cur.fetchone()
            if not row:
                con.close()
                return f"ERROR: chat id '{__chat_id__}' not found in DB."

            chat_obj  = json.loads(row["chat"])
            history   = chat_obj.get("history", {})
            messages_map = history.get("messages", {})
            current_id   = history.get("currentId", "")

            if not messages_map or not current_id:
                return "ERROR: Chat history is empty or malformed — nothing to compact."

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
            branch.reverse()

            total_before = len(branch)
            KEEP = 4
            kept = branch[-KEEP:] if len(branch) > KEEP else branch

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

            if kept:
                kept[0] = dict(kept[0])
                kept[0]["parentId"] = summary_id

            new_messages = {summary_msg["id"]: summary_msg}
            for msg in kept:
                new_messages[msg["id"]] = msg

            new_history = {
                "currentId": kept[-1]["id"] if kept else summary_id,
                "messages": new_messages,
            }

            chat_obj["history"] = new_history
            cur.execute(
                "UPDATE chat SET chat = ? WHERE id = ?",
                (json.dumps(chat_obj), __chat_id__),
            )
            con.commit()
            con.close()

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

        except Exception as e:
            return f"ERROR during compact_context: {str(e)}"

    # ── RAG private helpers ──────────────────────────────────────────────────

    def _embed(self, text: str) -> list:
        """768-dim embedding from Ollama nomic-embed-text (CPU-only, no GPU pressure)."""
        import requests  # noqa: PLC0415
        r = requests.post(
            f"{self.valves.OLLAMA_URL}/api/embed",
            json={"model": self.valves.EMBED_MODEL,
                  "input": "search_query: " + text[:5000]},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["embeddings"][0]

    def _es(self):
        """Lazy Elasticsearch 8.x client."""
        from elasticsearch import Elasticsearch  # noqa: PLC0415
        return Elasticsearch(self.valves.ES_URL, request_timeout=10)

    # ── RAG tool functions ───────────────────────────────────────────────────

    def search_kb(
        self,
        query: str,
        min_score: float = 0.72,
        max_results: int = 5,
        topic_filter: str = "",
    ) -> str:
        """
        Search the LSE knowledge base using semantic + keyword hybrid search.

        KB-FIRST RULE — mandatory:
          ALWAYS call this before search_web or any SearxNG query.
          The KB contains curated, locally-verified technical knowledge about this system.
          Searching the web for something already in the KB is a protocol violation.

        RESULT QUALITY:
          Each result includes a quality_score (0.0–1.0):
            0.3 = stub / single fact — verify before using
            0.5 = rough first draft — usable but may be incomplete
            0.6 = reasonable coverage — good starting point
            0.8 = web-verified — cross-referenced with live source
            1.0 = authoritative — manually verified or official docs

        ON MISS:
          If this returns "KB miss", fall through to search_web(). Then call
          index_to_kb() with the best result to grow the KB for next time.

        Args:
            query:        Natural language search query.
            min_score:    Cosine similarity threshold (0–1). Default 0.72.
            max_results:  Max results to return. Default 5.
            topic_filter: Optional topic tag: 'comfyui', 'wan2.1', 'searxng',
                          'llama-cpp', 'pfsense', 'infrastructure', 'openwebui'.
        """
        self._log(f"SEARCH-KB: {query}")
        try:
            embedding = self._embed(query)
            es = self._es()
            filter_clause = [{"term": {"topic": topic_filter}}] if topic_filter else []
            body = {
                "knn": {"field": "embedding", "query_vector": embedding,
                        "k": max_results, "num_candidates": 50, "boost": 0.7},
                "query": {"bool": {
                    "must": [{"multi_match": {"query": query,
                                             "fields": ["title^2", "content"],
                                             "boost": 0.3}}],
                    "filter": filter_clause,
                }},
                "_source": ["title", "content", "source_path", "source_url",
                            "topic", "quality_score", "updated_at"],
                "size": max_results,
            }
            resp = es.search(index="lse-kb", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= min_score]
            if not hits:
                return (
                    f"KB miss — no results above threshold {min_score} for '{query}'.\n"
                    "Fall through to search_web(), then call index_to_kb() with quality results."
                )
            lines = [f"KB results for '{query}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                src = s.get("source_path") or s.get("source_url") or "unknown"
                lines.append(
                    f"[{i}] {s['title']} | topic={s['topic']} | "
                    f"quality={s['quality_score']:.2f} | score={h['_score']:.3f}\n"
                    f"    source: {src}\n"
                    f"    {s['content'][:400].strip()}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            self._log(f"SEARCH-KB ERROR: {e}")
            return f"KB search error: {e}\nFall through to search_web()."

    def index_to_kb(
        self,
        content: str,
        title: str,
        topic: str,
        source_url: str = "",
        quality_score: float = 0.8,
    ) -> str:
        """
        Index a document into the LSE knowledge base (lse-kb index).

        WHEN TO CALL:
          After finding high-quality information from search_web() or Playwright
          that is not already in the KB, or that is better than what's there.
          Call this every time you find something worth keeping — it grows the KB.

        DEDUPLICATION:
          If a nearly identical document already exists (cosine > 0.92), this
          UPDATES the existing entry rather than duplicating it. quality_score
          is raised to max(existing, new). The KB improves over time.

        Args:
            content:       Full text to index.
            title:         Human-readable title.
            topic:         Use existing tags: 'wan2.1', 'comfyui', 'stable-diffusion',
                           'llama-cpp', 'searxng', 'pfsense', 'openwebui',
                           'lse-operations', 'infrastructure', 'general'.
            source_url:    URL where found (empty string for local content).
            quality_score: 0.0–1.0. Web-sourced=0.8, verified=1.0.
        """
        import hashlib  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415
        self._log(f"INDEX-KB: title={title} topic={topic} quality={quality_score}")
        try:
            embedding = self._embed(content)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]
            dup_resp = es.search(index="lse-kb", body={
                "knn": {"field": "embedding", "query_vector": embedding,
                        "k": 1, "num_candidates": 10},
                "_source": ["quality_score", "refinement_count", "version"],
                "size": 1,
            })
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.92:
                existing = dup_hits[0]
                new_q = min(1.0, max(existing["_source"]["quality_score"], quality_score))
                es.update(index="lse-kb", id=existing["_id"], body={"doc": {
                    "content": content, "embedding": embedding,
                    "quality_score": new_q,
                    "refinement_count": existing["_source"]["refinement_count"] + 1,
                    "updated_at": now,
                    "version": existing["_source"]["version"] + 1,
                    "source_url": source_url or None,
                }})
                return (
                    f"KB updated (refined): doc_id={existing['_id']} | "
                    f"quality {existing['_source']['quality_score']:.2f} → {new_q:.2f} | "
                    f"refinements={existing['_source']['refinement_count'] + 1}"
                )
            doc = {
                "doc_id": doc_hash, "title": title, "content": content,
                "source_path": None, "source_url": source_url or None,
                "topic": topic, "tags": [topic],
                "quality_score": quality_score, "refinement_count": 0,
                "embedding": embedding, "created_at": now, "updated_at": now, "version": 1,
            }
            es.index(index="lse-kb", id=doc_hash, document=doc)
            return (
                f"KB created: doc_id={doc_hash} | title='{title}' | "
                f"topic={topic} | quality={quality_score:.2f}"
            )
        except Exception as e:
            self._log(f"INDEX-KB ERROR: {e}")
            return f"KB index error: {e}"

    def record_error(self, error_text: str, context: str, resolution: str) -> str:
        """
        Record an error and its resolution to the LSE error knowledge base.

        MANDATORY — call this after recovering from ANY mistake:
          After fixing any error (command failure, wrong path, permission denied,
          wrong flag, broken pipe, etc.), call this so the same mistake is never
          made again in any future session.

        Args:
            error_text:  The exact error message or clear description of the failure.
            context:     What you were trying to do when the error occurred.
            resolution:  Exactly what fixed it.
        """
        import hashlib, re  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415
        self._log(f"RECORD-ERROR: {error_text[:80]}")
        try:
            embedding = self._embed(error_text + " " + context)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            normalised = re.sub(r'\s+', ' ', error_text.lower().strip())
            error_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]
            dup_resp = es.search(index="lse-errors", body={
                "knn": {"field": "embedding", "query_vector": embedding,
                        "k": 1, "num_candidates": 10},
                "_source": ["occurrence_count"],
                "size": 1,
            })
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.90:
                existing = dup_hits[0]
                new_count = existing["_source"]["occurrence_count"] + 1
                es.update(index="lse-errors", id=existing["_id"], body={"doc": {
                    "last_seen": now, "occurrence_count": new_count,
                    "resolution": resolution,
                }})
                return f"Error KB updated: known error now seen {new_count}x. Resolution updated."
            doc = {
                "error_hash": error_hash, "error_text": error_text,
                "context": context, "resolution": resolution,
                "embedding": embedding, "occurrence_count": 1,
                "first_seen": now, "last_seen": now,
            }
            es.index(index="lse-errors", id=error_hash, document=doc)
            return f"Error KB created: new error pattern recorded (hash={error_hash})."
        except Exception as e:
            self._log(f"RECORD-ERROR ERROR: {e}")
            return f"Error KB record failed: {e}"

    def check_error_kb(self, error_text: str) -> str:
        """
        Check if an error has been seen before and retrieve its known resolution.

        KB-FIRST RULE — call this BEFORE any operation that might fail in a known way.
          Surface the resolution immediately rather than hitting the same failure again.

        Args:
            error_text: The error message or description to look up.
        """
        self._log(f"CHECK-ERROR-KB: {error_text[:80]}")
        try:
            embedding = self._embed(error_text)
            es = self._es()
            resp = es.search(index="lse-errors", body={
                "knn": {"field": "embedding", "query_vector": embedding,
                        "k": 1, "num_candidates": 10},
                "_source": ["error_text", "resolution", "occurrence_count", "last_seen"],
                "size": 1,
            })
            hits = resp["hits"]["hits"]
            if hits and hits[0]["_score"] >= 0.88:
                h = hits[0]["_source"]
                return (
                    f"⚠️ KNOWN ERROR (seen {h['occurrence_count']}x, "
                    f"last: {h['last_seen'][:10]})\n"
                    f"Error: {h['error_text'][:200]}\n"
                    f"Resolution: {h['resolution']}\n"
                    f"Apply the known resolution — do not repeat the failed approach."
                )
            return (
                "Not seen before — proceed carefully. "
                "Call record_error() after resolving to prevent recurrence."
            )
        except Exception as e:
            self._log(f"CHECK-ERROR-KB ERROR: {e}")
            return f"Error KB check failed: {e}. Proceed with caution."

    def record_outcome(
        self,
        doc_id: str,
        success: bool,
        notes: str = "",
    ) -> str:
        """
        Record an operational outcome against an existing KB document.

        WHEN TO CALL:
          After applying a procedure documented in the KB:
            success=True  — the documented approach worked as described.
            success=False — it failed or needed modification. Also call record_error().

          Increments empirical_runs, success_count, and failure_count on the KB doc
          so the LSE can track how many times a procedure has been tested in production
          and whether it reliably works.

        Args:
            doc_id:   The doc_id field from a search_kb or index_to_kb result.
            success:  True if the procedure succeeded, False if it failed.
            notes:    Optional context: variant used, environment, what differed, etc.
        """
        from datetime import timezone  # noqa: PLC0415
        self._log(f"RECORD-OUTCOME: doc_id={doc_id} success={success}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resp = es.get(
                index="lse-kb", id=doc_id,
                _source=["empirical_runs", "success_count", "failure_count", "title"],
            )
            src = resp["_source"]
            runs          = src.get("empirical_runs", 0) + 1
            success_count = src.get("success_count",  0) + (1 if success else 0)
            failure_count = src.get("failure_count",  0) + (0 if success else 1)
            update: dict = {
                "empirical_runs": runs,
                "success_count":  success_count,
                "failure_count":  failure_count,
                "last_outcome_at": now,
            }
            if notes:
                update["last_outcome_notes"] = notes
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            outcome_str = "✅ success" if success else "❌ failure"
            return (
                f"Outcome recorded: {outcome_str} | "
                f"doc='{src.get('title', doc_id)}' | "
                f"runs={runs} ({success_count} success / {failure_count} failure)"
            )
        except Exception as e:
            self._log(f"RECORD-OUTCOME ERROR: {e}")
            return f"record_outcome failed: {e}"

    def mentor_correct(
        self,
        doc_id: str,
        correction: str,
        new_quality: float,
    ) -> str:
        """
        Apply a human-authored correction to an existing KB document.

        WHEN TO CALL:
          When the user identifies an error, outdated information, or an important
          improvement in a KB entry. Replaces the document content with the corrected
          version, re-embeds it, and raises the quality score.

        QUALITY RULE:
          This function never lowers the quality score. If new_quality is lower than
          the existing score, the call is rejected. Use index_to_kb to add a competing
          entry at a lower quality instead.

        Args:
            doc_id:       The doc_id of the KB entry to correct.
            correction:   The full corrected content to replace the existing entry.
            new_quality:  New quality score (0.0–1.0).
                          Use 0.95–1.0 for human-verified corrections.
        """
        from datetime import timezone  # noqa: PLC0415
        self._log(f"MENTOR-CORRECT: doc_id={doc_id} new_quality={new_quality}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resp = es.get(
                index="lse-kb", id=doc_id,
                _source=["quality_score", "refinement_count", "title"],
            )
            src = resp["_source"]
            old_quality = src.get("quality_score", 0.0)
            if new_quality < old_quality:
                return (
                    f"REJECTED: new_quality ({new_quality:.2f}) is lower than existing "
                    f"({old_quality:.2f}). mentor_correct must not lower quality. "
                    f"Use index_to_kb to add a competing entry instead."
                )
            embedding = self._embed(correction)
            es.update(index="lse-kb", id=doc_id, body={"doc": {
                "content":             correction,
                "embedding":           embedding,
                "quality_score":       new_quality,
                "refinement_count":    src.get("refinement_count", 0) + 1,
                "updated_at":          now,
                "mentor_corrected_at": now,
            }})
            return (
                f"Mentor correction applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f} | "
                f"refinements={src.get('refinement_count', 0) + 1}"
            )
        except Exception as e:
            self._log(f"MENTOR-CORRECT ERROR: {e}")
            return f"mentor_correct failed: {e}"
