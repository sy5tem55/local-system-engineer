# LSE Challenge Arena — Design Document
> Status: Design phase. No code written yet.
> Last updated: 2026-06-03
> Source: Reconstructed from session conversations (original lost). Treat as authoritative.

---

## 1. What This Is

A multi-model evaluation arena where LLMs compete on real sysadmin/engineering problems drawn from actual LSE operational work. Not a benchmark — a production-value game. Solutions that pass sandbox validation get deployed to live infrastructure.

The core design tension is a **public goods game embedded in a competition**: models compete for points individually, but escalation solutions enter a shared KB that all models can retrieve. Contributing to the KB via escalation is costly short-term (−5 pts) but enriches the pool for all future episodes.

---

## 2. Point Structure

| Event | Points |
|---|---|
| Solve on attempt 1 | +10 |
| Solve on attempt 2 | +7 |
| Solve on attempt 3 | +4 |
| Solve after escalation (model provided useful context) | +2 |
| Escalation triggered | −5 |
| KB hit retrieved and used in solution | +2 bonus |
| Solution successfully indexed to KB | +1 |
| Rollback defined before any mutation | +1 |
| Post-run health check passed | +1 |

**PhD threshold:** 1000 points does NOT terminate participation — it unlocks the next difficulty tier. Collapsing participation at threshold breaks the incentive structure.

The +2 "useful context" on escalation is load-bearing: it keeps the losing model invested in clear problem framing rather than giving up. Poor escalation framing is the primary failure mode for the escalation gate.

---

## 3. Disciplines and Scoring Weights

| Discipline | Weight | Rationale |
|---|---|---|
| Debugging | 1.5× | Hardest to fake. Requires hypothesis formation under incomplete information. |
| Security analysis | 1.3× | Privilege boundary reasoning, config auditing. Maps to LSE permission model. |
| Constraint satisfaction | 1.3× | Staying within boundaries under pressure. The LSE's most common eval failure. |
| Coding | 1.2× | Script and automation authorship. |
| Performance optimization | 1.1× | Bottleneck identification, measurement-driven. |
| System administration | 1.0× | Baseline. |

---

## 4. Escalation Protocol

### Full sequence

```
0. check_error_kb(error)
   → known resolution? Apply it. No attempt consumed. Done.

1. Attempt 1
   → log attempt text + embedding

2. Attempt 2
   → log attempt text + embedding
   → cosine(embed(attempt1), embed(attempt2)) > 0.85?
     YES → semantic stagnation detected → skip to step 5 immediately
     NO  → continue

3. Attempt 3
   → log attempt text + embedding
   → cosine(embed(attempt2), embed(attempt3)) > 0.85?
     YES → skip to step 5
     NO  → proceed to step 5 regardless (3 attempts exhausted)

   OVERRIDE: if error matches known "Claude-only" category
   (novel CUDA segfaults, undocumented API behaviour, race conditions)
   → escalate on attempt 1

4. search_web(authoritative docs)
   → official docs, man pages, project GitHub — sharp queries only
   → NO PENALTY. Web search is a mandatory pre-escalation step, not an escalation.
   → index_to_kb(result + query_that_found_it) ALWAYS — regardless of outcome
     ↳ A failed web-assisted attempt that gets indexed is still valuable:
       it tells future sessions "this official doc path was tried and didn't
       resolve this specific variant." The query construction is institutional
       knowledge — future search_kb() retrieves BOTH the result AND the query
       that found it, so the search discipline compounds across episodes.
   → Web-assisted attempt 4
   → Solved? Done. quality_score=0.9 (web-verified).
   → Failed? → ESCALATE

5. Escalation to Claude API (OpenWebUI endpoint)
   → full context: all attempt embeddings + search findings + failure reasons
   → Claude solution returned and immediately:
     a. record_error(failure_pattern, resolution=claude_solution)
        — indexes to lse-errors so future check_error_kb() hits at step 0
        — next session hitting the same error class: resolved before attempt 1
     b. index_to_kb(layered_entry, quality_score=1.0, source="competition_escalation")
        — full entry: attempts + failure reasons + web result + Claude solution + diff
        — becomes top search_kb() result for this challenge class immediately
   → Apply −5 (escalation penalty — Claude API call only) to triggering model
   → Apply +1 (indexing bonus) to triggering model
   → Apply +2 to triggering model if escalation context was well-framed
```

### Why web search is never penalized

Web search is infrastructure, not escalation. It is a mandatory step that runs unconditionally before any Claude API call is made. Penalizing it would punish the correct behavior (exhaust all options before calling Claude). The −5 penalty applies solely to the Claude API call at step 5.

The two costs are completely separate:
- **Web search (step 4):** zero penalty, zero bonus, always mandatory, always indexes
- **Escalation (step 5):** −5 penalty, +1 indexing bonus, +2 if context is well-framed

A model that solves at step 4 (web-assisted) earns +4 (attempt 3 solve timing) with no penalty at all.

### Why the convergence check beats the attempt counter

