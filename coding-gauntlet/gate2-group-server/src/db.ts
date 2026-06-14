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
  createAccount(a: Omit<Account, "createdAt"> & { passwordHash?: string }): Account;
  getAccountByHandle(handle: string): (Account & { passwordHash?: string }) | undefined;
  getAccount(id: string): Account | undefined;
  upsertAgent(a: Omit<AgentAccount, "createdAt">): AgentAccount;
  createRoom(name: string): Room;
  listRooms(): Room[];
  getRoom(id: string): Room | undefined;
  addMember(roomId: string, accountId: string): Membership;
  isMember(roomId: string, accountId: string): boolean;
  listAgentsInRoom(roomId: string): AgentAccount[];
  appendMessage(m: Message): void;
  listMessages(roomId: string, opts?: { before?: number; limit?: number }): Message[];
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
    serialized TEXT NOT NULL
  )`);

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
      db.run(`INSERT OR REPLACE INTO accounts (id, handle, kind, passwordHash, createdAt)
        VALUES (?, ?, ?, ?, ?)`, [id, a.handle, a.kind, a.passwordHash || null, now]);
      save();
      return { id, handle: a.handle, kind: a.kind, createdAt: now };
    },

    getAccountByHandle(handle) {
      const rows = db.exec(`SELECT id, handle, kind, passwordHash, createdAt, endpoint, model, persona FROM accounts WHERE handle = ?`, [handle]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      const v = rows[0].values[0];
      return {
        id: v[0] as string,
        handle: v[1] as string,
        kind: v[2] as string,
        passwordHash: v[3] as string | undefined,
        createdAt: v[4] as number,
        endpoint: (v[5] as string) || undefined,
        model: (v[6] as string) || undefined,
        persona: (v[7] as string) || undefined,
      };
    },

    getAccount(id) {
      const rows = db.exec(`SELECT id, handle, kind, createdAt, endpoint, model, persona FROM accounts WHERE id = ?`, [id]);
      if (!rows || rows.length === 0 || !rows[0].values || rows[0].values.length === 0) return undefined;
      const v = rows[0].values[0];
      return { id: v[0], handle: v[1], kind: v[2], createdAt: v[3] };
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
      return { id: v[0], name: v[1], createdAt: v[2] };
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

    appendMessage(m) {
      const serialized = serializeMessage(m);
      db.run(`INSERT OR REPLACE INTO messages (id, serialized) VALUES (?, ?)`, [m.id, serialized]);
      save();
    },

    listMessages(roomId, opts) {
      let sql = `SELECT serialized FROM messages WHERE id IN (SELECT id FROM messages WHERE serialized LIKE '%"room":"' || ? || '"%')`;
      // Better approach: parse the serialized JSON to check room
      // Actually let's store room separately for efficient querying
      // For now, let's use a simpler approach: store room_id in messages table
      // Let me fix the schema...
      // Actually, let's just query all messages and filter in JS for now
      // No, let's fix the schema properly.
      
      // Re-approach: let's add a room column to messages
      // But we already created the table. Let's just query all and filter.
      const allRows = db.exec(`SELECT serialized FROM messages ORDER BY rowid`);
      if (!allRows || allRows.length === 0 || !allRows[0].values) return [];
      
      let msgs: Message[] = [];
      for (const row of allRows[0].values) {
        const m = deserializeMessage(row[0] as string);
        if (m.room === roomId) msgs.push(m);
      }
      
      if (opts?.before !== undefined) {
        msgs = msgs.filter(m => m.ts < opts.before!);
      }
      msgs.sort((a, b) => a.ts - b.ts);
      if (opts?.limit !== undefined) {
        msgs = msgs.slice(-opts.limit);
      }
      return msgs;
    },

    close() {
      save();
      db.close();
    },
  };
}
