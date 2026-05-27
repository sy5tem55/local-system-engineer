# CUDA Toolkit Upgrade — llama.cpp Rebuild Procedure

**Last updated:** 2026-05-27  
**Performed:** CUDA 12.8 → 13.3 on Ubuntu 24.04 WSL2, RTX 4090, driver 610.47

---

## Overview

Upgrading the Windows NVIDIA driver to a version that supports a new CUDA major release (e.g. 610.47 → CUDA 13) requires three steps:

1. Install the new CUDA toolkit in WSL
2. Rebuild llama.cpp against the new toolkit
3. Verify the binary links against the correct libraries

All three steps have non-obvious failure modes documented below.

---

## Step 0 — Verify the driver supports CUDA 13

The Windows GPU driver version determines the maximum CUDA version WSL can use.
Driver 610.47 supports CUDA 13.x. Check the NVIDIA driver → CUDA compatibility table before proceeding.

---

## Step 1 — Check what is actually installed

Before doing anything, verify what nvcc and the toolkit packages report:

```bash
nvcc --version
dpkg -l | grep -E "cuda-compiler|cuda-toolkit-[0-9]" | grep -v "^rc"
```

### Common trap: config-common package version ≠ CUDA version

The package `cuda-toolkit-config-common 13.3.29-1` looks like CUDA 13 but is **not** the toolkit. It is a metadata/configuration meta-package whose own version number happens to start with 13. The actual CUDA version is determined by the compiler packages (`cuda-compiler-12-8`, etc.). Always confirm with `nvcc --version`, not by reading apt package versions.

---

## Step 2 — Check available CUDA 13 packages

```bash
apt-cache search "^cuda" | grep -E "^cuda-(toolkit|compiler)-13" | sort
```

Install the latest minor version (13.3 as of this writing). CUDA toolkit versions coexist — installing 13.3 does not remove 12.8:

```bash
sudo apt install cuda-toolkit-13-3
```

---

## Step 3 — Verify and fix the /usr/local/cuda symlink

After install, check the symlink:

```bash
ls -la /usr/local/cuda
nvcc --version
```

The install may update `/usr/local/cuda` automatically via `update-alternatives`. If nvcc still reports the old version, fix the symlink manually:

```bash
sudo ln -sfn /usr/local/cuda-13.3 /usr/local/cuda
nvcc --version   # must show 13.3 before proceeding
```

---

## Step 4 — Stop the stack before rebuilding

Kill llama-server and close OpenWebUI/Playwright tabs before replacing the binary:

```bash
kill $(pgrep llama-server)
```

---

## Step 5 — Rebuild llama.cpp

Clear the cmake cache — stale entries from the previous CUDA version cause subtle failures:

```bash
cd /home/sy5/llama.cpp/build
rm CMakeCache.txt
cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="89" -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-14
make -j$(nproc)
```

**RTX 4090 architecture flag:** `-DCMAKE_CUDA_ARCHITECTURES="89"` (Ada Lovelace = SM 89). Do not change this.

**Why gcc-14 as host compiler:** see GCC 13.3 ICE section below.

---

## Step 6 — Verify the binary links against CUDA 13

```bash
ldd /home/sy5/llama.cpp/build/bin/llama-server | grep -i cuda
```

Expected output:

```
libcudart.so.13  => /usr/local/cuda/lib64/libcudart.so.13
libcublas.so.13  => /usr/local/cuda/lib64/libcublas.so.13
libcublasLt.so.13 => /usr/local/cuda/lib64/libcublasLt.so.13
libcuda.so.1     => /usr/lib/wsl/lib/libcuda.so.1
```

If you see `libcudart.so.12` the cmake step found the wrong toolkit — the `/usr/local/cuda` symlink was not updated before running cmake. Clear the cache and rebuild.

---

## Step 7 — Restart via launcher

Use the launcher rather than a manual command. It writes the correct WSL scripts and opens all tabs in the right order.

---

## Known Issue: GCC 13.3 ICE on MXFP4 kernel

### Symptom

Build fails mid-way with:

```
internal compiler error: in try_forward_edges, at cfgcleanup.cc:580
...mmq-instance-mxfp4.cu.o] Error 1
```

### Cause

CUDA 13 added MXFP4 (Microscaling FP4) matrix multiplication kernels for Blackwell hardware. GCC 13.3 (Ubuntu 24.04 default) has an ICE (internal compiler error) in its control flow graph cleanup pass when compiling these template instantiations. The RTX 4090 (Ada Lovelace, SM 89) has no MXFP4 hardware, but GCC 13.3 still crashes trying to compile the kernel.

### Fix — use GCC 14 as the NVCC host compiler

```bash
sudo apt install gcc-14 g++-14
cd /home/sy5/llama.cpp/build
rm CMakeCache.txt
cmake .. -DGGML_CUDA=ON \
         -DCMAKE_CUDA_ARCHITECTURES="89" \
         -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-14
make -j$(nproc)
```

GCC 14 does not have this ICE and compiles the MXFP4 kernels cleanly. The resulting binary includes MXFP4 code paths (harmless on SM 89 — they will never execute on this GPU) and links correctly against CUDA 13.3.

Do **not** use `-DGGML_CUDA_MXFP4=OFF` to work around the error — the GCC 14 fix is cleaner and produces a complete build.

---

## Quick Reference

| Step | Command |
|------|---------|
| Check nvcc | `nvcc --version` |
| Check installed packages | `dpkg -l \| grep -E "cuda-compiler\|cuda-toolkit-[0-9]"` |
| Check available CUDA 13 | `apt-cache search "^cuda" \| grep -E "^cuda-(toolkit\|compiler)-13"` |
| Install CUDA 13.3 | `sudo apt install cuda-toolkit-13-3` |
| Fix symlink | `sudo ln -sfn /usr/local/cuda-13.3 /usr/local/cuda` |
| Install GCC 14 | `sudo apt install gcc-14 g++-14` |
| Clear cmake cache | `rm CMakeCache.txt` |
| Configure | `cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="89" -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-14` |
| Build | `make -j$(nproc)` |
| Verify | `ldd .../llama-server \| grep -i cuda` |
