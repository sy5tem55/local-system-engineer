# Gate 3 — Integration: the runnable app (`index.ts`)

The harnesses proved the pieces. This wires them into **one product a human can open and use**:
the Gate 2 server + the Gate 3 plugin host + the opencode web client, behind a single `npm start`.
This is `src/index.ts` (currently a stub).

## Goal

`npm start` → open `http://<host>:<port>` in a browser → register/login → create a room → add a
local-model agent → `@mention` it and get a streamed reply → run a `/search` plugin and see the
result render in-thread. Humans + local models + plugins, in one running app.

## Architecture (compose, don't duplicate)

Gate 3 *is* "the plugin framework on the Gate 2 server," so the composed entry lives here and depends
on Gate 2:

- Add Gate 2 as a local dependency: in `package.json`, `"gate2-group-server": "file:../gate2-group-server"`
  (and give Gate 2 a proper `exports`/`main` for `createServer`, `openStore`, `makeLiveModelClient`).
- `src/index.ts` imports Gate 2's server building blocks + this project's `PluginRegistry`/`PluginHost`.

## What `index.ts` must do

1. **Boot the backend:** `const store = openStore(process.env.DB_PATH ?? "data/app.sqlite")`,
   `const model = makeLiveModelClient()`, `const server = createServer({ store, model })`.
2. **Real HostCapabilities** for plugins:
   - `net = { fetchText: (url) => fetch(url).then(r => r.text()) }`
   - `room = { history: (roomId, limit) => store.listMessages(roomId, { limit }) }`
   - `exec` — only wire a genuinely sandboxed runner, or omit it (no exec capability granted).
3. **Plugin host:** `const registry = new PluginRegistry()`; load every `./plugins/*/manifest.json`
   via `registry.load(...)`; `const host = new PluginHost({ registry, capabilities })`.
4. **Wire plugins into the message flow:** when a posted message's content starts with `/` (a command),
   call `host.dispatchCommand(roomId, cmd, args, author)` and post each `PluginResult` back into the
   room as a message (authored by a `system`/plugin account) so it renders in-thread; also run
   `host.dispatchMessage` for `on_message` hooks. (Hook this where the Gate 2 server persists+fans-out
   a human message.)
5. **Serve the web client same-origin** (no CORS): `GET /` returns
   `../gate2-group-server/web/index.html`; the client auto-targets its own origin.
6. **Listen:** `server.listen(Number(process.env.PORT ?? 8787))`. (You can use `:55`, but <1024 needs
   privilege — `8787` or `5055` is friendlier.) Ctrl-C → clean close (server + store + plugin
   subprocesses).

## Reference plugins (build at least one)

- `plugins/search/` — `manifest.json` (capabilities `["net"]`, command `/search`) + `plugin.js` that
  uses `ctx.net.fetchText` to hit your local SearXNG/Firecrawl and returns a `PluginResult` (markdown
  list). This is the live demo that proves the whole stack.

## Acceptance (eye-graded — this is the product, not a unit)

- `npm start`, open the URL: register two users (two tabs), create/join a room.
- Add a model agent (endpoint `http://node4090.home.arpa:8080`); `@mention` it → reply streams in,
  rendered the opencode way; the second tab sees it (fan-out).
- `/search <query>` → the plugin runs (isolated subprocess) and its result renders in-thread.
- It looks opencode: `#0a0a0a` ground, amber own-messages, purple agent names, blue mentions, mono.

## Why this is the milestone

It's the first time the gauntlet's pieces are a *product*: transport (G1) + backend/realtime/
multi-agent (G2) + plugins/sandbox (G3) + the opencode client, running together. Gate 4 (iOS) is the
native client onto this exact backend.
