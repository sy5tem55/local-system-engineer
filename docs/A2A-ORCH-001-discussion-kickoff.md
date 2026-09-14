# A2A-ORCH-001 Discussion Kickoff

**Status:** ALL SIX QUESTIONS RESOLVED 2026-09-14 (Q5 adopted with two hardening rules); GUI control plane (A2A + Ray) scoped as a separate project; ready for Phase 6+ planning; no implementation yet
**Date:** 2026-09-14
**Companion to:** ADR-ORCH-001 (Goethe distributed task contracts), Phase 6+

## Context

ADR-ORCH-001 defers A2A to Phase 6+: "optional A2A 1.0 adapter ... maps one
external Goethe agent to Runs/Tasks; it does not expose node3090, node4090,
node5090, or internal Ray actors as public agents." The deferral was conditioned
on inspecting the existing MCP SDK/version and operating deployment. That
inspection is done (2026-09-14): MCP SDK = mcp 1.26.0 in the /home/sy5/owui venv
(no fastmcp module); gateway goethe_mcp.py v1.13.0 exposes 48 tools over
streamable HTTP on :9700 (token-gated; also serves the ledger UI at /ui).

Current phase state (see KB 034785138164e3a8): Phases 1-3 implemented, covered
by the 19-test local integration suite (re-verified 2026-09-14, 19 passed);
Phase 4 network prerequisites and the first cross-VLAN cluster verified, with
remaining items pending (capacity reservations, scheduler policy tuning, Grafana
panels, failure injection); Phase 5 (Redis Streams event log) not deployed.

## Scope

- One external Goethe agent, mapped to internal Runs/Tasks. A2A is a client-
  boundary adapter, not a second orchestrator: it translates A2A AgentCard/task
  semantics into Run/Task/Attempt records in the existing ledger.
- Internal Ray topology (NodeSupervisor/ModelExecutor actors, GPU reservations,
  cluster membership) is never exposed through A2A.
- ToolBroker tiering carries over unchanged: Tier-1 read-only tool policies are
  the only ones reachable for A2A-mediated work; Tier-2 remains an
  orchestrator-held approval workflow; Tier-3 is never delegated.
- The adapter is optional and valve-gated (following the existing valve
  convention, e.g. GOETHE_A2A_ENABLED), default off, with rollback to the
  current MCP-only surface.

## Non-Goals

- No public exposure of node3090, node4090, or node5090 as A2A agents.
- No internal Ray actor as a public agent.
- No remote shell/write tools for A2A-mediated work (acceptance item 7: tool
  policy denies a remote shell/write request even if the model emits it).
- No exposure of event log, artifact store, or ledger internals beyond the
  result summary/evidence contract.
- No new task database: A2A tasks map onto existing Runs/Tasks in the Goethe
  ledger.

## Open Questions

1. SDK choice: mcp 1.26.0 has no fastmcp — implement A2A 1.0 as a thin adapter
   on the existing gateway (9700), or adopt a dedicated A2A SDK/library?
   **RESOLVED 2026-09-14:** dedicated A2A SDK (see Decision Log).
2. Transport: extend the existing streamable-HTTP endpoint on :9700 with an
   A2A route, or stand up a new port/service?
   **RESOLVED 2026-09-14:** :9701, standalone service; control plane in the Goethe GUI (see Decision Log).
3. Auth: reuse the GOETHE_MCP_TOKEN bearer, or issue a separate A2A token?
   (The ADR forbids reusing GOETHE_MCP_TOKEN for Ray; the same hygiene logic
   may apply to A2A.)
   **RESOLVED 2026-09-14:** one shared JWT token for :9700 + A2A, stored in Vaultwarden as `goethe-a2a-token` (see Decision Log).
4. Audit trail (acceptance item 6): how does an A2A-mediated remote researcher
   end up calling only ToolBroker.research_web, and how is the enforced
   search_kb -> web fallback ordering recorded so it is auditable from the
   A2A side?
   **RESOLVED 2026-09-14:** hard gate in ToolBroker, per-task granularity (>=1 search_kb before first research_web in the task); on violation -> refuse call + POLICY_VIOLATION event surfaced in the A2A result. Hard-refuse for A2A-mediated runs, soft-flag for local. (The tool-restriction half is already enforced via the immutable ToolPolicyRef.)
5. Failure semantics: how do A2A task cancellation/timeout map to orchestrator
   lease expiry and attempt states (LEASED -> CANCELED, TIMED_OUT, retry
   classification)?
   **RESOLVED 2026-09-14:** mapping adopted as drafted (submitted=Run PENDING; working=QUEUED/LEASED/RUNNING, retries invisible to client; completed=COMPLETED+result artifact; canceled=attempt CANCELED, lease released, TERMINAL no auto-retry; failed=attempts exhausted, final message carries classification; rejected=denial at submission, no Run; input-required unused in v1 — Tier-2 stays operator/GUI-only). Hardening: (a) deadline outranks attempt budget — retries stop at envelope deadline, expiry = failed(classified: deadline), valve-configurable default deadline; (b) exactly-once result — distinct idempotency keys per attempt, A2A surface emits exactly one result per task.
