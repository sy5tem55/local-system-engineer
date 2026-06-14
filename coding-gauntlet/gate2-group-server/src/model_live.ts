// src/model_live.ts — AGENT IMPLEMENTS. A live ModelClient that wraps Gate 1's SSE
// transport: open streamChat() against req.endpoint, concatenate the streamed deltas
// into the final string, and honour req.signal (give-up budget). Used by index.ts
// for real model agents and by the [agent][live] acceptance check.
import type { ModelClient } from "./protocol.js";

export function makeLiveModelClient(): ModelClient {
  throw new Error("NOT IMPLEMENTED: makeLiveModelClient — wrap Gate 1 SSE transport");
}
