# Faust Agent Client

A zero-dependency reconnecting client for autonomous Faust agents (Hermes, the LSE, …).
Drop `faust-agent-client.mjs` next to your agent and wrap your model around one `onCue`
hook — it handles everything else:

- **Durable auth** with a long-lived API key (`fa_…`) — no re-login on reconnect.
- **Persistent WebSocket** with exponential-backoff reconnect (1s→30s) + auto re-subscribe.
- **Heartbeat** ping; backoff resets once re-subscribed.
- **Turn-cue parsing** — calls `onCue()` only when the moderator posts
  `▶ @<your-handle> — your turn`, with the phase, round, objective, and recent history.

Requires Node 18.5+/22+ (uses the built-in global `WebSocket` and `fetch`). No `npm install`.

## 0. Provision agent keys (preferred — no agent passwords)

The steady-state auth is the **API key**, not passwords. The cleanest way to give an agent a
key is to have the **admin (`sy5`) issue one for it** — the agent never needs a password:

```bash
# admin logs in once (human), then issues durable keys FOR each agent.
# --noproxy '*' avoids a proxy swallowing localhost (conda/corp shells set http_proxy).
TOKEN=$(curl -s --noproxy '*' -X POST http://localhost:8787/auth/login -H 'content-type: application/json' \
      -d '{"handle":"sy5","password":"<sy5 pw>"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
echo "token chars: ${#TOKEN}"   # expect 64; if 0, check the login response / proxy / password
curl -s --noproxy '*' -X POST http://localhost:8787/auth/key -H "authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"label":"lse-sidecar","for":"lse"}'      # -> {"key":"fa_…","owner":"u:lse"}
curl -s --noproxy '*' -X POST http://localhost:8787/auth/key -H "authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"label":"hermes-bot","for":"hermes"}'    # -> {"key":"fa_…","owner":"u:hermes"}
```

Store each `fa_…` as that agent's `FAUST_KEY`. Only the human admin ever uses a password.

## 1. (Alternative) self-mint a durable key once

Each agent mints a key one time, then stores it (env var, secrets file, Vaultwarden):

```js
import { FaustAgent } from "./faust-agent-client.mjs";
const a = new FaustAgent({ baseUrl: "http://localhost:8787", handle: "hermes", password: "<pw>", room: "SY5L4N" });
console.log(await a.mintApiKey());   // -> fa_…  (store this; shown once)
```

## 2. Run the agent

```js
import { FaustAgent } from "./faust-agent-client.mjs";

const agent = new FaustAgent({
  baseUrl: "http://localhost:8787",
  handle: "hermes",
  apiKey: process.env.FAUST_KEY,        // the fa_ key from step 1 (durable across restarts)
  room: "SY5L4N",
  onCue: async ({ phase, round, objective, history, handle }) => {
    // YOUR reasoning goes here. `history` is the recent room messages
    // (each {author:{name}, role, content}). Return the text to post.
    const transcript = history.map(m => `${m.author?.name}: ${m.content}`).join("\n");

    if (phase === "planning") {
      const reply = await myModel.generate(
        `You are ${handle}. Objective: ${objective}\n${transcript}\n` +
        `Propose or refine the plan in <=120 words. If you fully agree with the ` +
        `current plan, end with the token [[CONVERGED]].`
      );
      return reply;   // include [[CONVERGED]] when you agree
    }
    // tasking
    return await myModel.generate(
      `You are ${handle}. Assign concrete work to peers as "@handle: <task>" and ` +
      `end with [[DONE]] when your assignments are placed.\n${transcript}`
    );
  },
});

await agent.start();   // connects, subscribes, and stays alive across server restarts
```

## Protocol reminder

- **Planning**: respond on your cue; end with `[[CONVERGED]]` once you agree. Planning ends
  on unanimous convergence or after 5 rounds, then the human admin `/approve`s.
- **Tasking**: assign work as `@handle: <task>`; end with `[[DONE]]`.
- The server cues you by name — only act on `▶ @<your-handle> — your turn`.

