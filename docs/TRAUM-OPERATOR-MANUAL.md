# TRAUM GUI Operator Manual

This manual covers routine operation of the TRAUM learning loop in the Goethe
Console at `http://localhost:9700/ui`. TRAUM analyzes the episode, error, and
knowledge corpora; produces typed proposals; and records whether accepted
changes improve later retrieval and task outcomes. The Console is the routine
control surface. The CLI remains an expert recovery and isolated-evaluation
surface.

## 1. Start here

1. Open the Console and enter the existing `GOETHE_MCP_TOKEN` in the gateway
   token field.
2. Read **TRAUM — Dream Digest** and the canonical run table.
3. If **needs decision** is non-zero, review the **TRAUM — Human Gate** inbox.
4. Preview each proposal before deciding. Approve only when the evidence and
   proposed semantic change agree.
5. Use **Acknowledge** after investigating a failed or blocked attempt. Use
   **Archive** when a terminal run no longer belongs in the default view.

The Console does not expose a command box, executable path, environment
editor, PID field, sudo action, or systemd mutation. Every control maps to one
server-defined operation with a bounded schema.

## 2. Control-plane boundary

TRAUM controls and Goethe Permissions are intentionally separate.

| Plane | Purpose | TRAUM interaction |
|---|---|---|
| TRAUM Digest / control surface | Dream runs, pass attempts, proposals, redacted logs, acknowledgement, archive, learning-lift evidence | This manual |
| Permissions — Pending Approvals | Agent requests for read/write/sudo authority | Unchanged; TRAUM neither creates nor consumes requests |
| Active Grants | Existing operational grants and sudo-grant workflow | Unchanged; TRAUM does not inspect or mutate grants |
| Nightly systemd timer | Unattended scheduling | Status is visible, but pause/resume/start/stop are not exposed |

Authentication uses the existing gateway bearer token. TRAUM controls fail
closed when no token is configured, even though older read-only Console panels
can retain their localhost posture. There are no new roles or integrations
with `goethe_perms`.

## 3. Reading run state

Each cycle has an immutable run ID. Each execution of a pass has its own
attempt ID, including retries. A retry never overwrites the failed attempt.

| State | Meaning | Operator action |
|---|---|---|
| `QUEUED` | Accepted by the controller but not started | Wait briefly; a persistent queued state is abnormal |
| `RUNNING` | The controller owns an active child operation | Read logs; cancel only when necessary |
| `SUCCEEDED` | The requested operation completed | Review any pending semantic proposals |
| `NULL` | The pass looked and found nothing above its thresholds | None; this is a healthy evidence-bearing result |
| `BLOCKED` | A guard, dependency, lock, or whole-cycle budget prevented completion | Resolve the named condition, then Retry |
| `DEGRADED` | Some operations completed and at least one did not | Inspect individual attempts; retry only failed/blocked attempts |
| `FAILED` | No acceptable complete outcome was obtained | Inspect the redacted log and failure artifact |
| `CANCELLED` | A controller-owned operation was stopped | Confirm why, then acknowledge/archive as appropriate |

Null, blocked, and failed are deliberately distinct. “Nothing was found” must
never be used to conceal “the corpus was not examined.”

## 4. Running TRAUM

### Standard cycle

Choose **standard cycle**, set the session cap and the whole-cycle time budget,
then select **Run**. The fixed operation sequence is:

1. `dedup`
2. `stale-contradiction`
3. `error-cluster`
4. `patterns`
5. `insights`
6. operator digest refresh

The session cap is 1–100. The cycle budget is 5–45 minutes for the complete
operation, not 45 minutes per pass. Each pass receives only the remaining
budget. Guards stay enabled and writes go only to TRAUM artifacts/canonical
state; proposals still require their own decision.

Only one GUI-owned TRAUM operation is admitted at a time. A second request
returns a conflict and does not leave a queued run behind.

The controller never infers ownership from a stored PID. GUI operations persist
a bounded UTC `deadline_at`; each attempt persists `lease_expires_at`, capped by
that operation deadline.

### Post-restart lease recovery

After a gateway restart, process ownership is intentionally lost. Recovery and
new-run admission use only canonical state:

- before the deadline plus the default 30-second recovery grace, a `RUNNING` or
  `QUEUED` row is **UNOWNED / STATUS UNKNOWN**; Cancel is unavailable and a new
  GUI/scheduled run is denied;
- after that fence expires, the next recovery/admission transaction marks the
  abandoned run and active attempts `BLOCKED` with
  `ControllerLeaseExpired`, then makes Retry available;
- `STAGED`, `PENDING`, or `DEFERRED` proposals from an expired parent attempt
  become `SYSTEM_REJECTED`; their rows and audit evidence remain retained;
- a late worker cannot publish proposals or a successful result after its
  lease/parent state has been fenced;
