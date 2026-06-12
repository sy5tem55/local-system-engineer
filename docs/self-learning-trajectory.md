# Self-Learning Trajectory — Consolidated Execution Path
> Status: DRAFT for review · 2026-06-11 (P20 Cowork)
> Parent: `docs/lse-1.7.0-design.md` §3–4. This document is the ORDER OF OPERATIONS.
> Empirical anchor: episodes #32–34 (node-t3-005) — every claim below has today's evidence behind it.

---

## Why this order

Two hard sequencing rules drive everything:

1. **Baseline before learning.** Once skills start injecting, an uncontaminated Condition A baseline can never be recorded retroactively. S1 must complete before S3/S4 ship.
2. **Stop the bleeding first.** The KB is being polluted *now* (3 junk "web-search: node-t3-005" docs at quality 0.7 indexed today alone — one per episode). Hygiene is S0, not a backlog item.

Today's episodes also supplied the motivating observation for the whole skills concept: all three t3-005 runs got a KB hit ("Lse Architecture", score 28–29) injected at reset — **and it never helped**. Retrieval returned a generic fact doc when the model needed a *procedure* ("how to safely delete a file you lack permissions for, given execute_command blocks sudo"). Facts ≠ skills. That gap is what `lse-skills` closes.

---

## S0 — Hygiene + skill #1 (this week, no dependencies)