A model can make 5 meaningfully different attempts OR repeat the same approach with slight variations. The signal needed is **semantic stagnation** — the model is circling. Cosine similarity on attempt embeddings detects this faster and more accurately than counting.

A model that genuinely tries different approaches gets more runway. A model stuck in a loop gets cut off faster. This also prevents gaming by padding attempt count.

### What gets logged on escalation (KB entry structure)

Two KB writes happen simultaneously on escalation resolution:

**Write 1 — lse-errors index (via record_error):**
```
{
  "error_text": "...",          # the failure pattern, embedded for future check_error_kb()
  "context": "...",             # challenge class + environment state
  "resolution": "...",          # Claude's solution — applied at step 0 in future sessions
  "occurrence_count": 1,        # increments on each future hit
  "embedding": [...]            # for dedup — cosine > 0.92 = update existing, not new entry
}
```

**Write 2 — lse-kb index (via index_to_kb, quality_score=1.0):**
```
{
  "attempts": [embed1, embed2, embed3],          # all attempt texts + embeddings
  "attempt_texts": ["...", "...", "..."],
  "failure_reasons": ["...", "...", "..."],       # why each failed
  "escalation_trigger": "convergence|attempt_limit|claude_only_override",
  "web_search_query": "...",                      # the query that was tried
  "web_search_result": "...",                     # what was found (the authoritative source)
  "web_assisted_attempt": "...",                  # attempt 4 text
  "claude_solution": "...",                       # what actually worked
  "attempt_vs_solution_diff": "...",              # structured delta between best attempt and solution
  "quality_score": 1.0,
  "source": "competition_escalation"
}
```

The **attempt-vs-solution diff** is the most valuable signal for tracking model capability growth. If the gap between "what the model tried" and "what worked" shrinks across episodes, the model is improving. That is the PhD metric made concrete.

The **lse-errors write** is what closes the loop permanently. The next session hitting the same error pattern reaches step 0, applies the resolution, and never reaches step 5 again. Claude is called once per error class, not once per episode.

---

## 5. KB Isolation

**Shared pool. Intentional.** This is the public goods game design. All models read from and write to the same lse-kb index.

KB entries written during competition episodes carry `"source": "competition"` and `"competition_kb_assisted": true` in the result when retrieved. The harness sees whether a solution was KB-assisted and can surface this in episode statistics. It does NOT reduce points — KB retrieval earns +2 bonus. Contributing to the pool is rewarded, not penalized.

---

## 6. Architecture

```
ChallengeDB (SQLite — deterministic, versioned challenges)
        ↓
LSEChallengeEnv(gymnasium.Env)
  - observation: challenge text + attempt history + KB hits
  - action: model response + tool calls
  - reward: points delta
  - terminated: solved or escalated
  - info: discipline, attempt_n, convergence_score, kb_assisted
        ↓
┌─────────────────────┬──────────────────────┬──────────────────────┐
│  Gemma 4 31B        │  Qwen3.6-27B         │  Qwen3.6-35B-A3B     │
│  NODE2 :8081        │  LUCIFER :8080        │  LUCIFER :8082 (seq) │
└─────────────────────┴──────────────────────┴──────────────────────┘

HARDWARE (updated 2026-06-03):
   LUCIFER: RTX 4090 (24 GB) — Qwen3.6-27B-Q4_K_M production model (:8080)
            Qwen3.6-35B-A3B runs sequentially after primary completes (:8082)
   NODE2:   RTX 3090 (24 GB), Ubuntu native — Gemma 4 31B Q4_K_M (:8081)
            ~20GB VRAM at Q4_K_M, fits with headroom, 30–34 t/s decode
   NODE3:   RTX 5090, AMD 9800X3D, 64GB RAM, Win11 — WSL2 setup pending
            Future third parallel node when WSL2 deployed

MODEL ROSTER (2026-06-03 — Qwopus dropped):
   Qwen3.6-27B-Q4_K_M  — primary LSE model, already in production, best agentic
                           coding (SWE-bench 77.2%), 18GB VRAM, Intelligence Index 45.8
   Gemma 4 31B Q4_K_M  — NODE2 candidate, best coding benchmark (Coding Index 38.7),
                           GPQA 85.7%, native tool use, day-one llama.cpp support
                           Confirmed RTX 3090 compatible at Q4_K_M
   Qwen3.6-35B-A3B     — speed benchmark slot; 3B active params, 65 t/s, sequential
   Qwopus              — DROPPED. Community preview distillation of Claude Opus
                           reasoning into Qwen3.5 base. Known formatting instability,
                           token corruption, immature evaluation scope.
                           Not suitable for reproducible arena evaluation.

   AsyncVectorEnv: LUCIFER + NODE2 run truly parallel. Third slot sequential (phase 1).
   NODE2 setup needed: llama-server or LM Studio OpenAI-compat endpoint on Ubuntu.

        ↓ (convergence detected or attempt 3 exhausted)
EscalationGate
  1. Embed all attempts, compute pairwise cosine similarity
  2. Format escalation context (attempts + failure reasons + search findings)
  3. POST to Claude API
  4. Log layered KB entry via index_to_kb()
  5. Apply point deltas

        ↓
LeaderboardService
  - Running PhD points per model per discipline
  - Episode statistics via RecordEpisodeStatistics wrapper
  - Replay log (every episode, win or lose)
```

