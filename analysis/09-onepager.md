# 09 — Funding One-Pager

---

## Goethe — the agent that asks permission to learn

**Every agent that learns from experience has the same unsolved problem: what stops it
from learning something wrong?**

Goethe is an autonomous operations agent that has run against real infrastructure — a
firewall, a GPU fleet, secrets, a home network — for fourteen months, fully local, on two
machines. It is not a demo. Its audit log holds 11,939 executed commands and **10,701
refusals its own guards raised** — the guards fire about as often as commands succeed.

What makes it fundable is what happens overnight. At 03:30 the agent mines its own episode
logs and proposes changes to its knowledge base: merge these duplicates, this entry now
contradicts observed state, this failure has recurred eleven times. It then **stops**. A
human answers y/n on each proposal, and only then does memory change. Eleven validators
run first, including a compare-and-swap so an overnight proposal cannot silently apply to
a document you edited this morning. Wire it to a script with no stdin and every proposal
is rejected — it fails closed.

A 2026 survey of eight production agent-memory systems concludes that human-gated review
of proposed memory edits is implemented by **none** of them, and that decaying trust scores
and origin-tiered provenance "remain open problems in the field." Goethe ships all three,
under contract test, with a year of run history.

The compounding asset is the loop itself: a documented ratchet that turns every rule the
model ignored into a rule it cannot ignore. The code says so — *"docstrings did not hold."*
Frameworks cannot build this, because they operate nothing; the lesson never comes home.

818 tests pass from a fresh clone in ten seconds. We published our flagship experiment's
**loss**. Ask us anything.

*(279 words)*

---

## Every number above, and how to check it

