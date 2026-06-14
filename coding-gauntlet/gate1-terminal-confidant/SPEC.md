# Gate 1 — The Terminal Confidant (challenge spec)

> Coding Gauntlet, gate 1 of 4. A capability ramp for the LSE coding-agent workflow.
> This file is the **contract**: the LSE agent implements the stubbed modules until
> `npm test` is all-green. Same ground-truth discipline as the infra arena — a gate is
> "passed" only on demonstrated behavior, not self-report.

## Goal

One human ↔ one local model, in a terminal, **rendered the opencode way**. A single-binary
TUI chat client that streams from the local llama-server and renders the reply (markdown +
syntax-highlighted code) on the `#0a0a0a` opencode ground.

## Stack (locked)

TypeScript + **Ink** (React-for-the-terminal), truecolor. Node ≥ 20. ESM (`"type":"module"`).
Talks to llama-server's OpenAI-compatible API at `:8080` (LUCIFER / `node4090.home.arpa`) or
node3090 `:8642`. The message schema is **shared TS types from here on** — Gates 2–4 import
`src/schema.ts` unchanged.

## What's authored vs. what you build

**Authored & FROZEN (do not edit the shapes):**
- `src/schema.ts` — canonical `Message` / `Author` + `validateMessage` / `serializeMessage` /
  `deserializeMessage`. The on-disk form is JSONL: one validated `Message` per line.
- `src/tokens.ts` — typed loader for `../design-tokens/opencode-tokens.json` plus the color
  helpers you must use: `fg(hex)` / `bg(hex)` (ANSI 24-bit SGR), `RESET`, `deltaE()`, `SIGNATURE`,
  `allTokenHexes()`.
- `test/acceptance.test.ts` — the grader. Don't edit it to pass; implement against it.

**You implement (stubs throw `NOT IMPLEMENTED`):**

| Module | Export | Contract |
|---|---|---|
| `src/transport.ts` | `streamChat(opts): AsyncIterable<string>` | POST `/v1/chat/completions` with `stream:true`; parse `data: {…}` SSE lines; **yield** `choices[0].delta.content` chunks as they arrive; stop on `data: [DONE]` or when `opts.signal` aborts. Must not buffer the whole reply. |
| `src/render.ts` | `renderMessageToAnsi(msg, opts?): string` | Render one message to ANSI truecolor on the `#0a0a0a` ground: markdown (headings/bold/links/inline-code) + **syntax-highlighted fenced code blocks**. Use `fg()`/`bg()` from tokens. Code blocks must paint opencode **syntax** colors; emit **no color outside the token palette**. |
| `src/log.ts` | `class MessageLog { append(msg); all() }` | Append-only JSONL via the schema (de)serializers. Round-trip: append → a fresh `MessageLog` over the same path reads back, schema-valid and deep-equal. |
| `src/app.tsx` | `App(props)` | The Ink view: input box (amber `primary` cursor), scrolling pane that prints `renderMessageToAnsi(msg)` per entry, a live streaming assistant line fed by `streamChat()`. |
| `src/index.ts` | entry | `npm start` → parse `--url/--room/--log`, mount `<App/>`, Ctrl-C clean exit, enforce the give-up budget on the stream. |

## Transport detail (llama-server is OpenAI-compatible)

```
POST {baseUrl}/v1/chat/completions
{ "model": "<any>", "stream": true,
  "messages": [ {"role":"user","content":"…"} ] }
```
Response is `text/event-stream`: lines `data: {json}` whose `choices[0].delta.content` carries
token text; the stream ends with `data: [DONE]`. Yield each delta. Wire `opts.signal` to `fetch`.

## Give-up budget (mandatory — house rule)

Every agentic loop gets a ceiling. `streamChat` takes an `AbortSignal`; the app must enforce a
**max-tokens and max-wall-time** budget and abort the stream when either trips. Past the knee,
more tokens buy ~nothing — the loop stops, it doesn't smoke compute.

## Acceptance (each criterion is a runnable check in `npm test`)

| PYRAMID criterion | Check | Starts |
|---|---|---|
| message schema is canonical | `[authored] schema round-trips…` | green |
| palette pinned to opencode | `[authored] token signatures…` | green |
| runs with one command | `[authored] runs with one command` | green |
| log round-trips to disk in the schema | `[agent] message log round-trips…` | **red** |
| code blocks in opencode syntax colors | `[agent] renderer paints fenced code…` | **red** |
| palette matches token file within ΔE | `[agent] renderer uses only the opencode palette` | **red** |
| streams a live reply from llama-server | `[agent][live] streams ≥1 token…` | skip → **red/green** |

**Definition of done:** `npm test` is all-green offline (authored + the three agent checks), and
`GATE1_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test` passes the live stream.

ΔE tolerance is **ΔE76 ≤ 2.0** (just-noticeable). The renderer must emit only colors within that
of a token in `opencode-tokens.json` — no rogue colors.

## Side-effect deliverable: pin the tokens

The token file ships with the four signatures `confirmed:true` (`#0a0a0a #fab283 #9d7cd8 #5c9cf5`)
and the rest marked `APPROX`. Part of Gate 1 is reconciling the APPROX colors + the exact webfont
against opencode's canonical `opencode.json` and flipping them to `confirmed:true`. After Gate 1 the
palette is **frozen for all gates**. (The authored signature check guards the four locked colors
against regression.)

## Run

```bash
npm install
npm test                 # offline: authored green, agent red until built
npm start -- --url http://node4090.home.arpa:8080      # the TUI
GATE1_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test   # + live stream
```

## Feeds the pinnacle

Transport (G1) + the shared schema + the frozen tokens are the substrate of every gate above:
G2's web client wears these tokens, G2's server speaks this schema, G4's iOS app consumes both.
