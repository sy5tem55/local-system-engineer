# D7 — mixin extraction, atomized plan for Sonnet 5

Grounded on a live AST scan of `tools/goethe.py` @ `feb7911`, 2026-07-31.
Execute steps **in order**. Each step is independently verifiable; do not batch.

---

## Why the audit's original order is wrong

The D1–D8 audit proposed extracting `PlannerMixin` first because it is the
biggest. A coupling scan says otherwise — measured calls from each candidate
group to methods *outside* that group:

| Candidate | Methods | Lines | External deps | Risk |
|---|---|---|---|---|
| **NetSec** | 4 | 433 | `_log` only | **lowest** |
| **NodeLifecycle** | 6 | 572 | `_log`, `_live_node_profile` | low |
| **Planner** | 18 | 1038 | (largest surface) | medium |
| **Web** | 8 | 583 | 8 distinct helpers | **highest** |

Extract in ascending risk: **NetSec → NodeLifecycle → Planner → Web**. The
first extraction is a pilot that proves the pattern end-to-end on 433 lines
instead of 1038; if the seam is wrong, you find out cheaply.

**Do NOT extract the safety group** (`execute_command`, `write_file`,
`read_file`, `sudo_delegation_block`, `_validate_command_safety`,
`_is_allowed_*`, `_norm`, `_log` — 13 methods, 753 lines). It stays in `Tools`.
Reasons: it is the product wedge; D5 (2026-07-31) just found four live bypasses
in it; and `_log` / `_norm` / `_is_allowed_*` are called by every other group,
so it is the shared base, not a leaf. Moving the most security-sensitive code
while it has known open holes is the one change here that could actually hurt.

Expected end state: `Tools` retains the ~33 shared/uncategorised methods
(~1446 lines) plus safety (~753) ≈ 2200 lines, down from 5692.

---

## Invariants that must hold after EVERY step

Run all four. A step is not done until they pass.

```bash
cd ~/projects/local-system-engineer
/home/sy5/owui/bin/python3 -m py_compile tools/goethe.py
/home/sy5/miniforge3/bin/ruff check tools/                 # full ruleset, miniforge binary
/home/sy5/owui/bin/python3 -m pytest tests/ -q             # 548 passed, 10 xfailed
/home/sy5/owui/bin/python3 -c "
import importlib.util, inspect
s=importlib.util.spec_from_file_location('g','tools/goethe.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
pub=[n for n,_ in inspect.getmembers(m.Tools, inspect.isfunction) if not n.startswith('_')]
print('public tools:', len(pub)); assert len(pub)==39, 'TOOL SURFACE CHANGED'"
```

`ruff check tools/` (the directory, not just `goethe.py`) — new mixin files must
be linted from the moment they exist.

---

## Hazards specific to this refactor

1. **`self.valves` is defined on `Tools`, not on any mixin.** Every extracted
   method references it. Mixins must never define or instantiate `Valves`; they
   read `self.valves` and are only ever used *through* `Tools`. Add a
   `TYPE_CHECKING`-only protocol if type hints complain — never a runtime import
   back into `goethe.py`.
2. **Import direction is one-way.** `goethe.py` imports mixins. A mixin must
   never import `goethe.py` — that is a cycle and will fail at load. This is the
   same rule `goethe_kb.KBMixin` already follows; copy that file's shape.
3. **`_log` is called by every group.** It stays on `Tools`. Mixins call
   `self._log(...)` and rely on MRO. Do not duplicate it.
4. **Class-level attributes must travel with their methods:**
   `_SSH_BASE_OPTS`, `_SSH_CTL_PATH` → NetSec ·
   `_NODE_REGISTRY`, `_PROFILE_FLAGS` → NodeLifecycle ·
   `_GEMMA_MODELS`, `_PLANNER_CONTRACT`, `_PLANNER_KB_*` → Planner.
   Leave the safety constants (`_ALLOWED_*`, `_BLOCKED_*`, `_PRIVILEGED_*`,
   `_WRITE_OPS`, `_HEREDOC_PATTERN`) on `Tools`.
   `_NODE_REGISTRY` is read as `self._NODE_REGISTRY` (D6 wired it that way) —
   MRO keeps that working, but verify explicitly, because a method-local
   definition would break silently at runtime and no test covers it.
5. **The three AST guard tests only scan files listed inside them.** New mixin
   files escape the guards unless you add them:
   - `tests/test_except_clause_resolvable.py` → `_TARGETS`
   - `tests/test_topology_literals.py` → its scanned-file list
   Add the new filename in the SAME step that creates it. A mixin that is not in
   `_TARGETS` is unguarded code.
6. **`goethe_mcp.py` registers tools by inspecting the instance.** Inherited
   methods still register, and the docstring 1024-char window still applies.
   Do not reflow or re-indent any docstring while moving a method — D3 pinned
   those contracts and `test_docstring_mcp_truncation.py` will fail if a
   contract keyword slips past char 1024.

---

## Steps

### Step 1 — baseline
Record the pre-refactor state: `git rev-parse HEAD`, full test output, tool
count, and `wc -l tools/goethe.py` into `/tmp/d7_baseline.txt`.
**Verify:** file exists, records 548 passed / 10 xfailed and 39 public tools.

### Step 2 — study the existing seam
Read `tools/goethe_kb.py` (the `KBMixin` already in use) and write
`/tmp/d7_pattern.md` describing: how it declares the class, how it accesses
`self.valves`, how `Tools` inherits it, and its import direction.
**Verify:** the note names `KBMixin`, states the import direction as
mixin ← goethe.py, and confirms it does not import `goethe.py`.
**No code changes in this step.**