| # | Action | Artifact / change |
|---|---|---|
| 0.1 | **Purge junk web-search docs** indexed during stagnation (episodes #32–34): ES delete-by-query on title prefix `web-search: node-t3-005`, then audit for other `web-search: *` entries with quality ≥0.7 and stagnation-query phrasing | one-off script `rag/purge_stagnation_docs.py` |
| 0.2 | **Gate auto-indexing** in `escalation_wrapper.py`: index web-search results only if cosine(result, challenge description) ≥ 0.6; default quality **0.4** (was unconditional 0.7) | escalation_wrapper v2 |
| 0.3 | **Hand-write skill #1** — the sudo-blocker discovery: "execute_command blocks `sudo` (substring); /opt paths owned by other users are unwritable; fix is structural (group membership/setgid), not escalation." This validates the schema on real content before any automation | `kb/skills/linux-sysadmin--permission-blocked-cleanup.md` (seed for S3) |

**Done when:** ES contains zero stagnation-query docs; next stagnation episode indexes nothing or at 0.4; skill #1 written and reviewed.

## S1 — Measurement foundation (before ANY learning feature ships)

| # | Action | Artifact / change |
|---|---|---|
| 1.0 | **Episode actuation layer (P0, found in P20):** `run_episode.py` calls llama-server bare — model commands are never executed; `verify_ssh` overrides self-report. Write challenges are deterministic failures (t3-005: identical 2/4 across 9 attempts — model output never mattered). Env must parse and execute model command blocks via SSH, porting the tool's safety gates (blocklist, no-sudo, privileged paths). Until then the arena measures world state, not the model | `lse_challenge_env.py` v2 |
| 1.1 | `verify_ssh` ground truth on every assertion of every bench candidate (absorbs P0 Arena item; pattern already proven in node-t3-004/005 seeds) | challenge seeds |
| 1.2 | `--eval --no-learn` flag: disables `index_to_kb`, skill writes, web-search auto-indexing; tags leaderboard rows `suite`, `condition` | `run_episode.py` v2 |
| 1.3 | **Freeze `lse-bench-v1`**: 30–40 challenges stratified by tier × domain, manifest with challenge ids + seed-script SHA-256 | `eval/lse-bench-v1.manifest.json` |
| 1.4 | **Record Condition A** (injection OFF) ×3 runs | `eval/lse-bench-reports/` |
| 1.5 | Bench report mode: resolve rate, pass@1, pass@3, partial credit (mean assertion fraction), attempts, wall time, 95% CI | `leaderboard.py` v2 |

**Done when:** Condition A baseline exists with CIs; suite manifest is version-pinned; re-running produces consistent numbers (variance sanity check).

## S2 — Retrieval evaluation + hybrid scoring (parallel with S1)

| # | Action | Artifact / change |
|---|---|---|
| 2.1 | **Gold set**: ~50 (query → expected doc) pairs covering all KB topics + known past failures (e.g. "node3090 canonical launch command" → node3090-llama-launch.md) | `eval/retrieval-gold-v1.jsonl` |
| 2.2 | Eval harness: recall@3, MRR, per-index breakdown | `rag/eval_retrieval.py` |
| 2.3 | **Hybrid BM25 + kNN via RRF** in `search_kb` (ES native, zero infra). Ship only if gold-set metrics improve; otherwise keep kNN and record the result | `rag/rag_tools_v2.py` |
| 2.4 | Re-examine the 0.72 hit threshold against gold-set ROC — it was never empirically chosen | threshold note in rag/README |

**Done when:** recall@3 and MRR have baseline numbers; hybrid decision is data-backed either way.

## S3 — `lse-skills` index + retrieval path (needs S0.3 schema validation; S2 harness reused)

| # | Action | Artifact / change |
|---|---|---|
| 3.1 | Index mapping: occupation, task, preconditions, procedure[], verification, failure_modes[], provenance[], embedding(768), quality, stats{} | `rag/02-es-setup.py` extension |
| 3.2 | Tool functions `skill_search`, `skill_record` — **docstring-optimizer pass mandatory** before deploy | tool v1.7.0-c |
| 3.3 | EscalationWrapper reset hook: query `lse-skills` first (occupation+task embedding), fall back to `lse-kb`; **max 2 skills injected** (context budget) | escalation_wrapper v3 |
| 3.4 | Seed: skill #1 from S0.3 + distill the other resolved T3 episodes retroactively (t3-003/004 restart procedure is skill #2) | ~5 seed skills |
| 3.5 | Extend gold set with skill queries; measure skills retrieval with S2 harness | gold-v2 |

**Done when:** an episode reset against a permission-flavored challenge retrieves skill #1 instead of (or ahead of) "Lse Architecture".

## S4 — Episode distillation loop (needs S1 flags + S3 index)

| # | Action | Artifact / change |
|---|---|---|
| 4.1 | Post-episode debrief step in `run_episode.py`: extract what worked / what blocked → `skill_record` (create or update). Runs ONLY when not `--eval` | run_episode v3 |
| 4.2 | Quality movement on evidence only: +0.1 verified episode success using the skill · −0.15 verified failure where skill was injected · +0.2 authoritative cross-ref · floor 0.2 → archive | skill lifecycle rules |
| 4.3 | Error-KB promotion: ≥2 `record_error` hits on same fingerprint → auto-propose skill stub (quality 0.3, flagged for review) | rag job |

**Done when:** a solved episode produces/updates a skill without human action, and the skill's stats reflect it.

## S5 — Occupational curriculum + lifecycle jobs (needs S4 stable)

| # | Action | Artifact / change |
|---|---|---|
| 5.1 | Occupation taxonomy: linux-sysadmin, network-engineer, sre, dba, security-analyst — each with task statements (O*NET-style + vendor runbooks) | `rag/occupations.yaml` |
| 5.2 | Batch research job: occupation task → web search → candidate skill at quality 0.4 pending verification. Scheduled, never in-episode | `rag/curriculum_batch.py` |
| 5.3 | Weekly consolidation: near-dup merge (cosine >0.92), stale provenance flagging, archive sweep | `rag/skill_consolidate.py` |
| 5.4 | **SOUL.md curation discipline (SY5, P20)** — capstone self-improvement skill: LSE proposes appends of *proven* knowledge to Hermes's SOUL.md. Highest bar in the system, because SOUL.md is in every future Hermes context — one error poisons everything. Hard gates: (a) fact verified by ground-truth probe, not self-report; (b) identity-relevant only (principals, operating constraints, backend facts — general knowledge goes to memories/KB instead); (c) token budget: SOUL.md ≤ ~1.5KB total, every append justifies permanent context cost; (d) `requires_human_approval=1` — human reviews the exact diff; (e) timestamped backup → append → gateway restart → verify via Telegram/hermes_ask that Hermes states the new fact correctly. Design as arena challenge family `hermes-t4-xxx` — it tests verification, restraint, and protocol compliance in one task | challenge family + skill doc |

**Done when:** first curriculum batch lands ≥20 candidate skills and consolidation keeps the index clean for two consecutive weeks.

## S6 — Lift measurement cadence (needs S1 + S3; the actual science)

| # | Action | Artifact / change |
|---|---|---|
| 6.1 | **Monthly paired run**: Condition A (OFF) vs B (ON), identical frozen suite, n=3 each | `eval/lse-bench-reports/YYYY-MM/` |
| 6.2 | **Learning lift** = resolve(B) − resolve(A); McNemar's on paired per-challenge outcomes; report with CIs | report template |
| 6.3 | **Contamination audit** pre-run: zero overlap between skill provenance episode ids and suite challenge ids — hard abort on violation | audit step in run_episode --eval |
| 6.4 | Track the lift curve over months — that curve IS the self-learning evolution. Secondary: pass@1 trend, skill reuse rate, mean attempts | dashboard / report |

**Targets:** detectable lift ≥ +15pp on suite v1 (statistical floor at n≈35); pass@1 monotonic over 3 cycles; zero contamination violations. Model + quant pinned for the life of suite v1 — any model change resets the baseline.

---

## Dependency graph

```
S0 (hygiene + skill #1) ──────────────┐
S1 (baseline) ────────────┬───────────┼──→ S4 (distillation) ──→ S5 (curriculum)
S2 (retrieval eval) ──→ S3 (skills index) ─┘                          │
S1 + S3 ──────────────────────────────────────→ S6 (monthly lift) ←───┘
```

S0 and S2 start immediately. S1 gates everything downstream — **no skill injection in production episodes until Condition A is recorded.**