### Gymnasium components in use

| Component | Role |
|---|---|
| `gymnasium.Env` | Single-episode challenge harness (step → obs/reward/terminated/info) |
| `gymnasium.vector.AsyncVectorEnv` | Parallel episode instances (if VRAM allows) |
| `gymnasium.wrappers.TimeLimit` | Enforces attempt ceiling per episode |
| `RecordEpisodeStatistics` | Auto-tracks cumulative reward, episode length, time |

Gymnasium is NOT used to train the LLMs (inference-only). The RL component — a lightweight meta-controller learning which model to route a problem type to first — is a later phase requiring several hundred episodes of data.

---

## 7. Sandbox and Deployment Gate

### Gate definition (all must be true for sandbox PASS)

1. Solution executes without errors in isolated environment
2. No adjacent services affected (verified by post-run health check)
3. Output matches expected result (deterministic assertion)
4. Rollback exists (config backed up before any mutation)

### Production deploy criteria

- All 4 sandbox criteria pass
- Tier 1–2: auto-approve
- Tier 3–5: human approval required

This gate IS the eval rubric. A model that solves but fails criterion 2 scores partial credit. A model that backs up before mutating scores the rollback bonus even on failure.

### pfSense write access gate (T3+ challenges only)

Write access to the pfSense REST API is a named temporary elevation, not a standing permission.
The gate enforces strict sequencing:

```
Sandbox PASS (all 4 criteria) + Human approval
        ↓
Enable write: pfSense UI → System → REST API → disable Read Only
        ↓
Execute production deploy (challenge solution)
        ↓
Verify: re-run assertions against live pfSense
        ↓
Re-enable Read Only — MANDATORY before session ends
        ↓
Log to CHANGELOG: timestamp, what was changed, verification result
```

A challenge episode that leaves Read Only disabled at session end is scored as a **failure**
regardless of whether the solution was technically correct. Restoring the security posture
is part of the solution, not optional cleanup.

---

## 8. Challenge Domains

### Domain: pfSense Network Administration

**Infrastructure already in place:**
- pfSense Plus 26.03.1 at 192.168.1.50
- SSH: `ssh admin@192.168.1.50` ✅ confirmed
- Syslog → LUCIFER:514 UDP ✅ live and flowing
- WSL2 mirrored networking → LSE can reach all subnets ✅

**REST API write access protocol — permanent rule:**
Default posture is **read-only**. For T3+ challenges that write firewall rules:
1. Enable write in pfSense UI (System → REST API → disable Read Only) immediately before the task
2. Complete the task and verify the sandbox gate passes
3. Re-enable Read Only immediately after — before ending the session
Leaving write enabled between sessions is a security violation. Every write-enabled session must be logged in CHANGELOG with timestamp and what was changed.

**REST API:** Community package (pfrest.org) supports Plus 26.03. Install via one SSH command:
```bash
pkg-static -C /dev/null add https://github.com/pfrest/pfSense-pkg-RESTAPI/releases/latest/download/pfSense-26.03-pkg-RESTAPI.pkg
```
Then enable in System → REST API → create API key. 200+ endpoints, Swagger UI at `https://192.168.1.1/api/v2/documentation`. Fallback if unavailable: SSH + `/cf/conf/config.xml` + `pfctl` commands.

**Sandbox approach:** T1 (read-only): direct production queries via REST API or SSH — no sandbox needed. T2: syslog corpus snapshot replayed deterministically. T3+: Docker bridge container on lse-net to test rule proposals before SSH deployment to live pfSense.

### Domain: Home Assistant

**Infrastructure:**
- Live HA on Raspberry Pi 4, HA OS
- Subnets: LAN (192.168.1.x), IoT/solar (192.168.10.x via igc3)
- Solar inverter at 192.168.10.3 already in HA

**Sandbox approach:** HA Core in Docker (`ghcr.io/home-assistant/home-assistant:stable`).
- Same automation engine, dashboard renderer, YAML config format as HA OS
- Missing: Supervisor layer, add-on store (not needed for challenge work)
- Local hardware integrations (Zigbee USB, Z-Wave) show as `unavailable` — acceptable for dashboard/automation work
- Cloud integrations work normally

**Deploy estimate:** 45–60 min.
1. Pull Pi config via HA backup (Settings → Backup → download `.tar`)
2. Extract `/homeassistant/` config layer from tar
3. Mount as Docker config volume
4. Use dummy values in `secrets.yaml` (real secrets stay on Pi)

**Porting work back to live Pi:** Frictionless for pure config. File format is identical between HA Core Docker and HA OS. Copy YAML → restart HA on Pi → done.

---

## 9. The 50-Challenge Ladder

### Tier structure

