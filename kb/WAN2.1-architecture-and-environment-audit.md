# WAN2.1 Architecture and Environment Audit — LUCIFER

**Date:** May 2025
**Status:** Investigation Phase (Not Yet Deployed)

---

## 1. WAN2.1 Architecture Overview

WAN2.1 is a family of open-source video generation models by Alibaba's Wan team, based on the **DiT (Diffusion Transformer)** architecture within a **Flow Matching** framework.

### 1.1 Core Architecture Components

- **Transformer Architecture:** Based on Diffusion Transformers (DiT)
- **WanAttentionBlocks** — each containing:
  - Vision self-attention
  - Text-to-vision cross-attention
  - Feed-forward layers
- **Text Encoder:** T5 (text conditioning backbone)
- **Training Framework:** Flow Matching paradigm (not traditional diffusion)

### 1.2 Model Variants

| Model | Parameters | VRAM (FP16) | VRAM (4-bit) | Use Case |
|-------|-----------|-------------|--------------|----------|
| WAN2.1-T2V-1.3B | 1.3B | ~5 GB | ~3 GB | Text-to-video (small) |
| WAN2.1-T2V-14B | 14B | ~28 GB | ~7-8 GB | Text-to-video (large) |
| WAN2.1-I2V-14B | 14B | ~28 GB | ~7-8 GB | Image-to-video |
| WAN2.1-VACE-14B | 14B | ~28 GB | ~7-8 GB | Unified creation/editing |

### 1.3 Model Specifications (WAN2.1-T2V-14B)

- Model dimension: 5120
- Feedforward dimension: 13824
- Transformer layers: 40
- Attention heads: 40
- Input/output dimension: 16
- Frequency dimension: 256

### 1.4 Latest Addition — VACE

**Wan2.1-VACE-14B** (Video All-in-one Creation and Editing):
- Unified semantic-controlled video generation model
- Based on Wan2.1-14B-I2V with a **Mixture-of-Transformers architecture**
- Supports in-context controls: concept, style, motion, camera
- Unifies text-to-video, inpainting, and structural control tasks

### 1.5 Distribution Formats

- Hugging Face models (safetensors)
- GGUF quantized versions (Q8_0, Q4_0) — available on Hugging Face
- Multi-GPU distributed training using Ulysses parallelism and FSDP

### 1.6 Model References

- Wan-AI/Wan2.1-T2V-14B (Hugging Face)
- Wan-AI/Wan2.1-I2V-14B (Hugging Face)
- Wan-AI/Wan2.1-VACE-14B (Hugging Face)
- Wan-AI/Wan2.1-T2V-1.3B (Hugging Face)

---

## 2. Environment Audit — LUCIFER

### 2.1 Hardware

| Component | Detail |
|-----------|--------|
| GPU | NVIDIA GeForce RTX 4090 |
| VRAM | 24 GB (21.8 GB currently free) |
| Compute Capability | 8.9 (Ada Lovelace) |
| CUDA Driver | 610.43 |
| CUDA Toolkit | 13.3 (nvcc at /usr/local/cuda-13.3/bin/nvcc) |
| CPU | x86_64 (WSL2) |
| RAM | 47 GB total, ~43 GB available |
| Swap | 8 GB |
| Kernel | 6.6.114.1-microsoft-standard-WSL2 |

### 2.2 Storage

| Path | Total | Free | Use% |
|------|-------|------|------|
| / (dev/sdd) | 1007 GB | 565 GB | 41% |
| /mnt/c | 1.9 TB | 981 GB | 48% |
| /home/sy5/models/ | — | — | 140 GB |
| /home/sy5/.cache/huggingface/hub/ | — | — | 22 GB |

### 2.3 GPU Memory Management

- llama-server: ~2.2 GB VRAM (Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf on port 8080)
- Free: 21.8 GB

### 2.4 CUDA Version Compatibility Matrix

