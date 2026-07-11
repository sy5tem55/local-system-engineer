# TRAUM dedup threshold-labeling worksheet

floor=0.75 band-width=0.03 thresholds=(0.78, 0.82, 0.86) sample-n=20

> **Claude's first pass (2026-07-11):** every pair below was read (title + content
> preview, not title alone). 38 pairs looked clear-cut and are pre-checked;
> 17 were genuinely ambiguous and left with a `NOTE (Claude):` explaining why.
> **All 55 pairs are now fully labeled** — the 16 that needed a real judgment
> call are marked `RESOLVED (Joe): ...`; the remaining `NOTE (Claude):` entries
> are Claude's own confident calls, kept as-is for context, plus corpus-hygiene
> flags (title/content mismatches, a real gap in the same-document-chunk filter,
> and one doc that looks stale/contradicted rather than duplicated) that are
> independent of the label itself.

## Threshold 0.78 — band [0.78, 0.81) — 20 pair(s) sampled

1. cosine=0.8077
   A doc_id=3a8fce016b8e06d7 title='SearxNG Configuration Reference'
      '# SearxNG Configuration Reference\n# Path: /opt/local-se/kb/searxng-config.md\n# Use this file before proposing any settings.yml changes.\n\n---\n\n## Paths (Docker install)\n\nSettings:  `/home/sy5/searxng-d'
   B doc_id=9eb1b0d523213788 title='SearXNG Observability Stack — Complete Deployment Reference'
      '# SearXNG Observability Stack — Complete Deployment Reference\n\n## Architecture\n```\n┌─────────────┐     /metrics      ┌──────────────┐     /api/v1/query     ┌──────────────┐     SQLite\n│  SearXNG    │ '
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

2. cosine=0.8051
   A doc_id=24315e0811489a72 title='Open-Source Claude Alternatives — Complete Setup (OpenCode + Hermes + Open Design)'
      '# Hermes Agent — Telegram API Gateway + OpenWebUI Webhook Integration\n\n**System:** LUCIFER (WSL2 Ubuntu 24.04)\n**Date:** 2026-06-10\n**Verified:** End-to-end tested and operational\n\n---\n\n## Architectur'
   B doc_id=a9361df7b6b60bb8 title='Hermes Ports on node3090 — 8642 (API) / 8643 (socat relay) / 8644 (webhook)'
      '## Hermes Ports on node3090 — Architecture\n\n**Verified:** 2026-06-13 via live SSH, ss, ps, curl, call_hermes tool\n\n### Port Map\n\n| Port | Service | Auth | Bind | Purpose |\n|---|---|---|---|---|\n| **86'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

3. cosine=0.8044
   A doc_id=80b95f2e6c7f6fbb title='LSE Session Learnings (part 11)'
      'common endpoint"\n  **Failed because:** No prohibition — model treated it as a valid call for log analysis,\n  bypassing pfsense_log_summary entirely\n  **Fix:** Add LOG ENDPOINT PROHIBITION block to pfs'
   B doc_id=2544fd6f9f1c314a title='Session Learnings'
      '# LSE Session Learnings\n\nCumulative KB entries from post-session debriefs.\n\n## Session 2026-06-07 — Qwen 3.6 cross-file invariant failures in net-discovery\n\n### What worked\n- Rewriting `echarts_topolo'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — the older unchunked copy is superseded by
   the newer chunked re-index.

4. cosine=0.8011
   A doc_id=1b3b75067b99b255 title='Firecrawl on node3090 — Complete Working Configuration'
      '## Firecrawl on node3090 — Final Working Configuration\n\n**Updated:** 2026-06-17\n\n### API Endpoints\n- **Firecrawl API:** `http://192.168.5.41:3002`\n- **Ollama (CPU-only):** `http://192.168.5.41:11434`\n'
   B doc_id=2806106e29d36ae8 title='node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname…'
      'node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname `node3090.home.arpa` also works for ping/SSH but use IP for curl to avoid any DNS edge cases.'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

