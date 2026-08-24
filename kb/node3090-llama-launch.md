# node3090 llama-server Launch Configuration

## Scope
node3090 only (192.168.5.41, ssh user lse-admin).
NOT node4090 (LUCIFER): its llama-server is /home/sy5/llama.cpp/build/bin/llama-server bound to 127.0.0.1:8080 — do not confuse the two nodes.

## Hardware
- GPU: RTX 3090 24 GB (live command splits across 2 GPUs: --tensor-split 3,1)
- CPU: Intel Core i9-9900K (8c/16t)
- RAM: 32 GB | OS: Ubuntu 24.04

## Binary
- /usr/local/bin/llama-server — version 10106 (1425386fd), shared-library layout since the 2026-08-19 rebuild (thin ~18 KB ELF stub; libs live in /usr/local/lib — verify with ldd, see KB ce741b669d5e978c). New rebuilds land here.
- /opt/llama.cpp/bin/llama-server — PINNED b64 build, reserved for model training. Coexistence is by design.

## Model
- File: /opt/models/unsloth/Qwen3.8-27B/Qwen3.8-27B-UD-Q6_K_XL.gguf
- alias: Qwen3.8-27B-UD-Q6_K_XL

## Canonical Launch Command
Verified live 2026-08-19 via pgrep -a llama-server (PID 1792373):

/usr/local/bin/llama-server \
  -m /opt/models/unsloth/Qwen3.8-27B/Qwen3.8-27B-UD-Q6_K_XL.gguf \
  --alias Qwen3.8-27B-UD-Q6_K_XL \
  --host 0.0.0.0 --port 8080 \
  --threads 15 --threads-batch 15 \
  --flash-attn on \
  --ctx-size 196608 \
  --batch-size 2048 --ubatch-size 512 \
  --n-gpu-layers 99 --tensor-split 3,1 \
  --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --temp 0.6 --top-p 0.95 --top_k 20 --min_p 0.0 --repeat-penalty 1.0 \
  --jinja --reasoning-format deepseek \
  --metrics

Flag notes:
- --metrics is REQUIRED: Prometheus job "node3090-llama-server" scrapes 192.168.5.41:8080/metrics (15s); without it the endpoint returns 501.
- node3090 binds 0.0.0.0 (unlike node4090's 127.0.0.1 loopback).
- --flash-attn requires an explicit value: on|off|auto.

## Verification
- Local: curl -s http://localhost:8080/health
- LAN:  curl -s http://192.168.5.41:8080/health
- Metrics: curl -s http://192.168.5.41:8080/metrics | head — expect llamacpp:* families

## Access
- Local: http://localhost:8080
- LAN: http://node3090.home.arpa:8080 (192.168.5.41:8080)

## History
- 2026-08-19: corrected to the live canonical config (Qwen3.8-27B-UD-Q6_K_XL @ ctx 196608). Prior content was a stale Qwen3.6-27B-A3B @ 32768 launch command; three consecutive kb_verify mismatches flagged it.
- 2026-07-20: original doc (Qwen3.6-27B Q4_K_M @ 81920) — superseded.
