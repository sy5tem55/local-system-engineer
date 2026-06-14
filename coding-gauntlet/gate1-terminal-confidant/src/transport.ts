// src/transport.ts — AGENT IMPLEMENTS.
// SSE streaming from an OpenAI-compatible llama-server /v1/chat/completions.
// POST { model, messages:[{role,content}], stream:true }; read `data: {...}`
// lines; yield choices[0].delta.content; stop on `data: [DONE]` or abort.
import type { Message } from "./schema.js";

export interface StreamOpts {
  baseUrl: string; // e.g. http://node4090.home.arpa:8080  (or node3090 :8642)
  model?: string; // optional; llama-server tolerates/echoes
  messages: Message[]; // conversation so far
  signal?: AbortSignal; // GIVE-UP BUDGET: caller aborts on max-tokens/max-time
}

/**
 * MUST yield assistant content deltas (token chunks) as they arrive.
 * MUST terminate cleanly on `[DONE]` or when `signal` aborts.
 * MUST NOT buffer the whole reply before yielding (it has to stream).
 */
export async function* streamChat(_opts: StreamOpts): AsyncIterable<string> {
  throw new Error(
    "NOT IMPLEMENTED: streamChat — Gate 1 SSE transport (/v1/chat/completions)",
  );
}
