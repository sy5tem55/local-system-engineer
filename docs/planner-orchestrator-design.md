# Planner-Orchestrator — Pre-flight Triage on Hermes
> Status: DESIGN for 1.7.2 · 2026-06-12 (P22 Cowork)
> Trigger incident: "Goethe spiral" — 34 web searches, ~78K tokens, two turns,
> zero surfaced output on turn 2, fabricated verbatim quote on turn 1.
> Companions: cogitator v1.7.1 (budget gates + task blocks, SHIPPED), lse-1.7.0-design §2 (Hermes protocol).

---

## 1. Problem statement

LSE cannot monitor its own context fill: the model's attention is fully absorbed
by the task (observed: `get_context_status` exists and was never called during
the spiral; the context-monitor filter watched and could not intervene).
Therefore session-feasibility decisions must happen BEFORE execution, outside
the executing model, and termination must be enforced IN CODE during execution.

Three interlocking layers, two already shipped in v1.7.1:

| Layer | Where | Mechanism | Status |
|---|---|---|---|
| 1. Budget gates | cogitator (code) | rolling-window web-call budget; banner at ≤2, refusal at 0 | SHIPPED v1.7.1 |
| 2. Task blocks | cogitator + SQLite | task_checkpoint/task_resume carryover | SHIPPED v1.7.1 |
| 3. Planner | Hermes (node3090) | pre-flight prompt packaging + session estimate | THIS DOC |

The planner does not replace layers 1–2; it reduces how often they fire.
A misjudged plan is still contained by the budget gate, and progress is still
preserved by task blocks. No layer trusts model attention.

## 2. Why Hermes

- Already a structured peer with an API surface (gateway :8643, `call_hermes`),
  two-principal protocol designed in 1.7.0-b.
- Already persists tasks: `~/.hermes/kanban.db` — the task board exists.
- Different node (node3090) → planner survives LUCIFER/OWUI session loss.
- Clean capability separation holds: Hermes plans and watches, LSE executes.
  Hermes still gets no SSH to node infrastructure.

## 3. Flow

```
SY5 task → Hermes PLAN intent → plan envelope → SY5 (or filter) starts LSE
   session with packaged prompt → LSE executes (budget-gated, checkpointing)
   → on session end or budget refusal: task block updated → next session:
   task_resume → … → status=done → Hermes notified (kanban card closed)
```

### 3.1 Plan envelope (extends the §2.2 protocol envelope)
```json
{
  "v": 1, "intent": "plan", "correlation_id": "...",
  "task_id": "5128ac43",
  "packaged_prompt": "exact starting prompt for LSE, incl. KB pointers",
  "sessions_estimate": 1,
  "steps": [
    {"n": 1, "what": "...", "web_calls": 2, "tool_calls": 6, "verify": "..."}
  ],
  "single_session": true,
  "confidence": "low|medium|high",
  "abort_criteria": "stop conditions the executor must respect"
}
```

### 3.2 Planner prompt contract (Hermes side)
Input: raw user task + LSE capability sheet (tool list + budget defaults +
the 16-tool-call OWUI session layer limit). Output: the envelope above. Rules:
- DEFAULT to multi-session when research-shaped ("verify", "find all, compare",
  unfamiliar domain). The Goethe task would be classed: 2 sessions, web_calls
  budget 6, abort criterion "if 3 consecutive searches return off-domain hits
  (wrong OPERA/FAUST), stop reformulating — checkpoint and surface."
- Every step gets a verify clause (P2 applies to plans too).
- packaged_prompt must name which KB/skill entries to load first
  (skill_search/search_kb pointers), not just describe the task.

### 3.3 Calibration (estimates will be wrong at first)
- Log per-session actuals (tool calls, web calls, tokens from leaderboard.db /
  llama-server metrics) against the plan's estimates; store delta on the kanban card.
- After ~20 plans: fit the correction factor; until then planner runs
  conservative (prefer splitting into sessions — a needless checkpoint costs
  ~200 tokens; a spiral costs 78K).

## 4. Implementation steps (1.7.2)
1. Hermes-side planner prompt installed as a skill/memory entry (via call_hermes
   task, same install path as the LSE-relationship entry — never hand-edit).
2. `hermes_plan(task)` tool function in cogitator: wraps call_hermes with
   intent=plan, returns the envelope, writes the initial task block
   (task_checkpoint with the planner's packaged_prompt as next_prompt).
3. Filter hook (context-monitor v1.3): on user message that looks like a fresh
   complex task (heuristic: >2 sentences or contains "verify/research/compare"),
   suggest hermes_plan first. Suggestion only — SY5 can bypass.
4. Kanban sync: plan → card created; status=done checkpoint → card closed.
   (Survey kanban.db schema first — same format-survey rule as memories.)
5. Calibration report in leaderboard.py after 20 plans.

## 5. Risks
- **Planner adds latency** to every complex task (~one 27B round-trip). Accept:
  seconds vs 78K-token spirals.
- **Hermes down → no planner.** Degrade: LSE proceeds without a plan; layers
  1–2 still protect. hermes_plan returns "PLANNER UNAVAILABLE — proceed with
  default budgets, checkpoint early."
- **Two task stores** (kanban.db on node3090, tasks.db on LUCIFER). tasks.db is
  ground truth for execution state; kanban is the board view. Sync is one-way
  (LSE → Hermes). Do not let Hermes write tasks.db.
- **Planner self-reports** are estimates, not truth — never raise skill/KB
  quality from a plan, only from verified execution (P2).