- legacy active state with no derivable deadline remains unowned and requires
  expert reconciliation.

No recovery path kills a stored PID or automatically replays a semantic apply.
An interrupted `APPLYING` proposal is handled separately as `APPLY_FAILED` and
still requires operator reconciliation.

### One pass

Choose **single pass**, select one of the five fixed pass names, and run it.
Use this after resolving a pass-specific dependency or while investigating a
specific corpus. The browser cannot add flags such as `--ignore-guards`.

### Retry

Retry appears only on `FAILED` or `BLOCKED` attempts. It creates a new attempt
under the same run and links it to the earlier attempt. Dependency-blocked
retries do not require a separate semantic confirmation.

`APPLY_FAILED` proposal state is different: the external write may have partly
completed, so the Console deliberately does not offer Approve/replay. Reconcile
the target and audit evidence before rejecting or performing expert recovery.

### Cancel

Cancel requires confirmation. It targets only the exact `Popen` object owned
by the current gateway controller. The API accepts neither a PID nor a process
name. The controller first requests termination and performs a bounded kill
escalation only if that same owned child ignores termination. After a gateway
restart, an old PID is not considered owned and cannot be cancelled here. See
the post-restart lease recovery contract above.

## 5. Logs

Select **Logs** on a run to view the newest attempt by default. Logs are:

- redacted before being written and redacted again before display;
- stored under a controller-owned directory with directory mode `0700` and
  file mode `0600` on POSIX systems;
- capped at 512 KiB of source data and at 1–1,000 requested lines;
- resolved from canonical attempt metadata, never from a browser path.

An empty log can mean the attempt predates the controller, including an
imported legacy day. Consult its retained report/crash artifact through the
expert recovery workflow if needed.

## 6. Human Gate

The default inbox contains only currently actionable semantic work:

- `PENDING` proposals;
- `DEFERRED` proposals whose date has arrived;
- `APPLY_FAILED` items requiring reconciliation.

Future-deferred proposals stay out of the default inbox. Select **show
future-deferred proposals early** only for deliberate advance review.

The inbox header reports **showing N / total**. When the result is truncated,
the Console says so and continues to retain every unseen item in canonical
state. If an older controller cannot obtain an exact inventory, it labels the
number as a lower bound and must not report the human gate as clear.

Malformed/invariant-violating proposals, exact repeats, superseded proposals,
and expiry receive typed lifecycle states without becoming routine human
questions. Healthy null results and guard-blocked attempts remain in run
history, not the semantic inbox.

### Preview

Preview performs live invariant and target-revision checks but makes no state,
KB, prompt, or decision-log change. The displayed revision must still match
when a decision is made.

### Approve

Approve first runs Preview and asks for confirmation. Approval then:

1. checks proposal revision and current target token;
2. revalidates hard invariants;
3. atomically claims a proposal/pair as `APPLYING`;
4. executes the fixed typed call without a shell;
5. records `APPLIED` or fail-closes as `APPLY_FAILED`.

The typed result remains on screen for inspection or copying until you select
**Dismiss**. For `kb_verify`/reverification this result can contain the next
live-probe instructions; do not dismiss it before recording the required
follow-up.

### Reject

Reject requires a concise reason. It retains the proposal, actor, timestamp,
revision, and reason in canonical history; it does not delete evidence.

### Defer

Defer requires a future ISO date within 365 days. It removes the proposal from
the actionable inbox until that date. Defer when evidence is not yet available,
not as a substitute for rejecting a bad proposal.

## 7. Failure acknowledgement and archive

**Acknowledge** means “the operator has reviewed this failure/block.” It does
not change the attempt outcome or remove artifacts.

**Archive** hides a terminal run from the default table. It does not delete its
run, attempts, proposals, events, reports, crashes, or logs. Select **show
archived** to retrieve it.

On controller startup, filesystem-only historical days are reconciled into
stable `legacy_*` runs. This makes the 2026-07-17 and 2026-07-20 failures
acknowledgeable and archivable while preserving their original files. If a
legacy import is interrupted, the next startup resumes idempotently.

## 8. Timer status

The timer box performs one fixed read-only query for
`goethe-dream.timer` and shows enabled/active state, last trigger, and next run.
There is no timer mutation route.

If scheduling must change, treat it as a separate operational task. Do not use
TRAUM to create a Pending Approval or Active Grant, and do not alter the sudo
grant model as part of Dream Planner operation.

## 9. A/B learning-lift evidence

The A/B box is monitoring-only. It reads the staged, isolated v2 evaluation
registry and reports:

- latest evaluation ID and stage;
- analysis completeness separately from promotion eligibility;
- sanitized outcome/hash evidence;
- the learning delta (documents added / removed / modified between the frozen
  baseline and the post-window corpus);
- the next typed stage and any elapsed-window block;
- aggregate continuous-evidence counts and policy-review eligibility.

