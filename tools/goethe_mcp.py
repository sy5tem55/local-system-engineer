#!/usr/bin/env python3
"""
goethe_mcp.py - serve the LSE Goethe Tools as an MCP server (stdio or HTTP).
=============================================================================
Decouples the LSE toolset from any chat frontend. Works with llama-ui, Claude,
or any MCP-capable client. goethe's methods are plain
Python with the safety gates enforced INSIDE each method, so this wrapper just
imports the Tools class and re-exposes its public methods as MCP tools. The
docstrings you tuned for the model become the MCP tool descriptions for free.

USAGE
  # List the tools that would be exposed (pre-deploy sanity check) and exit
  python3 goethe_mcp.py --goethe ./goethe.py --list

  # stdio  (local clients: Claude, scripts, the Faust executor) - no network surface
  python3 goethe_mcp.py --goethe ./goethe.py

  # HTTP   (for llama-ui): bind 127.0.0.1, require a bearer token
  # Pick a FREE port - 9100 is node-exporter, 98xx are your other exporters.
  # Check first:  ss -tlnp | grep ':9700'   (empty = free)
  GOETHE_MCP_TOKEN=$(openssl rand -hex 16) \
  python3 goethe_mcp.py --goethe ./goethe.py --transport http --port 9700

VALVES
  Override any goethe valve via env GOETHE_<FIELD>, e.g.
    GOETHE_COMMAND_TIMEOUT=200  GOETHE_PFSENSE_API_KEY=...  GOETHE_ES_URL=...

EPISODE JOURNALING  (TRAUM Thread 1 — docs/dreaming/DESIGN.md)
  Every tool call appends one redacted, size-capped JSONL line to
    $GOETHE_EPISODE_DIR/YYYY-MM-DD/<session>.jsonl
  ON by default (GOETHE_EPISODE_DIR defaults to /opt/local-se/episodes). Set
  GOETHE_EPISODE_DIR="" to disable entirely (mirrors the GOETHE_MCP_TOKEN
  off-by-empty convention above). A journaling failure never breaks the
  underlying tool call — see _safe_journal().
  Size hygiene: a day-dir stops accepting new journal lines once it reaches
  GOETHE_EPISODE_DAY_CAP_MB (default 500) — loud stderr warning, tool call
  itself is unaffected. Rotation (gzip day-dirs older than 7 days) and the
  manifest.db build are a separate periodic job: tools/episode_index.py.

SECURITY  (read this - goethe runs shell + SSH + pfSense writes)
  Over HTTP this is a remote-code-execution surface. This server:
    * binds 127.0.0.1 by default (warns loudly if you change it),
    * requires a bearer token on HTTP when GOETHE_MCP_TOKEN is set (and warns
      when it is not),
    * sets CORS for the llama-ui origin so you can point the webui DIRECTLY at
      it and skip llama.cpp's CORS proxy (which has shipped an open-proxy bug
      and does not forward API keys to MCP servers).
  Never expose llama-server itself to the network. The internal gates (denylist,
  sudo-blocker, path allowlist, download/snapshot guards) limit WHAT runs, not
  WHO calls - the token is the "who".

REQUIRES:  pip install "mcp"  (+ uvicorn/starlette, pulled in for HTTP)
"""

import argparse
import datetime
import importlib.util
import inspect
import json
import os
import re
import sys
import time
import typing

