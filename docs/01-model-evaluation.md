# 01 — Model Evaluation: Model Selection for Local System Engineering

> **Last updated: 2026-05-23**
> **Current recommendation: Qwen3.6-27B-Q5_K_M** (supersedes all prior recommendations)
> **Host: Intel 14900K · 64 GB RAM · RTX 4090 24 GB · WSL2 Ubuntu 24.04 · 48 GB WSL RAM pool**

---

## Summary Decision Table

| Model | Context | Terminal-Bench 2.0 | VRAM at Q5_K_M | Verdict |
|---|---|---|---|---|
| **Qwen3.6-27B** | 262 144 native | **59.3** (= Claude Opus) | ~20.5 GB ✅ | ✅ **Use this** |
| Qwen3.6-35B-A3B | 262 144 native | 51.5 | ~15 GB (MoE) | ❌ Weaker on terminals |
| Qwen3-32B | ~32 768 | not listed | ~23 GB | ❌ Superseded |
| Gemma4-31B | ~32 768 | 42.9 | ~23 GB | ❌ Weak on terminals |
| gemma-4-26B-A4B (MoE) | ~32 768 | not listed | ~16 GB | ❌ Superseded |

---

## 1. Why Qwen3.6-27B Wins for This Use Case

### 1.1 Terminal-Bench 2.0 — the definitive signal

Terminal-Bench 2.0 tests agentic terminal interaction: bash tools, file editing, multi-step operations in a real shell with a 3-hour timeout and 32 CPU / 48 GB RAM harness. It is the closest published benchmark to what your Local System Engineer agent actually does.

```
Qwen3.6-27B:          59.3   ← 27B local model
Claude 4.5 Opus:      59.3   ← frontier closed model
Qwen3.5-397B-A17B:   52.5   ← 12× larger MoE
Qwen3.6-35B-A3B:     51.5
Gemma4-31B:          42.9
```

A 27B local quantized model matching Claude Opus on terminal agent tasks is the clearest possible signal that this is the right architecture for this job.

### 1.2 The context problem is architecturally solved

Qwen3.6-27B uses a **hybrid Gated DeltaNet + Gated Attention** architecture. Its 64 layers are arranged as:

```
16 × [ (Gated DeltaNet → FFN) × 3  →  (Gated Attention → FFN) × 1 ]
```

Three out of every four layers use **linear attention** (DeltaNet maintains a fixed-size recurrent state, not a KV cache that grows with context). Only one in four layers uses standard quadratic attention with a GQA KV cache (4 KV heads, head_dim 256).

Consequences:
- **Native context: 262 144 tokens** — the 30 000-token degradation cliff simply does not apply
- **KV cache is ~¼ the size** of an equivalent pure transformer — only 16 of 64 layers contribute to it
- **Context management (doc 03) is still best practice** but is an optimisation layer, not a reliability crutch
- **Thinking Preservation**: the model can retain its chain-of-thought reasoning traces across multi-turn agentic sessions, reducing redundant reasoning and improving KV cache efficiency

### 1.3 Native tool calling design

Unlike Gemma 4, Qwen3.6 was trained with structured function calling as a first-class capability. Tool call JSON is stable across long multi-turn threads. The llama.cpp `--jinja` flag activates the correct chat template for this.

---

## 2. Hardware Fit Analysis

### 2.1 RTX 4090 VRAM budget (24 GB)

| Quant | Est. size | 4090 headroom | Verdict |
|---|---|---|---|
| Q5_K_M | ~20.5 GB | ~3.5 GB for KV cache | ✅ **Recommended** — pure GPU |
| Q4_K_L | ~17.8 GB | ~6 GB for KV cache | ✅ Good fallback |
| Q4_K_M | ~16.8 GB | ~7 GB for KV cache | ✅ Safe minimum |
| Q6_K | ~23.5 GB | Marginal | ⚠️ Skip — too tight |

