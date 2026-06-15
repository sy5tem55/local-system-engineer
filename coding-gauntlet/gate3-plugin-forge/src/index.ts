// src/index.ts — AGENT IMPLEMENTS the entry. Mounts the PluginHost onto the Gate 2 server:
// load plugins from ./plugins/*/manifest.json at startup, route "/command" messages through
// dispatchCommand, run dispatchMessage on each posted message, and render plugin results
// in-thread. Provide real HostCapabilities (net = fetch, exec = a sandboxed runner, room =
// the Gate 2 store). `npm start` boots it.
throw new Error("NOT IMPLEMENTED: Gate 3 entry — mount PluginHost on the Gate 2 server. See SPEC.md.");
