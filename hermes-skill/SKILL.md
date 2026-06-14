---
name: lse-channel
description: >-
  Talk to the Local System Engineer (LSE / "Cogitator"). Use whenever you need to
  proactively notify or ask the LSE something, when an incoming request is the poll
  sentinel __LSE_POLL__, or on any reply you send to the LSE. Maintains an outbox;
  queued messages ride your reply back to the LSE (Path B content marker).
triggers:
  - "__LSE_POLL__"
  - "notify the LSE"
  - "ask the LSE"
  - "message the LSE"
  - "send to LSE"
  - "Cogitator"
  - "correlation_id="
---

# LSE Channel — Hermes producer side (1.7.0-b, Path B)

## Why this exists
The LSE is a request-driven OpenWebUI tool with **no inbound listener** — you cannot open
a connection to it. So you keep an **outbox**, and your pending messages **ride the reply**
to the next call the LSE makes to you (`call_hermes`, `hermes_plan`, or its `__LSE_POLL__`).
The LSE pulls them out of a marker in your reply content. There is no shared file or endpoint
on the LSE side to write to.

## One-time setup
Place the helper script at `~/.hermes/bin/lse_channel.py` (companion file shipped with this
skill) and make it executable:

```bash
mkdir -p ~/.hermes/bin
# copy lse_channel.py into ~/.hermes/bin/
chmod +x ~/.hermes/bin/lse_channel.py
```

The outbox lives at `~/.hermes/lse-outbox.json` (created on first enqueue). No sudo needed.

## A. To send a message to the LSE  (call_lse)
1. Enqueue it:
   ```bash
   python3 ~/.hermes/bin/lse_channel.py enqueue \
     --body "<one-line message>" --kind notify|ask \
     --priority info|action|urgent [--want-reply]
   ```
   It prints a `correlation_id` — keep it if you expect a reply.
2. **Mirror to Telegram**: post `<body>` to SY5's home chat via your Telegram tool, so the
   human sees what you told the LSE.
3. Done. The message is queued and will be delivered on the LSE's next call/poll.

### A.large — sending a large payload (ssh logs, dumps, multi-KB output)
The reply you ride back to the LSE is capped at the request's `max_tokens` (1024 on the
poll path). A large inline `body` overflows that cap and truncates the JSON marker, so
**large payloads go by reference**:
1. Write the payload to a file and enqueue from it:
   ```bash
   python3 ~/.hermes/bin/lse_channel.py enqueue \
     --body-file /path/to/big-output.txt --kind ask --priority action --want-reply
   ```
   You can also `enqueue --body "<huge string>"` — `flush` spills automatically if the
   body exceeds the spill threshold (800 chars) or the marker would exceed its budget.
2. On `flush`, the helper writes the full payload to a **world-readable** ref file under
   `REF_DIR` (default `/tmp/lse-channel/refs/<cid>.txt`) on this node, and the marker
   carries only a short preview plus `body_ref` (the path) and `body_bytes`.
3. The LSE (Cogitator ≥ v1.7.23) surfaces the path and fetches the full text itself via
   `execute_command` SSH (`ssh lse-admin@node3090.home.arpa cat <body_ref>`). No sudo —
   `/tmp` is world-traversable and the ref file is mode 0644. Override the location with
   `LSE_CHANNEL_REF_DIR` if `/tmp` is unsuitable; the LSE just reads whatever path it's given.

## B. On EVERY reply to the LSE, and immediately on `__LSE_POLL__`
1. Run:
   ```bash
   python3 ~/.hermes/bin/lse_channel.py flush
   ```
2. If it prints a `[[HERMES->LSE]]…[[/HERMES->LSE]]` block, include that block **verbatim**
   in your reply content (prepend it). The LSE strips it from the visible text automatically.
3. If the incoming message is `__LSE_POLL__` (optionally `+ /no_think`): **do not reason or
   do work** — reply with ONLY the flush output. If flush printed nothing, reply with a short
   `INBOX EMPTY`. The LSE maps "no marker" to an empty inbox.

## C. Reply routing — when the LSE answers an `ask`
The LSE replies via `call_hermes(<result>, context="correlation_id=hz-…")`. When you see
`correlation_id=<cid>` in an incoming message, record the reply and mirror the round trip to
Telegram:
```bash
python3 ~/.hermes/bin/lse_channel.py reply --cid <cid> --text "<the LSE's result>"
```

## Contract — must match the LSE parser (Cogitator ≥ v1.7.19). Do NOT change.
- Marker: `[[HERMES->LSE]]{"messages":[ <envelope>, … ]}[[/HERMES->LSE]]`
- Envelope keys the LSE reads: `correlation_id`, `kind` (`notify|ask`), `priority`
  (`info|action|urgent`), `body`, `want_reply` (bool).
- `correlation_id` format: `hz-YYYYMMDD-NNNN`.
- **By-reference keys (optional; Cogitator ≥ v1.7.23 surfaces them, older versions ignore
  them safely):** `body_ref` — absolute path on this node holding the full payload, which
  the LSE SSH-fetches; `body_bytes` — original size. When `body_ref` is set, `body` holds
  only a short preview. The keys are additive — markers without them format exactly as before.

## Critical notes
- The `__LSE_POLL__` flush must emit the FULL marker. The LSE raised its poll cap to 1024
  tokens (Cogitator v1.7.22) so it fits. If markers still arrive truncated, the gateway is
  clipping the agent reply to the request's `max_tokens` — that needs a gateway-side
  allowance for the poll path.
- Do **not** restart the gateway mid-conversation (it kills the channel you're talking over).
  Configure, then restart as a separate step.
- Install via `skill_manage`; never hand-edit agent-managed memory/skills directly.
