# 05 — Milestone Plan (M0 … M6)

**Objective:** move the fundability score from **41 → 85+** (`04`), crossing the
threshold at M4.

**Effort units:** *Qwen-day* = one working day of Qwen3.8 (local, free, high-volume,
mechanical). *Sonnet-day* = one working day of Sonnet5 (cloud, metered, judgment).
Routing rules in `06`.

**Ordering rule:** strictly risk-reducing. **No milestone depends on a later one.**
Verified below.

**Exit criteria are verbatim-runnable.** Each is the exact command and the exact expected
output pattern. A milestone is not done because it looks done; it is done because the
command printed the pattern and the raw output is in the KB (`07`).

---

## Dependency graph

```
M0 canonicalisation + safety net   ── no deps
 ├─► M1 docs, CI hardening, releases          (needs M0's CI skeleton)
 ├─► M2 drift detector + version SSoT         (needs M0's CI + M1's doc cleanup)
 │    └─► M3 security + epistemics hardening  (needs M2: no silent drift while guards change)
 │         └─► M4 eval consolidation + baselines + TRAUM efficacy   ← FUNDABLE HERE
 │              └─► M5 demo + metrics + packaging
 │                   └─► M6 narrative + funding package
 └─► (KB decision, §KB below, resolved IN M0, consumed by M2 and by 07)
```

---

## The KB unification decision — resolved here, sequenced as an M0 deliverable

The brief requires this be chosen, justified, and made a milestone dependency rather than
left dangling.

**Decision: DO NOT MERGE. Single-writer tracker on node4090; node3090 stays
memory-independent; the divergence becomes an instrumented metric.**

### Justification

1. **Merging would destroy the thing being sold.** `02` §7 scores two-machine sovereignty
   on the demonstration that each instance carries *its own local memory*. A merged,
   replicated KB turns Goethe into a client of a central knowledge service — which is
   architecturally ordinary and contradicts the sovereignty claim. The 6.3× divergence is
   not a bug in the product story; it is the product story, badly instrumented.
2. **The tracker needs one writer, not one KB.** `07`'s requirement is that program state
   have a single source of truth. That is satisfied by declaring **node4090's `lse-kb` the
   sole tracker KB**. node3090 never holds `MILESTONE-*` or `TASK-*` docs. No merge needed.
3. **The 45 documents on node3090 are not valuable content.** They are an
   under-populated instance, not a second corpus worth reconciling. Merging would import
   near-duplicates into a 282-doc KB and trigger exactly the dedup work TRAUM exists to do.
4. **One part of the divergence *is* a defect and must be fixed separately.**
   `lse-errors` = **1 document** on node3090 (`03` P1-11) makes `check_error_kb` a no-op
   there. That is not sovereignty; that is a broken index. Seed it — one-way, once, from
   A's 82 — and then let it diverge again.

### What ships as a result

| deliverable | milestone |
|---|---|
| `docs/KB-TOPOLOGY.md` — declares node4090 `lse-kb` = tracker KB (single writer); node3090 = memory-independent instance | **M0** |
| One-way seed of `lse-errors` A→B, recorded as a one-off with a manifest | **M0** |
| `scripts/kb_parity.py` — reports per-index doc counts, quality distribution, quarantine counts across both instances | **M5** (metrics) |
| `07` tracker specified for **single-KB operation**, with a parity check as a health signal | **M2** onward |

**This decision is a hard dependency of M2 and of `07`.** Nothing writes tracker docs
until `docs/KB-TOPOLOGY.md` is merged and the KB has a backup (M0).

---

# M0 — Canonicalisation + safety net

> **Before any refactor. Nothing in this milestone changes behaviour.**

**Moves:** Provenance 15 → 70 · **the single highest-leverage milestone in the plan.**

**Scope (files touched):** `PROVENANCE.md` (new), `.github/workflows/ci.yml` (new),
`pyproject.toml`, `scripts/corpus_manifest.py` (new), `scripts/bootstrap.sh` (new),
`docs/KB-TOPOLOGY.md` (new), `lse/` (git remote), `.gitignore`, `EVIDENCE-MANIFEST.md`
(new), `lse/services/*.timer` (backup units), `tests/test_gateway_pin.py` (extend).

### Tasks

