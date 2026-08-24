# 07 — Qwen3.8 as KB Milestone Tracker

**Mandate:** the KB is the **single source of truth for program state**. Not a chat log,
not `ROADMAP.md`, not a hand-written task file. Qwen3.8 maintains it.

**Design constraint that shapes everything below:** this must be built from the system's
*own* primitives — `index_to_kb`, `search_kb`, `record_outcome`, `mentor_correct`,
`mentor_demote`, `kb_verify`, `task_checkpoint`, `task_resume`. No new datastore, no
sidecar file, no new schema engine. The program that improves Goethe is run *by* Goethe.
That is the strongest dogfooding argument available and it belongs in the funding
narrative.

**Two hard prerequisites from `05`:**
1. `docs/KB-TOPOLOGY.md` merged (M0-11) — **tracker KB = node4090 `lse-kb`, single
   writer.** node3090 never holds tracker docs. No merge; see `05` §KB.
2. KB backups live (M0-9). Nothing writes tracker state into an unbacked store.

**And one irony that must be stated:** `/opt/local-se/active-task.md` is a hand-written
tracking file that has been live for 44 days in violation of the protocol (`03` P1-4).
**Milestone M0 retires it, and this tracker is its replacement.** The first act of the
tracker is to make its own predecessor's failure mode impossible — M3-4 adds the guard.

---

## 1. Document schema

Two document types, both ordinary `lse-kb` documents so that every existing KB
mechanism — search, trust scoring, decay, quarantine, mentor override, the `[STALE]` and
`[EXPIRED]` banners — applies to program state for free.

### 1.1 `MILESTONE-M<n>: <name>`

Written with:

```python
index_to_kb(
    title        = "MILESTONE-M0: Canonicalisation + safety net",
    topic        = "program-state/milestone",
    content      = <the YAML block below>,
    source_tier  = "ground_truth",     # program state IS ground truth about ourselves
    origin       = "local-probe",      # required: ground_truth needs local-probe or human
    quality_score= 1.0,
    volatility   = "fast",             # so the TTL surfaces staleness aggressively
    evidence     = <verbatim output of the most recent exit-criteria run, >=50 chars>,
)
```

> **Why `origin="local-probe"` is mandatory here.** `TrustPolicy.apply_origin`
> (`goethe_kb.py:60–68`) auto-downgrades `origin="web"` away from `ground_truth`, and
> anything unrecognised is stored as `"unspecified"`. A milestone doc written without an
> origin cannot hold `ground_truth`. And `ground_truth` requires `evidence >= 50` chars
> (`goethe_kb.py:1559`) — so **the schema physically cannot hold a milestone doc with no
> evidence.** The tracker's integrity is enforced by the product's own gates.

`content` body:

```yaml
milestone:      M0
name:           Canonicalisation + safety net
status:         open | in_progress | blocked | done | abandoned
owner_model:    qwen3.8 | sonnet5 | mixed
depends_on:     []                       # milestone ids; MUST be a subset of earlier ids
exit_criteria:                           # VERBATIM from 05 — never paraphrased
  - id:      E0.1
    command: "git -C lse remote -v"
    expect:  "^origin\\s+\\S+\\s+\\(fetch\\)$"
    state:   pass | fail | not_run
    last_run: 2026-08-20T14:03:11+02:00
  - id:      E0.7
    command: "bash scripts/bootstrap.sh --clean-vm && curl -s ... | python3 -c '...'"
    expect:  "TOOLS 44"
    state:   not_run
    last_run: null
evidence_log:                            # append-only. NEVER edited, NEVER summarised.
  - at:        2026-08-20T14:03:11+02:00
    criterion: E0.1
    command:   "git -C lse remote -v"
    output: |
      origin	git@github.com:sy5tem55/lse-deploy.git (fetch)
      origin	git@github.com:sy5tem55/lse-deploy.git (push)
    verdict:   pass
blockers:
  - id:     BLK-M0-1
    what:   "M0-12 credential rotation requires the human"
    since:  2026-08-19
    owner:  human
last_verified:  2026-08-20T14:03:11+02:00
next_action:    "Run E0.7 on a clean VM"
fundable_criterion: "B (Provenance) 15 -> 70"
tasks:          [TASK-M0-1, TASK-M0-2, ...]
```

