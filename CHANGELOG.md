# LSE Changelog
> Append-only. One entry per session. Never edit past entries.
> Format: `## YYYY-MM-DD — <what shipped>`

---
## 2026-06-13 — P27 (Cowork): Cogitator v1.7.12 — reconstruction + ask_id→task_id fix + line-count ground rule

- **v1.7.12 rebuilt** (P27, ast OK, raw sha256 `165874ee…`, black-norm `a2faad62…`, **4043 lines**, +109 vs v1.7.11):
  - **P26 Write-tool truncation incident**: P26 wrote cogitator-v1.7.12.py but the Write tool truncated it at 4015 lines (last character was bare `t` — middle of `task_id=tid,`). Original was 4465 lines. User pasted the full original but context ran out before it could be written. P27 rebuilt from truncated head + v1.7.11 tail. All functions present and AST-valid.
  - **ask_id→task_id bug fixed**: tail reconstruction introduced `ask_id=tid` (invalid kwarg) at the `task_checkpoint()` call inside `hermes_plan`. Corrected to `task_id=tid` (matches the function signature). This was a silent TypeError at runtime.
  - **New ground rule (P27)**: always verify line count delta between versions. Report delta and keep tally in VERSION.md Line Count Tally section.
  - **Checksums updated**: old (P26 rebuild) raw `ce2de61a…` / black-norm `519a8e8e…` → new (P27 rebuild) raw `165874ee…` / black-norm `a2faad62…`.
- READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.

---
## 2026-06-13 — P26 (Cowork): Cogitator v1.7.12 — SSH device auto-fingerprint (device-identity hallucination fix in code)

- **v1.7.12 built** (P26 — SUPERSEDED by P27 rebuild; original 4465-line version lost to Write-tool truncation incident; raw sha256 `ce2de61a…` was the 4043-line P26 partial rebuild, not the full original):
  - **SSH device auto-fingerprint**: `execute_command` intercepts any `ssh ` command (excludes recursive fingerprint sub-calls via `__FP__` guard). Parses options/flags to extract `user@host`, derives `_fp_host`. On first connection to a host (not yet in `self._device_cache`), fires a sub-SSH with `BatchMode=yes -o StrictHostKeyChecking=no` running `cat /etc/os-release; uname -srm`. Parses `PRETTY_NAME` (preferred) or `uname` output into `_platform`.
  - **Cache only on success**: fingerprint result stored in `self._device_cache[host]` ONLY if `returncode == 0` and `platform != "unknown"`. Failed attempts (wrong key, auth error, empty output) are NOT cached — next SSH call with the correct key will retry. Closes the "second call hits stale unknown cache" bug found in P26 live test.
  - **Banner behaviour**: success → `[DEVICE FINGERPRINT: host=… | platform=… | source=os-release/uname — ground truth. Use this platform for ALL CLI decisions. Never infer device type from IP or hostname.]`; failed auth → `[DEVICE FINGERPRINT PENDING: host=… | platform=unknown — SSH auth failed or no output. Fingerprint NOT cached; will retry on next SSH call. Do NOT infer device type from IP or hostname.]`
  - **`self._device_cache: dict = {}`** added to `__init__` (session-scoped; cleared on each new OWUI tool instance).
  - **Root cause fixed**: MikroTik device-identity hallucination (P26) — model stated "MikroTik RouterOS" before any tool call, purely from IP/hostname pattern recognition. With this fix: all platform claims must trace to the `[DEVICE FINGERPRINT]` banner in the tool result. Code emits the ground truth; model cannot fabricate it.
- READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.

---
## 2026-06-13 — P26 (Cowork): Cogitator v1.7.11 — KB source-tier quality gate

- **v1.7.11 built** (ast OK, raw sha256 `631d11df…`, black-norm `09595a23…`, 208,234 B):
  - **`index_to_kb` new params**: `source_tier` (ground_truth|primary|secondary|inferred, default=inferred), `evidence` (required for ground_truth), `verified_against` (version/config snapshot). Quality hard-capped at tier ceiling regardless of model-passed value. Default `quality_score` 0.8→0.5 (model must be explicit). Tier and evidence stored in document.
  - **`skill_record` new param**: `source_tier`; ceiling applied; tier stored in document.
  - **`skill_outcome` new param**: `source_tier` (default=secondary); `new_q` capped at tier ceiling; pushing to 1.0 requires `source_tier=ground_truth`; evidence threshold 20→50 chars for ground_truth.
  - **Tier ceiling map**: ground_truth=1.0 (live system test, ≥40-char tool-result evidence — else downgraded to 0.7 with warning); primary=0.8 (vendor docs, official README, RFC, man pages); secondary=0.6 (community forums, Stack Overflow, Reddit); inferred=0.4 (untested hypothesis, model inference).
  - **Root cause fixed**: pfSense read-only incident — LSE indexed untested hypothesis at quality=1.0 before verifying chicken-and-egg lock. With this gate: default tier=inferred caps at 0.4; reaching 1.0 requires live bidirectional test + evidence string from actual tool output. Model cannot self-grant max score.
- READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.

---
## 2026-06-13 — P26 (Cowork): Cogitator v1.7.10 — source-claim verification (fabrication #5 fix in code)

- **v1.7.10 built** (ast OK, raw sha256 `463e0941…`, black-norm `48e13812…`, 203,008 B):
  - **`verify_source_claims(url, claims)`**: new tool function. Re-fetches source URL (or uses `self._fetch_cache` if within TTL) and checks each comma-separated claim for verbatim presence. Returns `FOUND` + ±300-char excerpt, `PARTIAL` (specific token found but full claim absent — excerpt shows what source ACTUALLY says), or `NOT_FOUND` (with list of version strings the source DOES contain). Does NOT count against search budget.
  - **`fetch_url` modified**: on every successful text extraction, caches content to `self._fetch_cache[url]` and appends a code-emitted `[SOURCE-VERIFY MANDATE]` banner instructing the model to call `verify_source_claims` before asserting any version number, date, or specific value. Error/non-text returns untouched (no false mandate).
  - **New valve**: `SOURCE_VERIFY_CACHE_TTL` (default 300s) — controls cache TTL; set to 0 to always re-fetch.
  - **Root cause fixed**: fabrication #5 (P25) — model had 07.22.3=Stable / 07.23.4=Latest in context, emitted phantom 07.23.5 + 07.22.4. Evidence overwrite at synthesis; prompt fences proved ineffective. Fix: code does the comparison (model cannot fabricate `verify_source_claims` return value). Enforcement in code, sudo-blocker lineage.
- READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.

---
## 2026-06-12 — P25 (Cowork): Cogitator v1.7.9 — hermes_plan creates the kanban card (capability gap closed in code)

