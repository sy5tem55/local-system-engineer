# ADR: A2A Web-Research Delegation — node3090 server + node4090 client

Status: accepted for implementation (plan 58fffd80, 2026-09-16)
Inputs: docs/A2A-PLAN-spec-notes.md (Step 1), docs/A2A-gateway-audit.md (Step 2),
KB f9ce9b992d53040b (A2A 1.0 spec, verified 2026-09-16), KB b63681fedec22641
(A2A-ORCH-001 decisions D1–D6), KB 72ef0d23dcf61050 (existing :9701 deployment).

## 1. Context

node4090's Goethe stack performs web research (search_reddit, fetch_url) via the
local SearxNG-only surface. node3090 runs firecrawl (general web) and camoufox
(JS-rendered, anti-bot, reddit) but exposes them only to the LSE tool layer.
Goal: node4090 delegates web-research tasks to a dedicated A2A server on
node3090 over the official A2A 1.0 protocol, with Ed25519 JWT auth, TLS,
append-only audit, and transparent local fallback when node3090 is unreachable.

This is task-level delegation to a specialized research agent — the A2A
problem, distinct from the 2026-08-18 peer-tool-access channel (MCP-solved).
Both channels coexist on node3090.

## 2. Roles & topology

| Role | Node | Port | Service |
|---|---|---|---|
| A2A web-research SERVER (new) | node3090 | 9701 (TLS) | /opt/local-se/a2a/web_research_server.py (a2a-sdk) |
| A2A CLIENT (new) | node4090 | — | /opt/local-se/a2a/a2a_client.py (library, used by goethe_web.py) |
| Existing A2A gateway (modified) | node4090 | 9701 (TLS after fix) | tools/goethe_a2a.py (goethe researcher, D1–D6) |
| MCP gateway (unchanged) | node4090 | 9700 | goethe_mcp.py, token-gated |
| Research backends | node3090 | — | firecrawl (general), camoufox (reddit) |
| Local fallback backends | node4090 | — | SearxNG :8088, curl |

Discovery: Direct_Configuration strategy (spec §8, strategy 3) — 2-node private
LAN, static relationship. Cards are static files pinned in config on each node;
conditional re-fetch via ETag where an HTTP fetch is used.

## 3. Decisions

### D-A: node3090 server
Standalone a2a-sdk service on :9701 (TLS). Endpoints: public GET /health and
GET /.well-known/agent-card.json; JWT-protected SendMessage, SendStreaming
(SSE), GetTask, ListTasks, CancelTask. Executor routing:
- host matches reddit.com / old.reddit.com → camoufox
- everything else → firecrawl
Result: structured Message/Artifact with Parts carrying source URL + excerpt.
SearxNG is NOT used on node3090 (node4090-only service).

### D-B: Ed25519 per-node keypairs + JWT flow
- Each node generates its OWN Ed25519 keypair locally. Private keys never
  cross the wire. Publics live in /opt/local-se/a2a/agent-cards/<node>.pub.
- JWT (PyJWT, alg EdDSA) claims enforced both ways: iss, aud, iat, nbf, exp,
  jti. exp default 600s; nbf skew tolerance 30s (clock_skew handling, R8).
- node4090 signs with node4090 key when calling node3090; node3090 verifies
  against node4090.pub. Reverse direction (node3090 → node4090 gateway)
  verifies node3090.pub against the modified goethe_a2a.py middleware.
- Shared module /opt/local-se/a2a/jwt_auth.py on both nodes:
  sign_ed25519_jwt() / verify_ed25519_jwt().
- Divergence from A2A-ORCH-001 D3 (single shared JWT, Vault-held key): that
  decision governed the node4090 :9700/:9701 pair. This ADR adds per-node
  asymmetric identity for cross-node A2A; the existing D3 mechanism on
  node4090 stays untouched.

