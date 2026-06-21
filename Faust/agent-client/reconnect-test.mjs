// reconnect-test.mjs — proves the FaustAgent client survives a server restart.
// Boots the server, runs two scripted agents through the planning protocol, KILLS the
// server, RESTARTS it (same DB), and confirms the agents reconnect and converge again.
import { spawn } from "node:child_process";
import { FaustAgent } from "./faust-agent-client.mjs";

const PORT = 8793, BASE = `http://127.0.0.1:${PORT}`, DB = "/tmp/reconnect.sqlite";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const j = async (m, p, tok, b) => {
  const r = await fetch(BASE + p, { method: m, headers: { "content-type": "application/json", ...(tok ? { authorization: `Bearer ${tok}` } : {}) }, body: b ? JSON.stringify(b) : undefined });
  try { return { status: r.status, data: JSON.parse(await r.text()) }; } catch { return { status: r.status, data: null }; }
};
const auth = async (h, pw) => { let r = await j("POST", "/auth/register", null, { handle: h, password: pw }); if (r.status >= 400) r = await j("POST", "/auth/login", null, { handle: h, password: pw }); return r.data; };

function startServer() {
  const cp = spawn("node", ["--import", "tsx", "src/index.ts"], {
    cwd: new URL("../gate2-group-server/", import.meta.url).pathname,
    env: { ...process.env, PORT: String(PORT), DB_PATH: DB, ADMIN_HANDLES: "sy5", AGENT_HANDLES: "hermes,lse" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  return new Promise((res) => {
    const onData = (d) => { if (d.toString().includes("Faust running")) { cp.stdout.off("data", onData); res(cp); } };
    cp.stdout.on("data", onData);
  });
}
const onCue = async ({ phase, round, handle }) => {
  if (phase === "tasking") return `@${handle === "hermes" ? "lse" : "hermes"}: own your part [[DONE]]`;
  return round >= 2 ? `agreed, looks good [[CONVERGED]]` : `${handle} proposes: scope tight, ship MVP, measure`;
};
const waitFor = async (token, roomId, needleAfterTs, ms) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const msgs = (await j("GET", `/rooms/${roomId}/messages`, token)).data ?? [];
    if (msgs.some((m) => m.content.includes("PLAN CONVERGED") && m.ts > needleAfterTs)) return true;
    await sleep(200);
  }
  return false;
};

let srv;
try {
  console.log("boot server #1"); srv = await startServer();
  const admin = await auth("sy5", "pw");
  await auth("hermes", "pw"); await auth("lse", "pw");
  const room = (await j("POST", "/rooms", admin.token, { name: "SY5L4N" })).data;
  console.log("room:", room.id);

  // mint durable API keys, start agents with them
  const agents = [];
  for (const h of ["hermes", "lse"]) {
    const a = new FaustAgent({ baseUrl: BASE, handle: h, password: "pw", room: "SY5L4N", onCue, log: () => {} });
    const key = await a.mintApiKey();
    a.apiKey = key; a.password = null;        // now durable-key only
    await a.start(); agents.push(a);
  }
  await sleep(400);

  console.log("\n=== cycle 1 (fresh) ==="); let t = Date.now();
  await j("POST", `/rooms/${room.id}/messages`, admin.token, { content: "/plan revamp onboarding" });
  console.log("cycle 1 converged:", await waitFor(admin.token, room.id, t, 8000) ? "✅" : "❌");

  console.log("\n=== KILL server, restart (same DB) ===");
  srv.kill("SIGKILL"); await sleep(1500);
  srv = await startServer(); console.log("server #2 up");
  console.log("waiting for agents to reconnect (backoff)…"); await sleep(6000);

  console.log("\n=== cycle 2 (after restart — agents must have reconnected) ==="); t = Date.now();
  await j("POST", `/rooms/${room.id}/messages`, admin.token, { content: "/plan add API key scopes" });
  const ok2 = await waitFor(admin.token, room.id, t, 12000);
  console.log("cycle 2 converged AFTER restart:", ok2 ? "✅ RECONNECTION WORKS" : "❌ agents did not reconnect");

  for (const a of agents) a.stop();
  process.exit(ok2 ? 0 : 1);
} catch (e) { console.error("TEST ERROR:", e); process.exit(1); }
finally { if (srv) try { srv.kill("SIGKILL"); } catch {} }
