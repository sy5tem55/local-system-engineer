# node3090 llama.cpp recompile package — running (e8f19cc0a, 2026-07-16) → v0.2.0 (bb4caa754, 2026-08-21)

Status: DRAFT — package doc for a planned maintenance-window deploy; nothing on node3090 has been changed by this document. Date: 2026-08-24 (compiled from live probes; task 5520f387).

## Section A — Recompile command (node3090)

```bash
# node3090 — recompile llama.cpp at v0.2.0, matching the running build's flags
cd /home/lse-admin/llama.cpp        # or: git clone https://github.com/ggml-org/llama.cpp
git fetch --tags
git checkout v0.2.0                 # tag bb4caa754, published 2026-08-21 — first stable semver release

export CC=gcc-14 CXX=g++-14
cmake -B build \
  -DGGML_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES="86" \
  -DGGML_CUDA_FA=ON \
  -DGGML_CUDA_FA_ALL_QUANTS=ON \
  -DGGML_CUDA_GRAPHS=ON \
  -DGGML_AVX512=OFF \
  -DGGML_AVX512_VNNI=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j16

sudo cmake --install build --prefix /usr/local   # installs to /usr/local/bin
```

Notes:
- `CMAKE_CUDA_ARCHITECTURES="86"` targets the RTX 3090 (sm_86). The second GPU (RTX 5060 Ti) participates only via `--tensor-split 3,1`; if it must run CUDA kernels natively, its own sm_ must be added to the arch list.
- `GGML_AVX512`/`GGML_AVX512_VNNI` are OFF to match the currently running build (host CPU has no usable AVX-512 path in this configuration).
- The currently running server is `/opt/llama.cpp/bin/llama-server` at commit e8f19cc0a ("version 64", 2026-07-16). `/usr/local/bin/llama-server` is an unused 18 KB shared-lib stub at b10106 — see Section C for what a v0.2.0 install to `/usr/local/bin` means for the live service.
- Install to `/usr/local` requires sudo (node3090: lse-admin sudo for this path); the build itself runs as lse-admin with no privilege.

## Section B — What changes: running build vs v0.2.0

- **FROM:** `/opt/llama.cpp/bin/llama-server`, commit `e8f19cc0a`, dated 2026-07-16, self-reported `version 64` (shallow-clone build-number artifact, not a release).
- **TO:** tag `v0.2.0`, commit `bb4caa754`, published 2026-08-21 — the FIRST stable semver release (vX.Y.Z = stable track; b[NUM] = nightly track).
- **SPAN:** 511 commits.

| Area | Commits |
|---|---|
| ui/webui | 71 |
| ggml | 61 |
| model | 50 |
| ci | 49 |
| server | 48 |
| sycl | 39 |
| mtmd | 29 |
| cuda | 24 |
| common | 24 |
| opencl | 22 |
| quant | 22 |
| vulkan | 18 |
| metal | 17 |
| hip | 7 |

Caveat: counts come from `grep -ci` over the 511-line delta file using conventional-commit area prefixes, and prefixes overlap (a commit can match more than one area), so the rows do not sum to 511.

