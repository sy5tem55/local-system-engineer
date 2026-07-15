# Local System Engineer (LSE): Your AI Sysadmin That Actually Works

Forget chatbots that give you advice. LSE is a locally-hosted AI system administrator that acts, executing commands, managing services, rotating credentials, and deploying fixes across your networking infrastructure. Built on a private inference stack (Qwen 27B), it operates within strict permission boundaries: no silent privilege escalation, no cloud dependencies, no hallucinated commands.

LSE doesn't just answer questions, it enforces protocols. Every operation follows a KB-first discipline: check documented procedures before acting, verify outcomes with ground-truth probes, and record failures for continuous improvement. It manages a living knowledge base of empirically tested runbooks, an RFC authority index for protocol-level diagnosis, and a challenge arena where LLMs compete on real sysadmin problems drawn from live infrastructure.

The stack spans WSL2/Ubuntu, remote GPU nodes (node3090/node5090), pfSense firewalls, Grafana monitoring, Vaultwarden secrets management, and self-hosted web search. LSE orchestrates them all through a unified MCP gateway with 45 tools, from SSH orchestration and Docker management to network discovery and firewall log analysis. It delegates privilege escalation to you, never runs it silently.

Built for networking infrastructure operators who want AI that respects their infrastructure. No SaaS lock-in, no data leaving your network, no "let me think about that", just precise, verified actions with evidence trails you can audit.

**Key capabilities:**
- Multi-node orchestration (WSL2 + remote GPU nodes via SSH)
- Empirical knowledge base with decay tracking and human correction
- RFC authority index for protocol-level diagnosis
- Challenge arena with leaderboard for continuous LLM evaluation
- Vaultwarden integration for secrets management
- Grafana/Prometheus monitoring integration
- pfSense firewall management and log analysis
- Strict permission boundaries with privilege delegation

---

# Local System Engineer (LSE)

A locally-hosted AI system administrator running on a private inference stack. Operates within a strict permission boundary on WSL2/Ubuntu 24.04: executes shell commands, reads/writes files in allowed paths, delegates sudo to the user, searches the web only on demand, and never escalates privileges silently.

---

## Current Stack

| Layer | Component |
|---|---|
| Host | Windows 11 → WSL2 → Ubuntu 24.04 (hostname: LUCIFER) |
| Inference | llama.cpp `llama-server` |
| Model | Qwen3.6-27B-Q4_K_M (KV:q8_0 · think:3072) |
| Frontend | llama-ui (built into llama-server, localhost:8080) |
| MCP Gateway | goethe_mcp.py v1.9.3 · port 9700 · `bash tools/start-goethe.sh` |
| Web search | SearxNG (self-hosted, localhost:8088) |
| Monitoring | Prometheus + Grafana |
| Launcher | Windows Terminal PowerShell profiles (lse-stack-launch-*.ps1) |
| KB / RAG | Elasticsearch (lse-kb + lse-rfc-kb) + Ollama nomic-embed-text |
| RFC Authority | 20 RFCs indexed · `lse-rfc-kb` · authority_ceiling/recency/confirmation model |

---

## Current Component Versions

| Component | Version | File |
|---|---|---|
| Tool | **Goethe v0.2.5** | `tools/goethe.py` |
| MCP Gateway | **goethe_mcp v1.9.3** | `tools/goethe_mcp.py` |
| System Prompt (LUCIFER) | **v0.5.18** | `tools/system-prompt-v0.5.18.md` |
| System Prompt (node3090) | **v0.1.0** | `tools/system-prompt-node3090-v0.1.0.md` |
| Routing filter | v1.2.0 | `tools/lse-routing-filter-v1.2.0.py` |
| Vaultwarden Tool | v1.3.0 | `tools/vaultwarden_tools_v1.3.0.py` |
| Launcher CLI | v1.078 | `LSEStack_gui/lse-stack-launch-1.078.ps1` |
| Launcher GUI | v1.5 | `LSEStack_gui/lse-stack-launch-gui.ps1` |