| id | task | owner |
|---|---|---|
| M0-1 | Push `lse/` to a remote (or vendor as subtree — decide and record) | Sonnet5 (decision) → Qwen3.8 (execution) |
| M0-2 | Pin the deployed gateway: copy `/mnt/c/…/Scripts/goethe_mcp.py` + `start-goethe-safe.sh` into the repo under `deploy/`, extend `tests/test_gateway_pin.py` to assert the running sha matches | Sonnet5 |
| M0-3 | Write `PROVENANCE.md` — canonical repo, canonical branch, deployed artifact, status of every other tree | Sonnet5 |
| M0-4 | Declare the canonical branch and merge/retire the 7 unpushed local branches | Sonnet5 |
| M0-5 | `pyproject.toml` `[project]` + pinned deps + lockfile; delete the docstring pin at `goethe.py:6` | Qwen3.8 |
| M0-6 | `.github/workflows/ci.yml` — lint + test jobs (drift job lands in M2) | Qwen3.8 |
| M0-7 | `scripts/corpus_manifest.py --generate/--verify` over tracked code **and** declared data stores | Qwen3.8 |
| M0-8 | `scripts/bootstrap.sh` — clean-VM clone → deps → services → health check | Qwen3.8 |
| M0-9 | Backup policy: ES snapshot repo + nightly SQLite `.backup` + episode rotation, as tracked systemd units | Qwen3.8 |
| M0-10 | Corpus B: `git clone` the remote onto node3090 **or** freeze it with `EVIDENCE-MANIFEST.md` (hashes + mtimes + "frozen evidence" status). Recommend: clone, so B stops being a provenance hole. Rescue the T0/T1 suite + v2 gold sets into the repo first. | Sonnet5 (decide) → Qwen3.8 |
| M0-11 | `docs/KB-TOPOLOGY.md` + one-way `lse-errors` seed A→B | Sonnet5 |
| M0-12 | Rotate the credential found in `agent_commands.log` and confirm in writing | **human** |

### Exit criteria — verbatim

```bash
# E0.1 — lse/ has a remote
$ git -C lse remote -v
# EXPECT: at least one line matching '^origin\s+\S+\s+\(fetch\)$'   (currently: empty)

# E0.2 — the running gateway is a tracked artifact
$ python3 -m pytest tests/test_gateway_pin.py -q
# EXPECT: '1 passed' (or more), 0 failed

# E0.3 — one-line answer exists
$ head -1 PROVENANCE.md
# EXPECT: matches '^Canonical: https://github\.com/sy5tem55/local-system-engineer(\.git)? @ \S+$'

# E0.4 — every tree accounted for
$ grep -cE '^\| *(canonical|vendored|frozen-evidence|retired) *\|' PROVENANCE.md
# EXPECT: >= 4   (local-system-engineer, lse/, Goethe3.0, node3090)

# E0.5 — deps installable from the manifest alone
$ python3 -m venv /tmp/v && /tmp/v/bin/pip install -e . -q && /tmp/v/bin/python -c "import elasticsearch, requests, pydantic; print('DEPS OK')"
# EXPECT: 'DEPS OK'

# E0.6 — CI exists and is green on the canonical branch
$ gh run list --workflow=ci.yml --branch master --limit 1 --json conclusion -q '.[0].conclusion'
# EXPECT: 'success'

# E0.7 — fresh clone reproduces the tool surface (the milestone's headline)
$ bash scripts/bootstrap.sh --clean-vm && curl -s -H "Authorization: Bearer $GOETHE_MCP_TOKEN" localhost:9700/mcp -d '{"method":"tools/list"}' | python3 -c "import sys,json; print('TOOLS', len(json.load(sys.stdin)['result']['tools']))"
# EXPECT: 'TOOLS 44'    (44 verified by AST count of public Tools methods; assert exact)

# E0.8 — corpus manifest verifies
$ python3 scripts/corpus_manifest.py --verify && echo MANIFEST_OK
# EXPECT: 'MANIFEST_OK'

# E0.9 — corpus B provably clone-or-frozen
$ ssh node3090.home.arpa 'git -C /home/lse-admin/projects/local-system-engineer rev-parse HEAD'
# EXPECT: a 40-hex sha   OR, if frozen: EVIDENCE-MANIFEST.md verifies:
$ python3 scripts/corpus_manifest.py --verify --host node3090 && echo B_FROZEN_OK

# E0.10 — backups actually run and restore
$ systemctl list-timers --all | grep -E 'goethe-backup'
# EXPECT: a line with an ACTIVATES column and a future NEXT
$ bash scripts/restore_drill.sh --dry-run && echo RESTORE_DRILL_OK
# EXPECT: 'RESTORE_DRILL_OK'

# E0.11 — the KB decision is merged
$ test -f docs/KB-TOPOLOGY.md && grep -q 'tracker KB: node4090 lse-kb (single writer)' docs/KB-TOPOLOGY.md && echo KB_DECISION_OK

# E0.12 — node3090's error index is no longer a no-op
$ ssh node3090.home.arpa 'curl -s localhost:9200/lse-errors-1024/_count'
# EXPECT: '"count":' followed by a number >= 50   (currently: 1)
```