**Q5_K_M at ~20.5 GB** fits entirely in 24 GB VRAM with ~3.5 GB of headroom. Because only 16 of 64 layers use a growing KV cache, even at 64K context the KV cache adds roughly 2–3 GB — well within budget. This means pure GPU inference at maximum token/s.

### 2.2 WSL RAM — increase before downloading

The default 32 GB WSL allocation leaves 32 GB unused on a 64 GB machine. Increase it:

**File: `C:\Users\SY5\.wslconfig`** (create if it doesn't exist):
```ini
[wsl2]
memory=48GB
processors=20
swap=8GB
```

Then from a Windows terminal:
```cmd
wsl --shutdown
```

Reopen WSL. This gives WSL 48 GB while leaving 16 GB for Windows — enough for the desktop, browser, and GPU driver overhead simultaneously.

The 48 GB pool matters for: KV cache overflow at very long contexts, the OpenWebUI Python process, and any future larger models.

---

## 3. llama.cpp Compatibility Check

Qwen3.6's Gated DeltaNet architecture required new code in llama.cpp. Before loading the model, verify your build:

```bash
llama-server --version
# Must show build b5100 or later
```

If older, update llama.cpp from source:
```bash
cd /path/to/llama.cpp
git pull
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
```

### Recommended llama-server launch flags for Qwen3.6-27B

```bash
llama-server \
  --model /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf \
  --ctx-size 65536 \
  --n-gpu-layers 99 \
  --parallel 1 \
  --jinja \
  --threads 8 \
  --host 0.0.0.0 \
  --port 8080
```

Key changes from prior Gemma/Qwen3 flags:
- `--ctx-size 65536` — 64K is safe and useful; push to 131072 if performance testing confirms it
- `--jinja` — required for Qwen3.6 chat template and tool call handling
- No `--rope-scaling yarn` needed — the hybrid architecture handles long context natively
- No `--rope-freq-scale` needed for the same reason

---

## 4. Revised Evaluation Benchmark Suite

The benchmark suite from the initial version remains valid. Apply it to Qwen3.6-27B with these additions:

### 4.1 Architecture-specific tests

| Test ID | Task | Pass criteria |
|---|---|---|
| A1 | Run a 40-step agentic session (inject 40K tokens of history) | No constraint drift, no path hallucinations |
| A2 | Verify Thinking Preservation: reference reasoning from 5 turns ago | Correctly cites prior reasoning block |
| A3 | Tool call JSON validity across 20 consecutive calls | Zero malformed tool call JSON |

### 4.2 Updated scoring sheet template

```
Model: Qwen3.6-27B   Quant: Q5_K_M   llama.cpp build: ___   Date: ___
WSL RAM: 48GB   --ctx-size: 65536   --jinja: yes

Short-context:   S1__ S2__ S3__ S4__ S5__   Total: __/15
Mid-context:     M1__ M2__ M3__ M4__          Total: __/12
Long-context:    M1__ M2__ M3__ M4__          Total: __/12
Web-search gate: W1__ W2__ W3__               Total: __/9
Architecture:    A1__ A2__ A3__               Total: __/9

Grand total: __/57
Notes:
```

---

## 5. Prior Models — Disposition

| Model | Status | Notes |
|---|---|---|
| gemma-4-31B-it-Q4_K_M.gguf | Keep as fallback | Known context issues beyond 30K; do not use as primary |
| gemma-4-26B-A4B-it-GGUF | Retire | MoE routing instability; outclassed on all relevant benchmarks |
| Qwen3-32B (if downloaded) | Keep as secondary | Solid model; outclassed by Qwen3.6-27B on terminal tasks |

---

## 6. Eval Result Naming Convention

Commit scored result sheets alongside the prompt version used:
```
eval-results/2026-05-23_Qwen3.6-27B-Q5_K_M_v0.3-prompt.md
```
Note Reasoning budget:
llama-server \
  --model /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf \
  --ctx-size 32768 \
  --n-gpu-layers 99 \
  --parallel 1 \
  --reasoning-budget 0 \
  --jinja \
  --threads 8 \
  --host 0.0.0.0 \
  --port 8080