### 1.2 `TASK-M<n>-<k>: <title>`

Same write pattern, `topic = "program-state/task"`, `content` = **the `06` §2 task
contract verbatim**, plus:

```yaml
status:        open | in_progress | blocked | done | escalated | abandoned
attempts:      0                          # against max_iterations
evidence_log:  []                         # append-only, same shape as above
escalated_to:  sonnet5 | null
escalation_reason: null
bundle:        patch-TASK-M3-1            # if it crossed the air gap
last_verified: <ISO>
```

**One task, one document. One milestone, one document.** No sub-documents, no threads.
`search_kb("MILESTONE-M3")` must return exactly one authoritative answer.

### 1.3 Naming is load-bearing

Titles are prefixed `MILESTONE-` / `TASK-` so `search_kb` retrieves program state
distinctly from operational knowledge. `_resolve_kb_id()` (`goethe_kb.py:802`) accepts
either an id or a title, so **the human-readable title is a stable handle** — no doc-id
bookkeeping. Never reuse an id; an abandoned task stays `abandoned`, it is not recycled.

---

## 2. Update protocol

Executed by Qwen3.8 after every completed task. **The order is not negotiable.**

```
 1. CLAIM
    search_kb("TASK-M<n>-<k>")            → confirm status == open, blocked_by all done
    ── refuse if any other in_progress task shares an input_file  (this IS the lock, 06 §4)
    mentor_correct(doc_id, ... status: in_progress ...)
    ── set attempts += 1 in the same write

 2. WORK
    (the task)

 3. VERIFY  — run the exit-criteria command EXACTLY as written, capture raw stdout+stderr
    result = execute_command(<contract.acceptance_test.command>)

 4. RECORD EVIDENCE FIRST  — append verbatim output to evidence_log
    mentor_correct(doc_id, content=<content with evidence_log appended>,
                   evidence=<the raw output>)
    ── evidence is pasted, never summarised. >=20 chars, and after M3-1 it must be
       provably from a real tool result.

 5. FLIP STATUS ONLY ON PASS
    if expect matched and exit == expect_exit:
        status = done
        record_outcome(doc_id, success=True,
                       notes="acceptance criterion <id> passed")
    else:
        status stays in_progress
        record_outcome(doc_id, success=False, evidence=<raw failure output>)
        ── this DEMOTES the doc: quality = max(0.2, q-0.15)  (goethe_kb.py:936)
           A task that keeps failing visibly loses trust. That is the point.

 6. TOUCH THE PARENT
    mentor_correct("MILESTONE-M<n>", ... last_verified=now, next_action=<next> ...)
```

### Two consecutive failures → blocked + escalate

```
 if consecutive_failures >= 2  (read it off the doc — record_outcome maintains it,
                                goethe_kb.py:937):
     status = blocked
     blockers += {what: <the two verbatim failures>, owner: sonnet5}
     escalated_to = sonnet5
     escalation_reason = <one sentence>
     ── do NOT retry. Build the bundle (06 §3) and stop.
```

This reuses `consecutive_failures`, a field the KB already maintains for exactly this
purpose. No new counter.

### Using the KB's own primitives — the mapping

