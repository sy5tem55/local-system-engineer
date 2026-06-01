#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LSE RAG Stack — Step 1: Ollama + nomic-embed-text setup
# Run once on the WSL host (Ubuntu-24.04) as sy5
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

EMBED_MODEL="nomic-embed-text"
OLLAMA_PORT=11434

echo "=== LSE RAG: Ollama + ${EMBED_MODEL} setup ==="

# ── 1. Install Ollama if not present ─────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo "[1/4] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "[1/4] Ollama already installed: $(ollama --version)"
fi

# ── 2. Start Ollama service (CPU-only, no GPU — preserve VRAM for llama-server)
echo "[2/4] Starting Ollama service (CPU-only)..."
# Force CPU-only by unsetting CUDA vars so it doesn't touch the 4090
export CUDA_VISIBLE_DEVICES=""
export OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}"

if ! pgrep -x ollama &>/dev/null; then
    CUDA_VISIBLE_DEVICES="" nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    echo "    Ollama started (PID $!)"
else
    echo "    Ollama already running"
fi

# ── 3. Pull nomic-embed-text ──────────────────────────────────────────────────
echo "[3/4] Pulling ${EMBED_MODEL}..."
OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" ollama pull ${EMBED_MODEL}

# ── 4. Verify embedding endpoint ─────────────────────────────────────────────
echo "[4/4] Verifying embedding endpoint..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:${OLLAMA_PORT}/api/embed \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"${EMBED_MODEL}\", \"input\": \"test\"}")

if echo "$RESPONSE" | grep -q '"embeddings"'; then
    DIM=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['embeddings'][0]))")
    echo "    ✅ Embedding endpoint OK — ${DIM} dimensions"
else
    echo "    ❌ Embedding endpoint failed:"
    echo "    $RESPONSE"
    exit 1
fi

echo ""
echo "=== Done. Ollama + ${EMBED_MODEL} ready at http://127.0.0.1:${OLLAMA_PORT} ==="
echo ""
echo "Next step: deploy Elasticsearch via Portainer, then run 02-es-setup.py"
