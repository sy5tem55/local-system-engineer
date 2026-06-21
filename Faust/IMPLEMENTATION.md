# Faust — Implementation Ledger

> Living record of what's been built, what's approved-but-pending, and what's only
> proposed. **Update this file at the end of every planning/implementation session**
> so the next session (human or agent) starts from ground truth instead of re-deriving it.
> Status keys: ✅ implemented · 🟡 approved, not yet built · 💡 proposed · ⏸ deferred.

Last updated: 2026-06-19 (P31).

---

## Core platform (Coding Gauntlet → Faust v0.1.0)

| Capability | Status | Where |
|---|---|---|
| Group chat: auth, rooms, membership, REST + WebSocket, SQLite | ✅ | `gate2-group-server/src/{server,db,auth}.ts` |
| Admin actions: delete/clear room, delete message, kick | ✅ | `server.ts` (admin-gated) |
| Mention-reply orchestration (server-called agents, turn budget) | ✅ | `orchestrator.ts` (`MentionReplyPolicy`) |
| Single-file web client (opencode style) | ✅ | `gate2-group-server/web/index.html` |
| Presence / live member list | ✅ | `GET /rooms/:id/presence` (connected+subscribed accounts w/ handles); web client shows `● online: …` in the room header, refreshed on `presence` WS frames |
| **Optional TLS (HTTPS + WSS)** for browsers/iPad | ✅ | `server.ts`: plain HTTP stays on `PORT` (localhost agents unchanged); when `TLS_CERT`+`TLS_KEY` set, a 2nd listener serves HTTPS/WSS on `TLS_PORT` (default 8443) sharing the same handlers. Web client auto-derives `wss://` from `https://`. Use mkcert for a LAN-trusted cert; install its root CA on the iPad. Verified: http + https + wss all serve. |
| Capability-sandboxed plugin host (subprocess, `--permission`) | ✅ | `gate2-group-server/src/{host,registry,sandbox,plugin-contract}.ts`, `plugin-runner.js` |
| `/search` reference plugin | ✅ | `gate2-group-server/plugins/search/` |
| Reconnecting agent client (durable key + backoff + `on_cue`) | ✅ | `agent-client/` (JS + Python), `reconnect-test.*` verify restart survival |
| LSE Faust sidecar (cue → llama-server `:8080` → post) | ✅ | `agent-client/lse-sidecar.py`, `sidecar_test.py` (verified converge) |
| **Goethe↔Faust execution bridge** (ReAct executor runs `@lse` assignments) | ✅ | `agent-client/goethe_executor.py` (imports Goethe `Tools`, drives llama-server ReAct, gates enforced); `lse-sidecar.py` ledger trigger; `exec_test.py` (verified plan→approve→task→execute) |
| Generic model agent (`claude` etc. via any OpenAI-compatible endpoint) | ✅ | `agent-client/model-agent.py` — reconnecting client + `on_cue`→`MODEL_URL`; e.g. Claude via OWUI Opus preset. Reasoning-only. Add handle to `AGENT_HANDLES`. |
| **Server-supervised agent sidecars** (start/restart/stop with the server) | ✅ | `src/supervisor.ts` (`AgentSupervisor`: spawn as managed child, exp-backoff restart on crash, kill on shutdown). Opt-in `AGENT_SIDECARS=lse`; specs from `agents.json` or built-in default; secrets as `${VAR}` from launch env. `/agents` status, `/agent <name> start\|stop\|restart` (admin). Verified: start→up, restart→+1, stop→frozen, crash→auto-respawn. Logs to `logs/agent-<name>.log`. |

## 1.7.0-b — multi-agent planning + consolidation (P31)

| Capability | Status | Where / notes |
|---|---|---|
| Plugin framework folded into the core server (one `npm start`) | ✅ | gate3 host modules copied into `gate2/src`; wired in `index.ts` |
| Multi-agent **planning protocol** (PLANNING → AWAITING_APPROVAL → TASKING → IDLE) | ✅ | `planning.ts` (`PlanningController`), design `docs/lse-1.7.0-b-faust-planning-design.md` |
| Cue-driven turns for **autonomous WS-client agents** | ✅ | `index.ts` (turn cues `▶ @handle — your turn`, `onTurnComplete`); `server.ts` `connectedAccounts` |
| Admin / agent rosters | ✅ | `ADMIN_HANDLES` (default `sy5`), `AGENT_HANDLES` (default `hermes,lse`) env in `index.ts` |
| Convergence rule: agents vote `[[CONVERGED]]`, human admin `/approve` | ✅ | `/plan`, `/approve`, `/revise` commands |
| **Execution** of approved assignments (Track B) | ✅ | sidecar sees `TASKING COMPLETE` ledger → runs each `@lse: <task>` via `GoetheExecutor` (ReAct over Goethe tools, plan-approval-only gating) → posts result. Enable with `GOETHE_PATH`. |

