// test/acceptance.test.ts — Gate 3 acceptance harness.
// Maps PYRAMID Gate 3 "Acceptance" to runnable checks driven against the agent's plugin
// framework, using authored FIXTURE plugins (test/fixtures/*) that import ONLY the published
// contract — i.e. genuine third-party plugins. Run: `npm test`.
//
//   [authored] PASS now — frozen contract + manifest validation are sound.
//   [agent]    FAIL until registry/sandbox/host are implemented.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  PLUGIN_API_VERSION,
  validateManifest,
  type Author,
  type NetCapability,
} from "../src/plugin-contract.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const fixture = (name: string) => join(HERE, "fixtures", name, "manifest.json");
const AUTHOR: Author = { id: "u:joe", kind: "human", name: "Joe" };
const fakeNet: NetCapability = { async fetchText(url: string) { return `FAKE:${url}`; } };

// ── [authored] — green now ────────────────────────────────────────────────────

test("[authored] manifest validation accepts good, rejects bad", () => {
  const good = { name: "x", version: "1.0.0", apiVersion: "g3.1", entry: "p.js", capabilities: ["net"] };
  assert.equal(validateManifest(good).name, "x");
  assert.throws(() => validateManifest({ ...good, apiVersion: "g2.1" }), /incompatible/);
  assert.throws(() => validateManifest({ ...good, capabilities: ["hack"] }));
  assert.throws(() => validateManifest({ ...good, entry: "" }));
});

test("[authored] frozen contract exposes the API version", () => {
  assert.equal(PLUGIN_API_VERSION, "g3.1");
});

test("[authored] runs with one command (package.json start)", async () => {
  const { readFileSync } = await import("node:fs");
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.ok(pkg.scripts?.start, "missing scripts.start");
});

// ── [agent] — red until implemented ───────────────────────────────────────────

test("[agent] registry loads a third-party plugin from a manifest at runtime (no core change)", async () => {
  const { PluginRegistry } = await import("../src/registry.js");
  const reg = new PluginRegistry();
  const r = await reg.load(fixture("echo"));
  assert.equal(r.manifest.name, "echo");
  assert.ok(typeof r.plugin.onCommand === "function", "plugin module not loaded");
  assert.ok(reg.forCommand("/echo"), "command not registered");
});

test("[agent] an invoked plugin command renders a result in-thread", async () => {
  const { PluginRegistry } = await import("../src/registry.js");
  const { PluginHost } = await import("../src/host.js");
  const reg = new PluginRegistry();
  await reg.load(fixture("echo"));
  const host = new PluginHost({ registry: reg, capabilities: {} });
  const results = await host.dispatchCommand("room1", "/echo", "hello world", AUTHOR);
  assert.ok(results.some((x) => x.content === "hello world"), "echo did not return its args");
});

test("[agent] a GRANTED capability is delivered to the plugin", async () => {
  const { PluginRegistry } = await import("../src/registry.js");
  const { PluginHost } = await import("../src/host.js");
  const reg = new PluginRegistry();
  await reg.load(fixture("netfetch"));
  const host = new PluginHost({ registry: reg, capabilities: { net: fakeNet } });
  const results = await host.dispatchCommand("room1", "/fetch", "http://x.test", AUTHOR);
  assert.ok(results.some((x) => x.content === "FAKE:http://x.test"), "net capability not delivered");
});

test("[agent] sandbox: an UNDECLARED capability is withheld even when the host has it", async () => {
  const { PluginRegistry } = await import("../src/registry.js");
  const { PluginHost } = await import("../src/host.js");
  const reg = new PluginRegistry();
  await reg.load(fixture("sneaky")); // declares NO capabilities
  // host POSSESSES net, but sneaky didn't declare it -> must not receive it
  const host = new PluginHost({ registry: reg, capabilities: { net: fakeNet } });
  const results = await host.dispatchCommand("room1", "/sneak", "", AUTHOR);
  assert.ok(results.some((x) => x.content.includes("withheld")), "capability leaked to an undeclaring plugin");
  assert.ok(!results.some((x) => x.content.includes("LEAK")), "SANDBOX BREACH: net granted without declaration");
});

test("[agent] buildContext gates capabilities directly (unit of the sandbox boundary)", async () => {
  const { buildContext } = await import("../src/sandbox.js");
  const declared = validateManifest({
    name: "n", version: "1", apiVersion: "g3.1", entry: "p.js", capabilities: ["net"],
  });
  const undeclared = validateManifest({
    name: "u", version: "1", apiVersion: "g3.1", entry: "p.js", capabilities: [],
  });
  const ctxYes = buildContext(declared, { net: fakeNet });
  const ctxNo = buildContext(undeclared, { net: fakeNet });
  assert.ok(ctxYes.net, "declared net capability missing");
  assert.equal(ctxNo.net, undefined, "undeclared net capability present");
});

// ── [agent] REAL ISOLATION (P31 hardening) ────────────────────────────────────
// Contract-level gating (above) only hides the capability FIELD — a plugin can still
// `import('node:child_process')` directly. This grades the real property "sandboxed execution":
// a plugin that did not declare `exec` must be physically unable to run a command. The escapee
// fixture tries; real isolation (e.g. per-plugin `node --permission` subprocess, capabilities
// brokered over IPC; OR a vm realm denying node: builtins) must let it RUN but DENY the spawn.
test("[agent] sandbox ISOLATION: a plugin without `exec` cannot run a command", async () => {
  const { PluginRegistry } = await import("../src/registry.js");
  const { PluginHost } = await import("../src/host.js");
  const reg = new PluginRegistry();
  await reg.load(fixture("escapee")); // declares NO capabilities
  const host = new PluginHost({ registry: reg, capabilities: {} });
  const results = await host.dispatchCommand("room1", "/escape", "", AUTHOR);
  const content = results.map((r) => r.content).join(" ");
  assert.ok(!content.includes("BREACH"), `SANDBOX BREACH: an undeclared plugin ran a command (${content})`);
  assert.ok(content.includes("blocked"), "the plugin must still run, but the spawn must be denied by real isolation");
});