## Reconnection (verified)

`reconnect-test.mjs` boots the server, runs two agents through a planning round, **kills and
restarts the server**, and confirms the agents reconnect on their own and converge again:

```bash
node reconnect-test.mjs    # → "cycle 2 converged AFTER restart: ✅ RECONNECTION WORKS"
```

## Notes

- The API **key** is what makes reconnection durable (the reconnect path reuses it with no
  re-login). Scope is stored server-side but not yet enforced — any valid key authenticates
  as its owner with full access for now (see `Faust/IMPLEMENTATION.md`).
- If you pass `password` instead of `apiKey`, the client re-logs-in on each reconnect — works,
  but minting a key once is cleaner.


---

## Python (`faust_agent_client.py`)

Same client for Python agents. Deps: `pip install websockets` (REST uses the stdlib).

```python
import asyncio, os
from faust_agent_client import FaustAgent

async def on_cue(ctx):                       # ctx: phase, round, objective, history, handle, post
    transcript = "\n".join(f"{m['author'].get('name')}: {m['content']}" for m in ctx["history"])
    if ctx["phase"] == "planning":
        return await my_model(f"Objective: {ctx['objective']}\n{transcript}\n"
                              f"Propose/refine in <=120 words; end with [[CONVERGED]] when you agree.")
    return await my_model(f"Assign work as '@handle: <task>'; end with [[DONE]].\n{transcript}")

agent = FaustAgent(base_url="http://localhost:8787", handle="hermes",
                   api_key=os.environ["FAUST_KEY"], room="SY5L4N", on_cue=on_cue)
asyncio.run(agent.start())     # mint a key once: FaustAgent(..., password="…").mint_api_key()
```

**Do not block the socket loop.** `on_cue` runs on the client's asyncio loop; if your model
call is blocking, wrap it (`await asyncio.to_thread(blocking_generate, ...)`) so the agent keeps
servicing the WebSocket (heartbeats, other frames). A blocking `on_cue` stalls reconnection too.

## Integrating your two agents

- **Hermes** (standing Python agent, skill system): host `FaustAgent` inside its own loop, or
  package it as a `faust-connector` skill. Hermes owns the socket; `on_cue` calls its reasoning
  directly (off-loop per the note above).
- **The LSE** (OpenWebUI Goethe tool): an OWUI tool is request→response and **cannot** hold a
  socket, so run the ready-made **`lse-sidecar.py`** as a standalone process. Its `on_cue` calls
  the LSE's model directly at **llama-server `:8080`** (`/v1/chat/completions`, OpenAI-compatible)
  with a planning persona, and posts the completion. (Configurable to OWUI `:3000` via
  `LSE_MODEL_URL`/`LSE_MODEL_KEY`, but local Qwen3.6 doesn't reliably emit tool-calls over the API,
  so direct-to-llama-server is simpler and equivalent for planning.) Goethe stays the LSE's
  toolbelt for its normal OWUI chat work; the sidecar is just its planning-room voice.

  ```bash
  pip install websockets
  FAUST_BASE=http://localhost:8787 FAUST_PASSWORD='<lse pw>' \
    LSE_MODEL_URL=http://localhost:8080/v1/chat/completions \
    python3 lse-sidecar.py        # mints a durable key on first run; store it as FAUST_KEY
  ```

## Verified

- `reconnect_test.py` — Python client ↔ real Node server; **kills and restarts** the server and
  confirms both agents reconnect and converge again (`RECONNECTION WORKS`).
- `sidecar_test.py` — runs the real `lse-sidecar.py` (calling a stand-in model) + a scripted
  `hermes` through a `/plan`, confirming the sidecar participates and the room converges
  (`LSE sidecar participated + converged: WORKS`).


## Execution bridge (Track B) — assignments actually run

By default the LSE sidecar only *reasons* in planning. Set **`GOETHE_PATH`** to also let it
*execute* the `@lse:` assignments from the tasking ledger:

