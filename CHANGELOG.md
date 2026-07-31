# LSE Changelog
> Append-only. One entry per session. Never edit past entries.
> Format: `## YYYY-MM-DD — <what shipped>`

---

## 2026-07-27 (Codex): TRAUM GUI/control-plane redesign approved and documented

- Approved a GUI-first TRAUM surface in the Goethe Console for canonical run
  history, typed run/pass controls, redacted logs, acknowledgement/archive,
  Human Gate decisions, read-only timer status, and learning-lift monitoring;
  CLI use remains expert recovery, deployment, and isolated evaluation.
- The design keeps `NULL`, `BLOCKED`, and `FAILED` distinct, retains the
  2026-07-17 and 2026-07-20 legacy failures as evidence while making terminal
  history acknowledgeable/archivable, and automates malformed, duplicate,
  superseded, and stale proposal lifecycle decisions before human review.
- A/B reporting separates `analysis_complete` from
  `promotion_eligible`. Historical v1 remains protocol **LOSS** with causal
  interpretation **INCONCLUSIVE**; continuous decision-to-outcome wiring is
  still `not_connected`, and no auto-apply policy is enabled.
- Durable UTC run deadlines and attempt leases now fence post-restart
  admission/recovery: expired work becomes `BLOCKED`, its `STAGED`, `PENDING`,
  and `DEFERRED` proposals become `SYSTEM_REJECTED`, and late publication is
  rejected. The recovery path never guesses from a PID or replays a semantic
  apply.
- **Unchanged control boundary:** Permissions — Pending Approvals, Active
  Grants, and the sudo delegation/grant-synchronization workflow are unchanged;
  TRAUM neither creates nor consumes those authorities.

## 2026-07-23 (Codex): Goethe Console v0.3.0 — complete, scrollable Task Ledger

- Removed the API's 25-task cap and the dashboard's 12-task slice, so every
  task block is available in the Task Ledger.
- The task table now has a fixed-height, wheel-scrollable viewport with a
  visually hidden scrollbar, contained overscroll, keyboard focus, and a
  sticky header.
- Added a confirmed Delete column. The token-gated endpoint accepts one exact
  task ID and atomically snapshots the complete row into
  `task_blocks_deleted` before deleting it from the active ledger.

## 2026-07-23 (Codex): Goethe Console v0.2.2 — delete invalid permission requests

- Unapprovable legacy sudo requests can now be permanently deleted from the
  Console individually, or cleared together with **Delete all**.
- Both delete paths validate request state and sudo safety again on the server.
  Approve/deny remains the lifecycle for valid requests, while active grants
  remain revocable only; deletion cannot cross those boundaries.
- Deleted request details remain represented in the permission audit log.

## 2026-07-23 (Codex): Goethe v0.4.9 — fail-closed exact sudo grants

- **Root cause fixed at both boundaries.** The privileged-prefix guard no
  longer files approvable requests for pipelines, redirects, chained commands,
  shell expansion, or non-`sudo` escalation forms. `goethe_perms` independently
  rejects the same unsafe patterns at request, grant, approval, match, and
  sudoers-render time.
- **Sudoers output is now exact.** Stored patterns omit the leading `sudo`;
  executables must resolve through a root-controlled, non-user-writable path;
  arguments are exact and escaped; commands with no arguments render an
  explicit `""`; wildcard/prefix grants are unsupported.
- **Unsafe legacy rows fail closed.** They remain visible and revocable, but
  are labeled `NOT INSTALLABLE` by the CLI/Console and render only as
  `# SKIPPED` comments. Approval is atomic and duplicate active grants dedupe.
- **Operator surface corrected.** The Console disables approval of invalid
  legacy requests and explains that only valid exact grants are installed by
  `goethe-perm sync-sudoers`.
- **Verification:** 39 focused permission/UI tests passed, dashboard JavaScript
  syntax checked, 321 non-ES tests passed, and a copied production permissions
  DB generated a comments-only policy that `visudo -cf` accepted. The broader
  suite reached 267 passing tests before its live Elasticsearch fixture timed
  out; the two empty test indices left by that fixture were removed and cluster
  health returned green.

## 2026-07-21 — Goethe v0.4.8 — planner sync revert (v0.4.6 async split reverted)

- Reverted d314e60: async planner (plan_status(), wait= param, plan_status/plan_result ledger columns, async tests) removed. planner() returns a plan directly again.
- KEPT: v0.4.5 timeout work (120→240s, Ollama stage removed) and v0.4.7 docstring reorder.
- Rationale: async split was a usability regression — turned a one-call tool into a two-call protocol requiring the model to execute a poll loop it learned about from a truncated docstring.
- Net effect vs v0.4.4: same one-call interface, roughly double the generation budget, MANDATORY TRIGGER block visible to the model.
- Transport ceiling above ~240s remains UNSOLVED and deliberately left that way.

## 2026-07-21 — Goethe v0.4.7 — planner docstring reordered above the MCP description cut

- Field report: "get a plan to enable IPv6 on Home Assistant" produced a hand-written prose plan and no planner() call at all.
- Root cause: goethe_mcp.py registers tools with description=__doc__[:1024]; planner's docstring was 7,408 chars, so 86% was discarded — including the MANDATORY TRIGGER block at char 1,974.
- Fix: reordered so MANDATORY TRIGGER (char 136) and ASYNC poll contract (char 589) both complete inside the 1024-char window.
- Also: goethe_mcp.py now uses inspect.getdoc() instead of __doc__ — reclaimed ~240 chars of leading whitespace per tool (8,768 chars across 39 tools).
- NOTE: 29 of 39 tools are still over the 1024 cut — planner is fixed, the rest not audited yet.

## 2026-07-21 — Goethe v0.4.6 — planner async by default (SHIPPED AND REVERTED IN v0.4.8)

- planner() now seeded the ledger, handed generation to a daemon thread, returned a task_id receipt in under a second; new plan_status(task_id) collected the finished plan.
- planner(wait=True) kept the old synchronous path for tests and callers with a long timeout.
- Two ledger columns added (plan_status, plan_result) via the existing migration.
- Chosen over shrinking the envelope: measured field breakdown is 28% packaged_prompt prose and 72% atomization, so trimming to fit buys little.
- Status: REVERTED in v0.4.8 due to usability regression.

## 2026-07-21 — Goethe v0.4.5 — planner timeout/cascade fix (LSE-debugged)

- Intermittent "planner failed, never clear why" traced to v0.3.3: max_tokens raised 2048→8192 but call timeout stayed at 120s. At ~42 tok/s on node3090 that is a hard ~5,000-token delivery ceiling.
- Reproduced: a complete 8-step envelope = 5,231 tokens in 125.3s, killed at 120s.
- Fixes: (1) timeout 120→240, sized to the 8,192 the request already allows; (2) finish_reason=="length" now logged as truncation instead of "JSON parse failed"; (3) Ollama CPU fallback removed (0 successes across 5 logged invocations, +300s per failure); (4) all-slots-busy now logged.
- max_tokens deliberately NOT lowered to 4096: that truncates real envelopes (measured 5,231).

## 2026-07-21 — Goethe v0.4.4 — PH4-1 DATA — run_tests "data" scope

- Added run_tests "data" scope (dataset_lint in scope=all).

## 2026-07-18 — Goethe v0.4.3 — PH3-4 docstring optimizer pass (SCRIBE-5)
## 2026-07-18 (Cowork): PH5-1/PH5-2 — Goethe v0.4.1: TrustPolicy + goethe_kb.py extraction; P0 closed (except rotation); neural-search claim verified live

- **Neural-search verification (operator request):** all 5 design phases confirmed live on node3090 — lazy sidecars (cold 4.1 s / warm 137 ms), lse-web-idx 44,751 chunks, :8092 API active, `!nl` SearxNG engine returns neural results, recrawl timer armed. Finding: `sear_primary` was down post-reboot (manual pre-reboot stop cleared `restart: always` trigger) — restarted, :8088 → 200.
- **P0-1/P0-3/P0-4/P0-6 closed** (commits `be53e52`, follow-up): VERSION.md live-reconciled (goethe_mcp was recorded v1.9.3, live `__version__` 1.11.1; llama-server LUCIFER `bf2c86ddc` v20 / node3090 `e8f19cc0a` v64 — both recorded builds obsolete); 29-file final purge → `.backups/pre-purge-20260718/`; OWUI grep-audit clean (historical docs only). **P0-2 rotation deferred to end-of-roadmap batch per operator** — but launcher v2.1.3 already implements the binding/CORS/secrets-location hardening; tokenless curl → 401 verified today.
- **PH5-1 (REFACTOR-1):** `TrustPolicy` in new `tools/goethe_kb.py` — single `TIER_CEILING` + `ceiling(tier, default)`; kills the 3× duplicated dicts; defaults preserved ("inferred" for index_to_kb/skill_record, "secondary" for skill_outcome).
- **PH5-2 (REFACTOR-2):** KB surface (goethe.py 4663–6067: `_embed`, `_es`, `search_kb`, `index_to_kb`, `record_error`, `check_error_kb`, `_resolve_kb_id`, `record_outcome`, `mentor_correct`, `kb_verify`, `mentor_demote`, `skill_search`, `skill_record`, `skill_outcome`) moved verbatim to `KBMixin`; `class Tools(KBMixin)`. goethe.py 7238 → 5851L. **Release gates: MCP tool-list diff EMPTY (38 pre/post via `--list` on HEAD copy vs working tree); contract tests 420/420.** One extraction bug caught by the suite (55 failures: block relied on goethe.py module-level `datetime`/`json`/`os`/`Optional` imports) — fixed, re-run green. Gateway restarted on v0.4.1 via `start-goethe.sh`.
- Legacy `scripts/` harness findings (pre-existing, unchanged): `gymnasium` missing (challenge-env tests), `test_hermes_inbox.py` references purged `cogitator-v1.7.15.py`.

## 2026-07-18 — Goethe v0.4.3 — PH3-4 docstring optimizer pass (SCRIBE-5)

- time_check delegation-edge GOOD/BAD, run_tests scope-misuse GOOD/BAD, assert_state explicit GATE.
- Audit: 0 FAIL, 3 WARN fixed, planner/kb_verify/mentor_demote already exemplary.

## 2026-07-18 — Goethe v0.4.2 — PH5-3 origin tags

- index_to_kb origin= param added.
- TrustPolicy.apply_origin asymmetric trust rule (web never mints ground_truth).

## 2026-07-04 — Goethe v0.2.8 — planner PATH 3 — VRAM-aware Gemma GGUF spawn
## 2026-07-15 (Codex): TRAUM production reconciliation — hardened Thread 4, Qwen/1024 index alignment, tracked timer, 420-test release gate

Corrective close after auditing LSE commits `7348aef`, `fc85468`, and `87026fb` against `docs/traum-dreaming-plan.md`, the live stack, and the newer hardened work that had existed only in the timer checkout.

- **Hardened Thread 4 restored to the authoritative checkout.** Ported lock/session guards, per-run LLM and wall-clock budgets, crash discipline, pass-scoped artifacts, queue source-file resolution, secret redaction, threat model, A/B design/report, and loaded-model-aware node3090 routing.
- **Unsafe LSE additions retired.** No Elasticsearch delete primitive is exposed. Quarantine remains review/proposal policy, not a hard-delete path. The generic nightly ledger summarizer was not retained: Prompt 3.3 is satisfied by the cited, schema-aware one-off `kb/ledger-mining-proposals.md`. `DREAM_AUTO_APPLY` remains empty after the recorded A/B **LOSS** (A=53/60, B=51/60).
- **Embedding contract aligned.** Goethe, dream runner/apply/digest, tests, and launcher now use `qwen3-embedding:0.6b` and `lse-errors-1024`. Live aliases/counts at verification: `lse-kb` → `lse-kb-1024` (56), `lse-skills` → `lse-skills-1024` (2), `lse-errors-1024` (44 before the reconciliation error records). A fresh Goethe instance produced a 1024-dimensional vector and wrote error records successfully.
- **Gateway launcher repaired.** `start-goethe.sh` v2.1.3 again launches detached via `setsid nohup`, redirects stdin/logs, then reaches the port/process/PID verification steps. Live restart produced exactly one HTTP gateway process with the Qwen model override.
- **Timer made repository-owned and fail-visible.** Added `scripts/systemd/goethe-dream.{service,timer}` plus executable `tools/run-dream-cycle.sh`. Installed unit runs `/home/sy5/projects/local-system-engineer`, has no ignored `ExecStart`, uses one 45-minute cycle timeout, and is enabled/active. Manual acceptance start returned `Result=success`; the five passes correctly skipped inside the 30-minute active-session window and the digest refreshed.
- **Release proof.** `bash -n` clean; `systemd-analyze verify` clean; authoritative `pytest tests/ -q`: **420 passed**; direct Goethe `run_tests(scope=all)`: **KB PASS, retrieval PASS, harness/tests PASS**. The T1 feedback harness now uses `sys.executable`, eliminating PATH-dependent Miniforge failures.

Unrelated modified/untracked logs, prompts, backups, and operator artifacts in the authoritative checkout were preserved and not staged.

## 2026-07-15 (Cowork): TRAUM Thread 4 (TRAUM-AUTO) — dream operations hardened: secret redaction, quarantine passes, proposal queue with expiry, systemd timer, ledger mining, auto-apply earn path, digest prompt-rule counting

Thread 4 close. All 9 remaining dream operations implemented and tested live against LUCIFER.

- **Secret redaction (3 rules, 426/9609 events redacted).** `dream_runner.py` now redacts sensitive tool outputs (`vault_*`, `get_vault_secret`, `set_vault_secret`) before writing to episode JSONL — prevents credential leakage into the dream corpus. 3 redaction patterns covering 426 of 9,609 audited events.
- **Pass-scoped filenames.** Each dream pass now writes to `$DREAM_DIR/YYYY-MM-DD/report-<pass>.md` and `proposals-<pass>.jsonl` (e.g. `report-dedup.md`, `proposals-insights.jsonl`) — eliminates filename collisions when multiple runs occur on the same day.
- **Quarantine-delete-request pass.** `dream_runner.py` scans `lse-kb` for quarantined docs (stale=true, quality=0.2) and generates delete proposals for human review — closes the KB-DECAY-1 quarantine→deletion loop. Live run: 0 quarantined docs found.
- **dreamed_at auto-stamp.** `dream_apply.py` now stamps `dreamed_at` on session manifest rows during apply — prevents re-dreaming already-processed sessions on crash recovery. 50 sessions stamped in initial run.
- **Proposal queue with 14-day expiry.** `dream_apply.py --queue` lists pending human-gate proposals across all dream runs (oldest first, grouped by type). Proposals older than 14 days auto-expired with reason. 28 pending proposals from 4 files at close.
- **systemd timer (goethe-dream.timer active).** `start-goethe.sh` updated with quarantine pass integration. Timer fires nightly at 03:30 with 15m random delay — VRAM-aware fallback to Ollama/CPU path if node3090 GPU busy.
- **Ledger mining.** `dream_runner.py` now reads `tasks.db` planner ledger and generates kb-fact proposals from completed tasks' evidence fields. 10 kb-fact proposals from 49 done tasks in initial run.
- **Auto-apply earn path.** `dream_apply.py` eval DB initialized with `--earn-status` flag — tracks per-type success/failure rates for the 2-consecutive-week zero-rejected-in-hindsight promotion bar (DESIGN.md §7). No types auto-promoted yet (eval period not started).
- **Digest prompt-rule counting.** `dream_digest.py` now counts pending proposals by type and surfaces ⚠ warning when `prompt-rule` proposals exist. Type breakdown shown in digest header.

**Files modified:** `tools/dream_runner.py` (+quarantine pass, +ledger-mining pass, +sessions writing, +redaction, +pass-scoped filenames), `tools/dream_apply.py` (+es_delete dispatch, +dreamed_at stamping, +queue mode, +earn path), `tools/dream_digest.py` (+prompt-rule counting), `tools/goethe.py` (minor), `tools/start-goethe.sh` (+quarantine pass). Backups at `.bak.step5`.

**Deploy note:** systemd timer `goethe-dream.timer` active. No gateway restart required (dream tools are offline, invoked by timer).

## 2026-07-13 (Codex): TRAUM end-to-end acceptance + slot-aware dreamer routing (dream_runner v0.4.1)

- Ran all five dream passes against live read-only inputs with artifacts isolated
  under `/tmp/lse`; verified digest, queue, dry-run apply, and invariant rejection
  without a production KB write.
- Found the default 2,000 MiB VRAM gate misclassified an idle, already-loaded
  llama-server as busy (model allocation left 1,128 MiB free), forcing CPU Ollama
  and a 300-second timeout.
- `dream_runner.py` now reads llama-server `/slots`: an idle loaded slot is
  reused, an active slot falls back to CPU, and free VRAM remains the fail-closed
  fallback only when slot state is unavailable.
- Regression coverage expanded to 412/412 passing tests (14 focused routing
  contracts), followed by a default-settings live sandbox rerun.
- Updated the historical TRAUM plan to implemented/accepted status and added
  `docs/dreaming/KB-ENTRY-PROMPT.md` for connected LSE and portable users.

## 2026-07-13 (Cowork, cont'd): TRAUM Thread 4 CLOSE (Prompts 4.9 + 4.10) — **WORKSTREAM COMPLETE; the v0.4.0 line is the TRAUM era.** 408/408 tests; nightly loop live; tonight's dream reviews its own construction

- **Prompt 4.9 — documentation pass, every command executed live first**:
  `docs/07-operations-runbook.md` §10 "Dreaming operations" (5-minute morning
  review loop, timer health, failed-night escalation + lock handling,
  re-dreaming a session, provenance tracing doc→dream→episode, path table —
  all 8 command groups run on LUCIFER 2026-07-13 before being written down);
  `VALVES.md` +17 Thread-4 valve rows (lock/budgets/activity-guard,
  node3090 SSH VRAM-gate quartet, patterns/insights knobs) and the
  `DREAM_AUTO_APPLY` row re-pointed at the §7.4 decision; `README.md`
  repo-layout updated (dream tools, eval TRAUM artifacts, lse/services,
  docs/dreaming).
- **Prompt 4.10 — close**:
  - **`.gitignore` decision (flagged at 4.5, decided now):** line 44's
    blanket `eval/` → `eval/*` + 5 explicit re-includes (frozen gold set,
    v35 harness, A/B design doc, its verdict report, v3.5 suite text) —
    a directory-level ignore can't be negated from inside, so the class
    stays ignored while the citable artifacts become trackable for the
    first time ever.
  - **Full test pass: `pytest tests/ -q` → 408 passed** (includes the 290
    dream-scoped + kb contracts run against live ES).
  - CURRENT-STATE.md TRAUM row: workstream complete, eval verdict recorded
    (LOSS, methodologically inconclusive), interpreter/client-drift note
    (units on system python3 / ES client 9.4.1; still no requirements.txt
    pinning — standing risk from the 2026-07-11 drift).
  - ROADMAP.md reconciled: PH4-2 [x] (all 4 TRAUM threads), SCRIBE-4 [x]
    (continuous self-measurement, stronger than the monthly ask), PH5-2
    urgency re-assessed (goethe.py 7,228 lines — the stale "before v0.4"
    bar is breached; next goethe.py-touching workstream is blocked on the
    extract), PH5-3 [~] (dreaming chapter exists; P0-2 example + real
    origin-tags still open).
  - Prompt 4.10's last act, rewritten for the live timer: tonight's
    03:32 unattended cycle processes THIS workstream's own sessions —
    the loop reviewing its own construction is the acceptance test; read
    `/opt/local-se/dreams/latest-digest.md` tomorrow morning.
- **Known-open at close (named, not hidden):** operator credential rotation
  (the sshpass password redaction now scrubs is still live in the log
  file and wherever it authenticates); ES client unpinned (add
  requirements pin with PH5-2); eval re-run per report §7 is the entry
  ticket for any future DREAM_AUTO_APPLY promotion; origin-tags
  (PH5-3) remain the structural gap the threat model leans hardest on.

---
## 2026-07-13 (Cowork): TRAUM Thread 4 (TRAUM-AUTO), Prompts 4.1-install + 4.8 — nightly timer LIVE on LUCIFER; autonomy decision recorded: DREAM_AUTO_APPLY stays empty, nightly cadence retained

- **Prompt 4.1 gap closed — timer installed and enabled live** (the 4.1
  session had written `lse/services/goethe-dream.{service,timer}.tmpl` but
  never installed them; `systemctl` confirmed `Unit goethe-dream.timer could
  not be found` before this). Rendered live units from the templates
  (ExecStart → `/usr/bin/python3 /home/sy5/local-system-engineer/tools/
  dream_runner.py`, one per pass ×5; system python3 chosen deliberately —
  its elasticsearch client (9.4.1) is the one verified against the live ES
  9.4.3 server, while the owui venv still carries 8.19.3), verified with
  `systemd-analyze verify`, smoke-tested the runner end-to-end (patterns
  pass, dry-run, real corpus: 13 sessions, lse-kb=376), then installed via
  operator sudo-delegation: `enabled`, `active (waiting)`, first unattended
  fire **2026-07-14 03:32:12 CEST**. Sandbox cwd `/var/lib/lse/dream-sandbox`
  created per the template's install notes.
- **Prompt 4.8 — autonomy decisions recorded in DESIGN.md §7.4** (the
  decision log the promotion rule requires be written BEFORE any valve
  change): `DREAM_AUTO_APPLY` stays `""` on four independent grounds
  (§7.3 2-week measurement window only starts with tonight's first
  unattended cycle; the A/B eval's pre-registered LOSS verdict is
  methodologically inconclusive and in any case not positive evidence FOR
  promotion; threat-model finding that origin-tag laundering protection is
  a blunt ceiling with origin=web tagging unimplemented; Thread 2's gate
  rejected 8/11 calibration proposals). Cadence: **nightly retained**, with
  a recorded revisit trigger (4 consecutive all-null weeks → 2-3×/week) and
  the eval re-run precondition (≥1 week real elapsed dreaming + multiple
  trials/pinned sampling) named as the entry ticket for ever revisiting
  promotion.