- **v1.7.9 built**: `_kanban_create_card()` — direct `INSERT OR IGNORE` into node3090 `kanban.db` over ssh (BatchMode, 10s timeout), called by `hermes_plan` after envelope parse + checkpoint. status=`triage`, assignee=`lse`, created_by=`lse-cogitator`, goal_mode=0, `idempotency_key=hermes_plan:<task_id>`, created_at INTEGER epoch. Fail-open: card failure becomes a `card_error` line in the plan result, never blocks the envelope. Pre-check (P24 carry): tasks schema has NO CHECK on status; `VALID_INITIAL_STATUSES={running,blocked}` gates only the Python create API — not this path; `triage` is in `VALID_STATUSES`. Single-quote/control-char sanitization on all interpolated values; SQL delivered via stdin (no shell-quoting layer). ast clean.
- **Planner contract v2.2**: card-creation instruction REMOVED from Hermes side (P24 ground truth: planner session has no kanban-write tool — it hunted cronjob → skills_list and gave up; wording cannot fix a missing tool). Hermes now emits the envelope immediately; rules 2-3 (never promote lse cards) retained.
- Enforcement-in-code lineage: sudo blocker → budget gate → card creation. Side effects the model "should" do become code the model cannot skip.
- **DEPLOYED + verified same session**: black-norm `2e15e467…` MATCH in OWUI; smoke test `rutx50web01` → card created, stayed `triage`, no workers.
- **Auto-decomposer incident (first live card)**: Hermes `kanban_decompose.py` claims EVERY triage card on dispatcher tick (`auto_decompose: true` default) — flipped our card triage→todo, fanned 3 `t_*` children, dispatched 2 workers (9788, 11699) that re-did finished LSE research on node3090 GPU + Browserbase quota. P22 "triage is the only safe state" FALSIFIED. Fix: `auto_decompose: false` in node3090 `~/.hermes/config.yaml` (line ~441, `.bak-P25`) + hermes-gateway restart. Lesson: archiving a card does NOT stop its in-flight worker — kill `tasks.worker_pid` too.
- **06-10 "unattributed invocation" CLOSED**: it was SY5's own OWUI chat "🛡️ Claude Code Security Check" (22:12 local, npm supply-chain concern after Check Point research). P24's "webui.db clean" was a FALSE NEGATIVE — wrong query shape; a time-window SQL on `chat` found it in seconds. P0 escalation moot.
- **FABRICATION #5 — through a prompt fence, with the source in context**: RUTX50 task; LSE cited phantom firmwares 07.23.5 + 07.22.4 (invented dates/changelogs recombined from the REAL 07.23 changelog) AFTER successfully fetching the wiki page that lists 07.22.3=Stable/07.23.4=Latest, and DESPITE explicit "no version newer than 07.23.4 exists" in context. Caught by independent re-fetch within minutes. Deliverables corrected: `docs/rutx50/rutx50-remediation-decision.md` (correction header, verified versions, forum draft clean). v1.7.10 lead candidate: code-enforced source-claim verification — fences don't hold at synthesis.
- RUTX50 ground truth: webui-login bug unpatched (07.23.4 newest); official fallback 07.22.3; 07.23 reworked login path (WebUI/SSH 2FA, Lua 5.1→LuaJIT 2.1) — fits SSH-works/webui-fails; recovery = `/etc/init.d/uhttpd restart` (prepared, untested); device stack: uhttpd → api_dispatcher.lua (LuaJIT) → ubus session; ssh = dropbear, separate path.

---
## 2026-06-12 — P22 (Cowork) final: Cogitator v1.7.2 — budget window 30→2 min

