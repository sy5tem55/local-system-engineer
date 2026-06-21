// src/index.ts — Gate 3 entry: compose Gate 2 server + PluginHost + web client
import { readFileSync, existsSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "gate2-group-server/server.js";
import { openStore } from "gate2-group-server/db.js";
import { makeLiveModelClient } from "gate2-group-server/model_live.js";
import { PluginRegistry } from "./registry.js";
import { PluginHost } from "./host.js";
import type { Message } from "./schema.js";
import type { PluginResult } from "./plugin-contract.js";

const __dir = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dir, "..");

// ── Config ────────────────────────────────────────────────────────────────────
const DB_PATH = process.env.DB_PATH ?? join(PROJECT_ROOT, "data", "app.sqlite");
const PORT = Number(process.env.PORT ?? 8787);
const WEB_CLIENT = join(PROJECT_ROOT, "..", "gate2-group-server", "web", "index.html");

// ── Boot ──────────────────────────────────────────────────────────────────────
async function main() {
  console.log("Gate 3 — Plugin Forge starting...");

  // 1. Open the SQLite store
  const store = openStore(DB_PATH);
  console.log(`  Store: ${DB_PATH}`);

  // 2. Create the live model client
  const model = makeLiveModelClient();
  console.log("  Model client: live (OpenAI-compatible)");

  // 3. Load plugins from plugins/*/manifest.json
  const { readdirSync } = await import("node:fs");
  const registry = new PluginRegistry();
  const pluginsDir = join(PROJECT_ROOT, "plugins");
  if (existsSync(pluginsDir)) {
    for (const name of readdirSync(pluginsDir)) {
      const manifestPath = join(pluginsDir, name, "manifest.json");
      if (existsSync(manifestPath)) {
        try {
          await registry.load(manifestPath);
          console.log(`  Plugin loaded: ${name}`);
        } catch (e: any) {
          console.warn(`  Plugin load failed (${name}): ${e.message}`);
        }
      }
    }
  }
  console.log(`  Plugins: ${registry.list().length} loaded`);

  // 4. Build real HostCapabilities
  const hostCapabilities = {
    net: {
      fetchText: async (url: string): Promise<string> => {
        const r = await fetch(url, { headers: { "Accept": "application/json, text/plain, */*" } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      },
    },
    room: {
      history: (roomId: string, limit?: number): Message[] => {
        return store.listMessages(roomId, { limit });
      },
    },
    // exec intentionally omitted — no sandboxed runner available on this host
  };

  // 5. Create the PluginHost
  const host = new PluginHost({ registry, capabilities: hostCapabilities, budgetMs: 10000 });

  // 6. Wire plugin dispatch into the message flow
  async function onMessage(
    roomId: string,
    message: Message,
    broadcast: (roomId: string, frame: unknown) => void,
  ): Promise<void> {
    // Only process "/" command messages
    if (!message.content.startsWith("/")) return;

    // Parse command: /command args...
    const spaceIdx = message.content.indexOf(" ");
    const command = spaceIdx >= 0 ? message.content.slice(0, spaceIdx) : message.content;
    const args = spaceIdx >= 0 ? message.content.slice(spaceIdx + 1).trim() : "";

    console.log(`  Plugin command: ${command} args="${args}" in room ${roomId}`);

    // Dispatch to plugin host
    const results = await host.dispatchCommand(roomId, command, args, message.author);

    // Post each result back into the room as a system message
    for (const result of results) {
      const pluginMsg: Message = {
        id: `plugin:${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        room: roomId,
        author: { id: "plugin", kind: "model", name: "plugin" },
        role: "system",
        content: result.content,
        ts: Date.now(),
      };
      store.appendMessage(pluginMsg);
      broadcast(roomId, { type: "message", message: pluginMsg });
      console.log(`  Plugin result posted (${result.content.slice(0, 60)}...)`);
    }

    if (results.length === 0) {
      const fallback: Message = {
        id: `plugin:${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        room: roomId,
        author: { id: "plugin", kind: "model", name: "plugin" },
        role: "system",
        content: `Unknown command: \`${command}\`. Available: ${registry.list().map(p => p.manifest.commands?.join(", ") || "").filter(Boolean).join(", ") || "none"}`,
        ts: Date.now(),
      };
      store.appendMessage(fallback);
      broadcast(roomId, { type: "message", message: fallback });
    }
  }

  // 7. Create the server with plugin hook + static file serving
  const server = createServer({
    store,
    model,
    onMessage,
    staticFiles: {
      "/": WEB_CLIENT,
    },
  });

  // 8. Listen
  const port = await server.listen(PORT);
  console.log(`\n  🚀 Gate 3 running at http://localhost:${port}`);
  console.log(`  Open in browser to register, create rooms, add agents, @mention, /search\n`);

  // 9. Graceful shutdown
  const shutdown = async (signal: string) => {
    console.log(`\n  ${signal} — shutting down...`);
    // Close all plugin subprocesses
    for (const entry of registry.list()) {
      entry._subprocess?.close();
    }
    await server.close();
    store.close();
    console.log("  Clean shutdown complete.");
    process.exit(0);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main().catch((err) => {
  console.error("Failed to start:", err);
  process.exit(1);
});