| tracker need | KB primitive | note |
|---|---|---|
| create a milestone/task doc | `index_to_kb(...)` | `source_tier=ground_truth`, `origin=local-probe`, `volatility=fast` |
| update status / append evidence | `mentor_correct(doc_id, ...)` | the tier-gated write; the only thing that can *raise* quality and clear quarantine |
| record a criterion pass/fail | `record_outcome(doc_id, success, evidence)` | maintains `empirical_runs`, `consecutive_failures`, and auto-demotes on evidenced failure |
| re-verify a criterion later | `kb_verify(doc_id, observed=<raw output>)` | two-phase regression probe; **auto-demotes on mismatch**, and rejects `observed < 20` chars (`:1132`) |
| retire a superseded plan doc | `mentor_demote(doc_id, 0.2, reason)` | human-authorised kill switch → quarantine |
| cross-session handoff | `task_checkpoint(...)` / `task_resume(...)` | §4 |
| find stale program state | `search_kb("MILESTONE-", ...)` | `volatility=fast` surfaces `[EXPIRED]` automatically |

**`volatility="fast"` is the key choice.** Program state goes stale in hours. The TTL
machinery then tags an untouched milestone `[EXPIRED]` and demotes it in the reranker
without anyone running anything. **The tracker detects its own neglect using a mechanism
built for third-party facts.**

### Guard against the tracker becoming what it replaced

`ROADMAP.md:52` still carries an open **P0-1** whose target versions are seven minor
releases stale (`03` P2-4). A backlog that drifts from its code is exactly the failure
this tracker exists to prevent, and it is not automatic. Mitigation, in the digest (§3):
any milestone with `last_verified` older than **7 days** appears in the digest under
**STALE**, and older than **21 days** is auto-`blocked` with
`blockers += {what: "no verification in 21 days", owner: human}`.

---

## 3. Daily digest

Posted by Qwen3.8 at **session start** and **session end**. It rides the same discipline
as the existing `[DREAM]` digest (`dream_digest.py`, ≤30 lines) so operators read it.

**Format — fixed, ≤30 lines, no prose paragraphs:**

```
[PROGRAM] 2026-08-20T09:02+02:00 · health 71/100 (+3 since 08-19) · M2 in_progress

M0 canonicalisation      done        7/7 criteria · verified 08-18
M1 docs + CI + releases  done        7/7 criteria · verified 08-19
M2 drift detector        in_progress 4/6 criteria · verified 08-20 09:01
     next: TASK-M2-4 wire drift job as blocking in ci.yml  (qwen3.8)
     delta: E2.2 negative test now PASSES (caught the v1.11.2 injection)
M3 security+epistemics   blocked     0/8 · BLK: TASK-M3-1 escalated to sonnet5 (2d)
M4 eval + baselines      open        0/6 · depends M3
M5 demo + metrics        open        0/7 · depends M4
M6 narrative             open        0/4 · depends M5

BLOCKERS (2)
  BLK-M0-1  credential rotation (agent_commands.log)   owner: human    12d  ⚠
  BLK-M3-1  evidence-provenance design                 owner: sonnet5   2d

STALE (1)
  MILESTONE-M0  last_verified 08-18 (2d)  — re-run E0.10 restore drill

PARITY  node4090 lse-kb 289 · node3090 45 · errors 82/61 · drift: none
NEXT    TASK-M2-4 (qwen3.8) · then TASK-M2-5 (qwen3.8)
```

**Health score** = the `04` weighted score, recomputed from criteria states:
`sum(weight_g * (passed_criteria_g / total_criteria_g))`. One number, same scale as `04`,
so progress toward 85 is legible without reading anything else. The `(+3 since …)` delta
is what makes an operator read line 1.

**Session-start digest** additionally runs the cold-start re-verification of §4 and
prepends any mismatch as a `⚠ COLD-START` line.
**Session-end digest** additionally writes a `task_checkpoint` (§4).

---

## 4. Handoff — the exact `task_checkpoint` Qwen3.8 writes

Called at every session end, and immediately on any `BUDGET EXHAUSTED` notice (the
existing checkpoint rule, `goethe_planner.py:883` docstring).

