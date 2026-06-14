// src/server.ts — AGENT IMPLEMENTS. The Group Server: HTTP (REST) + WebSocket (ws),
// wired to an injected Store + ModelClient + SpeakerPolicy. Dependency-injected so
// the acceptance harness can run it in-process with a fake model and a temp SQLite db.
//
// REST routes + WS frames per protocol.ts. On a human `send`: persist the message,
// fan it out to subscribers, then drive runTurn() so @mentioned agents reply. Auth
// gates every room read/write (401 no token, 403 not a member). Delivery target <1s.
import type { Store } from "./db.js";
import type { ModelClient, SpeakerPolicy } from "./protocol.js";

export interface ServerDeps {
  store: Store;
  model: ModelClient;
  policy?: SpeakerPolicy; // default: MentionReplyPolicy
  secret?: string; // auth signing secret
  turnBudget?: number;
}

export interface RunningServer {
  /** Begin listening; resolves with the bound port (use 0 for an ephemeral port). */
  listen(port?: number): Promise<number>;
  /** In-process request handling (handy for REST tests without a socket). */
  fetch(req: Request): Promise<Response>;
  url(): string; // e.g. http://127.0.0.1:54321
  wsUrl(token: string): string; // ws://127.0.0.1:54321/ws?token=…
  close(): Promise<void>;
}

export function createServer(_deps: ServerDeps): RunningServer {
  throw new Error("NOT IMPLEMENTED: createServer — Gate 2 HTTP+WS group server (see SPEC)");
}
