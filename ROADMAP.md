# LSE Roadmap — Open Items Only
> Completed work lives in `CHANGELOG.md`. Current versions in `CURRENT-STATE.md`.
> Last updated: 2026-06-11 (P20 Cowork)

---

## Immediate — P20 Active (2026-06-11)

- [ ] **node-t3-005 Duplicate Model Cleanup** — 3 runs TRUNCATED 2/4, ROOT CAUSE FOUND (P20):
  **the episode harness has no actuation path.** `run_episode.py` calls llama-server directly
  (bare chat completion, no tools); `lse_challenge_env.step()` only parses the JSON and runs
  `verify_ssh` ground truth — model-emitted commands are NEVER executed. verify_ssh overrides
  self-report, so write challenges pass only if the world is already fixed (t3-004 "solved" via
  the interactive LSE session at 19:27/19:33, not the episode). Secondary findings still valid:
  execute_command sudo-blocker + /opt/models perms (fixed: lse-admin in sy5 group, WRITE-OK ✅).
  **Next:** perform the cleanup via interactive LSE chat session, then run the episode as verifier
  (expect 4/4); long-term fix = episode actuation layer (see v1.7.0-a).
- [x] **Hermes KB entry — LSE relationship** ✅ (2026-06-11 P21) — installed via Hermes's own
  memory tool: LSE sent `call_hermes` task to read `/tmp/hermes-kb-lse-relationship.md` and save
  to persistent memory (hand-editing `.hermes/memories/USER.md` rejected — agent-managed + lock).
  Verified cross-channel via Telegram "what is LSE". Exercised the full LSE→socat 8643→gateway path.
- [x] **hermes-gateway TimeoutStopSec fix** ✅ (2026-06-11 P21) — drop-in
  `/etc/systemd/system/hermes-gateway.service.d/timeout.conf` with `TimeoutStopSec=210s`,
  daemon-reloaded, verified `TimeoutStopUSec=3min 30s`, gateway active.
- [ ] **Hermes /status "Agent Running: No"** — assessed as normal idle state (agent sessions spawn
  per conversation; gateway holds messaging+cron). Confirm: /status during an active reply.
- [ ] **Hermes web_search/firecrawl broken** — `externally-managed-environment` pip failure in
  gateway log; Hermes SSH to node3090 fails (password auth). Triage later — low priority.
- [x] **[P0] Model store reconciliation — node3090** ✅ (2026-06-12 P21):
  `/opt/models` symlink removed, real directory created, all model files migrated via
  same-fs `mv` (zero downtime — running server held the inode via mmap). 18 `.gguf` files
  `chattr +i` immutable. sha256 records: `/opt/models/SHA256SUMS` (node) + `kb/node3090-model-sha256sums.md`
  (repo). Canonical launch consolidated to `/opt/local-se/scripts/start-llama-server.sh`
  (ctx 81920, q8_0 KV both, threads 7/7, log `/home/lse-admin/llama-server.log`) — runbook
  step 2 now calls the script. Verification restart completed, Hermes notified pre/post.
  Postmortem: `docs/incident-2026-06-11-model-deletion.md`.