```bash
FAUST_KEY='fa_…(lse)' \
  LSE_MODEL_URL=http://localhost:8080/v1/chat/completions \
  GOETHE_PATH=~/projects/local-system-engineer/tools/goethe-v0.2.1.py \
  python3 lse-sidecar.py
```

How it works: after `/approve` and tasking converge, the moderator posts a `TASKING COMPLETE`
ledger. The sidecar parses lines `→ @lse: <task>`, and for each runs `GoetheExecutor`
(`goethe_executor.py`) — which imports Goethe's `Tools`, drives llama-server in a
Thought/Action/Observation ReAct loop over a curated tool subset (`execute_command`,
`read_file`, `search_kb`, `search_web`), and posts the result. Goethe's safety gates
(blocklist, no-sudo, privileged-path) are enforced on every call; the only human gate is the
plan `/approve` (plan-approval-only). Verified by `exec_test.py`.

To give **Hermes** the same power, wrap a ReAct executor over its own tools the same way.


## Putting Claude (or any model) in the room — `model-agent.py`

`model-agent.py` is a generic, reusable planning agent: the reconnecting client + an
`on_cue` that calls **any OpenAI-compatible endpoint**. Point it at a model and it joins as
a full planning participant (reasoning only; no tool execution — that's the LSE sidecar's job).

To add **Claude** via your OWUI **"LSE L2 — Claude Opus"** preset:

```bash
# 1. create the account + mint its key (admin, server running)
python3 faust-admin.py create-account claude          # if it doesn't exist yet (or register in the UI)
TOKEN=$(curl -s --noproxy '*' -X POST http://localhost:8787/auth/login -H 'content-type: application/json' \
      -d '{"handle":"sy5","password":"<sy5 pw>"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s --noproxy '*' -X POST http://localhost:8787/auth/key -H "authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"label":"claude-agent","for":"claude"}'   # -> {"key":"fa_…"}

# 2. add claude to the cued roster (restart the server with it included)
ADMIN_HANDLES=sy5 AGENT_HANDLES=hermes,lse,claude npx tsx src/index.ts

# 3. run the Claude agent (MODEL_KEY = an OWUI API key from OWUI → Settings → Account → API Keys;
#    MODEL_ID = the Opus preset's model id, e.g. claude-opus-4-6)
FAUST_KEY='fa_…(claude)' FAUST_HANDLE=claude \
  MODEL_URL=http://localhost:3000/api/chat/completions \
  MODEL_ID=claude-opus-4-6 MODEL_KEY='<owui api key>' \
  python3 model-agent.py
```

Then `/plan <objective>` cues `lse`, `hermes`, and `claude` in join order. The same binary
hosts any model agent — just change `FAUST_HANDLE` / `MODEL_*`.


## Let Faust supervise the LSE sidecar (no separate terminal)

Instead of running `lse-sidecar.py` by hand, have the **server** start/restart/stop it as a
managed child. Opt in with `AGENT_SIDECARS` and provide the LSE's key in the launch env (the
spec in `agents.json` references it as `${LSE_FAUST_KEY}`, so the secret stays out of the file):

```bash
cd ~/projects/Faust/gate2-group-server
LSE_FAUST_KEY='fa_…(lse)' \
  GOETHE_PATH=~/projects/local-system-engineer/tools/goethe-v0.2.1.py \
  ADMIN_HANDLES=sy5 AGENT_HANDLES=hermes,lse AGENT_SIDECARS=lse \
  npx tsx src/index.ts
```

The LSE comes up with the server, auto-restarts on crash (exp. backoff), and is killed on
shutdown. Its output goes to `gate2-group-server/logs/agent-lse.log`. Control it live from any
room: `/agents` (status) and `/agent lse restart|stop|start` (admin only). Spawn specs live in
`gate2-group-server/agents.json` — add more sidecars there. (This is a managed-process mechanism,
not the sandboxed plugin host; sidecars hold sockets and must persist, which the plugin sandbox
deliberately doesn't allow.)
