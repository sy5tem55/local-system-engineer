#!/usr/bin/env bash
# node3090_start_llm.sh
# Start llama-server on node3090 via SSH and wait until it's ready.
# Safe to call when the server is already running — exits 0 immediately.
#
# Usage:
#   ./scripts/node3090_start_llm.sh          # start
#   ./scripts/node3090_start_llm.sh stop     # stop
#   ./scripts/node3090_start_llm.sh status   # check
#
# ── node3090 facts (from LSE-ARCHITECTURE.md _NODE_REGISTRY) ─────────────────
# FQDN required — "node3090" alone fails (DHCP option 119 pending)
NODE_HOST="node3090.home.arpa"   # FQDN required for SSH
NODE_IP="192.168.5.41"           # Use IP for HTTP — WSL2 TCP to FQDN fails despite DNS resolving
NODE_USER="lse-admin"
NODE_PORT=22
LLM_PORT=8080

# Exact model path on node3090 (/opt/models is a REAL directory since 2026-06-11 P21 — no symlinks; .gguf files chattr +i)
MODEL_PATH="/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf"

# llama-server binary — confirm path with: ssh lse-admin@node3090.home.arpa which llama-server
LLAMA_BIN="llama-server"   # assumed on PATH after build; adjust if needed

# Launch flags — mirrored from agent_profile in _NODE_REGISTRY
NGL=129         # gpu_layers: full model fits in 3090's 24 GB at Q4_K_M
CTX=96000       # ctx_size
THREADS=7       # threads + threads_batch
# ─────────────────────────────────────────────────────────────────────────────

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=5 -p ${NODE_PORT}"
REMOTE_LOG="/tmp/llama-server.log"

ssh_cmd() {
    ssh ${SSH_OPTS} "${NODE_USER}@${NODE_HOST}" "$@"
}

is_running() {
    # Check if llama-server is listening on the expected port (local check via SSH)
    ssh_cmd "ss -tlnp 2>/dev/null | grep -q ':${LLM_PORT}'" 2>/dev/null
}

wait_ready() {
    local deadline=$(( $(date +%s) + 90 ))
    echo "   Waiting for llama-server on ${NODE_HOST}:${LLM_PORT} …"
    while (( $(date +%s) < deadline )); do
        if curl -sf "http://${NODE_IP}:${LLM_PORT}/health" >/dev/null 2>&1; then
            echo "   ✓  Ready"
            return 0
        fi
        sleep 3
    done
    echo "   ❌  Timed out waiting for llama-server" >&2
    return 1
}

cmd="${1:-start}"

case "$cmd" in

  start)
    if curl -sf "http://${NODE_IP}:${LLM_PORT}/health" >/dev/null 2>&1; then
        echo "llama-server is UP at http://${NODE_HOST}:${LLM_PORT}"
        curl -sf "http://${NODE_IP}:${LLM_PORT}/v1/models" \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print('  Model:', d['data'][0]['id'])" \
            2>/dev/null || true
        exit 0
    else
        echo "llama-server is NOT running on ${NODE_HOST}:${LLM_PORT}" >&2
        echo "Ask LSE: 'start node3090'  then re-run." >&2
        exit 1
    fi
    ;;

  stop)
    echo "🛑  Stopping llama-server on ${NODE_HOST} …"
    ssh_cmd "pkill -f 'llama-server.*${LLM_PORT}' 2>/dev/null; echo done"
    ;;

  status)
    if curl -sf "http://${NODE_IP}:${LLM_PORT}/health" >/dev/null 2>&1; then
        echo "✓  llama-server is UP at http://${NODE_HOST}:${LLM_PORT}"
        curl -sf "http://${NODE_IP}:${LLM_PORT}/v1/models" \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print('  Model:', d['data'][0]['id'])" \
            2>/dev/null || true
    else
        echo "✗  llama-server is NOT running on ${NODE_HOST}:${LLM_PORT}"
    fi
    ;;

  logs)
    echo "📜  Last 50 lines from ${NODE_HOST}:${REMOTE_LOG}"
    ssh_cmd "tail -50 '${REMOTE_LOG}'"
    ;;

  *)
    echo "Usage: $0 [start|stop|status|logs]" >&2
    exit 1
    ;;

esac
