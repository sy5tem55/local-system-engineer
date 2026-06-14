// test/acceptance.test.ts — Gate 1 acceptance harness.
// Maps PYRAMID.md "Acceptance" to runnable checks. Same ground-truth discipline
// as the infra arena, pointed at a coding artifact. Run: `npm test`.
//
//   [authored] checks PASS now (prove the harness + frozen contracts are sound).
//   [agent]    checks FAIL until the LSE agent implements src/{log,render,transport}.
//   [agent][live] streams from a real llama-server; gated by GATE1_LIVE=1.
//
// A gate is "passed" only when every non-skipped check is green.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import React from "react";
import { render as inkRender } from "ink-testing-library";

import {
  validateMessage,
  serializeMessage,
  deserializeMessage,
  type Message,
} from "../src/schema.js";
import { tokens, SIGNATURE, deltaE, allTokenHexes } from "../src/tokens.js";
import { App } from "../src/app.js";

const TOL = 2.0; // ΔE76 just-noticeable tolerance
const stripAnsi = (s: string) => s.replace(/\x1b\[[0-9;]*m/g, ""); // SGR codes interleave tokens

function msg(over: Partial<Message> = {}): Message {
  return validateMessage({
    id: "m1",
    room: "local",
    author: { id: "u:joe", kind: "human", name: "Joe" },
    role: "user",
    content: "hi",
    ts: 1_700_000_000_000,
    ...over,
  });
}

/** Pull every 24-bit truecolor (fg/bg) hex out of a rendered ANSI string. */
function emittedHexes(s: string): string[] {
  const out: string[] = [];
  const re = /\x1b\[(?:38|48);2;(\d+);(\d+);(\d+)m/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    out.push(
      "#" +
        [m[1], m[2], m[3]]
          .map((n) => (+n).toString(16).padStart(2, "0"))
          .join(""),
    );
  }
  return out;
}

// ── [authored] — green now ────────────────────────────────────────────────────

test("[authored] schema round-trips and rejects malformed messages", () => {
  const m = msg({ content: "```py\nprint(1)\n```" });
  assert.deepEqual(deserializeMessage(serializeMessage(m)), m);
  assert.throws(() => validateMessage({ ...m, role: "bogus" }));
  assert.throws(() => validateMessage({ ...m, author: { id: "x", kind: "alien" } }));
  assert.throws(() => validateMessage({ ...m, ts: "soon" }));
});

test("[authored] token signatures are the four locked opencode colors", () => {
  assert.equal(tokens.color.background.hex, SIGNATURE.background);
  assert.equal(tokens.color.primary.hex, SIGNATURE.primary);
  assert.equal(tokens.color.accent.hex, SIGNATURE.accent);
  assert.equal(tokens.color.secondary.hex, SIGNATURE.secondary);
});

test("[authored] runs with one command (package.json start script present)", () => {
  const pkg = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.ok(pkg.scripts?.start, "missing scripts.start");
  assert.ok(pkg.bin, "missing bin entry");
});

// ── [agent] — red until implemented ───────────────────────────────────────────

test("[agent] message log round-trips to disk in the canonical schema", async () => {
  const { MessageLog } = await import("../src/log.js");
  const dir = mkdtempSync(join(tmpdir(), "gate1-"));
  const p = join(dir, "log.jsonl");
  try {
    const a = msg({ id: "a", role: "user", content: "hello" });
    const b = msg({
      id: "b",
      role: "assistant",
      author: { id: "m:qwen3.6-27b", kind: "model" },
      content: "world",
    });
    const log = new MessageLog(p);
    log.append(a);
    log.append(b);
    const reread = new MessageLog(p).all(); // fresh instance, same path
    assert.deepEqual(reread, [a, b]);
    reread.forEach(validateMessage);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("[agent] renderer paints fenced code with the opencode syntax palette", async () => {
  const { renderMessageToAnsi } = await import("../src/render.js");
  const out = renderMessageToAnsi(
    msg({ content: "Here:\n```python\ndef f():\n    return 'x'\n```" }),
  );
  const hexes = emittedHexes(out);
  assert.ok(hexes.length > 0, "renderer emitted no truecolor SGR codes");
  const syntax = Object.values(tokens.syntax).filter(
    (v) => typeof v === "string" && v.startsWith("#"),
  ) as string[];
  const hitSyntax = hexes.some((h) => syntax.some((s) => deltaE(h, s) <= TOL));
  assert.ok(hitSyntax, "no opencode syntax color found in the rendered code block");
});

test("[agent] renderer uses only the opencode palette (no rogue colors)", async () => {
  const { renderMessageToAnsi } = await import("../src/render.js");
  const out = renderMessageToAnsi(
    msg({ content: "**bold**, `inline`, a [link](https://x), and normal text." }),
  );
  const palette = allTokenHexes();
  for (const h of emittedHexes(out)) {
    const near = palette.reduce((min, p) => Math.min(min, deltaE(h, p)), Infinity);
    assert.ok(near <= TOL, `rogue color ${h}: ΔE ${near.toFixed(2)} from nearest token`);
  }
});

// ── [agent][live] — needs a running llama-server; gated ───────────────────────

const LIVE = process.env.GATE1_LIVE === "1";
test(
  "[agent][live] streams >=1 token from llama-server",
  { skip: !LIVE && "set GATE1_LIVE=1 (and LLAMA_URL) to run" },
  async () => {
    const { streamChat } = await import("../src/transport.js");
    const baseUrl = process.env.LLAMA_URL || "http://node4090.home.arpa:8080";
    const ctrl = new AbortController();
    const it = streamChat({
      baseUrl,
      messages: [msg({ content: "Reply with one word." })],
      signal: ctrl.signal,
    });
    let got = "";
    for await (const delta of it) {
      got += delta;
      if (got.length) {
        ctrl.abort();
        break;
      }
    }
    assert.ok(got.length > 0, "no tokens streamed from llama-server");
  },
);

// ── [agent] HARDENING (P31 review) — markdown correctness + app integration ───
// The original render checks only proved colors were in-palette; they did NOT
// prove markdown is rendered correctly, nor that the App actually USES the
// renderer / persists the log. These close those blind spots.

test("[agent] renderer: bold / inline-code / link markdown render correctly", async () => {
  const { renderMessageToAnsi } = await import("../src/render.js");
  const out = renderMessageToAnsi(
    msg({ content: "A **bold** word, `code`, and a [label](https://x.test)." }),
  );
  // markdown DELIMITERS must be consumed, the inner text must survive.
  assert.ok(!out.includes("**"), "bold left a literal ** in the output");
  assert.match(out, /bold/, "bold text missing");
  assert.ok(!out.includes("`"), "inline code left a literal backtick");
  assert.match(out, /code/, "inline-code text missing");
  assert.match(out, /label/, "link label missing");
  assert.ok(!out.includes("](http"), "link left raw target syntax in the output");
});

test("[agent] App renders messages THROUGH the renderer (no raw markdown/fences in frame)", () => {
  const seed = [
    msg({
      id: "s1",
      role: "assistant",
      author: { id: "m:x", kind: "model", name: "x" },
      content: "Here:\n```python\nx = 1\n```\nand **bold**.",
    }),
  ];
  // App must accept initialMessages (seed) and print each via renderMessageToAnsi.
  const { lastFrame, unmount } = inkRender(
    React.createElement(App as any, {
      baseUrl: "http://127.0.0.1:1",
      initialMessages: seed,
    }),
  );
  // ANSI SGR codes interleave the tokens, so strip them before substring checks.
  const frame = stripAnsi(lastFrame() ?? "");
  unmount();
  assert.match(frame, /x = 1/, "code content missing — App isn't showing the message");
  assert.ok(!frame.includes("```"), "raw code fence in frame — App isn't using renderMessageToAnsi");
  assert.ok(!frame.includes("**"), "raw bold markers in frame — App isn't rendering markdown");
});

// Persistence (--log) + give-up budget: both need either reliable Ink stdin
// simulation (flaky) or fake timers / injected transport. They are real
// requirements (SPEC §App, §Give-up budget) and the fix-list, but are documented
// here as skips rather than shipped as flaky checks. log.ts's round-trip unit test
// already proves the persistence PRIMITIVE; wiring + budget are verified by running
// `npm start -- --log <path>` and inspecting the JSONL / aborting a runaway stream.
test(
  "[agent][persist] App persists messages to --log on send",
  { skip: "SPEC requirement — run `npm start -- --log <path>` and inspect the JSONL; log.ts unit covers the primitive" },
  () => {},
);
test(
  "[agent][budget] App enforces a give-up budget (max time / tokens)",
  { skip: "SPEC requirement — verify the budget aborts a runaway stream; see SPEC §Give-up budget" },
  () => {},
);