| Component | Version | Notes |
|-----------|---------|-------|
| CUDA Toolkit (nvcc) | 13.3 | /usr/local/cuda-13.3/bin/nvcc |
| PyTorch CUDA | 13.0 | PyTorch 2.12.0 built with CUDA 13.0 |
| CUDA Driver | 610.43 | |
| CUDA Runtime | 13.0 | PyTorch CUDA runtime |

### 2.5 CUDA 13.3 nvcc C++ Standard Support

CUDA 13.3 nvcc supports:
- C++03, C++11, C++14, C++17, C++20, **C++23** (officially added in 13.3)

This is critical for flash-attn compilation, which requires C++17 (`-std=c++17`). CUDA 13.3 nvcc fully supports C++17.

---

## 3. Complete Python Instance Inventory

### 3.1 System Python

| Path | Version | Type |
|------|---------|------|
| `/usr/bin/python3.12` | Python 3.12.3 | System base |
| `/snap/core22/2411/usr/bin/python3.10` | Python 3.10.12 | Snap (legacy) |

### 3.2 Miniforge Base Environment

| Path | Version | Type |
|------|---------|------|
| `/home/sy5/miniforge3/bin/python3.13` | Python 3.13.13 | Base environment |

### 3.3 Miniforge Conda Environments

| Environment | Path | Version |
|-------------|------|---------|
| env_a1111 | `/home/sy5/miniforge3/envs/env_a1111/bin/python3.10` | Python 3.10.20 |
| env_orchestrator | `/home/sy5/miniforge3/envs/env_orchestrator/bin/python3.12` | Python 3.12.13 |

### 3.4 Virtual Environments (Symlinks)

| Env | Path | Symlink Target | Version |
|-----|------|---------------|---------|
| owui (OpenWebUI) | `/home/sy5/owui/bin/python3.12` | → `/usr/bin/python3.12` | Python 3.12.3 |
| comfyui | `/home/sy5/comfyui/venv/bin/python3.13` | → `/home/sy5/miniforge3/bin/python3.13` | Python 3.13.13 |
| interpreter-env | `/home/sy5/interpreter-env/bin/python3.12` | → `/usr/bin/python3.12` | Python 3.12.3 |

### 3.5 NVIDIA NSight Tools (Dev/Debug Only)

| Tool | Path | Version |
|------|------|---------|
| NSight Compute | `/opt/nvidia/nsight-compute/2026.2.0/host/target-linux-x64/python/bin/python` | Python 3.12.12 |
| NSight Systems | `/opt/nvidia/nsight-systems/2026.1.3/host-linux-x64/python/bin/python` | Python 3.12.12 |

### 3.6 Timeshift Snapshots (Old Copies — Ignore)

- `/timeshift/snapshots/*/localhost/...` — old copies, not functional

### 3.7 Conda Package Cache (Archived Copies — Ignore)

- `/home/sy5/miniforge3/pkgs/https/conda.anaconda.org/conda-forge/linux-64/python-*` — archived package copies
- `/home/sy5/miniforge3/pkgs/python-3.13.13-*` — archived package copies

### 3.8 Summary: Functional Python Instances

| Version | Count | Purpose |
|---------|-------|---------|
| **3.10.12** | 1 | Snap (legacy, not functional) |
| **3.10.20** | 1 | env_a1111 conda environment |
| **3.12.3** | 3 | System, owui venv, interpreter-env (all same binary) |
| **3.12.13** | 2 | env_orchestrator conda, NSight tools |
| **3.13.13** | 1 | Miniforge base, comfyui venv |

**5 functional Python instances total** (3.10, 3.12, 3.13), with multiple symlinks pointing to them.

---

## 4. Python Environment Inventory

### 4.1 owui (OpenWebUI) — Python 3.12.3

**Path:** /home/sy5/owui/bin/python3.12 (symlink → /usr/bin/python3.12)

