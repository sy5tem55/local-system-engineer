# TRAUM / Cowork session handoff

Read this file at the start of any new Cowork thread continuing TRAUM work.
It exists because Cowork threads do not share memory with each other — each
new thread starts cold and must re-derive everything below from the repo.
Keep this file current: update it (don't append-only like CHANGELOG.md —
this one gets overwritten) at the end of every thread that touches TRAUM.

## 1. What this is

TRAUM is the offline "dreaming" self-improvement loop for the LSE (Local
System Engineer) project — plan doc: `docs/traum-dreaming-plan.md`. The plan
has 4 Threads, each with numbered Prompts (4.1, 4.2, ...). Ground truth for
what's actually been BUILT (not just planned) is `CHANGELOG.md`'s TOP entry
— read it first, every time. The plan doc itself has no status tracker; it
is the spec, not the log.

## 2. Current status (as of 2026-07-13)

**ALL FOUR THREADS CLOSED — the TRAUM workstream is COMPLETE (v0.4.0 line).**
Committed at the Thread 4 close (see git log). Standing state a future
thread should know:

  - Nightly timer LIVE: `goethe-dream.timer`, 03:30 ±15 min, first
    unattended fire 2026-07-14 03:32 CEST. Units in /etc/systemd/system,
    templates in `lse/services/`. Runbook: `docs/07-operations-runbook.md` §10.
  - `DREAM_AUTO_APPLY` is EMPTY by recorded decision (DESIGN.md §7.4,
    2026-07-13) — do not change without a new §7.4 entry; the 2-week
    measurement window starts with the first unattended cycle.
  - Eval verdict on record: LOSS, methodologically inconclusive
    (`eval/eval-report-traum-1.md` §6-7); its §7 re-run recipe is the
    precondition for ever promoting a type.
  - Thread-3's two flagged findings were FIXED at Thread-4 open:
    pass-scoped `report-<pass>.md`/`proposals-<pass>.jsonl` (readers glob,
    legacy day-dirs still readable) and `redact_log_text()` in
    `dream_runner.py` (agent-log secrets scrubbed at parse time).
  - Known-open: operator credential rotation (sshpass password);
    elasticsearch-py unpinned anywhere (drift bit once already,
    2026-07-11); origin-tags unimplemented (PH5-3); PH5-2 (goethe.py
    7,228 lines) blocks the next goethe.py-touching workstream.

Historical status below preserved for context:

Threads 1 (TRAUM-CORPUS), 2 (TRAUM-ENGINE), 3 (TRAUM-INSIGHT) are closed.
Thread 4 (TRAUM-AUTO) was in progress: **Prompts 4.1–4.7 done** (4.8–4.10
closed 2026-07-13, plus the 4.1 install gap — the .tmpl units existed but
the timer was never installed; found and closed same day).

  - 4.1 Timer + scheduling — `lse/services/goethe-dream.service/.timer`
  - 4.2 Concurrency + budget guardrails — lockfile, DreamBudget
  - 4.3 Failure handling — record_crash_error, FAILED-banner reports,
    3-consecutive-failed-nights digest escalation
  - 4.4 Pending-gate queue — `dream_apply.py --queue`, 14-day auto-expiry
  - 4.5 A/B eval design — `eval/traum-ab-design.md` written. Reconstructed
    + committed `eval/v35_harness.py` v0.1.0 (the original named by the
    plan was never actually committed and its `/tmp/lse/` copy had already
    been cleared — confirmed gone on both LUCIFER and node3090; this is a
    from-scratch rebuild from `eval-report-v8.md`'s description + the
    proven wiring in `t1_mcp_harness.py`, not a recovered original — see
    the file's own docstring). Gold set `retrieval-gold-v1.jsonl` frozen
    (sha256 in the design doc, DATA-3). **IMPORTANT finding baked into the
    design**: there is no ES snapshot repository configured on LUCIFER
    (`GET /_snapshot` → `{}`) and no true pre-dreaming-era snapshot exists
    — Condition A had to be redefined as "frozen at eval-start" rather
    than "frozen before Thread 2" (that data is genuinely gone, mutated in
    place by 3 dedup merges + a full Thread-3 dream cycle + ongoing
    backfill since 2026-07-11). Read `eval/traum-ab-design.md` §2 before
    starting 4.6 — the snapshot-repo registration + Condition-A snapshot +
    disposable second-ES-instance steps are specified there but
    DELIBERATELY NOT YET EXECUTED (design-only scope for 4.5).
  - **GITIGNORE FINDING (discovered while committing 4.5's harness):** `.gitignore` line 44 is a blanket `eval/` rule — the ENTIRE eval/ directory is untracked, always has been. This is the real reason v35_harness.py was "never committed" (nothing in eval/ ever was, including t1_mcp_harness.py, retrieval-gold-v1.jsonl, every eval-report-v*.md). v35_harness.py and traum-ab-design.md were written to disk in eval/ for 4.5 but are NOT in git history — this matches the "commits happen at thread-close" convention (§5) for now, but whoever runs Prompt 4.10 (Thread 4 close) must first decide whether to carve an exception into .gitignore for eval/ (at minimum the frozen gold set + this harness) before `git commit` can actually capture them. Flagged, not fixed, in 4.5 — changing repo-wide .gitignore policy was judged out of scope for a design-only prompt.

  - 4.6 Run the eval — DONE. Verdict: **LOSS** (A=53/60, B=51/60 on v3.5;
    tool calls A=31/B=34, more not fewer — both legs of the win criterion
    failed). Full report: `eval/eval-report-traum-1.md`. **Root cause is
    methodological, not a bad KB write** — read report §6-7 before doing
    anything with this verdict: Condition A's snapshot and B's live run
    happened only ~15 min apart (no nightly dream cycle in between), so
    the two KBs barely diverged; retrieval recall/MRR was bit-for-bit
    identical between conditions and wrong-KB-hit count was 0 for both.
    The score delta traces to tool-use-reasoning differences (sudo/
    permission judgment, a hallucinated "file doesn't exist" on a
    permission-denied read) in scenarios that never touched `lse-kb`
    content — almost certainly ordinary model-sampling variance
    (n=1 per condition, `--reasoning-budget -1`, no temperature pinning),
    not evidence dreaming hurts quality. `record_error` filed
    (hash `6122c47830260f4e`) instead of a fabricated bad-KB-write
    citation. `DREAM_AUTO_APPLY` left empty regardless. **Deviated from
    the design doc's ES-native-snapshot plan**: the live ES container has
    no `path.repo` configured; rather than restart production ES mid-eval
    to add one, Condition A's isolation was achieved by cloning every doc
    (mapping + `_id` + `_source`, trust fields intact) into a disposable
    `elasticsearch:9.4.3` container instead — same isolation guarantee,
    zero production risk. Disposable infra (port 9701 gateway,
    `elasticsearch-eval-a` container+volume) was torn down after the
    report was filed; `llama-server` (`:8080`, which was NOT running at
    the start of 4.6 and had to be started fresh) was left running as a
    shared service.
  - 4.7 Threat-model addendum — DONE. Created `docs/threat-model-kb.md`
    (REFACTOR-4/PH5-3 confirmed NOT landed on ROADMAP.md before creating
    it — this file did not exist). Wrote the dreaming section only (§1-4);
    §5 is a deliberate stub for REFACTOR-4's broader scope (P0-2 gateway
    exposure, tier self-grant, NTP spoof, ES-unauthenticated) — do NOT
    treat this file as "REFACTOR-4 done," only its dreaming chapter.
    **Real finding surfaced while writing it**: `origin=web`/`origin=human`/
    `origin=local-probe` tagging (the other 3/4 of the origin-tag plan
    `origin=dream` is supposed to extend) does not exist anywhere in
    `goethe.py`'s live `index_to_kb` path — grep-verified, zero hits. So
    the poisoning-via-web-content-laundering mitigation is currently the
    blunt "dream can never mint ground_truth regardless of source," not
    genuine source-aware detection. Also found: the "secret-scan CI check"
    DESIGN.md §5 described as already-a-mitigation was never actually
    built (no `.github/workflows/` in this repo at all) — corrected in the
    new doc, not silently carried forward as if it existed. All 127 cited
    test node-ids were `pytest --collect-only`-verified against the live
    test files before being written down — if a future edit to
    `tests/test_dream_*.py` renames or removes one of them, this doc's
    §4 table goes stale silently; worth a lint pass if this file gets
    revisited.
  - 4.8–4.9 not started (autonomy tuning — the 4.6 loss verdict +
    root-cause finding AND 4.7's threat-model gaps are now both direct
    inputs to that decision; runbook + Thread close). A proper eval re-run
    recommendation (real elapsed dreaming window + multiple trials) is in
    `eval/eval-report-traum-1.md` §7, not yet acted on.

Live versions right now: `dream_runner.py` v0.11.0, `dream_digest.py`
v0.2.0, `dream_apply.py` v0.3.0, `eval/v35_harness.py` v0.1.0 (new).
(Re-check via `grep __version__` — this file can go stale; the grep never
lies.)

## 3. Execution model — READ THIS FIRST

This is a **Cowork session with live tool access to the real LUCIFER box**
via `mcp__goethe__*` tools (`read_file`, `write_file`, `execute_command`,
`search_kb`, ...). This is **NOT** a local sandbox task — there is no
"Edit" tool for this filesystem. The local Read/Edit/Write/Bash tools (if
present) operate on a totally separate throwaway sandbox and are USELESS
for this work except as scratch space before transferring content via
`mcp__goethe__write_file`.

**The anchored-edit pattern** (since there's no remote Edit tool): write a
Python script to `/tmp/edit_*.py` via `execute_command` heredoc, read the
target file, do `src.count(old) == 1`-verified `str.replace(old, new, 1)`
calls (fail loudly if the anchor isn't exactly 1 match), write back, then
`python3 -m py_compile` to verify syntax. Clean up `/tmp/edit_*.py` when
done. `rm -rf` is permanently blocked — use uniquely-named tmp dirs instead
of trying to delete them, or `python3 -c "import shutil;
shutil.rmtree(...)"` for a specific known-safe path.

## 4. The user's pattern

The user pastes a prompt's markdown block verbatim as their entire message,
often with zero additional instructions. This means: **implement it fully
against the live repo**, don't ask clarifying questions the codebase's own
conventions already answer. If the exact same prompt text is pasted again,
check whether it's already done (git log / CHANGELOG top entry / grep
version numbers) before redoing anything — this has happened twice before
and the correct move both times was to report status, not repeat work.

When a prompt's own stated premise turns out to be false against the live
system (4.5's "v35_harness.py ... it is still in /tmp/lse/" — it wasn't),
the established move (set by 4.5) is: verify directly rather than trust
the prompt text, document the discrepancy plainly in the deliverable, and
do the best-faith reconstruction/workaround rather than silently skip the
requirement or silently paper over the gap.

## 5. Conventions every prompt is expected to follow (established across
   4.1–4.5, not stated explicitly by the user — discovered from the repo)

  - Real code changes on LUCIFER via goethe tools (never local-only).
  - New `DreamConfig`/`DigestConfig` fields always get **defaults** — the
    ~6 existing test files construct these directly and must never break.
  - Thorough tests reusing established fixture patterns: local `_cfg()`
    helper and local `FakeES` class PER TEST FILE (not shared/imported
    cross-file — that's the established, deliberate convention).
    `REPO_ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0,
    str(REPO_ROOT / "tools"))` at the top of every test file.
  - `python3 -m py_compile` on every edited module + `systemd-analyze
    verify --recursive-errors=no` on any edited `.tmpl` unit file.
  - **Run tests scoped**: `pytest tests/ -k dream -q` — the FULL suite
    (`pytest tests/`) reliably times out the `execute_command` MCP call
    (~60s+ including live-ES contract tests); dream-scoped alone runs in
    5-8s and is what's been used for verification throughout.
  - A version bump in the affected module's `__version__`.
  - A CHANGELOG.md entry at the very top of the file (right after the
    `---` separator, before the previous top entry) — one entry PER
    PROMPT, not per thread. Format: `## YYYY-MM-DD (Cowork, cont'd xN):
    TRAUM Thread N (CODENAME), Prompt N.M — <summary>` + detailed bullets
    per component touched, ending with a "Deferred to later prompts" list.
    Insert via the same anchored-python-script pattern, anchoring on the
    previous top entry's exact heading line.
  - Git commits happen ONLY at THREAD-CLOSE prompts (confirmed via `git
    log` showing "TRAUM Thread N close" messages) — not per-prompt. 4.5
    did NOT commit to git (new files written directly via write_file);
    the next git commit happens at the Thread 4 close prompt (4.10).
  - Live smoke-test whatever was just built against a synthetic tmp tree
    (or real dry-run config) before calling a prompt done. For 4.5:
    `v35_harness.py --suite eval/test-suite-v3.5.md --list` was run for
    real and confirmed 19 chains / 20 scenarios with correct A1→A2 linkage
    before the design doc referenced that number.

## 6. Quick-start for a new thread

Paste this file's path and say "continue TRAUM from here, next prompt is
4.8" — or just paste the Prompt 4.8 block from `docs/traum-dreaming-plan.md`
directly; the conventions above should be re-derived from the repo itself
(CHANGELOG.md entries for 4.1–4.7 are worked examples of the expected
depth) rather than assumed from this summary alone if anything here looks
stale. Before starting 4.8 (autonomy tuning), read BOTH
`eval/eval-report-traum-1.md` in full AND `docs/threat-model-kb.md` §2-4 —
4.8's per-type auto-apply decision (ROADMAP/DESIGN.md §7.3's promotion
rule: 2 consecutive weeks of zero rejected-in-hindsight applies, gated on
an eval verdict) now has two real inputs, not one: the 4.6 eval's LOSS
verdict (inconclusive-by-timing, not a clean data point against auto-apply
— see that report's §6-7), and 4.7's threat model, which found that the
origin-tag asymmetric-trust protection this whole promotion rule leans on
is currently a blunt ceiling, not genuine source-aware laundering
detection (origin=web isn't written anywhere in the live write path yet).
Treat "keep everything human-gated for now" as a live option 4.8 should
seriously weigh, not just the default to fall back to if the numbers don't
clearly support otherwise — Prompt 4.8's own text in the plan doc says so
explicitly ("If evidence says keep everything human-gated — that is a fine
steady state, write it down"), and DESIGN.md §7.3 already anticipates this
verdict shape.