__version__ = "1.13.0"
# 1.13.0 — tool-description cap: the bare `__doc__[:1024]` slice (v1.9.3,
#           2026-07-01) silently dropped the tail of 39 of 48 docstrings. The
#           v0.4.7 incident (planner's MANDATORY TRIGGER cut) produced
#           tests/test_docstring_mcp_truncation.py, but that gate only reads
#           goethe.py's Tools class and only counts methods with >=1 real
#           parameter -- so the pfsense/vaultwarden/net-discovery add-ons and
#           every zero-arg tool were never checked. Four tools were losing
#           contract keywords unnoticed: pfsense_query (NEVER@2997, RULE@2032),
#           pfsense_graphql (NEVER@1256), pfsense_log_summary (NEVER@1091) and
#           time_check (GATE@2037 -- in goethe.py, missed for taking no args).
#           Cap raised to 3072, the cheapest value that loses zero contracts
#           (measured 2026-08-08: 1024 -> 45,564 chars total; 3072 -> 83,294).
#           Truncation is now bounded AND loud -- never silent again.
# 1.12.0 — Goethe Console: mount tools/goethe_ui.py (UIRouter) into the HTTP
#           stack — GET /ui serves the dashboard (goethe_dashboard.html,
#           static, no token needed), GET /api/ui/* are read-only JSON panels
#           (KB trust lifecycle, TRAUM dream digest, tasks.db ledger, episode
#           stats) gated by the SAME bearer token as /mcp. The router sits
#           between _TokenGuard and CORSMiddleware so the static page loads in
#           a plain browser while data stays token-gated; it does its own
#           token check with the same normalisation _TokenGuard uses. Import
#           is fail-safe: a missing/broken goethe_ui.py logs a warning and the
#           MCP surface is completely unaffected. Disable with GOETHE_UI=off.
# 1.11.1 — fix a real redaction gap Prompt 1.8's contract tests caught: the
#           RESULT of a _SENSITIVE_TOOLS call (get_vault_secret, etc.) was only
#           run through the generic value/pattern redaction in _redact_text,
#           same as any other tool's result — meaning the actual secret
#           get_vault_secret returns would sail straight into the episode
#           JSONL untouched unless it happened to match a known valve value or
#           a Bearer/pattern regex. _journal() now blanket-redacts the result
#           for _SENSITIVE_TOOLS the same way _redact_args already blanket-
#           redacts the args (DESIGN.md §4 rule 1), before the
#           exception/string/json branches even run.
# 1.11.0 — episode journaling size hygiene (TRAUM Thread 1, Prompt 1.4): refuse
#           to journal (loud stderr warning, tool call itself still succeeds)
#           once a day-dir reaches GOETHE_EPISODE_DAY_CAP_MB (default 500MB).
#           Day-dir size is cached for 30s (_DAY_SIZE_CACHE_TTL) so the cap
#           check doesn't turn into a directory walk on every single tool call;
#           the cache is nudged forward on each successful write rather than
#           re-scanned. Actual rotation (gzip day-dirs older than 7 days) and
#           the manifest.db build live in the new tools/episode_index.py,
#           run periodically — this valve is the write-time half only.
# 1.10.0 — episode journaling: every tool call appends one redacted, capped JSONL
#           line to $GOETHE_EPISODE_DIR/YYYY-MM-DD/<session>.jsonl (TRAUM Thread 1,
#           Prompt 1.3; schema + redaction rules from docs/dreaming/DESIGN.md).
#           Session id prefers real MCP connection identity — read via the SDK's
#           request_ctx contextvar (mcp.server.lowlevel.server), no wrapper-schema
#           changes required — and falls back to gateway-PID + first-call-timestamp
#           when unavailable (stdio transport, or an older/newer SDK that doesn't
#           expose it the same way). Every tool call is wrapped in try/except/
#           finally so a journal failure can never break the tool call itself —
#           it's caught and logged to stderr instead. Default
#           GOETHE_EPISODE_DIR=/opt/local-se/episodes; set to "" to disable
#           (mirrors the GOETHE_MCP_TOKEN off-by-empty pattern already in this file).
# 1.9.3 — _TokenGuard accepts both "Bearer <token>" and raw "<token>" — normalises
#          auth header before comparison so llama-ui client format doesn't matter.
# 1.9.2 — remove all OpenWebUI/OWUI references from comments and docstrings;
#          owui venv path retained in start-goethe.sh (still has mcp installed).
# 1.9.1 — pass goethe.py's own version to FastMCP so the llama-ui banner
#          shows "LSE Goethe v0.2.2" instead of the mcp library version.
# 1.0.0 — initial release
# 1.1.0 — fix CORS middleware: declare at Starlette construction time so OPTIONS
#          preflights are intercepted before the route handler returns 405
# 1.2.0 — run sync tools via asyncio.to_thread to avoid blocking the uvicorn
#          event loop during long-running commands (caused client hangs / no SSE keepalives)
# 1.3.0 — fix 404 on GET /mcp: replace Starlette Mount("/", ...) wrapping (which
#          strips the leading "/" and mangles paths) with direct ASGI wrapping
# 1.4.0 — attempted ASGI response interception to strip anyOf-null; _ToolSchemaFixer
#          buffers response chunks and rewrites.
# 1.5.0 — fix anyOf-null at source: _annotation() no longer wraps None-default params
#          in Optional[X]. FastMCP emits {type:X} instead of anyOf:[{type:X},{null}].
#          Pydantic v2 validate_default=False means None defaults are never validated,
#          so omitted optional params still work.
# 1.6.0 — neutralize _ToolSchemaFixer: its buffering_send held SSE responses until
#          more_body=False which never arrives, causing "ASGI callable returned without
#          completing response". Since _annotation() already eliminates anyOf at source,
#          _ToolSchemaFixer is now a transparent passthrough.
# 1.7.0 — fix OPTIONS 400: CORSMiddleware returned 400 for DELETE preflights (session
#          teardown) because DELETE was absent from allow_methods. Added DELETE.
#          Also added _OptionsGuard as absolute outermost layer to catch any OPTIONS
#          missing Access-Control-Request-Method that CORSMiddleware would pass through
#          to FastMCP (which returns 400 for unknown methods).
# 1.8.0 — remove _OptionsGuard: it intercepted all OPTIONS including non-preflight
#          discovery requests llama-ui uses, returning a generic 200 instead of whatever
#          FastMCP returns — this prevented the initialize POST from ever being sent.
#          The DELETE preflight fix from 1.7.0 (allow_methods includes DELETE) is kept.
# 1.9.0 — self-contained port management: _free_port() kills any process holding the
#          port before binding (no external fuser dependency in start script). Added
#          graceful SIGTERM/SIGINT handler that shuts uvicorn cleanly so the port is
#          released immediately on exit.

