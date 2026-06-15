// src/sandbox.ts — Capability boundary, invocation budget, and subprocess isolation.
import { spawn, ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import type {
  Capability, PluginContext, PluginManifest, PluginResult,
  NetCapability, ExecCapability, ReadRoomCapability,
} from "./plugin-contract.js";

export interface HostCapabilities {
  net?: NetCapability;
  exec?: ExecCapability;
  room?: ReadRoomCapability;
}

// ── buildContext (pure — unit-tested independently) ──────────────────────────
/** Build the capability-scoped context for a plugin from its manifest + the host's impls. */
export function buildContext(
  manifest: PluginManifest,
  host: HostCapabilities,
  opts?: { signal?: AbortSignal; onLog?: (m: string) => void },
): PluginContext {
  const declared = new Set(manifest.capabilities);
  const granted = new Set<Capability>();

  if (declared.has("net") && host.net) granted.add("net");
  if (declared.has("exec") && host.exec) granted.add("exec");
  if (declared.has("read_room") && host.room) granted.add("read_room");

  const ctx: PluginContext = {
    granted,
    log: opts?.onLog ? (msg: string) => opts.onLog!(msg) : () => {},
    signal: opts?.signal,
  };

  if (granted.has("net")) ctx.net = host.net;
  if (granted.has("exec")) ctx.exec = host.exec;
  if (granted.has("read_room")) ctx.room = host.room;

  return ctx;
}

// ── invoke (budgeted — unchanged) ─────────────────────────────────────────────
/** Invoke a plugin hook under a budget. Returns its PluginResult (or void). */
export async function invoke(
  fn: (() => Promise<PluginResult | void> | PluginResult | void) | undefined,
  budgetMs: number,
): Promise<PluginResult | void> {
  if (!fn) return;
  const timeout = new Promise<never>((_, rej) =>
    setTimeout(() => rej(new Error(`Plugin invocation timed out after ${budgetMs}ms`)), budgetMs),
  );
  return Promise.race([fn(), timeout]);
}

// ── Subprocess sandbox (Node 22 --permission model) ──────────────────────────

/** Resolve a node binary that supports --permission (v22+). */
function findNodeBinary(): string {
  const home = process.env.HOME ?? "";
  const candidates = [
    join(home, ".nvm", "versions", "node", "v24.16.0", "bin", "node"),
    join(home, ".nvm", "versions", "node", "v24.0.0", "bin", "node"),
    join(home, ".nvm", "versions", "node", "v22.0.0", "bin", "node"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return "node"; // fallback
}

const NODE_BIN = findNodeBinary();

/** Runner script path (plain .js — no transpiler needed in the restricted child). */
const RUNNER = join(
  typeof __dirname !== "undefined" ? __dirname : new URL(".", import.meta.url).pathname,
  "plugin-runner.js",
);

/** Called by the subprocess stdout parser to resolve a capability request. */
export type CapHandler = (cap: string, method: string, args: unknown[]) => Promise<unknown>;

export interface PluginSubprocess {
  process: ChildProcess;
  sendInvoke(hook: "onCommand" | "onMessage", event: unknown): Promise<PluginResult | void>;
  close(): void;
}

/**
 * Global tracker for all spawned plugin subprocesses.
 * Ensures they are killed when the host process exits (e.g. after tests).
 */
const _allSubprocesses = new Set<ChildProcess>();

// Clean up all subprocesses on process exit — prevents the test runner from hanging.
process.on("exit", () => {
  for (const child of _allSubprocesses) {
    try { child.kill("SIGKILL"); } catch { /* already dead */ }
  }
});

/**
 * Spawn a plugin in its own `node --permission` subprocess.
 * Only the --allow-* flags matching the plugin's declared capabilities are granted.
 * No --allow-child-process means child_process throws ERR_ACCESS_DENIED.
 *
 * `onCapRequest` is called whenever the subprocess requests a capability;
 * the host resolves it and the result is piped back automatically.
 */
export function spawnPlugin(
  pluginPath: string,
  pluginDir: string,
  grantedCaps: Capability[],
  onCapRequest: CapHandler,
): PluginSubprocess {
  // Build --permission flags
  const permFlags: string[] = [];

  // Always allow reading the plugin's own directory (needed to load the module)
  // Also allow reading the src/ directory (where the runner lives)
  const srcDir = join(pluginDir, "..", "..");
  permFlags.push(`--allow-fs-read=${pluginDir}`);
  permFlags.push(`--allow-fs-read=${srcDir}`);

  // Grant child_process ONLY if exec was declared
  if (grantedCaps.includes("exec")) {
    permFlags.push("--allow-child-process");
  }

  const capsJson = JSON.stringify(grantedCaps);
  const child = spawn(NODE_BIN, ["--permission", ...permFlags, RUNNER, pluginPath, capsJson], {
    stdio: ["pipe", "pipe", "inherit"],
    env: { ...process.env, NODE_ENV: "production" },
  });

  _allSubprocesses.add(child);

  let nextId = 1;
  const pendingHooks = new Map<number, { resolve: (v: PluginResult | void) => void; reject: (e: Error) => void }>();

  // Parse stdout lines — handle hook results and capability requests
  let buffer = "";
  child.stdout.on("data", (chunk: Buffer) => {
    buffer += chunk.toString();
    let newlineIdx;
    while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIdx).trim();
      buffer = buffer.slice(newlineIdx + 1);
      if (!line) continue;
      let msg: unknown;
      try {
        msg = JSON.parse(line);
      } catch {
        continue;
      }
      const m = msg as Record<string, unknown>;

      if (m.type === "hook_result") {
        const p = pendingHooks.get(Number(m.id));
        if (p) { pendingHooks.delete(Number(m.id)); p.resolve(m.result as PluginResult | void); }
      } else if (m.type === "hook_error") {
        const p = pendingHooks.get(Number(m.id));
        if (p) {
          pendingHooks.delete(Number(m.id));
          p.reject(Object.assign(new Error(String(m.error)), { code: m.code }));
        }
      } else if (m.type === "cap_req") {
        const capReq = m as { id: number; cap: string; method: string; args: unknown[] };
        // Resolve the capability request via the host's handler, then pipe back
        (async () => {
          try {
            const value = await onCapRequest(capReq.cap, capReq.method, capReq.args);
            child.stdin.write(JSON.stringify({ type: "cap_res", id: capReq.id, value }) + "\n");
          } catch (err) {
            child.stdin.write(JSON.stringify({ type: "cap_res", id: capReq.id, error: String(err) }) + "\n");
          }
        })();
      }
      // "log" type messages are ignored here (could be forwarded to a logger)
    }
  });

  child.on("error", (e) => {
    for (const p of pendingHooks.values()) p.reject(e);
  });

  child.on("close", () => {
    _allSubprocesses.delete(child);
  });

  return {
    process: child,
    async sendInvoke(hook, event): Promise<PluginResult | void> {
      const id = nextId++;
      child.stdin.write(JSON.stringify({ type: "invoke", id, hook, event }) + "\n");
      return new Promise((resolve, reject) => pendingHooks.set(id, { resolve, reject }));
    },
    close() {
      // Reject all pending hooks immediately
      for (const p of pendingHooks.values()) p.reject(new Error("Subprocess closed"));
      pendingHooks.clear();
      // Destroy stdin to unblock the child, then force kill
      try { child.stdin.destroy(); } catch { /* already destroyed */ }
      try { child.kill("SIGKILL"); } catch { /* already dead */ }
    },
  };
}

export type { Capability };
