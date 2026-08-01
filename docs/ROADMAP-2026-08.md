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