```python
task_checkpoint(
  task_id = "goethe-funding-program",       # STABLE across all sessions — never regenerate
  status  = "open",
  goal    = "Take Goethe from fundability 41/100 to 85+ per analysis/04 and 05. "
            "Current milestone: M2 (drift detector).",
  plan    = "M0 done · M1 done · M2 in_progress · M3 blocked(sonnet5) · M4/M5/M6 open. "
            "Full plan: search_kb('MILESTONE-M2'). Never re-derive the plan from chat.",
  done    = "M0 7/7, M1 7/7, M2 4/6 (E2.1,E2.3,E2.5,E2.6 pass). "
            "Evidence for every one is in the evidence_log of its MILESTONE- doc.",
  findings= "E2.2 negative test confirmed the detector catches the historical "
            "v1.11.2-vs-v1.13.0 drift. TASK-M3-1 escalated to sonnet5 on 08-18.",
  unverified = "E2.4 (CI job blocking) and E2.2 have NOT been re-run since ci.yml "
               "changed on 08-20. Treat both as not_run until re-verified.",
  next_prompt = """
COLD START — Goethe funding program. Do these five things IN ORDER before anything else.

1. CORPUS IDENTITY. Run:
     git -C /home/sy5/projects/local-system-engineer rev-parse HEAD
     python3 scripts/corpus_manifest.py --verify
   If the manifest does NOT verify, or HEAD differs from the sha recorded in
   MILESTONE-M0's evidence_log, STOP. Re-run the analysis/00 ingestion audit before
   touching any task. A changed corpus invalidates every stored verification.

2. LOAD STATE FROM THE KB, NOT FROM MEMORY. Run:
     search_kb("MILESTONE-", max_results=10)
   Read every milestone doc. Note any tagged [STALE] or [EXPIRED] — those are
   verifications you must NOT trust.

3. RE-VERIFY THE CURRENT MILESTONE'S CRITERIA. For M2, re-run every criterion whose
   state is 'pass' but whose last_run predates the newest commit touching its
   input_files. Paste raw output into evidence_log via mentor_correct. A criterion
   that passed against older code is 'not_run'.

4. CHECK LIVE DRIFT (CI cannot see the boxes):
     bash scripts/live_prompt_check.sh
   Any MISMATCH is a blocker on M2 — file it before proceeding.

5. POST THE SESSION-START DIGEST (analysis/07 §3), then claim the single task named
   in next_action. Claim exactly one task. Do not batch.

RULES FOR THIS SESSION:
  - Evidence first, status second. Never flip a status before the evidence_log write
    returns success.
  - Two consecutive failures on one task => status=blocked, escalate to sonnet5,
    do not retry.
  - Never edit tools/ on node3090 (the rsync overwrites it).
  - systemctl stop goethe-dream.timer before ANY task touching TRAUM; verify with
    `systemctl is-active goethe-dream.timer` returning 'inactive'.
  - Never write a hand-written tracking file. The KB is the tracker. That rule is the
    reason this tracker exists.
""",
)
```

**What a cold-start Qwen3.8 must re-verify first, in priority order:**

1. **Corpus identity** — if the corpus hash changed, **re-run the `analysis/00` ingestion
   audit before any task.** Every stored verification is conditional on the tree it ran
   against. This is the §3 requirement and it is non-negotiable.
2. **KB reachability and the tracker doc set** — `search_kb("MILESTONE-")` must return 7
   docs (M0…M6). Fewer means state loss; restore from the M0-9 backup before proceeding.
3. **Anything `[STALE]`/`[EXPIRED]`** — these are self-reported untrustworthy.
4. **Criteria that passed against older code** — a `pass` whose `last_run` predates the
   newest commit to its `input_files` is downgraded to `not_run`. Mechanical, from git.
5. **Live prompt drift** — CI cannot see node4090/node3090; the tracker can.

---

## 5. Staleness and integrity

### 5.1 How the tracker detects its own drift

