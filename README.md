# Local System Engineer (LSE)

A locally-hosted AI system administrator running on a private inference stack. Operates within a strict permission boundary on WSL2/Ubuntu 24.04: executes shell commands, reads/writes files in allowed paths, delegates sudo to the user, searches the web only on demand, and never escalates privileges silently.

---

## Current Stack

| Layer | Component |
|---|---|
| Host | Windows 11 → WSL2 → Ubuntu 24.04 (hostname: LUCIFER) |
| Inference | llama.cpp `llama-server` |
| Model | Qwen3.6-27B-Q4_K_M (64k ctx · KV:q8_0 · think:3072) |
| Frontend | OpenWebUI (localhost:3000) |
| Web search | SearxNG (self-hosted, localhost:8088) |
| Monitoring | Prometheus + Grafana + context alert pipeline |
| Launcher | Windows Terminal PowerShell profiles (lse-stack-launch-*.ps1) |
| KB / RAG | Elasticsearch (lse-kb + lse-rfc-kb) + Ollama nomic-embed-text |
| RFC Authority | 20 RFCs indexed · `lse-rfc-kb` · authority_ceiling/recency/confirmation model |

---

## Current Component Versions

| Component | Version | File |
|---|---|---|
| Tool | **Cogitator v1.7.13** | `tools/cogitator-v1.7.13.py` |
| Prompt | v0.5.15 | `prompts/v0.5.15.md` |
| Routing filter | v1.2.0 | `tools/lse-routing-filter-v1.2.0.py` |
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
- `search_kb` / `index_to_kb` / `record_error` / `check_error_kb` — ES RAG layer
- `search_web` via SearxNG · `fetch_url` for full-page fetch
- `pfsense_query()` — pfSense REST API v2 (read-only by default)

**Permanently blocked:** `mkfs fdisk parted iptables -F passwd visudo wipefs dd if=`

---

## Security Model

**No autonomous sudo.** Every privileged operation emits a `sudo_delegation_block`.
**Confirmation before destruction.** Any `rm`, truncate, or overwrite requires explicit yes/no.
**Read before write.** Any sudo touching a config file must read current state first.
**pfSense write access** is a named temporary elevation — re-enable Read Only before session ends.

---

## Context Alert Pipeline

```
llama-server /metrics → llama-context-exporter (port 9836)
→ Prometheus → Grafana alert (KV > 80%) → grafana-owui-adapter (port 9837)
→ OpenWebUI lse-alerts channel
```

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
│   └── test_*.py               ← smoke tests
│
├── tools/
│   ├── cogitator-v1.7.13.py        ← current production tool (READY FOR DEPLOY)
│   ├── cogitator-v1.7.12.py        ← previous deployed version
│   └── lse-routing-filter-v1.2.0.py
│
├── prompts/
│   ├── CHANGELOG.md
│   └── v0.5.15.md               ← current production prompt
│
└── eval/
    └── eval-report-v6.md        ← Run 7: 62/63 (projected); see VERSION.md Co-test Matrix
```
