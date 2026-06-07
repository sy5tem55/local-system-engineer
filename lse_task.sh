#!/usr/bin/env bash
# lse_task.sh — one-command LSE coding pipeline
# Wakes node3090, starts llama-server, runs lse_agent.py, optionally shuts down.
#
# Usage:
#   ./lse_task.sh \
#     --task "Rewrite echarts_topology.py to fix tier edges" \
#     --files net-discovery/snapshot.json net-discovery/echarts_topology.py \
#     --target net-discovery/echarts_topology.py
#
# All lse_agent.py flags are forwarded (--dry-run, --skip-planner, etc.)
# Extra flags handled here:
#   --no-shutdown    keep llama-server running after task (default: stop it)
#   --no-wol         skip Wake-on-LAN (if node3090 is already up)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_SCRIPT="${SCRIPT_DIR}/scripts/node3090_start_llm.sh"
LSE_AGENT="${SCRIPT_DIR}/lse_agent.py"

# ── Configurable ─────────────────────────────────────────────────────────────
# Worker + Verifier: Qwen3.6 on LUCIFER (node4090), port 8080
LLM_URL="http://localhost:8080"

# Planner: Gemma on node3090, port 8080 — set to "" to use same node as Worker
PLANNER_URL="http://192.168.5.41:8080"

# node3090 SSH (for start/stop/status commands)
NODE_HOST="node3090"   # bare name works now (search home.arpa set in resolv.conf)
NODE_IP="192.168.5.41"
LLM_PORT=8080
# ─────────────────────────────────────────────────────────────────────────────

SHUTDOWN_AFTER=true
AGENT_ARGS=()

# Parse args — split lse_task flags from lse_agent flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-shutdown) SHUTDOWN_AFTER=false; shift ;;
        *)             AGENT_ARGS+=("$1"); shift ;;
    esac
done

if [[ ${#AGENT_ARGS[@]} -eq 0 ]]; then
    echo "Usage: $0 --task '...' --files file1 [file2 ...] [--target file] [options]"
    echo "       $0 --no-shutdown --task '...' --files ...   (keep server running)"
    exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo " LSE Agent Pipeline"
echo " Task: $(echo "${AGENT_ARGS[@]}" | grep -oP '(?<=--task ).*?(?= --|$)' || true)"
echo "════════════════════════════════════════════════════════════"

# ── 1. Check node3090 reachable only if Planner is running there ────────────
if [[ -n "${PLANNER_URL}" && "${PLANNER_URL}" == *"${NODE_IP}"* ]]; then
    if ! ping -c1 -W2 "${NODE_IP}" >/dev/null 2>&1; then
        echo "❌  node3090 is offline (needed for Planner)." >&2
        echo "    Ask LSE to start it, then re-run." >&2
        exit 1
    fi
    echo "✓  node3090 reachable (Planner)"
fi

# ── 2. Verify llama-server is ready (LSE handles start via start_node_agent) ──
if ! curl -sf "${LLM_URL}/health" >/dev/null 2>&1; then
    echo "❌  llama-server is not running at ${LLM_URL}" >&2
    echo "    Ask LSE: 'start node3090'  then re-run." >&2
    exit 1
fi
echo "llama-server ready at ${LLM_URL}"
MODEL=$(curl -sf "${LLM_URL}/v1/models" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'])" 2>/dev/null || echo "unknown")
echo "  Model: ${MODEL}" 

# ── 3. Run the agent pipeline ────────────────────────────────────────────────
echo ""
AGENT_CMD=(python3 "${LSE_AGENT}" --llm-url "${LLM_URL}")
if [[ -n "${PLANNER_URL}" && "${PLANNER_URL}" != "${LLM_URL}" ]]; then
    AGENT_CMD+=(--planner-url "${PLANNER_URL}")
fi
AGENT_CMD+=("${AGENT_ARGS[@]}")
"${AGENT_CMD[@]}"
AGENT_EXIT=$?

# ── 4. Shutdown (optional) ───────────────────────────────────────────────────
if [[ "$SHUTDOWN_AFTER" == true ]]; then
    echo ""
    bash "${NODE_SCRIPT}" stop
    echo "💤  node3090 llama-server stopped"
fi

exit $AGENT_EXIT