5. cosine=0.8009
   A doc_id=0137a0837f68a0f7 title='llama (part 3)'
      '****************************************************************** B E N C H M A R K *******************************************************************************\nYou are ready to run a local llama-'
   B doc_id=d63cb472db11e468 title='llama.cpp Build Reference'
      '## llama.cpp Build on node3090 — Corrected CMake Flags (b9967+)\n\n**Source:** `/home/lse-admin/llama.cpp` (git clone of ggerganov/llama.cpp master)\n**Build dir:** `/home/lse-admin/llama.cpp/build/`\n**D'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Correcting the guide you were given — it suggested
   "true-duplicate" for this pair based on titles alone. Read the content: A is
   a benchmark script header, B is CMake build flags. Different topics under a
   shared "llama" keyword — exactly the false-merge trap the guide itself warns
   about one row up (pair #1).

6. cosine=0.8007
   A doc_id=6c29a64b2e33ae4f title='pfSense Log Gateway — Complete Reference (part 3)'
      '-------|-------------|---------|\n| Full log fetch | ~10,000+ tokens | ~200 tokens | 98% |\n| Tail 50 lines | ~5,000+ tokens | ~100 tokens | 98% |\n| Incremental delta | ~5,000+ tokens | ~50 tokens | 99%'
   B doc_id=7f761f42a2f55566 title='LSE Session Learnings (part 10)'
      "ed — long/privileged jobs run from WSL\n- lse-kb.sqlite is vestigial (0 bytes, no code references it — tool v1.6.4's only sqlite is the OWUI chat DB)\n- Two repo clones on LUCIFER (~/projects vs /mnt/c)"
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

7. cosine=0.7930
   A doc_id=772eff9665357474 title='LSE Architecture — Technical Design Document (part 2)'
      '───────────────────────────────────────┐\n│  VPS (external)                                             │\n│  SearxNG (Docker) — metasearch proxy, randomised UA         │\n│  Reddit engine BLOCKED on VPS'
   B doc_id=32b5f882ffa05707 title='LSE Goethe MCP Server — Architecture and Reference'
      '# LSE Goethe MCP Server — Reference\n\n**Source:** `/home/sy5/projects/local-system-engineer/tools/goethe_mcp.py`\n**Python:** `/home/sy5/owui/bin/python3` (OpenWebUI venv)\n\n## Canonical Startup Command\n'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

8. cosine=0.7921
   A doc_id=dda6a706809d5851 title='Gemma 4 31B as Planner in Multi-Agent Coding Workflows — Research Synthesis'
      '## Gemma 4 31B for Multi-Agent Coding Workflows — Key Findings (Jun 2026)\n\n### Performance Benchmarks\n- **τ2-bench Retail (agentic tool use)**: Gemma 4 31B = 86.4%, Gemma 3 27B = 6.6% — massive improv'
   B doc_id=c45355b2847b6d08 title='r/LocalLLaMA Community Findings: VS Code Insiders & Multi-Agent Coding Workflows'
      '## r/LocalLLaMA: VS Code Insiders & Multi-Agent Coding Workflows — Community Findings (Jun 2026)\n\n### Key Posts Scraped via Firecrawl/Camoufox on node3090\n\n#### 1. Qwen3.5-35B-A3B for Agentic Coding w'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

9. cosine=0.7914
   A doc_id=5bdcb7028c158353 title='pfSense Log Gateway — Complete Reference'
      '# pfSense Log Gateway — Complete Reference\n\n> **Source of Truth** — This single document covers architecture, tool integration, and usage.\n> **KB doc_id:** 471b028dc810773d | **Quality:** 0.95\n\n---\n\n#'
   B doc_id=3a527e6092ea7b37 title='pfSense REST API — General'
      'General Home Edit on GitHub pfSense REST API The pfSense REST API package is an unofficial, open-source REST and GraphQL API for pfSense CE and pfSense Plus\nfirewalls. It is designed to be light-weigh'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

10. cosine=0.7898
   A doc_id=cbce62b2a37c0830 title='LSE — Local System Engineer'
      '# LSE — Local System Engineer\n\n**What LSE is:** LSE (Local System Engineer) is the OpenWebUI tool agent that\nmanages the homelab infrastructure on behalf of SY5. It runs against the local\nQwen3.6-27B '
   B doc_id=a5139fec3afdb3eb title='start_node_agent stale parameters — OpenWebUI in-memory tool cache'
      "## Problem\nstart_node_agent() on LUCIFER launches llama-server on node3090 with stale parameters from OpenWebUI's in-memory tool cache. The on-disk `_NODE_REGISTRY` in `/opt/local-se/openwebui-tool-v1"
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

11. cosine=0.7890
   A doc_id=017e3a0378cde0fc title='LSE Session Learnings (part 5)'
      'broken for Docker and bare hostnames).\n  **Fix:** Restore resolv.conf manually:\n  ```bash\n  echo -e "nameserver 10.255.255.254\\nnameserver 192.168.1.50\\nsearch home.arpa" | tee /etc/resolv.conf\n  ```\n'
   B doc_id=de52870fae4bbf80 title='Kb Entry Es Memory Floor'
      '## 2026-06-01 — Elasticsearch memory floor + Compose migration\n\n### What happened\nElasticsearch was repeatedly exiting with code 143 (SIGTERM from Docker OOM enforcement)\nduring long sessions. Root ca'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

12. cosine=0.7882
   A doc_id=772eff9665357474 title='LSE Architecture — Technical Design Document (part 2)'
      '───────────────────────────────────────┐\n│  VPS (external)                                             │\n│  SearxNG (Docker) — metasearch proxy, randomised UA         │\n│  Reddit engine BLOCKED on VPS'
   B doc_id=40b072ca9dd0261c title='Start Claude Code with Free Proxy (Daily Workflow)'
      '## Free Claude Code Proxy — Per-Tier Routing Config (2026-06-17)\n\n**Proxy:** `fcc-proxy` Docker container on `localhost:8082`\n**Config:** `/home/sy5/.fcc/.env` (root-owned, chmod 644)\n**Image:** `free'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

13. cosine=0.7878
   A doc_id=a65a32b191607ebe title='LSE Session Learnings (part 7)'
      'ovider_custom:` dict with `custom_providers:` list:\n  ```yaml\n  model:\n    provider: custom\n    model: Qwen3.6-27B-Q4_K_M.gguf\n    base_url: http://localhost:8080/v1\n  custom_providers:\n    - name: Lo'
   B doc_id=c11e2f4fec824966 title='Hermes Restart Procedure — node3090 Stack Recovery'
      '## Hermes Restart Procedure — node3090 Stack Recovery\n\n**Ground Truth Verified:** 2026-06-17 — daemon-reload + enable + start confirmed working.\n\n**SYMPTOMS:** Hermes not responding on Telegram / port'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

14. cosine=0.7866
   A doc_id=224ee06461831e55 title='Goethe MCP Running Versions — 2026-07-01'
      '# Goethe MCP — Running Versions (2026-07-01)\n\n## Current Versions\n\n| Component | Version | Path |\n|---|---|---|\n| `goethe_mcp.py` | **1.9.3** | `/home/sy5/projects/local-system-engineer/tools/goethe_m'
   B doc_id=27d457e4c665d19a title='Three different version strings currently coexist for "Goethe": `tools/goethe.py`…'
      'Three different version strings currently coexist for "Goethe": `tools/goethe.py` title/version = v0.3.8 (live, matches CURRENT-STATE.md changelog line), `goethe_mcp` startup banner = v1.9.3, and the '
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — same underlying subject; the inconsistency
   finding effectively supersedes/corrects the version snapshot table.

15. cosine=0.7860
   A doc_id=875f1a30d7a17cd1 title='node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)'
      'node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)'
   B doc_id=a1a3b09b26dc56e4 title='ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds…'
      'ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds :8642 direct.'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)

