// src/render.ts — AGENT IMPLEMENTS.
// Render ONE Message to an ANSI truecolor string using the opencode tokens on
// the #0a0a0a ground: markdown (bold/headings/links/inline-code) + syntax-
// highlighted fenced code blocks. The Ink view AND the acceptance harness both
// call this — so it is the single source of visual truth.
//
// Rules the harness enforces:
//   - emit ANSI 24-bit SGR codes (use fg()/bg() from tokens.ts)
//   - a fenced code block must paint at least one opencode SYNTAX color
//   - every color emitted must be within ΔE<=2 of SOME token (no rogue colors)
import type { Message } from "./schema.js";
import { tokens } from "./tokens.js";

export interface RenderOpts {
  width?: number;
}

export function renderMessageToAnsi(_msg: Message, _opts: RenderOpts = {}): string {
  void tokens;
  throw new Error("NOT IMPLEMENTED: renderMessageToAnsi — Gate 1 opencode renderer");
}
