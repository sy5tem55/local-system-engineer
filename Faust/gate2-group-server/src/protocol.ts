// src/protocol.ts — FROZEN Gate 2 wire contract.
// This is THE API the Gate 4 iOS app (and the Gate 2/3 web client) consume verbatim:
// entities, REST DTOs, the WebSocket envelope unions, and the orchestration interfaces.
// Reuses the canonical Message/Author from schema.ts. Do not change shapes without a
// version bump — Gates 3 and 4 are bound to it.
import type { Message, Author, AuthorKind } from "./schema.js";
export type { Message, Author, AuthorKind };

export const PROTOCOL_VERSION = "g2.1" as const;

// ── Entities ──────────────────────────────────────────────────────────────────

export interface Account {
  id: string; // "u:joe" (human) or "m:critic-glm" (model) — matches Author.id
  handle: string; // unique login/display handle, e.g. "joe"
  kind: AuthorKind; // human | model
  isAdmin?: boolean; // true if this account has admin privileges
  createdAt: number; // epoch ms
}

/** A model-bound account: an LLM endpoint dressed as a first-class room participant. */
export interface AgentAccount extends Account {
  kind: "model";
  endpoint: string; // llama-server base, e.g. http://node3090.home.arpa:8642
  model?: string; // optional model id passed through
  persona?: string; // optional system prompt / role (e.g. "cross-family critic")
  maxTokens?: number; // max tokens for model responses (default 2048)
}

export interface Room {
  id: string;
  name: string;
  createdAt: number;
}

export interface Membership {
  roomId: string;
  accountId: string;
  joinedAt: number;
}

// ── REST (auth = Bearer token in Authorization header unless noted) ────────────
// POST /auth/register   {handle, password}            -> AuthResult            (no auth)
// POST /auth/login      {handle, password}            -> AuthResult            (no auth)
// GET  /rooms                                          -> Room[]
// POST /rooms           {name}                         -> Room
// POST /rooms/:id/join                                 -> Membership
// POST /rooms/:id/agents {handle, endpoint, model?, persona?, maxTokens?} -> AgentAccount  (adds a model account to the room)
// GET  /rooms/:id/messages?before?&limit?              -> Message[]            (must be a member -> else 403)
// POST /rooms/:id/messages {content}                   -> Message             (optional REST send; primary path is WS)
// Errors: 401 (no/invalid token), 403 (not a member), 404, 400.

export interface AuthResult {
  accountId: string;
  handle: string;
  token: string;
  isAdmin: boolean;
}
export interface CreateRoomReq { name: string; }
export interface AddAgentReq {
  handle: string;
  endpoint: string;
  model?: string;
  persona?: string;
  maxTokens?: number;
}
export interface SendReq { content: string; }
export interface ApiError { error: string; code: number; }

// ── WebSocket envelopes (connect: ws://host/ws?token=…) ───────────────────────

export type ClientFrame =
  | { type: "subscribe"; roomId: string } // start receiving room events
  | { type: "send"; roomId: string; content: string } // post a message
  | { type: "ping" };

export type ServerFrame =
  | { type: "message"; message: Message } // a new message in a subscribed room
  | { type: "ack"; ref: string } // server accepted a client send (ref = client-supplied or message id)
  | { type: "presence"; roomId: string; accountId: string; online: boolean }
  | { type: "error"; error: string; code: number }
  | { type: "pong" };

// ── Orchestration (locked: mention-+-reply behind a swappable SpeakerPolicy) ──

export interface SpeakerContext {
  room: Room;
  message: Message; // the message that just landed
  agents: AgentAccount[]; // model accounts present in the room
  turnBudgetRemaining: number; // fan-out budget left for THIS origin turn (0 => must stop)
}

/**
 * Decides which model agents (if any) should respond to `message`.
 * The DEFAULT and only Gate-2 policy is mention-+-reply (see MentionReplyPolicy):
 * an agent is selected only if it is @mentioned or directly replied-to, it never
 * selects the message's own author, and selection is empty once the budget is 0.
 * Autonomous-cadence / director policies are later implementations of this SAME
 * interface — not rewrites.
 */
export interface SpeakerPolicy {
  readonly name: string;
  selectResponders(ctx: SpeakerContext): AgentAccount[];
}

export interface ModelClient {
  complete(req: {
    endpoint: string;
    model?: string;
    messages: Message[];
    signal?: AbortSignal;
    maxTokens?: number;
  }): Promise<string>;
}

// Default per-human-message fan-out budget (termination guarantee). A human message
// opens a turn with this many agent responses; model messages never open a new turn,
// so any model<->model chain draws down the SAME budget and is guaranteed to halt.
export const DEFAULT_TURN_BUDGET = 6;
