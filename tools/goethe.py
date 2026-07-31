
"""
title: LSE Goethe v0.4.9
author: local-system-engineer
version: 0.4.9
requirements: elasticsearch==8.19.3, requests
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, ssh_run, ssh_script, read_file, write_file, sudo_delegation_block,
  search_web, get_github_release, get_context_status, compact_context, search_kb, index_to_kb,
  record_error, check_error_kb, record_outcome, mentor_correct, kb_verify, mentor_demote,
  time_check, run_tests, assert_state, pfsense_graphql, pfsense_query,
  pfsense_log_summary, start_node_agent, stop_node_agent, search_reddit, planner,
  plan_step_done, skill_search, skill_record,
  skill_outcome, task_checkpoint, and task_resume. Web tools share a code-enforced
  anti-spiral budget. All commands are logged to a persistent audit file. Privileged
  operations are blocked at the code level and routed through a delegation block.

  Full changelog: see CHANGELOG.md at repo root.
  Recent highlights:
    v0.4.9 — sudo grant fail-closed (exact sudo only, no chained shell)
    v0.4.8 — planner sync revert (async split reverted, one-call interface restored)
    v0.4.7 — planner docstring reordered above MCP 1024-char cut
    v0.4.5 — planner timeout fix (120→240s, Ollama fallback removed)
    v0.4.3 — docstring optimizer pass (SCRIBE-5)
    v0.4.2 — origin tags (web never mints ground_truth)
    v0.4.1 — TrustPolicy + KB surface extracted to goethe_kb.py
"""
from pydantic import BaseModel, Field
import subprocess
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

from typing import Optional

import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
from goethe_kb import KBMixin  # noqa: E402
from goethe_netsec import NetSecMixin  # noqa: E402
from goethe_node import NodeLifecycleMixin  # noqa: E402
# D6 topology sweep (2026-07-31), moved to goethe_constants.py in D7 Step 9
# (2026-07-31) so mixins can share it without importing goethe.py itself.
from goethe_constants import _LSE_BASE_PATH, _LOOPBACK  # noqa: E402
from goethe_planner import PlannerMixin  # noqa: E402



