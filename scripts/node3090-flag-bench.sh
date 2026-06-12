#!/bin/bash
# node3090 llama-server flag benchmark (P21) — ubatch/batch matrix at canonical ctx 81920.
# Measures prompt-processing (pp) and generation (tg) via /completion timings with cache_prompt=false.
# Restores the canonical launch (start-llama-server.sh) + gateway at the end, even after failures.
# Run: bash /tmp/node3090-flag-bench.sh   (~6-10 min; keep the SSH session open)
set -u
MODEL=/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf
LOG=/home/lse-admin/llama-server.log
RESULTS=/tmp/flag-bench-results.txt
: > "$RESULTS"

echo "=== flag bench start $(date) ==="
echo "stopping hermes-gateway for the bench window"
sudo systemctl stop hermes-gateway

python3 -c "print('The quick brown fox jumps over the lazy dog. ' * 900)" > /tmp/bench-prompt.txt

stop_server() {
  pkill -f "[l]lama-server" 2>/dev/null
  for i in $(seq 1 12); do
    v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    [ "$v" -lt 500 ] && return 0
    sleep 5
  done
  echo "WARN: VRAM not clear (${v} MiB)"
}

wait_health() {
  for i in $(seq 1 30); do
    curl -s localhost:8080/health 2>/dev/null | grep -q ok && return 0
    sleep 5
  done
  return 1
}

bench_one() {
  local UB=$1 B=$2
  stop_server
  nohup /usr/local/bin/llama-server --model "$MODEL" --ctx-size 81920 --n-gpu-layers 129 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --threads 7 --threads-batch 7 --reasoning-budget 3072 --n-predict 8192 --jinja --metrics --host 0.0.0.0 --port 8080 --ubatch-size "$UB" --batch-size "$B" < /dev/null > "$LOG" 2>&1 &
  if ! wait_health; then
    echo "ub=$UB b=$B FAILED (no health — likely OOM, check $LOG)" | tee -a "$RESULTS"
    return
  fi
  sleep 2
  UB=$UB B=$B python3 - >> "$RESULTS" <<'PY'
import json, os, urllib.request
payload = {"prompt": open("/tmp/bench-prompt.txt").read(), "n_predict": 128,
           "cache_prompt": False, "temperature": 0}
req = urllib.request.Request("http://localhost:8080/completion",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=600))
t = r.get("timings", {})
print(f"ub={os.environ['UB']:>4} b={os.environ['B']:>4}  "
      f"pp={t.get('prompt_per_second',0):7.1f} t/s ({t.get('prompt_n',0)} tok)  "
      f"tg={t.get('predicted_per_second',0):5.1f} t/s")
PY
  echo "                vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader)" >> "$RESULTS"
  tail -1 "$RESULTS"
}

bench_one  512 2048   # current canonical baseline
bench_one 1024 2048
bench_one 2048 2048
bench_one 2048 4096

echo "=== restoring canonical ==="
stop_server
bash /opt/local-se/scripts/start-llama-server.sh
if wait_health; then echo "canonical RESTORED, health ok"; else echo "RESTORE FAILED — run Restart _Hermes.md procedure"; fi
sudo systemctl reset-failed hermes-gateway hermes-socat 2>/dev/null
sudo systemctl start hermes-socat hermes-gateway
sleep 5
systemctl is-active hermes-gateway hermes-socat

echo
echo "=== RESULTS ==="
cat "$RESULTS"