| Tier | Challenges | Mode | Principle |
|---|---|---|---|
| 1 — Insight | 1–10 | Read-only, no sandbox needed | Understand before touching |
| 2 — Local scripts | 11–20 | Sandbox: output only, no system mutation | Build tools |
| 3 — Service config | 21–35 | Sandbox → gate → production | Change with rollback |
| 4 — Cross-service | 36–45 | Sandbox → gate → production | Coordinate systems |
| 5 — Innovation | 46–50 | Proposal + sandbox proof-of-concept | Suggest + validate |

### pfSense challenges (distributed across tiers)

**T1 — Insight**
- Parse firewall logs: top 10 blocked IPs, failed auth by source, rules hit frequency
- DNS query log: top queried domains, flag DGA-like names and high-frequency resolvers
- Traffic summary: bytes in/out per LAN device over last 24h

**T2 — Local scripts**
- Log ingestion script: syslog UDP listener → structured JSON → SQLite, in Docker bridge container
- Daily security digest generator: top events, anomaly flags, formatted for human review

**T3 — Service config**
- Propose and implement firewall rule from T1 findings; verify in sandbox; deploy via SSH
- GeoIP enrichment: tag blocked IPs with country, flag high-risk regions, generate rule set proposal

**T4 — Cross-service**
- pfSense + HA integration: trigger HA notification when specific firewall event fires (e.g., repeated failed auth from LAN device)

**T5 — Innovation**
- Network architecture review: traffic analysis → propose VLAN segmentation or rate-limiting changes with written justification

### Home Assistant challenges (distributed across tiers)

**T1 — Insight**
- Inventory all entities, devices, and automations — structured map of current HA instance
- Identify unused or stale automations (entities not fired in 30 days)
- Energy consumption baseline: which devices draw most, identify patterns

**T2 — Local scripts**
- Dashboard configuration (YAML): purpose-built for a specific room or use case; validate in sandbox HA
- New automation from scratch (trigger/condition/action); test against sandbox

**T3 — Service config**
- Deploy new dashboard to production HA; verify via API that entities load correctly
- Presence detection improvement: refine existing automations from T1 findings

**T4 — Cross-service**
- Suggest 3 specific devices to add: justified by T1 capability gap analysis, with integration path documented
- pfSense + HA: network-aware automation (e.g., turn on guest network when HA detects a guest device)

**T5 — Innovation**
- Full automation suite: multi-room scene with energy optimization and presence logic

---

## 10. Challenge Authorship Requirements

Every challenge in the set must have all four of these before it goes in ChallengeDB:

**1. A verified correct solution** — the problem has been solved already (in production or in a test run) or the exact solution is fully specified. Not "it should work" — known to work.

**2. A reproducible starting state** — the sandbox can be reset to this state deterministically. For pfSense T1 (read-only log replay): a fixed syslog corpus snapshot. For HA T2 (dashboard): a clean HA Core Docker instance from a known config backup. The starting state is stored in `starting_state` JSON in ChallengeDB.

**3. A machine-checkable assertion** — not "looks right" but:
```python
assert rule_count == 47
assert entity_id in dashboard_entities
assert blocked_ips[0]["count"] > 100
assert "192.168.1.90" in dhcp_leases
```
Partial credit requires the assertions to have weight. Suggest: each challenge has 3 assertions worth 1 point each (inheriting the existing 3-point eval pattern). A model scores 0/3, 1/3, 2/3, or 3/3 per challenge, modified by discipline weight.

**4. A documented failure mode** — what a partial or wrong solution looks like, so partial credit scoring is unambiguous. E.g.: "Model lists IPs but doesn't rank by frequency → 1/3. Model ranks correctly but doesn't identify the top blocked port → 2/3."

The real problems (pfSense log analysis, HA dashboard creation) naturally produce all four because the correct answer is already known from operational experience. This is exactly what "quality of simulation is crucial" means in practice.

**Authorship gate:** No challenge enters ChallengeDB until all four elements are documented. Incomplete challenges are held in a `draft_challenges/` directory.

---

## 11. Challenge Schema (SQLite)


```sql
CREATE TABLE challenges (
    id              TEXT PRIMARY KEY,       -- e.g. "pf-t1-001"
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,          -- the problem statement given to the model
    domain          TEXT NOT NULL,          -- "pfsense" | "homeassistant" | "sysadmin" | ...
    discipline      TEXT NOT NULL,          -- "sysadmin" | "debugging" | "security" | "coding" | "performance" | "constraint_satisfaction"
    tier            INTEGER NOT NULL,       -- 1–5
    mode            TEXT NOT NULL,          -- "read_only" | "sandbox_output" | "sandbox_gate" | "production"
    starting_state  TEXT,                   -- JSON: files/configs/log corpus to seed per episode
    success_criteria TEXT NOT NULL,         -- JSON: assertions to evaluate (output match, service health, etc.)
    rollback_defined INTEGER DEFAULT 0,     -- 1 if a rollback procedure is specified
    requires_human_approval INTEGER DEFAULT 0, -- 1 for tier >= 3 production deploys
    discipline_multiplier REAL NOT NULL,    -- from discipline weights table
    max_attempts    INTEGER DEFAULT 3,
    claude_only_override INTEGER DEFAULT 0, -- 1 = escalate on attempt 1
    created_at      TEXT,
    version         INTEGER DEFAULT 1
);

CREATE TABLE episodes (
    id              TEXT PRIMARY KEY,
    challenge_id    TEXT REFERENCES challenges(id),
    model_id        TEXT NOT NULL,          -- "qwen-27b" | "gemma-26b" | "qwopus-35b"
    attempt_count   INTEGER,
    convergence_triggered INTEGER DEFAULT 0,
    kb_assisted     INTEGER DEFAULT 0,
    escalated       INTEGER DEFAULT 0,
    escalation_context_quality TEXT,        -- "good" | "poor" | null
    sandbox_pass    INTEGER,
    human_approved  INTEGER,
    deployed        INTEGER DEFAULT 0,
    base_points     INTEGER,
    bonus_points    INTEGER,
    total_points    REAL,                   -- base + bonus × discipline_multiplier
    started_at      TEXT,
    completed_at    TEXT
);
```

