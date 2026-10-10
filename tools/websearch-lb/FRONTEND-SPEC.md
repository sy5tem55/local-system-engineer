# WebSearch LB — Frontend Specification

> Everything needed to code a frontend for the WebSearch LB MCP server.
> Every value below was verified live against the running server on 2026-10-07
> (source read + real handshake/call captures), not from memory.
> If this doc and the live server disagree, the live server wins — re-run §12.

## 1. What it is
FastMCP web-search load balancer on node4090 (WSL2 Ubuntu 24.04). Routes one
query through 5 no-card-required backends in priority order with per-backend
circuit breaking, failover, and normalized results.
The frontend talks ONLY to the LB — never to upstream search APIs — and needs
no API keys of its own.

## 2. Live snapshot (2026-10-07)
- Process: pid 483515, `.venv/bin/python websearch_lb_server.py` (dir below)
- HTTP: `127.0.0.1:9703` — **loopback bind only**; remote browser access needs
  a tunnel or `WEBSEARCH_LB_HOST` change
- Endpoints: `POST /mcp` (MCP streamable HTTP, SSE-framed), `GET /health` (plain HTTP)
- serverInfo: `{"name":"websearch-lb","version":"1.30.0"}`, protocolVersion `2025-06-18`
- Token gate: **OFF** (`WEBSEARCH_LB_TOKEN` unset; `/mcp` currently open). If it
  gets enabled, every `/mcp*` request needs `Authorization: Bearer <token>`;
  `/health` stays open.
- Active priority: `["jina","firecrawl","exa","searxng","ddg"]` (default)

## 3. Architecture
```
frontend (SPA, same host)
  → http://127.0.0.1:9703/mcp (MCP streamable HTTP, SSE-framed)
  → FastMCP websearch-lb → Router → circuit breakers
      jina       GET  https://s.jina.ai/{query}?count=N     Bearer JINA_API_KEY
      firecrawl  POST https://api.firecrawl.dev/v1/search   keyless
      exa        POST https://api.exa.ai/search             x-api-key, metered
      searxng    GET  http://localhost:8088/search?format=json  local Docker
      ddg        ddgs python lib (in-process, no key)
  read_url tool: GET {WEBSEARCH_LB_JINA}/{url} (default https://r.jina.ai), keyless, 20 RPM
```

## 4. Transport contract (MCP streamable HTTP) — captured live
- `POST http://127.0.0.1:9703/mcp`
- Request headers: `Content-Type: application/json`,
  `Accept: application/json, text/event-stream`
- **Responses are SSE, not plain JSON** (`content-type: text/event-stream`):
  ```
  event: message
  data: {"jsonrpc":"2.0", ...}
  ```
  Frontend must parse SSE frames: split on `\n\n`, take the `data:` line, `JSON.parse`.
- Handshake (verified):
  1. `initialize`:
     `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"<ua>","version":"<v>"}}}`
     → HTTP 200 + **`mcp-session-id` response header**. Store it.
  2. `{"jsonrpc":"2.0","method":"notifications/initialized"}` (no id) with the
     `mcp-session-id` header.
  3. All further requests (`tools/list`, `tools/call`) must echo `mcp-session-id`.
- Tool call:
  `{"jsonrpc":"2.0","id":N,"method":"tools/call","params":{"name":"web_search_balanced","arguments":{...}}}`
- **Result envelope (captured live):** the tool's dict is JSON-serialized inside
  a text content block:
  ```json
  {"jsonrpc":"2.0","id":3,"result":{
     "content":[{"type":"text","text":"{\n  \"ok\": true, ..."}],
     "isError":false}}
  ```
  Parser: take `result.content[0].text` → `JSON.parse` → tool dict.

## 5. Tool contracts
### 5.1 web_search_balanced
Input schema (verbatim from `tools/list`):
```json
{"type":"object","required":["query"],"properties":{
  "query":{"type":"string"},
  "max_results":{"type":"integer","default":5},
  "backends":{"type":["array","null"],"items":{"type":"string"},"default":null}}}
```
`backends` = optional priority override. Unknown names are ignored;
known-but-unlisted backends are appended at the tail. `null` = server default.