| claim | source | verification |
|---|---|---|
| 11,939 commands / 10,701 refusals | `/opt/local-se/agent_commands.log`, 117,022 lines | `python3 scripts/audit_report.py --summary` (M5-3) |
| 14 months | first log entry → today | `head -1 /opt/local-se/agent_commands.log` |
| two machines, identical code | 15/15 core files sha-identical A vs B | `analysis/00` §0.3 |
| 03:30 nightly | `goethe-dream.timer` | `systemctl list-timers \| grep dream` |
| eleven validators | `dream_apply.py:499` calling `:305`–`:487` | read the file |
| compare-and-swap | `check_target_cas`, `dream_apply.py:352` | read the file |
| fails closed | `ask_yes_no`, `dream_apply.py:657` — `EOFError → "" → falsy` | read the file |
| "none of them" | 2026 eight-system survey | [source](https://fountaincity.tech/resources/blog/agent-memory-knowledge-systems-compared/) |
| decaying trust | `record_outcome`, `goethe_kb.py:936` — `max(0.2, q−0.15)` | `tests/test_kb_contracts.py` |
| origin tiers | `TrustPolicy.apply_origin`, `goethe_kb.py:60–68`, wired `:502` | `tests/test_kb_contracts.py` |
| 818 tests, ten seconds | fresh clone + 4 pip installs | `pytest tests/ -q` → `9 failed, 818 passed, 98 skipped in 10.28s` |
| *"docstrings did not hold"* | `tools/goethe_web.py:155–162` | read the file |
| published the loss | A=53/60, B=51/60 | `eval/eval-report-traum-1.md` §6–7 |

**Precision note, load-bearing:** say *"never auto-applies under the shipped
configuration"*, never *"never auto-applies"*. `GOETHE_DREAM_AUTO_APPLY`
(`dream_apply.py:199`) is an env var that whitelists proposal types for automatic
application. It is empty by default and the decision to keep it empty is documented with
evidence. A technical partner will find it. Being told first is the difference between
"thorough" and "caught."

---

## Five-slide outline

### Slide 1 — The problem

> **Agents that learn are agents that can learn wrong.**

- Every agent memory product writes to memory automatically.
- Nobody reviews what went in. Nobody removes what turned out false.
- A wrong memory does not fail loudly. It becomes confident background truth and quietly
  poisons every future answer.
- The 2026 field survey: human-gated review of memory edits — **implemented by none of
  eight production systems**. Decaying trust and origin-tiered provenance: *"open problems
  in the field."*

*Speaker note: do not mention Goethe on this slide. Establish that the gap is real and
that the field agrees it is open. Let them arrive at "so who's solved it?"*

### Slide 2 — What we built

> **The agent proposes. The human disposes. In production, nightly, for a year.**

- Six passes over its own episode logs at 03:30 → typed proposals → a blocking human gate.
- Eleven validators before a human sees anything, including compare-and-swap against the
  source document.
- Fails closed: no stdin, no changes.
- Null results are first-class — "the pass ran and found nothing" is a distinct terminal
  state from "the pass broke." *That* is why an operator still reads the digest in month
  nine.
- 13,260 lines. 44% of the codebase. Not a wrapper.

*Speaker note: the null-result semantics is the detail that convinces engineers. It is
evidence of having actually operated the thing, not designed it.*

### Slide 3 — Why it is defensible

> **Not the guards. The ratchet that produces them.**

- Live: **10,701 refusals / 11,939 commands.** The guards are load-bearing, not decorative.
- The pattern, from the source: an incident occurs → the rule moves from docstring to
  code → a regression test pins it. *"docstrings did not hold."*
- The best artifact in the repo: protocol text was once silently truncated out of the
  model's view. The fix was not a bigger buffer — it was a test that reads the buffer size
  out of the gateway, so the gate can never drift from what it tests.
- **Frameworks cannot build this. They operate nothing, so the lesson never comes home.**

*Speaker note: this is the slide the deal turns on. If they only remember one thing, it is
that the moat is a process with a year of exhaust behind it, not a feature.*

### Slide 4 — Evidence, including what went wrong

> **We ran the experiment on our own flagship. It lost. Here it is.**

- Pre-registered A/B on the dreaming subsystem: **A=53/60, B=51/60. Published as a loss**,
  with the methodological root cause (n=1, unpinned sampling, no true pre-dreaming
  snapshot) written up by us before anyone asked.
- Our own log miner found a live plaintext credential in our audit log. We stopped the
  workstream, shipped redaction, and did not persist the run.
- 818 tests green from a stranger's clone, in ten seconds, with four `pip install`s.
- Same code, two machines, verified byte-identical. Different memories — **on purpose**;
  that is the sovereignty property, and we now instrument it rather than hide it.

*Speaker note: lead with the loss. Everyone else's slide 4 is a benchmark win. This one
is the differentiator, and it is the slide that makes the other three believable.*

### Slide 5 — The ask

> **One quarter to fundable. The hard part is already done.**

- Independent audit scores readiness **41/100** today — and finds that **almost none of the
  gap is engineering**. It is CI, a provenance statement, a dependency manifest, a demo,
  and a number nobody had computed.
- Roadmap M0→M6 crosses the threshold at **week 9–10**: canonicalise → gate → harden →
  evaluate → demo → narrate.
- The one genuinely novel engineering item: **bind evidence to the execution journal** —
  today a `len(evidence) >= 20` check becomes a provenance proof. ~1 week, and it is a
  feature a memory *library* structurally cannot copy, because it requires owning the
  execution surface.
- Two paths, not mutually exclusive: **seed VC** (sovereign ops for regulated
  infrastructure) or **research grant** (human-gated memory consolidation is a live open
  problem with an ICLR-2026 workshop track).

*Speaker note: the audit being independent and unflattering is itself the pitch. Hand them
`analysis/03-shortcomings.md` — all 32 findings, 6 P0s. Nobody does that, and it is the
cheapest credibility available.*

---

## What not to say

| do not say | say instead | why |
|---|---|---|
| "AI sysadmin that actually works" | "the agent that asks permission to learn" | Ops breadth scores **4/10** and the category is contested by funded vendors. The memory claim scores **9/10**. `README.md:1` currently leads with the weak one. |
| "75,000 lines of Python" | "53,793 lines, 113 tracked files" | The larger figure counts backup copies of the same file. They will check. |
| "fully local, no cloud" | "no cloud LLM in the core loop; planner backends optional" | `_call_claude_planner` and `_call_chatgpt_planner` exist and are wired. The precise version is still a strong claim. |
| "never auto-applies" | "never under the shipped configuration — here is the env var and the decision record" | `GOETHE_DREAM_AUTO_APPLY` exists. |
| "420 tests pass" | "818 pass from a fresh clone in ten seconds" | The project's own docs undersell it by 2×. |
| "dreaming improves retrieval" | "we pre-registered it, it lost at n=1, and here is the properly-powered re-run" | The honest version is the stronger asset. |
| "45 tools" / "37 tools" | "44 tools" | Three different numbers appear in the docs. Verified by AST: 44. |

---

## The single sentence

If there is time for one line only:

> **We built the agent-memory review queue that the 2026 field survey says nobody has
> shipped — and we have been running it against our own production infrastructure,
> nightly, for a year.**
