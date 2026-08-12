# 2026-08-12 — skill-feedback fork, TRAUM loop audit, QC critic, sudo grant fix

> Autonomous 3-part session, run to completion per operator instruction
> ("run all 3 parts autonomously", "re-verify everything myself"). Ground
> truth per AGENTS.md §9: every claim below was measured this session, not
> carried forward from a prior session's report.

## Part 1 — skill feedback loop fork, resolved

Full writeup: `docs/reports/2026-08-12-skill-feedback-loop-fork.md`.

The brief posed two candidate explanations for the dead skill-feedback loop:
(a) the `.keyword` query fix landed but is not yet proven live, or (b)
nothing ever calls `skill_outcome`/`skill_search`/`skill_record` at all.
Neither was quite right. Measured against the episode corpus
(2026-07-11→2026-08-09): **27 real `skill_outcome` invocations exist** —
this is not a dead caller. The ES index `lse-skills-1024` was created
2026-07-15T13:45:03, after 9 of those 27 calls, explaining their
non-persistence independent of any query bug. The `.keyword` fix (`95ca984`,
2026-08-09T20:41:48) is correct in source, verified directly against ES —
but a call 41 minutes later for a skill_id that demonstrably exists in the
index still failed "not found," pointing to a stale gateway process
(AGENTS.md §7) as the live-but-unproven remaining cause, not a code defect.
`docs/ROADMAP-2026-08.md` item 2 corrected accordingly — "nothing calls it"
was the wrong diagnosis.

## Part 2B — TRAUM loop audit (ground-truth health check)

`scripts/traum-loop-audit.py` + `tests/test_traum_loop_audit.py` (16 tests).
Pure measurement, no LLM: skill retrieval, outcome recording, KB
consultation, dream-loop completion, and `lse-skills` index health, each a
cheap yes/no check against episode logs / traum-state.db (opened
`?mode=ro`) / Elasticsearch. Live 3-day run correctly reproduces Part 1's
finding: skill retrieval ✅, KB consultation ✅, dream loop completion ✅,
but outcome recording ❌ (1 attempted / 0 succeeded / 1 errored — "not
found") and the skills index ❌ (0/25 skills with any recorded outcome) —
this script is now the standing, re-runnable proof of Part 1's finding
rather than a one-off measurement.

## Part 2A — QC critic (adversarial pre-human review)

`tools/qc_critic.py` + `tests/test_qc_critic.py` (17 tests) +
`scripts/calibrate-qc-critic.py`. Full calibration writeup:
`docs/reports/2026-08-12-qc-critic-calibration.md`.

Complements the mechanical R1/R2/R3 diagnosis-adjudication rules with an
LLM judgement call, scoped to flag/advise only (Hazard D: no code path can
approve or apply — grep-proven by `test_module_has_no_write_path`, which
checks the actual source rather than trusting the docstring). Every
failure mode (parse error, LLM cascade error, exception, missing reason)
fails open to `keep`. First prompt was measured uninformative (0/16/0
keep/needs_work/reject on the live 16-proposal calibration set — a
textbook "find flaws" prompt anti-pattern); rewritten to enumerate four
named failure shapes and default to `keep`, re-measured discriminating
(12/4/0). On the one case that actually matters — the `raspberrypi.com`
403 proposal R2 is currently disabled over — the critic reaches the
human's APPLIED conclusion unprompted. Shipped **disabled by default,
dry-run only**, per the calibration report's recommendation, until it has
been watched fire on a live PENDING queue.

## Part 3 — sudo grant-honoring path widened

`d4d59ba` fixed the grant-*filing* path to locate a privilege token
anywhere in a compound line. The grant-*honoring* path was never widened
to match: an approved grant for a compound line's atom (e.g. `cd /proj &&
sudo systemctl restart x`) was still permanently blocked, because the
honoring check required `command.strip().startswith("sudo ")` with no
shell metacharacter anywhere in the rest of the line. Fixed by extracting
the token-location scan and the shell-free-atom extraction into two
helpers (`_priv_token_hits`, `_shell_free_atom_after`) shared by both the
filing and honoring paths, then widening honoring to require a grant for
**every** privilege-token atom on the line — one granted atom never
vouches for a second, ungranted sudo elsewhere on the same line. `
check_sudo`'s exact-argv-equality contract, the exempt-set regex, and the
cwd-allowlist guard are all byte-for-byte unchanged (`goethe_perms.py` was
not touched at all). 9 new adversarial tests in
`tests/test_safety_gates_adversarial.py`, including the required
ungranted-sibling case. Break/red/restore proof: reverting the fix turns
exactly the 4 fix-dependent tests red while the 5 guard/regression tests
stay green; restored and re-verified before committing.

---

<!-- ACCEPTANCE
task: skill-feedback-loop-fork
commit: (docs only, folded into traum-loop-audit commit below)
tests_before: 878
tests_after: 878
files_changed: docs/reports/2026-08-12-skill-feedback-loop-fork.md, docs/ROADMAP-2026-08.md
ruff_clean: n/a (docs only)
runtime_verified: true
-->

<!-- ACCEPTANCE
task: traum-loop-audit
commit: 12a088e
tests_before: 878
tests_after: 894
files_changed: scripts/traum-loop-audit.py, tests/test_traum_loop_audit.py, docs/reports/2026-08-12-skill-feedback-loop-fork.md, docs/ROADMAP-2026-08.md
ruff_clean: scripts/traum-loop-audit.py, tests/test_traum_loop_audit.py
runtime_verified: true
-->

<!-- ACCEPTANCE
task: qc-critic
commit: b18399d
tests_before: 894
tests_after: 911
files_changed: tools/qc_critic.py, tests/test_qc_critic.py, scripts/calibrate-qc-critic.py, docs/reports/2026-08-12-qc-critic-calibration.md, docs/reports/2026-08-12-qc-critic-calibration-logs/v1-uninformative.log, docs/reports/2026-08-12-qc-critic-calibration-logs/v2-discriminating.log
ruff_clean: tools/qc_critic.py, tests/test_qc_critic.py, scripts/calibrate-qc-critic.py
runtime_verified: true
-->

<!-- ACCEPTANCE
task: sudo-grant-honoring-fix
commit: 2a0d73a
tests_before: 911
tests_after: 920
files_changed: tools/goethe.py, tests/test_safety_gates_adversarial.py, tests/test_goethe_perms.py
ruff_clean: tools/goethe.py, tests/test_safety_gates_adversarial.py
runtime_verified: true
-->
