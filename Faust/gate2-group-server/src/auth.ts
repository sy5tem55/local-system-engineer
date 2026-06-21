// src/auth.ts — Account auth + bearer tokens (salted hashing + persistent tokens)
import * as crypto from "node:crypto";
import type { Store } from "./db.js";
import type { AuthResult } from "./protocol.js";

/** Generate a Faust API key: fa_<base64url 32 bytes>. */
export function generateApiKey(): string {
  return "fa_" + crypto.randomBytes(32).toString("base64url");
}
/** SHA-256 hash of an API key (what we store; never the raw key). */
export function apiKeyHash(key: string): string {
  return crypto.createHash("sha256").update(key).digest("hex");
}

function generateSalt(): string {
  return crypto.randomBytes(16).toString("hex");
}

function hashPassword(password: string, salt: string): string {
  return crypto.createHash("sha256").update(salt + password).digest("hex");
}

function generateToken(): string {
  return crypto.randomBytes(32).toString("hex");
}

export interface Auth {
  register(handle: string, password: string): AuthResult;
  login(handle: string, password: string): AuthResult;
  verifyToken(token: string): string | undefined;
  /** Resolve a Bearer credential: session token OR fa_ API key -> accountId. */
  verifyBearer(token: string): string | undefined;
}

export function makeAuth(store: Store, _secret: string): Auth {
  return {
    register(handle, password) {
      handle = handle.trim().toLowerCase();
      const existing = store.getAccountByHandle(handle);
      if (existing) {
        throw new Error(`Account with handle "${handle}" already exists`);
      }
      const salt = generateSalt();
      const passwordHash = hashPassword(password, salt);
      const account = store.createAccount({
        id: `u:${handle}`,
        handle,
        kind: "human",
        passwordHash,
        salt,
      });
      const token = generateToken();
      store.saveToken(token, account.id);
      return { accountId: account.id, handle: account.handle, token, isAdmin: !!account.isAdmin };
    },

    login(handle, password) {
      handle = handle.trim().toLowerCase();
      const account = store.getAccountByHandle(handle);
      if (!account) {
        throw new Error(`Account "${handle}" not found`);
      }
      const salt = account.salt || "";
      const passwordHash = hashPassword(password, salt);
      if (account.passwordHash !== passwordHash) {
        throw new Error("Invalid password");
      }
      const token = generateToken();
      store.saveToken(token, account.id);
      return { accountId: account.id, handle: account.handle, token, isAdmin: !!account.isAdmin };
    },

    verifyToken(token) {
      return store.getToken(token);
    },

    verifyBearer(token) {
      const byToken = store.getToken(token);
      if (byToken) return byToken;
      if (token.startsWith("fa_")) return store.resolveApiKey(apiKeyHash(token));
      return undefined;
    },
  };
}
