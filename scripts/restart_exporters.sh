#!/usr/bin/env bash
# =============================================================================
# restart_exporters.sh — Restart all host-side Prometheus exporters
# =============================================================================
#
# Run this after every WSL2 restart. Docker containers (node-exporter,
# searxng-error-exporter) manage themselves via docker compose. This script
# handles the eight HOST-SIDE processes that WSL2 kills on restart:
#
#   Port  Job name               Script
#   ────  ─────────────────────  ──────────────────────────────────────────────
#   8766  (topology API)         net-discovery/echarts_topology.py
#   9120  netobs                 net-discovery/prometheus_exporter.py
#   9835  nvidia_gpu             /opt/local-se/nvidia-gpu-exporter.py  (*)
#   9836  llama-context-exporter /opt/local-se/llama-context-exporter.py  (*)
#   9838  download-speed         tools/download-speed-exporter.py
#   9839  llamacpp-slots         tools/llamacpp-slots-exporter.py
#   9840  llamacpp-reexporter    /opt/local-se/llamacpp-metrics-reexporter.py  (*)
#
#   (*) = installed to /opt/local-se — if missing, a warning is printed and
#         that exporter is skipped. Prometheus will show that target as "down"
#         until the exporter is reinstalled.
#
# Usage:
#   bash restart_exporters.sh          # start everything that isn't running
#   bash restart_exporters.sh --force  # kill and restart everything
#   bash restart_exporters.sh --status # show status only, no starts
#
# Logs: /tmp/lse-exporters/
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="/tmp/lse-exporters"
FORCE=false
STATUS_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --force)  FORCE=true ;;
        --status) STATUS_ONLY=true ;;
    esac
done

mkdir -p "$LOG_DIR"

# ── Dependencies ─────────────────────────────────────────────────────────────
# prometheus_client is required by netobs and other exporters.
# Install silently if missing — safe to re-run if already installed.
if ! python3 -c "import prometheus_client" 2>/dev/null; then
    echo "[exporters] Installing prometheus_client..."
    pip install prometheus_client==0.25.0 --break-system-packages --no-cache-dir -q
fi

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[exporters]${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail()  { echo -e "${RED}  ✗${NC} $*"; }

# ── Helpers ───────────────────────────────────────────────────────────────────
port_listening() {
    # Returns 0 (true) if something is already bound to the port
    ss -tlnp 2>/dev/null | grep -q ":${1} " || \
    ss -tlnp 2>/dev/null | grep -q ":${1}$"
}

start_bg() {
    # start_bg <name> <port> <logfile> <cmd...>
    local name=$1 port=$2 log=$3
    shift 3
    if port_listening "$port"; then
        if $FORCE; then
            warn "$name (port $port) already up — force-killing"
            fuser -k "${port}/tcp" 2>/dev/null || true
            sleep 1
        else
            ok "$name (port $port) already running — skip"
            return
        fi
    fi
    $STATUS_ONLY && { fail "$name (port $port) DOWN"; return; }
    nohup "$@" >> "$log" 2>&1 &
    sleep 1
    if port_listening "$port"; then
        ok "$name started on port $port  (log: $log)"
    else
        fail "$name failed to bind port $port — check $log"
    fi
}

start_optional() {
    # Like start_bg but warns and skips if script file does not exist
    local name=$1 port=$2 log=$3 script=$4
    shift 4
    if [[ ! -f "$script" ]]; then
        warn "$name — script not found: $script"
        warn "       Install it to /opt/local-se/ or rebuild — Prometheus target will stay down"
        return
    fi
    start_bg "$name" "$port" "$log" python3 "$script" "$@"
}

# =============================================================================
echo ""
echo "════════════════════════════════════════════════════════════"
echo " LSE Exporter Restart  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════"
echo ""

# ── 1. Topology API (port 8766) ───────────────────────────────────────────────
TOPOLOGY_SCRIPT="${PROJECT_DIR}/net-discovery/echarts_topology.py"
start_optional \
    "topology-api" 8766 "$LOG_DIR/topology.log" \
    "$TOPOLOGY_SCRIPT"

# ── 2. Netobs exporter (port 9120) ───────────────────────────────────────────
NETOBS_EXPORTER="${PROJECT_DIR}/net-discovery/prometheus_exporter.py"
start_optional \
    "netobs" 9120 "$LOG_DIR/netobs.log" \
    "$NETOBS_EXPORTER"

# ── 3. Download-speed exporter (port 9838) ───────────────────────────────────
DLSPEED_SCRIPT="${PROJECT_DIR}/tools/download-speed-exporter.py"
start_optional \
    "download-speed" 9838 "$LOG_DIR/download-speed.log" \
    "$DLSPEED_SCRIPT"

# ── 4. llamacpp-slots exporter (port 9839) ───────────────────────────────────
SLOTS_SCRIPT="${PROJECT_DIR}/tools/llamacpp-slots-exporter.py"
start_optional \
    "llamacpp-slots" 9839 "$LOG_DIR/llamacpp-slots.log" \
    "$SLOTS_SCRIPT"

# ── 5. llama-context-exporter (port 9836) ────────────────────────────────────
# This exporter was installed to /opt/local-se/ (outside the git repo).
# If it is missing, reinstall it from the Cowork session or copy from
# tools/lse-context-monitor-v1.3.0.py (OpenWebUI variant — different port).
CTX_SCRIPT="/opt/local-se/llama-context-exporter.py"
start_optional \
    "llama-context-exporter" 9836 "$LOG_DIR/context-exporter.log" \
    "$CTX_SCRIPT"

# ── 6. nvidia_gpu exporter (port 9835) ───────────────────────────────────────
# This exporter was installed to /opt/local-se/. It wraps nvidia-smi output
# as Prometheus gauges. If missing, check the LSE or reinstall.
NVIDIA_SCRIPT="/opt/local-se/nvidia-gpu-exporter.py"
start_optional \
    "nvidia-gpu" 9835 "$LOG_DIR/nvidia-gpu.log" \
    "$NVIDIA_SCRIPT"

# ── 7. llamacpp metrics re-exporter (port 9840) ─────────────────────────────
# Re-exposes the loopback-only llama-server (127.0.0.1:8080/metrics) on
# 0.0.0.0:9840 so the Docker bridge (172.17.0.1) can scrape it.
REEXPORTER_SCRIPT="/opt/local-se/llamacpp-metrics-reexporter.py"
start_optional \
    "llamacpp-reexporter" 9840 "$LOG_DIR/llamacpp-reexporter.log" \
    "$REEXPORTER_SCRIPT"

# =============================================================================
echo ""
info "Final port status:"
for port in 8766 9120 9835 9836 9838 9839 9840; do
    if port_listening "$port"; then
        ok "  :$port  UP"
    else
        fail "  :$port  DOWN"
    fi
done

echo ""
info "Verify in Prometheus: curl -s http://localhost:9090/api/v1/targets | python3 -c \\"
info "  \"import json,sys; [print(t['labels']['job'], t['health']) for t in json.load(sys.stdin)['data']['activeTargets']]\""
echo ""