- **RUTX50 incident** (first v1.7.1 live test): rolling 30-min window leaked across `task_resume` sessions — budget exhausted on the resume's first search; LSE stalled ~7 min mid-conversation and started answering firmware-downgrade questions from unverified training knowledge. Window default now **2 min** (`SEARCH_BUDGET_WINDOW_MIN`); 8 calls/2 min still forces surface points in a spiral, but blocked budgets self-heal within the conversation. Live mitigation available without redeploy: valve edit in OWUI.
- One real infra issue surfaced by the same transcript: SearxNG returning arxiv results for all queries — engine-health problem, check searxng-engine-health dashboard / suspended engines.
- One FABRICATION initially misread as an infra issue: `fbidownload.teltonika-networks.com` does not exist (zero web references, NXDOMAIN everywhere) — LSE invented the hostname, diagnosed the NXDOMAIN as a "DNS path issue", and presented the fake URL to the user. Real firmware source: wiki.teltonika-networks.com/view/RUTX50_Firmware_Downloads. Second fabrication-under-pressure (after the Goethe quote); pattern: retrieval blocked → confident invention wrapped in diagnostic narrative. Counter-measure belongs in the planner's abort criteria + an UNVERIFIED-URL rule (never present a URL to the user that was not retrieved from a tool result).
- `tools/cogitator-v1.7.2.py`: 3356 lines, ast clean, sha256 `eca3b518…`.
- **v1.7.3 (same session)**: UNVERIFIED-URL RULE added to budget-refusal text + `fetch_url` docstring — only fetch/present URLs received from tool results; a DNS failure on a self-generated hostname is evidence about the hostname, not the network. 3371 lines, ast clean, sha256 `849de276…`. P22 debrief written to `kb/session-learnings.md`.
- **v1.7.4 (same session)**: compact_context KV-erase fixed — llama.cpp slots API takes the action as a QUERY PARAM (`POST /slots/0?action=erase`, verified against llama.cpp master server README); the tool sent a JSON body, rejected with "Invalid action" on every version. Field diagnosis "slots API removed in v9577" was FALSE (third fabricated diagnosis this session — Goethe quote, fbidownload hostname, slots API) — the lse-errors entry recorded during the incident must be corrected. Response now reports `n_erased`. 3383 lines, ast clean, sha256 `2d3a9703…`.
- SearxNG Prometheus scrape job missing again (recurring): repo holds two CONFLICTING configs (backup: basic_auth `:JZVeoVch…` → `searxng:8080`; KB doc: `params: authenticate` → `searxng:8088`) and LSE reports a third ("bearer token") — drift is the root cause. Fix sequence: probe /metrics auth live, write matching job, canonicalize prometheus.yml into the repo, add scrape-target probe to stack health check.
- **RESOLVED + de-fragiled for good**: the outage was REAL (dashboard empty ~1d — scrapes not happening, prometheus likely down since the last stack event until relaunch). The *diagnosis* was fabricated: token "searxng-metrics-token-2026" invented (#4), "no job in prometheus.yml" wrong — LSE most plausibly grepped the dead `searxng-docker/` path from the stale KB docs and reported file-not-found as "not configured". Ground truth (docker inspect/exec): real token `JZVeoVch…`, real dirs `/home/sy5/docker/{searxng_data,prometheus}`, shared net `docker_searxng_net`, scrape job present with correct token. After prometheus restart: target `searxng=up`, no error. Shipped `observability/observability.env` (single source of truth) + `deploy-observability.sh` (idempotent drift repair, end-to-end verify with 60s target poll). Corrected 4 stale KB docs (correction header with real paths/token). Health-check skill gains ES 5-index `_count` probe (P21 item #3 closed) + prometheus targets probe pointing at the repair script.
- **v1.7.5 (same session)**: CONFIG GROUND-TRUTH RULE — execute_command + search_kb docstrings: tokens/paths/ports/config values must come from a same-session tool result, never recall; KB hits are pointers, not ground truth, for config values. Code change: search_kb results display per-hit age ("updated Xd ago"). 3415 lines, ast clean, sha256 `94a428a9…`. Closes the fabrication series: URLs (v1.7.3), procedures (planner verify clauses), config values (v1.7.5).

---
## 2026-06-12 — P22 (Cowork) continued: Goethe-spiral fix — Cogitator v1.7.1 anti-spiral gate + task blocks

- **Incident**: first v1.7.0 live test — Goethe quote verification spiraled into 34 web searches / ~78K tokens; turn 2 produced no surfaced output; turn 1 surfaced a fabricated German quote ("Es ist schon alles gedacht…" is not Goethe; real source is *Wilhelm Meisters Wanderjahre*, not an opera). Root cause: termination decisions left to model attention, which is fully absorbed by the task (get_context_status never called; context-monitor filter cannot intervene).
- **`_budget_gate()`** — search_web/search_reddit/fetch_url share a rolling-window budget (valves `SEARCH_BUDGET`=8, `SEARCH_BUDGET_WINDOW_MIN`=30). Remaining ≤2 → surface-NOW banner on every result; 0 → call refused in code with checkpoint+surface instructions. Sudo-blocker philosophy: enforcement in code, never docstring. Unit-tested: clean 1–5, banner 6–8, refused 9+.
- **Task blocks** — `task_checkpoint`/`task_resume` (SQLite, valve `TASKS_DB`=/opt/local-se/tasks.db): goal/plan/done/findings/**UNVERIFIED**/next_prompt, status open→done. findings/unverified separation is mandatory (fabricated-quote lesson: unverified claims poison the next session). Checkpoint triggers: step completion, budget banner, task end. Both docstrings through the 8-dimension audit. Roundtrip unit-tested.
- **Planner-orchestrator spec** (`docs/planner-orchestrator-design.md`, → 1.7.2): Hermes pre-flight triage — packaged_prompt + sessions_estimate + per-step budgets + abort criteria; kanban.db as board, tasks.db as execution ground truth (one-way sync); calibration from leaderboard actuals after ~20 plans. Layers interlock: planner estimates, budgets enforce, blocks carry over — no layer trusts model attention.
- `tools/cogitator-v1.7.1.py`: 3346 lines, ast.parse clean, sha256 `c8994555…`. v1.7.0 superseded before deployment.

---
## 2026-06-12 — P22 (Cowork): Hermes skill-learning analysis + Cogitator v1.7.0 skills layer

- **Hermes skill learning analyzed from ground truth** (node3090, hermes-agent v0.16.0): file-based SKILL.md store in `~/.hermes/skills/`, full-manifest prompt injection (`.skills_prompt_snapshot.json`), weekly idle-time curator (prune 30d / archive 90d / pin / umbrella merge), optional skills_hub downloads. **Observed: 0 skills created in 44h, curator run_count=0** — feature is wired but inert. Full analysis + surpass criteria: `docs/hermes-skill-learning-analysis.md`.
- **Tool renamed: `openwebui-tool-v1.6.4.py` → `tools/cogitator-v1.7.0.py`** (title "LSE Cogitator", sha256 `642067d9…`, 3104 lines, ast.parse clean, 35 tool functions).
- **Skills layer shipped (1.7.0-c pulled forward)**: `skill_search` (SKILLS-FIRST RULE, max 2 injected, usage stats on retrieval), `skill_record` (EVIDENCE GATE, <2-step procedures rejected as facts, verification required, dedup @0.92, initial quality cap 0.7), `skill_outcome` (+0.10/−0.15 on evidence only, floor 0.2 → auto-archive, evidence_log). Adopted from Hermes curator: `pinned`, `archived`, inspectable snapshot (audit log). All docstrings through lse-docstring-optimizer 8-dimension audit (P6).
- **`rag/06-skills-index-setup.py`** — idempotent `lse-skills` index creation (768-dim cosine kNN + keyword fields). Not yet run; deploy steps in handover.
- Design correction: v1.6.4 `search_kb` was already hybrid kNN(0.7)+BM25(0.3) — 1.7.0-design §3.5.2's "kNN-only" claim amended; S2 question is RRF-vs-weighted-boost, settled by the gold set.

---
## 2026-06-12 — P21 (Cowork) final: flag bench, ES index recovery, KB consolidation

- **Flag bench** (`scripts/node3090-flag-bench.sh`): ubatch 512→2048 = +5% pp (1323→1391 t/s @9k tok uncached), tg flat 38.1 t/s, +508MB VRAM → canonical stays 512/2048. Stack auto-restored by the script.
- **ES index loss root-caused**: es-data volume died in the 2026-06-08 WSL cascade; only lse-kb was reseeded; missing indices silent until first read (record_error 404 tonight). Recreated via `rag/02-es-setup.py`. lse-rfc-kb reseeded: 628 chunks / 13 RFCs / fully tagged.
- **RFC KB usage**: 0 `search_rfc` calls in 44,637 logged commands despite being wired since v1.5.18 — tagging investment deferred; docstring/prompt triggering review queued.
- **KB consolidation**: ONE real KB — repo `kb/` (git, Cowork-editable); `/opt/local-se/kb` → symlink. Old copy backed up (`kb.pre-link.bak`), 6 missing session blocks merged back, deduped to 13. Cowork cannot mount WSL UNC paths (product limit) — inverted-alias is the standing pattern.
- **lse-kb reseed** with `--reindex` delegated to LSE (doc count 53 → TBD).

---
## 2026-06-12 — P21 (Cowork) continued: P0 model store reconciliation + Hermes KB entry

### Hermes KB entry — LSE relationship (installed)
- Installed via Hermes's own memory tool: LSE `call_hermes` task → Hermes read `/tmp/hermes-kb-lse-relationship.md`, saved to persistent memory. Hand-editing `.hermes/memories/USER.md` rejected (agent-managed, lock-protected, injected every turn).
- Verified cross-channel via Telegram "what is LSE".

### P0 model store reconciliation — node3090 (SY5 directive, post-incident)
- `/opt/models` was a single root-owned symlink → `~/.lmstudio/models` (the incident's root cause). Removed; real `/opt/models` created; all models migrated via same-fs `mv` — zero downtime, running server kept serving off the mmap'd inode.
- 18 `.gguf` files `chattr +i` immutable. sha256: `/opt/models/SHA256SUMS` + `kb/node3090-model-sha256sums.md`. Qwen3.6-27B hash `33625d8d…` matches the byte-exact HF recovery.
- Canonical launch consolidated: `/opt/local-se/scripts/start-llama-server.sh` rewritten (was missing `--cache-type-v q8_0`, `--parallel 1`; had `--threads 8` vs 7/7; logged to `/tmp`). ctx-size canonized at 81920 (SY5 decision). Runbook step 2 now calls the script — edit the script, not the runbook.
- Verification restart: brief full outage caused by a two-operator race (LSE ran its own restart sequence concurrently with the WSL one-liner; pkill killed LSE's fresh server, script child died with the SSH session). Recovered via the new script: PID 44564 READY, gateway + socat active, Hermes notified pre/post.
- Lesson (also logged by LSE): agent self-reports ≠ ground truth — Hermes echoed LSE's stale PID 43871 instead of verifying. And: ONE operator at a time on the stack.
- Follow-ups in ROADMAP: LM Studio repoint to `/opt/models`, lse-errors ES index reinit, other nodes, node-t3-006 design.

---

## 2026-06-11 — P21 (Cowork): node3090 stack recovery + gateway TimeoutStopSec fix

### Stack recovery (per Restart _Hermes.md)
- llama-server relaunched with canonical command (PID 41557, READY), hermes-gateway + hermes-socat active
- Root cause of "silent" step-1 failures: `pkill -f llama-server` self-matched the SSH shell's command line — killed the session (and a likely-healthy backend) before printing. Log showed graceful "cleaning up before exit", not OOM.
- `Restart _Hermes.md` step 1 patched to `pkill -f "[l]lama-server"`; KB entry appended to `kb/session-learnings.md`

### hermes-gateway TimeoutStopSec fix
- Drop-in `/etc/systemd/system/hermes-gateway.service.d/timeout.conf`: `TimeoutStopSec=210s` (> drain_timeout 180s)
- Verified: `TimeoutStopUSec=3min 30s`, gateway active. Ends the SIGKILL-mid-drain / exit-code-1-on-stop pattern.

---

## 2026-06-05 — P4 (Cowork): v1.5.18 safety patch + HA challenge plumbing

### Tool patch (v1.5.18 in-place — safety fix)
- Added `_BLOCKED_WRITE_FILENAMES` set to `_is_allowed_write()` — blocks `.bashrc`, `.bash_profile`, `.profile`, `.zshrc`, `.zlogin`, `.zshenv`, `.fishrc`, `.ssh/authorized_keys`, `.ssh/config`, SSH private keys, `.gnupg/gpg.conf`
- **Root cause:** LSE wrote bare `-e` to `~/.bashrc` during HA token debugging session; `_ALLOWED_WRITE_PREFIXES` included `/home/` with no filename exclusions
- New SHA-256: `017443197a3d53fcf66a910fb8daa54248c98993411e297295d18e73dcb8a34a`

### HA challenges
- `seed_challengedb.py`: added ha-t2-002 (Template Sensor Audit T2) and ha-t3-001 (Template Migration T3, requires_human_approval=1)
- All 4 HA challenge `api_base` updated: `192.168.1.x` → `homeassistant.home.arpa`
- HA Pi confirmed reachable at `homeassistant.home.arpa:8123`
- HA token: JWT format (eyJ prefix) is correct — LSE misdiagnosed as invalid; KB doc at `docs/kb/ha-long-lived-token-format.md`
- Live DB patched: `UPDATE challenges SET starting_state = replace(starting_state, '192.168.1.x', 'homeassistant.home.arpa') WHERE id LIKE 'ha-%'`

---

## 2026-06-05 — P3 (Cowork): SearXNG Engine Health Dashboard — 6 tuning-signal panels

**Dashboard file:** `/home/sy5/docker/grafana/dashboards/searxng-engine-health.json`
New section **"Engine Tuning Signals"** appended (row id=20, panels 21–26, starting y=44).

| Panel | Type | Query | Signal |
|---|---|---|---|
| Avg Response Time — Slowest First | bargauge | `sort_desc(response_time_total_seconds)` | Red >5 s |
| Result Yield — Lowest First (1 h) | bargauge | `rate(result_count) / rate(request_count)` | Red <2 results/req |
| Reliability Event Rate — 24 h | bargauge | `rate(reliability_total[24h])` | Near-zero = suspect |
| Error Rate by Engine × Error Type | table | `rate(searxng_engine_errors_total[5m])` | No data until error-exporter fires |
| Dead Engines — zero requests 1 h | table | `increase(request_count[1h]) < 0.5` | Removal candidates |
| Response Time Trend per Engine | timeseries | `response_time_total_seconds{engine_name=~"$engine"}` | Filterable via $engine var |

**Label verification:** all 6 core metrics confirmed with `engine_name` label. `searxng_engine_errors_total` has zero series — error-exporter not active; Panel 24 is wired and waiting.

**Deployment:** provisioner has `allowUIUpdates: false` — UI edits revert in ~10 s. Edit the JSON file; provisioner auto-reloads within 30 s. Admin credentials confirmed (used `admin` + Vaultwarden password via browser session).

**P4 (error-exporter) deferred** — persistent open item. Panel 24 requires `searxng_engine_errors_total` to exist in Prometheus before it shows data.

---

## 2026-06-05 — Session 6: Claude L2 + Research presets — system prompts written, filter v1.2.0

**Claude model presets — deployed ✅:**
- `LSE L2 — Claude Opus` (`claude-opus-4-6`): escalation engineer role — knows full infrastructure, same permission boundary as Qwen3, framed to analyse prior failed attempts and deliver working solutions
- `LSE Research — Claude Sonnet` (`claude-sonnet-4-6`): research + KB curation — web research, SearXNG diagnostics, KB gap analysis
- Both presets: LSE tool v1.5.18 attached, no routing filter
- System prompts in `prompts/claude-l2-system-prompt.md`

**OpenWebUI filter architecture confirmed:**
- Routing filter Global toggle is **OFF** — not applying globally, Qwen3 preset only
- Routing filter stays at **v1.1.0** — Global OFF makes model-aware v1.2.0 unnecessary
- v1.2.0 built and kept as reference (`tools/lse-routing-filter-v1.2.0.py`) but not deployed

**Prompt file location convention:** Claude preset system prompts live in `prompts/` alongside Qwen3 versioned prompts, not `docs/`. README updated.

---

## 2026-06-05 — Routing filter v1.2.0 — model-aware passthrough

**Finding:** OpenWebUI filters/functions are globally enabled — no per-model or per-preset toggle exists in the UI. The routing filter v1.1.0, once enabled as a Function, fires for every model including Claude presets. Qwen3-specific tail-routing hints would be injected into Claude's context.

**Fix — `tools/lse-routing-filter-v1.2.0.py`:**
- New valve: `target_model_pattern` (default: `"qwen"`) — case-insensitive substring match against `body["model"]`
- `inlet()` returns body unmodified if model ID does not contain the pattern
- `claude-opus-4-6` and `claude-sonnet-4-6` pass through cleanly
- Empty pattern (`""`) restores old behaviour (apply to all models)
- Syntax verified: 167 lines · `ast.parse()` OK

**VALVES.md and CURRENT-STATE.md updated.** Deploy: Admin → Functions → replace v1.1.0 with v1.2.0. No valve changes needed — default covers the common case.

---

## 2026-06-05 — Session 6: SearXNG v3 live, SSL fixed, NVD + Semantic Scholar operational

**SearXNG v3 config applied:**
- bing news (wt 3) + google news (wt 3) + NVD (wt 3) now active
- NVD engine: was disabled on startup + SSL crash → ✅ returns CVEs with CVSS scores
- Semantic Scholar: was SSL crash (EngineError) → ✅ returns papers with metadata
- All pre-existing engines unaffected

**SSL root cause resolved:**
- Root cause chain: port confusion (diagnostic ran against wrong :8888 instance, not production :8088) → wrong env var (REQUESTS_CA_BUNDLE is for `requests` library; SearXNG uses `httpx` which reads `SSL_CERT_FILE`) → NVD upstream default `disabled: true` (our override works correctly now SSL is fixed)
- Fix: `SSL_CERT_FILE` env var pointing to host CA bundle — clean permanent solution
- `entrypoint-wrapper.sh` removed — was patching certifi inside the container, no longer needed

**Legacy cleanup:**
- `/home/sy5/searxng-docker/` (dead May-28 artifact) fully removed
- Confirmed: zero containers from old project; all four monitoring containers belong to `/home/sy5/docker/`
- Only active Docker Compose project: `/home/sy5/docker/` — grafana, prometheus, searxng, searxng-logger
- No port conflicts, no orphaned configs

---

## 2026-06-04 — Session 5: 63/63 eval, T2/T3 NAS + Samsung TV chains, 259.1 pts

**Eval:**
- Prompt v0.5.13 → v0.5.14 deployed (tool v1.5.18 confirmed). Run 7 partial (4 targeted tests):
  P4/M3/W1/A3 all 3/3. v0.5.14 added Docker NAT topology note; A1 confirmed 3/3 → **63/63**.
- eval-report-v6.md written.

**Arena — NAS chain (pf-t1-002 → nas-t2-001 → nas-t3-001):**
- nas-t2-001: NAS Unexpected Port Investigation — SOLVED a1 · 19.5 pts · 81.6s
  FTP anonymous login allowed (ftp_anonymous_allowed=True). 4 unexpected ports classified.
- nas-t3-001: NAS Anonymous Access Hardening Verification — SOLVED a1 · 19.5 pts · 42.9s
  restrict_anonymous=2 confirmed at source. SMB + FTP anonymous blocked. KB hit 40.934.

**QNAP anonymous access fix (human-applied, KB indexed at quality 1.0):**
- Root cause: QNAP QTS 4.x generates smb.conf dynamically on restart. Manual edits overwritten.
- Fix: `setcfg global "restrict anonymous" "2" -f /etc/config/smb.conf` + SMB restart.
- FTP anonymous: disabled via QNAP Control Panel → FTP Service.
- KB doc_id: 7ac7c02c1d118662 (quality 0.95 → 1.00, refinement +1).

**Arena — Samsung TV chain (net-t2-011 → net-t3-002):**
- net-t2-011: Samsung TV Traffic Analysis — SOLVED a1 · 19.5 pts · 73.5s
  Lease confirmed, WAN traffic found (4 destinations), risk assessed.
- net-t3-002: Samsung TV WAN Isolation — SOLVED a1 · 19.5 pts · 45.7s
  pfSense WAN block rule created for 192.168.1.90. Rule confirmed active.

**pfSense write-access protocol finding (KB indexed):**
- `/api/v2/system/api` returns 404 on pfSense Plus 26.03.1.
- Read-only toggle NOT controllable via REST API — web UI only.
- To verify: PATCH probe returns 403/read-only error when active.
- net-t3-002 a3 assertion patched: `write_access_re_enabled` → `write_access_verified_inactive`.

**Final leaderboard:** `qwen3.6-27b-q4-64k` — 259.1 pts · 15 eps · 14 solved · 0 esc · avg 1.13 att · **15/15 KB hits**

**Open:** SearXNG Grafana engine error panels show no data (engine errors + error rate by engine 5m stacked). Pending fix next session.

---

## 2026-06-04 — T1 arena complete: 10/10 challenges, 161.6 pts, 0 escalations

**Final T1 leaderboard:** `qwen3.6-27b-q4-64k` — 161.6 pts · 10 eps · 9 solved · 0 esc · avg 1.20 att · **10/10 KB hits**

All 10 T1 challenges solved first attempt with KB assist. Notable findings:
- NAS `192.168.5.45` (n45.home.arpa): 3 NFS exports, 4 SMB shares, 450 GB free
- HA: version 2024.6.3, 12 entities, **2 stale automations** flagged
- Samsung TV 192.168.1.90: DHCP hammer confirmed across multiple challenges
- The ha-t1-004 → ha-t1-008 KB chain fired within 4 minutes — same session

One challenge failure before fix (pf-t1-003): model hallucinated `.10` for NAS IP (actual: `.45`) from stale KB. Fixed by correcting the challenge starting_state. Demonstrates KB data quality risk when ground-truth IPs are missing from KB seed.

**Next:** ChallengeGenerator `--list-pending` after re-seed, then T2 challenges from discoveries.

---

## 2026-06-04 — ChallengeGenerator — discovery-driven challenge authorship

**`scripts/challenge_generator.py`** — 582 lines

The arena now grows from its own discoveries. When an episode finds something unexpected, the generator proposes a follow-up challenge automatically.

**Architecture:**
- `SignalDetector` — rule-based scan of the model's parsed JSON response for 4 triggers:
  - `unexpected_ports` list non-empty (pf-t1-002 NAS finding: 5 ports on 192.168.5.10)
  - `unexpected_findings` string non-empty (net-t1-009 confirmation: same NAS IP)
  - `anomalies` string non-empty (pf-t1-003 Ollama narrative output)
  - `top_blocked_ips[0].count > 200` (Samsung TV DHCP hammer class)
- `ChallengeAuthor` — calls `llama3.2:3b` via Ollama to generate title, description, 3 machine-checkable assertions, failure modes. Falls back to OpenWebUI local model.
- `ChallengeGenerator` — orchestrates pipeline, deduplicates, inserts to ChallengeDB with `status='pending_review'`

**Human approval gate:** All auto-generated challenges start as `pending_review`. Run before they execute in episodes:
```bash
python3 scripts/challenge_generator.py --list-pending
python3 scripts/challenge_generator.py --show   auto-pf-t1-002-unexpected-abc123
python3 scripts/challenge_generator.py --approve auto-pf-t1-002-unexpected-abc123
python3 scripts/challenge_generator.py --reject  auto-pf-t1-002-unexpected-abc123
```

**Tier elevation:** Auto-generated challenges spawn at `parent_tier + 1` (T1 discovery → T2 follow-up). The `parent_episode_id` links every challenge back to the finding that created it.

**Schema additions** to `challenges` table: `auto_generated INTEGER`, `parent_episode_id INTEGER`, `status TEXT DEFAULT 'active'`

**Wired into `run_episode.py`:** after each SOLVED episode, `_extract_json(last_response)` feeds the generator. Non-fatal — won't break episode runs if generator errors.

---

## 2026-06-04 — pf-t1-003 assertion fix + JSON truncation repair

**Root cause:** pf-t1-003 episode TRUNCATED despite model producing correct data.
Two distinct bugs exposed:

**Bug 1 — challenge assertion design:** `assert len(log_entries) >= 100` failed with
`TypeError: object of type 'int' has no len()` on attempt 1, where the model correctly
returned `log_count: 1245` as an integer. Intent was always "count ≥ 100", not "return
a list". Fixed: changed key to `log_count`, assertion to `assert int(log_count) >= 100`.
Also updated challenge description to explicitly say `use pfsense_log_summary()` and
`return log_count as an integer`.

**Bug 2 — `_extract_json()` truncation handling:** Attempts 2 and 3 opened a valid
` ```json ` block but hit `MaxPredictTokens=8192` before the closing ` ``` ` arrived.
The extractor silently returned `{}` — 0/3 NameErrors on all assertions.

Fix: added two new fallback paths to `_extract_json()`:
- Unclosed fence: `re.search(r"```json\s*(.*?)$", text, re.DOTALL)` extracts partial content
- Stack-based repair in `_repair_truncated_json()`: walks the string tracking open `{`/`[`
  with string-escape awareness, builds the exact closing suffix in correct nesting order
  (handles mid-entry truncation where simple bracket counting gives wrong order)

All 7 original smoke tests still pass. Re-seed LUCIFER: `python3 scripts/seed_challengedb.py --reset`

---

## 2026-06-04 — rfc_kb.py — RFC authority model (§3.5)

**`scripts/rfc_kb.py`** — RFC corpus ingestion and authority-weighted search

**Authority model:**
```
quality_score = min(authority_ceiling,
                    raw_score × confirmation_weight × recency_weight)
```
- `authority_ceiling`: Internet Std 0.95 · Proposed Std 0.85 · Informational 0.70 · Obsoleted 0.30
- `recency_weight`: 1.0 if current · 0.30 if obsoleted_by is set (RFC age does NOT drive this — RFC 793/1981 is still valid TCP; RFC 9293 obsoletes it, so 793 gets 0.30)
- `confirmation_weight`: starts 1.0 · ×1.1 per successful resolution citing section · ×0.95 per failure · `bump_confirmation()` updates ES doc in place

**20-RFC registry** covering LSE domain: DHCP (2131/2132), DNS (1034/1035/2308/2782), TLS (8446/5280), TCP (9293/792/1122), CIDR (4632), HTTP (9110/9112), Syslog (5424/5426), NTP (5905), NAT (3022), NFS (7530/1813)

**Three-layer retrieval:**
1. Protocol taxonomy filter (deterministic — `--protocol dhcp`)
2. kNN dense search on symptom+content embedding (nomic-embed-text)
3. Re-rank by `quality_score × ES relevance score`

**Symptom tagging** (offline, one-time at index time): Ollama `llama3.2:3b` generates 8-12 operational symptoms per RFC section — bridges the gap between "Samsung TV DHCP hammer" and RFC 2131 §4.4.5. Embedding is `symptom_tags + content` concatenated for richer retrieval.

**CLI:**
```bash
python3 scripts/rfc_kb.py --list                    # show registry
python3 scripts/rfc_kb.py --dry-run 2131            # chunk + print, no ES write
python3 scripts/rfc_kb.py --index 2131              # index single RFC
python3 scripts/rfc_kb.py --index-all               # full corpus (run once on LUCIFER)
python3 scripts/rfc_kb.py --index-all --no-tag      # skip Ollama, faster
python3 scripts/rfc_kb.py --search "DHCP DISCOVER repeated after ACK"
python3 scripts/rfc_kb.py --search "cert verify failed" --protocol tls
python3 scripts/rfc_kb.py --status                  # chunks + quality per RFC
```

**Next:** add `search_rfc()` to tool v1.5.18 so LSE can call it during escalation context building. Run `--index-all` on LUCIFER to populate `lse-rfc-kb`.

---

## 2026-06-04 — First live arena episode: pf-t1-001 SOLVED

**Episode result:**
- Challenge: pf-t1-001 — LAN Device Map (sysadmin 1.0×)
- Model: qwen3.6-27b-q4-64k (64k ctx · KV:q8_0 · think:3072)
- Outcome: SOLVED · attempt 1 · 3/3 assertions
- Raw reward: 15.0 (10 solve + 3 assertions + 2 KB hit bonus)
- Wall time: 105.9s
- KB assisted: ✅ hit on "LUCIFER Network Inventory: DHCP Static Mappings" (score 13.188)
- Escalated: No

**What this confirmed:**
- Full wrapper stack works end-to-end on LUCIFER (EscalationWrapper → TimeLimit → RecordEpisodeStatistics)
- KB hit at reset fires correctly — prior session knowledge injected before attempt 1
- Solution indexed at quality 0.9 — compounds for future episodes
- Model produced 21-device list with MACs from KB context alone (no live API call needed)
- LeaderboardService auto-recording wired into run_episode.py

---

## 2026-06-04 — Tool v1.5.17 — pfsense_log_summary + nmap_summary

**Problem solved:** pfSense firewall logs and nmap output are too large for direct
context injection. `GET /api/v2/status/logs/firewall` can return hundreds of KB;
raw nmap output is thousands of lines. Both fill the model context and trigger
truncation, making analysis unreliable.

**Solution (Option B — tool-level summarisers):** Two new tool functions that
replace direct raw-data calls. The model calls these instead of `pfsense_query`
or `execute_command('nmap ...')`.

**`pfsense_log_summary(hours, top_n, api_key)`** — `tools/openwebui-tool-v1.5.17.py`
- Fetches raw logs via pfSense REST API
- Programmatic extraction (Tier 1): top blocked IPs, top blocked ports, pass/block ratio per interface
- Ollama narrative summary (Tier 2, optional): `llama3.2:3b` anomaly detection on compact context
  Fires only if Ollama is reachable; skipped silently otherwise — summary is complete without it
- Never returns raw log lines. Output: ~600–900 chars regardless of log volume
- Docstring explicitly forbids calling `pfsense_query('/api/v2/status/logs/firewall')` directly

**`nmap_summary(targets, top_ports, known_services)`**
- Runs `nmap -sV --top-ports N -oX -` (XML output) — never raw text
- Parses XML: per-host open ports + service version strings
- Cross-references against `known_services` JSON baseline — flags unexpected ports
- Returns compact JSON: scan_results, unexpected_ports, host_count, scan_time_s, command
- Docstring forbids `execute_command('nmap ...')` for network audits

**Architecture note:** Tier 1 (programmatic extraction) satisfies all T1 assertions
deterministically. Ollama (Tier 2) handles narrative-only assertions. LSE never
sees raw logs or raw nmap output.

SHA-256: `f30c1e97493aa6f58fe3498df94c15784d747a5e1e04a209a405251e5211c973`
Status: built and syntax-verified — **pending deploy to OpenWebUI**

---

## 2026-06-04 — LSEChallengeEnv complete, 7/7 smoke tests

**LeaderboardService** — `scripts/leaderboard.py` ✅
- SQLite-backed (`/opt/local-se/leaderboard.db`, WAL mode)
- `record_episode(result_dict)` — inserts row, recomputes final_points = raw_reward × discipline_mult
- `standings()` — cumulative points per model, sorted desc
- `model_stats(model_id)` — per-discipline breakdown
- `recent_episodes(n, model_id)` — filtered history
- `challenge_history(challenge_id)` — all episodes for a challenge, oldest first
- `print_standings()` — formatted table to stdout
- 9/9 smoke tests passing

**run_episode.py** — full wrapper stack wired ✅
- `build_env()`: `LSEChallengeEnv → EscalationWrapper → TimeLimit(3) → RecordEpisodeStatistics`
- `call_model()`: OpenAI-compat POST, Qwen3 thinking mode on stagnation
- `run_episode()`: full loop, returns result dict for LeaderboardService
- CLI: `--list`, `--challenge`, `--dry-run`, `--model`, `--endpoint`, `--json`

**EscalationWrapper** — `scripts/escalation_wrapper.py` ✅
- Sits above LSEChallengeEnv; manages full escalation gate
- KB context injection at reset via ES kNN + BM25 hybrid search
- Cosine stagnation detection (threshold 0.85) on attempt embeddings (nomic-embed-text)
- Stagnation-breaking frame injection on count=1; web search on count=2+
- Mandatory SearXNG web search + unconditional KB indexing before escalation
- Claude API call (anthropic SDK → OpenWebUI fallback) with full context package
- Dual KB writes on escalation: `record_error()` (lse-errors) + `index_to_kb()` (lse-kb, quality 1.0)
- Point deltas: −5 escalation, +1 indexing, +2 context quality, +2 KB hit, +1 rollback/health (TODO)
- 9/9 smoke tests passing with mocked HTTP (unittest.mock)

**LSEChallengeEnv** — `scripts/lse_challenge_env.py` ✅
- `gymnasium.Env` wrapping ChallengeDB (SQLite)
- `reset()` / `step()` / `render(ansi)` / `list_challenges()` implemented
- Assertion eval in restricted exec namespace (`_SAFE_BUILTINS` allowlist — generator-safe)
- `_is_rfc1918()` domain helper injected into assertion namespace
- Solve bonus: 10/7/4 for attempt 1/2/3; partial credit = assertions passed
- 7/7 smoke tests passing: reset, correct-solve (13.0 reward), partial (2.0), truncation, discipline multiplier, RFC1918 helper, list_challenges

Next: `EscalationWrapper` (stub at `scripts/escalation_wrapper.py`)

---

## 2026-06-03 — Tool v1.5.16, pfSense SSL, session close

**Tool v1.5.16** — deployed ✅ (SHA-256: bcc04bb0fa3d944c9fa5a4e4786393950b2efc32f0ad69962716a217f88a66d1)
- `PFSENSE_CA_CERT` valve + `_pfsense_verify()` helper
- Uses `/opt/local-se/cert/pfsense-webgui-ca.crt` (sy5:sy5 644, valid → Apr 2036)
- Falls back to `verify=False` with logged warning if cert missing
- pfSense TLS now fully verified against WebGUI CA
- git: `7275f45`

**Repo hygiene pending:** `openwebui-tool-v1.5.14-BKP.py` committed accidentally — needs `git rm` + `.gitignore` rule for `*.BKP`

## 2026-06-03 — Tool v1.5.15, security hardening, launcher v1.078 + GUI v1.4

**Tool v1.5.15** — deployed ✅ (SHA-256: b9d00a17ad44eda7c4630368a7a19fde9d282e7871536ae306482e619a9c9dd0)
- `pfsense_query(endpoint, method, payload, api_key)` — pfSense REST API v2 client
- `PFSENSE_URL` + `PFSENSE_API_KEY` valves added
- `LOG_FILE` default moved to `/opt/local-se/agent_commands.log` (away from root-owned `~/.lse/`)
- SSL `verify=False` with rationale (LAN-only, self-signed cert); v1.5.16 will add `PFSENSE_CA_CERT` valve

**Tool v1.5.14** — deployed ✅ (SHA-256: 1cf298f74364426c4d25a06fb64cf43f7519c80a91b7d58a0799b3b4986b0e17)
- `sudo_delegation_block` gains `step_number`, `total_steps`, `verify_command` params
- THINKING PHASE RULE: never call inside `<think>` block

**Security hardening — `.lse` directory and secrets**
- `/home/sy5/.lse/` → root:sy5 710 (traversable by sy5 group, not listable)
- `/home/sy5/.lse/secrets` → root:sy5 640 (sy5 group readable, BW_PASSWORD via env var)
- `BW_PASSWORD` removed from OpenWebUI valve (plaintext SQLite) → sourced from `~/.lse/secrets`
- Vaultwarden tool v1.3.0: env var priority over valve, placeholder default in UI
- VALVES.md created — full valve registry with security posture for all tools

**Launcher v1.078 (CLI) + GUI v1.4**
- `$LaunchDir` moved from `/home/sy5/.lse/launch` to `/tmp/lse/launch` (tmpfs, RAM-backed, ~10× faster)
- Secrets pre-flight check + `webui.sh` sources `~/.lse/secrets` before OpenWebUI starts
- GUI v1.4: profiles from `lse-profiles.xml` (fixed broken line-offset parsing from v1.076)

**pfSense REST API**
- pfrest.org package installed (v2.8, Plus 26.03) — one SSH command
- Read-only, LAN+WAN+OPT1+OPT2 interfaces, access list: 192.168.1.57/32
- Write access protocol documented in arena doc and ROADMAP

**Checksums introduced** — SHA-256 for last two tool versions tracked in CURRENT-STATE.md

## 2026-06-03 — Prompt v0.5.12 + Tool v1.5.14, Challenge Arena design consolidated

**Prompt v0.5.12 + Tool v1.5.14** — deployed to OpenWebUI ✅
- Fix 1: STEP MILESTONE HEADERS — `── Step N/Total: [description] ──` required before each step on 4+-step tasks
- Fix 2: THINKING PHASE RULE added to sudo_delegation_block — must not fire inside `<think>` block
- Fix 3: sudo_delegation_block gains `step_number`, `total_steps`, `verify_command` params; block format updated

**LSE Challenge Arena** — design document written (`docs/lse-challenge-arena.md`)
- Reconstructed from lost session conversations
- Covers: point structure, discipline weights, escalation protocol (convergence detection), KB isolation (shared pool / public goods game), architecture sketch, 50-challenge ladder across pfSense and HA domains, challenge schema (SQLite), build order
- HA sandbox: HA Core Docker confirmed as approach (~1hr deploy, frictionless config porting)
- pfSense sandbox: log replay (syslog corpus already flowing to LUCIFER)
- VRAM concurrency strategy for 3-model parallel episodes: open, decision pending

## 2026-06-03 — SearXNG 27-engine deploy, syslog live, network topology

**SearXNG 27-engine config deployed** ✅
- Config already written to `/home/sy5/docker/searxng_data/settings.yml` — container just needed restart
- `valkey:` section added (replacing deprecated `redis:` key) — wires Valkey to limiter + caching
- `limiter: true` re-enabled after testing
- Verified: 27 engines configured, 11 active on `q=llama.cpp&categories=general,it,science`, 108 results
- Brave suspended during testing (VPS rate-limiting confirmed) — weight 1 is correct
- **Bug found:** `search_web` tool sends no `X-Forwarded-For` header → gets 429 from limiter; also missing `categories=general,it,science` → misses arxiv/github/scholar. Fix in tool v1.5.13.

## 2026-06-03 — Network infrastructure bootstrap, syslog live

**pfSense syslog pipeline established**
- pfSense Plus 26.03.1 confirmed at 192.168.1.50 — no built-in REST API (docs verified)
- SSH access confirmed: `ssh admin@pfsense.home.arpa`
- Syslog config was not written to `/etc/syslog.conf` on first GUI save — root cause: syslogd was not restarted
- Fix: re-saved settings in GUI → config regenerated → syslogd restarted with new PID
- pfSense → LUCIFER:514 UDP syslog now live and verified with tcpdump + nc
- WSL2 mirrored networking confirmed working (ping + port binding)

**Network topology expanded — three subnets confirmed**
- 192.168.1.0/24: LAN (pfSense, LUCIFER, HA Pi, Samsung TV)
- 192.168.5.0/24: NAS subnet (TS-419P II via igc2)
- 192.168.10.0/24: Solar/IoT subnet (inverter at 192.168.10.3 via igc3, already in HA)

**Syslog-derived findings (first 10 min of data)**
- Samsung S90C TV (192.168.1.90, MAC 1c:af:4a:04:5f:b6): DHCP hammer every 1–2 min + unblocked WAN access
- `filterdns: cisco.lan` stale DNS host override — superseded by .home.arpa domain migration
- cloudflare.time.com DNS reverse lookup error on Samsung TV DHCP events (benign)

**docs/network-topology.md** created with full node inventory, subnet map, service placement, WSL2 networking options, T1 challenge set (10 challenges), HA Pi add-on capacity table, future Pi 4 NAS plan, pfSense bootstrap section

## 2026-06-02 — Tool v1.5.12 deployed, prompt v0.5.10, tracking restructure `c5e3d84`

**Tool v1.5.12** — deployed to OpenWebUI
- `write_file` SIZE SANITY CHECK: code-level gate rejects overwrites where new content < 25% of existing line count; `force=True` override after explicit user confirmation
- `record_outcome(doc_id, success, notes)`: tracks empirical_runs, success_count, failure_count on KB docs
- `mentor_correct(doc_id, correction, new_quality)`: human correction with re-embed; never lowers quality score

**Prompt v0.5.10** — written (deploy to OpenWebUI pending)
- ENVIRONMENT: v0.5.10, tool v1.5.12
- TOOLS `write_file`: added `force` parameter documentation
- TOOLS `mentor_correct`: corrected signature `authority` → `new_quality`
- TOOLS `record_outcome`: corrected parameter `note` → `notes`
- OUTPUT RULES: added write_file SIZE SANITY CHECK handling rule

**Eval test-suite-v2.md** — P6 added (write_file overwrite size regression); total /57 → /60

## 2026-06-02 — Tracking restructure

- Introduced `CURRENT-STATE.md` (auto-reconcilable version table)
- Introduced `CHANGELOG.md` (this file, append-only)
- Stripped `ROADMAP.md` to open items only
- Fixed tool filename mismatch: `openwebui-tool-v1.5.10.py` renamed to `openwebui-tool-v1.5.11.py`
- Identified gaps: `record_outcome` / `mentor_correct` not yet implemented in tool; `write_file` SIZE SANITY CHECK not yet implemented

---

## 2026-06-01 — Tool v1.5.11 (fetch_url, monitor_download), RAG stack, ES memory floor, SearXNG observability, prompt v0.5.9

**Tool v1.5.11 — two undocumented additions (reconstructed from code)**
- `fetch_url(url, max_chars)` — HTML-stripped full-page fetch; part of SEARCH-THEN-FETCH protocol (Step 3 of search_web sequence). Strips script/style/nav/footer/head tags.
- `monitor_download(file_path, expected_bytes, interface)` — Prometheus-backed download progress monitor. Returns DOWNLOADING / COMPLETE / STALLED with ETA and SLEEP N. Uses `/opt/local-se/download-monitor.py` and Prometheus at localhost:9090.
- Note: v1.5.11 was saved as `openwebui-tool-v1.5.10.py` — filename mismatch (pending rename).
- Note: `record_outcome` and `mentor_correct` referenced in prompt v0.5.9 TOOLS section were NOT implemented in this version — tracked as open items.

## 2026-06-01 — RAG stack, ES memory floor, SearXNG observability, prompt v0.5.9

**RAG Stack (tool v1.5.9 → v1.5.11, prompt v0.5.7 → v0.5.9)**
- Elasticsearch 8.17.0 + Ollama nomic-embed-text (CPU) deployed on lse-net
- Four RAG tool functions added: `search_kb`, `index_to_kb`, `record_error`, `check_error_kb`
- KB-FIRST RULE: `search_kb` called before every `search_web`
- 12 seed KB docs / 32 chunks indexed at quality 0.3–0.6
- Error KB populated from WAN2.1 deployment session
- Mentor-authority entries indexed (Grafana-check-before-process-kill pattern, quality 0.95)
- `compact_context` (v1.5.8): true in-place compaction via OpenWebUI REST API + KV cache erase

**ES Memory Floor**
- ES was exiting code 143 (Docker OOM) — `docker inspect` confirmed Memory=0
- Migrated to `/home/sy5/docker/docker-compose.yml` with `mem_limit: 2g`, `mem_reservation: 1g`
- Merged alongside grafana, prometheus, searxng — orphan warning eliminated
- Named volume `es-data` preserved
- `dcd` alias added to `~/.bashrc`
- `lse:stack-health-check` skill updated with ES recovery

**SearXNG Observability Restoration**
- `/metrics` endpoint was returning 404 — root cause: `open_metrics` password missing
- Fix: added `open_metrics: 'metrics-admin-2025'` + `enable_metrics: true`
- Prometheus scrape job restored with `basic_auth.password`
- Grafana dashboards now receiving live `searxng_engines_*` data

**SearXNG 27-engine config prepared (NOT YET DEPLOYED)**
- Brave **demoted** (lower weight, not removed) — still contributes despite VPS rate-limiting
- 27-engine target: arXiv T1 weight 4, Google Scholar weight 3, Bing+DDG weight 2, Brave+Mojeek+Qwant weight 1, Wikipedia+Bing News always-on
- Config path confirmed: `/home/sy5/docker/searxng_data/settings.yml` (host) = `/etc/searxng/settings.yml` (container)
- Backups: `settings.yml.backup`, `settings.yml.backup-v1.0-20260525`, `settings.yml.bak`
- Valkey (Redis fork) already deployed on lse-net internal port 6379 — caching may already be available
- Production still running 4-engine set; Grafana confirms only Brave/DDG/Google/Wikipedia active

**Prompt v0.5.7–v0.5.9**
- v0.5.7: Grafana URL, KB path, RAG Tools v2, pip torch version guard, WARNING ESCALATION RULE, BACKGROUND PROCESS RULE, SYSTEM PACKAGE INSTALLATION RULE, RAG tool discipline rules
- v0.5.8: (inherits v0.5.7 changes)
- v0.5.9: MULTI-BLOCK TASK RULE — persistent `/opt/local-se/active-task.md` survives context resets; HANDOVER PROTOCOL updated to include active-task.md

---

## 2026-05-31 — WAN2.1 deployment

- Full WAN2.1 deployment on LUCIFER (RTX 4090, WSL2 Ubuntu 24.04)
- All models present and verified; I2V and T2V basic workflows tested
- T2V simplified and I2V upscale+framegen patched and ready
- ComfyUI Manager v4.2.1 active; `wan2-manager.sh` written
- WAN2.2 partially researched: 14B MoE (≥16 GB VRAM) and 5B hybrid (~8 GB) confirmed released

---

## 2026-05-29 — GUI launcher v1.1, Grafana context alert pipeline

**GUI Launcher v1.1**
- Click handler crashed PowerShell host — root cause: `ThreadPool.QueueUserWorkItem` has no runspace
- Fix: synchronous `Write-LaunchScripts` + `Start-WTSession` on UI thread; `DispatcherTimer` for PID poll
- Stale Authenticode signature stripped; errors now display in GUI status line

**Grafana Context Alert Pipeline**
- `lse-context-monitor-v1.3.0` inlet filter retired (used wrong metric prefix `llama_` vs `llamacpp:`)
- `llama-context-exporter` (port 9836, systemd) computes `llama_kv_cache_usage_ratio`
- `grafana-owui-adapter` (port 9837, systemd) converts Grafana JSON → OpenWebUI channel webhook
- Alert: `llama_kv_cache_usage_ratio > 0.8` for 1 min → `lse-alerts` channel
- Docker network `lse-net` consolidating all services
- End-to-end smoke test passed

**Tool v1.5.6 / v1.5.7**
- v1.5.6: POST-DELETE VERIFY RULE, NO YEAR INJECTION in search_web, `get_github_release` function
- v1.5.7: DESTRUCTIVE OPERATION PROTOCOL for `execute_command` (warn → name → ask yes/no → wait)

---

## 2026-05-26 — Grafana metrics integration

- `--metrics` flag added to launcher v1.063
- Prometheus scrape config targeting `localhost:8080/metrics`
- Grafana dashboard built with llama.cpp performance panels

---

## 2026-05-25 — Eval Run 4 (no-think), Eval Run 5 (partial)

- Run 4: tool v1.5.5 / prompt v0.5.2 / no-think (budget 0) → 49/57
  - S 15/15, P 13/15 (P3 no verify, P4 W2 regressions), M 9/9, W 7/9, A 5/9
  - Confirms thinking budget is load-bearing for P and A categories
- Run 5 (partial subset): tool v1.5.6 / prompt v0.5.2 / thinking → 15/21
  - P2 3/3 ✓, W2 3/3 ✓, A3 3/3 ✓ — targeted fixes confirmed
  - P1 0/3, P3 0/3 — execute_command lacked destructive-op gate → fixed in v1.5.7
  - A1 0/3 — questions answerable from inference, context monitor never triggered → prompt rework

---

## 2026-05-24 — Eval Run 3 — 57/57

- Tool v1.5.4 / prompt v0.5.1 / thinking (budget 3072) / test suite v3.2
- All 19 categories 3/3; perfect score
- P2 fixed (READ-FIRST RULE in sudo_delegation_block)
- A1 fixed (get_context_status field name corrected for llama-server build ≥9307)

---

## 2026-05-23 — Routing filter v1.1.0, tool v1.5.1–v1.5.4

- Routing filter v1.1.0 deployed
- v1.5.1: read_file PRIVILEGED PATH note; sudo_delegation_block stop instruction hardened
- v1.5.2: denylist hardening (shred, blkdiscard, rm -rf patterns, /mnt/ write block)
- v1.5.3: sudo_delegation_block STOP PROTOCOL — surface command in visible text
- v1.5.4: get_context_status field-name fix; sudo READ-FIRST RULE

---

## 2026-05-22 — Eval Run 2, prompt v0.4.1

- Run 2: tool v1.5.1 / prompt v0.4.1 / thinking → 45/57 (corrected to 54/57 on partial rerun)
- Baseline established for comparison

---

## Early sessions — Infrastructure, tool v1.4.x–v1.5.0, prompt v0.1–v0.4

- llama.cpp + OpenWebUI + SearxNG + Playwright stack stood up
- Windows Terminal launcher with three model profiles (32k, 64k, no-think)
- Tool v1.4.0: execute_command, read_file, write_file, sudo_delegation_block, search_web, get_context_status
- Tool v1.4.1–v1.4.3: routing rules, sudo pipeline fix, write_file protocol rewrite
- Tool v1.5.0: COMBINE RULE and search_web announcement promoted to docstrings; port 8088 fix
- Prompt v0.1 → v0.4.1: identity, permission boundary, live service rule, context handover
- Eval Run 1: unscored baseline
- Skills: `lse:eval-runner`, `lse:docstring-optimizer`, `lse:stack-health-check`, `lse:session-debrief`, `lse:version-manager`
- Docs: 01–06 written

---

## 2026-06-09 — P18 Cowork — pfsense-agent.py + OpenWebUI tool v1.6.1

### pfsense-agent.py — Option C orchestrator CLI
- Built `pfsense-agent.py`: natural language → Qwen3.6-27B (LM Studio node3090) → structured LSE prompt → LSE
- `--think` / `--no-think` / `--prompt-only` / `--auto` flags
- Streaming with live char/timing display
- Assistant prefill (`"Step 1: "`) for `--no-think` mode — forces clean output start
- `_extract_prompt` — DO NOT block anchor + contiguous ascending step sequence detection
  - `rfind(FIRST_DO_NOT)` → last DO NOT block; walk backwards through step matches to find sequence start
  - CRITICAL: use `^[ \t]*` not `^\s*` in multiline regex — `^\s*` swallows preceding `\n`, landing `match.start()` on newline instead of first space
  - Restores `Step 1: vault_unlock()...` when model correctly starts at Step 2
- Config: `/opt/local-se/pfsense-agent.conf` (chmod 600), `[lmstudio]` + `[openwebui]` sections
- `tool_ids: ["lse_system_admin_terminal", "lse_vaultwarden_tools"]` added to `submit_to_lse` payload

### OpenWebUI tool v1.6.1 deployed (lse_system_admin_terminal)
- Updated from v1.5.26 → v1.6.1 (pfSense three-tool architecture + schema introspection prohibition)
- Deployed via Admin → Tools → edit → paste → Save

### OpenWebUI API tool execution gap — confirmed
- `/api/chat/completions` with `tool_ids` injects tool definitions but local LM (Qwen3.6) generates
  reasoning text, not structured function-call JSON → agentic loop never fires
- Chat UI works because OWUI uses text-based tool invocation format (ReAct-style), not native FC
- Resolution: Dify multi-agent UI (see ROADMAP). OWUI pipe function deferred.

### Architecture decision — Dify for multi-agent UI
- Qwen3.6 (orchestrator/reasoning) + LSE (executor/tools) pipeline
- Deployed on-demand, not persistent always-on service
- OWUI pipe function for Qwen3.6 → LSE handoff: deferred

### pfSense security constraints confirmed
- SSH admin@pfsense = root shell, bypasses read-only API boundary — human-only, never LSE
- pfSense auth: `X-API-Key` header (NOT `Authorization: Bearer`)
