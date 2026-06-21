# Faust — Coding Gauntlet (Gates 2–3)

## What this is

Faust is the combined **Gate 2 + Gate 3** of a 4-gate progressive coding challenge (the "Coding Gauntlet"). It builds a realtime group chat server with AI model agents and a capability-sandboxed plugin framework.

- **Gate 2** (`gate2-group-server/`): Multi-room group chat — REST + WebSocket + SQLite + @mention orchestration with turn-budget termination
- **Gate 3** (`src/`): Typed, capability-sandboxed plugin framework on the Gate 2 server. Plugins run in isolated Node 22 `--permission` subprocesses. The host grants only declared capabilities over IPC.

## Quick start

```bash
npm install              # install top-level deps (wires gate2 symlink)
npm test                 # run Gate 3 acceptance + integration tests (11 tests)
npm run test:gate2       # run Gate 2 acceptance tests (8 tests + 1 live skip)
npm run test:all         # both test suites
npm start                # boot the composed server on port 8787
```

Requires **Node.js 22+** (for the `--permission` subprocess model).

## Directory layout

```
Faust/
├── src/                  ← CANONICAL Gate 3 source (edit here)
│   ├── plugin-contract.ts  FROZEN — third-party plugin API (manifest, capabilities, PluginContext)
│   ├── schema.ts            FROZEN — Gate 1 canonical Message/Author (vendored)
│   ├── tokens.ts            FROZEN — opencode design token loader
│   ├── registry.ts          PluginRegistry — runtime load from manifest, lazy subprocess spawn
│   ├── sandbox.ts           buildContext (capability gating) + spawnPlugin (--permission subprocess) + invoke (budget)
│   ├── host.ts              PluginHost — dispatchCommand/dispatchMessage with IPC brokering
│   ├── index.ts             Entry — compose Gate 2 server + PluginHost + plugins + web client
│   └── plugin-runner.js     Subprocess entry — JSON-lines IPC, capability proxies, idle timeout
├── test/
│   ├── acceptance.test.ts          Gate 3 grader (DON'T EDIT) — 9 tests
│   ├── runner-integration.test.ts  E2E integration tests (DON'T EDIT) — 2 tests
│   └── fixtures/                   Third-party test plugins (DON'T EDIT)
│       ├── echo/            Declares [] capabilities, /echo command
│       ├── netfetch/        Declares ["net"], /fetch command
│       ├── sneaky/          Declares [] — probes for ctx.net (must be withheld)
│       ├── escapee/         Declares [] — tries import('node:child_process') (must be blocked by OS)
│       └── runner/          Declares ["exec"], /run command
├── plugins/               ← Reference plugins (edit/build here)
│   ├── search/            /search — SearXNG backend, net capability
│   └── runner/            /run — shell command execution, exec capability
├── web/
│   └── index.html         Gate 3 web client (opencode component kit)
├── design-tokens/
│   └── opencode-tokens.json  FROZEN — shared design tokens (all gates consume this)
├── gate2-group-server/   ← Reference copy of Gate 2 (has own package.json/node_modules for tests)
│   ├── src/               Gate 2 source (server, db, auth, orchestrator, protocol, agents, model_live)
│   ├── test/              Gate 2 acceptance harness (DON'T EDIT)
│   └── web/index.html     Gate 2 web client (reference — Gate 3 client extends this)
├── gate3-plugin-forge/   ← Reference copy of Gate 3 (for independent testing)
├── CLAUDE.md              ← You are here
├── TASKS.md               ← AI-agent-optimized task roadmap
├── package.json           Top-level compose package
└── tsconfig.json          TypeScript config
```

## FROZEN files — DO NOT EDIT

These files are authored and version-locked. Changing them breaks the contract between gates:

