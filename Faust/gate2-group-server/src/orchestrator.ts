// src/orchestrator.ts — Mention-reply policy and turn engine
import type { SpeakerPolicy, SpeakerContext, AgentAccount, ModelClient, Room } from "./protocol.js";
import type { Message } from "./schema.js";
import { DEFAULT_TURN_BUDGET } from "./protocol.js";
import { generateAgentReply } from "./agents.js";

export class MentionReplyPolicy implements SpeakerPolicy {
  readonly name = "mention-reply";

  selectResponders(ctx: SpeakerContext): AgentAccount[] {
    // Budget exhausted — no responders
    if (ctx.turnBudgetRemaining <= 0) return [];

    // Parse mentions from the message content
    const mentions = parseMentions(ctx.message.content);

    // Filter: only agents in the room that are mentioned, excluding the message author
    return ctx.agents.filter(agent => {
      // Never select the author
      if (agent.id === ctx.message.author.id) return false;
      // Must be mentioned by handle
      return mentions.includes(agent.handle);
    });
  }
}

/** Parse @handle mentions out of message content. */
export function parseMentions(content: string): string[] {
  const matches = content.match(/@(\w+)/g);
  if (!matches) return [];
  // Deduplicate
  const handles = new Set<string>();
  for (const m of matches) {
    handles.add(m.slice(1)); // remove @
  }
  return [...handles];
}

export interface TurnEngineDeps {
  policy: SpeakerPolicy;
  model: ModelClient;
  agentsInRoom(roomId: string): AgentAccount[];
  history(roomId: string): Message[];
  onReply(m: Message): void | Promise<void>;
  budget?: number;
}

/** Drive responders for a freshly-landed message until the turn budget is exhausted. */
export async function runTurn(room: Room, origin: Message, deps: TurnEngineDeps): Promise<void> {
  // Only human messages open a turn
  if (origin.author.kind !== "human") return;

  let budget = deps.budget ?? DEFAULT_TURN_BUDGET;
  const policy = deps.policy;

  // Process the origin message
  await processMessage(room, origin, deps, policy, budget);
}

async function processMessage(
  room: Room,
  message: Message,
  deps: TurnEngineDeps,
  policy: SpeakerPolicy,
  budget: number,
): Promise<number> {
  let remaining = budget;

  // Get current agents in the room
  const agents = deps.agentsInRoom(room.id);
  const history = deps.history(room.id);

  // Build speaker context
  const ctx: SpeakerContext = {
    room,
    message,
    agents,
    turnBudgetRemaining: remaining,
  };

  // Get responders from policy
  const responders = policy.selectResponders(ctx);

  // Each responder generates a reply
  for (const agent of responders) {
    if (remaining <= 0) break;

    // Generate agent reply
    const signal = new AbortController().signal;
    const reply = await generateAgentReply(agent, room.id, history, deps.model, signal);

    // Persist and fan out the reply
    await deps.onReply(reply);

    // Decrement budget
    remaining--;

    // Recursively process the reply (agent replies can @mention other agents)
    remaining = await processMessage(room, reply, deps, policy, remaining);
  }

  return remaining;
}
