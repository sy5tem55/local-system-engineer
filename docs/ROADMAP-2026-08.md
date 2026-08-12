# Roadmap — after TRAUM R1–R3

> 2026-08-01. Ordering rationale: TRAUM has just produced its first real
> output but has still never completed a clean cycle. Several items below
> are deliberately gated on observing more real runs rather than acting
> now on a design whose production behaviour is barely observed.

---

## Status — 2026-08-09

> This section is the index. The prose below is the original reasoning, kept
> because *why* an item exists outlives its state. Where the two disagree,
> this table wins.

**Closed since 2026-08-01** (14 items, 11 verified independently):

| Item | § | Landed | Note |
|---|---|---|---|
| Manifest orphan-pruning | 1 | `f9379c1` | opt-in `prune=True`, wired into the Console purge |
| D5 safety-gate substring | 1 | `4ef18c7` | retested 2026-08-08; **new** false positive found, see Open |
| Corpus hygiene in the Console | 1 | `bc5680c` | quarantine-only, never destructive |
| SUPERSEDED vs QUARANTINED | 1 | `0622a09` + `2cd8c45` | LSE-implemented; its test was vacuous and was replaced |
| `diagnosis` proposal type | 1 | `668bfb1` | **proven in production 2026-08-08**: 9 applied |
| Index `session-learnings.md` | 1 | `a99146f` | verified: 73 hits in `lse-kb` |
| Cascade leg 0 → LUCIFER | 1b | `4968d31` | node3090 off the critical path |
| On-demand engine start | 1b | `9242ae2` | wake → SSH → start → poll |
| Node facts + profile matcher | 1b | `24391cb` | Layer 0+1 |
| R4 — sub-pass outcomes | 3 | `ccbe879` | reframed; the premise was wrong, see §3 |
| Cycle completes | 0 | `5612f59` | error-cluster envelope key, per-pass wall clock |
| Timer retired, dreaming manual | 0 | `b0a2758`…`3639fce` | units gone, templates deleted, test inverted |
| Tool-description cap | — | `594ccc9` | 39 of 48 docstrings were silently cut; gate now covers 48/48 |
| Test-suite concurrency safety | — | `ce7dfb7` | ES indices per-process; see the warning below |

**Two milestones met.** The loop now completes unattended-in-principle
(`run_49835c9f`, 2026-08-08: 6 of 6 passes, 11.4 min against a 45-min
deadline), and the Human Gate has adjudicated real output — 9 `diagnosis`
proposals applied, the first since the type shipped.

**A measurement warning that invalidates older numbers.** `test_kb_contracts.py`
is an Elasticsearch integration suite. Until `ce7dfb7` it used fixed index
names, so two overlapping pytest runs corrupted each other. **Every baseline
count recorded before 2026-08-09 is only meaningful if that run had exclusive
access to ES.** Check `pgrep -af pytest` before trusting any figure, including
one in this file.

### Open, ordered — see `docs/WORKFLOW-roadmap-execution.md` §5 for tier and ETA

