# Multi-Node Scaling Experiment + node5090 Commissioning

> Status: DRAFT · P30 Cowork (2026-06-14)
> Parent: `docs/node5090-deployment-design.md` (hardware/provisioning) · `coding-gauntlet/PYRAMID.md` (task corpus)
> Purpose: decide, on evidence, **when a multi-node agentic workflow beats a strong single
> model**, and pick the per-node models — without turning it into an endless benchmarking saga.

---

## 1. The question (and the one we are NOT asking)

The model pick per node is the well-trodden part — public benchmarks settle it. The genuinely
under-measured, decision-relevant variable is the **orchestration topology**:

> Does our heterogeneous local topology (Qwen coder + Qwen planner + a cross-family critic +
> a ground-truth verifier) beat a **cost-matched single best model with SOTA scaffolding** —
> and above what task complexity does the crossover happen?

We are **not** trying to re-run the general "1 vs 2 vs 3 agents" curve. The literature already
shows it: homogeneous scaling saturates by ~3–4 agents; **heterogeneity (different families) is
the real lever**; and on tool-heavy/sequential tasks (exactly our coding domain) naive
multi-agent can go *negative*. So we test only what is unsettled **for us**.

Sources anchoring the design: *Understanding Agent Scaling via Diversity* (arXiv 2602.03794),
*Correlated Errors in LLMs* (arXiv 2506.07962), *Do Mixed-Vendor Multi-Agent LLMs Improve
Clinical Diagnosis?* (arXiv 2603.04421).

---

## 2. Per-node model lineup (converged P30)

| Node | GPU / VRAM | Model | Role | Family |
|---|---|---|---|---|
| node5090 (NODE3) | RTX 5090 · 32 GB | **Qwen3-Coder-30B-A3B** (high quant, long ctx) | coder | Qwen |
| LUCIFER | RTX 4090 · 24 GB | **Qwen3.6-27B** (already deployed) | planner / orchestrator | Qwen |
| node3090 | RTX 3090 · 24 GB | **GLM-4.7-Flash** (30B-A3B) | cross-family critic / tester | Zhipu/GLM |

Rationale: best consumer agentic coder where the VRAM is; the proven dense orchestrator already
in place; and a **different-family** critic that builds the heterogeneity test into the default
topology for free — a critic role also sidesteps GLM's weaker tool-calling (it reviews in natural
language; the Qwen coder drives the tools).

**VRAM truth (the binding constraint):** for MoE, VRAM is set by *total* params (all experts
resident); "active" params only set *speed*. GLM-4.7-Flash is 30B-total/3B-active → **~24 GB**
(32 GB at full precision / long ctx), **not** 12 GB. Kimi K2.5 (1T total / 32B active) and
MiniMax 2.5 (~230B class) are server-class — excluded on memory, not merit.

**Rejected and why:** Kimi K2.5 (1T total — datacenter only); Qwen3-32B (same family as the
coder → no heterogeneity, older gen than the 27B); DeepSeek-R1-Distill-Qwen-32B (Jan-2025,
dated — if we want a DeepSeek voice, use a current one).

### Open commissioning constraint
node3090's 24 GB is **currently committed to Hermes's 27B backend**. Running GLM-4.7-Flash as the
critic there means one of: (a) swap Hermes's backend during experiment runs, (b) time-share the
GPU, or (c) host the critic elsewhere. **Resolve before the shootout** — a 24 GB card can't hold
the 27B and GLM-4.7-Flash simultaneously.

---

## 3. node5090 commissioning (prereq for everything below)

Execute `docs/node5090-deployment-design.md` (pfSense reservation already done; `192.168.1.55`,
`node5090.home.arpa`). Remaining:

1. `scripts/node5090/provision-node5090.sh` — lsestack group/setgid dirs, scoped sudoers, `llama` user.
2. Fetch **Qwen3-Coder-30B-A3B** GGUF → `/opt/models/` (stage via n45 NAS or HF).
3. Write `/etc/llama/llama-server-5090.env` — canonical launch params: `--no-mtp` (mandatory on
   A3B MoE), `--ctx-size 81920` (universal canon; bump only if perf-tested), `--jinja`, `:8080`,
   `--host 0.0.0.0`, high quant (Q5/Q6 fits 32 GB).
