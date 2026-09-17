# A2A Protocol — Spec Notes (Step 1 of A2A web-research delegation plan)

- Fetched: 2026-09-16 (live fetch + verify_source_claims this session)
- Sources:
  - https://a2a-protocol.org/latest/specification/ (official spec)
  - https://raw.githubusercontent.com/a2aproject/A2A/main/docs/topics/agent-discovery.md (repo main, raw)
  - KB f9ce9b992d53040b (quality 0.80, verified 2026-09-16) for §7 auth detail and SDK pin
- Provenance rule: every value below is either FOUND by verify_source_claims this
  session (marked VERIFIED) or taken from KB f9ce9b992d53040b (marked KB).

## Latest_Released_Version

- Latest_Released_Version: **1.0.0** (VERIFIED, spec page header, verbatim:
  "Latest Released Version 1.0.0")
- Previous versions: 0.3.0, 0.2.6, 0.1.0 (VERIFIED, same header line)
- Repo: a2aproject/A2A (Linux Foundation, ex-Google). Repo release tag v1.0.1
  published 2026-05-28 (KB, get_github_release-confirmed).
- Installed SDK on node4090: a2a-sdk 1.1.2 (KB). Pin at install time on
  node3090 — verify, do not guess.
- Normative source: spec/a2a.proto is the single authoritative definition of all
  data objects; JSON artifacts and SDKs are generated from it (VERIFIED, §1.4).

## Agent Card — required/expected fields (VERIFIED via agent-discovery.md)

- Identity: `name`, `description`, `provider`
- Service endpoint: `url`
- Capabilities: `streaming`, `pushNotifications`
- Authentication: `securitySchemes` — `schemes` e.g. "Bearer", "OAuth2"
  (spec §7.3: card declares schemes; credentials acquired OUT-OF-BAND)
- Skills: `AgentSkill` objects — `id`, `name`, `description`, `inputModes`,
  `outputModes`, `examples`
- Versioning/caching: `version` field feeds `ETag` (VERIFIED: "ETag header —
  derived from the card's version field or a content hash")
- Card MAY be JWS-signed (RFC 7515, JCS RFC 8785) (KB, spec §8.4)
- Extended (authenticated) card: spec §3.1.11 "Get Extended Agent Card" —
  client fetches a more detailed card after out-of-band credential acquisition
  (VERIFIED: present in spec TOC §6.9)

## Task lifecycle states

- Terminal states (VERIFIED, spec §3.1.1, verbatim): TASK_STATE_COMPLETED,
  TASK_STATE_FAILED, TASK_STATE_CANCELED, TASK_STATE_REJECTED
- Messages sent to terminal-state tasks → UnsupportedOperationError (VERIFIED)
- Non-terminal states (KB, spec §4): TASK_STATE_SUBMITTED, TASK_STATE_WORKING,
  TASK_STATE_INPUT_REQUIRED, TASK_STATE_AUTH_REQUIRED
  (TASK_STATE_AUTH_REQUIRED: KB-verified 2026-09-16; NOT re-found in this
  session's fetch window — re-verify against spec §4 before relying on it)
- Our D5 mapping (KB b63681fedec22641): submitted→PENDING, working→
  QUEUED/LEASED/RUNNING, completed→COMPLETED+artifact, canceled→CANCELED
  terminal no auto-retry, failed→attempts exhausted with classification,
  rejected→envelope/policy denial. input-required NOT used in v1.

## Message & Parts (VERIFIED, spec §2.2)

- Message: communication turn, role "user" or "agent", contains one or more Parts
- Part: smallest content unit — text, file reference, or structured data
- Artifact: task output composed of Parts
- Context: optional identifier grouping related tasks/messages
- Send Message returns Task OR direct Message; MUST return immediately;
  processing continues async (VERIFIED, §3.1.1)

## Streaming (SSE) events (VERIFIED, spec §3.1.2)

- Stream patterns (MUST be one of):
  1. Message-only stream: exactly one Message, then close
  2. Task lifecycle stream: Task first, then zero or more
     TaskStatusUpdateEvent / TaskArtifactUpdateEvent, closes at terminal state
- Errors: UnsupportedOperationError (streaming not supported / terminal task),
  ContentTypeNotSupportedError, TaskNotFoundError

## Auth requirements (KB, spec §7 — verified 2026-09-16)

- §7.1: production deployments MUST use TLS (TLS 1.3+ recommended)
- §7.3 client process: (1) discover schemes via card `securitySchemes`,
  (2) acquire credentials out-of-band, (3) include credentials in protocol
  headers on EVERY request
- §7.4: server MUST authenticate every incoming request
- §7.6: in-task authorization via TASK_STATE_AUTH_REQUIRED
- Design mapping (our D3): card declares bearer scheme + Ed25519 pubkey PEM;
  node4090 mints EdDSA JWT (out-of-band); node3090 verifies every request.
  Existing deployment precedent: tools/goethe_a2a.py on :9701 (KB
  72ef0d23dcf61050) — /health public, all other paths 401 without valid JWT,
  fails closed if pubkey unset.

## Direct_Configuration / discovery strategy (VERIFIED, agent-discovery.md §3)

Three strategies, in spec order:
1. Well-Known URI: `https://{domain}/.well-known/agent-card.json` (RFC 8615) —
   public/domain-controlled discovery
2. Curated registries — enterprise; no standard API prescribed by spec
3. Direct_Configuration / Private Discovery: "used for tightly coupled systems,
   private agents, or development purposes" — client pre-configured with card
   URL or content

Decision for this deployment: **strategy 3 (Direct_Configuration)** — 2-node
private LAN, static relationship. Card content cached locally; conditional
re-fetch via ETag (Cache-Control + ETag, VERIFIED).

Caching (VERIFIED): server SHOULD send Cache-Control max-age + ETag; client
SHOULD honor, use If-None-Match / If-Modified-Since on expiry.

## Operations surface (VERIFIED, spec §3.1 + TOC)

- Core: Send Message, Send Streaming Message, Get Task, List Tasks, Cancel
  Task, Get Agent Card (+ Get Extended Agent Card)
- Bindings: JSON-RPC 2.0 over HTTP(S) (VERIFIED), gRPC (HTTP/2), HTTP+JSON/REST
- Push notifications: server-initiated HTTP POST to client webhook (long-running
  / disconnected scenarios)

## Gaps vs spec for this deployment (KB f9ce9b992d53040b)

1. TLS is spec-MUST — LAN HTTP acceptable for pilot only; plan step 5 adds
   self-signed CA + per-node certs for :9701 on both nodes
2. node3090 WoL lifecycle — client MUST probe public /health before delegating
   (wake_node first, or keep A2A+firecrawl+camoufox always-on)
3. Scope note: KB 7177b1b9c3769368's 2026-08-18 A2A rejection was scoped to the
   PEER TOOL-ACCESS channel (solved by native MCP client); task-level
   delegation to a specialized research agent is the A2A problem. Both channels
   coexist on node3090.

## Executor routing (design input for steps 9–13)

- reddit.com / old.reddit.com → camoufox (JS render, anti-bot)
- everything else → firecrawl (faster, structured extraction)
- SearxNG is node4090-only — node3090 executor must NOT use it