Tool dict — success:
```json
{"ok":true,
 "results":[{"title":str,"url":str,"snippet":str,"rank":int,"backend":str,"latency_ms":int}],
 "per_backend":{"<name>":{"status":"ok","latency_ms":int,"n_results":int}}}
```
- `snippet` is truncated to **300 chars** server-side.
- Only the **first backend with ≥1 row** contributes results (rows capped at
  `max_results`); `per_backend` records every backend tried or skipped, in
  priority order, up to and including the winner.

`per_backend` status variants (exhaustive):
```json
{"status":"ok","latency_ms":2621,"n_results":2}
{"status":"ok_no_results","latency_ms":1200}
{"status":"error","error":"BackendError: jina HTTP 402: ...","latency_ms":3100}
{"status":"cooldown","detail":{"up":false,"consecutive_failures":0,
  "cooldown_until":12345.6,"last_latency_ms":2438}}
```
Total failure:
```json
{"ok":false,"results":[],"error":"all_backends_failed","per_backend":{...all 5...}}
```

### 5.2 read_url
Input: `{"url":{"type":"string"}}` (required).
```json
{"ok":true,"url":str,"markdown":str}
{"ok":false,"error":"jina_rate_limited","detail":"20 RPM keyless cap; retry later"}
{"ok":false,"error":"jina_http_<code>","detail":"<body truncated 200 chars>"}
```

## 6. /health (plain HTTP, no MCP framing)
`GET http://127.0.0.1:9703/health` — live example:
```json
{"status":"ok","priority":["jina","firecrawl","exa","searxng","ddg"],
 "backends":{"jina":{"up":true,"consecutive_failures":0,
   "cooldown_until":null,"last_latency_ms":2438}, "...one per registered backend..."}}
```
- `cooldown_until` is a **`time.monotonic()` value, not wall clock** — don't
  render it as a wall-clock countdown; display `up` + `last_latency_ms` instead.
- A backend missing from `backends` entirely = not registered (jina is absent
  when `JINA_API_KEY` is empty).

## 7. Backend reference
| name | upstream | auth | notes |
|---|---|---|---|
| jina | GET `s.jina.ai/{query}?count=N` | Bearer `JINA_API_KEY` | no key → backend not registered at all |
| firecrawl | POST `api.firecrawl.dev/v1/search` | none | keyless |
| exa | POST `api.exa.ai/search` | `x-api-key` `EXA_API_KEY` | metered; HTTP 402 → hard fail → failover |
| searxng | GET `localhost:8088/search?format=json` | none | local Docker, engines vary |
| ddg | `ddgs` python lib (in-process) | none | slowest tier |

Default priority `jina → firecrawl → exa → searxng → ddg`;
`WEBSEARCH_LB_PRIORITY` (comma list) overrides at process level.

## 8. Router / breaker semantics (what the status UI should convey)
- Breaker opens after **2 consecutive failures** (hard OR soft) → backend
  skipped for **300 s** (`WEBSEARCH_LB_COOLDOWN_S`); count resets on open.
- Any success resets the failure count.
- Soft fail = upstream 200 but zero rows (counts as failure, tries next backend).
- Hard fail = network/HTTP/auth/timeout.
- Per-backend timeout **10 s** (`WEBSEARCH_LB_TIMEOUT_S`), applied twice
  (httpx client + `asyncio.wait_for`).
- Observed latencies: single backend call can take 2–3 s (live: jina 2438–2621 ms)
  → UI request timeout should be ≥ 15 s.

## 9. Config reference (env only — never hardcode)
Server env (set in `websearch-lb.env` + launcher; secrets stay server-side):
| var | default | meaning |
|---|---|---|
| `WEBSEARCH_LB_HOST` | `127.0.0.1` | bind host |
| `WEBSEARCH_LB_PORT` | `9703` | bind port |
| `WEBSEARCH_LB_TIMEOUT_S` | `10` | per-backend timeout (s) |
| `WEBSEARCH_LB_COOLDOWN_S` | `300` | breaker cooldown (s) |
| `WEBSEARCH_LB_PRIORITY` | `jina,firecrawl,exa,searxng,ddg` | priority order |
| `WEBSEARCH_LB_TOKEN` | unset (gate OFF) | Bearer token required on `/mcp*` if set |
| `WEBSEARCH_LB_JINA` | `https://r.jina.ai` | reader base URL for `read_url` |
| `WEBSEARCH_LB_USAGE_LOG` | `/tmp/lse/websearch-lb/usage.jsonl` | usage log path |
| `EXA_API_KEY`, `JINA_API_KEY` | — | in `websearch-lb.env` (chmod 600) |