4. systemd unit reads the env file; restart = edit env + `systemctl restart llama-server-5090`.
5. Prometheus scrape targets on LUCIFER: `node5090.home.arpa:9100/:9835`, llama `/metrics`.
6. Smoke test: `node5090-t1` discovery, `t2` health, `t3` delegation — feeds the shootout.

---

## 4. Experiment design (the "someday science")

Independent variables, kept orthogonal so capability never rides the count knob:

- **Axis A — node/agent count:** 1 · 2 · 3.
- **Axis B — heterogeneity level:** H0 homogeneous (one model cloned) · H1 intra-family (Qwen
  sizes) · H2 cross-family (Qwen + GLM). The headline number is the **H1→H2 marginal lift**.

Two capability regimes to kill the node5090 confound (it's a *better* node, not just another):

- **Regime A — capability-pinned:** every node runs the **same model at 27B @ ctx 81920**, equal
  sampling budget. Isolates pure orchestration. node5090's extra VRAM idles — the price of a clean
  control.
- **Regime B — best-per-node:** the §2 lineup. node5090's superiority *is* the heterogeneity
  factor, measured explicitly, not smuggled.

Baselines & controls:

- **Strongest-single-node baseline:** node5090 at full tilt, same total GPU-seconds poured into
  best-of-N + a verification loop. The cluster must beat *throwing everything at the best box*.
- **On-node-roles control (T1):** planner/coder/critic time-sliced on ONE node — isolates
  role+verification benefit from extra hardware.
- **Role-swap control:** put the coder on a 24 GB node, critic on the 5090 — if gains track the
  model→role mapping regardless of chassis, it's real orchestration, not "node5090 magic."
- **Verification oracle:** execution/tests as a non-LLM "agent" — maximally decorrelated; likely
  our single biggest lever on tool-heavy coding.

Measurement:

- **Cost is GPU-seconds, not wall-clock** (silicon speed differs even at equal model). Report
  success **vs compute**, always. (MoE wrinkle: 35B/30B-A3B's ~3B active makes it cheap per token
  despite big memory — capacity ≠ compute here.)
- Dependent vars: resolve rate / pass@1 on acceptance tests, partial-credit fraction, GPU-seconds,
  coordination-failure rate. Derived: marginal lift per node, **lift per GPU-second**, the knee.
- **Stratify by task-complexity tier** (Gate 1→4 class). Hypothesis: multi-node lift is ~0 or
  negative on easy/tool-heavy tasks, turns positive only above a complexity threshold, saturates
  by N=3. **The deliverable is the crossover complexity** — it parameterizes the escalation ladder.
- Instrument: paired **McNemar** across treatments — the same ground-truth discipline as the infra
  bench, now pointed at coding acceptance tests. (n ≥ ~30–40 paired tasks for power.)

Falsifiable prediction (commit to it): **the knee is N=2** — coder + independent verifier captures
nearly all the lift; the separate planner adds little; on Gate-1-class tasks single-node-with-
verification wins outright on cost.

---

## 5. The pragmatic cut (the balance — do THIS first)

Do **not** run the full factorial before shipping. Stand up the §2 lineup and run **one** gauntlet
pass that answers only the two real unknowns:

1. **Coder:** Qwen3-Coder-30B vs the previously-planned 35B-A3B on node5090 (the never-run shootout).
2. **Critic:** does adding the cross-family GLM critic lift the result over coder+verifier alone?

Hard rule: every agentic loop gets a **give-up budget** (max iterations / max GPU-seconds). Past
the verification knee, more tokens buy ~nothing and can go negative — the loop must stop, not
smoke compute chasing points above the base model's ceiling. Then commit and stop benchmarking.

---

## 6. Honest capability expectation

No hopium. On raw per-shot capability we land a tier below frontier; scaffolding narrows, doesn't
close. Coder base ~50% SWE-bench Verified; a real agentic harness (plan → code → run tests → repair,
on budget) pulls that into the **high-60s/low-70s**; cross-family critic + best-of-N add a few more
with steep diminishing returns. **Landing zone ~70% vs frontier ~80%.**

The gap is **not uniform**, which is the whole strategy:
- routine, well-specified work (Gate 1–2): near-parity (~90% of frontier's effective success);
- hard, long-horizon work (Gate 3–4): 60–70% — frontier's reasoning depth + self-correction win.

Frontier-parity open weights exist (MiniMax 2.5 ≈ Claude on SWE-bench) — they just don't fit
24–32 GB. So "frontier on your desk" is a VRAM problem, not a model problem. **We don't win the
head-to-head; we win the economics:** free, local, private, relentless, and *learning* — a weaker
model that iterates without a meter and keeps its wins out-*delivers* a smarter metered one on the
repetitive 80%, while escalating the hard 20%. Engineer for that distribution.

---

## 7. P30 → P31 decision log

**Shipped/built P30 (code-side, verified offline; live deploy = Joe):**
- **Cogitator v1.7.23** (black-norm `46051eb3…`) — Hermes→LSE **by-reference** for large payloads
  (producer spills to `/tmp/lse-channel/refs/<cid>.txt`, marker carries `body_ref`; LSE surfaces an
  SSH fetch). Superset of v1.7.22 (poll cap 8→1024), so deploying 23 covers both. Round-trip
  verified offline (4.7 KB payload → 540-char marker).
- **RAG S2 (retrieval competence):** `eval/retrieval-gold-v1.jsonl` (50 query→doc pairs),
  `rag/eval_retrieval.py` (recall@1/@3 + MRR, 4 modes, `--self-test` passes), hybrid **RRF**
  `search_kb` staged in `rag/rag_tools_v2.py` — **ship-gated** on `--compare` beating `linear`;
  includes the S2.4 fix (0.60 cosine-floor miss gate replacing the 0.72-on-summed-score).

**Decisions:**
- **Pivot:** synthetic infra-bench growth (old Task 5) **paused**, not dropped — it's the McNemar
  instrument, repurposed onto the coding gauntlet.
- **Coding gauntlet** = the new direction. 4 gates (`coding-gauntlet/PYRAMID.md`); Joe owns Gate 4
  (iOS group-chat app for local-model + human chat, plugin framework, **opencode** aesthetic);
  gates 1–3 authored. Shared design tokens: `coding-gauntlet/design-tokens/opencode-tokens.json`.
- **Gauntlet = autonomous LSE-agent curriculum** (the Goethe coding curriculum) — challenges, not
  co-build.
- **Stack locked:** TypeScript across gates 1–3 (Ink TUI → Bun/`ws` + SQLite + web → TS plugin
  contract); shared TS message schema; Gate 2 REST+WS = the iOS app's API.
- **Orchestration locked:** mention-+-reply default behind a swappable `SpeakerPolicy`.
- **Heterogeneity finding:** the lever is **cross-family** (GLM vs Qwen), not intra-family variants
  — drives the per-node lineup and the H1→H2 measurement.
- **Per-node lineup converged** (§2).

**Carry to P31:**
1. (Joe, live) Deploy Cogitator v1.7.23 to OWUI; verify black-norm `46051eb3…`; re-stage
   `hermes-skill/` to node3090 `/tmp/lse-channel`; commit P30 work from WSL2.
2. (Joe, live) Run `rag/eval_retrieval.py --compare` → decide if RRF ships (port to Cogitator).
3. Resolve the node3090 GPU contention (Hermes 27B vs GLM critic) — §2 open constraint.
4. Commission node5090 (§3); fetch Qwen3-Coder-30B; smoke test.
5. Run the **one** pragmatic shootout (§5); then build Gate 1 as the curriculum's first challenge.