- Verification audits this session (before any new work): 4.2/4.3/4.4
  guardrail/crash/queue implementations re-tested (91 dedicated tests
  green), 4.5/4.6 artifacts verified (gold-set sha256 matches the frozen
  value in `traum-ab-design.md`; the LOSS verdict's `record_error`
  entry `6122c47830260f4e` confirmed present in live `lse-errors`),
  4.7's 22 cited test node-id groups re-collected against the live test
  tree — all still valid.

---
## 2026-07-12 (Cowork, cont'd x11): TRAUM Thread 4 (TRAUM-AUTO), prerequisite fixes — the two Thread 3 close findings closed before 4.8: agent-log secret redaction in the patterns pass; pass-scoped report/proposals filenames end the multi-pass day-dir clobber

- **`tools/dream_runner.py` v0.11.0 → v0.12.0**:
  - **Agent-log secret redaction** (`redact_log_text()` + `_REDACT_RULES`,
    applied inside `parse_agent_log_lines()` — one choke point, every
    downstream consumer sees only redacted text). The Thread 3 close's live
    run surfaced a plaintext password in a repeated `sshpass -p` command;
    `agent_commands.log` is written verbatim with no redaction of its own, so
    the dreamer scrubs at READ time, before anything reaches `patterns.json`,
    report files, or an off-host LLM prompt. Rules 1+3 are
    `goethe_mcp.py`'s episode-journaling regexes verbatim (`Bearer …`,
    `<ident-containing-key/token/secret/password>=<12+-char blob>`); rule 2
    adds the credential-as-CLI-flag shape (`sshpass -p`, `--password`,
    `--user`, `--token`, `--api-key`, `--secret`) the assignment rule can't
    catch. Bare `-u` deliberately NOT matched (`sort -u`/`python -u` would
    lose innocent arguments and corrupt the frequency table).
  - **Pass-scoped output filenames**: `write_report()` now writes
    `report-<pass>.md` / `proposals-<pass>.jsonl` (and the crash writer
    `report-<pass>.md`), not the shared `report.md`/`proposals.jsonl` —
    the Thread 3 close found a full multi-pass cycle silently discarded
    earlier passes' REAL pending proposals via per-pass overwrite (recovered
    by hand that close; 3.8's append-mode `null-results.jsonl` fixed null
    verdicts only). Re-running the SAME pass still overwrites only its own
    snapshot.
- **`tools/dream_digest.py` v0.2.0 → v0.3.0**: new `day_dir_files()` — union
  of pass-scoped + legacy shared names (Threads 2–3 day-dirs stay readable);
  `gather_top_insights()` scans every `report*.md` in a day-dir (union of
  insights, confidence-sorted), `gather_pending()` every `proposals*.jsonl`.
- **`tools/dream_apply.py` v0.3.0 → v0.4.0**: `gather_queue()` (Prompt 4.4's
  queue) and `render_group()`'s REPORT reference both glob via
  `dream_digest.day_dir_files()`.
- **Tests**: `tests/test_dream_patterns.py` +7 (redaction rules, parse-time
  application, redacted-command frequency stability, innocent-flag
  non-matches); `tests/test_dream_engine.py` +2 (pass-scoped filenames,
  two-pass no-clobber); `tests/test_dream_digest.py` +2 (`day_dir_files`
  union/ordering, `gather_pending` across pass files);
  `tests/test_dream_crash_discipline.py` fault-injection expectation updated
  to `report-patterns.md`. `pytest tests/ -k dream -q`: **290 passed**.
- Deferred: operator must still rotate the surfaced `sshpass` credential and
  move it to Vaultwarden (redaction protects future dreams, not the log
  file itself, which remains on disk unredacted).

---
## 2026-07-12 (Cowork, cont'd x10): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.7 — dreaming threat-model addendum; created `docs/threat-model-kb.md` (REFACTOR-4 had not landed); 4 named threats + 2 carried from DESIGN.md, each mitigation mapped to contract test by name, gaps stated honestly

- **Created `docs/threat-model-kb.md`** (did not exist — confirmed REFACTOR-4/
  PH5-3 unlanded on ROADMAP.md before creating it, per the prompt's own
  "creating the file if REFACTOR-4 hasn't landed" instruction). Structured
  as the Shostack 4-question frame (what we built / what can go wrong / what
  we do / did it work), matching and maturing the "mini pass" DESIGN.md §5
  already had (Thread 1, Prompt 1.2) — that section explicitly said it was
  "a draft input" to this doc, not a substitute; this prompt is that fold-in.
  §5 of the new file is a deliberate stub for the broader REFACTOR-4 scope
  (P0-2 gateway exposure, tier self-grant, NTP spoof, ES-unauthenticated)
  that Prompt 4.7 did not ask for — left open on ROADMAP.md, not silently
  claimed as done.
- **Four threats written per the prompt's exact list**: (1) poisoning via
  web-content laundered through episodes into dreamed facts — including the
  honest finding that `origin=web` tagging (the other half of the
  REFACTOR-4 asymmetric-trust rule this is supposed to extend) **does not
  exist anywhere in the live `index_to_kb` write path** (`grep`-verified),
  so today's real mitigation is the blunter "dream can never mint
  ground_truth regardless of source," not source-aware laundering
  detection; (2) prompt-injection persisted in episode JSONL replaying into
  the dreamer on every future run that reads that session, not just the
  fetch-time one; (3) gate fatigue, tied explicitly to how it's the actual
  delivery mechanism for (1) and (2) reaching `lse-kb`; (4) dreamer endpoint
  compromise — `GOETHE_DREAM_LLM_URL` has no allowlist/identity check, so
  the real mitigation is blast-radius containment (read-only ES client,
  budget caps, crash discipline), not endpoint verification. Plus the two
  DESIGN.md §5 already had (secret leakage, auto-apply scope creep), carried
  forward and re-verified rather than re-derived.
- **Every mitigation mapped to a contract test by name**, and every citation
  spot-checked with `pytest --collect-only` against the live test files
  before writing it down (`tests/test_dream_engine.py`,
  `tests/test_dream_guards.py`, `tests/test_dream_crash_discipline.py`,
  `tests/test_dream_apply_queue.py`, `tests/test_dream_corpus.py` — 127
  collected test node-ids verified, zero typos/renamed tests in the doc).
- **Three real gaps found and stated plainly, not glossed over**: no
  dedicated test for the verbatim-quote ≥20-char rule as its own case; no
  test/allowlist for `GOETHE_DREAM_LLM_URL` endpoint identity; the
  "secret-scan CI check" DESIGN.md §5 described as a mitigation **was never
  actually built** — confirmed no `.github/workflows/` exists in this repo
  at all. Recorded as open items with concrete follow-up suggestions, not
  fixed in this prompt (documentation scope).

Deferred to later prompts:
- Closing the three gaps above (test additions, `origin=web` tagging via
  REFACTOR-4, endpoint allowlisting) — out of scope for a doc-writing prompt.
- Prompt 4.8 (autonomy tuning — the LOSS verdict from 4.6 plus this threat
  model are both direct inputs now), 4.9 (runbook), 4.10 (Thread close).

## 2026-07-12 (Cowork, cont'd x9): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.6 — ran the A/B eval, verdict LOSS (`eval/eval-report-traum-1.md`); root cause identified as methodological (no elapsed dreaming window + model sampling variance), not a bad KB write; `record_error` filed; `DREAM_AUTO_APPLY` left empty

