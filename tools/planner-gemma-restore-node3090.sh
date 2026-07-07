#!/usr/bin/env bash
# planner-gemma-restore-node3090.sh — end the Gemma planner experiment: stop the
# Gemma :8085 instance on node3090 and replay the pre-swap llama-server command
# captured by planner-gemma-swap-node3090.sh. Run from LUCIFER.

set -euo pipefail

NODE="node3090.home.arpa"
NODE_IP="192.168.5.41"
USER="lse-admin"

echo "[gemma-restore] stopping ALL llama-server instances on ${NODE}..."
ssh "${USER}@${NODE}" "pkill -9 -f 'llama[-]server' 2>/dev/null; sleep 1; true"

echo "[gemma-restore] replaying pre-swap command..."
ssh "${USER}@${NODE}" "test -x /tmp/llama-preswap-cmd.sh" || {
  echo "[gemma-restore] ERROR: /tmp/llama-preswap-cmd.sh missing on ${NODE} —"
  echo "  the swap script never captured a running server (or /tmp was wiped)."
  echo "  Start Qwen manually with the node's usual launch procedure."; exit 1; }
ssh "${USER}@${NODE}" "nohup bash /tmp/llama-preswap-cmd.sh > /tmp/llama-restore.out 2>&1 < /dev/null; sleep 1; true"

echo "[gemma-restore] waiting for /health on ${NODE_IP}:8080..."
deadline=$(( $(date +%s) + 180 ))
until curl -sf "http://${NODE_IP}:8080/health" >/dev/null 2>&1; do
  (( $(date +%s) > deadline )) && { echo "[gemma-restore] TIMEOUT — check ssh ${USER}@${NODE} tail /tmp/llama-server.log"; exit 1; }
  sleep 3
done
echo "[gemma-restore] ✓ Qwen llama-server restored at http://${NODE_IP}:8080"
echo "  planner() Step-0 probe now finds :8085 down and cascades to Qwen normally."
