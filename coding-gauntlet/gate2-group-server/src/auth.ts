// src/auth.ts — Account auth + bearer tokens
import * as crypto from "node:crypto";
import type { Store } from "./db.js";
import type { AuthResult } from "./protocol.js";

// Simple in-memory token store (survives restart if backed by DB, but for tests in-memory is fine)
const tokenMap = new Map<string, string>(); // token -> accountId

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

function generateToken(): string {
  return crypto.randomBytes(32).toString("hex");
}

export interface Auth {
  register(handle: string, password: string): AuthResult;
  login(handle: string, password: string): AuthResult;
  verifyToken(token: string): string | undefined;
}

export function makeAuth(store: Store, _secret: string): Auth {
  return {
    register(handle, password) {
      const existing = store.getAccountByHandle(handle);
      if (existing) {
        throw new Error(`Account with handle "${handle}" already exists`);
      }
      const passwordHash = hashPassword(password);
      const account = store.createAccount({
        id: `u:${handle}`,
        handle,
        kind: "human",
        passwordHash,
      });
      const token = generateToken();
      tokenMap.set(token, account.id);
      return { accountId: account.id, handle: account.handle, token };
    },

    login(handle, password) {
      const account = store.getAccountByHandle(handle);
      if (!account) {
        throw new Error(`Account "${handle}" not found`);
      }
      const passwordHash = hashPassword(password);
      if (account.passwordHash !== passwordHash) {
        throw new Error("Invalid password");
      }
      const token = generateToken();
      tokenMap.set(token, account.id);
      return { accountId: account.id, handle: account.handle, token };
    },

    verifyToken(token) {
      return tokenMap.get(token);
    },
  };
}
