# D6 — planner prompt (surgical)

Paste into `planner(task=..., context=...)`. Backend: `claude` (Opus 5, pinned).
Grounded on a live scan of `tools/goethe.py` @ commit `766182a`, 2026-07-31.

---

## task

```
D6 topology-literal sweep in tools/goethe.py: eliminate the 22 hardcoded host/port/path
literals that sit OUTSIDE the Valves class, by routing each one to its correct existing
home (a Valves field, _NODE_REGISTRY, or a module constant). Resolve two live
configuration conflicts found during the audit. Add a regression test that pins the
result. Clear the 8 residual ruff findings. Zero behavior change except where a
conflict resolution deliberately corrects a wrong endpoint - and that must be probed
first, never guessed.
```

## context

```
=== GROUND TRUTH (measured, not estimated - AST scan @ 766182a) ===
goethe.py has 43 Valves fields and 52 non-docstring topology literals.
20 of those 52 are INSIDE Valves defaults. Those are ALREADY CORRECT: a valve default
containing "/opt/local-se" IS the configuration mechanism working as designed.
DO NOT TOUCH THEM. Rewriting them is pure churn and will look like progress while
adding risk. The real worklist is the 22 literals outside the Valves class:

  L348, L354    '/opt/local-se/'
  L736, L1212   'http://127.0.0.1:'      (planner port assembly)
  L1191, L2853  '127.0.0.1'              (L2853 has two on one line)
  L1307         '/home/sy5/'
  L3620         'http://localhost:3002'   <- SEE HAZARD 1
  L3623, L3625  'node3090.home.arpa'      (log string + ping argv)
  L3634         'http://node3090.home.arpa:3002'  <- SEE HAZARD 1
  L4101         '/opt/local-se/download-monitor.py'
  L4106         '/home/sy5/miniforge3/bin/python3'
  L4112         'SETUP_REQUIRED | ... not found at /opt/loc...'  (message text; low value)
  L4486         'http://127.0.0.1:11434'  <- SEE CONFLICT A
  L4504         'http://127.0.0.1:9200'
  L4594, L4626  'node3090.home.arpa', 'node5090.home.arpa'  (inside _NODE_REGISTRY - correct, leave)
  L5582         '/opt/local-se/kb/STACK-MAP.md'
  L5598, L5599  '/opt/local-se', '/opt/local-se/kb'

=== HAZARD 1: the :3002 collision (highest risk in this task) ===
Port 3002 refers to TWO DIFFERENT SERVICES on two different hosts:
  - node3090:3002  = Firecrawl (browser rendering). L3620 localhost:3002 is the
    same Firecrawl, reached locally when goethe runs ON node3090; L3634 is the
    remote path from LUCIFER.
  - LUCIFER:3002   = Grafana (per kb/STACK-MAP.md).
A sweep that creates one shared port constant, or points the Firecrawl calls at a
Grafana valve (or vice versa), silently breaks reddit fallback or observability.
Introduce a distinctly named FIRECRAWL_URL / FIRECRAWL_REMOTE_URL valve pair. Never a
generic PORT_3002. Verify the two are never unified.

=== HAZARD 2: hostnames already have a home - do not invent valves for them ===
_NODE_REGISTRY (L4592+) is the canonical node table: node3090 (agent_port 8080),
node5090 (agent_port 8081), each with mac/hostname/interface. It is referenced only
3 times in the whole file. The reddit-fallback block hardcodes 'node3090.home.arpa'
at L3623/L3625/L3634 instead of reading the registry.
CORRECT FIX: read _NODE_REGISTRY["node3090"]["hostname"]. Do NOT add a
NODE3090_HOSTNAME valve - that would create a second source of truth for a fact the
registry already owns, which is the D1 defect class all over again.
Note: node4090 is absent from the registry because node4090 IS LUCIFER, the WSL2 host
running goethe - it is not a wake-able remote node. That is correct; do not "fix" it.

=== CONFLICT A: two disagreeing Ollama endpoints (probe, do not guess) ===
L4486 (search_rfc embeddings) hardcodes  http://127.0.0.1:11434  (local).
Valve at L188 defaults to               http://node3090.home.arpa:11434  (remote).
One of these is wrong, or they are deliberately different and undocumented.
REQUIRED: probe both endpoints live (curl /api/tags or equivalent) and record which
actually answers, BEFORE changing either. If only one answers, route to it and say so
in the commit message. If both answer, keep current behavior and document why they
differ. Do not silently repoint a working call.

=== CONFLICT B: Elasticsearch endpoint ===
L4504 hardcodes http://127.0.0.1:9200 while an ES valve/config exists elsewhere.
Same rule: probe, then reconcile to the valve if and only if they agree.

=== NON-NEGOTIABLE PROCESS (learned the hard way this week) ===
1. FULL LINTER, NOT ONE RULE. D4 reported "ruff --select BLE001 -> 0 violations" and
   was clean on that rule while introducing 9 crash paths that plain `ruff check`
   caught as F821. Always run the whole configured ruleset.
2. VERIFY THE TOOL LOCATION. ruff is NOT in the owui venv. It lives at
   /home/sy5/miniforge3/bin/ruff. `/home/sy5/owui/bin/python3 -m ruff` fails with
   "No module named ruff" - a report claiming a clean ruff run from that interpreter
   did not actually run one.
3. TESTS ARE NOT SUFFICIENT ALONE. All 487 tests passed over the D4 defect because no
   test exercises network-failure paths. A green suite proves absence of regression in
   covered paths only - state explicitly which changes are unverified by tests.
4. The full harness is /home/sy5/owui/bin/python3 -m pytest tests/ -q, ~81s,
   currently 491 passed. It must still be 491+ green at the end.
5. These two guards must stay green and must not be weakened:
     tests/test_docstring_mcp_truncation.py     (MCP 1024-char contract window)
     tests/test_except_clause_resolvable.py     (except clauses resolve in scope)
6. Backup before edit: cp tools/goethe.py backups/goethe.py_pre-d6_$(date +%Y%m%d_%H%M%S)
7. Batch the edits (e.g. 4-6 sites per batch) and run py_compile + ruff between
   batches, not once at the end. A 22-site single-shot edit is how D4 shipped 9 bugs.

=== ALSO IN SCOPE: 8 residual ruff findings (cosmetic, no behavior risk) ===
  F401 L44 goethe_kb.TrustPolicy unused; L3718 html.parser.HTMLParser unused; L5707 re unused
  F811 L3646, L3669 redefinition of _re
  F841 L2030 scp_opts assigned but never used
  F541 L3784, L5304 f-string without placeholders
Fix these in their own commit, separate from the topology sweep, so the diff of each
stays reviewable.

=== DEFINITION OF DONE ===
- Every one of the 22 outside-Valves literals is either routed to a valve/_NODE_REGISTRY/
  module constant, OR explicitly justified in a comment as intentionally literal
  (log message text and SETUP_REQUIRED strings are legitimate keeps).
- No new valve duplicates a fact _NODE_REGISTRY already owns.
- Firecrawl and Grafana :3002 remain provably distinct.
- Conflicts A and B are resolved with recorded probe evidence, or documented as
  intentional with a reason.
- New test (suggested tests/test_topology_literals.py) asserts no NEW outside-Valves
  topology literal appears - an AST gate in the style of bump_gate.py and
  test_except_clause_resolvable.py. Include the current justified-keep list as an
  allowlist so the gate is enforceable rather than aspirational.
- ruff check tools/goethe.py -> All checks passed (full ruleset, miniforge ruff).
- Full harness 491+ passed.
- kb/STACK-MAP.md updated: it currently omits node5090 and does not record the
  :3002 Firecrawl/Grafana distinction. Both are gaps in the pinned ground truth.
- Separate commits: (1) topology sweep, (2) ruff cosmetics, (3) STACK-MAP + test.

=== ANTI-GOALS - do not do these ===
- Do NOT rewrite the 20 literals inside Valves defaults.
- Do NOT introduce a config-loader abstraction, settings module, or env-var layer.
  Valves + _NODE_REGISTRY are the existing mechanisms; use them.
- Do NOT touch D7 (mixin extraction). Class structure stays exactly as it is.
- Do NOT reformat, reorder, or reflow unrelated code. The diff must be readable as
  "literal -> reference" and nothing else.
- Do NOT change any docstring content (D3 just pinned the 1024-char contracts).
```