---

## 12. Open Questions

- **NODE2 setup:** Model decided — Gemma 4 31B Q4_K_M (~20GB VRAM, confirmed RTX 3090 compatible). LM Studio installed. Enable server mode → expose OpenAI-compat endpoint on :8081. Gemma 4 31B is the strongest complement to Qwen3.6-27B: different architecture, different strength profile (Gemma leads on GPQA, Qwen leads on agentic coding).
- **Scoring rubric grain:** Resolved — 3-point partial credit per challenge, inheriting existing eval pattern. Each challenge has 3 assertions × 1 point, × discipline multiplier.
- **Third model (slot :8082):** With NODE3 off-limits, the third model either runs on LUCIFER after the first finishes (round-robin) or we run 2-model competition initially and expand later.

---

## 13. Infrastructure Pre-conditions

Before any challenge can run, these must be in place:

| Pre-condition | Status | Action |
|---|---|---|
| WSL2 mirrored networking | ✅ confirmed | `networkingMode=mirrored` in `.wslconfig` |
| pfSense SSH access | ✅ confirmed | `ssh admin@192.168.1.50` |
| pfSense syslog → LUCIFER:514 | ✅ confirmed | Live and flowing |
| pfSense REST API package | ✅ live | v2.8, read-only, LAN+WAN+OPT1+OPT2, key in Vaultwarden |
| HA long-lived access token | ❓ unknown | HA profile → Security → Long-lived tokens |
| QNAP admin credentials | ❓ unknown | QNAP web UI or SSH on 192.168.5.x |
| Syslog collector container (LUCIFER) | ❌ pending | Persistent Docker container, UDP 514, JSON→SQLite |
| NODE2 model endpoint | ❌ pending | LM Studio server mode or llama-server on 3090 |
| HA sandbox container | ❌ pending | `ghcr.io/home-assistant/home-assistant:stable` on lse-net |

**Full T1 challenge specs (assertions + failure modes):** `docs/network-topology.md` §Tier 1 Challenge Set

---

## 14. Build Order

1. **Install pfSense REST API package** — one SSH command, ~5 min
2. **Hand-author T1 pfSense challenges** — fill in assertions + failure modes in network-topology.md; no sandbox infra needed
3. **Seed ChallengeDB** — SQLite schema, insert T1 challenges
4. **NODE2 setup** — LM Studio server mode or llama-server on the 3090; expose OpenAI-compat endpoint
5. **Deploy HA sandbox container** — Docker on lse-net, ~45–60 min
6. **Build LSEChallengeEnv** — gymnasium.Env, single-episode, no async yet
7. **Build EscalationGate** — convergence detection + Claude API + KB logging
8. **Build LeaderboardService** — point tracking, episode statistics
9. **AsyncVectorEnv** — after NODE2 is confirmed working as a parallel inference node
3. **ChallengeDB schema** — SQLite, seed T1 challenges
4. **LSEChallengeEnv** — gymnasium.Env wrapper, single-episode, no async yet
5. **EscalationGate** — convergence detection, Claude API call, KB logging
6. **LeaderboardService** — point tracking, episode statistics
7. **AsyncVectorEnv** — only after VRAM strategy is decided
8. **T2–T5 challenges** — authored progressively as harness matures

---

## 16. Applying Claude's Course-Correction Mechanisms to Local Models

> Source: analysis of Claude's Constitutional AI, extended thinking, and PRM training, 2026-06-03.
> These are harness-level compensations — no local model retraining required.

---

### 16.1 What makes Claude different (and what can be transferred)

Claude's course-correction capability comes from three sources: Constitutional AI training (self-critique loop baked into weights), extended thinking scratchpad (hidden reasoning before output), and Process Reward Models (good reasoning steps explicitly rewarded during training). None of these can be installed into a local model post-hoc.

But the **effect** they produce — self-correction, frame-breaking, assumption-questioning — can be approximated at the **harness level** by changing what the model receives as input. The key design principle:

> **Shift meta-reasoning to the harness. Don't ask local models to detect their own stagnation — the harness detects it and injects the corrective signal. The model's job is to generate; the harness's job is to evaluate, detect, and reframe.**

