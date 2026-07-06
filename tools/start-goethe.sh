#!/usr/bin/env bash
# start-goethe.sh — canonical startup for the Goethe MCP Gateway (HTTP, LUCIFER)
# Usage: bash ~/projects/local-system-engineer/tools/start-goethe.sh
# Python: owui venv (/home/sy5/owui/bin/python3) is retained as the LSE MCP runtime.
#         The OpenWebUI application is retired; the venv name is a historical artifact.
#
# v2.0 (2026-07-02) — P0-2 hardening:
#   * TOKEN: no longer hardcoded. Set in ~/.lse/secrets:
#       export GOETHE_MCP_TOKEN=$(openssl rand -hex 16)
#     (the old 6e003f5c… token is in git history — treat as public, rotate)
#   * BIND: 127.0.0.1 — verified 2026-07-02 via `ss -tnp`: the only client of
#     LUCIFER:9700 is the local llama-ui browser. node3090 runs its OWN gateway.
#   * CORS: restricted to the local llama-ui origin (was '*').
#   * PKILL: matches ONLY the --transport http instance. stdio instances
#     (Claude Desktop / Cowork bridge via start-goethe-stdio.sh) must SURVIVE
#     gateway restarts — a bare 'pkill -f goethe_mcp.py' would kill them.

set -euo pipefail

LSE_DIR="$HOME/projects/local-system-engineer/tools"

source ~/.lse/secrets
: "${GOETHE_MCP_TOKEN:?GOETHE_MCP_TOKEN not set — add 'export GOETHE_MCP_TOKEN=<openssl rand -hex 16>' to ~/.lse/secrets}"

# SIGKILL the old HTTP instance for instant death (SIGTERM triggers slow graceful drain).
# _free_port() inside goethe_mcp.py does belt-and-suspenders cleanup after.
if pkill -9 -f 'goethe_mcp.py.*--transport http' 2>/dev/null; then
  echo "[start-goethe] killed existing HTTP gateway instance"
  sleep 0.5
fi

GOETHE_MCP_TOKEN="$GOETHE_MCP_TOKEN" \
BW_PASSWORD="${BW_PASSWORD:-}" \
  /home/sy5/owui/bin/python3 "$LSE_DIR/goethe_mcp.py" \
  --goethe "$LSE_DIR/goethe.py" \
  --also  "$LSE_DIR/vaultwarden_tools_v1.3.0.py" \
  --also  "$LSE_DIR/pfsense_tools_v1.0.0.py" \
  --transport http \
  --port 9700 \
  --host 127.0.0.1 \
  --cors-origin 'http://127.0.0.1:8080' &

echo "[start-goethe] PID $! — listening on http://127.0.0.1:9700/mcp"
