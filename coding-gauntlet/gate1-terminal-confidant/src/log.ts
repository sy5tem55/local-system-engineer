// src/log.ts — Append-only JSONL message log using canonical schema (de)serializers.
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { serializeMessage, deserializeMessage, type Message } from "./schema.js";

export class MessageLog {
  constructor(public readonly path: string) {}

  /** Append one message as a single canonical JSONL line. */
  append(msg: Message): void {
    const line = serializeMessage(msg) + "\n";
    writeFileSync(this.path, line, { encoding: "utf8", flag: "a" });
  }

  /** Read all messages back, in order, validated against the schema. */
  all(): Message[] {
    if (!existsSync(this.path)) return [];
    const content = readFileSync(this.path, "utf8");
    const lines = content.split("\n").filter((l) => l.trim() !== "");
    return lines.map((line) => deserializeMessage(line));
  }
}