**Effort:** 6 Qwen-days · 3 Sonnet-days · 0.5 human-days
**Risk:** low — nothing changes agent behaviour.
**Rollback:** every task is additive; `git revert` per commit. The only destructive option
is M0-10's clone over node3090's tree — **take a full tar of `/home/lse-admin/projects`
first and verify it before touching anything** (that tree holds the only copy of the T0/T1
suite; rescue it into the repo in a separate, earlier commit).
**Fundable criterion moved most:** **B (Provenance), 15 → 70.**

---

# M1 — Documentation, CI hardening, release discipline

**Moves:** Docs 45 → 80 · Code integrity 25 → 70

**Scope:** `README.md`, `CHANGELOG.md`, `LICENSE` (review only), `docs/README.md` (new),
`LSE-ARCHITECTURE.md`, `.github/workflows/ci.yml`, `pyproject.toml`, git tags.

### Tasks

| id | task | owner |
|---|---|---|
| M1-1 | README: one H1; generated version block; a quickstart that ends in a running instance; lead with the memory claim, not "AI Sysadmin" | Sonnet5 (positioning) → Qwen3.8 (mechanics) |
| M1-2 | `CHANGELOG.md` → Keep-a-Changelog sections mapped to tags; **archive the 224 KB narrative to `docs/CHANGELOG-ARCHIVE.md`** rather than deleting it — it is real provenance evidence | Qwen3.8 |
| M1-3 | Tag every historical release that has a CHANGELOG section; tag current as `v0.4.9` | Qwen3.8 |
| M1-4 | `docs/README.md` index over the 80+ docs; promote `threat-model-kb.md`, `07-operations-runbook.md`, `TRAUM-OPERATOR-MANUAL.md` into the README | Qwen3.8 |
| M1-5 | Refresh `LSE-ARCHITECTURE.md` for the mixin layout and TRAUM's true 8-file / 13,260-LOC shape | Sonnet5 |
| M1-6 | Update `docs/threat-model-kb.md`: mark the origin-tagging finding **closed** (`goethe_kb.py:502`) — a reviewer currently finds it open | Sonnet5 |
| M1-7 | CI: add coverage with `--cov-fail-under=70`; add `mypy` non-strict as non-blocking, then ratchet | Qwen3.8 |
| M1-8 | CI: assert tool count == 44 and README version == `goethe.py:3` | Qwen3.8 |
| M1-9 | Fix `tools/node_facts.py:405` hardcoded Windows path → valve with documented default | Qwen3.8 |

### Exit criteria — verbatim

```bash
# E1.1 — README self-consistent with code
$ python3 scripts/check_version_drift.py --docs-only && echo DOCS_VERSION_OK
# EXPECT: 'DOCS_VERSION_OK'   (currently README:50 says v0.2.5, README:191 says v0.4.0-a, code says v0.4.9)

# E1.2 — exactly one H1 in README
$ grep -c '^# ' README.md
# EXPECT: '1'   (currently: 2)

# E1.3 — releases are tagged
$ git tag -l | wc -l
# EXPECT: >= 10   (currently: 0)
$ git tag -l | grep -c '^v0\.4\.9$'
# EXPECT: '1'

# E1.4 — coverage floor enforced
$ python3 -m pytest tests/ --cov=tools --cov-fail-under=70 -q 2>&1 | tail -2
# EXPECT: 'Required test coverage of 70% reached' AND '0 failed'

# E1.5 — the hardcoded-path failures are gone
$ python3 -m pytest tests/test_node_facts.py -q --no-header
# EXPECT: '0 failed'   (currently: 4 failed with FileNotFoundError '/mnt/c/Goethe3.0/…')

# E1.6 — docs are navigable
$ test -f docs/README.md && grep -c '\](\./' docs/README.md
# EXPECT: >= 40

# E1.7 — tool count asserted
$ python3 -m pytest tests/test_tool_surface.py -q
# EXPECT: '0 failed'
```

