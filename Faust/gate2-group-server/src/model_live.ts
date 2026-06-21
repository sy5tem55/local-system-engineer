// src/model_live.ts — Live ModelClient wrapping Gate 1's SSE transport
import type { ModelClient, Message } from "./protocol.js";

export function makeLiveModelClient(): ModelClient {
  const apiKey = process.env.MODEL_API_KEY || "";

  return {
    async complete(req) {
      const { endpoint, model, messages, signal, maxTokens } = req;

      // Build the OpenAI-compatible request body
      const body = {
        model: model || "default",
        messages: messages.map(m => ({
          role: m.role,
          content: m.content,
        })),
        stream: false, // non-streaming for speed
        max_tokens: maxTokens || 2048,
      };

      const url = `${endpoint}/v1/chat/completions`;

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (apiKey) {
        headers["Authorization"] = `Bearer ${apiKey}`;
      }

      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Model request failed: ${response.status} ${errText}`);
      }

      const data = await response.json();
      return data.choices?.[0]?.message?.content || "";
    },
  };
}
