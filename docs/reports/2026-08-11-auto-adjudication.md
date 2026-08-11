# SPEC-auto-adjudication-2026-08 — implementation report

Commit: `4a1c549` (branch `codex/fix-sudo-grants-live`). Design: Opus 5,
2026-08-09. Implementation: Sonnet 5 High, 2026-08-11.

## 1. What shipped

Three content rules for `diagnosis` proposals, added at record time via the
existing `_initial_state`/`_initial_reason` extension point
(`traum_state.py`'s `record_proposals`):

- **R1** (`tools/diagnosis_rules.py::rule_r1_semantic_duplicate`) — cosine
  similarity over `args.error_text` against every current PENDING/APPLIED
  `diagnosis` prior. `>= 0.92` → `SUPERSEDED`, reason names the surviving
  prior's id and state (`rule:semantic_duplicate:{id}:{state}`).
- **R2** (`rule_r2_third_party_resource_error`) — an HTTP status code plus a
  URL whose host is not confidently local (`.home.arpa`/`.local`/private-IP/
  a short internal-hostname allowlist) → `SYSTEM_REJECTED`
  (`rule:third_party_resource_error:{host}`).
- **R3** (`rule_r3_resolution_redundant`) — cosine similarity between
  `args.error_text` and `args.resolution` `>= 0.82` → `SYSTEM_REJECTED`
  (`rule:resolution_redundant_with_error_text:{sim}`).

No rule ever produces `APPLIED` or `STAGED` (Hazard D). Each is
independently switchable (`cfg.rule_r{1,2,3}_enabled`, default on) and every
fire is counted and printed to stderr from `dream_runner.py`'s
`apply_diagnosis_rules()` (Hazard A). `traum_state.py`'s `repeat_prior()`
now also honors the `rule:` reason prefix as a valid `SYSTEM_REJECTED` prior
(Hazard B) — without this, an R2/R3-rejected proposal redrafted next run
would silently re-enter `PENDING` every time; `tests/test_diagnosis_rules.py`
test 3 proves it doesn't.

`scripts/dry-run-diagnosis-rules.py` (shipped first, per spec §4) reads a
`traum-state.db` via a `file:...?mode=ro` connection — structurally
incapable of writing — replays the current PENDING/APPLIED `diagnosis` rows
in `created_at` order, and reports what R1/R2/R3 would decide without
calling `record_proposals`. This is what calibration and the V3 verification
below are run against.

## 2. Ground truth corrections (§2, verify-don't-trust)

The spec's §2 table was compiled 2026-08-09; re-probed live 2026-08-11
(AGENTS.md §9 — measured, not inferred):

- **18 pending → 16 pending.** Two of the originally-cited 18 proposals had
  already moved to `APPLIED` in the two days between the spec being written
  and this implementation session (confirmed by direct SQL query against
  `/opt/local-se/dreams/traum-state.db`). The live queue at implementation
  time was 16 PENDING `diagnosis` proposals, 13 already `APPLIED`.
- Every other §2 row (the machine-rejection path, the reason-prefix set, the
  `lse-errors-1024` embedding index, `_dedup_floor_default`/
  `_dedup_threshold_default`, the `ERROR_CLUSTER_MIN_OCCURRENCES`/
  `MIN_SESSIONS` bars) checked out exactly as written.

## 3. Threshold calibration (Hazard C — not inherited from 0.92 KB-dedup)

Real cosine scores over the live `error_text` field, via the live
`qwen3-embedding:0.6b` model on Ollama (`http://127.0.0.1:11434`), 2026-08-11:

| Pair | Cosine | Verdict needed |
|---|---|---|
| Reworded CancelledError vs. its APPLIED prior | 1.0000 | must merge |
| node3090 `[TIMEOUT] ssh_script` vs `ssh_run` (same host) | 0.9598–0.9689 | must merge |
| Reworded `[SSH FAILURE] exit 255` vs. its APPLIED prior | 0.9299 | must merge |
| `[TIMEOUT] ssh_run to <ip>` (generic) vs. `...to 192.168.5.41` (specific) | 0.9625 | **ambiguous — see §5** |
| SCP `Permission denied` vs. SSH `Connection timed out` | 0.6526–0.6607 | must NOT merge |
| SCP `Permission denied` vs. CancelledError | 0.5099 | must NOT merge |
| KB-search timeout vs. generic tool-call timeout | 0.4919 | must NOT merge |

**R1 = 0.92.** Clears every "must merge" pair with margin, sits comfortably
above every unambiguous "must NOT merge" pair (max 0.6607), and was chosen
specifically low enough to catch the 0.9299 SSH-FAILURE reword (0.93 missed
it by 0.0001 — confirmed by direct comparison, not a rounding assumption).

`error_text` vs `resolution` cosine, same live model:

| Case | Cosine | Verdict needed |
|---|---|---|
| pfSense API key (resolution restates the fix verbatim) | 0.8345 | must reject |
| SCP Permission-denied resolution (adds real interpretation) | 0.7724 | must NOT reject |
| `[TIMEOUT] ssh_run to <ip>` resolution | 0.7704 | must NOT reject |
| Tool-call-timeout resolution | 0.7083 | must NOT reject |
| SSH-FAILURE, KB-timeout, `ssh: connect... timed out` resolutions | 0.6521–0.6607 | must NOT reject |

**R3 = 0.82.** Sits below the one real redundant case (0.8345) and above
every genuinely-informative resolution observed (max 0.7724), biased toward
the conservative/false-negative side of that gap per spec §4.

## 4. Dry-run V3 transcript (`scripts/dry-run-diagnosis-rules.py --db <copy-of-live-db> --r1-threshold 0.92 --r3-threshold 0.82`)

```
[dry-run] 29 diagnosis row(s) loaded (16 PENDING, 13 APPLIED)
[dry-run] thresholds: r1=0.92 r3=0.82  rules enabled: r1=True r2=True r3=True
  prp_50f883fed87f4b3aad257475fd4cfd68  ->  PENDING (survives)
  prp_eb3873ee5eea483aa85c81d0a66fc2f7  ->  SUPERSEDED  rule:semantic_duplicate:prp_34b569bfdcc646e299c9cb6bd21ad481:APPLIED
  prp_c1e66c9235a2423aa3e088d776328a40  ->  SYSTEM_REJECTED  rule:resolution_redundant_with_error_text:0.8345
  prp_2a94912f70614b0c9c64999f3364e4bf  ->  SUPERSEDED  rule:semantic_duplicate:prp_d037cff23a424d3fbf33ecbe6b93de54:APPLIED
  prp_52584a9ebb3b445990eefb99ea04fb01  ->  PENDING (survives)
  prp_358ca782c4e049619c7615c4a8717492  ->  SUPERSEDED  rule:semantic_duplicate:prp_34b569bfdcc646e299c9cb6bd21ad481:APPLIED
  prp_c6fbb0a811154e8083c8c67550d2064d  ->  PENDING (survives)
  prp_4c17cf8ecb7741ea8402eb035810c078  ->  SUPERSEDED  rule:semantic_duplicate:prp_34b569bfdcc646e299c9cb6bd21ad481:APPLIED
  prp_9533c3c740dd4be58d38c6c53702de45  ->  PENDING (survives)
  prp_06c937864d6e4eec95f3542f67ae9eb3  ->  PENDING (survives)
  prp_c384e68723bc4e5488c69c477ca3419e  ->  SYSTEM_REJECTED  rule:third_party_resource_error:www.raspberrypi.com
  prp_8a7560280d0f4280aaf4f7f47f7c5ed0  ->  SUPERSEDED  rule:semantic_duplicate:prp_b0073400b5504625a5ca9e20e03e43c9:APPLIED
  prp_9ec21b7dc4244ae7b6e69d05b6cfdcba  ->  SUPERSEDED  rule:semantic_duplicate:prp_b0073400b5504625a5ca9e20e03e43c9:APPLIED
  prp_b8c683001c33455a9d1a375f931d318c  ->  SUPERSEDED  rule:semantic_duplicate:prp_06c937864d6e4eec95f3542f67ae9eb3:PENDING
  prp_caecef6140474152ace4c3d31be1561b  ->  SYSTEM_REJECTED  rule:third_party_resource_error:docs.fish.audio
  prp_31b7db5c6c5849e58ce32318f2b45c7b  ->  SUPERSEDED  rule:semantic_duplicate:prp_34b569bfdcc646e299c9cb6bd21ad481:APPLIED
[dry-run] 16 PENDING -> 5 survivor(s) (r1_superseded=8 r2_rejected=2 r3_rejected=1)
[dry-run] wrote nothing (read-only connection; no record_proposals call).
```

Run against a copy of the live database (`cp /opt/local-se/dreams/traum-state.db`
to a scratch path), never the live file itself.

**Acceptance against spec §8's two named targets:** the four `CancelledError`
entries collapse to their APPLIED prior (✅, all four, better than the "one
survives" framing since an APPLIED anchor already existed); `Permission
denied` (`prp_c6fbb0a811`) and the `Connection timed out` variant
(`prp_9533c3c740`) stay separate (✅, exactly as Hazard C required).

**Gap against the "four or fewer" aggregate number:** 5 survivors, not 4 —
see §6.

## 5. §2 mixed-cluster finding (reported, not fixed, per spec §5 anti-goal)

`prp_b8c683001c` (`[TIMEOUT] ssh_run to 192.168.5.41 exceeded 30s`) is
superseded by `prp_06c937864d` (`[TIMEOUT] ssh_run to <ip> exceeded 30s`) —
cosine 0.9625, above the R1 threshold. The second text is **not** a real IP;
the drafting model wrote the literal placeholder `<ip>`, and its `context`
field says "targeting a remote host" (no specific host named), while
`prp_b8c683001c`'s context explicitly names `192.168.5.41`. This is the exact
mixed-cluster hazard the spec's §2 flagged (`prp_b8c68300` justifying itself
with "only one occurrence" despite the `>=3`-occurrence cluster bar) —
confirmed here from a different angle: the upstream error-cluster pass
already treated these as interchangeable enough to draft one generic-host
diagnosis, and R1 (correctly, given its input) agrees with that judgment.
**Not fixed here** (anti-goal, and out of this spec's scope — the fix, if
any, belongs in `run_pass_error_cluster`'s clustering, not in the
adjudication rules that run after drafting).

A second, smaller instance of the same shape: `prp_9ec21b7dc4`
(`ssh_run to node3090.home.arpa exceeded 30s`) scored 0.9376 against the
APPLIED `ssh_script on node3090.home.arpa exceeded Xs` — just below the 0.94
threshold I evaluated but comfortably above the shipped 0.92, so it *does*
merge. This is defensible (same host, same timeout family) but worth naming:
at the margins, R1 cannot distinguish "different tool, same underlying
cause" from "different tool, different cause" — it only has `error_text` to
go on.

## 6. The "5, not 4" survivor gap

At the calibrated thresholds, 16 PENDING → 5 survivors:

- `prp_c6fbb0a811` (SCP `Permission denied`) and `prp_9533c3c740` (`ssh
  connect... Connection timed out`) — **must** stay separate per spec §3
  Hazard C explicitly.
- `prp_50f883fed8` (generic tool-call timeout, non-SSH), `prp_52584a9ebb`
  (KB/Elasticsearch connection timeout), `prp_06c937864d` (generic-host SSH
  timeout, absorbed `prp_b8c683001c` per §5) — three **novel** facts with no
  existing APPLIED prior close enough to merge against (best cross-matches
  measured at 0.48–0.65, far below threshold).

I confirmed this with the user mid-session rather than silently forcing a
merge to hit "four or fewer": lowering R1 further to force one of the three
novel facts into a merge would mean asserting two dissimilar errors (cosine
0.48–0.65, well inside the "must NOT merge" band measured in §3) are the same
underlying fact, with no evidence for it. Per spec §8's own words — "If a
rule would eat something a human would have kept, say so and turn that rule
off" — 5 honest survivors was chosen over 4 forced ones. 16→5 is still a
69% reduction in what reaches a human for this batch.

## 7. Tests (`tests/test_diagnosis_rules.py`, 15 tests, all passing)

Uses a deterministic hashed-bag-of-words fake embedding (no live-Ollama
dependency in the test suite) to exercise rule logic hermetically; the real
embedding's quality was validated separately in §3/§4 above.

1. Four reworded CancelledError diagnoses → one PENDING survivor, three
   SUPERSEDED naming it. **Load-bearing.**
2. SCP Permission-denied vs. SSH Connection-timed-out stay separate.
   **Load-bearing — Hazard C.**
3. An R2-rejected proposal redrafted next run (same narrow identity) is not
   re-drafted into PENDING. **Load-bearing — Hazard B.**
4. 403 against a third-party URL rejected; 404/500 against `.home.arpa`/RFC
   1918 hosts are not.
5. No rule produces `APPLIED`/`APPLYING` across four representative
   diagnoses (dup, third-party, redundant-resolution, novel). **Load-bearing
   — Hazard D.**
6. `dedup`/`demote`/`reverify`/`kb-fact` fingerprints byte-identical to the
   pre-this-spec formula (independently recomputed inline, same pattern as
   `test_gate_toil.py::test_6`), plus `apply_diagnosis_rules` leaves
   non-`diagnosis` proposals completely untouched (no `_initial_state` key
   added at all). **Load-bearing — Hazard F.**
7. Each rule individually disableable (4 tests: disable r1 only, r2 only,
   r3 only, all three — the last restores exactly today's/pre-spec
   behavior).
8. `scripts/dry-run-diagnosis-rules.py` writes nothing — proven by
   byte-identical database file content before and after, not just "no
   error was raised."

## 8. Hazard C / Hazard F guards proven to fail red, then restored

Per spec §6's closing instruction, both load-bearing guards were
deliberately broken, confirmed red, and restored — hash-verified
byte-identical to the pre-break file content, not just "tests pass again":

**Hazard C** — `tools/diagnosis_rules.py`'s `DIAGNOSIS_DUP_THRESHOLD_DEFAULT`
set to `0.0` (always merges):
```
FAILED tests/test_diagnosis_rules.py::TestDistinctFailuresStaySeparate::test_2_permission_denied_vs_connection_timed_out_stay_separate
AssertionError: assert 'SUPERSEDED' == 'PENDING'
```
Restored; `sha256sum` of `tools/diagnosis_rules.py` before-break and
after-restore identical
(`2381b126550bc938947f9e116aac29f23857af9f2ba9ca3826b50cc4ebbdba55`); test 2
green again.

**Hazard F** — `tools/traum_state.py`'s `_NARROW_IDENTITY_TYPES` temporarily
widened to `{"diagnosis", "dedup"}`:
```
FAILED tests/test_diagnosis_rules.py::...test_6_fingerprint_byte_identical_to_pre_spec_formula[dedup]
AssertionError: assert 'c0296031c6fb...' == 'a410b2574a73...'
```
(`demote`/`reverify`/`kb-fact` stayed green throughout, as expected — the
regression was scoped exactly to the type I widened.) Restored; `sha256sum`
of `tools/traum_state.py` before-break and after-restore identical
(`d41d46af96b96e288bd8a3cde3be3dd45435449a4f212d89988e717aaa168d76`); full
`TestOtherProposalTypesUntouched` class green again.

## 9. Invariants

```
/home/sy5/owui/bin/python3 -m py_compile tools/traum_state.py tools/dream_runner.py tools/diagnosis_rules.py scripts/dry-run-diagnosis-rules.py tests/test_diagnosis_rules.py
# -> clean

/home/sy5/miniforge3/bin/ruff check tools/traum_state.py tools/dream_runner.py tools/diagnosis_rules.py scripts/dry-run-diagnosis-rules.py tests/test_diagnosis_rules.py
# -> 22 errors: 4 in traum_state.py, 18 in dream_runner.py (both pre-existing,
#    byte-for-byte the same baseline count measured before this change);
#    0 in the three new files.

pgrep -af pytest   # confirmed empty (via ps aux | grep '[p]ytest' -- pgrep
                    # self-matches its own invocation, see goethe_mcp docs)
nohup /home/sy5/owui/bin/python3 -m pytest tests/ -q > /tmp/pt.log 2>&1 & disown
# baseline (before this change):  859 passed, 0 skipped, 123.69s
# after (with this change):       874 passed, 0 skipped, 123.97s (re-run after
#                                  the Hazard C/F break-restore cycle, to
#                                  confirm no residual state)
```

## 10. Anti-goals honored

No new proposal state or type. No rule ever approves/applies (§5, §8
proven). No rule scope beyond `diagnosis` (§7's Hazard-F tests prove
`dedup`/`demote`/`reverify`/`kb-fact` untouched). 0.92/0.82 independently
calibrated against live data, not inherited (§3). The three pre-existing
rules (`incomplete_budget_truncation`, malformed-shape,
`target_changed_since_generation`) are unmodified — `apply_diagnosis_rules`
runs strictly before the `cfg.budget.truncated` overwrite, so a truncated
run still unconditionally wins exactly as before. §2's mixed-cluster
behavior reported, not fixed (§5). `SPEC-diagnosis-probe-2026-08` untouched.
`tools/goethe_mcp.py` untouched (not even read for content — only its
presence as an untracked/pre-existing working-tree file was noted via `git
status`, never opened). Not pushed.

## 11. Known pre-existing, unrelated working-tree state

`git status --porcelain` after this commit still shows
`tools/goethe_mcp.py.bak.2026-08-11` and `tools/voicebox-tts-proxy.py` as
untracked — both pre-existing on `codex/fix-sudo-grants-live` before this
session started, not staged or touched by this commit (same situation prior
reports on this branch have flagged).

<!-- ACCEPTANCE
task: auto-adjudication
commit: 4a1c549
tests_before: 859
tests_after: 874
files_changed: tools/diagnosis_rules.py, scripts/dry-run-diagnosis-rules.py, tests/test_diagnosis_rules.py, tools/dream_runner.py, tools/traum_state.py
ruff_clean: tools/diagnosis_rules.py, scripts/dry-run-diagnosis-rules.py, tests/test_diagnosis_rules.py
runtime_verified: false
-->