- [ ] **ES index loss — follow-ups** (P21): `lse-errors` + `lse-rfc-kb` were wiped 2026-06-08
  (es-data volume lost in the WSL/Docker cascade failure; only `lse-kb` was reseeded). Missing
  indices are SILENT until first read. Recreated 2026-06-12 via `rag/02-es-setup.py` (idempotent).
  - Add ES index-existence probe to the stack health check:
    `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
  - RFC KB: ZERO `search_rfc` calls in 44,637 logged commands; rfc-cache untouched since ship day
    (2026-06-04). Index reseeded untagged; Ollama tagging DEFERRED to first real demand. Add a
    usage log line to `search_rfc` so the next review has data. Consider wiring RFC KB into LSE
    prompts/episodes or retiring it.
  - `lse-kb.sqlite` (0 bytes) is vestigial — no active code references it (tool v1.6.4's only
    sqlite is the OWUI chat DB). Delete or ignore; do NOT "reinitialize".
  - ~~Two repo clones on LUCIFER~~ RESOLVED (P21): `/home/sy5/projects/local-system-engineer` is a
    symlink → `/mnt/c/...` (since Jun 7). One real repo; no reconciliation needed. Repo had ~2 days
    of uncommitted session work — committed P21.
- [ ] **Model store reconciliation — follow-ups** (P21):
  - LM Studio repoint: My Models → models directory → `/opt/models` (confirm it indexes)
  - lse-errors ES index missing — LSE `record_error` failed (2026-06-12); reinitialize index
  - Other nodes (LUCIFER, node5090 when built) get the same one-real-dir + chattr +i treatment
  - Design challenge `node-t3-006` "Model Store Reconciliation" with inode-level assertions
    (replaces retired node-t3-005 — premise was false: the "duplicate" was one inode behind
    a symlink; deletion removed the only copy; recovered byte-exact via Hermes aria2c from HF)

---

## v1.7.0 — Hermes Core + Self-Learning Skills

> **Design doc: `docs/lse-1.7.0-design.md`** · **Execution order: `docs/self-learning-trajectory.md`** (S0–S6)
> **node5090 (NODE3): `docs/node5090-deployment-design.md`** + `scripts/node5090/` deploy/provision/teardown kit
> (P20, DRAFT for review). Four workstreams:
> structured Hermes peer protocol · occupational self-learning skills on RAG/ES ·
> frozen-suite benchmark with SWE-bench-comparable metrics · Qwen3.6-35B-A3B coding delegation.

- [ ] **1.7.0-a** — **episode actuation layer (NEW — P0):** env executes model-emitted command
  blocks via SSH with the tool's safety gates ported (blocklist, no-sudo, privileged-path guard);
  without it every write-mode challenge is a deterministic failure and the bench measures world
  state, not the model. Plus: `verify_ssh` on all bench challenges, `--eval --no-learn` flag,
  freeze `lse-bench-v1`, record Condition A baseline
- [ ] **1.7.0-b** — `hermes_notify`/`hermes_ask` structured protocol (correlation ids), KB entry live
- [ ] **1.7.0-c** — `lse-skills` ES index, episode distillation, retrieval gold set (recall@3/MRR),
  hybrid BM25+kNN scoring, gate web-search auto-indexing (quality 0.7→0.4 + relevance check)
- [ ] **1.7.0-d** — occupational curriculum batches, skill lifecycle jobs, learning-lift run #1 (A vs B);
  SOUL.md curation discipline (`hermes-t4` family — proven-knowledge appends to Hermes identity
  prompt, human-approved, ground-truth-verified; trajectory §5.4)
- [ ] **1.7.0** — 35B-A3B delegation after model shootout Runs 3–4 (Qwopus 35B vs Qwen3-Coder 30B);
  serving on node3090 LM Studio with Hermes maintenance-window coordination until NODE3 exists
- [x] **Reconcile VERSION.md** ✅ (P27 2026-06-13) — registry now current through Cogitator v1.7.13 (raw + black-norm sha256, line count tally v1.7.0–v1.7.13). Gap v1.6.2–v1.6.4 noted in version history.
- [ ] **v1.7.6 candidate — WATERFALL PROVENANCE RULE** (added P23 2026-06-12, SY5 observation):
  the source-of-truth hierarchy (KB → vendor docs/master README → github → web) exists as
  *available tools* but not as a *mandatory path for claims* — so "slots API removed in v9577"
  could be invented and persisted without ever touching the waterfall it contradicts.
  Enforce at the WRITE path (attention is not a control plane): `record_error`/`index_to_kb`
  reject resolutions/content containing external-software behavior claims ("removed/changed/added
  in version X") unless provenance from the waterfall is attached (kb doc id, fetched URL, RFC ref);
  otherwise persist tagged UNVERIFIED at quality ≤0.3. Companion docstring rule: version/behavior
  claims about vendor components require a waterfall lookup BEFORE diagnosis, same shape as the
  1.7.5 CONFIG GROUND-TRUTH rule.

---

## Immediate — GUI & Stack

- [ ] **Launcher docker container visibility** (added P23 2026-06-12) — show ALL running docker
  containers and their resource usage in the LSE Stack launcher GUI (next launcher version, ≥1.078).
  Launcher repo: `C:\Users\SY5\Claude\Projects\LSEStack_gui` (edit there, sign SY5TEM5Cert — see
  `docs/08-launcher-edit-workflow.md`).
  Source: `docker stats --no-stream --format json` (or `{{json .}}` per line) from WSL — gives
  name, CPU%, mem usage/limit, net/block IO per container. Display: container list panel with
  per-container CPU/MEM, refreshed on a DispatcherTimer tick (reuse the PS7 scope-fixed pattern
  from GUI v1.5). Covers searxng, elasticsearch, prometheus, grafana, exporters, dify (when up) —
  today only the compose-managed core services are visible/launchable, untracked containers are invisible.

- [x] **GUI v1.5 PS7 DispatcherTimer scope fix** ✅ — launch cycle + kill buttons fully working (2026-06-08)
- [x] **pfsense-agent.py v1.0** ✅ — Qwen3.6 → LSE orchestrator; `--think/--no-think/--prompt-only/--auto`; tool_ids pass-through; `_extract_prompt` DO NOT block anchor + contiguous step sequence extraction (2026-06-09)
- [x] **NoMtp flag: ps1 + XML** ✅ — `Build-LlamaServerCmd` now emits `--no-mtp` when `<NoMtp>true</NoMtp>` (2026-06-08)
  - Affects presets 9 (Qwopus 32k), 10 (Qwopus 96k), 11 (Huihui), 12 (HauhauCS) — all 35B A3B MoE
  - **Needs commit + re-sign from WSL** — changes not yet committed: `lse-stack-launch-gui.ps1`, `lse-profiles.xml`

- [x] **Grafana :3002 server error** ✅ — resolved (2026-06-09)

- [ ] **16-tool-call limit** — LSE stops after ~16 tool calls per session
  **Investigation result (2026-06-09):**
  - Env var `CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS` defaults to **256** — NOT the cause. Not set in launch scripts.
  - Old name `CHAT_RESPONSE_MAX_TOOL_CALL_RETRIES` (pre-v0.9.6) defaulted to 30 — also not 16.
  - Neither variable is set in `lse-stack-launch-1.077.ps1` → OWUI inherits default (256).
  - **Root cause candidates:** (a) per-model UI override in Admin → Models → [Qwen3 preset] → Advanced → Max Tool Calls; (b) Qwen3 model behaviour — model self-terminates tool loop; (c) context_monitor tool yielding early on HIGH/CRITICAL context state.
  **Next action:** Open WebUI Admin → Models → Qwen3.6 preset → Advanced → check "Max Tool Calls" field. If blank/256 → root cause is (b) or (c).

- [x] **llama.cpp b9577 upgrade** ✅ — upgraded from b9553 (2026-06-09)

- [x] **Confirm session-learnings.md KB entry landed** ✅ resolved 2026-06-12 (P21): confirmed the
  entries were NEVER written (not present in either KB copy nor the pre-link backup — the prepared
  WSL command was evidently never run). PS7 DispatcherTimer + Ollama GPU overhead learnings are
  lost; rewrite from memory if still relevant. KB copies since merged + deduped (13 session blocks)
  into the single real KB (repo kb/, symlinked from /opt/local-se/kb).

---

## Immediate — Claude L2 Setup

- [x] **Create Claude Opus L2 preset in OpenWebUI** ✅ — deployed (2026-06-05)
- [x] **Create Claude Sonnet Research preset in OpenWebUI** ✅ — deployed (2026-06-05)
- [x] **Write `prompts/claude-l2-system-prompt.md`** ✅ (2026-06-05)
- [x] **Routing filter stays v1.1.0** ✅ — Global OFF · Qwen3 preset only · v1.2.0 not needed
- [x] **Apply SearXNG settings v3** ✅ — bing news + google news active (2026-06-05)
- [x] **Run SearXNG diagnostic v2** ✅ — news gap confirmed fixed (2026-06-05) · NVD/cvedetails blocked (VPS 403, confirmed 2026-06-06)

- [x] **Grafana engine health panels** ✅ — 6 tuning-signal panels deployed (P3 Cowork 2026-06-05)
  - Response time ranking, result yield ranking, reliability rate, error rate table, dead-engine detector, response time trend
  - `searxng_engine_errors_total` (Panel 24) wired but empty — **see searxng-error-exporter below (now P1)**

---

## Immediate — Arena T2/T3 remaining

- [x] nas-t2-001 NAS Unexpected Port Investigation ✅ SOLVED · 19.5 pts
- [x] nas-t3-001 NAS Anonymous Access Hardening Verification ✅ SOLVED · 19.5 pts
- [x] net-t2-011 Samsung TV Traffic Analysis ✅ SOLVED · 19.5 pts
- [x] net-t3-002 Samsung TV WAN Isolation ✅ SOLVED · 19.5 pts (a3 assertion fixed post-run)

- [ ] **net-t3-002 re-run** (optional) — a3 was patched after the solve. Re-run to confirm
  `write_access_verified_inactive` assertion works correctly with the API probe approach.

- [ ] **Samsung TV DHCP hammer** — WAN blocked but DHCP rate still high (every 1-2 min)
  Needs T2.5 investigation: is the DHCP hammer causing network issues or just noise?

---

## Immediate — Eval

- [ ] All 63/63 confirmed ✅ (Run 7, v0.5.14 + v1.5.18)
- [ ] No new prompt/tool changes pending — Run 8 only after new gaps identified

---

## Immediate — Documentation Cleanup

- [ ] Delete `docs/searxng-settings-patch-v2.yml` — superseded by `docker/searxng_data/settings.yml`
- [ ] Archive `docs/searxng-config.md` — superseded by `docs/searxng-operations.md`
- [ ] Move `mesh_builder.py` + `portrait_3d_pifuhd.py` from root to `tools/` or delete
- [ ] Write `docs/claude-l2-system-prompt.md` — document the L2 escalation role

---

## Backlog — SearXNG

- [x] **[P1] arXiv pollutes general-purpose queries** ✅ ROOT CAUSE WAS TOOL-SIDE (P23 2026-06-12,
  surfaced during a multi-step research task). search_web requested `categories="general,it,science"`
  on every call; arxiv is in `[science,it,technology]` (settings.yml line 156) so it fired on all
  queries incl. general-domain/product ones, returning 4-5 off-domain physics/ML hits and burning the web budget.
  FIXED in cogitator v1.7.8: categories → `general` only. NOT a SearxNG misconfiguration.
- [ ] **Defense-in-depth: tighten arxiv to science-only in settings.yml** (optional follow-up) —
  even though the tool now requests `general` only, arxiv's `categories: [science, it, technology]`
  means any future `it`/`technology` query would re-pull it. Consider `categories: [science]` so
  arxiv only ever answers deliberate science searches. Low priority now that the tool no longer
  requests those categories. Verify canonical settings path via docker exec read before editing.

- [ ] **[P1] searxng-error-exporter** — Grafana "Failing engines" panel (Panel 24) shows 0.
  Without this, silently-failing engines (e.g. cvedetails 403) are invisible until manual diagnosis.
  Implementation: scrape SearXNG `/metrics` endpoint, parse `searx_engine_*` counters,
  expose `searxng_engine_errors_total{engine,error_type}` on :9840 for Prometheus to scrape.
  Replaces the stale searxng-logger approach. Deploy as systemd service alongside other exporters.

- [ ] **[P1] NVD custom SearXNG engine** — cvedetails.com VPS blocked (403). CVE search critical
  for security audit challenges. Write a custom engine file hitting NVD REST API directly:
  - Endpoint: `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=<q>&resultsPerPage=10`
  - Returns: CVE ID, CVSS score, description, published date — no IP restrictions, no auth needed
  - Rate limit: 5 req/30s unauthenticated (add `api_key` support for 50 req/30s later)
  - Deploy to: `/usr/local/searxng/searx/engines/nvd_api.py` via Docker volume mount
  - Engine name in settings: `nvd` · categories: `[it, security]` · weight: 3
  Workaround until built: `site:nvd.nist.gov <CVE-ID>` via Google

- [ ] **URL redirect leak fix** — google.com/search?q= URLs appearing in results
  Root cause: SearXNG parser issue, not config. Requires `docker pull searxng/searxng:latest`
  + test in staging before applying. Check current version: `docker exec searxng searxng --version`

- [ ] **Reddit engine** — blocked on VPS IPs for anonymous access
  Options: (a) Reddit OAuth app + bearer token, (b) site:reddit.com via Google (current workaround)
  "Velvet gloves" approach: OAuth with proper User-Agent, respect rate limits (60 req/min)

- [ ] **Google Scholar** — 0% reliability, VPS IP blocked
  Debug: `docker exec searxng curl -sA "Mozilla/5.0" "https://scholar.google.com/scholar?q=test" | head -3`
  Re-enable checklist in `docs/searxng-operations.md`

- [ ] **searxng-logger rewrite** — scrape /metrics directly with Authorization: Basic header
  (superseded by error-exporter P1 item above — do together)

---

## Backlog — Network Topology Challenge Series

> **Goal:** A progressive set of challenges whose collective deliverable is a high-quality
> illustrated network topology diagram with vendor icons — comparable to Cisco Visio-style
> diagrams. The LSE model discovers, validates, and documents the topology; the final
> challenge renders it as a PNG using the `diagrams` Python library (diagrams.mingrammer.com).
> Each challenge is independently solvable and feeds structured data into the next.

### T1 — Discovery Layer
- [ ] **net-t1-013 Subnet Host Enumeration** — nmap sweep of all three subnets (1.x, 5.x, 10.x).
  Note: 192.168.1.x includes ALL WiFi devices (AP at 192.168.1.1 bridges WiFi into LAN).
  192.168.10.x is dedicated wired IoT only (solar inverter). Expect most IoT on 1.x, not 10.x.
  Produce: JSON list of `{ip, mac, hostname, open_ports[], vendor}` for each live host.
  Assertions: a1=hosts found on each subnet, a2=MAC vendors resolved, a3=JSON written to KB.

- [ ] **net-t1-014 pfSense Interface Inventory** — enumerate pfSense interfaces, IPs, and
  assigned subnets via `pfsense_query("/api/v2/network/interface")`.
  Produce: `{interface, description, ip, subnet, connected_to}` per interface.
  Assertions: a1=3+ interfaces found, a2=each subnet mapped to interface, a3=KB indexed.

### T2 — Analysis Layer
- [ ] **net-t2-012 DNS Architecture Audit** — verify *.home.arpa resolution via DNS queries.
  Method: `dig +short @192.168.1.50 <host>` from LUCIFER — read-only, no API/SSH needed.
  ⚠️ Do NOT use SSH to pfSense or attempt to read /var/unbound/unbound.conf — SSH admin = root,
  bypasses the read-only API boundary. DNS queries are the correct read-only verification path.
  Confirm: pfsense/homeassistant/n45 resolve correctly. Identify gaps (lucifer, node2 = NXDOMAIN).
  Assertions: a1=known hosts resolve to correct IPs, a2=gap hosts return NXDOMAIN (documented),
  a3=resolution report produced with all 3 subnets' static hosts tested.

- [ ] **net-t2-013 NAS Subnet Topology** — map 192.168.5.0/24 physical topology.
  Discover Netgear switch (IP, model via SNMP/nmap), confirm NODE2 presence and MAC.
  Assertions: a1=switch identified, a2=all 5.x hosts mapped with MAC, a3=topology JSON produced.

- [ ] **net-t2-014 DHCP Static Mapping Audit** — enumerate all pfSense static DHCP mappings.
  Identify: which hosts have static mappings, which are dynamic, hostname coverage gaps.
  Assertions: a1=static mappings retrieved, a2=dynamic hosts identified, a3=gaps documented.

### T3 — Deliverable Layer
- [ ] **net-t3-003 Network Topology JSON** — produce a validated topology document combining
  all T1/T2 findings into a single canonical JSON:
  `{subnets[], hosts[], connections[], dns_entries[], missing_dns[]}`.
  Assertions: a1=all 3 subnets present, a2=all known hosts present with MAC+hostname, a3=JSON validates against schema.

- [ ] **net-t3-004 Network Topology Diagram** — render topology as PNG using `diagrams` library.
  Requirements: vendor icons (pfSense, QNAP, Raspberry Pi, Samsung, generic server/PC),
  subnet clusters (LAN / NAS+Server / IoT), edge labels (IP + hostname), Netgear switch node.
  Output: `/opt/local-se/topology/network-diagram.png` + source `.py` script.
  Assertions: a1=PNG file written (>10KB), a2=all subnets represented in diagram,
  a3=all static-mapped hosts appear as labelled nodes.

### Implementation notes
- `diagrams` library: `pip install diagrams` (requires Graphviz: `apt install graphviz`)
- Vendor icon sets available: `diagrams.onprem.network` (generic), custom PNG icons via `Custom()`
- For Cisco/pfSense/QNAP icons: use `Custom()` with downloaded vendor SVG/PNG icons
- Challenge `requires_human_approval=1` for T3-004 (writes files, needs Graphviz install)
- Natural T4 extension: `net-t4-001` — topology diff challenge (detect when topology changes)

---

## Backlog — Arena

- [ ] **[P0] Ground-truth assertion verifier** — node-t3-002 hallucination incident (2026-06-06):
  LSE reported `gpu_detected=True`, `cuda_major=13`, `cuda_verified=True` but `nvidia-smi` was not
  installed (`nvidia-compute-utils-595` removed during Ubuntu upgrade) and CUDA was 12.0 not 13.x.
  The assertion framework trusted the model's self-reported JSON — there is no independent verification.

  **Design**: Add an optional `verify_ssh` field to challenge assertions. After the model completes
  and reports its JSON, `lse_challenge_env.py` SSHes to the target node and runs the verify command
  independently. The actual stdout/exit code overrides the model's self-reported variable for that
  assertion. Model cannot pass a verify_ssh assertion by hallucination.

  Example assertion with ground-truth probe:
  ```python
  {
    "id": "a3", "points": 1,
    "code": "assert gpu_detected == True and 'RTX 3090' in gpu_name",
    "verify_ssh": {
      "host_key": "node3090",           # resolved via _NODE_REGISTRY
      "cmd": "nvidia-smi --query-gpu=name --format=csv,noheader",
      "parse": "gpu_name = stdout.strip(); gpu_detected = (exit_code == 0)"
    }
  }
  ```

  Priority: P0 — any challenge that touches real infrastructure can be gamed by hallucination.
  Affects: node-t3-001, node-t3-002, and any future infra challenges with measurable state.

- [ ] **Samsung TV T4** — DHCP hammer confirmed firmware noise (lease 7200s normal).
  Design challenge: measure DHCP rate from MAC 1c:af:4a:04:5f:b6 via DHCP logs,
  confirm lease time is not the cause, document remediation options (rate-limit UDP 67/68).
  Assertions: a1=DHCP request rate measured, a2=lease time confirmed normal (>3600s),
  a3=remediation documented (rate-limit rule spec or benign-noise classification).
- [x] **ha-t1-004** ✅ SOLVED 15.0 pts (2026-06-05)
- [x] **ha-t1-008** ✅ SOLVED 15.0 pts · 2 stale automations found (2026-06-05)
- [x] **ha-t2-002** ✅ SOLVED 19.5 pts · template sensors identified (2026-06-05)
- [x] **ha-t3-001** ✅ SOLVED 22.5 pts · YAML fixed + confirmed (2026-06-05)
- [x] **infra-t2-001** ✅ SOLVED 19.5 pts · SSH posture audited (2026-06-05)
- [x] **infra-t3-002** ✅ SOLVED 22.5 pts · key auth live, password auth disabled (2026-06-05)
- [ ] **ChallengeGenerator quality** — llama3.2:3b produces broken assertions (a2 bug in Samsung T2 proposal)
  Consider: validate assertions with AST parse before inserting to DB

---

## Backlog — Infrastructure

- [ ] **Local DNS Architecture** — converge all hosts to coherent `*.home.arpa` naming.
  Current state (pfSense DNS Resolver overrides):
  - `homeassistant.home.arpa` → 192.168.1.80 ✅
  - `n45.home.arpa` → 192.168.5.45 ✅
  - pfSense, LUCIFER (WSL2 + Windows), Samsung TV, NODE2, NODE3 — **not yet mapped**
  Work items:
  Known DNS entries confirmed via `dig @192.168.1.50` (2026-06-06):
  - `pfsense.home.arpa` → 192.168.1.50 ✅
  - `homeassistant.home.arpa` → 192.168.1.80 ✅
  - `n45.home.arpa` → 192.168.5.44 + 192.168.5.45 ✅ both correct
    (NAS has 2 NICs, failover config — switch doesn't support LACP. Both MACs in pfSense static DHCP.
    DNS returns both A records; clients use whichever NIC is active.)
  Missing (to add in pfSense DNS Resolver → Host Overrides):
  - `lucifer.home.arpa` → 192.168.1.57
  - `4090.home.arpa` → 192.168.1.57 (LUCIFER GPU alias — additive, no hostname change)
  - `3090.home.arpa` → 192.168.5.41 ✅ (NODE2/3090 · MAC 0c:9d:92:84:6e:6a · hostname set to 3090)
  - `5090.home.arpa` → NODE3 IP TBD (NODE3 GPU alias — after NODE3 setup)
  GPU naming strategy: DNS aliases only — machine hostnames (LUCIFER/NODE2/NODE3) unchanged.
  No script/prompt migration needed. Aliases coexist with existing names.
  Work items:
  1. Audit all current pfSense host overrides: `pfsense_query("/api/v2/services/unbound/host")`
  2. Add static DHCP mapping for NODE2 (MAC needed) → then `node2.home.arpa`
  3. Add PTR records (reverse DNS) — makes firewall log analysis readable by hostname
  4. Update LSE NETWORK_CONTEXT and KB docs to use hostnames over IPs consistently
  Design as arena challenges — see Network Topology Challenge Series below.
  Ref: RFC 8375 — `home.arpa` is the IETF-recommended local domain for residential networks.

- [ ] NODE2 — LM Studio server mode on RTX 3090, expose :8081, add to pfSense API access list
- [ ] NODE3 — WSL2 install, llama-server deploy, test `wsl-gaming-teardown.ps1`
- [x] HA long-lived token — ✅ created (2026-06-05) · stored in Vaultwarden as HA_TOKEN
- [ ] **Kostal Smart Energy Meter** — disconnected, pending integration on 192.168.10.x (OPT2)
  When connected: add static DHCP mapping, add `kostal.home.arpa` DNS entry, integrate with HA
  Design as arena challenge: `ha-t2-003` Energy Meter Integration

---

## Immediate — Multi-Agent UI (Dify)

> **Decision (P18 2026-06-09):** Adopt Dify for the Qwen3.6 → LSE multi-agent workflow UI.
> Replaces ad-hoc `pfsense-agent.py` for interactive/persistent pfSense work sessions.
> OWUI pipe function (Qwen3.6 → LSE handoff inside OpenWebUI) is **deferred** — not needed.

- [x] **Dify deploy** ✅ — v1.14.2, on-demand (not in launcher), port 4000, installed at `/opt/dify` (2026-06-09)
  `docker compose -f /opt/dify/docker/docker-compose.yaml up -d` to start; `down` to stop.
  GP shutdown script `docker-graceful-stop.ps1` handles graceful stop on Windows shutdown — committed to LSEStack_gui, signed SY5TEM5Cert.

- [ ] **Dify LM Studio connections** — add both LM Studio instances as OpenAI-compatible providers:
  - LUCIFER llama-server: `http://192.168.1.x:8080/v1` — model `qwen/qwen3.6-27b` (orchestrator)
  - node3090 LM Studio: `http://192.168.5.41:1234/v1` — model `qwen/qwen3.6-27b` (executor / alt)
  Note: Dify uses display names; actual model string must match what LM Studio serves.

