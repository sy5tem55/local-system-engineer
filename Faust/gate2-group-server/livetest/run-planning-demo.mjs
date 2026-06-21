// livetest/run-planning-demo.mjs — drives the full Faust planning protocol over
// REST against a running gate2 server. Validates PLANNING→APPROVE→TASKING with
// real HTTP model calls. Point AGENT_ENDPOINT at real model endpoints for a live run.
//   BASE=http://127.0.0.1:8787 AGENT_ENDPOINT=http://node3090.home.arpa:8642 node livetest/run-planning-demo.mjs
const BASE = process.env.BASE ?? "http://127.0.0.1:8787";
const AGENT_ENDPOINT = process.env.AGENT_ENDPOINT ?? "http://127.0.0.1:9100";
const ADMIN = process.env.ADMIN_HANDLE ?? "sy5"; // must be in the server's ADMIN_HANDLES
const PROTOCOL_PERSONA =
  "You are a planning agent in a multi-agent room. Follow the moderator's protocol: " +
  "in PLANNING, make a concise proposal or refine the current plan; when you fully agree, " +
  "include the token [[CONVERGED]]. In TASKING, assign concrete work to peers as `@handle: <task>` " +
  "and include [[DONE]] when your assignments are placed.";

const j = async (method, path, token, bodyObj) => {
  const r = await fetch(BASE + path, {
    method,
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: bodyObj ? JSON.stringify(bodyObj) : undefined,
  });
  const text = await r.text();
  let data; try { data = JSON.parse(text); } catch { data = text; }
  return { status: r.status, data };
};

const auth = async (handle, password) => {
  let r = await j("POST", "/auth/register", null, { handle, password });
  if (r.status >= 400) r = await j("POST", "/auth/login", null, { handle, password });
  if (!r.data?.token) throw new Error(`auth failed for ${handle}: ${JSON.stringify(r.data)}`);
  return r.data.token;
};

const printTranscript = (label, msgs) => {
  console.log(`\n──────── ${label} ────────`);
  for (const m of msgs) console.log(`[${m.author.name}/${m.role}] ${m.content.replace(/\n/g, " ⏎ ")}`);
};

async function main() {
  const token = await auth(ADMIN, "pw");
  const room = (await j("POST", "/rooms", token, { name: "planning-demo" })).data;
  console.log(`room: ${room.id}`);

  for (const handle of ["alice", "bob"]) {
    const r = await j("POST", `/rooms/${room.id}/agents`, token, {
      handle, endpoint: AGENT_ENDPOINT, model: handle, persona: PROTOCOL_PERSONA,
    });
    console.log(`added agent ${handle}: ${r.status}`);
  }

  // PLANNING (REST send runs the round-robin synchronously)
  await j("POST", `/rooms/${room.id}/messages`, token, { content: "/plan revamp user onboarding to lift activation" });
  printTranscript("after /plan", (await j("GET", `/rooms/${room.id}/messages`, token)).data);

  // APPROVE → TASKING
  await j("POST", `/rooms/${room.id}/messages`, token, { content: "/approve" });
  const final = (await j("GET", `/rooms/${room.id}/messages`, token)).data;
  printTranscript("after /approve (full)", final);

  // checks
  const all = final.map((m) => m.content).join("\n");
  const ok = (label, cond) => console.log(`  ${cond ? "✅" : "❌"} ${label}`);
  console.log("\n──────── checks ────────");
  ok("planning framing posted", all.includes("PLANNING PHASE"));
  ok("plan converged", all.includes("PLAN CONVERGED"));
  ok("tasking phase entered", all.includes("TASKING PHASE"));
  ok("assignment ledger posted", all.includes("TASKING COMPLETE"));
  ok("an @handle: assignment captured in ledger", /TASKING COMPLETE[\s\S]*→ @/.test(all));
}
main().catch((e) => { console.error("DEMO FAILED:", e); process.exit(1); });
