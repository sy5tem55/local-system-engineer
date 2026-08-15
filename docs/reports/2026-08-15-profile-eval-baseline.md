# Profile-Synthesis Eval Baseline (SPEC-profile-question-eval, item 4)

Run: 2026-08-15T13:56–14:10Z · node4090 (LUCIFER) · gold set: eval/profile-questions-v1.jsonl (10 rows)
Method: class C = live node_facts/nvidia-smi probes only (zero search, zero recall); class B = search_kb → search_web → fetch_url → verify_source_claims (every asserted number has a cited source); class A = rag/eval_retrieval.py --mode rrf against lse-kb (ES 9.4.3).

| id | class | mechanism used | answer | sourced? | matches expected? | notes |
|----|-------|----------------|--------|----------|-------------------|-------|
| p01 | C | node_facts.collect_hardware('node3090') (SSH probe, 13:56:21Z) | 40887 MiB total ≈ 39.9 GiB (24576 + 16311) | YES (live probe) | YES — gold note says ~40 GiB | dual-GPU SUM: RTX 3090 24576 MiB + RTX 5060 Ti 16311 MiB. A "24GB from the 3090 alone" answer is the priors-not-probe error this row tests; probe returns both. |
| p02 | C | node_facts.collect_hardware('node4090') (local probe) | 24564 MiB ≈ 24 GiB | YES (live probe) | YES — gold note's own 2026-08-15 probe value, exact match | source=local-probe. |
| p03 | C | node_facts probe → UNREACHABLE (stale registry) → wake_node (already up) → live nvidia-smi probe via KB-verified SSH access | 32607 MiB ≈ 31.8 GiB GDDR7, driver 610.88 | YES (live probe) | YES — gold note says ~32 GiB | NOT a NULL: node was up (ping OK); the named probe path failed because _NODE_REGISTRY still says ssh_user: sy5 (registry is _stale). Probed successfully as lse-admin with key id_ed25519_node5090 (KB 317298c5dbba1e57). Registry drift = finding, see below. |
| p04 | C | node_facts gpu[*].name probe + supplementary nvidia-smi compute_cap probe on node3090 | RTX 3090 (compute_cap 8.6 → sm_86) + RTX 5060 Ti (12.0 → sm_120) | YES (live probe) | YES — gold note: sm_86 + sm_120 | arch values from live compute_cap probe, not recall; confirms why build needs explicit CMAKE_CUDA_ARCHITECTURES=86;120. |
| p05 | B | search_kb HIT (doc 27d5734767f4a144, q0.75) + fetch of official NVIDIA 30-series spec page | 936 GB/s | YES | YES — exact (936 ±2%) | 0 web searches (KB hit ≥0.6) + 1 fetch. NVIDIA page verify: 384-bit FOUND, 24 GB GDDR6X FOUND, CUDA 8.6 FOUND; literal "936 GB/s" NOT_FOUND on NVIDIA page (derived figure) — number sourced from KB doc → runaihome.com (cites NVIDIA official spec). Deliberately did NOT state the 19.5 Gbps derivation input (uncitable from fetched page). |
| p06 | B | KB miss → search_web (1) → fetch spheron 5090 page (comparison table) + TechSpot/TechPowerUp snippets | 1008 GB/s | YES | YES — exact (1008 ±2%) | 1 search needed. Top result 403 (gigagpu.com), TechSpot 403 on fetch. Verified FOUND: "RTX 4090 24GB GDDR6X 1,008 GB/s" on spheron table; TechPowerUp snippet gives inputs (384-bit, 21 Gbps eff). |
| p07 | B | KB miss → search_web (1) → fetch spheron (row source) + TechPowerUp snippet (2nd independent source) | 1792 GB/s | YES | YES — exact (1792 ±2%) | 1 search needed. verify FOUND on spheron: 1,792 GB/s / 512-bit / 32GB GDDR7; TechPowerUp snippet: 32 GB GDDR7, 512-bit, 28 Gbps effective (512×28/8=1792). GDDR7 jump, no GDDR6X carry-over. |
| p08 | B | KB has worked examples (doc b5edefe6fa66e7d9, q0.90) but no general formula → search_web (1) → fetch lyceum.technology KV-calc guide | KV bytes ≈ 2 (K and V) × n_layers × n_kv_heads × head_dim × ctx × bytes_per_elem; fp16/bf16 = 2 B/elem, 8-bit (q8_0) ≈ 1 B/elem | YES | YES — formula exact | 1 search needed. verify FOUND verbatim: GQA formula "2 * layers * kv_heads * head_dim * seq_len * batch_size * bytes_per_element", MHA variant, "FP16 or BF16 … 2 bytes", "For FP8, it is 1 byte". No worked numbers asserted (tolerance requires model config for those); local cross-check anchor: KB worked example ~135 KB/token q8_0 (Qwen3.8-27B, 64 layers). GQA caveat stated: n_heads instead of n_kv_heads overestimates. |
| p09 | A | rag/eval_retrieval.py --mode rrf (reuses retrieval-gold-v1 q01) | rank 1 → node3090-llama-launch.md | n/a (retrieval) | YES (rank 1) | Gold note claims this is "the classic retrieval miss" — live measurement 2026-08-15: rank 1. Note appears stale. |
| p10 | A | rag/eval_retrieval.py --mode rrf (reuses retrieval-gold-v1 q02) | rank 2 (in @3) → node3090-llama-launch.md | n/a (retrieval) | YES (rank 2, within @3) | Full-set context: recall@1=0.82, recall@3=0.94, MRR=0.882 (50 rows). |

