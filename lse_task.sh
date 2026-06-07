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
NODE_HOST="node3090.home.arpa"   # FQDN required for SSH (bare "node3090" fails; DHCP option 119 pending)
NODE_IP="192.168.5.41"           # Use IP for HTTP — WSL2 TCP to FQDN fails despite DNS resolving
LLM_PORT=8080
LLM_URL="http://${NODE_IP}:${LLM_PORT}"  # IP avoids WSL2 hostname TCP bug
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

# ── 1. Check node3090 is reachable (WoL is handled by LSE) ──────────────────
if ! ping -c1 -W2 "${NODE_IP}" >/dev/null 2>&1; then
    echo "❌  node3090 is offline." >&2
    echo "    Ask LSE to start it, wait for it to boot, then re-run." >&2
    exit 1
fi
echo "✓  node3090 is reachable"

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
python3 "${LSE_AGENT}" \
    --llm-url "${LLM_URL}" \
    "${AGENT_ARGS[@]}"
AGENT_EXIT=$?

# ── 4. Shutdown (optional) ───────────────────────────────────────────────────
if [[ "$SHUTDOWN_AFTER" == true ]]; then
    echo ""
    bash "${NODE_SCRIPT}" stop
    echo "💤  node3090 llama-server stopped"
fi

exit $AGENT_EXIT
