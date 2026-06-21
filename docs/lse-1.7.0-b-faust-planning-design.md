# LSE 1.7.0-b — Faust Multi-Agent Planning Protocol

> Status: DRAFT (P31, 2026-06-19). Supersedes the original 1.7.0-b "Hermes→LSE push channel"
> design. The bidirectional-communication paradigm has changed: agent↔agent and
> human↔agent coordination now happens inside **Faust**, the realtime group-chat app
> that came out of the Coding Gauntlet (`Faust/`), not through an OWUI push channel.

---

## 1. Why the paradigm changed

The original 1.7.0-b framed the problem as "Hermes cannot initiate contact with LSE" and
proposed an OWUI inject / gateway webhook / polling tool to give Hermes a push path into an
LSE session. Cogitator v1.7.15–v1.7.19 partially delivered the pull side (`check_hermes_inbox`,
Path A/B markers, by-reference payloads).

That whole framing assumed the two agents only ever meet inside an OWUI chat turn. **Faust
removes that constraint.** Faust is a standing group-chat server (REST + WebSocket + SQLite)
where humans and local-model agents are first-class room participants. Agents already connect
and exchange messages with a human in the loop. So the coordination problem is no longer "how
does Hermes wake LSE" — it is "what protocol do multiple agents follow, in a shared room, to
plan together and then divide the work," with a human able to watch and gate.

## 2. What Faust is today (grounded read, P31)

- `gate2-group-server/` — the running core server: auth, SQLite store, model-agent accounts,
  REST + WebSocket transport, admin (delete/clear/kick/delete-message), a single-file web UI.
- `gate3-plugin-forge/` — a capability-sandboxed plugin framework (subprocess isolation via
  Node `--permission`), with one reference `/search` plugin. Being folded into gate2 (see §6).
- Orchestration is a **swappable `SpeakerPolicy`** (`protocol.ts`). The only policy today is
  `MentionReplyPolicy`: a turn opens only on a *human* message, agents reply only when
  `@mentioned`, and a recursion budget (`DEFAULT_TURN_BUDGET = 6`) guarantees termination.
- There **is** a WebSocket (message fan-out), but `model_live.ts` sets `stream:false` and there
  is no typing-indicator envelope — agents post a complete message at once, so you cannot watch
  them type in real time. Live typing is out of scope here (see §8, deferred).

The `SpeakerPolicy` interface header already anticipates this work: *"Autonomous-cadence /
director policies are later implementations of this SAME interface — not rewrites."* The
planning protocol is exactly such a director policy.

## 3. Target flow

```
  human: /plan <objective>
      │
      ▼
  ┌─────────────┐   round-robin proposals (≤5 rounds)        agents emit [[CONVERGED]]
  │  PLANNING   │ ──────────────────────────────────────▶   when they agree
  └─────────────┘
      │  all agents CONVERGED in a round  ──or──  round 5 cap reached
      ▼
  ┌──────────────────┐   moderator posts the converged plan; waits for a human admin
  │ AWAITING_APPROVAL│   /approve  → TASKING      /revise <note> → back to PLANNING
  └──────────────────┘
      │  admin /approve
      ▼
  ┌─────────────┐   agents assign each other working tasks via `@handle: <task>`
  │   TASKING   │   emit [[DONE]] when their assignments are placed (≤3 rounds)
  └─────────────┘
      │  all DONE  ──or──  tasking cap
      ▼
  IDLE  (moderator posts the assignment ledger; normal mention-reply resumes)
```

Convergence rule (per the product decision): **agents vote `[[CONVERGED]]`, then the human
admin approves.** Agreement is evaluated at round boundaries — every active agent must carry
`[[CONVERGED]]` in the *current* round for consensus; otherwise the round counter advances and
votes reset, up to a hard cap of 5 rounds.

## 4. How it fits the existing architecture (no rewrites)

Three additive pieces; `MentionReplyPolicy` stays the default and is untouched.

1. **`planning.ts` — `PlanningController`.** Holds per-room state
   (`phase`, `objective`, round-robin `order`, `round`, `spokenThisRound`, `votesThisRound`,
   captured `assignments`) in memory, keyed by `roomId`. Pure state transitions, fully unit-
   testable. Exposes: `startPlanning`, `noteMessage` (scan a landed agent message for the vote
   token + `@handle:` assignments), `nextSpeaker` (round-robin selection; returns `null` and
   transitions to `AWAITING_APPROVAL`/`IDLE` at a boundary), `approve`, `revise`, `phase`,
   and a `takeNotices` queue of moderator announcements the server drains.

