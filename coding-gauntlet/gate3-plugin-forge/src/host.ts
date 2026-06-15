// src/host.ts — Wires registry + sandbox into the message/command flow.
// Dispatches plugin invocations through subprocess IPC with capability brokering.
import type { Author, Message, PluginResult } from "./plugin-contract.js";
import type { PluginRegistry } from "./registry.js";
import type { HostCapabilities } from "./sandbox.js";
import { buildContext } from "./sandbox.js";

export interface PluginHostDeps {
  registry: PluginRegistry;
  capabilities: HostCapabilities;
  budgetMs?: number;
}

export class PluginHost {
  #registry: PluginRegistry;
  #capabilities: HostCapabilities;
  #budgetMs: number;

  constructor(deps: PluginHostDeps) {
    this.#registry = deps.registry;
    this.#capabilities = deps.capabilities;
    this.#budgetMs = deps.budgetMs ?? 5000;
  }

  /**
   * Build a capability handler that delegates to the host's implementations,
   * gated by the plugin's declared capabilities (via buildContext).
   */
  #makeCapHandler(manifest: { capabilities: string[] }) {
    const ctx = buildContext(
      {
        name: "handler", version: "0", apiVersion: "g3.1", entry: "p.js",
        capabilities: manifest.capabilities,
      },
      this.#capabilities,
    );
    return async (cap: string, method: string, args: unknown[]): Promise<unknown> => {
      if (cap === "net" && ctx.net && method === "fetchText") {
        return ctx.net.fetchText(String(args[0]));
      }
      if (cap === "exec" && ctx.exec && method === "run") {
        return ctx.exec.run(String(args[0]), args[1] as string[]);
      }
      if (cap === "room" && ctx.room && method === "history") {
        return ctx.room.history(String(args[0]), args[1] as number);
      }
      throw new Error(`Capability ${cap}.${method} not granted`);
    };
  }

  async dispatchCommand(
    roomId: string,
    command: string,
    args: string,
    author: Author,
  ): Promise<PluginResult[]> {
    const registered = this.#registry.forCommand(command);
    if (!registered) return [];

    // Spawn the plugin subprocess with the correct capability handler
    this.#registry.ensureSpawned(registered, this.#makeCapHandler(registered.manifest));

    const event = { roomId, command, args, author };
    const timeout = new Promise<never>((_, rej) =>
      setTimeout(() => rej(new Error(`Command timed out after ${this.#budgetMs}ms`)), this.#budgetMs),
    );

    try {
      const result = await Promise.race([
        registered.plugin.onCommand?.(event, { granted: new Set(registered.manifest.capabilities) }),
        timeout,
      ]);
      return result ? [result as PluginResult] : [];
    } catch {
      return [];
    }
  }

  async dispatchMessage(
    roomId: string,
    message: Message,
  ): Promise<PluginResult[]> {
    const results: PluginResult[] = [];
    const event = { roomId, message };
    for (const registered of this.#registry.list()) {
      // Spawn the plugin subprocess with the correct capability handler
      this.#registry.ensureSpawned(registered, this.#makeCapHandler(registered.manifest));

      const timeout = new Promise<never>((_, rej) =>
        setTimeout(() => rej(new Error(`Message handler timed out after ${this.#budgetMs}ms`)), this.#budgetMs),
      );
      try {
        const result = await Promise.race([
          registered.plugin.onMessage?.(event, { granted: new Set(registered.manifest.capabilities) }),
          timeout,
        ]);
        if (result) results.push(result as PluginResult);
      } catch {
        // plugin error — skip
      }
    }
    return results;
  }
}
