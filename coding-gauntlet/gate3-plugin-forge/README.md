# Gate 3 — The Plugin Forge

Coding Gauntlet, gate 3. A typed, capability-sandboxed **plugin framework** on the Gate 2 server,
plus the full **opencode component kit**. Full challenge contract in [`SPEC.md`](./SPEC.md).

```bash
npm install
npm test     # acceptance harness — authored checks green, agent checks red until built
npm start    # mount the plugin host on the Gate 2 server
```

**Layout**

```
src/plugin-contract.ts  FROZEN — manifest, capabilities, PluginContext (sandbox boundary),
                                 lifecycle hooks, validateManifest (the third-party API)
src/schema.ts           FROZEN — Gate 1 canonical Message/Author (vendored)
src/tokens.ts           FROZEN — opencode token loader
src/registry.ts         agent — runtime plugin load from a manifest (no core change)
src/sandbox.ts          agent — buildContext (capability gating) + invoke (budget)
src/host.ts             agent — dispatchCommand/dispatchMessage into the Gate 2 flow
src/index.ts            agent — mount on the Gate 2 server; `npm start`
plugins/*               agent — 2-3 reference plugins (/search, code-runner, attachment)
web/index.html          agent — full opencode component kit (eye-graded)
test/acceptance.test.ts the grader (don't edit to pass)
test/fixtures/*         authored third-party plugins (echo / netfetch / sneaky)
```

Security is capability-based **and** OS-enforced: a plugin gets **only** what its manifest declares
(the `sneaky` fixture proves an undeclared capability stays withheld), and a plugin that didn't
declare `exec` is **physically unable to spawn** (the `escapee` fixture — graded via Node's
permission model). The contract/capability checks are proven satisfiable by a reference impl; the
isolation check is satisfiable via the verified `node --permission` mechanism. Tokens from
`../design-tokens/opencode-tokens.json`.
