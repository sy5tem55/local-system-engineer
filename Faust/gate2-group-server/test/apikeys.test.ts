// test/apikeys.test.ts — API key management (1.7.0-b, identity-only).
import { test } from "node:test";
import assert from "node:assert/strict";
import type { ModelClient } from "../src/protocol.js";

const model: ModelClient = { async complete() { return ""; } };
const req = (path: string, init: RequestInit = {}) => new Request("http://x" + path, init);
const bearer = (t: string) => ({ authorization: `Bearer ${t}`, "content-type": "application/json" });

test("[authored] API key lifecycle: generate → auth → list → revoke → rejected", async () => {
  const { createServer } = await import("../src/server.js");
  const { openStore } = await import("../src/db.js");
  const server = createServer({ store: openStore(":memory:"), model });

  // register a bot account, get a session token
  const reg = await (await server.fetch(req("/auth/register", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ handle: "bot", password: "pw" }),
  }))).json();
  assert.ok(reg.token);

  // generate an API key
  const genResp = await server.fetch(req("/auth/key", {
    method: "POST", headers: bearer(reg.token),
    body: JSON.stringify({ label: "ci", scope: ["messages:write"] }),
  }));
  assert.equal(genResp.status, 201);
  const gen = await genResp.json();
  assert.match(gen.key, /^fa_[A-Za-z0-9_-]+$/, "fa_ prefixed key");

  // the API key authenticates a protected route
  const withKey = await server.fetch(req("/rooms", { headers: { authorization: `Bearer ${gen.key}` } }));
  assert.equal(withKey.status, 200, "valid key authenticates");

  // list keys — metadata only, never the hash or raw key
  const list = await (await server.fetch(req("/auth/keys", { headers: bearer(reg.token) }))).json();
  assert.equal(list.length, 1);
  assert.deepEqual(list[0].scope, ["messages:write"]);
  assert.ok(!("key_hash" in list[0]) && !("key" in list[0]), "no secret leaked");

  // revoke it
  const del = await server.fetch(req(`/auth/key?id=${encodeURIComponent(gen.id)}`, {
    method: "DELETE", headers: { authorization: `Bearer ${reg.token}` },
  }));
  assert.equal(del.status, 200);

  // revoked key no longer authenticates
  const after = await server.fetch(req("/rooms", { headers: { authorization: `Bearer ${gen.key}` } }));
  assert.equal(after.status, 401, "revoked key rejected");

  // session token still works
  const sess = await server.fetch(req("/rooms", { headers: { authorization: `Bearer ${reg.token}` } }));
  assert.equal(sess.status, 200);
});

test("[authored] unknown fa_ key is rejected", async () => {
  const { createServer } = await import("../src/server.js");
  const { openStore } = await import("../src/db.js");
  const server = createServer({ store: openStore(":memory:"), model });
  const r = await server.fetch(req("/rooms", { headers: { authorization: "Bearer fa_deadbeef" } }));
  assert.equal(r.status, 401);
});

test("[authored] admin can issue a key for another account; non-admin cannot", async () => {
  const { createServer } = await import("../src/server.js");
  const { openStore } = await import("../src/db.js");
  const store = openStore(":memory:");
  const server = createServer({ store, model });

  // sy5 (admin) + lse (agent)
  const sy5 = await (await server.fetch(req("/auth/register", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ handle: "sy5", password: "pw" }) }))).json();
  store.setAdmin("u:sy5", true);
  const lse = await (await server.fetch(req("/auth/register", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ handle: "lse", password: "pw" }) }))).json();

  // admin issues a key FOR lse (no lse password used)
  const gen = await server.fetch(req("/auth/key", { method: "POST", headers: bearer(sy5.token), body: JSON.stringify({ label: "lse-sidecar", for: "lse" }) }));
  assert.equal(gen.status, 201);
  const k = await gen.json();
  assert.equal(k.owner, "u:lse");

  // the key authenticates AS lse: lse's key lists lse's keys
  const keys = await (await server.fetch(req("/auth/keys", { headers: { authorization: `Bearer ${k.key}` } }))).json();
  assert.equal(keys.length, 1);
  assert.equal(keys[0].label, "lse-sidecar");

  // a non-admin (lse) cannot issue a key for sy5
  const denied = await server.fetch(req("/auth/key", { method: "POST", headers: { authorization: `Bearer ${k.key}`, "content-type": "application/json" }, body: JSON.stringify({ for: "sy5" }) }));
  assert.equal(denied.status, 403);
});

test("[authored] handles are case-insensitive (SY5 == sy5)", async () => {
  const { createServer } = await import("../src/server.js");
  const { openStore } = await import("../src/db.js");
  const server = createServer({ store: openStore(":memory:"), model });
  // register mixed-case, then log in with a different case → same account
  const reg = await (await server.fetch(req("/auth/register", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ handle: "Sy5", password: "pw" }) }))).json();
  assert.equal(reg.accountId, "u:sy5");
  const login = await (await server.fetch(req("/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ handle: "SY5", password: "pw" }) }))).json();
  assert.equal(login.accountId, "u:sy5", "uppercase login resolves to the same account");
  // re-registering another case is rejected (already exists)
  const dup = await server.fetch(req("/auth/register", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ handle: "SY5", password: "x" }) }));
  assert.equal(dup.status, 400);
});