- `src/plugin-contract.ts` — the third-party plugin API surface
- `src/schema.ts` — canonical Message/Author types
- `src/tokens.ts` — opencode design token loader + CIE76 color distance
- `test/acceptance.test.ts` — the Gate 3 grader
- `test/runner-integration.test.ts` — the Gate 3 E2E integration tests
- `test/fixtures/*/plugin.js` — genuine third-party test plugins
- `test/fixtures/*/manifest.json` — their manifests
- `design-tokens/opencode-tokens.json` — the visual contract
- `gate2-group-server/src/protocol.ts` — Gate 2 wire contract
- `gate2-group-server/src/schema.ts` — Gate 2 schema (same shape as Gate 3's)
- `gate2-group-server/src/tokens.ts` — Gate 2 token loader
- `gate2-group-server/test/acceptance.test.ts` — Gate 2 grader

## The capability model

Security is **capability-based, declarative, and OS-enforced**:

1. A plugin lists needed capabilities in its manifest: `net | exec | render | read_room | attach`
2. The host grants **only** those the manifest declares AND the host provides — undeclared → `ctx.<cap> === undefined`
3. **Real isolation**: each plugin runs in its own `node --permission` subprocess. Without `--allow-child-process`, `import('node:child_process')` throws `ERR_ACCESS_DENIED` at the OS level. The `escapee` fixture proves this.

### IPC protocol (host ↔ child subprocess)

- **Host → Child** (stdin): `{ type: "invoke", id, hook, event }` | `{ type: "cap_res", id, value/error }`
- **Child → Host** (stdout): `{ type: "hook_result", id, result }` | `{ type: "hook_error", id, error, code }` | `{ type: "cap_req", id, cap, method, args }`

The child never has direct access to host capabilities — it requests them over IPC and the host gates through `buildContext`.

### Turn budget

`invoke()` enforces per-call `budgetMs` (default 5000ms). A plugin that hangs or loops is aborted, never the host. In Gate 2, the turn budget (DEFAULT_TURN_BUDGET = 6) guarantees model↔model chains terminate.

## The opencode aesthetic

All visual output (web client, TUI) follows the **opencode** dark theme:

- **Ground**: `#0a0a0a` (deep black)
- **Primary**: `#fab283` (warm amber — own messages, cursor, links)
- **Accent**: `#9d7cd8` (purple — headings, keywords, agent names)
- **Secondary**: `#5c9cf5` (blue — mentions, selected state)
- **Mono everywhere** — JetBrains Mono / Berkeley Mono / system monospace
- **Panels**: `#141414` background, `#2a2a2a` borders
- Full token set in `design-tokens/opencode-tokens.json`

## Key constraints

1. **Node.js 22+** required for `--permission` model (subprocess isolation)
2. **WSL2 native filesystem** — work on ext4 (`~/projects/Faust/`), NOT on `/mnt/c/`. The /mnt/c mount is 30× slower and breaks binary permissions (esbuild EACCES)
3. **No transpiler in subprocess** — plugins run as plain `.js` so the restricted child doesn't need `tsx`
4. **`findNodeBinary()`** in `sandbox.ts` resolves the current `process.execPath` first (handles nvm/fnm/asdf dynamically), falls back to known nvm paths, then `"node"`
5. **SQLite via sql.js** (pure WASM, no native deps) — database is file-backed, persists across restarts
6. **Password hashing** uses SHA-256 with a per-password random 16-byte salt (acceptable for coding exercise, not production)
7. **Auth tokens** are persisted in SQLite (`tokens` table) — survive server restarts
8. **`invoke()`** clears its timeout in a `finally` block — no timer leak on early resolve
9. **Zone.Identifier files** — Windows NTFS alternate data streams; covered by `.gitignore` but may still appear from `/mnt/c/` copies. Delete with `find . -name '*:Zone.Identifier' -not -path './node_modules/*' -delete`
10. **Room ownership** — rooms track their creator as `ownerId` in the DB. Only the owner can delete a room, clear its messages, delete individual messages, or kick members. The `ownerId` is a DB column only — not part of the frozen `Room` interface in `protocol.ts`.
11. **New broadcast frames** — `room_removed`, `room_cleared`, `message_deleted`, `member_kicked` are sent as plain JSON over WebSocket. They are NOT in the frozen `ServerFrame` union type in `protocol.ts`. The web client handles them as dynamic JSON.

## How to add a new plugin

1. Create `plugins/<name>/manifest.json` with name, version, apiVersion `"g3.1"`, entry, capabilities, commands
2. Create `plugins/<name>/plugin.js` with a default export: `{ async onCommand(e, ctx) { ... } }`
3. The plugin is auto-loaded at startup from `plugins/*/manifest.json`
4. Capability proxies (`ctx.net`, `ctx.exec`, `ctx.room`) are only present if declared in the manifest AND the host provides them — use `ctx.granted.has("net")` to check

## How to add a new test

1. Tests are frozen once authored — they are ground truth. Don't edit to pass; fix implementation.
2. Gate 3 tests go in `test/`. Use `node --import tsx --test` and import from `../src/`.
3. Gate 2 tests go in `gate2-group-server/test/`. Same runner, import from `../src/`.
4. After adding tests, update test counts in this file and `TASKS.md → Current State`.

## Testing philosophy

Each gate has a frozen acceptance harness that is **proven satisfiable** — a correct implementation turns all tests green. The harness is ground truth; don't edit it to pass. Fix the implementation to satisfy the harness.

- Gate 3: 3 authored (green) + 5 agent (green) + 1 isolation (green) + 2 integration (green) = **11 tests, all pass**
- Gate 2: 3 authored (green) + 5 agent (green) + 1 live (skip) = **8 pass, 1 skipped**

Total: **19 pass, 0 fail, 1 skip**