**Effort:** 5 Qwen-days · 2 Sonnet-days
**Risk:** low. **Rollback:** `git revert`; M1-9 is the only behaviour change (guarded by
its own test).
**Fundable criterion moved most:** **C (Documentation), 45 → 80.**

---

# M2 — Drift detector + version single-source-of-truth

**Moves:** Code integrity 70 → 85 · closes P0-6 permanently

**Depends on:** M0 (CI skeleton), M1 (docs must be correct before a gate freezes them),
KB decision (M0-11).

**Scope:** `scripts/check_version_drift.py` (new), `prompts/DEPLOYED.toml` (new),
`.github/workflows/ci.yml`, `tests/test_version_drift.py` (new),
`scripts/live_prompt_check.sh` (new).

### Design (full wiring specified in `03` P0-6)

Three extractors — **code** (authoritative), **deployed prompt templates** (named in
`prompts/DEPLOYED.toml`, so the 42 historical templates cannot fail the build), **docs** —
one comparison, exit 1 on any mismatch. Five distinct failure messages, including the
per-instance class ("two deployed templates disagree with each other").

Plus a **live extension** the CI cannot run (it cannot see the boxes) and the Qwen tracker
runs at session start (`07` §5): `ssh <host> sha256sum <deployed prompt>` vs the tracked
template hash, catching a hand-edited prompt on a live instance.

### Exit criteria — verbatim

```bash
# E2.1 — detector passes on a correct tree
$ python3 scripts/check_version_drift.py --strict && echo DRIFT_NONE
# EXPECT: 'DRIFT_NONE'

# E2.2 — detector CATCHES the historical failure (negative test — the important one)
$ git stash && sed -i 's/goethe_mcp v1\.13\.0/goethe_mcp v1.11.2/' prompts/v0.6.2.md
$ python3 scripts/check_version_drift.py --strict; echo "EXIT=$?"
# EXPECT: 'EXIT=1' AND stderr matching 'DRIFT: prompts/v0\.6\.2\.md claims goethe_mcp v1\.11\.2, code is v1\.13\.0'
$ git checkout prompts/v0.6.2.md && git stash pop

# E2.3 — detector catches the PER-INSTANCE class (two prompts disagreeing)
$ python3 -m pytest tests/test_version_drift.py::test_two_deployed_prompts_disagree -q
# EXPECT: '1 passed'

# E2.4 — CI job wired and blocking
$ gh api repos/:owner/:repo/actions/workflows/ci.yml --jq '.state'
# EXPECT: 'active'
$ grep -c 'check_version_drift' .github/workflows/ci.yml
# EXPECT: >= 1

# E2.5 — deployed-template manifest exists and resolves
$ python3 -c "import tomllib;d=tomllib.load(open('prompts/DEPLOYED.toml','rb'));import os;print('MANIFEST_OK' if all(os.path.exists('prompts/'+v) for v in d.values()) else 'BROKEN')"
# EXPECT: 'MANIFEST_OK'

# E2.6 — live drift check across both instances
$ bash scripts/live_prompt_check.sh
# EXPECT: 'node4090 prompt sha MATCH' AND 'node3090 prompt sha MATCH'
```

**Effort:** 3 Qwen-days · 1 Sonnet-day
**Risk:** low-moderate — the detector will initially fail on 19 real drift sites; that is
the point. Land it non-blocking for one week, fix the sites, then flip to blocking.
**Rollback:** set the CI job to `continue-on-error: true`.
**Fundable criterion moved most:** **A (Code integrity), 70 → 85**, and it makes P0-6
structurally impossible to recur — the thing two prior docs passes failed to achieve.

---

# M3 — Security + epistemics hardening

**Moves:** Security 50 → 82 · **and it upgrades the moat itself** (`02` §1: 7 → 9)

**Depends on:** M2 (guards must not be changed while drift can go unnoticed).

**Scope:** `tools/goethe_kb.py`, `tools/goethe.py`, `tools/goethe_web.py`,
`tools/goethe_mcp.py`, `tools/goethe_netsec.py`, `docs/security.md` (new),
`docs/threat-model-kb.md`, new contract tests.

### Tasks

