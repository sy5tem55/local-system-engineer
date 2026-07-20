# Goethe as a Product — Console + Gap-Closer Plan
> Created 2026-07-19 (Cowork session). Companion to ROADMAP.md — this is the
> productization track only. Phase 0 shipped this session.

## Positioning

The 2026-07-19 landscape review (verified against GitHub API + live search;
the earlier locally-generated competitor list was largely fabricated) puts
Goethe in a class with commercial AI SRE agents (Resolve.ai, Cleric,
Traversal, Parity) above it in distribution and self-hosted agent runtimes
(OpenClaw, goose, Hermes Agent, OpenHands) beside it in reach. Nothing in
either group has Goethe's three differentiators: the empirical KB trust
lifecycle (decay, quarantine, kb_verify), TRAUM (nightly offline
consolidation with human-gated apply and honest A/B evals), and the
evidence-gated planner ledger. The product strategy is therefore: **surface
the differentiators visibly, then close the packaging gaps** — not add
intelligence features.

## Phase 0 — Goethe Console (SHIPPED this session, pending deploy)

Gateway-served dashboard: `GET /ui` on :9700. New `tools/goethe_ui.py`
(stdlib-only ASGI router — deliberately no ES client library, per the
documented 9.4.1/8.19.3/9.4.3 drift risk) + `tools/goethe_dashboard.html`
(single file, no CDN, works offline). goethe_mcp v1.12.0 mounts it fail-safe:
a broken UI can never take down the MCP surface. `GOETHE_UI=off` disables.

Panels: KB trust (quality histogram, tier/volatility breakdown, quarantine +
decay counts, lowest-trust docs), TRAUM (latest digest verbatim, 14-night
cycle table with proposal/status/crash/FAILED flags), task ledger (step
progress from steps_json), episodes (7-day call volume by exit_class, top
tools). All `/api/ui/*` endpoints are read-only by construction and gated by
the same bearer token as `/mcp`.

Deploy: restart the gateway (`bash tools/start-goethe.sh`), open
`http://127.0.0.1:9700/ui`, paste the GOETHE_MCP_TOKEN once (stored in
browser localStorage). Tests: `tests/test_ui_router.py` (15, stdlib harness,
no live ES needed).

## Phase 1 — One-command deploy (est. 3–6h)

`docker compose up` bringing up gateway + Elasticsearch + SearxNG + Grafana +
Ollama with a seeded empty lse-kb (run `rag/08-kb-trust-migration.py` mapping
at first boot). llama-server stays native (GPU passthrough on WSL2 is the
operator's concern); the compose file takes `LLAMA_URL` as env. The existing
`docker-compose.yml` already carries SearxNG/ES — extend it rather than fork
it. Acceptance: fresh machine → compose up → `/ui` green chips except model.

## Phase 2 — Plugin drop-in (est. 2–4h — the mechanism already exists)

`--also` already loads extra Tools files with first-wins dedupe. Generalize:
`GOETHE_PLUGINS_DIR` (default `~/.goethe/plugins`) scanned at startup, each
`*.py` with a `Tools` class registered via the same `register()` path, loud
per-file failure warnings, never fatal. This is ~30 lines in `main()`. The
docstring-as-tool-description convention plus lse-docstring-optimizer becomes
the plugin authoring story — a real differentiator vs goose/OpenClaw skills,
because plugins here inherit the evidence-gate culture.

## Phase 3 — Scheduler / missions (est. 4–8h)

Generalize the `goethe-dream.service`/`.timer` pattern (repo-owned units,
fail-visible, budgets, lockfile, session-activity guard — all built for
TRAUM Thread 4) into a mission template: `missions/<name>.mission.yaml` →
generated systemd unit pair running `run_episode.py`-style prompts through
the planner ledger. Reuse, don't rebuild: the 30-min active-session guard and
crash discipline from dream_runner are exactly what kronos/OpenClaw cron
lacks (their scheduled jobs fail silent). Every mission run lands in the
episode journal → visible on the Console episodes panel for free.

## Phase 4 — Messaging gateway (est. 4–8h)

Telegram (or Matrix) bridge: message → llama-server chat completion with the
goethe MCP toolset → streamed reply. `pfsense-agent.py` already demonstrates
the orchestrator pattern (Qwen → LSE with think-mode control); the bridge is
that pattern with a Telegram transport. Hard rule carried over: sudo
delegation and shutdown/write confirmation gates surface as explicit
confirm-reply prompts in chat — never auto-confirmed. This is the phase that
makes Goethe demoable to anyone in 30 seconds.

## Deliberately deferred

Multi-user/RBAC (no second user yet), multi-agent swarms (the single-agent
evidence loop is the product, not a limitation), browser automation (Firecrawl
on node3090 already covers the fetch_url fallback), marketplace (a plugins
dir + docs is enough until there are external plugin authors).

## Sequencing

Phase 1 → 2 are independent of each other and small; do next. Phase 3 builds
on Phase 2 (missions should be able to call plugin tools). Phase 4 last —
it's the widest new attack surface and deserves the same threat-model pass
`docs/threat-model-kb.md` got.