**Installed AI packages:**
| Package | Version |
|---------|---------|
| torch | 2.12.0+cu130 |
| transformers | 5.5.4 |
| accelerate | 1.13.0 |
| sentence-transformers | 5.4.0 |
| onnxruntime | 1.24.3 |
| safetensors | 0.7.0 |
| openai | 2.29.0 |
| triton | 3.7.0 |
| pillow | 12.1.1 |
| pyclipper | 1.4.0 |
| pyperclip | 1.11.0 |
| rapidocr-onnxruntime | 1.4.4 |
| sentencepiece | 0.2.1 |

**Missing for WAN2.1:**
- ❌ diffusers
- ❌ bitsandbytes (4-bit quantization)
- ❌ peft (adapters)
- ❌ flash-attn (compile from source)
- ❌ xformers (memory-efficient attention)
- ❌ torchvision / torchaudio

### 4.2 env_a1111 — Python 3.10.20

**Path:** /home/sy5/miniforge3/envs/env_a1111/bin/python3.10

**Installed AI packages:**
| Package | Version |
|---------|---------|
| torch | 2.12.0+cu130 |
| torchvision | 0.27.0 |
| diffusers | 0.38.0 |
| xformers | 0.0.35 |
| transformers | 5.9.0 |
| accelerate | 1.13.0 |
| open_clip_torch | 3.3.0 |
| triton | 3.7.0 |
| einops | 0.8.2 |
| pillow | 12.2.0 |
| pillow-avif-plugin | 1.5.5 |
| opencv-python | 4.13.0.92 |
| safetensors | 0.8.0rc0 |
| numpy | 2.2.6 |
| scipy | 1.15.3 |
| scikit-image | 0.25.2 |
| ImageIO | 2.37.3 |
| pytorch-lightning | 2.6.4 |
| torchmetrics | 1.9.0 |
| torchsde | 0.2.6 |
| torchdiffeq | 0.2.5 |
| cuda-bindings | 13.2.0 |
| cuda-pathfinder | 1.5.4 |
| cuda-toolkit | 13.0.2 |
| nvidia-cuda-cupti | 13.0.85 |
| nvidia-cuda-nvrtc | 13.0.88 |
| nvidia-cuda-runtime | 13.0.96 |

**Missing for WAN2.1:**
- ❌ flash-attn (compile from source with nvcc 13.3)
- ❌ bitsandbytes (need CUDA 13.0 wheel)
- ❌ peft (pure Python, easy install)
- ❌ onnxruntime (pure Python, easy install)
- ❌ sentencepiece (may need compilation)
- ❌ openai (optional, pure Python)

### 4.3 env_orchestrator — Python 3.12.13

**Path:** /home/sy5/miniforge3/envs/env_orchestrator/bin/python3.12

**Purpose:** FastAPI + Google API environment
**AI packages:** None

### 4.4 Python Version Compatibility Summary

| Python Version | CUDA Wheels Available | flash-attn Compatible | xformers Compatible | bitsandbytes Compatible |
|---------------|----------------------|-----------------------|---------------------|------------------------|
| 3.10 (env_a1111) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| 3.12 (owui, orchestrator) | ❌ No CUDA 12+ wheels | ⚠️ Source compile only | ⚠️ Source compile only | ⚠️ CUDA 12.4 only |
| 3.13 (comfyui) | ❌ No CUDA 12+ wheels | ⚠️ Source + C API ABI risk | ⚠️ Source + C API ABI risk | ⚠️ CUDA 12.4 only |

**Key finding:** Python 3.13 is NOT installed as a standalone system Python. It only exists within miniforge base and the comfyui venv. The system uses Python 3.12.3 (owui) and Python 3.10.20 (env_a1111).

---

## 5. Existing Models (Hugging Face Cache)

### 5.1 FLUX Models