16. cosine=0.7855
   A doc_id=6f61153e03d041f4 title='pfSense REST API v2 — Firewall Rule Operations (Complete Reference) (part 3)'
      'Block a specific IP on LAN:**\n```bash\ncurl -X POST -H "X-API-Key: <key>" -H "Content-Type: application/json" \\\n  https://pfsense.home.arpa/api/v2/firewall/rule \\\n  -d \'{"type":"block","interface":"lan'
   B doc_id=ed793c952f253e75 title='pfSense REST API v2 — Comprehensive Endpoint Reference'
      '# pfSense REST API v2 — Comprehensive Reference\n\n**Source:** pfrest.org (official REST API package documentation)\n**Local Swagger UI:** `https://pfsense.home.arpa/api/v2/documentation` (verified acces'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — the comprehensive reference already covers
   the firewall-rule-operations content.

17. cosine=0.7848
   A doc_id=ab0f3ce1904c6ff7 title='LSE Session Learnings (part 15)'
      'ALLED)\n- Hermes /status "Agent Running: No" = normal idle (agent spawns per conversation)\n- EscalationWrapper auto-indexed 4 junk web-search docs at quality 0.7 during stagnation\n  (episodes #32-35) —'
   B doc_id=c11e2f4fec824966 title='Hermes Restart Procedure — node3090 Stack Recovery'
      '## Hermes Restart Procedure — node3090 Stack Recovery\n\n**Ground Truth Verified:** 2026-06-17 — daemon-reload + enable + start confirmed working.\n\n**SYMPTOMS:** Hermes not responding on Telegram / port'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

18. cosine=0.7838
   A doc_id=e2e670e6a254f6b2 title='LSE Session Learnings (part 6)'
      'n port **9120**, not 9101. Port 9101 had a half-open TCP\n  connection from a previous session. `curl -s` without `--max-time` blocks forever.\n  **Fix:** Always use `curl -s --max-time 3` for health ch'
   B doc_id=47e63e36edcd0421 title='LSE Stack Troubleshooting Guide (part 7)'
      'Cowork bash tool.\n```bash\n# In WSL terminal (not Cowork bash):\ncd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer\ngit add -A\ngit commit -m "fix: <description>"\n```\n\nIf `.git/index.lock` exists:'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

19. cosine=0.7837
   A doc_id=cbce62b2a37c0830 title='LSE — Local System Engineer'
      '# LSE — Local System Engineer\n\n**What LSE is:** LSE (Local System Engineer) is the OpenWebUI tool agent that\nmanages the homelab infrastructure on behalf of SY5. It runs against the local\nQwen3.6-27B '
   B doc_id=a130e2457855ff5b title='Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`,…'
      'Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`, `start-hermes-gateway.sh`.'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

20. cosine=0.7835
   A doc_id=3ce2548ed1f20f94 title='SearXNG Observability Stack — Complete Deployment Reference (part 2)'
      'g\n- Engine comparison analysis\n- Historical performance trending\n\n### Grafana Use Cases\n- Real-time engine health dashboard\n- Request/response time visualization\n- Reliability trend charts\n- Custom al'
   B doc_id=2ea0b7a5e8760026 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 3)'
      'g(timestamp);\nCREATE INDEX idx_engine ON query_log(engine);\nCREATE INDEX idx_date ON query_log(date(timestamp));\n```\n\n### Query Examples\n\n```sql\n-- Daily queries per engine\nSELECT date(timestamp) as d'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — same underlying overlap as the "Deployment
   Guide" vs "Deployment Plan" root-doc finding in the 0.86 band below.

## Threshold 0.82 — band [0.82, 0.85) — 20 pair(s) sampled

1. cosine=0.8496
   A doc_id=017e3a0378cde0fc title='LSE Session Learnings (part 5)'
      'broken for Docker and bare hostnames).\n  **Fix:** Restore resolv.conf manually:\n  ```bash\n  echo -e "nameserver 10.255.255.254\\nnameserver 192.168.1.50\\nsearch home.arpa" | tee /etc/resolv.conf\n  ```\n'
   B doc_id=c3699d6b2274c019 title='LSE Stack Troubleshooting Guide (part 3)'
      '`nameserver ::1` which is broken.\n\n**Diagnosis:**\n```bash\ncat /etc/resolv.conf\n# Broken: nameserver ::1\n# Correct: nameserver 10.255.255.254 + nameserver 192.168.1.50\n```\n\n**Fix:**\n```bash\necho -e "na'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   NOTE (Claude): Content previews contain nearly identical text for the same
   resolv.conf fix (same nameserver values, same fix). Looks like the same fix
   got documented in two different KB series (session-learnings vs
   troubleshooting-guide) — a good example of a real cross-series duplicate.

2. cosine=0.8471
   A doc_id=182fcf50245bbe11 title='Camofox v150.0.2 — Upgrade and Bug Fixes on node3090'
      '## Camoufox Browser v150.0.2 on node3090\n\n**Updated:** 2026-07-01 — MAX_SNAPSHOT_CHARS increased to 120000. Wrapper script v3 with action chain.\n**Official sources:** https://camoufox.com/ , https://g'
   B doc_id=5bfd23c475f47d4c title='Reddit extraction requires Camoufox — fetch_url returns empty'
      '## Reddit Extraction Requires Camoufox\n\n**Observed:** 2026-06-28\n**Verified against:** https://camoufox.com/ , https://github.com/jo-inc/camofox-browser\n\n**Problem:** `fetch_url` returns empty for Red'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

