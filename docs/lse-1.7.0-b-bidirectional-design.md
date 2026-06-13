# LSE 1.7.0-b — Hermes ↔ LSE Bidirectional Communication (design)

> Status: DESIGN (P28 Cowork, 2026-06-13). Decision recorded; implementation split below.
> Supersedes the three bare options in ROADMAP §1.7.0-b with a recommended design.
> Builds on Fable5's `planner-orchestrator-design.md` and `lse-1.7.0-design.md §2` (envelope protocol).

## Problem (the phone metaphor)

LSE can dial Hermes (`call_hermes` → gateway `POST /v1/chat/completions`; `hermes_plan`
returns a plan envelope). Hermes answers. But **Hermes cannot dial LSE**, and SY5 wants
Hermes→LSE messages mirrored into **Telegram**.

Root cause: **LSE is request-driven, not a daemon.** It is an OpenWebUI tool agent that
only executes during a chat turn — there is no inbound socket for Hermes to reach.

## Key realisation (SY5, P28) — the return channel already exists

`call_hermes` / `hermes_plan` are **request/response**: LSE sends an intent, Hermes returns
a structured **envelope synchronously in the response body**, already carrying a
`correlation_id` (planner-orchestrator-design §3.1). So Hermes is *already* sending content
TO LSE — as the reply to a call LSE initiated. Hermes does **not** need a new outbound
transport, and per the capability separation (planner doc §2, §5) it must **not** get SSH
to LSE/infra; sync stays one-way LSE→Hermes at the *transport* level.

Therefore "Hermes messages LSE" = **Hermes rides the reply to any call LSE makes.**

## Decision — Hermes outbox, flushed onto the gateway response

| Concern | Mechanism |
|---|---|
| Hermes → LSE delivery | Hermes keeps a per-principal **outbox**. On any LSE→gateway call (`call_hermes`, `hermes_plan`, or a `check_hermes_inbox` poll), Hermes appends pending messages to the response envelope. |
| LSE picks up | New LSE tool `check_hermes_inbox()` makes a minimal gateway call (`intent=poll`) and returns queued messages. Called at conversation start / task boundaries. **HTTP only — no SSH, no new DB.** |
| SY5 visibility | Hermes routes all outbound-to-LSE through one `call_lse(...)` that also posts to **Telegram** (Hermes already owns the Telegram channel). Replies mirrored too. |
| Reply routing | LSE replies via `call_hermes` carrying the same `correlation_id`; Hermes closes the outbox item and routes to the originating task. |

This reuses the **working** channel, adds no transport, and honours the architecture
(Hermes plans/watches via its gateway API; LSE executes). The earlier `lse_inbox`
SQLite-over-SSH table is **dropped** — it duplicated the gateway and crossed the one-way-sync line.

### What this does and does not give

- ✅ Delivers any Hermes directive/alert the **next time LSE checks in** (conversation
  start, task boundary, or an explicit poll). For "next session do X" / "here's an alert",
  this is the whole job.
- ⚠️ Does **not** wake an idle LSE with no chat turn happening. That genuinely requires
  manufacturing a turn — see Optional escalation. Deferred; not core.

## Protocol — `hermes_notify` / `hermes_ask` (envelope, extends §2.2 / §3.1)

```json
{
  "v": 1, "correlation_id": "hz-20260613-0001",
  "kind": "notify | ask",
  "priority": "info | action | urgent",
  "body": "node3090 llama-server OOM at 14:02; restart requested",
  "want_reply": true,
  "created_at": 1760000000
}
```

- `notify` — informational; LSE acks, no action required.
- `ask` — LSE acts and replies via `call_hermes` with the same `correlation_id`.
- Messages are returned inside the normal gateway response envelope under a
  `hermes_messages: [...]` field, so existing `call_hermes`/`hermes_plan` calls carry them
  for free; `check_hermes_inbox()` is just the no-task call that surfaces them on demand.

## Implementation split

### LSE side — Cogitator v1.7.15 (this repo; I can build)
- New tool `check_hermes_inbox()` — POST to `{HERMES_API_URL}` with a minimal `intent=poll`
  body; parse `hermes_messages` from the response; return them for the model to act on.
  Reuses the existing `HERMES_API_URL` (`:8642`) + `HERMES_API_KEY` valves — **no new
  secrets, no SSH.**
- Parse `hermes_messages` out of the **existing** `call_hermes` / `hermes_plan` responses
  too, so directives arrive even without an explicit poll.
- Docstring cadence rule: call `check_hermes_inbox()` at conversation start and at task
  boundaries (same discipline shape as KB-FIRST). On an `ask` with `want_reply`, execute,
  then `call_hermes` the result with the `correlation_id`.

### Hermes side — node3090 (NOT in this repo; spec for Hermes/SY5 to self-install)
- An **outbox** in Hermes's own store (`~/.hermes/`), keyed by principal + `correlation_id`.
- `call_lse(body, kind, priority, want_reply)`:
  1. Enqueue the envelope in the outbox.
  2. Post `body` to **Telegram** (mirror); post the reply when it arrives.
- Gateway change: on every inbound LSE call, attach pending outbox items as
  `hermes_messages` in the response; mark them delivered; record replies that carry a
  known `correlation_id`.
- Install path: same as the LSE-relationship KB entry — via a `call_hermes` task to
  Hermes's own memory/skill tooling, never hand-edited.

## Optional escalation (deferred) — wake an idle LSE
Only the OWUI API inject can manufacture a chat turn when LSE is idle: Hermes `POST`s to
OWUI `/api/chat/completions` with the LSE model+tool, seeded with an `urgent` envelope.
Adds fragility (OWUI auth, headless model addressing, spawns a conversation). Build only if
a real act-now-while-idle need appears; the outbox-on-response path covers everything else.

## Notes / cleanups
- `kb/hermes-kb-lse-relationship.md` **and** `planner-orchestrator-design.md §2` still cite
  the socat `:8643` bridge — **stale since P27** (socat eliminated; gateway binds
  `0.0.0.0:8642` directly). Correct both when this ships.
- Confirm before building the Hermes side: Telegram chat id Hermes already posts to (reuse);
  the `hermes_messages` field name is free in the current envelope schema.