- [ ] **Dify pfSense workflow** — visual pipeline: User message → Qwen3.6 orchestrator →
  structured LSE prompt → LSE node (OpenWebUI API or direct tool call) → streamed output.
  Human-in-the-loop node: show generated prompt, wait for approval before submitting to LSE.
  Persistent chat history: Dify maintains conversation across sessions (PostgreSQL backend).

- [ ] **OpenWebUI pipe function** — Qwen3.6 → LSE handoff inside OWUI.
  **DEFERRED** — root cause: local Qwen3.6 doesn't emit OpenAI-style function-call JSON via API;
  ReAct-style tool invocation only works in Chat UI, not `/api/chat/completions` path.
  Revisit when: (a) Dify covers the use case, or (b) a local FC-capable model is available.

---

## Deferred — Zero-Persistence Trust (ZPT) Architecture

> **Definition:** A session-scoped secret architecture where no operational secret persists
> on disk between sessions. A physical USB key is the session gate — present to start,
> removed to terminate all secret access. Extends Zero Trust with a physical persistence
> boundary: even a fully compromised host cannot access secrets after USB removal.

### Design Principles

1. **Single physical gate** — USB presence is the only requirement to start a session.
   No USB = no secrets = no session. Removes the "always-on credential" attack surface.

2. **Load-once, session-scoped** — Secrets are read from USB once at launch into tmpfs
   (`/run/lse-secrets/` or similar). tmpfs is wiped on unmount/reboot. No disk writes.