Breaking-change scan: the only breaking flag change in the span is `--mmap` → `--load-mode` (#26934), which node3090 does not use; the launch argv passes `--port 8080` explicitly, so the port-notice change (#26508) is also a non-issue.

### Node-relevant commits (why they matter here)

Node context: dual-GPU RTX 3090 + RTX 5060 Ti, `--tensor-split 3,1`, Qwen3.8-27B UD-Q6_K_XL, KV cache q8_0/q8_0, flash-attn on, ctx 196608.

- #26079 CUDA mvq→MMQ decode crossover tuning per HW+quant — directly affects decode throughput for Q6_K on sm_86; expect a token/s shift, benchmark before/after.
- #26574 CUDA static workspace for cuBLAS handles — reduces per-call allocation churn; relevant with GPU0 sitting ~98% full after load.
- #26993 tensor-split / TP work (commit b2e5e9b28, LFM2/LFM2MOE) — touches the tensor-split path that is LOAD-BEARING on this node.
- #27376 server sleep-mode /metrics access — Prometheus scraping of :8080/metrics keeps working while the server is in sleep mode.
- #27346 `--dedup-cache-models` — new optional flag, not currently used.
- #22877 quantize per-layer memory eviction — only affects local quantize runs, not serving.
- #26508 port notice — informational; the launch argv already passes `--port 8080` explicitly, so no behaviour change.
- #26040 backend split scheduler race fix — stability fix on the multi-backend path this node exercises.
- #27392 FA 'V is view of K' attention build — flash-attn is ON here.

Full 511-commit list: companion file `node3090-llama-delta-e8f19cc0a-v0.2.0.txt` in this same KB directory.

## Section C — Service-safe deploy procedure (execute in a maintenance window, NOT now)

### C1. Pre-deploy checks

- `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health` → 200 (baseline).
- Record baseline tokens/s from `:8080/metrics` before the swap so the #26079 decode-crossover change can be measured.
- `nvidia-smi`: confirm GPU0 (RTX 3090) and GPU1 (RTX 5060 Ti) both visible and mostly free once the old server is down.
- Confirm no in-flight planner requests (node3090 :8080 is the planner local primary, 240s budget).
- Keep the OLD binary: the running server is `/opt/llama.cpp/bin/llama-server` (e8f19cc0a). Back it up before overwriting anything:
  `cp /opt/llama.cpp/bin/llama-server /opt/llama.cpp/bin/llama-server.e8f19cc0a_$(date +%Y%m%d_%H%M%S)`

### C2. Binary placement decision

Section A installs to `/usr/local/bin`. The service currently runs `/opt/llama.cpp/bin/llama-server`. Two options:
- (a) Point the launch command at `/usr/local/bin/llama-server`. Note: `/usr/local/bin/llama-server` today is an unused 18 KB shared-lib stub at b10106 whose libs live in `/usr/local/lib`, so `LD_LIBRARY_PATH` matters.
- (b) Copy the freshly built binary over `/opt/llama.cpp/bin/llama-server` after the backup in C1.

Recommend **(b)** for minimum change to the launch path. Whichever option is chosen must ALSO be reflected in `_NODE_REGISTRY['node3090']['agent_profile']` in `/home/sy5/projects/local-system-engineer/tools/goethe_node.py` — that registry is the source of truth for the launch command (and for `check_node_agent_drift` / `start_node_agent`).

### C3. Restart the main :8080 server

- It has NO systemd unit. It runs as `lse-admin` under `nohup`. The PID at capture time was 6612 — re-check with `pgrep -af llama-server | grep 8080` before killing; do not trust a stale PID.
- Stop: `kill <pid>` (graceful SIGTERM; the log should show `cleaning up before exit`).
- Start (byte-exact, matches the captured argv; reproduce this block exactly):

```bash
nohup /opt/llama.cpp/bin/llama-server \
  --model /opt/models/unsloth/Qwen3.8-27B/Qwen3.8-27B-UD-Q6_K_XL.gguf \
  --port 8080 --host 0.0.0.0 \
  --ctx-size 196608 --n-gpu-layers 99 \
  --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 \
  --parallel 1 --threads 15 --threads-batch 15 \
  --reasoning-format deepseek --jinja --metrics \
  --tensor-split 3,1 --batch-size 2048 --ubatch-size 512 \
  > ~/llama-server.log 2>&1 &
```

- Health gate: poll `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health` until 200 (~10s). A single `cudaMalloc failed: out of memory` line during model load is TOLERATED — GPU0 ends ~98% full and the server still reaches 200.
- `--tensor-split 3,1` is LOAD-BEARING on this dual-GPU node; without it the 25 GB model + 196k ctx does not fit.

### C4. Neural sidecars (lse-emb / lse-rerank)

- lse-emb :8090 (bge-m3) and lse-rerank :8091 (bge-reranker-v2-m3) are separate llama-server processes under systemd, independent of the :8080 main server.
- IMPORTANT — **inactive is their CORRECT steady state**. `lse-sidecar-watchdog.timer` (5-min cadence) runs `/opt/local-se/bin/sidecar-idle-watchdog.sh` and `systemctl stop`s them after ~10 min without traffic. A clean stop logs `cleaning up before exit`. Vanished sidecar PIDs are NOT an incident.
- If the recompiled binary also replaces the sidecars' llama-server, restart them explicitly after the swap: `sudo systemctl start lse-emb lse-rerank`
- Verify the whole chain instead of the units: `curl "http://localhost:8092/search?q=llama server startup procedure"` → JSON results, and both sidecars become active (first hybrid query after idle takes ~7s including startup). Then let the watchdog idle-stop them again — that is expected.

### C5. Post-deploy verification

- `:8080/health` → 200.
- `:8080/metrics` scrapes (Prometheus :9090 job for llamacpp still reporting).
- Confirm the new version: the server startup log line in `~/llama-server.log` reports v0.2.0 (bb4caa754), not e8f19cc0a.
- `nvidia-smi`: GPU0 ~24/24.5 GB used post-load, GPU1 holding its ~6 GB share (tensor-split 3,1).
- Run one real planner request against node3090 :8080 end-to-end (it is the planner local primary, 240s budget).
- Compare tokens/s against the pre-deploy baseline captured in C1 (#26079 changes the decode path).
- `curl "http://localhost:8092/search?q=..."` for the neural chain.

### C6. Rollback

- Kill the new server, restore the pre-deploy binary backup (`/opt/llama.cpp/bin/llama-server.e8f19cc0a_<timestamp>` → `/opt/llama.cpp/bin/llama-server`), relaunch with the exact C3 nohup command, re-gate on `/health` 200.
- Rollback is fast because the model file and all launch flags are unchanged — only the binary moves.