class Tools(KBMixin, NetSecMixin, NodeLifecycleMixin, PlannerMixin):

    class Valves(BaseModel):
        LOG_FILE: str = Field(
            default="/opt/local-se/agent_commands.log",
            description="Path to the persistent agent command audit log. "
            "Moved from ~/.lse/ (root:sy5 710, sy5 cannot write) "
            "to /opt/local-se/ (sy5-writable).",
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
            default=200,
            description="Subprocess timeout in seconds. Raised 30->200 (v0.2.0) so "
            "the download-monitor adaptive sleep (MAX_SLEEP_SECONDS=180) survives "
            "a single execute_command('sleep N') call, giving ~5 polls on a "
            "multi-minute download instead of ~20. TRADE-OFF: a genuinely hung "
            "command now blocks up to 200s before timing out (was 30s). Keep "
            "MAX_SLEEP_SECONDS in download-monitor.py strictly below this value.",
        )
        LLAMA_SERVER_URL: str = Field(
            default="http://localhost:8080",
            description="Base URL of the llama.cpp server (for get_context_status).",
        )
        SEARXNG_URL: str = Field(
            default="http://localhost:8088/search",
            description="SearxNG JSON search endpoint (for search_web).",
        )
        CAMOUFOX_URL: str = Field(
            default="http://192.168.5.41:9377",
            description="Camoufox browser server URL on node3090 (for Reddit scraping).",
        )

        FIRECRAWL_URL: str = Field(
            default="http://localhost:3002",
            description="Firecrawl browser-rendering endpoint when goethe runs ON node3090. " 
            "Distinct from Grafana which also uses port 3002 on LUCIFER.",
        )
        FIRECRAWL_REMOTE_URL: str = Field(
            default="http://node3090.home.arpa:3002",
            description="Firecrawl browser-rendering endpoint when goethe runs on LUCIFER or another node, " 
            "reaching node3090 over LAN. Distinct from Grafana on LUCIFER:3002.",
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
            description="Ollama base URL for KB embeddings (CPU-only, no GPU).",
        )
        EMBED_MODEL: str = Field(
            default="qwen3-embedding:0.6b",
            description="Ollama embedding model (1024-dim). Must match the live ES index mappings.",
        )
        REPO_DIR: str = Field(
            default="/home/sy5/projects/local-system-engineer",
            description="v0.3.6 (PROVE-1): repo root where run_tests finds the "
            "allowlisted test assets (rag/eval_retrieval.py, eval_goethe_rules.py, "
            "tests/, scripts/). Override per node via GOETHE_REPO_DIR; scopes "
            "whose assets are absent on a node report SKIP, never error.",
        )
        PLANNER_FORCE_URL: str = Field(
            default="",
            description="v0.3.2: when set, the planner calls THIS OpenAI-compatible "
            "endpoint first (e.g. http://node3090.home.arpa:8085 for the Gemma-31B "
            "swap experiment), falling back to the normal cascade on error. "
            "Cross-LLM-family planner experiments become pure configuration.",
        )
        PLANNER_FORCE_MODEL: str = Field(
            default="",
            description="Optional model name sent with PLANNER_FORCE_URL requests "
            "(needed for Ollama-style endpoints; llama-server ignores it).",
        )
        MODEL_PRETRAIN_CUTOFF: str = Field(
            default="",
            description="CHRONOS-2 (v0.3.1): the serving model's published pretraining "
            "cutoff as YYYY-MM (e.g. '2025-06' for Qwen3.6). Drives the [TIME] banner "
            "gap computation in time_check() and the first search_kb/search_web return "
            "of each session. Empty = banner warns that the cutoff is unset. Set "
            "per-model, per-node (env GOETHE_MODEL_PRETRAIN_CUTOFF in start scripts).",
        )
        DREAM_DIGEST_PATH: str = Field(
            default="/opt/local-se/dreams/latest-digest.md",
            description="TRAUM Thread 3 (v0.4.0-a), Prompt 3.5: path to "
            "tools/dream_digest.py's output, read once per session to build the "
            "[DREAM] banner appended alongside the [TIME] banner on the first "
            "search_kb return (_consume_time_banner()). Empty = banner disabled. "
            "Missing/unreadable/unparseable file = banner silently omitted, "
            "never an error (env GOETHE_DREAM_DIGEST_PATH in start scripts; "
            "matches DREAM_DIR in dream_runner.py/dream_apply.py/dream_digest.py "
            "by default, but is intentionally its own valve since goethe.py "
            "never itself writes into that directory).",
        )
        PFSENSE_URL: str = Field(
            default="https://pfsense.home.arpa",
            description="Base URL of the pfSense REST API (pfrest.org package, Plus 26.03). "
            "Not a secret — safe to store in valve.",
        )
        PFSENSE_API_KEY: str = Field(
            default="",
            description="pfSense REST API key (read-only). Acceptable blast radius: exposes "
            "network topology and firewall rules but cannot modify anything. "
            "Alternatively retrieve from Vaultwarden at runtime via vault_unlock() "
            "+ get_vault_secret() and pass as api_key parameter to pfsense_query(). "
            "WRITE ACCESS PROTOCOL: key is read-only by default. If pfSense write "
            "access is temporarily enabled (T3+ challenges), rotate this key "
            "immediately after and re-enable Read Only in pfSense UI.",
        )
        PFSENSE_CA_CERT: str = Field(
            default="/opt/local-se/cert/pfsense-webgui-ca.crt",
            description="Path to the exported pfSense WebGUI CA certificate for TLS verification. "
            "Export from pfSense: System → Cert Manager → CAs → Export CA. "
            "When set and the file exists, pfsense_query uses verify=<path>. "
            "When empty or file missing, falls back to verify=False (logged warning). "
            "Cert at default path: CN=pfsense-webgui-ca, valid until Apr 2036.",
        )
        HERMES_API_URL: str = Field(
            default="http://192.168.5.41:8642",
            description="[RETIRED v0.2.7] Hermes gateway — service no longer runs. "
            "node_plan() now calls node3090 llama-server directly. "
            "Valve retained to avoid breaking existing goethe_mcp valve configs.",
        )
        HERMES_API_KEY: str = Field(
            default="7aa537e027e2efeda7cc660a959516eed414373c6e7b3df3d9a567e48fc3319e",
            description="[RETIRED v0.2.7] Hermes API key — no longer used.",
        )
        NODE3090_LLM_URL: str = Field(
            default="http://node3090.home.arpa:8080",
            description="node3090 llama-server URL — PRIMARY planner for node_plan(). "
            "OpenAI-compatible /v1/chat/completions endpoint. "
            "Model: Qwen3.6-27B (GPU). Health check: GET /health (expects 200). "
            "node_plan() probes this first; falls back to NODE3090_OLLAMA_URL on failure.",
        )
        NODE3090_OLLAMA_URL: str = Field(
            default="http://node3090.home.arpa:11434",
            description="node3090 Ollama URL — CPU FALLBACK planner for node_plan(). "
            "Used when llama-server is unavailable, busy, or health probe times out. "
            "OpenAI-compatible /v1/chat/completions endpoint. "
            "Model: set by NODE3090_PLANNER_FALLBACK_MODEL valve.",
        )
        NODE3090_PLANNER_FALLBACK_MODEL: str = Field(
            default="qwen3:4b",
            description="Ollama model for CPU-fallback planning in node_plan(). "
            "Must be already pulled on node3090 (qwen3:4b is confirmed present). "
            "qwen3:4b supports extended thinking and is usable for structured planning. "
            "Alternative: gemma3 (also confirmed on node3090 Ollama).",
        )
        PLANNER_MODEL_DIR: str = Field(
            default="/opt/models/lmstudio-community",
            description="Base directory for Gemma GGUF + mmproj files for Path 3 planning "
            "(v0.2.8). Uses lmstudio-community subdir layout — paths in _GEMMA_MODELS "
            "are relative to this dir (e.g. gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf). "
            "Verified on node3090: /opt/models/lmstudio-community/{E4B,26B-A4B,31B}-GGUF/. "
            "Path 3 fires only when both llama-server and Ollama return errors.",
        )
        PLANNER_PORT: int = Field(
            default=8085,
            description="Port for the transiently spawned Gemma llama-server (Path 3, v0.2.8). "
            "Must not conflict with :8080 (main llama-server) or :8642 (retired Hermes). "
            "The process is started, used for one call, then killed.",
        )
        PLANNER_LLAMA_BIN: str = Field(
            default="/home/lse-admin/llama.cpp/build/bin/llama-server",
            description="Absolute path to the llama-server binary used to spawn Gemma "
            "instances (Path 3, v0.2.8). Must be executable by the goethe process user. "
            "Typical locations: ~/llama.cpp/build/bin/llama-server or "
            "/usr/local/bin/llama-server.",
        )

        # ── Planner backend selection (v1.13.0) ────────────────────────────
        # _call_node_planner (above) is untouched and is exactly what backend
        # 'local' calls. These four valves add three more backends behind a
        # single dispatcher (_call_planner_backend) — see that method for the
        # routing table. Every *_API_KEY valve name ends in API_KEY so it's
        # picked up for free by goethe_mcp's _SECRET_FIELD_RE log redaction,
        # same convention HERMES_API_KEY already relies on.
        PLANNER_BACKEND: str = Field(
            default="local",
            description="Default planner backend: 'local' (existing llama-server/"
            "Ollama/Gemma cascade — _call_node_planner, unchanged) | 'chatgpt' "
            "(OpenAI — Codex CLI OAuth session if `codex login` has run, else "
            "PLANNER_OPENAI_API_KEY) | 'claude' (Anthropic Messages API — Claude "
            "Code OAuth session if `claude login` has run, else "
            "PLANNER_ANTHROPIC_API_KEY) | 'rest' (any OpenAI-compatible "
            "/v1/chat/completions server via PLANNER_REST_URL — OpenRouter, "
            "Groq, Together, vLLM, LM Studio, etc.). planner(..., backend=...) "
            "overrides this for a single call without changing the default.",
        )
        PLANNER_REST_URL: str = Field(
            default="",
            description="Base URL for backend='rest' (e.g. "
            "https://openrouter.ai/api or http://192.168.1.20:1234 for a LAN "
            "LM Studio instance). POSTs to <url>/v1/chat/completions — the one "
            "genuinely universal option since almost every inference server "
            "and every gateway speaks this shape.",
        )
        PLANNER_REST_MODEL: str = Field(
            default="",
            description="Model name sent with backend='rest' requests. Required "
            "by most gateways (OpenRouter, Together); llama.cpp/LM Studio "
            "ignore it if the server is only loaded with one model.",
        )
        PLANNER_REST_API_KEY: str = Field(
            default="",
            description="Bearer token for backend='rest', sent as "
            "'Authorization: Bearer <key>'. Leave empty for LAN servers with "
            "no auth (llama-server, LM Studio, vLLM defaults).",
        )
        PLANNER_OPENAI_MODEL: str = Field(
            default="gpt-4o",
            description="Model for backend='chatgpt'. Verify this is still a "
            "valid model name for your account/key before relying on it — "
            "OpenAI's catalog moves faster than this default will be updated.",
        )
        PLANNER_OPENAI_API_KEY: str = Field(
            default="",
            description="Fallback credential for backend='chatgpt', used ONLY "
            "when no Codex CLI OAuth session is found at all (see "
            "PLANNER_CODEX_AUTH_PATHS). This is a normal pay-per-token OpenAI "
            "API key — a DIFFERENT credential from a ChatGPT subscription "
            "login, billed separately.",
        )
        PLANNER_ANTHROPIC_MODEL: str = Field(
            default="claude-sonnet-5",
            description="Model for backend='claude' (Anthropic Messages API).",
        )
        PLANNER_ANTHROPIC_API_KEY: str = Field(
            default="",
            description="Fallback credential for backend='claude', used ONLY "
            "when no Claude Code OAuth session is found at all (see "
            "PLANNER_CLAUDE_AUTH_PATHS). Sent as 'x-api-key' (standard "
            "Anthropic API auth) rather than the Bearer-token form the OAuth "
            "path uses.",
        )
        PLANNER_CODEX_AUTH_PATHS: str = Field(
            default="~/.codex/auth.json",
            description="Colon-separated candidate file paths for Codex CLI's "
            "(`codex login`) stored OAuth session, checked in order — first "
            "one that exists and parses wins. UNDOCUMENTED FILE FORMAT: this "
            "path and shape come from observed Codex CLI behavior, not an "
            "OpenAI spec, and may drift between Codex CLI versions. "
            "_read_codex_oauth_token() degrades to None (not an exception) if "
            "nothing usable is found, so backend='chatgpt' falls through to "
            "PLANNER_OPENAI_API_KEY rather than failing outright.",
        )
        PLANNER_CLAUDE_AUTH_PATHS: str = Field(
            default="~/.claude/.credentials.json:~/.config/claude/.credentials.json",
            description="Colon-separated candidate file paths for Claude Code's "
            "(`claude login`) stored OAuth session, checked in order. Same "
            "undocumented-format caveat as PLANNER_CODEX_AUTH_PATHS — on "
            "macOS this is normally in Keychain instead of a file, so this "
            "path list is a Linux/WSL-oriented best effort, not a guarantee.",
        )

        PLANNER_CLI_TIMEOUT_S: int = Field(
            default=900,
            description="Subprocess timeout (seconds) for backend='claude' CLI "
            "plan generation. Was hardcoded 180 (v0.4.5); Opus-class models on "
            "large atomization prompts measured ~10 min end-to-end (2026-07-30), "
            "so 180 guaranteed failure. The MCP transport still gives up near "
            "60s - the plan lands in the ledger anyway and is recovered via "
            "task_resume(); this valve only bounds server-side generation.",
        )

        SEARCH_BUDGET: int = Field(
            default=15,
            description="Max search_web/search_reddit/fetch_url calls per rolling "
            "window (anti-spiral gate, v1.7.1). Code-enforced.",
        )
        SEARCH_BUDGET_WINDOW_MIN: int = Field(
            default=2,
            description="Rolling window (minutes) for SEARCH_BUDGET. v1.7.2: 30→2 — "
            "30 min bricked legitimate research and leaked across session "
            "resumes (RUTX50 incident); 2 min still breaks tight spirals.",
        )
        TASKS_DB: str = Field(
            default="/opt/local-se/tasks.db",
            description="SQLite path for multi-session task blocks "
            "(task_checkpoint/task_resume).",
        )
        SOURCE_VERIFY_CACHE_TTL: int = Field(
            default=300,
            description="TTL in seconds for the fetch_url content cache used by "
            "verify_source_claims (v1.7.10). Re-fetches after expiry. "
            "Set to 0 to always re-fetch.",
        )

    # ── Hard-coded permission lists ───────────────────────────────────────────

    _ALLOWED_READ_PREFIXES = [
        "/home/",
        "/etc/",
        "/var/log/",
        "/tmp/",
        _LSE_BASE_PATH + "/",
    ]

    _ALLOWED_WRITE_PREFIXES = [
        "/home/",
        "/tmp/",
        _LSE_BASE_PATH + "/",
    ]

    _BLOCKED_COMMANDS = (
        # Filesystem destruction — disk/partition tools
        "mkfs",
        "fdisk",
        "parted",
        "sgdisk",
        "wipefs",
        "blkdiscard",
        "partprobe",
        "shred",
        # Block device writes — dd and shell redirection
        "dd if=",
        "of=/dev/",
        "> /dev/sd",
        "> /dev/nvme",
        # Recursive forced remove (all common flag orderings)
        "rm -rf",
        "rm -fr",
        "rm -r -f",
        "rm -f -r",
        # Fork bomb
        ":(){ :|",
        # Account deletion
        "userdel",
        "groupdel",
        # Privilege / credential management
        "passwd",
        "visudo",
        # Firewall flush
        "iptables -f",
        "iptables -F",
    )

    # v1.4.2: uses 'in' check (not startswith) to catch sudo in pipelines
    _PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")

    _PRIVILEGED_WRITE_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/", "/mnt/")

    _WRITE_OPS = (
        "cp ",
        "mv ",
        "rm ",
        "tee ",
        "> ",
        ">> ",
        "sed -i",
        "truncate",
        "dd ",
        "chmod -r ",
        "chown -r ",
    )

    # ── Initialiser ──────────────────────────────────────────────────────────

    def __init__(self):
        self.valves = self.Valves()
        self._fetch_cache: dict = {}  # url -> {"text": str, "ts": float} (v1.7.10)
        self._device_cache: dict = {}  # host -> {"platform": str, "raw": str} (v1.7.12)
        self._time_banner_emitted = False  # CHRONOS-2 (v0.3.1): [TIME] banner once/session
    # PlannerMixin: planner/ledger execution loop (29 methods, 5 class
    # attrs incl. _PLANNER_CONTRACT, _GEMMA_MODELS, _PLANNER_KB_*)
    # EXTRACTED to goethe_planner.py (D7, 2026-07-31). Membership computed
    # as the call-closure reachable from planner()/plan_step_done()/
    # task_checkpoint()/task_resume() - see that file's module docstring.
    # Behavior pinned by the full test suite + docs/D7-MIXIN-EXTRACTION-
    # PLAN.md Step 9 runtime proof (STACK-MAP grounding exercised live).


    # ── Internal helpers ─────────────────────────────────────────────────────

    def _norm(self, path: str) -> str:
        """Resolve symlinks and normalise path so prefix checks work correctly."""
        return os.path.realpath(os.path.expanduser(path)).rstrip("/") + "/"

    def _is_allowed_read(self, path: str) -> bool:
        normed = self._norm(path)
        # Literal (symlink-UNresolved) form as well: an allowed prefix such as
        # /opt/local-se/ contains symlinked subdirs (kb -> /mnt/c/...). Judging
        # only by realpath silently revoked read access to the KB the allowlist
        # was written to grant (2026-07-19 paradox: LSE could not read its own
        # KB). Read-side only -- the read allowlist is already broad
        # (/home, /etc, /var/log, /tmp), so honouring an operator-created
        # symlink under it grants nothing new in practice. _is_allowed_write
        # deliberately stays realpath-strict.
        literal = os.path.normpath(os.path.expanduser(path)).rstrip("/") + "/"
        for pref in self._ALLOWED_READ_PREFIXES:
            pref = pref.rstrip("/") + "/"
            if normed.startswith(pref) or literal.startswith(pref):
                return True
        gp = self._perms_mod()
        return bool(gp and gp.check_path("read", normed))

    def _perms_mod(self):
        """goethe_perms module if available (DB-backed user grants, v1.8.0)."""
        try:
            import goethe_perms  # noqa: PLC0415

            return goethe_perms
        except Exception:  # noqa: BLE001 (import degrade)
            return None

    def _perm_note(self, kind: str, target: str, reason: str = "") -> str:
        """File a pending grant request; returns text for the BLOCKED message."""
        gp = self._perms_mod()
        if not gp:
            return ""
        rid = gp.file_request(kind, target, reason)
        if rid is None:
            return ""
        return (
            f" Pending grant request #{rid} filed - the user can allow this "
            f"with: goethe-perm approve {rid} (review first: goethe-perm "
            "pending). Do NOT retry until the user confirms approval."
        )

    # Shell/session config files that must never be written by the agent
    _BLOCKED_WRITE_FILENAMES = {
        ".bashrc",
        ".bash_profile",
        ".bash_login",
        ".profile",
        ".zshrc",
        ".zprofile",
        ".zlogin",
        ".zshenv",
        ".cshrc",
        ".tcshrc",
        ".fishrc",
        ".ssh/authorized_keys",
        ".ssh/config",
        ".ssh/id_rsa",
        ".ssh/id_ed25519",
        ".gnupg/gpg.conf",
        ".config/fish/config.fish",
    }

    def _is_allowed_write(self, path: str) -> bool:
        normed = self._norm(path)
        # Block shell/session config files regardless of prefix
        import os as _os

        # _norm() returns a trailing-slash form ("/home/u/.bashrc/"), so
        # os.path.basename() on it yields "" and rel_home keeps a trailing
        # slash. Both comparisons below therefore never matched ANY entry in
        # _BLOCKED_WRITE_FILENAMES: shell rc files, SSH private keys and
        # authorized_keys were all writable. Strip the slash before comparing.
        # (D5 adversarial audit, 2026-07-31 — the guard had never fired.)
        _bare = normed.rstrip("/")
        basename = _os.path.basename(_bare)
        rel_home = _bare.replace(self.valves.DEFAULT_WORKING_DIR + "/", "", 1)
        if (
            basename in self._BLOCKED_WRITE_FILENAMES
            or rel_home in self._BLOCKED_WRITE_FILENAMES
        ):
            return False
        if any(
            normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_WRITE_PREFIXES
        ):
            return True
        if self.valves.EXTRA_WRITE_PATHS:
            for extra in self.valves.EXTRA_WRITE_PATHS.split(":"):
                extra = extra.strip()
                if extra and normed.startswith(extra.rstrip("/") + "/"):
                    return True
        gp = self._perms_mod()
        return bool(gp and gp.check_path("write", normed))

    def _log(self, entry: str) -> None:
        """Append a timestamped line to the audit log (best-effort)."""
        try:
            log_path = self.valves.LOG_FILE
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                try:
                    from redact import redact_sensitive_text  # tools/redact.py — P0 write-time redaction (2026-07-17)
                except ImportError:
                    import os as _os, sys as _sys
                    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                    from redact import redact_sensitive_text
                entry = redact_sensitive_text(entry)
            except Exception:  # noqa: BLE001 (redaction must not break audit log)
                pass  # redaction must never break the audit log; raw fallback = pre-P0 behavior
            with open(log_path, "a") as f:
                f.write(f"[{ts}] {entry}\n")
        except Exception:  # noqa: BLE001 (audit log must never crash)
            pass

    # ── Tool functions ────────────────────────────────────────────────────────

    # ── Anti-spiral budget gate (v1.7.1) ─────────────────────────────────────

    def _budget_gate(self) -> str:
        """Rolling-window budget shared by search_web/search_reddit/fetch_url.

        Returns '' (allowed), a low-budget banner (allowed, prepend/append it),
        or refusal text starting with 'BUDGET EXHAUSTED' (caller must return it
        without executing). Code-level enforcement: never relies on model attention.
        """
        import json as _json  # noqa: PLC0415
        import time  # noqa: PLC0415
        import os  # noqa: PLC0415

        path = os.path.join(
            os.path.dirname(self.valves.TASKS_DB) or ".", ".search_budget.json"
        )
        window_s = max(1, int(self.valves.SEARCH_BUDGET_WINDOW_MIN)) * 60
        budget = max(1, int(self.valves.SEARCH_BUDGET))
        now = time.time()
        try:
            with open(path, encoding="utf-8") as f:
                stamps = [t for t in _json.load(f) if now - t < window_s]
        except (OSError, json.JSONDecodeError):
            stamps = []
        if len(stamps) >= budget:
            retry_min = int((window_s - (now - stamps[0])) / 60) + 1
            self._log(f"BUDGET-GATE: refused (≥{budget} in {window_s//60}min)")
            return (
                f"BUDGET EXHAUSTED — web access paused: {budget} search/fetch calls "
                f"in {window_s // 60} min (anti-spiral gate). Do NOT retry or "
                "reformulate the query.\n"
                "REQUIRED NOW, in this order:\n"
                "  1. task_checkpoint(...) — record findings, UNVERIFIED items, and "
                "the next_prompt a future session should start from.\n"
                "  2. Surface your best partial answer to the user immediately, "
                "explicitly marking every unverified claim as unverified.\n"
                f"Budget resets in ~{retry_min} min. Continuing to search instead of "
                "surfacing is a protocol violation. UNVERIFIED-URL RULE: any URL or "
                "hostname you did not receive from a tool result is UNVERIFIED — "
                "presenting one to the user is a protocol violation."
            )
        stamps.append(now)
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(stamps, f)
        except OSError:
            pass
        remaining = budget - len(stamps)
        if remaining <= 2:
            return (
                f"\n\n⚠ SEARCH BUDGET: only {remaining} of {budget} web calls left "
                f"in this {window_s // 60}-min window. Surface findings NOW; if the "
                "task is incomplete, call task_checkpoint() before anything else."
            )
        return ""

    def _active_download_guard(self, command: str) -> str:
        """Block starting a NEW download while one is already running on the host,
        so the LSE cannot clobber an in-progress partial file (data corruption,
        SY5 report). Returns a refusal string when `command` initiates a download
        AND a real downloader process is already active; '' otherwise.

        Code-level enforcement: the LSE has repeatedly re-issued download commands
        (curl / hf download) instead of calling monitor_download() to check
        progress, restarting the transfer and producing partial/corrupt files —
        docstrings did not hold. Conservative to avoid false positives: pgrep only
        runs for download-initiating commands; curl must carry an output flag so a
        health-check curl never trips it; hf/wget/aria2c/git-lfs always qualify;
        fail-open if the host cannot be probed."""
        import re as _re  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        _INITIATORS = (
            "curl ", "wget ", "aria2c ", "hf download",
            "huggingface-cli download", "git lfs pull", "git lfs fetch",
        )
        if not any(t in command.lower() for t in _INITIATORS):
            return ""  # not a download command — skip the probe entirely
        try:
            ps = _sp.run(
                ["pgrep", "-af",
                 "curl|wget|aria2c|hf download|huggingface-cli|git-lfs"],
                capture_output=True, text=True, timeout=5,
            )
        except subprocess.SubprocessError:
            return ""  # cannot probe — fail open, do not block
        qualify = _re.compile(
            r"(?:wget |aria2c |hf download|huggingface-cli download|git-lfs|"
            r"curl\b.*(?:-O\b|-o |--output|--remote-name))"
        )
        active = [
            ln.strip()
            for ln in ps.stdout.splitlines()
            if ln.strip() and "pgrep" not in ln and qualify.search(ln)
            and "/dev/null" not in ln  # health-probe curls, not downloads
            and not _re.search(r"-o\s+-(?:\s|$)", ln)
        ]
        if not active:
            return ""
        self._log(f"DOWNLOAD-GUARD: blocked new download; active={active[0][:120]}")
        return (
            "BLOCKED: a download is already running on this host:\n"
            f"    {active[0][:200]}\n"
            "Starting another download now writes a second stream into the same "
            "partial file and CORRUPTS it — this is the reported failure.\n"
            "  • To CHECK progress, call the monitor_download tool with "
            "(file_path, expected_bytes). Do NOT re-run the download command.\n"
            "  • Start a new download ONLY after the current one COMPLETES, or "
            "after you intentionally kill it AND delete the partial file."
        )



    # Matches `<<[-]?'DELIM' ... DELIM` / `<<[-]?DELIM ... DELIM` heredoc blocks,
    # including the body between the opening marker and the closing delimiter
    # line. DOTALL so '.' spans newlines (body may be many lines); MULTILINE so
    # '^' anchors the closing delimiter to the start of its own line — without
    # that anchor, the delimiter word appearing mid-line elsewhere would also
    # close the match, or a permissive body could bleed into 'the rest of the
    # command'. Left as a plain string (not pre-compiled): this module imports
    # `re` locally per-method rather than at module scope, so a class-body
    # `re.compile(...)` would NameError at class-definition time. `re.sub`
    # with a string pattern is fine here — cpython's re module memoises
    # compiled patterns internally, and this runs once per command, not in
    # a hot loop.
    _HEREDOC_PATTERN = r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\2[ \t]*$"

    def _strip_heredoc_bodies(self, command: str) -> str:
        """Blank out heredoc payload bodies before running safety substring
        scans over a command.

        Why: a heredoc body is DATA being written to a file or piped
        somewhere — not a command being executed. The old scan ran
        _BLOCKED_COMMANDS/_PRIVILEGED_PREFIXES checks over the ENTIRE raw
        command string including heredoc content, so writing a KB note that
        merely *mentions* 'sudo install ...' as documentation text inside a
        `cat >> file << 'EOF' ... EOF` block got hard-blocked as if it were
        an actual privilege-escalation attempt. Keep the opening `<<DELIM`
        and closing `DELIM` marker lines intact (so a redirect target like
        `cat >> /etc/passwd << EOF` is still caught by the separate
        priv-write-path check, which looks at the header line) and blank
        only what's between them.
        """
        import re as _re  # noqa: PLC0415

        def _replace(m: "_re.Match") -> str:
            first_line = m.group(0).split("\n", 1)[0]
            return f"{first_line}\n[HEREDOC BODY OMITTED FROM SAFETY SCAN]\n{m.group(2)}"

        try:
            return _re.sub(
                self._HEREDOC_PATTERN, _replace, command,
                flags=_re.MULTILINE | _re.DOTALL,
            )
        except Exception:  # noqa: BLE001 (guard must never crash)
            # Scanning must never crash the guard — fail closed by scanning
            # the original text if the regex substitution itself errors.
            return command

    def _validate_command_safety(self, command: str, cwd: str) -> Optional[str]:
        """Validate command safety. Returns error string if blocked, None if safe."""
        # Heredoc bodies are data, not commands — strip them before any
        # substring scan below. `command` itself (used for actual execution
        # and for the leading-'sudo '-prefix check) stays untouched.
        scan_command = self._strip_heredoc_bodies(command)

        # ── Block permanently forbidden commands ──────────────────────────────
        cmd_lower = scan_command.lower().strip()
        for blocked in self._BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                self._log(f"HARD-BLOCKED: {command}")
                return (
                    f"BLOCKED: '{blocked}' is permanently forbidden. "
                    "This operation cannot be performed by the agent under any circumstances."
                )

        # ── DB-granted privileged commands (goethe_perms, user-approved) ─────
        _stripped = command.strip()
        _priv_rest = None
        if _stripped.startswith("sudo "):
            _priv_rest = _stripped[5:].lstrip()
            if _priv_rest.startswith("-n "):
                _priv_rest = _priv_rest[3:].lstrip()
        if _priv_rest and not any(
            t in _priv_rest for t in (";", "|", "&", "`", "$(", "\n", ">", "<")
        ):
            _gp = self._perms_mod()
            _gid = _gp.check_sudo(_priv_rest) if _gp else None
            if _gid:
                if not self._is_allowed_read(cwd):
                    return (
                        f"BLOCKED: working_dir '{cwd}' is outside allowed read paths."
                    )
                self._log(f"PRIV-GRANTED grant#{_gid}: {command}")
                return None

        # ── Block privilege escalation anywhere in the command (v1.4.2 fix) ──
        for priv in self._PRIVILEGED_PREFIXES:
            if priv in cmd_lower:
                self._log(f"PRIV-BLOCKED: {command}")
                if _priv_rest and not any(
                    t in _priv_rest for t in (";", "|", "&", "`", "$(", "\n", ">", "<")
                ):
                    _note = self._perm_note(
                        "sudo", _priv_rest, "agent requested privileged command"
                    )
                    return (
                        f"BLOCKED: '{priv.strip()}' detected in command. "
                        "Use sudo_delegation_block instead." + _note
                    )
                return (
                    f"BLOCKED: '{priv.strip()}' detected in a chained or complex "
                    "command. Complex shell text cannot become a sudo grant. "
                    "Use sudo_delegation_block and split the privileged operation "
                    "into one exact command without pipes, redirects, chaining, "
                    "or shell expansion."
                )

        # ── Block writes to privileged system paths ───────────────────────────
        # Only block when a write op TARGETS a privileged path; reads (cat/tr/grep
        # < /proc, ps, etc.) are allowed. /mnt/ dropped (legit user data lives there).
        import re as _re_pw  # noqa: PLC0415
        _priv_re = r"(?:/etc/|/usr/|/boot/|/sys/|/proc/)"
        _write_to_priv = _re_pw.search(
            r">>?\s*" + _priv_re
            + r"|\btee\s+(?:-a\s+)?" + _priv_re
            + r"|\b(?:cp|mv|dd|truncate)\b[^|;&\n]*\s" + _priv_re
            + r"|\bsed\s+-i\b[^|;&\n]*" + _priv_re
            + r"|\brm\s+[^|;&\n]*" + _priv_re,
            scan_command,
        )
        if _write_to_priv:
            self._log(f"WRITE-BLOCKED: {command}")
            return (
                f"BLOCKED: write targeting a privileged path — matched {_write_to_priv.group(0)!r}. "
                "Use sudo_delegation_block to delegate this to the user, or report a false positive."
            )

        # ── Block clobbering an in-progress download (v0.2.0) ─────────────────
        # If a download is already running, refuse a new one and route the model
        # to monitor_download instead. Prevents the partial-file corruption from
        # the LSE re-issuing curl/hf download to "check progress".
        _dl_block = self._active_download_guard(command)
        if _dl_block:
            return _dl_block

        # ── Validate working directory ────────────────────────────────────────
        if not self._is_allowed_read(cwd):
            _rp = os.path.realpath(os.path.expanduser(cwd))
            return (
                f"BLOCKED: working_dir '{cwd}' is outside allowed read paths."
                + self._perm_note("read", _rp, "working_dir blocked")
            )
        return None

    def execute_command(self, command: str, working_dir: str = "") -> str:
        """
        SPEC: Execute a read-only or write-safe shell command in the WSL Ubuntu environment.
        Use for: ls, cat, grep, find, ps, df, uname, systemctl status, apt list,
                 journalctl, tail, head, wc, etc.
        Do NOT use for commands requiring sudo — use sudo_delegation_block instead.
        Output is capped at MAX_OUTPUT_CHARS. Always pipe through grep/head/awk.

        COMBINE RULE — batch independent commands into a single call:
          Use && when the second depends on the first; ; when independent.
          Never make two calls when one combined call will do.

        DOWNLOAD PROGRESS RULE — mandatory: call monitor_download to check progress.
        NEVER re-run a download command (curl/wget/hf) to "test" or "check" it —
        a second fetch corrupts the partial file. Code-enforced refusal applies.

        CONFIG GROUND-TRUTH RULE — mandatory: tokens/paths/ports/config values
        must come from a tool result THIS session (read_file, cat/grep, docker inspect).
        Never from recall or from a KB doc older than the system it describes.
        Citing a config value without a same-session read is a protocol violation.

        RESOURCE-AVAILABILITY RULE — mandatory before any external connection:
        Before SSH/API/docker/curl to a remote resource, verify it is reachable first.
        For managed nodes: ping → if unreachable, check node registry → wake_node if listed.
        Attempting a connection without verifying availability is a protocol violation.

        VENDOR-BEHAVIOR GROUND-TRUTH RULE — mandatory before modifying external software:
        Verify assumptions via the waterfall (search_kb → vendor docs → GitHub → search_web)
        before any sed/patch/write_file on external project files. Patching on recall is
        a protocol violation regardless of confidence.

        RELEASE ASSET RULE — mandatory before referencing any external artifact:
        Call get_github_release("<owner>/<repo>") to confirm exact tag and asset filenames.
        Never construct download URLs or version strings from memory or pattern extension.

        DESTRUCTIVE OPERATION PROTOCOL — mandatory before rm/truncate/overwrite:
        Name the exact target, warn the user, ask "Shall I proceed? (yes/no)", wait for yes.
        Proceeding without confirmation is a protocol violation.

        POST-DELETE VERIFY RULE — mandatory after any deletion:
        Immediately make a follow-up call to confirm the target is gone (stat/ls).

        SSH KB-FIRST RULE — mandatory before any ssh command:
        Call search_kb(query='{hostname} SSH access') with NO topic_filter.
        Use the exact key path from the KB result. Never bare ssh to a key-only device.

        DEVICE-IDENTITY RULE — SSH only: device type comes from auto-fingerprint,
        never from IP/hostname guessing. Choose CLI syntax from the fingerprint.

        SLOW REMOTE COMMAND RULE — mandatory for SSH disk inspection:
        NEVER chain multiple du -sh on remote mounts. Use df -h or ls -lh instead.

        NOTES:
        Output filter examples:
          GOOD: execute_command("journalctl -u nginx -n 20 --no-pager")
          BAD:  execute_command("journalctl -u nginx")   ← no output limit
          BAD:  execute_command("sudo systemctl restart nginx")  ← use sudo_delegation_block
        """
        cwd = working_dir.strip() or self.valves.DEFAULT_WORKING_DIR

        if (err := self._validate_command_safety(command, cwd)):
            return err

        # ── SSH device auto-fingerprint (v1.7.12) ──────────────────────────────
        _fp_note = ""
        _cmd_stripped = command.lstrip()
        if _cmd_stripped.startswith("ssh ") and not any(
            m in command for m in ("os-release", "uname -srm", "__FP__")
        ):
            # Extract ssh options + user@host prefix from original command
            import re as _re_fp  # noqa: PLC0415

            _tokens = command.split()
            _OPTS_WITH_VAL = {
                "-p",
                "-i",
                "-o",
                "-l",
                "-F",
                "-J",
                "-c",
                "-D",
                "-E",
                "-I",
                "-L",
                "-m",
                "-R",
                "-S",
                "-w",
                "-W",
                "-b",
                "-Q",
            }
            _hi, _i = None, 1
            while _i < len(_tokens):
                if _tokens[_i].startswith("-"):
                    _hi = None
                    _i += 2 if _tokens[_i] in _OPTS_WITH_VAL else 1
                else:
                    _hi = _i
                    break
            if _hi is not None:
                _user_at_host = _tokens[_hi]
                _fp_host = _user_at_host.split("@")[-1]
                if _fp_host not in self._device_cache:
                    _ssh_prefix = " ".join(_tokens[1 : _hi + 1])
                    _fp_cmd = (
                        f"ssh -o BatchMode=yes -o ConnectTimeout=8 "
                        f"-o StrictHostKeyChecking=no {_ssh_prefix} "
                        f"'echo __FP__; cat /etc/os-release 2>/dev/null; "
                        f"echo __UNAME__; uname -srm 2>/dev/null'"
                    )
                    try:
                        _fp_proc = subprocess.run(
                            _fp_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=15,
                            cwd=cwd,
                        )
                        _fp_out = (_fp_proc.stdout or "").strip()
                        _platform = "unknown"
                        _mp = _re_fp.search(r'PRETTY_NAME="?([^"\n]+)"?', _fp_out)
                        if _mp:
                            _platform = _mp.group(1).strip('"')
                        else:
                            _mu = _re_fp.search(r"__UNAME__\s*([^\n]+)", _fp_out)
                            if _mu:
                                _platform = _mu.group(1).strip()
                        # Only cache on success — unknown/error results must not
                        # block a retry on the next SSH call with the correct key.
                        if (
                            _fp_proc.returncode == 0
                            and _platform != "unknown"
                            and not _platform.startswith("(fingerprint")
                        ):
                            self._device_cache[_fp_host] = {
                                "platform": _platform, "raw": _fp_out[:500]
                            }
                            self._log(f"DEVICE-FP: {_fp_host} -> {_platform}")
                        else:
                            self._log(
                                f"DEVICE-FP FAILED (not cached): {_fp_host} "
                                f"rc={_fp_proc.returncode} platform={_platform}"
                            )
                            _platform = "unknown"  # ensure consistent state
                    except subprocess.SubprocessError as _fp_e:
                        # Do not cache — allow retry on next SSH call
                        self._log(f"DEVICE-FP ERROR (not cached): {_fp_host}: {_fp_e}")
                        _platform = "unknown"
                if _fp_host in self._device_cache:
                    _cached = self._device_cache[_fp_host]
                    _fp_note = (
                        f"\n[DEVICE FINGERPRINT: host={_fp_host} | "
                        f"platform={_cached['platform']} | "
                        f"source=os-release/uname — ground truth. "
                        f"Use this platform for ALL CLI decisions. "
                        f"Never infer device type from IP or hostname.]"
                    )
                elif _platform == "unknown":
                    _fp_note = (
                        f"\n[DEVICE FINGERPRINT PENDING: host={_fp_host} | "
                        f"platform=unknown — SSH auth failed or no output. "
                        f"Fingerprint NOT cached; will retry on next SSH call. "
                        f"Do NOT infer device type from IP or hostname.]"
                    )

        # ── SSH complexity guard (v0.2.6) ────────────────────────────────────
        # Block patterns that cause exit 255 when routed through bash -c + SSH.
        # Redirect model to ssh_script() which transfers the script as a file.
        if _cmd_stripped.startswith("ssh "):
            _SSH_COMPLEX_MARKERS = [
                "nohup", "& disown", "&disown", "export ", "eval ", "$(", "`",
            ]
            if any(m in command for m in _SSH_COMPLEX_MARKERS):
                import re as _re_guard
                _hm = _re_guard.search(
                    r'ssh\s+(?:\S+\s+)*?(\S+@\S+|\d{1,3}(?:\.\d{1,3}){3}|\S+\.(?:home\.arpa|\w+))',
                    command
                )
                _detected = [m for m in _SSH_COMPLEX_MARKERS if m in command]
                _host_hint = _hm.group(1).split("@")[-1] if _hm else "<host>"
                return (
                    "[SSH_COMPLEXITY_GUARD] Command blocked — contains patterns that cause "
                    f"exit 255 when passed through bash -c + SSH:\n"
                    f"  Detected: {_detected}\n\n"
                    "Root cause: Python → bash -c → SSH → remote sh applies three layers of "
                    "shell parsing. Special characters ($, \", &, ;) are reinterpreted at each "
                    "layer. The command arrives on the remote host corrupted or not at all.\n\n"
                    "→ Use ssh_script() — transfers the script as a raw file, zero escaping:\n\n"
                    f"  ssh_script(\n"
                    f"      host={_host_hint!r},\n"
                    f"      script='''\n"
                    f"  <paste your commands here, one per line, no escaping needed>\n"
                    f"  '''\n"
                    f"  )"
                )

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
            result_str = output if rc == 0 else f"[exit {rc}]\n{output}"
            return result_str + _fp_note
        except subprocess.TimeoutExpired:
            self._log(f"TIMEOUT: {command}")
            return (
                f"ERROR: Command timed out after {self.valves.COMMAND_TIMEOUT} seconds."
            )
        except OSError as e:
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
            _rp = os.path.realpath(os.path.expanduser(path))
            return (
                f"BLOCKED: '{path}' is outside allowed read paths (resolves to "
                f"'{_rp}')." + self._perm_note("read", _rp, "read_file blocked")
            )

        resolved = os.path.realpath(os.path.expanduser(path))
        if not os.path.isfile(resolved):
            return f"ERROR: File not found: {path}"

        self._log(f"READ: {path} lines={offset_lines}..{offset_lines + max_lines}")
        try:
            with open(resolved, "r", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            sliced = lines[offset_lines : offset_lines + max_lines]
            content = "".join(sliced)
            footer = (
                f"\n--- Lines {offset_lines + 1}–{offset_lines + len(sliced)} "
                f"of {total} total ---"
            )
            return content + footer
        except (OSError, UnicodeDecodeError) as e:
            return f"ERROR: {str(e)}"

    def _snapshot_before_write(self, resolved: str):
        """Recovery snapshot of an existing file before an in-place overwrite or
        append (v0.2.0 code gate). Returns (ok: bool, note: str).

        git-native first: `git hash-object -w` stores the CURRENT content as a
        recoverable blob WITHOUT touching the index, working tree, or HEAD, then
        update-ref pins it under refs/lse-snapshots/ so gc cannot reap it. Falls
        back to a timestamped copy under <dir>/.lse-backups/. If BOTH fail the
        function returns ok=False and the caller MUST refuse the write — an
        in-place edit with no recovery point is exactly the failure this gate
        prevents. Enforcement in code, not docstring (sudo-blocker lineage)."""
        import subprocess as _sp  # noqa: PLC0415
        import shutil as _sh  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        import time as _t  # noqa: PLC0415

        if not _os.path.isfile(resolved):
            return True, "new file — no snapshot needed"
        # 1) git-native snapshot — non-intrusive (no index/worktree/HEAD change)
        try:
            top = _sp.run(
                ["git", "-C", _os.path.dirname(resolved),
                 "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if top.returncode == 0 and top.stdout.strip():
                root = top.stdout.strip()
                h = _sp.run(
                    ["git", "-C", root, "hash-object", "-w", resolved],
                    capture_output=True, text=True, timeout=10,
                )
                if h.returncode == 0 and h.stdout.strip():
                    sha = h.stdout.strip()
                    ts = _t.strftime("%Y%m%d-%H%M%S")
                    rel = _os.path.relpath(resolved, root)
                    _sp.run(
                        ["git", "-C", root, "update-ref",
                         f"refs/lse-snapshots/{ts}-{sha[:8]}", sha],
                        capture_output=True, text=True, timeout=5,
                    )
                    self._log(f"SNAPSHOT(git): {rel} -> {sha[:12]}")
                    return True, (
                        f"git blob {sha[:12]} "
                        f"(restore: git -C {root} cat-file -p {sha[:12]} > {rel})"
                    )
        except Exception as e:  # noqa: BLE001
            self._log(f"SNAPSHOT git path error: {e}")
        # 2) filesystem fallback — timestamped copy beside the file
        try:
            bdir = _os.path.join(_os.path.dirname(resolved), ".lse-backups")
            _os.makedirs(bdir, exist_ok=True)
            ts = _t.strftime("%Y%m%d-%H%M%S")
            dest = _os.path.join(bdir, f"{_os.path.basename(resolved)}.{ts}.bak")
            _sh.copy2(resolved, dest)
            self._log(f"SNAPSHOT(copy): {dest}")
            return True, f"backup copy {dest}"
        except Exception as e:  # noqa: BLE001
            self._log(f"SNAPSHOT FAILED: {resolved}: {e}")
            return False, f"snapshot failed: {e}"

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

        RECOVERY SNAPSHOT — automatic, code-enforced (v0.2.0):
          Before any in-place write to an EXISTING file, this function snapshots
          the current content (git blob via `git hash-object -w`, pinned under
          refs/lse-snapshots/; or a timestamped copy under .lse-backups/ outside
          git). If no snapshot can be made, the write is REFUSED — the docstring
          confirmation rule above is not self-enforcing, so this gate guarantees
          every overwrite/append is reversible. The recovery command is included
          in the return value. New-file creation is exempt (nothing to recover).

        For files under /etc/ or other privileged paths, use sudo_delegation_block.
        """
        if not self._is_allowed_write(path):
            _rp = os.path.realpath(os.path.expanduser(path))
            return (
                f"BLOCKED: '{path}' is outside allowed write paths (resolves to "
                f"'{_rp}'). Use sudo_delegation_block for privileged paths."
                + self._perm_note("write", _rp, "write_file blocked")
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
            except OSError:
                pass  # If comparison fails, proceed — don't block on a check error

        # ── In-place edit safety net (v0.2.0): snapshot-or-refuse ─────────────
        # Before mutating an existing file, capture a recovery point. If none can
        # be made, REFUSE — never edit in place without a way back. New-file
        # creation skips this (nothing to recover).
        snap_note = ""
        if os.path.isfile(resolved):
            ok_snap, snap = self._snapshot_before_write(resolved)
            if not ok_snap:
                self._log(f"WRITE-REFUSED (no snapshot): {path}")
                return (
                    f"BLOCKED: could not create a recovery snapshot of '{path}' "
                    f"before this in-place {mode} ({snap}). Refusing so no original "
                    "is lost. Fix the snapshot location (a writable git repo or "
                    "directory) or back the file up manually, then retry."
                )
            snap_note = f" | recovery snapshot: {snap}"

        self._log(f"WRITE: {path} mode={mode} len={len(content)}")
        try:
            os.makedirs(parent, exist_ok=True)
            file_mode = "a" if mode == "append" else "w"
            with open(resolved, file_mode) as f:
                f.write(content)
            return (
                f"OK: {len(content)} characters written to {path} "
                f"(mode={mode}).{snap_note}"
            )
        except OSError as e:
            return f"ERROR: {str(e)}"

    async def sudo_delegation_block(
        self,
        command: str,
        reason: str,
        expected_output_hint: str = "",
        step_number: int = 0,
        total_steps: int = 0,
        verify_command: str = "",
        __event_emitter__=None,
    ) -> str:
        """
        SPEC: Use whenever an operation requires sudo or touches a privileged path
        (/etc/, systemctl enable/start/stop/restart, apt install/remove, etc.).
        Produces a formatted block for the user to run manually in their terminal.
        NEVER attempt to run sudo yourself. Always call this function instead.

        THINKING PHASE RULE — never call inside a reasoning block:
        Call only in the response phase, after thinking has closed.
        Calling sudo_delegation_block during thinking is a protocol violation.

        READ-FIRST RULE — mandatory for any privileged file modification:
        Before delegating a write/append to a config file, first read it
        using read_file or execute_command('cat <path>'). Confirms the setting
        does not already exist, lets you compose the correct command.
        Skipping the read when the file IS readable is a protocol violation.

        STOP PROTOCOL — mandatory, no exceptions:
        After calling this function, your visible reply MUST be exactly the markdown
        the directive returns — the ```bash fenced command and verify block if any,
        and the "Paste the full terminal output here to continue." line.
        Output nothing before or after it. Your next turn begins only after user input.

        ARGS:
          command — The exact command the user must run.
          reason — One sentence explaining why this delegation is needed.
          expected_output_hint — (secondary) hint about success. Prefer verify_command.
          step_number — Position in a multi-step sequence (1-based). Pass 0 for standalone.
          total_steps — Total delegation blocks in sequence. Required when step_number > 0.
          verify_command — Explicit follow-up command to confirm success.

        RETURN VALUE SEMANTICS:
        This function returns a DIRECTIVE (v1.7.21), not text to summarize. The
        directive contains the exact markdown — including a ```bash fenced code block —
        that your visible reply must reproduce verbatim, and nothing else.
        The command has NOT run yet; it is now in the user's hands.
        Do NOT call this function again for the same command.
        Do NOT make any further tool calls in this turn after calling this function.

        NOTES:
        (v1.7.20 code backstop: if called mid-reasoning, the block is force-surfaced
        via event emitter, but the rule still stands for clean turn structure.)
        """
        self._log(f"SUDO-DELEGATE: {command}  reason={reason}")

        # Step indicator
        if step_number > 0 and total_steps > 0:
            step_line = f" — step {step_number} of {total_steps}"
        else:
            step_line = ""

        # Verify block (markdown ```bash fence)
        if verify_command:
            verify_line = f"\nVerify with:\n\n```bash\n{verify_command}\n```\n"
        elif expected_output_hint:
            verify_line = f"\n_Expected output: {expected_output_hint}_\n"
        else:
            verify_line = ""

        block = (
            f"⚠️ **SUDO REQUIRED — action delegated to you**{step_line}\n\n"
            f"**Reason:** {reason}\n\n"
            f"Run this in your terminal:\n\n"
            f"```bash\n{command}\n```\n"
            f"{verify_line}\n"
            f"Paste the full terminal output here to continue."
        )
        # v1.7.21: the emitter is best-effort — if the model called this mid-<think>,
        # emitted content can stay collapsed. The authoritative surface is the model's
        # visible post-<think> reply, forced by the directive returned below.
        if __event_emitter__ is not None:
            try:
                await __event_emitter__(
                    {"type": "message", "data": {"content": "\n" + block + "\n"}}
                )
            except Exception as _e:  # noqa: BLE001
                self._log(f"SUDO-DELEGATE emit failed: {_e}")
        directive = (
            "SUDO DELEGATION SURFACED (v1.7.21). The command has NOT run yet — it is now "
            "in the user's hands.\n\n"
            "Your visible reply for THIS turn must be EXACTLY the markdown below and "
            "NOTHING else: no preamble, no summary, no commentary, no further tool calls. "
            "Reproduce it verbatim (keep the ```bash fence) so the user gets a copyable "
            "command:\n\n"
            "----- BEGIN REQUIRED REPLY -----\n"
            f"{block}\n"
            "----- END REQUIRED REPLY -----\n\n"
            "Then STOP and wait for the user to paste the terminal output."
        )
        return directive

    # pfsense_graphql, pfsense_query, _pfsense_verify, _pfsense_cap_response --
    # EXTRACTED to lse/skills/pfsense/tools.py (Phase 2 skill extraction,
    # 2026-07-06). Loaded at runtime via goethe_mcp's `--also
    # tools/pfsense_tools_v1.0.0.py` flag (see start-goethe*.sh /
    # goethe-mcp.service), same pattern as vaultwarden_tools_v1.3.0.py.
    # See lse/skills/pfsense/DESIGN.md for the extraction design + incident
    # writeup.

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

        TIME DISCIPLINE (v0.3.1 — ENFORCED IN CODE, not prose; CHRONOS-4 retired
        the old YEAR-INJECTION and 30d/7d staleness rules from this docstring):
          - Standalone years (e.g. "2025") are STRIPPED from the query server-side —
            they filter out current results. Compound ids like CVE-2025-1234 survive.
          - The first search_kb/search_web return of each session carries a [TIME]
            banner (system-clock based; call time_check() for NTP-verified time).
          - KB freshness is enforced by volatility TTLs in search_kb ([EXPIRED] tags
            + rerank demotion) — no manual date arithmetic needed.
          For version lookups of GitHub projects, prefer get_github_release.
        """
        import requests  # noqa: PLC0415

        query = self._strip_years(query)
        _tb = self._consume_time_banner()

        self._log(f"SEARCH: {query} max={max_results}")
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            return _tb + _gate
        try:
            resp = requests.get(
                self.valves.SEARXNG_URL,
                params={"q": query, "format": "json", "categories": "general"},
                headers={"X-Forwarded-For": _LOOPBACK, "X-Real-IP": _LOOPBACK},
                timeout=(5, 10),
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:max_results]
            if not results:
                return _tb + "No results found." + _gate
            lines = []
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("content", "")[:300]
                lines.append(f"**{title}**\n{url}\n{snippet}")
            return _tb + "\n---\n".join(lines) + _gate
        except (requests.RequestException, json.JSONDecodeError) as e:
            return f"ERROR searching SearxNG: {str(e)}"

    # ── CAMOUFOX REDDIT SCRAPING (v0.3.10) ──────────────────────────────────

    def _camoufox_scrape(self, url: str, wait_s: int = 8) -> str:
        """Use Camoufox on node3090 to scrape a URL. Returns accessibility tree text."""
        import requests  # noqa: PLC0415
        import time  # noqa: PLC0415

        base = self.valves.CAMOUFOX_URL.rstrip("/")
        try:
            # Step 1: Open tab
            resp = requests.post(
                f"{base}/tabs",
                json={"userId": "lse", "sessionKey": "lse", "url": url},
                timeout=15,
            )
            resp.raise_for_status()
            tab_id = resp.json().get("tabId")
            if not tab_id:
                return ""

            # Step 2: Wait for page load
            time.sleep(wait_s)

            # Step 3: Get snapshot
            snap_resp = requests.get(
                f"{base}/tabs/{tab_id}/snapshot",
                params={"userId": "lse", "sessionKey": "lse"},
                timeout=10,
            )
            snap_resp.raise_for_status()
            snapshot = snap_resp.json().get("snapshot", "")

            # Close tab
            try:
                requests.delete(
                    f"{base}/tabs/{tab_id}",
                    params={"userId": "lse", "sessionKey": "lse"},
                    timeout=5,
                )
            except Exception:  # noqa: BLE001 (tab cleanup)
                pass  # Non-critical cleanup

            return snapshot
        except requests.RequestException as e:
            self._log(f"CAMOUFOX-ERROR: {e}")
            return ""

    def _parse_reddit_posts(self, snapshot: str) -> list:
        """Extract Reddit posts from Camoufox accessibility tree.
        Returns list of dicts: {title, url, votes, comments, author, time}
        
        Actual format from Reddit search:
          heading "Title" [level=2]:
            link "Title" [eN]:
              /url: /r/subreddit/comments/...
          text: ·
          time: Xh ago
          link "Title" [eN]:
            /url: /r/subreddit/comments/...
          text: N votes·N comments
        """
        import re  # noqa: PLC0415

        posts = []
        lines = snapshot.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for heading level=2 (Reddit post titles)
            if 'heading "' in line and '[level=2]' in line:
                m = re.search(r'heading "([^"]+)"', line)
                if m:
                    title = m.group(1)
                    post = {"title": title, "url": "", "votes": "", "comments": "", "author": "", "time": ""}

                    # Look for URL in next 10 lines
                    for j in range(i+1, min(len(lines), i+15)):
                        url_m = re.search(r'/url: (https?://www\.reddit\.com/r/[^\s]+)', lines[j])
                        if url_m:
                            post["url"] = url_m.group(1)
                            break

                    # Look for time in next 15 lines
                    for j in range(i+1, min(len(lines), i+20)):
                        time_m = re.search(r'time: (.+)', lines[j])
                        if time_m:
                            post["time"] = time_m.group(1).strip()
                            break

                    # Look for votes·comments in next 20 lines
                    for j in range(i+1, min(len(lines), i+25)):
                        vc_m = re.search(r'(\d+) votes·(\d+) comments', lines[j])
                        if vc_m:
                            post["votes"] = vc_m.group(1)
                            post["comments"] = vc_m.group(2)
                            break

                    posts.append(post)
            i += 1

        return posts

    def search_reddit(
        self,
        query: str,
        subreddit: str = "",
        max_results: int = 5,
    ) -> str:
        """
        Search Reddit for posts and discussions.

        PRIMARY: Camoufox browser on node3090 — renders JS, bypasses Reddit anti-bot,
        returns structured post data (title, URL, votes, comments, author, time).
        FALLBACK: SearxNG site:reddit.com search if Camoufox is unavailable.

        KB-FIRST RULE — mandatory:
          Call search_kb() before this function. Only call search_reddit() on a KB miss.
          After finding useful results, call index_to_kb() to store for next time.

        REQUIRED SEQUENCE — follow exactly:
          Step 1: Write to user: "Searching Reddit for [topic]."
          Step 2: Call search_reddit() once for this topic.
          Step 3: If snippets are too short, call fetch_url() on the most relevant post URL.
          Step 4: Synthesise in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Args:
            query:       Search terms (e.g. "RTX 3090 thermal paste replacement")
            subreddit:   Optional subreddit without r/ prefix (e.g. "homelab", "hardware")
                         If empty, searches all of reddit.com
            max_results: Number of results to return (default 5)

        Returns:
            Formatted search results string.
        """
        self._log(f"SEARCH-REDDIT: subreddit={subreddit!r} query={query!r}")

        # ── PRIMARY: Camoufox on node3090 ──────────────────────────────────
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search/?q={query}&sort=hot" if subreddit else f"https://www.reddit.com/search/?q={query}&sort=hot"
            snapshot = self._camoufox_scrape(url, wait_s=8)
            if snapshot:
                posts = self._parse_reddit_posts(snapshot)[:max_results]
                if posts:
                    lines = []
                    for p in posts:
                        title = p.get("title", "Untitled")
                        url = p.get("url", "")
                        votes = p.get("votes", "")
                        comments = p.get("comments", "")
                        author = p.get("author", "")
                        time_ = p.get("time", "")
                        snippet = f"{votes} • {comments}" if votes and comments else ""
                        if author:
                            snippet += f" • u/{author}"
                        if time_:
                            snippet += f" • {time_}"
                        snippet = snippet.lstrip(" • ")
                        lines.append(f"**{title}**\n{url}\n{snippet}")
                    return "\n---\n".join(lines) if lines else "No posts found."
        except Exception as e:  # noqa: BLE001 (camoufox complex chain)
            self._log(f"CAMOUFOX-FAIL: {e}")

        # ── FALLBACK: SearxNG ─────────────────────────────────────────────
        self._log("SEARCH-REDDIT: falling back to SearxNG")
        site = f"site:reddit.com/r/{subreddit}" if subreddit else "site:reddit.com"
        full_query = f"{site} {query}"
        return self.search_web(full_query, max_results=max_results)

    # ── CHRONOS — enforced sense of time (v0.3.1, Workstream B) ─────────────

    def _strip_years(self, query: str) -> str:
        """CHRONOS-4 (v0.3.1): year injection defined out of existence — strip
        standalone 19xx/20xx tokens from search queries (they filter out current
        results). Compound tokens survive: CVE-2025-1234, ubuntu-24.04, b2025x."""
        import re as _re  # noqa: PLC0415

        stripped = _re.sub(r"(?<![\w.\-])(?:19|20)\d{2}(?![\w.\-])", " ", query)
        stripped = _re.sub(r"\s{2,}", " ", stripped).strip()
        if stripped and stripped != query.strip():
            self._log(f"SEARCH year-strip: {query!r} -> {stripped!r}")
            return stripped
        return query

    def _sntp_offset(self, server: str, timeout: float = 2.0):
        """SNTP query via stdlib UDP (no ntplib dependency). Returns the offset
        in seconds (server − local midpoint) or None on any failure. Read-only:
        never adjusts the clock."""
        import socket  # noqa: PLC0415
        import struct  # noqa: PLC0415
        import time as _t  # noqa: PLC0415

        NTP_DELTA = 2208988800  # seconds between 1900-01-01 and 1970-01-01
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            t0 = _t.time()
            sock.sendto(b"\x1b" + 47 * b"\0", (server, 123))
            data, _ = sock.recvfrom(64)
            t3 = _t.time()
            if len(data) < 48:
                return None
            secs, frac = struct.unpack("!II", data[40:48])
            server_time = secs - NTP_DELTA + frac / 2**32
            return server_time - (t0 + t3) / 2
        except (OSError, ValueError):
            return None
        finally:
            sock.close()

    def _tls_date_offset(self, url: str = ""):
        """Offset (seconds) between the HTTPS Date response header of a known
        endpoint and the local clock. Coarse (1s header resolution) — used only
        as a third-source sanity check on the unauthenticated NTP answers
        (Shostack: NTP is spoofable; TLS date rides an authenticated channel).
        Tries two endpoints — without a TLS answer the clock-fix suggestion
        gate can never open, so availability matters."""
        import email.utils  # noqa: PLC0415
        import time as _t  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        urls = (url,) if url else (
            "https://www.cloudflare.com",
            "https://www.google.com",
        )
        for u in urls:
            try:
                req = urllib.request.Request(u, method="HEAD")
                t0 = _t.time()
                with urllib.request.urlopen(req, timeout=4) as r:
                    date_hdr = r.headers.get("Date")
                t3 = _t.time()
                if date_hdr:
                    server = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                    return server - (t0 + t3) / 2
            except (ValueError, IndexError):
                continue
        return None

    def _time_banner(self, verified: bool = False) -> str:
        """The [TIME] banner (CHRONOS-2). Injected server-side into the first
        search_kb/search_web return of each session and into every time_check()."""
        now = datetime.now().astimezone()
        cutoff = (self.valves.MODEL_PRETRAIN_CUTOFF or "").strip()
        if cutoff:
            try:
                cy, cm = int(cutoff[:4]), int(cutoff[5:7])
                gap = (now.year - cy) * 12 + (now.month - cm)
                cut_txt = f"model cutoff={cutoff} | gap≈{gap} months"
            except Exception:  # noqa: BLE001 (time_check main fallback)
                cut_txt = f"model cutoff={cutoff!r} (unparseable — use YYYY-MM)"
        else:
            cut_txt = "model cutoff UNSET (set MODEL_PRETRAIN_CUTOFF valve)"
        src = "NTP-verified" if verified else "system clock — run time_check() to NTP-verify"
        return (
            f"[TIME] now={now:%Y-%m-%d} ({src}) | {cut_txt} — any version/price/"
            "CVE/firmware claim from model memory is presumed stale; web-verify "
            "before asserting."
        )

    _DREAM_DIGEST_MAX_CHARS = 200

    def _dream_banner(self) -> str:
        """The [DREAM] banner (TRAUM Thread 3, Prompt 3.5, v0.4.0-a). Reads
        dream_digest.py's own output (DREAM_DIGEST_PATH valve) and surfaces
        just the digest date + pending human-gate count, with a pointer to
        the full file for detail — the LSE should never need to know
        tools/dream_digest.py exists to learn a digest is waiting.

        Missing valve, missing/unreadable file, or a digest whose header we
        can't parse are all legitimate null results (no dream cycle has run
        yet, DREAM_DIGEST_PATH is unset, etc.) — this degrades to "" rather
        than raising or emitting a confusing partial line, same non-fatal
        discipline as dream_digest.py's own gather_* steps.
        """
        path = (self.valves.DREAM_DIGEST_PATH or "").strip()
        if not path:
            return ""
        try:
            with open(path, "rt", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        import re as _re  # noqa: PLC0415

        m_date = _re.search(r"generated (\d{4}-\d{2}-\d{2})", text)
        m_pending = _re.search(r"## Pending human-gate \((\d+)\)", text)
        if not m_date or not m_pending:
            return ""
        line = (
            f"[DREAM] digest={m_date.group(1)} | pending-gate={m_pending.group(1)} "
            f"| read {path} for details"
        )
        return line[: self._DREAM_DIGEST_MAX_CHARS]

    def _consume_time_banner(self) -> str:
        """Return the [TIME] banner exactly once per session (server-side
        enforcement — compliance must not depend on the model reading
        docstrings). TRAUM Thread 3 (v0.4.0-a): also appends the [DREAM]
        banner (Prompt 3.5) on this same first-call gate — one server-side
        injection point covers both time-anchoring and dream-digest
        awareness before the session's first real search_kb result.
        Do NOT add a second, separate once-per-session flag for [DREAM] —
        reusing _time_banner_emitted is what guarantees the two banners can
        never desync (one firing without the other)."""
        if self._time_banner_emitted:
            return ""
        self._time_banner_emitted = True
        banner = self._time_banner(verified=False)
        dream_line = self._dream_banner()
        if dream_line:
            banner += "\n" + dream_line
        return banner + "\n\n"

    def time_check(self) -> str:
        """
        Verify the system clock against external time sources and anchor the
        session against the model's pretraining cutoff (CHRONOS-1/2, v0.3.1).

        WHEN TO CALL:
          - At the start of any session involving dates, versions, CVEs, firmware,
            prices, or release timelines.
          - Whenever a KB hit is tagged [EXPIRED] or a claim depends on "now".
          - When the user asks "what time/date is it" or doubts the clock.

        WHAT IT DOES (report-only — NEVER adjusts the clock):
          1. Queries 2 NTP servers (pool.ntp.org, time.cloudflare.com; 2s timeout,
             stdlib SNTP) for clock offset.
          2. Cross-checks against the TLS Date header of a known HTTPS endpoint —
             NTP is unauthenticated/spoofable; a fix is only ever SUGGESTED when
             both NTP servers agree AND the TLS date corroborates.
          3. Compares verified now against MODEL_PRETRAIN_CUTOFF and returns the
             [TIME] banner: everything the model "remembers" after that gap is
             presumed stale.
          Offset >2s → discrepancy report with the suggested fix command
          (timedatectl/chronyc) for the HUMAN to run, and the event is recorded
          to lse-errors. Graceful degrade: no NTP reachable → system clock + WARN.

        FIX EXECUTION PROHIBITION — mandatory, no exceptions:
          NEVER execute the suggested clock fix yourself — not via
          execute_command, not by raising an unrequested sudo_delegation_block.
          Surface the discrepancy; the human decides. Only produce a delegation
          block if the user explicitly asks to fix the clock. Executing or
          auto-delegating a clock change unasked is a protocol violation.
          GOOD: offset 4.2s found -> report it + show the suggested command.
                User replies "yes fix it" -> NOW raise the delegation block.
          BAD:  offset found -> immediately emit sudo_delegation_block
                <- unasked delegation. The report IS the deliverable.

        GATE: call at most once per session unless the user asks again — results
        do not change mid-session.
        """
        self._log("TIME-CHECK")
        try:
            servers = ("pool.ntp.org", "time.cloudflare.com")
            offsets = {s: self._sntp_offset(s) for s in servers}
            good = {s: o for s, o in offsets.items() if o is not None}
            tls_off = self._tls_date_offset()
            now = datetime.now().astimezone()
            lines = [f"TIME CHECK — system clock: {now:%Y-%m-%d %H:%M:%S %z}"]
            for s in servers:
                o = offsets[s]
                lines.append(
                    f"  NTP {s}: " + (f"offset {o * 1000:+.0f} ms" if o is not None
                                      else "UNREACHABLE")
                )
            lines.append(
                "  TLS date (cloudflare.com): "
                + (f"offset {tls_off:+.1f} s" if tls_off is not None else "unavailable")
            )
            verified = False
            if len(good) == 2:
                o1, o2 = good.values()
                if abs(o1 - o2) <= 1.0:
                    verified = True
                    mean = (o1 + o2) / 2
                    if abs(mean) > 2.0:
                        tls_agrees = tls_off is not None and abs(tls_off - mean) <= 5.0
                        lines.append(
                            f"  ⚠️ CLOCK DISCREPANCY: system clock is {mean:+.1f}s vs "
                            "NTP consensus"
                            + ("" if tls_agrees else " (TLS date does NOT corroborate "
                               "— treat the NTP answer itself as suspect, no fix "
                               "suggested)")
                        )
                        if tls_agrees:
                            lines.append(
                                "  SUGGESTED FIX (human-run, never automatic): "
                                "sudo timedatectl set-ntp true   # or: chronyc makestep"
                            )
                            self.record_error(
                                error_text=f"system clock offset {mean:+.1f}s vs NTP consensus",
                                context="time_check() CHRONOS-1 discrepancy detection",
                                resolution="suggested timedatectl set-ntp true / chronyc makestep (human-run)",
                            )
                    else:
                        lines.append("  ✅ clock agrees with NTP consensus (<2s)")
                else:
                    lines.append(
                        "  ⚠️ NTP servers DISAGREE with each other (>1s) — "
                        "unauthenticated NTP cannot be trusted here; using system clock"
                    )
            elif len(good) == 1:
                s, o = next(iter(good.items()))
                verified = tls_off is not None and abs(tls_off - o) <= 5.0
                lines.append(
                    f"  single NTP source ({s}) "
                    + ("corroborated by TLS date" if verified
                       else "NOT corroborated — treating as unverified")
                )
            else:
                lines.append(
                    "  WARN: no NTP source reachable — degrading to system clock"
                )
            self._time_banner_emitted = True  # this return carries the banner
            lines.append("")
            lines.append(self._time_banner(verified=verified))
            # TRAUM Thread 3 close (v0.4.0-a, 2026-07-12): time_check() sets the
            # SAME _time_banner_emitted flag _consume_time_banner() gates on, so
            # a session that calls time_check() before its first search_kb was
            # silently losing the [DREAM] banner forever (the flag trips here,
            # _consume_time_banner() later sees it already True and returns "").
            # This is exactly the desync _consume_time_banner()'s own docstring
            # says reusing the flag is supposed to prevent — the assumption that
            # _consume_time_banner() is the ONLY place that sets the flag was
            # wrong; time_check() is a second one and the system prompt's own
            # TIME DISCIPLINE section tells the model to call it first for any
            # "date-sensitive work", which a TRAUM digest-review session is.
            # Fix: time_check() must also append the [DREAM] line on the same
            # gate it already owns, so whichever tool fires first, both banners
            # still always appear together — restoring the "can never desync"
            # guarantee for real instead of only for the search_kb-first case.
            dream_line = self._dream_banner()
            if dream_line:
                lines.append(dream_line)
            return "\n".join(lines)
        except Exception as e:  # noqa: BLE001 (time_check main fallback)
            self._log(f"TIME-CHECK ERROR: {e}")
            return f"time_check failed: {e}\n{self._time_banner(verified=False)}"

    # ── PROVE-IT — user-callable tests as evidence (v0.3.6, Workstream C) ────

    def run_tests(self, scope: str = "all") -> str:
        """
        SPEC: Run the LSE's own test surface and return the RAW output as evidence
        (PROVE-1, v0.3.6). When the user says "prove it" / "run the tests" /
        "is the harness green", THIS is the answer — never prose.

        EVIDENCE RULE — mandatory:
        The verbatim output below each section IS the evidence. Paste the
        relevant lines into evidence= fields — do NOT summarise test output.
        A FAIL result must be reported verbatim, never softened.

        GATE: at most once per scope per session unless code changed between.
        Do NOT run to "double-check" a scope that just passed.

        SCOPES (hardcoded allowlist — model supplies ONLY the scope name):
          kb        — ES index existence + doc-count sanity (read-only probes)
          retrieval — rag/eval_retrieval.py --self-test (no ES/Ollama needed)
          rules     — eval_goethe_rules.py — LLM-BEHAVIOR eval via llama-server.
                      Minutes of GPU time. EXPLICIT scope only, never part of 'all';
                      do not run while the user is mid-conversation with the model.
          harness   — pytest tests/ (contract suites) AND pytest scripts/
                      (legacy harness; failures there are FINDINGS, report them)
          data      — scripts/dataset_lint.py: gold-set schema/provenance lint
          all       — kb + retrieval + pytest tests/ + data (rules/scripts only
                      when explicitly named; ~1-2 minutes)

        NOTES:
        Args: scope: one of kb | retrieval | rules | harness | data | all.
        """
        import subprocess as _sp  # noqa: PLC0415
        import sys as _sys  # noqa: PLC0415

        self._log(f"RUN-TESTS: scope={scope}")
        scopes = ("kb", "retrieval", "rules", "harness", "data", "all")
        if scope not in scopes:
            return f"run_tests: unknown scope '{scope}'. Valid: {', '.join(scopes)}."
        repo = self.valves.REPO_DIR.rstrip("/")
        py = _sys.executable
        sections: list = []

        def _kb_scope() -> tuple:
            try:
                es = self._es()
                lines = []
                ok = True
                for idx in ("lse-kb", "lse-errors-1024", "lse-skills",
                            "lse-rfc-kb", "lse-search-cache"):
                    try:
                        if es.indices.exists(index=idx):
                            c = es.count(index=idx)["count"]
                            lines.append(f"  {idx}: EXISTS, {c} docs")
                            if idx == "lse-kb" and c == 0:
                                ok = False
                                lines.append("    ^ FAIL: lse-kb is EMPTY")
                        else:
                            lines.append(f"  {idx}: MISSING")
                            if idx in ("lse-kb", "lse-errors-1024"):
                                ok = False
                    except Exception as exc:  # noqa: BLE001 (ES inner)
                        lines.append(f"  {idx}: ERROR {exc}")
                        ok = False
                return ("PASS" if ok else "FAIL"), "\n".join(lines)
            except Exception as exc:  # noqa: BLE001 (ES client black-box; not a requests exception)
                return "FAIL", f"  ES unreachable: {exc}"

        def _cmd_scope(label, rel_target, argv, timeout_s) -> tuple:
            target = os.path.join(repo, rel_target)
            if not os.path.exists(target):
                return "SKIP", f"  {rel_target} not present on this node ({repo})"
            try:
                r = _sp.run(argv, cwd=repo, capture_output=True, text=True,
                            timeout=timeout_s)
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                if len(out) > 1200:
                    out = out[:300] + f"\n  … [{len(out) - 1500} chars omitted] …\n" + out[-1200:]
                status = "PASS" if r.returncode == 0 else f"FAIL (exit {r.returncode})"
                return status, out or "(no output)"
            except _sp.TimeoutExpired:
                return "FAIL", f"  TIMEOUT after {timeout_s}s"
            except subprocess.SubprocessError as exc:
                return "FAIL", f"  {exc}"

        want = (scope,) if scope != "all" else ("kb", "retrieval", "harness", "data")
        for sc in want:
            if sc == "kb":
                st, body = _kb_scope()
                sections.append((sc, st, body))
            elif sc == "retrieval":
                st, body = _cmd_scope(
                    sc, "rag/eval_retrieval.py",
                    [py, "rag/eval_retrieval.py", "--self-test"], 90)
                sections.append((sc, st, body))
            elif sc == "data":
                st, body = _cmd_scope(
                    sc, "scripts/dataset_lint.py",
                    [py, "scripts/dataset_lint.py"], 60)
                sections.append((sc, st, body))
            elif sc == "rules":
                st, body = _cmd_scope(
                    sc, "eval_goethe_rules.py",
                    [py, "eval_goethe_rules.py"], 300)
                sections.append((sc, st, body))
            elif sc == "harness":
                st, body = _cmd_scope(
                    "harness/tests", "tests",
                    [py, "-m", "pytest", "tests/", "-q", "--tb=line",
                     "-p", "no:cacheprovider"], 200)
                sections.append(("harness/tests", st, body))
                if scope == "harness":  # legacy scripts only on explicit ask
                    st2, body2 = _cmd_scope(
                        "harness/scripts", "scripts",
                        [py, "-m", "pytest", "scripts/", "-q", "--tb=line",
                         "-p", "no:cacheprovider"], 150)
                    sections.append(("harness/scripts", st2, body2))
        overall = "PASS"
        if any(st.startswith("FAIL") for _, st, _ in sections):
            overall = "FAIL"
        elif all(st == "SKIP" for _, st, _ in sections):
            overall = "SKIP"
        head = " | ".join(f"{name}={st}" for name, st, _ in sections)
        report = [f"RUN-TESTS [{overall}] — {head}", ""]
        for name, st, body in sections:
            report.append(f"── {name}: {st} ──")
            report.append(body)
            report.append("")
        return "\n".join(report)[:3800]

    # Read-only argv allowlist for assert_state. Threat note (Shostack): this
    # is an exec surface — first token must match, mutating verbs and shell
    # metacharacters are rejected, and execution is argv-only (no shell).
    _ASSERT_ALLOW = {
        "df", "ss", "sha256sum", "dig", "pgrep", "stat", "ls", "wc",
        "free", "uptime", "curl", "systemctl", "ping", "ip", "nvidia-smi",
    }
    _ASSERT_CURL_DENY = {
        "-x", "--request", "-d", "--data", "--data-raw", "--data-binary",
        "--data-urlencode", "-f", "--form", "-t", "--upload-file",
        "-o", "--output", "-O", "--remote-name", "-K", "--config",
    }

    def assert_state(self, check_command: str, expected_regex: str) -> str:
        """
        SPEC: Run ONE read-only check command and assert a regex against its output —
        turning "I claim it worked" into "I ran the check and the output
        matched" (PROVE-3, v0.3.6). This is the PREFERRED producer for
        evidence= fields (plan_step_done, skill_outcome, record_outcome).

        GATE: call whenever you are about to CLAIM a state ("service is up",
        "file exists", "port is free") in a finding, evidence= field, or
        response — one assert per claim. Do NOT call for states you are not
        about to assert, and never as a substitute for reading file content.

        ALLOWLIST — read-only commands ONLY (argv-exec, no shell):
          df, ss, sha256sum, dig, pgrep, stat, ls, wc, free, uptime, ip (show
          subcommands), nvidia-smi, curl (GET only — no -X/-d/-o/upload),
          systemctl (is-active/is-enabled/is-failed/show only), ping (count
          capped). Anything else — including pipes, redirects, ';', '&&' — is
          REJECTED. This tool NEVER mutates state. Trying to sneak a mutating
          command through here is a protocol violation.

        GOOD: assert_state("systemctl is-active ollama", "^active")
        BAD:  assert_state("systemctl restart ollama", "active")  ← mutating
        BAD:  assert_state("df -h | grep sda", "9[0-9]%")         ← pipe

        AFTER THE RESULT:
          PASS ✅ → paste the returned block as evidence where needed.
          FAIL ❌ → the claim is NOT established. Report the mismatch verbatim;
          do NOT retry with a looser regex just to make it pass — weakening an
          assertion to green is a protocol violation.

        NOTES:
        Args: check_command (one allowlisted command), expected_regex (Python regex).
        """
        import re as _re  # noqa: PLC0415
        import shlex  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        self._log(f"ASSERT-STATE: {check_command[:100]!r} ~ /{expected_regex[:60]}/")
        try:
            argv = shlex.split(check_command)
        except ValueError as exc:
            return f"assert_state rejected: unparseable command ({exc})."
        if not argv:
            return "assert_state rejected: empty command."
        bad_tokens = [t for t in argv if any(c in t for c in ";|&`$><\n")]
        if bad_tokens:
            return (
                f"assert_state rejected: shell metacharacters in {bad_tokens!r} — "
                "no pipes/redirects/chaining. Put filtering in expected_regex."
            )
        prog = os.path.basename(argv[0])
        if prog not in self._ASSERT_ALLOW:
            return (
                f"assert_state rejected: '{prog}' is not in the read-only "
                f"allowlist ({', '.join(sorted(self._ASSERT_ALLOW))}). "
                "Use execute_command for anything else."
            )
        if prog == "systemctl":
            verb = argv[1] if len(argv) > 1 else ""
            if verb not in ("is-active", "is-enabled", "is-failed", "show", "status"):
                return (
                    f"assert_state rejected: systemctl verb '{verb}' — only "
                    "is-active/is-enabled/is-failed/show/status (read-only)."
                )
            if verb == "status" and "--no-pager" not in argv:
                argv.insert(2, "--no-pager")
        if prog == "curl":
            lowered = {t.lower() for t in argv[1:]}
            hit = lowered & self._ASSERT_CURL_DENY
            if hit:
                return (
                    f"assert_state rejected: curl flag(s) {sorted(hit)} — "
                    "GET-only probes here; writes go through execute_command."
                )
            if "-s" not in argv:
                argv.insert(1, "-s")
        if prog == "ip":
            sub = argv[1] if len(argv) > 1 else ""
            if sub not in ("addr", "address", "route", "link", "neigh", "-br"):
                return "assert_state rejected: only 'ip addr/route/link/neigh' reads."
            if any(t in ("add", "del", "set", "flush", "replace") for t in argv):
                return "assert_state rejected: mutating ip subcommand."
        if prog == "ping" and "-c" not in argv:
            argv[1:1] = ["-c", "3"]
        try:
            r = _sp.run(argv, capture_output=True, text=True, timeout=20)
            out = ((r.stdout or "") + (r.stderr or "")).strip() or "(no output)"
        except _sp.TimeoutExpired:
            return f"ASSERT FAIL ❌ — '{check_command}' timed out after 20s."
        except FileNotFoundError:
            return f"ASSERT FAIL ❌ — '{prog}' not found on this host."
        except OSError as exc:
            return f"assert_state error: {exc}"
        out_cap = out[:1500]
        try:
            m = _re.search(expected_regex, out, _re.MULTILINE)
        except _re.error as exc:
            return f"assert_state rejected: invalid regex /{expected_regex}/ ({exc})."
        if m:
            return (
                f"ASSERT PASS ✅ — /{expected_regex}/ matched {m.group(0)!r} "
                f"(exit {r.returncode})\n--- {check_command} ---\n{out_cap}"
            )
        return (
            f"ASSERT FAIL ❌ — /{expected_regex}/ NOT found in output "
            f"(exit {r.returncode})\n--- {check_command} ---\n{out_cap}"
        )

    # ------------------------------------------------------------------
    # Browser-rendering fallback helpers (v1.5.29)
    # Used by fetch_url when a reddit.com URL returns empty content
    # or an HTTP error (reddit blocks plain requests with 429/403).
    # ------------------------------------------------------------------

    def _fetch_via_browser(self, url: str, firecrawl_base: str, max_chars: int) -> str:
        """
        POST url to Firecrawl's /v1/scrape endpoint (JS-rendering stack).
        Returns extracted markdown text (capped at max_chars) or "" on any failure.

        firecrawl_base examples:
          "http://localhost:3002"            — node3090 local
          "http://node3090.home.arpa:3002"   — from LUCIFER over LAN
        """
        import requests as _req  # noqa: PLC0415

        try:
            resp = _req.post(
                f"{firecrawl_base}/v1/scrape",
                json={"url": url, "formats": ["markdown"]},
                timeout=45,
            )
            if resp.ok:
                data = resp.json()
                text = ((data.get("data") or {}).get("markdown") or "").strip()
                if text:
                    self._log(
                        f"FETCH-BROWSER: {len(text)} chars from {firecrawl_base}"
                    )
                    return text[:max_chars]
                self._log(f"FETCH-BROWSER: empty markdown from {firecrawl_base}")
            else:
                self._log(
                    f"FETCH-BROWSER: HTTP {resp.status_code} from {firecrawl_base}"
                )
        except _req.RequestException as exc:
            self._log(f"FETCH-BROWSER: error ({firecrawl_base}): {exc}")
        return ""

    def _reddit_browser_fallback(self, url: str, max_chars: int) -> str:
        """
        Route a reddit.com URL to the JS-rendering stack when plain requests
        returns empty content or errors.

        Routing logic (hostname-aware):
          node3090 → local Firecrawl at localhost:3002
          LUCIFER / other → ping node3090.home.arpa; if up, use Firecrawl
                            at node3090:3002 over LAN; if down, return "".

        Returns extracted text or "" (caller must handle the empty case).
        """
        import socket as _socket  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        hostname = _socket.gethostname().lower()

        if "node3090" in hostname:
            self._log("REDDIT-FALLBACK: node3090 — local Firecrawl")
            return self._fetch_via_browser(url, self.valves.FIRECRAWL_URL, max_chars)

        # LUCIFER or other node — check node3090 reachability first.
        self._log(f"REDDIT-FALLBACK: pinging {self._NODE_REGISTRY['node3090']['hostname']}")
        ping = _sp.run(
            ["ping", "-c", "1", "-W", "2", self._NODE_REGISTRY["node3090"]["hostname"]],
            capture_output=True,
        )
        if ping.returncode != 0:
            self._log("REDDIT-FALLBACK: node3090 offline — no browser rendering")
            return ""

        self._log("REDDIT-FALLBACK: node3090 up — using remote Firecrawl")
        return self._fetch_via_browser(
            url, self.valves.FIRECRAWL_REMOTE_URL, max_chars
        )

    def _extract_text_from_html(self, html: str, max_chars: int) -> str:
        """Extract plain text from HTML, stripping tags and control chars."""
        from html.parser import HTMLParser
        import re as _re  # noqa: PLC0415

        def _sanitize(s):
            # Strip control chars so stray binary bytes are removed
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)


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


        def _sanitize(s):
            # Strip control chars (except \n\t) so a stray binary byte can never
            # derail the OWUI markdown/HTML renderer downstream (v1.7.7).
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)

        parser = _TextExtractor()
        parser.feed(html)
        return _sanitize(parser.get_text())[:max_chars]

    def fetch_url(self, url: str, max_chars: int = 20000) -> str:
        """
        Fetch the full text content of a URL. Use as Step 3 of the SEARCH-THEN-FETCH
        protocol when search_web returns a snippet too short to answer the question.

        WHEN TO CALL:
          After search_web, if the snippet (≤300 chars) is truncated or insufficient.
          Call on the top result URL only — do not fetch multiple URLs per search.

        WHEN NOT TO CALL:
          If the search_web snippet already answers the question fully.
          Do not use as a substitute for search_web — always search first.

        UNVERIFIED-URL RULE — mandatory:
          Only fetch URLs received from a tool result (search_web, search_kb, KB
          docs, user message). NEVER construct a URL or hostname from memory; if
          a guessed hostname fails DNS, that is evidence the hostname is wrong —
          not that the network is broken. Presenting a self-generated URL to the
          user is a protocol violation.

        Returns plain text with HTML tags stripped, capped at max_chars characters.

        REDDIT BROWSER FALLBACK (v1.5.29):
          When the URL contains "reddit.com" and the plain requests fetch returns
          empty content OR raises an HTTP error (reddit blocks bots with 429/403),
          fetch_url automatically routes to _reddit_browser_fallback():
            node3090: local Firecrawl at localhost:3002
            LUCIFER:  pings node3090, then uses Firecrawl at node3090:3002 over LAN
          Successful browser-rendered results are prefixed "[browser-rendered]"
          and cached normally. If the fallback also fails, the original
          "No text content extracted" or error message is returned.
          Use search_reddit() as a further alternative when both paths fail.
        """
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            self._log(f"FETCH BLOCKED (budget): {url}")
            return _gate
        import requests  # noqa: PLC0415
        self._log(f"FETCH: {url}")
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                },
            )
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "").lower()
            head = resp.content[:5]

            # CONTENT-TYPE GUARD (v1.7.7): never feed binary to the HTML parser.
            # A PDF/image/octet-stream body decoded as text is raw FlateDecode
            # garbage — it pollutes context AND breaks OWUI <details> rendering.
            is_pdf = "application/pdf" in ctype or head == b"%PDF-"
            if is_pdf:
                text = self._extract_pdf_text(resp.content)
                if text.strip():
                    import re as _re  # noqa: PLC0415
                    out = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", " ".join(text.split()))[:max_chars]
                    self._fetch_cache[url] = {
                        "text": out,
                        "ts": datetime.now().timestamp(),
                    }
                    mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    return ("[PDF text-extracted] " + out + mandate) + _gate
                return (
                    f"PDF at {url} ({len(resp.content)} bytes) — text could not be "
                    "extracted here (no pdfminer/pypdf). Binary NOT returned. "
                    "Find an HTML source for the same content, or ask the operator "
                    "to run pdftotext. Do NOT retry this URL."
                ) + _gate
            if ctype and not (
                "text/html" in ctype
                or "text/plain" in ctype
                or "xml" in ctype
                or "json" in ctype
            ):
                return (
                    f"Non-text content at {url} (Content-Type: {ctype or 'unknown'}). "
                    "Binary NOT returned to avoid context pollution. Use an HTML "
                    "source. Do NOT retry this URL."
                ) + _gate

            text = self._extract_text_from_html(resp.text, max_chars)
            if text:
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                mandate = (
                    f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                    'claims="<fact1>, <fact2>") before asserting any version number, '
                    "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                )
                return (text + mandate) + _gate
            # Empty extract — try browser rendering for reddit URLs (v1.5.29)
            if "reddit.com" in url.lower():
                self._log("FETCH: empty for reddit URL — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return "No text content extracted." + _gate
        except requests.RequestException as e:
            # HTTP error (e.g. 403/429) — also try browser fallback for reddit (v1.5.29)
            if "reddit.com" in url.lower():
                self._log(f"FETCH: exception for reddit URL ({e}) — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return f"ERROR fetching {url}: {e}"

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF. Tries pdfminer, falls back to pypdf."""
        try:
            import io  # noqa: PLC0415
            from pdfminer.high_level import extract_text as _pe  # noqa: PLC0415
            return _pe(io.BytesIO(pdf_bytes)) or ""
        except Exception:  # noqa: BLE001 (pdfminer fallback chain)
            try:
                import io  # noqa: PLC0415
                from pypdf import PdfReader as _PR  # noqa: PLC0415
                rdr = _PR(io.BytesIO(pdf_bytes))
                return "\n".join(
                    (p.extract_text() or "") for p in rdr.pages)
            except Exception:  # noqa: BLE001 (pypdf fallback end)
                return ""

    def verify_source_claims(self, url: str, claims: str) -> str:
        """
        SPEC: Re-fetch a source URL and check whether specific factual claims appear
        in it verbatim. Call BEFORE asserting any version number, date, release name,
        or config value derived from fetch_url. Returns FOUND / PARTIAL / NOT_FOUND
        per claim with verbatim ±300-char excerpts.

        MANDATORY after every fetch_url — do NOT skip:
        The fabrication#5 root cause was synthesis-overwrite: the model had the
        correct source in context yet emitted phantom version strings. Prompt fences
        do not hold at synthesis (P25 proven). This function re-fetches the source
        in code and returns what is ACTUALLY there — the model cannot fabricate it.

        NOT_FOUND: claim absent from source. Label it UNVERIFIED. Do NOT retry.
        PARTIAL:   a token from your claim is present but the full claim is absent.
        FOUND:     the claim appears verbatim.

        This call does NOT count against the search budget.

        RULE — UNVERIFIED-URL: only fetch URLs received from a tool result.
        Never construct a URL or hostname from memory.

        NOTES:
        Args: url (source URL from a tool result), claims (comma-separated facts).
        Returns one FOUND/PARTIAL/NOT_FOUND line per claim with verbatim excerpt.
        """
        import re as _re  # noqa: PLC0415

        claim_list = [c.strip() for c in claims.split(",") if c.strip()]
        if not claim_list:
            return 'ERROR: no claims provided. Pass comma-separated facts to verify, e.g. claims="07.23.5, released 2026-05-30"'

        # ── Use cache or re-fetch ────────────────────────────────────────────
        ttl = max(0, int(getattr(self.valves, "SOURCE_VERIFY_CACHE_TTL", 300)))
        cached = self._fetch_cache.get(url)
        if cached and ttl > 0 and (datetime.now().timestamp() - cached["ts"]) < ttl:
            text = cached["text"]
            source_note = "(cached)"
        else:
            import requests as _req  # noqa: PLC0415
            self._log(f"VERIFY-FETCH: {url}")
            try:
                resp = _req.get(
                    url,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
                )
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").lower()
                is_pdf = "application/pdf" in ctype or resp.content[:5] == b"%PDF-"
                if is_pdf:
                    text = self._extract_pdf_text(resp.content)
                else:
                    text = self._extract_text_from_html(resp.text, 80000)
                text = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:80000]
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                source_note = "(re-fetched)"
            except _req.RequestException as e:
                return (
                    f"VERIFY ERROR: could not fetch {url}: {e}\n"
                    "All claims remain UNVERIFIED — label them as such in your response."
                )

        text_l = text.lower()
        WINDOW = 300

        # ── Check each claim ─────────────────────────────────────────────────
        results = [f"Source: {url} {source_note}"]
        for claim in claim_list:
            claim_l = claim.lower()

            # Exact substring match
            idx = text_l.find(claim_l)
            if idx >= 0:
                start = max(0, idx - WINDOW)
                end = min(len(text), idx + len(claim) + WINDOW)
                excerpt = text[start:end].strip().replace("\n", " ")
                results.append(
                    f"  FOUND    | {claim!r}\n" f"           | excerpt: ...{excerpt}..."
                )
                continue

            # Token-level: version strings first, then long words
            ver_tokens = _re.findall(r"\b\d{1,3}[\.\d]{2,}\b", claim)
            word_tokens = _re.findall(r"\b[a-z0-9_-]{5,}\b", claim_l)
            tokens_to_try = (ver_tokens or []) + word_tokens

            found_tok = None
            for tok in tokens_to_try:
                tidx = text_l.find(tok.lower())
                if tidx >= 0 and found_tok is None:
                    start = max(0, tidx - WINDOW)
                    end = min(len(text), tidx + len(tok) + WINDOW)
                    found_tok = (tok, text[start:end].strip().replace("\n", " "))

            if found_tok:
                tok, exc = found_tok
                results.append(
                    f"  PARTIAL  | {claim!r}\n"
                    f"           | token {tok!r} found but full claim absent.\n"
                    f"           | Read excerpt for what source ACTUALLY says:\n"
                    f"           | ...{exc}..."
                )
            else:
                src_vers = _re.findall(r"\b\d{2}\.\d{2}[\.\d]*\b", text)
                ver_ctx = (
                    ", ".join(dict.fromkeys(src_vers[:8]))
                    if src_vers
                    else "(none found)"
                )
                results.append(
                    f"  NOT_FOUND| {claim!r}\n"
                    f"           | source version strings: {ver_ctx}\n"
                    f"           | → label this claim UNVERIFIED in your response"
                )

        return "\n".join(results)

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
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            if resp.status_code == 404:
                return f"No releases found for '{repo}' (repo may not exist or have no releases)."
            resp.raise_for_status()
            data = resp.json()
            tag = data.get("tag_name", "unknown")
            name = data.get("name", tag)
            published = data.get("published_at", "unknown date")[:10]  # YYYY-MM-DD
            prerelease = data.get("prerelease", False)
            draft = data.get("draft", False)
            html_url = data.get("html_url", "")

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
        except requests.RequestException as e:
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
            resp = requests.get(f"{self.valves.LLAMA_SERVER_URL}/slots", timeout=5)
            slots = resp.json()
            if not slots:
                return "No active slots found on llama.cpp server."
            s = slots[0]

            # v1.5.4 fix: llama-server build >=9307 uses n_prompt_tokens, not n_past.
            n_prompt = s.get("n_prompt_tokens", 0)
            n_ctx = s.get("n_ctx", 65536)
            n_cache = s.get("n_prompt_tokens_cache", 0)
            n_proc = s.get("n_prompt_tokens_processed", 0)

            next_tok = s.get("next_token", [{}])
            nt = next_tok[0] if next_tok else {}
            n_decoded = nt.get("n_decoded", 0)
            n_remain = nt.get("n_remain", -1)
            n_predict = s.get("params", {}).get("n_predict", 0)

            pct = round(n_prompt / n_ctx * 100, 1) if n_ctx else 0.0
            cache_pct = round(n_cache / n_prompt * 100) if n_prompt else 0

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
        except requests.RequestException as e:
            return f"ERROR querying llama.cpp: {str(e)}"

    def monitor_download(
        self, file_path: str, expected_bytes: int, interface: str = ""
    ) -> str:
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
        import shutil  # noqa: PLC0415
        import os as _os  # noqa: PLC0415

        monitor_script = _os.path.join(_LSE_BASE_PATH, "download-monitor.py")
        # Prefer the miniforge interpreter when it actually exists; otherwise fall
        # back to whatever python3 is on PATH. The previous logic used the hardcoded
        # miniforge path unconditionally unless python3 was missing from PATH, which
        # broke on hosts without miniforge installed.
        python_bin = "/home/sy5/miniforge3/bin/python3"  # miniforge python for Prometheus client; falls back to PATH python3 if missing
        if not _os.path.exists(python_bin):
            python_bin = shutil.which("python3") or "python3"

        if not _os.path.exists(monitor_script):
            return (
                "SETUP_REQUIRED | download-monitor.py not found at /opt/local-se/. "  # user-facing message text; intentionally literal
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
        except (subprocess.SubprocessError, OSError) as exc:
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
          6. Erases the llama.cpp KV cache slot via POST /slots/0?action=erase
             (action is a QUERY PARAMETER — a JSON body {"action":...} is rejected
             with "Invalid action" on every llama.cpp version).
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

            chat_obj = json.loads(row["chat"])
            history = chat_obj.get("history", {})
            messages_map = history.get("messages", {})
            current_id = history.get("currentId", "")

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
                slots_url = (
                    self.valves.LLAMA_SERVER_URL.rstrip("/") + "/slots/0?action=erase"
                )
                kv_req = urllib.request.Request(
                    slots_url,
                    data=b"",
                    method="POST",
                )
                with urllib.request.urlopen(kv_req, timeout=5) as resp:
                    try:
                        n_erased = json.loads(resp.read()).get("n_erased", "?")
                    except Exception:  # noqa: BLE001 (KV cache metadata parse)
                        n_erased = "?"
                    kv_status = (
                        f"KV cache erased (slot 0, HTTP {resp.status}, "
                        f"n_erased={n_erased})"
                    )
            except (urllib.error.URLError, OSError) as kv_err:
                kv_status = f"KV cache erase failed: {kv_err}"

            return (
                f"Compacted: {total_before} → {len(kept) + 1} messages "
                f"({total_before - len(kept)} dropped). "
                f"Summary node prepended. {kv_status}."
            )

        except (json.JSONDecodeError, urllib.error.URLError, OSError) as e:
            return f"ERROR during compact_context: {str(e)}"

    # ── RAG / KB surface — EXTRACTED to goethe_kb.py (PH5-2, 2026-07-18) ────
    # _embed, _es, search_kb, index_to_kb, record_error, check_error_kb,
    # _resolve_kb_id, record_outcome, mentor_correct, kb_verify, mentor_demote,
    # skill_search, skill_record, skill_outcome now live in KBMixin
    # (tools/goethe_kb.py) with TrustPolicy (PH5-1). Behavior pinned by
    # tests/test_kb_contracts.py.


    # search_rfc: REMOVED 2026-07-31. Retired PH4-3 (2026-07-18) after 0 calls
    # across 6,967 journaled tool calls; it had been unregistered via
    # goethe_mcp SKIP_TOOLS ever since, so this body was unreachable code.
    # The lse-rfc-kb ES index (1490 chunks) is deliberately LEFT IN PLACE,
    # dormant - removing the caller does not justify destroying the corpus.
    # See CHANGELOG.md. Restore from backups/ if RFC lookup is ever revived.
    # NodeLifecycleMixin: _NODE_REGISTRY, _PROFILE_FLAGS, wake_node,
    # query_node_agent, check_node_agent_drift, start_node_agent,
    # stop_node_agent, shutdown_node EXTRACTED to goethe_node.py (D7,
    # 2026-07-31). _parse_llama_cmdline and _live_node_profile stay HERE:
    # they are called only by each other and by the extracted methods via
    # self, so they remain co-located with their sole caller chain.




    # ── Canonical-vs-live agent profile drift (v1.14.0) ──────────────────────
    # _NODE_REGISTRY[node]["agent_profile"] is the CANONICAL description of how
    # a node's llama-server should run. Nothing previously checked it against
    # reality, so the two drifted silently: on 2026-07-29 node3090's canonical
    # profile said ctx 96000 / 129 layers / 7 threads / budget 3072 while the
    # live server ran 131072 / 99 / 16 / 8192. start_node_agent() would have
    # "restarted" the node into a materially different configuration and
    # reported success.


    def _parse_llama_cmdline(self, cmdline: str) -> dict:
        """Parse a running llama-server command line into agent_profile keys.

        Returns the profile-shaped dict plus '_unmodelled': flags the server
        is running that agent_profile has no way to express. That second list
        matters more than it looks — it is the set of settings a restart would
        silently drop.
        """
        toks = cmdline.split()
        flag_to_key = {v: k for k, v in self._PROFILE_FLAGS.items()}
        out: dict = {}
        unmodelled: list = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if not t.startswith("--"):
                i += 1
                continue
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            has_val = bool(nxt) and not nxt.startswith("--")
            if t in flag_to_key:
                key = flag_to_key[t]
                val = nxt if has_val else ""
                if key != "model":
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        pass
                out[key] = val
            elif t == "--flash-attn":
                out["flash_attn"] = (nxt.lower() != "off") if has_val else True
            elif t == "--jinja":
                out["jinja"] = True
            elif t == "--metrics":
                out["metrics"] = True
            elif t not in ("--host", "--port"):
                unmodelled.append(t)
            i += 2 if has_val else 1
        out["_unmodelled"] = unmodelled
        return out

    def _live_node_profile(self, node: str):
        """(profile_dict, error_str). Reads the running llama-server cmdline
        over SSH. profile_dict is None when nothing is running."""
        import subprocess as _sp  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return None, f"Unknown node '{node}'"
        try:
            r = _sp.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                 "-o", "BatchMode=yes", f"{reg['ssh_user']}@{reg['hostname']}",
                 "pgrep -af 'llama[-]server' | head -1"],
                capture_output=True, text=True, timeout=25,
            )
        except subprocess.SubprocessError as exc:
            return None, f"SSH error: {exc}"
        if r.returncode != 0 and not r.stdout.strip():
            return None, ""
        line = r.stdout.strip()
        if not line:
            return None, ""
        parts = line.split(None, 1)
        return (self._parse_llama_cmdline(parts[1]) if len(parts) > 1 else {}), ""





    # ── Hermes Agent delegation ───────────────────────────────────────────────

    def _call_hermes(self, task: str, context: str = "", no_think: bool = True) -> str:
        """[RETIRED v0.2.7] — Hermes gateway (port 8642) no longer runs.
        Use _call_node_planner() instead.
        """
        return "ERROR: _call_hermes is RETIRED (v0.2.7) — use _call_node_planner"

    def _kanban_create_card(self, task_id: str, title: str, body: str) -> str:
        """[RETIRED v0.2.7] — kanban.db was Hermes-specific (/home/hermes-admin/.hermes/).
        Hermes has been retired. This method is dead code and will be removed.
        """
        return "kanban retired (v0.2.7)"
