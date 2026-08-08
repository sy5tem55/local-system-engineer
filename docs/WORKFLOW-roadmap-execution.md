# Workflow — executing the roadmap

> 2026-08-02. How a roadmap item goes from entry to ticked-off.
> Companion to `docs/WORKFLOW-thread-handover.md` (how to hand work over).
>
> Governing tension, stated by the operator: **choose the most efficient model
> for the task, never at the expense of reliability.**

---

## 0. The correction this document exists to make

The obvious reading of "efficiency vs reliability" is *harder task → bigger
model*. That is wrong, and this project has the evidence.

Opus is the most capable tier available here, and during 2026-07-31 to 08-02
it was wrong about the node3090 wake procedure **three times**, wrong about
why the Console appeared not to update, and wrong about R1's founding premise
(it assumed node3090 was the primary dreamer; node4090 — which is LUCIFER
itself — is). None of those were fixed by thinking harder. Each was fixed by
a measurement, or by the operator supplying a fact.

**Reliability does not come from model tier. It comes from verification.**
Tier and verification depth are two separate dials, and conflating them is
how a project ends up paying for a large model and still shipping a wrong
premise.

So: pick the **lowest tier that can do the work**, and set verification depth
from **what it costs to be wrong**, independently.

---

## 1. Dial one — model tier

Routing is grounded in measured performance on this codebase, not reputation.

### LSE — local Qwen3.6 27B *(free, fastest, always available)*

**Evidence for:** wakes node3090 6/6 consecutively from a KB procedure;
executes known runbooks reliably; good at isolated single-function work.

**Evidence against:** in D4 it ran a *narrow* ruff check, declared success,
and introduced 9 F821 crash paths. Session-learnings 2026-06-07 records it
losing cross-file invariants — wrong IPs, tier edges dropped — needing three
correction passes.

**Route here when:** the task is fully specified, single-file or mechanical,
and an existing test or probe proves it. Fact-gathering, running a documented
procedure, P3 cosmetic lint, bulk rote edits with a green suite.

**Never route here:** security gates, anything with unstated invariants,
anything where "looks done" and "is done" can diverge silently.

**Never route here — writing the test that guards its own work.** Measured
2026-08-08 on roadmap #7 (SUPERSEDED vs QUARANTINED), a deliberate calibration
run. The *production edit was correct* — both files, including the
`(failure_count||0)` guard for the live `None` case, `esc()` on the tooltip,
correct branch order, no new CSS, no doc-id parsing out of free text. For a
fully-specified mechanical edit it passed cleanly.

Its **test was vacuous**: it string-matched the source for `"SUPERSEDED"`,
`"QUARANTINED"` and their relative position, and never evaluated the branch.
Mutating the condition from `===0` to `!==0` — exactly inverting the
behaviour — left it green. A gate that cannot fail for the reason it exists
is not a gate. Replaced with three behavioural tests that execute the shipped
ternary in node; both mutations now fail, and dropping the `||0` guard fails
only the `None` fixture.

Its **numbers were wrong, but its failures were real** — and the reviewer
(Opus) got this wrong first. It cited baseline 781 against an actual 830, and
attributed failures in `test_kb_contracts.py` to "pre-existing" issues. An
exclusive run showed 831 passed, so the failures were initially called
fabricated. That was unfair. `test_kb_contracts.py` is an Elasticsearch
integration suite that creates and drops a shared `lse-kb-test` index; two
overlapping pytest runs collide with `resource_already_exists_exception` and
`index_not_found_exception`. Run alone it is 91/91 green. The LSE observed
something real and misdiagnosed its cause; the reviewer then misdiagnosed the
misdiagnosis by trusting a single clean run.

**Two operational rules follow.**
1. An LSE verification claim carries no information *by itself*. Re-run the
   suite — but re-run it **exclusively**, and check `pgrep -af pytest` first.
   Every baseline in this repo is only valid for a run with sole access to
   Elasticsearch.
2. Route the edit to the LSE; write the test yourself or route it to Sonnet.

### Sonnet 5 High — the workhorse

**Evidence for, this session, 3 for 3:** held the 39-tool invariant across a
four-mixin extraction (D7); on the manifest-prune task caught two real bugs
in its own first attempts *by running the suite rather than trusting the
diff*; on the privilege-gate task caught the `"" in "-/_."` empty-string trap
and the `/usr/bin/sudo` path case, and **declined to widen an exemption to
satisfy a literal spec line** because doing so would have reopened
`sh -c "sudo id"`. That last one is judgment, not compliance.

**Evidence against:** overstated one severity claim in D7 until a
reverted-fix test disproved it.

**Route here when:** implementing from a written spec; multi-file work with
invariants; security-adjacent work **where the spec already names the
hazards**. This is the default tier for roadmap items.

### Opus 5 High — reserved

**Route here when:** writing the spec (hazard identification is the scarce
skill — naming a trap costs three sentences and saves an afternoon);
architectural decisions; unknown-unknowns; and **independent verification of
high-stakes work**.

**Do not route here** merely because a task feels big. A big task with a good
spec is a Sonnet task.

---

## 2. Dial two — verification depth

Set from the cost of being wrong, **independently of tier**.

