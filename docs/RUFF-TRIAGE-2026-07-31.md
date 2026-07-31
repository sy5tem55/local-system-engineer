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
| **F821** undefined name | **7** | **live crash path** | **P0 — fix now** |
| F401 unused import | 16 | cosmetic | P3 — auto-fixable |
| F841 unused local | 10 | cosmetic (7 are the F821s) | P3 — auto-fixable |
| F541 f-string, no placeholder | 9 | cosmetic | P3 — auto-fixable |
| BLE001 blind `except` | 119 | judgement-heavy | P2 — per-site triage |

30 of the 161 are auto-fixable. 119 need human judgement. **7 are a real bug.**

---

## P0 — the 7 × F821 are one live bug, seven times

All in `goethe_ui.py`, lines 925, 943, 959, 977, 989, 999, 1020. Identical shape:

```python
except Exception as exc:
    await self._traum_response(send, lambda: (_ for _ in ()).throw(exc))
```

Python **deletes** the `except ... as exc` binding when the block exits (implicit
`del exc`). The lambda is invoked later, inside `_traum_response`, by which time
its closure cell is empty. Reproduced:

```
NameError: cannot access free variable 'exc' where it is not associated
           with a value in enclosing scope
```

This is worse than a crash — **it destroys the original exception.** The handler
meant to report a `ValueError` raises `NameError` instead, so the operator sees
a misleading error and the real cause is gone. It fires only on the error path,
which is why no test caught it and why it has survived: this is precisely the
D4 failure mode — *converting designed graceful degradation into a crash exactly
when the system is already degraded.*

These sit on the TRAUM HTTP control plane, so every one is reachable from a
malformed request body.

**Fix** — bind the exception as a default argument, one line each:

```python
except Exception as exc:
    await self._traum_response(send, lambda e=exc: (_ for _ in ()).throw(e))
```

Default arguments are evaluated at lambda-creation time, while `exc` is still
bound. This also clears the 7 matching F841s, taking 161 → 147.

Risk: minimal, mechanical, and `goethe_ui.py` is not imported by `goethe.py`
(separate process — the :9700 console), so it cannot affect the tool surface.
Worth a live smoke test of the TRAUM endpoints after, since the suite does not
cover this path.

---

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

Do P0 now — 7 one-line changes closing a live crash path that masks real errors.
Everything else is genuine but non-urgent debt; schedule P2 as a "D9" with the
D4 method and its re-lint discipline, and cherry-pick the safe half of P3
alongside it.