3. **Secret tiering by access frequency:**
   - `HIGH FREQ` (pfSense API key, HA token, HF_TOKEN) → USB → tmpfs → `.lse/secrets`
     ~50 tokens per read, no Vaultwarden roundtrip needed
   - `LOW FREQ` (user passwords, OAuth tokens) → Vaultwarden only
     Vault roundtrip acceptable for rare operations
   - `GATE KEY` (Vaultwarden master password) → USB only, never written to disk

4. **Vaultwarden role narrows** — becomes the store for secrets requiring human-level
   protection or rare access. High-frequency operational keys bypass it entirely.
   Token cost of vault unlock is paid at most once per session.

5. **HF_TOKEN and other env var secrets removed from `.bashrc`** — currently exposed
   in plaintext. Must move to USB → tmpfs load before ZPT can be considered complete.

### Implementation Tasks (deferred)

- [ ] Audit all plaintext secrets currently in `.bashrc`, `.lse/secrets`, env vars
- [ ] Design USB filesystem layout (encrypted LUKS partition recommended)
- [ ] Modify `lse-stack-launch-1.078.ps1` — add USB presence check + secrets load to tmpfs
- [ ] Replace `.bashrc` `export HF_TOKEN=...` with tmpfs-loaded env injection at launch
- [ ] Write shutdown hook — wipe tmpfs on session end / USB removal
- [ ] Design as arena challenge: `infra-t3-003` ZPT Bootstrap (T3, security, 1.5×)
- [ ] Test: disconnect USB mid-session → verify new secret fetches fail gracefully

