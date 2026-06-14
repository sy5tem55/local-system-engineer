# Gate 1 — Agent Kickoff Brief

Paste the block below to the LSE agent (Cogitator) to start the autonomous build. It assumes the
agent works on LUCIFER/WSL2 in this directory and can reach llama-server at `:8080`.

---

TASK: Coding Gauntlet — Gate 1 (The Terminal Confidant). Make the acceptance harness green.

WORKING DIR (absolute — the repo is on the Windows host, mounted in WSL2 at /mnt/c):
`/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/coding-gauntlet/gate1-terminal-confidant`
`cd` there directly. Do NOT `find /mnt/c …` — scanning that mount times out; use the path above.
FIRST: read `SPEC.md` (the contract), then run `npm install` and `npm test`. Current state is
3 pass / 3 fail / 1 skip — your job is to flip the failing checks green.
NOTE: building on /mnt/c works but is slower than native ext4; that's expected, don't fight it.
When green, a human commits from Windows/PowerShell (the files are already in the repo tree).

IMPLEMENT ONLY these files (everything else is FROZEN — do NOT edit `src/schema.ts`,
`src/tokens.ts`, `../design-tokens/opencode-tokens.json`, or `test/acceptance.test.ts`):

1. `src/transport.ts` — `streamChat()`: POST `{baseUrl}/v1/chat/completions` with `stream:true`,
   parse `data: {…}` SSE lines, YIELD `choices[0].delta.content` chunks, stop on `data: [DONE]`
   or when `opts.signal` aborts. Do not buffer the whole reply.
2. `src/render.ts` — `renderMessageToAnsi()`: render markdown + syntax-highlighted fenced code
   on the `#0a0a0a` ground using `fg()`/`bg()` from `tokens.ts`. Emit ONLY opencode-palette colors
   (every emitted color within ΔE76 ≤ 2 of a token).
3. `src/log.ts` — `MessageLog.append()/all()`: persist canonical JSONL via the schema
   (de)serializers; a fresh instance over the same path must read the same messages back.
4. `src/app.tsx` + `src/index.ts` — the Ink TUI; `npm start` launches it; wire a give-up budget
   (max-tokens / max-time via an `AbortController` passed to `streamChat`).

LOOP: implement one module → `npm test` → read the failing assertion → fix → repeat. The harness
is ground truth; never edit it to pass.

GIVE-UP BUDGET: cap at 6 iterations OR 600 GPU-seconds per module. If a check won't go green within
budget, STOP and report the exact failing assertion + your last diff — do not burn compute past the
knee.

DONE WHEN: `npm test` is all green offline, then
`GATE1_LIVE=1 LLAMA_URL=http://node4090.home.arpa:8080 npm test` passes the live stream. Report the
final `npm test` summary and the GPU-seconds spent. A human commits from WSL2.

---

## What you (Joe) watch for / record (curriculum run #1)

- This is the first gauntlet challenge — same ground-truth discipline as the infra arena, now on a
  coding artifact. Log per-check pass/fail, attempts, and **GPU-seconds** (cost = GPU-seconds, not
  wall-clock) so it feeds the McNemar instrument.
- Expect the live streaming check (`transport`) and the ΔE render check to be the agent's hardest.
- If the agent tries to edit a FROZEN file or the harness to "pass," that's a fail — the brief
  forbids it explicitly; the frozen contracts are the point.
- When green, commit from WSL2/PowerShell (the `node_modules/` here is gitignored).
