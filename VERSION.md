# LSE Version Registry
> Last updated: 2026-06-12 (P22 Cowork)

---

## Current Versions

| Component | Version | Shipped | Status |
|---|---|---|---|
| Tool | **Cogitator v1.7.4** | 2026-06-12 | built ✅ — compact_context KV-erase fix (?action=erase query param); import to OWUI |
| Prompt | v0.5.15 | 2026-06-09 | deployed ✅ |
| Filter | **v1.2.0** | 2026-06-11 | deployed ✅ |
| Vaultwarden tool | v1.3.0 | 2026-06-03 | deployed ✅ |
| Launcher CLI | v1.078 | 2026-06-03 | deployed ✅ |
| Launcher GUI | **v1.5** | 2026-06-08 | deployed ✅ |
| pfsense-agent | **v1.0** | 2026-06-09 | `/opt/local-se/pfsense-agent.py` ✅ |
| ChallengeDB | seeded ✅ | `/opt/local-se/challenges.db` — 10 T1 challenges |
| Leaderboard DB | live ✅ | `/opt/local-se/leaderboard.db` — 6 episodes |
| RFC KB | indexed ✅ | `lse-rfc-kb` ES index — 1490 chunks (tagging in progress) |
| LSEChallengeEnv | v1 | 2026-06-04 | `scripts/lse_challenge_env.py` |
| EscalationWrapper | v1 | 2026-06-04 | `scripts/escalation_wrapper.py` |
| LeaderboardService | v1 | 2026-06-04 | `scripts/leaderboard.py` |
| run_episode.py | v1 | 2026-06-04 | `scripts/run_episode.py` |
| ChallengeGenerator | v1 | 2026-06-04 | `scripts/challenge_generator.py` |
| rfc_kb.py | v1 | 2026-06-04 | `scripts/rfc_kb.py` |

---

## Tool Checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `cogitator-v1.7.4.py` | `2d3a97034049460f30b2703a42dd4d2df61908632896bde7fe6d70cb9bd4946b` |
| `cogitator-v1.7.3.py` | `849de2767350b478a0994c7d0e0ee26ca989e89a5e4d18144a4164175bc00de9` |
| `cogitator-v1.7.2.py` | `eca3b5186c8cc2b23f9a1d39eb660e660970d38a85761a50ba62c682c7898de5` |
| `cogitator-v1.7.1.py` | `c89945553320ded2918b0afda7190d13f39c098f38c517077a6049f8c5557bb9` |
| `cogitator-v1.7.0.py` | `642067d99b094bf03a3cb26968bd5f05c40596764952f52e46c681f27626c24a` |
| `openwebui-tool-v1.5.18.py` | `6532afd72fffa531ed02d8e18d31e5f03ffe0c9bc29bd726d281d1e3211b7cd1` |
| `openwebui-tool-v1.5.17.py` | `f30c1e97493aa6f58fe3498df94c15784d747a5e1e04a209a405251e5211c973` |
| `openwebui-tool-v1.5.16.py` | `bcc04bb0fa3d944c9fa5a4e4786393950b2efc32f0ad69962716a217f88a66d1` |
| `openwebui-tool-v1.5.15.py` | `b9d00a17ad44eda7c4630368a7a19fde9d282e7871536ae306482e619a9c9dd0` |

---

## Arena Leaderboard Snapshot (2026-06-04)

| Model | Points | Episodes | Solved | Esc | Avg Att | KB Hits |
|---|---|---|---|---|---|---|
| qwen3.6-27b-q4-64k | 100.1 | 6 | 5 | 0 | 1.33 | 6 |

Active profile: `Qwen3.6 27B Q4_K_M · 64k · KV:q8_0 · think:3072 → :8080`

---

## Co-test Matrix

