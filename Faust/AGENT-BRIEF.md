# Gate 3 — Agent Kickoff Brief

Native-fs setup first (same as Gates 1–2 — the agent can't write `/mnt/c`, and ext4 avoids the
30s-install / slow-fs traps):

```bash
# you, once, in WSL2 bash:
mkdir -p ~/cg3 && cp -r /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/coding-gauntlet/{gate3-plugin-forge,design-tokens} ~/cg3/
cd ~/cg3/gate3-plugin-forge && rm -rf node_modules && npm install
```

Then paste:

---

TASK: Coding Gauntlet — Gate 3 (The Plugin Forge). Make the acceptance harness green.

ENVIRONMENT (read first):
- Working dir: /home/sy5/cg3/gate3-plugin-forge — cd there. Native Linux fs: write files directly
  with execute_command (shell redirects work, no delegation). Do NOT write to or `find` /mnt/c.
- Dependencies are already installed. Do NOT run `npm install`. Just run `npm test`.
- Keep each command under ~30s; split long ones into separate execute_command calls.

START: cd /home/sy5/cg3/gate3-plugin-forge && cat SPEC.md && npm test
SPEC.md is the contract; the harness in test/ is ground truth (proven satisfiable — a correct impl
turns all 8 green). Do NOT edit the harness, the fixtures, or any FROZEN file: src/plugin-contract.ts,
src/schema.ts, src/tokens.ts, ../design-tokens. Current state: 3 authored pass, 5 [agent] fail.

IMPLEMENT (stubs throw NOT IMPLEMENTED; see SPEC.md §What you build). Order:
1. src/registry.ts — PluginRegistry.load(manifestPath): read+validateManifest, dynamically import
   manifest.entry's default export (resolve relative to the manifest dir; pathToFileURL for the
   import), register under name + commands. list / forCommand / unload. Runtime load, ZERO core changes.
2. src/sandbox.ts — buildContext(manifest, host): expose ONLY capabilities the manifest declares AND
   the host provides (undeclared => ctx.<cap> === undefined). invoke(fn, budgetMs): run a hook under
   a give-up budget (Promise.race with a timeout); never let a plugin hang the host.
3. src/host.ts — PluginHost{ dispatchCommand, dispatchMessage }: route /cmd to forCommand's plugin,
   run onMessage across all; each call gets buildContext(...) + the budget; return PluginResult[].
4. src/index.ts — mount on the Gate 2 server, load ./plugins/*/manifest.json at startup, render
   results in-thread (Gate 1 renderer), provide REAL HostCapabilities (net=fetch, exec=sandboxed
   runner, room=Gate 2 store).
5. plugins/* — 2-3 reference plugins (/search using net, a code-runner using exec, an attachment
   handler). web/index.html — the full opencode component kit.

SANDBOX — REAL ISOLATION IS GRADED (not just the field). The `escapee` fixture declares NO
capabilities and tries `import('node:child_process')` + spawn; the harness asserts it RUNS but is
BLOCKED. Contract gating alone (ctx.exec undefined) does NOT pass this — a direct import bypasses it.
Use a real mechanism:
  - RECOMMENDED: per-plugin SUBPROCESS via Node's permission model (Node 22): spawn
    `node --permission [--allow-* per declared capability] runner.js`; without --allow-child-process,
    child_process throws ERR_ACCESS_DENIED. Broker granted capabilities back over IPC. Plugins run as
    plain .js in the restricted child (fixtures are .js) so no transpiler is needed there.
  - OR a `vm` realm whose dynamic-import hook denies `node:` builtins unless granted.
  - NOT worker_threads alone — a worker can still import child_process; it does NOT isolate built-ins.

LOOP: implement one module -> npm test -> read the failing assertion -> fix. Budget: ~6 tries per
module, then report the blocker. Don't edit the harness or fixtures.

DONE: npm test all green offline (6 [agent] checks, incl. the ISOLATION test). REPORT the actual
summary verbatim. Then demonstrate a reference plugin (/search) and the web kit by eye.

---

## What you (Joe) verify after it claims green

1. **Integrity diff** (it must not weaken the grader or contract):
   ```bash
   cd ~/cg3/gate3-plugin-forge
   REPO=/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/coding-gauntlet
   for f in test/acceptance.test.ts src/plugin-contract.ts src/schema.ts src/tokens.ts \
            test/fixtures/echo/plugin.ts test/fixtures/netfetch/plugin.ts test/fixtures/sneaky/plugin.ts; do
     diff -q "$f" "$REPO/gate3-plugin-forge/$f" >/dev/null && echo "UNCHANGED  $f" || echo "MODIFIED   $f  <-- investigate"
   done
   ```
2. **The sandbox is the thing to eyeball** — confirm the agent enforced isolation, not just the
   capability fields. Ask it which isolation mechanism it used (worker_threads / vm / subprocess) and
   sanity-check a no-`exec` plugin genuinely can't run a command.
3. **Copy back + commit** once green and verified:
   `cp -r ~/cg3/gate3-plugin-forge/src/* "$REPO/gate3-plugin-forge/src/"` (plus `plugins/` and `web/`).