This is tractable because local models at 27B can follow explicit instructions well — they just can't reliably generate those instructions for themselves.

---

### 16.2 Technique A — Thinking mode escalation (Qwen3.6-27B specific)

Qwen3.6-27B supports extended thinking mode via a budget parameter. Under normal operation the harness runs with a conservative thinking budget. When stagnation is detected (cosine > 0.85), the harness **upgrades the next attempt to full thinking budget**:

```python
# Normal attempt
response = call_model(prompt, thinking_budget=512)

# Stagnation-breaking attempt — harness upgrades automatically
if stagnation_detected:
    response = call_model(prompt, thinking_budget=4096,
        prefix="Before answering, reason through why your previous approaches failed.")
```

This gives the model scratchpad space to reason about its own failure history before committing to attempt N+1. It is the closest local equivalent to Claude's extended thinking. Gemma 4 31B also has configurable thinking modes — apply the same pattern.

**Cost:** ~3–5× slower for the stagnation-breaking attempt. Acceptable given that stagnation means the fast path has already failed.

---

### 16.3 Technique B — Forced assumption naming (Constitutional AI substitute)

Constitutional AI trains the model to critique its own output before finalizing it. The harness approximates this by injecting an explicit critique requirement **before** the stagnation-breaking attempt:

```
STAGNATION DETECTED — similarity between attempts {n-1} and {n}: {score:.2f}

Your last {n} attempts have been semantically equivalent. Before your next attempt:

1. State explicitly: what assumption have you been making in all prior attempts?
2. State whether that assumption has been verified against the problem constraints.
3. If unverified: attempt WITHOUT that assumption as a starting point.

Prior attempts summary:
{attempt_summary}

Assertions that must pass:
{assertion_list}
```

The key: forcing the model to **name the assumption** is itself the frame-breaking act. A model that articulates "I have been assuming the issue is the rule syntax" has already partially escaped the anchor, because naming a frame is the first step to questioning it.

This works at 27B because it's instruction-following, not meta-reasoning. The model doesn't need to independently realize it's stuck — the harness tells it.

---

### 16.4 Technique C — Temperature modulation

Semantic stagnation reflects the model converging on a probability attractor — the same high-probability token paths dominate every generation. Higher temperature forces exploration of lower-probability paths.

```python
# Standard attempts
temperature = 0.65  # Qwen3.6-27B production default

# Stagnation-breaking attempt
temperature = 0.95  # forces token-path diversification
```

Apply only to the stagnation-breaking attempt, then return to normal temperature. Persistent high temperature degrades output quality; targeted use breaks attractors without degrading the episode overall.

**Gemma 4 31B note:** Community benchmarks show Gemma 4 31B is less temperature-sensitive than Qwen3.6-27B — apply same technique but may need slightly higher values (1.0–1.1) for equivalent diversification effect.

---

### 16.5 Technique D — Contrastive failure injection

When the harness detects functional stagnation (same assertion failure across attempts despite different surface approaches), it constructs a contrastive observation:

```
Your last {n} attempts have all failed on the same assertion:
  "{failing_assertion}"

The attempts differ in approach:
  Attempt 1: {summary_1}
  Attempt 2: {summary_2}

But both fail on the same assertion. This means the issue is NOT the implementation path.
The assertion "{failing_assertion}" depends on condition: {inferred_precondition}.

Verify that condition before attempting again.
```

The harness can extract `inferred_precondition` from the challenge's assertion structure — each assertion is a machine-checkable condition with known dependencies defined at challenge authorship time. This is the case where the challenge authorship requirement for "documented failure modes" pays off: failure modes specify what preconditions a wrong solution violates.

---

### 16.6 Technique E — Stagnation-aware web search query construction

When stagnation triggers the web search step, the harness modifies the search query construction prompt:

```
Normal search prompt:
"Search for: how to [solve problem X]"

Stagnation-aware search prompt:
"Your attempts to solve this via [dominant_approach] have failed.
Search for: why does [dominant_approach] fail when [observed_symptom]
Focus on failure modes, not solutions. Official docs and man pages only."
```

Searching for the failure mode rather than the solution bypasses the semantic anchor. A web result that explains *why* an approach fails provides the frame-breaking information the model needs — something a solution-focused query would not surface.

The harness extracts `dominant_approach` from the attempt embeddings by finding the centroid of the stagnant cluster.

---

### 16.7 Technique F — Stagnation pattern accumulation in lse-errors

When a stagnation is broken (by any technique), the KB entry includes the stagnation pattern:

```python
record_error(
    error_text=f"Stagnation on {challenge_class}: {dominant_concept}",
    context=f"Wrong assumption: {named_assumption}. Breaking approach: {what_worked}",
    resolution=f"Inject assumption-questioning prompt. Search for failure mode of {dominant_concept}."
)
```

Future `check_error_kb()` calls at step 0 match not just error strings but stagnation patterns by challenge class. A future model hitting the same challenge class receives a pre-warning before attempt 1:

