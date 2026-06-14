// src/auth.ts — AGENT IMPLEMENTS. Account auth + bearer tokens.
// register/login hash the password (no plaintext at rest), issue an opaque token;
// verifyToken resolves a token to an accountId. Token scheme is yours (signed JWT
// or random + table) as long as verifyToken is O(1)-ish and survives restart if
// you chose a table. The server uses these to gate REST + WS access.
import type { Store } from "./db.js";
import type { AuthResult } from "./protocol.js";

export interface Auth {
  register(handle: string, password: string): AuthResult;
  login(handle: string, password: string): AuthResult;
  verifyToken(token: string): string | undefined; // -> accountId
}

export function makeAuth(_store: Store, _secret: string): Auth {
  throw new Error("NOT IMPLEMENTED: makeAuth — Gate 2 auth (register/login/verifyToken)");
}
