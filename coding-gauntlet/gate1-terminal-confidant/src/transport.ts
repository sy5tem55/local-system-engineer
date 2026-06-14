// src/transport.ts — SSE streaming from an OpenAI-compatible llama-server.
// POST /v1/chat/completions { model, messages, stream: true }
// Yield choices[0].delta.content as it arrives.
import type { Message } from "./schema.js";

export interface StreamOpts {
  baseUrl: string;
  model?: string;
  messages: Message[];
  signal?: AbortSignal;
}

export async function* streamChat(opts: StreamOpts): AsyncIterable<string> {
  const { baseUrl, messages, signal } = opts;
  const url = `${baseUrl.replace(/\/+$/, "")}/v1/chat/completions`;

  const body = JSON.stringify({
    model: opts.model,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    stream: true,
  });

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`streamChat HTTP ${resp.status}: ${text.slice(0, 200)}`);
  }

  const reader = resp.body?.getReader();
  if (!reader) throw new Error("no response body");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) continue;

        if (line === "data: [DONE]") {
          return;
        }

        if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6);
          try {
            const json = JSON.parse(jsonStr);
            const content = json.choices?.[0]?.delta?.content;
            if (typeof content === "string" && content.length > 0) {
              yield content;
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    }

    // decode any remaining buffer
    if (buffer.trim()) {
      const line = buffer.trim();
      if (line.startsWith("data: ") && line !== "data: [DONE]") {
        try {
          const json = JSON.parse(line.slice(6));
          const content = json.choices?.[0]?.delta?.content;
          if (typeof content === "string" && content.length > 0) {
            yield content;
          }
        } catch { /* skip */ }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