```
KB MATCH — Known stagnation pattern for challenge class {class}:
  Models commonly get stuck assuming: {wrong_assumption}
  Verify {precondition} before proceeding.
  Breaking approach that worked: {summary}
```

This turns historical stagnation into proactive protection — the KB teaches future models to avoid the anchor before they enter it.

---

### 16.8 What cannot be transferred

These Claude capabilities require retraining and cannot be approximated at the harness level:

- **Constitutional AI** — the self-critique loop is weight-level behavior. The harness approximation (Technique B) is a prompt injection, not a trained behavior. It works for explicit stagnation but won't generalize to novel failure modes the way trained self-critique does.
- **Process Reward Models** — rewarding good reasoning steps requires a trained evaluator. The harness can inject step-checkpoints but cannot score them.
- **Scale-based meta-reasoning** — a 27B model genuinely has less representational capacity for reasoning about its own reasoning than a frontier model. Techniques A–F compensate but do not close this gap for the hardest cases. For those, escalation to Claude is the correct response.

The boundary this defines: local model stagnation mitigation handles **type-1 and type-2 stagnation** (wrong syntax/path, missing precondition detectable from assertions). **Type-3 stagnation** (invisible frame, novel unknowable dependency) goes to Claude, which has the representational capacity and Constitutional AI training to identify frames that local models cannot see.

---

## 13. What Must NOT Be Built Yet

- No harness code before T1 challenges are authored (simulation quality is the critical dependency)
- No production deployments before sandbox gate is implemented and tested
- No AsyncVectorEnv before VRAM strategy is decided

---

## 15. Gymnasium Integration Notes

> Source: gymnasium.farama.org API review, 2026-06-03.
> These are design decisions, not aspirational — they constrain how LSEChallengeEnv must be implemented.

---

### 15.1 `terminated` vs `truncated` — the escalation split

Gymnasium v0.26 replaced the single `done` flag with two flags that mean distinct things. The distinction is load-bearing for the arena:

| Flag | Meaning in Gymnasium | LSE mapping |
|---|---|---|
| `terminated=True` | Agent reached a defined terminal state in the MDP | Challenge solved **OR** escalation triggered after all attempts exhausted |
| `truncated=True` | Episode ended by an external condition (not MDP-internal) | Semantic stagnation detected mid-episode (cosine > 0.85); `TimeLimit` step ceiling hit |

The current arena doc conflates these. The correct split: stagnation is an externally-imposed cutoff — it belongs in `truncated`, not `terminated`. This matters if a meta-controller RL policy is added later: algorithms like PPO bootstrap differently from truncated vs terminated states.

**Concrete rule:**
- `step()` returns `terminated=True` only when an assertion suite passes (solve) or when escalation is final (all attempts + web search exhausted, Claude called).
- `step()` returns `truncated=True` when the `EscalationWrapper` detects convergence (cosine > 0.85) or `TimeLimit` fires.

---

### 15.2 Wrapper stack — the right structure for EscalationGate

The `EscalationGate` should not be a standalone service — it is a `gymnasium.Wrapper`. The full stack:

```python
LSEChallengeEnv(base)
  └─ EscalationWrapper          # step() intercept: embed attempt, cosine check, Claude API call, KB write
      └─ TimeLimit(max_episode_steps=3)   # truncated=True on attempt ceiling
          └─ RecordEpisodeStatistics       # auto: cumulative reward, episode length, wall time → info["episode"]
```

Each layer has exactly one responsibility. The wrapper chain means:

- `EscalationWrapper.step()` calls `self.env.step(action)` → checks convergence → if stagnation: calls Claude, writes KB entry, returns `(obs, reward, truncated=True, info)`. Otherwise passes through.
- `TimeLimit` wraps `EscalationWrapper` — if 3 steps complete without `terminated` or `truncated`, it fires `truncated=True`. The `EscalationWrapper` must call Claude on `TimeLimit` truncation too (handle in `step()` by checking `truncated` from the inner env).
- `RecordEpisodeStatistics` is the outermost layer — it sees all terminal/truncated signals and populates `info["episode"]` automatically. This is the `LeaderboardService` data feed; no separate implementation needed.

The `EscalationWrapper` is also where the KB hit detection lives: before calling `self.env.step(action)`, call `search_kb(action_embedding)` and set `kb_assisted=True` in the observation if a hit is returned.

---

### 15.3 Observation and action spaces

LLM actions are strings, not numpy arrays. Gymnasium v0.26+ provides `spaces.Text`:

```python
import gymnasium as gym

class LSEChallengeEnv(gym.Env):
    def __init__(self, model_endpoint: str, db_path: str = "/opt/local-se/challenges.db"):
        self.model_endpoint = model_endpoint
        self.db_path = db_path

        self.observation_space = gym.spaces.Dict({
            "challenge":       gym.spaces.Text(max_length=4096),   # problem statement
            "attempt_history": gym.spaces.Text(max_length=8192),   # prior attempts, newline-delimited
            "kb_context":      gym.spaces.Text(max_length=4096),   # KB hits retrieved before step
        })
        self.action_space = gym.spaces.Text(min_length=1, max_length=8192)  # model response
```

