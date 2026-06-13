# LSE Version Registry
> Last updated: 2026-06-13 (P27 Cowork)
> Authored by: Claude (Anthropic) — P26 contributions: cogitator v1.7.10 (source-claim verification, fabrication #5 class), v1.7.11 (KB source-tier quality gate, pfSense self-grant incident). P27: v1.7.12 restored from OWUI backup + cache fix; v1.7.13 SSH KB-FIRST rule (bare-ssh-before-KB + wrong-topic-filter incidents). Ground truth is earned, not claimed.
> **Ground Rule (P27):** Always verify line count between versions. Report delta and track in Line Count Tally below.

---

## Current Versions

| Component | Version | Shipped | Status |
|---|---|---|---|
| Tool | **Cogitator v1.7.13** | 2026-06-13 | READY FOR DEPLOY (P27, ast OK, black-norm `866b0b4d…`, raw `cfc194c5…`, 4508 lines) — SSH KB-FIRST RULE in execute_command docstring: search_kb before any ssh command (no topic_filter); never bare ssh without key. Closes: bare-ssh-before-KB-lookup + wrong-topic-filter-on-SSH-query (rutx50 live test). Previous: v1.7.12 deployed ✅ (P27, ast OK, black-norm `a2faad62…`, raw `a6911429…`, 4483 lines) — SSH device auto-fingerprint: execute_command intercepts `ssh ` prefix, extracts host, runs os-release+uname on first connection, prepends `[DEVICE FINGERPRINT]` banner. Failed fingerprints NOT cached (retry on next SSH call with correct key); failed attempts emit `[DEVICE FINGERPRINT PENDING]` note. Source: restored from OWUI backup (4465 lines CRLF) + cache fix applied = 4483 lines LF. Previous: v1.7.11 deployed ✅ (P26, ast OK, black-norm `09595a23…`, raw `631d11df…`, 3934 lines) — source_tier quality gate on index_to_kb/skill_record/skill_outcome: ground_truth=1.0 (evidence required), primary=0.8, secondary=0.6, inferred=0.4 (default). quality=1.0 unreachable without source_tier=ground_truth + ≥40-char tool-result evidence. verified_against field for staleness tracking. Previous: v1.7.10 deployed ✅ (P26, ast OK, black-norm `48e13812…`, raw `463e0941…`, 3859 lines) — verify_source_claims(): re-fetches source + FOUND/PARTIAL/NOT_FOUND per claim with verbatim ±300-char excerpts; fetch_url caches content + emits SOURCE-VERIFY MANDATE banner; SOURCE_VERIFY_CACHE_TTL valve (300s). Does NOT count against search budget. Previous: v1.7.9 deployed ✅ (P25, black-norm `2e15e467…` MATCH, 3679 lines) — hermes_plan kanban card INSERT. NOTE: OWUI black-formats on save — verify deploys by black-normalizing, not raw sha. |
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

| File | Lines | Raw SHA-256 | Black-norm SHA-256 |
|---|---|---|---|
| `cogitator-v1.7.13.py` | 4508 | `cfc194c518db698fbff95ac75ce6191e5db890e4fbac617ebc657a0a042ae9b9` | `866b0b4d656a20753bd2bf18d159389da44f00366678f80804495349c03dc67c` |
| `cogitator-v1.7.12.py` | 4483 | `a691142910077ea9ff9ec4df282dc7e421e9e43eea8d17b7aca0a904d9b40d79` | `a2faad62a1fa03031e5d066e1e830953a30adfcf206a3bcfc678d9d526a1f3cd` |
| `cogitator-v1.7.11.py` | 3934 | `631d11dfb09ad203ff5f0e0feb759dc6d045b5febc40ee5d3c9d48c143c452d2` | `09595a23…` |
| `cogitator-v1.7.10.py` | 3859 | `463e0941dad82d8c8d4ba6738fc44de3584f81f5037f275ffb5f365ed262ae17` | `48e13812…` |
| `cogitator-v1.7.9.py` | 3679 | `36d9dcc2…` (see P25) | `2e15e467…` |
| `cogitator-v1.7.8.py` | 3607 | `fd65fea6efadfcabf818a68284d3f0a8184970182c3f9d990e1f8a5a95a15e70` | — |
| `cogitator-v1.7.7.py` | 3598 | `fa8bd376e95e9d9a42764cf530c2dee9e1995c27941b3a30fa45ef70c0321b74` | — |
| `cogitator-v1.7.6.py` | 3544 | `7a5162468b42cdd1f4c8d675e55b85482c55a0566577f57d8e5968bd844dd248` | — |
| `cogitator-v1.7.5.py` | 3415 | `94a428a936d37722f2fcba8e0ae1d80ca20c2593e899dafc6f0c1aa45b104b7f` | — |
| `cogitator-v1.7.4.py` | 3383 | `2d3a97034049460f30b2703a42dd4d2df61908632896bde7fe6d70cb9bd4946b` | — |
| `cogitator-v1.7.3.py` | 3371 | `849de2767350b478a0994c7d0e0ee26ca989e89a5e4d18144a4164175bc00de9` | — |
| `cogitator-v1.7.2.py` | 3356 | `eca3b5186c8cc2b23f9a1d39eb660e660970d38a85761a50ba62c682c7898de5` | — |
| `cogitator-v1.7.1.py` | 3348 | `c89945553320ded2918b0afda7190d13f39c098f38c517077a6049f8c5557bb9` | — |
| `cogitator-v1.7.0.py` | 3104 | `642067d99b094bf03a3cb26968bd5f05c40596764952f52e46c681f27626c24a` | — |

### Line Count Tally (Cogitator)

| Version | Lines | Delta | Note |
|---|---|---|---|
| v1.7.13 | 4508 | +25 vs v1.7.12 | SSH KB-FIRST RULE docstring + v1.7.13 changelog entry in module docstring. |
| v1.7.12 | 4483 | +549 vs v1.7.11 | Restored from OWUI backup (4465 lines CRLF, normalized to LF) + cache fix (+18 lines). black-norm: 4484 lines. |
| v1.7.11 | 3934 | +75 vs v1.7.10 | source_tier quality gate |
| v1.7.10 | 3859 | +180 vs v1.7.9 | verify_source_claims + fetch cache |
| v1.7.9 | 3679 | +72 vs v1.7.8 | hermes_plan + _kanban_create_card |
| v1.7.8 | 3607 | +9 vs v1.7.7 | search_web categories fix |
| v1.7.7 | 3598 | +54 vs v1.7.6 | fetch_url content-type guard |
| v1.7.6 | 3544 | +129 vs v1.7.5 | hermes_plan + call_hermes fix |
| v1.7.5 | 3415 | +32 vs v1.7.4 | CONFIG GROUND-TRUTH RULE |
| v1.7.4 | 3383 | +12 vs v1.7.3 | compact_context KV erase fix |
| v1.7.3 | 3371 | +15 vs v1.7.2 | UNVERIFIED-URL RULE |
| v1.7.2 | 3356 | +8 vs v1.7.1 | SEARCH_BUDGET_WINDOW_MIN 30→2 |
| v1.7.1 | 3348 | +244 vs v1.7.0 | anti-spiral budget gate + task blocks |
| v1.7.0 | 3104 | — | initial Cogitator rename, skills layer |
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
| **Cogitator v1.7.5** | 2026-06-12 | CONFIG GROUND-TRUTH RULE in execute_command + search_kb (values from same-session tool results only, never recall); search_kb hits show age (updated Xd ago) with staleness caveat for config values (sha256 94a428a9…) |
| **Cogitator v1.7.13** | 2026-06-13 | SSH KB-FIRST RULE in execute_command docstring: (1) call search_kb(query='{hostname} SSH access') with NO topic_filter before any ssh command; (2) never attempt bare ssh without -i key; (3) never apply topic_filter of another device to an SSH access query. Closes bare-ssh-before-KB-lookup and wrong-topic-filter-on-SSH-query (rutx50 live test: model tried ssh root@rutx50 with no key → 30s timeout, then searched KB with topic_filter=pfsense → pfSense API docs). (raw `cfc194c5…`, black-norm `866b0b4d…`, 4508 lines, +25 vs v1.7.12) |
| **Cogitator v1.7.12** | 2026-06-13 | SSH DEVICE AUTO-FINGERPRINT: execute_command intercepts `ssh ` prefix, extracts host, runs `cat /etc/os-release; uname -srm` on first connection per session. Prepends `[DEVICE FINGERPRINT: host=… | platform=…]` banner. Failed fingerprints (auth error, unknown) NOT cached — retry fires on next SSH call with correct key. Failed attempts show `[DEVICE FINGERPRINT PENDING]` note. `self._device_cache: dict` in `__init__`. Closes MikroTik device-identity hallucination class (infers OS from IP/hostname instead of SSH). P27: restored from OWUI backup (4465 lines CRLF) + cache fix = 4483 lines LF. (raw `a6911429…`, black-norm `a2faad62…`, 4483 lines, +549 vs v1.7.11) |
| **Cogitator v1.7.11** | 2026-06-13 | KB SOURCE-TIER QUALITY GATE: source_tier param on index_to_kb/skill_record/skill_outcome. Ceiling map: ground_truth=1.0 (evidence≥40 chars required, else 0.7), primary=0.8, secondary=0.6, inferred=0.4 (default). quality=1.0 unreachable without ground_truth + real tool-result evidence. verified_against field stored. skill_outcome: ceiling applied to new_q; ground_truth required to push to 1.0; evidence threshold 20→50 chars for ground_truth. (raw `631d11df…`, black-norm `09595a23…`) |
| **Cogitator v1.7.10** | 2026-06-13 | SOURCE-CLAIM VERIFICATION: verify_source_claims(url, claims) re-fetches source + FOUND/PARTIAL/NOT_FOUND per comma-separated claim with verbatim ±300-char excerpts. fetch_url caches to self._fetch_cache + emits SOURCE-VERIFY MANDATE banner (code-emitted). NOT_FOUND shows what version strings ARE in source. SOURCE_VERIFY_CACHE_TTL valve (300s). Does NOT count against search budget. Enforcement in code, sudo-blocker lineage. (raw sha256 463e0941…, black-norm 48e13812…) |
| **Cogitator v1.7.9** | 2026-06-12 | _kanban_create_card(): hermes_plan INSERTs the triage card into node3090 kanban.db over ssh (status=triage, assignee=lse, goal_mode=0, idempotency_key=hermes_plan:<tid>, created_at epoch INT, INSERT OR IGNORE). Fail-open card_error line. Companion: planner contract v2.2 (sha256 36d9dcc2…) |
| **Cogitator v1.7.8** | 2026-06-12 | search_web categories "general,it,science"→"general". arxiv (in [science,it,technology], weight 2, ~15% reliable) fired on every query incl. non-science → 4-5 off-domain hits, burned web budget. General engines (google/bing/ddg) cover LSE's mix. Research-task incident pt2 (sha256 fd65fea6…) |
| **Cogitator v1.7.7** | 2026-06-12 | fetch_url CONTENT-TYPE GUARD: PDF→pdfminer/pypdf text extract (clean refusal if neither lib present), other non-text content-types refused, all output control-char sanitized. fetch_url fed resp.text to HTMLParser unconditionally → PDF dumped raw FlateDecode binary into context AND broke OWUI <details> rendering downstream. Research-task incident (sha256 fa8bd376…) |
| **Cogitator v1.7.6** | 2026-06-12 | hermes_plan() pre-flight planner (wraps call_hermes intent=plan, parses envelope, writes initial task block, degrades to PLANNER UNAVAILABLE); FIXES call_hermes error handling truncated since v1.7.3 — HTTPError fell through to None, URLError raised uncaught (sha256 7a516246…) |

---

## pfsense-agent Version History

| Version | Shipped | Key change |
|---|---|---|
| **v1.0** | 2026-06-09 | Initial — Qwen3.6 orchestrator + LSE submit; `--think/--no-think/--prompt-only/--auto`; `_extract_prompt` DO NOT anchor + contiguous step sequence; tool_ids pass-through |
