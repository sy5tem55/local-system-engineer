#!/usr/bin/env bash
# Start the WebSearch LB MCP server (streamable HTTP, 127.0.0.1:9703).
# Idempotent; sources websearch-lb.env (EXA_API_KEY); verifies /health.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${WEBSEARCH_LB_ENV_FILE:-$HERE/websearch-lb.env}"
LOG="${WEBSEARCH_LB_LOG:-/tmp/websearch-lb.log}"
PY="$HERE/.venv/bin/python"
HOST="${WEBSEARCH_LB_HOST:-127.0.0.1}"
PORT="${WEBSEARCH_LB_PORT:-9703}"

if [ -f "$ENV_FILE" ]; then
  set -a; source "$ENV_FILE"; set +a
  echo "[start-wblb] sourced $ENV_FILE"
else
  echo "[start-wblb] WARN: $ENV_FILE missing — EXA backend will be unavailable"
fi

if pgrep -f 'websearch_lb_[s]erver.py' >/dev/null 2>&1; then
  echo "[start-wblb] already running: pid(s) $(pgrep -f 'websearch_lb_[s]erver.py' | tr '\n' ' ')"
  exit 0
fi

mkdir -p /tmp/lse/websearch-lb
WEBSEARCH_LB_HOST="$HOST" WEBSEARCH_LB_PORT="$PORT" nohup "$PY" "$HERE/websearch_lb_server.py" >> "$LOG" 2>&1 &
echo "[start-wblb] started pid $!"

for i in $(seq 1 15); do
  if curl -sf -m 2 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "[start-wblb] healthy at http://$HOST:$PORT/health"
    exit 0
  fi
  sleep 1
done
echo "[start-wblb] FAILED health check — log tail:"
tail -20 "$LOG"
exit 1