| id | task | owner | why |
|---|---|---|---|
| M3-1 | **Evidence provenance**: require the `evidence` string to be a substring of a result the current session actually received, read from the episode journal. Replaces `len(evidence) >= 20` at `goethe_kb.py:935`, `:1132`, `dream_apply.py:384`. | **Sonnet5** | `03` P1-2. Turns a length check into a provenance proof, using infrastructure that already exists. **The single highest-value item in the plan.** |
| M3-2 | **Argv execution path**: allowlisted, shell-free `execute_command` mode as the default for common operations; `shell=True` becomes a flagged escape hatch logged at a distinct level. Pattern already proven by `assert_state` (`goethe.py:1980`). | **Sonnet5** | `03` P1-1 |
| M3-3 | **KB-FIRST becomes a code gate**: session flag set by `search_kb`, checked by `search_web`, refusal naming the missing call. Shape already proven by `_budget_gate` in the same file. | Qwen3.8 | `03` P1-3 |
| M3-4 | **`active-task.md` guard**: `planner()` refuses to start while an unregistered `*task*.md` exists under `/opt/local-se/`, naming the file. | Qwen3.8 | `03` P1-4 — converts the project's most embarrassing artifact into a demo of the ratchet |
| M3-5 | **SSH audit coverage**: log every `ssh_run`/`ssh_script` with host, user, redacted command. Currently 3 log sites on the highest-privilege path. | Qwen3.8 | `03` P1-7 |
| M3-6 | **One secret resolution order**: `docs/security.md`; delete the other two paths; move secrets to Vaultwarden handles where possible. | Sonnet5 | `03` P1-14 |
| M3-7 | Secret-scanning in CI (`gitleaks`) over tree **and** a redacted log sample | Qwen3.8 | `03` P1-14 / D3 |
| M3-8 | External security review pass, written sign-off | **human** (external) | D5 |

### Exit criteria — verbatim

```bash
# E3.1 — fabricated evidence is REFUSED (the headline)
$ python3 -m pytest tests/test_evidence_provenance.py -q
# EXPECT: '0 failed'
# and specifically, this must hold:
$ python3 -c "
from tools.goethe import Tools; t=Tools()
print(t.record_outcome(doc_id='<seeded>', success=False, evidence='aaaaaaaaaaaaaaaaaaaaaaaaaaaa'))"
# EXPECT: output containing 'NOT demoted' AND 'evidence not found in this session'
#         (today this string DEMOTES the document)

# E3.2 — argv path is default, shell path is flagged and logged
$ python3 -m pytest tests/test_argv_execution.py -q
# EXPECT: '0 failed'
$ grep -c 'SHELL-ESCAPE' /opt/local-se/agent_commands.log
# EXPECT: a number (tag exists)

# E3.3 — KB-FIRST is enforced, not exhorted
$ python3 -c "
from tools.goethe import Tools; t=Tools()
print(t.search_web('anything'))"
# EXPECT: output starting 'KB-FIRST GATE:' and naming search_kb
#         (today this executes the search)

# E3.4 — the in-vivo breach cannot recur
$ touch /opt/local-se/scratch-task.md
$ python3 -c "from tools.goethe import Tools; print(Tools().planner('x'))"
# EXPECT: output containing 'PROTOCOL: unregistered tracking file' AND '/opt/local-se/scratch-task.md'
$ rm /opt/local-se/scratch-task.md

# E3.5 — SSH is audited
$ grep -cE '^\S+ \S+ SSH(-RUN|-SCRIPT)' /opt/local-se/agent_commands.log
# EXPECT: a count that increases by exactly 1 after one ssh_run call

# E3.6 — no secrets anywhere
$ gitleaks detect --no-banner --exit-code 1 && echo GITLEAKS_CLEAN
# EXPECT: 'GITLEAKS_CLEAN'

# E3.7 — one documented secret path
$ grep -c 'resolution order' docs/security.md
# EXPECT: '1'
$ grep -rn 'lse/secrets' --include='*.sh' --include='*.py' tools/ | wc -l
# EXPECT: a number, and every hit resolves to the SAME path (assert in test)

# E3.8 — external review
$ test -f docs/security-review-2026.md && grep -q 'Reviewer:' docs/security-review-2026.md && echo REVIEW_SIGNED
```

