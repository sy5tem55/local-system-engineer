# DEEP_SEARCH_FINAL_STATE

Task: 0d0ba451 · node4090 · 2026-10-08
Scope: deep_search (DeepSearchMixin) live integration into the Goethe MCP gateway :9700,
end-to-end verification via the HTTP test harness.

Pipeline components (all verified in place):
- `deep_search_core.py` — state-machine deep-research core (shipped from node3090, py_compile OK)
- `goethe_deep_search.py` — DeepSearchMixin exposing `deep_search` as an MCP tool (cold tier)
- `goethe.py` — mixin integrated into the Tools class hierarchy
- `deep_search_test_harness.py` — live-HTTP harness (BrowseComp-style multi-hop ×3, KB-heavy ×1, baseline ×1)

## 1. Step-25 failure: cold-tier registration + empty API key

After the first operator-gated restart (step 24), `deep_search` did NOT appear in the
eager `tools/list` — it landed in the COLD registry only. The harness's direct MCP calls
to `deep_search` therefore failed at preflight. Routed via the cold-tier bridge
(`tool_search` → `tool_invoke`), the call reached the tool but returned a FAILED dict:

- error.class = `ConfigurationError`
- message: `DEEP_SEARCH_MODEL_API_KEY valve is empty`

Root cause (from `/tmp/lse/deep_search_fix_analysis.json`, step 25, read-only inspection):
- `goethe.py` `Valves` dataclass has 59 fields; NONE are `DEEP_SEARCH_*`.
- `goethe_deep_search.py:334`: `key = getattr(self.valves, "DEEP_SEARCH_MODEL_API_KEY", "")`
  → attribute never exists → key is always `""` → refusal at PLANNING, by design.
- The live model credentials DO exist in the gateway env under the planner names:
  `PLANNER_FORCE_URL`, `PLANNER_FORCE_MODEL`, `PLANNER_FORCE_API_KEY` (all three present
  in both the Valves dataclass and the running process environ).

## 2. Fix

1. **Key fallback (step 26)** — `goethe_deep_search.py` patched: `DEEP_SEARCH_MODEL_API_KEY`
   valve lookup now falls back to the live gateway env var `GOETHE_PLANNER_FORCE_API_KEY`
   via `os.environ` (line 335). `py_compile` OK.
   Backup: `/opt/local-se/bkp/goethe_deep_search.py_<ts>` (2026-10-08).
2. **Harness bridge patch (step 27)** — `deep_search_test_harness.py` patched so every
   direct `deep_search` MCP call goes through the `tool_search` + `tool_invoke` cold-tier
   bridge; preflight now accepts cold-tier registration. `py_compile` OK, offline
   `--selftest` → `SELFTEST OK`.
   Backup: `/opt/local-se/bkp/deep_search_test_harness.py_<ts>` (2026-10-08).

## 3. Operator-gated second restart (step 28)

Performed by the operator from the Goethe GUI (C:\Goethe3.0) per canonical protocol
(KB 1dd544d695ba6b48 — agent never self-restarts the gateway).
Evidence `/tmp/lse/deep_search_restart_verify.json`:

```json
{"old_pid": "978086", "new_pid": "1050596", "env_key_present": true}
```

`GOETHE_PLANNER_FORCE_API_KEY` confirmed present in the new gateway environ.

## 4. Live valve probe (step 29)

Live `tool_invoke` probe against new pid 1050596, token read from
`/proc/1050596/environ` (ground truth, never from a file). Evidence
`/tmp/lse/deep_search_valve_probe.json`:

- status: **DONE** — no `ConfigurationError`; the key fallback works end-to-end.
- Full legal state trace: PLANNING → SEARCHING → REASONING → READING → SYNTHESIZING → DONE.
- tasks.db child-run recorded with parent `0d0ba451`, scope `deep-search-core`.
- (The probe question "valve probe" returned an unrelated irrigation PDF — the probe
  verifies transport + key + state machine, not research quality.)

## 5. Final harness evidence (step 30)

### First live run (13:51–13:54) — infrastructure failure, not deep_search

All 5 entries `HARNESS_ERROR`. The gateway (pid 1050596) died mid-run during mc1
(`RemoteProtocolError` after 169.3 s; mc2/mc3/kb1/base1 then `ConnectError`).
Forensics: no Python traceback in its launch log (abrupt end), no OOM in dmesg,
no kernel segfault; core pattern is `|/wsl-capture-crash` (native crashes route to the
Windows side). A new gateway came up at 13:54:13 (pid 1085519) — 4 s after death,
consistent with launcher auto-restart. The failed results file was backed up to
`/opt/local-se/bkp/deep_search_test_results.json_20261008_140233` before the rerun.

### Final run (run2, 14:03–14:12, harness PID 1104480)

Gateway 1085519 survived the entire run (no crash recurrence).
`HARNESS DONE pass=1/5`. Log: `/tmp/lse/harness_run_final.log`;
results: `/tmp/lse/deep_search_test_results.json`:

| id    | kind       | status  | elapsed_s | error                                                                                   |
|-------|------------|---------|-----------|-----------------------------------------------------------------------------------------|
| mc1   | multi-hop  | FAILED  | 152.1     | model_timeout_unrecoverable — FirstOutputTimeout 60 s, at SYNTHESIZING (8 sources held) |
| mc2   | multi-hop  | FAILED  | 132.9     | model_timeout_unrecoverable — FirstOutputTimeout 60 s, at SYNTHESIZING (8 sources held) |
| mc3   | multi-hop  | FAILED  | 116.7     | budget_exhausted — maxSteps=6 exceeded, refusing search action 7, at SEARCHING          |
| kb1   | kb-heavy   | FAILED  | 66.1      | plan_invalid — model plan still invalid after one repair attempt, at PLANNING           |
| base1 | baseline   | DONE    | 110.0     | none — cited report, 750 chars, 8 sources                                               |

## 6. Interpretation

Proven working: state machine + transition discipline, budget enforcement
(`budget_exhausted` raised *before* execution, as designed), cold-tier
`tool_invoke` bridge, API-key fallback, citation pipeline, cited-report generation
(baseline), tasks.db child-run scoping, and gateway coexistence (harness is a pure
HTTP client; gateway stayed up through 5 consecutive deep_search executions).

Open quality issues — outside this task's scope, candidates for follow-up:
1. 60 s first-output timeout is too tight for SYNTHESIZING on long 8-source contexts
   (mc1/mc2 die at the last step with all evidence already collected).
2. Default `maxSteps=6` is below what 3-hop BrowseComp questions need (mc3);
   the harness can pass a `max_steps` override per question.
3. `plan_invalid` on the internal KB-heavy question (kb1) — planner-model plan
   format/repair needs a look at the actual rejected plan.
4. The 1050596 mid-run crash has no local trace (suspected C-level crash captured by
   `/wsl-capture-crash`, or external kill); monitor for recurrence — run2 showed none.

## 7. Artifact manifest

- Results: `/tmp/lse/deep_search_test_results.json` (final run)
- Harness log: `/tmp/lse/harness_run_final.log` (= `/tmp/lse/deep_search_harness_run2.log`)
- Probe: `/tmp/lse/deep_search_valve_probe.json`
- Restart evidence: `/tmp/lse/deep_search_restart_verify.json`
- Fix analysis: `/tmp/lse/deep_search_fix_analysis.json`
- Backups (all timestamped): `/opt/local-se/bkp/` — goethe_deep_search.py,
  deep_search_test_harness.py, tasks.db, deep_search_test_results.json
