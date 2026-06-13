# Experiment — KV cache V→Q4 @ 128k context (LUCIFER 4090)

> Proposed: P29 Cowork (2026-06-14, SY5). Status: **NOT YET RUN.**
> Owner gate: must run on LUCIFER (RTX 4090 24GB, WSL2) — cannot be run from the Cowork sandbox.

## Canonical baseline (current settings)

`81920` ctx is the empirically-confirmed VRAM sweet spot on **both** the 4090 (LUCIFER)
and node3090 (3090) at current cache settings — **K=q8_0, V=q8_0**. This is the canon the
challenge ground truth (`node-t3-003/004`) asserts. Any `96000` reference in node running-state
docs reflects a pre-cutover state, not the canon.

Ground rule (unchanged): **K cache must stay `q8_0`** — the model breaks below it. **V is the
only lever.** This experiment tests exactly that lever.

## Hypothesis

Dropping V from `q8_0` → `q4_0` roughly halves the per-token V-cache footprint. The freed VRAM
may permit pushing context from 81920 → **128000** within the same 24 GB budget **without** a
meaningful quality regression. If it holds, 128k becomes available for long-context work at no
hardware cost; if quality regresses, fall back to an intermediate V quant or stay at the baseline.

## Test configuration

Keep every other flag at canonical values; change only V-cache type and ctx-size.

```bash
/usr/local/bin/llama-server \
  --model <Qwen3.6-27B-Q4_K_M.gguf> \
  --ctx-size 128000 \
  --n-gpu-layers 129 \
  --flash-attn on \          # REQUIRED for a quantized V cache
  --cache-type-k q8_0 \      # K stays q8_0 — non-negotiable
  --cache-type-v q4_0 \      # the variable under test
  --reasoning-budget 3072 --n-predict 8192 \
  --jinja --metrics --host 0.0.0.0 --port 8080 --threads 8
```

Intermediate fallbacks if `q4_0` regresses quality: `q5_1` → `q5_0` → back to `q8_0` (baseline).

## What to measure

1. **Load / OOM** — does it load at 128k? `nvidia-smi` VRAM at load, and again after filling
   context to ~120k tokens (KV grows with occupancy). Need headroom for the nomic-embed-text
   model (~0.4 GB) + Ollama overhead reservation.
2. **Quality regression** — the decisive metric. Run the **frozen `lse-bench-v1` Condition A**
   at the baseline (K q8_0 / V q8_0 / 81920) vs this config (K q8_0 / V q4_0 / 128000) and compare
   correctness. A McNemar test on the paired per-challenge outcomes tells whether any delta is real
   or noise. (This reuses the same instrument built for the Goethe ascension gate.)
3. **Throughput** — prefill tok/s and decode tok/s at both configs (`--metrics` / server timings),
   since quantized V can shift the compute/bandwidth balance.

## Pass criteria

- Loads at 128k with VRAM headroom at high context occupancy (no OOM under realistic fill).
- Quality within statistical noise of the 81920 baseline (McNemar p not significant, or a delta
  small enough to accept for the context gain).
- Throughput acceptable (no severe decode-rate cliff).

## Rollback

Revert to the canonical launch (K q8_0 / V q8_0 / 81920). One-line: restart with the canonical
flags. No persistent state is changed by the experiment.

## Notes / open questions

- Confirm flash-attn is on — a quantized V cache silently degrades or is rejected without it.
- 128000 is not a round 2^n; confirm llama.cpp does not pad/round it in a way that changes the
  VRAM math.
- If adopting 128k as a new profile, it is a **separate** profile from the 81920 canon, not a
  replacement — the 81920 sweet spot stays the default until this experiment clears it.