### Step 3 — create `tools/goethe_netsec.py` (pilot)
Move `_ssh_opts`, `ssh_run`, `ssh_script`, `nmap_summary` and the class
attributes `_SSH_BASE_OPTS`, `_SSH_CTL_PATH` into a new `NetSecMixin`, byte-for-byte —
no logic edits, no docstring edits, no reformatting. Add the module docstring
explaining what it is and that it must not import `goethe.py`.
**Verify:** `py_compile` on the new file; it contains exactly 4 `def ` at class level.

### Step 4 — wire the mixin in
In `goethe.py`: add the import next to the existing `goethe_kb` import, change
`class Tools(KBMixin):` to `class Tools(KBMixin, NetSecMixin):`, delete the four
moved methods and the two moved attributes.
**Verify:** all four invariants above. Tool count still 39.

### Step 5 — guard the new file
Add `goethe_netsec.py` to `_TARGETS` in `tests/test_except_clause_resolvable.py`
and to the scanned list in `tests/test_topology_literals.py`.
**Verify:** both tests pass and demonstrably scan the new file (temporarily
inject a bad literal, confirm failure, revert — state that you checked).

### Step 6 — runtime proof, not just import proof
The suite does not exercise SSH. Prove the moved code still resolves at runtime:
```bash
/home/sy5/owui/bin/python3 -c "
import importlib.util,inspect
s=importlib.util.spec_from_file_location('g','tools/goethe.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m); t=m.Tools()
print(t._SSH_BASE_OPTS, t._SSH_CTL_PATH)
print(inspect.signature(t.ssh_run))
print(t._ssh_opts() if callable(t._ssh_opts) else 'n/a')"
```
**Verify:** attributes print via MRO and `_ssh_opts` executes without
`AttributeError`. This is the check that catches a class attribute left behind —
the D4/D5 failure mode where tests pass and production breaks.

### Step 7 — commit the pilot
`git add tools/goethe_netsec.py tools/goethe.py tests/` and commit alone.
Message states line counts before/after and that behaviour is unchanged.
**Verify:** `git show --stat` shows only those files.

### Step 8 — `NodeLifecycleMixin`
Repeat steps 3–7 for `wake_node`, `query_node_agent`, `check_node_agent_drift`,
`start_node_agent`, `stop_node_agent`, `shutdown_node`, plus `_NODE_REGISTRY`
and `_PROFILE_FLAGS`. `_live_node_profile` is an external dependency: leave it on
`Tools` and call it via `self`.
**Verify:** as step 6, plus explicitly
`t._NODE_REGISTRY["node3090"]["hostname"] == "node3090.home.arpa"` — D6 rewired
the reddit fallback to read this through `self`, so a broken move silently
breaks browser rendering with no test coverage.

### Step 9 — `PlannerMixin`
The 18 planner methods plus `_GEMMA_MODELS`, `_PLANNER_CONTRACT`,
`_PLANNER_KB_CHAR_BUDGET`, `_PLANNER_KB_MAX_DOCS`, `_PLANNER_KB_TIMEOUT_S`.
Keep `_augment_context_with_kb*` WITH the planner — it is planner-only and holds
the pinned STACK-MAP grounding.
**Verify:** as before, plus prove grounding still works end-to-end:
```bash
/home/sy5/owui/bin/python3 -c "
import importlib.util
s=importlib.util.spec_from_file_location('g','tools/goethe.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m); t=m.Tools()
out=t._augment_context_with_kb('stack map','marker')
assert 'PINNED GROUND TRUTH' in out and 'marker' in out
print('grounding OK')"
```
Also confirm `tests/test_planner_ledger.py` passes — it monkeypatches
`_call_node_planner` and `_augment_context_with_kb` by name on the instance,
which keeps working under MRO but must be verified, not assumed.

### Step 10 — `WebMixin` (highest risk — do last, or defer)
`search_web`, `search_reddit`, `fetch_url`, `get_github_release`,
`verify_source_claims`, `monitor_download`, `_fetch_via_browser`,
`_active_download_guard`. This group has 8 external dependencies
(`_budget_gate`, `_camoufox_scrape`, `_consume_time_banner`, `_extract_pdf_text`,
`_extract_text_from_html`, `_log`, `_parse_reddit_posts`,
`_reddit_browser_fallback`, `_strip_years`).
**Decide first, in writing:** either move the private helpers along with the
group (if nothing else calls them — check first) or leave them on `Tools`.
Record the decision and the evidence in `/tmp/d7_web_decision.md` BEFORE editing.
If more than two helpers are shared with other groups, **stop and report** —
the seam is not clean and forcing it produces worse code than leaving Web in
place. Stopping here is a valid, successful outcome.

### Step 11 — final verification and report
Full invariants, plus `wc -l` on every file, plus a statement of what is now
where. Write `/tmp/d7_report.md` with the before/after line counts, the four
commits, and an explicit list of what was verified only by import versus what
was verified at runtime.

---

## Anti-goals

- Do NOT extract the safety group. It stays in `Tools`.
- Do NOT change any method body, signature, or docstring while moving it. This
  refactor is pure relocation; a diff that shows logic changes has failed.
- Do NOT fix the four D5 xfail holes here. Separate concern, separate change.
- Do NOT reformat, reorder methods, or "tidy" imports beyond what the move
  requires. The review question is "is this the same code in a new file?" and a
  reformatted diff makes that unanswerable.
- Do NOT create a mixin that imports `goethe.py`.
- Do NOT proceed to the next mixin while any invariant is red.
