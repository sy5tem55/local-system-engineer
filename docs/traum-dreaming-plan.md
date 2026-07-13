# TRAUM — Out-of-Band Dreaming for the LSE

> Workstream codename: **TRAUM** (Ger. "dream" — keeps the Goethe/Faust register).
> Created 2026-07-11 (Cowork). Source concept: Lamis Mukta (Anthropic MTS),
> "Learning while you sleep: Beyond memory to dreaming", AI Native DevCon, June 2026.
> Status: **IMPLEMENTED** — all four threads closed 2026-07-13; 408-test close
> suite green. End-to-end operator acceptance rerun 2026-07-13; see §5 and
> `docs/dreaming/KB-ENTRY-PROMPT.md`.

---

## 1. Why — the gap Mukta names, mapped to our stack

Mukta's memory evolution path vs. where Goethe v0.3.9 already is:

| Mukta level | Her reference | LSE equivalent | Status |
|---|---|---|---|
| 1. Static prompt file | GOETHE.md (sic — CLAUDE.md pattern) | `prompts/node4090-v0.6.0.md`, pasted into llama-ui | ✅ mature |
| 2. In-band memory tool | Memory tool | `search_kb`/`index_to_kb`/`record_error`/`check_error_kb`/`record_outcome` on `lse-kb`/`lse-errors` (ES) | ✅ mature, trust lifecycle (KB-DECAY) + TTLs (CHRONOS) |
| 3. Skills | Agent Skills | `skill_record`/`skill_search`/`skill_outcome` on `lse-skills`; `lse-session-debrief`, `lse-docstring-optimizer` | ✅ live, evidence-gated |
| 4. Agent-managed memory | Memory Stores (managed-agents beta) | quality/stale/volatility fields, quarantine, mentor gates | 🟡 partial — versioned, but curated only in-band |
| **5. Dreaming** | Dreaming (GA on platform) | **nothing** | ❌ this workstream |

The failure mode she describes is precisely ours: every memory operation is
**in-band**. The LSE splits focus between the task and `record_error`/
`index_to_kb`; the debrief skill sees only its own session; nothing ever reads
across sessions. The evidence is already on disk:

- `/opt/local-se/agent_commands.log` — 44,000+ audited commands nobody has mined
  (the RFC-KB lesson: zero `search_rfc` calls in 44,637 commands was discovered
  by hand, months late).
- `/opt/local-se/tasks.db` — planner-v2 ledger with per-step evidence and
  failure routes; never analyzed across tasks.
- `kb/session-learnings.md` — 860 lines of debrief prose no retrieval loop consumes
  (the exact SCRIBE-2 complaint).
- `lse-kb` — dedup happens only at `index_to_kb` write time; near-duplicates and
  TTL-expired docs accumulate until a human notices.
- The 2026-07-06 pfSense token-bomb and the 2026-07-04 exit-255 storm each cost
  hours and were each turned into hardening *by hand, in-session*. Dreaming is
  the mechanism that does that turn automatically, overnight.

**Bottom line (hers, adopted):** memory alone isn't enough. We add a post-session
reflection loop that curates, prunes, and learns from accumulated experience —
so the LSE improves over time instead of just remembering more.

## 2. Architecture decisions (fixed for this workstream)

1. **The dreamer is the local model, offline.** A scheduled sandbox job
   (systemd timer on LUCIFER) drives the same llama-server/Ollama cascade the
   planner already uses (`_llm_call` pattern, node3090 :8080 → Ollama → Gemma
   GGUF spawn, VRAM-gated). No cloud dependency; Cowork remains available for
   ad-hoc deep passes but is not in the loop.
2. **Dreams propose; gates apply.** Dream output is a proposals file, not direct
   ES writes. Semantic changes pass the same human-confirm gate the debrief
   skill uses. Only a small allowlist of mechanical operations may auto-apply,
   and only after the eval in Thread 4 earns it.
3. **Hard invariants, code-enforced (same philosophy as v0.3.9 pfSense caps):**
   - A dream can never *raise* `quality`, never write `source_tier=ground_truth`,
     never touch quarantined (stale=true, q=0.2) docs except to propose deletion
     to a human.
   - Every dream-originated write carries `provenance=dream-YYYY-MM-DD` and
     `origin=dream` (extends the REFACTOR-4 origin-tag plan: `web|local-probe|human|dream`).
   - The dreamer's own episodes are excluded from its corpus (no dream-of-dreams).
