# A2A Gateway Audit — node4090 :9701 (Step 2)

Probed live 2026-09-16 (ss, pgrep, systemctl --user, find, source read).
Source: /home/sy5/projects/local-system-engineer/tools/goethe_a2a.py (733 lines)
Tests: tests/test_a2a_adapter.py (16 tests per KB 72ef0d23dcf61050)
Log: /tmp/goethe-a2a.log

## 1. Process & binding (live)

- pid 1254557: `/home/sy5/owui/bin/python3 .../tools/goethe_a2a.py`
- LISTEN **0.0.0.0:9701** (python3) — LAN-reachable, not loopback-only
- :9700 = goethe_mcp gateway (pid 1594469), token-gated streamable HTTP
- NOT a systemd unit — plain background process (systemctl --user shows no
  a2a unit). Start-on-demand per KB 72ef0d23dcf61050.
- Config default in code (line 677/731): GOETHE_A2A_HOST defaults to
  **0.0.0.0** — the currently running instance uses that default. The KB's
  verified start command used GOETHE_A2A_HOST=127.0.0.1; live state differs.

## 2. Valve/config surface

| Env | Default | Purpose |
|---|---|---|
| GOETHE_A2A_ENABLED | off | master valve |
| GOETHE_A2A_JWT_PUBKEY | (unset) | Ed25519 public key PEM; unset → fail-closed 503 on authed paths |
| GOETHE_A2A_HOST | 0.0.0.0 | bind address |
| GOETHE_A2A_PORT | 9701 | port |
| GOETHE_A2A_EVENTS_DB | shared default | event journal (SQLite) |
| GOETHE_A2A_MAX_ATTEMPTS | 2 | attempt budget per task |
| GOETHE_A2A_ATTEMPT_TTL_S | 600 | envelope TTL per attempt |
| GOETHE_A2A_DEFAULT_DEADLINE_S | 300 | per-task deadline (D5a: outranks budget) |
| GOETHE_EXECUTION_BACKEND | local | executor backend |

## 3. Current auth mechanism (D3)

`JwtAuthMiddleware` (Starlette BaseHTTPMiddleware, lines ~189–227):

- PUBLIC_PATHS = {"/health"} — the ONLY unauthenticated path
- `OPTIONS` requests pass through (preflight)
- Every other path requires `Authorization: Bearer <token>`
- Token verified via PyJWT `jwt.decode(token, pub_pem, algorithms=["EdDSA"])`
  against GOETHE_A2A_JWT_PUBKEY
- Fail-closed: no pubkey configured → 503 "server misconfigured" on authed paths
- Missing/malformed/invalid token → 401 `{"error": "unauthorized"}`
- Token minting (KB 72ef0d23dcf61050): sign with the Ed25519 PRIVATE key from
  Vaultwarden item `goethe-a2a-jwt-key` (claims iss/sub/exp, alg EdDSA).
  WARNING: Vaultwarden item `goethe-a2a-token` (64-hex) is NOT a JWT and will
  NOT pass the EdDSA verifier.

## 4. Why a browser request without a token gets 401

Root cause chain:
1. Agent card served at `/.well-known/agent-card.json` — **not** in
   PUBLIC_PATHS → 401 without a Bearer token.
2. Browsers cannot attach a custom Authorization header to cross-origin
   requests without CORS preflight approval, and the app registers **no
   CORSMiddleware** (no CORS handling anywhere in goethe_a2a.py) → browser
   fetches are additionally blocked at the browser level.
3. The 401 itself is spec-correct (A2A §7.4: server MUST authenticate every
   request) — the problem is the *surface*: no public card/health discovery
   path for a browser client to bootstrap from.

Fix scope (plan step 11): allow public GET /health, agent-card, and OPTIONS;
verify Ed25519 JWT with node3090 public key; serve HTTPS with node4090 cert
(step 5); keep 401 on protected A2A endpoints.

## 5. Agent card (current)

`generate_agent_card(tool_policy_ref, jwt_pubkey_pem)` (line ~603):
- name=goethe, version=<0.1.0>+policy.<12-hex hash> (bumps on policy change)
- capabilities: streaming=true, pushNotifications=absent
- skill id: goethe-researcher-v1
- securitySchemes.bearer.httpAuthSecurityScheme.bearerFormat = Ed25519 pubkey PEM
- Without pubkey: card carries no auth scheme

## 6. Executor (Tier-1 pipeline) — relevant to the new node3090 server

- search_kb → delegated to :9700 gateway MCP surface (tools/call round-trip)
- research_web → **direct to local SearxNG** (node4090-only service)
- D4 ToolBroker gate: >=1 search_kb before first research_web per task;
  violation → task fails classified 'policy' with POLICY_VIOLATION
- IMPLICATION: the new node3090 web-research server CANNOT reuse this
  executor — it must route reddit→camoufox, everything else→firecrawl
  (both node3090 services).

## 7. State mapping (D5, in effect)

submitted→Run PENDING · working→QUEUED/LEASED/RUNNING · completed→COMPLETED
+result artifact · canceled→CANCELED terminal, no auto-retry · failed→attempts
exhausted with classification (deadline/lease/OOM/policy) · rejected→envelope
denial, no Run. input-required NOT used in v1. D5a: per-task deadline outranks
attempt budget; exactly-once result per idempotency key.

## 8. Rollback & backups

- Valve GOETHE_A2A_ENABLED=off keeps the :9700 MCP-only surface unchanged
- Existing backup of goethe_mcp.py: /opt/local-se/bkp/goethe_mcp.py_20260914_092710
- Step 4 of the plan backs up goethe_a2a.py before any modification
