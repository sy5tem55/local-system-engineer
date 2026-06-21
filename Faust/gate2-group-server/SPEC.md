# Gate 2 — The Group Server (challenge spec)

> Coding Gauntlet, gate 2 of 4. Builds directly on Gate 1: same TypeScript, same frozen
> message schema, same opencode tokens. The LSE agent implements the stubbed modules until
> `npm test` is all-green. A gate is "passed" only on demonstrated behavior.

## Goal

Many participants — humans **and** local-model agents — in shared, **persistent**, **realtime**
rooms. A backend service (REST + WebSocket + SQLite) plus a thin token-skinned web client, with
multi-agent orchestration as a clean, swappable interface.

**This gate's REST+WS contract (`src/protocol.ts`) is frozen** — it is the exact API the Gate 4
iOS app consumes, and the Gate 3 plugin host extends.

## Stack (locked)

TypeScript — **Bun or Node** + **`ws`** server, **SQLite** to start, a minimal React/Svelte (or
vanilla) web client skinned with Gate 1's tokens. Reuses Gate 1's `schema.ts` verbatim (vendored;
keep in sync). Model agents fan out to llama-server (`:8080` LUCIFER) / node3090 (`:8642`).

## What's authored vs. what you build

**Authored & FROZEN:**
- `src/schema.ts` — the Gate 1 canonical `Message`/`Author` (vendored, unchanged).
- `src/protocol.ts` — entities (`Account`, `AgentAccount`, `Room`, `Membership`), REST DTOs, the
  WebSocket `ClientFrame`/`ServerFrame` unions, and the orchestration interfaces (`SpeakerPolicy`,
  `ModelClient`), plus `DEFAULT_TURN_BUDGET` and `PROTOCOL_VERSION`. **This is the iOS app's API.**
- `src/tokens.ts` — the opencode token loader (for the web client).
- `test/acceptance.test.ts` — the grader. Don't edit it to pass.

**You implement (stubs throw `NOT IMPLEMENTED`):**

| Module | Export | Contract |
|---|---|---|
| `src/db.ts` | `openStore(path): Store` | SQLite-backed accounts/rooms/memberships/messages. **Survives restart**: a fresh `Store` over the same file returns the same data. Messages stored via the canonical (de)serializers. `":memory:"` allowed for tests. |
| `src/auth.ts` | `makeAuth(store, secret): Auth` | `register`/`login` (hash the password, no plaintext at rest), `verifyToken(token) -> accountId`. Gates REST + WS. |
| `src/orchestrator.ts` | `MentionReplyPolicy`, `parseMentions`, `runTurn` | The locked policy + the turn engine that guarantees termination (below). |
| `src/agents.ts` | `generateAgentReply(agent, roomId, history, model, signal)` | Build the messages array (persona as a system msg + mapped history), call `model.complete`, wrap the text as a canonical assistant `Message` authored by the agent. |
| `src/model_live.ts` | `makeLiveModelClient(): ModelClient` | Live `ModelClient` wrapping Gate 1's SSE transport (stream → string), honouring the abort signal. |
| `src/server.ts` | `createServer(deps): RunningServer` | HTTP (REST) + WS (`ws`), dependency-injected (`store`, `model`, optional `policy`/`secret`/`turnBudget`). `listen(0)` → ephemeral port; `fetch(req)` for in-process REST. |
| `src/index.ts` | entry | `npm start`: real SQLite store + `makeLiveModelClient()` + `createServer().listen(PORT)`; Ctrl-C → clean close. |
| `web/index.html` | — | Minimal WS client skinned with the opencode tokens (the Gate 3 component seed; mirrored by iOS). Manual/visual, not graded by the harness. |

## REST API (Bearer token unless noted)

