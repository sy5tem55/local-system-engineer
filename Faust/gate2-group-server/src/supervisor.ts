// src/supervisor.ts — supervise long-running agent sidecars as managed children.
//
// Plugins (host.ts) are sandboxed, ephemeral, command→response. Sidecars are the
// opposite: persistent WS-client agents (e.g. the LSE) that hold a socket and call a
// model. This supervisor starts them WITH the server, restarts on crash (exp. backoff),
// and stops them on shutdown — so one `npx tsx src/index.ts` brings up Faust + its agents.
//
// Specs come from agents.json (or a built-in default per known name); env values may
// reference ${VAR}, resolved from the server's own env so secrets (FAUST_KEY) never live
// in the committed config.
import { spawn, type ChildProcess } from "node:child_process";
import { createWriteStream, mkdirSync, type WriteStream } from "node:fs";
import { isAbsolute, join } from "node:path";

export interface AgentSpec {
  name: string;
  command: string;
  args?: string[];
  cwd?: string; // relative to root unless absolute
  env?: Record<string, string>; // values may reference ${VAR} from process.env
}

interface AgentState {
  spec: AgentSpec;
  child?: ChildProcess;
  pid?: number;
  running: boolean;
  stopped: boolean; // explicit stop — suppress auto-restart
  restarts: number;
  startedAt?: number;
  lastExit?: { code: number | null; signal: NodeJS.Signals | null; at: number };
  backoffMs: number;
  timer?: ReturnType<typeof setTimeout>;
  log?: WriteStream;
}

const MIN_BACKOFF = 1000;
const MAX_BACKOFF = 30_000;

function resolveEnv(env: Record<string, string> | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(env ?? {})) {
    out[k] = String(v).replace(/\$\{(\w+)\}/g, (_, name) => process.env[name] ?? "");
  }
  return out;
}

export class AgentSupervisor {
  private agents = new Map<string, AgentState>();
  private shuttingDown = false;

  constructor(
    private root: string,
    private logDir: string,
  ) {}

  register(spec: AgentSpec): void {
    if (this.agents.has(spec.name)) return;
    this.agents.set(spec.name, {
      spec,
      running: false,
      stopped: false,
      restarts: 0,
      backoffMs: MIN_BACKOFF,
    });
  }

  names(): string[] {
    return [...this.agents.keys()];
  }

  start(name: string): boolean {
    const a = this.agents.get(name);
    if (!a || a.running) return false;
    a.stopped = false;
    a.backoffMs = MIN_BACKOFF;
    this.spawnOne(a);
    return true;
  }

  startAll(): void {
    for (const name of this.agents.keys()) this.start(name);
  }

  private spawnOne(a: AgentState): void {
    const { spec } = a;
    const cwd = spec.cwd ? (isAbsolute(spec.cwd) ? spec.cwd : join(this.root, spec.cwd)) : this.root;
    try {
      mkdirSync(this.logDir, { recursive: true });
    } catch {
      /* ignore */
    }
    const logPath = join(this.logDir, `agent-${spec.name}.log`);
    const log = createWriteStream(logPath, { flags: "a" });
    a.log = log;
    log.write(
      `\n=== ${new Date().toISOString()} start: ${spec.command} ${(spec.args ?? []).join(" ")} (cwd ${cwd}) ===\n`,
    );
    const child = spawn(spec.command, spec.args ?? [], {
      cwd,
      env: { ...process.env, ...resolveEnv(spec.env) },
      stdio: ["ignore", "pipe", "pipe"],
    });
    a.child = child;
    a.pid = child.pid;
    a.running = true;
    a.startedAt = Date.now();
    child.stdout?.pipe(log, { end: false });
    child.stderr?.pipe(log, { end: false });
    console.log(`  agent up: ${spec.name} (pid ${child.pid}) -> ${logPath}`);

    child.on("error", (err) => {
      log.write(`=== spawn error: ${err.message} ===\n`);
      console.warn(`  agent error: ${spec.name}: ${err.message}`);
    });
    child.on("exit", (code, signal) => {
      a.running = false;
      a.lastExit = { code, signal, at: Date.now() };
      a.child = undefined;
      a.pid = undefined;
      log.write(`=== exit code=${code} signal=${signal} at ${new Date().toISOString()} ===\n`);
      if (this.shuttingDown || a.stopped) {
        log.end();
        return;
      }
      // Crash → restart with backoff. If it had been up >60s, treat as healthy: reset.
      const ranMs = a.startedAt ? Date.now() - a.startedAt : 0;
      if (ranMs > 60_000) a.backoffMs = MIN_BACKOFF;
      const delay = a.backoffMs;
      a.backoffMs = Math.min(a.backoffMs * 2, MAX_BACKOFF);
      a.restarts++;
      console.warn(`  agent down: ${spec.name} (code ${code}) — restart in ${delay}ms (#${a.restarts})`);
      a.timer = setTimeout(() => {
        if (!this.shuttingDown && !a.stopped) this.spawnOne(a);
      }, delay);
    });
  }

  restart(name: string): boolean {
    const a = this.agents.get(name);
    if (!a) return false;
    a.stopped = false;
    a.backoffMs = MIN_BACKOFF;
    if (a.timer) clearTimeout(a.timer);
    if (a.child) {
      a.child.kill("SIGTERM"); // exit handler respawns
      return true;
    }
    this.spawnOne(a);
    return true;
  }

  stop(name: string): boolean {
    const a = this.agents.get(name);
    if (!a) return false;
    a.stopped = true;
    if (a.timer) clearTimeout(a.timer);
    const child = a.child;
    if (!child) {
      a.running = false;
      return true;
    }
    child.kill("SIGTERM");
    setTimeout(() => {
      if (a.child && !a.child.killed) a.child.kill("SIGKILL");
    }, 5000);
    return true;
  }

  async stopAll(): Promise<void> {
    this.shuttingDown = true;
    for (const a of this.agents.values()) {
      if (a.timer) clearTimeout(a.timer);
      a.child?.kill("SIGTERM");
    }
    await new Promise((r) => setTimeout(r, 800));
    for (const a of this.agents.values()) {
      if (a.child && !a.child.killed) a.child.kill("SIGKILL");
      a.log?.end();
    }
  }

  status(): Array<Record<string, unknown>> {
    return [...this.agents.values()].map((a) => ({
      name: a.spec.name,
      running: a.running,
      pid: a.pid ?? null,
      restarts: a.restarts,
      uptimeS: a.running && a.startedAt ? Math.round((Date.now() - a.startedAt) / 1000) : 0,
      lastExit: a.lastExit ? { code: a.lastExit.code, signal: a.lastExit.signal } : null,
    }));
  }
}
