// src/planning.ts — Multi-agent planning protocol (LSE 1.7.0-b, Faust).
//
// A stateful director that runs a room through:
//   PLANNING (round-robin proposals, ≤maxRounds, agents vote [[CONVERGED]])
//     → AWAITING_APPROVAL (human admin /approve or /revise)
//     → TASKING (agents assign each other work via `@handle: <task>`, emit [[DONE]])
//     → IDLE (assignment ledger posted; normal mention-reply resumes)
//
// Implemented as an additive SpeakerPolicy + a controller holding per-room state.
// MentionReplyPolicy is untouched and remains the default; PlanningPolicy delegates
// to it when a room is IDLE. Termination is guaranteed by the phase logic (consensus
// or round caps), with the recursion budget as a backstop. See
// docs/lse-1.7.0-b-faust-planning-design.md.
import type { SpeakerPolicy, SpeakerContext, AgentAccount } from "./protocol.js";
import type { Message } from "./schema.js";

export const CONVERGED_TOKEN = "[[CONVERGED]]";
export const DONE_TOKEN = "[[DONE]]";

export type PlanPhase = "idle" | "planning" | "awaiting_approval" | "tasking";

export interface Assignment {
  from: string; // author handle
  to: string; // assignee handle
  task: string; // assignment text
}

export interface PlanState {
  phase: PlanPhase;
  objective: string;
  order: string[]; // agent handles, round-robin order
  round: number; // 1-based planning round
  maxRounds: number;
  taskingRound: number; // 1-based tasking round
  maxTaskingRounds: number;
  spokenThisRound: Set<string>; // handles that have spoken in the current round
  votesThisRound: Set<string>; // handles that emitted the phase vote token this round
  assignments: Assignment[];
}

export interface PlanningOptions {
  maxRounds?: number; // planning rounds cap (default 5)
  maxTaskingRounds?: number; // tasking rounds cap (default 3)
}

/** Parse `@handle: task` assignments out of a message body. */
export function parseAssignments(from: string, content: string): Assignment[] {
  const out: Assignment[] = [];
  // @handle: <task up to newline or next @handle:>
  const re = /@([\w-]+)\s*:\s*([^\n]+?)(?=(?:\s+@[\w-]+\s*:)|$)/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    const to = m[1];
    const task = m[2].trim();
    if (to && task) out.push({ from, to, task });
  }
  return out;
}

/**
 * Per-room planning state machine. Pure transitions; emits queued moderator
 * notices that the server drains and posts (as role:"assistant" so agents see them).
 */
export class PlanningController {
  #rooms = new Map<string, PlanState>();
  #notices = new Map<string, string[]>();

  phase(roomId: string): PlanPhase {
    return this.#rooms.get(roomId)?.phase ?? "idle";
  }

  state(roomId: string): PlanState | undefined {
    return this.#rooms.get(roomId);
  }

  isActive(roomId: string): boolean {
    return this.phase(roomId) !== "idle";
  }

