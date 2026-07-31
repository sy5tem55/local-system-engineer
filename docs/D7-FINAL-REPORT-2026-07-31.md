# D7 — mixin extraction, final report

Executed 2026-07-31 against docs/D7-MIXIN-EXTRACTION-PLAN.md (grounded on
`feb7911`). All four planned extractions completed: NetSec -> NodeLifecycle
-> Planner -> Web, in the plan's ascending-risk order. No step was skipped;
Step 10 (Web) was explicitly permitted to stop-and-report instead of
extracting, but the coupling scan came back clean enough to proceed.

## Commits (chronological)

| Commit | Step | What moved |
|---|---|---|
| `10b6b50` | 3-7 | NetSecMixin (pilot): 4 methods + 2 class attrs, 433 lines |
| `dd315c4` | 8 | NodeLifecycleMixin: 6 methods + 2 class attrs, ~572 lines |
| `a841ad5` | 9 | PlannerMixin: 29 methods + 5 class attrs, 1691 lines |
| `ec0ee9a` | 10 | WebMixin: 8 methods + 8 helpers, 995 lines |

## Line counts, before -> after

| File | Before | After |
|---|---|---|
| tools/goethe.py | 5692 (D7 baseline) | 2109 |
| tools/goethe_netsec.py | — (new) | 483 |
| tools/goethe_node.py | — (new) | 692 |
| tools/goethe_planner.py | — (new) | 1691 |
| tools/goethe_constants.py | — (new) | 29 |
| tools/goethe_web.py | — (new) | 995 |
| tools/goethe_kb.py (pre-existing, untouched) | 1624 | 1624 |
| **Total (goethe.py + 5 new mixins)** | 5692 | 5999 |

