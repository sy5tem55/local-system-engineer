# Gate 2 — The Group Server

Coding Gauntlet, gate 2. A TypeScript backend (REST + WebSocket + SQLite) where humans and
local-model agents share persistent realtime rooms, with mention-+-reply orchestration. Full
challenge contract in [`SPEC.md`](./SPEC.md).

```bash
npm install
npm test     # acceptance harness — authored checks green, agent checks red until built
npm start    # PORT, DB_PATH env
```

**Layout**

```
src/schema.ts      FROZEN — Gate 1 canonical Message/Author (vendored)
src/protocol.ts    FROZEN — entities + REST DTOs + WS frames + SpeakerPolicy/ModelClient
                            (this is the iOS app's API)
src/tokens.ts      FROZEN — opencode token loader (web client)
src/db.ts          agent — SQLite Store (survives restart)
src/auth.ts        agent — register/login/verifyToken
src/orchestrator.ts agent — MentionReplyPolicy + parseMentions + runTurn (termination guarantee)
src/agents.ts      agent — generateAgentReply (model account -> reply Message)
src/model_live.ts  agent — live ModelClient (wraps Gate 1 SSE transport)
src/server.ts      agent — HTTP + WS group server (DI: store, model, policy)
src/index.ts       agent — entry; `npm start`
web/index.html     agent — token-skinned WS web client (manual)
test/acceptance.test.ts   the grader (don't edit to pass)
```

The harness injects a fake `ModelClient` so mention-routing and the model↔model termination
guarantee are tested deterministically offline; `GATE2_LIVE=1` runs a real llama-server agent.
Tokens consumed from `../design-tokens/opencode-tokens.json` (shared across all four gates).