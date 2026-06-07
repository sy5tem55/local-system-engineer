#!/usr/bin/env bash
# run_netobs.sh — Start all network observability services
#
# Services managed:
#   discovery_engine.py   --loop (writes snapshot.json every INTERVAL seconds)
#   ws_server.py          (pushes snapshot to topology map browsers on :8765)
#   prometheus_exporter.py (serves /metrics on :9120 for Prometheus scraping)
#
# Usage:
#   ./run_netobs.sh            # start all three, logs to logs/
#   ./run_netobs.sh stop       # kill all three
#   ./run_netobs.sh status     # show running PIDs
#   ./run_netobs.sh tail       # tail all logs
#
# Env vars (set before running, or export in ~/.bashrc):
#   PFSENSE_API_KEY   — required for probe_dhcp.py
#   ASUS_PASS         — required for probe_wifi.py (ASUS GT-BE19000)
#   NETOBS_INTERVAL   — discovery loop interval in seconds (default: 60)
#
# Logs: net-discovery/logs/{engine,ws,exporter}.log
# PIDs: net-discovery/logs/{engine,ws,exporter}.pid

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON="${PYTHON:-python3}"
INTERVAL="${NETOBS_INTERVAL:-60}"

# ── Helpers ─────────────────────────────────────────────────────────────────
die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[netobs] $*"; }

_pid_file()  { echo "$LOG_DIR/$1.pid"; }
_log_file()  { echo "$LOG_DIR/$1.log"; }

_running() {
    local name=$1
    local pidfile; pidfile=$(_pid_file "$name")
    [[ -f "$pidfile" ]] || return 1
    local pid; pid=$(cat "$pidfile")
    kill -0 "$pid" 2>/dev/null
}

_start_service() {
    local name=$1
    shift
    local cmd=("$@")
    local pidfile; pidfile=$(_pid_file "$name")
    local logfile; logfile=$(_log_file "$name")

    if _running "$name"; then
        info "$name already running (PID $(cat "$pidfile"))"
        return
    fi

    mkdir -p "$LOG_DIR"
    nohup "${cmd[@]}" >> "$logfile" 2>&1 &
    echo $! > "$pidfile"
    info "$name started (PID $!) → $logfile"
}

_stop_service() {
    local name=$1
    local pidfile; pidfile=$(_pid_file "$name")
    if ! _running "$name"; then
        info "$name not running"
        rm -f "$pidfile"
        return
    fi
    local pid; pid=$(cat "$pidfile")
    kill "$pid" && info "$name stopped (PID $pid)" || info "$name kill failed"
    rm -f "$pidfile"
}

# ── Guards ───────────────────────────────────────────────────────────────────
_check_env() {
    if [[ -z "${PFSENSE_API_KEY:-}" ]]; then
        die "PFSENSE_API_KEY is not set. Export it before running:\n  export PFSENSE_API_KEY=<your_key>"
    fi

    # websockets check (needed by ws_server.py)
    if ! "$PYTHON" -c "import websockets" 2>/dev/null; then
        echo "WARNING: 'websockets' library not installed."
        echo "  Check:   pip show websockets"
        echo "  Install: pip install websockets --break-system-packages"
        echo "  ws_server.py will fail without it."
    fi
}

# ── Commands ─────────────────────────────────────────────────────────────────
cmd_start() {
    _check_env
    cd "$SCRIPT_DIR"

    _start_service "engine" \
        "$PYTHON" discovery_engine.py --loop --interval "$INTERVAL"

    _start_service "ws" \
        "$PYTHON" ws_server.py

    _start_service "exporter" \
        "$PYTHON" prometheus_exporter.py

    echo ""
    info "All services started. Check status with: $0 status"
    info "Topology map: http://localhost:8080/netobs/ (after nginx container is up)"
    info "Direct serve: python3 -m http.server 8080 (from net-discovery/)"
    info "Prometheus:   http://localhost:9090 → target netobs at :9120"
}

cmd_stop() {
    _stop_service "engine"
    _stop_service "ws"
    _stop_service "exporter"
}

cmd_status() {
    for name in engine ws exporter; do
        local pidfile; pidfile=$(_pid_file "$name")
        if _running "$name"; then
            echo "  ✅ $name  PID=$(cat "$pidfile")"
        else
            echo "  ❌ $name  not running"
        fi
    done
}

cmd_tail() {
    local logs=()
    for name in engine ws exporter; do
        local logfile; logfile=$(_log_file "$name")
        [[ -f "$logfile" ]] && logs+=("$logfile")
    done
    if [[ ${#logs[@]} -eq 0 ]]; then
        die "No log files found in $LOG_DIR. Have you run '$0 start'?"
    fi
    tail -f "${logs[@]}"
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-start}" in
    start)  cmd_start  ;;
    stop)   cmd_stop   ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
    status) cmd_status ;;
    tail)   cmd_tail   ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|tail}"
        exit 1
        ;;
esac
