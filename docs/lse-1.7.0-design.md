# LSE v1.7.0 — Design: Hermes Core + Self-Learning Skills
> Status: DRAFT for review · 2026-06-11 (P20 Cowork)
> Baseline: tool v1.6.4 (tools/openwebui-tool-v1.6.4.py) · prompt v0.5.15 · RAG stack (ES 8.17 + nomic-embed-text)
> Note: VERSION.md still lists tool v1.6.1 deployed — reconcile registry before 1.7.0 work starts.

---

## 0. Scope

Four workstreams, one release train:

1. **Hermes core feature** — promote Hermes from notification endpoint to structured peer agent.
2. **Self-learning skills** — occupational skill acquisition on top of the existing RAG/ES architecture.
3. **Scientific measurement** — make self-learning evolution measurable with SWE-bench-comparable metrics.
4. **35B-A3B delegation** — route hard coding tasks beyond Qwen3.6-27B-Q4 to Qwen3.6-35B-A3B.

---

## 1. Core Principles

**P1 — Skills are artifacts, not behaviors.** A skill is a versioned, quality-scored ES document with provenance and usage statistics — never an implicit change to prompt or weights. Everything the LSE "learns" must be inspectable, diffable, and deletable.

**P2 — Learning is closed-loop and grounded.** A skill's quality score moves only on evidence: episode outcomes verified by `verify_ssh` ground truth, or cross-referenced authoritative sources. Self-reported success never raises quality (node-t3-002 hallucination incident is the permanent reminder).

**P3 — Measurement requires a frozen test set.** Challenges used for learning must never overlap with challenges used for evaluation. Without a held-out suite, "improvement" is contamination. This is the single most important methodological rule in this document.

**P4 — Escalate by capability tier, locally first.** 27B handles operations; 35B-A3B handles hard coding; Claude L2 remains the ceiling. Each delegation is logged with reason, outcome, and cost so routing thresholds are tuned from data, not vibes.

**P5 — Two principals, one protocol.** SY5 and LSE are Hermes's principals. All LSE↔Hermes traffic is structured (intent + payload + correlation id), auditable, and survives gateway restarts. No free-text-only coordination.

**P6 — Don't break the deployed system.** Eval suite stays green (63/63) across every 1.7.0 increment. New tool functions go through `lse-docstring-optimizer` before deployment. NTFS file-handling rules apply (no Edit on >100-line Python; heredoc → ast.parse → cp).

---

## 2. Hermes Core Feature

### 2.1 Current state
`call_hermes(message, no_think)` — fire-and-forget text over socat :8643 → gateway :8642. Used for restart pre/post notifications. Hermes does not know what LSE is (KB entry pending install), gateway unit had a SIGKILL-mid-drain bug (fix in flight), and Hermes's own SSH to node3090 fails (password auth, no key).

### 2.2 Target: structured peer protocol
New tool functions (each through docstring-optimizer before ship):

| Function | Purpose |
|---|---|
| `hermes_notify(event, payload)` | Typed events: `maintenance_start`, `maintenance_end`, `cleanup`, `alert`. Replaces free-text call_hermes for protocol traffic (call_hermes stays for conversation). |
| `hermes_ask(question, timeout_s)` | Synchronous request/response with correlation id — LSE can ask Hermes to verify reachability, confirm state from its side, or answer from its memories. |
| `hermes_task(task_spec)` | Hand Hermes a bounded task (e.g. "watch llama-server health for 10 min, alert on failure"). Requires Hermes-side cron/session support — gate behind capability probe. |

Protocol envelope (JSON over the existing port): `{v:1, from:"lse", intent, correlation_id, ts, payload}`. Hermes replies with same correlation_id. Degrade gracefully: if Hermes replies non-JSON, treat as legacy text.

### 2.3 Prerequisites (already in motion, P20)
- Hermes KB/memory entry so Hermes can answer "what is LSE" (install into `~/.hermes/memories/` — format survey pending).
- `TimeoutStopSec=210s` unit fix (drain 180s + margin).
- Decide whether Hermes gets key-based SSH to node3090 or stays SSH-less (recommended: SSH-less; LSE is the hands, Hermes is the watcher — clean separation of capability).

---

## 3. Self-Learning Skills from Real-World Occupations

### 3.1 Concept
The existing RAG loop (search_kb → miss → web → index_to_kb, quality 0.3→1.0) learns **facts**. The skills layer learns **procedures**, modeled on real-world occupational practice: Linux sysadmin, network engineer, SRE, DBA, security analyst. Each skill is a runbook-shaped document the model retrieves at episode start (the EscalationWrapper KB-injection hook already exists — skills ride the same path).

