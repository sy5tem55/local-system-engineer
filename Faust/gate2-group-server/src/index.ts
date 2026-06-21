// src/index.ts — Faust entry point: one running app.
// Group server + multi-agent PLANNING protocol (cue-driven for autonomous WS-client
// agents) + in-tree capability-sandboxed PLUGIN host + web UI, behind one `npm start`.
//   MODEL_API_KEY=<key> ADMIN_HANDLES=sy5,lse AGENT_HANDLES=hermes-agent npx tsx src/index.ts
import { openStore } from "./db.js";
import { makeLiveModelClient } from "./model_live.js";
import { createServer, type RunningServer } from "./server.js";
import { MentionReplyPolicy } from "./orchestrator.js";
import { PlanningController } from "./planning.js";
import { PluginRegistry } from "./registry.js";
import { PluginHost } from "./host.js";
import { AgentSupervisor, type AgentSpec } from "./supervisor.js";
import type { Message } from "./schema.js";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, readFileSync, readdirSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, "..");

const DB_PATH = process.env.DB_PATH ?? join(PROJECT_ROOT, "data", "gate2.sqlite");
const PORT = Number(process.env.PORT ?? 8787);
const PLUGINS_DIR = join(PROJECT_ROOT, "plugins");
const WEB_CLIENT = join(PROJECT_ROOT, "web", "index.html");
const TURN_BUDGET = Number(process.env.TURN_BUDGET ?? 16);
// Human-in-the-loop admins (can /approve, /revise, room admin actions). Promoted
// lazily the first time they post.
const ADMIN_HANDLES = new Set(
  (process.env.ADMIN_HANDLES ?? "sy5").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
);
// Autonomous AI agents authenticate as ordinary (human-kind) accounts and connect as
// WS clients, so they can't be told apart by `kind`. This roster names which connected
// handles are planning participants the server cues for turns.
const AGENT_HANDLES = new Set(
  (process.env.AGENT_HANDLES ?? "hermes,lse").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
);
// Sidecars to supervise as managed children (start with the server, restart on crash,
// stop on shutdown). Opt-in: AGENT_SIDECARS=lse. Specs come from agents.json or a built-in
// default per known name. Secrets (FAUST_KEY) are referenced as ${VAR} from the launch env.
const AGENT_SIDECARS = (process.env.AGENT_SIDECARS ?? "")
  .split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
const DEFAULT_SIDECARS: Record<string, AgentSpec> = {
  lse: {
    name: "lse",
    command: "python3",
    args: ["-u", "lse-sidecar.py"],
    cwd: "../agent-client",
    env: {
      FAUST_BASE: "http://localhost:8787",
      FAUST_HANDLE: "lse",
      FAUST_ROOM: "SY5L4N",
      FAUST_KEY: "${LSE_FAUST_KEY}",
      LSE_MODEL_URL: "http://localhost:8080/v1/chat/completions",
      GOETHE_PATH: "${GOETHE_PATH}",
    },
  },
};

type Broadcast = (roomId: string, frame: unknown) => void;