---

## LSE Challenge Arena

An evaluation arena where LLMs compete on real sysadmin problems drawn from live infrastructure. Solutions that pass sandbox assertions get deployed to production.

| Component | File | Description |
|---|---|---|
| ChallengeDB | `/opt/local-se/challenges.db` | 24 challenges seeded (T1–T3) |
| Leaderboard | `/opt/local-se/leaderboard.db` | Episode scores by model |
| LSEChallengeEnv | `scripts/lse_challenge_env.py` | gymnasium.Env harness |
| EscalationWrapper | `scripts/escalation_wrapper.py` | Stagnation detection + Claude API |
| LeaderboardService | `scripts/leaderboard.py` | Score tracking + standings |
| run_episode.py | `scripts/run_episode.py` | Full episode runner |
| ChallengeGenerator | `scripts/challenge_generator.py` | Auto-proposes follow-up challenges from discoveries |

**Run an episode:**
```bash
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
python3 scripts/run_episode.py --challenge pf-t1-001 --model "qwen3.6-27b-q4-64k"
python3 scripts/run_episode.py --list          # show all challenges
python3 scripts/run_episode.py --challenge pf-t1-001 --dry-run  # prompt preview only
```

**Review auto-generated challenges:**
```bash
python3 scripts/challenge_generator.py --list-pending
python3 scripts/challenge_generator.py --approve auto-pf-t1-002-unexpected-abc123
```

---

## RFC Authority KB

20 core RFCs (DHCP, DNS, TLS, TCP, HTTP, Syslog, NTP, NAT, NFS) chunked and indexed.

```bash
python3 scripts/rfc_kb.py --search "DHCP client retransmits after receiving ACK"
python3 scripts/rfc_kb.py --search "TLS certificate verify failed" --protocol tls
python3 scripts/rfc_kb.py --status
```

Quality model: `quality_score = min(authority_ceiling, raw × confirmation_weight × recency_weight)`

---

## Agent Capabilities

- Read files within `/home/` `/etc/` `/var/log/` `/tmp/lse/` `/opt/local-se/`
- Write files within `/home/` `/tmp/lse/` `/opt/local-se/`
- Execute shell commands (never >80 lines raw output)
- Delegate any `sudo` to the user via `sudo_delegation_block` — never runs sudo itself
- `pfsense_log_summary()` — compact firewall log analysis (never returns raw logs)
- `nmap_summary()` — XML-parsed port scan (never returns raw nmap text)
- `search_kb` / `index_to_kb` / `record_error` / `check_error_kb` / `mentor_correct` — ES RAG layer
- `search_web` via SearxNG · `fetch_url` for full-page fetch (reddit: camoufox/Firecrawl fallback)
- `search_reddit()` — reddit search via SearxNG
- `pfsense_query()` / `pfsense_graphql()` / `pfsense_log_summary()` — pfSense REST API v2
- `wake_node()` / `shutdown_node()` — node lifecycle (ping-first, two-step confirmation for shutdown)
- `get_github_release()` — fetch verified release version before pinning any version string
- `hermes_plan()` — inline pre-flight planner via Hermes API
- `skill_search` / `skill_record` / `skill_outcome` — occupational self-learning skills layer
- `task_checkpoint` / `task_resume` — SQLite-backed task state persistence

**Permanently blocked:** `mkfs fdisk parted iptables -F passwd visudo wipefs dd if=`

---

## Security Model

**No autonomous sudo.** Every privileged operation emits a `sudo_delegation_block`.
**Confirmation before destruction.** Any `rm`, truncate, or overwrite requires explicit yes/no.
**Read before write.** Any sudo touching a config file must read current state first.
**pfSense write access** is a named temporary elevation — re-enable Read Only before session ends.

---

## MCP Gateway