3. cosine=0.8469
   A doc_id=9eb1b0d523213788 title='SearXNG Observability Stack — Complete Deployment Reference'
      '# SearXNG Observability Stack — Complete Deployment Reference\n\n## Architecture\n```\n┌─────────────┐     /metrics      ┌──────────────┐     /api/v1/query     ┌──────────────┐     SQLite\n│  SearXNG    │ '
   B doc_id=b42f019546c3648b title='SearXNG SQLite Query Logger - Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — this is the crux decision for the whole
   "Deployment Plan" / "Deployment Reference" cluster; see band 0.86 pair #5
   for the direct root-vs-root call these other pairs inherit from.

4. cosine=0.8457
   A doc_id=165efd6ec8ea78af title='LSE Architecture — Technical Design Document (part 8)'
      '| P2 | DHCP option 119 | Add `home.arpa` search domain so `ssh node3090` resolves without FQDN. |\n| P3 | node5090 setup | WoL + SSH deferred. |\n| P3 | RTX 2080Ti install | Watercooling loop prep requi'
   B doc_id=c296b8146fc89fd1 title='SY5 Home Network Map'
      '## node3090 DNS Resolution Fix — systemd-resolved Uses Cloudflare Instead of pfSense\n\n**Date:** 2026-06-17\n**Verified:** ground truth via SSH to node3090\n\n### Symptom\nnode3090 cannot resolve internal '
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

5. cosine=0.8440
   A doc_id=a5dbb4286ac84a8a title='Goethe MCP restart reference — LUCIFER HTTP, node3090, Claude stdio bridge'
      'Three goethe_mcp instances exist; each restarts differently. For the step-by-step runbook use skill_search("restart goethe mcp gateway") — this entry is the fact sheet.\n\n1) LUCIFER HTTP gateway (serve'
   B doc_id=32b5f882ffa05707 title='LSE Goethe MCP Server — Architecture and Reference'
      '# LSE Goethe MCP Server — Reference\n\n**Source:** `/home/sy5/projects/local-system-engineer/tools/goethe_mcp.py`\n**Python:** `/home/sy5/owui/bin/python3` (OpenWebUI venv)\n\n## Canonical Startup Command\n'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — same underlying subject (goethe_mcp
   restart/startup); the "fact sheet" framing doesn't add distinct content
   worth keeping separate from the architecture/reference doc.

6. cosine=0.8409
   A doc_id=915f23163c33d815 title='Llama Cpp Build'
      '# llama.cpp Build Reference\n\n**Host:** LUCIFER (WSL2 · Ubuntu · CUDA 13.3 · RTX 4090 sm_89)\n**Source:** `/home/sy5/llama.cpp`\n**Build dir:** `/home/sy5/llama.cpp/build`\n**Compiler:** GCC 14 (avoids GC'
   B doc_id=46c353706046d302 title='node3090 llama-server Launch Configuration'
      '## llama.cpp b9864 Binary Checksums — node4090\n\n**Build date:** 2026-07-09\n**Commit:** b5315e16e (b9864)\n**Compiler:** GCC 14.2.0, CUDA 13.3\n**Arch:** sm_89 (RTX 4090)\n**Flags:** FA_ALL_QUANTS=ON, CUD'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — separately flagging a likely KB metadata
   issue: doc_id 46c353706046d302 is titled "node3090 llama-server Launch
   Configuration" but its content preview is about node4090 binary checksums —
   title and content don't match on this doc. Worth a separate look regardless
   of the label. (Same doc_id recurs in pairs #20 below and band-0.86 #7.)

7. cosine=0.8365
   A doc_id=7934816b860f6640 title='goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of…'
      'goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of whether the path is written as `/mnt/c/...` or `C:\\Users\\...` — always delegate git and repo-root writes under th'
   B doc_id=866d12e9a0c38599 title='Repo copies identical: /home/sy5/projects/local-system-engineer/tools/goethe.py =='
      "`~/projects/local-system-engineer` is a symlink to `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` — same privileged-path block applies through the symlink for goethe's write_file, but Claude"
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   NOTE (Claude): Both describe the same specific finding (the privileged-path
   block covers /mnt/ and still applies through the ~/projects symlink).

8. cosine=0.8361
   A doc_id=f7e9ae27790fb3d1 title='Searxng Deployment Complete'
      '# SearXNG Observability Stack — Complete Deployment Reference\n\n## Architecture\n```\n┌─────────────┐     /metrics      ┌──────────────┐     /api/v1/query     ┌──────────────┐     SQLite\n│  SearXNG    │ '
   B doc_id=a0ce9558d6292a37 title='Searxng Sqlite Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Same two topics as pair #3 above (Observability Stack vs
   SQLite Query Logger Plan) — still NOT-duplicate as a pair (different
   subjects). But separately: this pair's own content previews are byte-for-byte
   identical to pair #3's A and B, under different, shorter titles
   ("Searxng Deployment Complete" / "Searxng Sqlite Deployment Plan"). That
   looks like the corpus has TWO aliased copies each of these two docs —
   a corpus-hygiene finding worth a look, separate from this pair's own label.

9. cosine=0.8319
   A doc_id=c296b8146fc89fd1 title='SY5 Home Network Map'
      '## node3090 DNS Resolution Fix — systemd-resolved Uses Cloudflare Instead of pfSense\n\n**Date:** 2026-06-17\n**Verified:** ground truth via SSH to node3090\n\n### Symptom\nnode3090 cannot resolve internal '
   B doc_id=3b0e47b762a28ee4 title='node4090 IS LUCIFER — DNS Alias and Docker Inventory'
      '## node4090 IS LUCIFER — DNS Alias Finding\n\n**Discovered:** 2026-06-28\n\n`node4090.home.arpa` resolves to **192.168.1.57**, which is the same IP as `lucifer.home.arpa`. They are the same machine — the '
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

