# Experiment — Extending usable context on LUCIFER (4090) via KV-cache quantization

> Proposed P29, rewritten P31 (2026-06-14) as a falsifiable experiment.
> Status: **NOT YET RUN.** Must run on LUCIFER (RTX 4090 24 GB, WSL2) — not from the Cowork sandbox.
> Method: Galilean — isolate one variable, predict before measuring, let the measurement falsify.

---

## 0. Observation that motivates this

On Gate 2 of the coding gauntlet, the LSE agent (Qwen3.6-27B) hit **~75k of its 80k context
window** and had to self-hand-over mid-task. The ceiling that stopped it was **context length,
not coding capability** — it wrote a correct realtime server, it just ran out of window to hold the
whole task. So the decision-relevant question is narrow and practical:

> Can we extend the *usable* context of the deployed 27B on a single 24 GB 4090 — far enough to
> hold a whole gate without a handover — **without** a quality regression we'd actually notice?

Two levers exist. This doc tests both, in order of risk.

---

## 1. Background facts (the constraints the experiment lives inside)

- **Canonical baseline:** `ctx 81920`, **K=q8_0, V=q8_0**, the empirically-confirmed VRAM sweet
  spot on the 4090 and node3090. This is the ground-truth canon (`node-t3-003/004` assert it).
- **The K-floor rule:** with *naive* llama.cpp quantization, **K must stay `q8_0`** — the model
  breaks below it. V is the only lever. (This rule is specific to naive scalar quant; see §Arm B,
  which dissolves it.)
- **Flash attention is mandatory** for any quantized V cache — a quantized V silently degrades or
  is rejected without `-fa on`.
