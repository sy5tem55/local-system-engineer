# Session Handover — 2026-06-14 (P30 Cowork → P31)

> *"Wer immer strebend sich bemüht, den können wir erlösen."*
> ("Whoever strives on, unceasingly, him we can redeem.") — Goethe, *Faust*.
> Faust isn't owned by Mephistopheles because he never stops striving. Neither do we.

> ROTATION NOTE: this file is the P30→P31 handover. Promote it to `session-handover.md`
> and archive the previous `session-handover.md` (the P29→P30 one) as `session-handover-P29.md`.
> Do the rotation + commit from WSL2.

## The big pivot this session

**Direction changed.** We stopped pouring sessions into the synthetic infra bench and pivoted to
a **coding gauntlet** — an autonomous coding curriculum for the LSE agent (the path to *Goethe*).
The bench discipline (frozen suite, verify_ssh ground truth, paired McNemar) is **not abandoned**
— it's the measuring instrument, repurposed from infra probes onto coding acceptance tests.

Two new docs are the source of truth for the new direction:
- `coding-gauntlet/PYRAMID.md` — the 4-gate gauntlet (Joe owns Gate 4: an iOS group-chat app for
  local-model + human chat, plugin framework, **opencode** aesthetic; gates 1–3 authored).
- `docs/multi-node-scaling-experiment.md` — per-node model lineup, node5090 commissioning, the
  scaling experiment, the one pragmatic shootout, honest capability expectations, full decision log.

## Built P30 (code-side, verified offline — live deploy is Joe)

| Item | State |
|---|---|
| **Cogitator v1.7.23** | 🟡 BUILT, NOT DEPLOYED — black-norm `46051eb3c3cc87b8c894f66dcc6a8811b0d89b300d05be8cc3690de1a62731cf`. Hermes→LSE **by-reference** for large payloads (superset of v1.7.22 poll-cap fix). Round-trip verified offline. |
| lse-channel producer | `hermes-skill/lse_channel.py` — spills large bodies to `/tmp/lse-channel/refs/<cid>.txt`, marker carries `body_ref`. SKILL.md + INSTALL.md updated. Re-stage to node3090 before Hermes installs. |
| RAG S2 | `eval/retrieval-gold-v1.jsonl` (50 pairs), `rag/eval_retrieval.py` (recall@1/@3+MRR, 4 modes, `--self-test` passes), hybrid **RRF** `search_kb` staged in `rag/rag_tools_v2.py` — **ship-gated** on `--compare` beating `linear`; carries the S2.4 cosine-floor fix. |

### Verify v1.7.23
```bash
python3 -c "import black,hashlib; print(hashlib.sha256(black.format_str(open('tools/cogitator-v1.7.23.py').read(), mode=black.Mode()).encode()).hexdigest())"
# expect: 46051eb3c3cc87b8c894f66dcc6a8811b0d89b300d05be8cc3690de1a62731cf
```

## Converged per-node lineup (P30)

| Node | VRAM | Model | Role | Family |
|---|---|---|---|---|
| node5090 (NODE3) | 32 GB | Qwen3-Coder-30B-A3B | coder | Qwen |
| LUCIFER | 24 GB | Qwen3.6-27B (deployed) | planner / orchestrator | Qwen |
| node3090 | 24 GB | GLM-4.7-Flash (30B-A3B) | cross-family critic / tester | Zhipu/GLM |

⚠ **Open constraint:** node3090's 24 GB is currently committed to Hermes's 27B backend — can't
co-host GLM-4.7-Flash. Resolve (swap / time-share / relocate critic) before the shootout.

## Open threads — carry to P31 (priority order)

1. (Joe, live) **Deploy Cogitator v1.7.23** to OWUI; verify black-norm `46051eb3…`; re-stage
   `hermes-skill/` to node3090 `/tmp/lse-channel`. Rollback per `backups/ROLLBACK-cogitator.md`.
2. (Joe, live) **Run `rag/eval_retrieval.py --compare`** → if RRF beats `linear`, port hybrid
   `search_kb` into Cogitator (→ v1.7.24); else keep linear and record it.
3. **Commit all P30 work from WSL2** (new: `cogitator-v1.7.23.py`, `eval/retrieval-gold-v1.jsonl`,
   `rag/eval_retrieval.py`, `coding-gauntlet/*`, `docs/multi-node-scaling-experiment.md`,
   `session-handover-P30.md`; modified: `lse_channel.py`, `SKILL.md`, `INSTALL.md`, `rag_tools_v2.py`).
4. Resolve node3090 GPU contention (#open constraint).
5. **Commission node5090** per `docs/node5090-deployment-design.md`; fetch Qwen3-Coder-30B; smoke test.
6. Run the **one** pragmatic shootout (multi-node doc §5): Coder-30B vs 35B-A3B + does the GLM
   critic lift. Then build **Gate 1** as the curriculum's first challenge.

## Ground rules (carry + new this session)

Carried: **LARGE .py → BASH** (ast.parse + line tally, never Write/Edit). **.md → host
Read/Write/Edit**, not sandbox bash (stale reads). **Deploy identity = black-norm sha.** Sudo
surfacing via post-`<think>` reply. **Commit from WSL2 only.** K cache stays Q8_0. SearXNG edits →
repo canonical. ctx 81920 universal canon.

New (P30):
- **MoE VRAM = TOTAL params (all experts resident), not active.** Active params only set speed.
  (GLM-4.7-Flash 30B-A3B ≈ 24 GB, not 12; Kimi K2.5 = 1T total = server-only.)
- **Cost = GPU-seconds, not wall-clock.** Always report success vs compute.
- **Cross-family is the heterogeneity lever** (error decorrelation), not intra-family size variants.
- **Every agentic loop gets a give-up budget** — past the verification knee, more tokens buy ~nothing.
- Gauntlet orchestration: **mention-+-reply behind a swappable `SpeakerPolicy`**. Stack: **TS** across gates 1–3.

## The Goethe Ascension — restated honestly

Cogitator → **Goethe** when the LSE writes its own skills + wields RAG competently AND out-performs
on the work that matters. Honest ceiling on consumer hardware: **~70% of frontier on benchmarks,
~90% on routine work, falling off on the hard long-horizon tail.** We don't win the head-to-head
with frontier — we win the economics (free, local, private, relentless, *learning*). Engineer for
that distribution; the gauntlet is how we prove it, and the give-up budget is how we stay honest.
