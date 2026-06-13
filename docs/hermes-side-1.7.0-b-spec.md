# Hermes-Side Implementation Spec — 1.7.0-b (node3090)

> Status: SPEC (P28 Cowork, 2026-06-13). To be self-installed by Hermes on node3090.
> Companion to `docs/lse-1.7.0-b-bidirectional-design.md` (the decision) and the
> LSE side already shipped in Cogitator v1.7.15 (`check_hermes_inbox`, inbound parse).
> Hermes is Hermes Agent (Nous Research): `~/.local/bin/hermes`, runs as `hermes-admin`,
> gateway `:8642`, has terminal/file/memory/skill/Telegram tools, **no SSH to infra**.

## Goal

Let Hermes initiate contact with the LSE and have SY5 see it in Telegram. Hermes
cannot open a connection to the LSE (the LSE is a request-driven OWUI tool). So
Hermes holds an **outbox** and its messages **ride the reply** to any call the LSE
makes (`call_hermes`, `hermes_plan`, or the `check_hermes_inbox` poll).

## ⚠ Architectural fork to resolve FIRST (against Hermes Agent docs)

The LSE side (v1.7.15) currently reads a **top-level `hermes_messages` field** on the
gateway's `/v1/chat/completions` response. Whether Hermes can put a field there
depends on Hermes Agent's extensibility:

- **Path A — gateway response hook/middleware/plugin.** If Hermes Agent supports a
  response hook that can add a top-level JSON field, use it to attach
  `hermes_messages`. **No LSE change needed.** Check the docs
  (`skill_view('hermes-agent')` + hermes-agent.nousresearch.com/docs) for a
  response/middleware/plugin mechanism.
- **Path B — content marker (always works, no gateway internals).** Hermes embeds the
  pending messages inside its normal reply **content**, wrapped in a sentinel:
  ```
  [[HERMES->LSE]]{"messages":[ ...envelopes... ]}[[/HERMES->LSE]]
  ```
  This is fully self-installable (Hermes controls its own reply text via a skill),
  but requires a **small LSE-side update (Cogitator v1.7.19)** so `check_hermes_inbox`
  / `call_hermes` parse the marker out of `content` instead of a top-level field.

**Recommendation:** Path B unless the docs confirm a clean response-field hook.
It's guaranteed implementable with Hermes's own tools; the LSE v1.7.19 parser tweak
is ~10 lines (extract the sentinel block, `json.loads` it, reuse `_format_hermes_messages`).

## 1. Outbox store

A small store Hermes owns and can write without sudo. Two options:

- **Simplest:** a JSON file `~/.hermes/lse-outbox.json` — a list of envelopes.
- **Parity with kanban:** a table in `~/.hermes/kanban.db`:

```sql
CREATE TABLE IF NOT EXISTS lse_outbox (
  correlation_id TEXT PRIMARY KEY,
  kind           TEXT NOT NULL DEFAULT 'notify',   -- notify | ask
  priority       TEXT NOT NULL DEFAULT 'info',      -- info | action | urgent
  body           TEXT NOT NULL,
  want_reply     INTEGER NOT NULL DEFAULT 0,
  created_at     INTEGER NOT NULL,
  delivered      INTEGER NOT NULL DEFAULT 0,
  delivered_at   INTEGER,
  reply          TEXT,
  replied_at     INTEGER
);
```

## 2. Envelope (matches the LSE side + planner §3.1)

```json
{
  "v": 1,
  "correlation_id": "hz-20260613-0001",
  "kind": "notify | ask",
  "priority": "info | action | urgent",
  "body": "node3090 llama-server OOM at 14:02; restart requested",
  "want_reply": true,
  "created_at": 1760000000
}
```

## 3. `call_lse(body, kind="notify", priority="info", want_reply=False)`

Hermes-side function (install as a skill / tool via `skill_manage`, or a helper the
agent calls from its `terminal`/`file` tools). Steps:

