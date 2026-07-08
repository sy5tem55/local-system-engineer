#!/usr/bin/env bash
# start-goethe-stdio.sh — Goethe MCP over stdio for Claude Desktop / Cowork (Option 1)
# Added 2026-07-02.
#
# Transport: stdio — the MCP client (Claude Desktop) owns this process and speaks
# JSON-RPC over stdin/stdout. NO network surface: no port, no token, no CORS.
# Coexists with the HTTP instance on :9700 (llama-ui) — do NOT pkill it here.
#
# CRITICAL: stdout belongs to the MCP protocol. Never echo/print to stdout in this
# script — diagnostics go to stderr only.
#
# ZPT note: secrets come from ~/.lse/secrets today. When the USB/tmpfs Zero-Trust
# layout lands, only the `source` line below changes (→ /run/lse-secrets/env).

set -euo pipefail

LSE_DIR="$HOME/projects/local-system-engineer/tools"

if [[ -f "$HOME/.lse/secrets" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.lse/secrets"
else
  echo "[start-goethe-stdio] WARN: ~/.lse/secrets not found — vault tools will be degraded" >&2
fi

export BW_PASSWORD="${BW_PASSWORD:-}"

exec /home/sy5/owui/bin/python3 "$LSE_DIR/goethe_mcp.py" \
  --goethe "$LSE_DIR/goethe.py" \
  --also   "$LSE_DIR/vaultwarden_tools_v1.3.0.py" \
  --also   "$LSE_DIR/pfsense_tools_v1.0.0.py" \
  --also   "$LSE_DIR/net_discovery_tools_v1.0.0.py"
