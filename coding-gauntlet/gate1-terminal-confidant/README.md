# Gate 1 — The Terminal Confidant

Coding Gauntlet, gate 1. A one-binary TypeScript + **Ink** TUI: one human ↔ one local model,
streamed from llama-server and rendered in the **opencode** aesthetic. Full challenge contract in
[`SPEC.md`](./SPEC.md).

```bash
npm install
npm test     # acceptance harness — authored checks green, agent checks red until built
npm start -- --url http://node4090.home.arpa:8080
```

**Layout**

```
src/schema.ts     FROZEN — canonical Message/Author + (de)serialize (shared by all gates)
src/tokens.ts     FROZEN — typed opencode-token loader + fg/bg/ΔE helpers
src/transport.ts  agent — SSE streamChat() from /v1/chat/completions
src/render.ts     agent — renderMessageToAnsi(): markdown + syntax-highlighted code
src/log.ts        agent — MessageLog: append-only canonical JSONL
src/app.tsx       agent — the Ink view
src/index.ts      agent — entry; `npm start`
test/acceptance.test.ts   the grader (don't edit to pass)
```

Status is whatever `npm test` reports — a gate passes only on demonstrated behavior. Tokens consumed
from `../design-tokens/opencode-tokens.json` (shared across all four gates).
