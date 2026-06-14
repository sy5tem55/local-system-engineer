# The Coding Gauntlet — a 4-gate agentic pyramid

> A capability ramp for the coding-agent workflow. Each gate is a **real, runnable
> artifact** AND a coding challenge of rising difficulty. Crucially, every gate builds a
> slice of the pinnacle, so by the time we attempt Gate 4 nothing in it is unproven.

## The through-line

One product, built in four passes of increasing complexity: **a chat fabric where local
models and humans share group conversations, extensible by plugins.** Gate 4 (your pinnacle)
is the native iOS expression of it. Gates 1–3 (my proposal) each introduce exactly one new
hard axis and hand its output forward:

```
Gate 1  transport + design tokens + message schema
   │        (talk to a local model, render it the opencode way)
   ▼
Gate 2  backend + accounts + realtime + multi-agent orchestration
   │        (many humans + many model accounts in one room)
   ▼
Gate 3  plugin framework + full design system
   │        (extensibility + the finished opencode UI, web dress-rehearsal)
   ▼
Gate 4  NATIVE iOS — everything converges  ◀── your pinnacle
```

Nothing is throwaway: Gate 1's tokens skin Gate 2's web client; Gate 2's server is the
backend Gate 4's app talks to; Gate 3's plugin contract and component system port onto iOS.

## The shared aesthetic (locked from Gate 1)

The opencode look is the spine. All gates consume one token file —
`design-tokens/opencode-tokens.json` — so the app looks identical from terminal to iOS.

| Token | Hex | Role |
|---|---|---|
| background | `#0a0a0a` | deep-black ground |
| primary | `#fab283` | warm amber — cursor, links, own messages, primary action |
| accent | `#9d7cd8` | purple — headings, agent-name accents, keywords |
| secondary | `#5c9cf5` | blue — selection, mentions, focused state |
| text / muted | `#e0e0e0` / `#808080` | foreground / timestamps |

Confirmed signatures: `#0a0a0a`, `#fab283`, `#9d7cd8`, `#5c9cf5`. Font: **monospace
everywhere** (terminal-native feel). Gate 1 reconciles the approximate tokens + the exact
webfont against opencode's canonical `opencode.json`, and pins them — after that the palette
is frozen for all gates.

---

## Gate 1 — *The Terminal Confidant*  (foundational)

**Goal.** A single human ↔ a single local model, in a terminal, rendered the opencode way.

**What gets built.** A one-binary TUI chat client that streams from the local llama-server
(OpenAI-compatible `/v1/chat/completions`, SSE token streaming), renders the model's markdown
and **syntax-highlighted code blocks** using the opencode tokens on a `#0a0a0a` ground, and
keeps a clean message log.

**New axis it forces.** Local-model transport (streaming), the canonical **message schema**
(`id, room, author{id,kind:human|model}, role, content, ts`), and first contact with the
opencode visual language. Deliverable side-effect: the **frozen design-token file** every later
gate reuses.

**Stack (locked).** TypeScript + **Ink** (React-for-the-terminal); truecolor. Talks to
`:8080` (LUCIFER) or node3090 `:8642`. Shared TS types for the message schema start here and
are imported by every later gate.

**Acceptance.** Streams a live reply from llama-server; code blocks render in opencode syntax
colors; palette matches the token file within ΔE tolerance; runs with one command; message log
round-trips to disk in the canonical schema.

**Feeds the pinnacle.** Transport + schema + locked tokens — the substrate of everything above.

---

## Gate 2 — *The Group Server*  (intermediate)

**Goal.** Many participants — humans **and** models — in shared, persistent rooms, in real time.

**What gets built.** A backend service + thin web client implementing: human **accounts**
(auth + identity), **model agent accounts** (each bound to a local model endpoint), **rooms**
with **WebSocket** fan-out, **persistent history** (SQLite), and the orchestration layer. This
is where local models start talking *to each other* and to people.