- **Executed the eval** per `traum-ab-design.md`: Condition A = `lse-kb`/
  `lse-errors`/`lse-skills` cloned document-for-document (mapping + `_id` +
  `_source`, trust fields intact) into a disposable `elasticsearch:9.4.3`
  container (deviation from the design's ES-native-snapshot plan — the
  live container has no `path.repo` configured and restarting it to add
  one was judged too risky mid-eval; the clone approach gives the same
  isolation guarantee without touching production). A second `goethe_mcp`
  gateway (byte-identical `goethe.py`/`goethe_mcp.py` to the live one,
  diffed) served Condition A on a spare port against the disposable ES;
  Condition B ran against the real live gateway. `llama-server` was not
  running at prompt start — started fresh (`Qwen3.6-27B-UD-Q4_K_XL`, ctx
  131072, matching Run 9's header) and served both conditions sequentially
  (one GPU).
- **Score sheet**: A=53/60, B=51/60 (v3.5 S/P/M/W/A/L). Tool calls: A=31,
  B=34 (more, not fewer). **Both legs of the pre-registered B-wins
  criterion fail — verdict LOSS**, recorded mechanically, not reframed.
  Full per-scenario grading with transcript evidence in the report,
  including a harness limitation discovered mid-grading (P1/P3/M2's
  suite text assumes an interactive human typing "yes" mid-conversation;
  `v35_harness.py` has no mechanism for that — adjudicated symmetrically
  for both conditions per the same precedent Run 9 already established,
  with a strict-literal cross-check confirming the verdict direction is
  unaffected either way).
- **Root-cause analysis (the important part)**: none of the scenarios
  driving the score delta (S3, P3, P5, M2, W1) involved a KB-content
  difference between conditions — all were tool-use-reasoning gaps
  (sudo/permission judgment, a hallucinated "file doesn't exist" on a
  permission-denied read, an incorrect "elevated access required" claim
  disproven by the other condition's own successful direct read).
  Retrieval recall/MRR on the frozen gold set was bit-for-bit identical
  between conditions on production (linear) mode; wrong-KB-hit count was
  0 for both. Condition A's snapshot and Condition B's live run happened
  ~15 minutes apart with no nightly dream cycle in between (03:30 timer),
  so the two KBs barely diverged — this run mostly measured model-sampling
  variance (`--reasoning-budget -1`, no temperature pinning, n=1 per
  condition), not a dreaming effect. Recorded honestly as a null-adjacent
  result with a methodological gap, not oversold as evidence dreaming
  hurts quality.
- **Per the loss-verdict instruction**: no `lse-errors` entry blames a
  specific bad KB write, because none was found — filing one anyway to
  satisfy the letter of the instruction was judged worse than explaining
  why it doesn't apply. A `record_error` entry (hash `6122c47830260f4e`)
  captures the verdict + root-cause finding + re-run recommendation for
  the next dreaming-lift attempt. `DREAM_AUTO_APPLY` stays empty
  regardless of root cause, per the instruction.
- **Also discovered**: `test-suite-v3.5.md`'s M2 precondition ("gs alias
  not present") is stale again — same drift class CURRENT-STATE.md already
  flagged once for this exact scenario, now recurred.
- Disposable infra (Condition-A gateway on 9701, `elasticsearch-eval-a`
  container + volume) torn down after the report was filed. `llama-server`
  left running (shared service, not eval-specific).

Deferred to later prompts:
- A proper re-run with a real elapsed dreaming window and multiple trials
  per condition (or pinned sampling) — recommended in the report §7, not
  done here since Prompt 4.6's scope was "run the eval as designed," not
  "redesign it mid-run."
- Prompt 4.7 (threat-model addendum), 4.8 (autonomy tuning — this loss
  verdict is now an input), 4.9 (runbook), 4.10 (Thread close).

## 2026-07-12 (Cowork, cont'd x8): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.5 — A/B learning-lift eval design (`eval/traum-ab-design.md`); reconstructed + committed `eval/v35_harness.py` v0.1.0 (original lost, never committed, `/tmp/lse/` cleared); gold-set DATA-3 freeze (sha256)

- **`eval/traum-ab-design.md`** (new). Design-only per the prompt ("before
  running anything"). Condition A = `lse-kb` frozen via ES snapshot
  (repository + snapshot + restore into a disposable second ES instance,
  commands specified, not yet executed); Condition B = live dreamed KB.
  Reframed "pre-dreaming-era" (§2): the literal pre-Thread-2 snapshot does
  not exist (`GET /_snapshot` → `{}`, no repo ever registered — this gap
  was already flagged in `calibration-run-1.md` and deferred to this
  prompt) and cannot be reconstructed from logs (in-place trust-field
  mutation would contaminate the control) — Condition A is now defined as
  "frozen at eval-start," anchoring every future TRAUM eval to a real
  baseline instead of a stale reference point.
- **Metrics specified**: suite score (v3.5 S/P/M/W/A/L, 0/2/3 rubric,
  human/LLM-graded from harness transcripts); retrieval recall/MRR on
  `retrieval-gold-v1.jsonl` (50 rows, sha256 frozen per DATA-3:
  `a5fe1380...1379be`); tool-call count to completion per scenario (the
  "faster verification" claim); wrong-KB-hit count (defined precisely —
  requires evidence the model used a bad `search_kb` hit, not just that
  one was returned; direct empirical check on the poisoning-via-dreaming
  invariants).
- **Pre-registered success criterion** (§6): B wins iff suite score
  strictly improves, OR tool-calls drop ≥10% with no score loss. Anything
  else recorded as null/loss, no post-hoc reframing.
- **`eval/v35_harness.py`** (new, v0.1.0). The plan named this file as
  "the harness" and instructed committing it first since it lived only in
  `/tmp/lse/` — confirmed gone on both LUCIFER and node3090 while writing
  this design (the loss was already documented 2026-07-07 in
  `t1_feedback_loop.py`'s docstring and `CURRENT-STATE.md`'s Outstanding
  note; never actually committed). Reconstructed from the surviving
  description in `eval-report-v8.md` + the proven MCP-driving-a-model
  wiring already committed in `t1_mcp_harness.py`. Adds multi-turn
  conversation-chain support the original wasn't documented as having:
  parses `test-suite-v3.5.md` directly, detects "continuing in the same
  conversation as X" linkage in the suite's own prose, and correctly
  grouped the real suite into 19 chains / 20 scenarios (A1→A2 linked,
  everything else fresh) — verified live via `--list` against the real
  file, not just unit-tested.
- **Gold-set freeze (DATA-3, partial)**: `eval/retrieval-gold-v1.jsonl`
  sha256 recorded in the design doc; must be re-checked at the top of
  Prompt 4.6, void if it doesn't match. General `freeze_bench.py`-style
  gold-set tooling (the full DATA-3 item) remains open on ROADMAP.md — not
  built here, this eval doesn't wait on it.

Deferred to later prompts:
- Actually registering the ES snapshot repo, taking the Condition-A
  snapshot, and standing up the disposable second ES instance — explicitly
  left to Prompt 4.6 (design-only scope for 4.5).
- Freezing `test-suite-v3.5.md` itself under DATA-3 (only the gold set was
  frozen here).
- Confirming the live model on `:8080` at run time — not assumed in the
  design, to be recorded verbatim in `eval-report-traum-1.md`.
- Running the eval itself (Prompt 4.6), the threat-model addendum (4.7),
  autonomy tuning (4.8), and the runbook pass (4.9).

## 2026-07-12 (Cowork, cont'd x7): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.4 — `dream_apply.py --queue` (pending human-gate proposals across ALL day-dirs, oldest first, grouped by type), 14-day staleness auto-expiry; `dream_apply.py` v0.2.0 -> v0.3.0

- **`dream_apply.py --queue`** (new CLI mode). Until now, dream_apply.py only
  ever operated on ONE day-dir's proposals.jsonl at a time; the morning
  "what's waiting on me" view was a lightweight preview baked into
  dream_digest.py's own "Pending human-gate" section (capped at 6 lines,
  bounded by lookback_days, no expiry — that section's own docstring
  explicitly said "Prompt 4.4 will formalize this later"). `--queue` is
  that formal version: `gather_queue()` walks EVERY YYYY-MM-DD day-dir
  under `--dream-dir` (default `$GOETHE_DREAM_DIR` or
  `/opt/local-se/dreams` — same variable dream_runner.py/dream_digest.py
  already use for the same root), oldest day-dir first, and returns every
  proposal not yet resolved — "resolved" meaning its content-hash (reusing
  `dream_digest.proposal_key`, so identity matches the digest's own
  preview exactly) already appears in that day-dir's applied.jsonl OR
  rejected.jsonl OR the new expired.jsonl (below). `group_queue_by_type()`
  then buckets the oldest-first stream by proposal `type`, which gets
  "oldest first, grouped by type" (the prompt's own phrasing) for free:
  dict insertion order means whichever type's single oldest pending item
  appears earliest in the stream leads the listing, not alphabetical
  order. `render_queue()` prints a plain-text inventory (date, age in
  days, `call`, `pair_id` when set, truncated `why`) to **stdout**
  (everything else in this file logs to stderr — `--queue`'s actual
  output is a report meant to be read/redirected, unlike the interactive
  apply flow's status lines). **`--queue` never loads goethe.py's Tools
  class and never touches ES** — it is pure local dream-dir bookkeeping,
  provable by a new test that monkeypatches `load_tools_class` to explode
  and confirms `--queue` still runs clean.
- **14-day staleness auto-expiry** (`DREAM_QUEUE_STALE_DAYS = 14`, inside
  `gather_queue()`). A pending proposal whose day-dir is more than 14 days
  old gets ONE line appended to that day-dir's new `expired.jsonl` —
  `{proposal, reason, expired_at, age_days}`, reason text: "stale (>14d,
  age=Nd) — auto-expired; re-dream will re-propose if still true" (the
  prompt's own rationale, verbatim) — and is excluded from the pending
  listing from then on. This write is **unconditional, not gated by
  `--dry-run`** — the same precedent this file already set for
  `rejected.jsonl` in the single-run flow (human-decline / invariant-fail
  rejections are logged regardless of `--dry-run` too, since `--dry-run`
  here only ever means "don't call a Tools method / don't write to ES";
  expiry is local bookkeeping, not an ES write). Idempotent: a
  second `--queue` run over the same stale proposal does not re-append or
  duplicate — it's already in `expired.jsonl`'s own resolved-set. Boundary
  is `age_days > 14` (exactly 14 days old is still the last safe day, not
  yet expired) — the day-dir-name-parses-but-isn't-a-real-date case (e.g.
  `2026-13-40`, which `dream_digest._DAY_DIR_RE`'s regex accepts but
  `date.fromisoformat()` cannot) fails CLOSED: `age_days=0`, never
  auto-expired, matching this file's own long-standing "when in doubt,
  leave it for a human" discipline.
- **`dream_digest.py`** — updated (not rewritten) the two places that
  described the pending-items preview as "no expiry rule, no --queue flag"
  (module docstring §3, `gather_pending()`'s own docstring), since that's
  no longer accurate now that Prompt 4.4 exists. Both now point at
  `dream_apply.py --queue` as the formal version and explain, explicitly,
  why the digest's own preview still does NOT apply the expiry rule
  itself (refreshing the digest must never mutate dream-dir state as a
  side effect — only an actual `--queue` invocation may expire anything).
  No behavior change in `dream_digest.py`, docstrings only.
- **Morning review loop, short version** (full runbook write-up is its
  own later prompt, 4.9 — not done here): added a MORNING REVIEW LOOP
  section to `dream_apply.py`'s own module docstring plus a `--queue`
  usage example, describing the ~5-minute loop: (1) `dream_apply.py
  --queue` to see everything pending oldest-first and let staleness expire
  what's moved on, (2) apply each day-dir's batch the normal way
  (`dream_apply.py --proposals <dream-dir>/<date>/proposals.jsonl
  --no-dry-run`, still per-proposal yes/no — `--queue` only changes how
  you FIND what's waiting, never how it's applied), (3) re-run `--queue`
  to confirm it's empty. This is deliberately the CONCISE version living
  next to the code it documents; the operator-facing runbook entry Prompt
  4.9 asks for is a separate, fuller doc not yet written.
- **Tests.** New `tests/test_dream_apply_queue.py` (30 tests) — the first
  test file dream_apply.py has ever had (its ES-mutating apply flow has no
  tests yet; `--queue` is deliberately ES-free/Tools-free, so it was
  testable in full without any FakeES/FakeTools scaffolding).
  `TestGatherQueueBasic` (empty root, day-dir with no proposals.jsonl,
  single fresh day-dir, oldest-day-dir-first ordering across two dirs),
  `TestGatherQueueExpiry` (past the 14-day line, exactly at the 14-day
  boundary — must NOT expire, one day past the boundary — must expire,
  expired.jsonl's full field shape, a signature-inspection assertion that
  `gather_queue` has no `dry_run` parameter at all, and a second-call
  idempotency check that nothing gets re-expired or duplicated),
  `TestGatherQueueResolvedExclusion` (already-applied, already-rejected,
  an old-but-already-applied proposal correctly staying OUT of `expired`
  too, and one resolved + one still-pending proposal coexisting in the
  same day-dir), `TestGatherQueueMalformedDayDir` (the `2026-13-40`
  regex-matches-but-unparseable case), `TestGroupQueueByType` (within-type
  ordering, cross-type bucket-order-follows-oldest-item, missing `type`
  bucketing as `"unknown"`), `TestRenderQueue` (all rendered fields, long
  `why` truncation, header count/date), `TestCmdQueue` (empty-queue
  message on stderr, listing on stdout vs. summary on stderr, expiry
  notice on stderr), `TestMainQueueWiring` (`--queue` doesn't require
  `--proposals`, `--stale-days` defaults to the constant, missing
  `--proposals` without `--queue` raises `SystemExit`, and — the most
  load-bearing test in the file — `--queue` proven to never call
  `load_tools_class` by monkeypatching it to raise, both directly and via
  a full `main(["--queue", ...])` end-to-end run).
  Live smoke test directly against a synthetic multi-day-dir tree (run
  outside pytest, three day-dirs at ages 32d/15d/2d) confirmed the exact
  same behavior the tests assert: the two stale day-dirs' proposals were
  auto-expired to their own `expired.jsonl` on the first `--queue` call,
  a second call did not re-expire or duplicate them, the fresh day-dir's
  two proposals showed up correctly grouped by type, and marking one of
  them as already-applied (via a hand-written `applied.jsonl` entry) made
  it disappear from a third `--queue` call while its sibling proposal
  correctly remained.
  Full dream-scoped suite: `pytest tests/ -k dream -q` — **279 passed**
  (249 prior + 30 new), 0 failed.
- **Deferred to their own later prompts, not done here:** the full
  operator-facing runbook entry for the morning review loop (Prompt 4.9 —
  this prompt's own text explicitly assigns that write-up there, not
  here). Also not done: any change to `dream_apply.py`'s single-run apply
  flow itself (invariant checks, confirm-gate rendering, ES writes) —
  `--queue` is purely additive, a new read path alongside the existing
  write path, and does not touch it.

---
## 2026-07-12 (Cowork, cont'd x6): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.3 — crash discipline (record_crash_error, FAILED-banner partial reports, explicit Restart=no), 3-consecutive-failed-nights digest escalation; `dream_runner.py` v0.10.0 -> v0.11.0, `dream_digest.py` v0.1.0 -> v0.2.0

- **`record_crash_error`** (new, `dream_runner.py`) — the ONE sanctioned
  exception to this file's otherwise-absolute ES-read-only invariant
  (module docstring INVARIANTS section updated to say so explicitly;
  `search_index()`'s own docstring now points at it too). Hardcoded
  `index="lse-errors"`, `provenance="dream-infra"`, `context="dream-runner"`
  — structurally incapable of writing `lse-kb`; an OPERATIONAL failure
  record about the dreaming system itself, the same class of thing
  `goethe.py`'s own `Tools.record_error` already writes for every other
  LSE subsystem. Deliberately does NOT instantiate `goethe.py`'s Tools
  god-class for this one call (the whole point of TRAUM's "new files, not
  god-class growth" architecture note) — reimplements just enough of its
  document shape directly against this file's own `es_client(cfg)`: same
  sha256-of-normalized-text hash as goethe.py's own `error_hash` (so an
  identical error string collides to the SAME doc whether recorded here or
  via the interactive tool), plain get-then-update occurrence-count bump
  on a repeat, `es.index()` fallback on any get failure (not-found is the
  common case; ES-down is the rare one, both land in the same fallback).
  Deliberately skips goethe.py's embedding-based KNN dedup — a crash
  handler must be maximally simple, and adding an Ollama embedding
  dependency to the path that handles Ollama/node3090 already having
  failed would be exactly backwards. Honors `cfg.dry_run` (prints instead
  of writing, per this file's own long-standing "touches no files, no ES"
  dry-run guarantee). Total failure inside this function is caught and
  returned as a string, never raised — a broken error-reporting path must
  never mask the original crash.
- **`write_failure_report`** (new, `dream_runner.py`). A PARTIAL
  `report.md` with a `## FAILED` banner, the exception type/message, a
  full traceback, and an explicit "manifest.db's dreamed_at is untouched
  ... safe to re-dream" statement — written from whatever `main()` still
  has at crash time (`sessions_count` defaults to 0, so a crash before
  session-selection even runs still gets a usable report). Same
  `<dream-dir>/<date>/report.md` path and "last invocation today wins"
  convention `write_report()` already has. Also appends one line to the
  new `<dream-dir>/<date>/crashes.jsonl` (same `"at"`-append convention as
  `null-results.jsonl` — survives the night's whole multi-pass sequence
  intact, unlike `report.md`) — this is what the new escalation banner
  (below) scans for.
- **`main()` rewired**: the whole run body now sits inside
  `try / except Exception / finally`. On ANY unhandled exception:
  `_handle_crash()` runs all three steps (write the FAILED report, call
  `record_crash_error`, refresh the digest so an escalation banner shows
  up immediately if this crash makes 3-in-a-row) — each step independently
  try/excepted so one broken reporting path can't mask the original
  exception — and then the ORIGINAL exception is **re-raised unchanged**.
  The process still exits non-zero (systemd/journalctl correctly show the
  pass failed); `finally` still runs `release_lock()` regardless, so a
  crash never leaves an orphaned lock blocking tomorrow's cycle. The
  guard-check phase (recent-session-activity, lock acquisition) stays
  deliberately OUTSIDE this try/except — it runs before the lock even
  exists to release, and both guard functions already degrade
  internally rather than raising.
- **`goethe-dream.service.tmpl`** (Prompt 4.1 file, updated): `Restart=no`
  is now an EXPLICIT line (Prompt 4.3's own words), not just relied on as
  `Type=oneshot`'s default — so a future edit to this unit can't silently
  reintroduce a restart spiral without a very visible diff. ExecStart
  comment block rewritten to describe the real crash-discipline flow now
  that it exists (previously said "not yet implemented as of this unit").
  `systemd-analyze verify` clean after the edit.
- **3-consecutive-failed-nights escalation** (`dream_digest.py`, new
  `gather_crash_streak` + `CRASH_ESCALATION_THRESHOLD = 3`). Walks
  backward from today counting consecutive day-dirs with a non-empty
  `crashes.jsonl` — a night counts as "failed" if ANY pass crashed that
  night (deliberately coarse/alarm-prone; per-pass detail lives in
  `report.md`'s own FAILED banner and the future `dream_apply --queue`).
  A day-dir with no/empty `crashes.jsonl`, OR a day-dir that doesn't exist
  at all, breaks the streak — an ambiguous gap (box off, cycle didn't run)
  is deliberately NOT treated as evidence of 3 bad nights. Bounded by the
  existing `lookback_days` knob. `render_digest()` renders the banner
  (`## :rotating_light: ESCALATION — N consecutive failed dream nights`,
  pointing at that night's `report.md`/`crashes.jsonl`/`lse-errors`)
  **immediately after the title line** — before every other section — so
  `MAX_DIGEST_LINES` truncation can never cut it, and it is absent
  entirely below the threshold (same "say nothing when there's nothing to
  say" discipline as every other section). `write_digest()` gathers it
  with the same independent try/except-degrades-to-nothing guard as every
  other `gather_*` step.
- **Tests.** New `tests/test_dream_crash_discipline.py`, 20 tests:
  `record_crash_error` (dry-run zero ES calls, new-doc shape, repeat bumps
  occurrence_count not a new doc, case/whitespace normalization collides
  to the same hash, total ES failure swallowed), `write_failure_report`
  (dry-run prints nothing to disk, real write's banner/traceback/
  crashes.jsonl fields, appends-not-overwrites across two passes in one
  day-dir), `_handle_crash` (calls all three steps, never raises even
  when EVERY step is made to fail), **fault injection through the REAL
  `main()`** (`PASS_FUNCS["patterns"]` monkeypatched to raise mid-run,
  driven through actual `--no-dry-run` argv against tmp_path dirs and a
  FakeES double): confirms the report.md FAILED banner and crashes.jsonl
  are really on disk, the ES write really has
  `context=dream-runner`/`provenance=dream-infra`, the lockfile is really
  gone afterward (no orphan), a synthetic manifest.db's `dreamed_at`
  column is completely untouched after the crash, and `pytest.raises`
  confirms the original exception really does propagate out of `main()`.
  Plus `gather_crash_streak` (3-in-a-row, a clean night breaking the
  streak, a missing day-dir breaking the streak, the lookback_days bound)
  and the escalation banner (absent below 3, present at 3, survives
  `MAX_DIGEST_LINES` truncation via the same many-`insights` overflow
  technique `test_dream_digest.py`'s own heavy-overflow test uses — an
  earlier version of this test tried to force overflow via a huge
  `applied` list and silently passed for the wrong reason, since
  `applied` is capped at 6 items inside `render_digest()` itself; caught
  by asserting the omission marker line, not just line count). Live
  dry-run smoke check directly against LUCIFER's real `lse.toml` defaults
  confirmed the ES round-trip path end-to-end.
  Full dream-scoped suite: `pytest tests/ -k dream -q` — **249 passed**
  (229 prior + 20 new), 0 failed.
- **Deferred to their own later prompts, not done here:** the
  `dream_apply --queue` morning workflow (4.4), VALVES.md documentation of
  every TRAUM valve including the new crash/escalation-related ones (4.9,
  though this prompt added no NEW env vars — `record_crash_error` and
  `gather_crash_streak` are unconditional, unconfigurable behavior, not
  valves). Also not done: an actual live 3-night crash streak on LUCIFER
  (impractical to wait out in-session) — `gather_crash_streak`'s unit
  tests construct the day-dir/crashes.jsonl fixtures directly rather than
  waiting for real failed nights to accumulate.

---
## 2026-07-12 (Cowork, cont'd x5): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.2 — lockfile, recent-session-activity guard, per-run budgets (sessions/LLM-calls/45min wall-clock), dreamer-episode-exclusion assert; `dream_runner.py` v0.9.0 -> v0.10.0

- **Lockfile** (`acquire_lock`/`release_lock`, new). Single-writer lock
  across ALL dream_runner.py invocations on this box (not just same-`--pass`
  ones), covering both the scheduled 5-ExecStart nightly cycle somehow
  still running when the next night's timer fires and an operator's manual
  CLI run overlapping the scheduled one. Atomic `O_CREAT|O_EXCL` create
  avoids the check-then-create race. A held lock is reclaimed once when
  its PID is provably dead (`os.kill(pid, 0)`) or the file is older than
  `--lock-max-age-s` (default 4h, matching `goethe-dream.service.tmpl`'s
  own `TimeoutStartSec` outer bound from Prompt 4.1) -- the PID-reuse edge
  case. `release_lock` only ever removes a lock it can prove is its own
  (PID match in the lock's own JSON payload), so it can never yank a lock
  out from under a process that already reclaimed it as stale. New:
  `--lockfile` (default `<dream-dir>/.dream.lock`), `--lock-max-age-s`.
- **Recent-session-activity guard** (`_recent_session_active`, new). Skips
  the run (clean, logged, exit 0 -- never an error) if any LSE session's
  `end_ts` in manifest.db falls within `--session-active-window-min`
  (default 30) of now. Refreshes manifest.db first
  (`episode_index.build_manifest`) so "per manifest" -- the prompt's own
  phrasing -- reflects near-real-time state; nothing else on this box
  currently rebuilds manifest.db on its own schedule, so without this
  refresh the check could easily miss a session that started minutes ago.
  Degrades to "don't block" on a missing manifest, an unparseable
  timestamp, or the refresh itself throwing -- and on a future `end_ts`
  (clock skew), rather than false-positive-blocking a nightly run.
- **Per-run budgets** (`DreamBudget`, new dataclass; `_budget_checkpoint`
  helper). Three dimensions, checked in a fixed order (wall-clock first,
  then LLM-calls, then sessions) so the report always states what
  ACTUALLY stopped a run first: `--budget-max-wall-clock-min` (default
  45, per the prompt), `--budget-max-llm-calls` (default 100),
  `--budget-max-sessions` (default: same value as `--sessions`, so out of
  the box this adds no NEW restriction beyond the existing selection cap).
  Attached to `cfg.budget` ONLY by `main()` for real runs -- every direct
  `DreamConfig(...)` construction elsewhere (all 6 test files as of this
  prompt) leaves it `None` and every check is a silent no-op, so zero
  existing call sites needed to change. `call_dream_llm` checks the
  budget FIRST, before even the DREAM_LLM_URL forced-endpoint leg -- once
  exhausted, a run makes ZERO further network calls of any kind, not just
  zero node3090 calls -- and returns `'BUDGET_EXHAUSTED: <reason>'` rather
  than `'ERROR: ...'` so `request_dream_envelope` can tell "we chose to
  stop" apart from "the dreamer failed us" (and skips its normal 2-attempt
  retry for that reply -- retrying an exhausted budget is pointless).
  Loop-level `_budget_checkpoint(cfg)` break-checks added to all four
  per-item loops that can consume budget: `run_pass_dedup`'s
  `DEDUP_LLM_BATCH_SIZE` batch loop, `run_pass_stale_contradiction`'s
  per-session demote loop (also the one pass with a natural
  `record_session()` call -- dedup batches PAIRS, error-cluster batches
  CLUSTERS, insights batches DOMAINS, patterns makes no LLM call and
  explicitly ignores `sessions`, so "sessions consumed" stays inert for
  those by design, not by oversight), `run_pass_error_cluster`'s cluster
  loop, and `run_pass_insights`'s domain loop. `main()` centrally appends
  ONE **BUDGET TRUNCATION** note to the pass's narrative when
  `cfg.budget.truncated` (usage numbers for all three dimensions,
  explicit "this is a normal, expected exit, not an error" line,
  reminder that `dreamed_at` is untouched so a re-dream naturally picks
  up the rest) -- centralized so none of the four pass functions needed
  their own note-formatting logic, only the loop-level break.
- **Dreamer-episode-exclusion assert** (`assert_no_episode_writes` +
  `_snapshot_episode_session_files`, new). DESIGN.md §2 invariant 3(e)
  ("no dream-of-dreams") made STRUCTURAL, not just conventional -- it was
  already true by construction (the dreamer doesn't run through
  `goethe_mcp.py`'s `register()` journaling wrapper, so nothing in this
  file has a write path into `EPISODE_DIR` at all today), but "true by
  construction" is an assumption a future edit could quietly break. Now:
  a before/after `{relative_path: mtime}` snapshot of every SESSION file
  (`day-dir/*.jsonl[.gz]`, via `episode_index.py`'s own
  `iter_day_dirs`/`iter_session_files` so "what counts as a session file"
  has exactly one definition in this codebase) is taken at the start and
  end of every real run; any addition, removal, or modification raises
  `AssertionError` -- deliberately uncaught in `main()`, as loud as a real
  bug. `manifest.db` itself (which lives inside `EPISODE_DIR` by default)
  is correctly excluded from the snapshot -- it's a legitimate, expected
  write target for both `episode_index.build_manifest` (including this
  same prompt's own session-activity-guard refresh) and `dream_apply.py`'s
  `dreamed_at` column, not a violation.
- **`main()` rewired** around all of the above: guards checked first
  (skip, don't error, unless `--ignore-guards` -- a manual/debug-only
  escape hatch `goethe-dream.service.tmpl` never sets), budget constructed
  and attached, the whole existing body wrapped in `try/finally` so
  `release_lock` always runs (even if the episode-exclusion assert itself
  is what fails), episode snapshot taken before `select_undreamed_sessions`
  and checked as the last statement inside the `try` block.
- **Tests.** New `tests/test_dream_guards.py`, 31 tests: `DreamBudget`
  dimension/ordering/mark-once semantics, `_budget_checkpoint`,
  `call_dream_llm`'s zero-network-calls-when-exhausted short circuit,
  `request_dream_envelope`'s no-retry-on-budget-exhaustion (with a sanity
  check that the pre-existing real-`ERROR:` retry behavior is untouched),
  full lock lifecycle (acquire/release round-trip, live-lock blocks a
  second acquire, dead-PID reclaim, too-old-even-if-alive reclaim,
  release-never-steals-a-lock-it-doesn't-own, release-on-missing-file is
  a safe no-op -- dead PIDs obtained by actually spawning and waiting on a
  real subprocess, not guessed), `_recent_session_active` (blocks/doesn't
  block/clock-skew/missing-manifest/refresh-failure, against real
  synthetic manifest.db files), `assert_no_episode_writes`
  (passes/new-file-raises/modified-file-raises/manifest.db-is-exempt), and
  two integration tests driving `run_pass_stale_contradiction`'s REAL loop
  (not simulated) to confirm it actually stops early -- 3 of 10 sessions
  processed under an LLM-call budget of 3, 4 of 10 under a session budget
  of 4 -- via a monkeypatched `_health_probe`/`_post_chat_completion`
  (letting the real `call_dream_llm` do its real bookkeeping) rather than
  stubbing `call_dream_llm` itself, after an initial version of that test
  falsely passed 10/10 sessions because stubbing `call_dream_llm` directly
  had silently removed its own budget accounting along with it -- caught
  by the test asserting `sessions_consumed == 3`, not just `truncated`.
  Full dream-scoped suite: `pytest tests/ -k dream -q` -- 229 passed
  (198 prior + 31 new), 0 failed.
- **Live smoke test on LUCIFER.** `python3 tools/dream_runner.py --pass
  patterns --episode-dir /tmp/smoke-dream-42/... --dry-run`: exit 0,
  correct null-result digest (real lse-kb=372/lse-errors=32/lse-skills=17
  counts from live ES), lockfile created and cleanly removed on exit,
  episode-exclusion assert passed silently.
- **Deferred to their own later prompts, not done here:** crash discipline
  proper (record_error, FAILED-banner partial report, 3-consecutive-
  failed-nights escalation — 4.3), the `dream_apply --queue` morning
  workflow (4.4), VALVES.md documentation of every new
  `GOETHE_DREAM_LOCKFILE`/`GOETHE_DREAM_SESSION_ACTIVE_WINDOW_MIN`/
  `GOETHE_DREAM_BUDGET_*` valve (4.9). Also not done: injecting a real
  fault to exercise the "budget exhaustion mid-run on a live corpus"
  path end-to-end against actual node3090/Ollama traffic -- the unit +
  integration tests above cover the mechanism; a live 45-minute wall-clock
  trip is impractical to actually wait out in this session and is exactly
  the kind of thing Prompt 4.3's fault-injection ask will want anyway.

---
## 2026-07-12 (Cowork, cont'd x4): TRAUM Thread 4 (TRAUM-AUTO), Prompt 4.1 — `goethe-dream.service.tmpl` + `.timer.tmpl` (nightly 03:30 +/-15min), `dream_runner.py` v0.8.0 -> v0.9.0 (remote node3090 VRAM gate)

Opens Thread 4. Scope was exactly Prompt 4.1's ask: the systemd trigger, a
real VRAM-aware fallback behind it, and wiring the new service pair into
the product layout doc the same way the existing `services/*.tmpl` files
are declared (goethe-mcp.service.tmpl and llama-server.service.tmpl have no
other "launch script" wiring on this box today — they are still manual/
`start-goethe.sh`-launched, so LSE-PRODUCT-LAYOUT.md's services/ manifest
+ carve-mapping + product-file-manifest tables are the only place any of
these three are "wired in", and that's what this prompt's own "the same
way existing services are" phrase resolves to).

- **`lse/services/goethe-dream.service.tmpl` + `goethe-dream.timer.tmpl`**
  (new). Template-style match to `goethe-mcp.service.tmpl`: same
  system-install-layout disclaimer/manual-install block, same
  `ProtectSystem=full` + explicit `ReadWritePaths` hardening posture. Five
  `ExecStart=` lines (`Type=oneshot`), one per `dream_runner.py --pass`
  (dedup, stale-contradiction, error-cluster, patterns, insights, in
  `PASS_FUNCS` declaration order), each `--no-dry-run` and each prefixed
  `-` so one pass's uncaught exception doesn't blank out the other four
  before Prompt 4.3's real crash discipline lands. Runs as `User=sy5`,
  `WorkingDirectory=/var/lib/lse/dream-sandbox` — a dedicated, disposable
  cwd distinct from `goethe-mcp.service.tmpl`'s `/opt/lse` code-tree
  WorkingDirectory, since this is an unattended offline batch job, not a
  colocated long-lived service. Timer: `OnCalendar=*-*-* 03:30:00`,
  `RandomizedDelaySec=15min`, `Persistent=true` (catches up on next boot if
  LUCIFER was asleep at 03:30 — safe, since manifest.db's `dreamed_at` gate
  makes a late/duplicate run just see fewer or zero undreamed sessions).
  Verified with `systemd-analyze verify` (clean, no warnings) and
  `systemd-analyze calendar` (next-elapse math checks out) on LUCIFER's own
  systemd 255.
- **`dream_runner.py` remote VRAM gate** (v0.8.0 -> v0.9.0). New
  `_node3090_free_vram_mb()`: SSHes to node3090 (`-o BatchMode=yes`, fails
  CLOSED to 0 == "busy" on any error) and runs the identical
  `nvidia-smi --query-gpu=memory.free` probe goethe.py's
  `Tools._planner_free_vram_mb` (tools/goethe.py:1486) already runs
  locally for the Gemma-spawn gate — same pattern, applied to a box
  dream_runner doesn't own. Wired into `call_dream_llm`'s cascade: below
  the new `--node3090-vram-gate-mb` floor (default 2000 MiB,
  `GOETHE_NODE3090_VRAM_GATE_MB`), the llama-server leg is skipped
  entirely (never even health-probed) and the cascade goes straight to
  Ollama/CPU — satisfies the prompt's explicit "fall back... rather than
  skipping" (dreams are latency-insensitive, so losing GPU speed is fine;
  losing the run entirely would not be). New CLI flags/env:
  `--node3090-ssh-host/-user/-port`, `--node3090-vram-gate-mb`. New
  `DreamConfig` fields default-valued (not required) so every existing
  direct-construction call site (5 test files) kept working unmodified —
  confirmed by running the full pre-existing suite unchanged after the
  edit: `pytest tests/ -k dream -q` — 198 passed, 0 failed, 0 skipped.
- **`tests/test_dream_vram_gate.py`** (new, 10 tests). `_node3090_free_vram_mb`
  parsing (single/multi-GPU nvidia-smi output, SSH timeout, unparseable
  output — all fail CLOSED to 0). `call_dream_llm` cascade: GPU-busy skips
  llama-server without probing it and calls Ollama directly; GPU-free runs
  llama-server exactly as before the gate existed; GPU-free-but-the-actual-
  call-still-fails still falls through to Ollama (pre-existing behavior
  survives the new gate in front of it); the forced `DREAM_LLM_URL` leg
  short-circuits before the VRAM probe is ever called at all. All via
  `monkeypatch`/`unittest.mock`, zero live SSH/HTTP. 10/10 passed.
- **`lse/docs/LSE-PRODUCT-LAYOUT.md`** updated: `services/` tree listing,
  carve-mapping table, and product-file-manifest table all now list
  `dream_runner.py`/`dream_apply.py`/`dream_digest.py`/`episode_index.py`
  -> `$LSE_HOME/goethe/` and the new service pair -> `$LSE_HOME/services/`,
  plus a one-line addition to the `systemd=true` WSL invariant noting timer
  units need it too. No other launch-script wiring exists for this box's
  services yet (see scope note above) — deliberately did not touch
  `scripts/restart_exporters.sh` (that script is explicitly host-side,
  non-systemd processes WSL2 kills on restart; a `systemctl enable`d timer
  survives a WSL2 restart on its own and doesn't belong in that list) or
  the Windows `lse-stack-launch-*.ps1` launcher (a different concern
  entirely — interactive llama-server model-profile switching, not
  systemd service enablement).
- **Deferred to their own later prompts, not done here (by design):**
  concurrency/budget guardrails + lockfile (4.2), crash discipline /
  `record_error` on unhandled exceptions (4.3), the `dream_apply --queue`
  morning workflow (4.4), VALVES.md documentation of the new
  `GOETHE_NODE3090_SSH_*`/`GOETHE_NODE3090_VRAM_GATE_MB` valves (4.9).

Not yet done: actually installing/enabling the unit on a live box (no root
on this Cowork session; `systemd-analyze verify` is the strongest
pre-install check available here) — first real firing + morning-after
report review is Prompt 4.1's true acceptance test and is the operator's
to run.

---
## 2026-07-12 (Cowork, cont'd x3): TRAUM Thread 3 (TRAUM-INSIGHT) CLOSED — v0.4.0-a deployed live to LUCIFER, `[DREAM]`/`time_check()` desync fixed, first real dream cycle, security + data-loss findings, debrief

Closes Thread 3. Unlike every prior TRAUM entry this thread, this one ran
against LUCIFER for real via live `mcp__goethe__*` tool access (this Cowork
session turned out to be running on LUCIFER itself — `~/projects/local-
system-engineer` on WSL2 is the same repo this Windows-side session edits,
confirmed via `git log` matching and `/mnt/c/Users/SY5/...` in the WSL2
`pytest` rootdir). That changed what "full test pass" and "verify" could
mean this close: not simulated, not sandboxed — the real gateway, the real
`lse-kb` (372 docs), the real `agent_commands.log`, the real `tasks.db`.

- **Full test pass — live, not sandboxed.** `python3 -m pytest tests/ -q`
  run directly on LUCIFER (`/usr/bin/python3`, pytest 9.1.1, against real
  Elasticsearch): **306 passed, 0 failed** — the complete suite, not just
  the dream-related files. This supersedes Prompt 3.9's own CHANGELOG entry,
  which had explicitly flagged `test_kb_contracts.py::TestDreamBanner` as
  traced-but-unexecuted because the Cowork bash sandbox's FUSE mount had
  `goethe.py` truncated mid-file; run on LUCIFER's real filesystem, that
  file is valid (confirmed `ast.parse` clean, 7210 lines) and all 7
  `TestDreamBanner` tests pass for real, closing that gap.
- **Deploy (v0.4.0-a → LUCIFER).** `bash tools/start-goethe.sh` — killed the
  running HTTP gateway (was serving pre-3.5 code, PID 189793) and relaunched
  it (new PID confirmed listening on `127.0.0.1:9700`); two unrelated stdio-
  transport `goethe_mcp.py` processes on the same host were left untouched
  (the start script's kill pattern only matches `--transport http`, so it
  never touches non-gateway instances — confirmed by PID/port inspection
  before and after). **Existing llama-ui threads have NOT picked this up —
  a fresh thread is still required**, per the v0.4.0-a changelog's own
  DEPLOY NOTE; that one step is the operator's to take, no tool here can
  drive the llama-ui browser session.
- **Live-deploy bug found and fixed: `time_check()` silently ate the
  `[DREAM]` banner.** Verifying "banner appears on first search_kb" the
  straightforward way (call `time_check()` first, since CHRONOS's own
  docstring and the system prompt's TIME DISCIPLINE section both say to,
  for date-sensitive work — and a TRAUM close is exactly that) exposed a
  real design gap: `time_check()` sets the same `_time_banner_emitted` flag
  `_consume_time_banner()` gates on, but only ever appends the `[TIME]`
  banner, never `[DREAM]`. A session that calls `time_check()` before its
  first `search_kb` gets `[TIME]` immediately and then **never** sees
  `[DREAM]` for the rest of that session — the exact desync
  `_consume_time_banner()`'s own docstring says reusing the flag was
  supposed to prevent, except the docstring's reasoning only accounted for
  `_consume_time_banner()` itself setting the flag, not `time_check()`
  doing it independently. **Fix**: `tools/goethe.py`'s `time_check()` now
  also calls `_dream_banner()` and appends the line on the same gate, so
  both banners always arrive together regardless of which tool fires
  first. New test `TestChronosTimeCheck::test_time_check_first_still_
  carries_dream_banner` (`tests/test_kb_contracts.py`) pins this; the whole
  suite re-run green (306/306) before redeploying a second time to ship the
  fix. **This is a genuine correctness bug that would not have been caught
  by any unit test written before this close** — every existing
  `TestDreamBanner`/`TestChronosTimeCheck` test exercised each banner tool
  in isolation; only calling them in the realistic order, live, surfaced
  the interaction.
- **`[DREAM]` banner verified live, end to end.** After the second redeploy,
  a real `search_kb` call returned both banners together for real:
  `[TIME] now=2026-07-12 ... | [DREAM] digest=2026-07-12 | pending-gate=6 |
  read /opt/local-se/dreams/latest-digest.md for details`. Not a fixture,
  not a mock — the actual deployed code, the actual digest file, the actual
  gate count.
- **First real dream cycle against live LUCIFER data.** `patterns` pass run
  `--dry-run` (preview only, see security finding below): 8,431 events
  mined from 50,000 windowed lines of the real `agent_commands.log`
  (2026-07-03 .. 2026-07-12), 56 sessions inferred, 1 automation-candidate
  sequence (4 commands, 3 sessions). `dedup` run `--no-dry-run` for real:
  4 candidate pairs at/above the 0.92 merge threshold out of 917 above the
  0.75 floor, out of 371 embedded docs — 6 proposals (3 `mentor_correct`
  merges + 3 `record_outcome` demotions), all "exact character-for-character
  duplicate." `stale-contradiction` and `error-cluster` both ran
  `--no-dry-run` for real and came back genuine, structured null results
  (`no_reverify_and_no_contradictions` / `no_cluster_cleared_bar`, both
  `looked=True`) — the null-result discipline built in Prompt 3.8 working
  exactly as designed on real data for the first time. `insights` was
  deliberately **not** run for real this close (see security finding).
  None of these proposals were applied — `dream_apply.py` (the human-gated
  write path) was not invoked; the 6 dedup proposals sit in today's
  `proposals.jsonl`/the digest's "Pending human-gate (6)" section for the
  operator's own review, same as Thread 2's first run.
- **Live-deploy finding, not fixed this close — flagged for Thread 4:
  `proposals.jsonl` has no append-mode equivalent of `null-results.jsonl`,
  and this cycle proved it's a real, not theoretical, data-loss risk.**
  Running `dedup` (6 real proposals) followed by `stale-contradiction` and
  `error-cluster` (both null) in the same day-dir silently **overwrote**
  `dedup`'s 6 proposals out of `proposals.jsonl` — `report.md`/
  `proposals.jsonl` are documented single-pass-per-invocation snapshots
  (unchanged since before Prompt 3.8), and 3.8 only gave the null-result
  side of that an append-mode file. The digest's "Pending human-gate" count
  genuinely dropped from 6 to 0 after the two null passes ran — caught only
  because this close happened to review the digest between each pass rather
  than only at the end. Recovered by hand (re-ran `dedup` last, after the
  null passes, so its output is what survives on disk); the underlying
  gap — proposals need the same append-only persistence null_records got —
  is real and should be Thread 4's first fix, not something patched
  unilaterally in a closing pass.
- **Live-deploy finding, security — flagged for Thread 4, credential
  rotation recommended to the operator now.** The `patterns` pass's
  `command_frequency()` mining reads `agent_commands.log` verbatim with
  **no secret-redaction of any kind**. The real `--dry-run` preview above
  surfaced a live plaintext password embedded in a repeated `sshpass -p
  '...' ssh ...` command (6 occurrences, targeting a LAN host). Had this
  pass been run `--no-dry-run`, that password would have been written
  straight into a git-tracked `patterns.json`/`report.md`/`proposals.jsonl`
  under `docs/dreaming/`; had `insights` then run against that
  `patterns.json`, `_domain_command_frequency()` would have sent it
  off-host in a prompt to node3090's LLM as "evidence." Neither happened —
  `patterns` was kept at its `--dry-run` default specifically because of
  this, and `insights` was not run at all this close. The password itself
  is not repeated anywhere in this repo. **Recommended, not yet done**: the
  operator should rotate that credential and move it to Vaultwarden
  (matching how the pfSense API key is already handled), and `dream_runner.py`
  should gain a redaction step (common patterns: `-p '...'`, `password=`,
  `Authorization: Bearer`, etc.) over any raw-command text before it's
  mined, written to disk, or handed to an LLM — this is squarely a
  precondition for Thread 4 (TRAUM-AUTO) even being safe to build, since
  auto-apply and scheduled runs would hit this same log on a timer with no
  human dry-run preview in between.
- **`docs/dreaming/2026-07-11-thread2-close/report.md`** — small
  correction, not new work: its "Why this wasn't applied for real in this
  session" section is now "## Applied" with the real
  `dream_apply.py --no-dry-run` result from when that proposal was actually
  applied live on LUCIFER (`applied=1`, `index_to_kb`'s own dedup path
  fired and merged into an existing near-duplicate doc rather than creating
  a new one) — this had already happened before this close; the doc just
  hadn't been updated to say so.
- **`CURRENT-STATE.md`** — TRAUM row rewritten for Thread 3 close (all of
  3.1/3.2/3.4/3.5/3.6/3.8/3.9 + this close's live findings); 3.3
  (ledger-mining) noted as done-as-a-one-off-analysis
  (`kb/ledger-mining-proposals.md`, real findings against `tasks.db`'s 81
  rows) rather than an automated `dream_runner.py` pass — it was never
  coded as one, and this close doesn't change that. Goethe row bumped to
  v0.4.0-a DEPLOYED. 3.7 (self-measurement) and 3.10's own remaining
  scope beyond this close are folded in as "Thread 4 NOT STARTED."
- **`kb/session-learnings.md`** — Thread 3 close debrief written via the
  unified path, including the operator-judged non-obvious finding for this
  close (see that file — not duplicated here to avoid two slightly-
  diverging copies of the same judgment call).

**Known issues carried forward (recorded, not fixed this close):**
- Same three carried forward from Thread 2's close, still true: no
  `dreamed_at` write path in `dream_apply.py` (done by hand); dedup
  re-proposes already-merged pairs every run (harmless, wasteful); no ES
  snapshot mechanism for true before/after retrieval comparison.
- New this close: `proposals.jsonl` overwrite risk across a multi-pass
  cycle (above) — Thread 4's first fix.
- New this close: `patterns` pass has no secret-redaction (above) —
  blocking for any Thread 4 auto-apply/scheduling work.

---
## 2026-07-12 (Cowork, cont'd x2): TRAUM Thread 3, Prompt 3.9 — test coverage extended (determinism, digest/banner caps, learned-rules target invariant, insight schema), `_dream_banner()`-adjacent docstring audit

Still mid-thread — `CURRENT-STATE.md` untouched, per convention (only
rewritten at thread-close prompts; Thread 3 closes at 3.10). No
`dream_runner.py`/`dream_apply.py`/`dream_digest.py`/`goethe.py` behavior
changed this prompt except one docstring (see below); this was a
tests-and-audit prompt, not a features prompt.

- **`tests/test_dream_patterns.py`** — new `TestPatternsJsonDeterminism`
  class (3 tests): `mine_patterns()` is byte-identical across two calls on
  the same parsed events (pins the module's own documented purity — "no
  file I/O, no network, no randomness, no LLM call"); `write_patterns_json()`
  output is identical run-to-run once the one legitimately non-deterministic
  field (`generated_at`, a wall-clock write timestamp) is excluded; a control
  test confirms a genuinely different fixture log mines a genuinely
  different result, so the first two aren't vacuously true.
- **`tests/test_dream_digest.py`** (new file, 191 lines) — `TestDigestLineCap`
  (4 tests: digest stays at/under `MAX_DIGEST_LINES=30` with a large
  synthetic corpus, is well under the cap on a small one, the cap holds
  across `applied`/`insights`/`pending` entry mixes) and
  `TestDigestOnEmptyCorpus` (2 tests: empty-corpus digest renders and stays
  short).
- **`tests/test_kb_contracts.py`** — new `TestDreamBanner` class (7 tests),
  inserted between the existing `TestChronosTimeBanner` and
  `TestChronosYearStrip` classes, reusing the file's existing fixtures:
  empty valve disables the banner; missing digest file degrades to `""`;
  an unparseable digest (missing either regex group) degrades to `""`;
  a valid digest parses date + pending-gate count into the exact
  `[DREAM] digest=<date> | pending-gate=<N> | read <path> for details`
  format; the 200-char cap (`_DREAM_DIGEST_MAX_CHARS`) is enforced exactly
  on a long path; a short-path digest is left untruncated; the banner is
  appended to `[TIME]` only on `search_kb`'s first call in a session, never
  again (reuses `_time_banner_emitted`, per `_consume_time_banner()`'s own
  docstring — see the docstring fix below).
- **`tests/test_dream_engine.py`** — new `TestPromptRuleTargetInvariant`
  class (19 test methods, incl. parametrized cases), covering Prompt 3.9's
  own named ask ("learned-rules.md never auto-merged: validator rejects
  prompt-rule proposals targeting `prompts/node4090*`") end to end at both
  validation layers: `dream_runner.validate_proposal_shape()` (generation-
  time) rejects any `target_file` other than the exact
  `dr.LEARNED_RULES_TARGET` constant — tested against `None`, empty string,
  `prompts/node4090-v0.6.0.md`, a path-traversal attempt, and a
  correctly-named-but-wrong-directory decoy; `dream_apply.check_prompt_rule_target()`
  re-checks the same invariant at apply-time as defense-in-depth (a
  proposal that only fails the apply-time check, not the shape check, is
  still rejected); and one end-to-end `validate_proposal_for_apply()` test
  confirming the rejection reason names the one allowed path. The
  `_prompt_rule_proposal()` test helper deliberately treats an explicit
  `target_file=None` override as "leave it None," not "unset, use the
  default" — a first draft got this backwards (see below).
- **`tests/test_dream_insights.py`** — closed two real, pre-existing
  coverage gaps in `_validate_insight_item()`/`_insight_to_proposal()`:
  `prompt_rule` sub-object handling had no kept-when-complete/dropped-when-
  incomplete test pair (unlike `kb_fact`/`skill`, which both already had
  one) — added `test_prompt_rule_detail_kept_when_complete`,
  `_dropped_when_incomplete`, `_dropped_when_missing_entirely`,
  `_section_hint_defaults_when_blank`, and
  `test_prompt_rule_never_carries_a_target_file_key` (confirms a
  model-supplied `target_file` inside `prompt_rule` is stripped, not
  passed through — the write target is a fixed code constant, never model
  output). `_insight_to_proposal`'s prompt-rule branch itself had zero
  coverage of any kind before this prompt (the existing parametrized test
  only ever exercised the "no `prompt_rule` key" `None`-returning path) —
  added `test_prompt_rule_with_detail_becomes_append_learned_rule_proposal`
  (asserts `call == "append_learned_rule"`, `args["target_file"] ==
  dr.LEARNED_RULES_TARGET`, and that the resulting proposal passes the
  shared `validate_proposal_shape()` gate) and
  `test_prompt_rule_without_detail_is_none`.
- **`tools/goethe.py`** — one docstring-only fix to
  `Tools._consume_time_banner()`, staged by an `lse-docstring-optimizer`
  audit (below): added one sentence explicitly prohibiting the most likely
  future-editor mistake — adding a second, separate once-per-session gate
  for `[DREAM]` instead of reusing `_time_banner_emitted`, which is what
  guarantees the `[TIME]`/`[DREAM]` banners can never desync. No behavior
  change; verified present at `tools/goethe.py:3546`.
- **`docs/dreaming/docstring-audit-dream-banner-2026-07-12.md`** (new) —
  full `lse-docstring-optimizer` audit of the four `[DREAM]`-banner-adjacent
  artifacts: `_dream_banner()` and the `_consume_time_banner()` addition
  (both private/maintainer-facing, so the skill's rubric scores them mostly
  N/A per its own proportionality rule — one real WARN on
  `_consume_time_banner()`, fixed above), the `DREAM_DIGEST_PATH` Valve
  description (out of scope, admin UI text), and — recognizing the skill's
  real purpose is catching *model*-compliance gaps — the rendered
  `[DREAM]` banner line itself, the one artifact from this feature the
  model actually reads at runtime. That audit surfaced two genuine FAILs
  (Compliance language / Failure prohibitions, and Trigger gate): the
  banner states a pending-review count with zero directive language and no
  stated condition for when the model should act on or mention it, in a
  system whose core invariant (DESIGN.md §2) is that dream proposals are
  strictly human-gated. No behavioral fix was made this prompt — the
  banner is already within a few characters of its 200-char cap in real
  digests, so appending a directive risks silently truncating the
  `read <path> for details` pointer — the doc instead recommends the
  correct fix is a future `prompt-rule` insight through the existing
  human-gated `append_learned_rule` path (Prompt 3.6), landing in
  `prompts/learned-rules.md` for the operator to merge, not a direct
  `goethe.py` edit.
- **Verification, stated plainly:** `python3 -m pytest` run for real
  (not just traced) against `tests/test_dream_corpus.py`,
  `test_dream_digest.py`, `test_dream_engine.py`, `test_dream_insights.py`,
  `test_dream_patterns.py` together: **180 passed, 0 failed.**
  `tests/test_kb_contracts.py`'s new `TestDreamBanner` class was **not**
  run through a live pytest process this prompt — importing it requires
  the full 7211-line `tools/goethe.py`, and the sandbox's mounted repo copy
  used for test execution has an unrelated FUSE staleness bug (see below)
  that leaves its copy of `goethe.py` truncated mid-file (confirmed via
  `ast.parse` raising `SyntaxError: unterminated string literal` at line
  7207); reconstructing all 7211 lines through the file-read pipeline to
  work around it was judged not worth the cost for one test class. Instead
  `TestDreamBanner`'s assertions were independently confirmed by tracing
  `_dream_banner()`'s actual behavior with a standalone live script
  (empty valve, missing file, unparseable digest, valid digest, and the
  exact 200-char cap all produced the documented output) before the test
  class was written — the test class expresses the same checks that
  script already ran live, but the test class itself is unexecuted. This
  is flagged here rather than folded silently into "all green."
- **Known infra issue, unresolved:** the Cowork bash sandbox's FUSE-mounted
  copy of this repo continues to intermittently lag behind the true
  (Windows-side) files for an unpredictable duration after an edit —
  confirmed again this prompt for `test_dream_engine.py`,
  `test_dream_insights.py`, `test_dream_patterns.py`, and `goethe.py`
  (`dream_runner.py`/`dream_apply.py` had caught up by this prompt).
  Workaround used: reconstruct each stale file's true content into
  `outputs/repo_copy/tests/` via the file-read/file-write tools (which are
  always correct, unlike the bash mount), symlink `outputs/repo_copy/tools`
  to the mount's (confirmed-synced) `tools/` directory, and run pytest
  there. This is a sandbox artifact, not a repo bug — noted here again so
  a future session doesn't waste time assuming a real regression.

---
## 2026-07-12 (Cowork, cont'd): TRAUM Thread 3 (TRAUM-INSIGHT), Prompt 3.8 — null-result discipline formalized, `dream_runner.py` v0.7.0 → v0.8.0; first full dream cycle (all 5 passes)

Thread 3 status update: 3.1 patterns, 3.2 insights, 3.4 digest, 3.5
in-session banner, 3.6 prompt-rule proposals, and now 3.8 null-result
discipline are implemented; 3.3 ledger-mining and 3.7/3.9/3.10 are not —
still a mid-thread prompt, `CURRENT-STATE.md`'s TRAUM row stays as-is per
the project's convention of only rewriting it at each thread's close
prompt. (3.7, self-measurement, was skipped in plan order to do 3.8 first
per the prompt actually run this session — no dependency between them.)

- **`tools/dream_runner.py`** (v0.7.0 -> v0.8.0) — every `run_pass_*()`
  (`dedup`, `stale-contradiction`, `error-cluster`, `patterns`, `insights`)
  now returns a 3-tuple `(proposals, narrative, null_record)` instead of
  2. `null_record` is a new structured dict (`_null_record()`, new
  function ahead of `run_pass_dedup`) — `pass`, `result="null"`, `reason`
  (short greppable code, e.g. `empty_kb`, `no_candidate_pairs`,
  `all_domains_empty`), `looked` (bool), `corpus_size` (dict of plain
  counts the pass actually examined), `thresholds` (dict of the config
  values applied) — or `None` when the pass produced >=1 proposal or
  otherwise has something non-null to show. This formalizes the "Null
  result (PH3-2)" PROSE every pass has narrated since Prompt 2.2 into
  something machine-readable: `looked=True` means the pass genuinely
  inspected `corpus_size`-worth of data at `thresholds` and still found
  nothing ("nothing there"); `looked=False` means an upstream gate — empty
  index, unreachable Ollama, missing/empty log window — stopped it before
  it could look at anything at all ("didn't look"). Each pass's early-return
  gates were audited individually for which case applies (e.g. dedup's
  "lse-kb returned zero docs" is `looked=False`, but "candidate pairs found
  above the floor but none reached the merge threshold" is `looked=True`
  since embeddings and pairwise cosine actually ran). The `patterns` pass
  needed its own null definition since it never emits proposals in the
  first place (raw-analytics pass, DESIGN.md §6.2 proposal types don't
  include it): null is now "all four mechanical sub-passes (command
  frequency, failure-retry, tool usage, automation candidates) came back
  empty", distinct from the pre-existing "Null sub-result" partial-empty
  narrative (kept, unchanged, no `null_record` attached — only genuinely
  ALL-empty gets the structured record). `stale-contradiction` bundles its
  two sub-passes (reverify + demote) into one `null_record` only when BOTH
  are null this run.
- **`write_report()`** gained an optional `null_record` parameter
  (default `None` — every pre-3.8 2-positional-arg call site still works).
  When set: report.md gets a new, dedicated "## Null result" section
  (Prompt 3.8's "report.md says so plainly" — not left buried inside the
  `## Narrative` prose above it) stating the looked/didn't-look verdict,
  corpus size examined, and thresholds used; the SAME record is also
  appended (`"at"` mode, never overwritten) to the new
  `<dream-dir>/<date>/null-results.jsonl`. This is deliberate and
  necessary: report.md and proposals.jsonl are both documented
  single-pass-per-invocation snapshots (`write_report()`'s own module
  comment, `dream_digest.py`'s `gather_top_insights()` docstring) — the
  LAST pass run that day overwrites both. A full dream cycle runs five
  passes in sequence against the same day-dir, so without an append-mode
  file, only the final pass's null verdict (if any) would survive the day
  — null-results.jsonl is the one artifact every pass's null verdict
  for the day survives intact, same `"at"` convention `dream_apply.py`
  already uses for `applied.jsonl`/`rejected.jsonl`.
- **`main()`** unpacks the new 3-tuple, passes `null_record` through to
  `write_report()`, and appends a `null_result=<reason> (looked=<bool>)`
  suffix to its own stderr done-line when set.
- **`tests/test_dream_patterns.py`** — the two existing null-result tests
  (`test_null_result_when_log_missing`,
  `test_null_result_when_log_has_only_bootstrap_lines`) updated for the
  3-tuple return and now assert `null_record`'s shape directly (both are
  `looked=False`, per the reasoning above). New
  `test_null_result_when_all_domains_empty_but_events_present`: a
  DONE-only log (no CMD ever) exercises the `all_domains_empty` /
  `looked=True` branch specifically — verified by reading
  `tool_usage_by_week()`'s own docstring ("DONE is CMD's own completion
  marker, not a distinct tool" — DONE-tagged events are excluded from that
  domain too) before picking the fixture, since a NOTE/other-tag line
  would NOT trigger this branch (it would still populate
  `tool_usage_by_week`). The other five `run_pass_patterns()` call sites
  in this file fixed to 3-tuple unpacking (no behavior assertions added —
  they weren't null-result tests).
- **`tests/test_dream_insights.py`** — `test_null_result_when_nothing_to_feed`
  updated for the 3-tuple return, now asserts `null_record` (`looked=False`,
  `reason="no_data_to_feed"`); `test_end_to_end_with_mocked_llm` fixed to
  3-tuple unpacking with an added `assert null_record is None` (a real
  insight was accepted that run).
- **`docs/dreaming/dream-run-2026-07-12-full-cycle.md`** (new) — the
  Prompt 3.8 "run a full dream cycle now" deliverable: all five passes
  traced against this sandbox's actual state (no `manifest.db`, no
  reachable ES, no `agent_commands.log` — same constraint as every
  2026-07-12 entry). Every pass correctly emits `looked=False` (a genuine
  "didn't look", not "nothing there") rather than crashing or fabricating
  a finding; `dream_digest.refresh_digest()` degrades the same way. Real
  execution against the live LUCIFER corpus (near-duplicate `lse-kb`
  docs, actual TTL expiry, actual repeated command sequences) remains the
  next real dream cycle, not this session's.
- **Verification note:** same constraint as every 2026-07-12 entry above —
  no live `/opt/local-se`, ES, or Ollama in this sandbox this session.
  Verified by full manual read-through of every edited function (all five
  `run_pass_*`, `_null_record`, `write_report`, `main`) plus both edited
  test files, region by region, checking return-arity consistency, paren/
  quote balance, and control flow — the same method the 2026-07-12 Prompt
  3.6 entry above used and explained why (`run_tests`/`py_compile` not
  usable: this session's sandbox mount of the repo is stale, showing
  `tools/dream_runner.py` truncated at 2,840 of its true (now) 3,194 lines
  on every retry, a worse case of the same staleness the Prompt 3.6 entry
  hit). `tests/test_dream_patterns.py` and `tests/test_dream_insights.py`
  were NOT executed under pytest for the same reason (pytest itself isn't
  installed in this sandbox either) — the new
  `test_null_result_when_all_domains_empty_but_events_present` fixture was
  traced by hand against `infer_sessions`/`session_command_lists`/
  `tool_usage_by_week`/`command_frequency`/`find_failure_retries` to
  confirm it actually lands on the `all_domains_empty` branch rather than
  asserted by construction.

---
## 2026-07-12 (Cowork, cont'd): TRAUM Thread 3 (TRAUM-INSIGHT), Prompt 3.6 — `prompts/learned-rules.md` + `append_learned_rule`, `dream_runner.py` v0.7.0 / `dream_apply.py` v0.2.0

Thread 3 status update: 3.1 patterns, 3.2 insights, 3.4 digest, 3.5
in-session banner, and now 3.6 prompt-rule proposals are implemented; 3.3
ledger-mining and 3.7-3.10 are not — still a mid-thread prompt,
`CURRENT-STATE.md`'s TRAUM row stays as-is per the project's convention of
only rewriting it at each thread's close prompt.

- **`tools/dream_runner.py`** (v0.6.0 -> v0.7.0) — the insights pass
  (Prompt 3.2) now handles `proposed_change: "prompt-rule"` as a real
  proposal instead of report.md-only. `_INSIGHT_SCHEMA_BLOCK` gained a
  `prompt_rule: {rule, rationale, section_hint}` sub-object (mirroring
  `kb_fact`/`skill`'s own pattern); `_validate_insight_item` validates it
  (non-empty `rule`/`rationale`, same discipline as the other two);
  `_insight_to_proposal` emits `{"type": "prompt-rule", "call":
  "append_learned_rule", "args": {"target_file": LEARNED_RULES_TARGET,
  "rule", "rationale", "section_hint", "provenance", "source_tier":
  "inferred"}, "evidence": [...]}`. The critical property (plan §3.6: "NEVER
  direct edits to the canonical node4090 prompt"): `target_file` is a new
  module constant, `LEARNED_RULES_TARGET = "prompts/learned-rules.md"`,
  hard-coded in `_insight_to_proposal` — never read from the model's own
  output at generation time, so there is no field through which an injected
  episode could steer the write target. `KNOWN_PROPOSAL_TYPES` gained
  `"prompt-rule"`; `validate_proposal_shape()` gained a structural check
  (Prompt 3.9's own named test, done one prompt early since the type exists
  now: rejects any `prompt-rule` proposal whose `args.target_file` isn't
  exactly `LEARNED_RULES_TARGET`, or whose `rule`/`rationale` is empty)
  ahead of `dream_apply.py`'s apply-time re-check of the same thing.
  Updated three places that previously said "prompt-rule/tool-change are
  report.md-only" (CLI help text, `_insight_to_proposal`'s docstring,
  `run_pass_insights`' narrative) — only `tool-change` still has no write
  path of any kind.
- **`tools/dream_apply.py`** (v0.1.1 -> v0.2.0) — the apply-time half.
  `check_prompt_rule_target()` re-validates `append_learned_rule` proposals'
  `target_file` against the same `dr.LEARNED_RULES_TARGET` constant at
  apply time (belt-and-suspenders against a hand-edited `proposals.jsonl`,
  same reasoning as the existing `check_provenance_format()`), wired into
  `validate_proposal_for_apply()` alongside the other invariant checks —
  DESIGN.md §2 row 3 gained clause (f). `render_group()` gained an
  `append_learned_rule` confirm-gate block (target_file/section_hint/
  provenance/source_tier/evidence-refs, `rule`+`rationale` as multiline
  fields) and its `TARGET:` header logic now also recognizes
  `args.target_file`, not just `args.doc_id`. `apply_group()` gained a new
  `append_learned_rule` branch calling the new `append_learned_rule()`
  function — **the one call in this file that never touches ES**: it
  appends one `## Pending` entry to `prompts/learned-rules.md` (creating
  the file with a fixed header if it doesn't exist yet), resolved against a
  new `--repo-root`/`GOETHE_REPO_ROOT` option (default: cwd) rather than
  ES/Tools at all. Dry-run behavior is unchanged — the existing top-of-loop
  `if dry_run: ... continue` already short-circuits before this branch,
  same as every other call type, so no special-case was needed there.
- **`prompts/learned-rules.md`** (new, seeded) — created with the header +
  `## Pending`/`## Merged` structure DESIGN.md §8.4 specifies. Seeded with
  one `## Pending` entry recording an explicit **null result** for "seed
  learned-rules.md with any accepted insights from prompts 3.2-3.3" (the
  plan's own Prompt 3.6 text): Prompt 3.2 has only ever been exercised
  against synthetic fixtures in this Cowork session (no live
  `/opt/local-se` corpus available, per the 2026-07-12 Prompt 3.4/3.5
  entries above), and Prompt 3.3 (ledger-mining) is not implemented yet —
  there is no real, evidence-backed `prompt-rule` insight to seed, so one
  wasn't fabricated (PH3-2 null-result discipline, applied here one prompt
  early since plan Prompt 3.8 is where that discipline is formally
  generalized).
- **`docs/dreaming/DESIGN.md`** — new §8 ("Prompt-rule proposals —
  `prompts/learned-rules.md`"): why this proposal type gets its own write
  path instead of reusing Tools (§8.1), the proposal shape (§8.2), the
  target-fixed-in-code invariant enforced at both generation and apply time
  (§8.3), the file's `## Pending`/`## Merged` structure (§8.4), the
  operator's manual merge-into-next-node4090-version-bump workflow (§8.5),
  and this prompt's own seeding status (§8.6, the null-result explanation
  above). Noted but NOT fixed in this pass: the file already had two
  differently-worded `## 7` sections (Thread 2 Prompt 2.6's auto-apply
  policy, apparently drafted twice) before this edit — out of scope for
  Prompt 3.6, flagged here so it isn't mistaken for something this entry
  introduced.
- **Verification note:** no live `/opt/local-se`, ES, or Ollama available
  in this session (same constraint every 2026-07-12 entry above has noted);
  changes verified by full manual read-through of every edited region in
  both files (bracket/quote balance, control flow) rather than by
  `run_tests`/`py_compile` — this session's sandbox mount of the repo
  proved stale mid-session (showed a truncated, pre-edit byte count of
  `tools/dream_runner.py`/`tools/dream_apply.py` on every retry), so
  in-sandbox compilation wasn't usable as a check this time. Formal pytest
  coverage (`learned-rules.md never auto-merged` etc.) is Prompt 3.9's job
  per the plan, not this one — flagging the unusual verification method
  here rather than silently asserting `run_tests` was green when it wasn't
  run.

---
## 2026-07-12 (Cowork, cont'd): TRAUM Thread 3 (TRAUM-INSIGHT), Prompt 3.5 — `goethe.py` v0.4.0-a, [DREAM] banner surfaced in-session

Thread 3 status update: 3.1 patterns, 3.2 insights, 3.4 digest, and now 3.5
in-session banner are implemented; 3.3 ledger-mining and 3.6-3.10 are not —
still a mid-thread prompt, `CURRENT-STATE.md`'s TRAUM row stays as-is per the
project's convention of only rewriting it at each thread's close prompt.

- **`tools/goethe.py`** (v0.4.0 -> v0.4.0-a) — wired `tools/dream_digest.py`'s
  `latest-digest.md` into session start the CHRONOS way: server-injected, not
  docstring-dependent. `_consume_time_banner()` was already the single
  once-per-session gate for the `[TIME]` banner on the first `search_kb`
  return (CHRONOS-2, v0.3.1); it now also calls a new `_dream_banner()` and
  appends its result. `_dream_banner()` reads the new `DREAM_DIGEST_PATH`
  valve (default `/opt/local-se/dreams/latest-digest.md`), regex-parses the
  digest's own header date (`generated YYYY-MM-DD`) and its
  `## Pending human-gate (N)` count, and renders
  `[DREAM] digest=<date> | pending-gate=<N> | read <path> for details`,
  hard-capped at 200 chars (`line[:200]`, defense-in-depth on top of the
  format already being well under the cap). Missing valve, missing file, or
  an unparseable digest all degrade to `""` (no `[DREAM]` line) rather than
  raising — same non-fatal discipline as `dream_digest.py`'s own `gather_*`
  steps; the `[TIME]` banner is never affected either way. Deliberately
  minimal per the PH5-2 warning (plan §2, `docs/traum-dreaming-plan.md`):
  one valve, one new private method, a 3-line change to an existing method —
  no restructuring of this god-class (still ~7,100 lines; PH5-2 extraction
  of `goethe_kb.py` remains undone and unblocked by this change).
  Verified in-session (no live `/opt/local-se` available here): synthetic
  `latest-digest.md` fixture -> correct `[DREAM]` line, appears alongside
  `[TIME]` exactly once per session then goes silent on subsequent calls;
  missing digest file and a malformed digest (no parseable header) both -> no
  `[DREAM]` line and no exception; empty `DREAM_DIGEST_PATH` -> banner fully
  disabled. Formal pytest coverage is Prompt 3.9's job, not this one.
  **DEPLOY NOTE:** existing `llama-ui` threads do not pick up this change —
  each needs a fresh thread after `goethe_mcp.py` restart for the `[DREAM]`
  banner to appear, same as any other `Tools`-class behavior change.
- **`VALVES.md`** — new `DREAM_DIGEST_PATH` row under the TRAUM dreaming
  section (§4), same table as `EPISODE_DIR`/`DREAM_DIR`/etc.

---
## 2026-07-12 (Cowork): TRAUM Thread 3 (TRAUM-INSIGHT), Prompt 3.4 — `tools/dream_digest.py` v0.1.0 morning digest; `tools/dream_apply.py` v0.1.1 bug fix

Thread 3 is still open (3.1 patterns, 3.2 insights, and now 3.4 digest are
implemented; 3.3 ledger-mining, 3.5 in-session banner, and 3.6-3.10 are not
— this is a mid-thread prompt, not a thread close, so `CURRENT-STATE.md`'s
TRAUM row is intentionally left as-is per the project's own convention of
only rewriting it at each thread's close prompt).

- **`tools/dream_digest.py`** (3.4, new, v0.1.0) — generates
  `/opt/local-se/dreams/latest-digest.md`, <=30 lines, hard-capped
  deterministically (earliest content kept, one truncation-marker line if
  cut). Four sections: (1) applied-overnight — real (non-`--dry-run`)
  `applied.jsonl` entries from the current cycle's day-dir; (2) top 3
  insights — parsed back out of `report.md`'s "## Cross-session insights"
  heading (Prompt 3.2's own narrative format), searching backward across
  day-dirs since `report.md` is one shared file per day-dir that the last
  pass run that day overwrites; (3) pending human-gate items — proposals
  whose content-hash isn't yet in that day's `applied.jsonl`/`rejected.jsonl`,
  a lightweight preview of what Prompt 4.4's `dream_apply --queue` will
  formalize later; (4) one-line corpus stats — `manifest.db` session counts
  plus best-effort `lse-kb`/`lse-errors`/`lse-skills` ES doc counts. Every
  gather step is independently exception-guarded (one bad file degrades one
  section to a null-result line, not the whole digest — PH3-2 discipline).
  `refresh_digest()` is the integration point; it never raises. Wired into
  the end of both `dream_runner.py`'s and `dream_apply.py`'s `main()` — "at
  the end of every dream run" covers both the proposing half and the
  applying half. No live `/opt/local-se` or ES available in this session;
  validated against synthetic `manifest.db`/`dreams/` fixtures instead
  (empty-corpus null result, populated cycle with a same-day pending pair,
  applied/pending state flip after simulated `dream_apply`, and a
  forced-low-cap run to exercise the hard-truncation branch).
- **`tools/dream_apply.py`** (v0.1.0 -> v0.1.1, bug fix) — `main()` opened
  `applied_f = open(applied_path, ...)` with `applied_path` never assigned
  (only `rejected_path` was); every real run with >=1 proposal would have
  raised `NameError` before writing anything. Fixed by defining
  `applied_path = os.path.join(dream_dir, "applied.jsonl")` alongside
  `rejected_path`, matching the module docstring's own stated output
  contract ("writes `applied.jsonl` ... and `rejected.jsonl`"). Found while
  building dream_digest.py's applied-overnight section, which reads that
  same file.

---
## 2026-07-11 (Cowork, cont'd): TRAUM Thread 2 (TRAUM-ENGINE) CLOSED — `tools/dream_apply.py` v0.1.0 apply gate (2.5), auto-apply policy (2.6, DESIGN.md §7, still empty), first supervised dream + calibration (2.7-2.8), invariant tests (2.9, `tests/test_dream_engine.py`), thread close (2.10)

Closes out the same-day Thread 2 entry below (dream_runner.py 2.1-2.4). Every
proposal Thread 2 has ever generated has now passed through a human
confirm-gate at least once, live, on the real ~368-doc `lse-kb` — this is
Thread 2's own dogfood run, not a synthetic exercise.

- **`tools/dream_apply.py`** (2.5, new, v0.1.0) — the apply gate. Re-validates
  every proposal against the code-enforced invariants fail-closed (never
  raise quality, never `source_tier=ground_truth`, never touch a quarantined
  doc except the named exception, evidence ≥20 chars) using the doc's LIVE
  state at apply time, not the proposal's generation-time snapshot. Renders
  the exact SCRIBE-1 confirm-gate block shape (`docs/dreaming/DESIGN.md` §6.4)
  and asks a per-proposal yes/no; dedup pairs (`pair_id`-linked) are
  confirmed and applied as one unit. Applies through `goethe.py`'s own
  `Tools` class, dynamically loaded exactly the way `goethe_mcp.py` does it
  — one write path regardless of caller. Logs every rejection (invariant or
  human "no") with reason to `applied.jsonl`/`rejected.jsonl`.
- **`index_to_kb` ("kb-fact") dispatch — completed this close, not new in
  2.5.** DESIGN.md §6.2 (Thread 1, Prompt 1.5) already specified `kb-fact` as
  the fifth proposal type dream_apply.py "reuses verbatim" from the SCRIBE-1
  debrief format, but Prompt 2.5's original `apply_group()`/`render_group()`
  only wired up the four Thread-2-pass call types (`mentor_correct`,
  `record_outcome`, `kb_verify`, `skill_record`) — a real gap, silently
  present since 2.5, only surfaced while preparing this close's own
  kb-fact debrief proposal (see below). Fixed: `index_to_kb` now has a full
  apply-time dispatch branch and a DESIGN.md §6.4-shaped confirm-gate render
  (title/topic/source_tier/quality_score/verified_against/volatility/
  evidence/content). Like `mentor_correct`/`record_outcome`, `index_to_kb`
  has neither `provenance` nor `origin` — it gets the same full stamp
  (both fields), located via the `doc_id=...` parsed out of its own "KB
  created"/"KB updated (refined)" return string. `tests/test_dream_engine.py`
  gained a `TestKbFactProposal` class (4 tests) covering this path;
  `FakeES.index()` in that suite was corrected from an unconditional-raise
  to a real recording stub once this surfaced that `index_to_kb`/
  `skill_record` legitimately call `es.index()` for a brand-new doc (only
  `es.delete()` is truly forbidden — no hard-delete tool exists anywhere in
  this codebase).
- **Auto-apply allowlist (2.6, design only)** — added `docs/dreaming/DESIGN.md`
  §7: `dedup` is eligible only for the identical-pair subcase (cosine ≥0.99
  AND `verified_against` populated and character-identical on both sides);
  `reverify` is eligible (a `kb_verify` tag changes no content); `demote`,
  `skill-candidate`, and `kb-fact` are permanently or provisionally excluded
  (each creates or removes trust rather than just tagging). This closes a
  dangling reference — `docs/dreaming/calibration-run-1.md` (written during
  2.8) already cited "DESIGN.md §7.1"/"§7.2" before §7 existed; the section
  now matches what those citations assumed. `GOETHE_DREAM_AUTO_APPLY` stays
  `""` (empty) — the promotion bar (2 consecutive weeks, zero
  rejected-in-hindsight, per type) is Thread 4's to measure, not earned yet
  off one calibration run.
- **First supervised dream (2.7)** — full backlog: 13/13 previously-undreamed
  sessions, full `lse-kb` (368 docs), full `lse-errors` (32 docs). `dedup`:
  3/3 pairs applied (cosine 0.98–1.00, all genuine same-claim duplicates,
  none had `verified_against` set so none qualified for the new §7.2
  auto-apply subcase anyway — correctly stayed human-gated). `stale-
  contradiction` reverify: 0 TTL-expired docs, valid null result. `stale-
  contradiction` contradiction: **0/7 valuable — 100% false-positive rate**
  on verbatim-evidence review (non-sequitur pairings, category mismatches,
  historical-vs-live claim confusion, a self-contradictory proposal, a
  hostname/IP conflation) — the concrete, first-run demonstration of why
  DESIGN.md's threat model rules `demote` out of auto-apply permanently.
  `error-cluster`: 0/1 — the one skill-candidate was built entirely from a
  `tests/test_dream_corpus.py` fixture that leaks into the real episode
  corpus (missing `GOETHE_EPISODE_DIR` monkeypatch — flagged, not fixed
  this run, see Known issues below). See `docs/dreaming/dream-run-2026-07-11.md`
  for the full per-item breakdown. Also surfaced: `dream_runner.py`/
  `dream_apply.py` must run under `/home/sy5/owui/bin/python3` on LUCIFER
  (bare `python3` has an incompatible `elasticsearch==9.4.1`) — undocumented
  until now.
- **Calibration measurement (2.8)** — `docs/dreaming/calibration-run-1.md`.
  Production `linear` retrieval mode is **bit-for-bit identical**
  (recall@1=0.76, recall@3=0.84, MRR=0.800) before vs after the dream despite
  ~84% corpus growth (≈200→368 docs) since the last recorded sweep.
  `min_score=4.2` re-swept per its own maintenance rule ("re-sweep after
  major KB growth") and holds: 38/38 correct top-1 hits kept at the 4.020
  cut, 0 correct lost — same shape as the v0.3.8 finding. `lse-kb` doc count
  unchanged at 368 (dedup demotes, never deletes). 3 demotions applied,
  quality 0.50→0.35. **Verdict: no regression — clear to open Thread 3.**
  Two non-blocking findings carried forward (see Known issues below).
- **Invariant tests (2.9)** — `tests/test_dream_engine.py`, 16 tests, fully
  mock-based (no live ES/Ollama/goethe.py needed): proposal-validator
  rejection of the three hard invariants (quality-raise, `ground_truth`,
  quarantine-touch, plus the `quarantine-delete-request` exception),
  origin/provenance stamping against a disposable in-memory doc, dedup
  trust-field union (keep-doc only, retire-doc untouched), dream_runner's
  ES-read-only boundary, dream_apply's dry-run-makes-zero-ES-calls
  guarantee, and (added during this close) the `kb-fact`/`index_to_kb`
  path. Written to run alongside `tests/test_kb_contracts.py` (live-ES
  contracts) without conflict — different fixtures, no shared state.

**Known issues carried forward (recorded, not fixed this close):**
- `dream_apply.py` has **no code path that sets `manifest.db`'s
  `dreamed_at`** despite `episode_index.py`'s own comment claiming it is
  "set by Thread 2's dream_apply.py" — the 2.7 run marked all 13 sessions
  by hand (`sqlite3 UPDATE`). A real gap between the two files; whichever of
  dream_runner.py (knows the session list) or dream_apply.py (knows what
  was actually reviewed) should own this is a design call for Thread 3's
  first prompt, not made unilaterally in this closing pass.
- The dedup pass's candidate query (`match_all` over `lse-kb`) doesn't
  exclude docs already demoted by a prior dedup merge, so a resolved pair
  keeps re-surfacing on every subsequent run (confirmed live: the same 3
  pairs re-detected in 2.8's fresh dry-run). Harmless if a human keeps
  saying yes, but wasteful and a "why is this here again" trap.
- `tests/test_dream_corpus.py::test_tool_exception_still_propagates_after_journaling`
  doesn't monkeypatch `GOETHE_EPISODE_DIR`, so its real `_journal()` call
  writes synthetic `method_raises` episodes into the live corpus on every
  test run — traced as the root cause of 2.7's one false error-cluster
  proposal.
- No ES snapshot mechanism exists for a true same-day before/after
  retrieval comparison (2.8 used the last recorded baseline, 7 days stale,
  as "before"). Thread 4 Prompt 4.5 (A/B eval design) should specify one.

## 2026-07-11 (Cowork, cont'd): TRAUM Thread 2 (TRAUM-ENGINE) — `tools/dream_runner.py` dedup (2.2), stale/contradiction (2.3), and error-cluster (2.4) passes shipped and verified live; Goethe v0.3.9 → v0.4.0

Continues the same-day Thread 1 entry below. Thread 2 is the offline dream
runner itself (`docs/traum-dreaming-plan.md`) — reads the corpus Thread 1
built, proposes but never applies (`dream_apply.py`, Prompt 2.5, is still
not started; every proposal below requires a human confirm before anything
touches ES).

- **`tools/dream_runner.py`** (2.1, new) — offline, read-only runner.
  Scans `manifest.db` for `dreamed_at IS NULL` sessions, reads their episode
  JSONL, drives the local model through the same endpoint cascade as
  `goethe.py`'s node planner (`DREAM_LLM_URL` forced endpoint →
  `NODE3090_LLM_URL` → `NODE3090_OLLAMA_URL`, `thinking_budget_tokens=0`,
  two-attempt envelope retry). Writes `dreams/YYYY-MM-DD/{report.md,
  proposals.jsonl}`, gated by `--dry-run` (default true). Zero
  `es.index/update/delete` call sites in the file by construction — dedup
  and stale-contradiction passes below only ever *propose* calling
  `mentor_correct`/`record_outcome`/`kb_verify`, never call them directly.
- **Dedup pass (2.2)** — embeds every `lse-kb` doc (Ollama nomic-embed-text,
  same `search_query:` prefix quirk as `search_kb`/`index_to_kb` so fresh
  embeddings are comparable to what's already indexed), pairwise cosine,
  filters out same-source-document chunk pairs (titles differing only by
  a `(part N)` suffix — a real false-positive class found live: adjacent
  chunks of one big doc, not independent duplicates), then has the model
  confirm each remaining candidate is a genuine same-claim duplicate
  before proposing a merge. Each confirmed pair becomes one
  `mentor_correct` proposal (keep-doc, merged text, quality raised) +
  one `record_outcome(success=False)` proposal (retire-doc, nudges toward
  the existing KB-DECAY quarantine path — no hard-delete tool exists, so
  retirement reuses the demotion primitive). **Calibration finding, run
  live against Ollama:** a genuine near-duplicate pair scored cosine=0.82,
  well under `index_to_kb`'s inherited 0.92 dedup threshold — defaults
  lowered (floor 0.75, sample thresholds 0.78/0.82/0.86) so the
  `--sample-labels` worksheet mode has real pairs to show. Ran for real
  against the live ~365-doc `lse-kb`: 988 candidate pairs (after dropping
  88 same-chunk pairs); worksheet saved to
  `eval/dedup-threshold-labels-2026-07-11.md`, human labeling in progress.
- **Stale/contradiction pass (2.3)** — two independent sub-passes. (a)
  **reverify**: deterministic CHRONOS TTL check reusing `search_kb`'s own
  `_TTL_DAYS`/`_is_expired` math verbatim; eligible only with volatility
  *explicitly* set (absent ≠ hands-off per corpus-audit.md's 79%-unscored
  finding), `verified_against` non-empty (else `kb_verify` phase 1 is a
  no-op), and not already quarantined. Zero candidates in the live corpus
  right now — real null result, not a bug (the 34 volatility+verified
  docs are all ≤8 days old). (b) **demote**: for each undreamed session,
  doc_ids surfaced via `search_kb` are parsed straight out of its own
  return text (`doc_id=<_id>` per hit), then cross-checked against that
  session's other tool results for a genuine, model-judged contradiction.
  Both sides must be quoted verbatim; the validator re-checks each quote
  is a REAL substring of its claimed source (code-enforced, not just
  prompted) — proven live with a fabricated-quote unit test (2/3
  synthetic candidates correctly rejected). One demote per `doc_id` per
  run (a single finding surfaced via 3 separate evidence lines was, before
  this fix, about to triple-demote the same doc — caught on the first
  live run). Ran for real against 12 live sessions: 3 sessions had both a
  high-quality surfaced doc and other evidence to check; 5 confirmed
  contradictions, including a real `[llama-server]` JSON parse failure
  (control character in a reply) correctly recovered by the two-attempt
  retry loop.
- **`tools/goethe.py` v0.3.9 → v0.4.0** — no code changed in this file for
  the bump. Recorded because its write surface (`mentor_correct`,
  `record_outcome`, `kb_verify`) now has a second, non-interactive
  consumer in its design (`dream_runner.py`'s proposals) for the first
  time — see the v0.4.0 changelog entry in the file's own docstring.
- **Error-cluster pass (2.4)** — groups `lse-errors` docs + episode
  error/timeout occurrences by embedding similarity (union-find over the
  cosine≥0.80 graph); clusters with ≥3 episode occurrences spanning ≥2
  sessions get a drafted `skill-candidate` proposal (`skill_record` body:
  task/procedure/verification/preconditions/failure_modes,
  `provenance=dream-YYYY-MM-DD`, `source_tier=inferred` so it can never
  self-grant `ground_truth`). `skill_record` has no `trigger` parameter
  (DESIGN.md §6.3), so the drafted trigger text is folded into
  `procedure`'s own opening line and kept as a separate top-level
  `trigger` field on the proposal for confirm-gate readability; the
  cluster's full episode-id list rides as a top-level `evidence` field
  (skill_record itself has no evidence arg either). A matching
  `lse-errors` doc contributes prior-art context (its `resolution` text)
  but never counts toward the occurrence/session bar — it's an aggregate
  with no verifiable per-session breakdown of its own. Ran for real: 45
  items embedded (13 episode occurrences + 32 `lse-errors` docs), 35
  clusters, 1 qualified (6 occurrences across 6 sessions — a
  `method_raises` contract-test artifact from Thread 1's own journaling
  test suite, correctly clustered and drafted, though not a genuine
  production incident; a human at the confirm-gate would reasonably
  reject it as noise, which is exactly what the gate is for).
  **Archetype retrospective (per the prompt's explicit ask):** would the
  corpus have caught the exit-255 ControlMaster storm (2026-07-04, 11
  failed attempts) or the Grafana `GF_ADMIN_PASSWORD` env-var confusion
  (2026-06-07)? **No, for two different reasons.** The exit-255 storm
  *is* in `lse-errors` (doc `f9f1e7f511ca19d3`), but as one aggregate
  occurrence (`occurrence_count=1`) — episode journaling (the only source
  of per-session occurrence data this pass counts) didn't exist until
  today, a week after the incident, so there was never more than one
  timestamped occurrence to cluster. Notably, the *exact same* failure
  class recurred twice, live, during this build-out session (two
  `ssh_run exit 255 ... node3090 ControlMaster` episodes, different
  sessions) — one more occurrence and this pass would flag it for real.
  The Grafana env-var confusion has zero footprint in either `lse-errors`
  or episode JSONL — it lives only as unindexed prose in
  `kb/session-learnings.md` (2026-06-07, pre-dates SCRIBE-1's structured
  backfill by over a month), which this pass doesn't read; it's invisible
  to this pass's inputs categorically, not merely under-clustered.
- **Not yet done:** `dream_apply.py` (2.5, the only code allowed to
  actually write ES — Thread 2's last prompt) and the dedup threshold
  labeling exercise's human sign-off (worksheet generated, awaiting Joe's
  labels on the sampled pairs).

---
## 2026-07-11 (Cowork): TRAUM Thread 1 (TRAUM-CORPUS) complete — goethe_mcp v1.10.0 → v1.11.1, SCRIBE-1/2/3 shipped as the unified debrief write path

Closes `docs/traum-dreaming-plan.md` Thread 1 (Prompts 1.1–1.10). TRAUM is the
out-of-band "dreaming"/reflection workstream absorbing SCRIBE-1..5 (ROADMAP
Workstream E) — this thread builds the corpus side (episode journaling +
manifest) and the human-facing half of the unified write path; Threads 2–4
(offline dream runner, apply gate, eval) are not yet started.

- **`docs/dreaming/corpus-audit.md`** (1.1) — per-surface readiness verdict on
  `agent_commands.log`, `tasks.db`, `lse-kb`/`lse-errors`/`lse-skills`,
  `session-learnings.md`. Key finding: `stale`/`volatility` fields absent
  (not `false`) on 79–88% of `lse-kb` docs pre-dating CHRONOS-3/KB-DECAY.
- **`docs/dreaming/DESIGN.md`** (1.2) — dataflow diagram, §2 architecture
  invariants as testable assertions, episode JSONL schema, redaction rule
  list, Shostack 4-question threat model on the dream write path, §6 SCRIBE-1
  confirm-gate proposal format (the contract Thread 2's `dream_apply.py` must
  reuse verbatim). `HERMES_API_KEY` explicitly excluded from the redaction
  rule list (decommissioned, not a live secret) — a generic `*_API_KEY`
  catch-all covers any replacement.
- **`tools/goethe_mcp.py` v1.10.0 → v1.11.1** (1.3, 1.4, 1.8) — every tool
  call now appends one redacted, size-capped JSONL line to
  `$GOETHE_EPISODE_DIR/YYYY-MM-DD/<session>.jsonl`, written even on failure,
  never blocking the underlying call (wrapped try/except/finally in
  `register()`). v1.10.0: journaling + redaction (vault secrets, Bearer
  tokens, `*_KEY`/`*_TOKEN`/`*_SECRET`/`*_PASSWORD` valve pattern, last-resort
  regex sweep) + real MCP session identity via the SDK's `request_ctx`
  contextvar (fallback `gw-<pid>-<epoch>` only when unavailable). v1.11.0:
  size hygiene — day-dir refuses new lines past `GOETHE_EPISODE_DAY_CAP_MB`
  (default 500MB, loud stderr warning, tool call itself unaffected);
  30s-cached size check to avoid a directory walk per call. v1.11.1: **bugfix**
  — `_SENSITIVE_TOOLS` (`get_vault_secret`/`set_vault_secret`/`vault_unlock`/
  `list_vault_items`) were blanket-redacting args but not the RESULT, meaning
  a vault secret's actual return value could reach the episode log unredacted
  unless it happened to match a known valve value. Caught by a new contract
  test (`test_journal_redacts_vault_tool_call_entirely`), not by inspection —
  fixed by adding a result-side blanket-redaction branch ahead of the
  string/JSON branches.
- **`tools/episode_index.py`** (1.4, new) — manifest builder
  (`/opt/local-se/episodes/manifest.db`: session_id, start_ts, end_ts,
  n_calls, n_errors, tools_used, bytes, `dreamed_at`) + rotation (gzip
  day-dirs older than 7 days). UPSERT preserves `dreamed_at` across re-scans
  so a manifest rebuild never un-marks episodes Thread 2 already consumed.
- **`skills/lse-session-debrief/SKILL.md`** (1.5, 1.6) — SCRIBE-1: Step 4 now
  additionally classifies the entry's own bullets into structured
  `index_to_kb`/`skill_record` proposals, rendered in the SAME confirm block
  as the file write and committed on ONE human yes (no separate per-call
  confirmation). SCRIBE-3: before finalizing any `index_to_kb` proposal,
  `search_kb` for conflict (not just duplication) — a genuine contradiction
  pairs a `record_outcome(success=False, ...)` demotion with the correcting
  fact, never demotes alone, never leaves two disagreeing entries both live.
  Both features mirrored into `docs/dreaming/DESIGN.md` §6 as the fixed
  contract Thread 2 (`dream_apply.py`) must reuse byte-for-byte.
- **`scripts/distill_learnings.py`** (1.7, new — SCRIBE-2 backfill) — one-shot
  distiller over the existing `kb/session-learnings.md` corpus. Two-pass CLI:
  pass 1 writes `docs/dreaming/backfill-proposals.jsonl` +
  `backfill-review.md` (no ES writes); pass 2 (`--apply <approved-ids-file>`)
  calls `index_to_kb`/`skill_record` directly. **Run for real** against the
  live corpus: 197 candidates generated, 137 high-confidence approved and
  applied to production `lse-kb` (234 → 364 docs). 39 medium- and
  21 low-confidence candidates reviewed and explicitly not approved this
  pass — see `docs/dreaming/backfill-review.md`.
- **Contract tests** (1.8) — `tests/test_dream_corpus.py` grew to 47 tests:
  end-to-end redaction, result-cap boundary tests, provenance-format
  validators (`"debrief YYYY-MM-DD"` vs `"debrief-backfill-YYYY-MM-DD"` vs
  `"dream-YYYY-MM-DD"` — fixed, non-interchangeable strings), and
  journal-failure-never-raises-into-tool-call tests (sync + async). Full
  contract suite 165/165 green.
- **Docstring/skill audit** (1.9, SCRIBE-5) — ran the `lse-docstring-optimizer`
  discipline over `skills/lse-session-debrief/SKILL.md` and
  `docs/dreaming/DESIGN.md` §6, checking specifically for the v0.3.4
  planner-GATE-conflict failure class (two individually-reasonable MUST rules
  that combine into a forbidden action). Found and fixed one: Step 1's "if a
  duplicate exists, skip writing" used the same word "skip" as the WRITE
  SEQUENCE's "skipping any step is a protocol violation" — reworded both so a
  legitimate no-write/no-propose *result* of running a check can't be misread
  as a forbidden skipped step. Also fixed a staleness risk: the Hermes
  contradiction worked example asserted a live KB doc was "still
  unaddressed" — since SKILL.md is re-read on every future invocation, this
  goes stale the moment the doc is actually demoted; added a
  verify-current-state-via-search_kb caveat in both files.
- **Thread close** (1.10) — `run_tests(scope=all)` on LUCIFER: kb=PASS,
  retrieval=PASS, harness/tests=PASS (165/165). `run_tests(scope=harness)`
  separately still shows the 2 pre-existing, unrelated `scripts/` legacy
  harness collection errors documented in 1.8 (missing `gymnasium`; missing
  `tools/cogitator-v1.7.15.py`) — confirmed not caused by Thread 1's work.
  Gateway restarted via `tools/start-goethe.sh` — v1.11.1, 48 tools, clean
  process-count/port checks. Episode journaling confirmed live immediately
  post-restart (`/opt/local-se/episodes/2026-07-11/sess-*.jsonl` growing with
  real per-connection session ids, redaction/cap/exit_class fields intact).
  **OPERATOR NOTE:** llama-ui snapshots the tool schema per thread — start a
  FRESH llama-ui thread to pick up any schema-relevant change from this
  deploy (this thread's changes are journaling-only, no tool signatures
  changed, but the reminder is unconditional per standing practice).
  ROADMAP.md Workstream E SCRIBE-1/2/3 ticked done; SCRIBE-4 remains open
  (Thread 3). This debrief itself was written through the new unified path —
  see `kb/session-learnings.md`.

---
## 2026-07-04 (Cowork): P0-5 done — canonical system prompt `prompts/node4090-v0.6.0.md`

Lineage reconciled: v0.5.21 (prompts/) confirmed as the newer line (v0.5.19 in tools/ is a
strict subset); canonical dir = `prompts/`. **v0.6.0** built for Goethe v0.3.8 / 45 tools:

- **NEW REQUEST-SHAPE MAPPINGS section** — "get a plan"→planner, "prove it"→run_tests/
  assert_state, "resume"→task_resume, human-says-wrong→mentor_demote vs evidence-says-wrong
  →record_outcome. Prose answers to these shapes are named protocol violations.
- **ROOT CAUSE RETIRED**: the old MULTI-BLOCK TASK RULE *mandated* hand-writing
  /opt/local-se/active-task.md — the LSE's DNS-audit ledger bypass was rule-following, not
  improvisation. Replaced by the PLANNED-TASK LOOP (planner → plan_step_done → task_resume)
  with the ledger as the only sanctioned task state; NO AUTONOMOUS NOTE-WRITING updated to
  match. HANDOVER PROTOCOL rewritten ledger-first with the ≥70% context handoff.
- Tool entries added/updated: planner v2 (+reads-don't-close-the-window gate),
  plan_step_done, kb_verify, mentor_demote, time_check, run_tests, assert_state,
  record_outcome evidence demotion, search_kb trust surface + hybrid threshold note,
  ssh_run v0.3.7 guards (mux auto-recovery, PKILL rule), ssh_script bracketed-pkill example,
  TIME DISCIPLINE (server-injected banner), search_web year-strip note.
- OPERATOR ACTION: paste v0.6.0 into llama-ui's system prompt field on node4090 and start
  fresh threads. node3090's system prompt (v0.1.0) still needs its own smaller update.

---
## 2026-07-04 (Cowork): Goethe v0.3.8 — PH3-2 retrieval decision: linear beats RRF; threshold no-op found and recalibrated 0.72 → 4.2

Gold-set eval on live ES (n=50, ~200 docs): **linear** (production 0.7·knn + 0.3·BM25)
recall@1 0.76 / recall@3 0.84 / MRR 0.800 vs **rrf** 0.64 / 0.84 / 0.735 — RRF rejected on
data, ranking unchanged (null result recorded). **Bonus finding:** the search_kb
min_score=0.72 default was calibrated for cosine [0,1] but hybrid scores run ~3.5–16 — the
filter was a NO-OP. Recalibrated to **4.2** per --threshold-report (38/38 correct top-1
kept, 3/11 wrong dropped, 0 correct lost). Maintenance rule: re-sweep after major KB growth
(BM25 stats drift). KB doc 2253baf1e9df847d (ground_truth). 110/110 tests; both gateways
on v0.3.8. Live smoke: natural query → 1 precise hit with [TIME] banner + trust surface
all composing.

---
## 2026-07-04 (Cowork): Goethe v0.3.7 — SSH post-mortem hardening (mux auto-recovery + pkill self-match guard)

LSE-authored post-mortem on the node3090 exit-255 storm (11 failed attempts) → both root
causes moved from prose into code:

- **ssh_run MUX AUTO-RECOVERY**: exit 255 with a ControlMaster socket present → `ssh -O
  exit` the dead master, unlink the socket, retry ONCE, annotate. Stale-socket storms are
  now self-healing; the failure message gives the diagnostic order (ping → sshd → self-match).
- **ssh_run PKILL SELF-MATCH GUARD**: unbracketed `pkill -f <pattern>` BLOCKED — the remote
  shell's cmdline contains the pattern, so pkill kills the SSH session (exit 255, target
  possibly dead but unconfirmed — the post-mortem's "irony" case). Hint shows the bracketed
  form and the ssh_script alternative. Third occurrence of this failure class this week
  (v0.3.0 deploy script, v0.3.1 agent-shell probe, now the LSE at runtime) — now impossible
  via ssh_run.
- **ssh_script docstring**: script files never self-match (correct home for kill-by-pattern);
  `|| true` rule for pkill exit-1 (already-dead target reads as false failure).
- KB: ground-truth post-mortem doc indexed (diagnostic order for exit 255); LSE's own
  record_error entry complements it for check_error_kb hits.
- Tests 105 → **110/110 green** (guard + failure-message contracts). Both gateways on v0.3.7.

---
## 2026-07-04 — Goethe v0.2.8 — planner PATH 3 — VRAM-aware Gemma GGUF spawn

- _call_node_planner gained a three-path cascade: (1) node3090 llama-server :8080 (Qwen 27B, GPU) — primary; (2) node3090 Ollama :11434 qwen3:4b (CPU) — GPU fallback; (3) Local Gemma GGUF spawn — fires only when paths 1+2 both error.
- Model selection by task class (small/medium/large) and confirmed free VRAM via nvidia-smi; supports vision via mmproj.
- Models: E4B (~5 GB, 5200 MB gate), 26B-A4B (~16.7 GB, 17200 MB gate), 31B (~18.5 GB, 19100 MB gate).
- New valves: PLANNER_MODEL_DIR, PLANNER_PORT, PLANNER_LLAMA_BIN.
- New helpers: _planner_task_class, _planner_free_vram_mb, _planner_gemma_select, _spawn_gemma_server, _stop_gemma_server.

## 2026-07-04 — Goethe v0.2.7 — HERMES RETIRED — node planner cascade replaces Hermes

- _call_hermes and _kanban_create_card retired (stubs only).
- New: _call_node_planner — two-path cascade (llama-server → Ollama CPU).
- New valves: NODE3090_LLM_URL, NODE3090_OLLAMA_URL, NODE3090_PLANNER_FALLBACK_MODEL.
- hermes_plan rewritten to call _call_node_planner, parse JSON envelope, checkpoint task.

## 2026-07-04 — Goethe v0.2.6 — SSH OVERHAUL — ssh_run + ssh_script + ControlMaster + complexity guard

- Three root causes of exit-255 SSH failures addressed:
  (1) Double-shell escaping: new ssh_run() passes commands as argv[], not via bash -c.
  (2) nohup/disown in SSH sessions: new ssh_script() transfers script content as a file via scp, executes as bash /tmp/lse_script_<hash>.sh. Auto-injects </dev/null on nohup lines.
  (3) Per-call TCP+auth overhead: SSH ControlMaster (-o ControlMaster=auto, ControlPersist=60s) maintains a persistent mux socket.
- execute_command SSH complexity guard: commands containing nohup/disown/export/eval/subshell markers are blocked and return an actionable ssh_script() hint.

## 2026-07-03 (Cowork): Goethe v0.3.6 — PROVE-IT surface shipped (PH3-1: PROVE-1 + PROVE-3, PROVE-4 partial)

The user can now say "prove it" and get test output instead of prose.

- **PROVE-1 `run_tests(scope)`** — scopes: `kb` (ES index/count probes), `retrieval`
  (rag/eval_retrieval.py --self-test), `rules` (eval_goethe_rules.py — discovered to be an
  LLM-BEHAVIOR eval driving 9 scenarios through the live llama-server: minutes of GPU time,
  therefore EXPLICIT-only, excluded from `all`, 300s budget), `harness` (pytest tests/ +
  legacy scripts/ — hermes-era failures there are findings, reported verbatim), `all` (kb +
  retrieval + tests/). Exec-surface discipline: commands/paths/args HARDCODED per scope —
  the model supplies only the scope name (sudo-allowlist pattern). Verbatim output IS the
  evidence; missing assets → SKIP (node3090 has no rag/ or tests/). New valve REPO_DIR.
- **PROVE-3 `assert_state(check_command, expected_regex)`** — read-only argv allowlist
  (df, ss, sha256sum, dig, pgrep, stat, ls, wc, free, uptime, ip-reads, nvidia-smi,
  curl GET-only, systemctl read-verbs, ping count-capped), shlex + shell=False,
  metacharacter/pipe rejection, 20s timeout → `ASSERT PASS/FAIL` + verbatim output.
  Docstring bans assertion-loosening ("weakening a regex to green is a protocol violation").
- Both docstrings written to the 8-dimension audit standard BEFORE deploy (SCRIBE-5
  discipline honored this time). Live-verified: run_tests(kb) PASS on 5 indices;
  assert_state systemctl probe PASS.
- **PROVE-4 partial**: run_tests exists for the health-check/eval-runner wiring, but the
  installed lse-stack-health-check skill is Cowork-side read-only — wiring lands with the
  PH3-3 eval-runner rewrite.
- Tests 91 → **105/105 green** (new tests/test_prove_it.py). Both gateways on v0.3.6
  (45 tools). Observed: LUCIFER lse-kb at 200 docs, lse-skills 8 — the KB is compounding.

---
## 2026-07-03 (Cowork): Goethe v0.3.5 — SCRIBE-5 pulled forward: docstring-optimizer audit of the four v0.3.x tools + node3090 lse-skills index created

**SCRIBE-5 (partial, pulled forward from Phase 4):** 8-dimension lse-docstring-optimizer
audit on kb_verify / time_check / mentor_demote / plan_step_done. Findings → fixes
(docstring-only, shipped as v0.3.5):
- kb_verify [FAIL dim3]: GOOD/BAD pair for `observed=` (verbatim probe output vs
  paraphrased claim) + probe-must-run-THIS-session rule.
- time_check [FAIL dim5]: FIX EXECUTION PROHIBITION — never execute or auto-delegate
  the suggested clock fix unasked; human decides. (P2/P3 failure class.)
- mentor_demote [FAIL dim3]: GOOD/BAD pair pinning human-words-authorize vs
  evidence-demotes (P26 class); trust-the-return rule added (dim8 WARN).
- plan_step_done [FAIL dim8]: GOOD/BAD evidence pair; no mid-loop task_resume;
  NEW CONTEXT HANDOFF rule — past 70% context, hand the next step to a fresh session
  (encodes the DNS Phase-2 77%-context lesson as a named protocol violation).
91/91 tests; both gateways redeployed. Remaining SCRIBE-5 scope: audit older tool
docstrings opportunistically at next touch.

**node3090 lse-skills index created** (was NotFoundError since the node got its own ES
2026-06-28 — 06-skills-index-setup.py had only ever run on LUCIFER). Created empty via
curl PUT with the canonical mapping; skill_search now returns clean misses and
skill_record can write. NOTE: node3090's skill memory is independent of LUCIFER's
(5 skills) — copy/reindex is a follow-up decision. node3090 local lse-kb observed at
9 docs (was 7) — its LSE is indexing independently.

---
## 2026-07-03 (Cowork): Goethe v0.3.4 — planner GATE conflict fix (docstring-only) + ledger reconciliation of the DNS audit run

**Field report 1 (stale tool surface):** the DNS Phase-2 LSE thread predated the v0.3.3
gateway restart → no plan_step_done in its tool list → ledger block 2ae2f45e sat untouched
while 5 steps completed. Reconciled from Cowork: steps 1–5 struck with the run's evidence;
`planner(mode="revise")` (first live **Gemma-31B**-served plan, node3090:8080) appended
steps 6–13 correctly folding all findings incl. human-gated WRITE ACCESS PROTOCOL steps.
Lesson: llama-ui snapshots the tool schema per thread — after a gateway deploy, START A
FRESH THREAD.

**Field report 2 (gate conflict → v0.3.4):** told "get a plan to audit DNS infra", the LSE
never called planner(): the old GATE ("must be your first or second tool call") conflicted
with KB-FIRST/SKILLS-FIRST — after 2× search_kb the model treated planning as forbidden,
hand-wrote a prose plan + ad-hoc /opt/local-se/active-task.md, bypassing the ledger.
Fix (docstring-only): information gathering (KB, read-only probes) does NOT close the
planning window — findings go into `context=`; window closes at first STATE CHANGE. New
MANDATORY TRIGGER: a user request for "a plan" REQUIRES planner(); hand-written plan files
are a named protocol violation. GOOD/BAD examples updated (reads→planner(context=…)).

**Also fixed en route (v0.3.3 hotfix, same session):** `task_resume` broken for ALL blocks
since the steps_json migration (`SELECT *` + 11-value unpack vs 12 columns) — pinned
explicit column list + regression test. Tests **91/91 green**. Both gateways redeployed.

**Follow-up for P0-5 (canonical system prompt):** add the request-shape mappings
("get a plan" → planner; "prove it" → run_tests/assert_state; mentor_demote = human-only)
so tool routing does not depend on docstrings alone.

---
## 2026-07-03 (Cowork): Goethe v0.3.3 — "PLANNER UNAVAILABLE" root-cause fix (LSE-debugged, Cowork-confirmed)

Three compounding causes, all in `_call_node_planner`/`planner()`:

1. **max_tokens=2048 truncated v2 envelopes** — per-step packaged prompts need far more
   than the v1 allowance → raised to 8192.
2. **Qwen3.6 thinking ate the completion budget** — node3090 runs 35B-A3B with
   `--reasoning-budget 16000 --reasoning-preserve`; `/no_think` is prose and does not hold.
   Fix: per-request `"thinking_budget_tokens": 0` — the server-enforced reasoning-budget
   kill-switch (request value 0 OVERRIDES any CLI budget; the -1 sentinel collision from
   KB doc 29c77cd7 does not apply to 0). Ignored harmlessly by think-tag-less models (Gemma).
3. **No resilience** — new two-attempt envelope loop: a parse failure feeds a corrective
   "PREVIOUS REPLY REJECTED: <reason>" note back to the planner and retries once before
   surfacing PLANNER UNAVAILABLE.

**Bonus fix from the live smoke**: the model copies the schema-example task_id
("a1b2c3d4") verbatim → every plan would collide onto one ledger row. task_id removed
from the contract schema; the server now ALWAYS generates the ledger id (task+time hash).

Live verification: real planner call against node3090 (35B-A3B, reasoning budget active)
returned a clean 5-step atomized envelope, each step 1 tool call with a concrete verify.
Tests 88 → **90/90 green** (retry loop, payload contract: max_tokens/thinking_budget_tokens).

---
## 2026-07-03 (Cowork): Goethe v0.3.2 — PLANNER v2: atomized plans + living tasks.db ledger + cross-family (Gemma) planner path

Built for the DNS-migration workload class: Qwen3.6 performs best tightly scoped, and 131k
context must be managed across long multi-session work.

- **Contract v2** (`_PLANNER_CONTRACT`): every step is ONE atomized unit — ≤5 tool calls,
  one verifiable outcome, mandatory concrete `verify`, explicit `depends_on`/`inputs`/`output`
  edges, topological order, and its OWN self-contained `packaged_prompt` (executable by a
  fresh agent with zero memory + a compact ledger summary). BACKUP RULE retained.
- **Living ledger**: `steps_json` column on task_blocks (idempotent PRAGMA migration in
  `_tasks_db`); `planner()` writes the atomized plan there. NEW **`plan_step_done(task_id,
  step_n, evidence, failed=False)`** strikes a step (evidence gate ≥20 chars, stored for
  forensics), returns the NEXT step's fresh-context prompt (ledger header: last 8 strikes +
  remaining), closes the block on the last strike; `failed=True` routes to revise.
- **`planner(mode="revise", task_id=…)`**: feeds completed/failed steps (with evidence)
  back as LEDGER context; planner re-plans ONLY the remainder; done history preserved in
  the merged plan.
- **Decision — no websocket**: the SQLite ledger IS the planner↔agent channel (durable
  across context resets/crashes; goethe has no event loop). Real-time multi-agent planning
  remains Faust's job when its state machine lands.
- **Cross-family planner**: NEW valves `PLANNER_FORCE_URL`/`PLANNER_FORCE_MODEL` — Step-0
  health-probed endpoint override (used when up, silent cascade when down, so it can stay
  set permanently). NEW `tools/planner-gemma-swap-node3090.sh` + `…restore…sh`:
  swap-on-demand **Gemma-4-31B planner on node3090:8085** (GGUF verified present, 17.4GB);
  captures the pre-swap llama-server cmdline to /tmp for exact restore; Gemma sampling
  (temp 1.0, top-k 64); bracketed `llama[-]server` pkill patterns per the self-kill lesson.
- **Bug found by tests**: task_checkpoint's `INSERT OR REPLACE VALUES(11)` broke against the
  12-column table AND would have silently wiped steps_json on every checkpoint — fixed with
  explicit column list + steps_json carry-through.
- **Tests**: NEW `tests/test_planner_ledger.py` (13 tests, canned envelopes, no ES/LLM
  needed) — full suite now **88/88 green**.

---
## 2026-07-02 (Cowork, same session): PH2 shipped — Goethe v0.3.1 CHRONOS: enforced sense of time (CHRONOS-1..4)

**Goethe v0.3.1** (`tools/goethe.py`, 6387 lines). Time discipline moved from docstring
pleading to server-side enforcement (Ousterhout: define the failure mode out of existence):

- **CHRONOS-1** — NEW `time_check()`: stdlib SNTP (no ntplib dep) against pool.ntp.org +
  time.cloudflare.com (2s timeout each, graceful degrade to system clock + WARN), offsets
  in ms. Threat-modeled per Shostack: NTP is unauthenticated, so a clock-fix command
  (timedatectl/chronyc, HUMAN-run, never automatic) is only suggested when BOTH NTP
  sources agree (≤1s) AND the TLS Date header of a known HTTPS endpoint corroborates
  (≤5s; two-endpoint fallback cloudflare→google). Offset >2s → discrepancy report +
  lse-errors record. Live smoke: consensus verified at +175/+326 ms, TLS −0.4s.
- **CHRONOS-2** — NEW valve `MODEL_PRETRAIN_CUTOFF` (YYYY-MM, per-model; set via
  `GOETHE_MODEL_PRETRAIN_CUTOFF` in ~/.lse/secrets — goethe_mcp maps GOETHE_<FIELD> envs).
  `[TIME] now=… | model cutoff=… | gap≈N months` banner returned by time_check AND
  server-injected into the FIRST search_kb/search_web return of each session
  (`_consume_time_banner` session flag). Unset valve → banner nags UNSET.
- **CHRONOS-3** — Volatility TTLs enforced: `index_to_kb(volatility=static|slow|fast)`
  (default slow; invalid → slow). TTLs: static=∞, slow=90d, fast=7d. `search_kb` tags
  `[EXPIRED — <class> TTL exceeded; pointer only, re-verify live]` and demotes expired
  hits ×0.5 in the trust rerank (same as stale). `record_outcome(success=True)` now bumps
  `updated_at` — re-verification resets the TTL clock. NOTE: pre-existing docs default to
  slow — anything >90d old now surfaces as EXPIRED until re-verified (intended).
- **CHRONOS-4** — YEAR-INJECTION + 30d/7d staleness rules RETIRED from the search_web
  docstring (single source of truth). Years now stripped server-side (`_strip_years`:
  standalone 19xx/20xx tokens; CVE-2025-1234 / ubuntu-24.04 / b2025 compounds survive).

**Contract tests**: 53 → **75, all green** (44s) — banner once-per-session, gap math,
year-strip table, volatility store/validate/expire/static/reset, and all four time_check
trust paths (consensus / discrepancy+TLS→fix / discrepancy−TLS→no-fix / NTP-disagree /
no-NTP degrade) with monkeypatched sources.

---
## 2026-07-02 (Cowork, same session as PH1-1): PH1-2 shipped — Goethe v0.3.0 KB trust lifecycle (KB-DECAY-1..5)

**Goethe v0.3.0** (`tools/goethe.py`, 6128 lines): lse-kb quality is **no longer monotonic
upward** — verified failure evidence now demotes, closing the "app updated → KB ground truth
silently wrong forever" regression gap.

- **KB-DECAY-1** — `record_outcome` gains `evidence=`: success=False + evidence (≥20 chars)
  → `quality = max(0.2, q − 0.15)` + `consecutive_failures` streak; at the 0.2 floor →
  `stale: true` QUARANTINE (never deleted — forensics). Failure without evidence counts but
  never demotes (same gate as skill_outcome). success=True resets the streak only — no free
  re-elevation. Recovery is tier-gated: index_to_kb dedup or mentor_correct raising quality
  above 0.2 clears stale + streak.
- **KB-DECAY-2** — `search_kb` surfaces trust: `runs=N (ok/fail)` or `untested` per hit,
  `[STALE — quarantined, verify live before use]` banner, client-side trust rerank
  (score × (1 − 0.3·fail/runs), stale ×0.5 → quarantined docs always rank below fresh).
  Deliberately not ES function_score yet — measure with the gold set first (PH3-2).
- **KB-DECAY-3** — NEW `kb_verify(doc_id[, observed])`: two-phase verified_against
  regression probe. Phase 1 returns the stored snapshot + probe instructions; phase 2
  compares live probe output (token containment, ≥20-char gate) — MATCH → auto
  record_outcome(success=True); MISMATCH → auto record_outcome(success=False,
  evidence="verified_against regression: …") which fires the KB-DECAY-1 demotion.
- **KB-DECAY-4** — NEW `mentor_demote(doc_id, new_quality, reason)`: human-authorized-only
  kill-switch for wrong high-quality docs (reason ≥10 chars stored as `demote_reason`;
  ≤0.2 → stale). `mentor_correct` stays raise-only.
- **KB-DECAY-5** — `rag/08-kb-trust-migration.py` (idempotent): added `stale`,
  `consecutive_failures`, `volatility` (CHRONOS-3-ready) to the live lse-kb mapping. ✅ RUN.
- **skill_outcome floor reconciled** — demotion now `max(0.2, q − 0.15)` matching its
  docstring (was 0.0; PROVE-2 finding); archive fires only on failure at the floor.

**Contract tests extended**: `tests/test_kb_contracts.py` 34 → **53 tests, all green**
(29.5s, owui-venv python vs live ES; anchor-blended fake embeddings added so rerank tests
get controllable mid-range cosine similarity). Production verified untouched post-run.

---
## 2026-07-02 (Cowork): PH1-1 shipped — PROVE-2 contract tests (`tests/test_kb_contracts.py`)

**34 contract tests, all green** (19.5s, run with the production interpreter
`/home/sy5/owui/bin/python3` — pytest 9.1.1, elasticsearch-py 8.19.3 — against live ES 8.13.0).
Pins the current Goethe v0.2.9 KB-mutation contracts as the Fowler safety net required before
KB-DECAY (PH1-2) and the Phase-5 refactors (TrustPolicy extraction, goethe_kb.py split):

- **index_to_kb**: tier ceilings (inferred 0.4 / secondary 0.6 / primary 0.8 / ground_truth 1.0;
  unknown tier → inferred), ground_truth evidence gate (<40 chars → 0.7 downgrade), waterfall
  provenance cap (version claim w/o provenance → ≤0.3 + [UNVERIFIED] prefix + tier=inferred),
  dedup at cosine ≥0.92 (updates, never duplicates; quality = max(existing, new); refinement/version bump).
- **record_outcome**: counts increment; **quality_score never touched — even on failure**
  (the monotonic-upward behavior KB-DECAY-1 will change; test carries an update note);
  id/title resolution; graceful unknown-ref handling.
- **mentor_correct**: REJECTS lowering (doc fully untouched on rejection); raise path replaces
  content, re-embeds, bumps refinement_count, stamps mentor_corrected_at.
- **skill_record**: quality clamp min(q, 0.7, tier ceiling) with floor 0.2; <2-step procedure
  rejected as fact; empty verification rejected; dedup updates; missing provenance → FLAGGED/UNATTRIBUTED.
- **skill_outcome**: evidence gates (≥20 chars, ≥50 for ground_truth); +0.10 capped at tier
  ceiling; −0.15 demotion; auto-archive below 0.2; pinned skills never archived.
  **Discrepancy documented:** code floors demotion at 0.0 (`max(0.0, q−0.15)`) while the
  docstring says "floor 0.2" — the test pins the CODE (0.25 → 0.10 + ARCHIVED).

**Safety design**: every ES call from code under test passes through an index-rewrite proxy
(`lse-kb`→`lse-kb-test`, `lse-skills`→`lse-skills-test`; any other index → RuntimeError), so
production indices are physically unreachable. Embeddings are deterministic fakes (no Ollama
dependency; identical text → cosine 1.0, distinct → ~0.0) so the 0.92 dedup threshold is exact.
Throwaway indices created/deleted per test; post-run verified: no `-test` indices remain,
lse-kb=187 / lse-skills=5 docs intact.

Run: `cd <repo> && /home/sy5/owui/bin/python3 -m pytest tests/test_kb_contracts.py -q`
(pytest installed into the owui venv this session; system python3 lacks pydantic/elasticsearch.)

---
## 2026-06-30 (Cowork): Capital-case file sync — README, CURRENT-STATE, VERSION, CHANGELOG, VALVES updated to Goethe v0.2.5 / llama-ui / goethe_mcp v1.9.3

All top-level documentation files cross-referenced against on-disk tool versions and updated to reflect post-P31 sessions (Jun 21–29). Key changes recorded:
- **README.md**: frontend OWUI→llama-ui, goethe_mcp entry, tool/prompt/gateway version table, repo layout.
- **CURRENT-STATE.md**: Deployed Versions table rewritten for Goethe v0.2.5 + goethe_mcp v1.9.3 + system-prompt v0.5.18. Architecture Change Log section added. node3090 local ES/Ollama/Firecrawl stack noted. OWUI marked retired.
- **VERSION.md**: Current Versions table updated. Goethe Checksums + goethe_mcp lineage table added. Line Count Tally (Goethe) added before the Cogitator tally.
- **CHANGELOG.md**: Post-P31 session entries added (Jun 21, Jun 25, Jun 26, Jun 28–29).
- **VALVES.md**: Section 1 tool reference updated cogitator→goethe.py v0.2.5; OWUI security note updated to MCP context.

---
## 2026-06-29 — Goethe v0.2.5 + node3090 MCP deploy script

**Goethe v0.2.5** (`tools/goethe.py`, 5343 lines, raw `aa2aa1e1…`):
- `fetch_url` **reddit/camoufox browser fallback**: reddit.com 403/429/empty → retries via Firecrawl (`_reddit_browser_fallback`). On node3090: `localhost:3002`. From LUCIFER: ping node3090 first, then `node3090:3002`. Result prefixed `[browser-rendered]`, cached, SOURCE-VERIFY MANDATE tagged. Fails gracefully if node3090 offline.
- `wake_node` overhauled (v0.2.3 cumulative): ping-first (skip WoL if already up), `search_kb` for current wake procedure before sending magic packet, KB notes surfaced in all return paths.
- `shutdown_node` two-step gate (v0.2.4 cumulative): `confirmed=False` returns prompt for user; `confirmed=True` executes. Model must surface the prompt and wait for explicit yes.

**`tools/start-goethe-node3090.sh`**: rsync `goethe.py` + `goethe_mcp.py` to node3090, kill old instance, start via nohup with local ES (`localhost:9200`) + Ollama (`127.0.0.1:11434`) env overrides. Token `266ce5843de4fd3ad04dffefae8f17db`. Logs to `/tmp/goethe-node3090.log`.

**`tools/system-prompt-node3090-v0.1.0.md`**: node3090-specific system prompt (v0.1.0). Separate identity/environment section for the node3090 agent instance.

---
## 2026-06-28 — goethe_mcp v1.9.3 + system prompt v0.5.17→v0.5.18

**goethe_mcp v1.9.3** (`tools/goethe_mcp.py`, 487 lines):
- v1.9.3: `_TokenGuard` accepts both `Bearer <token>` and raw `<token>` — normalises auth header format so llama-ui client format differences don't matter.
- v1.9.2: removed all OpenWebUI/OWUI references from comments; owui venv path retained (historical artifact, still hosts `mcp` lib).
- v1.9.1: passes goethe.py's own version to FastMCP banner.
- v1.9.0: `_free_port()` self-contained port management — kills any process holding the port before binding.

**System Prompt v0.5.18** (`tools/system-prompt-v0.5.18.md`):
- WEB SEARCH BUDGET FALLBACK: new named section — when budget exhausted, ping node3090, check/start firecrawl and camoufox, route remaining searches through them. firecrawl = general content; camoufox = reddit.
- ENVIRONMENT updated to goethe_mcp v1.9.3; start command simplified to `bash start-goethe.sh`.

**System Prompt v0.5.17** (`tools/system-prompt-v0.5.17.md`):
- KB-FIRST RULE: new named section — search_kb() BEFORE any operational answer, BEFORE any tool call, BEFORE reasoning from training knowledge.
- ENVIRONMENT: goethe_mcp bumped to v1.9.3.
- search_kb entry in TOOLS: scope expanded to all operational questions.

---
## 2026-06-26 — Goethe v0.2.2: three ground-truth-before-action rules

**Goethe v0.2.2** (`tools/goethe-v0.2.2.py`, 5126 lines, raw `bc403c44…`):
THREE GROUND-TRUTH-BEFORE-ACTION RULES added to `execute_command` docstring (design session; Camoufox + n45 incidents as empirical basis — rules abstracted to pattern class):
1. **RESOURCE-AVAILABILITY RULE**: before any external connection (SSH, API, docker exec, curl to service), verify resource state first via ping/health-check. For managed nodes: check `_NODE_REGISTRY` → `wake_node` if found; else `search_kb("<hostname> access")`; else stop. Prevents 30s SSH timeouts misdiagnosed as credential failures.
2. **VENDOR-BEHAVIOR GROUND-TRUTH RULE**: before modifying any file from an external project based on an assumption about HOW that software behaves internally, run the waterfall: search_kb → vendor changelog/README → GitHub issues → search_web. `write_file` snapshot gate makes patches reversible; it does NOT prevent acting on a false premise.
3. **RELEASE ASSET RULE**: before writing any download URL, VERSION variable, image tag, or package pin, fetch the source of truth — `get_github_release("<owner>/<repo>")` for GitHub, registry page/API for Docker/PyPI/npm. Version patterns cannot be inferred by incrementing a prior release.

---
## 2026-06-25 — Goethe v0.2.1: KB doc-id resolution + stable goethe.py filename

**Goethe v0.2.1** (`tools/goethe-v0.2.1.py` → stable `tools/goethe.py`, 5022 lines, raw `b3cf97f2…`):
- **KB DOC-ID RESOLUTION** (SY5 debug — mentor_correct 404): `mentor_correct`/`record_outcome` passed the KB doc TITLE as `doc_id` → `NotFoundError(404)`. Root cause: `search_kb` never printed the doc_id. Fixes: (a) `search_kb` now prints `doc_id=<_id>` on every hit; (b) new `_resolve_kb_id()` accepts `_id` OR title (exact `match_phrase` lookup); (c) `mentor_correct` + `record_outcome` use it — return actionable error ("run search_kb for the doc_id") instead of raw 404; ambiguous titles list candidate ids.
- **Stable filename**: switched to `goethe.py` — ends per-bump renames that broke path references. Version now lives in frontmatter `title:` / `version:` only. `exec_test.py` resolves via glob.
- v0.2.0 (cumulative): `download-monitor.py` UnboundLocalError fix + false-COMPLETE fix + interpreter-selection fix + wrong PromQL fix; `monitor_download()` interpreter selection fix; `monitor_download` audit pass.

---
## 2026-06-21 — OWUI → llama-ui migration; goethe_mcp initial deployment; system prompt v0.5.16

**Architecture migration — OpenWebUI retired:**
- Frontend: **OpenWebUI (port 3000) → llama-ui** (built into llama-server, served at `:8080`). No separate process. Model runs directly in llama-server's built-in web interface.
- **goethe_mcp v1.3.0** deployed: MCP gateway at `:9700`, HTTP transport, bearer-token-gated (`GOETHE_MCP_TOKEN=6e003f5c…`). Started via `bash tools/start-goethe.sh`. Loads `goethe.py` + `vaultwarden_tools_v1.3.0.py` via `--also` flag.
- `compact_context` removed from tool surface (OWUI-only, not exposed via goethe_mcp).

**System Prompt v0.5.16** (`tools/system-prompt-v0.5.16.md`):
- ENVIRONMENT: `Frontend` OpenWebUI/3000 → llama-ui/8080. MCP GW entry added (goethe_mcp v1.3.0, port 9700).
- `sudo_delegation_block`: SURFACE RULE added — "described in thinking ≠ called".
- `compact_context`: removed from TOOLS section.
- HANDOVER PROTOCOL: updated — no compact_context step.
- KNOWLEDGE BASE: OpenWebUI section removed.

---
## 2026-06-19 — P31 (Cowork): Goethe v0.1.0 — Cogitator fork, Faust consolidation

**Goethe v0.1.0** (`tools/goethe-v0.1.py`, fork of Cogitator v1.7.24; ast OK, raw `a7f379dd…`, 4721 lines, black-norm pending):
Retires the in-tool Hermes↔LSE OWUI channel — superseded by the **Faust** group-chat room
(`Faust/`, 1.7.0-b). The async outbox/inbox coordination no longer belongs in the OWUI tool.

- **Removed**: `hermes_cooperate`, `_cooperate_exec`, `check_hermes_inbox`, `_format_hermes_messages`,
  `_flush_voicemail`, and the Path A/B content-marker + by-reference inbox/outbox machinery
  (`_extract_content_marker`, `_strip_hermes_marker`). `_call_hermes` simplified to return the
  plain reply (no inbox append / marker strip).
- **Kept**: `hermes_plan` (inline pre-flight planner — distinct use, genuinely useful) + its
  `_call_hermes` backend + `_kanban_create_card`; and all general LSE tooling/hardening
  (execute_command, sudo_delegation_block, file ops, search_kb/index_to_kb, record_error,
  pfSense tools, WATERFALL provenance, source-claim verification, SSH KB-first/fingerprint rules).
- Net: 5051 → 4721 lines. New lineage `goethe-v*`; Cogitator v1.7.x history retained in the module changelog.
- **Pre-deploy**: black-norm sha, then paste into OWUI as the LSE tool. The LSE's Faust presence is the
  separate `agent-client/` sidecar (its `on_cue` calls this model via OWUI `/api/chat/completions`).

---
## 2026-06-19 — P31 (Cowork): Cogitator v1.7.23–v1.7.24 — Hermes by-reference + call_hermes demodeled to internal-only

**Cogitator v1.7.23 → v1.7.24** (cumulative on the deployed v1.7.21; both STAGED, black-norm pending — `black` unavailable in build env, compute before deploy):

- **v1.7.23** (ast OK, raw `3bf589bf…`, black-norm pending, 5031 lines, +16 vs v1.7.22): **HERMES→LSE BY-REFERENCE** (large-payload fix). When an inbound envelope carries `body_ref` (a path written by the Hermes producer on node3090 because the full payload would overflow the reply token cap and truncate the JSON marker), `_format_hermes_messages` now surfaces a fetch instruction (`execute_command` SSH `cat`) alongside the preview, so the model can pull the full text on demand. Unknown-key safe — older markers without `body_ref` format exactly as before. No new tool; the existing `execute_command` SSH path does the fetch. Implements the "carry large artifacts by reference" finding from P29.
- **v1.7.24** (ast OK, raw `a76c385c…`, black-norm pending, 5051 lines, +20 vs v1.7.23): **`call_hermes` DEMODELED → internal-only `_call_hermes`** (URGENT). The model must no longer invoke the Hermes chat-completion call directly — direct calls frequently surface OWUI networking errors, and the direct entry point is being superseded by `hermes_plan` and `hermes_cooperate`. Renamed `call_hermes` → `_call_hermes` so OWUI no longer exposes it in the tool spec (leading underscore = internal helper). **All logic preserved** — it remains the shared backend both `hermes_plan` (planner) and `hermes_cooperate` (conference call) invoke internally; both tools are behaviourally unchanged. The `check_hermes_inbox` 'ask' reply path, which previously instructed the model to `call_hermes` directly, now routes through `hermes_cooperate(objective=<result>, max_rounds=1, context='correlation_id=<cid>')`. Module tool list + docstring references to `call_hermes` reworded so nothing points the model at the hidden function; historical changelog entries left intact (past-version records).

**Registry:** VERSION.md + CURRENT-STATE.md updated — Current Versions row, Tool Checksums (raw sha + line count; black-norm `_pending_`), Line Count Tally, and Tool Changelog Summary. v1.7.21 remains the DEPLOYED build; v1.7.22–v1.7.24 staged.

**Pre-deploy TODO:** run `black` on `cogitator-v1.7.23.py` and `cogitator-v1.7.24.py`, record black-norm sha256 in VERSION.md (replaces the two `_pending_` cells), then paste v1.7.24 into OWUI Admin → Tools → LSE Cogitator → Save and confirm `call_hermes` no longer appears in the model's tool list.

---
## 2026-06-14 — P29 (Cowork): sudo-block surfacing (v1.7.20→22), Hermes channel producer skill, bench Condition A, doc stamps

**Cogitator v1.7.20 → v1.7.22** (cumulative on the deployed v1.7.19; black-norm = deploy identity):

- **v1.7.20** (ast OK, raw `b5dcfb95…`, black-norm `75ad4a6a…`, 4993 lines, +23): `sudo_delegation_block` made async + force-surface via `__event_emitter__` message event. Insufficient alone — content emitted mid-`<think>` stays collapsed.
- **v1.7.21** (ast OK, raw `67ffb2dd…`, black-norm `79b74fde…`, 5009 lines, +16): **DEPLOYED & confirmed (P29).** sudo block reformatted as a copyable ```bash fence; the function now RETURNS a directive forcing the model's visible post-`<think>` reply to reproduce the fence verbatim — the only channel that renders reliably. Fixes the long-standing "delegation hidden in thinking / needs explicit user request" issue.
- **v1.7.22** (ast OK, raw `ba815cd2…`, black-norm `142f155a…`, 5015 lines, +6): inbox poll `max_tokens` 8→1024 (Path B companion — the marker rides reply content, can't fit in 8). BUILT; deploy candidate pending live channel test.

**Hermes channel — producer side built** (`hermes-skill/`): `SKILL.md` (lse-channel, agentskills.io format) + `lse_channel.py` (atomic outbox: enqueue/flush/reply) + `INSTALL.md`. Round-trip verified offline against the LSE parser (`_extract_content_marker`→`_format_hermes_messages`). Staged to node3090 `/tmp`; Hermes self-install via `skill_manage` pending. **Channel finding:** small messages round-trip, but large payloads (e.g. a full ssh log) overflow the reply token cap and truncate the JSON marker → carry large artifacts **by reference** (Hermes writes a file, envelope body holds the path, LSE fetches via SSH), not inline.

**Bench:** re-froze `lse-bench-v1` (1 valid: node-t3-006; 003/004 dropped — no actuation block; 24 self-report excluded). **Condition A** (eval, learning off): 1/1 SOLVED, 21.0 pts — `verify_ssh` caught a false self-report on A2 (model claimed success; ground truth failed attempt 1, solved attempt 2).

**Docs/safety:** ctx-size **81920 confirmed universal canon** (4090 + node3090); `docs/kv-cache-vq4-128k-experiment.md` (KQ8/VQ4 @ 128k test plan); `docs/node-t3-003-004-rebuild-spec.md`; `backups/` (v1.7.19 rollback copy + `ROLLBACK-cogitator.md`).

---
## 2026-06-13 — P28 (Cowork): actuation layer (1.7.0-a) + Hermes↔LSE channel (v1.7.15–v1.7.19) + WATERFALL rule + self-repairing SearXNG + Firecrawl

**Cogitator lineage v1.7.15 → v1.7.19** (each cumulative; black-norm sha = deploy identity, raw sha for reference):

- **v1.7.15** (ast OK, raw `88f2a422…`, black-norm `5058ab2a…`, **4609 lines**, +94 vs v1.7.14): `check_hermes_inbox()` + `_format_hermes_messages` + `call_hermes` inbound passthrough — the Hermes→LSE half of the bidirectional channel (1.7.0-b). Inbox correctly returns `INBOX EMPTY` until the Hermes side queues a real message.
- **v1.7.16** (ast OK, raw `d6da1af8…`, black-norm `4e50c802…`, **4750 lines**, +141): `hermes_cooperate()` bounded conference call + `_flush_voicemail`.
- **v1.7.17** (ast OK, raw `53f17c29…`, black-norm `0839d47f…`, **4836 lines**, +86): `allow_sudo` allowlist + `_cooperate_exec` gated executor.
- **v1.7.18** (ast OK, raw `759c7bdc…`, black-norm `620abcc3…`, **4929 lines**, +93): **WATERFALL PROVENANCE RULE** — `_wf_version_claim`/`_wf_has_provenance`; unprovenanced external version/behavior claims persist tagged `[UNVERIFIED]` at quality ≤0.3. Closes ROADMAP 1.7.6.
- **v1.7.19** (ast OK, raw `7c1de10e…`, black-norm `e76d28b6…`, **4970 lines**, +41): Path B content-marker parser — `_extract_content_marker`/`_strip_hermes_marker`. **DEPLOYED** ✅ (black-norm `e76d28b6…` verified against live OWUI). LSE side now supports both Path A (gateway field) and Path B (content marker).

**v1.7.0-a episode actuation layer — COMPLETE & validated live:**
- `scripts/actuation.py` (NEW) — extract ` ```bash ` block → gate (ported Cogitator gates) → SSH-execute on the challenge host. 16/16 gate self-tests pass.
- `scripts/lse_challenge_env.py` (+63) — `_actuate()` runs before `_evaluate_assertions` so `verify_ssh` reads the world the model actually changed. Backward-compatible (read-only challenges unaffected).
- `scripts/run_episode.py` — `--no-learn`/`--eval` flags + `--bench <name>` runner (`run_bench`).
- `scripts/escalation_wrapper.py` (+12) — `learn` flag threaded; `_index_to_kb`/`_record_error` suppressed in eval (closes the KB-write-back leak).
- `scripts/seed_node_t3_006.py` (NEW) — first actuation challenge; **SOLVED 3/3 live** via pure `verify_ssh` ground truth.
- `scripts/freeze_bench.py` (NEW) + `bench/lse-bench-v1.json` — tamper-evident frozen manifest; selects only bench-valid challenges (all assertions `verify_ssh`-backed AND write-mode → has `actuation`). **Re-freeze pending** (drops invalid node-t3-003/004).

**Infra:**
- **SearXNG self-repairing** — `docker/searxng_data/settings.yml` canonical (27 engines pinned, reddit excluded, sha `1194c84a…`) + `scripts/searxng-config-guard.sh` + systemd `.service`/`.timer` (`scripts/systemd/`). Drift root cause solved (file overwrite 6/07 + `:latest` recreate 6/08). KB purged of 13 `competition_kb` entries.
- **Firecrawl** stood up on node3090 (`firecrawl-api-1` :3002; `sear_primary` SearXNG :5580). **Hermes web_search rewired to it** — verified live. Closes ROADMAP "Hermes web_search/firecrawl broken".
- Design docs: `docs/lse-1.7.0-a-actuation-design.md`, `docs/lse-1.7.0-b-bidirectional-design.md`, `docs/hermes-side-1.7.0-b-spec.md` (Hermes self-install pending).

---
## 2026-06-13 — P27 (Cowork): Cogitator v1.7.14 — HERMES_API_URL direct connect (:8643→:8642)

- **v1.7.14 built** (P27, ast OK, raw sha256 `ff377203…`, black-norm `435c319a…`, **4515 lines**, +7 vs v1.7.13):
  - **Root cause**: `HERMES_API_URL` valve default was `http://192.168.5.41:8643` — the socat port — not the gateway's real bind address. `ss -tlnp` on node3090 confirmed gateway binds `0.0.0.0:8642` directly. socat PID 8485 (`0.0.0.0:8643 → 127.0.0.1:8642`) was a workaround from when the gateway was loopback-only; now redundant. HTTP 200 confirmed from LUCIFER direct to `:8642`.
  - **Changes**: HERMES_API_URL valve default `:8643` → `:8642`; valve description updated; `call_hermes` docstring port updated; module changelog entries v1.6.2 and v1.6.4 corrected to remove socat references; v1.7.14 changelog entry added.
  - **No code logic change** — valve default and docstrings only. No behavioral difference if socat was already running; prevents breakage once socat is killed.
  - **VALVES.md updated**: HERMES_API_URL and HERMES_API_KEY added to active valve registry for section 1.
  - **socat PID 8485**: to kill → `ssh lse-admin@node3090.home.arpa "sudo kill 8485"` then verify `ss -tlnp | grep -E '8642|8643'`
  - READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.
  - Verify: `python3 -m black --quiet - < tools/cogitator-v1.7.14.py | sha256sum` → `435c319aae260a8616b4eeb14751fa747b2ad919d785db33685e461e5009d2c8`

---
## 2026-06-13 — P27 (Cowork): Cogitator v1.7.13 — SSH KB-FIRST rule (bare-ssh + wrong-topic-filter incidents)

- **v1.7.13 built** (P27, ast OK, raw sha256 `cfc194c5…`, black-norm `866b0b4d…`, **4508 lines**, +25 vs v1.7.12):
  - **Root cause**: rutx50 live test revealed two behavioral bugs: (1) model attempted `ssh root@rutx50 'uptime'` with no key → 30s timeout; only searched KB after user explicitly prompted. (2) KB search used `topic_filter=pfsense` for a rutx50 SSH access query → returned pfSense REST API docs, not rutx50 access params. Model eventually course-corrected but wasted 3 tool calls and one timeout.
  - **SSH KB-FIRST RULE** added to `execute_command` docstring: mandatory `search_kb(query='{hostname} SSH access')` with NO `topic_filter` before any `ssh` command. The KB stores the correct key path, username, and IP for every managed device. Attempting SSH without the key on a key-only device is a protocol violation.
  - **topic_filter rule**: explicitly bans applying one device's `topic_filter` to an SSH query for a different device. `topic_filter='pfsense'` on a rutx50 query returns only pfSense-tagged KB entries (wrong).
  - **Enforcement**: docstring only (sudo-blocker lineage); no code change needed — the SSH fingerprint fires on first successful connection regardless.
  - **Live test result** (v1.7.12, post cache-fix): `ssh -i ~/.ssh/id_ed25519_rutx50 root@192.168.5.3 'uptime'` → `[DEVICE FINGERPRINT: host=192.168.5.3 | platform=OpenWrt 21.02.0 | source=os-release/uname — ground truth.]` ✅
- READY FOR DEPLOY — paste into OWUI Admin → Tools → LSE Cogitator → Save.

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
- Tool v1.4.0: execute_command, read_file, write_f
