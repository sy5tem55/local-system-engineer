# node3090 llama.cpp Canonical Rebuild (RTX 3090)

Host: node3090 — i9-9900K (8c/16t), 32 GB RAM, RTX 3090 24 GB (Ampere, sm_86), Ubuntu 24.04
Toolchain: CUDA 13.3 + gcc-14.2 (verified compatible on this host 2026-07-19)
Repo: /home/lse-admin/llama.cpp (full clone, master — NOT shallow)
Binary: /usr/local/bin/llama-server (install needs sudo)
Note: build2/ in the repo is stale cruft — ignore or delete. Canonical build dir is build/.

## Rebuild command

```bash
# 1. LIVE SERVICE RULE — stop llama-server first
pgrep -a llama-server        # note PID
kill <PID>                   # confirm gone: pgrep -a llama-server -> empty

# 2. Pull latest + configure + build
cd /home/lse-admin/llama.cpp && git fetch --tags && git pull \
  && rm -f build/CMakeCache.txt && cmake -B build \
  -DCMAKE_C_COMPILER=gcc-14 \
  -DCMAKE_CXX_COMPILER=g++-14 \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES="86" \
  -DGGML_CUDA_FA=ON \
  -DGGML_CUDA_FA_ALL_QUANTS=ON \
  -DGGML_CUDA_GRAPHS=ON \
  -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON \
  -DGGML_F16C=ON -DGGML_BMI2=ON -DGGML_SSE42=ON \
  -DGGML_AVX_VNNI=OFF -DGGML_AVX512=OFF \
  && cmake --build build -j16 2>&1 | tee /tmp/build.log | tail -5

# 3. Verify BEFORE install, then install
build/bin/llama-server --version
sudo install -m 755 build/bin/llama-server /usr/local/bin/llama-server
llama-server --version

# 4. Relaunch per node3090-llama-launch.md
```

## Flag rationale

| Flag | Value | Why |
|---|---|---|
| CMAKE_CUDA_ARCHITECTURES | "86" | RTX 3090 = sm_86 Ampere. Compiling all arches hits the CUDA 13.3 Blackwell nvfp4 template segfault. |
| gcc-14 / g++-14 | — | Avoids GCC 13 ICE on CUDA host templates under -O3. CUDA 13.3 accepts gcc-14. |
| GGML_CUDA_FA_ALL_QUANTS | ON | FlashAttention kernels for every KV-cache quant combo (needed for q8_0 KV etc.). Longer compile, bigger binary — intended. |
| GGML_CUDA_GRAPHS | ON | CUDA graph capture speedup. |
| AVX/AVX2/FMA/F16C/BMI2/SSE42 | ON | All supported by i9-9900K (Coffee Lake). |
| AVX_VNNI / AVX512 | OFF | NOT supported by 9900K — do not enable. |

## Known gotchas
- Low "version: N" in --version = missing git tags, not a shallow clone. Fix: git fetch --tags. Repo confirmed non-shallow 2026-07-19.
- Never rebuild while llama-server is running (binary corruption of live process).
- rm CMakeCache.txt whenever flags change, else stale cache wins.
- /build.json returning a low "version" (e.g. 64) is the prebuilt web-UI bundle's own stamp — cosmetic. The authoritative binary version is `curl /props` → build_info (e.g. b10068-571d0d540) or `llama-server --version`. Do NOT rebuild with LLAMA_USE_PREBUILT_UI=OFF to "fix" this.
