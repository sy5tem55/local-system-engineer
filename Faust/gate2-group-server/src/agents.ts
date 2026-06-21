// src/agents.ts — Generate agent reply via ModelClient
import type { AgentAccount, ModelClient } from "./protocol.js";
import type { Message } from "./schema.js";

export async function generateAgentReply(
  agent: AgentAccount,
  roomId: string,
  history: Message[],
  model: ModelClient,
  signal?: AbortSignal,
): Promise<Message> {
  // Build messages array for the model
  const modelMessages: Message[] = [];

  // Prepend persona as system message if present
  if (agent.persona) {
    modelMessages.push({
      id: `sys-${Date.now()}`,
      room: roomId,
      author: { id: "system", kind: "model" },
      role: "system",
      content: agent.persona,
      ts: Date.now(),
    });
  }

  // Map history messages (exclude system messages, keep user/assistant)
  for (const m of history) {
    if (m.role !== "system") {
      modelMessages.push(m);
    }
  }

  // Call the model
  const text = await model.complete({
    endpoint: agent.endpoint,
    model: agent.model,
    messages: modelMessages,
    signal,
    maxTokens: agent.maxTokens,
  });

  // Guard: schema requires non-empty content; use fallback if model returns nothing
  const content = (text && text.trim())
    ? text.trim()
    : `*(${agent.handle} produced no response — check endpoint ${agent.endpoint})*`;

  // Wrap as a canonical assistant Message authored by the agent
  return {
    id: `m:${agent.handle}:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    room: roomId,
    author: {
      id: agent.id,
      kind: "model",
      name: agent.handle,
    },
    role: "assistant",
    content,
    ts: Date.now(),
  };
}