**Frontend config = `BASE_URL` (and `TOKEN` only if the gate gets enabled).**

## 10. Operations (user-level, no sudo)
- Status: `pgrep -af websearch_lb` · `curl -s http://127.0.0.1:9703/health`
- Start: `bash .../tools/websearch-lb/start-websearch-lb.sh`
  (idempotent — exits 0 if already running; kill first to restart)
- Restart: `pkill -f 'websearch_lb_[s]erver.py' && bash start-websearch-lb.sh`
- Server log: `/tmp/websearch-lb.log` (uvicorn, appends)
- Usage log: `/tmp/lse/websearch-lb/usage.jsonl`, one JSON per call:
  `{"ts":<epoch>,"query_hash":<sha256[:16]>,"ok":bool,"backends":{name:status}}`
  (query hashes only — no raw queries)
- Contract tests: `.venv/bin/python test_websearch_lb.py` (13/13)
- Files (dir `/home/sy5/projects/local-system-engineer/tools/websearch-lb/`):
  `websearch_lb_server.py` (326 lines — single source of truth),
  `start-websearch-lb.sh`, `test_websearch_lb.py`, `websearch-lb.env`

## 11. Frontend build list
**Must-have**
1. Search form: `query` (required), `max_results` (1–10, default 5), optional
   backend multi-select — pre-select from `/health` priority; checked set in
   display order = `backends` override, none/empty = `null` (server default).
2. Results view: ranked cards — rank, title (link, `target=_blank`), backend
   badge, latency_ms, snippet (≤300 chars, no truncation needed client-side).
3. Per-request diagnostics strip: one status chip per backend —
   ok / ok_no_results / error (with message) / cooldown.
4. `read_url` expansion: "Read full page" per result → inline markdown panel;
   surface `jina_rate_limited` as "20 RPM cap — retry later", **no auto-retry**.
5. Health widget: poll `GET /health` every 5–10 s — per-backend up/down,
   last latency, active priority.
6. Error states: `all_backends_failed` → show per-backend error details;
   SSE/JSON parse failure → raw-response inspector panel.

**Nice-to-have:** client-side query history, latency history (from
`usage.jsonl` if served), dark theme.

**Constraints / gotchas**
- Server is loopback-bound: run the frontend on node4090 (any static server,
  e.g. `python -m http.server` on 127.0.0.1) or tunnel; Windows-host browsers
  need a WSL NAT exception to reach 127.0.0.1:9703.
- Responses to `/mcp` are **SSE frames** — do not `response.json()` directly.
- `mcp-session-id` header is mandatory after `initialize`.
- No secrets in the frontend; one-time cost is the 3-step MCP handshake.
- Expect multi-second first-backend latency; spinner ≥ 15 s timeout.
- Jina reader 20 RPM keyless; exa metered — never auto-retry rate limits.

## 12. Pre-build contract verification (re-run; live server wins)
```bash
curl -s http://127.0.0.1:9703/health
# initialize (capture mcp-session-id header), then tools/list, then tools/call:
curl -s -D - -X POST http://127.0.0.1:9703/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
.venv/bin/python test_websearch_lb.py    # expect: ALL 13 TESTS PASSED
```

## 13. Provenance
- Verified live 2026-10-07: `/health` probe; MCP `initialize` / `tools/list` /
  `tools/call` handshake captures (jina winner, 2621 ms); full source read
  (326 lines); launcher + test suite read.
- KB doc: `b21ad9d8b50dcbec` (topic `searxng`) — server overview incl. jina backend.
- Ledgers: `ed483269` (initial build), `e687fd14` (jina backend).
- Design notes: `/tmp/lse/websearch-lb-design.md`.