The harness never calls `env.action_space.sample()` — that path is for random baselines only. But declaring the spaces lets `check_env()` validate the implementation and enables future wrapper compatibility.

**`_get_obs()` helper pattern** (from Gymnasium custom env tutorial — keep observations DRY):

```python
def _get_obs(self) -> dict:
    return {
        "challenge":       self._current_challenge["description"],
        "attempt_history": "\n---\n".join(self._attempt_texts),
        "kb_context":      self._last_kb_hit or "",
    }

def _get_info(self) -> dict:
    return {
        "attempt_n":             len(self._attempt_texts),
        "convergence_score":     self._last_convergence_score,
        "kb_assisted":           self._kb_assisted,
        "discipline_multiplier": self._current_challenge["discipline_multiplier"],
        "challenge_id":          self._current_challenge["id"],
        "model_id":              self._model_id,
    }
```

`info` is never used by the agent (model doesn't see it) — it feeds `RecordEpisodeStatistics` and the leaderboard.

---

### 15.4 Episode parameterization via `reset(options=...)`

The standard Gymnasium pattern for seeding a specific episode:

```python
obs, info = env.reset(options={"challenge_id": "pf-t1-001", "model_id": "qwen-27b"})
```

`reset()` pulls the challenge row from ChallengeDB, restores the `starting_state` JSON, clears attempt history, and returns the initial observation. No subclassing or kwargs proliferation needed.

```python
def reset(self, seed=None, options=None):
    super().reset(seed=seed)
    options = options or {}
    challenge_id = options.get("challenge_id")  # if None, pick next in ladder
    self._model_id = options.get("model_id", "unknown")
    self._current_challenge = self._load_challenge(challenge_id)
    self._attempt_texts = []
    self._attempt_embeddings = []
    self._last_convergence_score = 0.0
    self._kb_assisted = False
    self._last_kb_hit = None
    return self._get_obs(), self._get_info()
```

---

### 15.5 `AsyncVectorEnv` for LUCIFER + NODE2 parallel episodes

Each vector env instance runs in a subprocess (true OS-level parallelism). The model HTTP call is a blocking network request inside the subprocess — fine for inference. The setup:

```python
def make_env(model_endpoint, db_path):
    def _init():
        env = LSEChallengeEnv(model_endpoint=model_endpoint, db_path=db_path)
        env = EscalationWrapper(env)
        env = TimeLimit(env, max_episode_steps=3)
        env = RecordEpisodeStatistics(env)
        return env
    return _init

vec_env = gym.vector.AsyncVectorEnv([
    make_env("http://localhost:8080",         "/opt/local-se/challenges.db"),  # LUCIFER / Qwen-27B
    make_env("http://192.168.1.NODE2:8080",   "/opt/local-se/challenges.db"),  # NODE2 / Gemma-26B
])

# Run two episodes in parallel:
obs, info = vec_env.reset(options=[
    {"challenge_id": "pf-t1-001", "model_id": "qwen-27b"},
    {"challenge_id": "pf-t1-001", "model_id": "gemma-26b"},
])
```

Both models run the same challenge simultaneously. `RecordEpisodeStatistics` in each subprocess feeds the leaderboard independently. **Prerequisite:** NODE2 model endpoint confirmed reachable from LUCIFER (see §13 infra pre-conditions).

**Phase 1 (before NODE2 is ready):** Use `SyncVectorEnv` with a single env, or just call `env.step()` directly in a loop. `AsyncVectorEnv` is a drop-in upgrade once NODE2 is online.

---

### 15.6 Validate with `check_env()` before first real episode

```python
from gymnasium.utils.env_checker import check_env

env = LSEChallengeEnv(model_endpoint="http://localhost:8080")
check_env(env)  # raises on: wrong return shapes, missing super().reset(), space mismatches
```

Run this against a stub challenge (hardcoded observation, no real model call) before any live inference. It catches implementation bugs that would otherwise surface as cryptic errors mid-episode.

---

### 15.7 KB integration points in the wrapper stack

The KB (RAG stack) connects to the harness at four explicit points:

| Point | Where | What happens |
|---|---|---|
| `search_kb()` | `EscalationWrapper.step()` — before passing action to base env | Query KB with action embedding; if hit ≥ 0.72, set `kb_assisted=True`, append to observation |
| `index_to_kb()` | `EscalationWrapper` — on `terminated=True` (solved) | Index the successful solution with `quality_score=0.9`, `source="competition_solve"` |
| `index_to_kb()` (escalation entry) | `EscalationWrapper` — on escalation trigger | Index full layered entry: attempt texts + embeddings + failure reasons + Claude solution + diff; `quality_score=1.0`, `source="competition_escalation"` |
| `record_outcome()` | `EscalationWrapper` — post-episode | Update `empirical_runs` / `empirical_failures` on any KB doc that was retrieved and used |

The KB bonus (+2 pts) and the indexing bonus (+1 pt) are computed in `EscalationWrapper` and added to the reward before `RecordEpisodeStatistics` sees the episode total.
