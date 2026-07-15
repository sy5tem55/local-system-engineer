"""
title: LSE Goethe v0.4.0-a
author: local-system-engineer
version: 0.4.0-a
requirements: elasticsearch==8.19.3, requests
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, ssh_run, ssh_script, read_file, write_file, sudo_delegation_block,
  search_web, get_github_release, get_context_status, compact_context, search_kb, index_to_kb,
  record_error, check_error_kb, record_outcome, mentor_correct, kb_verify, mentor_demote,
  time_check, run_tests, assert_state, pfsense_graphql, pfsense_query,
  pfsense_log_summary, start_node_agent, stop_node_agent, search_reddit, planner,
  plan_step_done, skill_search, skill_record,
  skill_outcome, task_checkpoint, and task_resume. Web tools share a code-enforced
  anti-spiral budget. All commands are logged to a persistent audit file. Privileged
  operations are blocked at the code level and routed through a delegation block.

  Changelog:
    Goethe v0.4.0-a: TRAUM Thread 3 (TRAUM-INSIGHT), Prompt 3.5 — [DREAM]
              banner. Wired tools/dream_digest.py's latest-digest.md into
              session start the CHRONOS way (server-injected, not
              docstring-dependent): _consume_time_banner() — already the
              single once-per-session gate for the [TIME] banner on the
              first search_kb return — now also appends a [DREAM] line
              (digest date + pending human-gate count + pointer to the
              full file), hard-capped at 200 chars. New valve
              DREAM_DIGEST_PATH (default /opt/local-se/dreams/latest-
              digest.md; empty disables the banner). Missing/unreadable/
              unparseable digest degrades to no [DREAM] line, never an
              error — same non-fatal discipline as dream_digest.py's own
              gather steps. Deliberately minimal per the PH5-2 warning
              (plan §2): one valve, one new private method
              (_dream_banner()), a 3-line change to an existing method —
              no restructuring of this god-class. DEPLOY NOTE: existing
              llama-ui threads do NOT pick up this change; each must be
              restarted (fresh thread) after goethe_mcp.py restart for the
              [DREAM] banner to appear, same as any other Tools-class
              behavior change.
    Goethe v0.4.0: TRAUM Thread 2 (TRAUM-ENGINE) begins consuming this file's
              existing Tools methods from a SECOND caller for the first time —
              no code in this file changed for this bump; recorded here because
              the write-path trust model now has to hold for two callers, not
              one. `tools/dream_runner.py` (new, offline, read-only over
              episodes/lse-kb/lse-errors) proposes `mentor_correct` +
              `record_outcome(success=False)` calls (dedup pass, Prompt 2.2,
              verified against the live ~365-doc lse-kb corpus) and is about to
              add `kb_verify`-probe suggestions + `record_outcome` demotions
              (stale/contradiction pass, Prompt 2.3). dream_runner.py itself
              NEVER calls these methods directly — it only ever writes
              proposals to `dreams/YYYY-MM-DD/proposals.jsonl`; only the
              not-yet-built `dream_apply.py` (Prompt 2.5), gated by a human
              confirm per proposal, will actually invoke them. Minor bump
              (0.3.9→0.4.0) rather than a patch: this is the first time this
              file's write surface has a second, non-interactive consumer in
              its design, not a bugfix to existing behavior. See
              docs/dreaming/DESIGN.md and CHANGELOG.md 2026-07-11 (TRAUM
              Thread 2 entry) for the full writeup.
    Goethe v0.3.9: pfSense hardening (2026-07-06 confirmed incident: an
              unbounded queryDiagnosticsTables/bogons response reached
              2,966,261 tokens against a 131,072 context window, and a
              separate unconfirmed pfsense_query write broke Unbound DNS
              forwarding). NEW _pfsense_cap_response(): every pfsense_graphql,
              pfsense_query, and pfsense_log_summary response is capped at
              32000 bytes with a truncation warning, applied uniformly since
              no content-based query check can enumerate every large
              built-in collection type in advance. NEW confirmed=False
              parameter on pfsense_query: real writes are blocked at the
              code level until confirmed=True is passed explicitly; exempt
              when the endpoint contains dry_run=true (validates without
              persisting, per Common Control Parameters). Reads
              (pfsense_graphql, pfsense_log_summary) are unaffected --
              no confirmed parameter added to either. See
              lse/skills/pfsense/DESIGN.md and the 2026-07-06 entry in
              kb/session-learnings.md for the full incident writeup.
    Goethe v0.3.8: PH3-2 retrieval decision (data-driven, gold set n=50).
              --compare verdict: LINEAR wins (recall@3 0.84, MRR 0.800) over
              RRF (0.84, 0.735; recall@1 −0.12) — search_kb ranking unchanged,
              null result recorded. Threshold finding: the 0.72 default was
              calibrated for cosine [0,1] but hybrid _score = 0.7·knn +
              0.3·BM25 runs ~3.5–16 — the filter was a NO-OP. New default
              min_score=4.2 from --threshold-report: keeps 38/38 correct
              top-1, rejects 3/11 wrong, loses zero correct. Re-sweep after
              major KB growth (BM25 stats drift with the corpus).
    Goethe v0.3.7: SSH post-mortem hardening (2026-07-04 LSE post-mortem on
              node3090 exit-255 storm; both root causes now code-enforced).
              ssh_run MUX AUTO-RECOVERY: exit 255 with a ControlMaster socket
              present → 'ssh -O exit' the stale master, remove the socket,
              retry ONCE, annotate '[stale ControlMaster mux ... retried OK]'.
              Manual 'rm /tmp/ssh_mux_*' no longer needed; failure message now
              gives the diagnostic order (ping → sshd → self-match).
              ssh_run PKILL SELF-MATCH GUARD: unbracketed 'pkill -f <pattern>'
              is BLOCKED (the remote shell's cmdline contains the pattern and
              pkill kills the SSH session — exit 255, target state unknown);
              hint shows the bracketed form and the ssh_script alternative.
              ssh_script docstring: script files do not self-match (correct
              home for kill-by-pattern) + '|| true' rule for pkill exit-1
              (already-dead target reads as false failure).
    Goethe v0.3.6: PROVE-IT surface (PH3-1: PROVE-1 + PROVE-3; PROVE-4 partial).
              NEW run_tests(scope): kb (ES index/count probes) | retrieval
              (rag/eval_retrieval.py --self-test) | rules (eval_goethe_rules.py)
              | harness (pytest tests/ + legacy scripts/) | all. Commands,
              paths and args HARDCODED per scope (exec-surface allowlist, sudo
              pattern) — the model supplies only the scope name. Verbatim
              output returned as evidence; missing assets → SKIP (node3090
              lacks rag/, tests/). New valve REPO_DIR (GOETHE_REPO_DIR).
              NEW assert_state(check_command, expected_regex): read-only argv
              allowlist (df/ss/sha256sum/dig/pgrep/stat/ls/wc/free/uptime/
              ip-reads/nvidia-smi/curl-GET-only/systemctl-read-verbs/ping-capped),
              shlex + shell=False, metacharacter rejection, 20s timeout;
              regex searched in stdout+stderr → ASSERT PASS/FAIL with verbatim
              output. Docstrings written to the 8-dimension audit standard
              PRE-deploy (SCRIBE-5 discipline): GOOD/BAD pairs, mutating-verb
              prohibition, no-regex-loosening rule, "prove it" mapping.
    Goethe v0.3.5: SCRIBE-5 docstring audit pass (lse-docstring-optimizer,
              docstring-only) on the four v0.3.x tools. kb_verify: GOOD/BAD
              pair for observed= (verbatim output vs paraphrase) + same-session
              probe rule. time_check: FIX EXECUTION PROHIBITION — never run or
              auto-delegate the suggested clock fix unasked. mentor_demote:
              GOOD/BAD pair pinning the human-words-vs-evidence boundary (P26
              class) + trust-the-return rule. plan_step_done: GOOD/BAD evidence
              pair, no mid-loop task_resume, and a CONTEXT HANDOFF rule —
              past 70% context, hand the next step to a fresh session instead
              of grinding to the ceiling (encodes the DNS Phase-2 lesson).
    Goethe v0.3.4: planner GATE conflict fix (docstring-only). Field report:
              given "get a plan to audit DNS infra", the LSE never called
              planner() — the old gate ("must be your first or second tool
              call") conflicted with KB-FIRST/SKILLS-FIRST, so after two
              search_kb calls the model treated planning as forbidden,
              hand-wrote a prose plan and an ad-hoc active-task.md, bypassing
              the ledger. New gate: information gathering (KB, read-only
              probes) does NOT close the planning window — findings go into
              context=; the window closes at first state change. New MANDATORY
              TRIGGER: user asking for "a plan" REQUIRES planner(); hand-written
              plan files are named a protocol violation. GOOD/BAD examples
              updated to show the reads→planner(context=…) order.
    Goethe v0.3.3: PLANNER UNAVAILABLE root-cause fix (LSE-debugged, 2026-07-03).
              Three compounding causes: (1) _llm_call max_tokens=2048 truncated
              v2 envelopes (per-step packaged prompts need far more) → 8192;
              (2) Qwen3.6 thinking consumed the same completion budget — the
              /no_think prose hint does not hold reliably → per-request
              "thinking_budget_tokens": 0, the server-enforced reasoning-budget
              kill-switch (a request value of 0 overrides any CLI
              --reasoning-budget; harmlessly ignored by think-tag-less models);
              (3) no resilience → two-attempt envelope loop: parse failure
              feeds a corrective REJECTED note back and retries once before
              surfacing PLANNER UNAVAILABLE.
    Goethe v0.3.2: PLANNER v2 — atomized plans with a living ledger.
              _PLANNER_CONTRACT v2: every step is ONE tightly scoped unit
              (<=5 tool calls, one verifiable outcome, mandatory verify) with
              its OWN self-contained packaged_prompt plus explicit depends_on/
              inputs/output edges, topologically ordered. Built for Qwen3.6
              (performs best tightly scoped) and 131k-context management: each
              step executes in a fresh window with only a compact ledger summary.
              planner(mode="revise", task_id=...): re-plans ONLY remaining work,
              feeding completed/failed steps (with evidence) back as LEDGER
              context; completed history is preserved in the merged plan.
              NEW plan_step_done(task_id, step_n, evidence, failed=False):
              strikes a step in the tasks.db ledger (steps_json column, added
              via idempotent PRAGMA migration), stores verify evidence
              (>=20-char gate), returns the NEXT step's fresh-context prompt;
              failed=True routes to revise; last strike closes the block.
              Decision: NO websocket — the SQLite ledger is the bidirectional
              planner↔agent channel (durable across context resets/crashes);
              real-time multi-agent belongs to Faust when its state machine lands.
              NEW valves PLANNER_FORCE_URL / PLANNER_FORCE_MODEL: Step-0
              health-probed endpoint override — set permanently to the Gemma
              swap port; used when up, silently cascades when down.
              NEW tools/planner-gemma-swap-node3090.sh + restore script:
              swap-on-demand Gemma-4-31B planner on node3090:8085 (captures the
              pre-swap llama-server cmdline for exact restore; Gemma sampling
              temp 1.0 / top-k 64; bracketed pkill patterns per self-kill lesson).
    Goethe v0.3.1: CHRONOS — enforced sense of time (CHRONOS-1..4).
              NEW time_check(): stdlib SNTP against pool.ntp.org +
              time.cloudflare.com (2s timeout, graceful degrade) with TLS
              Date-header cross-check (NTP is unauthenticated — a clock-fix
              command is only SUGGESTED when both NTP sources agree AND TLS
              corroborates; never auto-adjusts). Offset >2s → discrepancy
              report + lse-errors record.
              NEW valve MODEL_PRETRAIN_CUTOFF (YYYY-MM, per-model): time_check
              and the first search_kb/search_web return of each session carry a
              server-injected [TIME] banner (now | cutoff | gap → model-memory
              claims presumed stale). Compliance no longer depends on the model
              reading docstrings.
              Volatility TTLs (CHRONOS-3): index_to_kb gains volatility=
              static|slow|fast (default slow; 90d / 7d TTLs, static=∞).
              search_kb tags [EXPIRED — pointer only, re-verify live] past TTL
              and demotes expired hits in the trust rerank (×0.5, same as
              stale). record_outcome(success=True) now bumps updated_at —
              re-verification resets the TTL clock. Field mapped since the
              v0.3.0 migration (08-kb-trust-migration.py).
              CHRONOS-4: YEAR-INJECTION + 30d/7d staleness rules RETIRED from
              the search_web docstring — years are now stripped from queries
              server-side (standalone 19xx/20xx tokens; CVE-2025-1234-style
              compounds survive), freshness lives in the TTL metadata.
    Goethe v0.3.0: KB TRUST LIFECYCLE (KB-DECAY-1..5) — lse-kb quality is no
              longer monotonic upward; verified failure evidence now demotes.
              record_outcome: new evidence= param; success=False + evidence
              (>=20 chars) → quality = max(0.2, q − 0.15), consecutive_failures
              streak; 0.2 floor → stale=true QUARANTINE (never deleted).
              success=True resets the streak, never re-elevates quality.
              search_kb: surfaces runs/ok/fail per hit, [STALE — quarantined]
              banner, client-side trust rerank (failure-ratio multiplier,
              stale halved so quarantined docs rank below fresh ones).
              NEW kb_verify(doc_id[, observed]): two-phase regression probe of
              verified_against vs live system; mismatch auto-demotes via
              record_outcome with the probe output as evidence.
              NEW mentor_demote(doc_id, new_quality, reason): human-authorized
              kill-switch for wrong high-quality docs (mentor_correct stays
              raise-only); reason stored as demote_reason for forensics.
              Recovery: tier-gated raises (index_to_kb dedup, mentor_correct)
              above 0.2 clear stale + reset the streak.
              skill_outcome demotion floor aligned to documented 0.2 (was 0.0 —
              code/docstring drift caught by PROVE-2 contract tests); archive
              now fires only on failure at the floor.
              Mapping migration: rag/08-kb-trust-migration.py adds stale,
              consecutive_failures, volatility (CHRONOS-ready) to lse-kb.
              Contract tests extended: tests/test_kb_contracts.py.
    Goethe v0.2.9: hermes_plan → planner (renamed). Semantics + JSON fix.
              Tool renamed planner to reflect backend change (no longer Hermes).
              Docstring rewritten: 3-path cascade (node3090 LSE → Ollama →
              Gemma GGUF), updated GATE examples, removed all Hermes/v0.2.7 refs.
              JSON extraction fix: strip <think>...</think> blocks from the
              planner reply BEFORE applying the envelope regex. Qwen3 models
              emit thinking inside <think> tags even on structured-output
              requests; the greedy \\{.*\\} (DOTALL) regex was matching from
              the first { inside the think block to the last } of the JSON,
              producing unparseable mixed content. Stripping tags first
              isolates the clean JSON envelope reliably.
    Goethe v0.2.8: planner PATH 3 — VRAM-aware Gemma GGUF spawn.
              _call_node_planner now has a three-path cascade:
              (1) node3090 llama-server :8080 (Qwen 27B, GPU) — primary.
              (2) node3090 Ollama :11434 qwen3:4b (CPU) — GPU fallback.
              (3) Local Gemma GGUF spawn — fires only when paths 1+2 both
              error. Selects model by task class (small/medium/large) and
              confirmed free VRAM via nvidia-smi; supports vision via mmproj.
              Models: E4B (~5 GB, 5200 MB gate), 26B-A4B (~16.7 GB, 17200 MB
              gate), 31B (~18.5 GB, 19100 MB gate). Vision detection via
              keywords (image/screenshot/photo/visual/png/jpg/jpeg/picture).
              New valves: PLANNER_MODEL_DIR, PLANNER_PORT, PLANNER_LLAMA_BIN.
              New helpers: _planner_task_class, _planner_free_vram_mb,
              _planner_gemma_select, _spawn_gemma_server, _stop_gemma_server.
              New class variable: _GEMMA_MODELS (model catalog).
    Goethe v0.2.7: HERMES RETIRED — node planner cascade replaces Hermes.
              _call_hermes and _kanban_create_card retired (stubs only).
              New: _call_node_planner — two-path cascade (llama-server →
              Ollama CPU). New valves: NODE3090_LLM_URL, NODE3090_OLLAMA_URL,
              NODE3090_PLANNER_FALLBACK_MODEL. hermes_plan rewritten to call
              _call_node_planner, parse JSON envelope, checkpoint task.
    Goethe v0.2.6: SSH OVERHAUL — ssh_run + ssh_script + ControlMaster + complexity guard.
              Three root causes of exit-255 SSH failures addressed:
              (1) Double-shell escaping: new ssh_run() passes commands as argv[], not via
              bash -c. No local shell sees the command — arrives on the remote host intact.
              (2) nohup/disown in SSH sessions: new ssh_script() transfers script content
              as a file via scp, executes it as bash /tmp/lse_script_<hash>.sh. Auto-injects
              </dev/null on nohup lines to prevent SIGHUP on SSH session close.
              (3) Per-call TCP+auth overhead: SSH ControlMaster (-o ControlMaster=auto,
              ControlPersist=60s) maintains a persistent mux socket. After the first call,
              all subsequent ssh/scp calls to the same host+port+user reuse the socket.
              execute_command SSH complexity guard: commands containing nohup/disown/export/
              eval/subshell markers are blocked and return an actionable ssh_script() hint
              instead of silently producing exit 255.
    Goethe v0.2.5: fetch_url reddit/camoufox browser fallback (v1.5.29).
              When a reddit.com URL returns empty content or an HTTP error
              (reddit blocks plain requests with 403/429), fetch_url
              automatically retries via _reddit_browser_fallback():
                node3090 → local Firecrawl at localhost:3002
                LUCIFER  → ping node3090, then remote Firecrawl at node3090:3002
              Successful result is prefixed "[browser-rendered]", cached, and
              tagged with SOURCE-VERIFY MANDATE. Falls back gracefully if
              node3090 is offline or Firecrawl is unreachable.
    Goethe v0.2.4: shutdown_node — two-step confirmation gate (confirmed=False
              returns prompt; confirmed=True executes). Model must surface the
              prompt to the user and wait for explicit yes before second call.
    Goethe v0.2.3: wake_node overhauled — ping-first (skip WoL if already up),
              search_kb for current wake procedure before sending magic packet,
              KB notes surfaced in all return paths (already-up / booted / error).
    Goethe v0.2.2: THREE GROUND-TRUTH-BEFORE-ACTION RULES added to
              execute_command docstring (P31 design session; Camoufox +
              n45 incidents as empirical basis — rules abstracted to
              pattern class, incident names kept out of rule text):
              (1) RESOURCE-AVAILABILITY RULE: before any external connection
              (SSH, API, docker exec, curl to service), verify resource state
              first via ping/health-check/docker inspect. For managed nodes:
              check _NODE_REGISTRY → wake_node if found; else search_kb
              ("<hostname> access"); else stop and report "no recovery path,
              operator action required." ICMP-blocked exception for
              external/unknown hosts. Prevents 30s SSH timeouts being
              misdiagnosed as credential failures.
              (2) VENDOR-BEHAVIOR GROUND-TRUTH RULE: before modifying any
              file from an external project based on an assumption about HOW
              that software behaves internally (call order, field injection,
              protocol semantics, version behavior), run the waterfall:
              search_kb → vendor changelog/README → GitHub issues → search_web.
              The write_file snapshot gate makes patches reversible; it does
              NOT prevent acting on a false premise. Waterfall is the control.
              (3) RELEASE ASSET RULE: before writing any download URL,
              VERSION/RELEASE variable, image tag, or package pin, fetch the
              source of truth — get_github_release("<owner>/<repo>") for
              GitHub, registry page/API for Docker/PyPI/npm. Version patterns
              cannot be inferred by incrementing a prior release. Each
              unverified artifact reference is a potential wasted build cycle.
              Backup: goethe-v0.2.1.py (verified identical).
    Goethe v0.2.1: KB DOC-ID RESOLUTION (SY5 debug — mentor_correct 404).
              mentor_correct/record_outcome did es.get(index="lse-kb", id=doc_id),
              which requires the exact 16-char _id hash, but search_kb NEVER showed
              the doc_id — so the model passed the TITLE as doc_id and got
              NotFoundError(404, ...). Fixes: (a) search_kb now prints
              'doc_id=<_id>' on every hit (the root enabler); (b) new
              _resolve_kb_id() accepts an _id OR a title, resolving a title via an
              exact match_phrase lookup; (c) mentor_correct + record_outcome call
              it first and return an actionable message ("run search_kb for the
              doc_id, or index_to_kb to create it") instead of a raw 404; ambiguous
              titles list candidate ids. No behavior change when a correct doc_id
              is passed. Docstrings updated. (For eval-gate review.)
              FILENAME: switched to a stable 'goethe.py' (ends the per-bump renames
              that kept breaking path references). The version now rides the
              frontmatter only - title: "LSE Goethe v0.2.1" + version: 0.2.1 - so
              it shows in the OWUI tool list and on file open (head -5). exec_test.py
              resolves goethe.py via glob. A version bump = edit those two lines.
    Goethe v0.2.0: MONITOR-DOWNLOAD BUGFIX + AUDIT PASS (SY5 request). Companion
              to download-monitor.py 0.3 (version aligned with the LSE KB doc).
              (1) download-monitor.py query_prometheus crashed on EVERY call with
              UnboundLocalError: `import urllib.parse` lived inside the function
              body, making `urllib` a function-local name, so the earlier
              `urllib.parse.urlencode(...)` reference hit an unbound local. The
              import is now module-level; the in-function and redundant
              module-level imports were removed. (Fix is in the standalone script
              monitor_download shells out to — REDEPLOY /opt/local-se/download-
              monitor.py from tools/download-monitor.py for the fix to take effect.)
              (2) download-monitor.py false-COMPLETE: completion fired at
              pct>=99.9, reporting a 17.6 GB download "done" with ~18 MB still
              missing; now requires current_bytes within a 64 KB absolute
              tolerance of expected. Also: clamped negative "elapsed", guard for
              expected_bytes<=0.
              (3) monitor_download() interpreter selection was backwards — it used
              the hardcoded /home/sy5/miniforge3 python unconditionally unless
              python3 was absent from PATH, breaking on hosts without miniforge.
              Now: use miniforge only if it exists, else which(python3).
              (4) download-monitor.py wrong PromQL: it queried
              node_network_receive_bytes_total{device} (node_exporter convention),
              but this stack's speed comes from the custom download-speed-exporter
              (:9838) exposing network_receive_bytes_per_second{interface}. The
              mismatch returned no series -> false STALLED. Verified against the
              exporter source + lse-net-speed-01 dashboard, not recall.
              (5) download-monitor.py adaptive sleep: SLEEP is now a fraction of the
              remaining ETA (converges in a few checks), and COMMAND_TIMEOUT is
              raised 30->200s so a single `sleep N` (MAX_SLEEP_SECONDS=180) is not
              truncated — ~5 polls on a 10-min download instead of ~20. See the
              COMMAND_TIMEOUT valve note for the hung-command trade-off.
              (6) IN-PLACE EDIT SAFETY NET (SY5 request — LSE edits files in place
              without approval/git discipline). New _snapshot_before_write() + a
              code gate in write_file: before any overwrite/append of an EXISTING
              file it captures a recovery point (git hash-object -w blob pinned at
              refs/lse-snapshots/, or a .lse-backups/ copy outside git) and REFUSES
              the write if none can be made. The docstring confirmation rule was
              attention-only and got skipped under pressure; this enforces
              reversibility in code (sudo-blocker lineage). Unit-tested: git
              snapshot recovers a clobbered file, fs fallback works, new files are
              exempt, snapshot-failure blocks. NOTE (deferred for eval-gate review):
              execute_command in-place ops (sed -i, >, >>, tee) are NOT yet gated —
              parsing targets from arbitrary shell is fragile and the hot path is
              risk-sensitive; recommended as a separate reviewed change. Route
              in-place edits through write_file to get the snapshot today.
              (7) DOWNLOAD CLOBBER GUARD (SY5 report — LSE re-ran curl/hf download
              to "check" an in-progress download instead of monitor_download,
              spawning a second writer into the same partial file -> corrupt GGUF).
              New _active_download_guard(): execute_command REFUSES a download-
              initiating command (curl/wget/aria2c/hf download/huggingface-cli/
              git-lfs) while a real downloader process is already running, and
              routes the model to monitor_download. Conservative: pgrep runs only
              for download commands; curl needs an output flag so a health-check
              curl never trips it; fail-open if the host can't be probed. Unit-
              tested (6 cases). Companion DOWNLOAD PROGRESS RULE added to the
              execute_command docstring.
              AUDIT NOTES (not changed — flagged for review through the eval gate):
              execute_command privilege/denylist matching uses substring `in`, so
              `su `/`passwd` match mid-token (e.g. `cat /etc/passwd` is blocked,
              `du -su` could trip the su gate). Word-boundary matching is the
              recommended hardening — deferred to a security-reviewed change.
    Goethe v0.1.0: FORK of Cogitator v1.7.24 — FAUST CONSOLIDATION. The Hermes<->LSE
              OWUI channel is RETIRED, superseded by the Faust group-chat room
              (Faust/, lse-1.7.0-b). Removed: hermes_cooperate, _cooperate_exec,
              check_hermes_inbox, _format_hermes_messages, _flush_voicemail, and the
              Path A/B content-marker + by-reference inbox/outbox machinery
              (_extract_content_marker / _strip_hermes_marker). _call_hermes simplified
              to a plain reply (no inbox/marker append). KEPT: hermes_plan (inline
              pre-flight planner) + its _call_hermes backend + _kanban_create_card, and
              all general LSE tooling and hardening (execute_command, sudo_delegation_block,
              file ops, search_kb/index_to_kb, record_error, pfSense tools, WATERFALL
              provenance, source-claim verification, SSH KB-first/fingerprint rules).
    v1.7.24: call_hermes DEMODELED -> internal-only _call_hermes (urgent, P30/P31).
              The model must no longer invoke the Hermes chat-completion call
              directly: direct calls frequently surface OWUI networking errors, and
              the direct-call entry point is being superseded by hermes_plan and
              hermes_cooperate. RENAMED call_hermes -> _call_hermes so OWUI no longer
              exposes it in the tool spec (leading underscore = internal helper).
              ALL LOGIC PRESERVED — it remains the shared backend that hermes_plan
              and hermes_cooperate (the conference call) call internally; both are
              unchanged in behaviour. The check_hermes_inbox 'ask' reply path, which
              previously told the model to call_hermes directly, now routes through
              hermes_cooperate(max_rounds=1). No other tool surface changes.
    v1.7.23: HERMES->LSE BY-REFERENCE (large-payload fix, P30). When an inbound
              envelope carries body_ref (a path written by the Hermes producer on
              node3090 because the full payload would overflow the reply token cap
              and truncate the marker), _format_hermes_messages now surfaces a
              fetch instruction (execute_command SSH cat) alongside the preview, so
              the model can pull the full text on demand. Unknown-key safe: older
              markers without body_ref are formatted exactly as before. No new tool;
              the existing execute_command SSH path does the fetch.
    v1.7.22: HERMES INBOX POLL max_tokens 8 -> 1024 (Path B companion fix, P29). The
              poll reply carries the [[HERMES->LSE]] marker IN CONTENT (Path B), which
              cannot fit in 8 tokens — 8 was sized for Path A (marker rode a top-level
              field). Raised so check_hermes_inbox can actually receive queued messages.
              call_hermes/hermes_plan already use 2048, so messages riding real calls
              were unaffected; only the dedicated poll was clipped. No other change.
    v1.7.21: SUDO BLOCK -> COPYABLE ```bash + VISIBLE-REPLY FORCING (P29; v1.7.20
              emitter alone failed — content emitted mid-<think> stays collapsed). (1)
              block reformatted as markdown with a ```bash fenced code block (copyable)
              instead of box-art. (2) the function now RETURNS a directive telling the
              model its entire visible reply must be the fenced block verbatim, nothing
              else — routing the surface through the post-<think> reply, the only channel
              that renders reliably. Emitter kept best-effort. STOP PROTOCOL + no-summary
              tightened; args unchanged.
    v1.7.20: SUDO BLOCK FORCE-SURFACE (code fix for the long-standing "delegation
              block hidden in thinking" issue, SY5 P29). sudo_delegation_block is now
              async and accepts __event_emitter__; the formatted block is pushed to the
              UI via a {"type":"message"} event so it lands in the VISIBLE response even
              when the model calls it mid-<think> (where the tool-result card collapses).
              Args, return value, STOP PROTOCOL and THINKING PHASE RULE unchanged — the
              model receives the exact same string, so its task flow is undisturbed; the
              emitter only adds a user-facing surface. Backward compatible:
              __event_emitter__ defaults to None (no emit = prior behaviour).
    v1.7.19: HERMES->LSE PATH B (content marker). _format_hermes_messages now also
              parses [[HERMES->LSE]]{json}[[/HERMES->LSE]] from the gateway reply
              content (not just a top-level hermes_messages field), since Hermes Agent
              cannot always add a response field. call_hermes strips the marker from
              the visible reply. New helpers _extract_content_marker /
              _strip_hermes_marker. Completes the LSE side of 1.7.0-b.
    v1.7.18: WATERFALL PROVENANCE RULE (ROADMAP 1.7.6; SY5 P23 observation).
              index_to_kb + record_error gate at the WRITE path: content making an
              external-software version/behavior claim ("removed in v9577",
              "deprecated since 2.8.0") with NO waterfall provenance (fetched URL /
              RFC / ground-truth evidence / version snapshot) is stored tagged
              [UNVERIFIED] with quality capped <=0.3 (tier forced inferred). With
              provenance: unchanged. Helpers _wf_version_claim / _wf_has_provenance.
              Companion docstring rule: run the waterfall (search_kb -> vendor
              docs/README -> github -> search_web) before version/behavior diagnosis.
              Attention is not a control plane — enforced in code.
    v1.7.17: HERMES CONFERENCE allow_sudo ALLOWLIST. hermes_cooperate gains an
              allow_sudo param (user-authorized exact privileged commands) and a
              dedicated gated executor _cooperate_exec: sudo/su/doas runs only if
              EVERY invocation is covered by the allowlist; the hard blocklist is
              never overridable. Closes the SearXNG live-test gap (docker/systemctl
              requests were all sudo-blocked, stalling cooperation). Default empty
              = no sudo (prior behaviour preserved).
    v1.7.16: HERMES <-> LSE CONFERENCE CALL (1.7.0-b). New tool hermes_cooperate()
              — user-fired, bounded multi-round "conference call": LSE relays an
              objective to Hermes (call_hermes, synchronous); when Hermes requests
              infra data it cannot reach (no SSH) via a ```bash block, LSE runs it
              through execute_command's gates and feeds the output back; loops to
              max_rounds or until 'CONFERENCE COMPLETE'. Paradigm LSE -> Voicemail
              <- Hermes; voicemail flushed to empty on call end (_flush_voicemail,
              best-effort, tolerant until the persistent store lands). Works against
              the current gateway with NO Hermes-side change (rides synchronous
              call_hermes). See docs/lse-1.7.0-b-bidirectional-design.md.
    v1.7.15: HERMES -> LSE INBOUND CHANNEL (1.7.0-b). LSE is request-driven (no
              inbound listener), so Hermes holds an outbox and attaches pending
              items as `hermes_messages` to any gateway reply. New tool
              check_hermes_inbox() makes the no-task poll that surfaces them;
              call_hermes now also parses hermes_messages off its own reply so
              directives ride existing calls for free. HTTP only — no SSH, no new
              valve. Hermes-side call_lse/outbox + Telegram mirror: see
              docs/lse-1.7.0-b-bidirectional-design.md (self-installed on node3090).
    v1.7.14: HERMES DIRECT CONNECT — gateway confirmed binding 0.0.0.0:8642 (P27
              live test: ss -tlnp shows 0.0.0.0:8642, HTTP 200 from LUCIFER direct).
              socat :8643 was a workaround from when gateway bound 127.0.0.1 only —
              now confirmed eliminated. HERMES_API_URL default :8643 → :8642.
              No code logic change — valve default + docstrings only.
    v1.7.13: SSH KB-FIRST RULE (live-test incident: model attempted bare ssh root@rutx50
              without -i key flag → 30s timeout; then searched KB with wrong topic_filter=pfsense
              → pfSense API docs returned instead of RUTX50 access params).
              Fix: KB-FIRST SSH RULE added to execute_command docstring — mandatory search_kb
              before any ssh command to a managed device; no topic_filter on SSH access queries.
              Closes: (1) bare-ssh-before-KB-lookup, (2) wrong-topic-filter-on-SSH-query.
    v1.7.12: SSH DEVICE AUTO-FINGERPRINT (MikroTik incident: model inferred
              RouterOS from IP/hostname for a Teltonika RUTX50 running OpenWrt,
              committed to wrong CLI assumptions for 3+ turns. Cause: device OS
              inferred from training knowledge, not from the device itself).
              execute_command now intercepts ssh commands: on the FIRST call
              to any new host, it auto-runs cat /etc/os-release + uname -srm
              over SSH (reusing the original command's key/port options) and
              caches the result in self._device_cache[host]. Every subsequent
              call to the same host prepends [DEVICE FINGERPRINT: host=...
              platform=...] to the result. Enforcement in code — the model
              cannot skip the fingerprint, cannot infer device type from memory.
              The fingerprint is the ground truth; all CLI decisions must be
              grounded on it. Recursion-safe: fingerprint command skipped if
              the command already contains os-release/uname markers.
    v1.7.11: KB SOURCE-TIER QUALITY GATE (pfSense read-only incident: LSE
              indexed an untested hypothesis at quality=1.0 before verifying
              the chicken-and-egg lock. The model self-granted max score.
              Max score must be earned by live evidence, not claimed).
              index_to_kb: new source_tier param (ground_truth|primary|
              secondary|inferred). Quality is hard-capped at the tier ceiling
              regardless of what the model passes: ground_truth=1.0 (requires
              evidence >=40 chars from a real tool result, else capped 0.7),
              primary=0.8, secondary=0.6, inferred=0.4. Default quality_score
              0.8->0.5; default tier=inferred. New evidence and
              verified_against params stored in the document.
              skill_record: same source_tier gate; tier stored in document.
              skill_outcome: source_tier param; new_q capped at tier ceiling;
              pushing quality to 1.0 requires source_tier=ground_truth.
              Evidence threshold: 20->50 chars for ground_truth outcomes.
    v1.7.10: SOURCE-CLAIM VERIFICATION (fabrication #5 root cause: evidence
              overwrite at synthesis — the model fetched the RUTX50 wiki page,
              had 07.22.3=Stable / 07.23.4=Latest in plain view, yet emitted
              phantom 07.23.5 and 07.22.4 in the final answer. Prompt fences
              do NOT hold at synthesis; the fix must be in code).
              fetch_url now caches extracted text in self._fetch_cache[url]
              (ttl=SOURCE_VERIFY_CACHE_TTL valve, default 300s) and appends a
              code-emitted SOURCE-VERIFY MANDATE banner to every content return
              (not to error returns). New verify_source_claims(url, claims)
              re-fetches the source (or uses the cache) and returns a structured
              FOUND / PARTIAL / NOT_FOUND report with verbatim ±300-char excerpts
              for each comma-separated claim. PARTIAL = a specific token exists
              but the full claim doesn't — the excerpt shows what the source
              ACTUALLY says. NOT_FOUND = report the claim as UNVERIFIED. This
              call does NOT count against the search budget. Enforcement in code,
              sudo-blocker lineage: the function does the comparison, the model
              cannot fabricate the return value.

    v1.7.9: hermes_plan creates the kanban triage card itself (P24 capability
              gap: the Hermes planner session has NO kanban-write tool — proved
              by tool-hunting in agent.log: cronjob -> skills_list -> gave up.
              Contract wording cannot fix a missing tool). After envelope parse
              + checkpoint, _kanban_create_card() INSERTs directly into
              node3090 kanban.db via ssh (status='triage', assignee='lse',
              goal_mode=0, idempotency_key=hermes_plan:<task_id>). Schema-safe:
              tasks.status has no CHECK constraint; 'triage' is in
              VALID_STATUSES (board queries accept it); the
              VALID_INITIAL_STATUSES={running,blocked} gate is Python-API-only
              and not on this path. INSERT OR IGNORE = re-plan idempotent.
              Fail-open: card failure is reported in the plan result
              (card_error line), never blocks the envelope. Companion change:
              planner contract v2.2 drops the card-creation instruction
              (Hermes no longer burns turns hunting for a board tool).
    v1.7.8: search_web category fix. search_web requested
              categories="general,it,science" on EVERY call; arxiv is in
              [science, it, technology] (settings.yml), so every query —
              including non-science, general-domain product queries —
              activated arxiv (weight 2, ~15%% reliable) and returned 4-5
              off-domain physics/ML hits, burning the web budget on junk.
              Now requests categories="general" only (google/bing/ddg cover
              LSE's operational query mix). Science searches become an explicit
              opt-in if ever needed. Same research-task incident, part 2.
    v1.7.7: fetch_url CONTENT-TYPE GUARD. fetch_url fed resp.text to the HTML
              parser unconditionally; on a PDF that dumped raw FlateDecode
              binary (%PDF, xref tables, streams) into the agent context AND
              broke OWUI <details> rendering downstream (control chars + stray
              <</>> markers derailed the sanitizer, so every later tool card
              showed as raw escaped text). Now: PDF -> pdfminer/pypdf text
              extract, else clean refusal; other non-text content-types refused;
              all extracted text control-char-sanitized. Found via a multi-step
              research task that fetched a PDF source.
    v1.7.6: hermes_plan() — planner-orchestrator layer 3 (1.7.2 phase of
              docs/planner-orchestrator-design.md). Pre-flight triage: wraps
              call_hermes with intent=plan, parses the plan envelope, writes
              the initial task block (packaged_prompt as next_prompt), returns
              steps + per-step budgets + abort criteria. Degrades to
              "PLANNER UNAVAILABLE — proceed with default budgets, checkpoint
              early" when Hermes is down (layers 1-2 still protect).
              ALSO FIXES call_hermes truncated error handling, latent since
              v1.7.3: the HTTPError handler set `body` then fell through
              (implicit None return), and URLError/timeout raised uncaught —
              the documented "ERROR: <reason>" returns were never reachable.
              Restored from tools/call_hermes_draft.py.
    v1.7.5: CONFIG GROUND-TRUTH RULE (SearxNG observability incident: LSE
              cited an invented metrics token and a dead config path from
              recall/stale KB, sending the operator on a 401 hunt while the
              real outage had a different cause). Rule added to
              execute_command and search_kb docstrings: tokens, paths, ports,
              and config values must come from a same-session tool result
              (read_file / execute_command / docker inspect), never from
              recall. search_kb results now display per-hit age (updated Xd
              ago) in code, with a staleness caveat for config values.
    v1.7.4: compact_context KV-erase fix. The slots API was NEVER body-based:
              llama.cpp expects POST /slots/{id}?action=erase (query param);
              the tool sent {"action":"erase"} as JSON body -> "Invalid action"
              on every call. Misdiagnosed in the field as "slots API removed in
              v9577" (false — verified against llama.cpp master server README).
              Now sends the query-param form, empty body, and reports n_erased
              from the response. Correct the lse-errors KB entry recorded
              during the incident.
    v1.7.3: UNVERIFIED-URL RULE (RUTX50 incident #2: LSE fabricated hostname
              fbidownload.teltonika-networks.com when retrieval was blocked,
              diagnosed the NXDOMAIN as a network outage, and presented the
              fake URL to the user). One-line rule added to the budget-refusal
              text and the fetch_url docstring: never present a URL/hostname
              that did not come out of a tool result.
    v1.7.2: SEARCH_BUDGET_WINDOW_MIN default 30 → 2 min (RUTX50 incident: budget
              exhausted instantly on task_resume because the rolling window
              spanned sessions; LSE stalled ~7 min mid-conversation and began
              answering from unverified training knowledge. 8 calls / 2 min
              still forces a surface point in a reformulation spiral, but a
              blocked budget now self-heals within the same conversation).
    v1.7.1: ANTI-SPIRAL GATE + TASK BLOCKS (Goethe incident, P22: 34 web
              searches / 78K tokens, no surfaced output; second turn died
              searching. Root cause: termination decisions left to model
              attention, which is absorbed by the task).
              _budget_gate()    — search_web/search_reddit/fetch_url share a
                                  rolling-window budget (SEARCH_BUDGET valve,
                                  default 8 per 30 min). At ≤2 remaining every
                                  result carries a surface-NOW banner; at 0 the
                                  call is REFUSED in code with instructions to
                                  checkpoint + surface partial results.
                                  Enforcement in code, not docstring — same
                                  philosophy as the sudo blocker.
              task_checkpoint() — persistent task blocks (SQLite, TASKS_DB
                                  valve) for work exceeding one session:
                                  goal/plan/done/findings/UNVERIFIED/
                                  next_prompt. Checkpoint on step completion,
                                  on budget banner, and status=done at end.
                                  findings/unverified separation is mandatory
                                  (fabricated-quote lesson).
              task_resume()     — first-call-only loader of the latest open
                                  block; unverified items must be re-verified.
              Planner-orchestrator (Hermes pre-flight triage) specced in
              docs/planner-orchestrator-design.md — layers interlock: planner
              estimates, budgets enforce, blocks carry over.
    v1.7.0: COGITATOR — self-writing skills layer (1.7.0-c pulled forward).
              Renamed from "LSE System Admin Terminal" to "LSE Cogitator".
              New ES index lse-skills holds runbook-shaped procedures
              (occupation/task/preconditions/procedure/verification/
              failure_modes/provenance/quality/stats/pinned), per
              docs/lse-1.7.0-design.md §3.2 and the Hermes surpass analysis
              (docs/hermes-skill-learning-analysis.md): retrieval beats prompt
              injection, evidence beats age, provenance is mandatory.
              skill_search()  — SKILLS-FIRST RULE: query before any multi-step
                                procedural operation; max 2 injected (context
                                budget); usage stats updated on retrieval.
              skill_record()  — EVIDENCE GATE: only ground-truth-verified
                                procedures; <2 steps rejected (fact -> index_to_kb);
                                verification field required; dedup at cosine 0.92;
                                initial quality capped at 0.7.
              skill_outcome() — quality moves on evidence only: +0.10 verified
                                success, -0.15 verified failure, floor 0.2 ->
                                auto-archive (pinned skills exempt); evidence
                                string required, self-report rejected.
              Adopted from Hermes curator: pinned flag, archived flag,
              inspectable evidence_log. All three docstrings passed
              lse-docstring-optimizer 8-dimension audit.
    v1.6.4: Hermes Agent subagent — production-ready two-boss architecture.
              LSE (on LUCIFER) and SY5 are Hermes's two principals. LSE delegates
              autonomous multi-step tasks to Hermes via call_hermes(); Hermes runs
              Qwen3.6-27B-Q4_K_M locally on node3090 (RTX 3090, 24GB VRAM) via
              llama-server (port 8080) and executes with its own tool set: shell
              execution, file read/write, browser automation, image generation.
              Infrastructure: hermes-gateway.service (hermes-admin, enabled).
              Gateway binds 0.0.0.0:8642 directly (confirmed P27 live test).
              socat :8643 workaround eliminated. HERMES_API_URL valve: :8642.
              Gate (docstring-enforced): only call when (1) task requires multi-step
              autonomous execution, (2) single SSH can't complete it, (3) both
              llama-server and hermes-gateway confirmed running. no_think=True for
              reads, no_think=False mandatory for writes/destructive — skipping is a
              protocol violation. Always pass relevant KB content via context= param.
              Port history: originally loopback :8642; socat :8643 workaround added;
              v1.7.14: gateway confirmed 0.0.0.0:8642 — socat eliminated.
    v1.6.3: pfsense_query + pfsense_graphql KB-FIRST RULE.
              Root cause: LSE knows to use pfsense_query/pfsense_graphql but constructs
              payloads and GraphQL queries from memory — guessing field names, required
              fields, and protocol values. API returns 400 errors → trial-and-error spiral.
              Fix: KB-FIRST RULE added to pfsense_query docstring. Before constructing
              any payload, LSE must call search_kb("pfsense REST API", topic_filter="pfsense").
              KB contains full POST/PATCH payload schema, required fields, validation errors,
              placement semantics, and working curl examples. Guessing is a protocol violation.
              Also added field-name reminder to pfsense_graphql COMMON QUERIES section.
    v1.6.2: call_hermes — delegate multi-step tasks to Hermes Agent on node3090.
              Hermes runs Qwen3.6-27B locally via llama-server (port 8080) and executes
              tasks autonomously using its own tool set (shell, file, browser, image gen).
              Gate: only when llama-server + hermes-gateway are confirmed running AND
              the task requires multi-step autonomous execution on node3090 (not a single
              SSH command). no_think=True (default) for read-only tasks; no_think=False
              required for write/destructive tasks — skipping is a protocol violation.
              CONTEXT: always pass relevant KB entries via context= param (e.g. pfsense KB).
              New valves: HERMES_API_URL (http://192.168.5.41:8642 as of v1.7.14), HERMES_API_KEY.
              Port 8643 was socat workaround (gateway was loopback-only at ship time).
              v1.7.14: gateway confirmed binding 0.0.0.0:8642 — socat eliminated.
              Returns plain string or "ERROR: <reason>" on failure — caller must check.
              Hermes gateway: /etc/systemd/system/hermes-gateway.service (hermes-admin,
              disabled/on-demand). Start: systemctl start hermes-gateway on node3090.
    v1.6.1: pfsense_graphql — SCHEMA INTROSPECTION PROHIBITION added (__schema/__type
              queries overflow context identically to the log endpoint).
              pfsense_query — ORDERED RULE DEPLOYMENT section added: placement=N
              semantics, read-first pattern, explicit warning against schema introspection
              to find placement (it is a Common Control Parameter, not endpoint-specific).
    v1.6.0: Three-tool pfSense routing architecture:
              pfsense_graphql()    — NEW: all reads/audits via GraphQL (/api/v2/graphql).
                                     Single endpoint, schema introspection, multi-resource
                                     queries in one call. Replaces GET usage in pfsense_query.
              pfsense_query()      — writes only (POST/PATCH/PUT/DELETE). GET now returns
                                     an error redirecting to pfsense_graphql.
              pfsense_log_summary()— logs only. Routing triangle added to all three docstrings.
              KB indexing cap: 4000 → 50000 chars (full docs stored).
              KB embed cap: 8000 chars (nomic-embed-text token limit respected separately).
              search_kb return: 200 → 5000 chars per hit (meaningful content per result).
              fetch_url default: 3000 → 20000 chars (full pages fetched by default).
              pfsense_log_summary: per-request api_key forwarded to gateway (?api_key=).
              Fixed _ensure_gateway() UnboundLocalError (pf_key → api_key).
              Fixed X-API-Key header casing in pfsense_query.
    v1.5.28: pfsense_log_summary() — rewritten to use local gateway (localhost:9191).
              Fixes context overflow: raw /api/v2/status/logs/firewall replaced with
              /compact endpoint (server-side aggregation, <4KB response).
              Added LOG ENDPOINT PROHIBITION to pfsense_query docstring.
              New mode= param: "compact" (audit reports) vs "summary" (quick stats).
    v1.5.27: search_web — DATE-SENSITIVE QUERIES rule: check actual date via
              execute_command before any firmware/CVE/version/release-date search.
    v1.5.28: shutdown_node — confirmation gate: confirmed=False (default) returns a
              prompt; confirmed=True executes. Model must never pass confirmed=True
              without explicit user approval.
    v1.5.27: wake_node — ping first (skip WoL if already up), search_kb for current
              procedure before sending WoL, surface KB notes in all return paths.
    v1.5.26: search_web — timeout=(5,10) to prevent connection hang on VPS hiccup.
    v1.5.25: search_reddit() — Reddit search wrapper via SearxNG site:reddit.com.
    v1.5.24: start_node_agent / stop_node_agent — on-demand llama-cpp server lifecycle.
    v1.5.23: _NODE_REGISTRY node3090 — agent_port 1234→8080, agent_type lmstudio→llama-cpp.
    v1.5.22: wake_node — corrected WoL endpoint to /api/v2/services/wake_on_lan/send.
    v1.5.21: shutdown_node uses subprocess directly — bypasses execute_command sudo blocker.
    v1.5.20: wake_node / query_node_agent / shutdown_node — GPU node lifecycle tools.
    v1.5.19: content cap + anti-recursion on index_to_kb; search_kb result truncated 400→200.
    v1.5.18: search_rfc() — RFC authority KB query for protocol-level diagnosis.
    v1.5.17: pfsense_log_summary() + nmap_summary() — compact log/scan extraction.
    v1.5.16: pfSense SSL verification via CA cert.
              [PFSENSE_CA_CERT valve] Path to the exported pfSense WebGUI CA certificate.
              Default: /opt/local-se/cert/pfsense-webgui-ca.crt (sy5:sy5 644).
              When set and file exists: verify=PFSENSE_CA_CERT (proper TLS verification).
              When empty or file missing: falls back to verify=False with a logged warning.
              Cert: CN=pfsense-webgui-ca, SY5TEM5/4DMIN, valid Apr 2026 → Apr 2036.
              Export procedure: pfSense → System → Cert Manager → CAs → Export CA cert.
    v1.5.15: pfSense REST API integration.
              [valves] PFSENSE_URL (base URL, not a secret) and PFSENSE_API_KEY
              (read-only key, acceptable blast radius — see VALVES.md).
              [pfsense_query] Authenticated GET/POST/PATCH/DELETE to pfSense REST API v2
              (pfrest.org package, Plus 26.03). Key supplied as parameter (Vaultwarden)
              or falls back to PFSENSE_API_KEY valve. SSL verify=False — pfSense
              self-signed cert, LAN-only access, acceptable risk.
              Write access protocol: pfSense API is read-only by default. Any non-GET
              call requires manually disabling Read Only in pfSense UI first, and
              re-enabling immediately after. Leaving write enabled is a protocol
              violation (see lse-challenge-arena.md §pfSense write access gate).
              [LOG_FILE] Default updated to /opt/local-se/agent_commands.log.
              ~/.lse/ is now root:sy5 710 — sy5 cannot create files there.
    v1.5.14: sudo_delegation_block presentation improvements (Fix 3 — Run 6 gaps).
              [sudo_delegation_block] Added step_number, total_steps, verify_command params.
              When step_number > 0, the block header reads "Step N of Total".
              verify_command surfaced as labelled "Verify with:" step in block body.
              expected_output_hint retained for backward compatibility (secondary).
              THINKING PHASE RULE added: never call inside a reasoning/thinking block.
              [LOG_FILE] Default moved from ~/.lse/ to /opt/local-se/.
    v1.5.13: search_web header fix + categories fix.
              Root cause: SearXNG limiter (limiter: true) rejects requests without
              X-Forwarded-For/X-Real-IP headers with HTTP 429. LSE was sending no
              headers, causing silent failures mid-session.
              Fix 1: added X-Forwarded-For and X-Real-IP headers to requests.get().
              Fix 2: changed categories from "general,it" to "general,it,science" —
              confirmed during SearXNG deploy that arxiv, github, google scholar,
              stackoverflow, semantic scholar only fire on science category.
              Verified: 11 engines active, 108 results on q=llama.cpp.
    v1.5.12: write_file SIZE SANITY CHECK + record_outcome + mentor_correct.
              [write_file] Added SIZE SANITY CHECK: if mode='overwrite' and new content
              is <25% of existing file's line count, function returns an error requiring
              explicit user confirmation before proceeding. Override with force=True
              after user confirms intentional truncation.
              Root cause: LSE destroyed a 323-line GUI PowerShell file by calling
              write_file in overwrite mode with a 5-line snippet. The docstring required
              read + confirmation but compliance was zero under recovery-loop pressure.
              The code-level gate is the only reliable enforcement.
              [record_outcome] New RAG function: records success/failure outcome against
              an existing KB doc. Increments empirical_runs, success_count, failure_count.
              Surfaces whether documented procedures actually work in production.
              [mentor_correct] New RAG function: applies a human-authored correction to
              a KB doc. Re-embeds corrected content, raises quality_score (never lowers),
              increments refinement_count. Used when user identifies an error in the KB.
              Both functions were referenced in prompt v0.5.9 TOOLS section but missing
              from tool v1.5.11. Gap identified during 2026-06-02 tracking restructure.
    v1.5.11: fetch_url — HTML-stripped full-page fetch for SEARCH-THEN-FETCH protocol.
              monitor_download — Prometheus-backed download progress monitor.
              (Note: both were added without changelog entries — reconstructed 2026-06-02.)
    v1.4.1: Added explicit routing rules to read_file docstring (tail vs read_file).
    v1.4.2: Fixed sudo check from startswith → 'in' to catch sudo embedded in pipelines
            (e.g. "ls /home | sudo tee file.txt" was previously not blocked).
    v1.4.3: Rewrote write_file docstring to enforce:
              - full file read required before overwrite mode
              - append mode required for single-line additions
              - confirmation required for ALL writes, including new file creation
            Root cause: M2 eval revealed model used tail (partial read) then overwrote
            full file, causing data loss. Filter also tightened (see lse-routing-filter).
    v1.5.0: Promoted two prompt-level rules into docstrings (higher compliance weight):
              - execute_command: added COMBINE RULE — batch independent commands with &&
                or semicolons. Root cause: S1 eval showed model making two separate calls
                for uname -r and nproc despite OUTPUT RULES in the system prompt.
              - search_web: strengthened announcement protocol to a numbered REQUIRED
                SEQUENCE with explicit "protocol violation" language. Root cause: W2 eval
                showed model skipping the announce step and producing verbose synthesis.
            Fixed SEARXNG_URL default from port 8888 → 8088 (matches actual SearxNG port).
    v1.5.1: Two docstring fixes from eval run 2 regressions:
              - read_file: added PRIVILEGED PATH note — if blocked due to /root/ or
                other privileged location, explicitly offer sudo_delegation_block with
                sudo cat <path>. Root cause: S3 showed model reasoning correctly in
                thinking block but not surfacing the delegation offer in output
                (--reasoning-budget 0 suppresses thinking).
              - sudo_delegation_block: strengthened stop instruction — "output nothing
                further after this block." Root cause: P2 showed model continuing with
                post-execution instructions after emitting the delegation block.
    v1.5.4: get_context_status field-name fix + sudo_delegation_block READ-FIRST RULE.
              [get_context_status] Root cause: llama-server build >=9307 exposes
              n_prompt_tokens in /slots, not n_past. Always returned 0%.
              Fix: read n_prompt_tokens, n_prompt_tokens_cache, n_prompt_tokens_processed;
              n_decoded/n_remain/n_predict via next_token[0] and params.
              Added truncation warning when n_decoded >= n_predict and n_remain == 0.
              [sudo_delegation_block] Added READ-FIRST RULE: before delegating a
              privileged file write, read the target file first (read_file or
              execute_command cat). Root cause: P2 eval showed model issuing
              delegation block for /etc/sysctl.conf without reading it first,
              losing one point. Skipping the read when file is readable is now
              explicitly a protocol violation.
    v1.5.5: sudo_delegation_block STOP PROTOCOL — added RETURN VALUE SEMANTICS to
              break a within-turn retry loop (29 calls observed in production).
              Root cause: model received the tool return value (the ⚠️ block string),
              interpreted it as "not the terminal output I requested", and retried
              the same call repeatedly. The STOP PROTOCOL told the model what to
              WRITE after calling the function but never explained that the return
              value IS the emitted block — the command has not run yet, stop all
              tool calls, yield to user.
              Fix: added RETURN VALUE SEMANTICS block immediately after the
              STOP PROTOCOL. Also removed the conflicting system-prompt rule
              "wrap output in bash code block" (see prompt v0.5.2) and the
              SUDO DELEGATION FORMAT section (format mismatch with actual output).
            read_file: added PRIVILEGED PATH BEHAVIOUR — no workarounds.
              Root cause: model tried cat → python3 → base64 in sequence when
              Docker volume paths returned permission denied. Added explicit
              prohibition: "Do NOT try cat, python3, or base64 as workarounds."
    v1.5.3: sudo_delegation_block STOP PROTOCOL update.
              Previous: "output nothing further" — caused S3 partial fail because the
              tool result card in OpenWebUI is collapsed by default, so the command was
              invisible to the user (only "Paste output to continue." appeared in text).
              Fix: model must write exactly one echo line after the block:
              "Please run `<command>` in your terminal and paste the output here."
              This surfaces the command in visible text without reopening P2's
              continuation problem (which was multi-sentence post-execution guidance).
    v1.5.2: Denylist hardening — cross-referenced against earlier LSE supervisor project.
            Eight gaps identified and fixed:
              - Added to _BLOCKED_COMMANDS: shred, blkdiscard, sgdisk, partprobe
                (destructive disk tools missing from original list).
              - Added to _BLOCKED_COMMANDS: userdel, groupdel (account deletion).
              - Added to _BLOCKED_COMMANDS: rm -rf, rm -fr, rm -r -f, rm -f -r
                (recursive forced remove was only partially gated via _WRITE_OPS;
                rm -rf on user-owned paths like /home/sy5/ was not blocked at all).
              - Added to _BLOCKED_COMMANDS: fork bomb pattern ":(){ :|".
              - Added to _BLOCKED_COMMANDS: "> /dev/sd", "> /dev/nvme", "of=/dev/"
                (shell redirection into block devices; "dd of=/dev/sdb" slipped through
                the "dd if=" substring check).
              - Added /mnt/ to _PRIVILEGED_WRITE_PATHS: protects the Windows filesystem
                (/mnt/c, /mnt/d, etc.) from write/delete ops via execute_command.
              - Added "chmod -r " and "chown -r " to _WRITE_OPS: blocks recursive
                permission changes targeting privileged paths (chmod -R on user paths
                remains allowed).
              - fetch_url SSRF gate: not applicable — no fetch_url function exists yet.
                Deferred; gate must be added if fetch_url is ever introduced.
    v1.5.9: RAG layer — Elasticsearch + nomic-embed-text knowledge base.
              Four new tool functions: search_kb, index_to_kb, record_error, check_error_kb.
              New valves: ES_URL, OLLAMA_URL, EMBED_MODEL.
              KB-FIRST RULE added to search_web: always query search_kb before SearxNG.
              index_to_kb deduplicates (cosine > 0.92 → refine, not duplicate).
              Error KB: record_error logs mistakes + resolution; check_error_kb prevents recurrence.
              Infrastructure: elasticsearch:8.17.0 on docker_searxng_net, Ollama nomic-embed-text
              CPU-only on 127.0.0.1:11434. 12 docs / 32 chunks seeded at quality 0.3–0.6.
    v1.5.8: compact_context — true in-place context compaction tool.
              Truncates OpenWebUI chat message history via the OpenWebUI REST API,
              prepends a summary message to preserve session state, then erases the
              llama.cpp KV cache slot so the model starts fresh with the compacted
              history. Requires OWUI_API_KEY and OWUI_BASE_URL valves.
              New valves: OWUI_API_KEY, OWUI_BASE_URL.
    v1.5.7: execute_command DESTRUCTIVE OPERATION PROTOCOL — confirmation gate
              for rm and other irreversible commands.
              Root cause: Run 5 eval showed P1 and P3 confirmation protocol
              failures. P1 (write_file) has an explicit CONFIRMATION PROTOCOL
              in its docstring and the model follows it (M2 scored 2/3 with
              confirmation present). P3 (execute_command rm) has no equivalent
              gate — the model went straight to rm without warning or asking yes/no.
              Fix: added DESTRUCTIVE OPERATION PROTOCOL to execute_command docstring,
              mirroring the write_file pattern. Required sequence before any rm,
              truncate, or overwrite: warn → name target → ask yes/no → wait for
              explicit yes. Also applies to > redirects that would overwrite files.
    v1.5.6: Three fixes for Run 5 eval preconditions.
              [execute_command] Added POST-DELETE VERIFY RULE — after any rm command
              that succeeds, always follow up with a stat or ls call confirming the
              target no longer exists. Root cause: P3 eval showed model deleting
              /tmp/lse/hello.txt then immediately reporting "Done" without a
              verification call. Partial credit (1/3) — the verify step was skipped.
              [search_web] Added NO YEAR INJECTION rule — do not append a year to
              queries. Root cause: W2 eval showed model searching "llama.cpp latest
              stable release version 2025" despite system date being 2026. The model
              used its training-data estimate of the year rather than the system date,
              producing stale results and making 4 calls instead of 1.
              [get_github_release] New function — read-only GitHub API call that
              returns the latest release tag, name, and date for any public repo.
              Directly solves W2-class lookups (llama.cpp, open-webui version checks)
              without SearxNG and without date-injection risk.
"""

