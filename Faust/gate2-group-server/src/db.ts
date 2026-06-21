// src/db.ts — SQLite-backed store using sql.js (pure JS, no native deps)
import * as fs from "node:fs";
import * as path from "node:path";
import initSqlJs, { Database } from "sql.js";
import type { Account, AgentAccount, Room, Membership } from "./protocol.js";
import type { Message } from "./schema.js";
import { serializeMessage, deserializeMessage } from "./schema.js";

// Top-level await: initialize sql.js before any export is used
const SQLModule = await initSqlJs();

function uid(prefix: string): string {
  return `${prefix}:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export interface Store {
  createAccount(a: Omit<Account, "createdAt"> & { passwordHash?: string; salt?: string; isAdmin?: boolean }): Account;
  getAccountByHandle(handle: string): (Account & { passwordHash?: string; salt?: string; isAdmin?: boolean }) | undefined;
  getAccount(id: string): (Account & { isAdmin?: boolean }) | undefined;
  upsertAgent(a: Omit<AgentAccount, "createdAt">): AgentAccount;
  createRoom(name: string): Room;
  listRooms(): Room[];
  getRoom(id: string): Room | undefined;
  deleteRoom(roomId: string): boolean;
  clearMessages(roomId: string): void;
  addMember(roomId: string, accountId: string): Membership;
  isMember(roomId: string, accountId: string): boolean;
  isAdmin(accountId: string): boolean;
  setAdmin(accountId: string, value: boolean): void;
  listAgentsInRoom(roomId: string): AgentAccount[];
  deleteMessage(messageId: string): boolean;
  removeMember(roomId: string, accountId: string): boolean;
  listMembers(roomId: string): Array<{accountId: string, joinedAt: number}>;
  appendMessage(m: Message): void;
  listMessages(roomId: string, opts?: { before?: number; limit?: number }): Message[];
  // Token persistence (Phase 6b)
  saveToken(token: string, accountId: string): void;
  getToken(token: string): string | undefined;
  // API keys (1.7.0-b — identity auth for bots; scope stored, not yet enforced)
  createApiKey(rec: { id: string; userId: string; keyHash: string; label?: string; scope?: string; expiresAt?: number }): void;
  listApiKeys(userId: string): Array<{ id: string; label: string | null; scope: string | null; createdAt: number; expiresAt: number | null; revokedAt: number | null }>;
  revokeApiKey(id: string, userId: string): boolean;
  resolveApiKey(keyHash: string): string | undefined;
  close(): void;
}

export function openStore(dbPath: string): Store {
  let db: Database;
  if (dbPath === ":memory:") {
    db = new SQLModule.Database();
  } else {
    const dir = path.dirname(dbPath);
    if (dir && dir !== "." && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const existing = fs.existsSync(dbPath) ? fs.readFileSync(dbPath) : undefined;
    db = new SQLModule.Database(existing);
  }

  // Create tables
  db.run(`CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    handle TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL DEFAULT 'human',
    passwordHash TEXT,
    salt TEXT,
    isAdmin INTEGER NOT NULL DEFAULT 0,
    createdAt INTEGER NOT NULL,
    endpoint TEXT,
    model TEXT,
    persona TEXT
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    createdAt INTEGER NOT NULL
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS memberships (
    roomId TEXT NOT NULL,
    accountId TEXT NOT NULL,
    joinedAt INTEGER NOT NULL,
    PRIMARY KEY (roomId, accountId)
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    room_id TEXT,
    serialized TEXT NOT NULL
  )`);

  // Token persistence table (Phase 6b)
  db.run(`CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    accountId TEXT NOT NULL,
    createdAt INTEGER NOT NULL
  )`);

  // API keys (1.7.0-b)
  db.run(`CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    label TEXT,
    scope TEXT,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    revoked_at INTEGER
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)`);

  // Migrations for existing databases (no-op on fresh tables)
  try { db.run(`ALTER TABLE messages ADD COLUMN room_id TEXT`); } catch { /* column already exists */ }
  try { db.run(`ALTER TABLE accounts ADD COLUMN salt TEXT`); } catch { /* column already exists */ }
  try { db.run(`ALTER TABLE accounts ADD COLUMN isAdmin INTEGER NOT NULL DEFAULT 0`); } catch { /* column already exists */ }
  // Removal of ownerId from rooms is idempotent — column simply stops being queried.
  // Existing rows with ownerId are harmless; new code never reads it.

  function save() {
    if (dbPath !== ":memory:") {
      const data = db.export();
      const buffer = Buffer.from(data);
      fs.writeFileSync(dbPath, buffer);
    }
  }

  return {
    createAccount(a) {
      const now = Date.now();
      const id = a.id || uid(a.kind === "model" ? "m" : "u");
      db.run(`INSERT OR REPLACE INTO accounts (id, handle, kind, passwordHash, salt, isAdmin, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)`, [id, a.handle, a.kind, a.passwordHash || null, a.salt || null, a.isAdmin ? 1 : 0, now]);
      save();
      return { id, handle: a.handle, kind: a.kind, createdAt: now };
    },

    getAccountByHandle(handle) {
      const rows = db.exec(`SELECT id, handle, kind, passwordHash, salt, isAdmin, createdAt, endpoint, model, persona FROM accounts WHERE handle = ?`, [handle]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      const v = rows[0].values[0];
      return {
        id: v[0] as string,
        handle: v[1] as string,
        kind: v[2] as import("./schema.js").AuthorKind,
        passwordHash: v[3] as string | undefined,
        salt: v[4] as string | undefined,
        isAdmin: !!(v[5] as number),
        createdAt: v[6] as number,
        endpoint: (v[7] as string) || undefined,
        model: (v[8] as string) || undefined,
        persona: (v[9] as string) || undefined,
      };
    },

    getAccount(id) {
      const rows = db.exec(`SELECT id, handle, kind, isAdmin, createdAt, endpoint, model, persona FROM accounts WHERE id = ?`, [id]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      const v = rows[0].values[0];
      return { id: v[0] as string, handle: v[1] as string, kind: v[2] as import("./schema.js").AuthorKind, isAdmin: !!(v[3] as number), createdAt: v[4] as number };
    },

    upsertAgent(a) {
      const now = Date.now();
      const id = a.id || uid("m");
      db.run(`INSERT OR REPLACE INTO accounts (id, handle, kind, createdAt, endpoint, model, persona)
        VALUES (?, ?, 'model', ?, ?, ?, ?)`, [id, a.handle, now, a.endpoint, a.model || null, a.persona || null]);
      save();
      return { id, handle: a.handle, kind: "model" as const, createdAt: now, endpoint: a.endpoint, model: a.model, persona: a.persona };
    },

    createRoom(name) {
      const now = Date.now();
      const id = uid("r");
      db.run(`INSERT INTO rooms (id, name, createdAt) VALUES (?, ?, ?)`, [id, name, now]);
      save();
      return { id, name, createdAt: now };
    },

    listRooms() {
      const rows = db.exec(`SELECT id, name, createdAt FROM rooms ORDER BY createdAt`);
      if (!rows || rows.length === 0 || !rows[0].values) return [];
      return rows[0].values.map((v: any[]) => ({ id: v[0], name: v[1], createdAt: v[2] }));
    },

    getRoom(id) {
      const rows = db.exec(`SELECT id, name, createdAt FROM rooms WHERE id = ?`, [id]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      const v = rows[0].values[0];
      return { id: v[0] as string, name: v[1] as string, createdAt: v[2] as number };
    },

    isAdmin(accountId) {
      const rows = db.exec(`SELECT isAdmin FROM accounts WHERE id = ?`, [accountId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      return (rows[0].values[0][0] as number) === 1;
    },

    setAdmin(accountId, value) {
      db.run(`UPDATE accounts SET isAdmin = ? WHERE id = ?`, [value ? 1 : 0, accountId]);
      save();
    },

    deleteRoom(roomId) {
      // Check if room exists
      const rows = db.exec(`SELECT id FROM rooms WHERE id = ?`, [roomId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      // Delete in order: messages → memberships → room (foreign-key safety)
      db.run(`DELETE FROM messages WHERE room_id = ?`, [roomId]);
      db.run(`DELETE FROM memberships WHERE roomId = ?`, [roomId]);
      db.run(`DELETE FROM rooms WHERE id = ?`, [roomId]);
      save();
      return true;
    },

    clearMessages(roomId) {
      db.run(`DELETE FROM messages WHERE room_id = ?`, [roomId]);
      save();
    },

    addMember(roomId, accountId) {
      const now = Date.now();
      db.run(`INSERT OR IGNORE INTO memberships (roomId, accountId, joinedAt) VALUES (?, ?, ?)`, [roomId, accountId, now]);
      save();
      return { roomId, accountId, joinedAt: now };
    },

    isMember(roomId, accountId) {
      const rows = db.exec(`SELECT COUNT(*) FROM memberships WHERE roomId = ? AND accountId = ?`, [roomId, accountId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      return (rows[0].values[0][0] as number) > 0;
    },

    listAgentsInRoom(roomId) {
      const rows = db.exec(`SELECT a.id, a.handle, a.kind, a.createdAt, a.endpoint, a.model, a.persona
        FROM accounts a
        JOIN memberships m ON a.id = m.accountId
        WHERE m.roomId = ? AND a.kind = 'model'`, [roomId]);
      if (!rows || rows.length === 0 || !rows[0].values) return [];
      return rows[0].values.map((v: any[]) => ({
        id: v[0], handle: v[1], kind: "model" as const, createdAt: v[3],
        endpoint: v[4], model: v[5], persona: v[6],
      }));
    },

    deleteMessage(messageId) {
      const rows = db.exec(`SELECT id FROM messages WHERE id = ?`, [messageId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      db.run(`DELETE FROM messages WHERE id = ?`, [messageId]);
      save();
      return true;
    },

    removeMember(roomId, accountId) {
      const rows = db.exec(`SELECT roomId FROM memberships WHERE roomId = ? AND accountId = ?`, [roomId, accountId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      db.run(`DELETE FROM memberships WHERE roomId = ? AND accountId = ?`, [roomId, accountId]);
      save();
      return true;
    },

    listMembers(roomId) {
      const rows = db.exec(`SELECT accountId, joinedAt FROM memberships WHERE roomId = ? ORDER BY joinedAt`, [roomId]);
      if (!rows || rows.length === 0 || !rows[0].values) return [];
      return rows[0].values.map((v: any[]) => ({ accountId: v[0] as string, joinedAt: v[1] as number }));
    },

    appendMessage(m) {
      const serialized = serializeMessage(m);
      db.run(`INSERT OR REPLACE INTO messages (id, room_id, serialized) VALUES (?, ?, ?)`, [m.id, m.room, serialized]);
      save();
    },

    listMessages(roomId, opts) {
      const rows = db.exec(`SELECT serialized FROM messages WHERE room_id = ? ORDER BY rowid`, [roomId]);
      if (!rows || rows.length === 0 || !rows[0].values) return [];

      let msgs: Message[] = rows[0].values.map((v: any[]) =>
        deserializeMessage(v[0] as string),
      );

      if (opts?.before !== undefined) {
        msgs = msgs.filter(m => m.ts < opts.before!);
      }
      if (opts?.limit !== undefined) {
        msgs = msgs.slice(-opts.limit);
      }
      return msgs;
    },

    // Token persistence (Phase 6b)
    saveToken(token, accountId) {
      const now = Date.now();
      db.run(`INSERT OR REPLACE INTO tokens (token, accountId, createdAt) VALUES (?, ?, ?)`, [token, accountId, now]);
      save();
    },

    getToken(token) {
      const rows = db.exec(`SELECT accountId FROM tokens WHERE token = ?`, [token]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      return rows[0].values[0][0] as string;
    },

    createApiKey(rec) {
      db.run(`INSERT INTO api_keys (id, user_id, key_hash, label, scope, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)`,
        [rec.id, rec.userId, rec.keyHash, rec.label ?? null, rec.scope ?? null, Date.now(), rec.expiresAt ?? null]);
      save();
    },

    listApiKeys(userId) {
      const rows = db.exec(`SELECT id, label, scope, created_at, expires_at, revoked_at FROM api_keys WHERE user_id = ? ORDER BY created_at`, [userId]);
      if (!rows || rows.length === 0 || !rows[0].values) return [];
      return rows[0].values.map((v) => ({
        id: v[0] as string, label: v[1] as string | null, scope: v[2] as string | null,
        createdAt: v[3] as number, expiresAt: v[4] as number | null, revokedAt: v[5] as number | null,
      }));
    },

    revokeApiKey(id, userId) {
      const rows = db.exec(`SELECT id FROM api_keys WHERE id = ? AND user_id = ? AND revoked_at IS NULL`, [id, userId]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return false;
      db.run(`UPDATE api_keys SET revoked_at = ? WHERE id = ?`, [Date.now(), id]);
      save();
      return true;
    },

    resolveApiKey(keyHash) {
      const rows = db.exec(`SELECT user_id FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?)`, [keyHash, Date.now()]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      return rows[0].values[0][0] as string;
    },

    close() {
      save();
      db.close();
    },
  };
}