4. **Corpus is server-side.** llama-ui stores chat threads client-side, so
   transcripts are captured where every tool call already flows: the
   `goethe_mcp.py` `register()` wrapper journals request+response per session
   to episode JSONL files. Audit log, tasks.db, and the three ES indices
   complete the corpus.
5. **SCRIBE is absorbed.** SCRIBE-1/-2/-3 become Thread 1 prompts (the unified
   write path IS the dream apply-path); SCRIBE-4 becomes Thread 3 prompt 7.
   SCRIBE-5 stays a standing discipline (docstring audits appear in every thread).

**Known risk carried forward:** goethe.py is 7,087 lines; PH5-2 (extract
`goethe_kb.py`) was deliberately NOT made a prerequisite (4-thread scope
decision). TRAUM adds code mostly in *new* files (`tools/dream_runner.py`,
`tools/dream_apply.py`, gateway journaling) to avoid growing the god-class;
if Thread 2 forces significant goethe.py edits, stop and do PH5-2 first.

**Reference docs (for the Cowork threads, not the local model):**
Memory Stores — platform.claude.com/docs/en/managed-agents/memory (beta,
`managed-agents-2026-04-01` header); Dreaming —
platform.claude.com/docs/en/managed-agents/dreaming (GA); Memory tool —
platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool; Skills —
platform.claude.com/docs/en/agents-and-tools/agent-skills/overview; Anthropic
research post "Long-running Claude for scientific computing" (Mishra-Sharma,
Mar 2026). Use these as design cribs — we implement the local equivalent, not
the managed service.

## 3. Phase map

| Thread | Codename | Delivers | Gate to next |
|---|---|---|---|
| 1 | TRAUM-CORPUS | Episode journaling at gateway; SCRIBE-1/-3 unified debrief write path; SCRIBE-2 backfill | Episodes flowing; contract tests green |
| 2 | TRAUM-ENGINE | `dream_runner.py` (dedup/stale/contradiction/error-cluster passes) + `dream_apply.py` gate | First supervised dream reviewed; invariant tests green |
| 3 | TRAUM-INSIGHT | Cross-session mining (audit log, ledger), skill candidates, morning dream digest, SCRIBE-4 self-measurement | Digest surfacing at session start |
| 4 | TRAUM-AUTO | systemd timer, guardrails, A/B learning-lift eval, threat-model addendum, runbook | Eval verdict recorded (win, loss, or null) |

Each thread is a fresh Cowork thread: paste prompt 1, work to completion,
paste prompt 2, etc. Prompts assume repo root
`C:\Users\SY5\Documents\Claude\Projects\local-system-engineer`
(WSL: `/home/sy5/local-system-engineer`). Every thread ends with the
standard close: tests green → CHANGELOG.md → CURRENT-STATE.md → commit → debrief.

---

## Thread 1 — TRAUM-CORPUS (episode capture + unified write path)

**Goal:** a durable, server-side record of every session, and one gated write
path from human-readable learnings into the retrieval surface.

**Prompt 1.1 — Corpus audit (read-only).**
> Read docs/traum-dreaming-plan.md sections 1–3 for context. Survey the four memory surfaces read-only and write docs/dreaming/corpus-audit.md: (a) /opt/local-se/agent_commands.log — line format, date range, count, one sample per distinct format era; (b) /opt/local-se/tasks.db — full schema (.schema), row counts, steps_json shape from one real task; (c) ES indices lse-kb / lse-errors / lse-skills — doc counts, mapping fields, quality/stale/volatility distributions; (d) kb/session-learnings.md — entry count, date range, section-structure consistency. No writes outside docs/dreaming/. End with a "corpus readiness" verdict per surface.

**Prompt 1.2 — Design doc.**
> Write docs/dreaming/DESIGN.md: dataflow diagram (sessions → episode JSONL → dream_runner → proposals.jsonl → dream_apply gate → ES/kb), the five architecture decisions from docs/traum-dreaming-plan.md §2 restated as testable invariants, episode JSONL schema (ts, session_id, tool, args_redacted, result_truncated, exit_class), and a redaction rule list (vault secrets, PFSENSE_API_KEY, HERMES_API_KEY, Bearer tokens never enter episodes). Include a Shostack 4-question mini threat model for the dream write path — poisoning via dreamed content is the headline threat; cite the REFACTOR-4 origin-tags plan.

