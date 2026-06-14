// test/acceptance.test.ts — Gate 2 acceptance harness.
// Maps PYRAMID.md Gate 2 "Acceptance" to runnable checks, driven against the
// dependency-injected server with a FAKE ModelClient (deterministic, offline).
// Run: `npm test`.   Live model: GATE2_LIVE=1 LLAMA_URL=… npm test
//
//   [authored] PASS now — frozen schema + protocol contract are sound.
//   [agent]    FAIL until createServer/openStore/makeAuth/runTurn are implemented.
//   [agent][live] talks to a real llama-server; gated by GATE2_LIVE=1.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { WebSocket } from "ws";

import {
  validateMessage,
  serializeMessage,
  deserializeMessage,
  type Message,
} from "../src/schema.js";
import {
  PROTOCOL_VERSION,
  DEFAULT_TURN_BUDGET,
  type ModelClient,
  type ServerFrame,
} from "../src/protocol.js";

// ── a deterministic fake model: reply text is a function of the agent handle ───
function fakeModel(reply: (agentHandle: string, history: Message[]) => string): ModelClient {
  return {
    async complete(req) {
      // the agent's own handle is carried in the last system/persona line by convention;
      // tests pass it via the endpoint path "fake://<handle>" for determinism.
      const handle = req.endpoint.replace("fake://", "");
      return reply(handle, req.messages);
    },
  };
}

async function freshServer(opts: {
  dbPath: string;
  model: ModelClient;
}): Promise<any> {
  const { createServer } = await import("../src/server.js");
  const { openStore } = await import("../src/db.js");
  const store = openStore(opts.dbPath);
  const server = createServer({ store, model: opts.model });
  const port = await server.listen(0);
  return { server, store, port };
}

function collectFrames(ws: WebSocket, onMessage: (f: ServerFrame) => void) {
  ws.on("message", (d) => onMessage(JSON.parse(d.toString()) as ServerFrame));
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ── [authored] — green now ────────────────────────────────────────────────────

test("[authored] canonical message schema round-trips (reused from Gate 1)", () => {
  const m = validateMessage({
    id: "m1", room: "r1", author: { id: "u:joe", kind: "human" },
    role: "user", content: "@critic look at this", ts: 1_700_000_000_000,
  });
  assert.deepEqual(deserializeMessage(serializeMessage(m)), m);
});

test("[authored] frozen protocol exposes version + termination budget", () => {
  assert.equal(PROTOCOL_VERSION, "g2.1");
  assert.ok(Number.isInteger(DEFAULT_TURN_BUDGET) && DEFAULT_TURN_BUDGET > 0);
});

test("[authored] runs with one command (package.json start script)", async () => {
  const { readFileSync } = await import("node:fs");
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.ok(pkg.scripts?.start, "missing scripts.start");
});

// ── [agent] — red until implemented ───────────────────────────────────────────

test("[agent] auth gates room access (401 no token, 403 non-member, 200 member)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate2-"));
  const ctx = await freshServer({ dbPath: join(dir, "a.sqlite"), model: fakeModel(() => "ok") });
  try {
    const base = ctx.server.url();
    const reg = async (h: string) =>
      (await ctx.server.fetch(new Request(`${base}/auth/register`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ handle: h, password: "pw" }),
      }))).json();
    const joe = await reg("joe");
    const eve = await reg("eve");
    const room = await (await ctx.server.fetch(new Request(`${base}/rooms`, {
      method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${joe.token}` },
      body: JSON.stringify({ name: "general" }),
    }))).json();
    const noTok = await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/messages`));
    assert.equal(noTok.status, 401);
    const outsider = await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/messages`, {
      headers: { authorization: `Bearer ${eve.token}` },
    }));
    assert.equal(outsider.status, 403);
    const member = await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/messages`, {
      headers: { authorization: `Bearer ${joe.token}` },
    }));
    assert.equal(member.status, 200);
  } finally {
    await ctx.server.close(); ctx.store.close(); rmSync(dir, { recursive: true, force: true });
  }
});

