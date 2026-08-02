# Roadmap — after TRAUM R1–R3

> 2026-08-01. Ordering rationale: TRAUM has just produced its first real
> output but has still never completed a clean cycle. Several items below
> are deliberately gated on observing more real runs rather than acting
> now on a design whose production behaviour is barely observed.

---

## 0. Immediate — run cycles, change nothing

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

---

## 1. Near-term, small, well-understood

These are each a session or less and do not depend on more TRAUM data.

**Prune the manifest on corpus deletion.** `build_manifest()` never
removes rows for files that no longer exist (found 2026-08-01 during the
`method_raises` purge — 67 ghost rows survived a rebuild). Any deletion
path must prune explicitly, or analysis keeps seeing sessions that aren't
there. Small fix, real correctness bug.

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

**Give `error-cluster` a correctly-shaped output type.** Raised
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

1. **Index `session-learnings.md` into the KB.** Chunk per `## Session`
   entry so retrieval returns one incident, not a 1,300-line file. Tag
   `source_tier` honestly — these are verified post-hoc observations, not
   ground truth. Once indexed, `search_kb` surfaces them and the loop closes.
   This is the single highest-leverage item on this list: the content already
   exists and is good; it is simply unreachable.

2. **Add a repo-root agent brief.** `docs/WORKFLOW-thread-handover.md`
   already is one in substance — tool-loading preamble, when to flip vs start
   fresh, turn budget, the six sections a spec needs, the verification rules.
   It is not in the conventional location or name, so nothing loads it
   automatically.

3. **Codify the review stage.** Independent re-verification of an
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

**R4 — honour the NULL/BLOCKED distinction** *(~1 session)*. A pass that
examined the corpus and found nothing is `NULL`; one that could not
examine it is `BLOCKED`. Today they are conflated, which is why the run
table is hard to read. The manual already specifies the correct semantics,
so this is making the code match its own documented contract. Best done
now-ish: the 2026-07-31 run finally produced non-blocked outcomes to
distinguish.

**R5 — collapse the proposal state machine** *(1–2 sessions)*. Ten states;
production has ever used four. Explicitly gated on the loop running
first — do not restructure a state machine whose real behaviour is still
barely observed. Still true: one run is not enough.

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