# Frontend-injected parameters goethe methods may declare — never exposed as MCP tool args.
INJECTED = {
    "__event_emitter__", "__event_call__", "__chat_id__", "__user__",
    "__request__", "__metadata__", "__model__", "__messages__",
    "__files__", "__id__", "__task__", "__tools__",
}

# Methods that require a chat-frontend DB — not functional via MCP, excluded
# from tool exposure. To revive one, remove it from this set.
#
# search_rfc used to be listed here. It was retired PH4-3 (2026-07-18) after 0
# calls across 6,967 journaled tool calls, which left its body unreachable, and
# the body was removed from goethe.py on 2026-07-31. The lse-rfc-kb ES index
# (1490 chunks) is deliberately left in place, dormant.
SKIP_TOOLS = {"compact_context"}

# Upper bound on the tool description handed to the MCP client. A docstring IS
# the tool's contract here (see docs and the lse-docstring-optimizer skill), so
# a cap that cuts one mid-sentence removes a rule the model is still judged by.
# 3072 is measured, not guessed: it is the smallest value at which no tool's
# MUST/MANDATORY/NEVER/GATE/RULE/REQUIRED keyword falls past the cut
# (2026-08-08; pfsense_query's NEVER sits at 2997, the deepest in the fleet).
# Raising this is cheap in code and expensive in context -- every byte here is
# resident in every request. Prefer front-loading a docstring over raising it.
_TOOL_DESC_MAX = int(os.environ.get("GOETHE_MCP_TOOL_DESC_MAX", "3072"))


