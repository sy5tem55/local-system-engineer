# Ruff backlog triage — `tools/`, 161 findings

> 2026-07-31 · scope: the 13 modules D1–D8 never touched. The six D7-scoped
> modules (`goethe.py`, `goethe_planner.py`, `goethe_web.py`, `goethe_node.py`,
> `goethe_netsec.py`, `goethe_constants.py`) are clean and stay clean — that is
> what the guards protect.
> Command: `/home/sy5/miniforge3/bin/ruff check tools/` (full ruleset, miniforge
> binary — **not** `owui/bin/python3 -m ruff`, which does not exist and silently
> "passes").

## Summary

| Rule | Count | Class | Action |
|---|---|---|---|
| **F821** undefined name | 7 | fragile, not live (see correction) | **DONE** — hardened |
| F401 unused import | 16 | cosmetic | P3 — auto-fixable |
| F841 unused local | 10 | cosmetic (7 are the F821s) | P3 — auto-fixable |
| F541 f-string, no placeholder | 9 | cosmetic | P3 — auto-fixable |
| BLE001 blind `except` | 119 | judgement-heavy | P2 — per-site triage |

30 of the 161 were auto-fixable. 119 need human judgement.

**Status after this pass: 161 → 147.** The 7 F821 (and the 7 F841 that shadowed
them) are fixed. Nothing in the remaining 147 is a live defect — see the
correction below for why the one candidate turned out not to be.

---

## P0 (CORRECTED) — the 7 × F821 are fragile, but were NOT a live bug

> **Correction, same day.** This section originally claimed these seven were a
> live crash path that destroyed the original exception. **That was wrong, and
> the error was mine.** I "reproduced" it with a snippet that returned the
> lambda *out* of the `except` block — which changes the semantics — and then
> believed the result instead of testing the code as written. The regression
> tests I wrote passed against the reverted fix, which is what exposed it.
> Recorded here rather than quietly edited, because a triage document that
> overstates severity is worse than one that misses something.

All seven are in `goethe_ui.py` (lines 925, 943, 959, 977, 989, 999, 1020):

```python
except (TypeError, ValueError) as exc:
    await self._traum_response(send, lambda: (_ for _ in ()).throw(exc))
    return
```

The lambda re-raises the caught error inside `_traum_response` so its status
mapping (`ValueError` → 400) applies instead of the generic 503 branch.

**Why ruff is right and the code still worked.** Python deletes the
`except ... as exc` binding when the block exits, so `exc` is genuinely
unbound afterwards — ruff cannot prove the lambda is only ever called before
that, so F821 is a legitimate warning about fragile code. But every one of
these `await`s happens *inside* its own except block, so `exc` is still bound
when `asyncio.to_thread` runs the lambda. Verified empirically:

| Shape | Result |
|---|---|
| as written (await inside the block) | `400 bad request: archived must be true or false` |
| lambda escaping the block first | `503 NameError: cannot access free variable 'exc'` |

**Action taken:** changed to `lambda e=exc: (_ for _ in ()).throw(e)`. The
default argument is evaluated at lambda-creation time, while `exc` is bound.
Equivalent today, and still correct if anyone later defers the call past the
block — the exact refactor that would turn this latent fragility into the real
503-and-lose-the-error bug. Clears 7 F821 + 7 F841, taking **161 → 147**.

Two tests added to `tests/test_ui_router.py` pinning the 400-vs-503 contract
across all five query-param paths and the malformed-JSON POST path. Their
docstrings state plainly that they do **not** discriminate between the two
lambda forms — they hold the contract, not the binding.

Severity: this was **P3 hardening**, not P0. The genuine P0 in this backlog is
that nothing here is P0.

## P2 — 119 × BLE001, by file

| File | Count | Note |
|---|---|---|
| `goethe_kb.py` | 19 | in the tool surface via `KBMixin` — highest value |
| `dream_runner.py` | 18 | |
| `goethe_ui.py` | 14 | console |
| `traum_controller.py` | 12 | |
| `goethe_mcp.py` | 11 | **the loader** — a swallowed error here hides tool-registration failures |
| `dream_digest.py` | 9 | |
| `pfsense_tools_v1.0.0.py` | 8 | loaded via `--also` |
| `dream_apply.py` | 6 | |
| `pfsense_log_gateway.py` | 5 | |
| others | 17 | 1–3 each |

Suggested order: `goethe_mcp.py` (11) first — it is the loader, and D7 just
reshaped what it loads, so a blind `except` there could mask a mixin import
failure as "tool missing". Then `goethe_kb.py` (19), the only one of these
inside the live tool surface.

Apply the D4 method exactly: triage each into (a) intentional degrade → keep,
add `# noqa: BLE001` **and** a written justification plus a `self._log` call,
(b) narrow to the real exception type, (c) let it raise. And the D4 lesson —
**after narrowing, re-run the full ruleset**, because narrowing is what
introduced 9 × F821 last time. That is the same rule class as the 7 above.

---

## P3 — 30 auto-fixable

`ruff check tools/ --fix` clears F401 (16), F841 (10), F541 (9) — but do **not**
blanket-apply:

- `context_monitor.py:37-40` imports `rich.*` — these may be deliberate
  availability probes (ruff's own message suggests `importlib.util.find_spec`).
  Removing them could change behaviour if wrapped in `try: import`.
- `portrait_3d_pifuhd.py` (5) is a vendored third-party script — leave it.
- The 7 `goethe_ui.py` F841s are the P0 bug; fix them properly, not by deleting.

Genuinely safe: `goethe_kb.py:18,20`, `traum_controller.py:18,25`,
`download-monitor.py:74`, `pfsense_log_gateway.py:39`, and all 9 F541.

**Checked and cleared:** `traum_state.py:1827` (`run = self.create_run(...)`) and
`dream_apply.py:1201` (`failed = state.finalize_proposals(...)`) are
side-effecting calls whose return value is simply unused — not dropped results.

---

## Recommendation

The F821s are done (hardening, not the crash fix first claimed here — see the
correction above). **147 findings remain and none is a live defect.**

Schedule the 119 BLE001 as a "D9" using the D4 method and its re-lint
discipline, starting with `goethe_mcp.py` (the loader, 11) then `goethe_kb.py`
(19, the only one inside the live tool surface). Cherry-pick the safe half of
P3 alongside it.

Worth carrying forward from this pass: the reason the severity error was caught
was writing the regression test *and then reverting the fix to watch it fail*.
It didn't fail — which is the only reason the mistaken diagnosis surfaced
before it reached a commit message describing a crash that never happened. A
guard you haven't watched fail is a guard you haven't tested; that applies to
one's own conclusions too.