### 3.2 Skill document schema (new ES index `lse-skills`)
```json
{
  "skill_id": "linux-sysadmin/disk-cleanup-duplicate-files",
  "occupation": "linux-sysadmin",          // taxonomy below
  "task": "Free disk space by removing duplicate large files",
  "preconditions": ["write access to target dir", "active consumers identified"],
  "procedure": ["enumerate candidates", "verify active usage (lsof/proc)", "safety gate", "delete", "verify"],
  "verification": "df delta + consumer health check",
  "failure_modes": ["deleting the in-use copy", "permission denied (no sudo in execute_command)"],
  "provenance": [{"type": "episode", "id": "node-t3-005"}, {"type": "web", "url": "..."}],
  "embedding": [768],
  "quality": 0.5,
  "stats": {"uses": 3, "episode_successes": 2, "episode_failures": 1, "last_used": "..."}
}
```

### 3.3 Acquisition loop (three sources, one pipeline)
1. **Episode distillation** (primary): after every episode, a debrief step (extend `run_episode.py`) extracts the procedure that worked or the failure that blocked, and writes/updates a skill. node-t3-005 is the canonical example: two failed runs distilled to "execute_command blocks sudo — solve permissions structurally, not with escalation."
2. **Occupational research** (proactive): a curriculum job maps occupation → task list (seeded from O*NET-style task statements + vendor runbooks), searches the web for authoritative procedures, and indexes candidate skills at quality 0.4 pending verification. Run as scheduled batches, not in-episode.
3. **Error KB promotion**: recurring `record_error` patterns (≥2 hits on the same fingerprint) auto-propose a skill stub.

### 3.4 Lifecycle
- Quality moves on evidence only (P2): +0.1 on verified episode success using the skill, −0.15 on verified failure where the skill was injected, +0.2 on cross-reference with authoritative doc; cap 1.0, floor 0.2 then archive.
- Consolidation job (weekly): near-duplicate merge (cosine > 0.92), stale-provenance flagging — same philosophy as the existing KB refinement.
- Retrieval: episode reset queries `lse-skills` first (occupation + task embedding), falls back to `lse-kb`. Inject at most 2 skills to protect context budget (27B @ 64k, context_monitor already polices this).

### 3.5 Architecture assessment — what to improve, what to keep
**Keep:** ES 8.17 single node, nomic-embed-text 768-dim via Ollama CPU, quality-score model, 0.72 hit threshold. All adequate at current corpus size (~1.5k chunks + 12 docs); no re-platforming.

**Improve:**
1. **Retrieval is currently unevaluated.** Build a 50-query gold set (query → expected doc) and track recall@3 / MRR per index. This is the RAG analog of the eval suite. Without it, embedding/threshold changes are blind.
2. **Hybrid scoring**: ES supports BM25 + kNN natively — current setup appears kNN-only. Hybrid (RRF) typically lifts recall on exact-term queries (error strings, flag names) at zero infra cost. Measure with the gold set before/after.
3. **Web-search auto-indexing is contaminating quality**: the P20 episodes indexed a useless stagnation search at quality 0.7 ("why fails infrastructure...") — unconditional indexing should be gated on a relevance check vs the challenge description (cosine ≥ 0.6) and default to quality 0.4, not 0.7.
4. **Chunking provenance**: store source span offsets so skill citations can point at exact lines.
5. Defer: reranker models, GPU embeddings, multi-node ES — not justified at this scale.

---

## 4. Measuring Self-Learning Scientifically

### 4.1 The benchmark: LSE-bench
A **frozen** suite of 30–40 challenges, stratified by tier (T1/T2/T3) and domain (node, net, ha, infra, nas), with `verify_ssh` ground truth on every assertion (P0 roadmap item — now a hard prerequisite). Frozen means: never used for skill acquisition, KB writes disabled during eval runs, suite version-pinned (`lse-bench-v1`). New challenges go to the next suite version, never retrofitted.

### 4.2 Metrics (SWE-bench-comparable)
| Metric | Definition | SWE-bench analog |
|---|---|---|
| **Resolve rate** | % challenges fully solved (all assertions) on the frozen suite | % resolved |
| **pass@1** | solved on attempt 1, temp fixed | pass@1 |
| **pass@3** | solved within max_attempts=3 | pass@k |
| **Partial credit** | mean assertion fraction (the 2/4 episodes carry signal) | n/a (richer than SWE-bench) |
| **Mean attempts to solve** | over solved subset | n/a |
| **Wall time / tokens per solve** | cost axis | $ per resolve |
| **Escalation rate** | % requiring L2/35B | n/a |

### 4.3 Isolating the learning effect (the actual science)
- **Condition A (frozen baseline):** eval run with KB+skills injection OFF.
- **Condition B (learned):** identical run with injection ON, using the skill corpus as of date D.
- **Learning lift** = resolve(B) − resolve(A). Track lift over time as the corpus grows: that curve IS the self-learning evolution.
- Re-run A and B monthly (model and quantization pinned — any model change resets the baseline).
- **Statistics:** n=3 runs per condition minimum (temp seeds vary), report mean ± 95% CI; paired per-challenge outcomes tested with McNemar's. With ~35 challenges, detectable lift is roughly ≥15pp — acceptable for a homelab-scale benchmark; grow the suite to tighten.
- **Contamination audit:** before each eval, assert zero overlap between skill provenance episode ids and suite challenge ids.

