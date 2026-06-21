# Gate 3 — The Plugin Forge (challenge spec)

> Coding Gauntlet, gate 3 of 4. Makes the system **extensible** and finishes the **design system**
> — the web dress-rehearsal for iOS. Builds on Gate 2's server; reuses Gate 1's schema + tokens.
> The LSE agent implements the stubbed modules until `npm test` is all-green. Same ground-truth
> discipline; a gate passes only on demonstrated behavior.

## Goal

A **typed, capability-sandboxed plugin framework** on the Gate 2 server — third parties can ship a
plugin against a documented contract alone, agents invoke plugin capabilities mid-conversation and
the result renders in-thread — plus a **polished reference web client** implementing the *complete*
opencode component kit (panels, borders, diff, markdown, syntax) that the iOS app will mirror.

## Stack (locked)

TypeScript. The plugin contract is a **versioned TS interface** (`src/plugin-contract.ts`, frozen).
Execution isolation (worker_threads / `vm` / subprocess) is the **Gate-3 sandbox decision** — yours
to make (see below). Reference web client built out in Gate 2's web framework to a real component kit.

## What's authored vs. what you build

**Authored & FROZEN (do not edit):**
- `src/plugin-contract.ts` — `PluginManifest`, `Capability`, the capability-scoped `PluginContext`
  (the sandbox boundary), the `Plugin` lifecycle (`onMessage` / `onCommand`), `PluginResult`, and
  `validateManifest`. **This is the third-party API and the surface Gate 4 carries to iOS.**
- `src/schema.ts`, `src/tokens.ts` — the Gate 1 frozen contracts (vendored).
- `test/acceptance.test.ts` + `test/fixtures/*` — the grader, and three **fixture plugins** that
  import only the contract (genuine third-party stand-ins: `echo`, `netfetch`, `sneaky`).

**You implement (stubs throw `NOT IMPLEMENTED`):**

| Module | Export | Contract |
|---|---|---|
| `src/registry.ts` | `class PluginRegistry { load, list, forCommand, unload }` | `load(manifestPath)`: read+`validateManifest`, dynamically import `manifest.entry`'s default export, register under name + commands. **Runtime load, zero core changes** — a new plugin is just a manifest + module on disk. |
| `src/sandbox.ts` | `buildContext(manifest, host, opts?)`, `invoke(fn, budgetMs)` | `buildContext` exposes **only** the capabilities the manifest declares *and* the host provides — an undeclared capability is **absent** (`ctx.net === undefined`). `invoke` runs a hook under a give-up budget; never lets a plugin hang the host. |
| `src/host.ts` | `class PluginHost { dispatchCommand, dispatchMessage }` | DI'd with `{ registry, capabilities, budgetMs? }`. `dispatchCommand` routes `/cmd args` to the registering plugin; `dispatchMessage` runs every plugin's `onMessage`. Each invocation gets a capability-scoped context + budget; returns `PluginResult[]` to render in-thread. |
| `src/index.ts` | entry | `npm start`: mount `PluginHost` on the Gate 2 server, load `./plugins/*/manifest.json` at startup, route `/command` messages, render results in-thread with Gate 1's renderer, provide **real** `HostCapabilities` (net = fetch, exec = a sandboxed runner, room = the Gate 2 store). |
| `plugins/*` | 2–3 reference plugins | e.g. `/search` (net), a code-runner (exec), an attachment/image handler. Manually/eye-graded — they prove the contract is usable by real plugins. |
| `web/index.html` | component kit | The full opencode kit (panels/borders/diff/markdown/syntax). Eye + token-fidelity graded, like Gate 1's TUI. |

## The capability model (the heart of the gate)

Security is **capability-based and declarative**: a plugin lists the `Capability`s it needs in its
manifest (`net | exec | render | read_room | attach`); the host grants **only those**, by
constructing a `PluginContext` where ungranted capability fields are simply absent. *No grant ⇒ no
API.* The `sneaky` fixture declares **nothing** yet probes for `ctx.net` while the host **possesses**
net — the harness asserts it's withheld (a leak there is a sandbox breach).

**Sandbox decision (yours) — and real isolation IS graded.** Contract gating only hides the
capability *field*; a hostile module can still `import('node:child_process')` and run a command. The
harness now grades the real property: a plugin that didn't declare `exec` must be **physically unable
to spawn** (the `escapee` fixture proves it). Pick a real mechanism:
- **Node permission model (recommended; Node 22, which LUCIFER has):** run each plugin in its own
  subprocess with `node --permission` and only the `--allow-*` flags its manifest declares — no
  `--allow-child-process` ⇒ `child_process` throws `ERR_ACCESS_DENIED`. Broker granted capabilities
  (net/exec/room) back to the host over IPC. (Verified: `--permission` blocks `child_process`,
  `--allow-child-process` restores it — so it's grantable per capability.) Run plugins as plain `.js`
  in the restricted child (the fixtures are `.js`) so the child needs no transpiler.
- **`vm` realm:** load plugin source into a `vm` context whose dynamic-import hook denies `node:`
  builtins unless granted — in-process, no subprocess.
- **NOT `worker_threads` alone** — a worker can still `import('node:child_process')`; it isolates
  scope/globals, not built-ins. Don't ship that as "sandboxed."

## Give-up budget

`invoke` enforces a per-call `budgetMs` (default 5000) — a plugin that hangs or loops is aborted,
never the host. House rule: every loop has a ceiling.

## Acceptance (each is a runnable check in `npm test`)

| PYRAMID criterion | Check | Starts |
|---|---|---|
| manifest contract is sound | `[authored] manifest validation…` | green |
| frozen API version pinned | `[authored] frozen contract exposes the API version` | green |
| runs with one command | `[authored] runs with one command` | green |
| **load a plugin from a manifest at runtime** (no core change) | `[agent] registry loads a third-party plugin…` | **red** |
| **an agent invokes a capability, result renders in-thread** | `[agent] an invoked plugin command renders…` | **red** |
| a granted capability is delivered | `[agent] a GRANTED capability is delivered…` | **red** |
| **capability sandbox holds** (undeclared = withheld even when host has it) | `[agent] sandbox: an UNDECLARED capability is withheld…` | **red** |
| capability gating unit | `[agent] buildContext gates capabilities directly` | **red** |
| **real isolation: a no-`exec` plugin physically cannot spawn** | `[agent] sandbox ISOLATION: a plugin without exec cannot run a command` | **red** |

**Definition of done:** `npm test` all-green offline (authored + the **six** agent checks, incl. real
isolation). The
reference plugins (`/search`, code-runner) and the web component kit are verified by running them and
by an eye/token-fidelity check (the harness can't judge "looks opencode" or a real network call).

> The harness is **proven satisfiable** — a correct registry/sandbox/host turns all 8 green
> (verified). A third party writing only against `plugin-contract.ts` (the fixtures do exactly this)
> must load and run with no core changes; that's the extensibility bar.

## Run

```bash
npm install
npm test                 # authored green, agent red until built
npm start                # mount on the Gate 2 server
```

## Feeds the pinnacle

Hands Gate 4 the two things it carries onto iOS: the **plugin framework** (the versioned contract +
capability sandbox) and the **finished, validated opencode design system**.
