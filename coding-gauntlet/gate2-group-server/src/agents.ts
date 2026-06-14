// src/agents.ts — AGENT IMPLEMENTS. Turn an AgentAccount + room history into a reply
// Message by calling the ModelClient. Build the messages array from history (map each
// stored Message to {role, content}; prepend the agent persona as a system message),
// call model.complete(), wrap the text in a canonical assistant Message authored by
// the agent account. Honour an AbortSignal for the give-up budget.
import type { AgentAccount, ModelClient } from "./protocol.js";
import type { Message } from "./schema.js";

export async function generateAgentReply(
  _agent: AgentAccount,
  _roomId: string,
  _history: Message[],
  _model: ModelClient,
  _signal?: AbortSignal,
): Promise<Message> {
  throw new Error("NOT IMPLEMENTED: generateAgentReply — Gate 2 model-agent runner");
}