```
llama-ui (llama-server :8080) → MCP client → goethe_mcp.py (:9700, bearer-token-gated)
→ goethe.py Tools class (execute_command, search_kb, pfsense_*, etc.)
```

Start: `bash ~/projects/local-system-engineer/tools/start-goethe.sh`
node3090: `bash ~/projects/local-system-engineer/tools/start-goethe-node3090.sh`

---

## Repository Layout

```
local-system-engineer/
├── README.md / ROADMAP.md / CURRENT-STATE.md / CHANGELOG.md / VERSION.md / VALVES.md
├── session-handover.md          ← read at start of every session
│
├── docs/
│   ├── 01–09-*.md               ← design docs
│   ├── 10-log-summariser.md     ← pfsense_log_summary + nmap_summary design
│   ├── lse-challenge-arena.md   ← Arena full design doc
│   └── network-topology.md     ← live network map + T1 challenge set
│
├── prompts/
│   ├── CHANGELOG.md
│   ├── claude-l2-system-prompt.md  ← Claude Opus L2 + Sonnet Research system prompts
│   └── v0.1-baseline.md … v0.5.14.md  ← Qwen3 LSE agent prompt versions
│
├── scripts/
│   ├── lse_challenge_env.py     ← gymnasium.Env
│   ├── escalation_wrapper.py   ← stagnation + Claude escalation
│   ├── leaderboard.py          ← SQLite score tracker
│   ├── run_episode.py          ← full episode runner (CLI)
│   ├── challenge_generator.py  ← discovery → follow-up challenge
│   ├── rfc_kb.py               ← RFC corpus ingestion + search
│   ├── seed_challengedb.py     ← seed /opt/local-se/challenges.db
│   ├── systemd/                ← repository-owned service/timer units
│   └── test_*.py               ← smoke tests
│
├── tools/
│   ├── goethe.py                    ← current production tool (Goethe v0.4.0-a, stable filename)
│   ├── goethe_mcp.py                ← MCP gateway server (v1.11.1, TRAUM episode journaling)
│   ├── dream_runner.py              ← TRAUM offline dream passes (proposes, never writes ES)
│   ├── dream_apply.py               ← TRAUM human confirm-gate + --queue (the ONLY dream write path)
│   ├── dream_digest.py              ← TRAUM ≤30-line morning digest
│   ├── run-dream-cycle.sh            ← fail-visible five-pass nightly cycle
│   ├── episode_index.py             ← episode manifest.db build + rotation
│   ├── start-goethe.sh              ← LUCIFER MCP startup script
│   ├── start-goethe-node3090.sh     ← node3090 MCP deploy + startup script
│   ├── system-prompt-v0.5.18.md    ← current LUCIFER system prompt
│   ├── system-prompt-node3090-v0.1.0.md ← node3090 agent system prompt
│   ├── vaultwarden_tools_v1.3.0.py ← Vaultwarden MCP tool
│   ├── lse-routing-filter-v1.2.0.py
│   └── goethe-v0.2.*.py / cogitator-v1.7.*.py  ← version history
│
├── prompts/
│   ├── CHANGELOG.md
│   └── v0.5.15.md               ← last OWUI-era system prompt (archived)
│
├── eval/
│   ├── eval-report-v6.md        ← Run 7: 62/63 (projected); see VERSION.md Co-test Matrix
│   ├── traum-ab-design.md       ← TRAUM A/B learning-lift eval design (pre-registered criterion)
│   ├── eval-report-traum-1.md   ← TRAUM A/B run 1 verdict: LOSS (methodologically inconclusive — see §6-7)
│   ├── v35_harness.py           ← v3.5 suite harness (reconstruction; original was never committed)
│   └── retrieval-gold-v1.jsonl  ← frozen retrieval gold set (sha256 in traum-ab-design.md)
│
└── docs/dreaming/               ← TRAUM design + run artifacts (DESIGN.md, corpus-audit, calibration)
```
