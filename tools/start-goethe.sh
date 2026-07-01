#!/usr/bin/env bash
# start-goethe.sh — canonical startup for the Goethe MCP Gateway (v1.9.2)
# Usage: bash ~/projects/local-system-engineer/tools/start-goethe.sh
# Python: owui venv (/home/sy5/owui/bin/python3) is retained as the LSE MCP runtime.
#         The OpenWebUI application is retired; the venv name is a historical artifact.

set -euo pipefail

LSE_DIR="$HOME/projects/local-system-engineer/tools"

# SIGKILL the old instance for instant death (SIGTERM triggers slow graceful drain).
# _free_port() inside goethe_mcp.py does belt-and-suspenders cleanup after.
if pkill -9 -f goethe_mcp.py 2>/dev/null; then
  echo "[start-goethe] killed existing goethe_mcp.py process"
  sleep 0.5
fi

source ~/.lse/secrets

GOETHE_MCP_TOKEN=6e003f5c3862d8de12048439e94b96cf \
BW_PASSWORD="$BW_PASSWORD" \
  /home/sy5/owui/bin/python3 "$LSE_DIR/goethe_mcp.py" \
  --goethe "$LSE_DIR/goethe.py" \
  --also  "$LSE_DIR/vaultwarden_tools_v1.3.0.py" \
  --transport http \
  --port 9700 \
  --host 0.0.0.0 \
  --cors-origin '*' &

echo "[start-goethe] PID $! — listening on http://0.0.0.0:9700/mcp"
