# llama.cpp Build Reference

**Host:** LUCIFER (WSL2 · Ubuntu · CUDA 13.3 · RTX 4090 sm_89)
**Source:** `/home/sy5/llama.cpp`
**Build dir:** `/home/sy5/llama.cpp/build`
**Compiler:** GCC 14 (avoids GCC 13 `-O3` template ICE)
**CPU:** Intel Core i9-14900KF (AVX, AVX2, AVX_VNNI — no AVX-512)

---

## Verified Rebuild Command (Fully Optimized)

```bash
cd /home/sy5/llama.cpp && git fetch && git checkout b9496 && cd build && rm -f CMakeCache.txt && cmake .. \
  -DCMAKE_C_COMPILER=gcc-14 \
  -DCMAKE_CXX_COMPILER=g++-14 \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES="89" \
  -DGGML_AVX=ON \
  -DGGML_AVX2=ON \
  -DGGML_AVX_VNNI=ON \
  && make -j$(nproc) 2>&1 | tee /tmp/build.log
```

### Flags explained

| Flag | Value | Reason |
|---|---|---|
| `CMAKE_C_COMPILER` / `CXX` | `gcc-14` / `g++-14` | Avoids GCC 13 ICE on complex CUDA host templates under `-O3` |
| `GGML_CUDA` | `ON` | Enable CUDA backend |
| `CMAKE_CUDA_ARCHITECTURES` | `"89"` | RTX 4090 is sm_89 (Ada Lovelace). Omitting this compiles for all arches (including sm_100 Blackwell), which segfaults on nvfp4 templates with CUDA 13.3 |
| `GGML_AVX` / `AVX2` / `AVX_VNNI` | `ON` | Unlocks vectorized CPU math on i9-14900KF. ~5–10% faster prompt processing; ~30–50% faster if running partial CPU offload. CPU does **not** support AVX-512 — those flags would be ignored or cause issues. |

### Incremental Build Note

If you change flags but not source files, CMake may perform an **incremental build** (skipping CUDA kernel recompilation). This is normal and very fast — the new flags will be applied to the host code on the next full rebuild or manual `make clean`.

### Known failure modes

| Error | Cause | Fix |
|---|---|---|
| `internal compiler error: in try_forward_edges, at cfgcleanup.cc:580` | GCC 13 aggressive `-O3` loop unrolling on CUDA host templates | Use GCC 14 (system default) or force `-DCMAKE_CXX_FLAGS_RELEASE="-O2 -DNDEBUG"` |
| `Segmentation fault` on `mmq-instance-nvfp4.cu` | CUDA 13.3 compiling Blackwell NV FP4 kernels for wrong arch | Add `-DCMAKE_CUDA_ARCHITECTURES="89"` |
| `cmake .. -DGGML_CUDA=ON` not finding CMakeLists.txt | Commands pasted as one line into terminal | Run as `&&`-chained single line |
| `rm: cannot remove CMakeCache.txt: No such file or directory` | Clean build dir — safe to ignore with `-f` flag | Use `rm -f` |

---

## After Build

Binaries land in `/home/sy5/llama.cpp/build/bin/`. The launcher calls `llama-server` directly — no install step needed.

Check the new binary version:

```bash
/home/sy5/llama.cpp/build/bin/llama-server --version
```

Check build log for errors:

```bash
grep -E "Error|fault|Killed|warning" /tmp/build.log | grep -v "^--" | tail -30
```

---

## Post-Rebuild: New Prometheus Metrics

Builds after b9307 expose two native KV cache metrics that earlier builds lack:

```
llamacpp:kv_cache_usage_ratio   # 0.0–1.0 fill ratio
llamacpp:kv_cache_tokens        # absolute tokens in KV cache
```

Verify they appear after restarting the stack:

```bash
curl -s http://localhost:8080/metrics | grep kv_cache
```

---

## Wrong Version Number In llama-ui Corner (e.g. "build = 20" instead of "b10011")

**Symptom:** `--version` / the llama-ui bottom-right corner shows a small integer
(seen: 20, 64) that looks nothing like the real GitHub release tags (b10xxx).
Commit hash and compiler string ARE correct — only the build NUMBER is wrong.
Easy to mistake for a broken compile or a llama.cpp bug; it is neither.

**Root cause:** `cmake/build-info.cmake` derives `LLAMA_BUILD_NUMBER` from
`git rev-list --count HEAD` (see also `scripts/build-info.sh`). If the repo is a
**shallow clone** (`.git/shallow` exists — created by `git clone --depth=N` or an
old shallow fetch), `rev-list --count` can only see the commits present locally
and returns that small count, not the true total.

**Diagnosis (read-only, confirms before touching anything):**
```bash
cd /home/sy5/llama.cpp
ls -la .git/shallow 2>&1         # exists = confirmed shallow
git rev-list --count HEAD        # the wrong small number, matches the corner
git describe --tags              # the REAL identity, e.g. "b10005-6-gbf2c86ddc"
cat build/common/build-info.cpp  # LLAMA_BUILD_NUMBER hardcoded at last configure
```
If `git describe --tags` shows a real bNNNNN-like tag while `rev-list --count`
is small (or `.git/shallow` exists), this is the shallow-clone bug — not a
compiler or flag problem. Do not change `-DCMAKE_*` flags to chase this; they
are unrelated.

**Fix:**
```bash
cd /home/sy5/llama.cpp
git fetch --unshallow             # deepens to full history (network-only, ~seconds)
# fallback if --unshallow errors on an already-shallow clone:
#   git fetch --depth=1000000 origin
```
This step alone does NOT touch the running binary or process — safe to run
with llama-server live. Verify: `.git/shallow` should now be gone and
`git rev-list --count HEAD` should match `git describe --tags`'s number.

Then, per the LIVE SERVICE RULE (pgrep-before-rebuild): **stop llama-server**,
rebuild (`cmake --build build --target llama-server -j$(nproc)`, same flags as
the Verified Rebuild Command above — flags are NOT the cause and need no
change), **restart**. The corner will show the correct build number only after
this rebuild regenerates `build/common/build-info.cpp`.

**Verified 2026-07-18 on LUCIFER:** before fix, `.git/shallow` present (3 lines),
`rev-list --count` = 20, `describe --tags` = `b10005-6-gbf2c86ddc`. After
`git fetch --unshallow` (2.7s): `.git/shallow` gone, `rev-list --count` = 10011,
matches `describe --tags` = `b10011` exactly (repo was sitting exactly on a
tagged release, hence no `-N-gHASH` suffix). Binary rebuild deferred — apply
via LIVE SERVICE RULE when ready to cycle the model.

**Prevention:** never `git clone --depth=N` this repo. If a shallow clone is
ever created (accidentally, or by a tool/script), run `git fetch --unshallow`
immediately as part of setup, before the first build.