---

## SSH COMMAND= PROTOCOL — read-only SSH escalation

When a challenge requires read access to pfSense or another host's filesystem that is
not exposed via REST API, the approved pattern is OpenSSH `command=` in authorized_keys:

```
command="<exact read-only command>",no-pty,no-port-forwarding,no-agent-forwarding ssh-ed25519 AAAA...
```

This locks the key to one specific command — the SSH client cannot request a shell or
run anything else. The key is added by a human (setup step) before the challenge runs.

Rules:
- One key per command — never reuse a `command=` key for a different operation
- Command must be read-only (grep, cat, dig, etc.) — never write/restart/edit
- Key is added to the target host's `~/.ssh/authorized_keys` by the human operator
- Document the key and command in the challenge's `starting_state` / pre-requisites
- Remove the key after the challenge series is complete

This is NOT general SSH access. It is a scoped, auditable, read-only channel.
Full SSH access to pfSense (admin shell) remains human-only — never delegated to LSE.

---

## WRITE ACCESS PROTOCOL — permanent rule

pfSense REST API is read-only by default. For T3+ write challenges:
1. Enable write in pfSense UI (System → REST API → disable Read Only) immediately before task
2. Complete task and verify
3. Re-enable Read Only before ending the session
4. Log in CHANGELOG: timestamp + what was changed

Verify re-enabled: `pfsense_query('/api/v2/firewall/rule', method='PATCH', payload={})` should return 403.
**NOTE:** `/api/v2/system/api` returns 404 — read-only toggle NOT available via REST API, web UI only.
