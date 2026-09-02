# 11 — Node Agent Delegation

Why `query_node_agent()` talks to a node's plain llama-server instead of its
Goethe gateway, and why that separation is load-bearing rather than an oversight.

## The two endpoints on a GPU node

| Endpoint | What it is | Tools |
|---|---|---|
| llama-server (`agent_port` from `_NODE_REGISTRY`) | Plain OpenAI-compatible `/v1/chat/completions` | NONE — a no-tools system prompt is injected on every call |
| goethe_mcp gateway :9700 (node3090) | Full Goethe tool surface, token-gated | YES — called directly by llama-ui from the browser |

## Why query_node_agent never touches the gateway

1. **Blast radius.** Delegated inference is "think for me" work: summarise,
   review, second-opinion. Routing it through a tool-bearing agent would let a
   delegated prompt trigger side effects on the node it was only asked to think on.
2. **Load separation.** The gateway serves the interactive UI. Node-inference
   delegation is batch-ish and can run long; mixing the two queues starves the UI.
3. **Auth boundary.** The gateway is token-gated for the UI's browser origin.
   In-process delegation (LUCIFER → node) needs no second credential path.

## Consequences

- A tool-call block in a `query_node_agent` response is a hallucination —
  nothing ran. The caller (LUCIFER) must carry out any proposed action itself,
  after review, via execute_command / ssh_run.
- The node must be awake (`wake_node`) before querying. The endpoint comes from
  `_NODE_REGISTRY[node]["agent_port"]`, never a hardcoded port (8081 was LM
  Studio, decommissioned).
- Drift between `agent_profile` and the live server: run
  `check_node_agent_drift` before `start_node_agent` / `stop_node_agent`.

Reconstructed 2026-08-30 from the `query_node_agent` docstring (task 85375467)
— the file was referenced by the tool contract but missing from the repo.