### D-C: Static direct-config agent cards
Static JSON under /opt/local-se/a2a/agent-cards/:
- agent-card-node3090.json: name, url (https://node3090.home.arpa:9701),
  protocolVersion 1.0.0, capabilities {streaming: true}, skills
  (web-research, reddit-research with inputModes/outputModes),
  securitySchemes.bearer + Ed25519 public key, version field for ETag.
- agent-card-node4090.json: gateway card (goethe researcher).
Client pins the card path in config; revalidation = ETag conditional GET.

### D-D: TLS with self-signed CA + pinning
- One CA generated on node4090; server certs for node4090:9701 and
  node3090:9701 (SANs: hostname + LAN IP) signed by the CA.
- CA + cert/key files under /opt/local-se/a2a/certs/ on both nodes.
- Clients (a2a_client.py, curl-based probes) pin the CA fingerprint recorded
  in /opt/local-se/a2a/ca-fingerprint.txt on each node; mismatch = hard fail
  (no silent re-accept). Key rotation = new keypair + card version bump +
  fingerprint update on both nodes (R8 runbook).

### D-E: Append-only audit log
JSONL at /opt/local-se/a2a/logs/a2a-audit.jsonl on BOTH nodes. One line per
event, fields:
  ts (ISO8601 UTC), node, direction (outbound/inbound), task_id, jti,
  endpoint, routing (firecrawl|camoufox|local-fallback), status,
  latency_ms, error (nullable), client_iss
Append-only: opened O_APPEND, never truncated in place; review via
/opt/local-se/a2a/review_audit.sh (last N + counts + df check, exit code on
disk pressure). Rotation = new file + .1 suffix, never delete.

### D-F: Task lifecycle → D5 mapping
Reuses A2A-ORCH-001 D5 semantics so the node4090 orchestrator sees one
vocabulary:
- submitted → Run PENDING
- working → QUEUED/LEASED/RUNNING (retries invisible to client)
- completed → COMPLETED + result artifact (source URL/excerpt)
- canceled → CANCELED, terminal, no auto-retry (client may resubmit)
- failed → attempts exhausted, final message carries classification
  (deadline|lease-expiry|backend-down|policy)
- rejected → envelope/policy denial at submission, no Run created
- input-required: NOT used in v1 (operator/GUI-only approvals)
Per-task deadline (valve, default 300s) outranks attempt budget; exactly-once
result per idempotency key.

### D-G: node4090 client + fallback
/opt/local-se/a2a/a2a_client.py: send_message, stream_task, get_task,
health probe. Reachability gate: ping node3090 first; if down or /health
fails → transparent fallback: search_reddit/fetch_url in goethe_web.py use
local SearxNG/curl as today. Every delegation and every fallback is audit-
logged (routing=local-fallback). Fallback is transparent to the MCP caller —
same result shape, routing recorded in audit only.

### D-H: 9701 fix (node4090 existing gateway)
Precise change to tools/goethe_a2a.py JwtAuthMiddleware (audit §4):
- PUBLIC_PATHS becomes {"/health", "/.well-known/agent-card.json"}
- OPTIONS already passes (preflight) — keep
- GET on the two public paths: 200, no auth; all A2A methods
  (SendMessage/GetTask/ListTasks/CancelTask/JSON-RPC surface) remain
  401 without a valid Ed25519 JWT
- Middleware verifies against BOTH registered public keys: existing
  GOETHE_A2A_JWT_PUBKEY (D3, node4090 minted) AND node3090.pub (new, for
  cross-node calls)
- TLS: uvicorn served with node4090 cert/key from D-D; /health public over
  HTTPS, protected A2A endpoint returns 401 to unauthenticated HTTPS client
- No CORSMiddleware: browser clients are out of scope; the card is consumed
  by the A2A client library, not a browser page. The "browser 401" symptom is
  resolved by the public card path, not by opening auth.
Backup before modification (Step 4), py_compile + existing 16-test suite
after.

## 4. R8 failure modes (failure_mode table)

| failure_mode | Detection | Behavior | Operator action |
|---|---|---|---|
| node3090_down | ping fail or /health timeout (<5s) | client falls back to local SearxNG/curl; audit routing=local-fallback; wake_node offered in result metadata | wake_node, verify firecrawl/camoufox up |
| firecrawl_down | backend HTTP error/timeout during task | task retries within attempt budget; final classification 'backend-down'; audit entry | restart firecrawl container on node3090 |
| camoufox_down | same, reddit-routed tasks only | same classification; non-reddit tasks unaffected (firecrawl path) | restart camoufox; re-route reddit via firecrawl degraded |
| jwt_clock_skew | nbf/exp reject at verify | 401 with classification 'clock-skew' in audit; 30s nbf tolerance; no retry storm (max 1 re-mint) | time_check / NTP sync on offending node |
| audit_disk_full | df >90% on a2a log volume at write | writes continue (append), review_audit.sh exits non-zero, gateway surfaces AUDIT_DISK_PRESSURE in task metadata | rotate logs, free space |
| port_conflict_9700_9701 | bind fail at service start (EADDRINUSE) | service refuses to start, logs conflicting PID; NO silent port shift | identify holder (ss -ltnp), stop or reassign |
| ca_pin_mismatch | TLS verify against pinned fingerprint fails | hard fail, no fallback to local (a2a_client raises CA_MISMATCH), audit entry | key rotation runbook: new CA/certs + fingerprint on both nodes + card version bump |
| tls_cert_expired | cert validity check at client init | task fails classified 'cert-expiry' | re-issue from CA, bump card version |

## 5. Non-goals

- No GUI control plane (separate project, A2A-ORCH-001 D2)
- No push notifications (webhook) in v1 — polling/streaming only
- No registry-based discovery — Direct_Configuration only
- No changes to :9700 MCP surface or SearxNG
- No browser-facing endpoints on :9701

## 6. Acceptance (R7 E2E)

From node4090: MCP search_reddit(real topic) → A2A delegation to node3090 →
structured result with sources → one cited claim verified against its URL →
full round-trip present in audit log on both nodes. Fallback test (R8):
node3090 service stopped → same calls succeed via local SearxNG/curl with
routing=local-fallback in audit.