6. AgentCard contents: which capabilities/roles does the single external
   Goethe agent advertise, and how do versioned agent profiles (e.g.
   researcher) map to A2A skills?
   **RESOLVED 2026-09-14:** AgentCard generated from the live ToolPolicyRef (policy change -> card change); v1 = agent `goethe`, single skill `goethe-researcher-v1` (Tier-1 research only); capabilities: streaming + stateTransitionHistory, no pushNotifications; auth: bearer JWT; card version bumps on any profile/policy change. Rendering in the GUI control plane belongs to the separate control-plane project.

## Decision Log

| Date | Decision | Owner | Rationale |
| --- | --- | --- | --- |
| 2026-09-14 | SDK: adopt a dedicated A2A SDK as a standalone service — not a thin adapter on the :9700 gateway | operator | Keeps the 48-tool MCP gateway stable; A2A 1.0 semantics (AgentCard, tasks, streaming) map cleanly onto Runs/Tasks |
| 2026-09-14 | Auth: single SSO token for A2A, stored in Vaultwarden — no second parallel token regime | operator | One credential surface, vault-managed rotation; consistent with the ADR hygiene rule against reusing GOETHE_MCP_TOKEN |
| 2026-09-14 | Transport: standalone A2A service on :9701; control plane (start/stop, status, AgentCard, token state) implemented in the Goethe GUI (WinUI 3/.NET, Goethe.App) — not in shell scripts | operator | GUI is the operator's control surface; :9700 gateway stays a pure MCP surface |
| 2026-09-14 | Auth detail: SSO = one shared JWT token for :9700 and A2A; stored in Vaultwarden as `goethe-a2a-token` | operator | One token, one vault item, both surfaces; JWT allows expiry/claims without rotation |
| 2026-09-14 | Scope: A2A and Ray control plane in the Goethe GUI is a SEPARATE project; the LSE stack, including the A2A service, stays in Python (a2a-sdk) — Phase 6+ A2A scope excludes GUI work | operator | Keeps the A2A build on the existing Python toolchain; GUI panels deferred to their own project |
| 2026-09-14 | Q3 key management: asymmetric Ed25519 — private signing key in Vaultwarden (`goethe-a2a-jwt-key`), public key embedded in the AgentCard's auth section; both :9700 and :9701 verify, only the gateway (issuer) signs | operator + agent | Token holders cannot forge tokens; rotation = new keypair in Vault + card version bump; no shared symmetric secret across surfaces |
| 2026-09-14 | Q4 audit trail: hard gate in ToolBroker, per-task granularity (>=1 search_kb before first research_web per task); violation -> refuse call + POLICY_VIOLATION event in the A2A result; hard-refuse for A2A runs, soft-flag for local | operator + agent | ADR acceptance item 6 demands an 'enforced' ordering, not prompt-level; ToolBroker is the only chokepoint; tool restriction already enforced via ToolPolicyRef |
| 2026-09-14 | Q6 AgentCard: generated from the live ToolPolicyRef; v1 = agent `goethe` + skill `goethe-researcher-v1` (Tier-1 only), streaming + stateTransitionHistory, no pushNotifications, bearer JWT, version bump on profile/policy change | operator + agent | The card must never promise what the policy denies; GUI rendering deferred with the control-plane project |
| 2026-09-14 | Q5 failure semantics: mapping adopted as drafted — cancel=TERMINAL no auto-retry; lease-expiry=TIMED_OUT retryable per TaskEnvelope, invisible to client; rejected at submission (no Run); input-required unused in v1 (Tier-2 operator/GUI-only); failed carries classification. Hardening: deadline outranks attempt budget (valve-configurable default deadline); exactly-once result via idempotency_key dedupe | operator + agent | A2A has no built-in task timeout — client cancel (decision, terminal) vs lease expiry (accident, retryable) must not be conflated; all internal machinery already exists in the ADR, Q5 is boundary translation only |

## Cross-References

- ADR: /home/sy5/projects/local-system-engineer/docs/ADR-ORCH-001-distributed-task-contracts.md (canonical; Claude-mirror copy abandoned 2026-09-14)
- KB 034785138164e3a8 — ADR-ORCH-001 operative state (phase status, 19-test suite, rollback valves, 14 config names, A2A deferral)
- KB 4017ddb60ebe68e2 — Ray observability state + token storage
- KB 444c3d5ea7a528ff — Ray cluster cross-VLAN verified
- KB 2ef82c34997d6084 — Ray 2.58.0 audit (advisories, token auth, ports)