## Summary
**Class C: 4/4 probed correctly** (all live, zero recall; p03 required wake + KB-verified key after a stale-registry probe failure). **Class B: 4/4 sourced within tolerance with zero uncited numbers** (each answer has a fetched or KB-cited source; verify_source_claims ran for every fetched page).

## Findings for operator review
1. **node_facts/_NODE_REGISTRY drift on node5090** (goethe_node.py): registry says `ssh_user: sy5`, `agent_type: lmstudio`, flagged `_stale` (2026-07-29). The named class-C probe `collect_hardware('node5090')` fails on an up, healthy node; correct access is lse-admin + `~/.ssh/id_ed25519_node5090` (KB 317298c5dbba1e57, q0.80) and the fleet has moved to llama-server. Registry migration needed before the next class-C run.
2. **Gold note p09 stale**: q01 "classic retrieval miss" no longer reproduces (live rank 1).
3. **Separate retrieval finding (outside this eval's rows)**: q46 "node3090 performance tokens per second on the 3090" is a MISS in the live gold run (got llama.md / node3090-llama-build.md / quickstart; want node3090-llama-launch.md).

No files under eval/ or docs/ were touched; nothing committed or pushed.

---

## Reviewer verification (Claude, 2026-08-15)

Verified against ground truth, not the LSE's summary:
- **node5090 confirmed up** (ping 1.3 ms) — p03 (32607 MiB) is a real live probe, not a recalled "32 GB". The recursive class-C priors-vs-probe test PASSED on the hardest row.
- **Registry drift confirmed** in `tools/goethe_node.py`: node5090 block has `agent_type: "lmstudio"`, `ssh_user: "sy5"`, `_stale` flag dated 2026-07-29. Finding #1 is accurate.
- **KB doc `971efc5e9f7ada50`** (bandwidth reference) reviewed: 3090/4090/5090 table with correct bus widths, matches the gold set, primary tier / 0.75. Legitimate.
- Class-B answers (936/1008/1792 + KV formula) match the gold `expected_value`s.

### Caveat — Class-B baseline is confirmatory, not blind (reviewer design flaw)
The delegation had the LSE `read_file` the full gold set, which contains `expected_value` for every Class-B row — so the model knew the targets. Its per-row citations (independent sources, honest 403 notes, derived-vs-literal distinction on p05) show genuine search rather than parroting, but "Class B 4/4 within tolerance" is a **confirmatory** measurement, not blind. A rigorous Class-B number requires a v2 driver that presents only `query`, never `expected_value`. **Class C is clean** (no `expected_value` in the file; the probe returns ground truth), and it is the more important half.

### Milestone status vs the "good enough" line
- Class C: 4/4 routed-to-probe, 100% — **meets** the bar.
- Class A: recall@3 = 0.94 — **meets** the ≥0.90 bar.
- Class B: process sound, but the number is confirmatory — **needs a blind v2 re-run** to claim the ≥90% bar rigorously.

### Follow-ups
1. Migrate node5090 in `_NODE_REGISTRY`: `ssh_user` → `lse-admin`, key `id_ed25519_node5090`, `agent_type` lmstudio → llama-server, drop `_stale`. (goethe_node.py is mirror-watched; goes live on gateway restart.)
2. Refresh gold note p09 — q01 is no longer "the classic miss" (live rank 1).
3. Investigate q46 retrieval miss (node3090 t/s → returns build.md, want launch.md) — separate, in the full retrieval-gold set.
