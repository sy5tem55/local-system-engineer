// src/db.ts — AGENT IMPLEMENTS. Durable store (SQLite to start).
// Persistence contract: messages/rooms/accounts written here MUST survive process
// restart — a fresh Store over the same file path returns the same data. Use the
// canonical schema (serializeMessage/deserializeMessage) for the messages table.
import type { Account, AgentAccount, Room, Membership } from "./protocol.js";
import type { Message } from "./schema.js";

export interface Store {
  // accounts
  createAccount(a: Omit<Account, "createdAt"> & { passwordHash?: string }): Account;
  getAccountByHandle(handle: string): (Account & { passwordHash?: string }) | undefined;
  getAccount(id: string): Account | undefined;
  upsertAgent(a: Omit<AgentAccount, "createdAt">): AgentAccount;
  // rooms + membership
  createRoom(name: string): Room;
  listRooms(): Room[];
  getRoom(id: string): Room | undefined;
  addMember(roomId: string, accountId: string): Membership;
  isMember(roomId: string, accountId: string): boolean;
  listAgentsInRoom(roomId: string): AgentAccount[];
  // messages
  appendMessage(m: Message): void;
  listMessages(roomId: string, opts?: { before?: number; limit?: number }): Message[];
  close(): void;
}

/** Open (or create) a SQLite-backed Store at `path` (":memory:" allowed for tests). */
export function openStore(_path: string): Store {
  throw new Error("NOT IMPLEMENTED: openStore — Gate 2 SQLite Store (see SPEC §Persistence)");
}
