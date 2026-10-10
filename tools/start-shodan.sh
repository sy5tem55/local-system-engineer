#!/usr/bin/env bash
# Start the Shodan MCP server (KEYLESS WEB MODE — streamable-HTTP on
# 127.0.0.1:9702 by default).
#
# Usage:
#   ./start-shodan.sh
#
# Behaviour:
#   - sources tools/shodan-mcp.env ONLY if present (optional env: valves like
#     SHODAN_MCP_HOST/PORT/TOKEN). No API key is needed — the backend scrapes
#     www.shodan.io keyless, so a missing or keyless env file is fine.
#   - idempotent: exits 0 if a server is already running
#   - backs up the previous log to /opt/local-se/bkp/ before overwriting
#   - verifies /health before declaring success; exits 1 with log tail on failure
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SHODAN_ENV_FILE:-$HERE/shodan-mcp.env}"
LOG="${SHODAN_MCP_LOG:-/tmp/shodan_mcp.log}"
PY="${PYTHON:-/home/sy5/miniforge3/bin/python}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  echo "[start-shodan] sourced $ENV_FILE (optional env — keyless web mode needs no key)"
else
  echo "[start-shodan] note: $ENV_FILE not found — starting keyless web mode without env file"
fi

HOST="${SHODAN_MCP_HOST:-127.0.0.1}"
PORT="${SHODAN_MCP_PORT:-9702}"

# Bracket pattern: matches the python process, never this script's own cmdline.
if pgrep -f 'shodan_mcp_[s]erver.py' >/dev/null 2>&1; then
  echo "[start-shodan] already running: pid(s) $(pgrep -f 'shodan_mcp_[s]erver.py' | tr '\n' ' ')"
  exit 0
fi

mkdir -p "$(dirname "$LOG")"
if [ -f "$LOG" ]; then
  mkdir -p /opt/local-se/bkp 2>/dev/null || true
  cp "$LOG" "/opt/local-se/bkp/shodan_mcp.log_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
fi

nohup "$PY" "$HERE/shodan_mcp_server.py" > "$LOG" 2>&1 &
sleep 2

if curl -sf "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
  echo "[start-shodan] up (keyless web mode): http://${HOST}:${PORT}/mcp (pid $(pgrep -f 'shodan_mcp_[s]erver.py' | head -1), log $LOG)"
else
  echo "[start-shodan] FAILED to start — last log lines:" >&2
  tail -10 "$LOG" >&2
  exit 1
fi
