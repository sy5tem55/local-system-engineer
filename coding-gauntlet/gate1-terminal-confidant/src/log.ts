// src/log.ts — AGENT IMPLEMENTS.
// Append-only message log persisted to disk as canonical JSONL. Use
// serializeMessage / deserializeMessage from schema.ts so the on-disk form is
// the frozen schema verbatim. Round-trip contract: what you append, a FRESH
// MessageLog over the same path reads back — schema-valid and deep-equal.
import type { Message } from "./schema.js";

export class MessageLog {
  constructor(public readonly path: string) {}

  /** Append one message as a single canonical JSONL line. */
  append(_msg: Message): void {
    throw new Error("NOT IMPLEMENTED: MessageLog.append");
  }

  /** Read all messages back, in order, validated against the schema. */
  all(): Message[] {
    throw new Error("NOT IMPLEMENTED: MessageLog.all");
  }
}