| drift class | detector | cadence |
|---|---|---|
| Milestone doc vs. live code | `kb_verify(doc_id, observed=<re-run output>)` — auto-demotes on mismatch | per criterion, at session start |
| Criterion verified against stale code | `last_run` vs. `git log -1 --format=%cI -- <input_files>` | session start |
| Program state neglected | `volatility="fast"` → `[EXPIRED]` tag + rerank demotion, automatic | continuous |
| >7d unverified | digest **STALE** section | daily |
| >21d unverified | auto-`blocked` + human blocker | daily |
| Corpus changed under stored evidence | `corpus_manifest.py --verify` vs. M0 evidence_log | session start |
| **Prompt-vs-code drift (in repo)** | `scripts/check_version_drift.py --strict` — the M2 detector | CI, every push |
| **Prompt-vs-code drift (live, per-instance)** | `scripts/live_prompt_check.sh` — `ssh <host> sha256sum <deployed prompt>` vs. the tracked template hash | session start |

The last row is the extension the brief asks for. The M2 CI detector covers the repo; it
**cannot see the live boxes**. The tracker runs in the environment and can. Together they
close both halves of the class that produced `prompts/node3090-v0.3.0.md:37` (v1.11.2) and
`prompts/v0.6.2.md:12` (v1.12.0) both describing byte-identical v1.13.0 code.

Concretely, at session start:

```bash
for host in node4090 node3090; do
  tmpl=$(python3 -c "import tomllib;print(tomllib.load(open('prompts/DEPLOYED.toml','rb'))['$host'])")
  live=$(ssh "$host" "sha256sum \$GOETHE_SYSTEM_PROMPT" | cut -d' ' -f1)
  repo=$(sha256sum "prompts/$tmpl" | cut -d' ' -f1)
  [ "$live" = "$repo" ] && echo "$host prompt sha MATCH" || echo "$host prompt sha MISMATCH"
done
```
Any `MISMATCH` is filed as a blocker on the active milestone before any task is claimed.

### 5.2 Quarantine rules for dead work items

| condition | action |
|---|---|
| Task superseded by a redesign | `mentor_demote(doc_id, 0.2, "superseded by TASK-M3-1b")` → quarantine; status `abandoned` |
| Milestone descoped | same; `depends_on` edges in successors rewritten in the **same session** |
| Task `blocked` >14 days with no blocker movement | digest escalation to human; if unresolved at 28 days → `abandoned` with a reason |
| Criterion no longer meaningful (the code it tested is gone) | remove from `exit_criteria`, and **record the removal in `evidence_log` with justification** — a criterion may never be silently dropped |
| Two docs describe the same work | `mentor_correct` the survivor, `mentor_demote` the duplicate; TRAUM's dedup pass would otherwise propose exactly this |

**Quarantined tracker docs are never deleted.** They sit at the 0.2 floor with
`stale=True`, retrievable for forensics, exactly as the KB treats any other decayed
knowledge (`goethe_kb.py:941–947`). The program's own dead ends become part of the record.

### 5.3 The `done` rule — the acid test

> **A milestone may only be `done` when a fresh session can re-verify every one of its
> exit criteria from the KB alone, with no chat history.**

Operationally, before flipping a milestone to `done`, Qwen3.8 must:

1. Start a **new session** (or `task_resume` with no carried context).
2. `search_kb("MILESTONE-M<n>")` — read only what comes back.
3. Run **every** `exit_criteria[].command` verbatim from the doc.
4. Confirm each produces its `expect`.
5. Append that whole run to `evidence_log` as a single **`verification_sweep`** entry.
6. Only then `mentor_correct(status="done")`.

If step 3 cannot be performed — a command references a path, variable, or piece of context
not in the document — **the criterion is defective and the milestone is not done.** Fix the
criterion, not the status. This is what forces exit criteria to stay genuinely
self-contained rather than degrading into "run the tests" over time, and it is the
mechanism that makes the whole plan auditable by a funding reviewer six months later.

### 5.4 Two-KB operation

Per the `05` §KB decision: **there is no two-KB tracker operation.** The tracker is
single-writer on node4090's `lse-kb`. node3090 holds no `MILESTONE-` or `TASK-` docs, ever.

