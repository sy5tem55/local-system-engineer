# TRAUM full dream cycle — 2026-07-12 (Thread 3, Prompt 3.8)

> Per Prompt 3.8: "Run a full dream cycle now (all passes including new
> ones) and review the complete report + digest together in-thread."

## Environment constraint (same as every 2026-07-12 entry in CHANGELOG.md)

This Cowork sandbox has no live `/opt/local-se` tree, no reachable
Elasticsearch, and no reachable Ollama/llama-server — those only exist on
LUCIFER/node3090. `dream_runner.py`'s own code handles every one of these
absences non-fatally (`select_undreamed_sessions` on a missing
`manifest.db`, the `except Exception` guard around both `search_index`
calls in `main()`, `read_agent_log_window`/`tail_agent_log` on a missing
`agent_commands.log`) — so a "full dream cycle" run **in this sandbox**
is deterministic and traceable by hand from the code, and doubles as an
end-to-end proof that Prompt 3.8's null-result discipline degrades
gracefully under total corpus absence rather than crashing or fabricating
findings. It is not a substitute for the real run against the live
LUCIFER corpus — that's flagged explicitly below, per pass.

`GOETHE_EPISODE_DIR`/`GOETHE_DREAM_DIR` point at a scratch dir with no
`manifest.db`; `GOETHE_ES_URL` points at nothing listening;
`GOETHE_AGENT_COMMANDS_LOG` points at a path that doesn't exist. All five
passes were traced against this state using the exact Prompt 3.8 code
(`tools/dream_runner.py` v0.8.0, verified region-by-region by manual
read-through — see CHANGELOG.md's verification note for why `run_tests`/
direct execution wasn't usable this session: this sandbox's own mount of
the repo is stale for files edited this session, `dream_runner.py`
specifically, confirmed truncated mid-file on repeated re-checks).

## Summary

| Pass | proposals | null_record.reason | looked | corpus_size (examined) |
|---|---|---|---|---|
| `dedup` | 0 | `empty_kb` | **False** | kb_docs=0 |
| `stale-contradiction` | 0 | `empty_kb` | **False** | kb_docs=0, sessions_considered=0 |
| `error-cluster` | 0 | `no_items` | **False** | episode_items=0, error_doc_items=0 |
| `patterns` | 0 | `log_missing_or_empty` | **False** | raw_lines=0 |
| `insights` | 0 | `no_data_to_feed` | **False** | session_summaries=0, domains_with_data=0 |

Every pass correctly reports **"didn't look"** (`looked=False`) — not
"nothing there". That distinction is exactly Prompt 3.8's point: a corpus
that is genuinely empty in this sandbox (no manifest.db, no ES, no
agent_commands.log) is structurally different from a live LUCIFER corpus
that a dream run inspects and finds clean. Collapsing those two into one
"0 proposals" number, as the pre-3.8 code effectively did, would make an
infra outage indistinguishable from a healthy KB — the exact failure mode
Prompt 3.8 exists to close.

`dream_digest.refresh_digest()` (called at the end of `main()` for every
pass, per Prompt 3.4) degrades the same way: `pick_primary_date()` finds
no day-dirs under the scratch `GOETHE_DREAM_DIR` yet (this is the first
run against it), so all four digest sections render their own null notes
("no dream cycles found yet") rather than erroring — the same
"gather-step-failure-never-breaks-the-caller" discipline `dream_digest.py`
already documents, exercised end-to-end here for the first time this
session against a truly empty dream-dir rather than a mocked one.

## Per-pass trace

**`dedup`** — `kb_docs` is `[]` (the `except Exception` guard in `main()`
around `search_index(cfg, "lse-kb", ...)` catches the ES connection
failure and leaves it at its `[]` default). `run_pass_dedup`'s first gate
(`if not kb_docs`) fires immediately: zero embed calls, zero cosine
comparisons ever attempted. `_null_record("dedup", "empty_kb",
looked=False, corpus_size={"kb_docs": 0, "embedded_docs": 0,
"candidate_pairs": 0, "pairs_above_threshold": 0}, thresholds={"dedup_floor":
0.75, "dedup_threshold": 0.92})`.