**Prompt 1.3 — Gateway journaling.**
> Implement episode journaling in tools/goethe_mcp.py: in the register() wrapper (~line 281), after each tool call, append one JSONL line per DESIGN.md schema to /opt/local-se/episodes/YYYY-MM-DD/<session>.jsonl. Session id: derive from MCP session/connection identity if the SDK exposes it, else fall back to gateway-PID + first-call timestamp. Cap result field at 2,000 chars (the 2026-07-06 token-bomb lesson — cap at write time). New valve EPISODE_DIR (env GOETHE_EPISODE_DIR), journaling ON by default, failures must never break the tool call (wrap in try/except, log to stderr). Bump goethe_mcp to v1.10.0.

**Prompt 1.4 — Episode manifest + rotation.**
> Add tools/episode_index.py: scans EPISODE_DIR, builds/updates /opt/local-se/episodes/manifest.db (SQLite: session_id, start_ts, end_ts, n_calls, n_errors, tools_used, bytes, dreamed_at NULL). Add size hygiene: gzip episode files older than 7 days, refuse to journal if the day-dir exceeds 500 MB (loud stderr warning). Unit-test manifest build against synthetic episode files in tests/test_dream_corpus.py.

**Prompt 1.5 — SCRIBE-1: unified debrief write path.**
> Extend the lse-session-debrief skill flow per ROADMAP Workstream E SCRIBE-1: debrief Step 4 additionally proposes structured calls — facts → index_to_kb(source_tier=..., verified_against=...), procedures → skill_record(provenance="debrief YYYY-MM-DD") — shown in the SAME single human-confirm gate; one yes commits file + ES together. kb/session-learnings.md remains the human journal, ES the retrieval surface. Update the skill doc/template accordingly and record the exact proposal format in docs/dreaming/DESIGN.md (dream_apply will reuse it verbatim).

**Prompt 1.6 — SCRIBE-3: contradiction step.**
> Add the "Contradicts existing KB?" step to the debrief template: before proposing new writes, search_kb for each claimed fact; if the session disproved an existing entry, the proposal must include record_outcome(doc_id, success=False, evidence=...) — KB-DECAY demotion — instead of writing the new truth alongside the old. Document one worked example using a real contradiction if the KB contains one (corpus-audit may have surfaced candidates).

**Prompt 1.7 — SCRIBE-2: backfill distiller.**
> Write scripts/distill_learnings.py: parse kb/session-learnings.md (860 lines, ~entry per session), propose index_to_kb/skill_record candidates as a diff-style review list (one JSONL proposal per candidate, provenance=debrief-backfill-<orig-date>). NO auto-commit — print for per-entry human approval, apply only approved ids via a second pass (--apply ids.txt). Run it, review together in this thread, apply the approved set, and record counts (proposed/approved/rejected) in the thread debrief.

**Prompt 1.8 — Contract tests.**
> Extend tests/test_dream_corpus.py: (a) journaling redaction — synthetic tool call containing a fake Bearer token and vault-shaped secret must produce a JSONL line with both redacted; (b) result-cap enforcement at 2,000 chars; (c) provenance format validation for debrief/backfill proposals; (d) journaling failure does not raise into the tool path. Wire the file into run_tests scope=harness (it lives under tests/, so pytest discovery should suffice — verify with run_tests output, not assumption).

**Prompt 1.9 — Docstring/skill audit.**
> Run the lse-docstring-optimizer discipline (SCRIBE-5) over everything Thread 1 touched that the model will read: the updated lse-session-debrief skill text and any changed valve descriptions. Fix ambiguities before deploy — the v0.3.4 planner-gate conflict is the cautionary precedent.

**Prompt 1.10 — Thread close.**
> Close TRAUM-CORPUS: run_tests(scope=all) on LUCIFER — all green or explained SKIPs; restart the gateway via tools/start-goethe.sh and verify episodes appear for a fresh llama-ui thread (REMINDER: fresh thread after gateway deploy — schema snapshot). Update CHANGELOG.md (goethe_mcp v1.10.0 entry), CURRENT-STATE.md (deployed versions + TRAUM status line), ROADMAP.md (tick absorbed SCRIBE items), commit, and run the session debrief — through the NEW unified write path, eating our own dogfood.

