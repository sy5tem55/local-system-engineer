// livetest/fake-model.mjs — a scripted OpenAI-compatible model server for the
// Faust planning live-test. Stands in for real llama-server/Hermes endpoints so
// the whole flow can be exercised offline. Branches on body.model + phase.
//   node livetest/fake-model.mjs            (listens on :9100)
import http from "node:http";

const PORT = Number(process.env.FAKE_PORT ?? 9100);
const calls = new Map(); // model -> planning-call count

const PROPOSE = {
  alice: "I propose: 1) audit the current onboarding funnel, 2) cut steps to 3, 3) add a progress bar.",
  bob: "Counter: keep 4 steps but make step 2 optional, and instrument drop-off before cutting anything.",
};
const CONVERGE = {
  alice: "Agreed — instrument first, then cut to optional step 2. [[CONVERGED]]",
  bob: "Works for me, the plan is solid. [[CONVERGED]]",
};
const TASK = {
  alice: "@bob: instrument the funnel drop-off events this week [[DONE]]",
  bob: "@alice: draft the 3-step flow once we have the drop-off data [[DONE]]",
};

const server = http.createServer((req, res) => {
  if (req.method !== "POST" || !req.url.includes("/chat/completions")) {
    res.writeHead(404).end("not found");
    return;
  }
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    let model = "alice";
    let joined = "";
    try {
      const j = JSON.parse(body);
      model = j.model || "alice";
      joined = (j.messages || []).map((m) => m.content).join("\n");
    } catch { /* ignore */ }

    let content;
    if (joined.includes("TASKING PHASE")) {
      content = TASK[model] ?? `@sy5: review the plan [[DONE]]`;
    } else {
      const n = calls.get(model) ?? 0;
      calls.set(model, n + 1);
      content = n === 0 ? (PROPOSE[model] ?? `${model} proposes a step`) : (CONVERGE[model] ?? `agreed [[CONVERGED]]`);
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ choices: [{ message: { role: "assistant", content } }] }));
  });
});
server.listen(PORT, () => console.log(`fake-model listening on :${PORT}`));