| Level | What | Use for |
|---|---|---|
| **V0** | Invariants only — py_compile, ruff, full suite | cosmetic, reversible, no behaviour change |
| **V1** | V0 + break-and-restore on load-bearing tests | anything adding or touching a guard |
| **V2** | V1 + independent adversarial probe, written **without reading the implementer's tests** | security, destructive ops, corpus/state mutation, anything whose output drives later decisions |
| **V3** | V2 + live runtime proof | any claim about runtime behaviour |

**V2 earns its cost.** On the corpus-purge task an independent probe — mixed
files passed explicitly, four path-traversal shapes, survivor checks —
confirmed safety the implementer's own tests could not, because it did not
inherit their assumptions. On the privilege gate it caught that a
"regression" was in fact the intended fix.

**V3 is the one people skip.** R1 passed every test and still had a false
negative: it polled `/health` for a service nothing starts on boot. Only a
live 03:32 run exposed it — node3090 had woken in 29 seconds while the script
declared failure for five minutes.

**Rule:** never report runtime success on test-only evidence. State which is
which, explicitly, every time.

---

## 3. The loop, per roadmap item

1. **Classify** — tier from §1, verification level from §2. Write both down
   before starting; deciding afterwards is how V-levels get quietly demoted.
2. **Spec** (Opus) unless one exists and still holds. Six sections:
   task+evidence, ground truth marked verify-don't-trust, hazards before
   design, what to implement + what must not change, named tests flagging the
   load-bearing ones, invariants with exact binary paths.
3. **Implement** at the chosen tier, in a fresh thread, using the handover
   prompt template in `WORKFLOW-thread-handover.md` §1. *(If you had to write
   a spec, start fresh; if a spec would be redundant, flip in-thread.)*
4. **Self-verify** to the chosen level; report what was proven at runtime
   versus by test.
5. **Independently verify** (V2+) from a different context. Do not read the
   implementer's tests first.
6. **Compound** — debrief anything non-obvious into
   `kb/session-learnings.md`, then `python3 rag/09-index-session-learnings.py`
   so it is retrievable rather than write-only.
7. **Close** — mirror sync if a watched module changed, commit with
   `git commit -F`, hand the operator the push command, tick the roadmap.

**Budget:** a well-specified single-file item should land in ~15–30
tool-using turns. Past ~40 with no working implementation, the spec is wrong,
not the model — stop and report the blocker.

---

## 4. Worked example — the next item, end to end

**Item:** node facts, model inventory, profile matcher
(`docs/SPEC-node-facts-and-profile-matcher-2026-08.md`, Layer 0+1 of §1b).

**Tier: Sonnet 5 High.**
- *Not LSE:* the obvious implementation is a flat cmdline diff, which is
  precisely Hazard A. Getting the three-class flag taxonomy right is judgment
  the spec can describe but not mechanise, and a wrong `exact` verdict would
  propagate into every later profile decision.
- *Not Opus:* the spec exists and names all four hazards. Sonnet has executed
  three comparable specs this session without a miss.

**Verification: V2, plus V3 on one claim.**
- V2 because the matcher's output drives Layer 3 profile decisions — a wrong
  verdict is expensive and silent.
- V3 on "it reports reality": run it against live LUCIFER and paste output
  verbatim. If node3090 is asleep, that is a valid result — show it.

**Acceptance:** 728-baseline suite green; ruff not increased; break-and-restore
on tests 2 and 6 reported; verbatim first real run; every ground-truth row
that turned out wrong called out.

**Then compound:** the fleet moves fast — the live engine config changed
twice during spec authoring — so any surprise goes into session-learnings and
gets indexed.

---

## 5. Queue after it

Ordered by return, with tier and verification pre-assigned so the decision is
not re-litigated each time.

| # | Item | Tier | V | Why this tier |
|---|---|---|---|---|
| 1 | node facts + matcher *(spec'd)* | Sonnet | V2+V3 | judgment in taxonomy; output drives later decisions |
| 2 | Disk at 82%, ~7 GB/day | LSE | V0 | pure fact-gathering; findings are self-evidencing |
| 3 | Wake → SSH → start engine → poll | Sonnet | V3 | live behaviour is the whole point; needs a real sleeping node |
| 4 | Retrieval eval set for profile questions | Opus spec → LSE runs | V1 | defining "good enough" is judgment; running evals is mechanical |
| 5 | Web/community data quality (firecrawl, camoufox on node3090) | Sonnet | V2 | the expensive layer; gated on #4 existing so it has an exit condition |
| 6 | `error-remedy` proposal type | Sonnet | V1 | schema change with a clear contract |
| 7 | SUPERSEDED vs QUARANTINED display | LSE | V0 | display-only; data already carries the distinction |
| 8 | Human Gate legibility | Sonnet | V1 | UX judgment, low blast radius |
| 9 | `/etc` change automation | Opus spec → Sonnet | V2 | root-write primitive; the failure mode is over-generality |
| 10 | P2/P3 ruff backlog (147) | LSE | V0 | mechanical, green suite proves it |

**Not on this list, deliberately:** multi-agent orchestration frameworks.
A framework coordinates capabilities you already have; the capabilities are
the gap. Revisit after #1–#5, with real data about where coordination hurts.
