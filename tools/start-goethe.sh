#!/usr/bin/env bash
# start-goethe.sh — canonical startup for the Goethe MCP Gateway (HTTP, LUCIFER)
# Usage: bash ~/projects/local-system-engineer/tools/start-goethe.sh
# Python: owui venv (/home/sy5/owui/bin/python3) is retained as the LSE MCP runtime.
#
# v2.1.4 — 2026-07-26: changed --host to 0.0.0.0 for Docker container access
#   (LibreChat container needs to reach Goethe via WSL2 IP 192.168.1.57:9700)
#
# v2.1.3 — corrections to the v2.1 proposal:
#   * ss checks use -H: without it ss prints a header even for a free port,
#     making "port free" impossible (Step 2 aborted every run) and
#     "is listening" vacuous (Step 4 passed even on crash).
#   * Positive process gate: verify zero gateway PROCESSES after kill and
#     exactly ONE after launch — port state alone proves neither.
#   * Pattern uses goethe_mcp[.]py so ad-hoc pgrep/pkill of this pattern
#     never self-matches a shell carrying the pattern in its cmdline.
#   * Real daemon PID: backgrounded setsid forks, so $! is the dead wrapper.
#     PID is read back post-bind and written to a pidfile — a SIGHUP-proof
#     daemon must stay findable. The GUI reads this pidfile for clean kills.
#   * Clean stale GUI child PID files before launch — prevents the GUI health
#     check from finding dead PIDs and falsely reporting the gateway as stopped.
set -euo pipefail

LSE_DIR="$HOME/projects/local-system-engineer/tools"
PAT='goethe_mcp[.]py.*--transport http'
PIDFILE=/tmp/goethe-gateway.pid
LOG=/tmp/goethe-gateway.log

source ~/.lse/secrets
: "${GOETHE_MCP_TOKEN:?GOETHE_MCP_TOKEN not set — add 'export GOETHE_MCP_TOKEN=<openssl rand -hex 16>' to ~/.lse/secrets}"

# ── Planner valves (added 2026-07-31) ───────────────────────────────────────
# The planner model pin and CLI timeout live in /opt/local-se/goethe-mcp.env.
# systemd reads that file via EnvironmentFile=, but this script (the GUI /
# manual launch path) did not — so PLANNER_ANTHROPIC_MODEL silently fell back
# to the code default claude-sonnet-5 instead of the pinned claude-opus-5, and
# nothing reported it. Verified inert on 2026-07-31: no GOETHE_PLANNER_* var
# was present in the environment of any running goethe_mcp.py process.
#
# ONLY GOETHE_PLANNER_* is imported. That same file also holds GOETHE_MCP_TOKEN
# and BW_PASSWORD, and its token DIFFERS from the one in ~/.lse/secrets
# (confirmed 2026-07-31). Sourcing it wholesale would swap the gateway token
# and break Console auth. Do not "simplify" this to a plain `. env-file`.
if [ -r /opt/local-se/goethe-mcp.env ]; then
  while IFS='=' read -r _k _v; do
    [ -n "${_k:-}" ] && export "$_k=$_v"
  done <<EOF
$(grep -E '^GOETHE_PLANNER_[A-Za-z_0-9]+=' /opt/local-se/goethe-mcp.env || true)
EOF
  unset _k _v
  echo "[start-goethe] planner valves: model=${GOETHE_PLANNER_ANTHROPIC_MODEL:-<code default>} timeout=${GOETHE_PLANNER_CLI_TIMEOUT_S:-<code default>}s"
fi

# ── Step 1: kill any existing HTTP gateway instances ────────────────────────
if pkill -9 -f "$PAT" 2>/dev/null; then
  echo "[start-goethe] killed existing HTTP gateway instance(s)"
fi

# ── Step 2: verify ZERO gateway processes remain (up to 5s) ─────────────────
for attempt in $(seq 1 10); do
  if ! pgrep -f "$PAT" >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 10 ]; then
    echo "[start-goethe] ERROR: gateway process(es) still alive after 5s — aborting"
    pgrep -af "$PAT" || true
    exit 1
  fi
  sleep 0.5
done

# ── Step 3: verify port 9700 is free (up to 5s) ─────────────────────────────
for attempt in $(seq 1 10); do
  if ! ss -tlnH sport = :9700 | grep -q .; then
    break
  fi
  if [ "$attempt" -eq 10 ]; then
    echo "[start-goethe] ERROR: port 9700 still occupied after 5s — aborting"
    ss -tlnpH sport = :9700 || true
    exit 1
  fi
  sleep 0.5
done

# ── Step 3.5: clean stale GUI child PID files ────────────────────────────────
rm -f /tmp/goethe-gui/Goethe_MCP-*-child.pid /tmp/goethe-gui/goethe_mcp-*-child.pid 2>/dev/null || true

# ── Step 4: launch detached and SIGHUP-proof ─────────────────────────────────
env GOETHE_MCP_TOKEN="$GOETHE_MCP_TOKEN" \
    BW_PASSWORD="${BW_PASSWORD:-}" \
    GOETHE_EMBED_MODEL="qwen3-embedding:0.6b" \
  setsid nohup /home/sy5/owui/bin/python3 "$LSE_DIR/goethe_mcp.py" \
  --goethe "$LSE_DIR/goethe.py" \
  --also  "$LSE_DIR/vaultwarden_tools_v1.3.0.py" \
  --also  "$LSE_DIR/pfsense_tools_v1.0.0.py" \
  --also  "$LSE_DIR/net_discovery_tools_v1.0.0.py" \
  --transport http \
  --port 9700 \
  --host 0.0.0.0 \
  --cors-origin '*' \
  </dev/null >"$LOG" 2>&1 &

# ── Step 5: verify the gateway is listening (up to 10s) ─────────────────────
for attempt in $(seq 1 20); do
  if ss -tlnH sport = :9700 | grep -q .; then
    break
  fi
  if [ "$attempt" -eq 20 ]; then
    echo "[start-goethe] ERROR: gateway did not bind port 9700"
    tail -20 "$LOG" 2>/dev/null || true
    exit 1
  fi
  sleep 0.5
done

# ── Step 6: verify EXACTLY ONE instance; record its real PID ────────────────
COUNT=$(pgrep -cf "$PAT" || true)
if [ "$COUNT" -ne 1 ]; then
  echo "[start-goethe] ERROR: expected exactly 1 gateway instance, found $COUNT — investigate"
  pgrep -af "$PAT" || true
  exit 1
fi
REAL_PID=$(pgrep -f "$PAT")
echo "$REAL_PID" > "$PIDFILE"

echo "[start-goethe] PID $REAL_PID — listening on http://0.0.0.0:9700/mcp"
echo "[start-goethe] log: $LOG   pidfile: $PIDFILE"