def _goethe_version(path: str) -> str:
    """Read the first 512 bytes of goethe.py and extract 'version: X.Y.Z'."""
    import re
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(512)
        m = re.search(r'^version:\s*(\S+)', head, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def load_goethe(path: str):
    """Import goethe.py (hyphen/extension agnostic) and return its Tools class."""
    abspath = os.path.abspath(path)
    if not os.path.isfile(abspath):
        raise SystemExit(f"[goethe_mcp] goethe file not found: {abspath}")
    spec = importlib.util.spec_from_file_location("goethe_mod", abspath)
    if spec is None or spec.loader is None:
        raise SystemExit(f"[goethe_mcp] cannot load module from {abspath}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Tools"):
        raise SystemExit("[goethe_mcp] goethe module has no `Tools` class")
    return mod.Tools


def _valve_dump(valves) -> dict:
    for meth in ("model_dump", "dict"):
        if hasattr(valves, meth):
            try:
                return getattr(valves, meth)()
            except Exception:
                pass
    return {}


def make_instance(Tools):
    """Instantiate Tools() and override valves from GOETHE_<FIELD> env vars."""
    inst = Tools()
    valves = getattr(inst, "valves", None)
    if valves is None:
        return inst
    fields = (
        getattr(type(valves), "model_fields", None)
        or getattr(type(valves), "__fields__", None)
        or {}
    )
    overrides = {}
    for fname in fields:
        env = os.environ.get("GOETHE_" + fname.upper())
        if env is not None:
            overrides[fname] = env
    if overrides:
        try:
            inst.valves = type(valves)(**{**_valve_dump(valves), **overrides})
            print(
                f"[goethe_mcp] applied valve overrides: {', '.join(sorted(overrides))}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"[goethe_mcp] valve override failed ({e}); using defaults", file=sys.stderr)
    return inst


def _annotation(p: inspect.Parameter):
    ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
    # Do NOT wrap in Optional[X] even when default=None.
    #
    # Optional[X] causes FastMCP to emit anyOf:[{type:X},{type:null}] in the
    # JSON schema, which llama-ui rejects — it terminates the session immediately
    # after ListToolsRequest if any tool has anyOf with null.
    #
    # Without Optional, FastMCP emits {type:X} for the field.  The parameter is
    # still optional from the schema's perspective (it won't appear in `required`
    # because it has a default).  Pydantic v2 with validate_default=False (the
    # default) never validates the None default value, so omitting the field from
    # the tool call works correctly.  The only scenario that would fail is if the
    # model sends an explicit null value for the param, which llama-ui does not do.
    return ann


def _flatten_anyof_null(obj):
    """Recursively flatten anyOf:[{...},{type:null}] → just the non-null schema.

    Pydantic needs Optional[X] internally so it accepts None when the model omits
    an optional param.  But llama-ui sees the JSON schema and rejects anyOf with
    null, closing the session right after ListToolsRequest.  This post-processes
    the exposed inputSchema only — Pydantic behaviour is unchanged.
    """
    if isinstance(obj, list):
        return [_flatten_anyof_null(i) for i in obj]
    if not isinstance(obj, dict):
        return obj
    if "anyOf" in obj:
        non_null = [_flatten_anyof_null(s) for s in obj["anyOf"]
                    if not (isinstance(s, dict) and s.get("type") == "null")]
        if len(non_null) == 1:
            # Collapse to the single non-null schema, preserve sibling keys
            merged = dict(non_null[0])
            for k, v in obj.items():
                if k != "anyOf":
                    merged.setdefault(k, _flatten_anyof_null(v))
            return merged
        obj = dict(obj)
        obj["anyOf"] = non_null
    return {k: _flatten_anyof_null(v) for k, v in obj.items()}


def _transform_tools_list_body(body: bytes) -> bytes:
    """Rewrite an SSE response body from a tools/list call, flattening anyOf-null
    in every tool's inputSchema.  Works on raw bytes so it is independent of
    FastMCP internals and version."""
    import json as _json
    try:
        text = body.decode("utf-8", errors="replace")
        out = []
        for line in text.splitlines(keepends=True):
            if not line.startswith("data:"):
                out.append(line)
                continue
            payload = line[5:].strip()
            if not payload:
                out.append(line)
                continue
            try:
                obj = _json.loads(payload)
            except _json.JSONDecodeError:
                out.append(line)
                continue
            tools = (obj.get("result") or {}).get("tools")
            if tools:
                for t in tools:
                    if "inputSchema" in t:
                        t["inputSchema"] = _flatten_anyof_null(t["inputSchema"])
            out.append("data: " + _json.dumps(obj) + "\n")
        return "".join(out).encode("utf-8")
    except Exception:
        return body  # never corrupt the stream


class _ToolSchemaFixer:
    """Transparent ASGI passthrough. Previously buffered SSE responses to strip
    anyOf-null schemas, but that approach deadlocked on streaming responses.
    anyOf elimination is now handled at source in _annotation(). Kept as a
    no-op wrapper in case future schema patching is needed here."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


# --- Episode journaling (TRAUM Thread 1, Prompt 1.3) -----------------------
# Schema and redaction rules are fixed by docs/dreaming/DESIGN.md — this is the
# implementation of that design, not a new design. Keep them in sync if either
# changes.

EPISODE_MAX_RESULT_CHARS = 2000  # the 2026-07-06 token-bomb lesson: cap at write time

# Tools whose entire call (args AND result) is inherently secret material —
# blanket-redacted rather than pattern-matched, since pattern-matching could
# miss a secret that happens not to look like a KEY/TOKEN/SECRET shape.
_SENSITIVE_TOOLS = {"get_vault_secret", "set_vault_secret", "vault_unlock", "list_vault_items"}

# Valve field names ending in these words are treated as secret-valued for
# redaction purposes (DESIGN.md §4 rules 2 + 4) — covers PFSENSE_API_KEY and
# any future *_KEY/*_TOKEN/*_SECRET/*_PASSWORD/*_API_KEY valve automatically,
# by naming convention rather than a hand-maintained list. (HERMES_API_KEY is
# decommissioned and intentionally not named here — this catch-all covers its
# replacement, if any, without needing an edit.)
_SECRET_FIELD_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)

_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+")
_TIMEOUT_RE = re.compile(r"\[TIMEOUT\]|timed out", re.IGNORECASE)
# Last-line-of-defense sweep for high-confidence secret shapes that slip past
# the valve-value and Bearer-token rules (DESIGN.md §4 rule 5). Matches any
# identifier CONTAINING key/token/secret/password (not just starting with it —
# aws_secret_access_key=... and PFSENSE_API_KEY=... both need to match) followed
# by an assignment and a long opaque blob.
_PATTERN_SECRET_RE = re.compile(
    r"(?i)([\w]*(?:key|token|secret|password)[\w]*)([\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9\-_./+]{12,}"
)

_fallback_session_id_cache = None

# --- Size hygiene (TRAUM Thread 1, Prompt 1.4 — write-time half) -----------
# Rotation (gzip old day-dirs) and the manifest.db build are a periodic batch
# job — see tools/episode_index.py. This is the other half: refuse to keep
# writing into a day-dir that's already blown past the cap, so one runaway day
# can't fill the disk between maintenance runs.
_DAY_CAP_BYTES = int(os.environ.get("GOETHE_EPISODE_DAY_CAP_MB", "500")) * 1024 * 1024
_DAY_SIZE_CACHE_TTL = 30.0  # seconds — bounds scandir overhead under call bursts
_day_size_cache = {}  # day_dir path -> (checked_at_monotonic, size_bytes)


def _day_dir_size(day_dir: str) -> int:
    """Total bytes of files directly under day_dir, cached briefly."""
    now = time.monotonic()
    cached = _day_size_cache.get(day_dir)
    if cached is not None and (now - cached[0]) < _DAY_SIZE_CACHE_TTL:
        return cached[1]
    total = 0
    try:
        with os.scandir(day_dir) as it:
            for entry in it:
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except OSError:
                    continue
    except OSError:
        total = 0
    _day_size_cache[day_dir] = (now, total)
    return total


def _note_bytes_written(day_dir: str, n: int) -> None:
    """Nudge the cached day-dir size forward after a successful write, instead
    of invalidating it — keeps the cap check cheap even under sustained load."""
    cached = _day_size_cache.get(day_dir)
    if cached is not None:
        _day_size_cache[day_dir] = (cached[0], cached[1] + n)


def _episode_dir() -> str:
    """Root directory for episode journaling — the EPISODE_DIR valve. Re-read
    from the environment on every call (not cached) so tests can point it at a
    tmp dir via GOETHE_EPISODE_DIR without needing to thread state through
    register(). Empty string disables journaling entirely."""
    return os.environ.get("GOETHE_EPISODE_DIR", "/opt/local-se/episodes")


def _iso_now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="microseconds")


def _fallback_session_id() -> str:
    """gateway-PID + first-call timestamp, memoized for the life of this process.
    Used when real MCP connection identity isn't available (see _mcp_session_id)."""
    global _fallback_session_id_cache
    if _fallback_session_id_cache is None:
        _fallback_session_id_cache = f"gw-{os.getpid()}-{int(time.time())}"
    return _fallback_session_id_cache


def _mcp_session_id() -> typing.Optional[str]:
    """Best-effort REAL per-connection identity, read from the SDK's own
    request-context contextvar. This requires no changes to the exposed tool
    schema (unlike adding a `ctx: Context` parameter, which would touch the
    same fragile anyOf-null schema pipeline _annotation()/_flatten_anyof_null()
    exist to work around) — it just reads ambient state the low-level Server
    already sets around every request via request_ctx.set() before dispatch.

    id(session) is stable for the life of one MCP connection (the ServerSession
    object persists for the connection's duration) but is only process-unique,
    so it's paired with the PID for safety. Returns None — triggering the
    _fallback_session_id() fallback — when unavailable: stdio transport has no
    per-connection session concept, and older/newer SDK versions may not expose
    this the same way.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx

        session = getattr(request_ctx.get(), "session", None)
        if session is not None:
            return f"sess-{os.getpid()}-{id(session):x}"
    except Exception:
        pass
    return None


def _session_id() -> str:
    return _mcp_session_id() or _fallback_session_id()


def _secret_values(inst) -> set:
    """Current secret-looking valve values on a Tools instance, for value-match
    redaction. Computed once per register() call (valves don't change mid-run)
    and reused across every wrapper closure created in that call."""
    values = set()
    valves = getattr(inst, "valves", None)
    if valves is None:
        return values
    for fname, fval in _valve_dump(valves).items():
        if isinstance(fval, str) and len(fval) >= 6 and _SECRET_FIELD_RE.search(fname):
            values.add(fval)
    return values


def _redact_text(text: str, secret_values: set) -> str:
    if not text:
        return text
    for val in secret_values:
        if val in text:
            text = text.replace(val, "[REDACTED:valve-secret]")
    text = _BEARER_RE.sub("[REDACTED:bearer-token]", text)
    text = _PATTERN_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:pattern-match]", text)
    try:
        from redact import redact_sensitive_text  # shared sweep: 37 vendor prefixes, JWTs, URL query params (2026-07-17)
        text = redact_sensitive_text(text)
    except Exception:
        pass  # DESIGN.md: journaling failures must never break the tool call
    return text


def _redact_args(tool_name: str, kwargs: dict, secret_values: set) -> dict:
    if tool_name in _SENSITIVE_TOOLS:
        # Whole-call redaction: every arg to a vault-secret tool either IS the
        # secret or identifies which secret to fetch/set — DESIGN.md §4 rule 1.
        return {k: "[REDACTED:vault-tool-arg]" for k in kwargs}
    out = {}
    for k, v in kwargs.items():
        if isinstance(v, str):
            out[k] = _redact_text(v, secret_values)
        else:
            try:
                json.dumps(v)
                out[k] = v  # already JSON-safe, structure preserved for the dreamer
            except TypeError:
                out[k] = _redact_text(str(v), secret_values)
    return out


def _classify_exit(result, exc) -> str:
    """Heuristic exit_class classification. goethe.py Tools methods don't carry
    a structured status field — they signal failure/denial via free-text string
    conventions ("BLOCKED: ...", "[TIMEOUT] ...", "ERROR: ...") that are already
    consistent across the codebase, so we classify on those rather than
    inventing a second status channel goethe.py methods would need to adopt."""
    if exc is not None:
        return "error"
    text = result if isinstance(result, str) else ("" if result is None else str(result))
    if text.startswith("BLOCKED:"):
        return "denied"
    if _TIMEOUT_RE.search(text):
        return "timeout"
    if text.startswith(("ERROR", "[SSH FAILURE]", "[SCP FAILED]")):
        return "error"
    return "ok"


def _journal(tool_name: str, kwargs: dict, result, exc, secret_values: set) -> None:
    """Append one episode JSONL line per docs/dreaming/DESIGN.md's schema.
    Called from a `finally` block so it fires exactly once per tool call
    regardless of outcome. Allowed to raise — the caller (_safe_journal) is
    responsible for making sure that never reaches the tool call."""
    ep_dir = _episode_dir()
    if not ep_dir:
        return  # GOETHE_EPISODE_DIR="" — journaling disabled

    session_id = _session_id()
    day = datetime.date.today().isoformat()
    day_dir = os.path.join(ep_dir, day)
    path = os.path.join(day_dir, f"{session_id}.jsonl")

    if os.path.isdir(day_dir) and _day_dir_size(day_dir) >= _DAY_CAP_BYTES:
        print(
            f"[goethe_mcp] WARNING: episode day-dir {day_dir} has reached the "
            f"{_DAY_CAP_BYTES // (1024 * 1024)}MB cap — REFUSING to journal this "
            f"call (tool={tool_name}). The tool call itself is unaffected. Run "
            "tools/episode_index.py to rotate old sessions, or raise "
            "GOETHE_EPISODE_DAY_CAP_MB.",
            file=sys.stderr,
        )
        return

    os.makedirs(day_dir, exist_ok=True)

    exit_class = _classify_exit(result, exc)
    if tool_name in _SENSITIVE_TOOLS:
        # DESIGN.md §4 rule 1: every arg to a vault-secret tool is blanket-
        # redacted because it either IS the secret or identifies which one to
        # fetch/set — but the RESULT of get_vault_secret is even more clearly
        # secret: it's the tool's entire purpose to return the value. Without
        # this, a caught RuntimeError could still leak it via the exception
        # message path below, or a dict/JSON result could leak it via the
        # json.dumps path — blanket-redact before any of those branches run,
        # not just the plain-string case.
        result_text = "[REDACTED:vault-tool-result]"
    elif exc is not None:
        result_text = f"{type(exc).__name__}: {exc}"
    elif isinstance(result, str):
        result_text = result
    else:
        try:
            result_text = json.dumps(result, default=str)
        except Exception:
            result_text = str(result)

    result_text = _redact_text(result_text, secret_values)
    if len(result_text) > EPISODE_MAX_RESULT_CHARS:
        result_text = result_text[:EPISODE_MAX_RESULT_CHARS] + "…[truncated]"

    line = {
        "ts": _iso_now(),
        "session_id": session_id,
        "tool": tool_name,
        "args_redacted": _redact_args(tool_name, kwargs, secret_values),
        "result_truncated": result_text,
        "exit_class": exit_class,
    }
    payload = json.dumps(line, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(payload)
    _note_bytes_written(day_dir, len(payload.encode("utf-8")))


def _safe_journal(tool_name: str, kwargs: dict, result, exc, secret_values: set) -> None:
    """Journal one episode line; NEVER let a journaling failure affect the
    caller. This is the only entry point the register() wrappers call."""
    try:
        _journal(tool_name, kwargs, result, exc, secret_values)
    except Exception as e:
        print(f"[goethe_mcp] episode journal failed (tool={tool_name}): {e}", file=sys.stderr)


def register(mcp, inst, seen=None) -> list:
    """Wrap each model-callable Tools method as an MCP tool. Returns names exposed.
    `seen` (a set) dedupes across multiple modules — a name already registered by an
    earlier module is skipped so the first module wins on a collision."""
    if seen is None:
        seen = set()
    exposed_names = []
    secret_values = _secret_values(inst)  # for episode-journal redaction, computed once
    for name in sorted(dir(inst)):
        if name.startswith("_") or name in SKIP_TOOLS or name in seen:
            continue
        member = getattr(inst, name)
        if not callable(member) or inspect.isclass(member):
            continue
        try:
            sig = inspect.signature(member)
        except (TypeError, ValueError):
            continue

        params = []
        for pname, p in sig.parameters.items():
            if pname in INJECTED:
                continue
            if p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
                continue
            params.append(p.replace(annotation=_annotation(p)))

        is_async = inspect.iscoroutinefunction(member)
        if is_async:
            async def wrapper(__m=member, __tool_name=name, **kwargs):
                result, exc = None, None
                try:
                    result = await __m(**kwargs)
                    return result
                except BaseException as e:
                    exc = e
                    raise
                finally:
                    _safe_journal(__tool_name, kwargs, result, exc, secret_values)
        else:
            # Run sync tools in a thread so they don't block the uvicorn event loop.
            # Without this, a slow execute_command stalls ALL pending requests and
            # prevents SSE keepalives from being sent, causing clients to see hangs.
            async def wrapper(__m=member, __tool_name=name, **kwargs):
                import asyncio
                result, exc = None, None
                try:
                    result = await asyncio.to_thread(__m, **kwargs)
                    return result
                except BaseException as e:
                    exc = e
                    raise
                finally:
                    _safe_journal(__tool_name, kwargs, result, exc, secret_values)

        wrapper.__name__ = name
        wrapper.__doc__ = (member.__doc__ or name).strip()
        wrapper.__signature__ = sig.replace(parameters=params)
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        wrapper.__annotations__["return"] = str

        _doc = wrapper.__doc__
        if len(_doc) > _TOOL_DESC_MAX:
            # Loud, always. The v0.4.7 incident was expensive precisely because
            # the drop was silent: the model violated a rule it had never been
            # shown, and nothing in the logs said so.
            print(f"[goethe_mcp] WARNING: {name} description truncated "
                  f"{len(_doc)} -> {_TOOL_DESC_MAX} chars "
                  f"({len(_doc) - _TOOL_DESC_MAX} dropped). Front-load its "
                  f"contract or raise GOETHE_MCP_TOOL_DESC_MAX.",
                  file=sys.stderr)
        mcp.add_tool(wrapper, name=name, description=_doc[:_TOOL_DESC_MAX])
        seen.add(name)
        exposed_names.append(name)
    return exposed_names


def build_http_app(mcp, token: str, cors_origin: str):
    """Wrap FastMCP's streamable-HTTP ASGI app with CORS + optional bearer-token auth.

    Wraps the FastMCP ASGI callable directly (no Starlette routing) so paths are
    never mangled.  Starlette's Mount("/", ...) strips the leading "/" before
    forwarding, turning "/mcp" → "mcp" and causing 404s.  Direct ASGI wrapping
    avoids that entirely and guarantees CORSMiddleware intercepts OPTIONS before
    the inner app sees the request.

    Stack (outermost → innermost):
      CORSMiddleware → _TokenGuard (if token set) → _ToolSchemaFixer (passthrough) → FastMCP ASGI app
    """
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import Response

    inner = mcp.streamable_http_app()
    origins = [cors_origin] if (cors_origin and cors_origin != "*") else ["*"]

    # Innermost: schema fixer rewrites tools/list SSE responses at the wire level
    # so anyOf-null never reaches the client regardless of FastMCP version.
    app = _ToolSchemaFixer(inner)

    if token:
        _bearer = f"Bearer {token}"

        class _TokenGuard:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http" and scope.get("method") != "OPTIONS":
                    headers = dict(scope.get("headers", []))
                    auth = headers.get(b"authorization", b"").decode().strip()
                    # Accept "Bearer <token>" or raw "<token>" — clients differ
                    received = auth[7:] if auth.lower().startswith("bearer ") else auth
                    if received != token and auth != _bearer:
                        resp = Response(
                            '{"error":"unauthorized"}',
                            status_code=401,
                            media_type="application/json",
                        )
                        await resp(scope, receive, send)
                        return
                await self.app(scope, receive, send)

        app = _TokenGuard(app)

    # Goethe Console (v1.12.0) — /ui + /api/ui/*. Mounted OUTSIDE _TokenGuard
    # so the static page is browser-loadable; the router token-gates /api/ui/*
    # itself. Fail-safe: any load error leaves the MCP surface untouched.
    if os.environ.get("GOETHE_UI", "on").lower() not in ("off", "0", ""):
        try:
            _ui_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "goethe_ui.py")
            _ui_spec = importlib.util.spec_from_file_location("goethe_ui", _ui_path)
            _ui_mod = importlib.util.module_from_spec(_ui_spec)
            _ui_spec.loader.exec_module(_ui_mod)
            app = _ui_mod.UIRouter(app, token=token)
            print(f"[goethe_mcp] Goethe Console mounted at /ui "
                  f"(goethe_ui v{_ui_mod.__version__})", file=sys.stderr)
        except Exception as e:
            print(f"[goethe_mcp] WARNING: Goethe Console disabled ({e}) — "
                  "MCP surface unaffected", file=sys.stderr)

    # CORSMiddleware — intercepts OPTIONS before token check or routing.
    # DELETE is required: llama-ui sends DELETE /mcp?session_id=... to terminate
    # sessions, and browsers preflight DELETE with OPTIONS first.
    app = CORSMiddleware(
        app,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    return app


def _free_port(port: int) -> None:
    """Kill any process holding *port* and wait up to 5 s for the socket to close.

    Safe to call even when nothing is listening — errors are silently ignored.
    """
    import subprocess
    import time

    def _port_in_use() -> bool:
        # List all TCP listeners and check for our port — no filter args (avoids
        # ss filter syntax differences across distros).
        r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        return any(f":{port} " in line or f":{port}\n" in line
                   for line in r.stdout.splitlines())

    # fuser is the most direct: finds and kills by port, works even without PID lookup
    r = subprocess.run(["which", "fuser"], capture_output=True)
    if r.returncode == 0:
        subprocess.run(["fuser", "-k", "-KILL", f"{port}/tcp"], capture_output=True)
    else:
        # Fallback: ss to find PID, then SIGKILL
        r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        import re
        for line in r.stdout.splitlines():
            if f":{port}" in line:
                m = re.search(r'pid=(\d+)', line)
                if m:
                    try:
                        import os as _os, signal as _sig
                        _os.kill(int(m.group(1)), _sig.SIGKILL)
                    except Exception:
                        pass

    # Mandatory pause after SIGKILL for the OS to reclaim the socket, then poll
    time.sleep(0.3)
    for _ in range(10):
        if not _port_in_use():
            return
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser(description="Serve LSE Goethe as an MCP server.")
    ap.add_argument("--goethe", default=os.environ.get("GOETHE_PATH", ""),
                    help="path to goethe.py (or set GOETHE_PATH)")
    ap.add_argument("--transport", choices=["stdio", "http"],
                    default=os.environ.get("GOETHE_MCP_TRANSPORT", "stdio"))
    ap.add_argument("--host", default=os.environ.get("GOETHE_MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("GOETHE_MCP_PORT", "9700")))
    ap.add_argument("--cors-origin",
                    default=os.environ.get("GOETHE_MCP_CORS_ORIGIN", "http://127.0.0.1:8080"),
                    help="allowed browser origin for direct-CORS (the llama-ui URL)")
    ap.add_argument("--also", action="append", default=[], metavar="PATH",
                    help="additional LSE Tools file(s) to expose alongside goethe "
                    "(repeatable). e.g. --also tools/vaultwarden_tools_v1.3.0.py")
    ap.add_argument("--list", action="store_true",
                    help="print the tools that would be exposed, then exit")
    args = ap.parse_args()

    if not args.goethe:
        raise SystemExit("[goethe_mcp] provide --goethe /path/to/goethe.py (or GOETHE_PATH)")

    token = os.environ.get("GOETHE_MCP_TOKEN", "").strip()

    from mcp.server.fastmcp import FastMCP

    goethe_ver = _goethe_version(args.goethe)
    mcp = FastMCP("LSE Goethe", host=args.host, port=args.port)
    mcp._mcp_server.version = goethe_ver  # version lives on the low-level Server
    seen: set = set()
    names = register(mcp, make_instance(load_goethe(args.goethe)), seen)
    print(f"[goethe_mcp] {len(names)} from {os.path.basename(args.goethe)}: "
          f"{', '.join(names)}", file=sys.stderr)
    for extra in args.also:
        try:
            ex = register(mcp, make_instance(load_goethe(extra)), seen)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[goethe_mcp] WARNING: failed to load --also {extra}: {e}", file=sys.stderr)
            continue
        names += ex
        print(f"[goethe_mcp] +{len(ex)} from {os.path.basename(extra)}: "
              f"{', '.join(ex)}", file=sys.stderr)
    print(f"[goethe_mcp] exposed {len(names)} tools total (v{__version__})", file=sys.stderr)

    if args.list:
        for n in names:
            print(n)
        return

    if args.transport == "stdio":
        if token:
            print("[goethe_mcp] note: GOETHE_MCP_TOKEN ignored for stdio (no network surface)",
                  file=sys.stderr)
        mcp.run(transport="stdio")
        return

    # HTTP
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[goethe_mcp] WARNING: binding {args.host} exposes a SHELL EXECUTOR to the "
              "network. Use 127.0.0.1.", file=sys.stderr)
    if not token:
        print("[goethe_mcp] WARNING: no GOETHE_MCP_TOKEN set - HTTP endpoint has NO auth "
              "(relying on localhost binding only).", file=sys.stderr)
    import uvicorn

    # Free the port before binding — self-contained, no external script needed.
    # uvicorn.run() handles SIGTERM/SIGINT gracefully by default (drains connections,
    # closes socket) so no custom signal handler is required.
    _free_port(args.port)

    app = build_http_app(mcp, token, args.cors_origin)
    print(f"[goethe_mcp] serving streamable-HTTP on http://{args.host}:{args.port}/mcp "
          f"(token={'on' if token else 'OFF'}, cors_origin={args.cors_origin})", file=sys.stderr)

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        print("[goethe_mcp] port released, exiting.", file=sys.stderr)


if __name__ == "__main__":
    main()