goethe.py itself: **5692 -> 2109 lines, a 63% reduction.** The plan's own
estimate ("Tools retains ~1446 shared + ~753 safety = 2200 lines") predicted
2200; actual is 2109 — close, the small gap explained by the corrected
(larger) true PlannerMixin/WebMixin membership counts vs. the plan's
undercounted estimates (18 planner methods estimated vs. 34 elements
actual; both group-membership corrections are documented in-depth in each
extraction's own commit message and module docstring).

`Tools`' MRO is now:
`Tools -> KBMixin -> NetSecMixin -> NodeLifecycleMixin -> PlannerMixin -> WebMixin -> object`

## What is now where

- **tools/goethe.py (Tools class, 2109 lines):** the safety wedge
  (execute_command, write_file, read_file, sudo_delegation_block,
  _validate_command_safety, _is_allowed_*, _norm, _HEREDOC_PATTERN,
  _BLOCKED_*, _PRIVILEGED_*, 13 methods/753 lines — deliberately never
  extracted, per the plan's explicit anti-goal and D5's live findings on
  this exact surface) plus the remaining shared/uncategorised methods:
  __init__, Valves, _log, _time_banner, _dream_banner, time_check,
  run_tests, assert_state, pfsense_graphql/pfsense_query/_pfsense_verify/
  _pfsense_cap_response, compact_context, get_context_status,
  mentor_correct/mentor_demote, record_error/record_outcome,
  check_error_kb, and the remaining MCP/vault/permissions glue.
- **tools/goethe_kb.py (pre-existing, untouched):** KBMixin — search_kb,
  index_to_kb, kb_verify, skill_record/skill_outcome/skill_search. The
  original extraction precedent D7 copied its shape from.
- **tools/goethe_netsec.py:** NetSecMixin — ssh_run, ssh_script,
  nmap_summary, _ssh_opts, _SSH_BASE_OPTS, _SSH_CTL_PATH.
- **tools/goethe_node.py:** NodeLifecycleMixin — wake_node,
  query_node_agent, check_node_agent_drift, start_node_agent,
  stop_node_agent, shutdown_node, _NODE_REGISTRY, _PROFILE_FLAGS.
  (_live_node_profile, _parse_llama_cmdline stay on Tools — external deps.)
- **tools/goethe_planner.py:** PlannerMixin — the full planner/task-ledger
  execution loop: planner, plan_step_done, task_checkpoint, task_resume,
  the backend-dispatch chain (_call_node_planner, _resolve_backend_name,
  _call_planner_backend, _openai_style_call, _call_rest_planner,
  _call_chatgpt_planner, _call_claude_planner, oauth token readers), the
  Gemma spawn/stop pair, ledger parsing/normalization, and the pinned
  STACK-MAP grounding (_augment_context_with_kb*).
- **tools/goethe_constants.py:** _LSE_BASE_PATH, _LOOPBACK — zero-dependency
  shared literals, created in Step 9 because two mixins (Planner, Web) both
  needed them and a mixin cannot import goethe.py.
- **tools/goethe_web.py:** WebMixin — search_web, search_reddit, fetch_url,
  get_github_release, verify_source_claims, monitor_download,
  _fetch_via_browser, _active_download_guard, plus 8 helpers
  (_budget_gate, _camoufox_scrape, _consume_time_banner, _extract_pdf_text,
  _extract_text_from_html, _parse_reddit_posts, _reddit_browser_fallback,
  _strip_years).

## Full invariants (final run, 2026-07-31)

- `py_compile`: all 7 files (goethe.py + goethe_kb/netsec/node/planner/
  constants/web) — clean.
- `ruff check tools/goethe.py tools/goethe_netsec.py tools/goethe_node.py
  tools/goethe_planner.py tools/goethe_constants.py tools/goethe_web.py` —
  **All checks passed.** `ruff check tools/` (whole directory, the plan's
  literal invariant command) reports 161 errors, but every one is in files
  D7 never touched (traum_state.py, goethe_mcp.py, goethe_perms.py,
  goethe_ui.py, goethe_kb.py, dream_*.py, context_monitor.py,
  call_hermes_draft.py, pfsense_log_gateway.py, portrait_3d_pifuhd.py,
  traum_controller.py) — confirmed by filtering ruff's own file paths out
  of the run and by `git log` on goethe_kb.py showing its last commit
  (`7fdba10`, D3) predates D7's first commit (`10b6b50`). Pre-existing
  debt, correctly out of scope, not introduced or touched by this effort.
- `pytest tests/ -q`: **560 passed, 10 xfailed** (baseline 548 passed/10
  xfailed -> +12 across the four steps: +3 NetSec pilot guard IDs [Step 5],
  +3 NodeLifecycle guard IDs [Step 8], +3 Planner guard IDs [Step 9], +3
  Web guard IDs [Step 10] — each extension proven to demonstrably scan its
  new file via individually-run parametrized test IDs, not just import
  cleanly).
- Public tool surface: **39**, unchanged (verified via the real
  `inspect.getmembers` scan the plan specifies, not a manual count).
- `Tools.__mro__`: `Tools, KBMixin, NetSecMixin, NodeLifecycleMixin,
  PlannerMixin, WebMixin, object` — matches the intended layering exactly.
- Working tree clean except three untracked D4-era scratch files
  (`tools/goethe.py.bak.d4`, `.d4.fixed`, `.d4.fixed2`) present before D7
  started and never added to any D7 commit.

## Verified only by import vs. verified at runtime

**Runtime-verified (executed live against the real production loader,
`goethe_mcp.load_goethe` + `make_instance`, or an equivalent direct
instantiation of the compiled module):**
- NetSec (Step 6): `t._SSH_BASE_OPTS`/`t._SSH_CTL_PATH` print via MRO,
  `t._ssh_opts()` executes without AttributeError.
- NodeLifecycle (Step 8): `t._NODE_REGISTRY["node3090"]["hostname"] ==
  "node3090.home.arpa"` — the exact D6-rewired reddit-fallback dependency.
- Planner (Step 9): `t._augment_context_with_kb('stack map','marker')`
  returns both `'PINNED GROUND TRUTH'` and `'marker'` — the STACK-MAP
  grounding fix survives the move. `tests/test_planner_ledger.py` (16
  tests) re-run standalone and passing — its `monkeypatch.setattr(instance,
  name, fn)` pattern confirmed working under the new MRO, not assumed.
- Web (Step 10): all 16 moved methods resolve via MRO and are callable;
  `t._NODE_REGISTRY[...]` re-checked (cross-mixin read from
  `_reddit_browser_fallback`); `_fetch_cache`/`_time_banner_emitted`
  instance attributes present; `t._consume_time_banner()` **executed live**
  end-to-end post-move (not just signature-checked), proving the
  cross-mixin call into `Tools._time_banner`/`Tools._dream_banner` still
  resolves; `tests/test_safety_gates_adversarial.py` (D5, 55 tests) re-run
  and unchanged (55 passed/10 xfailed), confirming the reverse coupling
  from `_validate_command_safety` into the now-moved
  `_active_download_guard` still works and the safety gate itself is
  undisturbed.

**Verified only by import + full test suite (no dedicated live-network or
live-hardware exercise beyond what the existing suite already covers):**
- The actual network-facing bodies of `ssh_run`/`ssh_script`/`nmap_summary`
  (NetSec), `wake_node`/`query_node_agent`/`shutdown_node`
  (NodeLifecycle — these require live node hardware to fully exercise),
  the live LLM backend calls inside `_call_claude_planner`/
  `_call_chatgpt_planner`/`_openai_style_call` (Planner — covered by
  `test_planner_ledger.py`'s monkeypatched unit tests, not a live call),
  and `search_web`/`search_reddit`/`fetch_url`/`monitor_download` (Web —
  these hit SearxNG, Reddit, Firecrawl, and the download-monitor script
  respectively; none were called live during this refactor since the goal
  was behavior-preservation, not behavior-exercise, and the existing test
  suite's coverage of these paths — same as pre-D7 — was neither expanded
  nor reduced by moving the code).

This mirrors the plan's own stated limit (D4's lesson): a green suite
proves absence of regression in covered paths only. The live-hardware and
live-network paths were exercised at the "resolves via MRO and is callable"
level, not at the "actually talks to node3090/SearxNG/Reddit" level, for
all four extractions — consistent with how NetSec and NodeLifecycle were
already verified in Steps 6-8, before this report was written.

## Anti-goals — confirmed held

- Safety group never touched: `_validate_command_safety`, `_is_allowed_*`,
  `_norm`, `sudo_delegation_block`, `execute_command`, `write_file`,
  `read_file` all remain on `Tools`, byte-unchanged since D5.
- No method body, signature, or docstring edited during any move — every
  extraction was AST-diffed byte-identical against source before deletion.
- The four D5 xfail holes untouched (still 10 xfailed, same count/reasons
  throughout all four D7 commits).
- No reformatting/reordering beyond the move itself — two cases
  (`_budget_gate`, `search_web`) where a naive comment-absorption heuristic
  would have swept in unrelated section-header/historical comments were
  caught by content inspection and corrected before the deletion ran.
- No mixin imports goethe.py — all five (`goethe_kb`, `goethe_netsec`,
  `goethe_node`, `goethe_planner`, `goethe_web`) plus the dependency-free
  `goethe_constants` are one-way imported by goethe.py only.
- No step proceeded while an invariant was red — the one mid-step failure
  (Step 9's comment-absorption bug, caught via post-deletion inspection
  finding three orphaned comment fragments) was fully recovered via
  `git checkout -- tools/goethe.py` before continuing, documented in that
  commit's message.

## Not part of this effort (intentionally out of scope)

- The 161 pre-existing ruff findings in tools/ files D7 never touched.
- The BW_PASSWORD leak from earlier in this session (2026-07-31) — the
  user chose "Nothing for now"; remains parked pending new instruction.
- A secret-rotation skill for BW_PASSWORD — the user's stated future task,
  not yet requested to begin.
