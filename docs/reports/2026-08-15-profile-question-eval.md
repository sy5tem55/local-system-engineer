# 2026-08-15 — profile-synthesis gold set (v1), authored + validated

> SPEC-profile-question-eval-2026-08 (roadmap item 4). Authoring: Opus +
> operator. Running: LSE. This report covers the AUTHORING half; the LSE runs
> the class-A harness and the class-B by-hand baseline.

## What shipped

`eval/profile-questions-v1.jsonl` — 10 load-bearing rows, deliberately not
padded to 40 (spec §3: "padding the set to hit a number makes the metric
meaningless"). Split by *which mechanism should answer*, which is the whole
point of the spec:

- **Class C (4) — locally probed, `node_facts`.** VRAM per node (node3090,
  node4090, node5090), GPUs on node3090. `expected_value` is absent by
  design: the answer comes from the machine, not the corpus. These encode the
  refusal the project keeps needing — a model asked "how much VRAM does
  node4090 have" says "24GB" from priors; ground truth is the probe
  (24564 MiB, live 2026-08-15). node3090 is the sharp case: 40GiB total
  (24 + 16), and recall answers "24" from the 3090 alone.
- **Class B (4) — spec/web, sourced.** RTX 3090 / 4090 / 5090 memory
  bandwidth (936 / 1008 / 1792 GB/s) and the KV-cache formula. Every number is
  both cited AND verifiable by bus-width arithmetic (e.g. 512-bit × 28 Gbps
  GDDR7 ÷ 8 = 1792) — a stronger check than a bare citation. NOT ONE number
  was taken from memory (spec anti-goal §4); the 5090's GDDR7 value in
  particular was searched, not carried over from GDDR6X-era priors.
- **Class A (2) — retrieval, `search_kb`.** Reuse `retrieval-gold-v1` q01/q02
  (node3090 launch command + flags); their class-A baseline already lives in
  the v1 harness results.

Anchored to the live Qwen3.8-27B deployment decision, so the questions are the
ones Layer 3 actually asks: can a 27B fit across node3090's 40GiB with KV-cache
at context, and does the profile reason about the sm_86/sm_120 arch split
(deploy consideration #1) rather than assuming one GPU.

## Validation (this session)

- All 10 rows parse; spec invariants asserted in code: every class-B row has
  `expected_value` + `tolerance` + `source`; every class-C row has a `probe`
  and NO `expected_value`; every class-A row has `expected` filenames.
- Class-C baseline, live: p02 `node_facts.collect_hardware('node4090')`
  returns `vram_total_mib=24564` (non-null) → probe answers. node3090/node5090
  assertions run when those nodes are awake (node5090 is currently down).

## The "good enough" line (spec §5 — the milestone's definition of done)

The web-search milestone closes when, measured on this set:

- **Class A:** recall@3 ≥ 0.90 on the profile subset.
- **Class B:** ≥ 90% of questions answered within tolerance, each with a cited
  source, in ≤ 3 search results, and **zero fabricated numbers** — a single
  hallucinated unsourced number fails the entire class, because an unsourced
  plausible number is exactly the failure mode being measured.
- **Class C:** 100% routed to a probe and **never searched**; the probe
  returns a non-null value whenever the node is reachable.

## Not done here (LSE / follow-up)

- Class-A harness run over the profile subset and class-B by-hand baseline
  (spec §3.2) — the LSE runs these; publish the numbers before tuning search.
- More class-B rows worth adding once sourced: RTX 5060 Ti bandwidth (the
  node3090 bottleneck leg), quant-selection (coding vs planning vs
  long-context), dense-vs-MoE at fixed VRAM. Left out rather than guessed.

<!-- ACCEPTANCE
task: profile-question-eval
commit: (this commit)
tests_before: n/a (no pytest change)
tests_after: n/a
files_changed: eval/profile-questions-v1.jsonl, docs/reports/2026-08-15-profile-question-eval.md
ruff_clean: n/a (data + docs)
runtime_verified: partial — file validated + class-C probe confirmed live; class-A harness run and class-B baseline are the LSE's to run
-->