**Effort:** 6 Qwen-days · 8 Sonnet-days · external reviewer
**Risk:** **HIGH — this milestone changes guard behaviour on a live system.**
**Rollback:** every change behind a valve defaulting to the *old* behaviour for one week
(`EVIDENCE_PROVENANCE_ENFORCE=warn|block`, `EXEC_MODE=shell|argv`,
`KB_FIRST_GATE=warn|block`). Ship in `warn` mode, read the audit log for a week, then
flip. Never flip two at once.
**Fundable criterion moved most:** **D (Security), 50 → 82** — and `02` §1 from 7 to 9,
which is the only milestone that raises a *moat* score rather than a readiness score.

---

# M4 — Eval consolidation, regression baselines, TRAUM efficacy · **← FUNDABLE HERE**

**Moves:** Evaluation 48 → 85 → **total crosses 80**

**Depends on:** M3 (do not baseline behaviour that is about to change).

**Scope:** `eval/`, `tests/`, `.github/workflows/ci.yml`, `eval/baselines/` (new),
`docs/eval-methodology.md` (new).

### Tasks

| id | task | owner |
|---|---|---|
| M4-1 | Bring the T0/T1 behavioural suite into the repo from node3090 (`run_t0t1_suite.py`, `t1_feedback_loop.py`, `t1_mcp_harness.py`) + the v2 gold sets; add `.gitignore` carve-outs | Qwen3.8 |
| M4-2 | Merge the two disjoint suites into one behavioural suite with a single runner | Sonnet5 |
| M4-3 | **ES service container in CI** so the 98 skipped `test_kb_contracts.py` tests execute — the moat is currently unverified by construction | Qwen3.8 |
| M4-4 | Fix the remaining fresh-clone failures (`test_prove_it.py` ×3, `test_goethe_perms.py` ×1, `test_cycle_completes.py` ×1); mark genuinely env-coupled ones `@pytest.mark.integration` | Qwen3.8 |
| M4-5 | `eval/baselines/<version>.json` per release; CI diffs current vs baseline and fails on regression beyond tolerance | Qwen3.8 |
| M4-6 | **TRAUM efficacy eval, properly powered**: fix the three defects the team already diagnosed in `eval-report-traum-1.md` §6–7 — n>1, pinned sampling, and a *real* pre-dreaming ES snapshot (now possible, since M0-9 configured a snapshot repo) | **Sonnet5** |
| M4-7 | `docs/eval-methodology.md` — pre-registration protocol, so the next result is credible before it is known | Sonnet5 |
| M4-8 | Make TRAUM runnable in CI against a disposable ES (removes the N=1 risk, `03` P2-11) | Qwen3.8 |

**Note on M4-6.** The prior A/B **lost** (A=53/60, B=51/60) and was published as a loss.
The re-run may lose again. That is an acceptable and even a good outcome *if it is
properly powered* — a well-designed null result on a novel mechanism is publishable and is
honest grant material. What is not acceptable is shipping the n=1 result as the efficacy
claim. **Pre-register before running (M4-7 precedes M4-6).**

### Exit criteria — verbatim

```bash
# E4.1 — nothing skips silently
$ python3 -m pytest tests/ -q --no-header -rs 2>&1 | tail -1
# EXPECT: '0 failed' AND skip count == 0 for non-@integration tests
$ python3 -m pytest tests/ -q -rs 2>&1 | grep -c 'Elasticsearch not reachable'
# EXPECT: '0'    (currently: 98 skips from this one reason)

# E4.2 — full suite green in CI including KB contracts
$ gh run list --workflow=ci.yml --limit 1 --json conclusion -q '.[0].conclusion'
# EXPECT: 'success'
$ gh run view --log | grep -E '^\s*[0-9]+ passed'
# EXPECT: a number >= 920

# E4.3 — behavioural suite is in the repo and runs
$ git ls-files eval/ | grep -c 'run_t0t1_suite.py'
# EXPECT: '1'    (currently: 0 — it exists only on node3090)
$ python3 eval/run_t0t1_suite.py --dry-run && echo T0T1_OK

# E4.4 — baseline exists and regression is detected
$ test -f eval/baselines/v0.4.9.json && echo BASELINE_OK
$ python3 scripts/eval_regression.py --baseline eval/baselines/v0.4.9.json --current eval/latest.json
# EXPECT: 'NO REGRESSION' or an explicit delta table; exit 0

# E4.5 — TRAUM efficacy result exists, powered, pre-registered
$ test -f docs/eval-methodology.md && test -f eval/eval-report-traum-2.md
$ grep -E '^n *= *[0-9]+' eval/eval-report-traum-2.md
# EXPECT: n >= 5
$ grep -c 'pre-registered' eval/eval-report-traum-2.md
# EXPECT: >= 1
$ grep -E 'snapshot repo' eval/eval-report-traum-2.md
# EXPECT: a line confirming a REAL pre-dreaming snapshot was taken (the v1 defect)

# E4.6 — TRAUM runs off its home machine
$ gh run view --log | grep -c 'test_dream_engine'
# EXPECT: >= 1
```

