// src/orchestrator.ts — AGENT IMPLEMENTS the locked mention-+-reply policy and the
// turn engine that guarantees termination.
//
// MentionReplyPolicy.selectResponders(ctx):
//   - return the agents @mentioned by ctx.message (match on handle), MINUS the
//     message's own author, and only while ctx.turnBudgetRemaining > 0.
//   - never select the author (no self-trigger); dedupe.
//
// runTurn(origin): a HUMAN message opens a turn with DEFAULT_TURN_BUDGET. For each
// produced agent reply you: decrement the budget, persist + fan out the reply, then
// feed that reply back through the policy (agent replies can @mention other agents)
// drawing down the SAME budget. Model messages never open a new turn. When the budget
// hits 0 or no responders remain, the turn ends — this is the termination guarantee.
import type { SpeakerPolicy, SpeakerContext, AgentAccount, ModelClient, Room } from "./protocol.js";
import type { Message } from "./schema.js";

export class MentionReplyPolicy implements SpeakerPolicy {
  readonly name = "mention-reply";
  selectResponders(_ctx: SpeakerContext): AgentAccount[] {
    throw new Error("NOT IMPLEMENTED: MentionReplyPolicy.selectResponders");
  }
}

/** Parse @handle mentions out of message content. Pure helper the policy uses. */
export function parseMentions(_content: string): string[] {
  throw new Error("NOT IMPLEMENTED: parseMentions");
}

export interface TurnEngineDeps {
  policy: SpeakerPolicy;
  model: ModelClient;
  agentsInRoom(roomId: string): AgentAccount[];
  history(roomId: string): Message[];
  onReply(m: Message): void | Promise<void>; // persist + fan out
  budget?: number;
}

/** Drive responders for a freshly-landed message until the turn budget is exhausted. */
export async function runTurn(_room: Room, _origin: Message, _deps: TurnEngineDeps): Promise<void> {
  throw new Error("NOT IMPLEMENTED: runTurn — Gate 2 turn engine (termination guarantee)");
}
