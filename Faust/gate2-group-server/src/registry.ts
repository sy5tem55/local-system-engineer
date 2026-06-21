// src/registry.ts — Runtime plugin registry with lazy subprocess isolation.
// Plugins are loaded (manifest read) at registry.load() time but the subprocess
// is spawned lazily by PluginHost with the correct capability handler.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { validateManifest } from "./plugin-contract.js";
import type {
  Plugin, PluginManifest, PluginCommandEvent, PluginMessageEvent,
  PluginContext, PluginResult,
} from "./plugin-contract.js";
import type { PluginSubprocess, CapHandler } from "./sandbox.js";
import { spawnPlugin } from "./sandbox.js";

export interface RegisteredPlugin {
  manifest: PluginManifest;
  plugin: Plugin;          // IPC proxy — looks like a Plugin but routes to subprocess
  dir: string;
  _subprocess?: PluginSubprocess; // lazily created by host
  _entryPath: string;
}

export class PluginRegistry {
  #plugins = new Map<string, RegisteredPlugin>();
  #commands = new Map<string, string>(); // command -> plugin name

  /**
   * Load a plugin manifest. The subprocess is NOT spawned here — it is spawned
   * lazily by PluginHost with the correct capability handler.
   */
  async load(manifestPath: string): Promise<RegisteredPlugin> {
    const raw = JSON.parse(readFileSync(manifestPath, "utf8"));
    const manifest = validateManifest(raw);
    const dir = dirname(manifestPath);
    const entryPath = join(dir, manifest.entry);

    // Placeholder proxy — will be replaced when subprocess is spawned
    const placeholder: Plugin = {
      async onCommand(): Promise<PluginResult | void> {
        throw new Error("Plugin subprocess not spawned — host must call ensureSpawned()");
      },
      async onMessage(): Promise<PluginResult | void> {
        throw new Error("Plugin subprocess not spawned — host must call ensureSpawned()");
      },
    };

    const entry: RegisteredPlugin = {
      manifest, plugin: placeholder, dir, _entryPath: entryPath,
    };
    this.#plugins.set(manifest.name, entry);
    if (manifest.commands) {
      for (const cmd of manifest.commands) {
        this.#commands.set(cmd, manifest.name);
      }
    }
    return entry;
  }

  /**
   * Spawn the plugin subprocess with the given capability handler.
   * Called by PluginHost before dispatching.
   * Respawns if the previous subprocess died.
   */
  ensureSpawned(entry: RegisteredPlugin, capHandler: CapHandler): void {
    // Check if existing subprocess is still alive
    if (entry._subprocess) {
      const exitCode = entry._subprocess.process.exitCode;
      const signaled = entry._subprocess.process.killed;
      if (exitCode === null && !signaled) return; // still alive
      // Subprocess died — clear stale reference so we respawn below
      console.warn(`  Plugin subprocess ${entry.manifest.name} died (exit=${exitCode}, killed=${signaled}), respawning...`);
      entry._subprocess = undefined;
      entry.plugin = {
        async onCommand(): Promise<PluginResult | void> {
          throw new Error("Plugin subprocess not spawned — host must call ensureSpawned()");
        },
        async onMessage(): Promise<PluginResult | void> {
          throw new Error("Plugin subprocess not spawned — host must call ensureSpawned()");
        },
      };
    }

    const sub = spawnPlugin(entry._entryPath, entry.dir, entry.manifest.capabilities, capHandler);

    // Clear _subprocess reference when child exits so next call respawns
    sub.process.on("exit", (code, signal) => {
      console.warn(`  Plugin subprocess ${entry.manifest.name} exited (code=${code}, signal=${signal})`);
      // Don't clear here — let ensureSpawned detect and respawn on next call
    });

    // Replace the placeholder proxy with the real IPC proxy
    const proxy: Plugin = {
      async onCommand(event: PluginCommandEvent, _ctx: PluginContext): Promise<PluginResult | void> {
        return sub.sendInvoke("onCommand", event);
      },
      async onMessage(event: PluginMessageEvent, _ctx: PluginContext): Promise<PluginResult | void> {
        return sub.sendInvoke("onMessage", event);
      },
    };

    entry.plugin = proxy;
    entry._subprocess = sub;
  }

  list(): RegisteredPlugin[] {
    return Array.from(this.#plugins.values());
  }

  forCommand(command: string): RegisteredPlugin | undefined {
    const name = this.#commands.get(command);
    return name ? this.#plugins.get(name) : undefined;
  }

  unload(name: string): void {
    const entry = this.#plugins.get(name);
    if (entry) {
      entry._subprocess?.close();
      if (entry.manifest.commands) {
        for (const cmd of entry.manifest.commands) {
          this.#commands.delete(cmd);
        }
      }
      this.#plugins.delete(name);
    }
  }
}
