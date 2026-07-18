# node3090 llama-server Launch Configuration

## Hardware
- GPU: RTX 3090 24 GB VRAM
- CPU: Intel Core i9-9900K (8c/16t)
- RAM: 32 GB | OS: Ubuntu 24.04

## Binary
- Path: /usr/local/bin/llama-server (b1-6b80c74)
- Note: --flash-attn requires explicit arg: on|off|auto

## Model
- File: /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf
- VRAM: ~15.4 GB weights + ~7.2 GB KV cache (q8_0, 4 slots x 81920 ctx) = ~22.6 GB / 24 GB

## Launch Command
/usr/local/bin/llama-server \
  --model /opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf \
  --ctx-size 81920 --n-gpu-layers 129 --flash-attn on \
  --cache-type-k q8_0 --reasoning-budget 3072 --n-predict 8192 \
  --jinja --metrics --host 0.0.0.0 --port 8080 --threads 8

## Performance
- Prompt: ~131 tok/s | Generation: ~40 tok/s
- Disable thinking: chat_template_kwargs: {"enable_thinking": false}