1. Generate `correlation_id` (e.g. `hz-<UTC date>-<counter>`).
2. **Enqueue** the envelope into the outbox (file or `lse_outbox`), `delivered=0`.
3. **Mirror to Telegram** — post the body to SY5's chat so the human sees what Hermes
   told the LSE. (Hermes already owns the Telegram channel; reuse the home channel.)
4. Return the `correlation_id` so the caller can correlate the eventual reply.

## 4. Delivery — flush on the next LSE call

On **any** inbound request the gateway routes to the agent (the LSE's
`call_hermes`/`hermes_plan`/`__LSE_POLL__`):

- Read all `delivered=0` outbox rows.
- Emit them to the LSE via the chosen path:
  - **Path A:** attach `"hermes_messages": [envelopes]` to the response JSON.
  - **Path B:** prepend `[[HERMES->LSE]]{"messages":[envelopes]}[[/HERMES->LSE]]` to
    the reply content.
- Mark those rows `delivered=1`, `delivered_at=now`.

Recognise the poll sentinel: if the inbound user content is exactly `__LSE_POLL__`
(plus optional `/no_think`), short-circuit — do NOT spend a full reasoning turn;
just flush the outbox (empty → a minimal "INBOX EMPTY" content is fine, the LSE maps
that to no messages).

## 5. Reply routing (`ask` envelopes)

When the LSE acts on an `ask` and replies, it calls `call_hermes(<result>,
context="correlation_id=hz-...")` (LSE-side convention from v1.7.15). On the gateway
side, parse `correlation_id=` out of the incoming `context`/content, find the matching
outbox row, write `reply` + `replied_at`, and mirror the reply to Telegram so SY5 sees
the full round trip.

## 6. Firecrawl web_search wiring (bundled fix)

Hermes's `search.firecrawl` backend fails with PEP 668 (`externally-managed-environment`)
because it tries to auto-`pip install firecrawl-py`. A self-hosted Firecrawl now runs on
this node at `http://localhost:3002` (no auth — `USE_DB_AUTHENTICATION=false`; `/v1/scrape`
and `/v1/search` verified, SearXNG-backed). To switch Hermes onto it:

1. Install the SDK **into Hermes's own environment**, not system pip:
   `uv pip install 'firecrawl-py==4.17.0'` (or a venv pip). PEP 668 blocks system-wide.
2. Point the SDK at the local instance — `FIRECRAWL_API_URL=http://localhost:3002`
   (and any dummy `FIRECRAWL_API_KEY` if the client insists). Set it the supported way:
   `hermes config set ...` per the docs, or in the gateway's environment. Hermes runs
   as a host systemd service, so `localhost:3002` is directly reachable.
3. Verify: a `web_search` should now return SearXNG-backed, Firecrawl-scraped results
   with no PEP-668 error.

Load the `hermes-agent` skill and follow the docs for the exact config keys — do not
hand-edit agent-managed files. **Do not restart the gateway mid-conversation** (it
kills the channel you're talking over); configure, then restart as a separate step.

## 7. Install discipline (Hermes)

- Outbox + `call_lse` + the delivery rule: install as a **skill** (`skill_manage`) and/or
  a compact **memory** rule, the same path used for the LSE-relationship KB entry — never
  hand-edit agent-managed memory/skills directly.
- Confirm from Hermes Agent docs before building: (a) is there a gateway response hook
  (Path A) or do we use the content marker (Path B)? (b) the supported config key for the
  firecrawl base URL.

## 8. LSE-side follow-up (only if Path B)

Cogitator v1.7.19: in `check_hermes_inbox` and the `call_hermes`/`hermes_plan` reply
handling, extract `[[HERMES->LSE]]…[[/HERMES->LSE]]` from the response content,
`json.loads` the inner `{"messages":[...]}`, and feed it to the existing
`_format_hermes_messages`. ~10 lines; keeps everything else (cadence rule, reply-via-
correlation_id) intact.
