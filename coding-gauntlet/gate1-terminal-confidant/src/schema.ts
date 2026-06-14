// src/schema.ts — FROZEN canonical message schema for the Coding Gauntlet.
// Authored as part of the Gate 1 spec; imported UNCHANGED by every later gate
// (G2 server, G3 plugins, G4 iOS bridge). Do NOT change the shape without a
// version bump — Gates 2-4 are contractually bound to it.

export type AuthorKind = "human" | "model";

export interface Author {
  id: string; // stable id, e.g. "u:joe" or "m:qwen3.6-27b"
  kind: AuthorKind; // human | model — the heterogeneity axis starts here
  name?: string; // display name (optional)
}

export type Role = "user" | "assistant" | "system";

export interface Message {
  id: string; // unique message id (uuid/ulid)
  room: string; // room/conversation id (Gate 1: a single local room)
  author: Author; // who sent it
  role: Role; // chat role for transport (OpenAI-compatible)
  content: string; // the text (markdown allowed)
  ts: number; // epoch milliseconds
}

const KINDS: AuthorKind[] = ["human", "model"];
const ROLES: Role[] = ["user", "assistant", "system"];

export function isAuthor(x: any): x is Author {
  return (
    !!x &&
    typeof x.id === "string" &&
    x.id !== "" &&
    KINDS.includes(x.kind) &&
    (x.name === undefined || typeof x.name === "string")
  );
}

/** Validate + normalize an unknown object into a Message. Throws on any violation. */
export function validateMessage(x: any): Message {
  if (!x || typeof x !== "object") throw new TypeError("message: not an object");
  for (const f of ["id", "room", "content"] as const) {
    if (typeof x[f] !== "string" || x[f] === "")
      throw new TypeError(`message.${f}: non-empty string required`);
  }
  if (!ROLES.includes(x.role))
    throw new TypeError(`message.role: one of ${ROLES.join("|")}`);
  if (typeof x.ts !== "number" || !Number.isFinite(x.ts))
    throw new TypeError("message.ts: finite epoch-ms number required");
  if (!isAuthor(x.author))
    throw new TypeError("message.author: { id, kind:human|model, name? }");
  return {
    id: x.id,
    room: x.room,
    author: {
      id: x.author.id,
      kind: x.author.kind,
      ...(x.author.name !== undefined ? { name: x.author.name } : {}),
    },
    role: x.role,
    content: x.content,
    ts: x.ts,
  };
}

// Canonical on-disk form is JSONL: exactly one validated Message per line.
export function serializeMessage(m: Message): string {
  return JSON.stringify(validateMessage(m));
}
export function deserializeMessage(line: string): Message {
  return validateMessage(JSON.parse(line));
}
