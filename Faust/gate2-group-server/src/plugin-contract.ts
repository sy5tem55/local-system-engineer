// src/plugin-contract.ts — FROZEN versioned third-party plugin API for the Coding Gauntlet.
// This is THE contract a third party writes a plugin against, and the surface Gate 4 carries
// onto iOS. Do not change shapes without a version bump. Reuses the canonical Message/Author.
import type { Message, Author } from "./schema.js";

export const PLUGIN_API_VERSION = "g3.1" as const;
export const PLUGIN_API_MAJOR = 3 as const;

// ── Capabilities — the sandbox boundary ──────────────────────────────────────
// A plugin declares the capabilities it needs in its manifest. The host grants ONLY
// those; anything undeclared is absent from the PluginContext it receives. This is
// capability-based security: no grant => no API, enforced at the contract surface.
export type Capability = "net" | "exec" | "render" | "read_room" | "attach";

export interface PluginManifest {
  name: string; // unique plugin id, e.g. "search"
  version: string; // semver of the plugin
  apiVersion: string; // must satisfy PLUGIN_API_MAJOR (e.g. "g3.x")
  entry: string; // path (relative to the manifest) to the plugin module's default export
  capabilities: Capability[]; // what the host must grant
  commands?: string[]; // slash-commands it registers, e.g. ["/search"]
  description?: string;
}

// ── Capability-scoped host APIs (only present if granted) ─────────────────────
export interface NetCapability { fetchText(url: string): Promise<string>; }
export interface ExecCapability { run(cmd: string, args: string[]): Promise<{ stdout: string; code: number }>; }
export interface ReadRoomCapability { history(roomId: string, limit?: number): Message[]; }

/** What a plugin is allowed to touch. Capability fields are present IFF declared+granted. */
export interface PluginContext {
  readonly granted: ReadonlySet<Capability>;
  log(msg: string): void; // always available
  net?: NetCapability; // present iff "net" granted
  exec?: ExecCapability; // present iff "exec" granted
  room?: ReadRoomCapability; // present iff "read_room" granted
  signal?: AbortSignal; // give-up budget
}

// ── Events + result ───────────────────────────────────────────────────────────
export interface PluginMessageEvent { roomId: string; message: Message; }
export interface PluginCommandEvent { roomId: string; command: string; args: string; author: Author; }

/** A plugin renders back into the thread as a normal message body (markdown -> opencode renderer). */
export interface PluginResult {
  content: string; // markdown
  kind?: "text" | "code" | "image";
}

/** The lifecycle a plugin implements (default export). At least one hook required. */
export interface Plugin {
  onMessage?(e: PluginMessageEvent, ctx: PluginContext): Promise<PluginResult | void> | PluginResult | void;
  onCommand?(e: PluginCommandEvent, ctx: PluginContext): Promise<PluginResult | void> | PluginResult | void;
}

// ── Manifest validation (pure, frozen) ────────────────────────────────────────
const CAPS: Capability[] = ["net", "exec", "render", "read_room", "attach"];

export function validateManifest(x: any): PluginManifest {
  if (!x || typeof x !== "object") throw new TypeError("manifest: not an object");
  for (const f of ["name", "version", "apiVersion", "entry"] as const) {
    if (typeof x[f] !== "string" || x[f] === "") throw new TypeError(`manifest.${f}: non-empty string required`);
  }
  if (!Array.isArray(x.capabilities) || x.capabilities.some((c: any) => !CAPS.includes(c)))
    throw new TypeError(`manifest.capabilities: array of ${CAPS.join("|")}`);
  const major = String(x.apiVersion).split(".")[0];
  if (major !== `g${PLUGIN_API_MAJOR}`)
    throw new TypeError(`manifest.apiVersion ${x.apiVersion} incompatible with host ${PLUGIN_API_VERSION}`);
  if (x.commands !== undefined && (!Array.isArray(x.commands) || x.commands.some((c: any) => typeof c !== "string")))
    throw new TypeError("manifest.commands: string[]");
  return {
    name: x.name, version: x.version, apiVersion: x.apiVersion, entry: x.entry,
    capabilities: [...x.capabilities], ...(x.commands ? { commands: [...x.commands] } : {}),
    ...(x.description ? { description: x.description } : {}),
  };
}

export type { Message, Author };
