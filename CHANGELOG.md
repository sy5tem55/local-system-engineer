# LSE Changelog
> Append-only. One entry per session. Never edit past entries.
> Format: `## YYYY-MM-DD — <what shipped>`

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