10. cosine=0.8315
   A doc_id=9eb1b0d523213788 title='SearXNG Observability Stack — Complete Deployment Reference'
      '# SearXNG Observability Stack — Complete Deployment Reference\n\n## Architecture\n```\n┌─────────────┐     /metrics      ┌──────────────┐     /api/v1/query     ┌──────────────┐     SQLite\n│  SearXNG    │ '
   B doc_id=5777b93f0011a4da title='SearXNG OpenMetrics 404 Fix — open_metrics Must Be Under general: Not server:'
      '# SearXNG OpenMetrics Configuration Fix\n\n## The Problem\nThe `/metrics` endpoint returns **404 Not Found** even when `enable_metrics: true` is set and `open_metrics` password is configured.\n\n## Root Ca'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

11. cosine=0.8287
   A doc_id=6c52e923a4f17f40 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 4)'
      '/github.com/prometheus/OpenMetrics/blob/main/specification/OpenMetrics.txt\n4. **Prometheus Docs:** https://prometheus.io/docs/prometheus/latest/configuration/configuration/\n5. **SearXNG Issue #2154** '
   B doc_id=fee1c7eac5e9636f title='Searxng Metrics And Query Tracking'
      '# SearXNG Metrics & Query Tracking - Deployment Guide\n\n> Last updated: 2025-05-25\n> SearXNG version: 2026.5.17+d7e8b7cd1\n> Source: Container inspection + official docs + GitHub\n\n---\n\n## Architecture O'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): This is actually a same-document-chunk relationship that
   slipped past dream_runner.py's automated chunk filter — A is "(part 4)" of
   "SearXNG Metrics & Query Tracking - Deployment Guide," and B's content
   preview confirms it IS the base document of that exact series, just filed
   under a shortened alias title ("Searxng Metrics And Query Tracking" instead
   of the full series title) that didn't exact-string-match the filter's
   title-stripping logic. Correctly NOT a duplicate (merging would delete part
   4's distinct content) — but this is a real gap worth fixing in the filter:
   it only catches exact-match "(part N)" stripping, not aliased/shortened
   base titles for the same series.

12. cosine=0.8279
   A doc_id=c83f6c80d9b6c206 title='Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires…'
      'Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires root to read).'
   B doc_id=ef7c5158c105385c title='hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.'
      'hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

13. cosine=0.8267
   A doc_id=165efd6ec8ea78af title='LSE Architecture — Technical Design Document (part 8)'
      '| P2 | DHCP option 119 | Add `home.arpa` search domain so `ssh node3090` resolves without FQDN. |\n| P3 | node5090 setup | WoL + SSH deferred. |\n| P3 | RTX 2080Ti install | Watercooling loop prep requi'
   B doc_id=4eafc55c9055cf91 title='node3090 SSH Access Guide'
      '## node3090 SSH Access\n\n**Correct SSH key:** `~/.ssh/id_ed25519` (NOT `id_ed25519_node3090` — that key does NOT work)\n\n**Command:**\n```bash\nssh -i ~/.ssh/id_ed25519 lse-admin@node3090.home.arpa\n```\n\n*'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

14. cosine=0.8262
   A doc_id=1a622e182690fc76 title='Firecrawl on node3090 — Start/Stop Procedures'
      '# node3090 Full Startup Sequence — End to End\n\n**Updated:** 2026-07-11 — llama.cpp b9967 (v426). Added `--path` for llama-ui.\n**Hermes decommissioned:** hermes-gateway removed from stack (systemd unit'
   B doc_id=a130e2457855ff5b title='Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`,…'
      'Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`, `start-hermes-gateway.sh`.'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — separately flagging the title/content
   mismatch: A is titled "Firecrawl on node3090 — Start/Stop Procedures" but
   its content preview is the full node3090 startup sequence (mentions
   llama.cpp b9967, Hermes decommissioned) — not Firecrawl-specific. Worth a
   metadata fix independent of this pair's label.

15. cosine=0.8256
   A doc_id=1d3634f316c5f8e9 title='LSE Stack Troubleshooting Guide (part 2)'
      'kerd does not start automatically on reboot unless a startup script is configured.\n\n**Fix:**\n```bash\nsudo dockerd > /tmp/dockerd.log 2>&1 &\nsleep 5   # wait for socket creation — docker ps fails if yo'
   B doc_id=4fdfa57f3f600eb7 title='Troubleshooting'
      '# LSE Stack Troubleshooting Guide\n\n**Audience:** Models (Qwen3.6, Gemma) and humans diagnosing LSE failures.\n**Method:** Start with observation, determine root cause, apply the minimum fix, verify.\n**'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Same filter-gap pattern as pair #11 above: A is "(part 2)" of
   "LSE Stack Troubleshooting Guide," and B's content preview confirms it's the
   base doc of that same series ("# LSE Stack Troubleshooting Guide..."), just
   titled simply "Troubleshooting." Correctly NOT a duplicate (don't delete
   part 2's content) — another instance of the same alias-title filter gap.

16. cosine=0.8242
   A doc_id=835c8eec07f33fb3 title='Episteme Knowledge Graph Database Schema'
      'Episteme uses a SQLite-based graph database with two core tables: nodes (containing JSON metadata with unique id) and edges (containing source_id, target_id, and optional properties). The data is stor'
   B doc_id=8e0b786945667a5e title='Episteme v0.3.9 Schema Initialization Bug'
      "Episteme v0.3.9 on node4090 fails to initialize the knowledge graph schema ('nodes' and 'edges' tables) in ~/.episteme/db/episteme.db even after running 'epis install'. The installation script downloa"
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

17. cosine=0.8208
   A doc_id=1e82d6282fb2b839 title='Lse Architecture'
      '# LSE Architecture — Technical Design Document\n> Version: 2026-06-07 (aligned with tool v1.5.27)\n> Audience: coder LLM (node3090 agent) proposing changes + Claude Sonnet 4.6 as senior reviewer\n> Read '
   B doc_id=c45355b2847b6d08 title='r/LocalLLaMA Community Findings: VS Code Insiders & Multi-Agent Coding Workflows'
      '## r/LocalLLaMA: VS Code Insiders & Multi-Agent Coding Workflows — Community Findings (Jun 2026)\n\n### Key Posts Scraped via Firecrawl/Camoufox on node3090\n\n#### 1. Qwen3.5-35B-A3B for Agentic Coding w'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

18. cosine=0.8206
   A doc_id=cd24f2d5f7458cc7 title='LSE Session Learnings (part 4)'
      'it with `http://` again in curl\n- node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname `node3090.home.arpa` also works for ping/SSH but use IP for curl to avoid any DNS edge cases.\n'
   B doc_id=4fdfa57f3f600eb7 title='Troubleshooting'
      '# LSE Stack Troubleshooting Guide\n\n**Audience:** Models (Qwen3.6, Gemma) and humans diagnosing LSE failures.\n**Method:** Start with observation, determine root cause, apply the minimum fix, verify.\n**'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

19. cosine=0.8206
   A doc_id=e2e670e6a254f6b2 title='LSE Session Learnings (part 6)'
      'n port **9120**, not 9101. Port 9101 had a half-open TCP\n  connection from a previous session. `curl -s` without `--max-time` blocks forever.\n  **Fix:** Always use `curl -s --max-time 3` for health ch'
   B doc_id=e9fe28f028287726 title='LSE Stack Troubleshooting Guide (part 5)'
      'on port 1234):**\n```bash\n# Check reachability\nping -c1 192.168.5.41\n\n# Check LM Studio API\ncurl -sf http://192.168.5.41:1234/v1/models | python3 -c \\\n  "import json,sys; print(json.load(sys.stdin)[\'da'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)

20. cosine=0.8202
   A doc_id=46c353706046d302 title='node3090 llama-server Launch Configuration'
      '## llama.cpp b9864 Binary Checksums — node4090\n\n**Build date:** 2026-07-09\n**Commit:** b5315e16e (b9864)\n**Compiler:** GCC 14.2.0, CUDA 13.3\n**Arch:** sm_89 (RTX 4090)\n**Flags:** FA_ALL_QUANTS=ON, CUD'
   B doc_id=8d971a5f46a193ad title='Verified working llama-server command for node3090: `llama-server -m…'
      'Verified working llama-server command for node3090: `llama-server -m /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf -c 96000 -ngl 129 --flash-attn --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 -t 7 -t'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — same doc_id 46c353706046d302 title/content
   mismatch flagged at pair #6; treat as separate until that metadata issue is
   fixed at the source.

## Threshold 0.86 — band [0.86, 0.89) — 15 pair(s) sampled

1. cosine=0.8876
   A doc_id=6bea0aa609e187f1 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 2)'
      'ry query to SQLite with:\n- Timestamp\n- Query text (optional, can be hashed for privacy)\n- Engine used\n- Response time\n- Result count\n- Success/failure status\n\n**Pros:**\n- ✅ Full per-query history\n- ✅ '
   B doc_id=4ba7a03b9bd05d69 title='SearXNG SQLite Query Logger - Deployment Plan (part 2)'
      'Individual queries logged with timestamps\n- ✅ Can search query history by text or engine\n- ✅ No performance degradation\n\n### Risk: HIGH - Requires log parsing, potential performance impact\n\n---\n\n## Mi'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   NOTE (Claude): Both "(part 2)" of what look like two parallel, overlapping
   series ("...Deployment Guide" and "...Deployment Plan") describing the same
   SQLite query-logging feature set — near-identical bullet lists. See pair #5
   below for the root-doc comparison. A full resolution would mean deciding
   whether to merge the two whole series, not just this one pair.

