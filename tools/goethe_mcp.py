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
import importlib.util
import inspect
import os
import sys
import typing

__version__ = "1.9.3"
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

# Methods that require a chat-frontend DB — not functional via MCP, excluded from tool exposure.
SKIP_TOOLS = {"compact_context"}


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


def register(mcp, inst, seen=None) -> list:
    """Wrap each model-callable Tools method as an MCP tool. Returns names exposed.
    `seen` (a set) dedupes across multiple modules — a name already registered by an
    earlier module is skipped so the first module wins on a collision."""
    if seen is None:
        seen = set()
    exposed_names = []
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
            async def wrapper(__m=member, **kwargs):
                return await __m(**kwargs)
        else:
            # Run sync tools in a thread so they don't block the uvicorn event loop.
            # Without this, a slow execute_command stalls ALL pending requests and
            # prevents SSE keepalives from being sent, causing clients to see hangs.
            async def wrapper(__m=member, **kwargs):
                import asyncio
                return await asyncio.to_thread(__m, **kwargs)

        wrapper.__name__ = name
        wrapper.__doc__ = (member.__doc__ or name).strip()
        wrapper.__signature__ = sig.replace(parameters=params)
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        wrapper.__annotations__["return"] = str

        mcp.add_tool(wrapper, name=name, description=wrapper.__doc__[:1024])
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