It never returns condition endpoints, filesystem roots, registry paths, or raw
trial artifacts to the browser. It exposes no “run arbitrary eval” control.

An evaluation progresses through `initialized`, `baseline_wait`,
`b_window_ready`, `b_window_open`, `trials_running`, `trials_complete`, and
`analyzed`. Interpret the two decision concepts independently:

- `analysis_complete` means the registry reached `analyzed` and a statistical
  result artifact exists. It says nothing by itself about whether that result
  is favorable or safe.
- `promotion_eligible` means the outcome is `WIN` **and** every required safety,
  non-inferiority, and wrong-hit gate passed. It only nominates a policy for
  human review; it never enables auto-apply.

An analyzed `LOSS`, `NULL`, or `INCONCLUSIVE` result is analysis-complete but
not promotion-eligible. Where an older Console renders **analysis available**
from stage alone, read it as `analysis_complete` only and inspect the sanitized
outcome and gates before any policy review. Earlier stages state the next
action or block.

Until a v2 evaluation exists, the Console retains one clearly marked historical
reference: `eval-report-traum-1` recorded a pre-registered `LOSS`, with causal
interpretation `INCONCLUSIVE`. It is context for why v2 exists and is not
substituted for isolated v2 evidence. Preserve both conclusions; the report
must not be relabelled as a win or used to authorize auto-apply. See the
[v1 report](../eval/eval-report-traum-1.md) and the
[v2 design](../eval/traum-ab-design-v2.md).

Condition A must remain an immutable frozen baseline. Condition B is captured
only after the real learning window and only from its isolated store/gateway/
filesystem. Both arms use pinned models, prompts, retrievers, embeddings, tool
schemas, and paired seeds. A result is eligible for policy review only after
safety/non-inferiority and wrong-hit gates pass. It never enables auto-apply.

Continuous decision-to-outcome evidence is currently labelled
`decision_wiring: not_connected`. An empty evidence registry therefore means
“no outcome evidence recorded,” not “looked and found no impact.”

Expert staged-evaluation commands are documented by:

```bash
python3 tools/traum_eval.py --help
python3 tools/traum_eval.py status
python3 tools/traum_eval.py evidence-status
```

Do not use production ES/gateway/filesystem targets as either condition.

### Running an evaluation end to end

The evaluation runs offline, from the CLI, against disposable sandboxes. The
Console observes it; it cannot start it. Every step is idempotent — repeating a
command with the same bytes returns the same state rather than creating a second
record.

**1. Build two disposable sandboxes.** Bring up an Elasticsearch instance and a
gateway for each arm on non-production ports (for example `:19201`/`:19701` for
A and `:19202`/`:19702` for B) with disjoint data roots, and export those roots
as `$A_ROOT` and `$B_ROOT`. Ports `9200` and `9700` and roots under `/opt`,
`/var/lib/elasticsearch`, and `/var/lib/docker` are refused in code, for every
spelling of localhost.

**2. Write the spec and the two attestations.** The spec pins the model,
prompt, tool schema, retriever config, embedding model, dataset, at least three
seeds, `min_elapsed_seconds` (default 24h, floor 1h), and the decision gates.
Each `traum.eval.isolation.v1` attestation declares its condition isolated,
disposable, free of production data and writes, and auto-apply disabled. Schemas
live in `eval/traum-eval-spec-v2.schema.json` and
`eval/traum-isolation-attestation-v1.schema.json`.

**3. `init`.** The registry copies the spec, pins, and attestations, and returns
an immutable evaluation ID. Nothing after this point can change those inputs.

**4. `freeze-a`.** Export mapping, documents, and retrieval config from the A
sandbox into `$A_ROOT`, then freeze them. Sources must be absolute paths inside
`$A_ROOT`; they are hashed before and after copying and are never modified.

**5. Let the system actually learn.** Leave the window open across several real
scheduled dream cycles. `open-b` refuses to advance before the pinned interval
elapses and reports the remaining seconds. Do not shorten the window to finish
an experiment.

**6. `open-b`, then `capture-b`.** Export the post-window corpus into `$B_ROOT`.
B's mapping and config must hash equal to A — only documents may change. Two
refusals matter here:

