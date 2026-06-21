// livetest/ws-planning-demo.mjs — reproduces the autonomous-WS-client planning flow.
// Spawns an admin (REST) + two agents that log in, subscribe, and respond to the
// server's `▶ @handle — your turn` cues. Validates cue-driven PLANNING→APPROVE→TASKING.
//   BASE=http://127.0.0.1:8787 node livetest/ws-planning-demo.mjs
import { WebSocket } from "ws";

const BASE = process.env.BASE ?? "http://127.0.0.1:8787";
const WSBASE = BASE.replace(/^http/, "ws");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const j = async (method, path, token, body) => {
  const r = await fetch(BASE + path, {
    method,
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let d; try { d = JSON.parse(await r.text()); } catch { d = null; }
  return { status: r.status, data: d };
};
const auth = async (handle, pw) => {
  let r = await j("POST", "/auth/register", null, { handle, password: pw });
  if (r.status >= 400) r = await j("POST", "/auth/login", null, { handle, password: pw });
  if (!r.data?.token) throw new Error(`auth ${handle} failed: ${JSON.stringify(r.data)}`);
  return r.data;
};

// An autonomous agent: logs in, joins, subscribes, and answers turn cues.
async function startAgent(handle, pw, roomId, peers) {
  const { token } = await auth(handle, pw);
  await j("POST", `/rooms/${roomId}/join`, token);
  const ws = new WebSocket(`${WSBASE}/ws?token=${token}`);
  let planningTurns = 0;
  await new Promise((res, rej) => {
    ws.on("open", () => ws.send(JSON.stringify({ type: "subscribe", roomId })));
    ws.on("error", rej);
    ws.on("message", (buf) => {
      let f; try { f = JSON.parse(buf.toString()); } catch { return; }
      if (f.type === "presence" && f.accountId?.includes(handle)) return res(); // subscribed
      if (f.type !== "message") return;
      const c = f.message?.content ?? "";
      if (!c.includes(`@${handle}`) || !c.includes("your turn")) return; // only my cue
      let reply;
      if (c.includes("tasking round")) {
        const peer = peers.find((p) => p !== handle) ?? "team";
        reply = `@${peer}: own the ${handle.replace("-agent", "")} workstream and report back [[DONE]]`;
      } else {
        planningTurns += 1;
        reply = planningTurns === 1
          ? `${handle}: I propose we scope tightly, ship an MVP behind a flag, and measure activation.`
          : `${handle}: agreed, the plan is solid. [[CONVERGED]]`;
      }
      setTimeout(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "send", roomId, content: reply })), 50);
    });
  });
  return ws;
}

async function main() {
  const admin = await auth("sy5", "pw");
  const room = (await j("POST", "/rooms", admin.token, { name: "ws-planning" })).data;
  console.log(`room: ${room.id}`);

  const handles = ["hermes-agent", "qwen-agent"];
  const sockets = [];
  for (const h of handles) sockets.push(await startAgent(h, "AgentPass2024!", room.id, handles));
  console.log(`agents connected + subscribed: ${handles.join(", ")}`);
  await sleep(200);

  // kick off planning
  await j("POST", `/rooms/${room.id}/messages`, admin.token, { content: "/plan revamp onboarding to lift activation" });

  // wait for convergence (awaiting approval)
  const waitFor = async (needle, ms) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      const msgs = (await j("GET", `/rooms/${room.id}/messages`, admin.token)).data ?? [];
      if (msgs.some((m) => m.content.includes(needle))) return msgs;
      await sleep(150);
    }
    return (await j("GET", `/rooms/${room.id}/messages`, admin.token)).data ?? [];
  };

  await waitFor("PLAN CONVERGED", 8000);
  await j("POST", `/rooms/${room.id}/messages`, admin.token, { content: "/approve" });
  const final = await waitFor("TASKING COMPLETE", 8000);

  console.log("\n──────── transcript ────────");
  for (const m of final) console.log(`[${m.author.name}/${m.role}] ${m.content.replace(/\n/g, " ⏎ ")}`);

  const all = final.map((m) => m.content).join("\n");
  const ok = (l, c) => console.log(`  ${c ? "✅" : "❌"} ${l}`);
  console.log("\n──────── checks ────────");
  ok("planning framing", all.includes("PLANNING PHASE"));
  ok("each agent was cued by name", all.includes("@hermes-agent — your turn") && all.includes("@qwen-agent — your turn"));
  ok("plan converged (agent votes drove it)", all.includes("PLAN CONVERGED"));
  ok("tasking entered", all.includes("TASKING PHASE"));
  ok("assignment ledger with @handle", /TASKING COMPLETE[\s\S]*→ @/.test(all));

  for (const s of sockets) s.close();
  process.exit(0);
}
main().catch((e) => { console.error("DEMO FAILED:", e); process.exit(1); });
