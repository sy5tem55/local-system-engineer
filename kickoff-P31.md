Resume LSE session (P31) from handover. Read session-handover.md (the P30→P31 roll) first, then docs/multi-node-scaling-experiment.md and coding-gauntlet/PYRAMID.md.

State at start of P31:
* DIRECTION: pivoted from the synthetic infra bench to a 4-gate CODING GAUNTLET run as the autonomous LSE-agent curriculum (the path to Goethe). Bench discipline (frozen suite + verify_ssh ground truth + paired McNemar) is repurposed onto coding acceptance tests, not abandoned.
* Cogitator v1.7.23 BUILT, NOT DEPLOYED (black-norm 46051eb3…) — Hermes→LSE by-reference for large payloads; superset of v1.7.22 (poll cap 8→1024). Round-trip verified offline. Rollback per backups/ROLLBACK-cogitator.md.
* RAG S2 built + offline-verified: eval/retrieval-gold-v1.jsonl (50 pairs), rag/eval_retrieval.py (recall@1/@3+MRR, --self-test passes), hybrid RRF search_kb staged in rag/rag_tools_v2.py — SHIP-GATED on --compare beating linear; includes S2.4 cosine-floor fix.
* Per-node lineup converged: node5090(32GB)=Qwen3-Coder-30B-A3B coder · LUCIFER(24GB)=Qwen3.6-27B planner (deployed) · node3090(24GB)=GLM-4.7-Flash cross-family critic. OPEN: node3090 GPU is committed to Hermes's 27B — can't co-host GLM; resolve before shootout.

Immediate tasks (priority order):
1. Deploy Cogitator v1.7.23 to OWUI; verify black-norm 46051eb3…; re-stage hermes-skill/ to node3090 /tmp/lse-channel.
2. Run rag/eval_retrieval.py --compare → if RRF beats linear, port hybrid search_kb into Cogitator (v1.7.24); else keep linear and record it.
3. Commit all P30 work from WSL2 (see handover for file list); rotate session-handover-P30.md → session-handover.md.
4. Resolve node3090 GPU contention (Hermes 27B vs GLM critic).
5. Commission node5090 per docs/node5090-deployment-design.md; fetch Qwen3-Coder-30B; smoke test (node5090-t1/t2/t3).
6. Run the ONE pragmatic shootout (multi-node doc §5): Qwen3-Coder-30B vs 35B-A3B on node5090 + does the GLM critic lift the result. Then build Gate 1 (Terminal Confidant) as the curriculum's first challenge.

North star — Goethe ascension: Cogitator becomes Goethe when the LSE writes its own skills + wields RAG competently AND out-delivers on the work that matters. Honest ceiling on consumer hardware: ~70% of frontier on benchmarks, ~90% on routine work, falling off on the hard long-horizon tail. We don't win the frontier head-to-head — we win the economics (free, local, private, relentless, learning). The gauntlet proves it; the give-up budget keeps it honest.

Ground rules: LARGE .py → BASH (ast.parse + line tally, never Write/Edit). .md → host Read/Write/Edit, not sandbox bash (stale reads). Deploy identity = black-norm sha. Sudo surfacing via post-<think> reply. Commit from WSL2 only. K cache Q8_0. ctx 81920 canon. NEW: MoE VRAM = total params not active (GLM-4.7-Flash ≈ 24GB; Kimi K2.5 = 1T = server-only). Cost = GPU-seconds not wall-clock. Cross-family is the heterogeneity lever, not intra-family size. Every agentic loop gets a give-up budget. Gauntlet stack = TypeScript across gates 1–3; orchestration = mention-+-reply behind a swappable SpeakerPolicy.
