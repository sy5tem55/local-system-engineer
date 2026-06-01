# llama.cpp Build Reference

**Host:** LUCIFER (WSL2 · Ubuntu · CUDA 13.3 · RTX 4090 sm_89)
**Source:** `/home/sy5/llama.cpp`
**Build dir:** `/home/sy5/llama.cpp/build`

---

## Rebuild Command

Run as a single line from any directory:

```bash
cd /home/sy5/llama.cpp/build && rm -f CMakeCache.txt && cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="89" && make -j$(nproc) 2>&1 | tee /tmp/build.log
```

### Flags explained

| Flag | Value | Reason |
|---|---|---|
| `GGML_CUDA` | `ON` | Enable CUDA backend |
| `CMAKE_CUDA_ARCHITECTURES` | `89` | RTX 4090 is sm_89 (Ada Lovelace). Omitting this causes nvcc to compile for all arches including sm_100 (Blackwell), which segfaults on nvfp4 template instances with CUDA 13.3 |

### Known failure modes

| Error | Cause | Fix |
|---|---|---|
| `Segmentation fault` on `mmq-instance-nvfp4.cu` | CUDA 13.3 compiling Blackwell NV FP4 kernels for wrong arch | Add `-DCMAKE_CUDA_ARCHITECTURES="89"` |
| `cmake .. -DGGML_CUDA=ON` not finding CMakeLists.txt | Commands pasted as one line into terminal | Run as `&&`-chained single line or in separate steps |
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