  #queue(roomId: string, msg: string): void {
    const arr = this.#notices.get(roomId) ?? [];
    arr.push(msg);
    this.#notices.set(roomId, arr);
  }

  /** Drain queued moderator notices for a room (server posts them in order). */
  takeNotices(roomId: string): string[] {
    const arr = this.#notices.get(roomId) ?? [];
    this.#notices.set(roomId, []);
    return arr;
  }

  /** Begin a planning session. `order` is the round-robin speaking order (agent handles). */
  startPlanning(roomId: string, objective: string, order: string[], opts: PlanningOptions = {}): PlanState {
    const st: PlanState = {
      phase: "planning",
      objective: objective.trim(),
      order: [...order],
      round: 1,
      maxRounds: opts.maxRounds ?? 5,
      taskingRound: 1,
      maxTaskingRounds: opts.maxTaskingRounds ?? 3,
      spokenThisRound: new Set(),
      votesThisRound: new Set(),
      assignments: [],
    };
    this.#rooms.set(roomId, st);
    this.#queue(
      roomId,
      `**PLANNING PHASE** — Objective: ${st.objective}\n` +
        `Each agent: propose or refine the plan in ≤120 words, building on prior points. ` +
        `When you fully agree with the current plan, include the token ${CONVERGED_TOKEN} in your message. ` +
        `Planning ends when all agents converge in a round, or after ${st.maxRounds} rounds — then a human admin approves.\n` +
        `Speaking order: ${st.order.join(" → ") || "(no agents in room)"}.`,
    );
    return st;
  }

  /**
   * Record a just-landed message. No-op unless mid planning/tasking and the author
   * is an agent in the round-robin order. Captures the phase vote token and (in
   * tasking) any `@handle:` assignments.
   */
  observe(roomId: string, message: Message): void {
    const st = this.#rooms.get(roomId);
    if (!st) return;
    if (st.phase !== "planning" && st.phase !== "tasking") return;
    const handle = message.author.name;
    if (!handle || !st.order.includes(handle)) return; // not an ordered agent (e.g. human/moderator)
    if (message.author.id === "moderator" || message.author.id === "plugin") return;

    st.spokenThisRound.add(handle);
    if (st.phase === "planning") {
      if (message.content.includes(CONVERGED_TOKEN)) st.votesThisRound.add(handle);
    } else {
      // tasking
      if (message.content.includes(DONE_TOKEN)) st.votesThisRound.add(handle);
      const cleaned = message.content.split(DONE_TOKEN).join("").trim();
      st.assignments.push(...parseAssignments(handle, cleaned));
    }
  }

  /**
   * Round-robin: return the next agent handle to speak, or null at a phase boundary
   * (consensus / cap), transitioning the phase and queueing the moderator notice.
   */
  nextSpeaker(roomId: string): string | null {
    const st = this.#rooms.get(roomId);
    if (!st) return null;
    if (st.phase !== "planning" && st.phase !== "tasking") return null;
    if (st.order.length === 0) return null;

    const next = st.order.find((h) => !st.spokenThisRound.has(h));
    if (next) return next;

    // Round complete — evaluate the boundary.
    const allVoted = st.order.every((h) => st.votesThisRound.has(h));

    if (st.phase === "planning") {
      if (allVoted) {
        st.phase = "awaiting_approval";
        this.#queue(
          roomId,
          `**PLAN CONVERGED** (round ${st.round}/${st.maxRounds}) — all agents voted ${CONVERGED_TOKEN}. ` +
            `Admin: \`/approve\` to begin tasking, or \`/revise <note>\` to continue planning.`,
        );
        return null;
      }
      if (st.round >= st.maxRounds) {
        st.phase = "awaiting_approval";
        this.#queue(
          roomId,
          `**PLANNING CAP REACHED** (${st.maxRounds} rounds, no full consensus). ` +
            `Admin: \`/approve\` to begin tasking anyway, or \`/revise <note>\` to continue planning.`,
        );
        return null;
      }
      st.round += 1;
      st.spokenThisRound.clear();
      st.votesThisRound.clear();
      return st.order[0];
    }

    // tasking
    if (allVoted || st.taskingRound >= st.maxTaskingRounds) {
      st.phase = "idle";
      this.#queue(roomId, this.#ledgerNotice(st));
      return null;
    }
    st.taskingRound += 1;
    st.spokenThisRound.clear();
    st.votesThisRound.clear();
    return st.order[0];
  }

  /** Human admin approves the converged plan → start tasking. Returns false if not awaiting. */
  approve(roomId: string): boolean {
    const st = this.#rooms.get(roomId);
    if (!st || st.phase !== "awaiting_approval") return false;
    st.phase = "tasking";
    st.taskingRound = 1;
    st.spokenThisRound.clear();
    st.votesThisRound.clear();
    this.#queue(
      roomId,
      `**TASKING PHASE** — Plan approved. Agents: assign concrete working tasks to each other ` +
        `using \`@handle: <task>\`. Emit ${DONE_TOKEN} once your assignments are placed. ` +
        `(≤${st.maxTaskingRounds} rounds)`,
    );
    return true;
  }

  /** Human admin requests revision → resume planning with a fresh round window. */
  revise(roomId: string, note = ""): boolean {
    const st = this.#rooms.get(roomId);
    if (!st || st.phase !== "awaiting_approval") return false;
    st.phase = "planning";
    st.round = 1;
    st.spokenThisRound.clear();
    st.votesThisRound.clear();
    this.#queue(
      roomId,
      `**REVISION REQUESTED**${note ? ` — ${note.trim()}` : ""}\n` +
        `Resuming PLANNING (round reset). Vote ${CONVERGED_TOKEN} when you agree with the revised plan.`,
    );
    return true;
  }

  /** Abandon any planning state for a room (e.g. /plan stop). */
  reset(roomId: string): void {
    this.#rooms.delete(roomId);
    this.#notices.delete(roomId);
  }

  #ledgerNotice(st: PlanState): string {
    if (st.assignments.length === 0) {
      return `**TASKING COMPLETE** — no \`@handle: <task>\` assignments were captured. Normal chat resumes.`;
    }
    const lines = st.assignments.map((a) => `- ${a.from} → @${a.to}: ${a.task}`);
    return `**TASKING COMPLETE** — assignment ledger:\n${lines.join("\n")}`;
  }
}

/**
 * Director SpeakerPolicy: drives round-robin planning/tasking via the controller,
 * and delegates to a fallback (mention-reply) when the room is IDLE so normal chat
 * is unchanged. State lives in the controller — this is a thin selector over it.
 */
export class PlanningPolicy implements SpeakerPolicy {
  readonly name = "planning";
  #controller: PlanningController;
  #fallback: SpeakerPolicy;

  constructor(controller: PlanningController, fallback: SpeakerPolicy) {
    this.#controller = controller;
    this.#fallback = fallback;
  }

  selectResponders(ctx: SpeakerContext): AgentAccount[] {
    if (ctx.turnBudgetRemaining <= 0) return [];

    const phase = this.#controller.phase(ctx.room.id);
    if (phase === "idle") return this.#fallback.selectResponders(ctx);
    if (phase === "awaiting_approval") return [];

    // planning | tasking: record the landed message, then pick the next speaker.
    this.#controller.observe(ctx.room.id, ctx.message);
    const handle = this.#controller.nextSpeaker(ctx.room.id);
    if (!handle) return [];
    const agent = ctx.agents.find((a) => a.handle === handle);
    return agent ? [agent] : [];
  }
}
