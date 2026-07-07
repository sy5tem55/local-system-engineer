#!/usr/bin/env bash
# planner-gemma-swap-node3090.sh — swap node3090's GPU from Qwen (server :8080)
# to the Gemma-4-31B PLANNER instance on :8085. Run from LUCIFER.
#
# Cross-family planner experiment (Goethe v0.3.2):
#   goethe's planner() Step-0 probes PLANNER_FORCE_URL (/health) — set
#   GOETHE_PLANNER_FORCE_URL=http://192.168.5.41:8085 in the gateway env once;
#   plans route to Gemma whenever this swap is active, cascade to Qwen otherwise.
#
# The pre-swap llama-server command line is captured on node3090 at
# /tmp/llama-preswap-cmd.sh — planner-gemma-restore-node3090.sh replays it.
#
# PKILL SELF-KILL RULE: all remote patterns use bracketed chars ('llama[-]server')
# so the ssh wrapper's own cmdline never matches (see kb/session-learnings.md).

set -euo pipefail

NODE="node3090.home.arpa"
NODE_IP="192.168.5.41"
USER="lse-admin"
GEMMA_PORT=8085
GEMMA_GGUF="/opt/models/lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf"

echo "[gemma-swap] checking Gemma GGUF exists on ${NODE}..."
ssh "${USER}@${NODE}" "test -f '${GEMMA_GGUF}'" || {
  echo "[gemma-swap] ERROR: ${GEMMA_GGUF} not found on ${NODE}"; exit 1; }

echo "[gemma-swap] capturing current llama-server cmdline for restore..."
ssh "${USER}@${NODE}" "PID=\$(pgrep -f 'llama[-]server' | head -1); \
  if [ -n \"\$PID\" ]; then \
    { printf '#!/usr/bin/env bash\n'; tr '\0' ' ' < /proc/\$PID/cmdline; printf ' > /tmp/llama-server.log 2>&1 &\n'; } \
      > /tmp/llama-preswap-cmd.sh; chmod +x /tmp/llama-preswap-cmd.sh; \
    echo 'captured:'; tail -1 /tmp/llama-preswap-cmd.sh | head -c 200; echo; \
  else echo 'no llama-server running — nothing to capture'; fi"

echo "[gemma-swap] stopping current llama-server on ${NODE}..."
ssh "${USER}@${NODE}" "pkill -9 -f 'llama[-]server' 2>/dev/null; sleep 1; true"

echo "[gemma-swap] writing Gemma planner launcher..."
LAUNCHER="$(mktemp /tmp/gemma-planner-launcher.XXXXXX.sh)"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
# Gemma-4-31B planner instance — sampling per Gemma guidance (temp 1.0, top-k 64).
# ctx 16384: plans are small; leaves VRAM headroom on the 24GB 3090.
nohup llama-server \\
  -m ${GEMMA_GGUF} \\
  --alias Gemma-4-31B-planner \\
  --host 0.0.0.0 --port ${GEMMA_PORT} \\
  -ngl 99 --flash-attn on \\
  --ctx-size 16384 \\
  --temp 1.0 --top-k 64 --top-p 0.95 --min-p 0.0 \\
  --jinja \\
  > /tmp/gemma-planner.log 2>&1 < /dev/null &
disown
echo "[gemma-planner] PID \$! started on :${GEMMA_PORT}"
EOF
rsync -az "${LAUNCHER}" "${USER}@${NODE}:/tmp/gemma-planner-launcher.sh"
rm -f "${LAUNCHER}"

echo "[gemma-swap] starting Gemma planner..."
ssh "${USER}@${NODE}" 'bash /tmp/gemma-planner-launcher.sh'

echo "[gemma-swap] waiting for /health on ${NODE_IP}:${GEMMA_PORT}..."
deadline=$(( $(date +%s) + 120 ))
until curl -sf "http://${NODE_IP}:${GEMMA_PORT}/health" >/dev/null 2>&1; do
  (( $(date +%s) > deadline )) && { echo "[gemma-swap] TIMEOUT — check ssh ${USER}@${NODE} tail /tmp/gemma-planner.log"; exit 1; }
  sleep 3
done
echo "[gemma-swap] ✓ Gemma-4-31B planner READY at http://${NODE_IP}:${GEMMA_PORT}"
echo "  goethe planner() will use it automatically if the gateway env has:"
echo "    GOETHE_PLANNER_FORCE_URL=http://${NODE_IP}:${GEMMA_PORT}"
echo "  Restore Qwen with: bash tools/planner-gemma-restore-node3090.sh"
