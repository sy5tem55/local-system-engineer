# LSE Version Registry
> Last updated: 2026-06-04 (session 5)

---

## Current Versions

| Component | Version | Shipped | Status |
|---|---|---|---|
| Tool | v1.5.18 | 2026-06-04 | deployed ✅ |
| Prompt | v0.5.14 | 2026-06-04 | deployed ✅ |
| Filter | v1.1.0 | 2026-05-23 | deployed ✅ |
| Vaultwarden tool | v1.3.0 | 2026-06-03 | deployed ✅ |
| Launcher CLI | v1.078 | 2026-06-03 | deployed ✅ |
| Launcher GUI | v1.4 | 2026-06-03 | deployed ✅ |
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