---

## Thread 2 — TRAUM-ENGINE (the dream mechanics)

**Goal:** an offline runner that reads the corpus and emits gated proposals:
dedup merges, stale/contradiction demotions, error-cluster skill candidates.

**Prompt 2.1 — Runner skeleton.**
> Read docs/dreaming/DESIGN.md and docs/dreaming/corpus-audit.md. Write tools/dream_runner.py skeleton: loads manifest.db sessions where dreamed_at IS NULL, reads their episode JSONL + the ES indices READ-ONLY, drives the local model through the same endpoint cascade as goethe.py's planner (reuse the pattern: PLANNER_FORCE_URL-style valve DREAM_LLM_URL, thinking_budget_tokens=0, two-attempt envelope loop with corrective retry). Output: /opt/local-se/dreams/YYYY-MM-DD/report.md + proposals.jsonl. Dry-run only in this thread — the runner never writes to ES. CLI: --sessions N --since DATE --pass <name> --dry-run (default true).

**Prompt 2.2 — Dedup pass.**
> Implement the dedup pass: pull lse-kb docs, embed via Ollama nomic-embed-text (same 768-dim path as search_kb), find near-duplicate pairs by cosine. Sweep the threshold against eval/retrieval-gold-v1.jsonl-adjacent judgment (v2 is a DATA-1 aspiration, not yet built): sample 20 candidate pairs at 3 thresholds, we label them together in-thread, pick the threshold with zero false merges. Each dedup proposal: keep-doc (higher quality, else newer), merge-doc, merged-text suggestion from the model, and the WHY. Remember PH3-2: if the data says dedup finds nothing worth merging, record the null result — that is a valid outcome.

**Prompt 2.3 — Stale/contradiction pass.**
> Implement the staleness pass: (a) CHRONOS TTL-expired docs (volatility fast>7d, slow>90d without record_outcome bump) → proposal type "reverify" carrying a suggested kb_verify(doc_id) probe; (b) contradiction detection — for each recent episode where a tool result contradicts a high-quality KB doc surfaced in the same session (model judges, must quote both verbatim), proposal type "demote" carrying record_outcome(doc_id, success=False, evidence=<verbatim>). Evidence ≥20 chars, verbatim-quote rule enforced in the proposal validator, not just the prompt.