2. cosine=0.8842
   A doc_id=915f23163c33d815 title='Llama Cpp Build'
      '# llama.cpp Build Reference\n\n**Host:** LUCIFER (WSL2 · Ubuntu · CUDA 13.3 · RTX 4090 sm_89)\n**Source:** `/home/sy5/llama.cpp`\n**Build dir:** `/home/sy5/llama.cpp/build`\n**Compiler:** GCC 14 (avoids GC'
   B doc_id=d63cb472db11e468 title='llama.cpp Build Reference'
      '## llama.cpp Build on node3090 — Corrected CMake Flags (b9967+)\n\n**Source:** `/home/lse-admin/llama.cpp` (git clone of ggerganov/llama.cpp master)\n**Build dir:** `/home/lse-admin/llama.cpp/build/`\n**D'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — these are build docs for two different
   physical machines (LUCIFER/RTX4090 vs node3090) with different source paths
   and flags; keep separate.

3. cosine=0.8805
   A doc_id=d63cb472db11e468 title='llama.cpp Build Reference'
      '## llama.cpp Build on node3090 — Corrected CMake Flags (b9967+)\n\n**Source:** `/home/lse-admin/llama.cpp` (git clone of ggerganov/llama.cpp master)\n**Build dir:** `/home/lse-admin/llama.cpp/build/`\n**D'
   B doc_id=1a622e182690fc76 title='Firecrawl on node3090 — Start/Stop Procedures'
      '# node3090 Full Startup Sequence — End to End\n\n**Updated:** 2026-07-11 — llama.cpp b9967 (v426). Added `--path` for llama-ui.\n**Hermes decommissioned:** hermes-gateway removed from stack (systemd unit'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — same title/content mismatch on B flagged
   at 0.82 #14; treat as separate until that metadata issue is fixed.

