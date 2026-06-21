# Faust v0.1.0 — Realtime Group Chat

Local chat application with model agents, rooms, and plugin support.

## Structure

```
gate2-group-server/   — Core server (auth, DB, model agents, orchestrator, web UI)
gate3-plugin-forge/   — Plugin framework (capability-sandboxed, extends Gate 2)
archive/              — Stale code from project consolidation
```

## Start

```bash
cd gate2-group-server
MODEL_API_KEY=<hermes-api-key> npx tsx src/index.ts
```

Server listens on **http://localhost:8787**

## Accounts

| Handle | Kind |
|--------|------|
| `sy5`  | human |
| `lse`  | human |
| `hermes` | model |

## Stack

TypeScript · Node.js · SQLite · WebSocket · REST