| Model | Size | Purpose |
|-------|------|---------|
| black-forest-labs/FLUX.2-dev | 321 MB | Base FLUX.2 model |
| city96/FLUX.2-dev-gguf | 2.8 GB | GGUF quantized FLUX.2 |
| black-forest-labs/FLUX.1-dev-FP8 | 12 KB | FP8 quantized FLUX.1 |
| comfyanonymous/flux_text_encoders | 9.4 GB | FLUX text encoders |
| alibaba-pai/FLUX.2-dev-Fun-Controlnet-Union | 7.7 GB | FLUX.2 ControlNet union |
| XLabs-AI/flux-ip-adapter-v2 | 1 GB | FLUX IP-Adapter |
| unsloth/FLUX.2-dev-GGUF | 12 KB | GGUF FLUX.2 |

### 5.2 LLM Models (GGUF)

| Model | Size |
|-------|------|
| Qwopus3.6-35B-A3B-v1-Q4_K_M.gguf | Active (llama-server) |
| Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf | 140 GB total |
| Qwen_Qwen3.6-27B-Q4_K_M.gguf | |
| Qwen3.6-27B-Q5_K_M.gguf | |
| Huihui-Qwen3.6-35B-A3B-Claude-4.7-Opus-abliterated-ggml-model-Q4_K.gguf | |
| gemma-4-26B-A4B-it-GGUF | |
| gemma-4-31B-it-GGUF | |

### 5.3 Text/Embedding Models

| Model | Size |
|-------|------|
| openai/clip-vit-large-patch14 | 1.5 MB |
| sentence-transformers/all-MiniLM-L6-v2 | 888 MB |

### 5.4 No WAN2.1 Models Downloaded Yet

No WAN2.1 models exist in the Hugging Face cache or local storage.

---

## 6. WAN2.1 Deployment Feasibility Analysis

### 6.1 VRAM Constraints (24 GB RTX 4090)

| Model | FP16 VRAM | 4-bit VRAM | Feasible? |
|-------|-----------|------------|-----------|
| WAN2.1-T2V-1.3B | ~5 GB | ~3 GB | ✅ Yes (FP16 or 4-bit) |
| WAN2.1-T2V-14B | ~28 GB | ~7-8 GB | ✅ Only at 4-bit |
| WAN2.1-I2V-14B | ~28 GB | ~7-8 GB | ✅ Only at 4-bit |
| WAN2.1-VACE-14B | ~28 GB | ~7-8 GB | ✅ Only at 4-bit |

**Practical limits with 24 GB VRAM:**
- 14B at FP16: OVERFLOW (~28 GB required)
- 14B at 4-bit: ~7-8 GB + KV cache overhead (~3-4 GB) = ~10-12 GB — FEASIBLE
- 1.3B at FP16: ~5 GB + KV cache overhead = ~7-9 GB — FEASIBLE
- llama-server concurrent: +2 GB — must be stopped or use VRAM-aware scheduling

### 6.2 Required CUDA Extensions

| Extension | Pre-built Wheel? | CUDA 13.3 Compatible? | Notes |
|-----------|-----------------|----------------------|-------|
| flash-attn | ❌ No (source only) | ✅ Yes (C++17 supported) | Must compile with nvcc 13.3 |
| xformers | ❌ No (source only) | ✅ Yes | Python 3.10 C API stable |
| bitsandbytes | ⚠️ CUDA 12.4 only | ⚠️ May need source build | Need CUDA 13.0 wheel |
| peft | ✅ Yes (pure Python) | N/A | No compilation needed |
| onnxruntime | ✅ Yes (pure Python) | N/A | No compilation needed |

### 6.3 CUDA 13.3 nvcc + PyTorch 2.12.0+cu130 — Potential Issue

- PyTorch 2.12.0+cu130 was built with CUDA 13.0
- nvcc is CUDA 13.3 — CUDA runtime is backward compatible
- BUT flash-attn compilation may have ABI issues when linking against PyTorch's CUDA 13.0 libraries
- **This needs to be tested empirically**