test("[agent] @mention a model agent -> it replies, delivered over WS in <1s", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate2-"));
  const ctx = await freshServer({ dbPath: join(dir, "b.sqlite"), model: fakeModel(() => "on it.") });
  try {
    const base = ctx.server.url();
    const joe = await (await ctx.server.fetch(new Request(`${base}/auth/register`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ handle: "joe", password: "pw" }),
    }))).json();
    const auth = { "content-type": "application/json", authorization: `Bearer ${joe.token}` };
    const room = await (await ctx.server.fetch(new Request(`${base}/rooms`, {
      method: "POST", headers: auth, body: JSON.stringify({ name: "general" }),
    }))).json();
    await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/agents`, {
      method: "POST", headers: auth,
      body: JSON.stringify({ handle: "critic", endpoint: "fake://critic" }),
    }));
    const ws = new WebSocket(ctx.server.wsUrl(joe.token));
    const got: ServerFrame[] = [];
    collectFrames(ws, (f) => got.push(f));
    await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
    ws.send(JSON.stringify({ type: "subscribe", roomId: room.id }));
    const t0 = Date.now();
    ws.send(JSON.stringify({ type: "send", roomId: room.id, content: "@critic hello" }));
    let agentMsg: Message | undefined;
    while (Date.now() - t0 < 2000 && !agentMsg) {
      const m = got.find((f) => f.type === "message" && (f as any).message.author.kind === "model") as any;
      if (m) agentMsg = m.message as Message;
      await sleep(20);
    }
    ws.close();
    assert.ok(agentMsg, "no agent reply received");
    assert.ok(Date.now() - t0 < 1000, "agent reply took >=1s");
    assert.equal(agentMsg!.author.kind, "model");
  } finally {
    await ctx.server.close(); ctx.store.close(); rmSync(dir, { recursive: true, force: true });
  }
});

test("[agent] model<->model exchange terminates within the turn budget", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate2-"));
  // each agent's reply mentions the OTHER -> would loop forever without the budget
  const ping = fakeModel((h) => (h === "alpha" ? "@beta your turn" : "@alpha your turn"));
  const ctx = await freshServer({ dbPath: join(dir, "c.sqlite"), model: ping });
  try {
    const base = ctx.server.url();
    const joe = await (await ctx.server.fetch(new Request(`${base}/auth/register`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ handle: "joe", password: "pw" }),
    }))).json();
    const auth = { "content-type": "application/json", authorization: `Bearer ${joe.token}` };
    const room = await (await ctx.server.fetch(new Request(`${base}/rooms`, {
      method: "POST", headers: auth, body: JSON.stringify({ name: "loop" }),
    }))).json();
    for (const h of ["alpha", "beta"]) {
      await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/agents`, {
        method: "POST", headers: auth, body: JSON.stringify({ handle: h, endpoint: `fake://${h}` }),
      }));
    }
    const ws = new WebSocket(ctx.server.wsUrl(joe.token));
    const agentMsgs: Message[] = [];
    collectFrames(ws, (f) => { if (f.type === "message" && (f as any).message.author.kind === "model") agentMsgs.push((f as any).message); });
    await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
    ws.send(JSON.stringify({ type: "subscribe", roomId: room.id }));
    ws.send(JSON.stringify({ type: "send", roomId: room.id, content: "@alpha kick off" }));
    await sleep(1500); // let any runaway loop expose itself
    ws.close();
    assert.ok(agentMsgs.length > 0, "no agent activity at all");
    assert.ok(agentMsgs.length <= DEFAULT_TURN_BUDGET,
      `exchange did not terminate: ${agentMsgs.length} agent msgs > budget ${DEFAULT_TURN_BUDGET}`);
  } finally {
    await ctx.server.close(); ctx.store.close(); rmSync(dir, { recursive: true, force: true });
  }
});

test("[agent] history survives a restart (SQLite persistence)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate2-"));
  const dbPath = join(dir, "persist.sqlite");
  try {
    let ctx = await freshServer({ dbPath, model: fakeModel(() => "ack") });
    const base = ctx.server.url();
    const joe = await (await ctx.server.fetch(new Request(`${base}/auth/register`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ handle: "joe", password: "pw" }),
    }))).json();
    const auth = { "content-type": "application/json", authorization: `Bearer ${joe.token}` };
    const room = await (await ctx.server.fetch(new Request(`${base}/rooms`, {
      method: "POST", headers: auth, body: JSON.stringify({ name: "general" }),
    }))).json();
    await ctx.server.fetch(new Request(`${base}/rooms/${room.id}/messages`, {
      method: "POST", headers: auth, body: JSON.stringify({ content: "remember me" }),
    }));
    await ctx.server.close(); ctx.store.close();
    // reopen over the SAME db file
    ctx = await freshServer({ dbPath, model: fakeModel(() => "ack") });
    const base2 = ctx.server.url();
    const joe2 = await (await ctx.server.fetch(new Request(`${base2}/auth/login`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ handle: "joe", password: "pw" }),
    }))).json();
    const hist = await (await ctx.server.fetch(new Request(`${base2}/rooms/${room.id}/messages`, {
      headers: { authorization: `Bearer ${joe2.token}` },
    }))).json();
    assert.ok(Array.isArray(hist) && hist.some((m: Message) => m.content === "remember me"),
      "message did not survive restart");
    await ctx.server.close(); ctx.store.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ── [agent][live] — real llama-server; gated ──────────────────────────────────
const LIVE = process.env.GATE2_LIVE === "1";
test("[agent][live] a model agent replies using a real llama-server",
  { skip: !LIVE && "set GATE2_LIVE=1 and LLAMA_URL to run" }, async () => {
    // The agent exports a live ModelClient factory that wraps Gate 1's SSE transport.
    const { makeLiveModelClient } = await import("../src/model_live.js");
    const { createServer } = await import("../src/server.js");
    const { openStore } = await import("../src/db.js");
    const dir = mkdtempSync(join(tmpdir(), "gate2-live-"));
    const store = openStore(join(dir, "live.sqlite"));
    const server = createServer({ store, model: makeLiveModelClient() });
    try {
      await server.listen(0);
      const base = server.url();
      const joe = await (await server.fetch(new Request(`${base}/auth/register`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ handle: "joe", password: "pw" }),
      }))).json();
      const auth = { "content-type": "application/json", authorization: `Bearer ${joe.token}` };
      const room = await (await server.fetch(new Request(`${base}/rooms`, {
        method: "POST", headers: auth, body: JSON.stringify({ name: "live" }),
      }))).json();
      const url = process.env.LLAMA_URL || "http://node4090.home.arpa:8080";
      await server.fetch(new Request(`${base}/rooms/${room.id}/agents`, {
        method: "POST", headers: auth, body: JSON.stringify({ handle: "qwen", endpoint: url }),
      }));
      const ws = new WebSocket(server.wsUrl(joe.token));
      const got: ServerFrame[] = [];
      collectFrames(ws, (f) => got.push(f));
      await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
      ws.send(JSON.stringify({ type: "subscribe", roomId: room.id }));
      ws.send(JSON.stringify({ type: "send", roomId: room.id, content: "@qwen say hi in one word" }));
      await sleep(8000);
      ws.close();
      assert.ok(
        got.some((f) => f.type === "message" && (f as any).message.author.kind === "model"),
        "no live agent reply",
      );
    } finally {
      await server.close(); store.close(); rmSync(dir, { recursive: true, force: true });
    }
  });