async function main() {
  const store = openStore(DB_PATH);
  const model = makeLiveModelClient();

  // ── Plugins (capability-sandboxed, in-tree) ──────────────────────────────────
  const registry = new PluginRegistry();
  if (existsSync(PLUGINS_DIR)) {
    for (const name of readdirSync(PLUGINS_DIR)) {
      const manifestPath = join(PLUGINS_DIR, name, "manifest.json");
      if (!existsSync(manifestPath)) continue;
      try {
        await registry.load(manifestPath);
        console.log(`  plugin loaded: ${name}`);
      } catch (e: any) {
        console.warn(`  plugin load failed (${name}): ${e.message}`);
      }
    }
  }
  const host = new PluginHost({
    registry,
    capabilities: {
      net: {
        fetchText: async (url: string): Promise<string> => {
          const r = await fetch(url, { headers: { Accept: "application/json, text/plain, */*" } });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.text();
        },
      },
      room: {
        history: (roomId: string, limit?: number): Message[] => store.listMessages(roomId, { limit }),
      },
      // exec intentionally omitted — no sandboxed runner granted on this host.
    },
    budgetMs: 10_000,
  });

  // ── Multi-agent planning protocol (cue-driven) ───────────────────────────────
  const planning = new PlanningController();
  // Server-called agents (HTTP endpoints) would use PlanningPolicy + runTurn; this
  // deployment's agents are autonomous WS clients, so planning is driven by turn
  // cues in the message path and mention-reply stays the runTurn policy.
  const policy = new MentionReplyPolicy();
  let serverRef: RunningServer;

  // ── Supervised agent sidecars (long-running children, not sandboxed plugins) ──
  const supervisor = new AgentSupervisor(PROJECT_ROOT, join(PROJECT_ROOT, "logs"));
  if (AGENT_SIDECARS.length) {
    let fileSpecs: Record<string, AgentSpec> = {};
    const cfgPath = join(PROJECT_ROOT, process.env.AGENTS_CONFIG ?? "agents.json");
    if (existsSync(cfgPath)) {
      try {
        fileSpecs = JSON.parse(readFileSync(cfgPath, "utf8"));
      } catch (e: any) {
        console.warn(`  agents.json parse failed: ${e.message}`);
      }
    }
    for (const name of AGENT_SIDECARS) {
      const raw = fileSpecs[name] ?? DEFAULT_SIDECARS[name];
      if (!raw || !raw.command) {
        console.warn(`  no sidecar spec for "${name}" — add it to agents.json`);
        continue;
      }
      supervisor.register({ ...raw, name });
    }
  }

  function post(roomId: string, author: Message["author"], role: Message["role"], content: string, broadcast: Broadcast) {
    const msg: Message = {
      id: `${author.id}:${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      room: roomId,
      author,
      role,
      content,
      ts: Date.now(),
    };
    store.appendMessage(msg);
    broadcast(roomId, { type: "message", message: msg });
  }
  // Moderator framing must be role:"assistant" so model agents see it (agents.ts drops system).
  const postModerator = (roomId: string, content: string, b: Broadcast) =>
    post(roomId, { id: "moderator", kind: "model", name: "moderator" }, "assistant", content, b);
  const postPlugin = (roomId: string, content: string, b: Broadcast) =>
    post(roomId, { id: "plugin", kind: "model", name: "plugin" }, "system", content, b);
  const flushNotices = (roomId: string, b: Broadcast) => {
    for (const n of planning.takeNotices(roomId)) postModerator(roomId, n, b);
  };
  const pluginCommands = () =>
    registry.list().flatMap((p) => p.manifest.commands ?? []).join(", ") || "none";

  // Planning participants = connected room members on the AGENT_HANDLES roster, join order.
  const planningParticipants = (roomId: string): string[] => {
    const connected = new Set(serverRef.connectedAccounts(roomId));
    return store
      .listMembers(roomId)
      .filter((m) => connected.has(m.accountId))
      .sort((a, b) => a.joinedAt - b.joinedAt)
      .map((m) => store.getAccount(m.accountId))
      .filter((a): a is NonNullable<typeof a> => !!a && AGENT_HANDLES.has(a.handle))
      .map((a) => a.handle);
  };

  const cueLabel = (roomId: string): string => {
    const st = planning.state(roomId);
    if (!st) return "";
    return planning.phase(roomId) === "planning"
      ? `planning round ${st.round}/${st.maxRounds}`
      : `tasking round ${st.taskingRound}/${st.maxTaskingRounds}`;
  };

  // Drain notices, then cue the next participant (or stop at a phase boundary).
  const pump = (roomId: string, b: Broadcast): void => {
    flushNotices(roomId, b);
    const ph = planning.phase(roomId);
    if (ph !== "planning" && ph !== "tasking") return;
    const next = planning.nextSpeaker(roomId);
    flushNotices(roomId, b); // nextSpeaker may have queued a transition notice
    if (next) {
      postModerator(
        roomId,
        `▶ @${next} — your turn (${cueLabel(roomId)}). Post your contribution. ` +
          `In planning, include [[CONVERGED]] when you agree with the current plan. ` +
          `In tasking, assign work as \`@handle: <task>\` and include [[DONE]] when your assignments are placed.`,
        b,
      );
    }
  };

  // ── Message handler: agent turns + human commands ─────────────────────────────
  async function onMessage(roomId: string, message: Message, broadcast: Broadcast): Promise<void> {
    const handle = message.author.name;

    // 1) Planning turn advancement: a rostered agent posted a contribution.
    if (
      handle &&
      AGENT_HANDLES.has(handle) &&
      planning.isActive(roomId) &&
      message.author.id !== "moderator" &&
      message.author.id !== "plugin" &&
      !message.content.trim().startsWith("/")
    ) {
      const st = planning.state(roomId);
      if (st && st.order.includes(handle)) {
        planning.observe(roomId, message);
        pump(roomId, broadcast);
        return;
      }
    }

    // 2) Human commands.
    if (message.author.kind !== "human") return;
    if (handle && ADMIN_HANDLES.has(handle) && !store.isAdmin(message.author.id)) {
      store.setAdmin(message.author.id, true);
    }
    const content = message.content.trim();
    if (!content.startsWith("/")) return;

    const sp = content.indexOf(" ");
    const command = (sp >= 0 ? content.slice(0, sp) : content).toLowerCase();
    const args = sp >= 0 ? content.slice(sp + 1).trim() : "";

    if (command === "/plan") {
      if (args.toLowerCase() === "stop") {
        planning.reset(roomId);
        postModerator(roomId, "Planning cancelled.", broadcast);
        return;
      }
      if (!args) {
        postModerator(roomId, "Usage: `/plan <objective>` (or `/plan stop`).", broadcast);
        return;
      }
      const order = planningParticipants(roomId);
      if (order.length === 0) {
        postModerator(
          roomId,
          `No agents connected to this room. Have an agent (roster: ${[...AGENT_HANDLES].join(", ") || "none"}) join + subscribe, then \`/plan\` again.`,
          broadcast,
        );
        return;
      }
      planning.startPlanning(roomId, args, order);
      pump(roomId, broadcast); // posts framing + cues the first participant
      return;
    }
    if (command === "/approve" || command === "/revise") {
      if (!store.isAdmin(message.author.id)) {
        postModerator(roomId, `Only an admin can \`${command}\`.`, broadcast);
        return;
      }
      const ok = command === "/approve" ? planning.approve(roomId) : planning.revise(roomId, args);
      if (!ok) {
        postModerator(roomId, `Nothing to ${command.slice(1)} — no plan awaiting approval.`, broadcast);
        return;
      }
      pump(roomId, broadcast); // posts phase framing + cues the first participant
      return;
    }

    if (command === "/agents") {
      const rows = supervisor.status();
      const txt = rows.length
        ? rows
            .map((r) =>
              r.running
                ? `• ${r.name}: up (pid ${r.pid}, ${r.uptimeS}s, ${r.restarts} restarts)`
                : `• ${r.name}: down${r.lastExit ? ` (last code ${(r.lastExit as any).code})` : ""}`,
            )
            .join("\n")
        : "No supervised agents (start with `AGENT_SIDECARS=lse`).";
      postModerator(roomId, `Supervised agents:\n${txt}`, broadcast);
      return;
    }
    if (command === "/agent") {
      if (!store.isAdmin(message.author.id)) {
        postModerator(roomId, "Only an admin can `/agent`.", broadcast);
        return;
      }
      const [name, action] = args.split(/\s+/);
      if (!name || !action || !["restart", "stop", "start"].includes(action)) {
        postModerator(roomId, "Usage: `/agent <name> <start|stop|restart>`.", broadcast);
        return;
      }
      const ok =
        action === "restart"
          ? supervisor.restart(name)
          : action === "stop"
            ? supervisor.stop(name)
            : supervisor.start(name);
      postModerator(
        roomId,
        ok ? `Agent \`${name}\`: ${action} requested.` : `No supervised agent \`${name}\`.`,
        broadcast,
      );
      return;
    }

    // Plugin slash-commands
    const results = await host.dispatchCommand(roomId, command, args, message.author);
    if (results.length > 0) {
      for (const r of results) postPlugin(roomId, r.content, broadcast);
    } else if (!registry.forCommand(command)) {
      postPlugin(
        roomId,
        `Unknown command: \`${command}\`. Try \`/plan <objective>\`, \`/approve\`, \`/revise\`, \`/agents\`, or a plugin command (${pluginCommands()}).`,
        broadcast,
      );
    }
  }

  // Safety net: drain any notices left queued after a turn.
  async function onTurnComplete(roomId: string, broadcast: Broadcast): Promise<void> {
    flushNotices(roomId, broadcast);
  }

  const server = createServer({
    store,
    model,
    policy,
    turnBudget: TURN_BUDGET,
    onMessage,
    onTurnComplete,
    pluginManifests: () =>
      registry.list().map((p) => ({
        name: p.manifest.name,
        version: p.manifest.version,
        apiVersion: p.manifest.apiVersion,
        capabilities: p.manifest.capabilities,
        commands: p.manifest.commands,
        description: p.manifest.description,
      })),
    staticFiles: { "/": WEB_CLIENT },
  });
  serverRef = server;

  const port = await server.listen(PORT);
  console.log(`\n  Faust running at ${server.url()}  (port ${port})`);
  console.log(`  plugins: ${registry.list().length} (${pluginCommands()})`);
  console.log(`  admins: ${[...ADMIN_HANDLES].join(", ") || "(none)"}  |  agents: ${[...AGENT_HANDLES].join(", ") || "(none)"}`);
  console.log(`  planning: /plan <objective> → cues each agent → converge → admin /approve → tasking`);
  if (supervisor.names().length) {
    supervisor.startAll();
    console.log(`  sidecars: supervising ${supervisor.names().join(", ")}`);
  }
  console.log("");

  const shutdown = async (signal: string) => {
    console.log(`\n  ${signal} — shutting down...`);
    await supervisor.stopAll();
    for (const entry of registry.list()) entry._subprocess?.close();
    await server.close();
    store.close();
    process.exit(0);
  };
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main().catch((err) => {
  console.error("Failed to start:", err);
  process.exit(1);
});