What the tracker *does* do about the second instance:

- Runs `scripts/kb_parity.py` (M5-5) at session start and prints the `PARITY` line in the
  digest. Divergence is **reported as a metric, not corrected as an error** — it is the
  sovereignty property being instrumented (`02` §7).
- Treats one specific divergence as a defect rather than a feature: `lse-errors` at 1 doc
  on node3090 makes `check_error_kb` a no-op there (`03` P1-11). M0-12's one-way seed
  fixes it; the tracker asserts `count >= 50` thereafter and files a blocker if it regresses.
- Never writes to node3090's ES. If a task requires it, that task is `blocked` pending an
  explicit human decision — because a second writer would silently destroy the
  single-source-of-truth property this whole document exists to establish.

---

## 6. Human gate points

The exact moments the program stops and waits for a person. Everything else runs
unattended.

| # | gate | why a human | what they see | blocking? |
|---|---|---|---|---|
| **H1** | **`sudo_delegation_block`** — any privileged operation | The agent has never had sudo, by design. `goethe_perms.py` issues grants; a human runs them. | the delegation block, verbatim | **hard** |
| **H2** | **Sonnet5 budget spend** — before dispatching a bundle beyond the session's token allowance | Sonnet5 is metered; an unattended escalation loop is the expensive failure mode | task id, estimated tokens, running total vs. budget | **hard** |
| **H3** | **Merge of any core-module refactor** — `tools/goethe.py` core, `dream_runner.py`, or any guard function in `01` §7.1 | Blast radius; a guard that passes tests but stops guarding is not test-detectable | the diff, full suite output, drift-detector output | **hard** |
| **H4** | **Dream-cycle proposals** — `dream_apply`'s `ask_yes_no` (`dream_apply.py:657`) | **Never auto-applied.** The tracker may *schedule* the review; it may never answer it. `GOETHE_DREAM_AUTO_APPLY` stays empty (`:199`) and the tracker asserts this at session start. | rendered proposal group + CAS state | **hard, by design** |
| **H5** | **Funding one-pager sign-off** (M6-7) | Claims about the company are the founder's to make | the one-pager + `verify_claims.py` output | **hard** |
| **H6** | **Corpus B destructive operations** (M0-10 phase 2) | One-way door on the only host holding the T0/T1 suite | the verified backup tar + the rescue-list commit shas | **hard** |
| **H7** | **KB schema changes** | A partial migration across two ES instances is unrecoverable without snapshots | the migration plan + snapshot confirmation | **hard** |
| **H8** | **Flipping a guard valve from `warn` to `block`** (M3) | Changes live agent behaviour | one week of audit-log data showing what `block` *would* have refused | **hard** |
| **H9** | **Credential rotation** (M0-12) | Only a human can rotate and confirm | the finding + the rotation checklist | **hard** |
| **H10** | Marking a milestone `done` | Optional. The §5.3 verification sweep is the real gate. | the `verification_sweep` evidence entry | **soft — notify** |
| **H11** | External security review (M3-8) | Third-party judgment | the threat model + guard inventory | **hard** |

**The invariant across all eleven:** the tracker may *prepare*, *render*, *schedule* and
*escalate* a gate. It may never *pass* one. Every gate resolves to a human action recorded
in the relevant doc's `evidence_log` with a timestamp — which, once `03` P1-12's `actor`
field lands, also records **who**.

That last point is the bridge from this program to the product. Today every gate assumes
one human at one terminal and records no identity (`03` P1-12). The tracker will be the
first system to feel that gap — the first time two people run this program, `evidence_log`
will say a gate was passed and not by whom. **That is the forcing function for the
`actor` field, and the `actor` field is the first genuinely enterprise-shaped feature in
the roadmap.** Building the program in the product surfaces the product's next
requirement, which is the argument for doing it this way rather than in a spreadsheet.