### 4.4 Implementation
- `run_episode.py --eval --suite lse-bench-v1 --no-learn` flag: disables index_to_kb, skill writes, and web-search auto-indexing; tags leaderboard rows with suite+condition.
- `leaderboard.py` gains a benchmark report: per-suite, per-condition table with the metrics above.
- Results land in `eval/lse-bench-reports/` next to the existing eval reports.

---

## 5. Delegation to Qwen3.6-35B-A3B for Hard Coding

### 5.1 Rationale and placement
35B-A3B (MoE, ~3B active) presets already exist in the launcher (presets 9–12, Qwopus 32k/96k, `--no-mtp`). MoE gives near-27B latency with stronger coding. It slots between 27B and Claude L2 in the escalation ladder:

```
27B (operator) → 35B-A3B (hard coding) → Claude L2 (review/ceiling)
```

### 5.2 Serving topology (decision needed)
| Option | Pros | Cons |
|---|---|---|
| **A. node3090 LM Studio :1234 serves 35B-A3B** (recommended) | No contention with 27B on LUCIFER; LM Studio already running; pfsense-agent precedent for the endpoint | node3090 is also Hermes's backend host — VRAM budget: 35B-A3B Q4 ≈ 18–20GB, fits 24GB alone but NOT alongside 27B @ 81920 ctx. Requires model swap or Hermes downtime windows |
| B. LUCIFER swaps 27B↔35B per task | Single host | Kills the LSE session model mid-conversation — non-starter for in-episode delegation |
| C. Wait for NODE3/5090 | Clean dedicated host | Not deployed yet |

Recommendation: **A**, with delegation declared a maintenance-window operation until NODE3 exists (Hermes gets `maintenance_start` event, 27B on node3090 is swapped out, 35B in, swapped back after). The Hermes protocol from §2 is what makes this coordination safe — the two features interlock.

### 5.3 Delegation mechanics
- New tool function `delegate_coding_task(spec, context_files, acceptance)` — sends an OpenAI-compatible completion to the 35B endpoint; response must be code + self-test; LSE validates with `ast.parse`/test run before accepting (the model never trusts the delegate blindly — same P2 evidence rule).
- **Trigger criteria** (start conservative): task is code-generation >80 lines, OR 27B failed an attempt with syntax/logic errors, OR challenge is tagged `discipline=coding, tier>=3`.
- **Measure it like everything else:** delegation precision = % of delegated tasks where 35B succeeded after 27B failed; cost delta; resolve-rate lift on coding-tagged suite challenges. If precision <50% after 20 delegations, revisit triggers.

### 5.4 Open question for a model shootout
Roadmap already lists "Model shootout Runs 3–4 (Qwopus 35B, Qwen3-Coder 30B)". Run that first — if Qwen3-Coder-30B beats 35B-A3B on the coding suite, the delegation target changes and nothing else in this design moves.

---

## 6. Release Plan

| Phase | Deliverable | Gate |
|---|---|---|
| **1.7.0-a** | Ground-truth `verify_ssh` everywhere (P0), `--no-learn` eval flag, lse-bench-v1 frozen, baseline Condition A recorded | Eval 63/63 green |
| **1.7.0-b** | Hermes protocol (`hermes_notify`, `hermes_ask`), KB entry installed, unit fix verified | Hermes answers "what is LSE"; round-trip correlation id works |
| **1.7.0-c** | `lse-skills` index + episode distillation + retrieval gold set + hybrid scoring | recall@3 measured; first 10 skills distilled |
| **1.7.0-d** | Occupational curriculum batches + lifecycle jobs | Learning-lift measurement #1 (A vs B) |
| **1.7.0** | 35B-A3B delegation (post-shootout) + `hermes_task` | Delegation precision instrumented; full bench re-run |

Every phase: docstring-optimizer on new functions, CHANGELOG entry, VERSION.md bump, session-debrief to KB.

---

## 7. Risks
- **Context budget**: skill injection + KB injection + stagnation prompts compete for 64k. Mitigation: max 2 skills, context_monitor gating.
- **Quality-score inflation** from auto-indexed noise (already observed P20). Mitigation: §3.5.3 gating — do this early.
- **Benchmark too small for significance**: accept wide CIs initially; the trend over months matters more than any single comparison.
- **node3090 multi-tenancy** (llama-server + Hermes + 35B swaps): every swap is a Hermes outage. The §2 protocol is the mitigation; NODE3 is the cure.
