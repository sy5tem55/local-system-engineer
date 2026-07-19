#!/usr/bin/env bash
# start-goethe-node3090.sh — deploy and start Goethe MCP on node3090 from LUCIFER.
# Run from LUCIFER: bash ~/projects/local-system-engineer/tools/start-goethe-node3090.sh
#
# Architecture:
#   - Goethe MCP runs locally ON node3090 (execute_command runs in node3090's shell)
#   - ES and Ollama are on LUCIFER — reached over LAN via GOETHE_ES_URL / GOETHE_OLLAMA_URL
#   - Binds 0.0.0.0:9700 — accessed via http://node3090.home.arpa:9700/mcp
#     (127.0.0.1 only works when browser and server are on the same machine)
#   - No vaultwarden tools — node3090 agent manages local environment only

set -euo pipefail

NODE="node3090.home.arpa"
USER="lse-admin"
REMOTE_DIR="/home/lse-admin/projects/local-system-engineer/tools"
LOCAL_DIR="$HOME/projects/local-system-engineer/tools"

# Token for node3090's MCP instance — different from LUCIFER's token.
# Rotate via: openssl rand -hex 16
NODE3090_TOKEN="266ce5843de4fd3ad04dffefae8f17db"

# ES runs locally on node3090 (Docker: lse-kb-es, bound to 127.0.0.1:9200).
# Previously pointed at lucifer.home.arpa:9200 but WSL2/Windows Firewall blocks
# LAN access to Docker containers — node3090 gets its own KB index instead.
NODE3090_ES="http://localhost:9200"
# Ollama runs locally on node3090 (127.0.0.1:11434, CPU-only, nomic-embed-text loaded).
NODE3090_OLLAMA="http://127.0.0.1:11434"

# ── planner Path 3 — Gemma GGUF spawn ────────────────────────────────────────
# Verified 2026-07-01 on node3090:
#   PLANNER_LLAMA_BIN: /usr/local/bin/llama-server  (verified: which llama-server)
#   PLANNER_MODEL_DIR: no Gemma GGUFs present on node3090 — Path 3 will not fire.
#     If Gemma models are added later, place them under PLANNER_MODEL_DIR and
#     ensure filenames match _GEMMA_MODELS in goethe.py (Q4_K_M quantization).
#   PLANNER_PORT:      8085 (avoids conflict with llama-server on :8080)
NODE3090_PLANNER_MODEL_DIR="/opt/models/lmstudio-community"
NODE3090_PLANNER_LLAMA_BIN="/usr/local/bin/llama-server"
NODE3090_PLANNER_PORT="8085"

echo "[start-goethe-node3090] ensuring remote tools dir exists..."
ssh "${USER}@${NODE}" "mkdir -p ${REMOTE_DIR}"

echo "[start-goethe-node3090] syncing goethe.py and goethe_mcp.py to node3090..."
rsync -az --info=name \
  "${LOCAL_DIR}/goethe.py" \
  "${LOCAL_DIR}/goethe_mcp.py" \
  "${LOCAL_DIR}/goethe_kb.py" \
  "${LOCAL_DIR}/goethe_perms.py" \
  "${LOCAL_DIR}/redact.py" \
  "${USER}@${NODE}:${REMOTE_DIR}/"

echo "[start-goethe-node3090] killing any existing goethe_mcp.py on node3090..."
# NOTE (2026-07-02): pattern uses [.] so the ssh wrapper's own command line does
# NOT match the regex — a plain 'goethe_mcp.py' pattern made pkill SIGKILL its own
# parent shell (remote 'bash -c' cmdline contains the pattern), the ssh exited
# nonzero, and set -e aborted this script mid-deploy (v0.3.0 rollout incident).
ssh "${USER}@${NODE}" "pkill -9 -f 'goethe_mcp[.]py' 2>/dev/null && sleep 0.5 || true"

echo "[start-goethe-node3090] writing remote start script..."
# Write a self-contained launcher to a temp file and rsync it — avoids
# multiline SSH quoting issues and ensures clean daemonisation via disown.
LAUNCHER="$(mktemp /tmp/goethe-node3090-launcher.XXXXXX.sh)"
cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
pkill -9 -f 'goethe_mcp[.]py' 2>/dev/null || true
sleep 0.3
mkdir -p /home/lse-admin/lse /home/lse-admin/lse/bkp
GOETHE_MCP_TOKEN=${NODE3090_TOKEN} \\
GOETHE_ES_URL=${NODE3090_ES} \\
GOETHE_OLLAMA_URL=${NODE3090_OLLAMA} \\
GOETHE_MODEL_PRETRAIN_CUTOFF=2026-01 \\
GOETHE_TASKS_DB=/home/lse-admin/lse/tasks.db \\
GOETHE_PLANNER_MODEL_DIR=${NODE3090_PLANNER_MODEL_DIR} \\
GOETHE_PLANNER_LLAMA_BIN=${NODE3090_PLANNER_LLAMA_BIN} \\
GOETHE_PLANNER_PORT=${NODE3090_PLANNER_PORT} \\
nohup python3 ${REMOTE_DIR}/goethe_mcp.py \\
  --goethe ${REMOTE_DIR}/goethe.py \\
  --transport http \\
  --port 9700 \\
  --host 0.0.0.0 \\
  --cors-origin '*' \\
  > /tmp/goethe-node3090.log 2>&1 &
disown
echo "[goethe-node3090] PID \$! started"
EOF

rsync -az "${LAUNCHER}" "${USER}@${NODE}:/tmp/goethe-node3090-launcher.sh"
rm -f "${LAUNCHER}"

echo "[start-goethe-node3090] starting Goethe MCP on node3090..."
ssh "${USER}@${NODE}" 'bash /tmp/goethe-node3090-launcher.sh'

echo "[start-goethe-node3090] done — Goethe MCP running on node3090:9700"
echo "  Token:   ${NODE3090_TOKEN}"
echo "  Log:     ssh ${USER}@${NODE} 'tail -f /tmp/goethe-node3090.log'"
echo "  llama-ui MCP URL: http://node3090.home.arpa:9700/mcp"
echo "  Auth header:      Authorization: Bearer ${NODE3090_TOKEN}"
