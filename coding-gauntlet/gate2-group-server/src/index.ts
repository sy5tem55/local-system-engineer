// src/index.ts — AGENT IMPLEMENTS the entry. `npm start`:
//   - openStore(process.env.DB_PATH ?? "data/gate2.sqlite")
//   - a live ModelClient that wraps Gate 1's SSE transport (stream -> string),
//     pointed at each agent account's endpoint
//   - createServer({ store, model }).listen(Number(process.env.PORT ?? 8787))
//   - Ctrl-C -> server.close() + store.close()
throw new Error("NOT IMPLEMENTED: Gate 2 entry (server bootstrap). See SPEC.md.");
