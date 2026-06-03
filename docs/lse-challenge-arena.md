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
   → index_to_kb(result + query_that_found_it) ALWAYS — regardless of outcome
   → Web-assisted attempt 4
   → Solved? Done. quality_score=0.9 (web-verified).
   → Failed? → ESCALATE

5. Escalation to Claude
   → full context: all attempt embeddings + search findings + failure reasons
   → Claude solution indexed to KB (layered entry, see below)
   → Apply −5 (escalation) + +1 (indexing bonus) to triggering model
   → Apply +2 to triggering model if escalation context was well-framed
```

### Why the convergence check beats the attempt counter

A model can make 5 meaningfully different attempts OR repeat the same approach with slight variations. The signal needed is **semantic stagnation** — the model is circling. Cosine similarity on attempt embeddings detects this faster and more accurately than counting.

A model that genuinely tries different approaches gets more runway. A model stuck in a loop gets cut off faster. This also prevents gaming by padding attempt count.

### What gets logged on escalation (KB entry structure)

```
{
  "attempts": [embed1, embed2, embed3],          # all attempt texts + embeddings
  "attempt_texts": ["...", "...", "..."],
  "failure_reasons": ["...", "...", "..."],       # why each failed
  "escalation_trigger": "convergence|attempt_limit|claude_only_override",
  "web_search_query": "...",                      # the query that was tried
  "web_search_result": "...",                     # what was found
  "claude_solution": "...",                       # what actually worked
  "attempt_vs_solution_diff": "...",              # structured delta
  "quality_score": 1.0,
  "source": "competition_escalation"
}
```

The attempt-vs-solution diff is the most valuable signal for tracking model capability growth. If the gap between "what the model tried" and "what worked" shrinks across episodes, the model is improving. That is the PhD metric made concrete.

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
┌──────────────┬──────────────┬──────────────┐
│  Gemma-26B   │  Qwen-27B    │  Qwopus-35B  │
│  :8081       │  :8080       │  :8082       │
└──────────────┴──────────────┴──────────────┘

HARDWARE (updated — VRAM concurrency largely solved):
   LUCIFER: RTX 4090 (24 GB) — hosts one model node (:8080)
   NODE2:   RTX 3090 (24 GB), Ubuntu, LM Studio — hosts second model node (:8081)
   NODE3:   RTX 5090 (16 GB+) — GAMING PC, do not touch, WSL not set up
   
   Two models run truly in parallel across separate machines (network inference).
   Third model runs on LUCIFER after first completes, or on CPU offload.
   AsyncVectorEnv with 2 genuinely parallel + 1 sequential is acceptable for phase 1.
   NODE2 setup needed: deploy OpenWebUI, configure llama-server or LM Studio OpenAI-compat endpoint.

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

- **NODE2 setup:** OpenWebUI + llama-server or LM Studio OpenAI-compat endpoint needed. What model to deploy on the 3090 (24 GB)? Gemma-27B-Q4 fits. LM Studio already installed — may just need the server endpoint enabled.
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

## 13. What Must NOT Be Built Yet

- No harness code before T1 challenges are authored (simulation quality is the critical dependency)
- No production deployments before sandbox gate is implemented and tested
- No AsyncVectorEnv before VRAM strategy is decided