### 6.4 Recommended Deployment Environment

**env_a1111** is the best choice:
- Python 3.10.20 — stable C API, all extensions have pre-built wheels
- Already has: torch, torchvision, diffusers, xformers, accelerate, transformers, open_clip_torch, triton, einops, pillow, opencv, safetensors
- Only missing: flash-attn (compile), bitsandbytes (install), peft (install)

---

## 7. CUDA 13.3 Release Notes — Key Details

### 7.1 CUDA 13.3 C++ Support

- **Added official C++23 support** in nvcc and NVRTC
- nvcc supports: C++03, 11, 14, 17, 20, 23
- This is a **new feature**, not a deprecation
- Source: [CUDA Toolkit 13.3 Release Notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)
- Source: [CUDA Compiler Driver nvcc docs](https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/)

### 7.2 CUDA 13.3 CUDA Math Deprecations

- All legacy NPP APIs without the `_Ctx` suffix have been deprecated and removed
- Not directly relevant to WAN2.1 deployment

### 7.3 CUDA 13.3 New Features

- Tile programming in CUDA C++
- Compiler autotuning
- Python updates
- Expanded tensor interoperability with DLPack/mdspan in CCCL 3.3
- Source: [NVIDIA Developer Blog — CUDA 13.3](https://developer.nvidia.com/blog/nvidia-cuda-13-3-enhances-gpu-development-with-tile-programming-in-c-compiler-autotuning-and-python-updates/)

---

## 8. Python 3.13 + CUDA Compatibility — Research Summary

### 8.1 PyTorch Python 3.13 Support Timeline

| PyTorch Version | Python 3.13 Support | Notes |
|----------------|---------------------|-------|
| 2.6 (Jan 2025) | torch.compile only (JIT) | Not full binary compatibility |
| 2.9 (Oct 2025) | torch.compile only (beta) | Still not full binary compatibility |
| Current (2.12) | ❌ No official PyPI wheel | Only CUDA 11.8 wheels work with 3.13 |

**Sources:**
- [PyTorch 2.6 Release Blog](https://pytorch.org/blog/pytorch2-6/) — "compile support for Python 3.13"
- [PyTorch 2.9 Release Notes](https://github.com/pytorch/pytorch/releases) — "[Beta] torch.compile support for Python 3.13"
- [PyTorch PyPI](https://pypi.org/project/torch/) — wheel ABI tags
- [Stack Overflow](https://stackoverflow.com/questions/79782765/python-3-13-cuda-pytorch-2-8-support) — "Using Version 118 download.pytorch.org/whl/cu118 works with Python 3.13 — unfortunately, no other version does"

### 8.2 Python 3.13 C API ABI Changes

- Python 3.13 introduced free-threaded CPython (PEP 703)
- Changes the ABI for C extension modules
- flash-attn, xformers, bitsandbytes must compile from source and link against Python C API
- ABI compatibility uncertain with Python 3.13

### 8.3 flash-attn Compilation Issues

- flash-attn has **no pre-built wheels** on PyPI
- Must compile from source using nvcc
- Requirements: nvcc (CUDA >= 11.7), C++17 compiler, CUDA PyTorch, Ampere+ GPU
- Your RTX 4090 (sm_89) is fully supported
- CUDA 13.3 nvcc supports C++17
- The "nvcc fatal: Unsupported gpu architecture 'compute_120'" only applies to Blackwell (RTX 5090)

**Sources:**
- [flash-attn PyPI](https://pypi.org/project/flash-attn/)
- [flash-attn Issue #1916](https://github.com/Dao-AILab/flash-attention/issues/1916)
- [flash-attn Issue #1563](https://github.com/Dao-AILab/flash-attention/issues/1563)

### 8.4 bitsandbytes Python 3.13 Support

- bitsandbytes has pre-built wheels for Python 3.13, but **only for CUDA 12.4**
- Your CUDA is 13.3 — pre-built wheel won't work
- Would need to build bitsandbytes from source with nvcc 13.3

**Source:** [bitsandbytes PyPI](https://pypi.org/project/bitsandbytes/)

---

## 9. Storage Requirements for WAN2.1 Models

### 9.1 Model Sizes

| Model | Approximate Size |
|-------|-----------------|
| WAN2.1-T2V-14B | ~28 GB |
| WAN2.1-I2V-14B | ~28 GB |
| WAN2.1-VACE-14B | ~28 GB |
| WAN2.1-T2V-1.3B | ~6 GB |
| **Total** | **~118 GB** |

### 9.2 Available Storage

- /: 565 GB free — SUFFICIENT
- /mnt/c: 981 GB free — SUFFICIENT (preferred for Windows-side access)

### 9.3 Storage Recommendation

Store WAN2.1 models on `/mnt/c` if Windows-side access is needed. Store on `/` for WSL-only access.

---

## 10. Deployment Phases (PENDING — NOT STARTED)

### Phase 1: Environment Preparation
1. Activate env_a1111: `source /home/sy5/miniforge3/envs/env_a1111/bin/activate`
2. Verify torch.cuda.is_available() in env_a1111
3. Attempt flash-attn install — test CUDA 13.3 nvcc compatibility
4. Install bitsandbytes — for 4-bit quantization
5. Install peft — for adapters
6. Install onnxruntime — for certain workflows

### Phase 2: Model Download
1. Download WAN2.1-T2V-14B — test with 4-bit first
2. Download WAN2.1-I2V-14B
3. Download WAN2.1-VACE-14B
4. Download WAN2.1-T2V-1.3B

### Phase 3: Inference Setup
1. Stop llama-server before WAN2.1 inference (OR use VRAM-aware scheduling)
2. Load 14B at 4-bit + flash-attn + xformers
3. Configure fp8 inference if supported
4. Configure batch size based on available VRAM

### Phase 4: Workflow Integration
1. REST API layer for WAN2.1 inference
2. Prompt format standardization (T2V, I2V, VACE)
3. Video encoding (MP4/H.264) and output management

---

## 11. Risk Assessment

### HIGH RISK
1. **VRAM overflow on 14B model** — 24GB is tight. Must use 4-bit + flash-attn + xformers
2. **flash-attn compilation failure** — CUDA 13.3 nvcc compatibility with torch 2.12.0+cu130 (PyTorch built with CUDA 13.0)

### MEDIUM RISK
3. **Model download failures** — WAN2.1 models are large (28 GB each)
4. **bitsandbytes CUDA 13.0 compatibility** — pre-built wheels may only be for CUDA 12.x

### LOW RISK
5. **Python version compatibility** — Python 3.10 is the safest choice (used in env_a1111)

---

## 12. References

- [WAN-Video/Wan2.1 GitHub](https://github.com/Wan-Video/Wan2.1)
- [WAN2.1-T2V-1.3B Architecture](https://www.emergentmind.com/topics/wan2-1-t2v-1-3b)
- [WAN2.1 VACE 14B Architecture](https://www.emergentmind.com/topics/wan2-1-vace-14b)
- [CUDA 13.3 Release Notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)
- [CUDA Compiler Driver nvcc](https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/)
- [flash-attn PyPI](https://pypi.org/project/flash-attn/)
- [CUDA 13.3 Developer Blog](https://developer.nvidia.com/blog/nvidia-cuda-13-3-enhances-gpu-development-with-tile-programming-in-c-compiler-autotuning-and-python-updates/)
- [PyTorch 2.6 Release Blog](https://pytorch.org/blog/pytorch2-6/)
- [PyTorch 2.9 Release Notes](https://github.com/pytorch/pytorch/releases)
- [PyTorch PyPI](https://pypi.org/project/torch/)
- [bitsandbytes PyPI](https://pypi.org/project/bitsandbytes/)