```
POST /auth/register   {handle,password}                     -> AuthResult        (no auth)
POST /auth/login      {handle,password}                     -> AuthResult        (no auth)
GET  /rooms                                                  -> Room[]
POST /rooms           {name}                                 -> Room
POST /rooms/:id/join                                         -> Membership
POST /rooms/:id/agents {handle,endpoint,model?,persona?}     -> AgentAccount
GET  /rooms/:id/messages?before?&limit?                      -> Message[]         (member only)
POST /rooms/:id/messages {content}                           -> Message           (optional; WS is primary)
```
Errors: **401** no/invalid token · **403** not a member · 404 · 400.

## WebSocket (`ws://host/ws?token=…`)

Client→server: `{type:"subscribe",roomId}` · `{type:"send",roomId,content}` · `{type:"ping"}`.
Server→client: `{type:"message",message}` · `{type:"ack",ref}` · `{type:"presence",…}` ·
`{type:"error",error,code}` · `{type:"pong"}`. **Delivery target < 1s.**

## Orchestration (LOCKED: mention-+-reply behind a swappable `SpeakerPolicy`)

`MentionReplyPolicy.selectResponders(ctx)` returns the agents **@mentioned** in the message
(matched on handle), **minus the message's own author** (no self-trigger), and only while
`turnBudgetRemaining > 0`.

**Termination guarantee (the hard part).** A **human** message opens a turn with
`DEFAULT_TURN_BUDGET` (6). `runTurn` persists+fans-out each produced agent reply, decrements the
budget, and feeds that reply back through the policy (agent replies may @mention other agents) —
all drawing down the **same** budget. **Model messages never open a new turn.** When the budget
hits 0 or no responder remains, the turn ends. This makes any model↔model chain provably finite.
(Autonomous-cadence / director policies are later implementations of the same interface.)

## Give-up budget

`ModelClient.complete` takes an `AbortSignal`; agent generation must respect a per-reply
max-tokens/max-time, and `runTurn` is bounded by the turn budget. Loops stop; they don't smoke compute.

## Acceptance (each is a runnable check in `npm test`)

| PYRAMID criterion | Check | Starts |
|---|---|---|
| message schema is canonical | `[authored] …schema round-trips` | green |
| frozen wire contract present | `[authored] …protocol exposes version + budget` | green |
| runs with one command | `[authored] runs with one command` | green |
| auth gates room access | `[agent] auth gates room access (401/403/200)` | **red** |
| @mention a model → it replies; delivery < 1s | `[agent] @mention a model agent…` | **red** |
| model↔model exchange terminates (no runaway) | `[agent] model<->model …terminates within the turn budget` | **red** |
| history survives a restart | `[agent] history survives a restart` | **red** |
| **messages fan out to ALL subscribers** (2 humans + agent reply; exercises `/join`) | `[agent] room messages fan out to ALL subscribers…` | **red** |
| 2 humans + 2 model agents, live | `[agent][live] …real llama-server` | skip → **red/green** |

**Definition of done:** `npm test` all-green offline (authored + the **five** agent checks), and the
live check green with `GATE2_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test`.

> Fan-out (P31 hardening): a server that only echoes a reply to the *sender* would pass every
> single-client check but fail the room — "2 humans + 2 agents in one room" means a non-sender must
> receive both the human message and the agent's reply. The fan-out test opens two human WS clients,
> has the second **join** the room, and asserts the non-sender sees both.

> The acceptance harness injects a **fake `ModelClient`** (reply is a function of the agent handle,
> via `endpoint: "fake://<handle>"`) so mention-routing and termination are tested deterministically
> offline. The model↔model test wires two agents that always @mention each other — without the turn
> budget it would loop forever; the check asserts total agent messages ≤ budget.

## Run

```bash
npm install
npm test                       # authored green, agent red until built
npm start                      # the server (PORT, DB_PATH env)
GATE2_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test   # + live model agent
```

## Feeds the pinnacle

The frozen `protocol.ts` (accounts, rooms, WS frames, orchestration) **is** the backend Gate 4's
iOS app talks to, and the surface Gate 3's plugin framework hooks into. Every account, room, socket,
and orchestration rule here is reused verbatim upward.