- `unsafe_path` — a source outside `$B_ROOT` (including a symlink pointing out
  of it, or the other condition's root). Re-export inside the sandbox.
- `no_learning_delta` — the corpus is unchanged, or differs only in
  serialization. This is not a tooling failure; it means the window produced no
  KB change and there is nothing to measure. Investigate why dreaming produced
  no accepted change, then run a longer window.

**7. `record-trial` for every seed in both conditions.** Each trial declares the
input fingerprint, its condition export fingerprint, all six runtime
fingerprints, zero production writes, and zero input mutations. Raw transcripts
are mandatory and are hashed on admission. A mismatched fingerprint is rejected
rather than silently scored.

**8. `analyze`.** The registry recomputes the corpus delta from the immutable
manifests, refuses to score identical corpora, and writes paired 95% confidence
intervals, gate results, lift results, and one outcome. The artifact is
immutable: a second `analyze` with different results fails as
`immutable_conflict`.

**9. Read the result in the Console.** `WIN` with every safety gate passed makes
the evaluation *eligible for policy review* — a nomination for a human decision.
`LOSS`, `NULL`, and `INCONCLUSIVE` are complete results, not failures to retry
until favorable. No outcome enables auto-apply; no such action exists.

## 10. API reference

All routes require `Authorization: Bearer <GOETHE_MCP_TOKEN>`.

| Method and path | Typed purpose |
|---|---|
| `GET /api/ui/traum/status` | Counts, active controller run, timer, sanitized eval/evidence status |
| `GET /api/ui/traum/runs?archived=false&limit=50` | Runs plus pass attempts |
| `GET /api/ui/traum/runs/{run_id}/logs?limit=200` | Bounded redacted log |
| `GET /api/ui/traum/proposals?state=...&actionable=true&limit=50&offset=0` | Exact-count, paginated human-gate queue |
| `GET /api/ui/traum/timer` | Read-only fixed timer status |
| `POST /api/ui/traum/runs` | Start standard or fixed single-pass run |
| `POST /api/ui/traum/runs/{run_id}/retry` | Retry one failed/blocked attempt |
| `POST /api/ui/traum/runs/{run_id}/cancel` | Cancel one controller-owned run |
| `POST /api/ui/traum/runs/{run_id}/archive` | Reversible terminal-run archive |
| `POST /api/ui/traum/attempts/{attempt_id}/acknowledge` | Record operator review |
| `POST /api/ui/traum/proposals/{proposal_id}/preview` | Side-effect-free validation |
| `POST /api/ui/traum/proposals/{proposal_id}/decision` | Approve/reject/defer with revision CAS |

Example run request:

```json
{
  "profile": "single-pass",
  "pass": "patterns",
  "sessions": 50,
  "wall_clock_minutes": 20
}
```

Unknown fields are rejected. There are no fields for `command`, `argv`,
`path`, `env`, `pid`, `unit`, `sudo`, or guard bypass.

Common response codes:

- `400`: invalid type, enum, bound, ID, or unknown field;
- `401`: bearer token missing/wrong;
- `503`: gateway token or TRAUM controller is unavailable;
- `404`: canonical entity/route does not exist;
- `409`: lifecycle/revision conflict or non-owned cancellation target.

## 11. Troubleshooting

| Symptom | Interpretation | Action |
|---|---|---|
| TRAUM controls disabled: token not configured | Mutation surface failed closed | Configure the existing gateway token and restart the gateway |
| Operation already active | One-run admission guard | Wait, inspect Logs, or Cancel the owned run |
| `UNOWNED / STATUS UNKNOWN` | Durable active-looking state is not owned by this gateway process | Investigate canonical events and the actual process through expert recovery; there is intentionally no PID control |
| Human-gate count says “at least” | Full proposal inventory could not be counted | Do not treat an empty page as clear; restore the canonical-state query before deciding |
| `BLOCKED recent-session-activity` | Quiet-hours safety guard | Retry after the active session window |
| `BLOCKED dream-lock` | Another dream process owns the lock | Verify the other run; do not delete an active lock |
| `BLOCKED` near cycle deadline | Whole-cycle 5–45 minute budget exhausted | Retry only the incomplete pass or choose a justified larger cycle budget |
| Proposal revision changed | The reviewed proposal/target changed | Preview again; never force the old decision |
| `APPLY_FAILED` | External write completion is uncertain | Reconcile target and audit evidence; do not replay automatically |
| Logs unavailable for a legacy run | It predates controller logging | Inspect retained legacy report/crash artifacts via expert recovery |
| Eval evidence says BLOCKED | Evaluation is incomplete or elapsed window not met | Follow the displayed staged next action in the isolated harness |

## 12. Expert recovery rules

The CLI can expose more recovery detail than the GUI, but it is not a web
execution backend. Keep these rules:

- never point an ad hoc command at a browser-supplied path;
- never use `--ignore-guards` for routine or unattended operation;
- never delete a day directory to clear the Console;
- never replay `APPLY_FAILED` without reconciling whether the prior write
  completed;
- never modify Permissions/Active Grants to work around a TRAUM lifecycle
  state;
- retain run IDs, attempt IDs, proposal IDs, revisions, and artifact hashes in
  incident notes.

Architecture and rationale remain in `docs/dreaming/DESIGN.md`,
`docs/traum-dreaming-plan.md`, `eval/traum-ab-design.md`, and
`eval/traum-ab-design-v2.md`.