- **Cost is GPU-seconds, not wall-clock; capacity ≠ compute.** Report quality *vs* throughput.
- **Field data (llama.cpp #20969, naive `q4_0` KV on a 30B-class model):** `q4_0` KV cut KV memory
  ~72% vs fp16, prompt throughput unaffected, but **decode throughput degraded ~37% at ~110k**
  context from per-token dequant. Expect a decode cliff at depth, not a memory problem alone.

---

## 2. Hypotheses & falsifiable predictions (commit before running)

**H1 (Arm A — naive VQ4):** dropping V `q8_0→q4_0` frees enough VRAM to run `ctx 131072` on the
24 GB 4090 with the 27B Q4_K_M, with no quality regression noticeable on real work.

**H2 (Arm B — TurboQuant):** rotation-based 3-bit K+V (`turbo3`) on an experimental fork breaks the
K-floor entirely, fits *far* more context (256k+ demonstrated on smaller cards), and — *if* quality
holds — strictly dominates VQ4.

Predictions, stated so the experiment can prove them wrong:

- **P1 (fit, falsifiable):** Arm A *loads* at 131072 but with **tight headroom (<~2 GB free)**, so it
  risks OOM at high context occupancy and likely needs a fallback to ~110–120k. (Falsified if it
  loads with comfortable headroom, or if it OOMs at load outright.)
- **P2 (short-task quality):** on **short** tasks (Gate 2 re-run, `lse-bench-v1` Condition A), Arm A
  shows **no** measurable regression vs baseline (McNemar n.s.). VQ4 error doesn't show on short work.
- **P3 (deep-context quality — the real test):** on **deep-context reasoning** (occupancy > ~64k),
  Arm A shows a **measurable** degradation vs KQ8/VQ8 in the overlapping depth range — accumulated
  V-cache error surfaces only here. *This is the prediction the short tests cannot see, and the one
  that decides the experiment.*
- **P4 (throughput):** Arm A decode throughput degrades materially at depth (order ~30% by ~110k),
  per the field data. Prompt/prefill throughput roughly unaffected.
- **P5 (Arm B):** `turbo3` on the `sm_89` CUDA fork loads at ≥ 200k ctx with comfortable headroom;
  quality on the deep-reasoning eval is the **open risk** (contested in the wild — one tester found
  `turbo3` worse than `q4_0` perplexity; others report PPL within ~1–2% of fp16). Arm B is adopted
  only if it clears the *same* deep-reasoning bar as Arm A, on our model.

---

## 3. Controls (isolate the variable)

Change **only** the V-cache type and ctx-size between baseline and Arm A; hold every other launch
flag at canonical values. For quality, two regimes keep context-length from contaminating the
V-quant signal:

- **Overlap region (depth ≤ 81920):** compare **VQ4@131072 vs VQ8@81920 on identical inputs** —
  same depths, only V-quant differs → isolates the V-cache effect (paired McNemar).
- **Extension region (81920 < depth ≤ 131072):** no VQ8 baseline can exist there (that's *why* we
  quantize V), so score **VQ4 vs ground-truth absolute correctness** — this measures whether the
  extra context is *usable at all*, not just whether it fits.

---

## 4. Materials

### Arm A — naive KQ8/VQ4 on the **current mainline** build (Joe's profile)

```xml
<profile name="Qwen3.6 27B · Q4_K_M  [128k · q8_0]">
  <CtxSize>131072</CtxSize>          <!-- 128*1024, clean; resolves the old 128000 rounding worry -->
  <GpuLayers>129</GpuLayers>          <!-- offload all -->
  <FlashAttn>true</FlashAttn>          <!-- REQUIRED for quantized V -->
  <CacheTypeK>q8_0</CacheTypeK>        <!-- K stays at the floor -->
  <CacheTypeV>q4_0</CacheTypeV>        <!-- the variable under test -->
  <Threads>7</Threads> <ThreadsBatch>7</ThreadsBatch> <Parallel>1</Parallel>
  <ReasoningBudget>3072</ReasoningBudget> <MaxPredictTokens>8192</MaxPredictTokens>
</profile>
```
Intermediate fallbacks if VQ4 regresses or OOMs: ctx `122880`/`114688`/`98304`, or V `q5_1 → q5_0`.
**Never** drop K below `q8_0` in Arm A.

### Arm B — TurboQuant `turbo3` on an **experimental fork** (separate, non-production build)

- TurboQuant is **not** in mainline llama.cpp (only a discussion). Build from a CUDA fork. Closest
  arch match to Ada is the **RTX 3090 (Ampere) fork**: `spiritbuun/llama-cpp-turboquant-cuda`
  (branch `feature/turboquant-kv-cache`); upstream-of-it is `TheTom/llama-cpp-turboquant`.
- Build for Ada: `cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DGGML_CUDA_FORCE_CUBLAS=OFF`.
  **Use CUDA 12.8, not 13.1** (reported MMQ-kernel segfault). `turbo3` **requires `-fa on`**.
- Launch: `… -c 262144 -fa on -ctk turbo3 -ctv turbo3 …`. Validation on the wild: Qwen3.5-27B on a
  5090 → NIAH 6/6, ~14 KB/token (4.6× vs fp16); Qwen3.5-35B @ 262144 ctx on a 16 GB 5080 at ~65 tok/s.
- **Keep production on mainline** until Arm B clears the deep-reasoning bar. Arm B is an evaluation
  build, not a deploy, until proven.

---

## 5. Procedure

1. **Load / OOM ladder (Arm A).** Launch the profile. Record `nvidia-smi` VRAM at load. Fill context
   toward ~120k (KV grows with occupancy) and record VRAM again. If `cudaMalloc … out of memory` at
   load or under fill → step down ctx per the fallback ladder until it holds with headroom for
   nomic-embed-text (~0.4 GB) + overhead. **The first stable ctx is data point #1 (tests P1).**
2. **Functional check (Arm A).** Re-run **Gate 2** against the profile (sync the harness first:
   `cp "$REPO/gate2-group-server/test/acceptance.test.ts" ~/cg2/gate2-group-server/test/`, then
   `npm test` + `GATE2_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test`). This proves the
   config *generates correctly end-to-end* — but it is a **short-interaction** test and does **not**
   probe deep-context quality (tests P2 only).
   - ⚠ Live-test latency: `ReasoningBudget 3072` means even "say hi" may emit a long `<think>`; at
     cold-128k decode speed that can exceed the live test's ~30s poll. A timeout here is **latency,
     not breakage** — bump the poll or warm the model first. Also `model_live.ts` caps
     `max_tokens:256` (`stream:false`); if reasoning eats the 256 and returns empty content the
     schema rejects it. Recognize these as harness/latency artifacts, not VQ4 failures.
3. **Deep-context reasoning eval (Arm A, then Arm B) — the decisive test (P3/P5).**
   - **Probe corpus:** assemble inputs that fill the window to **32k / 64k / 96k / 120k** tokens
     (e.g. a large real codebase or concatenated docs). Plant, at known depths, (a) **retrieval
     needles** (a unique fact) and (b) **reasoning chains** that require combining ≥2 facts placed
     far apart (e.g. fact at 20k + fact at 95k → compute/derive a third). Reasoning chains are what
     accumulate V-error; pure needles are not enough.
   - **Run** the identical probe through: baseline (KQ8/VQ8@81920, depths ≤ 81920 only), Arm A
     (VQ4@131072, all depths), and Arm B (turbo3, all depths).
   - **Score** correctness per depth bucket. Overlap region → paired diff Arm A vs baseline.
     Extension region → absolute correctness vs ground truth.
4. **Throughput (all arms).** `--metrics` / server timings: prefill tok/s and **decode tok/s at each
   depth bucket** (decode is where the quantized-V cliff shows — tests P4).
5. **Perplexity (coarse cross-check).** `llama-perplexity` over a long held-out text at each config;
   report PPL delta vs fp16/baseline. (Coarse — necessary not sufficient; reasoning eval is primary.)

---

## 6. Measurement table (fill in)

| Config | Loads @ctx | VRAM @load | VRAM @~120k | Prefill tok/s | Decode @8k / @64k / @120k | Short-task (Gate2/benchA) | Deep-reason ≤81920 (vs base) | Deep-reason >81920 (abs) | PPL Δ |
|---|---|---|---|---|---|---|---|---|---|
| Baseline KQ8/VQ8 @81920 | — | | | | | | (ref) | n/a | (ref) |
| **Arm A** KQ8/VQ4 @131072 | | | | | | | | | |
| Arm B turbo3 @262144 | | | | | | | | | |

---

## 7. Decision rule

- **Adopt Arm A as a *new, separate* 128k profile** (the 81920 canon stays default) **iff** it loads
  with headroom under fill AND deep-reasoning correctness in the overlap region is within statistical
  noise of baseline AND extension-region correctness is high enough to be useful AND no
  unacceptable decode cliff. If deep-reasoning regresses (P3 confirmed), keep VQ4 for *short*
  high-context tasks only, or fall back to an intermediate V quant.
- **Adopt Arm B** only if it clears the **same** deep-reasoning bar on our model and the fork is
  stable enough to depend on. Until then it is an evaluation build.
- **Null result is a result:** if neither beats baseline on deep reasoning, the honest finding is
  "81920 KQ8/VQ8 remains the sweet spot; the context ceiling is addressed by task decomposition +
  handover discipline + the cross-family critic, not by raw KV extension." Record it and move on.

---

## 8. Honest caveat (don't let "it fits" masquerade as "it works")

Even at 256k, a 27B reasoning over 200k tokens is still a 27B — "lost in the middle" means raw
context is not free capability. The real win on offer here is letting the agent **hold a whole gate
without a handover** (which directly fixes the Gate-2 wall) — *not* closing the long-horizon
reasoning gap. That gap is still the job of decomposition and the GLM critic. Measure what the
extension buys (no-handover working memory), and don't over-claim it as reasoning headroom.

## 9. Rollback

Revert to the canonical launch (K q8_0 / V q8_0 / 81920) — one restart with canonical flags. The
experiment changes no persistent state. Arm B lives in a separate build dir and never touches the
production binary.

## 10. Run log

### Arm A, rung 1 — KQ8/VQ4 @ 96000, on the PRODUCTION OWUI/Cogitator server (P31, 2026-06-14)

Profile: `ctx 96000, K q8_0, V q4_0, FlashAttn on, Parallel 1, reasoning-budget 3072`.

- **Fit (P1): PASS.** `nvidia-smi` at load = **20,639 / 24,564 MiB (~3.8 GB free)**. KV is pre-allocated
  at load, so headroom is real. 131072 projects to ~22 GB (~2.5 GB free) — would fit, tight.
- **Short-task functional (P2): PASS.** Gate 2 = **9/9**, live reply in **4.4 s** — but on a *tiny*
  prompt ("say hi").
- **Large-context (the catch): FAIL — prefill cliff.** On Cogitator's real ~31k-token context the
  slot stalled: prompt processing **282 → 132 → 88 → 67 → 55 tok/s and falling** with depth; the
  model never reached generation; **~10-minute hang**, and on `Parallel 1` it jammed the single slot
  so all production traffic queued and cancelled (the LSE agent was effectively down). Rolled back to
  canonical `81920 / VQ8`.
- **Finding (preliminary):** VQ4's cost is **depth-dependent** — cheap on small prompts, explodes as
  the window fills. Self-defeating for an agent that ingests ~31k (system prompt + tools + RAG) every
  turn — exactly the 8–30k band the cliff hits. Memory was never the constraint; **prefill speed is.**
- **Confounds (why this isn't yet carved in stone):** (1) run on the contended `Parallel 1`
  production server; (2) ctx *and* V-quant changed together vs baseline. 
- **Clean confirmation needed:** offline `llama-bench`, GPU isolated, one variable at a time —
  `llama-bench -m <model> -fa 1 -ngl 129 -p 4096,16384,32768 -n 0 -ctk q8_0 -ctv q8_0|q4_0`. If VQ4 `pp`
  craters vs VQ8 at the same ctx, V-quant is the cause and Arm A is dead-on-arrival for this agent →
  go to Arm B (TurboQuant, near-`q8_0` prefill) or stay at 81920 and solve the ceiling with
  decomposition + the critic.
- **Decision so far:** **81920 KQ8/VQ8 remains the production default** (battle-tested). Arm A is
  parked pending the isolated `llama-bench` A/B.

## Sources (Arm B feasibility)

- llama.cpp Discussion #20969 — TurboQuant (Qwen 27B/35B on consumer GPUs, fork pointers, PPL caveats):
  https://github.com/ggml-org/llama.cpp/discussions/20969
- Forks: https://github.com/spiritbuun/llama-cpp-turboquant-cuda · https://github.com/TheTom/llama-cpp-turboquant
- Method overview (rotation + codebook, 3-bit K / 2-bit V):
  https://kaitchup.substack.com/p/turboquant-finally-fast-and-widely