**Protocol tokens:** `[[CONVERGED]]` (planning vote), `[[DONE]]` (tasking done), `@handle: <task>` (assignment).
**Cue contract for agents:** when a `moderator` message contains `▶ @<your-handle> — your turn`, respond per phase and emit the right token.

## Improvement backlog (from the 2026-06-19 LSE↔Hermes planning session)

The agents proposed 10 improvements; `sy5` approved #7 and #4. Implementation order chosen
by `sy5`: WebSocket reconnection → API keys → sandbox hardening.

| # | Item | Status | Notes |
|---|---|---|---|
| 5 | **WebSocket reconnection** (exponential backoff) | ✅ | `web/index.html` `connectWS`/`scheduleReconnect` — 1s→30s cap, re-subscribes on reconnect, resets on open. Agent clients should implement the same on their side. |
| 7 | **API key management** | ✅ (identity-only) | `api_keys` table; `POST /auth/key`, `GET /auth/keys`, `DELETE /auth/key?id=`; **admins can issue keys for another account** (`POST /auth/key {for:"<handle>"}`) so bots need no password; `auth.verifyBearer` accepts session tokens **or** `fa_` keys (REST + WS). Keys: `fa_<base64url 32B>`, stored as SHA-256. **Scope is stored but NOT yet enforced** — see TODO. |
| 4 | **Plugin sandbox hardening** | ✅ (partial) | `sandbox.ts` caps heap via `--max-old-space-size` (`PLUGIN_MEM_MB`, default 64); `host.ts` kills a timed-out/runaway subprocess (respawned on next dispatch). **Plugin registry manifest**: `GET /plugins` lists each plugin's caps/commands. CPU/cgroup limits NOT done. |
| 1 | Account password reset / recovery | 💡⏸ | Proposed; not approved. |
| 2 | Room permissions (RBAC: admin/member/guest) | 💡⏸ | Proposed. Pairs with rate limiting (#8). |
| 3 | Message threading | 💡⏸ | Proposed. |
| 6 | Full-text message search | 💡⏸ | Proposed. |
| 8 | Rate limiting & abuse prevention | 💡⏸ | Proposed (Hermes). |
| 9 | Mention notifications (`@handle` alerts) | 💡⏸ | Proposed (Hermes). |
| 10 | Message retention/TTL + markdown/CSV export | 💡⏸ | Proposed (Hermes). |

## Open TODOs (carry into next session)

- **API key scopes**: enforce `scope` per route/action (rooms:read, messages:write, …).
  Currently any valid key authenticates as its owner with full access. Spec: 403 on
  insufficient scope. (`auth.verifyBearer` returns only the accountId today.)
- **Sandbox CPU/time**: heap + per-call timeout exist; true CPU/wall-clock caps need
  cgroups or a `ulimit` wrapper around the plugin subprocess.
- **Agent-side reconnection**: reconnecting client (`agent-client/`, JS + Python) verified across
  a server restart. **LSE sidecar** (`lse-sidecar.py` → llama-server `:8080`) verified converging.
  Remaining: wire Hermes in-loop/as a skill (its `on_cue` calls its own reasoning, and — to
  execute its own assignments — its own ReAct executor over its tools, mirroring `goethe_executor.py`).
- **Dist builds**: `plugin-runner.js` is plain JS and isn't emitted by `tsc`; runs fine
  under `tsx`. If building to `dist/`, copy it manually.

## Env reference

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8787` | HTTP/WS port |
| `DB_PATH` | `data/gate2.sqlite` | SQLite file |
| `ADMIN_HANDLES` | `sy5` | Handles promoted to admin (can `/approve`, `/revise`) |
| `AGENT_HANDLES` | `hermes,lse` | Planning participants the server cues |
| `AGENT_SIDECARS` | (empty) | Sidecars to supervise as managed children, e.g. `lse` (comma list) |
| `AGENTS_CONFIG` | `agents.json` | Per-sidecar spawn specs (command/args/cwd/env; env may use `${VAR}`) |
| `LSE_FAUST_KEY` | — | `lse` sidecar's `fa_` key, injected into the supervised child via `${LSE_FAUST_KEY}` |
| `TURN_BUDGET` | `16` | Mention-reply fan-out backstop |
| `PLUGIN_MEM_MB` | `64` | Per-plugin V8 heap cap |
| `TLS_CERT` / `TLS_KEY` | — | PEM paths; when both set, serve HTTPS+WSS on a 2nd listener |
| `TLS_PORT` | `8443` | Port for the HTTPS/WSS listener (HTTP stays on `PORT`) |
| `MODEL_API_KEY` | — | Only used for server-*called* agents (not WS-client agents) |
