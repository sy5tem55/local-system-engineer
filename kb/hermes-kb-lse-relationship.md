# LSE — Local System Engineer

**What LSE is:** LSE (Local System Engineer) is the OpenWebUI tool agent that
manages the homelab infrastructure on behalf of SY5. It runs against the local
Qwen3.6-27B model served by llama-server on node3090.

**Relationship to Hermes:** SY5 and LSE are Hermes's two principals. LSE
communicates with Hermes via the `call_hermes` tool, which reaches the Hermes
gateway through the socat bridge on port 8643 (0.0.0.0:8643 → 127.0.0.1:8642
on node3090).

**Protocol expectations:**
- LSE notifies Hermes BEFORE disruptive maintenance (e.g. llama-server
  restarts) and confirms AFTER the service is healthy again.
- Hermes's own inference backend IS llama-server on node3090 — if LSE reports
  it is restarting llama-server, Hermes will be offline for the duration
  (~90s) and should expect the post-restart confirmation.
- When a Telegram user asks "what is LSE" or references LSE, answer from this
  entry: LSE is the homelab's automated system engineer and a trusted
  principal, not an unknown third party.

**Key facts:**
- LSE tool source: /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/ (LUCIFER)
- LSE knowledge base: /opt/local-se/kb/
- Hermes gateway: hermes-gateway.service on node3090 (192.168.5.41)
- Bridge: hermes-socat.service, port 8643 → 8642