**Effort:** 8 Qwen-days · 6 Sonnet-days
**Risk:** moderate — M4-6 may produce another null result. Mitigation: pre-register, and
plan the narrative for both outcomes (a powered null is still a stronger asset than an
unpowered loss).
**Rollback:** eval work is additive; baselines can be re-cut.
**Fundable criterion moved most:** **E (Evaluation), 48 → 85. This is the milestone that
crosses the fundability threshold (score ≈ 85).**

---

# M5 — Demo, metrics, packaging

**Moves:** Demo 10 → 85 · Metrics 35 → 85

**Depends on:** M4 (do not demo behaviour that has no baseline).

**Scope:** `scripts/demo.sh` (new), `fixtures/` (new), `scripts/audit_report.py` (new),
`scripts/kb_parity.py` (new), `lse/installer/`, `docs/07-operations-runbook.md`.

### Tasks

| id | task | owner |
|---|---|---|
| M5-1 | **10-minute demo on clean hardware, no homelab.** Must show the moat: seeded episodes → `dream_runner` proposes → proposal rendered → **human answers `n`** → KB unchanged → answers `y` → KB changed, with the CAS check visible. | Sonnet5 (script) → Qwen3.8 (fixtures) |
| M5-2 | `fixtures/` — a seeded ES + episode corpus, redacted, committed, so the demo is deterministic | Qwen3.8 |
| M5-3 | `scripts/audit_report.py` — parse `agent_commands.log` into the refusal taxonomy; emit the headline number | Qwen3.8 |
| M5-4 | KB health view: doc count, quality distribution, quarantine count, staleness, per index | Qwen3.8 |
| M5-5 | `scripts/kb_parity.py` — cross-instance divergence report (the KB decision's instrumentation) | Qwen3.8 |
| M5-6 | Inventory and document or drop `lse-rfc-kb` (628) and `lse-web-idx` (**45,415**) — `03` P1-10 | Sonnet5 |
| M5-7 | One-machine deploy script + packaging, promoted from `lse/installer/` | Qwen3.8 |

### Exit criteria — verbatim

```bash
# E5.1 — demo runs clean, in time, with no homelab
$ time bash scripts/demo.sh --clean 2>&1 | tail -5
# EXPECT: 'DEMO COMPLETE' AND real time < 10m0s AND no non-zero exit

# E5.2 — the demo actually shows the human gate refusing
$ bash scripts/demo.sh --clean --transcript /tmp/d.txt >/dev/null
$ grep -c 'KB UNCHANGED — proposal rejected at the human gate' /tmp/d.txt
# EXPECT: '1'
$ grep -c 'CAS check' /tmp/d.txt
# EXPECT: >= 1

# E5.3 — the headline metric is a command, not a claim
$ python3 scripts/audit_report.py --summary
# EXPECT: output matching 'refusals: [0-9]+ / commands: [0-9]+' with refusals >= 10000

# E5.4 — KB health visible
$ python3 scripts/audit_report.py --kb-health
# EXPECT: lines for lse-kb, lse-errors, lse-skills with count/mean-quality/quarantined

# E5.5 — cross-instance parity instrumented
$ python3 scripts/kb_parity.py
# EXPECT: a table with both hosts and a DIVERGENCE column

# E5.6 — no undocumented indices
$ python3 scripts/audit_report.py --index-inventory --strict && echo ALL_INDICES_DOCUMENTED
# EXPECT: 'ALL_INDICES_DOCUMENTED'   (today lse-web-idx @ 45,415 docs is undocumented)

# E5.7 — one-machine deploy
$ bash lse/installer/install.sh --dry-run && echo INSTALLER_OK
```

**Effort:** 7 Qwen-days · 3 Sonnet-days
**Risk:** low. **Rollback:** additive.
**Fundable criterion moved most:** **F (Demo-ability), 10 → 85.** In pure
meeting-conversion terms this is the highest-return milestone in the plan, which is why it
is worth the wait until the thing being demoed is baselined.

---

# M6 — Narrative and funding package

**Moves:** Narrative 0 → 90

**Depends on:** M5 (do not write the pitch before the demo exists — the demo determines
what the pitch can claim).

**Scope:** `09-onepager.md`, deck, `docs/positioning.md`.

### Tasks

| id | task | owner |
|---|---|---|
| M6-1 | One-pager from `02`'s narrative, refreshed with M4's efficacy result and M5's metric | **Sonnet5** |
| M6-2 | 5-slide outline (in `09`) | Sonnet5 |
| M6-3 | **Reposition**: lead with human-gated memory consolidation, not "AI Sysadmin". Sovereignty becomes a qualifier. | Sonnet5 |
| M6-4 | Precision pass on every conditional claim — e.g. "never auto-applies" → "not under the shipped configuration; `GOETHE_DREAM_AUTO_APPLY` is deliberately empty, decision recorded" | Sonnet5 |
| M6-5 | Publish the refusal taxonomy + a redacted dataset sample (first-mover on the benchmark, `02` §8b) | Sonnet5 |
| M6-6 | Grant-track variant: methods section from `docs/eval-methodology.md` | Sonnet5 |
| M6-7 | Human sign-off | **human** |

### Exit criteria — verbatim

```bash
# E6.1 — one-pager exists and is within budget
$ test -f 09-onepager.md && wc -w < 09-onepager.md
# EXPECT: <= 300 for the narrative section (assert on the section, not the file)

# E6.2 — every number in the one-pager is reproducible by a command in this plan
$ python3 scripts/verify_claims.py 09-onepager.md
# EXPECT: 'ALL CLAIMS VERIFIED (n=N)' with 0 unverified

# E6.3 — no unconditional claim where the code is conditional
$ grep -icE 'never (auto-)?appl|always|guarantee' 09-onepager.md
# EXPECT: '0'   (or each hit annotated with its condition — asserted by verify_claims.py)

# E6.4 — human sign-off recorded
$ grep -q 'Approved:' docs/positioning.md && echo SIGNED
```

**Effort:** 1 Qwen-day · 4 Sonnet-days · 1 human-day
**Risk:** low. **Rollback:** n/a.
**Fundable criterion moved most:** **I (Narrative), 0 → 90.**

---

## Mandatory-scope coverage check

The brief lists scope that must appear somewhere across the milestones. Mapping:

| required scope | where |
|---|---|
| README + CHANGELOG + LICENSE quality pass (improve, don't create) | M1-1, M1-2, H2 review in M1 |
| Test-suite expansion with coverage floor | M1-7 (floor), M4-3/4/8 (expansion) |
| Docstring/protocol extraction into standalone docs | M1-4, M1-5, M3-6 |
| The drift detector | **M2** (full wiring in `03` P0-6) |
| Core-module decomposition with behaviour-preserving gates | M1-9 + ongoing; gate = the 925-test contract suite, exactly as PH5-1/PH5-2 did it (`goethe_kb.py:3–15`) |
| Security review pass | M3-8 |
| Eval-suite expansion + regression tracking | M4-1…M4-5 |
| Reproducible demo + metrics dashboard | M5-1…M5-5 |
| Packaging + one-machine deploy script | M0-5, M0-8, M5-7 |
| Funding one-pager | M6-1 |
| **KB unification decision, sequenced** | **resolved above; ships in M0-11; consumed by M2 and `07`** |

---

## Totals

| milestone | Qwen-days | Sonnet-days | human-days | cumulative score |
|---|---|---|---|---|
| M0 | 6 | 3 | 0.5 | 41 → **58** |
| M1 | 5 | 2 | — | → **66** |
| M2 | 3 | 1 | — | → **71** |
| M3 | 6 | 8 | ext. review | → **78** |
| M4 | 8 | 6 | — | → **85** ← fundable |
| M5 | 7 | 3 | — | → **91** |
| M6 | 1 | 4 | 1 | → **94** |
| **total** | **36** | **27** | **~2.5 + review** | |

**~13 calendar weeks** at one milestone per 1.5–2 weeks with the two models working in
the parallelism `06` permits. The fundability threshold is crossed at **week 9–10**.

**Ordering sanity check:** M0 has no dependencies. M1→M0, M2→{M0,M1}, M3→M2, M4→M3,
M5→M4, M6→M5. **No milestone depends on a later one.** ✅
