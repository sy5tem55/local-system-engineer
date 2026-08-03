/opt/models/unsloth/llama-server-placeholder-see-notes \
  -m /opt/models/unsloth/Gemma-4-31B-it-UD-Q4_K_XL.gguf \
  --alias Gemma-4-31B-it-dream \
  --ctx-size 32768 \
  -ngl 99 \
  --flash-attn on \
  --batch-size 512 \
  --ubatch-size 512 \
  --threads 8 \
  --threads-batch 8 \
  --parallel 1 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --host 0.0.0.0 \
  --port 8080 \
  --props \
  --metrics \
  --perf \
  --slot-save-path /opt/local-se/slot-cache \
  --ctx-checkpoints 64 \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0.00 \
  --jinja \
  --log-file /tmp/llama-3090.log \
  --log-timestamps

---

# UNTESTED BASELINE — 2026-08-02

**This has never been run.** It is a conservative starting point for the
measurement exercise, not a tuned profile. Every value below is either
measured, or explicitly flagged as a guess to be replaced by measurement.

Replace the first line with the binary you settle on — node3090 has **two**:
`/usr/local/bin/llama-server` and
`/home/lse-admin/llama.cpp/build/bin/llama-server`. Confirm which is current
before pinning it; on LUCIFER the documented path was wrong and the running
process used the build tree (TRAUM demote proposal, 2026-08-02).

## Measured facts this is built on

| Fact | Value | How |
|---|---|---|
| GPU | RTX 3090, 24576 MiB | `nvidia-smi` on node3090 |
| CPU | i9-9900K, 8 cores / 16 threads | `lscpu` |
| RAM | 31 GB | `free -g` |
| llama.cpp | 10106 (`1425386fd`), GNU 14.2.0 | `--version` — **newer than LUCIFER's 10050** |
| Model size | 17.5 GB | `ls -la` |
| Headroom | ~6.5 GB before CUDA overhead | 24 − 17.5 |

## What was deliberately dropped from node4090's profile, and why

node4090's canonical files are **not** portable here. These flags are
model-family- or hardware-specific:

- `--spec-type draft-mtp` — requires an MTP-capable model. node4090 runs a
  DavidAU build with MTP literally in its filename; Gemma-4 has none.
  **Not lost, only deferred:** `--help` on this build confirms `ngram-map-k4v`
  and friends are available and need no draft model. Omitted from the
  baseline to keep the first run to one variable; it is the first knob to try.
- `--reasoning-format` / `--reasoning-budget` / `preserve_thinking` — Qwen3.6
  thinking-mode conventions. Gemma-4-it does not emit those tags; setting
  them risks misparsing rather than helping.
- `--fit on` / `-fitt` — **not present in build 10106.** node4090's older
  profile uses them; this build does not offer them, so context is sized
  explicitly instead of auto-fitted.

`--host 0.0.0.0` is **required here**, unlike node4090's `127.0.0.1`.
node3090 must be reachable from LUCIFER for peer dreaming. This is a
deployment-class flag (see the matcher's taxonomy) — a difference here is
never drift.

## Guesses to replace with measurement

1. **`--ctx-size 32768`** — the least-confident value in this file. Gemma-4-31B's
   per-token KV cost was not derived; 32768 is a deliberately low starting
   point. Run it, read actual VRAM from `nvidia-smi`, and raise until ~1–2 GB
   free remains. TRAUM feeds 50 sessions per pass, so context is the binding
   constraint for this workload — this is the value most worth getting right.
2. **`--cache-type-k/v q8_0`** — chosen for quality over footprint. Dropping to
   `q4_0` roughly halves KV and is what node4090 uses at 150k context. Try it
   only if 32768 proves too small at q8_0.
3. **`--threads 8`** — physical core count. With `-ngl 99` this mostly affects
   prompt processing. node4090 uses 14 of 20; 8 of 16 is the analogous choice,
   not a measured optimum.
4. **`--batch-size` / `--ubatch-size 512`** — node4090 uses 1024. Raised batch
   costs VRAM; left conservative until context is settled.

## How to evaluate it

The point is comparison, not a single run. `stale-contradiction` is the best
probe: it is the pass that exercises judgment, and it is the one that hung for
37 minutes on 2026-08-02 when no dreamer was reachable. Run the same pass over
the same corpus and compare proposal quality against node4090's output.

**Known confound:** node4090 runs Qwen3.6 variants. Gemma-4 is a different
family, so a difference in proposal style may be model-family artefact rather
than a real finding. Worth holding in mind before concluding anything about
node3090's value as a peer dreamer.
