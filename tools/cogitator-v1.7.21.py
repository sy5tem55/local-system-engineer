"""
title: LSE Cogitator
author: local-system-engineer
version: 1.7.21
requirements: elasticsearch==8.19.3, requests
description: Safe shell execution for the Local System Engineer (LSE) WSL2/Ubuntu 24.04 agent.
  Provides execute_command, read_file, write_file, sudo_delegation_block, search_web,
  get_github_release, get_context_status, compact_context, search_kb, index_to_kb,
  record_error, check_error_kb, record_outcome, mentor_correct, pfsense_graphql,
  pfsense_query, pfsense_log_summary, start_node_agent, stop_node_agent, search_reddit,
  call_hermes, check_hermes_inbox, hermes_cooperate, hermes_plan, skill_search, skill_record, skill_outcome, task_checkpoint,
  and task_resume. Web tools share a code-enforced anti-spiral budget.
  All commands are logged to a persistent audit file. Privileged operations are blocked
  at the code level and routed through a delegation block.

  Changelog:
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
            default=30,
            description="Subprocess timeout in seconds.",
        )
        LLAMA_SERVER_URL: str = Field(
            default="http://localhost:8080",
            description="Base URL of the llama.cpp server (for get_context_status).",
        )
        SEARXNG_URL: str = Field(
            default="http://localhost:8088/search",
            description="SearxNG JSON search endpoint (for search_web).",
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
            description="Hermes Agent gateway API URL on node3090. "
            "Gateway binds 0.0.0.0:8642 directly (verified P27). "
            "socat :8643 workaround eliminated — connect directly on :8642. "
            "Service: /etc/systemd/system/hermes-gateway.service (hermes-admin, on-demand). "
            "Start: ssh lse-admin@node3090 then sudo systemctl start hermes-gateway.",
        )
        HERMES_API_KEY: str = Field(
            default="7aa537e027e2efeda7cc660a959516eed414373c6e7b3df3d9a567e48fc3319e",
            description="Hermes Agent gateway API key "
            "(from /home/hermes-admin/.hermes/.env on node3090).",
        )
        SEARCH_BUDGET: int = Field(
            default=8,
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
        "/tmp/lse/",
        "/opt/local-se/",
    ]

    _ALLOWED_WRITE_PREFIXES = [
        "/home/",
        "/tmp/lse/",
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
        """SQLite handle for the task-block store (auto-creates schema)."""
        import sqlite3  # noqa: PLC0415

        conn = sqlite3.connect(self.valves.TASKS_DB, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS task_blocks ("
            "task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL, "
            "plan TEXT, done_steps TEXT, findings TEXT, unverified TEXT, "
            "next_prompt TEXT, checkpoints INTEGER DEFAULT 0, "
            "created_at TEXT, updated_at TEXT)"
        )
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
                    "SELECT checkpoints, created_at FROM task_blocks WHERE task_id=?",
                    (tid,),
                ).fetchone()
                n = (row[0] + 1) if row else 1
                created = row[1] if row else now
                conn.execute(
                    "INSERT OR REPLACE INTO task_blocks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
            conn = self._tasks_db()
            if task_id.strip():
                row = conn.execute(
                    "SELECT * FROM task_blocks WHERE task_id=?", (task_id.strip(),)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM task_blocks WHERE status='open' "
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

        Output filter examples:
          GOOD: execute_command("journalctl -u nginx -n 20 --no-pager")
          GOOD: execute_command("tail -20 /home/sy5/.bashrc")
          BAD:  execute_command("journalctl -u nginx")   ← no output limit
          BAD:  execute_command("sudo systemctl restart nginx")  ← use sudo_delegation_block
        """
        cwd = working_dir.strip() or self.valves.DEFAULT_WORKING_DIR

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
        if any(p in command for p in self._PRIVILEGED_WRITE_PATHS):
            if any(op in command for op in self._WRITE_OPS):
                self._log(f"WRITE-BLOCKED: {command}")
                return (
                    "BLOCKED: Write to a privileged system path detected. "
                    "Use sudo_delegation_block to delegate this to the user."
                )

        # ── Validate working directory ────────────────────────────────────────
        if not self._is_allowed_read(cwd):
            return f"BLOCKED: working_dir '{cwd}' is outside allowed read paths."

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

        self._log(f"WRITE: {path} mode={mode} len={len(content)}")
        try:
            os.makedirs(parent, exist_ok=True)
            file_mode = "a" if mode == "append" else "w"
            with open(resolved, file_mode) as f:
                f.write(content)
            return f"OK: {len(content)} characters written to {path} (mode={mode})."
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

    def _pfsense_verify(self):
        """Return verify param for pfSense requests: CA cert path or False."""
        import os as _os  # noqa: PLC0415

        cert = self.valves.PFSENSE_CA_CERT.strip()
        if cert and _os.path.isfile(cert):
            return cert
        if cert:
            self._log(
                f"PFSENSE-SSL-WARN: cert not found at {cert}, falling back to verify=False"
            )
        return False

    def pfsense_graphql(
        self,
        query: str,
        variables: dict = None,
        api_key: str = "",
    ) -> str:
        """
        Execute a GraphQL query or mutation against pfSense (pfrest.org package).
        Endpoint: POST https://pfsense.home.arpa/api/v2/graphql

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← YOU ARE HERE — ALL reads and audits
          pfsense_query      ← writes only (POST/PATCH/PUT/DELETE)
          pfsense_log_summary← firewall logs only

        GATE — use pfsense_graphql for:
          • Any question about current pfSense state or configuration
          • Firewall rules audit, DHCP leases, ARP table, routing, interfaces
          • System status, version, uptime, CPU/memory
          • Security audit, device inventory, connection map
          • Anything that reads data without changing it

        DO NOT use pfsense_query for reads — GraphQL is always preferred for reads.
        DO NOT use pfsense_log_summary for config/state — it only reads firewall logs.
        ──────────────────────────────────────────────────────────────────────────

        AUTHENTICATION:
          vault_unlock() → get_vault_secret("pfsense-api-key") → pass as api_key.

        SCHEMA INTROSPECTION PROHIBITION:
          NEVER query __schema, __type, or any introspection field.
          The full GraphQL schema is enormous — introspection returns megabytes
          and will overflow the context window exactly like the log endpoint.
          BAD:  pfsense_graphql('{ __schema { ... } }')   ← context bomb
          BAD:  pfsense_graphql('{ __type(name:"FirewallRule") { fields { name } } }')
          If you are unsure of field names, use the common queries listed below.
          For placement/ordering parameters, see pfsense_query docstring — they are
          Common Control Parameters, not GraphQL fields.

        COMMON QUERIES (field names are case-sensitive — verify with KB if unsure):
          search_kb("pfsense GraphQL fields", topic_filter="pfsense") for the full schema.

          # System info
          { SystemVersion { version } }

          # All firewall rules
          { FirewallRule { id type interface src dst srcport dstport protocol descr enabled log } }

          # Active DHCP leases (LAN device map)
          { DHCPServerLease { ip mac hostname start end } }

          # ARP table
          { ARPTable { ip mac interface hostname } }

          # Interface stats
          { NetworkInterface { name descr status mac ipaddr } }

          # Routing gateways
          { RoutingGateway { name interface gateway monitor } }

          # Multi-resource in one call (preferred — reduces tool calls)
          {
            SystemVersion { version }
            DHCPServerLease { ip mac hostname }
            FirewallRule { type interface src dst descr enabled }
          }

        LOG ENDPOINT PROHIBITION:
          NEVER query firewall logs via GraphQL or pfsense_query.
          Use pfsense_log_summary(mode="compact") for all log analysis.

        Args:
            query:     GraphQL query string (without wrapping braces if simple field list,
                       or full `query { ... }` / `mutation { ... }` syntax).
            variables: Optional variables dict for parameterised queries.
            api_key:   pfSense API key from Vaultwarden.
        """
        import requests as _req
        import json as _json

        key = api_key.strip() or self.valves.PFSENSE_API_KEY.strip()
        if not key:
            return (
                "ERROR: No pfSense API key. "
                "Call vault_unlock() → get_vault_secret('pfsense-api-key') → pass as api_key."
            )

        # Wrap bare field list in query { } if not already wrapped
        q = query.strip()
        if not q.startswith(("{", "query", "mutation", "subscription")):
            q = f"{{ {q} }}"

        url = self.valves.PFSENSE_URL.rstrip("/") + "/api/v2/graphql"
        self._log(f"PFSENSE-GRAPHQL: {q[:120]}")
        try:
            resp = _req.post(
                url,
                headers={"X-API-Key": key, "Content-Type": "application/json"},
                json={"query": q, **({"variables": variables} if variables else {})},
                verify=self._pfsense_verify(),
                timeout=20,
            )
            try:
                data = resp.json()
                if "errors" in data:
                    return f"GraphQL errors: {_json.dumps(data['errors'], indent=2)}"
                return _json.dumps(data.get("data", data), indent=2)
            except Exception:
                return f"[HTTP {resp.status_code}] {resp.text[:3000]}"
        except _req.exceptions.ConnectionError as e:
            return (
                f"ERROR: Cannot reach pfSense at {self.valves.PFSENSE_URL}. Detail: {e}"
            )
        except _req.exceptions.Timeout:
            return f"ERROR: pfSense GraphQL timed out after 20s."
        except Exception as e:
            return f"ERROR: pfsense_graphql failed: {e}"

    def pfsense_query(
        self,
        endpoint: str,
        method: str = "POST",
        payload: dict = None,
        api_key: str = "",
    ) -> str:
        """
        Write to the pfSense REST API v2 (POST, PATCH, PUT, DELETE only).
        Base URL: https://pfsense.home.arpa

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← ALL reads and audits (use this first)
          pfsense_query      ← YOU ARE HERE — writes only
          pfsense_log_summary← firewall logs only

        GATE — use pfsense_query ONLY for:
          • POST   — create a firewall rule, alias, route, etc.
          • PATCH  — update an existing object by ID
          • PUT    — replace all objects (bulk write)
          • DELETE — remove an object

        DO NOT use pfsense_query for GET/read operations.
        Use pfsense_graphql for all reads — it is always preferred for reads.
        ──────────────────────────────────────────────────────────────────────────

        KB-FIRST RULE — mandatory before constructing any payload:
          Before calling this function, call:
            search_kb("pfsense REST API firewall rules", topic_filter="pfsense")
          The KB contains the full POST/PATCH payload schema, required fields,
          valid field values, validation error shapes, and placement semantics.
          Guessing field names or required fields from training data is a protocol
          violation — the API will reject the call with a 400 error.

          GOOD: search_kb("pfsense REST API firewall rules", topic_filter="pfsense")
                → inspect schema → pfsense_query("/api/v2/firewall/rule", "POST", payload)
          BAD:  pfsense_query("/api/v2/firewall/rule", "POST", {"type":"pass",...})
                ← payload constructed without KB read — wrong field names / missing
                   required fields → 400 error → retry loop

        LOG ENDPOINT PROHIBITION — mandatory, no exceptions:
          NEVER call /api/v2/status/logs/firewall via this function.
          Use pfsense_log_summary() for all log analysis.

        WRITE ACCESS PROTOCOL — mandatory before any write:
          1. Disable Read Only: pfSense UI → System → REST API → Read Only: off
          2. Perform the write operation
          3. Verify the result with pfsense_graphql
          4. Re-enable Read Only before ending the session
          5. Log the change in CHANGELOG: timestamp + what changed
          Leaving Read Only disabled at session end is a protocol violation.

        ORDERED RULE DEPLOYMENT — placement parameter:
          Rules are evaluated top-to-bottom per interface, first match wins.
          placement=N inserts the rule at index N (0-indexed). Existing rules
          at N and below are shifted down by one.
          placement=0   → top of the list (evaluated first)
          placement=N   → before the rule currently at index N
          omit placement → appended at the bottom (evaluated last)

          CORRECT PATTERN — always read position first, then write:
            Step 1: find the target index
              rules = pfsense_graphql('{ FirewallRule { id type interface descr } }')
              # Inspect output to find e.g. deny-all at index 19
            Step 2: insert before it
              pfsense_query(
                endpoint="/api/v2/firewall/rule",
                method="POST",
                payload={
                  "type": "pass", "interface": "lan",
                  "src": "192.168.1.16", "dst": "any",
                  "dstport": "443", "protocol": "tcp",
                  "descr": "Allow Meross HTTPS",
                  "placement": 19,   ← inserts before the deny-all
                  "apply": True,
                },
                api_key=key
              )

          DO NOT introspect the GraphQL mutation schema to find placement —
          placement is a Common Control Parameter, not endpoint-specific.
          DO NOT guess the position — always read first with pfsense_graphql.

        COMMON WRITE ENDPOINTS:
          POST   /api/v2/firewall/rule          — create firewall rule
          PATCH  /api/v2/firewall/rule?id=N     — update rule at index N
          DELETE /api/v2/firewall/rule?id=N     — delete rule at index N
          PUT    /api/v2/firewall/rules          — replace all rules (destructive)
          POST   /api/v2/firewall/apply          — apply pending firewall changes
          POST   /api/v2/firewall/alias          — create alias
          PATCH  /api/v2/firewall/alias?id=N     — update alias

        SSL: Uses /opt/local-se/cert/pfsense-webgui-ca.crt (falls back to verify=False).

        Args:
            endpoint: API path, e.g. "/api/v2/firewall/rule"
            method:   POST | PATCH | PUT | DELETE (no GET — use pfsense_graphql instead)
            payload:  Dict for request body.
            api_key:  pfSense API key from Vaultwarden.
        """
        import requests  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        key = api_key.strip() or self.valves.PFSENSE_API_KEY.strip()
        if not key:
            return (
                "ERROR: No pfSense API key. Set PFSENSE_API_KEY valve or retrieve from "
                "Vaultwarden: vault_unlock() → get_vault_secret('pfsense-api-key') → "
                "pass result as api_key parameter."
            )

        method = method.upper()
        if method == "GET":
            return (
                "ERROR: pfsense_query is for writes only. "
                "Use pfsense_graphql() for all read operations."
            )
        url = self.valves.PFSENSE_URL.rstrip("/") + "/" + endpoint.lstrip("/")
        self._log(f"PFSENSE-WRITE: {method} {url}")

        try:
            resp = requests.request(
                method=method,
                url=url,
                headers={
                    "X-API-Key": key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload if payload else None,
                verify=self._pfsense_verify(),
                timeout=15,
            )
            try:
                return _json.dumps(resp.json(), indent=2)
            except Exception:
                return f"[HTTP {resp.status_code}] {resp.text[:2000]}"
        except requests.exceptions.ConnectionError as e:
            return (
                f"ERROR: Cannot reach pfSense at {self.valves.PFSENSE_URL}. Detail: {e}"
            )
        except requests.exceptions.Timeout:
            return f"ERROR: pfSense API timed out after 15s ({url})."
        except Exception as e:
            return f"ERROR querying pfSense API: {e}"

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

        YEAR INJECTION IS FORBIDDEN — if your query string contains any year (2024,
          2025, 2026, or any other), remove it before calling. No exceptions.
          WRONG: search_web("ASUSWRT-Merlin RT-BE19000 firmware 2025")
          RIGHT: search_web("ASUSWRT-Merlin RT-BE19000 firmware")
          Appending a year filters out current results and produces stale matches.
          The current date is already in your system prompt — trust it, don't bake it in.
          For version lookups of GitHub projects, prefer get_github_release instead.

        DATE-SENSITIVE QUERIES — mandatory pre-check:
          If the query involves ANY of: firmware versions, software releases, CVEs,
          hardware compatibility, product availability, or anything that changes over time:
          Step 0 (before search_kb): call execute_command("date +%Y-%m-%d") to confirm
          the actual current date. Then assess KB results for freshness:
            - KB entry older than 30 days for a firmware/CVE topic → treat as stale, go to web
            - KB entry older than 7 days for a CVE/security topic → treat as stale, go to web
            - KB entry from today → use directly, skip search_web
          This prevents accepting outdated KB entries for topics where correctness
          depends on recency. Never assume the date from training data.
        """
        import requests  # noqa: PLC0415

        self._log(f"SEARCH: {query} max={max_results}")
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            return _gate
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
                return "No results found." + _gate
            lines = []
            for r in results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("content", "")[:300]
                lines.append(f"**{title}**\n{url}\n{snippet}")
            return "\n---\n".join(lines) + _gate
        except Exception as e:
            return f"ERROR searching SearxNG: {str(e)}"

    def search_reddit(
        self,
        query: str,
        subreddit: str = "",
        max_results: int = 5,
    ) -> str:
        """
        Search Reddit for posts and discussions via SearxNG.

        Uses the site:reddit.com operator through the existing SearxNG instance on the VPS.
        No Reddit API, no OAuth, no account footprint required.

        KB-FIRST RULE — mandatory:
          Call search_kb() before this function. Only call search_reddit() on a KB miss.
          After finding useful results, call index_to_kb() to store for next time.

        REQUIRED SEQUENCE — follow exactly:
          Step 1: Write to user: "Searching Reddit for [topic]."
          Step 2: Call search_reddit() once for this topic.
          Step 3: If snippets are too short, call fetch_url() on the most relevant post URL.
          Step 4: Synthesise in ≤3 sentences. Do NOT paste raw results verbatim.
          Step 5: Call index_to_kb() with the synthesised result.

        Implementation note — Reddit engine is blocked on VPS IP (settings.yml line 39).
        This wrapper correctly routes through Google/Bing via site: operator instead.

        Args:
            query:       Search terms (e.g. "RTX 3090 thermal paste replacement")
            subreddit:   Optional subreddit without r/ prefix (e.g. "homelab", "hardware")
                         If empty, searches all of reddit.com
            max_results: Number of results to return (default 5)

        Returns:
            Formatted search results string from SearxNG, same format as search_web().
        """
        site = f"site:reddit.com/r/{subreddit}" if subreddit else "site:reddit.com"
        full_query = f"{site} {query}"
        self._log(f"SEARCH-REDDIT: subreddit={subreddit!r} query={query!r}")
        return self.search_web(full_query, max_results=max_results)

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
        """
        _gate = self._budget_gate()
        if _gate.startswith("BUDGET EXHAUSTED"):
            self._log(f"FETCH BLOCKED (budget): {url}")
            return _gate
        import requests  # noqa: PLC0415
        from html.parser import HTMLParser

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
                text = ""
                try:
                    import io  # noqa: PLC0415
                    from pdfminer.high_level import extract_text  # noqa: PLC0415

                    text = extract_text(io.BytesIO(resp.content)) or ""
                except Exception:
                    try:
                        import io  # noqa: PLC0415
                        from pypdf import PdfReader  # noqa: PLC0415

                        rdr = PdfReader(io.BytesIO(resp.content))
                        text = "\n".join((p.extract_text() or "") for p in rdr.pages)
                    except Exception:
                        text = ""
                if text.strip():
                    out = _sanitize(" ".join(text.split()))[:max_chars]
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

            parser = _TextExtractor()
            parser.feed(resp.text)
            text = _sanitize(parser.get_text())[:max_chars]
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
            return "No text content extracted." + _gate
        except Exception as e:
            return f"ERROR fetching {url}: {e}"

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
            from html.parser import HTMLParser as _HP  # noqa: PLC0415

            class _TE(_HP):
                def __init__(self):
                    super().__init__()
                    self._t = []
                    self._skip = False

                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style", "nav", "footer", "head"):
                        self._skip = True

                def handle_endtag(self, tag):
                    if tag in ("script", "style", "nav", "footer", "head"):
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip and data.strip():
                        self._t.append(data.strip())

                def get_text(self):
                    return " ".join(self._t)

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
                    text = ""
                    try:
                        import io  # noqa: PLC0415
                        from pdfminer.high_level import (
                            extract_text as _pe,
                        )  # noqa: PLC0415

                        text = _pe(io.BytesIO(resp.content)) or ""
                    except Exception:
                        try:
                            import io  # noqa: PLC0415
                            from pypdf import PdfReader as _PR  # noqa: PLC0415

                            rdr = _PR(io.BytesIO(resp.content))
                            text = "\n".join(
                                (p.extract_text() or "") for p in rdr.pages
                            )
                        except Exception:
                            text = ""
                else:
                    p = _TE()
                    p.feed(resp.text)
                    text = p.get_text()
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
        python_bin = "/home/sy5/miniforge3/bin/python3"
        if not shutil.which("python3"):
            python_bin = "python3"

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
        min_score: float = 0.72,
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
            min_score:    Cosine similarity threshold (0–1). Default 0.72.
            max_results:  Max results to return. Default 5.
            topic_filter: Optional topic tag: 'comfyui', 'wan2.1', 'searxng',
                          'llama-cpp', 'pfsense', 'infrastructure', 'openwebui'.
        """
        self._log(f"SEARCH-KB: {query}")
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
                ],
                "size": max_results,
            }
            resp = es.search(index="lse-kb", body=body)
            hits = [h for h in resp["hits"]["hits"] if h.get("_score", 0) >= min_score]
            if not hits:
                return (
                    f"KB miss — no results above threshold {min_score} for '{query}'.\n"
                    "Fall through to search_web(), then call index_to_kb() with quality results."
                )
            lines = [f"KB results for '{query}' ({len(hits)} found):\n"]
            for i, h in enumerate(hits, 1):
                s = h["_source"]
                src = s.get("source_path") or s.get("source_url") or "unknown"
                try:
                    _upd = s.get("updated_at") or ""
                    _age_d = max(
                        0,
                        (
                            datetime.now().astimezone() - datetime.fromisoformat(_upd)
                        ).days,
                    )
                    _age = f"updated {_age_d}d ago"
                except Exception:
                    _age = "age unknown"
                lines.append(
                    f"[{i}] {s['title']} | topic={s['topic']} | "
                    f"quality={s['quality_score']:.2f} | score={h['_score']:.3f} | {_age}\n"
                    f"    source: {src}\n"
                    f"    {s['content'][:5000].strip()}\n"
                )
            return "\n".join(lines)
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
                es.update(
                    index="lse-kb",
                    id=existing["_id"],
                    body={
                        "doc": {
                            "content": content,
                            "embedding": embedding,
                            "quality_score": new_q,
                            "refinement_count": existing["_source"]["refinement_count"]
                            + 1,
                            "updated_at": now,
                            "version": existing["_source"]["version"] + 1,
                            "source_url": source_url or None,
                        }
                    },
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

    def record_outcome(
        self,
        doc_id: str,
        success: bool,
        notes: str = "",
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

        Args:
            doc_id:   The doc_id field from a search_kb or index_to_kb result.
            success:  True if the procedure succeeded, False if it failed.
            notes:    Optional context: variant used, environment, what differed, etc.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"RECORD-OUTCOME: doc_id={doc_id} success={success}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
            resp = es.get(
                index="lse-kb",
                id=doc_id,
                _source=["empirical_runs", "success_count", "failure_count", "title"],
            )
            src = resp["_source"]
            runs = src.get("empirical_runs", 0) + 1
            success_count = src.get("success_count", 0) + (1 if success else 0)
            failure_count = src.get("failure_count", 0) + (0 if success else 1)
            update: dict = {
                "empirical_runs": runs,
                "success_count": success_count,
                "failure_count": failure_count,
                "last_outcome_at": now,
            }
            if notes:
                update["last_outcome_notes"] = notes
            es.update(index="lse-kb", id=doc_id, body={"doc": update})
            outcome_str = "✅ success" if success else "❌ failure"
            return (
                f"Outcome recorded: {outcome_str} | "
                f"doc='{src.get('title', doc_id)}' | "
                f"runs={runs} ({success_count} success / {failure_count} failure)"
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
            doc_id:       The doc_id of the KB entry to correct.
            correction:   The full corrected content to replace the existing entry.
            new_quality:  New quality score (0.0–1.0).
                          Use 0.95–1.0 for human-verified corrections.
        """
        from datetime import timezone  # noqa: PLC0415

        self._log(f"MENTOR-CORRECT: doc_id={doc_id} new_quality={new_quality}")
        try:
            es = self._es()
            now = datetime.now(timezone.utc).isoformat()
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
            es.update(
                index="lse-kb",
                id=doc_id,
                body={
                    "doc": {
                        "content": correction,
                        "embedding": embedding,
                        "quality_score": new_quality,
                        "refinement_count": src.get("refinement_count", 0) + 1,
                        "updated_at": now,
                        "mentor_corrected_at": now,
                    }
                },
            )
            return (
                f"Mentor correction applied: doc='{src.get('title', doc_id)}' | "
                f"quality {old_quality:.2f} → {new_quality:.2f} | "
                f"refinements={src.get('refinement_count', 0) + 1}"
            )
        except Exception as e:
            self._log(f"MENTOR-CORRECT ERROR: {e}")
            return f"mentor_correct failed: {e}"

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
            new_q = min(so_ceiling, old_q + 0.10) if success else max(0.0, old_q - 0.15)
            archived = (new_q < 0.2) and not h["_source"].get("pinned", False)
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

    def pfsense_log_summary(
        self,
        hours: int = 24,
        top_n: int = 10,
        mode: str = "compact",
        api_key: str = "",
    ) -> str:
        """
        Return a compact pfSense firewall log summary via the local log gateway.

        ── TOOL ROUTING — READ THIS FIRST ────────────────────────────────────────
        Three tools, three responsibilities. Use exactly the right one:

          pfsense_graphql    ← ALL reads and audits (config, rules, leases, ARP)
          pfsense_query      ← writes only (POST/PATCH/PUT/DELETE)
          pfsense_log_summary← YOU ARE HERE — firewall logs only

        GATE — use this function ONLY for:
          - "pfSense audit report" / "stability report" / "security report"
          - "firewall log analysis" / "what's being blocked" / "traffic patterns"
          - "is device X phoning home?" / "outbound connections from IP"
          - Any question about blocked IPs, blocked ports, or packet-level activity
          DO NOT use this for reading config, rules, leases, or system state.
          Use pfsense_graphql for config/state questions.
        ──────────────────────────────────────────────────────────────────────────

        LOG ACCESS PROHIBITION — mandatory, no exceptions:
          NEVER call pfsense_query('/api/v2/status/logs/firewall') for log analysis.
          That endpoint returns raw data (up to 2.7M tokens) which overflows the
          96k context window and terminates the session mid-response.
          NEVER call pfsense_query() or pfsense_graphql with any /logs/ endpoint.

          GOOD: pfsense_log_summary(hours=24, mode="compact")   ← gateway returns <4KB
          BAD:  pfsense_query('/api/v2/status/logs/firewall')    ← 2.7M tokens, session dies
          BAD:  pfsense_graphql('{ FirewallLog { ... } }')       ← same overflow risk

        HOW IT WORKS:
          Calls the local log gateway (http://localhost:9191) which pre-aggregates
          pfSense logs server-side before returning structured JSON.
          The gateway response is always under 32KB regardless of log volume.
          If the gateway is not running it is started automatically.

        MODE SELECTION:
          mode="compact"  (default) — dense audit summary, use for full reports (<4KB)
          mode="summary"            — structured stats only, faster for single questions

        RETURNED FIELDS (compact mode):
          pfsense.version, pfsense.uptime, pfsense.dhcp_active_leases
          firewall.total_entries_parsed, firewall.total_blocks, firewall.total_pass
          firewall.top_blocked_ips[{ip, count}]
          firewall.top_blocked_ports[{port, protocol, count}]
          firewall.interface_stats
          recent_block_sample

        PRE-CALL REQUIREMENT — mandatory, no exceptions:
          Before calling this function, retrieve the pfSense API key from Vaultwarden:
            vault_unlock() → get_vault_secret("pfsense-api-key") → pass here as api_key
          Calling without api_key when the gateway is not running will fail.
          If the gateway is already running from this session, api_key can be omitted.

        Args:
            hours:   Time window in hours (default 24).
            top_n:   Top N IPs/ports in summary mode (default 10, max 20).
            mode:    "compact" for audit reports, "summary" for quick stats.
            api_key: pfSense API key from Vaultwarden. Required to start the gateway.
        """
        import json as _json
        import subprocess

        GATEWAY_URL = "http://localhost:9191"
        GATEWAY_SCRIPT = "/opt/local-se/pfsense-gateway-tools.sh"

        def _ensure_gateway():
            """Start the gateway if not running.

            Key resolution order:
              1. api_key parameter (retrieved from Vaultwarden by LSE)
              2. PFSENSE_API_KEY env var (fallback if already set in environment)
            If none found, gateway starts keyless — pass api_key on each request.
            """
            import requests as _req
            import time as _time

            # Already running?
            try:
                r = _req.get(f"{GATEWAY_URL}/health", timeout=3)
                if r.status_code == 200:
                    return True, None
            except Exception:
                pass

            # Key comes from the api_key parameter — retrieved from Vaultwarden by LSE.
            # No secrets files. No valves. LSE calls vault_unlock() → get_vault_secret()
            # → passes result here. Fallback to PFSENSE_API_KEY env if already set.
            pf_key = api_key.strip() or os.environ.get("PFSENSE_API_KEY", "").strip()
            if not pf_key:
                # Gateway can start without key; key passed per-request via ?api_key=
                pf_key = ""

            # Start gateway with key in environment
            env = os.environ.copy()
            env["PFSENSE_API_KEY"] = pf_key
            try:
                subprocess.Popen(
                    ["bash", GATEWAY_SCRIPT, "restart"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _time.sleep(3)
                r = _req.get(f"{GATEWAY_URL}/health", timeout=5)
                if r.status_code == 200:
                    return True, None
                return (
                    False,
                    f"ERROR: Gateway started but /health returned {r.status_code}. Check /opt/local-se/logs/gateway.log",
                )
            except Exception as e:
                return False, f"ERROR: Could not start gateway: {e}"

        ok, err = _ensure_gateway()
        if not ok:
            return err or (
                "ERROR: pfSense log gateway not running and could not be started. "
                f"Run manually: bash {GATEWAY_SCRIPT} restart"
            )

        try:
            import requests as _req

            endpoint = "/compact" if mode == "compact" else "/summary"
            params = {"hours": hours}
            if mode == "summary":
                params["top"] = min(top_n, 20)
            # Forward the API key per-request — gateway uses it for pfSense calls
            # without storing it between requests (KISS: key comes from Vaultwarden each time)
            if api_key.strip():
                params["api_key"] = api_key.strip()

            r = _req.get(f"{GATEWAY_URL}{endpoint}", params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            self._log(
                f"PFSENSE-LOG-SUMMARY: gateway={mode} hours={hours} "
                f"blocks={data.get('firewall', {}).get('total_blocks', '?')}"
            )
            return _json.dumps(data, indent=2)

        except Exception as e:
            return f"ERROR: pfsense_log_summary — gateway call failed: {e}"

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
        Wake a GPU node via pfSense WoL REST API, then poll until it responds to ping.

        WRITE ACCESS NOTE:
          WoL is a POST to pfSense (/api/v2/services/wake_on_lan/send). It sends a UDP
          magic packet only — it does NOT modify pfSense config. Still requires
          pfSense read-only mode to be disabled before calling.
          After waking: re-enable read-only before ending the session.

        FULL WORKFLOW — call in order:
          1. wake_node(node)           — sends WoL + waits for ping response
          2. query_node_agent(node, …) — delegates work to the GPU node's AI agent
          3. shutdown_node(node)       — shuts the node down when done

        Args:
            node: "node3090" or "node5090"

        Returns:
            Success with boot time, or error string if timeout.
        """
        import time, subprocess  # noqa: PLC0415

        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        # Send magic packet via pfSense
        self._log(
            f"WAKE-NODE: sending WoL for {node} ({reg['mac']}) on {reg['interface']}"
        )
        wol_result = self.pfsense_query(
            endpoint="/api/v2/services/wake_on_lan/send",
            method="POST",
            payload={"interface": reg["interface"], "mac": reg["mac"]},
        )
        self._log(f"WAKE-NODE: pfSense response: {wol_result[:120]}")

        # Fast-fail: if the API call itself failed, do not waste 120s polling
        if wol_result.startswith("ERROR") or wol_result.startswith("[HTTP"):
            return (
                f"WAKE ABORTED — pfSense WoL API error (not starting poll):\n"
                f"{wol_result[:300]}\n\n"
                "Common causes:\n"
                "  • PFSENSE_API_KEY valve not set in OpenWebUI\n"
                "  • pfSense Read Only mode still enabled\n"
                "  • Endpoint mismatch (correct: POST /api/v2/services/wake_on_lan/send)"
            )

        # Poll ping — up to 120s
        hostname = reg["hostname"]
        start = time.time()
        for attempt in range(60):
            time.sleep(2)
            if attempt % 5 == 0:  # log every 10s so the tool card shows progress
                self._log(f"WAKE-NODE: waiting for {node}... {attempt*2}s elapsed")
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hostname],
                capture_output=True,
            )
            if r.returncode == 0:
                elapsed = int(time.time() - start)
                self._log(f"WAKE-NODE: {node} up in {elapsed}s")
                return (
                    f"{node} is up — boot took {elapsed}s\n"
                    f"Agent: http://{hostname}:{reg['agent_port']}/v1/\n"
                    f"Next: call query_node_agent('{node}', prompt)"
                )

        return (
            f"TIMEOUT: {node} did not respond after 120s. "
            f"WoL was sent (pfSense: {wol_result[:80]}). "
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

    def shutdown_node(self, node: str) -> str:
        """
        Gracefully shut down a GPU node via SSH.

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
            node: "node3090" or "node5090"

        Returns:
            Confirmation string or SSH error.
        """
        reg = self._NODE_REGISTRY.get(node)
        if not reg:
            return f"Unknown node '{node}'. Known: {list(self._NODE_REGISTRY.keys())}"

        hostname = reg["hostname"]
        user = reg["ssh_user"]

        if reg["os"] == "linux":
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} sudo shutdown -h now"
            )
        else:  # windows
            cmd = (
                f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "
                f"-o BatchMode=yes {user}@{hostname} shutdown /s /t 30"
            )

        self._log(f"SHUTDOWN-NODE: {cmd}")
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

    def call_hermes(self, task: str, context: str = "", no_think: bool = True) -> str:
        """
        Delegate a task to the Hermes Agent on node3090 (http://192.168.5.41:8642).
        Hermes runs Qwen3.6-27B locally and can autonomously execute tasks on node3090
        using its own tool set (shell, file, browser, image generation).

        GATE — call only when ALL of the following are true:
          1. The task requires autonomous multi-step execution on node3090.
          2. A single SSH command cannot answer or complete it.
          3. llama-server AND hermes-gateway are confirmed running on node3090.
        Do NOT call for facts answerable with one SSH command.
        Do NOT call if either service is down — diagnose first, then call.

        CRITICAL — DO NOT call_hermes during a llama-server restart:
          Hermes's inference backend IS llama-server (localhost:8080 on node3090).
          When llama-server is stopped, Hermes cannot generate responses.
          If you are restarting llama-server, the correct sequence is:
            1. call_hermes (pre-restart notification) ← llama-server still up
            2. SSH: stop llama-server
            3. SSH: start llama-server
            4. SSH: poll localhost:8080/health until ok  ← do NOT skip this
            5. call_hermes (post-restart confirmation)  ← only after health ok
          Calling call_hermes between steps 2 and 4 is a protocol violation.

        CONTEXT LOOP — if Hermes requests data in his reply (nvidia-smi, logs, etc.):
          Gather it via execute_command SSH and pass it in a follow-up call_hermes
          via the context= parameter. Do not ignore Hermes's data requests — they
          are required for him to complete the task accurately.

        GOOD: call_hermes("Check disk usage on all mountpoints and alert if any > 85%")
              ← multi-step: df + parsing + conditional logic, Hermes handles autonomously
        BAD:  call_hermes("What is the hostname of node3090?")
              ← single fact; use execute_command('ssh lse-admin@192.168.5.41 hostname')

        GOOD: call_hermes("Rotate the nginx logs and restart the service", no_think=False)
              ← complex + risky; use no_think=False so Hermes reasons before acting
        BAD:  call_hermes("Rotate the nginx logs and restart the service")
              ← no_think=True skips reasoning on a service-affecting task

        THINKING MODE:
          no_think=True  (default) — fast, no reasoning chain. Use for read-only tasks.
          no_think=False — Hermes reasons before acting. Use for write/destructive tasks.
          Skipping no_think=False on destructive tasks is a protocol violation.

        CONTEXT: pass relevant KB entries, prior command output, or constraints in context.
          GOOD: call_hermes("Update pfsense firewall rule",
                            context=read_file("/opt/local-se/kb/pfsense-firewall-rules-api.md"))
          BAD:  call_hermes("Update pfsense firewall rule")  ← no context, Hermes will guess

        AFTER CALLING: check that the returned string does not start with "ERROR:".
        If it does, report the error and do not treat the task as complete.
        Treating an ERROR: response as success is a protocol violation.

        Returns the Hermes agent response as a plain string.
        Returns "ERROR: <reason>" on connection failure, timeout, or API error.
        """
        import json as _json

        api_url = self.valves.HERMES_API_URL
        api_key = self.valves.HERMES_API_KEY

        content = task.strip()
        if context:
            content = f"CONTEXT:\n{context.strip()}\n\nTASK:\n{content}"
        if no_think:
            content += " /no_think"

        payload = _json.dumps(
            {
                "model": "default",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 2048,
            }
        ).encode()

        import urllib.request as _ureq
        import urllib.error as _uerr

        req = _ureq.Request(
            f"{api_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with _ureq.urlopen(req, timeout=180) as resp:
                data = _json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"]
                inbox = self._format_hermes_messages(data)
                reply = self._strip_hermes_marker(reply)
                return reply + inbox if inbox else reply
        except _uerr.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            return f"ERROR: HTTP {exc.code} from Hermes — {body}"
        except Exception as exc:
            return f"ERROR: Hermes call failed — {exc}"

    def _extract_content_marker(self, data: dict) -> list:
        """v1.7.19 (Path B): extract [[HERMES->LSE]]{json}[[/HERMES->LSE]] from the
        reply content and return its messages[] list. Used when the gateway can't add
        a top-level hermes_messages field, so Hermes embeds the outbox in reply text."""
        import re as _re  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            return []
        m = _re.search(
            r"\[\[HERMES->LSE\]\](.*?)\[\[/HERMES->LSE\]\]", content or "", _re.DOTALL
        )
        if not m:
            return []
        try:
            payload = _json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            return []
        msgs = payload.get("messages") if isinstance(payload, dict) else payload
        return msgs if isinstance(msgs, list) else []

    def _strip_hermes_marker(self, text: str) -> str:
        """v1.7.19: remove the [[HERMES->LSE]]...[[/HERMES->LSE]] block from reply text
        so the model sees a clean reply (the messages are surfaced separately)."""
        import re as _re  # noqa: PLC0415

        return _re.sub(
            r"\[\[HERMES->LSE\]\].*?\[\[/HERMES->LSE\]\]", "", text or "", flags=_re.DOTALL
        ).strip()

    def _format_hermes_messages(self, data: dict) -> str:
        """Format any hermes_messages[] attached to a gateway response envelope.

        Hermes -> LSE inbound channel (v1.7.15). Returns "" when none are present.
        Each item: {correlation_id, kind, priority, body, want_reply}.
        """
        msgs = data.get("hermes_messages")
        if not isinstance(msgs, list) or not msgs:
            msgs = self._extract_content_marker(data)  # Path B (v1.7.19)
        if not isinstance(msgs, list) or not msgs:
            return ""
        lines = ["", "\u2500\u2500 HERMES \u2192 LSE (inbound) \u2500\u2500"]
        for m in msgs:
            if not isinstance(m, dict):
                continue
            cid = m.get("correlation_id", "?")
            kind = m.get("kind", "notify")
            prio = m.get("priority", "info")
            body = str(m.get("body", "")).strip()
            wr = " [reply requested]" if m.get("want_reply") else ""
            lines.append(f"[{cid}] ({kind}/{prio}){wr} {body}")
        lines.append(
            "To respond to an 'ask': call_hermes(<result>, "
            "context='correlation_id=<cid>')."
        )
        return "\n".join(lines)

    def check_hermes_inbox(self) -> str:
        """Poll Hermes for any messages queued FOR the LSE (v1.7.15).

        WHY: Hermes cannot open a connection to LSE (LSE is an OWUI tool with no
        inbound listener — it only runs during a chat turn). Hermes therefore
        holds an outbox and attaches pending items as `hermes_messages` to any
        gateway reply. This tool makes the minimal no-task poll that surfaces
        them on demand; call_hermes/hermes_plan also carry them on their replies.

        CADENCE — call this:
          - at the START of a new conversation, and
          - at task boundaries (after finishing a task, before idling).

        INBOUND KINDS:
          - notify : informational; acknowledge, no action needed.
          - ask    : act on it, then call_hermes(<result>,
                     context='correlation_id=<cid>') so Hermes routes your reply
                     back to the originating task.

        Returns the formatted inbound messages, or
        "INBOX EMPTY \u2014 no pending Hermes messages."
        Returns "ERROR: <reason>" on connection/timeout/API failure. Do NOT
        treat an ERROR: response as an empty inbox.
        """
        import json as _json  # noqa: PLC0415
        import urllib.request as _ureq  # noqa: PLC0415
        import urllib.error as _uerr  # noqa: PLC0415

        api_url = self.valves.HERMES_API_URL
        api_key = self.valves.HERMES_API_KEY

        payload = _json.dumps(
            {
                "model": "default",
                "messages": [{"role": "user", "content": "__LSE_POLL__ /no_think"}],
                "max_tokens": 8,
            }
        ).encode()
        req = _ureq.Request(
            f"{api_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        self._log("HERMES-INBOX-POLL")
        try:
            with _ureq.urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read().decode())
        except _uerr.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            return f"ERROR: HTTP {exc.code} from Hermes inbox \u2014 {body}"
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: Hermes inbox poll failed \u2014 {exc}"

        inbox = self._format_hermes_messages(data)
        return inbox if inbox else "INBOX EMPTY \u2014 no pending Hermes messages."

    def _flush_voicemail(self, thread_id: str) -> str:
        """Flush a conference thread's voicemail to empty (v1.7.16, end-of-call).

        The conference (LSE -> Voicemail <- Hermes) leaves no dangling state: when
        the call ends the thread's voicemail is wiped. Best-effort DELETE in
        node3090 kanban.db; tolerant of a missing table (the persistent voicemail
        store lands with the Hermes-side outbox — until then this is a clean
        no-op). Returns "" on success/no-op, a short warning otherwise.
        """
        import subprocess as _sp  # noqa: PLC0415

        safe = "".join(c for c in str(thread_id) if c.isalnum() or c in "-_")[:64]
        sql = f"DELETE FROM lse_voicemail WHERE thread_id='{safe}';"
        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
            "-o", "BatchMode=yes", "lse-admin@node3090.home.arpa",
            "sudo", "sqlite3", "/home/hermes-admin/.hermes/kanban.db",
        ]
        try:
            r = _sp.run(cmd, input=sql, capture_output=True, text=True, timeout=10)
            if r.returncode != 0 and "no such table" not in r.stderr.lower():
                return f"flush warn: {r.stderr.strip()[:120]}"
            return ""
        except Exception as exc:  # noqa: BLE001
            return f"flush warn: {exc}"[:120]

    def _cooperate_exec(self, command: str, allow_sudo: list) -> str:
        """Gated executor for hermes_cooperate fulfilment (v1.7.17).

        Same gates as execute_command — the hard blocklist (disk wipes, rm -rf,
        fork bomb, account/credential mgmt) ALWAYS applies and can never be
        overridden — PLUS a per-conference allow_sudo allowlist: a command bearing
        sudo/su/doas runs only if EVERY such invocation is covered verbatim by an
        allowlist entry. Mirrors execute_command's run (shell, COMMAND_TIMEOUT,
        MAX_OUTPUT_CHARS truncation). Used only by hermes_cooperate.
        """
        cmd_lower = command.lower().strip()
        for blocked in self._BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                self._log(f"COOP HARD-BLOCKED: {command}")
                return f"BLOCKED: '{blocked}' is permanently forbidden (hard blocklist)."

        if any(p in cmd_lower for p in self._PRIVILEGED_PREFIXES):
            probe = " " + cmd_lower + " "
            for entry in allow_sudo:
                e = entry.strip().lower()
                if e:
                    probe = probe.replace(e, " ")
            if any(p in probe for p in self._PRIVILEGED_PREFIXES):
                self._log(f"COOP PRIV-BLOCKED: {command}")
                return (
                    "BLOCKED: privilege escalation not covered by this conference's "
                    "allow_sudo allowlist. Add the exact command to allow_sudo or "
                    "use sudo_delegation_block."
                )

        if any(p in command for p in self._PRIVILEGED_WRITE_PATHS) and any(
            op in command for op in self._WRITE_OPS
        ):
            if not any(
                e.strip() and e.strip().lower() in cmd_lower for e in allow_sudo
            ):
                self._log(f"COOP WRITE-BLOCKED: {command}")
                return "BLOCKED: write to a privileged system path (not allowlisted)."

        self._log(f"COOP-CMD: {command}")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.valves.COMMAND_TIMEOUT,
            )
            output = result.stdout or result.stderr or "(no output)"
            rc = result.returncode
            if len(output) > self.valves.MAX_OUTPUT_CHARS:
                output = output[: self.valves.MAX_OUTPUT_CHARS] + "\n... [TRUNCATED]"
            self._log(f"COOP-DONE rc={rc} len={len(output)}")
            return output if rc == 0 else f"[exit {rc}]\n{output}"
        except subprocess.TimeoutExpired:
            self._log(f"COOP-TIMEOUT: {command}")
            return f"ERROR: command timed out after {self.valves.COMMAND_TIMEOUT}s."
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: cooperate exec failed — {exc}"

    def hermes_cooperate(
        self,
        objective: str,
        max_rounds: int = 3,
        context: str = "",
        allow_sudo: str = "",
    ) -> str:
        """Run a bounded multi-round 'conference call' between LSE and Hermes (v1.7.16).

        PARADIGM: LSE -> Voicemail <- Hermes. The USER fires this on demand when a
        task genuinely needs Hermes's reasoning PLUS LSE's infra access. One fire
        runs up to max_rounds synchronous exchanges, then the voicemail is flushed
        to empty so nothing dangles into the next call.

        EACH ROUND: LSE sends the working message to Hermes (call_hermes) -> Hermes
        reasons and replies. If Hermes needs infra data it cannot reach (it has no
        SSH), it requests commands in a ```bash code block; LSE runs them through
        the SAME safety gates as execute_command and feeds the output back next
        round. The call ends when Hermes replies 'CONFERENCE COMPLETE', emits no
        command request, or max_rounds is reached.

        WHY ROUNDS EXIST: capability separation (Fable5 planner doc) — Hermes plans
        and reasons but has NO SSH to node infrastructure; LSE executes. The rounds
        let Hermes pull infra telemetry through LSE (gated) and reason on it, which
        neither party can do alone.

        IMPORTANT — the LSE *model* is not in the loop between rounds; this method
        shuttles deterministically. Hermes does the cross-round reasoning; LSE
        fulfils gated data requests. Firing this tool is a deliberate,
        human-initiated grant of GATED command execution to Hermes: every
        Hermes-requested command passes execute_command's hard blocklist, no-sudo,
        and privileged-path gates. A blocked request is reported back, not run.

        WHEN TO USE: joint diagnosis, plan-then-verify, telemetry-driven decisions.
        max_rounds caps cost — each round is a 27B round-trip on node3090. Do NOT
        call during a llama-server restart on node3090 (same restriction as
        call_hermes — the planner's backend IS that server).

        ALLOW_SUDO: comma/newline-separated EXACT privileged commands the USER has
        authorized for this conference (e.g. "sudo docker compose up -d, sudo docker
        ps"). A sudo/su/doas request runs ONLY if every such invocation is covered
        verbatim by this allowlist; otherwise it is blocked and reported back.
        Populate ONLY with commands the user explicitly approved in their request —
        never invent privileged grants. The hard blocklist is NEVER overridable.

        Returns the full conference transcript. "ERROR:" prefix on a fatal failure.
        """
        import re as _re  # noqa: PLC0415
        import time as _time  # noqa: PLC0415

        try:
            rounds = max(1, min(int(max_rounds), 6))
        except (TypeError, ValueError):
            rounds = 3
        allow_sudo_list = [
            x.strip() for x in _re.split(r"[,\n]", allow_sudo) if x.strip()
        ]

        thread_id = f"conf-{int(_time.time())}"
        message = (
            "CONFERENCE CALL with LSE (Local System Engineer). You reason and plan; "
            "LSE has the SSH/infra access you lack. If you need infra data, emit the "
            "exact commands in a ```bash code block and LSE will run them "
            "(safety-gated) and return the output next round. Reply 'CONFERENCE "
            f"COMPLETE' when the objective is met. Thread: {thread_id}.\n\n"
            f"OBJECTIVE:\n{objective.strip()}"
        )
        if context:
            message += f"\n\nCONTEXT:\n{context.strip()}"
        if allow_sudo_list:
            message += (
                "\n\nPRE-AUTHORIZED privileged commands you MAY request "
                "(others are blocked): " + "; ".join(allow_sudo_list)
            )

        transcript = [
            f"=== CONFERENCE {thread_id} (max {rounds} rounds) ===",
            f"OBJECTIVE: {objective.strip()}",
        ]
        completed = False

        for n in range(1, rounds + 1):
            reply = self.call_hermes(message, no_think=False)
            transcript.append(f"\n--- Round {n} · Hermes ---\n{reply}")
            if reply.startswith("ERROR:"):
                transcript.append("Conference aborted — Hermes call failed.")
                break
            if "CONFERENCE COMPLETE" in reply:
                completed = True
                break
            m = _re.search(
                r"```(?:bash|sh)\s*(.*?)```", reply, _re.DOTALL | _re.IGNORECASE
            )
            if not m:
                transcript.append(
                    f"\n--- Round {n} · no command request — ending conference ---"
                )
                completed = True
                break
            cmds = [
                ln.strip()
                for ln in m.group(1).splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            outputs = []
            for c in cmds:
                res = self._cooperate_exec(c, allow_sudo_list)
                outputs.append(f"$ {c}\n{res}")
            gathered = "\n\n".join(outputs) if outputs else "(no commands extracted)"
            transcript.append(f"\n--- Round {n} · LSE fulfilled (gated) ---\n{gathered}")
            message = (
                "LSE ran your requested commands (safety-gated). Results below. "
                "Continue, or reply 'CONFERENCE COMPLETE'.\n\n" + gathered
            )

        flush_warn = self._flush_voicemail(thread_id)
        status = "completed" if completed else f"max rounds ({rounds}) reached"
        tail = f"\n=== CONFERENCE END — {status} — voicemail flushed ==="
        if flush_warn:
            tail += f"\n({flush_warn})"
        transcript.append(tail)
        self._log(f"HERMES-COOPERATE {thread_id} rounds<={rounds} completed={completed}")
        return "\n".join(transcript)

    def _kanban_create_card(self, task_id: str, title: str, body: str) -> str:
        """Create the triage card for a plan envelope directly in node3090's
        kanban.db (INSERT OR IGNORE via ssh). Returns "" on success, a
        one-line error on failure. INTERNAL — called by hermes_plan only.
        Fail-open by design: a card failure must never block the envelope.

        Why direct INSERT (P24): the Hermes planner session has no
        kanban-write tool, and VALID_INITIAL_STATUSES={running,blocked} only
        gates the Python create API — the schema itself has no CHECK on
        status, and 'triage' is in VALID_STATUSES so board queries accept it.
        created_at is INTEGER epoch (NOT ISO text). idempotency_key +
        INSERT OR IGNORE make re-planning the same task a no-op.
        """
        import subprocess as _sp  # noqa: PLC0415
        import time as _time  # noqa: PLC0415

        def _clean(v: str, n: int) -> str:
            v = "".join(c for c in str(v) if c >= " " or c == "\n")
            return v[:n].replace("'", "''")

        sql = (
            "INSERT OR IGNORE INTO tasks "
            "(id, title, body, assignee, status, created_by, created_at, "
            "goal_mode, idempotency_key) VALUES "
            f"('{_clean(task_id, 64)}', '{_clean(title, 120)}', "
            f"'{_clean(body, 2000)}', 'lse', 'triage', 'lse-cogitator', "
            f"{int(_time.time())}, 0, 'hermes_plan:{_clean(task_id, 64)}');"
        )
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "BatchMode=yes",
            "lse-admin@node3090.home.arpa",
            "sudo",
            "sqlite3",
            "/home/hermes-admin/.hermes/kanban.db",
        ]
        self._log(f"KANBAN-CARD: {task_id}")
        try:
            r = _sp.run(cmd, input=sql, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return f"ssh/sqlite exit {r.returncode}: {r.stderr.strip()[:160]}"
            return ""
        except _sp.TimeoutExpired:
            return "ssh timeout (10s) — node3090 unreachable?"
        except Exception as exc:
            return f"{exc}"[:160]

    def hermes_plan(self, task: str, context: str = "") -> str:
        """
        Request a pre-flight execution plan from the Hermes planner (node3090)
        BEFORE starting a complex task. Returns the plan envelope (steps with
        per-step budgets, abort criteria, packaged starting prompt) and writes
        the initial task block so the plan survives session loss.

        GATE — call ONLY when ALL of the following are true:
          1. The user gave a FRESH multi-step task — research-shaped ("verify",
             "find all", "compare", unfamiliar domain) or >2 distinct steps.
          2. You have NOT started executing yet — this must be your first or
             second tool call for the task.
          3. You are NOT resuming carried-over work (that is task_resume).
        Do NOT call for single-fact lookups. Do NOT call mid-task — planning
        after execution has started is a protocol violation.
        Do NOT call during a llama-server restart on node3090 — the planner's
        inference backend IS that server (same restriction as call_hermes).

        GOOD: hermes_plan("Find the verbatim Goethe quote on architecture as
              frozen music and verify it against a primary source")
              ← research-shaped, spiral risk: plan first
        BAD:  hermes_plan("What is the hostname of node3090?")
              ← single fact; use execute_command. Planning it wastes a 27B round-trip.
        BAD:  10 web searches, then hermes_plan
              ← pre-flight means BEFORE execution. Protocol violation.

        AFTER A PLAN IS RETURNED — mandatory:
          Begin execution from the packaged prompt at the END of the result.
          Respect each step's web/tool budgets and the ABORT CRITERIA exactly.
          Checkpoint with task_checkpoint(task_id=<returned id>) after each step.
          Planner estimates are ESTIMATES, not established facts: never copy
          them into findings, never raise skill/KB quality from a plan (P2).
          Ignoring the abort criteria is a protocol violation.

        ON "PLANNER UNAVAILABLE":
          Proceed WITHOUT a plan: default budgets apply, checkpoint early.
          Do NOT retry hermes_plan more than once per task. The absence of a
          plan is NOT permission to skip checkpointing.

        Args:
            task:    The user's task, verbatim or lightly cleaned — do not
                     pre-digest it; the planner needs the original shape.
            context: Optional constraints, prior findings, or KB pointers for
                     the planner. Same usage as call_hermes context.

        Returns the plan summary + packaged prompt, or a string starting with
        "PLANNER UNAVAILABLE" on any failure (Hermes down, bad envelope).
        """
        import hashlib  # noqa: PLC0415
        import json as _json  # noqa: PLC0415
        import re as _re  # noqa: PLC0415

        self._log(f"HERMES-PLAN: {task[:80]}")
        corr = hashlib.sha256((task + datetime.now().isoformat()).encode()).hexdigest()[
            :12
        ]
        request = (
            f"PLAN REQUEST (intent=plan, correlation_id={corr}):\n"
            f"{task.strip()}\n\n"
            "Respond with ONLY the plan envelope JSON per your PLANNER "
            "CONTRACT memory entry (v=1, intent=plan). No prose, no markdown "
            "fences — a single JSON object."
        )
        reply = self.call_hermes(request, context=context, no_think=False)
        if not reply or reply.startswith("ERROR:"):
            return (
                "PLANNER UNAVAILABLE — proceed with default budgets, "
                f"checkpoint early. ({(reply or 'no reply')[:160]})"
            )
        m = _re.search(r"\{.*\}", reply, _re.DOTALL)
        if not m:
            return (
                "PLANNER UNAVAILABLE — no JSON envelope in Hermes reply. "
                "Proceed with default budgets, checkpoint early."
            )
        try:
            env = _json.loads(m.group(0))
        except Exception:
            return (
                "PLANNER UNAVAILABLE — envelope JSON failed to parse. "
                "Proceed with default budgets, checkpoint early."
            )
        packaged = str(env.get("packaged_prompt", "")).strip()
        steps = env.get("steps") or []
        if not packaged or not steps:
            return (
                "PLANNER UNAVAILABLE — envelope missing packaged_prompt "
                "or steps. Proceed with default budgets, checkpoint early."
            )
        tid = str(env.get("task_id") or hashlib.sha256(task.encode()).hexdigest()[:8])
        plan_lines = "; ".join(
            f"step {s.get('n', '?')}: {s.get('what', '')} "
            f"(web={s.get('web_calls', 0)}, tools={s.get('tool_calls', 0)}, "
            f"verify: {s.get('verify', 'NONE')})"
            for s in steps
        )
        ck = self.task_checkpoint(
            goal=task.strip()[:300],
            plan=plan_lines,
            done="",
            findings="",
            next_prompt=packaged,
            unverified="all planner estimates (sessions, budgets) — plan, not fact",
            status="open",
            task_id=tid,
        )
        card_err = self._kanban_create_card(
            tid,
            task.strip(),
            f"PLAN {corr}\n{plan_lines}\nABORT: "
            f"{env.get('abort_criteria', '(none)')}",
        )
        card_line = (
            "kanban: triage card created on node3090 (or already present)"
            if not card_err
            else f"kanban card_error: {card_err} (fail-open - plan proceeds; "
            "create the card manually if board tracking matters)"
        )
        return (
            f"PLAN ENVELOPE accepted: task_id={tid} | correlation_id={corr}\n"
            f"sessions_estimate={env.get('sessions_estimate', '?')} | "
            f"single_session={env.get('single_session', '?')} | "
            f"confidence={env.get('confidence', '?')}\n"
            f"STEPS: {plan_lines}\n"
            f"ABORT CRITERIA: "
            f"{env.get('abort_criteria', '(none given — budget gate is the only stop)')}\n"
            f"{ck}\n"
            f"{card_line}\n"
            "EXECUTE NOW from the packaged prompt below. Respect per-step "
            "budgets and abort criteria. Estimates are NOT facts (P2).\n"
            f"---\n{packaged}"
        )