**Prompt 2.4 — Error-cluster pass.**
> Implement the error-cluster pass: group lse-errors docs + episode exit_class≠0 sequences by embedding similarity; for clusters of ≥3 occurrences spanning ≥2 sessions, emit proposal type "skill-candidate" with a drafted skill_record body (trigger, procedure, provenance=dream-<date>, the cluster's episode ids as evidence). The exit-255 ControlMaster storm and the Grafana env-var confusion are the archetypes — check whether the corpus would have caught them.

**Prompt 2.5 — Apply gate.**
> Write tools/dream_apply.py: reads proposals.jsonl, validates every proposal against the code-enforced invariants (never raises quality, never ground_truth, never touches quarantined docs, origin=dream + provenance=dream-<date> stamped on every write, dedup merge preserves the higher quality and the union of runs/ok/fail stats), then presents them in the SCRIBE-1 confirm-gate format for per-proposal human yes/no. Applies via the same goethe.py tool functions (import the Tools class like goethe_mcp does — one write path, not two). Rejected proposals are logged with reason to the dream dir.

**Prompt 2.6 — Auto-apply allowlist (design only).**
> Add to DESIGN.md the auto-apply policy: which proposal types could EVER skip the human gate (candidates: exact-duplicate merge at cosine ≥0.99 with identical verified_against; TTL "reverify" tagging since it changes no content; nothing else), and the promotion rule — auto-apply is enabled per-type only after Thread 4's A/B eval shows the gate-reviewed version caused zero rejected-in-hindsight applies for 2 consecutive weeks. Code stays human-gated for now; add the DREAM_AUTO_APPLY valve (default "", comma-separated types) wired but empty.

**Prompt 2.7 — First supervised dream.**
> Run the first real dream: dream_runner over the full backlog (all undreamed sessions + full lse-kb for dedup/stale passes), dry-run. Read report.md together. For each pass record: proposals emitted, obviously-wrong count, obviously-valuable count. Then dream_apply the approved subset. Update manifest dreamed_at for consumed sessions. This is the calibration run — expect noise; the deliverable is the labeled review, not a clean report.

**Prompt 2.8 — Measure the dream.**
> Quantify the calibration run: run_tests(scope=retrieval) before/after numbers (recall@1/@3, MRR on the gold set — re-check min_score=4.2 still holds per the v0.3.8 re-sweep rule since doc count changed), lse-kb doc count delta, duplicate-pair count remaining, demotions applied. Write the numbers into docs/dreaming/calibration-run-1.md. If retrieval regressed, dream_apply has a bug or the gold set drifted — stop and diagnose before Thread 3.

**Prompt 2.9 — Invariant tests.**
> Write tests/test_dream_engine.py: proposal validator rejects quality-raising, ground_truth, and quarantine-touching proposals (synthetic fixtures); origin/provenance stamping verified on an applied proposal against a disposable ES doc; dedup merge preserves trust-field union; the runner's ES client is read-only (assert no index/update/delete calls escape dream_apply — mock-based). Run alongside test_kb_contracts.py; all green.

**Prompt 2.10 — Thread close.**
> Close TRAUM-ENGINE: full test pass, CHANGELOG (dream_runner/dream_apply v0.1.0 entries), CURRENT-STATE (TRAUM engine status + calibration numbers), VALVES.md (DREAM_LLM_URL, DREAM_AUTO_APPLY, EPISODE_DIR if not yet documented), commit, debrief via unified write path — include the calibration verdict as a KB fact proposal.

---

## Thread 3 — TRAUM-INSIGHT (cross-session learning surfaced forward)

**Goal:** the payoff Mukta promises — the next session starts smarter. Mining
across sessions, skill learning, and a digest the LSE actually sees.

**Prompt 3.1 — Audit-log miner.**
> Add a "patterns" pass to dream_runner: mine /opt/local-se/agent_commands.log (44k+ lines) mechanically first (no LLM): command frequency table, failure→retry adjacency (same command reissued within N lines after error), tool-usage counters per tool per week (the RFC-KB zero-usage class of finding), longest repeated command sequences (≥3 commands recurring across ≥3 sessions = automation candidates). Output patterns.json; keep it deterministic and unit-testable.

**Prompt 3.2 — Insight prompts.**
> Feed patterns.json + the last N session summaries to the local model with a structured insight schema: {observation, evidence_refs, cost_estimate (wasted calls/time), proposed_change (kb-fact | skill | prompt-rule | tool-change), confidence}. Prompt engineering matters here — tight scope per Qwen3.6's profile, one insight domain per call, verbatim-evidence rule. Insights land in report.md under "Cross-session insights"; proposal-shaped ones flow into proposals.jsonl through the same validator.

**Prompt 3.3 — Skill learning from the ledger.**
> Mine /opt/local-se/tasks.db: steps that failed then succeeded after revision → what changed between the two packaged_prompts becomes a skill-candidate or planner-contract note; tasks with >2 revise cycles → KB fact about that task class. Also backfill skill_outcome for existing lse-skills entries where ledger evidence shows use (match skill text against step evidence — propose, don't auto-write).

**Prompt 3.4 — The morning digest.**
> Generate /opt/local-se/dreams/latest-digest.md at the end of every dream run: ≤30 lines — what changed in the KB overnight (applied proposals), top 3 insights, pending human-gate items, one-line corpus stats. This file is for BOTH audiences: the operator reads it, and the LSE loads it (next prompt).

**Prompt 3.5 — Surface the digest in-session.**
> Wire the digest into session start the CHRONOS way — server-injected, not docstring-dependent: the first search_kb return of each gateway session already carries the [TIME] banner; extend that injection with a [DREAM] line (digest date + pending-gate count + "read /opt/local-se/dreams/latest-digest.md for details"). Cap the injection at 200 chars. This is a goethe.py change — keep it minimal (the PH5-2 warning from the plan §2 applies), bump to v0.4.0-a, and note that llama-ui threads must be restarted after deploy.

**Prompt 3.6 — Prompt-rule proposals.**
> Handle insight type "prompt-rule": dreams may propose additions to a new generated include file prompts/learned-rules.md (versioned, human-gated like everything else) — NEVER direct edits to the canonical node4090 prompt. Operator manually merges accepted rules into the next prompt version bump (the existing v0.5.x→v0.6.0 discipline). Document the merge workflow in DESIGN.md; seed learned-rules.md with any accepted insights from prompts 3.2–3.3.

**Prompt 3.7 — SCRIBE-4: self-measurement.**
> Build the self-measurement the RFC-KB lesson demands: dream runs append to report.md a retrieval-of-dreamed-docs section — are dream/debrief-provenance docs being HIT by search_kb in subsequent episodes (episode JSONL shows the calls), uses/successes/failures/archived from lse-skills stats, and month-over-month deltas. A memory system that writes docs nobody retrieves is the failure mode; measure it from day one.

**Prompt 3.8 — Null-result discipline.**
> Add explicit null-result handling: a pass that finds nothing emits a "null" record with corpus size + thresholds used (so we can distinguish "nothing there" from "didn't look"), and report.md says so plainly. Run a full dream cycle now (all passes including new ones) and review the complete report + digest together in-thread.

**Prompt 3.9 — Tests + audits.**
> Extend tests: patterns.json determinism (fixed fixture log → fixed output), digest ≤30 lines / [DREAM] injection ≤200 chars, learned-rules.md never auto-merged (validator rejects prompt-rule proposals targeting prompts/node4090*), insight schema validation. Run lse-docstring-optimizer over the [DREAM]-banner-adjacent docstring changes in goethe.py. All green.

**Prompt 3.10 — Thread close.**
> Close TRAUM-INSIGHT: full test pass, deploy v0.4.0-a to LUCIFER (fresh llama-ui thread), verify the [DREAM] banner appears on first search_kb, CHANGELOG + CURRENT-STATE + VALVES.md, commit, debrief through the unified path. Record in the debrief: the first insight the digest surfaced that you (operator) judge genuinely non-obvious — or the honest null.

---

## Thread 4 — TRAUM-AUTO (automation, guardrails, and proof)

**Goal:** nightly cycles without babysitting, and an honest answer to
"did dreaming actually help" — win, loss, or null, recorded either way.

**Prompt 4.1 — Timer + scheduling.**
> Create lse/services/goethe-dream.service + .timer (template style matching goethe-mcp.service.tmpl): nightly at 03:30, RandomizedDelaySec 15m, runs dream_runner as sy5 in a sandbox dir. VRAM-aware: reuse the _planner_free_vram_mb gate pattern — if node3090 GPU is busy, fall back to the Ollama/CPU path rather than skipping (dreams are latency-insensitive). Wire into the launch scripts the same way existing services are.

**Prompt 4.2 — Concurrency + budget guardrails.**
> Add to dream_runner: lockfile (skip run if an LSE session was active in the last 30 min per manifest, or a previous dream holds the lock), per-run budgets (max sessions consumed, max LLM calls, max wall-clock 45 min — hard kill with partial report), and dreamer-episode exclusion (the runner's own tool calls must not enter EPISODE_DIR — assert, don't assume). Budget exhaustion is a normal exit with a truncation note, not an error.

**Prompt 4.3 — Failure handling.**
> Crash discipline: any unhandled dream_runner exception → record_error to lse-errors (context="dream-runner", provenance=dream-infra), partial report written with a FAILED banner, manifest rows NOT marked dreamed_at (safe re-dream), timer keeps firing (no systemd failure spiral — Restart=no, next night retries). Test by injecting a fault. Also: 3 consecutive failed nights → digest banner escalates to the operator.

**Prompt 4.4 — Pending-gate queue.**
> Morning workflow: dream_apply --queue lists pending human-gate proposals across all dream runs (oldest first, grouped by type); latest-digest.md already counts them. Add a staleness rule — proposals older than 14 days are auto-expired with reason (the world moved; re-dream will re-propose if still true). Document the 5-minute morning review loop in the runbook entry (prompt 4.9).

**Prompt 4.5 — A/B eval design.**
> Design the learning-lift eval in eval/traum-ab-design.md before running anything: Condition A = current KB snapshotted pre-dreaming-era (ES snapshot; DATA-4 trust-field preservation applies), Condition B = live dreamed KB. Same harness (v35_harness.py — commit it to the repo first, it is still in /tmp/lse/), same suite (v3.5 S/A/W/P), same model + prompt version, fresh threads. Metrics: suite score, retrieval recall/MRR on the frozen gold set (retrieval-gold-v1.jsonl @50, sha256 per DATA-3), tool-call count to completion per scenario (the "faster verification" claim), wrong-KB-hit count. Pre-register the success criterion: B beats A on suite score OR reduces tool calls ≥10% with no score loss; anything else is a null or a loss — recorded either way.

**Prompt 4.6 — Run the eval.**
> Execute the A/B per the design doc: restore Condition A snapshot to a temp index (lse-kb-a), point a gateway instance at it (ES_URL/index valve override), run the suite; run Condition B against live. Score both, write eval/eval-report-traum-1.md with the pre-registered verdict. If the verdict is a loss, the plan's §2 invariants are suspect — file the specific bad KB writes to lse-errors and do NOT enable any auto-apply.

**Prompt 4.7 — Threat-model addendum.**
> Write the dreaming section of docs/threat-model-kb.md (creating the file if REFACTOR-4 hasn't landed): what we built (dream dataflow), what can go wrong — poisoning via web-content that flowed through episodes into dreamed facts (origin=dream can never launder origin=web into higher trust), prompt-injection persisted in episode JSONL replaying into the dreamer, gate fatigue (operator rubber-stamping proposals), dreamer endpoint compromise — what we do (invariant validator, redaction tests, budget caps, provenance forensics), did it work (map each mitigation to its contract test by name).

**Prompt 4.8 — Autonomy tuning.**
> With eval evidence in hand, decide auto-apply per the Thread-2 promotion rule: for each mechanical proposal type, count rejected-in-hindsight applies over the review period; enable in DREAM_AUTO_APPLY only types with zero. Decide cadence (nightly vs 2-3×/week) from corpus growth rate vs proposal yield in the reports. Record both decisions + evidence in DESIGN.md's decision log. If evidence says keep everything human-gated — that is a fine steady state, write it down.

**Prompt 4.9 — Documentation pass.**
> Runbook + docs: add "Dreaming operations" to docs/07-operations-runbook.md (morning review loop, digest location, timer status checks, failed-night escalation, how to re-dream a session, how to trace a KB doc back to its dream/episode via provenance), update VALVES.md with all TRAUM valves, update README.md repo-layout section, and verify every path/command in the runbook by executing it.

**Prompt 4.10 — Workstream close.**
> Close TRAUM: run_tests(scope=all) green on LUCIFER; final CHANGELOG entry (declare the v0.4.0 line = TRAUM era); CURRENT-STATE.md updated with dream service status + eval verdict; ROADMAP.md reconciled (TRAUM section marked with per-thread completion, absorbed SCRIBE items closed, PH5-2 urgency re-assessed given whatever goethe.py grew during Threads 2–3); commit; final debrief. Last act: let that night's dream run process THIS workstream's sessions, and read the digest the next morning — the loop reviewing its own construction is the acceptance test.

---

## 4. What we are explicitly NOT doing

- **Not** using Claude Managed Agents / Memory Stores / hosted Dreaming — the
  LSE is a local-first system; the platform docs are design cribs only.
- **Not** letting dreams write ground truth, raise quality, or edit the
  canonical system prompt — trust still flows only through probes and humans.
- **Not** deleting anything — quarantine and expiry, never deletion (existing
  KB-DECAY rule, unchanged).
- **Not** gating this workstream on the PH5-2 refactor — but Thread 2/3 goethe.py
  growth is the tripwire that re-opens that decision.

## 5. Acceptance status and operator entry point

The shipped system is operated from `docs/07-operations-runbook.md` §10; this
file remains the implementation history and prompt ledger. The reusable prompt
for creating or refreshing the operational KB entry is
`docs/dreaming/KB-ENTRY-PROMPT.md`.

The 2026-07-13 sandbox acceptance test exercised all five passes against live,
read-only corpus/ES inputs; wrote reports, proposals, null-results and the digest
only under `/tmp/lse/`; listed the queue; and ran the apply path in dry-run mode.
One proposed skill passed the apply validator and one malformed skill was
rejected, proving both sides of the gate without a production KB write.

Acceptance also found and fixed a loaded-model routing defect: free VRAM is not
an activity signal when llama-server already owns the GPU allocation. v0.4.1
uses `/slots` activity first (idle → reuse, processing → CPU fallback), retaining
the 2,000 MiB free-VRAM gate only when slot state cannot be read.
