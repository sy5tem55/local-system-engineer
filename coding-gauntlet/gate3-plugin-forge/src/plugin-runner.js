// src/plugin-runner.js — Subprocess entry point for plugin sandbox.
// Run via: node --permission --allow-fs-read=<dirs> plugin-runner.js <plugin_path> <granted_caps_json>
// IPC protocol (JSON lines on stdin/stdout):
//   Host → Child (stdin):
//     { type: "invoke", id: N, hook: "onCommand"|"onMessage", event: {...} }
//     { type: "cap_res", id: N, value: {...} }          — capability response
//     { type: "cap_res", id: N, error: "..." }          — capability error
//   Child → Host (stdout):
//     { type: "hook_result", id: N, result: {...} }
//     { type: "hook_error",  id: N, error: "...", code: "..." }
//     { type: "cap_req", id: N, cap: "net"|"exec"|"room", method: "...", args: [...] }
//     { type: "log", msg: "..." }

const PLUGIN_PATH = process.argv[2];
const GRANTED_CAPS = JSON.parse(process.argv[3] || "[]");

// Import the plugin module (ESM default export)
const mod = await import(PLUGIN_PATH);
const plugin = mod.default;

let nextId = 1;
const pendingCaps = new Map(); // id -> { resolve, reject }

// ── Build context with capability proxies ─────────────────────────────────────
const ctx = {
  granted: new Set(GRANTED_CAPS),
  log: (msg) => {
    process.stdout.write(JSON.stringify({ type: "log", msg }) + "\n");
  },
};

if (GRANTED_CAPS.includes("net")) {
  ctx.net = {
    async fetchText(url) {
      const id = nextId++;
      process.stdout.write(
        JSON.stringify({ type: "cap_req", id, cap: "net", method: "fetchText", args: [url] }) + "\n"
      );
      return new Promise((resolve, reject) => pendingCaps.set(id, { resolve, reject }));
    },
  };
}

if (GRANTED_CAPS.includes("exec")) {
  ctx.exec = {
    async run(cmd, args) {
      const id = nextId++;
      process.stdout.write(
        JSON.stringify({ type: "cap_req", id, cap: "exec", method: "run", args: [cmd, args] }) + "\n"
      );
      return new Promise((resolve, reject) => pendingCaps.set(id, { resolve, reject }));
    },
  };
}

if (GRANTED_CAPS.includes("read_room")) {
  ctx.room = {
    async history(roomId, limit) {
      const id = nextId++;
      process.stdout.write(
        JSON.stringify({
          type: "cap_req",
          id,
          cap: "room",
          method: "history",
          args: [roomId, limit],
        }) + "\n"
      );
      return new Promise((resolve, reject) => pendingCaps.set(id, { resolve, reject }));
    },
  };
}

// ── Idle timeout — self-terminate after inactivity to prevent test runner hangs ──
const IDLE_TIMEOUT_MS = 2000;
let idleTimer = setTimeout(() => process.exit(0), IDLE_TIMEOUT_MS);

function resetIdleTimer() {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => process.exit(0), IDLE_TIMEOUT_MS);
}

// ── Non-blocking stdin processing ─────────────────────────────────────────────
// cap_res messages resolve pending capability promises immediately (inline).
// invoke messages are queued and processed sequentially.

const invokeQueue = [];
let processingInvoke = false;

function drainInvokes() {
  if (processingInvoke) return;
  processingInvoke = true;
  (async () => {
    while (invokeQueue.length > 0) {
      await processInvoke(invokeQueue.shift());
    }
    processingInvoke = false;
    resetIdleTimer(); // reset after processing all queued invokes
  })();
}

async function processInvoke(msg) {
  let result;
  try {
    if (msg.hook === "onCommand" && typeof plugin.onCommand === "function") {
      result = await plugin.onCommand(msg.event, ctx);
    } else if (msg.hook === "onMessage" && typeof plugin.onMessage === "function") {
      result = await plugin.onMessage(msg.event, ctx);
    }
    process.stdout.write(JSON.stringify({ type: "hook_result", id: msg.id, result }) + "\n");
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ type: "hook_error", id: msg.id, error: e.message, code: e.code }) + "\n"
    );
  }
}

function resolveCapResponse(msg) {
  const p = pendingCaps.get(msg.id);
  if (p) {
    pendingCaps.delete(msg.id);
    if (msg.error) {
      p.reject(new Error(msg.error));
    } else {
      p.resolve(msg.value);
    }
  }
}

// Raw stdin data listener
let stdinBuffer = "";
process.stdin.on("data", (chunk) => {
  resetIdleTimer(); // reset on any activity
  stdinBuffer += chunk.toString();
  let newlineIdx;
  while ((newlineIdx = stdinBuffer.indexOf("\n")) !== -1) {
    const line = stdinBuffer.slice(0, newlineIdx).trim();
    stdinBuffer = stdinBuffer.slice(newlineIdx + 1);
    if (!line) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      continue;
    }

    if (msg.type === "cap_res") {
      // Resolve immediately — unblocks the awaiting plugin
      resolveCapResponse(msg);
    } else if (msg.type === "invoke") {
      // Queue for sequential processing
      invokeQueue.push(msg);
      drainInvokes();
    }
  }
});

// Exit cleanly on parent close
process.stdin.on("end", () => {
  clearTimeout(idleTimer);
  setTimeout(() => process.exit(0), 100);
});