| Eval Run | Tool | Prompt | Score | Report |
|---|---|---|---|---|
| eval-v1 | v1.4.0 | v0.1-baseline | — | eval/eval-report-v1.md |
| eval-v2 | v1.5.1 | v0.4.1 | 45/57 | eval/eval-report-v2.md |
| eval-v3 | v1.5.4 | v0.5.1 | 57/57 | eval/eval-report-v3.md |
| eval-v4 | v1.5.5 | v0.5.2 | 49/57 | eval/eval-report-v4.md |
| eval-v5 (partial) | v1.5.6 | v0.5.2 | 15/21 | eval/eval-report-v4.md (appended) |
| eval-v6 | v1.5.13 | v0.5.11 | 58/63 | eval/eval-report-v5.md |
| Run 7 (partial) | v1.5.18 | v0.5.13 | 62/63 (proj) | eval/eval-report-v6.md |

---

## Version History (tool)

| Version | Shipped | Key change |
|---|---|---|
| v1.4.0–v1.5.8 | 2026-05-23–29 | see CHANGELOG |
| v1.5.9 | 2026-05-31 | RAG layer (ES + Ollama) |
| v1.5.10 | 2026-06-01 | monitor_download() |
| v1.5.11 | 2026-06-01 | fetch_url() |
| v1.5.12 | 2026-06-02 | write_file SIZE SANITY CHECK + record_outcome + mentor_correct |
| v1.5.13 | 2026-06-03 | search_web header fix + categories fix |
| v1.5.14 | 2026-06-03 | sudo_delegation_block step_number/total_steps/verify_command |
| v1.5.15 | 2026-06-03 | pfsense_query() + PFSENSE_URL/KEY valves |
| v1.5.16 | 2026-06-03 | PFSENSE_CA_CERT valve + _pfsense_verify() |
| v1.5.17 | 2026-06-04 | pfsense_log_summary() + nmap_summary() — compact extraction |
| v1.5.18 | 2026-06-04 | search_rfc() — RFC authority KB query (2042 lines · syntax OK) |
| **v1.6.0** | 2026-06-08 | pfsense_graphql() three-tool architecture; pfsense_query writes-only; pfsense_log_summary logs-only |
| **v1.6.1** | 2026-06-09 | schema introspection prohibition (DO NOT __schema/__type) in pfsense_graphql docstring |
| v1.6.2–v1.6.4 | 2026-06-10/11 | call_hermes + KB-FIRST pfsense rule + two-boss architecture (see tool changelog; never registered here — registry gap closed in P22) |
| **Cogitator v1.7.0** | 2026-06-12 | RENAMED cogitator-v1.7.0.py; skills layer: skill_search/skill_record/skill_outcome + lse-skills index (3104 lines · ast.parse OK · sha256 642067d9…) |
| **Cogitator v1.7.1** | 2026-06-12 | Anti-spiral budget gate (search/fetch, code-enforced, 8/30min default) + task blocks (task_checkpoint/task_resume, SQLite) — Goethe-spiral fix; planner spec docs/planner-orchestrator-design.md (3346 lines · ast OK · unit-tested · sha256 c8994555…) |
| **Cogitator v1.7.2** | 2026-06-12 | SEARCH_BUDGET_WINDOW_MIN 30→2 min — window leaked across task_resume sessions and stalled live conversations (RUTX50 incident); 8/2min still forces surface points (sha256 eca3b518…) |
| **Cogitator v1.7.3** | 2026-06-12 | UNVERIFIED-URL RULE in budget-refusal text + fetch_url docstring — never present a URL/hostname not received from a tool result (fabricated fbidownload.* hostname incident) (sha256 849de276…) |
| **Cogitator v1.7.4** | 2026-06-12 | compact_context KV erase fixed: POST /slots/0?action=erase (query param, empty body, n_erased reported) — JSON-body form was never valid; "slots API removed in v9577" diagnosis was false (sha256 2d3a9703…) |

---

## pfsense-agent Version History

| Version | Shipped | Key change |
|---|---|---|
| **v1.0** | 2026-06-09 | Initial — Qwen3.6 orchestrator + LSE submit; `--think/--no-think/--prompt-only/--auto`; `_extract_prompt` DO NOT anchor + contiguous step sequence; tool_ids pass-through |
