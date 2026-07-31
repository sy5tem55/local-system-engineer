# P2 / P3 — work assignment by agent

> 2026-07-31 · Backlog: `docs/RUFF-TRIAGE-2026-07-31.md` (147 findings).
> Assignment logic is grounded in what each agent measurably did well and
> badly during D1–D8, not on general reputation.

---

## 0. Read this first: P2 is not the highest-value next task

TRAUM **R1–R3** should come before any of this. Evidence:
`docs/TRAUM-ANALYSIS-2026-07-31.md` — the learning loop has completed **zero**
cycles in production, produced **zero** proposals, and 21 of 32 attempts are
blocked on a dependency nothing satisfies. P2 makes error handling in working
code slightly better; R1–R3 makes a dead subsystem run at all, in hours.

P2/P3 are worth doing. They are not worth doing *first*.

---

## 1. What each agent demonstrated this week

| Agent | Did well | Failed at | Therefore |
|---|---|---|---|
| **LSE (local planner)** | D1, D2, D3, D6, D8 — mechanical, well-specified, checkable work at volume. D6 ran 24 planned steps to completion. | **D4**: reported `ruff --select BLE001 → 0 violations` and declared success, while the full ruleset showed **9 × F821** crash paths *it had just introduced*. It ran the narrow check that confirmed its own work. | Give it work where **correct is mechanically checkable**, and mandate the exact verification command. Never give it work where the judgement *is* the deliverable. |
| **Sonnet 5** | D7 (4 extractions, 6,565→2,109 lines, 39 tools invariant), D5 gate fixes, byte-verified AST moves, differential replay over 10,830 commands. Caught its own wrong-file edit and its own false severity claim. | Overstated F821 as a live crash bug until a reverted-fix test disproved it. Self-corrected in-repo. | Give it **delicate mechanical work that needs verification discipline** — refactors, per-site fixes in live code, anything where "prove it fails first" matters. |
| **Opus 5** | Produced the D6 prompt and D7 plan; the coupling-ordered strategy (NetSec→Node→Planner→Web) was right and held. | The D7 plan's membership estimate was **18 methods; truth was 34** — a keyword scan presented as ground truth. | Give it **design, ordering, and classification criteria**. Require it to state how a count was derived, and have the executor re-derive it. |

**The rule that follows:** LSE executes what is specified; Sonnet executes what
is delicate; Opus decides what "correct" means. Whoever writes the criteria
must not be the only one who checks them.

---

## 2. P2 — 119 × BLE001, grouped by risk

| Group | Files | Count | Assign | Why |
|---|---|---|---|---|
| **A. Live tool surface** | `goethe_mcp.py` 11 · `goethe_kb.py` 19 · `goethe_perms.py` 3 · `pfsense_tools` 8 · `net_discovery` 2 | **43** | **Opus plans → Sonnet executes** | `goethe_mcp.py` is the loader D7 just reshaped: a swallowed exception there hides a mixin import failure as "tool missing". `goethe_perms.py` is the permission backend — security-adjacent, and D5 already found one dead guard there. |
| **B. Console** | `goethe_ui.py` | **14** | **Sonnet** | Its documented contract is *"a UI failure must never affect the MCP surface"* — so several blind excepts are **correct by design**. Distinguishing those from real swallowing is judgement, not pattern-matching. |
| **C. TRAUM control plane** | `traum_controller.py` 12 · `traum_state.py` 3 | **15** | **DEFER** | Never ran in production. Do not harden error paths you have never seen execute. Revisit after R1–R3 produce real runs. |
| **D. Dream pipeline** | `dream_runner.py` 18 · `dream_digest.py` 9 · `dream_apply.py` 6 | **33** | **DEFER** | Same reason, plus this is the R6 refactor target. Doing BLE001 first guarantees redoing it. |
| **E. Peripheral scripts** | `pfsense_log_gateway` 5 · `context_monitor` 3 · `download-monitor` 2 · 4 × 1-off | **14** | **LSE** | Standalone scripts, no import into the tool surface, failure is visible and local. Exactly the mechanical/checkable profile LSE is good at. |

**Deferring C+D removes 48 of 119 (40%) on the honest grounds that the code
has no observed runtime.**

## 3. P3 — 28 cosmetics

| Rule | Count | Assign |
|---|---|---|
| F401 unused import | 16 | **LSE**, with carve-outs |
| F541 f-string no placeholder | 9 | **LSE** |
| F841 unused local | 3 | **LSE** |

**Mandatory carve-outs — do NOT blanket `--fix`:**
- `context_monitor.py:37-40` — `rich.*` imports may be deliberate availability
  probes; removing them can change behaviour. Leave, or convert to
  `importlib.util.find_spec`.
- `portrait_3d_pifuhd.py` (5) — vendored third-party. Do not touch.
- `traum_state.py:1827`, `dream_apply.py:1201` — already verified as unused
  return values of side-effecting calls. Leave the call, drop the binding only.

---

## 4. Assignment summary

| Work | Agent | Size |
|---|---|---|
| **TRAUM R1–R3** (do this first) | **Opus** designs · **Sonnet** implements | hours |
| P2 Group A — tool surface + loader | **Opus** criteria · **Sonnet** execution | 43 sites |
| P2 Group B — console | **Sonnet** | 14 sites |
| P2 Group E — peripheral scripts | **LSE** | 14 sites |
| P3 — cosmetics with carve-outs | **LSE** | 28 sites |
| P2 Groups C + D — TRAUM/dream | **deferred** until the loop runs | 48 sites |

---

## 5. Non-negotiable process for whoever executes

Carry forward verbatim from D4/D6/D7 — every one of these was learned by
something going wrong:

1. **Full ruleset, never one rule.** `ruff check tools/` — not
   `--select BLE001`. D4's clean narrow run hid 9 crash paths.
2. **Verify the binary.** `/home/sy5/miniforge3/bin/ruff`. It is **not** in the
   owui venv; `/home/sy5/owui/bin/python3 -m ruff` fails with "No module named
   ruff", so a report claiming a clean run from that interpreter did not make
   one.
3. **Re-lint after every batch.** Narrowing an except is what *introduces*
   F821. 4–6 sites per batch, `py_compile` + full `ruff` between batches.
4. **Classify each site in writing before editing:** (a) intentional degrade →
   keep, add `# noqa: BLE001` **and** a justification **and** a `self._log`
   call; (b) narrow to the real exception type; (c) let it raise.
5. **Prove a guard fails before trusting it to pass.** The mirror-sync guard
   silently watched 1 of 7 modules; the F821 "fix" was validated only because
   the test was re-run against reverted code and did *not* fail.
6. **Full suite green before and after:** `/home/sy5/owui/bin/python3 -m pytest
   tests/ -q` — currently **590 passed**. Tool surface must stay **39**.
7. **State what is unverified.** A green suite proves absence of regression in
   covered paths only; network and hardware paths are not covered.