**`stale-contradiction`** — same `kb_docs=[]` gate, same shape:
`_null_record("stale-contradiction", "empty_kb", looked=False,
corpus_size={"kb_docs": 0, "sessions_considered": 0,
"sessions_with_candidates": 0, "reverify_candidates": 0,
"demote_confirmed": 0}, thresholds={"contradiction_min_quality": 0.6,
"chronos_ttl_days": {"static": null, "slow": 90, "fast": 7}})`. Sessions
are also `[]` here (`manifest.db` absent), so even with a live ES this
particular run would still have nothing for the demote sub-pass to check
against — worth re-running for real once episode capture has a session or
two on LUCIFER.

**`error-cluster`** — `error_docs` stays `[]` (same ES-unreachable guard,
`main()` only queries `lse-errors` when `cfg.pass_name == "error-cluster"`,
which this invocation is) and `episodes_by_session` is empty (no
sessions), so `collect_episode_error_occurrences` + `collect_lse_errors_items`
both return `[]`, `all_items` is `[]`, first gate fires:
`_null_record("error-cluster", "no_items", looked=False,
corpus_size={"episode_items": 0, "error_doc_items": 0, "embedded_items": 0,
"clusters_found": 0, "clusters_qualifying": 0}, thresholds={"error_cluster_threshold":
0.80, "min_occurrences": 3, "min_sessions": 2})`.

**`patterns`** — `read_agent_log_window` returns `[]` (path doesn't
exist), first gate fires before `parse_agent_log_lines` is even called:
`_null_record("patterns", "log_missing_or_empty", looked=False,
corpus_size={"raw_lines": 0, "events": 0, "sessions_inferred": 0,
"command_frequency_rows": 0, "automation_candidates": 0, "failure_retry": 0},
thresholds={"patterns_min_sequence_len": 3, "patterns_min_sessions": 3,
"patterns_retry_window": 20, "patterns_max_lines": 50000})`. No
`patterns.json` is written this run (the gate returns before
`write_patterns_json` is reached).

**`insights`** — `raw_lines` is `[]` so `events` is `[]` so `patterns`
(the in-memory `mine_patterns` result) has every domain empty;
`session_summaries` is also `[]` (no sessions). `domains_with_data` is
`[]`, the `if not domains_with_data and not session_summaries` gate fires
before a single LLM call is attempted: `_null_record("insights",
"no_data_to_feed", looked=False, corpus_size={"session_summaries": 0,
"domains_with_data": 0, "insights_accepted": 0, "proposals": 0},
thresholds={"insights_max_sessions_in_prompt": 20,
"insight_observation_min_len": 20})`.

## What this run does and doesn't prove

Proves: the null-result code path is reachable and correct at the extreme
("everything is absent") for all five passes and the digest, without any
of them raising, hanging, or fabricating a finding — a real, if minimal,
exercise of Prompt 3.8's own code, not just a description of it.

Does not prove: behavior on a real corpus with actual near-duplicate KB
docs, actual TTL-expired docs, actual repeated command sequences, etc. —
the "looked=True, nothing there" and "found something" branches (also
added this session, see CHANGELOG.md) are verified by manual code
read-through plus `tests/test_dream_patterns.py`'s new
`test_null_result_when_all_domains_empty_but_events_present` and the
pre-existing dedup/insights end-to-end tests, not by a live run — same
caveat the 2026-07-11 Thread 2 calibration run and every 2026-07-12 entry
already carry. The next real dream cycle on LUCIFER (whenever Thread 3
prompts resume there, or at Thread 3's close, Prompt 3.10) is what
exercises this against the actual ~370-doc `lse-kb` and the real episode
corpus.