**Orchestration (locked: mention + reply, behind a swappable policy).** Speaker selection is a
`SpeakerPolicy` interface so the room's behavior is pluggable. The **default and only** policy
shipped at Gate 2 is **mention-+-reply**: an agent is invited to respond only when it is
`@mentioned` or directly replied-to — deterministic and trivially loop-safe (an agent never
self-triggers; a turn-budget guard caps any single human message's fan-out). Autonomous-cadence
and director policies are future implementations of the same interface, not rewrites.

**New axis it forces.** Backend architecture, auth, realtime delivery, persistence, and
**multi-agent orchestration** as a clean interface — mention routing, turn-budget arbitration,
and conversation-termination guarantees.

**Stack (locked).** TypeScript — **Bun** (or Node) + `ws` server, **SQLite** to start, a
minimal **React/Svelte** web client skinned with Gate 1's tokens. Reuses Gate 1's shared TS
message types. Model accounts fan out to llama-server / node3090. REST + WebSocket contract is
written down here as the API the iOS app will later consume.

**Acceptance.** 2 humans + 2 model agents in one room; `@mention` a model → it replies; a
model-to-model exchange **terminates** (no runaway loop); history survives a restart; delivery
< 1s; auth gates room access.

**Feeds the pinnacle.** This *is* the backend Gate 4's iOS app consumes — every account, room,
socket, and orchestration rule is reused verbatim.

---

## Gate 3 — *The Plugin Forge*  (advanced)

**Goal.** Make it **extensible**, and finish the design system — a web dress-rehearsal for iOS.

**What gets built.** A **plugin framework** on the Gate 2 server: a typed plugin contract
(manifest + lifecycle hooks `on_message` / `on_command` / capability-exposure), **sandboxed**
execution, a registry with runtime load, and **2–3 reference plugins** (e.g. `/search`,
a code-runner, an attachment/image handler) that agents can invoke mid-conversation. Plus a
**polished reference web client** implementing the *complete* opencode token model (panels,
borders, diff, markdown, syntax) as a component library the iOS app will mirror.

**New axis it forces.** Extensibility architecture (the framework you want), capability
sandboxing + a stable third-party API contract, and **full aesthetic fidelity** — proving the
entire design system on the easy platform before the hard one.

**Stack (locked).** TypeScript — plugin contract as a versioned TS interface; sandboxed
execution (subprocess or WASM, decided at Gate 3); reference client in Gate 2's web framework,
now built out to a real opencode component kit.

**Acceptance.** Load a plugin from a manifest at runtime (no core changes); an agent invokes a
plugin capability and the result renders in-thread; a third party can ship a plugin against the
documented contract alone; the web client passes a visual-fidelity check against the tokens.

**Feeds the pinnacle.** Hands Gate 4 the two things it must carry onto iOS: the **plugin
framework** and the **finished, validated design system**.

---

## Gate 4 — *The Pocket Agora*  (pinnacle — yours)

Native **iOS (SwiftUI)** chat app: human accounts + local-model agent accounts in **group
chats**, the **plugin framework**, and the **exact opencode aesthetic** (`#0a0a0a` /
`#fab283` / `#9d7cd8` / `#5c9cf5`, monospace, full token model), talking to the Gate 2/3
backend. Models interact with each other and with humans. Every lower gate converges here:
transport (G1) · backend + accounts + realtime + multi-agent (G2) · plugin framework + design
system (G3) → native platform.

---

## How the gates ladder

| Capability | G1 | G2 | G3 | G4 |
|---|:--:|:--:|:--:|:--:|
| Local-model transport (streaming) | ● | ↑ | ↑ | ↑ |
| opencode design tokens | ● (seed) | ↑ | ● (full) | ↑ |
| Canonical message schema | ● | ↑ | ↑ | ↑ |
| Accounts (human + model) | | ● | ↑ | ↑ |
| Realtime rooms + persistence | | ● | ↑ | ↑ |
| Multi-agent orchestration | | ● | ↑ | ↑ |
| Plugin framework | | | ● | ↑ |
| Native platform (iOS) | | | | ● |

(● introduced · ↑ reused/extended)

## Grading

Each gate ships with a small acceptance harness (the criteria above as runnable checks), so a
gate is "passed" only on demonstrated behavior — same ground-truth discipline as the arena, now
pointed at coding artifacts instead of infra probes. Difficulty climbs simple → advanced, which
is the whole point: it's a curriculum for the coding-agent workflow, not four unrelated tasks.

## Decisions locked

- **Stack:** TypeScript across gates 1–3 (Ink TUI → Bun/`ws` + SQLite + web client → TS plugin
  contract). One language end-to-end; the message schema is shared TS types from Gate 1 onward,
  and the Gate 2 REST+WS contract is the same JSON API the SwiftUI app consumes at Gate 4.
- **Orchestration:** mention-+-reply default, behind a swappable `SpeakerPolicy` interface
  (autonomous-cadence and director policies are later implementations, not rewrites).

## Open decisions (yours)

1. **Who builds the gates** — the LSE agent autonomously (the Goethe coding curriculum; I author
   specs + harness), or co-built with me scaffolding each gate.
2. **Gate 3 sandbox** — WASM vs subprocess (decide at Gate 3; not blocking now).