2. **`PlanningPolicy implements SpeakerPolicy`.** Wraps a fallback policy (the mention-reply
   policy). `selectResponders`: if the room is mid-planning/tasking, record the just-landed
   message via the controller and return the single next speaker (or `[]` at a boundary);
   if `IDLE`, delegate to the fallback so normal chat is unchanged. State lives in the
   controller — the policy is a thin selector over it. (The interface permits stateful
   policies; only `MentionReplyPolicy` is stateless.)

3. **Server seam — `onTurnComplete`.** One optional dep added to `ServerDeps`, called once
   after each `runTurn` (WS + REST paths). The controller drains queued moderator notices
   there (e.g. the "plan converged — admin approve" prompt) and posts them. Generic and
   additive; mention-reply ignores it.

Human commands (`/plan`, `/approve`, `/revise`) are handled in the existing `onMessage` hook —
the same seam plugins use — so they mutate controller state and post the moderator's framing
message *before* `runTurn` drives the agents.

### Agent-visibility constraint (important)

`agents.ts` excludes `role:"system"` messages from the model context. Therefore all moderator
framing (protocol instructions, phase announcements, the approval prompt) is posted as
**`role:"assistant"`** messages authored by a `moderator` account (`kind:"model"`,
`name:"moderator"`), so the models actually see the protocol in their history. No change to
`agents.ts` is required.

### Termination

Real termination comes from the phase logic: planning halts at consensus or the 5-round cap;
tasking at all-`[[DONE]]` or its cap; both then return `[]`. The numeric `turnBudget` is raised
(e.g. 60) only as a backstop for the recursion engine — it is not the primary guarantee.

## 5. Protocol tokens

- `[[CONVERGED]]` — an agent's vote that it agrees with the current plan (planning phase).
- `[[DONE]]` — an agent has placed all its task assignments (tasking phase).
- `@handle: <task>` — a task assignment captured into the room's assignment ledger.

These are simple, model-emittable, and easy to parse deterministically (no JSON-envelope
fragility — the lesson from the OWUI marker work).

## 6. Plugin integration (1.7.0-b companion)

Per the consolidation decision, the gate3 plugin host folds **into** gate2 (the core, running,
admin-capable server) so a single `npm start` in `gate2-group-server/` serves chat + plugins +
UI. The gate2 server already has the seams: a `deps.onMessage` hook ("Gate 3 intercepts '/'
commands here") and `staticFiles`. Integration copies the self-contained host modules
(`plugin-contract.ts`, `sandbox.ts`, `plugin-runner.js`, `registry.ts`, `host.ts`) plus the
`search` plugin into gate2, and rewrites gate2's `index.ts` to load plugins, build capability
brokers (`net`, `room`; `exec` omitted — no sandboxed runner on this host), and dispatch `/`
commands through the host — alongside the planning command handling.

## 7. Test plan

- `planning.test.ts` — controller state machine with scripted inputs: round-robin order,
  per-round vote reset, consensus detection, 5-round cap, approve→tasking, `/revise` loop,
  `@handle:` assignment capture, `[[DONE]]` tasking termination.
- Orchestrator integration via `runTurn` with a **mock `ModelClient`** that returns scripted
  proposals (some carrying `[[CONVERGED]]`) and an in-memory `onReply` collector — asserting the
  full PLANNING→AWAITING_APPROVAL→TASKING→IDLE sequence and the moderator notices.
- Existing `acceptance.test.ts` (mention-reply) must stay green — regression guard that the
  additive changes did not disturb the default path.

## 8. Deferred / follow-ups

- **Real-time typing**: needs (a) streaming from the model endpoint, (b) a partial-token WS
  envelope (`{type:"delta", …}`), (c) UI rendering. Separate workstream.
- **Persistence**: planning state is in-memory (resets on restart). Move `PlanState` into
  SQLite if a plan must survive a server bounce.
- **Assignment execution**: capturing `@handle: <task>` is a ledger only; wiring an assignment
  to an actual agent work-loop (or to LSE/Hermes tool execution) is 1.7.0-d territory.