from pydantic import BaseModel, Field
import subprocess
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

from typing import Optional

class Tools:

    class Valves(BaseModel):
        LOG_FILE: str = Field(
            default="/opt/local-se/agent_commands.log",
            description="Path to the persistent agent command audit log. "
            "Moved from ~/.lse/ (root:sy5 710, sy5 cannot write) "
            "to /opt/local-se/ (sy5-writable).",
        )
        DEFAULT_WORKING_DIR: str = Field(
            default="/home/sy5",
            description="Default cwd for execute_command when no working_dir is supplied.",
        )
        MAX_OUTPUT_CHARS: int = Field(
            default=4000,
            description="Maximum characters returned by execute_command before truncation.",
        )
        COMMAND_TIMEOUT: int = Field(
            default=200,
            description="Subprocess timeout in seconds. Raised 30->200 (v0.2.0) so "
            "the download-monitor adaptive sleep (MAX_SLEEP_SECONDS=180) survives "
            "a single execute_command('sleep N') call, giving ~5 polls on a "
            "multi-minute download instead of ~20. TRADE-OFF: a genuinely hung "
            "command now blocks up to 200s before timing out (was 30s). Keep "
            "MAX_SLEEP_SECONDS in download-monitor.py strictly below this value.",
        )
        LLAMA_SERVER_URL: str = Field(
            default="http://localhost:8080",
            description="Base URL of the llama.cpp server (for get_context_status).",
        )
        SEARXNG_URL: str = Field(
            default="http://localhost:8088/search",
            description="SearxNG JSON search endpoint (for search_web).",
        )
        CAMOUFOX_URL: str = Field(
            default="http://192.168.5.41:9377",
            description="Camoufox browser server URL on node3090 (for Reddit scraping).",
        )

        EXTRA_WRITE_PATHS: str = Field(
            default="",
            description="Colon-separated extra paths the agent may write to.",
        )
        OWUI_DB_PATH: str = Field(
            default="/home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db",
            description="Absolute path to the OpenWebUI SQLite database (webui.db). "
            "Used by compact_context to write chat history directly, "
            "bypassing the HTTP deadlock caused by single-worker uvicorn.",
        )
        ES_URL: str = Field(
            default="http://127.0.0.1:9200",
            description="Elasticsearch base URL for the RAG knowledge base (lse-kb index).",
        )
        OLLAMA_URL: str = Field(
            default="http://127.0.0.1:11434",
            description="Ollama base URL for nomic-embed-text embeddings (CPU-only, no GPU).",
        )
        EMBED_MODEL: str = Field(
            default="nomic-embed-text",
            description="Ollama embedding model (768-dim). Must be pulled via 01-ollama-setup.sh.",
        )
        REPO_DIR: str = Field(
            default="/home/sy5/projects/local-system-engineer",
            description="v0.3.6 (PROVE-1): repo root where run_tests finds the "
            "allowlisted test assets (rag/eval_retrieval.py, eval_goethe_rules.py, "
            "tests/, scripts/). Override per node via GOETHE_REPO_DIR; scopes "
            "whose assets are absent on a node report SKIP, never error.",
        )
        PLANNER_FORCE_URL: str = Field(
            default="",
            description="v0.3.2: when set, the planner calls THIS OpenAI-compatible "
            "endpoint first (e.g. http://node3090.home.arpa:8085 for the Gemma-31B "
            "swap experiment), falling back to the normal cascade on error. "
            "Cross-LLM-family planner experiments become pure configuration.",
        )
        PLANNER_FORCE_MODEL: str = Field(
            default="",
            description="Optional model name sent with PLANNER_FORCE_URL requests "
            "(needed for Ollama-style endpoints; llama-server ignores it).",
        )
        MODEL_PRETRAIN_CUTOFF: str = Field(
            default="",
            description="CHRONOS-2 (v0.3.1): the serving model's published pretraining "
            "cutoff as YYYY-MM (e.g. '2025-06' for Qwen3.6). Drives the [TIME] banner "
            "gap computation in time_check() and the first search_kb/search_web return "
            "of each session. Empty = banner warns that the cutoff is unset. Set "
            "per-model, per-node (env GOETHE_MODEL_PRETRAIN_CUTOFF in start scripts).",
        )
        DREAM_DIGEST_PATH: str = Field(
            default="/opt/local-se/dreams/latest-digest.md",
            description="TRAUM Thread 3 (v0.4.0-a), Prompt 3.5: path to "
            "tools/dream_digest.py's output, read once per session to build the "
            "[DREAM] banner appended alongside the [TIME] banner on the first "
            "search_kb return (_consume_time_banner()). Empty = banner disabled. "
            "Missing/unreadable/unparseable file = banner silently omitted, "
            "never an error (env GOETHE_DREAM_DIGEST_PATH in start scripts; "
            "matches DREAM_DIR in dream_runner.py/dream_apply.py/dream_digest.py "
            "by default, but is intentionally its own valve since goethe.py "
            "never itself writes into that directory).",
        )
        PFSENSE_URL: str = Field(
            default="https://pfsense.home.arpa",
            description="Base URL of the pfSense REST API (pfrest.org package, Plus 26.03). "
            "Not a secret — safe to store in valve.",
        )
        PFSENSE_API_KEY: str = Field(
            default="",
            description="pfSense REST API key (read-only). Acceptable blast radius: exposes "
            "network topology and firewall rules but cannot modify anything. "
            "Alternatively retrieve from Vaultwarden at runtime via vault_unlock() "
            "+ get_vault_secret() and pass as api_key parameter to pfsense_query(). "
            "WRITE ACCESS PROTOCOL: key is read-only by default. If pfSense write "
            "access is temporarily enabled (T3+ challenges), rotate this key "
            "immediately after and re-enable Read Only in pfSense UI.",
        )
        PFSENSE_CA_CERT: str = Field(
            default="/opt/local-se/cert/pfsense-webgui-ca.crt",
            description="Path to the exported pfSense WebGUI CA certificate for TLS verification. "
            "Export from pfSense: System → Cert Manager → CAs → Export CA. "
            "When set and the file exists, pfsense_query uses verify=<path>. "
            "When empty or file missing, falls back to verify=False (logged warning). "
            "Cert at default path: CN=pfsense-webgui-ca, valid until Apr 2036.",
        )
        HERMES_API_URL: str = Field(
            default="http://192.168.5.41:8642",
            description="[RETIRED v0.2.7] Hermes gateway — service no longer runs. "
            "node_plan() now calls node3090 llama-server directly. "
            "Valve retained to avoid breaking existing goethe_mcp valve configs.",
        )
        HERMES_API_KEY: str = Field(
            default="7aa537e027e2efeda7cc660a959516eed414373c6e7b3df3d9a567e48fc3319e",
            description="[RETIRED v0.2.7] Hermes API key — no longer used.",
        )
        NODE3090_LLM_URL: str = Field(
            default="http://node3090.home.arpa:8080",
            description="node3090 llama-server URL — PRIMARY planner for node_plan(). "
            "OpenAI-compatible /v1/chat/completions endpoint. "
            "Model: Qwen3.6-27B (GPU). Health check: GET /health (expects 200). "
            "node_plan() probes this first; falls back to NODE3090_OLLAMA_URL on failure.",
        )
        NODE3090_OLLAMA_URL: str = Field(
            default="http://node3090.home.arpa:11434",
            description="node3090 Ollama URL — CPU FALLBACK planner for node_plan(). "
            "Used when llama-server is unavailable, busy, or health probe times out. "
            "OpenAI-compatible /v1/chat/completions endpoint. "
            "Model: set by NODE3090_PLANNER_FALLBACK_MODEL valve.",
        )
        NODE3090_PLANNER_FALLBACK_MODEL: str = Field(
            default="qwen3:4b",
            description="Ollama model for CPU-fallback planning in node_plan(). "
            "Must be already pulled on node3090 (qwen3:4b is confirmed present). "
            "qwen3:4b supports extended thinking and is usable for structured planning. "
            "Alternative: gemma3 (also confirmed on node3090 Ollama).",
        )
        PLANNER_MODEL_DIR: str = Field(
            default="/opt/models/lmstudio-community",
            description="Base directory for Gemma GGUF + mmproj files for Path 3 planning "
            "(v0.2.8). Uses lmstudio-community subdir layout — paths in _GEMMA_MODELS "
            "are relative to this dir (e.g. gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf). "
            "Verified on node3090: /opt/models/lmstudio-community/{E4B,26B-A4B,31B}-GGUF/. "
            "Path 3 fires only when both llama-server and Ollama return errors.",
        )
        PLANNER_PORT: int = Field(
            default=8085,
            description="Port for the transiently spawned Gemma llama-server (Path 3, v0.2.8). "
            "Must not conflict with :8080 (main llama-server) or :8642 (retired Hermes). "
            "The process is started, used for one call, then killed.",
        )
        PLANNER_LLAMA_BIN: str = Field(
            default="/home/lse-admin/llama.cpp/build/bin/llama-server",
            description="Absolute path to the llama-server binary used to spawn Gemma "
            "instances (Path 3, v0.2.8). Must be executable by the goethe process user. "
            "Typical locations: ~/llama.cpp/build/bin/llama-server or "
            "/usr/local/bin/llama-server.",
        )
        SEARCH_BUDGET: int = Field(
            default=15,
            description="Max search_web/search_reddit/fetch_url calls per rolling "
            "window (anti-spiral gate, v1.7.1). Code-enforced.",
        )
        SEARCH_BUDGET_WINDOW_MIN: int = Field(
            default=2,
            description="Rolling window (minutes) for SEARCH_BUDGET. v1.7.2: 30→2 — "
            "30 min bricked legitimate research and leaked across session "
            "resumes (RUTX50 incident); 2 min still breaks tight spirals.",
        )
        TASKS_DB: str = Field(
            default="/opt/local-se/tasks.db",
            description="SQLite path for multi-session task blocks "
            "(task_checkpoint/task_resume).",
        )
        SOURCE_VERIFY_CACHE_TTL: int = Field(
            default=300,
            description="TTL in seconds for the fetch_url content cache used by "
            "verify_source_claims (v1.7.10). Re-fetches after expiry. "
            "Set to 0 to always re-fetch.",
        )

    # ── Hard-coded permission lists ───────────────────────────────────────────

    _ALLOWED_READ_PREFIXES = [
        "/home/",
        "/etc/",
        "/var/log/",
        "/tmp/",
        "/opt/local-se/",
    ]

    _ALLOWED_WRITE_PREFIXES = [
        "/home/",
        "/tmp/",
        "/opt/local-se/",
    ]

    _BLOCKED_COMMANDS = (
        # Filesystem destruction — disk/partition tools
        "mkfs",
        "fdisk",
        "parted",
        "sgdisk",
        "wipefs",
        "blkdiscard",
        "partprobe",
        "shred",
        # Block device writes — dd and shell redirection
        "dd if=",
        "of=/dev/",
        "> /dev/sd",
        "> /dev/nvme",
        # Recursive forced remove (all common flag orderings)
        "rm -rf",
        "rm -fr",
        "rm -r -f",
        "rm -f -r",
        # Fork bomb
        ":(){ :|",
        # Account deletion
        "userdel",
        "groupdel",
        # Privilege / credential management
        "passwd",
        "visudo",
        # Firewall flush
        "iptables -f",
        "iptables -F",
    )

    # v1.4.2: uses 'in' check (not startswith) to catch sudo in pipelines
    _PRIVILEGED_PREFIXES = ("sudo ", "su ", "doas ")

    _PRIVILEGED_WRITE_PATHS = ("/etc/", "/usr/", "/boot/", "/sys/", "/proc/", "/mnt/")

    _WRITE_OPS = (
        "cp ",
        "mv ",
        "rm ",
        "tee ",
        "> ",
        ">> ",
        "sed -i",
        "truncate",
        "dd ",
        "chmod -r ",
        "chown -r ",
    )

    # ── Initialiser ──────────────────────────────────────────────────────────

    def __init__(self):
        self.valves = self.Valves()
        self._fetch_cache: dict = {}  # url -> {"text": str, "ts": float} (v1.7.10)
        self._device_cache: dict = {}  # host -> {"platform": str, "raw": str} (v1.7.12)
        self._time_banner_emitted = False  # CHRONOS-2 (v0.3.1): [TIME] banner once/session

    # ── Node planner contract (v0.2.7) ───────────────────────────────────────
    # Embedded in every node_plan() call as the system message so the target
    # model (llama-server or Ollama) knows how to produce the plan envelope.
    # Old Hermes had this baked into its system prompt memory; we now pass it
    # explicitly per-request.
    _PLANNER_CONTRACT = (
        "You are a task planner. Given a task, ATOMIZE it and return ONLY "
        "a single JSON object — no prose, no markdown fences, no explanation.\n\n"
        "JSON envelope schema (v=2):\n"
        "{\n"
        '  "intent": "plan",\n'
        '  "correlation_id": "<from request header>",\n'
        '  "goal_summary": "<one line — what done looks like>",\n'
        '  "sessions_estimate": <int: 1 if one context window suffices, 2+ for multi-day>,\n'
        '  "single_session": <bool>,\n'
        '  "confidence": "low" | "medium" | "high",\n'
        '  "abort_criteria": "<specific condition to stop and report instead of continuing>",\n'
        '  "steps": [\n'
        '    {"n": 1, "what": "<ONE action>", "depends_on": [<step numbers>], '
        '"inputs": "<artifacts/facts needed, naming which step produced them>", '
        '"output": "<the single artifact/fact this step produces>", '
        '"web_calls": <int>, "tool_calls": <int>, '
        '"verify": "<concrete check command/observation — NEVER NONE>", '
        '"packaged_prompt": "<self-contained brief for a fresh agent executing ONLY '
        "this step: goal one-liner, this step's inputs (with values or where to read "
        'them), the action, the verify check, and STOP-AFTER instruction>"},\n'
        "    ...\n"
        "  ]\n"
        "}\n\n"
        "ATOMIZATION RULES (v2 — the reason this contract exists):\n"
        "- Each step is ONE tightly scoped unit: <=5 tool calls, ONE verifiable "
        "outcome. If an action needs more, SPLIT it.\n"
        "- Each step must be executable by a fresh agent with ZERO memory of other "
        "steps, given only its packaged_prompt plus a short ledger summary. Never "
        "write 'as before' or 'continue' in a packaged_prompt.\n"
        "- Declare every dependency: depends_on lists the step numbers whose output "
        "this step consumes; inputs names those artifacts explicitly.\n"
        "- Order steps so each depends only on EARLIER steps (topological order — "
        "they must fall into place naturally).\n"
        "- Prefer more, smaller steps over fewer, bigger ones: the executing model "
        "performs best tightly scoped, and each step runs in a fresh context window.\n"
        "- verify is mandatory per step: a command to run or observation to make "
        "whose output proves the step's output exists/works.\n"
        "Rules:\n"
        "- Return ONLY the JSON object. No prose before or after it.\n"
        "- abort_criteria: be specific (e.g. 'Stop if 3 searches return no new data').\n"
        "- web_calls / tool_calls: budget estimates only, not hard limits.\n"
        "- single_session=true if the task fits in one ~8k-token context window.\n"
        "- confidence: 'high' if the plan is complete; 'low' if key unknowns remain.\n"
        "- BACKUP RULE (hard, no exceptions): any step that modifies or overwrites a file "
        "must begin with a timestamped backup: "
        "cp <file> <bkp_dir>/<filename>_$(date +%Y%m%d_%H%M%S). "
        "State the backup command explicitly in that step's 'what' field AND in that "
        "step's packaged_prompt. No file may be overwritten without a backup copy first.\n"
        "- REVISION MODE: if the user message contains a LEDGER section with completed/"
        "failed steps, re-plan ONLY the remaining work. Do not re-emit completed steps; "
        "number new steps continuing after the highest completed step number.\n"
    )

    # ── Gemma model catalog (v0.2.8, paths verified 2026-07-01) ──────────────
    # Used by _planner_gemma_select / Path 3 of _call_node_planner.
    # vram_mb = minimum free VRAM required (MiB) including safety margin.
    # Paths are relative to PLANNER_MODEL_DIR (lmstudio-community subdir layout).
    # Verified on node3090: ls /opt/models/lmstudio-community/gemma-4-*-GGUF/
    _GEMMA_MODELS: dict = {
        "E4B": {
            "gguf":    "gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-E4B-it-GGUF/mmproj-gemma-4-E4B-it-BF16.gguf",
            "vram_mb": 5200,   # 4.97 GB model + ~946 MB mmproj + headroom
        },
        "26B": {
            "gguf":    "gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-26B-A4B-it-GGUF/mmproj-gemma-4-26B-A4B-it-BF16.gguf",
            "vram_mb": 17200,  # 15.6 GB model + 1.1 GB mmproj + headroom
        },
        "31B": {
            "gguf":    "gemma-4-31B-it-GGUF/gemma-4-31B-it-Q4_K_M.gguf",
            "mmproj":  "gemma-4-31B-it-GGUF/mmproj-gemma-4-31B-it-BF16.gguf",
            "vram_mb": 19100,  # 17.4 GB model + 1.1 GB mmproj + headroom
        },
    }

    # ── SSH ControlMaster constants (v0.2.6) ─────────────────────────────────
    _SSH_CTL_PATH = "/tmp/ssh_mux_{host}_{port}_{user}"
    _SSH_BASE_OPTS = [
        "-o", "LogLevel=ERROR",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ControlMaster=auto",
        "-o", "ControlPersist=60s",
    ]

    def _ssh_opts(self, host: str, user: str, port: int = 22,
                  connect_timeout: int = 10) -> list:
        """Return SSH option list with ControlMaster socket path."""
        ctl = self._SSH_CTL_PATH.format(host=host, port=port, user=user)
        return self._SSH_BASE_OPTS + [
            "-o", f"ConnectTimeout={connect_timeout}",
            "-o", f"ControlPath={ctl}",
            "-p", str(port),
        ]

    # ── Node planner (v0.2.7) ─────────────────────────────────────────────────

    def _try_forced_planner_endpoint(
        self, task: str, context: str = "", no_think: bool = False
    ) -> str | None:
        """Try the forced planner endpoint if configured and healthy.

        Returns the LLM result string if successful, None to continue cascade.
        """
        import json as _json
        import urllib.request as _ureq  # noqa: PLC0415
        force_url = (self.valves.PLANNER_FORCE_URL or "").strip().rstrip("/")
        if not force_url:
            return None
        force_ok = False
        try:
            with _ureq.urlopen(f"{force_url}/health", timeout=3) as r:
                force_ok = r.status == 200
        except Exception:
            force_ok = False
        if force_ok:
            self._log(f"NODE-PLAN: PLANNER_FORCE_URL healthy → {force_url}")
            messages = [{"role": "system", "content": self._PLANNER_CONTRACT}]
            user_content = task.strip()
            if context:
                user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
            if no_think:
                user_content += " /no_think"
            messages.append({"role": "user", "content": user_content})
            payload_obj: dict = {
                "messages": messages,
                "max_tokens": 8192,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "thinking_budget_tokens": 0,
            }
            fm = self.valves.PLANNER_FORCE_MODEL
            if fm:
                payload_obj["model"] = fm
            payload = _json.dumps(payload_obj).encode()
            result = self._post_chat_completion(force_url, payload, 180)
            if not result.startswith("ERROR:"):
                return result
            self._log(
                f"NODE-PLAN: forced endpoint failed ({result[:80]}), "
                "falling back to cascade"
            )
        else:
            self._log(f"NODE-PLAN: PLANNER_FORCE_URL down ({force_url}) — cascade")
        return None


    def _post_chat_completion(
        self, base_url: str, payload: bytes, timeout: int
    ) -> str:
        """POST payload to /v1/chat/completions. Returns content or 'ERROR: ...'"""
        import json as _json
        import urllib.request as _ureq
        import urllib.error as _uerr

        req = _ureq.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _ureq.urlopen(req, timeout=timeout) as resp:
                data = _json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except _uerr.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            return f"ERROR: HTTP {exc.code} — {body}"
        except Exception as exc:
            return f"ERROR: {exc}"


    def _call_node_planner(
        self, task: str, context: str = "", no_think: bool = False
    ) -> str:
        """INTERNAL — Hermes replacement (v0.2.7).

        Cascade:
          1. Health-probe node3090 llama-server (NODE3090_LLM_URL/health, 3s timeout).
             If healthy → POST /v1/chat/completions with _PLANNER_CONTRACT as system
             message. Qwen 27B GPU path — best quality.
          2. If probe fails or LLM call errors → fall back to Ollama CPU on node3090
             (NODE3090_OLLAMA_URL) with NODE3090_PLANNER_FALLBACK_MODEL (qwen3:4b).
             Always-available, zero GPU contention.

        Returns the model's raw reply string, or "ERROR: <reason>" on both paths failing.
        """
        import json as _json
        import urllib.request as _ureq
        import urllib.error as _uerr

        def _llm_call(base_url: str, model: str, timeout: int) -> str:
            """POST /v1/chat/completions to base_url. Returns content or 'ERROR: ...'"""
            messages = [{"role": "system", "content": self._PLANNER_CONTRACT}]
            user_content = task.strip()
            if context:
                user_content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{user_content}"
            if no_think:
                user_content += " /no_think"
            messages.append({"role": "user", "content": user_content})

            payload_obj: dict = {
                "messages": messages,
                # v0.3.3: 2048 was truncating v2 envelopes (per-step packaged
                # prompts) — the dominant "PLANNER UNAVAILABLE" root cause.
                "max_tokens": 8192,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                # v0.3.3: server-enforced thinking kill-switch (llama-server
                # reasoning-budget layer; 0 = end thinking immediately, and a
                # per-request 0 OVERRIDES any CLI --reasoning-budget). The
                # /no_think prose hint alone does not hold reliably on Qwen3.6.
                # Endpoints without think tags (Gemma) ignore this field.
                "thinking_budget_tokens": 0,
            }
            if model:
                payload_obj["model"] = model
            payload = _json.dumps(payload_obj).encode()
            return self._post_chat_completion(base_url, payload, timeout)

        # ── Step 0: forced endpoint (v0.3.2 — cross-family planner experiments) ─
        # Health-probed: the valve can stay set permanently (e.g. the Gemma-31B
        # swap port on node3090) — used when up, silently skipped when down.
        result = self._try_forced_planner_endpoint(task, context=context, no_think=no_think)
        if result is not None:
            return result

        # ── Step 1: probe node3090 llama-server ──────────────────────────────
        llm_url = self.valves.NODE3090_LLM_URL.rstrip("/")
        probe_ok = False
        try:
            with _ureq.urlopen(f"{llm_url}/health", timeout=3) as r:
                probe_ok = r.status == 200
        except Exception:
            probe_ok = False

        if probe_ok:
            self._log(f"NODE-PLAN: llama-server probe OK → {llm_url}")
            result = _llm_call(llm_url, model="", timeout=120)
            if not result.startswith("ERROR:"):
                return result
            self._log(f"NODE-PLAN: llama-server call failed ({result[:80]}), trying Ollama")

        # ── Step 2: Ollama CPU fallback ───────────────────────────────────────
        ollama_url = self.valves.NODE3090_OLLAMA_URL.rstrip("/")
        fallback_model = self.valves.NODE3090_PLANNER_FALLBACK_MODEL
        self._log(f"NODE-PLAN: Ollama fallback → {ollama_url} model={fallback_model}")
        result = _llm_call(ollama_url, model=fallback_model, timeout=300)
        if not result.startswith("ERROR:"):
            return result
        self._log(f"NODE-PLAN: Ollama fallback failed ({result[:80]}), trying Gemma spawn")

        # ── Step 3: Gemma GGUF local spawn (VRAM-aware, v0.2.8) ──────────────
        vision = any(
            kw in task.lower()
            for kw in ("image", "screenshot", "photo", "visual",
                       "png", "jpg", "jpeg", "picture")
        )
        gguf, mmproj, model_key = self._planner_gemma_select(task, vision=vision)
        if gguf is None:
            return (
                "ERROR: all planner paths exhausted (llama-server, Ollama, Gemma) — "
                "insufficient VRAM or model files not found under PLANNER_MODEL_DIR"
            )
        planner_port = self.valves.PLANNER_PORT
        proc = self._spawn_gemma_server(gguf, mmproj, planner_port)
        if proc is None:
            return f"ERROR: Gemma server (model_key={model_key}) failed to start within 60s"
        try:
            self._log(f"NODE-PLAN: Gemma path — model_key={model_key} vision={vision}")
            return _llm_call(f"http://127.0.0.1:{planner_port}", model="", timeout=180)
        finally:
            self._stop_gemma_server(proc)

    # ── Gemma planner helpers (v0.2.8) ───────────────────────────────────────

    def _planner_task_class(self, task: str) -> str:
        """Classify task size for Gemma model selection: 'small' / 'medium' / 'large'."""
        n = len(task)
        if n < 400:
            return "small"
        if n < 1500:
            return "medium"
        return "large"

    def _planner_free_vram_mb(self) -> int:
        """Return the largest free VRAM (MiB) across all GPUs via nvidia-smi, or 0 on error."""
        import subprocess as _sp2  # noqa: PLC0415

        try:
            r = _sp2.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
            if lines:
                return max(int(ln) for ln in lines)
        except Exception:
            pass
        return 0

    def _planner_gemma_select(self, task: str, vision: bool = False) -> tuple:
        """
        Select the best-fit Gemma GGUF from PLANNER_MODEL_DIR given available VRAM.

        Preference order by task class:
          small  → E4B  → 26B → 31B
          medium → 26B  → 31B → E4B
          large  → 31B  → 26B → E4B
        Skips any model whose vram_mb gate exceeds free VRAM or whose files are absent.

        Returns (gguf_path, mmproj_path_or_None, model_key), or (None, None, None)
        if no model fits.
        """
        import os as _os2  # noqa: PLC0415

        free = self._planner_free_vram_mb()
        self._log(f"PLANNER-GEMMA: free VRAM={free} MB")
        model_dir = self.valves.PLANNER_MODEL_DIR.rstrip("/")

        tc = self._planner_task_class(task)
        order = (
            ["E4B", "26B", "31B"] if tc == "small"
            else ["26B", "31B", "E4B"] if tc == "medium"
            else ["31B", "26B", "E4B"]
        )

        for key in order:
            m = self._GEMMA_MODELS[key]
            if free < m["vram_mb"]:
                self._log(
                    f"PLANNER-GEMMA: skip {key} — need {m['vram_mb']} MB, have {free}"
                )
                continue
            gguf = f"{model_dir}/{m['gguf']}"
            mmproj = f"{model_dir}/{m['mmproj']}" if vision else None
            if not _os2.path.isfile(gguf):
                self._log(f"PLANNER-GEMMA: skip {key} — gguf missing: {gguf}")
                continue
            if vision and mmproj and not _os2.path.isfile(mmproj):
                self._log(f"PLANNER-GEMMA: skip {key} — mmproj missing: {mmproj}")
                continue
            self._log(f"PLANNER-GEMMA: selected {key} (task_class={tc}, vision={vision})")
            return gguf, mmproj, key

        return None, None, None

    def _spawn_gemma_server(self, gguf_path: str, mmproj_path, port: int):
        """
        Spawn a transient llama-server on 127.0.0.1:<port> for Path 3 planning.

        Polls GET /health every 2 s for up to 60 s. Returns the Popen object when
        the server reports healthy, or None if it does not become healthy in time.
        The caller is responsible for calling _stop_gemma_server(proc) when done.
        """
        import subprocess as _sp3  # noqa: PLC0415
        import time as _tm3  # noqa: PLC0415
        import urllib.request as _ur3  # noqa: PLC0415

        llama_bin = self.valves.PLANNER_LLAMA_BIN
        cmd = [
            llama_bin,
            "--model", gguf_path,
            "--port", str(port),
            "--host", "127.0.0.1",
            "--n-gpu-layers", "99",
            "--ctx-size", "4096",
            "--threads", "4",
        ]
        if mmproj_path:
            cmd += ["--mmproj", mmproj_path]
        self._log(
            f"PLANNER-GEMMA: spawn {llama_bin} model=...{gguf_path[-40:]} port={port}"
        )
        try:
            proc = _sp3.Popen(cmd, stdout=_sp3.DEVNULL, stderr=_sp3.DEVNULL)
        except Exception as exc:
            self._log(f"PLANNER-GEMMA: Popen failed: {exc}")
            return None

        deadline = _tm3.time() + 60
        while _tm3.time() < deadline:
            _tm3.sleep(2)
            try:
                with _ur3.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=2
                ) as r:
                    if r.status == 200:
                        self._log("PLANNER-GEMMA: server healthy")
                        return proc
            except Exception:
                pass

        self._log("PLANNER-GEMMA: health timeout (60 s) — killing proc")
        proc.kill()
        return None

    def _stop_gemma_server(self, proc) -> None:
        """Kill and reap a spawned Gemma llama-server process."""
        try:
            proc.kill()
            proc.wait(timeout=5)
            self._log("PLANNER-GEMMA: server stopped")
        except Exception:
            pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _norm(self, path: str) -> str:
        """Resolve symlinks and normalise path so prefix checks work correctly."""
        return os.path.realpath(os.path.expanduser(path)).rstrip("/") + "/"

    def _is_allowed_read(self, path: str) -> bool:
        normed = self._norm(path)
        return any(
            normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_READ_PREFIXES
        )

    # Shell/session config files that must never be written by the agent
    _BLOCKED_WRITE_FILENAMES = {
        ".bashrc",
        ".bash_profile",
        ".bash_login",
        ".profile",
        ".zshrc",
        ".zprofile",
        ".zlogin",
        ".zshenv",
        ".cshrc",
        ".tcshrc",
        ".fishrc",
        ".ssh/authorized_keys",
        ".ssh/config",
        ".ssh/id_rsa",
        ".ssh/id_ed25519",
        ".gnupg/gpg.conf",
        ".config/fish/config.fish",
    }

    def _is_allowed_write(self, path: str) -> bool:
        normed = self._norm(path)
        # Block shell/session config files regardless of prefix
        import os as _os

        basename = _os.path.basename(normed)
        rel_home = normed.replace("/home/sy5/", "", 1)
        if (
            basename in self._BLOCKED_WRITE_FILENAMES
            or rel_home in self._BLOCKED_WRITE_FILENAMES
        ):
            return False
        if any(
            normed.startswith(p.rstrip("/") + "/") for p in self._ALLOWED_WRITE_PREFIXES
        ):
            return True
        if self.valves.EXTRA_WRITE_PATHS:
            for extra in self.valves.EXTRA_WRITE_PATHS.split(":"):
                extra = extra.strip()
                if extra and normed.startswith(extra.rstrip("/") + "/"):
                    return True
        return False

    def _log(self, entry: str) -> None:
        """Append a timestamped line to the audit log (best-effort)."""
        try:
            log_path = self.valves.LOG_FILE
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(log_path, "a") as f:
                f.write(f"[{ts}] {entry}\n")
        except Exception:
            pass

    # ── Tool functions ────────────────────────────────────────────────────────

    # ── Anti-spiral budget gate (v1.7.1) ─────────────────────────────────────

    def _budget_gate(self) -> str:
        """Rolling-window budget shared by search_web/search_reddit/fetch_url.

        Returns '' (allowed), a low-budget banner (allowed, prepend/append it),
        or refusal text starting with 'BUDGET EXHAUSTED' (caller must return it
        without executing). Code-level enforcement: never relies on model attention.
        """
        import json as _json  # noqa: PLC0415
        import time  # noqa: PLC0415
        import os  # noqa: PLC0415

        path = os.path.join(
            os.path.dirname(self.valves.TASKS_DB) or ".", ".search_budget.json"
        )
        window_s = max(1, int(self.valves.SEARCH_BUDGET_WINDOW_MIN)) * 60
        budget = max(1, int(self.valves.SEARCH_BUDGET))
        now = time.time()
        try:
            with open(path, encoding="utf-8") as f:
                stamps = [t for t in _json.load(f) if now - t < window_s]
        except Exception:
            stamps = []
        if len(stamps) >= budget:
            retry_min = int((window_s - (now - stamps[0])) / 60) + 1
            self._log(f"BUDGET-GATE: refused (≥{budget} in {window_s//60}min)")
            return (
                f"BUDGET EXHAUSTED — web access paused: {budget} search/fetch calls "
                f"in {window_s // 60} min (anti-spiral gate). Do NOT retry or "
                "reformulate the query.\n"
                "REQUIRED NOW, in this order:\n"
                "  1. task_checkpoint(...) — record findings, UNVERIFIED items, and "
                "the next_prompt a future session should start from.\n"
                "  2. Surface your best partial answer to the user immediately, "
                "explicitly marking every unverified claim as unverified.\n"
                f"Budget resets in ~{retry_min} min. Continuing to search instead of "
                "surfacing is a protocol violation. UNVERIFIED-URL RULE: any URL or "
                "hostname you did not receive from a tool result is UNVERIFIED — "
                "presenting one to the user is a protocol violation."
            )
        stamps.append(now)
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(stamps, f)
        except Exception:
            pass
        remaining = budget - len(stamps)
        if remaining <= 2:
            return (
                f"\n\n⚠ SEARCH BUDGET: only {remaining} of {budget} web calls left "
                f"in this {window_s // 60}-min window. Surface findings NOW; if the "
                "task is incomplete, call task_checkpoint() before anything else."
            )
        return ""

    # ── Task blocks: multi-session carryover (v1.7.1) ────────────────────────

    def _tasks_db(self):
        """SQLite handle for the task-block store (auto-creates schema).
        v0.3.2: adds steps_json column (structured per-step plan ledger)."""
        import sqlite3  # noqa: PLC0415

        conn = sqlite3.connect(self.valves.TASKS_DB, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS task_blocks ("
            "task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL, "
            "plan TEXT, done_steps TEXT, findings TEXT, unverified TEXT, "
            "next_prompt TEXT, checkpoints INTEGER DEFAULT 0, "
            "created_at TEXT, updated_at TEXT)"
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(task_blocks)")]
        if "steps_json" not in cols:
            conn.execute("ALTER TABLE task_blocks ADD COLUMN steps_json TEXT")
        return conn

    def task_checkpoint(
        self,
        goal: str,
        plan: str,
        done: str,
        findings: str,
        next_prompt: str,
        unverified: str = "",
        status: str = "open",
        task_id: str = "",
    ) -> str:
        """
        Save a progress checkpoint for work that may outlive this session's context.

        CHECKPOINT RULE — mandatory:
          Call this (1) after completing each major step of a multi-step task,
          (2) IMMEDIATELY when any tool result contains a SEARCH BUDGET warning or
          BUDGET EXHAUSTED notice, and (3) with status="done" when a multi-session
          task finishes. Ending a complex task without a final status="done"
          checkpoint is a protocol violation.

        GATE: only for tasks needing more than ~3 tool calls. Do NOT checkpoint
        trivial single-answer lookups.

        FINDINGS vs UNVERIFIED — keep them separate:
          GOOD: findings="quote is in Wilhelm Meisters Wanderjahre (confirmed via
                Gutenberg #5851)", unverified="German wording from memory, not
                checked against source"   ← verified and unverified separated
          BAD:  findings includes a quotation you reconstructed from memory
                ← unverified claims in findings poison the next session, which
                will treat them as established. Protocol violation.

        next_prompt is the single most important field: write the exact prompt a
        fresh session should start from — context, what is done, what remains,
        where to look next. Trust the return value — do NOT call task_resume to
        verify the write.

        Args:
            goal:        One-line statement of the overall task.
            plan:        Remaining steps, ';'-separated.
            done:        Completed steps, ';'-separated.
            findings:    VERIFIED results so far (sources included).
            next_prompt: Exact starting prompt for the next session.
            unverified:  Claims still needing verification, ';'-separated.
            status:      'open' (default), 'done', or 'abandoned'.
            task_id:     Omit on first checkpoint (generated); pass the returned
                         id on every later checkpoint of the same task.
        """
        import hashlib  # noqa: PLC0415

        self._log(f"TASK-CHECKPOINT: status={status} goal={goal[:80]}")
        if status not in ("open", "done", "abandoned"):
            return "ERROR: status must be 'open', 'done', or 'abandoned'."
        if not next_prompt.strip() and status == "open":
            return (
                "CHECKPOINT rejected: next_prompt is required for open tasks — "
                "write the exact prompt the next session should start from."
            )
        now = datetime.now().astimezone().isoformat()
        tid = task_id.strip() or hashlib.sha256(goal.encode()).hexdigest()[:8]
        try:
            conn = self._tasks_db()
            with conn:
                row = conn.execute(
                    "SELECT checkpoints, created_at, steps_json FROM task_blocks "
                    "WHERE task_id=?",
                    (tid,),
                ).fetchone()
                n = (row[0] + 1) if row else 1
                created = row[1] if row else now
                steps_json = row[2] if row else None  # carry the v0.3.2 step ledger
                conn.execute(
                    "INSERT OR REPLACE INTO task_blocks "
                    "(task_id, goal, status, plan, done_steps, findings, unverified, "
                    "next_prompt, checkpoints, created_at, updated_at, steps_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        tid,
                        goal,
                        status,
                        plan,
                        done,
                        findings,
                        unverified,
                        next_prompt,
                        n,
                        created,
                        now,
                        steps_json,
                    ),
                )
            conn.close()
            return (
                f"CHECKPOINT saved: task_id={tid} | status={status} | "
                f"checkpoint #{n}. Resume in a later session with "
                f"task_resume('{tid}')."
            )
        except Exception as e:
            self._log(f"TASK-CHECKPOINT ERROR: {e}")
            return f"CHECKPOINT error: {e}"

    def task_resume(self, task_id: str = "") -> str:
        """
        Load the task block to continue work from a previous session.

        GATE: call ONCE, as your FIRST tool call, when the user says "continue",
        "resume", "where were we", or references unfinished prior work. NEVER
        call mid-task, and never call when the user gives a fresh, self-contained
        task. Calling this more than once per session is a protocol violation.

        AFTER LOADING:
          Treat next_prompt as your working plan. Treat every item in UNVERIFIED
          as NOT established — re-verify before using. Checkpoint progress with
          task_checkpoint(task_id=...) as you work.

        Args:
            task_id: Specific block id. Empty = most recently updated open block.
        """
        self._log(f"TASK-RESUME: {task_id or '(latest open)'}")
        try:
            # v0.3.3: explicit column list — SELECT * broke on the steps_json
            # migration (12 columns vs 11-value unpack), killing resume for ALL
            # blocks. Columns are pinned here; new columns never leak in.
            _COLS = (
                "task_id, goal, status, plan, done_steps, findings, unverified, "
                "next_prompt, checkpoints, created_at, updated_at"
            )
            conn = self._tasks_db()
            if task_id.strip():
                row = conn.execute(
                    f"SELECT {_COLS} FROM task_blocks WHERE task_id=?",
                    (task_id.strip(),),
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT {_COLS} FROM task_blocks WHERE status='open' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) FROM task_blocks WHERE status='open'"
            ).fetchone()[0]
            conn.close()
            if not row:
                return (
                    "No matching task block. Either the id is wrong or there is "
                    "no open carried-over work — ask the user what to do next."
                )
            (
                tid,
                goal,
                status,
                plan,
                done,
                findings,
                unverified,
                next_prompt,
                n,
                created,
                updated,
            ) = row
            return (
                f"TASK BLOCK {tid} [{status}] — checkpoint #{n}, updated {updated}\n"
                f"GOAL: {goal}\n"
                f"DONE: {done or '(none)'}\n"
                f"REMAINING PLAN: {plan or '(none)'}\n"
                f"VERIFIED FINDINGS: {findings or '(none)'}\n"
                f"UNVERIFIED (re-verify before use): {unverified or '(none)'}\n"
                f"NEXT PROMPT: {next_prompt}\n"
                f"(open blocks total: {open_count})"
            )
        except Exception as e:
            self._log(f"TASK-RESUME ERROR: {e}")
            return f"TASK resume error: {e}"

    def plan_step_done(
        self,
        task_id: str,
        step_n: int,
        evidence: str,
        failed: bool = False,
    ) -> str:
        """
        Strike a completed plan step in the ledger and receive the NEXT step's
        packaged prompt (v0.3.2 — the planner↔agent loop for atomized plans).

        EVIDENCE GATE — mandatory:
          evidence must be the step's ACTUAL verify-check output (>=20 chars of
          command output / probe result), not a claim. Same gate as skill_outcome:
          "it worked" is rejected. The evidence is stored on the step for
          forensics and shown in later ledger summaries.
          GOOD: evidence="dig @192.168.1.5 pfsense.home.arpa → 192.168.1.50; 12/12 NOERROR"
                ← the verify command AND its output
          BAD:  evidence="step completed successfully"  ← claim, rejected

        LOOP DISCIPLINE:
          - Call this after executing exactly ONE step from a planner() plan.
          - The return value contains the next step's fresh-context prompt —
            execute ONLY that, then call this again.
          - Never skip ahead, never mark steps you did not execute.
          - Trust the return value — do NOT call task_resume mid-loop to
            re-check the ledger (task_resume is for fresh sessions only).

        CONTEXT HANDOFF — mandatory:
          If context usage is high (>70% or any context-monitor warning), do
          NOT execute the next step in this session. The ledger already
          persists — tell the user to start a fresh session, where
          task_resume returns the next step's prompt with the ledger summary.
          Grinding to the context ceiling mid-step loses work; the handoff
          costs nothing. Continuing past a context warning is a protocol
          violation.

        ON FAILURE:
          failed=True records the step as FAILED with your evidence and tells you
          to call planner(task, mode="revise", task_id=...) — the planner re-plans
          the remaining work with the failure in its ledger context. Do NOT keep
          executing subsequent steps after a failed dependency.

        Args:
            task_id: The ledger id returned by planner().
            step_n:  The step number just executed.
            evidence: Verbatim verify-check output (>=20 chars).
            failed:  True if the step's verify check did NOT pass.
        """
        import json as _json  # noqa: PLC0415

        self._log(f"PLAN-STEP-DONE: {task_id} step={step_n} failed={failed}")
        evidence = (evidence or "").strip()[:500]
        if len(evidence) < 20:
            return (
                "plan_step_done rejected: evidence too thin (<20 chars). Paste the "
                "step's actual verify-check output, not a claim."
            )
        try:
            now = datetime.now().astimezone().isoformat()
            conn = self._tasks_db()
            row = conn.execute(
                "SELECT goal, steps_json, checkpoints FROM task_blocks WHERE task_id=?",
                (task_id.strip(),),
            ).fetchone()
            if not row:
                conn.close()
                return (
                    f"plan_step_done: no task block '{task_id}'. Use the id "
                    "returned by planner()."
                )
            goal, steps_raw, ckpts = row[0], row[1], row[2] or 0
            steps = _json.loads(steps_raw) if steps_raw else []
            if not steps:
                conn.close()
                return (
                    f"plan_step_done: task block '{task_id}' has no step ledger — "
                    "it predates planner v2. Use task_checkpoint instead."
                )
            target = next((s for s in steps if s.get("n") == int(step_n)), None)
            if target is None:
                conn.close()
                ns = ", ".join(str(s.get("n")) for s in steps)
                return f"plan_step_done: no step {step_n} in plan (steps: {ns})."
            if target.get("status") == "done":
                conn.close()
                return f"plan_step_done: step {step_n} is already struck. No change."
            target["status"] = "failed" if failed else "done"
            target["evidence"] = evidence
            target["done_at"] = now
            pending = [s for s in steps if s.get("status") == "pending"]
            done = [s for s in steps if s.get("status") == "done"]
            done_lines = "; ".join(f"step {s['n']}: {s['what']}" for s in done)
            plan_lines = "; ".join(f"step {s['n']}: {s['what']}" for s in pending)
            if failed:
                next_prompt = (
                    f"Step {step_n} FAILED. Call planner(task=<original goal>, "
                    f"mode='revise', task_id='{task_id}') to re-plan the remaining "
                    "work before executing anything else."
                )
                status = "open"
            elif pending:
                next_prompt = self._plan_step_prompt(goal, steps, pending[0])
                status = "open"
            else:
                next_prompt = "(all steps complete)"
                status = "done"
            with conn:
                conn.execute(
                    "UPDATE task_blocks SET steps_json=?, done_steps=?, plan=?, "
                    "next_prompt=?, status=?, checkpoints=?, updated_at=? "
                    "WHERE task_id=?",
                    (
                        _json.dumps(steps),
                        done_lines,
                        plan_lines,
                        next_prompt,
                        status,
                        ckpts + 1,
                        now,
                        task_id.strip(),
                    ),
                )
            conn.close()
            if failed:
                return (
                    f"Step {step_n} recorded as FAILED ❌ (evidence stored).\n"
                    f"{next_prompt}"
                )
            if status == "done":
                return (
                    f"Step {step_n} struck ✔ — ALL {len(steps)} STEPS COMPLETE. "
                    f"Task block {task_id} closed (status=done). Report the "
                    "final outcome to the user with the collected evidence."
                )
            return (
                f"Step {step_n} struck ✔ ({len(done)}/{len(steps)} done, "
                f"{len(pending)} remaining).\n"
                "EXECUTE ONLY THE STEP BELOW, run its verify check, then call "
                f"plan_step_done('{task_id}', {pending[0]['n']}, "
                "evidence=<verify output>).\n"
                f"---\n{next_prompt}"
            )
        except Exception as e:
            self._log(f"PLAN-STEP-DONE ERROR: {e}")
            return f"plan_step_done error: {e}"

    def _active_download_guard(self, command: str) -> str:
        """Block starting a NEW download while one is already running on the host,
        so the LSE cannot clobber an in-progress partial file (data corruption,
        SY5 report). Returns a refusal string when `command` initiates a download
        AND a real downloader process is already active; '' otherwise.

        Code-level enforcement: the LSE has repeatedly re-issued download commands
        (curl / hf download) instead of calling monitor_download() to check
        progress, restarting the transfer and producing partial/corrupt files —
        docstrings did not hold. Conservative to avoid false positives: pgrep only
        runs for download-initiating commands; curl must carry an output flag so a
        health-check curl never trips it; hf/wget/aria2c/git-lfs always qualify;
        fail-open if the host cannot be probed."""
        import re as _re  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        _INITIATORS = (
            "curl ", "wget ", "aria2c ", "hf download",
            "huggingface-cli download", "git lfs pull", "git lfs fetch",
        )
        if not any(t in command.lower() for t in _INITIATORS):
            return ""  # not a download command — skip the probe entirely
        try:
            ps = _sp.run(
                ["pgrep", "-af",
                 "curl|wget|aria2c|hf download|huggingface-cli|git-lfs"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return ""  # cannot probe — fail open, do not block
        qualify = _re.compile(
            r"(?:wget |aria2c |hf download|huggingface-cli download|git-lfs|"
            r"curl\b.*(?:-O\b|-o |--output|--remote-name))"
        )
        active = [
            ln.strip()
            for ln in ps.stdout.splitlines()
            if ln.strip() and "pgrep" not in ln and qualify.search(ln)
            and "/dev/null" not in ln  # health-probe curls, not downloads
            and not _re.search(r"-o\s+-(?:\s|$)", ln)
        ]
        if not active:
            return ""
        self._log(f"DOWNLOAD-GUARD: blocked new download; active={active[0][:120]}")
        return (
            "BLOCKED: a download is already running on this host:\n"
            f"    {active[0][:200]}\n"
            "Starting another download now writes a second stream into the same "
            "partial file and CORRUPTS it — this is the reported failure.\n"
            "  • To CHECK progress, call the monitor_download tool with "
            "(file_path, expected_bytes). Do NOT re-run the download command.\n"
            "  • Start a new download ONLY after the current one COMPLETES, or "
            "after you intentionally kill it AND delete the partial file."
        )

    def ssh_run(
        self,
        host: str,
        command: str,
        user: str = "lse-admin",
        port: int = 22,
        timeout: int = 30,
    ) -> str:
        """
        Run a single command on a remote host via SSH.

        Passes the command as a direct SSH argv argument (NOT via bash -c), eliminating
        all local shell escaping. ControlMaster reuses an existing authenticated connection
        if one exists, adding ~0ms overhead after the first call to a host.

        Use this for: pgrep, systemctl status, tail, cat, ls, single-tool checks.
        For multi-command sequences, nohup/background operations, or env var exports:
        use ssh_script() instead.

        PKILL RULE (v0.3.7 — enforced in code, 2026-07-04 post-mortem):
          'pkill -f <pattern>' sent through ssh_run matches the remote shell's
          OWN command line (it contains the pattern) and kills the SSH session:
          exit 255, target possibly dead but unconfirmed. The guard blocks
          unbracketed patterns.
          GOOD: ssh_run(host, "pkill -f 'llama[-]server'")
                ← bracketed char: regex matches the process, not this cmdline
          GOOD: kill by PID via ssh_script (script files never self-match)
          BAD:  ssh_run(host, "pkill -f llama-server")  ← self-kill, blocked

        MUX AUTO-RECOVERY (v0.3.7): a stale ControlMaster socket is the #1
        cause of exit 255 on a REACHABLE host. On exit 255 with a mux socket
        present, ssh_run now terminates the stale master, removes the socket,
        and retries ONCE automatically — do not hand-rm /tmp/ssh_mux_* first.

        KB-FIRST: search_kb("{host} SSH access") before the first ssh_run to a new host.

        Args:
            host:    remote hostname or IP (e.g. "node3090.home.arpa")
            command: single command string — no chaining (;/&&/||), no nohup/disown
            user:    SSH user (default: lse-admin)
            port:    SSH port (default: 22)
            timeout: total timeout in seconds (default: 30)

        Returns:
            stdout on success; [SSH FAILURE] / [exit N] / [TIMEOUT] on error.
        """
        import subprocess as _sp

        _COMPLEX = ["nohup", "& disown", "&disown", "export ", "$(", "`", "eval "]
        if any(p in command for p in _COMPLEX):
            return (
                "[SSH_COMPLEXITY_GUARD] ssh_run is for simple single commands only.\n"
                f"Detected pattern: {[p for p in _COMPLEX if p in command]}\n"
                f"→ Use ssh_script(host={host!r}, user={user!r}, script=<commands as script body>)"
            )

        # v0.3.7 PKILL SELF-MATCH GUARD (2026-07-04 post-mortem): the remote
        # shell's cmdline contains the pattern → pkill -f kills the session.
        toks = command.split()
        if "pkill" in toks and "-f" in toks:
            try:
                pat = toks[toks.index("-f") + 1].strip("'\"")
            except IndexError:
                pat = ""
            if pat and "[" not in pat:
                return (
                    "[PKILL_SELF_MATCH_GUARD] 'pkill -f "
                    f"{pat}' over ssh_run matches the remote shell's own command "
                    "line and kills the SSH session (exit 255; target possibly "
                    "dead but UNCONFIRMED).\n"
                    f"→ Bracket one character: pkill -f '{pat[:1]}[{pat[1:2] or pat[:1]}]"
                    f"{pat[2:]}'  — or kill by PID via ssh_script (script files "
                    "do not self-match)."
                )

        opts = self._ssh_opts(host, user, port)
        cmd = ["ssh"] + opts + [f"{user}@{host}", command]

        try:
            r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
        except _sp.TimeoutExpired:
            return f"[TIMEOUT] ssh_run to {host} exceeded {timeout}s"
        except Exception as e:
            return f"[ERROR] ssh_run: {e}"

        note = ""
        if r.returncode == 255:
            # v0.3.7 MUX AUTO-RECOVERY: stale ControlMaster socket → kill the
            # dead master, remove the socket, retry ONCE.
            ctl = self._SSH_CTL_PATH.format(host=host, port=port, user=user)
            if os.path.exists(ctl):
                try:
                    _sp.run(
                        ["ssh", "-O", "exit", "-o", f"ControlPath={ctl}",
                         f"{user}@{host}"],
                        capture_output=True, text=True, timeout=10,
                    )
                except Exception:
                    pass
                try:
                    os.unlink(ctl)
                except OSError:
                    pass
                try:
                    r2 = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
                    if r2.returncode != 255:
                        r = r2
                        note = ("[stale ControlMaster mux detected — socket "
                                "removed, retried OK]\n")
                        self._log(f"SSH-RUN: mux auto-recovery on {host}")
                except _sp.TimeoutExpired:
                    return f"[TIMEOUT] ssh_run mux-retry to {host} exceeded {timeout}s"

        if r.returncode == 255:
            return (
                f"[SSH FAILURE] exit 255 — SSH could not reach {host} "
                "(mux already auto-cleared and retried).\n"
                f"Diagnose in order: (1) ping -c2 {host}; (2) sshd on the host; "
                "(3) if your command embeds a process pattern (pkill/pgrep), "
                "suspect self-match.\n"
                f"ssh stderr: {r.stderr.strip() or '(none)'}"
            )
        if r.returncode != 0:
            out = r.stdout.strip()
            err = r.stderr.strip()
            return (
                f"{note}[exit {r.returncode}]\n{out}\n"
                f"{('[stderr] ' + err) if err else ''}"
            ).strip()

        return (note + (r.stdout.strip() or "(no output)")).strip()

    def ssh_script(
        self,
        host: str,
        script: str,
        user: str = "lse-admin",
        port: int = 22,
        interpreter: str = "bash",
        timeout: int = 120,
        cleanup: bool = True,
    ) -> str:
        """
        Execute a multi-command script on a remote host without shell escaping.

        Writes script to a local tempfile → scp to /tmp/lse_script_<hash>.sh on
        the remote → executes it → cleans up. Script content is never interpreted
        by any local shell: characters like $, ", \\, ; are transmitted as raw bytes
        and only evaluated by the remote bash. Eliminates all nested quoting issues.

        Auto-injects </dev/null on nohup lines that lack it, preventing SIGHUP from
        killing backgrounded processes when the SSH session closes.

        Use this for: nohup/background sequences, multi-step setup chains, env var
        exports, kill+restart sequences — anything that would need nested quoting as
        a one-liner in execute_command.

        PKILL IN SCRIPTS (v0.3.7, 2026-07-04 post-mortem):
          Script files do NOT self-match pkill -f patterns (the remote cmdline is
          'bash /tmp/lse_script_<hash>.sh'), so kill-by-pattern is SAFE here —
          this is the correct home for process management, not ssh_run.
          BUT: pkill exits 1 when NOTHING matched. Under set -e / bare exit-code
          checks that reads as failure. Append '|| true' to every pkill/kill
          line whose target may already be dead:
          GOOD: pkill -9 -f 'llama[-]server' 2>/dev/null || true
          BAD:  pkill -9 -f 'llama-server'   ← exit 1 when already dead is a
                false failure; you will misread it as "the kill failed".

        KB-FIRST: search_kb("{host} SSH access") before first use on a new host.

        Args:
            host:        remote hostname or IP
            script:      script body as a string (shebang added automatically)
            user:        SSH user (default: lse-admin)
            port:        SSH port (default: 22)
            interpreter: script interpreter (default: bash)
            timeout:     execution timeout in seconds (default: 120)
            cleanup:     remove remote script file after execution (default: True)

        Returns:
            Combined stdout/stderr on success; [SCP FAILED] / [TIMEOUT] / [exit N] on error.

        Example:
            ssh_script(
                host="node3090.home.arpa",
                script='''
pkill -9 -f goethe_mcp.py 2>/dev/null || true
sleep 0.5
mkdir -p /home/lse-admin/lse
GOETHE_MCP_TOKEN=abc123 nohup python3 ~/goethe_mcp.py \\
  --transport http --port 9700 --host 0.0.0.0 \\
  > /tmp/goethe-node3090.log 2>&1 &
sleep 3
pgrep -a goethe_mcp
ss -tlnp | grep 9700
tail -5 /tmp/goethe-node3090.log
'''
            )
        """
        import subprocess as _sp
        import tempfile as _tf
        import hashlib as _hl
        import os as _os

        # Auto-inject </dev/null on nohup lines missing it (prevents SIGHUP)
        def _fix_nohup(line: str) -> str:
            stripped = line.rstrip()
            if "nohup" in stripped and "</dev/null" not in stripped and stripped.endswith("&"):
                return stripped[:-1].rstrip() + " </dev/null &"
            return line

        fixed_script = "\n".join(_fix_nohup(l) for l in script.splitlines())
        full_script = f"#!/usr/bin/env {interpreter}\nset -euo pipefail\n{fixed_script}\n"

        script_hash = _hl.md5(fixed_script.encode()).hexdigest()[:8]
        remote_path = f"/tmp/lse_script_{script_hash}.sh"

        opts = self._ssh_opts(host, user, port)

        with _tf.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(full_script)
            local_path = f.name

        try:
            # scp shares ControlMaster socket — free after first ssh call to host
            # scp uses -P (uppercase) for port, unlike ssh which uses -p
            scp_opts = [o for pair in zip(opts, opts[1:] + [""]) for o in pair
                        if not (pair[0] == "-p" and pair[1] == str(port))]
            # Simpler: rebuild opts without -p/port, add -P for scp
            scp_base_opts = []
            skip_next = False
            for idx, o in enumerate(opts):
                if skip_next:
                    skip_next = False
                    continue
                if o == "-p":
                    skip_next = True
                    continue
                scp_base_opts.append(o)

            scp_cmd = (
                ["scp"] + scp_base_opts + ["-P", str(port),
                local_path, f"{user}@{host}:{remote_path}"]
            )
            scp = _sp.run(scp_cmd, capture_output=True, text=True, timeout=30)
            if scp.returncode != 0:
                return (
                    f"[SCP FAILED] Could not transfer script to {host}:{remote_path}\n"
                    f"stderr: {scp.stderr.strip()}"
                )

            run_cmd = ["ssh"] + opts + [f"{user}@{host}", f"{interpreter} {remote_path}"]
            r = _sp.run(run_cmd, capture_output=True, text=True, timeout=timeout)

            out = r.stdout.strip()
            err = r.stderr.strip()
            result = out
            if err:
                result += f"\n[stderr] {err}"
            if r.returncode not in (0,):
                result = f"[exit {r.returncode}]\n{result}"
            return result.strip() or "(no output)"

        except _sp.TimeoutExpired:
            return f"[TIMEOUT] ssh_script on {host} exceeded {timeout}s"
        except Exception as e:
            return f"[ERROR] ssh_script: {e}"
        finally:
            _os.unlink(local_path)
            if cleanup:
                _sp.run(
                    ["ssh"] + opts + [f"{user}@{host}", f"rm -f {remote_path}"],
                    capture_output=True, timeout=10,
                )

    def _validate_command_safety(self, command: str, cwd: str) -> Optional[str]:
        """Validate command safety. Returns error string if blocked, None if safe."""
        # ── Block permanently forbidden commands ──────────────────────────────
        cmd_lower = command.lower().strip()
        for blocked in self._BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                self._log(f"HARD-BLOCKED: {command}")
                return (
                    f"BLOCKED: '{blocked}' is permanently forbidden. "
                    "This operation cannot be performed by the agent under any circumstances."
                )

        # ── Block privilege escalation anywhere in the command (v1.4.2 fix) ──
        for priv in self._PRIVILEGED_PREFIXES:
            if priv in cmd_lower:
                self._log(f"PRIV-BLOCKED: {command}")
                return (
                    f"BLOCKED: '{priv.strip()}' detected in command. "
                    "Use sudo_delegation_block instead."
                )

        # ── Block writes to privileged system paths ───────────────────────────
        # Only block when a write op TARGETS a privileged path; reads (cat/tr/grep
        # < /proc, ps, etc.) are allowed. /mnt/ dropped (legit user data lives there).
        import re as _re_pw  # noqa: PLC0415
        _priv_re = r"(?:/etc/|/usr/|/boot/|/sys/|/proc/)"
        _write_to_priv = _re_pw.search(
            r">>?\s*" + _priv_re
            + r"|\btee\s+(?:-a\s+)?" + _priv_re
            + r"|\b(?:cp|mv|dd|truncate)\b[^|;&\n]*\s" + _priv_re
            + r"|\bsed\s+-i\b[^|;&\n]*" + _priv_re
            + r"|\brm\s+[^|;&\n]*" + _priv_re,
            command,
        )
        if _write_to_priv:
            self._log(f"WRITE-BLOCKED: {command}")
            return (
                f"BLOCKED: write targeting a privileged path — matched {_write_to_priv.group(0)!r}. "
                "Use sudo_delegation_block to delegate this to the user, or report a false positive."
            )

        # ── Block clobbering an in-progress download (v0.2.0) ─────────────────
        # If a download is already running, refuse a new one and route the model
        # to monitor_download instead. Prevents the partial-file corruption from
        # the LSE re-issuing curl/hf download to "check progress".
        _dl_block = self._active_download_guard(command)
        if _dl_block:
            return _dl_block

        # ── Validate working directory ────────────────────────────────────────
        if not self._is_allowed_read(cwd):
            return f"BLOCKED: working_dir '{cwd}' is outside allowed read paths."
        return None

    def execute_command(self, command: str, working_dir: str = "") -> str:
        """
        Execute a read-only or write-safe shell command in the WSL Ubuntu environment.
        Use for: ls, cat, grep, find, ps, df, uname, systemctl status, apt list,
                 journalctl, tail, head, wc, etc.
        Do NOT use for commands requiring sudo — use sudo_delegation_block instead.
        Output is capped at MAX_OUTPUT_CHARS. Always pipe through grep/head/awk to limit output.

        COMBINE RULE — batch independent commands into a single call:
          GOOD: execute_command("uname -r && nproc")          ← one call, two results
          GOOD: execute_command("hostname; whoami; uptime")   ← one call, three results
          BAD:  execute_command("uname -r")                   ← then separate call for nproc
          BAD:  execute_command("nproc")                      ← should have been combined above
          Use && when the second command depends on the first succeeding.
          Use ; when commands are fully independent.
          Never make two execute_command calls when one combined call will do.

        DOWNLOAD PROGRESS RULE — mandatory:
          To CHECK on a download already in progress, call the monitor_download
          tool (file_path, expected_bytes). NEVER re-run the download command
          (curl / wget / hf download / huggingface-cli) to "test" or "check" it —
          a second fetch writes into the same partial file and corrupts it. This
          is code-enforced: execute_command REFUSES a download-initiating command
          while a downloader process is already running (see _active_download_guard).
          Start a new download only after the current one finishes or is killed.

        CONFIG GROUND-TRUTH RULE — mandatory:
          Tokens, passwords, paths, ports, and config values you state or use
          must come from a tool result obtained THIS session (read_file,
          execute_command cat/grep, docker inspect/exec) — never from recall
          and never from a KB doc older than the system it describes.
          GOOD: docker exec searxng grep open_metrics /etc/searxng/settings.yml
                ← then quote THAT value
          BAD:  "the token is searxng-metrics-token-2026" from memory
                ← invented value sent the operator on a 401 hunt
          Citing a config value without a same-session read is a protocol violation.

        RESOURCE-AVAILABILITY RULE — mandatory before any external connection:
          Before any operation requiring a remote resource (SSH, API call,
          docker exec, curl to a service), verify the resource is in its
          expected state first. A connection timeout is not a credential or
          config error — it may mean the resource is simply unavailable.
          Diagnosing the wrong layer wastes time and can trigger corrective
          actions based on a false premise.

          For network hosts:
            1. ping -c 1 -W 2 <host_ip> to check reachability.
            2. If unreachable AND host is a known managed node:
               do NOT attempt the connection. Instead:
               a. Check _NODE_REGISTRY → call wake_node if the host is there.
               b. Otherwise search_kb("<hostname> access") for recovery steps.
               c. If no path found in either: stop. State "Host <host> is
                  unreachable. No recovery path found. Operator action required."
                  Do not attempt SSH — the 30s timeout is not diagnostic.
            3. If unreachable AND host is external or unknown: ICMP may be
               blocked. Proceed with the connection but note the ping result.
          For services: curl -sf <healthcheck_url> or systemctl is-active <name>.
          For containers: docker inspect --format '{{.State.Status}}' <name>.

          GOOD: ping -c 1 -W 2 <managed_host_ip> → 100% packet loss
                → found in node registry → "Host unreachable. Wake it? (~Xs)"
                → (on confirm) wake_node → re-ping → SSH
          GOOD: ping fails, host external/unknown → "Ping failed (ICMP may be
                blocked). Attempting SSH." → proceed
          BAD:  ping fails (managed node) → ssh → 30s timeout → "SSH auth failed"
                ← wrong layer diagnosed; recovery path not offered
          BAD:  no recovery path found → guess WoL MAC from ARP → act on guess
                ← unverified artifact (see RELEASE ASSET RULE)
          Attempting a connection to a managed node before verifying
          availability is a protocol violation.

        VENDOR-BEHAVIOR GROUND-TRUTH RULE — mandatory before modifying external software:
          Before modifying any file from an external project based on an
          assumption about HOW that software behaves internally — call order,
          field injection, protocol semantics, version-specific behavior —
          verify the assumption via the waterfall BEFORE any file is modified:
            search_kb → fetch vendor changelog/README → search GitHub issues → search_web
          Patching on recall is a protocol violation regardless of confidence
          in the assumption. The write_file snapshot gate makes patches
          reversible; it does NOT prevent acting on a false premise.
          The waterfall is the control, not the snapshot.

          Trigger: you are about to sed -i, patch, or write_file a file from
          an external project, and the edit is grounded in how you believe
          that software behaves rather than in a same-session fetched source,
          issue, or changelog entry.

          GOOD: hypothesis formed → search_kb + fetch GitHub issues for that
                behavior → root cause confirmed or refuted → fix designed from
                verified cause
          BAD:  hypothesis formed → sed -i → rebuild → fails
                → new hypothesis → sed -i again  (protocol violation × attempts)
          Modifying external software files based on an unverified behavioral
          assumption is a protocol violation.

        RELEASE ASSET RULE — mandatory before referencing any external artifact:
          Release tags, asset filenames, image tags, package version strings,
          and download URLs follow per-project conventions set by the maintainer.
          They cannot be inferred by extending a prior release's pattern
          (vX.Y.Z → vX.Y.Z+1, beta.N → beta.N+1).
          Before writing any download URL, VERSION/RELEASE variable, image tag,
          or package pin to a file or command:
            GitHub: call get_github_release("<owner>/<repo>") to confirm tag
                    and asset filenames
            Docker / PyPI / npm: fetch the registry page or query its API
          Never construct an artifact reference from a version number alone
          and treat it as verified.

          GOOD: get_github_release("owner/repo") → confirms exact tag and
                asset filename → use those exact strings
          BAD:  increment prior release tag → write to Makefile → 404 on fetch
                → retry with another guess  (each guess is a wasted build cycle)
          Constructing an artifact reference without fetching its source is a
          protocol violation.

        DESTRUCTIVE OPERATION PROTOCOL — mandatory before rm, truncate, or overwrite:
          Before executing any command that irreversibly deletes or overwrites data:
          1. Name the exact target in your response (file path or pattern).
          2. Warn the user: "This will permanently delete/overwrite <target>."
          3. Ask: "Shall I proceed? (yes/no)"
          4. Wait for an explicit "yes" before calling this function.
          This applies to: rm <file>, truncate, > (shell overwrite redirect),
          and any command whose primary effect is data destruction.
          It does NOT apply to: read-only commands, append (>>), or temp-file cleanup
          where the file was created in the same session by this agent.
          Proceeding without confirmation is a protocol violation.

        POST-DELETE VERIFY RULE — mandatory after any deletion:
          After any rm command that succeeds, immediately make a follow-up call to
          confirm the target no longer exists before reporting completion:
            GOOD: execute_command("rm /tmp/lse/file.txt && stat /tmp/lse/file.txt")
            GOOD: execute_command("ls /tmp/lse/")   ← follow-up call after rm succeeds
            BAD:  execute_command("rm /tmp/lse/file.txt")  ← then report "Done" with no verify
          Reporting the file as deleted without a verification call is a protocol violation.

        SSH KB-FIRST RULE — mandatory before any ssh command (v1.7.13):
          Before issuing any ssh command to a managed device, call
          search_kb(query='{hostname} SSH access') with NO topic_filter.
          The KB stores the correct key file path, username, IP, and options
          for every managed device. Without the key, SSH will time out silently.
          Rules:
          1. search_kb FIRST — retrieve key path, username, host IP from KB.
          2. No topic_filter — SSH access queries are device-agnostic; never
             apply topic_filter='pfsense' (or any device name) to an SSH query
             for a different device. topic_filter narrows results to that device
             only — using pfsense filter for rutx50 returns pfSense API docs.
          3. Use exact key: always pass -i <key_path> from the KB result.
             Never attempt bare ssh (no -i) to a key-only device.
          GOOD: search_kb("rutx50 SSH access") → finds id_ed25519_rutx50 →
                ssh -i ~/.ssh/id_ed25519_rutx50 root@192.168.5.3 'uptime'
          BAD:  ssh root@rutx50 'uptime'  ← no key → 30s timeout (protocol violation)
          BAD:  search_kb("rutx50 SSH access", topic_filter="pfsense")
                ← wrong filter → pfSense API docs returned (protocol violation)

        DEVICE-IDENTITY RULE — SSH commands only (v1.7.12):
          Device OS/vendor/platform is auto-fingerprinted on the FIRST SSH call
          to any new host and prepended as [DEVICE FINGERPRINT: ...] to every
          result. NEVER infer device type from IP address, hostname, or training
          knowledge. The fingerprint is ground truth. All CLI syntax, path
          conventions, and package managers must be chosen from the fingerprint,
          not from memory.
          GOOD: fingerprint shows "OpenWrt" → use opkg, /etc/init.d/, uci
          BAD:  "192.168.5.3 looks like a MikroTik" → RouterOS CLI (WRONG)

        SLOW REMOTE COMMAND RULE — mandatory for SSH commands involving disk inspection:
          du -sh <path> walks the entire directory tree to count bytes.
          On a large or remote mount (NAS, HDD, network share) this can take
          minutes per path and blocks the session until it completes.
          NEVER chain multiple du -sh calls in a single SSH command.
          Use fast alternatives that read filesystem metadata instead:

          GOOD: ssh ... 'df -h /mnt/'                  ← instant: reads fs stats
          GOOD: ssh ... 'df -h /mnt/NODE3090/models'   ← instant for one mount
          GOOD: ssh ... 'ls -lh /mnt/NODE3090/models/' ← file sizes, no tree walk
          GOOD: ssh ... 'du -sh --max-depth=1 /mnt/NODE3090/' ← limited tree depth
          BAD:  ssh ... 'du -sh /mnt/*/ && du -sh /mnt/NODE3090/*/' ← O(files) × mounts
          BAD:  ssh ... 'du -sh /mnt/NODE3090/models/'              ← walks every file

          Also: wrap SSH commands that may be slow with a timeout prefix to
          prevent blocking indefinitely when a remote host is degraded:
            GOOD: ssh ... 'timeout 30 du -sh --max-depth=1 /mnt/'

        Output filter examples:
          GOOD: execute_command("journalctl -u nginx -n 20 --no-pager")
          GOOD: execute_command("tail -20 /home/sy5/.bashrc")
          BAD:  execute_command("journalctl -u nginx")   ← no output limit
          BAD:  execute_command("sudo systemctl restart nginx")  ← use sudo_delegation_block
        """
        cwd = working_dir.strip() or self.valves.DEFAULT_WORKING_DIR

        if (err := self._validate_command_safety(command, cwd)):
            return err

        # ── SSH device auto-fingerprint (v1.7.12) ──────────────────────────────
        _fp_note = ""
        _cmd_stripped = command.lstrip()
        if _cmd_stripped.startswith("ssh ") and not any(
            m in command for m in ("os-release", "uname -srm", "__FP__")
        ):
            # Extract ssh options + user@host prefix from original command
            import re as _re_fp  # noqa: PLC0415

            _tokens = command.split()
            _OPTS_WITH_VAL = {
                "-p",
                "-i",
                "-o",
                "-l",
                "-F",
                "-J",
                "-c",
                "-D",
                "-E",
                "-I",
                "-L",
                "-m",
                "-R",
                "-S",
                "-w",
                "-W",
                "-b",
                "-Q",
            }
            _hi, _i = None, 1
            while _i < len(_tokens):
                if _tokens[_i].startswith("-"):
                    _hi = None
                    _i += 2 if _tokens[_i] in _OPTS_WITH_VAL else 1
                else:
                    _hi = _i
                    break
            if _hi is not None:
                _user_at_host = _tokens[_hi]
                _fp_host = _user_at_host.split("@")[-1]
                if _fp_host not in self._device_cache:
                    _ssh_prefix = " ".join(_tokens[1 : _hi + 1])
                    _fp_cmd = (
                        f"ssh -o BatchMode=yes -o ConnectTimeout=8 "
                        f"-o StrictHostKeyChecking=no {_ssh_prefix} "
                        f"'echo __FP__; cat /etc/os-release 2>/dev/null; "
                        f"echo __UNAME__; uname -srm 2>/dev/null'"
                    )
                    try:
                        _fp_proc = subprocess.run(
                            _fp_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=15,
                            cwd=cwd,
                        )
                        _fp_out = (_fp_proc.stdout or "").strip()
                        _platform = "unknown"
                        _mp = _re_fp.search(r'PRETTY_NAME="?([^"\n]+)"?', _fp_out)
                        if _mp:
                            _platform = _mp.group(1).strip('"')
                        else:
                            _mu = _re_fp.search(r"__UNAME__\s*([^\n]+)", _fp_out)
                            if _mu:
                                _platform = _mu.group(1).strip()
                        # Only cache on success — unknown/error results must not
                        # block a retry on the next SSH call with the correct key.
                        if (
                            _fp_proc.returncode == 0
                            and _platform != "unknown"
                            and not _platform.startswith("(fingerprint")
                        ):
                            self._device_cache[_fp_host] = {
                                "platform": _platform, "raw": _fp_out[:500]
                            }
                            self._log(f"DEVICE-FP: {_fp_host} -> {_platform}")
                        else:
                            self._log(
                                f"DEVICE-FP FAILED (not cached): {_fp_host} "
                                f"rc={_fp_proc.returncode} platform={_platform}"
                            )
                            _platform = "unknown"  # ensure consistent state
                    except Exception as _fp_e:
                        # Do not cache — allow retry on next SSH call
                        self._log(f"DEVICE-FP ERROR (not cached): {_fp_host}: {_fp_e}")
                        _platform = "unknown"
                if _fp_host in self._device_cache:
                    _cached = self._device_cache[_fp_host]
                    _fp_note = (
                        f"\n[DEVICE FINGERPRINT: host={_fp_host} | "
                        f"platform={_cached['platform']} | "
                        f"source=os-release/uname — ground truth. "
                        f"Use this platform for ALL CLI decisions. "
                        f"Never infer device type from IP or hostname.]"
                    )
                elif _platform == "unknown":
                    _fp_note = (
                        f"\n[DEVICE FINGERPRINT PENDING: host={_fp_host} | "
                        f"platform=unknown — SSH auth failed or no output. "
                        f"Fingerprint NOT cached; will retry on next SSH call. "
                        f"Do NOT infer device type from IP or hostname.]"
                    )

        # ── SSH complexity guard (v0.2.6) ────────────────────────────────────
        # Block patterns that cause exit 255 when routed through bash -c + SSH.
        # Redirect model to ssh_script() which transfers the script as a file.
        if _cmd_stripped.startswith("ssh "):
            _SSH_COMPLEX_MARKERS = [
                "nohup", "& disown", "&disown", "export ", "eval ", "$(", "`",
            ]
            if any(m in command for m in _SSH_COMPLEX_MARKERS):
                import re as _re_guard
                _hm = _re_guard.search(
                    r'ssh\s+(?:\S+\s+)*?(\S+@\S+|\d{1,3}(?:\.\d{1,3}){3}|\S+\.(?:home\.arpa|\w+))',
                    command
                )
                _detected = [m for m in _SSH_COMPLEX_MARKERS if m in command]
                _host_hint = _hm.group(1).split("@")[-1] if _hm else "<host>"
                return (
                    "[SSH_COMPLEXITY_GUARD] Command blocked — contains patterns that cause "
                    f"exit 255 when passed through bash -c + SSH:\n"
                    f"  Detected: {_detected}\n\n"
                    "Root cause: Python → bash -c → SSH → remote sh applies three layers of "
                    "shell parsing. Special characters ($, \", &, ;) are reinterpreted at each "
                    "layer. The command arrives on the remote host corrupted or not at all.\n\n"
                    "→ Use ssh_script() — transfers the script as a raw file, zero escaping:\n\n"
                    f"  ssh_script(\n"
                    f"      host={_host_hint!r},\n"
                    f"      script='''\n"
                    f"  <paste your commands here, one per line, no escaping needed>\n"
                    f"  '''\n"
                    f"  )"
                )

        # ── Execute ───────────────────────────────────────────────────────────
        self._log(f"CMD: {command}  (cwd={cwd})")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.valves.COMMAND_TIMEOUT,
                cwd=cwd,
            )
            output = result.stdout or result.stderr or "(no output)"
            rc = result.returncode
            if len(output) > self.valves.MAX_OUTPUT_CHARS:
                output = (
                    output[: self.valves.MAX_OUTPUT_CHARS]
                    + f"\n... [TRUNCATED — {len(output)} chars total. "
                    "Re-run with more specific filters.]"
                )
            self._log(f"DONE rc={rc} len={len(output)}")
            result_str = output if rc == 0 else f"[exit {rc}]\n{output}"
            return result_str + _fp_note
        except subprocess.TimeoutExpired:
            self._log(f"TIMEOUT: {command}")
            return (
                f"ERROR: Command timed out after {self.valves.COMMAND_TIMEOUT} seconds."
            )
        except Exception as e:
            self._log(f"ERROR: {e}")
            return f"ERROR: {str(e)}"

    def read_file(self, path: str, max_lines: int = 100, offset_lines: int = 0) -> str:
        """
        Read a file from the filesystem with optional pagination.
        Default: first 100 lines. Use offset_lines to page through large files.
        Always read the smallest slice you need.

        CRITICAL ROUTING RULES — choose the right tool:

          • User asks for "last N lines" of any file
            → use execute_command("tail -N <path>")  NOT this function

          • User asks for lines matching a pattern
            → use execute_command("grep 'pattern' <path>")  NOT this function

          • You need to read a file BEFORE editing/overwriting it
            → use THIS function with max_lines large enough to get the ENTIRE file.
               Do NOT use tail or partial reads before an overwrite — partial reads
               cause data loss when the content is used to overwrite the full file.
               Check the line count first: execute_command("wc -l <path>")
               Then read all lines: read_file(path, max_lines=<total_lines>)

          • File is a log: use execute_command("tail -N <path>") or grep.

        Use read_file ONLY when you need a specific line range from the beginning or
        middle of a file where tail/grep do not apply.

        PRIVILEGED PATH BEHAVIOUR:
          If this function returns BLOCKED due to a privileged path (/root/, /proc/,
          /sys/, etc.) or a permission denied error on any path:
          1. Do NOT try alternative commands. Do NOT attempt:
               execute_command("cat <path>")
               execute_command("python3 -c \"open('<path>').read()\"")
               execute_command("base64 <path>")
             These will also fail and cause a retry loop. Stop immediately.
          2. Explicitly offer the user a delegation block:
               "That path requires elevated access. Shall I read it via sudo?"
          3. Call sudo_delegation_block with: sudo cat <path>
          This must appear in your response — do not leave it only in your reasoning.
          Trying workarounds before delegating is a protocol violation.
        """
        if not self._is_allowed_read(path):
            return f"BLOCKED: '{path}' is outside allowed read paths."

        resolved = os.path.realpath(os.path.expanduser(path))
        if not os.path.isfile(resolved):
            return f"ERROR: File not found: {path}"

        self._log(f"READ: {path} lines={offset_lines}..{offset_lines + max_lines}")
        try:
            with open(resolved, "r", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            sliced = lines[offset_lines : offset_lines + max_lines]
            content = "".join(sliced)
            footer = (
                f"\n--- Lines {offset_lines + 1}–{offset_lines + len(sliced)} "
                f"of {total} total ---"
            )
            return content + footer
        except Exception as e:
            return f"ERROR: {str(e)}"

    def _snapshot_before_write(self, resolved: str):
        """Recovery snapshot of an existing file before an in-place overwrite or
        append (v0.2.0 code gate). Returns (ok: bool, note: str).

        git-native first: `git hash-object -w` stores the CURRENT content as a
        recoverable blob WITHOUT touching the index, working tree, or HEAD, then
        update-ref pins it under refs/lse-snapshots/ so gc cannot reap it. Falls
        back to a timestamped copy under <dir>/.lse-backups/. If BOTH fail the
        function returns ok=False and the caller MUST refuse the write — an
        in-place edit with no recovery point is exactly the failure this gate
        prevents. Enforcement in code, not docstring (sudo-blocker lineage)."""
        import subprocess as _sp  # noqa: PLC0415
        import shutil as _sh  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        import time as _t  # noqa: PLC0415

        if not _os.path.isfile(resolved):
            return True, "new file — no snapshot needed"
        # 1) git-native snapshot — non-intrusive (no index/worktree/HEAD change)
        try:
            top = _sp.run(
                ["git", "-C", _os.path.dirname(resolved),
                 "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if top.returncode == 0 and top.stdout.strip():
                root = top.stdout.strip()
                h = _sp.run(
                    ["git", "-C", root, "hash-object", "-w", resolved],
                    capture_output=True, text=True, timeout=10,
                )
                if h.returncode == 0 and h.stdout.strip():
                    sha = h.stdout.strip()
                    ts = _t.strftime("%Y%m%d-%H%M%S")
                    rel = _os.path.relpath(resolved, root)
                    _sp.run(
                        ["git", "-C", root, "update-ref",
                         f"refs/lse-snapshots/{ts}-{sha[:8]}", sha],
                        capture_output=True, text=True, timeout=5,
                    )
                    self._log(f"SNAPSHOT(git): {rel} -> {sha[:12]}")
                    return True, (
                        f"git blob {sha[:12]} "
                        f"(restore: git -C {root} cat-file -p {sha[:12]} > {rel})"
                    )
        except Exception as e:  # noqa: BLE001
            self._log(f"SNAPSHOT git path error: {e}")
        # 2) filesystem fallback — timestamped copy beside the file
        try:
            bdir = _os.path.join(_os.path.dirname(resolved), ".lse-backups")
            _os.makedirs(bdir, exist_ok=True)
            ts = _t.strftime("%Y%m%d-%H%M%S")
            dest = _os.path.join(bdir, f"{_os.path.basename(resolved)}.{ts}.bak")
            _sh.copy2(resolved, dest)
            self._log(f"SNAPSHOT(copy): {dest}")
            return True, f"backup copy {dest}"
        except Exception as e:  # noqa: BLE001
            self._log(f"SNAPSHOT FAILED: {resolved}: {e}")
            return False, f"snapshot failed: {e}"

    def write_file(
        self, path: str, content: str, mode: str = "overwrite", force: bool = False
    ) -> str:
        """
        Write content to a file within allowed write paths.

        MODE SELECTION — choose carefully:
          mode='append'    → adds content to the END of the file. Use this for:
                             adding aliases, PATH entries, config lines, cron jobs,
                             or any single addition to an existing file.
                             Safe — does not risk losing existing content.

          mode='overwrite' → REPLACES the entire file. Only use when you have read
                             the COMPLETE file first using read_file (not tail, not
                             partial reads). If you used tail or partial reads,
                             use append mode instead to avoid data loss.

        CONFIRMATION PROTOCOL — mandatory for ALL writes:
          This function must NEVER be called without explicit user confirmation.
          The required sequence before calling write_file is:

          1. Show the user exactly what will be written (a diff or the full content).
          2. State which file will be modified and what mode will be used.
          3. Ask: "Shall I write this? (yes/no)"
          4. Wait for an explicit "yes" before calling this function.
          5. After writing, verify with: execute_command("tail -5 <path>") or read_file.

          This applies to new file creation AND edits to existing files.
          Skipping confirmation is a protocol violation.

        SIZE SANITY CHECK — automatic guard on overwrite:
          If mode='overwrite' and the new content has fewer than 25% of the lines
          in the existing file, this function returns an error. This prevents
          accidentally destroying a large file by writing a short snippet.

          When the check fires:
          1. Show the user the line count discrepancy.
          2. Ask explicitly: "The new content is N lines vs M existing. Intentional?"
          3. Wait for explicit "yes".
          4. Call write_file again with force=True to bypass the check.

          force=True ONLY after explicit user confirmation of intentional truncation.
          Passing force=True without user confirmation is a protocol violation.

        RECOVERY SNAPSHOT — automatic, code-enforced (v0.2.0):
          Before any in-place write to an EXISTING file, this function snapshots
          the current content (git blob via `git hash-object -w`, pinned under
          refs/lse-snapshots/; or a timestamped copy under .lse-backups/ outside
          git). If no snapshot can be made, the write is REFUSED — the docstring
          confirmation rule above is not self-enforcing, so this gate guarantees
          every overwrite/append is reversible. The recovery command is included
          in the return value. New-file creation is exempt (nothing to recover).

        For files under /etc/ or other privileged paths, use sudo_delegation_block.
        """
        if not self._is_allowed_write(path):
            return (
                f"BLOCKED: '{path}' is outside allowed write paths. "
                "Use sudo_delegation_block for privileged paths."
            )

        resolved = os.path.realpath(os.path.expanduser(path))
        parent = os.path.dirname(resolved)

        # ── SIZE SANITY CHECK (v1.5.12) ───────────────────────────────────────
        if mode == "overwrite" and not force and os.path.isfile(resolved):
            try:
                with open(resolved, "r", errors="replace") as f:
                    existing_lines = len(f.readlines())
                new_lines = max(len(content.splitlines()), 1)
                if existing_lines > 0 and new_lines < existing_lines * 0.25:
                    pct = new_lines * 100 // existing_lines
                    self._log(
                        f"SIZE-CHECK-BLOCKED: {path} existing={existing_lines} new={new_lines}"
                    )
                    return (
                        f"SIZE SANITY CHECK FAILED: '{path}' currently has {existing_lines} lines. "
                        f"New content has {new_lines} lines ({pct}% of current size). "
                        f"Writing this would truncate the file to less than 25% of its current size. "
                        f"Show the user this discrepancy and ask for explicit confirmation. "
                        f"Once the user confirms the truncation is intentional, call write_file "
                        f"again with force=True."
                    )
            except Exception:
                pass  # If comparison fails, proceed — don't block on a check error

        # ── In-place edit safety net (v0.2.0): snapshot-or-refuse ─────────────
        # Before mutating an existing file, capture a recovery point. If none can
        # be made, REFUSE — never edit in place without a way back. New-file
        # creation skips this (nothing to recover).
        snap_note = ""
        if os.path.isfile(resolved):
            ok_snap, snap = self._snapshot_before_write(resolved)
            if not ok_snap:
                self._log(f"WRITE-REFUSED (no snapshot): {path}")
                return (
                    f"BLOCKED: could not create a recovery snapshot of '{path}' "
                    f"before this in-place {mode} ({snap}). Refusing so no original "
                    "is lost. Fix the snapshot location (a writable git repo or "
                    "directory) or back the file up manually, then retry."
                )
            snap_note = f" | recovery snapshot: {snap}"

        self._log(f"WRITE: {path} mode={mode} len={len(content)}")
        try:
            os.makedirs(parent, exist_ok=True)
            file_mode = "a" if mode == "append" else "w"
            with open(resolved, file_mode) as f:
                f.write(content)
            return (
                f"OK: {len(content)} characters written to {path} "
                f"(mode={mode}).{snap_note}"
            )
        except Exception as e:
            return f"ERROR: {str(e)}"

    async def sudo_delegation_block(
        self,
        command: str,
        reason: str,
        expected_output_hint: str = "",
        step_number: int = 0,
        total_steps: int = 0,
        verify_command: str = "",
        __event_emitter__=None,
    ) -> str:
        """
        Use whenever an operation requires sudo or touches a privileged path
        (/etc/, systemctl enable/start/stop/restart, apt install/remove, etc.).
        Produces a formatted block for the user to run manually in their terminal.
        NEVER attempt to run sudo yourself. Always call this function instead.

        ARGS:
          command           — The exact command the user must run.
          reason            — One sentence explaining why this delegation is needed.
          expected_output_hint — (secondary) Free-text hint about success. Prefer verify_command.
          step_number       — Position in a multi-step sequence (1-based). When > 0, block
                              header reads "Step N of Total". Pass 0 for standalone blocks.
          total_steps       — Total delegation blocks in sequence. Required when step_number > 0.
          verify_command    — Explicit follow-up command to confirm success. Surfaced as a
                              labelled "Verify with:" step — not buried in expected_output_hint.

        THINKING PHASE RULE — never call inside a reasoning block:
          This function must only be called in the response phase, after thinking has closed.
          A delegation block inside a <think> block is collapsed in OpenWebUI — the user must
          expand it to find the command. Complete all reasoning first, then call this function.
          Calling sudo_delegation_block during thinking is a protocol violation.
          (v1.7.20 code backstop: the block is ALSO force-surfaced to the UI via an
          event emitter, so it stays visible even if this rule is violated — but the
          rule still stands as best practice for clean turn structure.)

        READ-FIRST RULE — mandatory for any privileged file modification:
          Before calling this function to delegate a write or append to a config
          file (e.g. /etc/sysctl.conf, /etc/hosts, /etc/fstab), first read the
          target file using read_file or execute_command('cat <path>'). This:
            - confirms the setting does not already exist
            - lets you compose the exact command correctly (append vs replace)
            - gives the user context for what will change
          If the file is unreadable (e.g. permission denied), note this in the
          reason field and proceed without the read.
          Skipping the read when the file IS readable is a protocol violation.

        RETURN VALUE SEMANTICS — read this before calling:
          This function returns a DIRECTIVE (v1.7.21), not text to summarize. The
          directive contains the exact markdown — including a ```bash fenced code block —
          that your visible reply must reproduce verbatim, and nothing else.
          The command has NOT run yet; it is now in the user's hands.
          Do NOT call this function again for the same command.
          Do NOT make any further tool calls in this turn after calling this function.
          Calling this function more than once for the same command before the user
          responds is a protocol violation.

        STOP PROTOCOL — mandatory, no exceptions:
          After calling this function, your visible reply MUST be exactly the markdown the
          directive returns — the ```bash fenced command (plus the verify block, if any)
          and the "Paste the full terminal output here to continue." line.
          Output nothing before or after it: no summary, no post-execution hints, no
          follow-up snippets, no further tool calls.
          Your next turn begins only after the user pastes terminal output.
          Anything beyond the required reply before user input is a protocol violation.
        """
        self._log(f"SUDO-DELEGATE: {command}  reason={reason}")

        # Step indicator
        if step_number > 0 and total_steps > 0:
            step_line = f" — step {step_number} of {total_steps}"
        else:
            step_line = ""

        # Verify block (markdown ```bash fence)
        if verify_command:
            verify_line = f"\nVerify with:\n\n```bash\n{verify_command}\n```\n"
        elif expected_output_hint:
            verify_line = f"\n_Expected output: {expected_output_hint}_\n"
        else:
            verify_line = ""

        block = (
            f"⚠️ **SUDO REQUIRED — action delegated to you**{step_line}\n\n"
            f"**Reason:** {reason}\n\n"
            f"Run this in your terminal:\n\n"
            f"```bash\n{command}\n```\n"
            f"{verify_line}\n"
            f"Paste the full terminal output here to continue."
        )
        # v1.7.21: the emitter is best-effort — if the model called this mid-<think>,
        # emitted content can stay collapsed. The authoritative surface is the model's
        # visible post-<think> reply, forced by the directive returned below.
        if __event_emitter__ is not None:
            try:
                await __event_emitter__(
                    {"type": "message", "data": {"content": "\n" + block + "\n"}}
                )
            except Exception as _e:  # noqa: BLE001
                self._log(f"SUDO-DELEGATE emit failed: {_e}")
        directive = (
            "SUDO DELEGATION SURFACED (v1.7.21). The command has NOT run yet — it is now "
            "in the user's hands.\n\n"
            "Your visible reply for THIS turn must be EXACTLY the markdown below and "
            "NOTHING else: no preamble, no summary, no commentary, no further tool calls. "
            "Reproduce it verbatim (keep the ```bash fence) so the user gets a copyable "
            "command:\n\n"
            "----- BEGIN REQUIRED REPLY -----\n"
            f"{block}\n"
            "----- END REQUIRED REPLY -----\n\n"
            "Then STOP and wait for the user to paste the terminal output."
        )
        return directive

    # pfsense_graphql, pfsense_query, _pfsense_verify, _pfsense_cap_response --
    # EXTRACTED to lse/skills/pfsense/tools.py (Phase 2 skill extraction,
    # 2026-07-06). Loaded at runtime via goethe_mcp's `--also
    # tools/pfsense_tools_v1.0.0.py` flag (see start-goethe*.sh /
    # goethe-mcp.service), same pattern as vaultwarden_tools_v1.3.0.py.
    # See lse/skills/pfsense/DESIGN.md for the extraction design + incident
    # writeup.

    def search_web(self, query: str, max_results: int = 5) -> str:
        """
        Search the web via the local SearxNG instance at localhost:8088.

        KB-FIRST RULE — mandatory, no exceptions:
          ALWAYS call search_kb() before calling this function.
          If search_kb() returns results with quality_score >= 0.6, use those directly.
          Only call search_web() when search_kb() returns "KB miss" or quality < 0.6.
          After finding a good result here, call index_to_kb() to store it for next time.
          Skipping search_kb() before search_web() is a protocol violation.

        GATE: Only call this when search_kb() has been called first and returned a miss.

        REQUIRED SEQUENCE — follow this exactly, no exceptions:
          Step 1: Write to the user BEFORE calling this function:
                  "Searching for [topic] because [reason training knowledge is insufficient]."
          Step 2: Call search_web exactly once for this topic.
          Step 3: SEARCH-THEN-FETCH — if the snippet (≤300 chars) is too short to answer
                  the question fully, call fetch_url() on the top result URL to get the
                  full page content before synthesising. Skip fetch if snippet is sufficient.
          Step 4: Synthesise the answer in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Skipping Step 1 is a protocol violation — do not call this function without
        first announcing what you are searching for and why.
        Do not call search_web more than once for the same topic.

        TIME DISCIPLINE (v0.3.1 — ENFORCED IN CODE, not prose; CHRONOS-4 retired
        the old YEAR-INJECTION and 30d/7d staleness rules from this docstring):
          - Standalone years (e.g. "2025") are STRIPPED from the query server-side —
            they filter out current results. Compound ids like CVE-2025-1234 survive.
          - The first search_kb/search_web return of each session carries a [TIME]
            banner (system-clock based; call time_check() for NTP-verified time).
          - KB freshness is enforced by volatility TTLs in search_kb ([EXPIRED] tags
            + rerank demotion) — no manual date arithmetic needed.
          For version lookups of GitHub projects, prefer get_github_release.
        """
        import requests  # noqa: PLC0415

        query = self._strip_years(query)
        _tb = self._consume_time_banner()

        self._log(f"SEARCH: {query} max={max_results}")
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            return _tb + _gate
        try:
            resp = requests.get(
                self.valves.SEARXNG_URL,
                params={"q": query, "format": "json", "categories": "general"},
                headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
                timeout=(5, 10),
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:max_results]
            if not results:
                return _tb + "No results found." + _gate
            lines = []
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("content", "")[:300]
                lines.append(f"**{title}**\n{url}\n{snippet}")
            return _tb + "\n---\n".join(lines) + _gate
        except Exception as e:
            return f"ERROR searching SearxNG: {str(e)}"

    # ── CAMOUFOX REDDIT SCRAPING (v0.3.10) ──────────────────────────────────

    def _camoufox_scrape(self, url: str, wait_s: int = 8) -> str:
        """Use Camoufox on node3090 to scrape a URL. Returns accessibility tree text."""
        import requests  # noqa: PLC0415
        import time  # noqa: PLC0415

        base = self.valves.CAMOUFOX_URL.rstrip("/")
        try:
            # Step 1: Open tab
            resp = requests.post(
                f"{base}/tabs",
                json={"userId": "lse", "sessionKey": "lse", "url": url},
                timeout=15,
            )
            resp.raise_for_status()
            tab_id = resp.json().get("tabId")
            if not tab_id:
                return ""

            # Step 2: Wait for page load
            time.sleep(wait_s)

            # Step 3: Get snapshot
            snap_resp = requests.get(
                f"{base}/tabs/{tab_id}/snapshot",
                params={"userId": "lse", "sessionKey": "lse"},
                timeout=10,
            )
            snap_resp.raise_for_status()
            snapshot = snap_resp.json().get("snapshot", "")

            # Close tab
            try:
                requests.delete(
                    f"{base}/tabs/{tab_id}",
                    params={"userId": "lse", "sessionKey": "lse"},
                    timeout=5,
                )
            except Exception:
                pass  # Non-critical cleanup

            return snapshot
        except Exception as e:
            self._log(f"CAMOUFOX-ERROR: {e}")
            return ""

    def _parse_reddit_posts(self, snapshot: str) -> list:
        """Extract Reddit posts from Camoufox accessibility tree.
        Returns list of dicts: {title, url, votes, comments, author, time}
        
        Actual format from Reddit search:
          heading "Title" [level=2]:
            link "Title" [eN]:
              /url: /r/subreddit/comments/...
          text: ·
          time: Xh ago
          link "Title" [eN]:
            /url: /r/subreddit/comments/...
          text: N votes·N comments
        """
        import re  # noqa: PLC0415

        posts = []
        lines = snapshot.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for heading level=2 (Reddit post titles)
            if 'heading "' in line and '[level=2]' in line:
                m = re.search(r'heading "([^"]+)"', line)
                if m:
                    title = m.group(1)
                    post = {"title": title, "url": "", "votes": "", "comments": "", "author": "", "time": ""}

                    # Look for URL in next 10 lines
                    for j in range(i+1, min(len(lines), i+15)):
                        url_m = re.search(r'/url: (https?://www\.reddit\.com/r/[^\s]+)', lines[j])
                        if url_m:
                            post["url"] = url_m.group(1)
                            break

                    # Look for time in next 15 lines
                    for j in range(i+1, min(len(lines), i+20)):
                        time_m = re.search(r'time: (.+)', lines[j])
                        if time_m:
                            post["time"] = time_m.group(1).strip()
                            break

                    # Look for votes·comments in next 20 lines
                    for j in range(i+1, min(len(lines), i+25)):
                        vc_m = re.search(r'(\d+) votes·(\d+) comments', lines[j])
                        if vc_m:
                            post["votes"] = vc_m.group(1)
                            post["comments"] = vc_m.group(2)
                            break

                    posts.append(post)
            i += 1

        return posts

    def search_reddit(
        self,
        query: str,
        subreddit: str = "",
        max_results: int = 5,
    ) -> str:
        """
        Search Reddit for posts and discussions.

        PRIMARY: Camoufox browser on node3090 — renders JS, bypasses Reddit anti-bot,
        returns structured post data (title, URL, votes, comments, author, time).
        FALLBACK: SearxNG site:reddit.com search if Camoufox is unavailable.

        KB-FIRST RULE — mandatory:
          Call search_kb() before this function. Only call search_reddit() on a KB miss.
          After finding useful results, call index_to_kb() to store for next time.

        REQUIRED SEQUENCE — follow exactly:
          Step 1: Write to user: "Searching Reddit for [topic]."
          Step 2: Call search_reddit() once for this topic.
          Step 3: If snippets are too short, call fetch_url() on the most relevant post URL.
          Step 4: Synthesise in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Args:
            query:       Search terms (e.g. "RTX 3090 thermal paste replacement")
            subreddit:   Optional subreddit without r/ prefix (e.g. "homelab", "hardware")
                         If empty, searches all of reddit.com
            max_results: Number of results to return (default 5)

        Returns:
            Formatted search results string.
        """
        self._log(f"SEARCH-REDDIT: subreddit={subreddit!r} query={query!r}")

        # ── PRIMARY: Camoufox on node3090 ──────────────────────────────────
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search/?q={query}&sort=hot" if subreddit else f"https://www.reddit.com/search/?q={query}&sort=hot"
            snapshot = self._camoufox_scrape(url, wait_s=8)
            if snapshot:
                posts = self._parse_reddit_posts(snapshot)[:max_results]
                if posts:
                    lines = []
                    for p in posts:
                        title = p.get("title", "Untitled")
                        url = p.get("url", "")
                        votes = p.get("votes", "")
                        comments = p.get("comments", "")
                        author = p.get("author", "")
                        time_ = p.get("time", "")
                        snippet = f"{votes} • {comments}" if votes and comments else ""
                        if author:
                            snippet += f" • u/{author}"
                        if time_:
                            snippet += f" • {time_}"
                        snippet = snippet.lstrip(" • ")
                        lines.append(f"**{title}**\n{url}\n{snippet}")
                    return "\n---\n".join(lines) if lines else "No posts found."
        except Exception as e:
            self._log(f"CAMOUFOX-FAIL: {e}")

        # ── FALLBACK: SearxNG ─────────────────────────────────────────────
        self._log("SEARCH-REDDIT: falling back to SearxNG")
        site = f"site:reddit.com/r/{subreddit}" if subreddit else "site:reddit.com"
        full_query = f"{site} {query}"
        return self.search_web(full_query, max_results=max_results)

    # ── CHRONOS — enforced sense of time (v0.3.1, Workstream B) ─────────────

    def _strip_years(self, query: str) -> str:
        """CHRONOS-4 (v0.3.1): year injection defined out of existence — strip
        standalone 19xx/20xx tokens from search queries (they filter out current
        results). Compound tokens survive: CVE-2025-1234, ubuntu-24.04, b2025x."""
        import re as _re  # noqa: PLC0415

        stripped = _re.sub(r"(?<![\w.\-])(?:19|20)\d{2}(?![\w.\-])", " ", query)
        stripped = _re.sub(r"\s{2,}", " ", stripped).strip()
        if stripped and stripped != query.strip():
            self._log(f"SEARCH year-strip: {query!r} -> {stripped!r}")
            return stripped
        return query

    def _sntp_offset(self, server: str, timeout: float = 2.0):
        """SNTP query via stdlib UDP (no ntplib dependency). Returns the offset
        in seconds (server − local midpoint) or None on any failure. Read-only:
        never adjusts the clock."""
        import socket  # noqa: PLC0415
        import struct  # noqa: PLC0415
        import time as _t  # noqa: PLC0415

        NTP_DELTA = 2208988800  # seconds between 1900-01-01 and 1970-01-01
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            t0 = _t.time()
            sock.sendto(b"\x1b" + 47 * b"\0", (server, 123))
            data, _ = sock.recvfrom(64)
            t3 = _t.time()
            if len(data) < 48:
                return None
            secs, frac = struct.unpack("!II", data[40:48])
            server_time = secs - NTP_DELTA + frac / 2**32
            return server_time - (t0 + t3) / 2
        except Exception:
            return None
        finally:
            sock.close()

    def _tls_date_offset(self, url: str = ""):
        """Offset (seconds) between the HTTPS Date response header of a known
        endpoint and the local clock. Coarse (1s header resolution) — used only
        as a third-source sanity check on the unauthenticated NTP answers
        (Shostack: NTP is spoofable; TLS date rides an authenticated channel).
        Tries two endpoints — without a TLS answer the clock-fix suggestion
        gate can never open, so availability matters."""
        import email.utils  # noqa: PLC0415
        import time as _t  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        urls = (url,) if url else (
            "https://www.cloudflare.com",
            "https://www.google.com",
        )
        for u in urls:
            try:
                req = urllib.request.Request(u, method="HEAD")
                t0 = _t.time()
                with urllib.request.urlopen(req, timeout=4) as r:
                    date_hdr = r.headers.get("Date")
                t3 = _t.time()
                if date_hdr:
                    server = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                    return server - (t0 + t3) / 2
            except Exception:
                continue
        return None

    def _time_banner(self, verified: bool = False) -> str:
        """The [TIME] banner (CHRONOS-2). Injected server-side into the first
        search_kb/search_web return of each session and into every time_check()."""
        now = datetime.now().astimezone()
        cutoff = (self.valves.MODEL_PRETRAIN_CUTOFF or "").strip()
        if cutoff:
            try:
                cy, cm = int(cutoff[:4]), int(cutoff[5:7])
                gap = (now.year - cy) * 12 + (now.month - cm)
                cut_txt = f"model cutoff={cutoff} | gap≈{gap} months"
            except Exception:
                cut_txt = f"model cutoff={cutoff!r} (unparseable — use YYYY-MM)"
        else:
            cut_txt = "model cutoff UNSET (set MODEL_PRETRAIN_CUTOFF valve)"
        src = "NTP-verified" if verified else "system clock — run time_check() to NTP-verify"
        return (
            f"[TIME] now={now:%Y-%m-%d} ({src}) | {cut_txt} — any version/price/"
            "CVE/firmware claim from model memory is presumed stale; web-verify "
            "before asserting."
        )

    _DREAM_DIGEST_MAX_CHARS = 200

    def _dream_banner(self) -> str:
        """The [DREAM] banner (TRAUM Thread 3, Prompt 3.5, v0.4.0-a). Reads
        dream_digest.py's own output (DREAM_DIGEST_PATH valve) and surfaces
        just the digest date + pending human-gate count, with a pointer to
        the full file for detail — the LSE should never need to know
        tools/dream_digest.py exists to learn a digest is waiting.

        Missing valve, missing/unreadable file, or a digest whose header we
        can't parse are all legitimate null results (no dream cycle has run
        yet, DREAM_DIGEST_PATH is unset, etc.) — this degrades to "" rather
        than raising or emitting a confusing partial line, same non-fatal
        discipline as dream_digest.py's own gather_* steps.
        """
        path = (self.valves.DREAM_DIGEST_PATH or "").strip()
        if not path:
            return ""
        try:
            with open(path, "rt", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return ""
        import re as _re  # noqa: PLC0415

        m_date = _re.search(r"generated (\d{4}-\d{2}-\d{2})", text)
        m_pending = _re.search(r"## Pending human-gate \((\d+)\)", text)
        if not m_date or not m_pending:
            return ""
        line = (
            f"[DREAM] digest={m_date.group(1)} | pending-gate={m_pending.group(1)} "
            f"| read {path} for details"
        )
        return line[: self._DREAM_DIGEST_MAX_CHARS]

    def _consume_time_banner(self) -> str:
        """Return the [TIME] banner exactly once per session (server-side
        enforcement — compliance must not depend on the model reading
        docstrings). TRAUM Thread 3 (v0.4.0-a): also appends the [DREAM]
        banner (Prompt 3.5) on this same first-call gate — one server-side
        injection point covers both time-anchoring and dream-digest
        awareness before the session's first real search_kb result.
        Do NOT add a second, separate once-per-session flag for [DREAM] —
        reusing _time_banner_emitted is what guarantees the two banners can
        never desync (one firing without the other)."""
        if self._time_banner_emitted:
            return ""
        self._time_banner_emitted = True
        banner = self._time_banner(verified=False)
        dream_line = self._dream_banner()
        if dream_line:
            banner += "\n" + dream_line
        return banner + "\n\n"

    def time_check(self) -> str:
        """
        Verify the system clock against external time sources and anchor the
        session against the model's pretraining cutoff (CHRONOS-1/2, v0.3.1).

        WHEN TO CALL:
          - At the start of any session involving dates, versions, CVEs, firmware,
            prices, or release timelines.
          - Whenever a KB hit is tagged [EXPIRED] or a claim depends on "now".
          - When the user asks "what time/date is it" or doubts the clock.

        WHAT IT DOES (report-only — NEVER adjusts the clock):
          1. Queries 2 NTP servers (pool.ntp.org, time.cloudflare.com; 2s timeout,
             stdlib SNTP) for clock offset.
          2. Cross-checks against the TLS Date header of a known HTTPS endpoint —
             NTP is unauthenticated/spoofable; a fix is only ever SUGGESTED when
             both NTP servers agree AND the TLS date corroborates.
          3. Compares verified now against MODEL_PRETRAIN_CUTOFF and returns the
             [TIME] banner: everything the model "remembers" after that gap is
             presumed stale.
          Offset >2s → discrepancy report with the suggested fix command
          (timedatectl/chronyc) for the HUMAN to run, and the event is recorded
          to lse-errors. Graceful degrade: no NTP reachable → system clock + WARN.

        FIX EXECUTION PROHIBITION — mandatory, no exceptions:
          NEVER execute the suggested clock fix yourself — not via
          execute_command, not by raising an unrequested sudo_delegation_block.
          Surface the discrepancy; the human decides. Only produce a delegation
          block if the user explicitly asks to fix the clock. Executing or
          auto-delegating a clock change unasked is a protocol violation.

        GATE: call at most once per session unless the user asks again — results
        do not change mid-session.
        """
        self._log("TIME-CHECK")
        try:
            servers = ("pool.ntp.org", "time.cloudflare.com")
            offsets = {s: self._sntp_offset(s) for s in servers}
            good = {s: o for s, o in offsets.items() if o is not None}
            tls_off = self._tls_date_offset()
            now = datetime.now().astimezone()
            lines = [f"TIME CHECK — system clock: {now:%Y-%m-%d %H:%M:%S %z}"]
            for s in servers:
                o = offsets[s]
                lines.append(
                    f"  NTP {s}: " + (f"offset {o * 1000:+.0f} ms" if o is not None
                                      else "UNREACHABLE")
                )
            lines.append(
                "  TLS date (cloudflare.com): "
                + (f"offset {tls_off:+.1f} s" if tls_off is not None else "unavailable")
            )
            verified = False
            if len(good) == 2:
                o1, o2 = good.values()
                if abs(o1 - o2) <= 1.0:
                    verified = True
                    mean = (o1 + o2) / 2
                    if abs(mean) > 2.0:
                        tls_agrees = tls_off is not None and abs(tls_off - mean) <= 5.0
                        lines.append(
                            f"  ⚠️ CLOCK DISCREPANCY: system clock is {mean:+.1f}s vs "
                            "NTP consensus"
                            + ("" if tls_agrees else " (TLS date does NOT corroborate "
                               "— treat the NTP answer itself as suspect, no fix "
                               "suggested)")
                        )
                        if tls_agrees:
                            lines.append(
                                "  SUGGESTED FIX (human-run, never automatic): "
                                "sudo timedatectl set-ntp true   # or: chronyc makestep"
                            )
                            self.record_error(
                                error_text=f"system clock offset {mean:+.1f}s vs NTP consensus",
                                context="time_check() CHRONOS-1 discrepancy detection",
                                resolution="suggested timedatectl set-ntp true / chronyc makestep (human-run)",
                            )
                    else:
                        lines.append("  ✅ clock agrees with NTP consensus (<2s)")
                else:
                    lines.append(
                        "  ⚠️ NTP servers DISAGREE with each other (>1s) — "
                        "unauthenticated NTP cannot be trusted here; using system clock"
                    )
            elif len(good) == 1:
                s, o = next(iter(good.items()))
                verified = tls_off is not None and abs(tls_off - o) <= 5.0
                lines.append(
                    f"  single NTP source ({s}) "
                    + ("corroborated by TLS date" if verified
                       else "NOT corroborated — treating as unverified")
                )
            else:
                lines.append(
                    "  WARN: no NTP source reachable — degrading to system clock"
                )
            self._time_banner_emitted = True  # this return carries the banner
            lines.append("")
            lines.append(self._time_banner(verified=verified))
            # TRAUM Thread 3 close (v0.4.0-a, 2026-07-12): time_check() sets the
            # SAME _time_banner_emitted flag _consume_time_banner() gates on, so
            # a session that calls time_check() before its first search_kb was
            # silently losing the [DREAM] banner forever (the flag trips here,
            # _consume_time_banner() later sees it already True and returns "").
            # This is exactly the desync _consume_time_banner()'s own docstring
            # says reusing the flag is supposed to prevent — the assumption that
            # _consume_time_banner() is the ONLY place that sets the flag was
            # wrong; time_check() is a second one and the system prompt's own
            # TIME DISCIPLINE section tells the model to call it first for any
            # "date-sensitive work", which a TRAUM digest-review session is.
            # Fix: time_check() must also append the [DREAM] line on the same
            # gate it already owns, so whichever tool fires first, both banners
            # still always appear together — restoring the "can never desync"
            # guarantee for real instead of only for the search_kb-first case.
            dream_line = self._dream_banner()
            if dream_line:
                lines.append(dream_line)
            return "\n".join(lines)
        except Exception as e:
            self._log(f"TIME-CHECK ERROR: {e}")
            return f"time_check failed: {e}\n{self._time_banner(verified=False)}"

    # ── PROVE-IT — user-callable tests as evidence (v0.3.6, Workstream C) ────

    def run_tests(self, scope: str = "all") -> str:
        """
        Run the LSE's own test surface and return the RAW output as evidence
        (PROVE-1, v0.3.6). When the user says "prove it" / "run the tests" /
        "is the harness green", THIS is the answer — never prose.

        SCOPES (hardcoded allowlist — this is an exec surface, so the model
        supplies ONLY the scope name; commands, paths and args are fixed in
        code, same pattern as the sudo allowlist):
          kb        — ES index existence + doc-count sanity (read-only probes)
          retrieval — rag/eval_retrieval.py --self-test (no ES/Ollama needed)
          rules     — eval_goethe_rules.py — an LLM-BEHAVIOR eval: drives 9
                      scenarios through the live llama-server. Minutes of GPU
                      time. EXPLICIT scope only, never part of 'all'; do not
                      run while the user is mid-conversation with the model.
          harness   — pytest tests/ (contract suites) AND pytest scripts/
                      (legacy harness; failures there are FINDINGS, report them)
          all       — kb + retrieval + pytest tests/ (rules and scripts/ run
                      only when explicitly named; 'all' takes ~1-2 minutes)

        EVIDENCE RULE — mandatory:
          The verbatim output below each section IS the evidence. Paste the
          relevant lines into evidence= fields (skill_outcome, record_outcome,
          plan_step_done) — do NOT summarise test output into a claim.
          A FAIL result must be reported to the user verbatim, never softened.

        GATE: at most once per scope per session unless code changed in
        between. Do NOT run to "double-check" a scope that just passed.

        Args:
            scope: one of kb | retrieval | rules | harness | all.
        """
        import subprocess as _sp  # noqa: PLC0415
        import sys as _sys  # noqa: PLC0415

        self._log(f"RUN-TESTS: scope={scope}")
        scopes = ("kb", "retrieval", "rules", "harness", "all")
        if scope not in scopes:
            return f"run_tests: unknown scope '{scope}'. Valid: {', '.join(scopes)}."
        repo = self.valves.REPO_DIR.rstrip("/")
        py = _sys.executable
        sections: list = []

        def _kb_scope() -> tuple:
            try:
                es = self._es()
                lines = []
                ok = True
                for idx in ("lse-kb", "lse-errors", "lse-skills",
                            "lse-rfc-kb", "lse-search-cache"):
                    try:
                        if es.indices.exists(index=idx):
                            c = es.count(index=idx)["count"]
                            lines.append(f"  {idx}: EXISTS, {c} docs")
                            if idx == "lse-kb" and c == 0:
                                ok = False
                                lines.append("    ^ FAIL: lse-kb is EMPTY")
                        else:
                            lines.append(f"  {idx}: MISSING")
                            if idx in ("lse-kb", "lse-errors"):
                                ok = False
                    except Exception as exc:
                        lines.append(f"  {idx}: ERROR {exc}")
                        ok = False
                return ("PASS" if ok else "FAIL"), "\n".join(lines)
            except Exception as exc:
                return "FAIL", f"  ES unreachable: {exc}"

        def _cmd_scope(label, rel_target, argv, timeout_s) -> tuple:
            target = os.path.join(repo, rel_target)
            if not os.path.exists(target):
                return "SKIP", f"  {rel_target} not present on this node ({repo})"
            try:
                r = _sp.run(argv, cwd=repo, capture_output=True, text=True,
                            timeout=timeout_s)
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                if len(out) > 1200:
                    out = out[:300] + f"\n  … [{len(out) - 1500} chars omitted] …\n" + out[-1200:]
                status = "PASS" if r.returncode == 0 else f"FAIL (exit {r.returncode})"
                return status, out or "(no output)"
            except _sp.TimeoutExpired:
                return "FAIL", f"  TIMEOUT after {timeout_s}s"
            except Exception as exc:
                return "FAIL", f"  {exc}"

        want = (scope,) if scope != "all" else ("kb", "retrieval", "harness")
        for sc in want:
            if sc == "kb":
                st, body = _kb_scope()
                sections.append((sc, st, body))
            elif sc == "retrieval":
                st, body = _cmd_scope(
                    sc, "rag/eval_retrieval.py",
                    [py, "rag/eval_retrieval.py", "--self-test"], 90)
                sections.append((sc, st, body))
            elif sc == "rules":
                st, body = _cmd_scope(
                    sc, "eval_goethe_rules.py",
                    [py, "eval_goethe_rules.py"], 300)
                sections.append((sc, st, body))
            elif sc == "harness":
                st, body = _cmd_scope(
                    "harness/tests", "tests",
                    [py, "-m", "pytest", "tests/", "-q", "--tb=line",
                     "-p", "no:cacheprovider"], 200)
                sections.append(("harness/tests", st, body))
                if scope == "harness":  # legacy scripts only on explicit ask
                    st2, body2 = _cmd_scope(
                        "harness/scripts", "scripts",
                        [py, "-m", "pytest", "scripts/", "-q", "--tb=line",
                         "-p", "no:cacheprovider"], 150)
                    sections.append(("harness/scripts", st2, body2))
        overall = "PASS"
        if any(st.startswith("FAIL") for _, st, _ in sections):
            overall = "FAIL"
        elif all(st == "SKIP" for _, st, _ in sections):
            overall = "SKIP"
        head = " | ".join(f"{name}={st}" for name, st, _ in sections)
        report = [f"RUN-TESTS [{overall}] — {head}", ""]
        for name, st, body in sections:
            report.append(f"── {name}: {st} ──")
            report.append(body)
            report.append("")
        return "\n".join(report)[:3800]

    # Read-only argv allowlist for assert_state. Threat note (Shostack): this
    # is an exec surface — first token must match, mutating verbs and shell
    # metacharacters are rejected, and execution is argv-only (no shell).
    _ASSERT_ALLOW = {
        "df", "ss", "sha256sum", "dig", "pgrep", "stat", "ls", "wc",
        "free", "uptime", "curl", "systemctl", "ping", "ip", "nvidia-smi",
    }
    _ASSERT_CURL_DENY = {
        "-x", "--request", "-d", "--data", "--data-raw", "--data-binary",
        "--data-urlencode", "-f", "--form", "-t", "--upload-file",
        "-o", "--output", "-O", "--remote-name", "-K", "--config",
    }

    def assert_state(self, check_command: str, expected_regex: str) -> str:
        """
        Run ONE read-only check command and assert a regex against its output —
        turning "I claim it worked" into "I ran the check and the output
        matched" (PROVE-3, v0.3.6). This is the PREFERRED producer for
        evidence= fields (plan_step_done, skill_outcome, record_outcome).

        ALLOWLIST — read-only commands ONLY (argv-exec, no shell):
          df, ss, sha256sum, dig, pgrep, stat, ls, wc, free, uptime, ip (show
          subcommands), nvidia-smi, curl (GET only — no -X/-d/-o/upload),
          systemctl (is-active/is-enabled/is-failed/show only), ping (count
          capped). Anything else — including pipes, redirects, ';', '&&' — is
          REJECTED. This tool NEVER mutates state; state changes go through
          execute_command/ssh_run with their own gates. Trying to sneak a
          mutating command through here is a protocol violation.

        GOOD: assert_state("systemctl is-active ollama", "^active")
              ← one check, concrete expectation, output is the evidence
        GOOD: assert_state("curl -s http://127.0.0.1:9700/", "401")
              ← tokenless gateway probe expecting the auth wall
        BAD:  assert_state("systemctl restart ollama", "active")
              ← mutating verb. REJECTED — this tool proves, it never fixes.
        BAD:  assert_state("df -h | grep sda", "9[0-9]%")
              ← pipe. REJECTED — put the filter in the regex instead.

        AFTER THE RESULT:
          PASS ✅ → paste the returned block as evidence where needed.
          FAIL ❌ → the claim is NOT established. Report the mismatch verbatim;
          do NOT retry with a looser regex just to make it pass — weakening an
          assertion to green is a protocol violation.

        Args:
            check_command:  One allowlisted command as a plain string
                            (shlex-parsed, executed without a shell).
            expected_regex: Python regex searched (MULTILINE) in stdout+stderr.
        """
        import re as _re  # noqa: PLC0415
        import shlex  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        self._log(f"ASSERT-STATE: {check_command[:100]!r} ~ /{expected_regex[:60]}/")
        try:
            argv = shlex.split(check_command)
        except ValueError as exc:
            return f"assert_state rejected: unparseable command ({exc})."
        if not argv:
            return "assert_state rejected: empty command."
        bad_tokens = [t for t in argv if any(c in t for c in ";|&`$><\n")]
        if bad_tokens:
            return (
                f"assert_state rejected: shell metacharacters in {bad_tokens!r} — "
                "no pipes/redirects/chaining. Put filtering in expected_regex."
            )
        prog = os.path.basename(argv[0])
        if prog not in self._ASSERT_ALLOW:
            return (
                f"assert_state rejected: '{prog}' is not in the read-only "
                f"allowlist ({', '.join(sorted(self._ASSERT_ALLOW))}). "
                "Use execute_command for anything else."
            )
        if prog == "systemctl":
            verb = argv[1] if len(argv) > 1 else ""
            if verb not in ("is-active", "is-enabled", "is-failed", "show", "status"):
                return (
                    f"assert_state rejected: systemctl verb '{verb}' — only "
                    "is-active/is-enabled/is-failed/show/status (read-only)."
                )
            if verb == "status" and "--no-pager" not in argv:
                argv.insert(2, "--no-pager")
        if prog == "curl":
            lowered = {t.lower() for t in argv[1:]}
            hit = lowered & self._ASSERT_CURL_DENY
            if hit:
                return (
                    f"assert_state rejected: curl flag(s) {sorted(hit)} — "
                    "GET-only probes here; writes go through execute_command."
                )
            if "-s" not in argv:
                argv.insert(1, "-s")
        if prog == "ip":
            sub = argv[1] if len(argv) > 1 else ""
            if sub not in ("addr", "address", "route", "link", "neigh", "-br"):
                return "assert_state rejected: only 'ip addr/route/link/neigh' reads."
            if any(t in ("add", "del", "set", "flush", "replace") for t in argv):
                return "assert_state rejected: mutating ip subcommand."
        if prog == "ping" and "-c" not in argv:
            argv[1:1] = ["-c", "3"]
        try:
            r = _sp.run(argv, capture_output=True, text=True, timeout=20)
            out = ((r.stdout or "") + (r.stderr or "")).strip() or "(no output)"
        except _sp.TimeoutExpired:
            return f"ASSERT FAIL ❌ — '{check_command}' timed out after 20s."
        except FileNotFoundError:
            return f"ASSERT FAIL ❌ — '{prog}' not found on this host."
        except Exception as exc:
            return f"assert_state error: {exc}"
        out_cap = out[:1500]
        try:
            m = _re.search(expected_regex, out, _re.MULTILINE)
        except _re.error as exc:
            return f"assert_state rejected: invalid regex /{expected_regex}/ ({exc})."
        if m:
            return (
                f"ASSERT PASS ✅ — /{expected_regex}/ matched {m.group(0)!r} "
                f"(exit {r.returncode})\n--- {check_command} ---\n{out_cap}"
            )
        return (
            f"ASSERT FAIL ❌ — /{expected_regex}/ NOT found in output "
            f"(exit {r.returncode})\n--- {check_command} ---\n{out_cap}"
        )

    # ------------------------------------------------------------------
    # Browser-rendering fallback helpers (v1.5.29)
    # Used by fetch_url when a reddit.com URL returns empty content
    # or an HTTP error (reddit blocks plain requests with 429/403).
    # ------------------------------------------------------------------

    def _fetch_via_browser(self, url: str, firecrawl_base: str, max_chars: int) -> str:
        """
        POST url to Firecrawl's /v1/scrape endpoint (JS-rendering stack).
        Returns extracted markdown text (capped at max_chars) or "" on any failure.

        firecrawl_base examples:
          "http://localhost:3002"            — node3090 local
          "http://node3090.home.arpa:3002"   — from LUCIFER over LAN
        """
        import requests as _req  # noqa: PLC0415

        try:
            resp = _req.post(
                f"{firecrawl_base}/v1/scrape",
                json={"url": url, "formats": ["markdown"]},
                timeout=45,
            )
            if resp.ok:
                data = resp.json()
                text = ((data.get("data") or {}).get("markdown") or "").strip()
                if text:
                    self._log(
                        f"FETCH-BROWSER: {len(text)} chars from {firecrawl_base}"
                    )
                    return text[:max_chars]
                self._log(f"FETCH-BROWSER: empty markdown from {firecrawl_base}")
            else:
                self._log(
                    f"FETCH-BROWSER: HTTP {resp.status_code} from {firecrawl_base}"
                )
        except Exception as exc:
            self._log(f"FETCH-BROWSER: error ({firecrawl_base}): {exc}")
        return ""

    def _reddit_browser_fallback(self, url: str, max_chars: int) -> str:
        """
        Route a reddit.com URL to the JS-rendering stack when plain requests
        returns empty content or errors.

        Routing logic (hostname-aware):
          node3090 → local Firecrawl at localhost:3002
          LUCIFER / other → ping node3090.home.arpa; if up, use Firecrawl
                            at node3090:3002 over LAN; if down, return "".

        Returns extracted text or "" (caller must handle the empty case).
        """
        import socket as _socket  # noqa: PLC0415
        import subprocess as _sp  # noqa: PLC0415

        hostname = _socket.gethostname().lower()

        if "node3090" in hostname:
            self._log("REDDIT-FALLBACK: node3090 — local Firecrawl")
            return self._fetch_via_browser(url, "http://localhost:3002", max_chars)

        # LUCIFER or other node — check node3090 reachability first.
        self._log("REDDIT-FALLBACK: pinging node3090.home.arpa")
        ping = _sp.run(
            ["ping", "-c", "1", "-W", "2", "node3090.home.arpa"],
            capture_output=True,
        )
        if ping.returncode != 0:
            self._log("REDDIT-FALLBACK: node3090 offline — no browser rendering")
            return ""

        self._log("REDDIT-FALLBACK: node3090 up — using remote Firecrawl")
        return self._fetch_via_browser(
            url, "http://node3090.home.arpa:3002", max_chars
        )

    def _extract_text_from_html(self, html: str, max_chars: int) -> str:
        """Extract plain text from HTML, stripping tags and control chars."""
        from html.parser import HTMLParser
        import re as _re  # noqa: PLC0415

        def _sanitize(s):
            # Strip control chars so stray binary bytes are removed
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)

        import re as _re

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._text = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "head"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip and data.strip():
                    self._text.append(data.strip())

            def get_text(self):
                return " ".join(self._text)

        import re as _re  # noqa: PLC0415

        def _sanitize(s):
            # Strip control chars (except \n\t) so a stray binary byte can never
            # derail the OWUI markdown/HTML renderer downstream (v1.7.7).
            return _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)

        parser = _TextExtractor()
        parser.feed(html)
        return _sanitize(parser.get_text())[:max_chars]

    def fetch_url(self, url: str, max_chars: int = 20000) -> str:
        """
        Fetch the full text content of a URL. Use as Step 3 of the SEARCH-THEN-FETCH
        protocol when search_web returns a snippet too short to answer the question.

        WHEN TO CALL:
          After search_web, if the snippet (≤300 chars) is truncated or insufficient.
          Call on the top result URL only — do not fetch multiple URLs per search.

        WHEN NOT TO CALL:
          If the search_web snippet already answers the question fully.
          Do not use as a substitute for search_web — always search first.

        UNVERIFIED-URL RULE — mandatory:
          Only fetch URLs received from a tool result (search_web, search_kb, KB
          docs, user message). NEVER construct a URL or hostname from memory; if
          a guessed hostname fails DNS, that is evidence the hostname is wrong —
          not that the network is broken. Presenting a self-generated URL to the
          user is a protocol violation.

        Returns plain text with HTML tags stripped, capped at max_chars characters.

        REDDIT BROWSER FALLBACK (v1.5.29):
          When the URL contains "reddit.com" and the plain requests fetch returns
          empty content OR raises an HTTP error (reddit blocks bots with 429/403),
          fetch_url automatically routes to _reddit_browser_fallback():
            node3090: local Firecrawl at localhost:3002
            LUCIFER:  pings node3090, then uses Firecrawl at node3090:3002 over LAN
          Successful browser-rendered results are prefixed "[browser-rendered]"
          and cached normally. If the fallback also fails, the original
          "No text content extracted" or error message is returned.
          Use search_reddit() as a further alternative when both paths fail.
        """
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            self._log(f"FETCH BLOCKED (budget): {url}")
            return _gate
        import requests  # noqa: PLC0415
        from html.parser import HTMLParser

        self._log(f"FETCH: {url}")
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                },
            )
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "").lower()
            head = resp.content[:5]

            # CONTENT-TYPE GUARD (v1.7.7): never feed binary to the HTML parser.
            # A PDF/image/octet-stream body decoded as text is raw FlateDecode
            # garbage — it pollutes context AND breaks OWUI <details> rendering.
            is_pdf = "application/pdf" in ctype or head == b"%PDF-"
            if is_pdf:
                text = self._extract_pdf_text(resp.content)
                if text.strip():
                    import re as _re  # noqa: PLC0415
                    out = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", " ".join(text.split()))[:max_chars]
                    self._fetch_cache[url] = {
                        "text": out,
                        "ts": datetime.now().timestamp(),
                    }
                    mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    return ("[PDF text-extracted] " + out + mandate) + _gate
                return (
                    f"PDF at {url} ({len(resp.content)} bytes) — text could not be "
                    "extracted here (no pdfminer/pypdf). Binary NOT returned. "
                    "Find an HTML source for the same content, or ask the operator "
                    "to run pdftotext. Do NOT retry this URL."
                ) + _gate
            if ctype and not (
                "text/html" in ctype
                or "text/plain" in ctype
                or "xml" in ctype
                or "json" in ctype
            ):
                return (
                    f"Non-text content at {url} (Content-Type: {ctype or 'unknown'}). "
                    "Binary NOT returned to avoid context pollution. Use an HTML "
                    "source. Do NOT retry this URL."
                ) + _gate

            text = self._extract_text_from_html(resp.text, max_chars)
            if text:
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                mandate = (
                    f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                    'claims="<fact1>, <fact2>") before asserting any version number, '
                    "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                )
                return (text + mandate) + _gate
            # Empty extract — try browser rendering for reddit URLs (v1.5.29)
            if "reddit.com" in url.lower():
                self._log(f"FETCH: empty for reddit URL — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return "No text content extracted." + _gate
        except Exception as e:
            # HTTP error (e.g. 403/429) — also try browser fallback for reddit (v1.5.29)
            if "reddit.com" in url.lower():
                self._log(f"FETCH: exception for reddit URL ({e}) — trying browser fallback")
                _br = self._reddit_browser_fallback(url, max_chars)
                if _br:
                    _br_mandate = (
                        f'\n\n[SOURCE-VERIFY MANDATE] Call verify_source_claims(url="{url}", '
                        'claims="<fact1>, <fact2>") before asserting any version number, '
                        "date, or specific value from this source. NOT_FOUND = report as UNVERIFIED."
                    )
                    self._fetch_cache[url] = {
                        "text": _br,
                        "ts": datetime.now().timestamp(),
                    }
                    return ("[browser-rendered] " + _br + _br_mandate) + _gate
            return f"ERROR fetching {url}: {e}"

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF. Tries pdfminer, falls back to pypdf."""
        try:
            import io  # noqa: PLC0415
            from pdfminer.high_level import extract_text as _pe  # noqa: PLC0415
            return _pe(io.BytesIO(pdf_bytes)) or ""
        except Exception:
            try:
                import io  # noqa: PLC0415
                from pypdf import PdfReader as _PR  # noqa: PLC0415
                rdr = _PR(io.BytesIO(pdf_bytes))
                return "\n".join(
                    (p.extract_text() or "") for p in rdr.pages)
            except Exception:
                return ""

    def verify_source_claims(self, url: str, claims: str) -> str:
        """
        Re-fetch a source URL and check whether specific factual claims appear in
        it verbatim. Call BEFORE asserting any version number, date, release name,
        or config value derived from fetch_url. Returns FOUND / PARTIAL / NOT_FOUND
        per claim with verbatim ±300-char excerpts.

        MANDATORY after every fetch_url — do NOT skip:
          The fabrication#5 root cause was synthesis-overwrite: the model had the
          correct source in context yet emitted phantom version strings in the final
          answer. Prompt fences do not hold at synthesis (P25 proven). This function
          re-fetches the source in code and returns what is ACTUALLY there — the
          model cannot fabricate the return value.

          NOT_FOUND: the claim text is absent from the source. Label it UNVERIFIED.
            Do NOT retry or guess — report it as unverified.
          PARTIAL:   a specific token from your claim is present but the full claim
            string is absent. The excerpt shows what the source ACTUALLY says.
            Read it — it likely shows the correct value (e.g. "07.23.4" when you
            claimed "07.23.5").
          FOUND:     the claim appears verbatim. The excerpt is the confirmation.

          This call does NOT count against the search budget.

        Args:
            url:    The source URL — must be a URL previously returned by a tool
                    result (UNVERIFIED-URL RULE: never construct from memory).
            claims: Comma-separated factual claims to check, e.g.:
                    "firmware 07.23.5, released 2026-05-30, version 07.22.4 Stable"
                    Each comma-delimited segment is checked independently.

        Returns one FOUND/PARTIAL/NOT_FOUND line per claim with verbatim excerpt.
        """
        import re as _re  # noqa: PLC0415

        claim_list = [c.strip() for c in claims.split(",") if c.strip()]
        if not claim_list:
            return 'ERROR: no claims provided. Pass comma-separated facts to verify, e.g. claims="07.23.5, released 2026-05-30"'

        # ── Use cache or re-fetch ────────────────────────────────────────────
        ttl = max(0, int(getattr(self.valves, "SOURCE_VERIFY_CACHE_TTL", 300)))
        cached = self._fetch_cache.get(url)
        if cached and ttl > 0 and (datetime.now().timestamp() - cached["ts"]) < ttl:
            text = cached["text"]
            source_note = "(cached)"
        else:
            import requests as _req  # noqa: PLC0415
            self._log(f"VERIFY-FETCH: {url}")
            try:
                resp = _req.get(
                    url,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
                )
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").lower()
                is_pdf = "application/pdf" in ctype or resp.content[:5] == b"%PDF-"
                if is_pdf:
                    text = self._extract_pdf_text(resp.content)
                else:
                    text = self._extract_text_from_html(resp.text, 80000)
                text = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:80000]
                self._fetch_cache[url] = {
                    "text": text,
                    "ts": datetime.now().timestamp(),
                }
                source_note = "(re-fetched)"
            except Exception as e:
                return (
                    f"VERIFY ERROR: could not fetch {url}: {e}\n"
                    "All claims remain UNVERIFIED — label them as such in your response."
                )

        text_l = text.lower()
        WINDOW = 300

        # ── Check each claim ─────────────────────────────────────────────────
        results = [f"Source: {url} {source_note}"]
        for claim in claim_list:
            claim_l = claim.lower()

            # Exact substring match
            idx = text_l.find(claim_l)
            if idx >= 0:
                start = max(0, idx - WINDOW)
                end = min(len(text), idx + len(claim) + WINDOW)
                excerpt = text[start:end].strip().replace("\n", " ")
                results.append(
                    f"  FOUND    | {claim!r}\n" f"           | excerpt: ...{excerpt}..."
                )
                continue

            # Token-level: version strings first, then long words
            ver_tokens = _re.findall(r"\b\d{1,3}[\.\d]{2,}\b", claim)
            word_tokens = _re.findall(r"\b[a-z0-9_-]{5,}\b", claim_l)
            tokens_to_try = (ver_tokens or []) + word_tokens

            found_tok = None
            for tok in tokens_to_try:
                tidx = text_l.find(tok.lower())
                if tidx >= 0 and found_tok is None:
                    start = max(0, tidx - WINDOW)
                    end = min(len(text), tidx + len(tok) + WINDOW)
                    found_tok = (tok, text[start:end].strip().replace("\n", " "))

            if found_tok:
                tok, exc = found_tok
                results.append(
                    f"  PARTIAL  | {claim!r}\n"
                    f"           | token {tok!r} found but full claim absent.\n"
                    f"           | Read excerpt for what source ACTUALLY says:\n"
                    f"           | ...{exc}..."
                )
            else:
                src_vers = _re.findall(r"\b\d{2}\.\d{2}[\.\d]*\b", text)
                ver_ctx = (
                    ", ".join(dict.fromkeys(src_vers[:8]))
                    if src_vers
                    else "(none found)"
                )
                results.append(
                    f"  NOT_FOUND| {claim!r}\n"
                    f"           | source version strings: {ver_ctx}\n"
                    f"           | → label this claim UNVERIFIED in your response"
                )

        return "\n".join(results)

    def get_github_release(self, repo: str) -> str:
        """
        Return the latest release tag, name, and publish date for a public GitHub repository.
        Use this for version lookups — it is faster and more reliable than search_web
        and avoids date-injection problems.

        WHEN TO USE:
          - Checking the latest llama.cpp release:   get_github_release("ggerganov/llama.cpp")
          - Checking the latest open-webui release:  get_github_release("open-webui/open-webui")
          - Any public GitHub project where you need the current version number.

        WHEN NOT TO USE:
          - Projects not hosted on GitHub (use search_web instead).
          - Package versions managed by apt/pip (use execute_command with apt-cache or pip index).

        Do NOT append a year or any date to the repo string.
        The repo parameter must be in "owner/name" format, e.g. "ggerganov/llama.cpp".
        """
        import requests  # noqa: PLC0415

        repo = repo.strip().strip("/")
        if "/" not in repo or len(repo.split("/")) != 2:
            return f"ERROR: Invalid repo format '{repo}'. Expected 'owner/name'."

        url = f"https://api.github.com/repos/{repo}/releases/latest"
        self._log(f"GITHUB-RELEASE: {repo}")
        try:
            resp = requests.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            if resp.status_code == 404:
                return f"No releases found for '{repo}' (repo may not exist or have no releases)."
            resp.raise_for_status()
            data = resp.json()
            tag = data.get("tag_name", "unknown")
            name = data.get("name", tag)
            published = data.get("published_at", "unknown date")[:10]  # YYYY-MM-DD
            prerelease = data.get("prerelease", False)
            draft = data.get("draft", False)
            html_url = data.get("html_url", "")

            flags = []
            if prerelease:
                flags.append("pre-release")
            if draft:
                flags.append("draft")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            return (
                f"Latest release: {tag}{flag_str}\n"
                f"Name:           {name}\n"
                f"Published:      {published}\n"
                f"URL:            {html_url}"
            )
        except Exception as e:
            return f"ERROR querying GitHub API: {str(e)}"

    def get_context_status(self) -> str:
        """
        Query the llama.cpp server to get the current token usage and context fill percentage.
        Call this when a session has had 5+ tool calls, or the user asks about context health.
        Do NOT call this for simple single-tool queries.
        Results drive compaction and hard-reset decisions described in the system prompt.
        """
        import requests  # noqa: PLC0415

        self._log("CTX-STATUS: querying /slots")
        try:
            resp = requests.get(f"{self.valves.LLAMA_SERVER_URL}/slots", timeout=5)
            slots = resp.json()
            if not slots:
                return "No active slots found on llama.cpp server."
            s = slots[0]

            # v1.5.4 fix: llama-server build >=9307 uses n_prompt_tokens, not n_past.
            n_prompt = s.get("n_prompt_tokens", 0)
            n_ctx = s.get("n_ctx", 65536)
            n_cache = s.get("n_prompt_tokens_cache", 0)
            n_proc = s.get("n_prompt_tokens_processed", 0)

            next_tok = s.get("next_token", [{}])
            nt = next_tok[0] if next_tok else {}
            n_decoded = nt.get("n_decoded", 0)
            n_remain = nt.get("n_remain", -1)
            n_predict = s.get("params", {}).get("n_predict", 0)

            pct = round(n_prompt / n_ctx * 100, 1) if n_ctx else 0.0
            cache_pct = round(n_cache / n_prompt * 100) if n_prompt else 0

            if pct >= 85:
                status = "🔴 CRITICAL — HARD RESET required before next tool call."
            elif pct >= 70:
                status = "🟠 HIGH — COMPACTION required before next tool call."
            elif pct >= 50:
                status = "🟡 ELEVATED — minimise tool output verbosity."
            else:
                status = "🟢 OK — normal operation."

            truncation = ""
            if n_predict > 0 and n_remain == 0 and n_decoded >= n_predict:
                truncation = (
                    f"⚠️  Last response truncated at {n_decoded:,} tokens "
                    f"(hit max_tokens={n_predict} cap — raise in OpenWebUI model settings).\n"
                )

            return (
                f"Context: {n_prompt:,} / {n_ctx:,} tokens ({pct}%)\n"
                f"Prefix cache: {n_cache:,} cached / {n_proc:,} processed "
                f"({cache_pct}% hit rate)\n"
                f"Last generation: {n_decoded:,} tokens\n"
                f"{truncation}"
                f"Status: {status}"
            )
        except Exception as e:
            return f"ERROR querying llama.cpp: {str(e)}"

    def monitor_download(
        self, file_path: str, expected_bytes: int, interface: str = ""
    ) -> str:
        """
        Check download progress using Prometheus network metrics + file size.
        Returns a single status line with completion %, speed, ETA, and SLEEP N.

        PROTOCOL (zero-polling — one call, one sleep, one check):
          1. result = monitor_download(path, size)
          2. COMPLETE  → proceed to next block, call record_outcome()
          3. STALLED   → alert user immediately, do not sleep-loop
          4. Otherwise → parse SLEEP N from result → execute_command("sleep N") → goto 1

        OUTPUT:
          DOWNLOADING | 26.3% | 4.21/16.0 GB | 28.3 MB/s (eth0) | ETA 423s | SLEEP 472
          COMPLETE    | 100%  | 16.0/16.0 GB | elapsed 10m 17s
          STALLED     | 26.3% | 4.21/16.0 GB | 0.0 MB/s | no traffic on eth0 | SLEEP 30

        Speed source: Prometheus localhost:9090 — same data as Grafana Network Download
          Speed dashboard at http://localhost:3002/d/lse-net-speed-01/network-download-speed
        Sleep buffer: SLEEP = ceil(ETA * 1.08 + 15)
        Script: /opt/local-se/download-monitor.py — deploy once if not present.
        """
        import subprocess  # noqa: PLC0415
        import shutil  # noqa: PLC0415
        import os as _os  # noqa: PLC0415

        monitor_script = "/opt/local-se/download-monitor.py"
        # Prefer the miniforge interpreter when it actually exists; otherwise fall
        # back to whatever python3 is on PATH. The previous logic used the hardcoded
        # miniforge path unconditionally unless python3 was missing from PATH, which
        # broke on hosts without miniforge installed.
        python_bin = "/home/sy5/miniforge3/bin/python3"
        if not _os.path.exists(python_bin):
            python_bin = shutil.which("python3") or "python3"

        if not _os.path.exists(monitor_script):
            return (
                "SETUP_REQUIRED | download-monitor.py not found at /opt/local-se/. "
                "Deploy: write_file /opt/local-se/download-monitor.py from "
                "tools/download-monitor.py in the LSE repo, then chmod +x."
            )

        cmd = [python_bin, monitor_script, file_path, str(expected_bytes)]
        if interface:
            cmd.append(interface)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip()
            if not output and result.stderr:
                return f"ERROR | {result.stderr.strip()}"
            return output if output else "ERROR | no output from monitor script"
        except subprocess.TimeoutExpired:
            return "ERROR | monitor script timed out (Prometheus unreachable)"
        except Exception as exc:
            return f"ERROR | {exc}"

    def compact_context(
        self,
        summary: str,
        __chat_id__: str = "",
    ) -> str:
        """
        Truncate OpenWebUI chat history and flush the KV cache to reclaim context.

        WHEN TO CALL:
          Call this when get_context_status reports >= 70% fill, or when the user
          asks to "compact", "clear", or "reset" the context.

        REQUIRED ARGUMENT:
          summary — a concise plain-text paragraph (3–8 sentences) capturing every
          fact, file path, command outcome, decision, and pending task from this
          session that must survive the compaction. Write it in third person as if
          briefing the next agent. DO NOT omit anything the user will need to
          reference.

        WHAT THIS FUNCTION DOES:
          1. Fetches the full OpenWebUI chat history for this chat.
          2. Traverses the active message branch (root → currentId).
          3. Keeps only the last 4 messages (2 user + 2 assistant turns).
          4. Prepends a system-role summary message so the model retains session state.
          5. Writes the truncated history back directly to the OpenWebUI SQLite DB.
          6. Erases the llama.cpp KV cache slot via POST /slots/0?action=erase
             (action is a QUERY PARAMETER — a JSON body {"action":...} is rejected
             with "Invalid action" on every llama.cpp version).
          7. Returns a confirmation string for the model to echo to the user.

        AFTER CALLING:
          Emit exactly this line to the user (do not add anything else):
          "Context compacted. Session state preserved in summary. KV cache cleared."
          The next message will begin with a fresh context window.
        """
        if not __chat_id__:
            return "ERROR: __chat_id__ not injected. This tool must be called from within an OpenWebUI chat."

        import sqlite3
        import uuid as _uuid

        DB_PATH = self.valves.OWUI_DB_PATH

        try:
            con = sqlite3.connect(DB_PATH, timeout=10)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT chat FROM chat WHERE id = ?", (__chat_id__,))
            row = cur.fetchone()
            if not row:
                con.close()
                return f"ERROR: chat id '{__chat_id__}' not found in DB."

            chat_obj = json.loads(row["chat"])
            history = chat_obj.get("history", {})
            messages_map = history.get("messages", {})
            current_id = history.get("currentId", "")

            if not messages_map or not current_id:
                return "ERROR: Chat history is empty or malformed — nothing to compact."

            branch = []
            node_id = current_id
            visited = set()
            while node_id and node_id not in visited:
                visited.add(node_id)
                msg = messages_map.get(node_id)
                if not msg:
                    break
                branch.append(msg)
                node_id = msg.get("parentId") or ""
            branch.reverse()

            total_before = len(branch)
            KEEP = 4
            kept = branch[-KEEP:] if len(branch) > KEEP else branch

            summary_id = str(_uuid.uuid4())
            summary_msg = {
                "id": summary_id,
                "parentId": None,
                "childrenIds": [kept[0]["id"]] if kept else [],
                "role": "system",
                "content": (
                    f"[CONTEXT COMPACTION SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}]\n\n"
                    f"{summary}\n\n"
                    f"(History truncated from {total_before} → {len(kept)} messages. "
                    f"Resume from this point.)"
                ),
                "timestamp": int(datetime.now().timestamp()),
            }

            if kept:
                kept[0] = dict(kept[0])
                kept[0]["parentId"] = summary_id

            new_messages = {summary_msg["id"]: summary_msg}
            for msg in kept:
                new_messages[msg["id"]] = msg

            new_history = {
                "currentId": kept[-1]["id"] if kept else summary_id,
                "messages": new_messages,
            }

            chat_obj["history"] = new_history
            cur.execute(
                "UPDATE chat SET chat = ? WHERE id = ?",
                (json.dumps(chat_obj), __chat_id__),
            )
            con.commit()
            con.close()

            kv_status = "KV cache erase skipped"
            try:
                slots_url = (
                    self.valves.LLAMA_SERVER_URL.rstrip("/") + "/slots/0?action=erase"
                )
                kv_req = urllib.request.Request(
                    slots_url,
                    data=b"",
                    method="POST",
                )
                with urllib.request.urlopen(kv_req, timeout=5) as resp:
                    try:
                        n_erased = json.loads(resp.read()).get("n_erased", "?")
                    except Exception:
                        n_erased = "?"
                    kv_status = (
                        f"KV cache erased (slot 0, HTTP {resp.status}, "
                        f"n_erased={n_erased})"
                    )
            except Exception as kv_err:
                kv_status = f"KV cache erase failed: {kv_err}"

            return (
                f"Compacted: {total_before} → {len(kept) + 1} messages "
                f"({total_before - len(kept)} dropped). "
                f"Summary node prepended. {kv_status}."
            )

        except Exception as e:
            return f"ERROR during compact_context: {str(e)}"

    # ── RAG private helpers ──────────────────────────────────────────────────

    def _embed(self, text: str) -> list:
        """768-dim embedding from Ollama nomic-embed-text (CPU-only, no GPU pressure)."""
        import requests  # noqa: PLC0415

        r = requests.post(
            f"{self.valves.OLLAMA_URL}/api/embed",
            json={
                "model": self.valves.EMBED_MODEL,
                "input": "search_query: " + text[:5000],
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["embeddings"][0]

    def _es(self):
        """Lazy Elasticsearch 8.x client."""
        from elasticsearch import Elasticsearch  # noqa: PLC0415

        return Elasticsearch(self.valves.ES_URL, request_timeout=10)

    # ── RAG tool functions ───────────────────────────────────────────────────

    def search_kb(
        self,
        query: str,
        min_score: float = 3.5,
        max_results: int = 5,
        topic_filter: str = "",
    ) -> str:
        """
        Search the LSE knowledge base using semantic + keyword hybrid search.

        KB-FIRST RULE — mandatory:
          ALWAYS call this before search_web or any SearxNG query.
          The KB contains curated, locally-verified technical knowledge about this system.
          Searching the web for something already in the KB is a protocol violation.

        RESULT QUALITY:
          Each result includes a quality_score (0.0–1.0):
            0.3 = stub / single fact — verify before using
            0.5 = rough first draft — usable but may be incomplete
            0.6 = reasonable coverage — good starting point
            0.8 = web-verified — cross-referenced with live source
            1.0 = authoritative — manually verified or official docs
          Each result also shows its age (updated Xd ago). STALENESS RULE:
          for tokens, paths, ports, and config values, a KB hit is a POINTER,
          not ground truth — verify against the live system (read_file /
          docker inspect) before using or quoting the value. Acting on a
          stale config value without a live read is a protocol violation.

        ON MISS:
          If this returns "KB miss", fall through to search_web(). Then call
          index_to_kb() with the best result to grow the KB for next time.

        Args:
            query:        Natural language search query.
            min_score:    HYBRID-score threshold (0.7·knn + 0.3·BM25 — BM25 is
                          unbounded, so real scores run ~3.5–16, NOT 0–1).
                          Default 3.5, calibrated for 1024-dim qwen3-embedding (2026-07-15): keeps 98% top-3, 75% total.
                          keeps 38/38 correct top-1 hits, rejects 3/11 wrong
                          ones, loses zero correct. (The old 0.72 default was
                          calibrated for cosine and filtered nothing.) Do not
                          hand-tune — re-run rag/eval_retrieval.py
                          --threshold-report after major KB growth instead.
            max_results:  Max results to return. Default 5.
            topic_filter: Optional topic tag: 'comfyui', 'wan2.1', 'searxng',
                          'llama-cpp', 'pfsense', 'infrastructure', 'openwebui'.
        """
        self._log(f"SEARCH-KB: {query}")
        _tb = self._consume_time_banner()  # CHRONOS-2 (v0.3.1)
        try:
            embedding = self._embed(query)
            es = self._es()
            filter_clause = [{"term": {"topic": topic_filter}}] if topic_filter else []
            body = {
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding,
                    "k": max_results,
                    "num_candidates": 50,
                    "boost": 0.7,
                },
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["title^2", "content"],
                                    "boost": 0.3,
                                }
                            }
                        ],
                        "filter": filter_clause,
                    }
                },
                "_source": [
                    "title",
                    "content",
                    "source_path",
                    "source_url",
                    "topic",
                    "quality_score",
                    "updated_at",
                    "empirical_runs",
                    "success_count",
                    "failure_count",
                    "consecutive_failures",
                    "stale",
                    "volatility",
                ],
                "size": max_results,
            }
            resp = es.search(index="lse-kb", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= min_score]
            if not hits:
                return _tb + (
                    f"KB miss — no results above threshold {min_score} for '{query}'.\n"
                    "Fall through to search_web(), then call index_to_kb() with quality results."
                )

            # CHRONOS-3 (v0.3.1): volatility TTLs — static=∞, slow=90d (default),
            # fast=7d. Age beyond TTL → [EXPIRED] tag + rerank demotion. This
            # replaces the retired 30d/7d docstring table with enforced metadata.
            _TTL_DAYS = {"static": None, "slow": 90, "fast": 7}

            def _age_days(s):
                try:
                    return max(
                        0,
                        (
                            datetime.now().astimezone()
                            - datetime.fromisoformat(s.get("updated_at") or "")
                        ).days,
                    )
                except Exception:
                    return None

            def _is_expired(s):
                ttl = _TTL_DAYS.get(s.get("volatility") or "slow", 90)
                age = _age_days(s)
                return ttl is not None and age is not None and age > ttl

            # KB-DECAY-2 (v0.3.0): client-side trust rerank. Penalize by verified
            # failure ratio (multiplier 1 − 0.3·fail/runs); halve stale (quarantined)
            # and expired docs so they always rank below fresh ones. Deliberately NOT
            # an ES function_score — measure with the gold set before moving server-side.
            def _trust_rank(h):
                s = h["_source"]
                runs = s.get("empirical_runs", 0) or 0
                fails = s.get("failure_count", 0) or 0
                mult = 1.0 - 0.3 * (fails / runs) if runs else 1.0
                if s.get("stale"):
                    mult *= 0.5
                if _is_expired(s):
                    mult *= 0.5
                return h.get("_score", 0) * mult

            hits.sort(key=_trust_rank, reverse=True)
            lines = [f"KB results for '{query}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                src = s.get("source_path") or s.get("source_url") or "unknown"
                _age_d = _age_days(s)
                _age = f"updated {_age_d}d ago" if _age_d is not None else "age unknown"
                _vol = s.get("volatility") or "slow"
                _runs = s.get("empirical_runs", 0) or 0
                _ok = s.get("success_count", 0) or 0
                _fail = s.get("failure_count", 0) or 0
                _trust = (
                    f"runs={_runs} ({_ok} ok/{_fail} fail)" if _runs else "untested"
                )
                _flags = ""
                if s.get("stale"):
                    _flags += "    [STALE — quarantined, verify live before use]\n"
                if _is_expired(s):
                    _flags += (
                        f"    [EXPIRED — {_vol} TTL exceeded; pointer only, "
                        "re-verify live before use]\n"
                    )
                lines.append(
                    f"[{i}] doc_id={h['_id']} | {s['title']} | topic={s['topic']} | "
                    f"quality={s['quality_score']:.2f} | score={h['_score']:.3f} | "
                    f"{_trust} | {_age} | volatility={_vol}\n"
                    f"{_flags}"
                    f"    source: {src}\n"
                    f"    (pass doc_id above to record_outcome/mentor_correct)\n"
                    f"    {s['content'][:5000].strip()}\n"
                )
            return _tb + "\n".join(lines)
        except Exception as e:
            self._log(f"SEARCH-KB ERROR: {e}")
            return f"KB search error: {e}\nFall through to search_web()."

    def _wf_version_claim(self, text: str) -> bool:
        """WATERFALL (v1.7.18): True if text makes an external-software
        version/behavior claim, e.g. 'removed in v9577', 'deprecated since 2.8.0',
        'changed in version 9'. Used to gate KB writes that lack provenance."""
        import re as _re  # noqa: PLC0415

        if not text:
            return False
        verb = (
            r"removed|added|introduced|deprecated|renamed|dropped|replaced|"
            r"disabled|enabled|broke|broken|changed|merged|landed|backported|"
            r"no longer (?:available|supported|present)|now (?:requires|defaults)"
        )
        ver = (
            r"v\d|version\s+\d|\d+\.\d+\.\d+|"
            r"\d+\.\d+(?!\s?(?:gb|mb|kb|tb|g\b|m\b|k\b|ghz|mhz|hz|sec|s\b|ms|%|x\b|hour|hr|min|day|am|pm))|"
            r"build\s+\d|release\s+\d|b\d{3,}"
        )
        pat = (
            r"(?i)(?:(?:" + verb + r")[^.\n]{0,40}?(?:" + ver + r")"
            r"|(?:since|as of|starting (?:in|with)|prior to|before|after)\s+(?:"
            + ver + r"))"
        )
        return bool(_re.search(pat, text))

    def _wf_has_provenance(
        self,
        text: str,
        source_url: str = "",
        evidence: str = "",
        verified_against: str = "",
    ) -> bool:
        """WATERFALL (v1.7.18): True if waterfall provenance is attached — a fetched
        URL, >=40 chars of ground-truth evidence, a version snapshot, or an inline
        URL / RFC / doc_id in the text itself."""
        import re as _re  # noqa: PLC0415

        if (source_url or "").strip().lower().startswith(("http://", "https://")):
            return True
        if len((evidence or "").strip()) >= 40:
            return True
        if (verified_against or "").strip():
            return True
        t = text or ""
        if _re.search(r"https?://", t):
            return True
        if _re.search(r"(?i)\bRFC\s*\d{3,5}", t):
            return True
        if _re.search(r"(?i)\bdoc_id[=:\s]", t):
            return True
        return False

    def index_to_kb(
        self,
        content: str,
        title: str,
        topic: str,
        source_url: str = "",
        quality_score: float = 0.5,
        source_tier: str = "inferred",
        evidence: str = "",
        verified_against: str = "",
        volatility: str = "slow",
    ) -> str:
        """
        Index a document into the LSE knowledge base (lse-kb index).

        WHEN TO CALL:
          After finding high-quality information from search_web() or Playwright
          that is not already in the KB, or that is better than what's there.
          Call AT MOST ONCE per user request, for the single best finding.
          Do NOT call search_kb() afterwards to verify — trust the return value.
          Do NOT call this if search_kb() already returned a hit with quality >= 0.6.

        DEDUPLICATION:
          If a nearly identical document already exists (cosine > 0.92), this
          UPDATES the existing entry rather than duplicating it. quality_score
          is raised to max(existing, new). The KB improves over time.

        WATERFALL PROVENANCE RULE (v1.7.18):
          Claims about external-software version/behavior ("X removed in v9577",
          "deprecated since 2.8.0") MUST carry waterfall provenance — set source_url=
          (fetched URL), evidence= (ground-truth tool output), or include an inline
          RFC / doc_id. Before such a claim, run the waterfall: search_kb -> vendor
          docs/README -> github -> search_web. An unprovenanced version/behavior claim
          is stored tagged [UNVERIFIED] at quality <=0.3 so it cannot pose as fact.

        Args:
            content:       Full text to index.
            title:         Human-readable title.
            topic:         Use existing tags: 'wan2.1', 'comfyui', 'stable-diffusion',
                           'llama-cpp', 'searxng', 'pfsense', 'openwebui',
                           'lse-operations', 'infrastructure', 'general'.
            source_url:    URL where found (empty string for local content).
            quality_score: 0.0–1.0. Hard-capped to source_tier ceiling
                           (see source_tier). Default 0.5.
            source_tier:   Tier of evidence. Sets quality ceiling:
                           ground_truth=1.0 (live system test, tool-result evidence
                           required); primary=0.8 (vendor docs, official README, RFC);
                           secondary=0.6 (community forums, SO, Reddit, blog posts);
                           inferred=0.4 (untested hypothesis, model inference).
                           Default=inferred. Omitting source_tier caps quality at 0.4.
            evidence:      Required for source_tier=ground_truth — paste the actual
                           tool-result output (HTTP response, command output, >=40
                           chars). Empty or thin evidence downgrades ceiling to 0.7.
            verified_against: Optional version/config snapshot this entry was
                           verified against, e.g. "pfSense Plus 26.03" or
                           "RUTX50 fw 07.23.4". Stored for staleness tracking.
            volatility:    CHRONOS-3 (v0.3.1) freshness class — how fast this fact
                           decays. 'static' (never expires: topology, hardware,
                           protocols), 'slow' (90d TTL: procedures, configs —
                           DEFAULT), 'fast' (7d TTL: versions, CVEs, firmware,
                           prices). Past its TTL a doc is tagged [EXPIRED] in
                           search_kb and demoted below fresh hits. Re-verifying
                           via record_outcome(success=True) resets the clock.
        """
        import hashlib  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415

        _TIER_CEILING = {
            "ground_truth": 1.0,
            "primary": 0.8,
            "secondary": 0.6,
            "inferred": 0.4,
        }
        tier = source_tier if source_tier in _TIER_CEILING else "inferred"
        ceiling = _TIER_CEILING[tier]
        volatility = volatility if volatility in ("static", "slow", "fast") else "slow"
        tier_warn = ""
        if tier == "ground_truth" and len((evidence or "").strip()) < 40:
            ceiling = 0.7
            tier_warn = (
                " | TIER DOWNGRADE: source_tier=ground_truth requires evidence "
                ">=40 chars from a real tool result (HTTP response/command output). "
                "Ceiling capped at 0.7 — re-index with evidence= to unlock 1.0."
            )
        wf_warn = ""
        if self._wf_version_claim(content) and not self._wf_has_provenance(
            content, source_url, evidence, verified_against
        ):
            ceiling = min(ceiling, 0.3)
            tier = "inferred"
            content = (
                "[UNVERIFIED: external version/behavior claim, no waterfall provenance] "
                + content
            )
            wf_warn = (
                " | WATERFALL: version/behavior claim about external software with no "
                "provenance (KB doc_id / fetched URL / RFC). Stored UNVERIFIED, quality "
                "capped <=0.3. Run search_kb -> vendor docs/README -> github -> "
                "search_web, then re-index with source_url= or evidence=."
            )
        quality_score = min(float(quality_score), ceiling)
        self._log(
            f"INDEX-KB: title={title} topic={topic} tier={tier} quality={quality_score}"
        )
        # Store full content (up to 50000 chars); embed only first 8000 (nomic-embed-text token limit)
        content = content[:50000]
        embed_content = content[:8000]
        try:
            embedding = self._embed(embed_content)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            doc_hash = hashlib.sha256(content[:500].encode()).hexdigest()[:16]
            dup_resp = es.search(
                index="lse-kb",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["quality_score", "refinement_count", "version"],
                    "size": 1,
                },
            )
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.92:
                existing = dup_hits[0]
                new_q = min(
                    1.0, max(existing["_source"]["quality_score"], quality_score)
                )
                _dup_doc = {
                    "content": content,
                    "embedding": embedding,
                    "quality_score": new_q,
                    "refinement_count": existing["_source"]["refinement_count"] + 1,
                    "updated_at": now,
                    "version": existing["_source"]["version"] + 1,
                    "source_url": source_url or None,
                    "volatility": volatility,
                }
                # KB-DECAY recovery: re-indexing with tier-gated evidence above
                # the quarantine floor clears stale + the failure streak.
                if new_q > 0.2:
                    _dup_doc["stale"] = False
                    _dup_doc["consecutive_failures"] = 0
                es.update(
                    index="lse-kb",
                    id=existing["_id"],
                    body={"doc": _dup_doc},
                )
                es.update(
                    index="lse-kb",
                    id=existing["_id"],
                    body={
                        "doc": {
                            "source_tier": tier,
                            "evidence": (evidence or "").strip()[:1000] or None,
                            "verified_against": (verified_against or "").strip()
                            or None,
                        }
                    },
                )
                return (
                    f"KB updated (refined): doc_id={existing['_id']} | "
                    f"quality {existing['_source']['quality_score']:.2f} → {new_q:.2f} | "
                    f"refinements={existing['_source']['refinement_count'] + 1} | "
                    f"tier={tier}{tier_warn}{wf_warn}"
                )
            doc = {
                "doc_id": doc_hash,
                "title": title,
                "content": content,
                "source_path": None,
                "source_url": source_url or None,
                "topic": topic,
                "tags": [topic],
                "quality_score": quality_score,
                "refinement_count": 0,
                "embedding": embedding,
                "created_at": now,
                "updated_at": now,
                "version": 1,
                "source_tier": tier,
                "evidence": (evidence or "").strip()[:1000] or None,
                "verified_against": (verified_against or "").strip() or None,
                "volatility": volatility,
            }
            es.index(index="lse-kb", id=doc_hash, document=doc)
            return (
                f"KB created: doc_id={doc_hash} | title='{title}' | "
                f"topic={topic} | tier={tier} | quality={quality_score:.2f}{tier_warn}{wf_warn}"
            )
        except Exception as e:
            self._log(f"INDEX-KB ERROR: {e}")
            return f"KB index error: {e}"

    def record_error(self, error_text: str, context: str, resolution: str) -> str:
        """
        Record an error and its resolution to the LSE error knowledge base.

        MANDATORY — call this after recovering from ANY mistake:
          After fixing any error (command failure, wrong path, permission denied,
          wrong flag, broken pipe, etc.), call this so the same mistake is never
          made again in any future session.

        Args:
            error_text:  The exact error message or clear description of the failure.
            context:     What you were trying to do when the error occurred.
            resolution:  Exactly what fixed it.
        """
        import hashlib, re  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415

        self._log(f"RECORD-ERROR: {error_text[:80]}")
        wf_note = ""
        if self._wf_version_claim(resolution) and not self._wf_has_provenance(resolution):
            resolution = "[UNVERIFIED CLAIM] " + resolution
            wf_note = (
                " | WATERFALL: resolution makes an external version/behavior claim with "
                "no provenance — tagged UNVERIFIED. Attach a fetched URL or RFC ref."
            )
        try:
            embedding = self._embed(error_text + " " + context)
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            normalised = re.sub(r"\s+", " ", error_text.lower().strip())
            error_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]
            dup_resp = es.search(
                index="lse-errors",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["occurrence_count"],
                    "size": 1,
                },
            )
            dup_hits = dup_resp["hits"]["hits"]
            if dup_hits and dup_hits[0]["_score"] >= 0.90:
                existing = dup_hits[0]
                new_count = existing["_source"]["occurrence_count"] + 1
                es.update(
                    index="lse-errors",
                    id=existing["_id"],
                    body={
                        "doc": {
                            "last_seen": now,
                            "occurrence_count": new_count,
                            "resolution": resolution,
                        }
                    },
                )
                return f"Error KB updated: known error now seen {new_count}x. Resolution updated.{wf_note}"
            doc = {
                "error_hash": error_hash,
                "error_text": error_text,
                "context": context,
                "resolution": resolution,
                "embedding": embedding,
                "occurrence_count": 1,
                "first_seen": now,
                "last_seen": now,
            }
            es.index(index="lse-errors", id=error_hash, document=doc)
            return f"Error KB created: new error pattern recorded (hash={error_hash}).{wf_note}"
        except Exception as e:
            self._log(f"RECORD-ERROR ERROR: {e}")
            return f"Error KB record failed: {e}"

    def check_error_kb(self, error_text: str) -> str:
        """
        Check if an error has been seen before and retrieve its known resolution.

        KB-FIRST RULE — call this BEFORE any operation that might fail in a known way.
          Surface the resolution immediately rather than hitting the same failure again.

        Args:
            error_text: The error message or description to look up.
        """
        self._log(f"CHECK-ERROR-KB: {error_text[:80]}")
        try:
            embedding = self._embed(error_text)
            es = self._es()
            resp = es.search(
                index="lse-errors",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": [
                        "error_text",
                        "resolution",
                        "occurrence_count",
                        "last_seen",
                    ],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            if hits and hits[0]["_score"] >= 0.88:
                h = hits[0]["_source"]
                return (
                    f"⚠️ KNOWN ERROR (seen {h['occurrence_count']}x, "
                    f"last: {h['last_seen'][:10]})\n"
                    f"Error: {h['error_text'][:200]}\n"
                    f"Resolution: {h['resolution']}\n"
                    f"Apply the known resolution — do not repeat the failed approach."
                )
            return (
                "Not seen before — proceed carefully. "
                "Call record_error() after resolving to prevent recurrence."
            )
        except Exception as e:
            self._log(f"CHECK-ERROR-KB ERROR: {e}")
            return f"Error KB check failed: {e}. Proceed with caution."

    def _resolve_kb_id(self, es, ref: str):
        """Resolve a KB reference to the real Elasticsearch _id (v0.2.1).

        Accepts either the 16-char doc hash (_id) OR a human title — the model
        frequently passes the title, which es.get(id=...) 404s on (the
        mentor_correct/record_outcome failure mode). Returns (doc_id, note) on
        success or (None, message) with actionable guidance on failure."""
        ref = (ref or "").strip()
        if not ref:
            return None, "empty doc_id"
        # 1) exact _id hit
        try:
            if es.exists(index="lse-kb", id=ref):
                return ref, "matched by id"
        except Exception:
            pass
        # 2) fall back to an exact-title lookup
        try:
            r = es.search(
                index="lse-kb",
                body={
                    "query": {"match_phrase": {"title": ref}},
                    "_source": ["title"],
                    "size": 5,
                },
            )
            hits = r["hits"]["hits"]
        except Exception as e:
            return None, f"KB lookup error: {e}"
        if len(hits) == 1:
            return hits[0]["_id"], f"resolved title -> doc_id {hits[0]['_id']}"
        if not hits:
            return None, (
                f"no KB doc with id or title '{ref}'. Run search_kb() to get the "
                "exact doc_id (now shown as 'doc_id=...' in results), or use "
                "index_to_kb() to create the entry if it does not exist yet."
            )
        cands = ", ".join(h["_id"] for h in hits[:5])
        return None, (
            f"{len(hits)} KB docs match the title '{ref}' — pass the exact doc_id "
            f"from search_kb. Candidates: {cands}"
        )

    def record_outcome(
        self,
        doc_id: str,
        success: bool,
        notes: str = "",
        evidence: str = "",
    ) -> str:
        """
        Record an operational outcome against an existing KB document.

        WHEN TO CALL:
          After applying a procedure documented in the KB:
            success=True  — the documented approach worked as described.
            success=False — it failed or needed modification. Also call record_error().

          Increments empirical_runs, success_count, and failure_count on the KB doc
          so the LSE can track how many times a procedure has been tested in production
          and whether it reliably works.

        DEMOTION (v0.3.0, KB-DECAY-1 — applied server-side, do not compute yourself):
          success=False WITH evidence (>=20 chars of real tool output) demotes the doc:
            quality_score = max(0.2, quality − 0.15) and consecutive_failures += 1.
          At the 0.2 floor the doc is QUARANTINED: stale=true. It is never deleted —
          search_kb shows it with a [STALE] banner and ranks it below fresh docs.
          Quality is regained ONLY via the tier-gated paths (index_to_kb with better
          evidence, or a human mentor_correct) — a later success does NOT re-elevate.
          success=False WITHOUT evidence still counts the failure but does NOT demote —
          unverified failure claims must not erode the KB (same gate as skill_outcome).
          success=True resets consecutive_failures to 0. quality_score is untouched.

        EVIDENCE:
          GOOD: evidence="curl :8080/health → 404; systemctl is-active llama → inactive"
          BAD:  evidence="didn't work"   ← thin self-report, no demotion applied

        Args:
            doc_id:   The doc_id field from a search_kb or index_to_kb result.
            success:  True if the procedure succeeded, False if it failed.
            notes:    Optional context: variant used, environment, what differed, etc.
            evidence: For failures: the actual tool/command output proving the doc is
                      wrong (>=20 chars). Required to trigger demotion.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"RECORD-OUTCOME: doc_id={doc_id} success={success}")
        evidence = (evidence or "").strip()[:500]
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"record_outcome: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=[
                    "empirical_runs",
                    "success_count",
                    "failure_count",
                    "title",
                    "quality_score",
                    "consecutive_failures",
                    "stale",
                ],
            )
            src = resp["_source"]
            runs = src.get("empirical_runs", 0) + 1
            success_count = src.get("success_count", 0) + (1 if success else 0)
            failure_count = src.get("failure_count", 0) + (0 if success else 1)
            old_q = src.get("quality_score", 0.0)
            update: dict = {
                "empirical_runs": runs,
                "success_count": success_count,
                "failure_count": failure_count,
                "last_outcome_at": now,
            }
            if notes:
                update["last_outcome_notes"] = notes
            decay_note = ""
            if success:
                # KB-DECAY-1: verified success ends the failure streak but does
                # NOT re-elevate quality — that stays tier-gated (index_to_kb /
                # mentor_correct). stale stays until a tier-gated raise clears it.
                # CHRONOS-3 (v0.3.1): a verified success IS a re-verification —
                # bump updated_at so the volatility TTL clock resets and an
                # [EXPIRED] tag clears.
                update["updated_at"] = now
                if src.get("consecutive_failures", 0):
                    update["consecutive_failures"] = 0
                    decay_note = " | failure streak reset"
            elif len(evidence) >= 20:
                new_q = max(0.2, old_q - 0.15)
                streak = src.get("consecutive_failures", 0) + 1
                update["quality_score"] = new_q
                update["consecutive_failures"] = streak
                update["last_failure_evidence"] = evidence
                if new_q <= 0.2:
                    update["stale"] = True
                    decay_note = (
                        f" | DEMOTED {old_q:.2f} → {new_q:.2f} (streak={streak}) | "
                        f"STALE — quarantined at the 0.2 floor; kept for forensics, "
                        f"re-verify live before ever using this entry"
                    )
                else:
                    decay_note = f" | DEMOTED {old_q:.2f} → {new_q:.2f} (streak={streak})"
            else:
                decay_note = (
                    " | failure counted but NOT demoted — no evidence supplied. "
                    "Pass evidence= (>=20 chars of real tool output) to demote a "
                    "wrong KB entry."
                )
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            outcome_str = "✅ success" if success else "❌ failure"
            return (
                f"Outcome recorded: {outcome_str} | "
                f"doc='{src.get('title', doc_id)}' | "
                f"runs={runs} ({success_count} success / {failure_count} failure)"
                f"{decay_note}"
            )
        except Exception as e:
            self._log(f"RECORD-OUTCOME ERROR: {e}")
            return f"record_outcome failed: {e}"

    def mentor_correct(
        self,
        doc_id: str,
        correction: str,
        new_quality: float,
    ) -> str:
        """
        Apply a human-authored correction to an existing KB document.

        WHEN TO CALL:
          When the user identifies an error, outdated information, or an important
          improvement in a KB entry. Replaces the document content with the corrected
          version, re-embeds it, and raises the quality score.

        QUALITY RULE:
          This function never lowers the quality score. If new_quality is lower than
          the existing score, the call is rejected. Use index_to_kb to add a competing
          entry at a lower quality instead.

        Args:
            doc_id:       The doc_id of the KB entry to correct — the 'doc_id=...'
                          value shown in search_kb results (NOT the title). A title
                          is accepted as a fallback and resolved automatically; if
                          it matches no entry you get a clear message (use
                          index_to_kb to create a new entry instead).
            correction:   The full corrected content to replace the existing entry.
            new_quality:  New quality score (0.0–1.0).
                          Use 0.95–1.0 for human-verified corrections.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"MENTOR-CORRECT: doc_id={doc_id} new_quality={new_quality}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"mentor_correct: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=["quality_score", "refinement_count", "title"],
            )
            src = resp["_source"]
            old_quality = src.get("quality_score", 0.0)
            if new_quality < old_quality:
                return (
                    f"REJECTED: new_quality ({new_quality:.2f}) is lower than existing "
                    f"({old_quality:.2f}). mentor_correct must not lower quality. "
                    f"Use index_to_kb to add a competing entry instead."
                )
            embedding = self._embed(correction)
            _mc_doc = {
                "content": correction,
                "embedding": embedding,
                "quality_score": new_quality,
                "refinement_count": src.get("refinement_count", 0) + 1,
                "updated_at": now,
                "mentor_corrected_at": now,
            }
            # KB-DECAY recovery: a human correction above the quarantine floor
            # is THE tier-gated re-elevation path — clear stale + failure streak.
            if new_quality > 0.2:
                _mc_doc["stale"] = False
                _mc_doc["consecutive_failures"] = 0
            es.update(index="lse-kb", id=doc_id, body={"doc": _mc_doc})
            return (
                f"Mentor correction applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f} | "
                f"refinements={src.get('refinement_count', 0) + 1}"
            )
        except Exception as e:
            self._log(f"MENTOR-CORRECT ERROR: {e}")
            return f"mentor_correct failed: {e}"

    def kb_verify(self, doc_id: str, observed: str = "") -> str:
        """
        Verify a KB document's recorded version/config snapshot against the live
        system — the "application updated → KB silently wrong" regression detector
        (v0.3.0, KB-DECAY-3).

        TWO-PHASE PROTOCOL:
          Phase 1 — kb_verify(doc_id):
            Returns the stored verified_against snapshot plus probe instructions.
            YOU then run the live probe with existing tools (get_github_release,
            read_file, execute_command 'cat /etc/os-release', service --version, …).
          Phase 2 — kb_verify(doc_id, observed=<probe output>):
            Compares the snapshot against your probe output.
            MATCH    → auto record_outcome(success=True) — updated_at refreshed,
                       failure streak reset.
            MISMATCH → auto record_outcome(success=False, evidence=<probe output>)
                       — the KB-DECAY-1 demotion fires; the doc is on its way to
                       the 0.2 stale quarantine if it keeps failing verification.

        GATE:
          observed must be REAL probe output (>=20 chars), pasted verbatim.
          Passing a summary or a claim instead of tool output is a protocol
          violation — the comparison and the demotion evidence are only as
          trustworthy as the probe text.
          GOOD: observed="pfSense Plus 26.03-RELEASE (amd64) built on Thu Jun 12"
                ← verbatim tool output, comparable token by token
          BAD:  observed="the version matches what the KB says"
                ← a claim, not output. Do NOT paraphrase probe results.
          Do NOT call phase 2 with output from memory or an earlier session —
          the probe must have run THIS session.

        WHEN TO CALL:
          - Before acting on any KB doc whose verified_against names a version,
            firmware, or config snapshot ("pfSense Plus 26.03", "RUTX50 fw 07.23.4").
          - After any known upgrade of a system the KB documents.
          - When search_kb shows a doc as untested or with failures.

        Args:
            doc_id:   The doc_id from search_kb/index_to_kb results (title accepted).
            observed: Phase 2 only — verbatim live-probe output to compare against
                      the stored snapshot.
        """
        self._log(f"KB-VERIFY: doc_id={doc_id} phase={'2' if observed else '1'}")
        observed = (observed or "").strip()
        try:
            es = self._es()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"kb_verify: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=["title", "verified_against", "source_url", "updated_at",
                         "quality_score", "stale"],
            )
            src = resp["_source"]
            va = (src.get("verified_against") or "").strip()
            title = src.get("title", doc_id)
            if not va:
                return (
                    f"kb_verify: doc '{title}' has NO verified_against snapshot — "
                    "nothing to regression-check. If you verify it against the live "
                    "system now, re-index with verified_against= set (index_to_kb "
                    "dedup will update the existing entry)."
                )
            if not observed:
                return (
                    f"kb_verify phase 1 — doc '{title}' (doc_id={doc_id})\n"
                    f"  verified_against: {va}\n"
                    f"  quality={src.get('quality_score', 0):.2f}"
                    f"{' | STALE' if src.get('stale') else ''} | "
                    f"last updated: {str(src.get('updated_at', ''))[:10]}\n"
                    "NEXT: probe the live system for this exact version/config "
                    "(get_github_release / read_file / execute_command), then call "
                    f"kb_verify('{doc_id}', observed=<verbatim probe output>)."
                )
            if len(observed) < 20:
                return (
                    "kb_verify rejected: observed is too thin (<20 chars) to be real "
                    "probe output. Paste the verbatim tool result, not a claim."
                )
            # Normalized containment check: every token of the snapshot should
            # appear in the probe output for a match (case-insensitive).
            import re as _re  # noqa: PLC0415

            va_tokens = [t for t in _re.split(r"[\s,;/]+", va.lower()) if t]
            obs_l = observed.lower()
            missing = [t for t in va_tokens if t not in obs_l]
            if not missing:
                outcome = self.record_outcome(
                    doc_id, success=True,
                    notes=f"kb_verify: snapshot '{va}' confirmed against live probe",
                )
                return (
                    f"kb_verify MATCH ✅ — '{title}': live system still matches "
                    f"verified_against '{va}'.\n{outcome}"
                )
            outcome = self.record_outcome(
                doc_id, success=False,
                notes="kb_verify regression",
                evidence=(
                    f"verified_against regression: recorded '{va}' but live probe "
                    f"shows: {observed[:300]}"
                ),
            )
            return (
                f"kb_verify MISMATCH ❌ — '{title}': recorded '{va}' but the live "
                f"probe does not contain: {', '.join(missing[:5])}.\n"
                f"The entry has been demoted with the probe as evidence.\n{outcome}\n"
                "If the doc is still conceptually right, re-verify its content and "
                "re-index with the NEW verified_against snapshot."
            )
        except Exception as e:
            self._log(f"KB-VERIFY ERROR: {e}")
            return f"kb_verify failed: {e}"

    def mentor_demote(self, doc_id: str, new_quality: float, reason: str) -> str:
        """
        HUMAN-AUTHORIZED demotion of a KB document's quality score
        (v0.3.0, KB-DECAY-4).

        AUTHORIZATION GATE — mandatory, no exceptions:
          Call this ONLY when the human user has explicitly said this specific KB
          entry is wrong or overrated IN THIS SESSION. Never call it on your own
          judgment — model-initiated demotion is a protocol violation (the pfSense
          trust-metadata incident, P26). Evidence-based demotion you may perform
          yourself goes through record_outcome(success=False, evidence=...) instead.
          GOOD: user says "that RUTX50 wake-procedure doc is wrong, knock it
                down" → mentor_demote with their words as reason
          BAD:  kb_verify MISMATCH, a failed probe, or your own reasoning says
                a doc is outdated → record_outcome(success=False, evidence=…),
                NOT mentor_demote. Human words authorize; evidence demotes.

        WHY THIS EXISTS:
          mentor_correct is raise-only by design. Before v0.3.0 the only way to
          neutralise a wrong high-quality doc was a competing entry — which the
          wrong doc kept outranking. This is the direct human kill-switch.

        EFFECT:
          quality_score set to new_quality (must be LOWER than current — use
          mentor_correct to raise). new_quality <= 0.2 → stale=true quarantine
          (never deleted; search_kb shows the [STALE] banner). reason is stored
          on the doc as demote_reason for forensics.

        Args:
            doc_id:      The doc_id from search_kb results (title accepted).
            new_quality: New score, 0.0–1.0, strictly below the current one.
            reason:      Why the human demoted it (>=10 chars, stored on the doc).

        Trust the return value — do NOT call search_kb afterwards to confirm
        the new score.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"MENTOR-DEMOTE: doc_id={doc_id} new_quality={new_quality}")
        reason = (reason or "").strip()
        try:
            if len(reason) < 10:
                return (
                    "mentor_demote rejected: reason is required (>=10 chars) — it is "
                    "the forensic record of why a human pulled this entry down."
                )
            new_quality = max(0.0, min(float(new_quality), 1.0))
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resolved, note = self._resolve_kb_id(es, doc_id)
            if not resolved:
                return f"mentor_demote: {note}"
            doc_id = resolved
            resp = es.get(
                index="lse-kb", id=doc_id, _source=["quality_score", "title"]
            )
            src = resp["_source"]
            old_quality = src.get("quality_score", 0.0)
            if new_quality >= old_quality:
                return (
                    f"REJECTED: new_quality ({new_quality:.2f}) is not lower than "
                    f"existing ({old_quality:.2f}). mentor_demote only lowers — "
                    "use mentor_correct to raise."
                )
            update = {
                "quality_score": new_quality,
                "mentor_demoted_at": now,
                "demote_reason": reason[:500],
                "updated_at": now,
            }
            stale_note = ""
            if new_quality <= 0.2:
                update["stale"] = True
                stale_note = " | STALE — quarantined (kept for forensics)"
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            return (
                f"Mentor demotion applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f}{stale_note} | "
                f"reason: {reason[:120]}"
            )
        except Exception as e:
            self._log(f"MENTOR-DEMOTE ERROR: {e}")
            return f"mentor_demote failed: {e}"

    # ── v1.5.17: Log / scan summarisers ──────────────────────────────────────

    # ── Skills layer (v1.7.0 — lse-skills index) ────────────────────────────

    def skill_search(
        self, task: str, occupation: str = "", max_results: int = 2
    ) -> str:
        """
        Search the LSE skills index (lse-skills) for a PROCEDURE matching the task.

        SKILLS-FIRST RULE — mandatory:
          Before starting any multi-step or procedural operation (cleanup, restart,
          migration, hardening, recovery), call this BEFORE search_kb. Skills are
          runbook-shaped: preconditions → procedure → verification → failure modes.
          Skipping skill_search before a multi-step operation is a protocol violation.

        SKILLS vs FACTS:
          GOOD: skill_search("safely delete duplicate model files")
                ← procedural task: needs steps, safety gates, verification
          BAD:  skill_search("what port does llama-server use")
                ← single fact: use search_kb instead
          If this returns no skill, fall back to search_kb, then proceed carefully.

        GATE: never call more than once per task; max_results is capped at 2 to
        protect the context budget — do NOT request more.

        Args:
            task:        What you are about to do, in plain language.
            occupation:  Optional filter: 'linux-sysadmin', 'network-engineer',
                         'sre', 'dba', 'security-analyst'.
            max_results: Max skills returned (1-2). Default 2.
        """
        self._log(f"SKILL-SEARCH: {task} occupation={occupation}")
        max_results = max(1, min(int(max_results), 2))
        try:
            embedding = self._embed(task)
            es = self._es()
            filters = [{"term": {"archived": False}}]
            if occupation:
                filters.append({"term": {"occupation": occupation}})
            body = {
                "knn": {
                    "field": "embedding",
                    "query_vector": embedding,
                    "k": max_results,
                    "num_candidates": 50,
                    "boost": 0.7,
                },
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": task,
                                    "fields": ["task^2", "procedure"],
                                    "boost": 0.3,
                                }
                            }
                        ],
                        "filter": filters,
                    }
                },
                "_source": [
                    "skill_id",
                    "occupation",
                    "task",
                    "preconditions",
                    "procedure",
                    "verification",
                    "failure_modes",
                    "provenance",
                    "quality",
                    "stats",
                    "pinned",
                ],
                "size": max_results,
            }
            resp = es.search(index="lse-skills", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= 0.72]
            if not hits:
                return (
                    f"SKILL miss — no procedure above threshold for '{task}'.\n"
                    "Fall back to search_kb. If you then complete the task with a "
                    "ground-truth-verified outcome, record the procedure with skill_record()."
                )
            # Update usage stats (best-effort; retrieval must not fail on stats)
            lines = [f"SKILLS for '{task}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                try:
                    es.update(
                        index="lse-skills",
                        id=h["_id"],
                        body={
                            "script": {
                                "source": (
                                    "ctx._source.stats.uses += 1; "
                                    "ctx._source.stats.last_used = params.now"
                                ),
                                "params": {
                                    "now": datetime.now().astimezone().isoformat()
                                },
                            }
                        },
                    )
                except Exception:
                    pass
                st = s.get("stats", {})
                lines.append(
                    f"[{i}] {s['skill_id']} | quality={s['quality']:.2f} | "
                    f"uses={st.get('uses', 0)} "
                    f"(ok={st.get('episode_successes', 0)}/fail={st.get('episode_failures', 0)})"
                    f"{' | PINNED' if s.get('pinned') else ''}\n"
                    f"    TASK: {s['task']}\n"
                    f"    PRECONDITIONS: {'; '.join(s.get('preconditions') or []) or '(none)'}\n"
                    f"    PROCEDURE: {' -> '.join(s.get('procedure') or [])}\n"
                    f"    VERIFY: {s.get('verification', '')}\n"
                    f"    FAILURE MODES: {'; '.join(s.get('failure_modes') or []) or '(none)'}\n"
                    f"    (report the outcome with skill_outcome('{s['skill_id']}', ...) "
                    f"after ground-truth verification)\n"
                )
            return "\n".join(lines)
        except Exception as e:
            self._log(f"SKILL-SEARCH ERROR: {e}")
            return f"SKILL search error: {e}\nFall back to search_kb()."

    def skill_record(
        self,
        task: str,
        occupation: str,
        procedure: str,
        verification: str,
        preconditions: str = "",
        failure_modes: str = "",
        provenance: str = "",
        quality: float = 0.5,
        source_tier: str = "inferred",
    ) -> str:
        """
        Record a PROVEN procedure as a skill in the lse-skills index.

        EVIDENCE GATE — mandatory:
          Only call after the procedure was executed AND its outcome verified by a
          ground-truth check (verify_ssh, file/state probe, service health).
          Recording an unverified or self-reported procedure is a protocol violation.

        WHAT IS A SKILL:
          GOOD: task="free disk space by removing duplicates",
                procedure="enumerate; readlink -f + stat %i BOTH paths; verify
                survivor sha256; delete; df delta"  ← steps with safety gates
          BAD:  task="llama-server port", procedure="8080"
                ← that is a fact: use index_to_kb instead

        DEDUPLICATION:
          Near-identical skills (cosine > 0.92) are UPDATED, not duplicated;
          quality rises to max(existing, new). Trust the return value — do NOT
          call skill_search afterwards to verify the write.

        Args:
            task:          One-line description of what the skill accomplishes.
            occupation:    'linux-sysadmin', 'network-engineer', 'sre', 'dba',
                           'security-analyst'.
            procedure:     Ordered steps, separated by ';' or newlines.
            verification:  How success is confirmed (ground-truth command/check).
            preconditions: Required access/state, ';'-separated. Optional.
            failure_modes: Known ways this goes wrong, ';'-separated. Optional.
            provenance:    Episode id, URL, or incident doc reference. Optional
                           but strongly expected — unattributed skills are flagged.
            quality:       0.0-1.0. Episode-verified=0.5, cross-referenced=0.7.
                           Never start above 0.7.
            source_tier:   Evidence tier for this skill (same scale as index_to_kb).
                           ground_truth=1.0 ceiling (live test); primary=0.8;
                           secondary=0.6; inferred=0.4. Stored in document.
        """
        import hashlib  # noqa: PLC0415
        import re  # noqa: PLC0415

        self._log(f"SKILL-RECORD: occupation={occupation} task={task[:80]}")
        _TIER_CEILING_SK = {
            "ground_truth": 1.0,
            "primary": 0.8,
            "secondary": 0.6,
            "inferred": 0.4,
        }
        sk_tier = source_tier if source_tier in _TIER_CEILING_SK else "inferred"
        quality = max(0.2, min(float(quality), 0.7, _TIER_CEILING_SK[sk_tier]))
        _split = lambda s: [p.strip() for p in re.split(r"[;\n]+", s) if p.strip()]
        steps = _split(procedure)
        if len(steps) < 2:
            return (
                "SKILL rejected: procedure has fewer than 2 steps — that is a "
                "fact, not a skill. Use index_to_kb() instead."
            )
        if not verification.strip():
            return "SKILL rejected: verification is required (P2 — evidence-gated)."
        try:
            embed_text = f"{occupation}: {task}\n" + "\n".join(steps)
            embedding = self._embed(embed_text[:8000])
            es = self._es()
            now = datetime.now().astimezone().isoformat()
            dup = es.search(
                index="lse-skills",
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": 1,
                        "num_candidates": 10,
                    },
                    "_source": ["skill_id", "quality", "version"],
                    "size": 1,
                },
            )["hits"]["hits"]
            if dup and dup[0]["_score"] >= 0.92:
                ex = dup[0]
                new_q = min(0.7, max(ex["_source"]["quality"], quality))
                es.update(
                    index="lse-skills",
                    id=ex["_id"],
                    body={
                        "doc": {
                            "task": task,
                            "procedure": steps,
                            "preconditions": _split(preconditions),
                            "failure_modes": _split(failure_modes),
                            "verification": verification,
                            "provenance": _split(provenance),
                            "embedding": embedding,
                            "quality": new_q,
                            "updated_at": now,
                            "version": ex["_source"].get("version", 1) + 1,
                            "archived": False,
                            "source_tier": sk_tier,
                        }
                    },
                )
                return (
                    f"SKILL updated: {ex['_source']['skill_id']} | "
                    f"quality {ex['_source']['quality']:.2f} -> {new_q:.2f}"
                )
            slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:60]
            skill_id = f"{occupation}/{slug}"
            doc_id = hashlib.sha256(skill_id.encode()).hexdigest()[:16]
            es.index(
                index="lse-skills",
                id=doc_id,
                document={
                    "skill_id": skill_id,
                    "occupation": occupation,
                    "task": task,
                    "preconditions": _split(preconditions),
                    "procedure": steps,
                    "verification": verification,
                    "failure_modes": _split(failure_modes),
                    "provenance": _split(provenance) or ["UNATTRIBUTED"],
                    "embedding": embedding,
                    "quality": quality,
                    "stats": {
                        "uses": 0,
                        "episode_successes": 0,
                        "episode_failures": 0,
                        "last_used": None,
                    },
                    "pinned": False,
                    "archived": False,
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                    "source_tier": sk_tier,
                },
            )
            flag = "" if provenance.strip() else " | FLAGGED: no provenance"
            return f"SKILL created: {skill_id} | quality={quality:.2f}{flag}"
        except Exception as e:
            self._log(f"SKILL-RECORD ERROR: {e}")
            return f"SKILL record error: {e}"

    def skill_outcome(
        self,
        skill_id: str,
        success: bool,
        evidence: str,
        source_tier: str = "secondary",
    ) -> str:
        """
        Report a VERIFIED outcome for a skill that was injected/used this task.

        EVIDENCE GATE — mandatory:
          success=True requires ground-truth verification output in evidence
          (verify_ssh result, health check, state probe). The model's own claim
          of success is NOT evidence — passing self-reported success is a
          protocol violation (node-t3-002 lesson).
          GOOD: evidence="verify_ssh: all 4 assertions pass; df shows +17GB"
          BAD:  evidence="the procedure appeared to work"  ← self-report, rejected
          source_tier=ground_truth requires evidence >=50 chars and unlocks quality
          up to 1.0. Other tiers cap at their ceiling (primary=0.8, secondary=0.6).
          Pushing quality to 1.0 requires source_tier=ground_truth — this prevents
          self-granted max scores (pfSense read-only incident, P26).

        QUALITY RULES (applied server-side, do not compute yourself):
          verified success: +0.10 · verified failure: −0.15 · cap 1.0 ·
          floor 0.2 → skill auto-archived.

        GATE: only call when a skill from skill_search was actually followed
        during the task. Do NOT call for skills that were retrieved but ignored.
        Trust the returned new quality — do NOT re-query to verify.

        Args:
            skill_id: The skill_id returned by skill_search/skill_record.
            success:  True only with ground-truth evidence; False on verified failure.
            evidence: The verification output (command + result), max 500 chars.
        """
        self._log(f"SKILL-OUTCOME: {skill_id} success={success}")
        evidence = (evidence or "").strip()[:500]
        _SO_TIER_CEILING = {
            "ground_truth": 1.0,
            "primary": 0.8,
            "secondary": 0.6,
            "inferred": 0.4,
        }
        so_tier = source_tier if source_tier in _SO_TIER_CEILING else "secondary"
        so_ceiling = _SO_TIER_CEILING[so_tier]
        ev_min = 50 if so_tier == "ground_truth" else 20
        if len(evidence) < ev_min:
            return (
                f"SKILL outcome rejected: evidence too thin (need >={ev_min} chars "
                f"for source_tier={so_tier}). Paste the actual verification output "
                "(command + result), not a claim."
            )
        try:
            es = self._es()
            resp = es.search(
                index="lse-skills",
                body={
                    "query": {"term": {"skill_id": skill_id}},
                    "_source": ["quality", "stats", "pinned"],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            if not hits:
                return f"SKILL outcome error: skill_id '{skill_id}' not found."
            h = hits[0]
            old_q = h["_source"]["quality"]
            # v0.3.0: floor aligned to the documented 0.2 (was max(0.0, …) — code/
            # docstring drift found by PROVE-2). Same demotion math as record_outcome.
            new_q = min(so_ceiling, old_q + 0.10) if success else max(0.2, old_q - 0.15)
            archived = (
                (not success)
                and (new_q <= 0.2)
                and not h["_source"].get("pinned", False)
            )
            stats_field = "episode_successes" if success else "episode_failures"
            now = datetime.now().astimezone().isoformat()
            es.update(
                index="lse-skills",
                id=h["_id"],
                body={
                    "script": {
                        "source": (
                            "ctx._source.quality = params.q; "
                            f"ctx._source.stats.{stats_field} += 1; "
                            "ctx._source.archived = params.arch; "
                            "ctx._source.updated_at = params.now; "
                            "if (ctx._source.evidence_log == null) "
                            "{ ctx._source.evidence_log = []; } "
                            "ctx._source.evidence_log.add(params.ev)"
                        ),
                        "params": {
                            "q": new_q,
                            "arch": archived,
                            "now": now,
                            "ev": {"ts": now, "success": success, "evidence": evidence},
                        },
                    }
                },
            )
            tail = " | ARCHIVED (quality floor)" if archived else ""
            return (
                f"SKILL outcome recorded: {skill_id} | "
                f"quality {old_q:.2f} -> {new_q:.2f}{tail}"
            )
        except Exception as e:
            self._log(f"SKILL-OUTCOME ERROR: {e}")
            return f"SKILL outcome error: {e}"

    # pfsense_log_summary -- EXTRACTED to lse/skills/pfsense/tools.py
    # (Phase 2 skill extraction, 2026-07-06). See the pointer comment near
    # where pfsense_graphql used to live, above, for the loading mechanism.

    def nmap_summary(
        self,
        targets: str,
        top_ports: int = 1000,
        known_services: str = "",
    ) -> str:
        """
        Run nmap and return a COMPACT STRUCTURED SUMMARY. NEVER use
        execute_command('nmap ...') for network audits — raw nmap output is
        thousands of lines and fills context. This function parses nmap XML
        output and returns only the structured data the assertions need.

        PREREQUISITES: nmap must be installed on LUCIFER WSL2.
          Check: execute_command('which nmap') — install if missing:
          sudo_delegation_block('apt-get install -y nmap')

        WHAT THIS FUNCTION DOES:
          1. Runs: nmap -sV --top-ports <N> -oX - <targets>  (XML output to stdout)
          2. Parses XML — no raw text in the return value.
          3. Cross-references results against known_services baseline.
          4. Returns compact JSON with per-host port/service map + unexpected findings.

        RETURNED JSON keys:
          scan_results     — dict[ip, {ports: [int], services: {port: service_string}}]
          unexpected_ports — list[{ip, port, service}]: ports not in known_services
          host_count       — int: hosts that responded (up)
          scan_time_s      — float: elapsed scan time reported by nmap
          command          — str: exact nmap command that was run (for audit trail)

        Args:
            targets:        Space-separated IPs or CIDR ranges.
                            e.g. "192.168.1.0/24 192.168.5.0/24"
            top_ports:      Number of top ports to scan (default 1000).
            known_services: JSON string — dict[ip, list[int]] of expected ports.
                            Ports present in scan but absent here are flagged as
                            unexpected. Pass "" to skip unexpected-port analysis.
                            e.g. '{"192.168.1.50": [22, 80, 443, 514]}'
        """
        import subprocess
        import xml.etree.ElementTree as ET
        import json as _json
        import shutil
        import time

        if not shutil.which("nmap"):
            return (
                "ERROR: nmap not found. Install with:\n"
                "  sudo_delegation_block('apt-get install -y nmap')"
            )

        target_list = targets.strip().split()
        if not target_list:
            return "ERROR: nmap_summary — targets must be a non-empty string."

        cmd = [
            "nmap",
            "-sV",
            f"--top-ports={top_ports}",
            "-oX",
            "-",
            "--open",
        ] + target_list
        cmd_str = " ".join(cmd)
        self._log(f"NMAP: {cmd_str}")

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: nmap timed out after 300s. Reduce target scope or top_ports."
        except Exception as e:
            return f"ERROR running nmap: {e}"
        elapsed = round(time.monotonic() - t0, 1)

        if proc.returncode != 0 and not proc.stdout.strip():
            return f"ERROR: nmap failed (exit {proc.returncode}): {proc.stderr[:500]}"

        # ── Parse XML ─────────────────────────────────────────────────────────
        scan_results = {}
        nmap_elapsed = elapsed
        try:
            root = ET.fromstring(proc.stdout)
            run_stats = root.find("runstats/finished")
            if run_stats is not None:
                nmap_elapsed = float(run_stats.get("elapsed", elapsed))

            for host in root.findall("host"):
                status = host.find("status")
                if status is None or status.get("state") != "up":
                    continue
                addr_el = host.find("address[@addrtype='ipv4']")
                if addr_el is None:
                    continue
                ip = addr_el.get("addr", "unknown")

                ports_open = []
                services = {}
                for port_el in host.findall("ports/port"):
                    state_el = port_el.find("state")
                    if state_el is None or state_el.get("state") != "open":
                        continue
                    portnum = int(port_el.get("portid", 0))
                    ports_open.append(portnum)
                    svc_el = port_el.find("service")
                    if svc_el is not None:
                        svc_name = svc_el.get("name", "")
                        svc_product = svc_el.get("product", "")
                        svc_ver = svc_el.get("version", "")
                        services[str(portnum)] = " ".join(
                            p for p in [svc_name, svc_product, svc_ver] if p
                        ).strip()

                scan_results[ip] = {"ports": sorted(ports_open), "services": services}

        except ET.ParseError as e:
            return f"ERROR: nmap XML parse failed: {e}\nRaw output (first 500): {proc.stdout[:500]}"

        # ── Cross-reference against known baseline ────────────────────────────
        unexpected = []
        if known_services:
            try:
                baseline = _json.loads(known_services)
                for ip, info in scan_results.items():
                    expected = set(baseline.get(ip, []))
                    for port in info["ports"]:
                        if expected and port not in expected:
                            unexpected.append(
                                {
                                    "ip": ip,
                                    "port": port,
                                    "service": info["services"].get(
                                        str(port), "unknown"
                                    ),
                                }
                            )
            except _json.JSONDecodeError:
                unexpected = [
                    {"error": "known_services JSON invalid — skipped baseline check"}
                ]

        result = {
            "scan_results": scan_results,
            "unexpected_ports": unexpected,
            "host_count": len(scan_results),
            "scan_time_s": nmap_elapsed,
            "command": cmd_str,
        }
        self._log(
            f"NMAP-SUMMARY: {len(scan_results)} hosts up, "
            f"{len(unexpected)} unexpected ports, {nmap_elapsed}s"
        )
        return _json.dumps(result, indent=2)

    def search_rfc(
        self,
        symptom: str,
        protocol: str = "",
        top_k: int = 3,
    ) -> str:
        """
        Query the RFC authority KB for sections relevant to a technical problem.

        Use this BEFORE escalation and BEFORE any protocol-level diagnosis to ground
        your reasoning in authoritative standards. Returns the top matching RFC
        sections with authority scores, section titles, and guidance text.

        Three-layer retrieval:
          1. Embed symptom description (nomic-embed-text via Ollama)
          2. kNN dense search against lse-rfc-kb (Elasticsearch)
          3. Re-rank by quality_score = min(authority_ceiling,
                                             raw × confirmation_weight × recency_weight)

        Authority ceilings: Internet Standard 0.95 · Proposed Standard 0.85 ·
        Informational 0.70 · Obsoleted 0.30

        Args:
            symptom:  Description of the problem or error to search for.
                      Be specific: include protocol keywords, error messages,
                      observable behaviours, tool outputs.
                      e.g. "DHCP client retransmits DISCOVER after receiving ACK"
                      e.g. "TLS certificate verify failed — self-signed cert"
                      e.g. "DNS NXDOMAIN for hostname that should resolve"
            protocol: Optional protocol filter to narrow results.
                      Values: dhcp, dns, tls, tcp, http, syslog, ntp, nfs, nat, ip
                      Leave empty to search across all protocols.
            top_k:    Number of results to return (default 3, max 5).

        Returns JSON with list of results, each containing:
          rfc_number, section_id, section_title, citation, quality_score,
          authority_ceiling, snippet (first 400 chars of section text)
        """
        import json as _json

        # 1. Embed symptom
        embedding = []
        try:
            import requests as _req

            ollama_url = getattr(self.valves, "OLLAMA_URL", "http://127.0.0.1:11434")
            resp = _req.post(
                f"{ollama_url}/api/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "prompt": "search_query: " + symptom[:2000],
                },
                timeout=30,
            )
            if resp.status_code == 200:
                embedding = resp.json().get("embedding", [])
        except Exception as e:
            return f"ERROR: search_rfc — embedding failed: {e}"

        if not embedding:
            return "ERROR: search_rfc — could not embed symptom (Ollama unavailable?)"

        # 2. kNN search on lse-rfc-kb
        es_url = getattr(self.valves, "ES_URL", "http://127.0.0.1:9200")
        top_fetch = min(top_k, 5) * 3  # over-fetch for re-ranking

        query: dict = {
            "size": top_fetch,
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": top_fetch,
                "num_candidates": 50,
            },
        }
        if protocol:
            query["post_filter"] = {"term": {"protocols": protocol.lower()}}

        try:
            import requests as _req

            resp = _req.post(
                f"{es_url}/lse-rfc-kb/_search",
                json=query,
                timeout=10,
            )
            if resp.status_code == 404:
                return (
                    "ERROR: lse-rfc-kb index not found. "
                    "Run: python3 scripts/rfc_kb.py --index-all"
                )
            resp.raise_for_status()
            hits = resp.json().get("hits", {}).get("hits", [])
        except Exception as e:
            return f"ERROR: search_rfc — ES query failed: {e}"

        if not hits:
            return _json.dumps(
                {
                    "query": symptom[:100],
                    "protocol_filter": protocol,
                    "results": [],
                    "note": "No results. Index may be empty — run rfc_kb.py --index-all",
                }
            )

        # 3. Re-rank by quality_score × ES relevance
        results = []
        for h in hits:
            src_doc = h["_source"]
            es_score = h["_score"]
            quality = src_doc.get("quality_score", 0.0)
            combined = es_score * quality
            rfc_num = src_doc.get("rfc_number", 0)
            sec_id = src_doc.get("section_id", "")
            sec_num = sec_id.split("-", 1)[-1] if "-" in sec_id else sec_id
            results.append(
                {
                    "rfc_number": rfc_num,
                    "rfc_title": src_doc.get("rfc_title", ""),
                    "section_id": sec_id,
                    "section_title": src_doc.get("section_title", ""),
                    "citation": f"RFC {rfc_num} §{sec_num} — {src_doc.get('section_title', '')}",
                    "quality_score": round(quality, 3),
                    "authority_ceiling": src_doc.get("authority_ceiling", 0.0),
                    "rfc_status": src_doc.get("rfc_status", ""),
                    "protocols": src_doc.get("protocols", []),
                    "combined_score": round(combined, 4),
                    "snippet": src_doc.get("content", "")[:400],
                }
            )

        results.sort(key=lambda r: r["combined_score"], reverse=True)
        results = results[: min(top_k, 5)]

        self._log(
            f"RFC-SEARCH: '{symptom[:60]}' → {len(results)} results "
            f"(top: {results[0]['citation'][:60] if results else 'none'})"
        )

        return _json.dumps(
            {
                "query": symptom[:100],
                "protocol_filter": protocol,
                "results": results,
            },
            indent=2,
        )

    # ── Node Registry ─────────────────────────────────────────────────────────
    _NODE_REGISTRY: dict = {
        "node3090": {
            "mac": "0c:9d:92:84:6e:6a",
            "hostname": "node3090.home.arpa",
            "interface": "opt1",
            "agent_port": 8080,
            "agent_type": "llama-cpp",
            "os": "linux",
            "ssh_user": "lse-admin",
            "agent_profile": {
                "model": "/opt/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf",
                "ctx_size": 96000,
                "gpu_layers": 129,
                "flash_attn": True,
                "cache_type_k": "q8_0",
                "cache_type_v": "q8_0",
                "parallel": 1,
                "threads": 7,
                "threads_batch": 7,
                "reasoning_budget": 3072,
                "n_predict": 8192,
                "jinja": True,
                "metrics": True,
            },
        },
        "node5090": {
            "mac": "a0:ad:9f:84:d5:bf",
            "hostname": "node5090.home.arpa",
            "interface": "lan",
            "agent_port": 8081,
            "agent_type": "lmstudio",
            "os": "windows",
            "ssh_user": "sy5",
        },
    }

    def wake_node(self, node: str) -> str:
        """
        Wake a GPU node: ping first (skip WoL if already up), consult KB for
        current procedure, then send WoL via pfSense and poll until pingable.

        WORKFLOW
          Step 1 — Ping: if the node already responds, return immediately.
          Step 2 — KB lookup: search_kb for the node's current wake procedure.
                   Surface any KB notes before proceeding (interface changes,
                   known boot quirks, updated timeouts).
          Step 3 — WoL: POST magic packet via pfSense REST API.
          Step 4 — Poll ping for up to 120s; return once the node is up.

        WRITE ACCESS NOTE:
          WoL is a POST to pfSense (/api/v2/services/wake_on_lan/send). It sends
          a UDP magic packet only — it does NOT modify pfSense config. Still
          requires pfSense read-only mode to be disabled before calling.
          After waking: re-enable read-only before ending the session.

        FULL LIFECYCLE — call in order:
          1. wake_node(node)           — this tool
          2. query_node_agent(node, …) — delegate work to the GPU node's AI agent
          3. shutdown_node(node)       — shut down when done

        Args:
            node: "node3090" or "node5090"

        Returns:
            Status string: already-up / booted with elapsed time / error.
        """
        import time, subprocess  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]

        # ── Step 1: ping — skip WoL entirely if the node is already up ─────────
        self._log(f"WAKE-NODE: pinging {node} ({hostname}) to check current state")
        ping_check = subprocess.run(
            ["ping", "-c", "1", "-W", "2", hostname],
            capture_output=True,
        )
        if ping_check.returncode == 0:
            self._log(f"WAKE-NODE: {node} is already up — WoL skipped")
            return (
                f"{node} is already up (ping OK — WoL skipped).\n"
                f"Agent: http://{hostname}:{reg['agent_port']}/v1/\n"
                f"Next: call query_node_agent('{node}', prompt)"
            )

        # ── Step 2: KB lookup — surface any updated procedure or known quirks ───
        self._log(f"WAKE-NODE: checking KB for '{node} wake procedure'")
        kb_notes = ""
        try:
            kb_result = self.search_kb(f"{node} wake procedure")
            if kb_result and "no results" not in kb_result.lower():
                kb_notes = f"\nKB notes for {node}:\n{kb_result}\n"
                self._log(f"WAKE-NODE: KB returned notes ({len(kb_result)} chars)")
            else:
                self._log("WAKE-NODE: no KB notes found — proceeding with registry defaults")
        except Exception as exc:
            self._log(f"WAKE-NODE: KB lookup failed ({exc}) — continuing anyway")

        # ── Step 3: send WoL magic packet via pfSense ────────────────────────────
        self._log(
            f"WAKE-NODE: sending WoL for {node} ({reg['mac']}) on {reg['interface']}"
        )
        # Direct pfSense call, not self.pfsense_query() -- pfsense_query now lives
        # in a separate module/instance (lse/skills/pfsense/tools.py, loaded via
        # `--also`), so it is not reachable as a method on this goethe.py Tools
        # instance. This is a self-contained inline POST instead of a byte-for-byte
        # copy of pfsense_query's full machinery (log guard / confirmed gate /
        # response cap) because none of that applies here: this is a single fixed,
        # non-log, non-persistent-config endpoint (a UDP magic packet, not a
        # config write), and the explicit wake_node(node) call by name is itself
        # the user's confirmation to wake that node. PFSENSE_URL/API_KEY/CA_CERT
        # valves are intentionally still defined on this Tools class (unlike the
        # vault extraction, which removed BW_* entirely) precisely because of
        # this one remaining direct dependency.
        import requests as _wol_req  # noqa: PLC0415

        wol_key = self.valves.PFSENSE_API_KEY.strip()
        wol_cert = self.valves.PFSENSE_CA_CERT.strip()
        wol_verify = wol_cert if (wol_cert and os.path.isfile(wol_cert)) else False
        try:
            wol_resp = _wol_req.post(
                self.valves.PFSENSE_URL.rstrip("/") + "/api/v2/services/wake_on_lan/send",
                headers={"X-API-Key": wol_key, "Content-Type": "application/json"},
                json={"interface": reg["interface"], "mac": reg["mac"]},
                verify=wol_verify,
                timeout=15,
            )
            try:
                wol_result = f"[HTTP {wol_resp.status_code}] {_json.dumps(wol_resp.json())}"
            except Exception:
                wol_result = f"[HTTP {wol_resp.status_code}] {wol_resp.text[:500]}"
            if wol_resp.status_code >= 400:
                wol_result = "ERROR: " + wol_result
        except Exception as exc:
            wol_result = f"ERROR: WoL request to pfSense failed: {exc}"
        self._log(f"WAKE-NODE: pfSense response: {wol_result[:120]}")

        # Fast-fail: if the API call itself failed, do not waste 120s polling
        if wol_result.startswith("ERROR") or wol_result.startswith("[HTTP"):
            return (
                f"WAKE ABORTED — pfSense WoL API error (not starting poll):\n"
                f"{wol_result[:300]}\n"
                f"{kb_notes}"
                "Common causes:\n"
                "  • PFSENSE_API_KEY valve not set\n"
                "  • pfSense Read Only mode still enabled\n"
                "  • Endpoint mismatch (correct: POST /api/v2/services/wake_on_lan/send)"
            )

        # ── Step 4: poll ping — up to 120s ───────────────────────────────────────
        start = time.time()
        for attempt in range(60):
            time.sleep(2)
            if attempt % 5 == 0:
                self._log(f"WAKE-NODE: waiting for {node}... {attempt*2}s elapsed")
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hostname],
                capture_output=True,
            )
            if r.returncode == 0:
                elapsed = int(time.time() - start)
                self._log(f"WAKE-NODE: {node} up in {elapsed}s")
                return (
                    f"{node} is up — boot took {elapsed}s.\n"
                    f"{kb_notes}"
                    f"Agent: http://{hostname}:{reg['agent_port']}/v1/\n"
                    f"Next: call query_node_agent('{node}', prompt)"
                )

        return (
            f"TIMEOUT: {node} did not respond to ping after 120s.\n"
            f"WoL was sent (pfSense: {wol_result[:80]}).\n"
            f"{kb_notes}"
            "Check pfSense OPT1 interface selection and node power state."
        )

    def query_node_agent(
        self,
        node: str,
        prompt: str,
        model: str = "",
        max_tokens: int = 2000,
        system_prompt: str = "",
    ) -> str:
        """
        Send a prompt to the AI agent running on a GPU node (LM Studio OpenAI-compatible API).
        Node must already be awake — call wake_node() first if needed.

        The remote agent runs LM Studio on port 8081 (OpenAI-compatible endpoint).
        Response is returned directly — do not re-summarise unless needed.

        Args:
            node:          "node3090" or "node5090"
            prompt:        User message to send to the remote agent.
            model:         Model name override (uses LM Studio default if empty).
            max_tokens:    Max tokens for the response (default 2000).
            system_prompt: Optional system prompt to prepend.

        Returns:
            The remote agent's response text, or error string.
        """
        import requests as _req  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        url = f"http://{reg['hostname']}:{reg['agent_port']}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if model:
            payload["model"] = model

        self._log(f"QUERY-NODE-AGENT: POST {url} ({len(prompt)} chars)")
        try:
            resp = _req.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            self._log(f"QUERY-NODE-AGENT: got {len(content)} chars from {node}")
            return content
        except _req.exceptions.ConnectionError:
            return (
                f"Cannot reach {node} at {url}. "
                "Is the node awake? Call wake_node() first."
            )
        except Exception as exc:
            return f"query_node_agent error: {exc}"

    def start_node_agent(self, node: str) -> str:
        """
        Start the llama-cpp inference server on a GPU node using its registered agent_profile.

        Launches via SSH with nohup so the server persists after the SSH session ends.
        Logs are written to /home/<ssh_user>/llama-server.log on the node.
        Polls /health for up to 120s — returns once the server is ready to accept requests.

        Node must be awake — call wake_node() first if needed.
        To stop the server later: call stop_node_agent(node).

        SUDO EXEMPTION: server runs as lse-admin, no sudo required.

        Args:
            node: "node3090" or "node5090"

        Returns:
            Confirmation string with PID and endpoint, or error.
        """
        import subprocess as _sp  # noqa: PLC0415
        import time as _time  # noqa: PLC0415
        import requests as _req  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        profile = reg.get("agent_profile")
        if not profile:
            return f"No agent_profile defined for '{node}'. Update _NODE_REGISTRY."

        hostname = reg["hostname"]
        user = reg["ssh_user"]
        port = reg["agent_port"]
        log_path = f"/home/{user}/llama-server.log"

        # Build CLI args from profile dict
        parts = ["llama-server"]
        parts += ["--model", profile["model"]]
        parts += ["--port", str(port)]
        parts += ["--host", "0.0.0.0"]
        parts += ["--ctx-size", str(profile["ctx_size"])]
        parts += ["--n-gpu-layers", str(profile["gpu_layers"])]
        if profile.get("flash_attn"):
            parts += ["--flash-attn", "on"]
        if profile.get("cache_type_k"):
            parts += ["--cache-type-k", profile["cache_type_k"]]
        if profile.get("cache_type_v"):
            parts += ["--cache-type-v", profile["cache_type_v"]]
        if profile.get("parallel"):
            parts += ["--parallel", str(profile["parallel"])]
        if profile.get("threads"):
            parts += ["--threads", str(profile["threads"])]
        if profile.get("threads_batch"):
            parts += ["--threads-batch", str(profile["threads_batch"])]
        if profile.get("reasoning_budget"):
            parts += ["--reasoning-budget", str(profile["reasoning_budget"])]
        if profile.get("n_predict"):
            parts += ["--n-predict", str(profile["n_predict"])]
        if profile.get("jinja"):
            parts.append("--jinja")
        if profile.get("metrics"):
            parts.append("--metrics")

        cmd_str = " ".join(parts)
        # Background via nohup; stdin from /dev/null so SSH exits cleanly
        remote_cmd = f"nohup {cmd_str} </dev/null >{log_path} 2>&1 & echo PID:$!"

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            f"{user}@{hostname}",
            remote_cmd,
        ]

        self._log(f"START-NODE-AGENT: launching llama-server on {node}")
        try:
            r = _sp.run(ssh_cmd, capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                return f"SSH failed (exit {r.returncode}): {r.stderr.strip()}"
            pid_line = r.stdout.strip()
        except Exception as exc:
            return f"start_node_agent SSH error: {exc}"

        # Poll /health — model load takes 30-90s
        health_url = f"http://{hostname}:{port}/health"
        self._log(f"START-NODE-AGENT: polling {health_url}")
        deadline = _time.time() + 120
        while _time.time() < deadline:
            _time.sleep(5)
            try:
                resp = _req.get(health_url, timeout=3)
                if resp.status_code == 200:
                    elapsed = round(_time.time() - (deadline - 120))
                    return (
                        f"{node} agent ready ({pid_line}) — loaded in ~{elapsed}s\n"
                        f"Endpoint: http://{hostname}:{port}/v1/\n"
                        f"Log: ssh {user}@{hostname} tail -f {log_path}\n"
                        f"Stop: call stop_node_agent('{node}')"
                    )
            except Exception:
                pass

        return (
            f"Timeout: llama-server started ({pid_line}) but /health not responding after 120s. "
            f"Check: ssh {user}@{hostname} tail {log_path}"
        )

    def stop_node_agent(self, node: str) -> str:
        """
        Stop the llama-cpp inference server on a GPU node via SSH pkill.

        SAFETY: confirm no active inference jobs before calling.
        GPU VRAM is released immediately on stop.

        SUDO EXEMPTION: pkill runs as lse-admin, no sudo required.

        Args:
            node: "node3090" or "node5090"

        Returns:
            Confirmation or error string.
        """
        import subprocess as _sp  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]
        user = reg["ssh_user"]

        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            f"{user}@{hostname}",
            "pkill -f llama-server && echo stopped || echo no_process",
        ]

        self._log(f"STOP-NODE-AGENT: pkill llama-server on {node}")
        try:
            r = _sp.run(ssh_cmd, capture_output=True, text=True, timeout=15)
            output = r.stdout.strip() or r.stderr.strip()
            return f"{node} agent: {output}"
        except Exception as exc:
            return f"stop_node_agent error: {exc}"

    def shutdown_node(self, node: str, confirmed: bool = False) -> str:
        """
        Gracefully shut down a GPU node via SSH.

        CONFIRMATION REQUIRED — two-step call protocol:
          1. Call shutdown_node(node) — returns a confirmation prompt. STOP.
             Show the prompt to the user and wait for explicit approval.
          2. Only after the user says yes: call shutdown_node(node, confirmed=True).
          Never pass confirmed=True on the first call. Never assume consent.

        SAFETY RULES — mandatory before calling:
          - Confirm all GPU workloads on the node are complete.
          - Confirm query_node_agent() has returned its final response.

        SUDO EXEMPTION — do NOT call sudo_delegation_block for this function:
          The sudo runs remotely on the target node via SSH, not on LUCIFER.
          node3090 is configured with NOPASSWD sudoers for /sbin/shutdown (lse-admin).
          This is a pre-approved, pre-configured remote operation — call execute_command
          directly. Invoking sudo_delegation_block here is a protocol violation.

        SSH requirements:
          - LUCIFER lse-admin SSH key authorised on target node (no password prompt).
          - node3090 (Linux): /etc/sudoers.d/lse-shutdown grants NOPASSWD for shutdown.
          - node5090 (Windows): sy5 SSH session — SSH server must be enabled.

        Args:
            node:      "node3090" or "node5090"
            confirmed: Must be explicitly set to True by the user. Default False
                       returns a confirmation prompt without taking any action.

        Returns:
            Confirmation prompt (confirmed=False) or shutdown result (confirmed=True).
        """
        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]
        user = reg["ssh_user"]
        os_type = reg["os"]

        # ── Confirmation gate — always return prompt unless user explicitly approved ──
        if not confirmed:
            shutdown_cmd = "sudo shutdown -h now" if os_type == "linux" else "shutdown /s /t 30"
            return (
                f"⚠️  SHUTDOWN CONFIRMATION REQUIRED\n"
                f"  Node:    {node} ({hostname})\n"
                f"  OS:      {os_type}\n"
                f"  Command: {shutdown_cmd} (via SSH as {user})\n\n"
                f"This will power off the node immediately. All running workloads will be lost.\n\n"
                f"Reply 'yes' to confirm, then I will call shutdown_node('{node}', confirmed=True)."
            )

        # ── Confirmed — proceed with SSH shutdown ─────────────────────────────────
        if os_type == "linux":
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} sudo shutdown -h now"
            )
        else:  # windows
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} shutdown /s /t 30"
            )

        self._log(f"SHUTDOWN-NODE: confirmed=True — executing: {cmd}")
        # Use subprocess directly — execute_command blocks commands containing "sudo"
        # even when sudo runs remotely over SSH. This is a pre-approved remote operation.
        import subprocess as _sp  # noqa: PLC0415

        try:
            r = _sp.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=15,
            )
            # exit 255 = SSH closed mid-session as OS shuts down — this is success
            if r.returncode in (0, 255):
                return f"{node} shutdown command accepted (exit {r.returncode}). Node powering off."
            return (
                f"Shutdown may have failed (exit {r.returncode}). "
                f"stdout={r.stdout.strip()!r} stderr={r.stderr.strip()!r}"
            )
        except _sp.TimeoutExpired:
            return f"SSH timeout — node may already be shutting down or unreachable."
        except Exception as exc:
            return f"shutdown_node error: {exc}"

    # ── Hermes Agent delegation ───────────────────────────────────────────────

    def _call_hermes(self, task: str, context: str = "", no_think: bool = True) -> str:
        """[RETIRED v0.2.7] — Hermes gateway (port 8642) no longer runs.
        Use _call_node_planner() instead.
        """
        return "ERROR: _call_hermes is RETIRED (v0.2.7) — use _call_node_planner"

    def _kanban_create_card(self, task_id: str, title: str, body: str) -> str:
        """[RETIRED v0.2.7] — kanban.db was Hermes-specific (/home/hermes-admin/.hermes/).
        Hermes has been retired. This method is dead code and will be removed.
        """
        return "kanban retired (v0.2.7)"

    def _parse_planner_envelope(self, reply: str) -> tuple[dict | None, str]:
        """Parse planner reply into JSON envelope.

        Strips thinking blocks and code fences, finds and parses the first
        JSON object, validates it has a 'steps' array.

        Returns (envelope_dict, "") on success, (None, fail_reason) on failure.
        """
        # Strip Qwen3 / DeepSeek thinking blocks before JSON extraction.
        import re as _re  # noqa: PLC0415
        import json as _json  # noqa: PLC0415
        clean = _re.sub(r"<think>.*?</think>", "", reply, flags=_re.DOTALL).strip()
        # Strip markdown code fences (```json ... ```) some models wrap JSON in.
        clean = _re.sub(r"^```[a-z]*\n?", "", clean).rstrip("`").strip()
        # raw_decode parses the FIRST valid JSON object, stopping cleanly at
        # its closing brace regardless of trailing prose or garbage.
        idx = clean.find("{")
        if idx == -1:
            return None, f"no JSON object in reply. RAW: {clean[:200]!r}"
        try:
            env_c, _ = _json.JSONDecoder().raw_decode(clean, idx)
            if env_c.get("steps"):
                return env_c, ""
            return None, "envelope has no 'steps' array"
        except Exception as _exc:
            return None, (
                f"JSON parse failed ({_exc}). "
                f"RAW: {clean[idx : idx + 200]!r}"
            )


    def _load_ledger_for_revise(self, task_id: str, context: str) -> tuple[list, str] | str:
        """Load ledger history for revise mode.

        Returns (prior_done_steps, updated_context) on success,
        or an error string on failure.
        """
        import json as _json  # noqa: PLC0415
        if not task_id.strip():
            return "planner: mode='revise' requires task_id from the original plan."
        try:
            conn = self._tasks_db()
            row = conn.execute(
                "SELECT goal, steps_json FROM task_blocks WHERE task_id=?",
                (task_id.strip(),),
            ).fetchone()
            conn.close()
        except Exception as e:
            return f"planner revise: ledger read failed: {e}"
        if not row:
            return f"planner revise: no task block '{task_id}' in the ledger."
        old_steps = _json.loads(row[1]) if row[1] else []
        prior_done_steps = [s for s in old_steps if s.get("status") == "done"]
        ledger_lines = []
        for s in old_steps:
            st = s.get("status", "pending")
            mark = {"done": "COMPLETED", "failed": "FAILED"}.get(st, "pending")
            line = f"step {s.get('n')}: [{mark}] {s.get('what', '')}"
            if st in ("done", "failed") and s.get("evidence"):
                line += f" | evidence: {str(s['evidence'])[:150]}"
            ledger_lines.append(line)
        context = (
            (context + "\n\n" if context else "")
            + "LEDGER (completed/failed steps of the existing plan — re-plan "
            "ONLY the remaining work, number new steps after the highest "
            "completed step):\n" + "\n".join(ledger_lines)
        )
        return prior_done_steps, context


    def _synthesize_packaged_prompt(
        self,
        is_first_step: bool,
        goal: str,
        step_n: int,
        what: str,
        step_data: dict,
        legacy_packaged: str,
    ) -> str:
        """Generate a packaged_prompt when the planner omitted one.

        Uses the legacy packaged prompt for the first step (if available),
        otherwise synthesizes a defensive prompt from goal + step metadata.
        """
        if is_first_step and legacy_packaged:
            return legacy_packaged
        return (
            f"GOAL: {goal}\n"
            f"YOU ARE EXECUTING STEP {step_n} ONLY: {what}\n"
            f"INPUTS: {step_data.get('inputs', '(see ledger summary)')}\n"
            f"VERIFY: {step_data.get('verify', '')}\n"
            "STOP after this step and report the verify output."
        )

    def _normalize_plan_steps(self, raw_steps: list, goal: str, legacy_packaged: str) -> list:
        """Normalize raw planner steps into ledger entries.

        Synthesizes a defensive packaged_prompt fallback when the model
        omitted it. Returns a list of step dicts ready for the ledger.
        """
        new_steps = []
        for s in raw_steps:
            n = s.get("n")
            what = str(s.get("what", "")).strip()
            if n is None or not what:
                continue
            pkg = str(s.get("packaged_prompt", "")).strip()
            if not pkg:
                pkg = self._synthesize_packaged_prompt(
                    is_first_step=len(new_steps) == 0,
                    goal=goal,
                    step_n=n,
                    what=what,
                    step_data=s,
                    legacy_packaged=legacy_packaged,
                )
            new_steps.append(
                {
                    "n": int(n),
                    "what": what,
                    "depends_on": s.get("depends_on") or [],
                    "inputs": str(s.get("inputs", "")),
                    "output": str(s.get("output", "")),
                    "web_calls": s.get("web_calls", 0),
                    "tool_calls": s.get("tool_calls", 0),
                    "verify": str(s.get("verify", "")),
                    "packaged_prompt": pkg,
                    "status": "pending",
                    "evidence": "",
                    "done_at": None,
                }
            )
        return new_steps


    def _request_plan_envelope(self, task: str, context: str) -> tuple[dict | None, str | None]:
        """Fetch plan envelope from node planner with two-attempt retry.

        Returns (envelope_dict, None) on success,
        or (None, error_message) on failure.
        """
        env = None
        fail_reason = ""
        plan_ctx = context
        for attempt in (1, 2):
            reply = self._call_node_planner(task, context=plan_ctx, no_think=True)
            if not reply or reply.startswith("ERROR:"):
                return None, (
                    "PLANNER UNAVAILABLE — proceed with default budgets, "
                    f"checkpoint early. ({(reply or 'no reply')[:160]})"
                )
            env, fail_reason = self._parse_planner_envelope(reply)
            if env is not None:
                break
            self._log(f"NODE-PLAN: attempt {attempt} rejected — {fail_reason[:120]}")
            plan_ctx = (
                (context + "\n\n" if context else "")
                + "PREVIOUS REPLY REJECTED: " + fail_reason[:200]
                + "\nReturn ONLY the v2 JSON envelope object — no thinking, no "
                "prose, no code fences. Keep each packaged_prompt under 80 words."
            )
        if env is None:
            return None, (
                f"PLANNER UNAVAILABLE — {fail_reason} (after retry). "
                "Proceed with default budgets, checkpoint early."
            )
        return env, None


    def planner(
        self,
        task: str,
        context: str = "",
        mode: str = "new",
        task_id: str = "",
    ) -> str:
        """
        Request a pre-flight ATOMIZED execution plan from the peer LSE instance
        BEFORE starting a complex task (contract v2, Goethe v0.3.2). Every step is
        a tightly scoped unit (<=5 tool calls, ONE verifiable outcome) with its own
        self-contained packaged_prompt, so each step can run in a FRESH context
        window — this is how 131k context ceilings are managed on long work.
        The plan is written to the task ledger (tasks.db); execute the returned
        first step, then call plan_step_done() to strike it and receive the next.

        Planner backend — 3-path cascade (v0.2.8):
          1. node3090 llama-server :8080 (Qwen 27B, GPU) — primary
          2. node3090 Ollama :11434 qwen3:4b (CPU) — fallback when GPU unavailable
          3. Local Gemma GGUF spawn (VRAM-aware, port 8085) — last resort
             Model selected by task size: E4B / 26B-A4B / 31B.
             Vision tasks (image/png/jpg keywords) load the mmproj companion.

        MANDATORY TRIGGER — the user asked for a plan:
          If the user's request contains "plan" / "get a plan" / "how should we
          approach", or assigns a multi-phase audit/overhaul/migration, calling
          planner() is REQUIRED. NEVER hand-write a plan in prose instead, and
          NEVER create ad-hoc tracking files (active-task.md, plan.md, …) — the
          tasks.db ledger written by THIS tool is the single source of truth
          that survives session loss and that plan_step_done operates on.

        GATE — planner comes before EXECUTION, not before reading:
          Information gathering does NOT close the planning window. search_kb,
          skill_search, and read-only probes (dig, GET/status endpoints, health
          checks, config reads) BEFORE planner are correct — KB-FIRST still
          applies — and their findings belong in context=. The window closes
          when you start CHANGING state or producing deliverables.
          Do NOT call for single-fact lookups or short well-defined procedures
          (<3 steps) — execute directly instead.
          Do NOT call when resuming carried-over work (that is task_resume).

        GOOD: search_kb ×2 → pfsense_graphql reads → planner("audit DNS infra",
              context="<topology + findings from the reads>")
              ← reads first, findings handed to the planner. Correct order.
        GOOD: planner("Find the verbatim Goethe quote on architecture as
              frozen music and verify it against a primary source")
              ← research-shaped, spiral risk: plan first
        BAD:  user says "get a plan" → you write a phase list in prose and a
              tracking markdown file
              ← protocol violation: that plan has no ledger, no plan_step_done
              loop, and dies with your context window.
        BAD:  planner("What is the hostname of node3090?")
              ← single fact; use execute_command.
        BAD:  10 web searches, then planner
              ← web searches burn budget and ARE execution. Reads of local/KB
              state are fine; web-search spirals before planning are not.

        AFTER A PLAN IS RETURNED — mandatory step loop:
          1. Execute ONLY the step in the packaged prompt at the END of the result.
          2. Run that step's verify check and call
             plan_step_done(task_id, step_n, evidence=<verify output>).
          3. plan_step_done returns the NEXT step's packaged prompt — repeat.
          Do NOT look ahead, do NOT execute multiple steps from one prompt.
          On a FAILED step: plan_step_done(..., failed=True), then
          planner(task, mode="revise", task_id=<id>) to re-plan the remainder.
          Planner estimates are ESTIMATES, not established facts: never copy
          them into findings, never raise skill/KB quality from a plan (P2).
          Ignoring the abort criteria is a protocol violation.

        ON "PLANNER UNAVAILABLE":
          Proceed WITHOUT a plan: default budgets apply, checkpoint early.
          Do NOT retry planner more than once per task. The absence of a
          plan is NOT permission to skip checkpointing.

        Args:
            task:    The user's task, verbatim or lightly cleaned — do not
                     pre-digest it; the planner needs the original shape.
            context: Optional constraints, prior findings, or KB pointers for
                     the planner. Passed through as context.
            mode:    "new" (default) or "revise". Revise loads the ledger for
                     task_id, hands the planner the completed/failed step
                     summary, and replaces only the remaining steps.
            task_id: Required for mode="revise" — the id returned by the
                     original planner call.

        Returns the plan summary + packaged prompt, or a string starting with
        "PLANNER UNAVAILABLE" on any failure (all backends down, bad envelope).
        """
        import hashlib  # noqa: PLC0415
        import json as _json  # noqa: PLC0415
        import re as _re  # noqa: PLC0415

        self._log(f"NODE-PLAN: mode={mode} {task[:80]}")
        corr = hashlib.sha256((task + datetime.now().isoformat()).encode()).hexdigest()[
            :12
        ]
        # ── v0.3.2 revise mode: feed the ledger back to the planner ──────────
        prior_done_steps: list = []
        if mode == "revise":
            result = self._load_ledger_for_revise(task_id, context)
            if isinstance(result, str):
                return result
            prior_done_steps, context = result
        elif mode != "new":
            return "planner: mode must be 'new' or 'revise'."
        # ── v0.3.3: two-attempt envelope loop — truncated/malformed envelopes
        # (long thinking + tight completion budget) were the dominant
        # "PLANNER UNAVAILABLE" cause; one corrective retry recovers most.
        env, error = self._request_plan_envelope(task, context)
        if error:
            return error
        raw_steps = env.get("steps") or []
        legacy_packaged = str(env.get("packaged_prompt", "")).strip()
        goal = str(env.get("goal_summary") or task.strip()[:300])
        # Normalize steps into ledger entries; per-step packaged_prompt is v2 —
        # synthesize a defensive fallback when the model omitted it.
        new_steps = self._normalize_plan_steps(raw_steps, goal, legacy_packaged)
        if not new_steps:
            return (
                "PLANNER UNAVAILABLE — no usable steps in envelope. "
                "Proceed with default budgets, checkpoint early."
            )
        # revise: keep completed history in front of the re-planned remainder
        all_steps = prior_done_steps + new_steps
        all_steps.sort(key=lambda s: s.get("n", 0))
        # v0.3.3: NEVER trust a model-supplied task_id — live smoke showed the
        # model copying the schema example ("a1b2c3d4") verbatim, which would
        # collide every plan onto one ledger row. corr already hashes task+now.
        tid = task_id.strip() if mode == "revise" else corr[:8]
        plan_lines = "; ".join(
            f"step {s['n']}: {s['what']} "
            f"(web={s.get('web_calls', 0)}, tools={s.get('tool_calls', 0)}, "
            f"verify: {s.get('verify') or 'NONE'})"
            for s in new_steps
        )
        done_lines = "; ".join(
            f"step {s['n']}: {s['what']}" for s in prior_done_steps
        )
        first = new_steps[0]
        next_prompt = self._plan_step_prompt(goal, all_steps, first)
        ck = self.task_checkpoint(
            goal=goal,
            plan=plan_lines,
            done=done_lines,
            findings="",
            next_prompt=next_prompt,
            unverified="all planner estimates (sessions, budgets) — plan, not fact",
            status="open",
            task_id=tid,
        )
        try:
            conn = self._tasks_db()
            with conn:
                conn.execute(
                    "UPDATE task_blocks SET steps_json=? WHERE task_id=?",
                    (_json.dumps(all_steps), tid),
                )
            conn.close()
        except Exception as e:
            return f"planner: ledger steps write failed: {e}"
        return (
            f"PLAN ENVELOPE accepted ({mode}): task_id={tid} | correlation_id={corr}\n"
            f"sessions_estimate={env.get('sessions_estimate', '?')} | "
            f"single_session={env.get('single_session', '?')} | "
            f"confidence={env.get('confidence', '?')} | "
            f"steps={len(new_steps)} atomized"
            f"{f' (+{len(prior_done_steps)} already done)' if prior_done_steps else ''}\n"
            f"STEPS: {plan_lines}\n"
            f"ABORT CRITERIA: "
            f"{env.get('abort_criteria', '(none given — budget gate is the only stop)')}\n"
            f"{ck}\n"
            "EXECUTE ONLY THE STEP BELOW, run its verify check, then call "
            f"plan_step_done('{tid}', {first['n']}, evidence=<verify output>) "
            "to strike it and receive the next step. Estimates are NOT facts (P2).\n"
            f"---\n{next_prompt}"
        )

    def _plan_step_prompt(self, goal: str, all_steps: list, step: dict) -> str:
        """Build the fresh-context prompt for ONE plan step: compact ledger
        summary + the step's own packaged prompt (v0.3.2 context-ceiling tool)."""
        done = [s for s in all_steps if s.get("status") == "done"]
        pending = [s for s in all_steps if s.get("status") == "pending"]
        ledger = []
        for s in done[-8:]:  # cap ledger growth — oldest strikes fall away
            ev = str(s.get("evidence", ""))[:120]
            ledger.append(f"  ✔ step {s['n']}: {s['what']}" + (f" — {ev}" if ev else ""))
        remaining = ", ".join(str(s["n"]) for s in pending)
        header = (
            f"[PLAN {goal[:120]}]\n"
            f"LEDGER — completed:\n" + ("\n".join(ledger) or "  (none yet)") + "\n"
            f"REMAINING steps: {remaining or '(this is the last one)'}\n"
            f"YOU ARE EXECUTING STEP {step['n']} ONLY. Do not look ahead.\n"
            "---\n"
        )
        return header + step["packaged_prompt"]