4. cosine=0.8799
   A doc_id=4ba7a03b9bd05d69 title='SearXNG SQLite Query Logger - Deployment Plan (part 2)'
      'Individual queries logged with timestamps\n- ✅ Can search query history by text or engine\n- ✅ No performance degradation\n\n### Risk: HIGH - Requires log parsing, potential performance impact\n\n---\n\n## Mi'
   B doc_id=fee1c7eac5e9636f title='Searxng Metrics And Query Tracking'
      '# SearXNG Metrics & Query Tracking - Deployment Guide\n\n> Last updated: 2025-05-25\n> SearXNG version: 2026.5.17+d7e8b7cd1\n> Source: Container inspection + official docs + GitHub\n\n---\n\n## Architecture O'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — cross-series pairing (Plan part 2 vs Guide
   base doc) is too indirect to merge on its own; see pair #5 below for the
   direct root-vs-root call on these two series.

5. cosine=0.8771
   A doc_id=fee1c7eac5e9636f title='Searxng Metrics And Query Tracking'
      '# SearXNG Metrics & Query Tracking - Deployment Guide\n\n> Last updated: 2025-05-25\n> SearXNG version: 2026.5.17+d7e8b7cd1\n> Source: Container inspection + official docs + GitHub\n\n---\n\n## Architecture O'
   B doc_id=a0ce9558d6292a37 title='Searxng Sqlite Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   NOTE (Claude): This is the crux pair for a whole cluster of others in this
   worksheet (0.78 #20, 0.82 #3/#8/#11, 0.86 #1/#4/#6/#8/#10/#12/#14): the
   BASE/root doc of the "SQLite Query Logger - Deployment Plan" series vs the
   BASE/root doc of the "Metrics & Query Tracking - Deployment Guide" series.
   Given how often these two series' content overlaps across this worksheet,
   they look like two whole document series describing the same underlying
   SearXNG SQLite logging work — the "Plan" likely predates and is superseded
   by the "Guide." I marked this true-duplicate, but flagging it prominently:
   this decision has the biggest blast radius of anything here, since a real
   merge would need to account for every part of BOTH series, not just these
   two root docs. Worth deciding this one first and letting it inform the
   related pairs above rather than treating each in isolation.

6. cosine=0.8765
   A doc_id=4ba7a03b9bd05d69 title='SearXNG SQLite Query Logger - Deployment Plan (part 2)'
      'Individual queries logged with timestamps\n- ✅ Can search query history by text or engine\n- ✅ No performance degradation\n\n### Risk: HIGH - Requires log parsing, potential performance impact\n\n---\n\n## Mi'
   B doc_id=a0ce9558d6292a37 title='Searxng Sqlite Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Filter-gap case again: A is "(part 2)" of "SearXNG SQLite
   Query Logger - Deployment Plan," and B's content confirms it's the base doc
   of that exact same series, titled just "Searxng Sqlite Deployment Plan"
   (missing "Query Logger -" from the full title, which is why the exact-match
   filter didn't catch it). Correctly NOT a duplicate — don't delete part 2's
   content.

7. cosine=0.8761
   A doc_id=46c353706046d302 title='node3090 llama-server Launch Configuration'
      '## llama.cpp b9864 Binary Checksums — node4090\n\n**Build date:** 2026-07-09\n**Commit:** b5315e16e (b9864)\n**Compiler:** GCC 14.2.0, CUDA 13.3\n**Arch:** sm_89 (RTX 4090)\n**Flags:** FA_ALL_QUANTS=ON, CUD'
   B doc_id=d63cb472db11e468 title='llama.cpp Build Reference'
      '## llama.cpp Build on node3090 — Corrected CMake Flags (b9967+)\n\n**Source:** `/home/lse-admin/llama.cpp` (git clone of ggerganov/llama.cpp master)\n**Build dir:** `/home/lse-admin/llama.cpp/build/`\n**D'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   RESOLVED (Joe): NOT a duplicate — same doc_id 46c353706046d302 title/content
   mismatch flagged at 0.82 #6/#20; treat as separate until that metadata
   issue is fixed at the source.

8. cosine=0.8734
   A doc_id=b42f019546c3648b title='SearXNG SQLite Query Logger - Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   B doc_id=fee1c7eac5e9636f title='Searxng Metrics And Query Tracking'
      '# SearXNG Metrics & Query Tracking - Deployment Guide\n\n> Last updated: 2025-05-25\n> SearXNG version: 2026.5.17+d7e8b7cd1\n> Source: Container inspection + official docs + GitHub\n\n---\n\n## Architecture O'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   NOTE (Claude): Same root-pair relationship as pair #5 above, but a
   DIFFERENT doc_id for the Plan side (b42f019546c3648b here vs a0ce9558d6292a37
   in pair #5) — meaning the corpus appears to have TWO separate near-duplicate
   copies of the "Plan" doc itself. Worth a look independent of this pair's label.

9. cosine=0.8721
   A doc_id=d8c34d69ebcffecb title='pfSense REST API v2 — Firewall Rule Operations (Complete Reference)'
      '# pfSense REST API v2 — Firewall Rule Operations (Complete Reference)\n\n**Source:** pfrest.org + pfSense-pkg-RESTAPI source + live Swagger at https://pfsense.home.arpa/api/v2/documentation\n**Topic:** p'
   B doc_id=4852d42064d2914e title='pfSense REST API v2 — Local Reference'
      '# pfSense REST API v2 — Local Reference\n\n> **Source:** https://github.com/pfrest/pfSense-pkg-RESTAPI (official)\n> **KB doc_id:** ed793c952f253e75 (quality 1.00, vector KB)\n> **Last updated:** 2026-07-'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — B is effectively a pointer to
   ed793c952f253e75 ("pfSense REST API v2 — Comprehensive Endpoint Reference,"
   band 0.78 #16) rather than independent content; safe to merge/collapse.

10. cosine=0.8719
   A doc_id=6bea0aa609e187f1 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 2)'
      'ry query to SQLite with:\n- Timestamp\n- Query text (optional, can be hashed for privacy)\n- Engine used\n- Response time\n- Result count\n- Success/failure status\n\n**Pros:**\n- ✅ Full per-query history\n- ✅ '
   B doc_id=fee1c7eac5e9636f title='Searxng Metrics And Query Tracking'
      '# SearXNG Metrics & Query Tracking - Deployment Guide\n\n> Last updated: 2025-05-25\n> SearXNG version: 2026.5.17+d7e8b7cd1\n> Source: Container inspection + official docs + GitHub\n\n---\n\n## Architecture O'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Same filter-gap pattern once more: A is "(part 2)" of the
   "Deployment Guide" series, B is that series' own base doc under the
   shortened alias title. Correctly NOT a duplicate.

11. cosine=0.8674
   A doc_id=c11e2f4fec824966 title='Hermes Restart Procedure — node3090 Stack Recovery'
      '## Hermes Restart Procedure — node3090 Stack Recovery\n\n**Ground Truth Verified:** 2026-06-17 — daemon-reload + enable + start confirmed working.\n\n**SYMPTOMS:** Hermes not responding on Telegram / port'
   B doc_id=1a622e182690fc76 title='Firecrawl on node3090 — Start/Stop Procedures'
      '# node3090 Full Startup Sequence — End to End\n\n**Updated:** 2026-07-11 — llama.cpp b9967 (v426). Added `--path` for llama-ui.\n**Hermes decommissioned:** hermes-gateway removed from stack (systemd unit'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): IMPORTANT — this isn't really a dedup question. B's content
   states "Hermes decommissioned: hermes-gateway removed from stack," which
   directly contradicts/obsoletes A ("Hermes Restart Procedure," ground-truth
   verified 2026-06-17, currently quality=0.2/stale=true in the live corpus).
   This looks like a genuine stale-contradiction finding (the kind Prompt 2.3's
   pass looks for), not a dedup case. Recommend a kb_verify/reverify or
   record_outcome on doc c11e2f4fec824966 separately from this labeling
   exercise, rather than merging these two.

12. cosine=0.8663
   A doc_id=2ea0b7a5e8760026 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 3)'
      'g(timestamp);\nCREATE INDEX idx_engine ON query_log(engine);\nCREATE INDEX idx_date ON query_log(date(timestamp));\n```\n\n### Query Examples\n\n```sql\n-- Daily queries per engine\nSELECT date(timestamp) as d'
   B doc_id=4ba7a03b9bd05d69 title='SearXNG SQLite Query Logger - Deployment Plan (part 2)'
      'Individual queries logged with timestamps\n- ✅ Can search query history by text or engine\n- ✅ No performance degradation\n\n### Risk: HIGH - Requires log parsing, potential performance impact\n\n---\n\n## Mi'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — consistent with the established series
   overlap (see pair #5), despite the non-corresponding part numbers.

13. cosine=0.8649
   A doc_id=017e3a0378cde0fc title='LSE Session Learnings (part 5)'
      'broken for Docker and bare hostnames).\n  **Fix:** Restore resolv.conf manually:\n  ```bash\n  echo -e "nameserver 10.255.255.254\\nnameserver 192.168.1.50\\nsearch home.arpa" | tee /etc/resolv.conf\n  ```\n'
   B doc_id=4fdfa57f3f600eb7 title='Troubleshooting'
      '# LSE Stack Troubleshooting Guide\n\n**Audience:** Models (Qwen3.6, Gemma) and humans diagnosing LSE failures.\n**Method:** Start with observation, determine root cause, apply the minimum fix, verify.\n**'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
   NOTE (Claude): Different from the similar-looking 0.82 pair #1: that pair
   matched a SPECIFIC troubleshooting-guide chunk that actually contains the
   resolv.conf fix text. This pair compares against the generic "Troubleshooting"
   BASE doc (a methodology preface — "start with observation, determine root
   cause..."), which doesn't appear to contain that specific fix itself.

14. cosine=0.8638
   A doc_id=6bea0aa609e187f1 title='SearXNG Metrics & Query Tracking - Deployment Guide (part 2)'
      'ry query to SQLite with:\n- Timestamp\n- Query text (optional, can be hashed for privacy)\n- Engine used\n- Response time\n- Result count\n- Success/failure status\n\n**Pros:**\n- ✅ Full per-query history\n- ✅ '
   B doc_id=a0ce9558d6292a37 title='Searxng Sqlite Deployment Plan'
      '# SearXNG SQLite Query Logger - Deployment Plan\n\n> Target: Persistent per-engine query counting with daily/monthly aggregation\n> Strategy: Custom SQLite logger via sidecar container (no SearXNG code c'
   LABEL: [x] true-duplicate   [ ] NOT a duplicate (false-merge)
   RESOLVED (Joe): true-duplicate — same underlying overlap as pair #5, despite
   the non-corresponding part numbers.

15. cosine=0.8613
   A doc_id=15b1a110444876a8 title='EAGLE3 Speculative Drafting Baseline — Qwen3.6-27B'
      'EAGLE3 Speculative Drafting Baseline for Qwen3.6-27B on LUCIFER.\n\nCommand:\nllama-server -m /home/sy5/models/Qwen3.6-27B-Q4_K_M/Qwen3.6-27B-Q4_K_M.gguf -c 65536 -ngl 999 -fa on -ctk q8_0 -ctv q8_0 -np '
   B doc_id=f56739cb0b2a3f26 title='Qwen3.6 27B/35B Local Agent Coding Stack — Reddit Guide by Lirezh'
      '## Qwen3.6 27B/35B Local Agent Coding Stack — Reddit Guide by Lirezh\n\n**Model:** `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` (unsloth, 21 GB, MoE)\n**Path:** `/opt/models/unsloth/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`'
   LABEL: [ ] true-duplicate   [x] NOT a duplicate (false-merge)
