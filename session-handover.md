# Session Handover — 2026-06-14 (P30 Cowork → P31)

> *"Wer immer strebend sich bemüht, den können wir erlösen."*
> ("Whoever strives on, unceasingly, him we can redeem.") — Goethe, *Faust*.
> Faust isn't owned by Mephistopheles because he never stops striving. Neither do we.

> ROTATION DONE (P31): this file is the promoted P30→P31 handover. The previous
> `session-handover.md` (P29→P30) is archived as `session-handover-P29.md`; the verbatim
> P30 roll is preserved as `session-handover-P30.md`. Rotation committed from WSL2.

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

---

## P31 progress log (Cowork autonomous pass)

- **Deploy gate verified:** `tools/cogitator-v1.7.23.py` black-norm sha256 recomputed =
  `46051eb3c3cc87b8c894f66dcc6a8811b0d89b300d05be8cc3690de1a62731cf` ✅ (black 26.5.1).
  AST parses clean; 5032 lines. Safe for Joe to deploy to OWUI.
- **RAG harness re-checked:** `rag/eval_retrieval.py --self-test` PASSES (50 gold rows, all
  expected files present, RRF math + metrics correct). Live `--compare` is Joe-live (needs ES:9200
  + Ollama nomic-embed-text — unreachable from sandbox).
- **Handover rotated:** P29→P30 archived as `session-handover-P29.md`; P30 promoted here; P30 roll
  preserved as `session-handover-P30.md`. **Git commit still pending — do from WSL2.**
- **node3090 contention recommendation** recorded below (see thread 4).

### Thread 4 — node3090 GPU contention: resolution recommendation (P31)

**Premises corrected by Joe (P31):** Hermes is **started on-demand**, not a resident occupant —
so node3090's 3090 24 GB is free except during active Hermes calls. And a **2080Ti (+11 GB)** is
being added to node3090, making it a **35 GB two-GPU host** (3090 24 + 2080Ti 11). This dissolves
the "no free card" bind I wrote first.

**Resolution: no destructive swap needed.** GLM-4.7-Flash (~24 GB total-resident, MoE = total
params) runs on the 3090; schedule critic-heavy runs when Hermes is idle, which on-demand means
is most of the time. True simultaneity of Hermes-27B **and** GLM on one host still won't fit
(11 GB can't hold a 27B), but you rarely need both hot at once.

**What the 2080Ti buys** (pick one):
- (a) **Tensor-split GLM across 3090+2080Ti** (35 GB pool) → higher quant or longer critic ctx.
  Split layers run at Turing pace, but a natural-language critic is latency-tolerant, so fine.
- (b) **Offload the RAG embedding (Ollama nomic-embed) + the verification-oracle / test-runner**
  onto the 2080Ti — decongests LUCIFER's 4090 and makes the §5 critic+verifier loop a single-node
  affair on node3090. Likely the higher-value use.

**Power check (Joe raised the 850 W rail).** 3090 (~350 W) + 2080Ti (~260 W) + 9900K (~127 W TDP,
~180 W peak) + board/fans/loop (~80 W) ≈ **870 W** under a synthetic all-core + dual-GPU peak —
right at/over 850 W. Inference almost never sustains it (A3B MoE is ~3 B active = low GPU draw;
the critic is bursty), but cap both GPUs with `nvidia-smi -pl` (e.g. 3090→300, 2080Ti→200) so a
worst-case concurrent spike physically can't trip the PSU. Negligible throughput cost, removes the
only real risk.

**Net:** the cross-family critic is feasible on existing + already-planned hardware — **no 4th-card
ask.** Steady-state topology holds (Hermes on-demand, GLM on the 3090, helpers on the 2080Ti); the
shootout needs no maintenance window.

**Doc reconciliation flagged (not yet edited):** `docs/node5090-deployment-design.md` §1 still
reads node5090 = 35B-A3B and node3090 "stays dedicated to 27B/Hermes." The P30 lineup supersedes
both — leave the design doc as-is until the shootout resolves the coder pick, then stamp §1 +
the cluster table in one pass.

### Joe-live runbook — hands-on-keyboard tasks (P31)

Offline prep above is done. These need the live stack / WSL2:

**A. Deploy Cogitator v1.7.23 to OWUI** (gate already verified: `46051eb3…`).
   1. OWUI → Admin → Tools → LSE Cogitator → replace whole body with `tools/cogitator-v1.7.23.py` → Save.
   2. Re-verify deploy identity (OWUI black-formats on save):
      `python3 -c "import black,hashlib;print(hashlib.sha256(black.format_str(open('tools/cogitator-v1.7.23.py').read(),mode=black.Mode()).encode()).hexdigest())"`
      → expect `46051eb3c3cc87b8c894f66dcc6a8811b0d89b300d05be8cc3690de1a62731cf`.
   3. Re-set any custom Valves from source defaults (UI overrides wiped on redeploy).
   4. Rollback if it misbehaves: replace with `backups/cogitator-v1.7.19-DEPLOYED-20260614.py`
      (verified `e76d28b6…`) per `backups/ROLLBACK-cogitator.md`.

**B. Re-stage hermes-skill to node3090** `/tmp/lse-channel`, then Hermes self-installs per
   `hermes-skill/INSTALL.md` (copy `SKILL.md` + `lse_channel.py`, smoke-test enqueue/flush,
   then `check_hermes_inbox` from LSE → expect "HERMES → LSE (inbound)"). v1.7.23 covers both
   the poll-cap and by-reference paths; smoke-test by-reference with `--body-file`.

**C. Run the RAG ship-gate** (needs ES:9200 + Ollama nomic-embed-text):
   `python3 rag/eval_retrieval.py --compare`
   → if `Δrecall@3`/`ΔMRR` for rrf vs linear is a real improvement, port the hybrid `search_kb`
   from `rag/rag_tools_v2.py` into Cogitator (→ v1.7.24); else keep linear and record the numbers.
   (Harness `--self-test` already re-confirmed green offline this session.)

**D. Commit P30 + P31 work from WSL2** (NEVER the sandbox). New: `tools/cogitator-v1.7.23.py`,
   `eval/retrieval-gold-v1.jsonl`, `rag/eval_retrieval.py`, `coding-gauntlet/*`,
   `docs/multi-node-scaling-experiment.md`, `session-handover-P30.md`, `session-handover-P29.md`;
   modified: `hermes-skill/{lse_channel.py,SKILL.md,INSTALL.md}`, `rag/rag_tools_v2.py`,
   `session-handover.md`. Lock recovery if needed: `Get-ChildItem ".git\*.lock" | Remove-Item -Force`.

**E. Commission node5090** per `docs/node5090-deployment-design.md` (pfSense done): run
   `provision-node5090.sh`, fetch the coder GGUF → `/opt/models/`, write
   `/etc/llama/llama-server-5090.env` (`--no-mtp` mandatory on A3B MoE, `--ctx-size 81920`,
   `--jinja`, `:8080`, `--host 0.0.0.0`, Q5/Q6), add LUCIFER Prometheus scrape targets, smoke
   test (`node5090-t1/t2/t3`).

**F. Then §5 shootout** (after E): step 1 coder Coder-30B vs 35B-A3B on node5090; step 2 critic-lift
   with GLM on node3090's 3090 (Hermes idle — on-demand, no swap needed; see Thread 4). Give-up
   budget on every loop. Then build **Gate 1 (Terminal Confidant)**.