| # | Item | § | State |
|---|---|---|---|
| 1 | Gate toil: duplicate diagnoses + `sub_passes` on the blocked path | 3 | spec'd `81d9fb8`, ready for Sonnet |
| 2 | The skill feedback loop has never fired | — | **re-measured 2026-08-12**: the query bug IS fixed (`95ca984`, term on `.keyword`). The loop is still dead for a different reason — **0 successes, 0 failures, 0 of 25 skills with any outcome, ever**. Nothing calls it. Fixing the caller, not the query, is the open work. |
| 3 | Repo-root agent brief (`AGENTS.md`) | 1 | absent; would have prevented the pin incident |
| 4 | Profile-questions eval set | 1b | spec'd `8177714`; `eval/profile-questions-v1.jsonl` absent — gates the whole web-search block |
| 5 | Hardware-aware profiles per node per workload | 1b | in flight — uncommitted `agent_profile` edit in `goethe_node.py` |
| 6 | Human Gate legibility — the edit action | 1 | half done (`22d3528` added apply-preview, which caught #1) |
| 7 | `/etc` change automation | 2 | not started; motivated again by the mask-ordering error below |
| 8 | Credential rotation skill | 1 | not started; `~/.git-credentials` is a third instance |
| 9 | Codify the review stage as a named step | 1 | partial — tiers and the LSE calibration are recorded, the step is not |
| 10 | R5 — collapse the proposal state machine | 3 | **unblocked**: 6 of 10 states now used in production, 8 runs of data |
| 11 | P2/P3 ruff backlog | 4 | 232 findings repo-wide (was 147) |
| 12 | R6 — split `dream_runner.py` | 3 | last, by design |

### Open, small, found 2026-08-08/09

- **Mask the retired timer.** The delegated block masked *before* `rm`, so
  mask failed ("file already exists") and the unit path is now unmasked.
  Mask belongs last, after `rm` and `daemon-reload`. Operator action.
- **Nine stale launcher pins.** `bin/` build outputs and the PR worktree still
  pin the pre-`594ccc9` hash of `tools/goethe_mcp.py`. Harmless until one is
  launched. `tests/test_gateway_pin.py` gates the two that matter.
- **Privilege gate trips on commit messages.** A `git commit` whose *message*
  quotes a privileged command is refused. Distinct from the identifier case
  `4ef18c7` fixed. Workaround: `git commit -F`.
- **Two clones.** The Cowork-mounted Windows checkout is on
  `feat/traum-control-plane` at `88f3130` (2026-08-03) with 66 dirty files;
  the live tree is the WSL checkout on `codex/fix-sudo-grants-live`. Same
  remote, five days apart. This has already cost confusion twice.

---

## 0. Immediate — run cycles, change nothing

**Update 2026-08-08:** `goethe-dream.timer` is retired
(SPEC-manual-dreaming-2026-08). "Run a standard cycle at the end of each
session" is no longer a wish alongside an unattended nightly timer -- it
is now the actual, sole, supported way a cycle starts.

The highest-value next action is **not code**. Run a standard cycle at the
end of each session for about a week, then re-read
`docs/TRAUM-ANALYSIS-2026-07-31.md` §1 against real numbers.

Every conclusion in that analysis was drawn from a system that had never
completed a cycle. One DEGRADED run with 3/5 passes succeeding has
already invalidated part of it. More data will reorder everything below.

Two specific things to watch:

- **Does `dedup` ever succeed?** It is now 0-for-5 and is the only pass
  that has never produced anything. With the quiet-period wait waived it
  should finally get to run.
- **Does `insights` stop blocking on `dream-llm`?** It blocked on
  2026-07-31 with node3090 healthy — most likely llama-server's slot was
  busy with interactive work. End-of-session runs should avoid that. If it
  still blocks, the cascade's slot-contention logic needs a look.
  **Update 2026-08-07:** part of this was never slot contention. `insights`
  runs one LLM call per domain; until `ccbe879` a single domain losing the
  dreamer marked the whole pass BLOCKED and threw away the other domains'
  proposals. Re-read this question against runs after that commit — the
  cascade may have been fine all along. See R4 in §3.

---

## 1. Near-term, small, well-understood

These are each a session or less and do not depend on more TRAUM data.

**Prune the manifest on corpus deletion.** `build_manifest()` never
removes rows for files that no longer exist (found 2026-08-01 during the
`method_raises` purge — 67 ghost rows survived a rebuild). Any deletion
path must prune explicitly, or analysis keeps seeing sessions that aren't
there. Small fix, real correctness bug.

**Credential rotation as an LSE skill.** Raised 2026-08-02 after
`tools/start-goethe-node3090.sh` was found carrying a hardcoded
`NODE3090_TOKEN` literal, committed and pushed. Repo is private, so this is
hygiene rather than incident — but it is the second credential-shaped item
after the parked BW_PASSWORD one, which makes it a pattern rather than a
one-off.

Rotation is harder here than "generate a new string", which is why it wants a
skill with verification rather than a runbook:

- A token lives in **more than one place**, and they drift. Measured
  2026-07-31: the running gateway's `GOETHE_MCP_TOKEN` was `5fa5643e…` while
  `/opt/local-se/goethe-mcp.env` on disk said `6e003f5c…`. Reading the file
  gave the *wrong* token and produced `{"error":"unauthorized"}`, which was
  then misread as "the feature is not deployed" and cost four turns. Ground
  truth is `/proc/<pid>/environ`, not the file.
- Rotation is therefore: update the store, restart the consumer, **verify the
  new value is live in the process**, and confirm the old one is rejected.
  A rotation that updates the file and stops there has changed nothing.
- Secrets should not sit in scripts at all. The convention already exists in
  this codebase — `tools/pfsense-gateway-tools.sh` states plainly that
  `PFSENSE_API_KEY` is *not* stored there and is passed in from Vaultwarden.
  `start-goethe-node3090.sh` should follow it.

Scope: an LSE skill that enumerates where a given credential lives, rotates
it, restarts what consumes it, and proves the new value is the live one and
the old value is dead. Vaultwarden is already wired (`vault_unlock`,
`get_vault_secret`, `set_vault_secret`).

**Fix the D5 safety-gate substring match.** The gate blocks any command
containing `sudo` as a substring — including read-only `git log` commands
that merely name the branch `codex/fix-sudo-grants-live`. It should match
`sudo` as a command token, not a substring. Found 2026-07-31.

**Corpus hygiene in the Console.** Today a contaminated-episode purge is a
manual shell operation. It should be an operator action: preview what
would be removed, quarantine rather than delete, rebuild *and* prune the
manifest as one step. Design it as a typed operation in the existing
Human Gate idiom, not a raw delete button.

**"QUARANTINED" means two opposite things.** Raised 2026-08-01 by the
operator, who reasonably asked how a doc can be `source_tier=ground_truth`
and QUARANTINED at once. It cannot — the label is wrong, not the data.

Two code paths both end at `stale=True` + low quality, and the Console shows
both as QUARANTINED:

| Path | Meaning | Floor |
|---|---|---|
| `kb_verify` failure decay (`goethe_kb.py:919`) | *"repeatedly failed — do not trust"* | 0.2 |
| `mentor_demote` (`goethe_kb.py:1227`) | *"correct but redundant — use the better copy"* | none |

The first is a correctness warning; the second is a filing decision. Shown
identically, and shown beside `ground_truth` (which is provenance and
correctly never changes), the second reads as a contradiction.

Live example: `RUTX50 Alternative WoL for node3090 via etherwake` and
`node3090 Full Stack Startup Procedure` both sit at quality 0.10, stale,
`failure_count: 0`, with `demote_reason` = *"Superseded by definitive doc
842595879f70576d (quality 1.0) … all its content is fully absorbed into the
definitive procedure."* They never failed. They are retired duplicates of a
doc that is healthy (quality 1.0, 7 empirical runs, 0 failures).

The diagnostic tell: 0.10 is **below** the 0.2 floor that failure-decay can
reach, so anything at 0.10 was demoted by human decision, not by failing.

Fix is display-level; the data needed already exists. A doc with
`mentor_demoted_at` set and `failure_count == 0` should render as
**SUPERSEDED → <target doc id>**, not QUARANTINED. Reserve QUARANTINED for
the failure-decay path. Same root cause as the `prp_` hashes below: the
Console surfaces internal state rather than its meaning.

**Human Gate legibility.** Proposals are presented as `prp_` hashes with
JSON-ish reasons and no plain-language statement of what approving would
actually do. There is also no edit action — a proposal with a correct
diagnosis but a poor procedure can only be rejected and rewritten
elsewhere. This is the operator-facing half of the original complaint
("it is not very intuitive how to operate it correctly") that R3 only
partly addressed.

**Add the `diagnosis` proposal type — spec'd, next up.** See
`docs/SPEC-diagnosis-proposal-type-2026-08.md`. Raised by the operator three
times; the third time with the definition the system was missing:

> *An agent skill is a series of actions the agent learns to concatenate
> together for a specific and repeatable deterministic outcome. These
> proposals are different — they are errors.*

The codebase already polices **fact vs skill** (`skill_record`'s docstring
rejects `task="llama-server port"` as a fact). It does not police **skill vs
diagnosis**, and everything `error-cluster` produces lands on the wrong side.

The axis is initiation: a skill is something you *decide to do*; a diagnosis
is something that *happens to you*. Routing tests — (1) can I decide to do
this? (2) is the value in the steps, or in "it is not what it looks like"?
By both, all six proposals pending 2026-08-03 are diagnoses, as is the
CancelledError skill recorded 2026-08-02 which the skills index scored 0.40
despite `source_tier=verified`.

The load-bearing new field is **`anti_response`** — what *not* to do. Three of
the six pending proposals are wrong precisely because they prescribe the
intuitive action (retry), which reproduces the failure. No existing type has
anywhere to say that.

Target is the existing `lse-errors-1024` (62 docs, `record_error`), extended
with `interpretation` and `anti_response` as real fields — not concatenated
into `resolution`, which is the mistake `skill_record` already made with
`trigger` and admits to at `dream_runner.py:1953`.

**Superseded:** the earlier "error-remedy" entry, which named the gap without
defining it.

**Superseded — original framing:** **Give `error-cluster` a correctly-shaped output type.** Raised
2026-08-01 by the operator, and the strongest single design finding of the
first real run.

`skill_record`'s contract is a repeatable *task* with steps
(preconditions → procedure → verification → failure modes). What
`error-cluster` actually produces is a *reaction*: "when you see error X,
do Y". Those are different genres — a reaction is a runbook/error-KB
entry, not a task — but `skill-candidate` is the only container the
dreamer has for it. The six emittable types are `reverify`, `demote`,
`dedup`, `kb-fact`, `prompt-rule`, `skill-candidate`; none means
"recurring error → known remedy".

The mismatch is visible in three places:

- `dream_runner.py:1953` concedes it in a comment — *"skill_record's real
  signature has no 'trigger' parameter (DESIGN.md §6.3) — fold it into
  procedure's own text"* — then reconstructs the missing field as
  `WHEN THIS HAPPENS: … FIX: …` inside free text. A schema needing a slot
  it does not have is the wrong schema.
- The correct target exists but is walled off: `lse-errors-1024` is
  reserved for dream-infra's own crash reports and is *"never touched by
  any pass function"*.
- Corroboration: a hand-written, genuinely verified entry of this shape,
  submitted as `quality=0.8, source_tier=verified`, was recorded by the
  skills index at **0.40**. The index is correctly scoring down a genre it
  was not built for.

Both `skill-candidate` proposals from the 2026-07-31 run are reactions,
not tasks — a 2-of-2 mis-typing rate on the pass's first real output.

Fix shape: add an `error-remedy` proposal type that writes to
`lse-errors-1024` through the Human Gate, and let `error-cluster` emit
`skill-candidate` only when a genuine repeatable procedure exists.
Requires opening the error index to pass functions under gate control —
deliberately, and with the dream-infra provenance boundary preserved.

**Close the compound-engineering loop.** Raised 2026-08-02. Compound
engineering (Every, Inc., Jan 2026) structures work as Plan → Work →
Review → Compound, where each cycle emits both the artifact and documented
learnings written back to persistent context that future cycles ingest.

This project already runs most of that, and in places exceeds it:

| Stage | State |
|---|---|
| Plan | Strong — the `SPEC-*.md` pattern (ground truth marked verify-don't-trust, hazards before design, named load-bearing tests, anti-goals) is ~40% of each cycle |
| Work | Spec → implementer → commit |
| Review | Partial — automated checks are strong, and break-and-restore exceeds the norm; structural review of *decisions* is ad hoc and uncodified |
| Compound | **Half-built** |

TRAUM *is* an automated compound stage: mine episodes → extract lessons →
propose → Human Gate → persistent KB. That is more ambitious than the
standard formulation. The gap is the human-authored half.

**Measured 2026-08-02:** `kb/session-learnings.md` is 1,300+ lines and is
indexed into `lse-kb-1024` **zero** times. Nothing reads it back. The
`lse-session-debrief` skill writes it; no retrieval path ingests it. It is
write-only memory — the exact failure the practice exists to prevent. There
is also no `AGENTS.md` or `CLAUDE.md` at this repo root for an agent to load
at session start.

Three concrete items, smallest first:

1. **Index `session-learnings.md` into the KB.** — **DONE** `a99146f`.
   Verified 2026-08-09: 73 `lse-kb` hits for `session-learnings`. Original
   text kept below.
    Chunk per `## Session`
   entry so retrieval returns one incident, not a 1,300-line file. Tag
   `source_tier` honestly — these are verified post-hoc observations, not
   ground truth. Once indexed, `search_kb` surfaces them and the loop closes.
   This is the single highest-leverage item on this list: the content already
   exists and is good; it is simply unreachable.

2. **Add a repo-root agent brief.** — **STILL OPEN, and it has now cost
   something.** `tools/goethe_mcp.py` is content-pinned by a Windows launcher
   that no file in this repo mentions; editing it broke the gateway on
   2026-08-08 and the refusal surfaced as a `ProcessLookupError` in a systemd
   supervisor, two layers from the cause. A root brief is where that kind of
   invisible coupling belongs.
    `docs/WORKFLOW-thread-handover.md`
   already is one in substance — tool-loading preamble, when to flip vs start
   fresh, turn budget, the six sections a spec needs, the verification rules.
   It is not in the conventional location or name, so nothing loads it
   automatically.

3. **Codify the review stage.** — **PARTIAL.** The tiers, the verification
   dials and the 2026-08-08 LSE calibration are now recorded in
   `docs/WORKFLOW-roadmap-execution.md`; the review *step itself* is still not
   a named part of the loop. Evidence it earns its keep: independent
   re-verification has now caught a vacuous test, two wrong ground-truth
   rows, a fabricated-looking baseline that turned out to be a real
   concurrency bug, and a reviewer error in the other direction.
    Independent re-verification of an
   implementer's report has caught real things (a mislabelled security
   "regression" that was the intended fix; a purge harness that needed
   adversarial probing separate from the implementer's own tests). Today that
   depends on whoever is reviewing remembering to do it. It belongs in the
   workflow doc as a named step with its own checklist.

Do **not** treat this as adopting a new methodology. The practice is already
here; these three items connect wires that are already run.

---

## 1b. Fleet architecture — the dreamer cascade points at the wrong machine

Established 2026-08-02, and it invalidates a premise R1 was built on.

**node4090 IS LUCIFER.** `goethe_node.py:293` states it plainly — *"node4090
is an alias for LUCIFER itself, is not a remote node, and is not routable
here."* `getent hosts node4090.home.arpa` → `192.168.1.57`, this machine.
node4090 is the **primary dreamer**; node3090 and node5090 are on-demand
compute for specialised workloads.

The cascade's defaults contradict that:

| Leg | Default | Should be |
|---|---|---|
| 0 `GOETHE_DREAM_LLM_URL` | `""` (unset) | LUCIFER/node4090 — the primary |
| 1 `GOETHE_NODE3090_LLM_URL` | `node3090:8080` | on-demand secondary |
| 2 `GOETHE_NODE3090_OLLAMA_URL` | `node3090:11434` | on-demand tertiary |

R1's stated premise — *"both real legs are on node3090, so a sleeping node
has zero fallback"* — was true of the **code** and wrong about the
**architecture**. The 2026-08-02 03:32 run proved it accidentally: the wake
"failed", the cycle "fell back" to LUCIFER, and completed all five passes
successfully. It had not degraded; it had reached the primary dreamer by
accident.

**Fix (small, high leverage):** default leg 0 to LUCIFER's local
llama-server. Leg 0 is health-probed, so if it is down the cascade still
falls through to node3090 unchanged. This removes node3090 from the nightly
critical path entirely.

### The on-demand service model this implies

No node auto-starts services **by design** — all nodes share one versatile
architecture, and the LSE starts what a given task needs. That makes
`wake-node-for-dream.sh`'s `/health` poll wrong in principle, not just in
detail: it waits for a service nothing was ever going to start. Confirmed
2026-08-02 — node3090 woke in 29s, then sat idle while the script polled
port 8080 for 300s (`systemctl is-enabled llama-server` → `not-found`).

Correct shape: wake → wait for **SSH** → start the required engine with the
right profile → *then* poll `/health`.

### Hardware-aware inference profiles *(operator priority)*

Elevate the LSE to start inference engines with parameters matched to the
specific node's hardware. The seed already exists: `_NODE_REGISTRY`'s
`agent_profile` and `_PROFILE_FLAGS` in `goethe_node.py`, hand-tuned for
node3090 on 2026-08-01 (ctx 131072, KV cache q4_0, 16 threads,
`--reasoning-format none`). Generalise to **profile per node per workload** —
chat, dreaming, voice, image, video — since the fleet spans 3090/4090/5090
with materially different VRAM and throughput.

### ML root-cause analysis

Strengthen structured RCA. Today failure analysis is ad hoc; TRAUM's
`error-cluster` finds recurring failures but has no correctly-shaped output
for them (see the `error-remedy` gap in §1). RCA and that gap are the same
problem seen from two ends.

### Multi-agent orchestration — deliberately later

LangGraph / AutoGen / CrewAI / Semantic Kernel were considered 2026-08-02.
Recommendation: **not yet, and probably LangGraph if ever.**

Reasoning: a framework coordinates capabilities you already have. The
capabilities are the gap — engines cannot yet be started with
hardware-appropriate parameters, and there is no RCA structure. Building a
control plane over that is premature. MCP already provides the substrate
(`query_node_agent` is agent-to-agent delegation today).

When revisited: LangGraph fits best — explicit state, conditional routing,
least opinionated, and this system's workflows are pipelines with gates.
AutoGen is conversation-centric and these agents execute rather than
negotiate. CrewAI is the most opinionated and would fight the invariant and
safety-gate discipline this codebase is built on. Semantic Kernel is
plausible given `Goethe.App` is .NET, but the substance lives in Python.

Revisit **after** profiles and RCA land, using real data about where
coordination actually hurts.

---

## 2. `/etc` change automation — spec, then build

Deferred from 2026-07-31 by explicit request; now unblocked.

Extend the existing dream-apply / Human-Gate pattern into a
`propose_file_change` capability: the agent writes the exact intended file
content, the operator sees a diff, approval applies it via a narrow root
helper. Strict path allowlisting and content validation
(`systemd-analyze verify` for units, `visudo -c` for sudoers) so it never
becomes a general root-write primitive.

Motivation: this session produced two `/etc` edits that had to be
hand-applied, and one of them (the timer) was saved unchanged on the first
attempt and silently did nothing — exactly the class of error a diff-then-
approve flow prevents.

**Spec first, build second.** The failure mode here is a too-general
primitive, and that is a design problem, not an implementation one.

---

## 3. TRAUM R4–R6 — gated on real data

From `docs/TRAUM-ANALYSIS-2026-07-31.md` §6, unchanged in priority but now
with a first data point.

**R4 — done 2026-08-07 (`ccbe879`), but not as written.** The premise was
wrong and the fix landed one level below where this entry pointed.

The NULL/BLOCKED boundary was **already correct**. `traum_state.py`'s run
aggregation and the controller's durable-state precedence both honoured the
distinction; confirmed as written in `SPEC-subpass-outcomes-2026-08` §2. What
made the run table hard to read was something else.

The real defect: `dream_runner.py`'s `_raise_if_dependency_blocked` scraped a
pass's *combined* narrative text for `DREAMER UNAVAILABLE` /
`DREAMER OUTPUT UNPARSEABLE` and raised unconditionally. In a pass with
independent sub-passes over the same pull — stale-contradiction's
`reverify` + `demote`, insights' one LLM call per domain — one sub-pass naming
its own failure in the shared narrative **discarded a sibling sub-pass's
already-good proposals** and recorded the whole attempt BLOCKED. A pass that
had partly succeeded was filed as one that never looked. That is why the
NULL/BLOCKED reading looked broken from the Console: the boundary was fine,
the input to it was not.

Fix, per `docs/SPEC-subpass-outcomes-2026-08.md`:

- `run_pass_stale_contradiction` and `run_pass_insights` return a 4th value,
  `sub_passes`, naming each sub-pass's own state / proposal count /
  dependency, folded into the attempt summary (Hazard B). Dispatch is
  length-tolerant, so the three 3-tuple passes are unchanged.
- The guard raises on the narrative-text markers **only when the pass
  produced nothing at all** (`if not raw_proposals and …`). The
  `looked is False` and `embedding_unavailable` paths still raise
  unconditionally, as they should.
- No new attempt state — `ATTEMPT_STATES` is byte-for-byte unchanged (Hazard
  A), no `PARTIAL`. `call_dream_llm`, the cascade and the circuit breaker are
  untouched.
- `_aggregate_run` records `passes_good`/`passes_total`, and `finalize_cycle`
  merges rather than overwrites `summary_json`, so a 5-of-6 DEGRADED run reads
  differently from a 1-of-6 one. It renders on the run-table
  `.badge.state-DEGRADED` — *not* `.chip`, which is what the spec assumed.

**Independently re-verified 2026-08-08** (review stage, §1 item 3), against
the repo rather than the report: guard and call site read as described;
`ATTEMPT_STATES` diff empty; 806 passed / 1 skipped reproduced; ruff 18 + 4 +
14 = 36 on `dream_runner.py` / `traum_state.py` / `traum_controller.py`,
identical before and after; new test files ruff-clean. Break/restore
reproduced from scratch — reverting the `not raw_proposals` clause turns
exactly two tests red
(`test_1_reverify_succeeds_demote_blocked_attempt_is_succeeded`,
`test_narrative_mentioning_dreamer_unavailable_does_not_raise_when_proposals_exist`),
restoring returns an empty diff and green.

Two corrections to the implementer's report, both open:

1. **The survey of the other passes is wrong for two of the three.** `dedup`
   (per-batch loop, `DEDUP_LLM_BATCH_SIZE`) and `error-cluster` (per-cluster
   loop) are *not* "single linear pipelines" — each makes one independent
   `request_dream_envelope` call per batch/cluster and appends the failure
   note to a shared `narrative_lines`, which is precisely the shape that
   caused this bug. They are protected from the data loss anyway, because the
   guard fix is global; what they lack is per-sub-pass reporting, so a dedup
   run that lost the dreamer on 1 of 4 batches is indistinguishable from one
   where all four ran. Extending `sub_passes` to both is small and should
   follow. Only `patterns` genuinely does not qualify — it is mechanical and
   makes no LLM call at all.

2. **The 1 skipped test is a `PATH` artifact, not a missing interpreter.**
   The report flags it honestly as "no `node` on this host"; in fact `node`
   v22.22.3 is at `~/.local/bin/node`, and with it on `PATH` the JS syntax
   check **passes**. The suite is under-reporting itself. Fix the test
   environment's `PATH` (or widen the `shutil.which` lookup) so the run is a
   clean 807.

**Superseded — original framing:** *honour the NULL/BLOCKED distinction
(~1 session). A pass that examined the corpus and found nothing is `NULL`;
one that could not examine it is `BLOCKED`. Today they are conflated, which
is why the run table is hard to read. The manual already specifies the
correct semantics, so this is making the code match its own documented
contract.* — accurate about the symptom, wrong about the cause.

**R5 — collapse the proposal state machine** *(1–2 sessions)*. **The gate has
lifted.** It was "do not restructure a state machine whose real behaviour is
barely observed"; as of 2026-08-09 production has used **six** of the ten —
`APPLIED`, `PENDING`, `REJECTED`, `SUPERSEDED`, `SYSTEM_REJECTED`, `EXPIRED` —
across 8 runs since dreaming went manual, including a full six-pass cycle and
nine applied diagnoses.

Six of ten is a different question from four of ten: the surviving four now
need a reason to exist rather than an absence of evidence. Do **not** start
until item #1 lands, though — the duplicate-diagnosis fix turns on
`SUPERSEDED` firing where it currently does not, which will change the
distribution again. Restructure after that has run for a few cycles, not
before.

**R6 — split `dream_runner.py`** *(4,550 lines, later)*. Same method as
the D7 work that took `goethe.py` from 6,565 to 2,109 lines. Explicitly
last. D7's lesson holds: do not restructure code whose runtime behaviour
you cannot observe, and TRAUM's runtime is one DEGRADED run old.

---

## 4. P2 / P3 — the ruff backlog

147 findings, triaged and assigned per-agent in
`docs/P2-P3-ASSIGNMENT-PLAN.md` (20 auto-fixable). Mostly `BLE001` broad
exception handlers.

Worth doing; not worth doing first. It improves error handling in code
that already works, whereas everything above either fixes something broken
or tells us what to fix next. Good filler work for a session with no
clear larger goal, and a good task to hand to LSE with explicit criteria.

---

## 5. Standing items

- **BW_PASSWORD leak** — parked by explicit decision ("nothing for now").
  Not to be actioned without a fresh instruction.
- **Quarantined episodes** —
  `/opt/local-se/episodes-quarantine-method_raises-20260801/` (67 files)
  can be deleted once you are satisfied nothing real was caught. Kept
  deliberately: the purge moved rather than destroyed.
- **`node5090` registry entry is stale** — `agent_port 8081`,
  `agent_type "lmstudio"` describe software decommissioned fleet-wide.
  Flagged in `goethe_node.py` since 2026-07-29. Run
  `check_node_agent_drift("node5090")` while the node is awake and correct
  it from what is actually there.
