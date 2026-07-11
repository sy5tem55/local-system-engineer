# SCRIBE-2 backfill — candidate review

Generated 2026-07-11T08:59:08+00:00 by scripts/distill_learnings.py from kb/session-learnings.md.

Total candidates: 197 (152 kb-fact, 45 skill-candidate).

Confidence breakdown (triage aid, not a tool field — see each proposal's 'confidence'): **high** 137 (Key-facts bullets — atomic by the template's own construction), **medium** 39 (fix-derived facts / skill-candidates with a verify signal found), **low** 21 (secrets were redacted from the source text, or no explicit verification step could be found — read these before approving).

Approve by writing approved ids (one per line) to a text file and running:
`python3 scripts/distill_learnings.py --apply ids.txt`

All high-confidence ids, if you want a starting point:
```
2026-06-07-e1-1
2026-06-07-e1-2
2026-06-07-e1-3
2026-06-07-e1-5
2026-06-07-e1-6
2026-06-07-e1-7
2026-06-07-e1-8
2026-06-07-e2-1
2026-06-07-e2-2
2026-06-07-e2-3
2026-06-07-e3-1
2026-06-07-e3-2
2026-06-07-e3-3
2026-06-07-e3-4
2026-06-07-e3-5
2026-06-07-e3-6
2026-06-08-e4-1
2026-06-08-e4-2
2026-06-08-e4-3
2026-06-08-e4-4
2026-06-08-e4-5
2026-06-08-e4-6
2026-06-08-e5-1
2026-06-08-e5-2
2026-06-08-e5-3
2026-06-08-e5-4
2026-06-08-e5-5
2026-06-11-e6-1
2026-06-11-e6-2
2026-06-11-e6-3
2026-06-11-e6-4
2026-06-11-e6-5
2026-06-11-e6-6
2026-06-11-e6-7
2026-06-11-e6-8
2026-06-11-e6-9
2026-06-11-e6-10
2026-06-11-e6-11
2026-06-11-e7-1
2026-06-11-e7-2
2026-06-11-e7-3
2026-06-11-e7-4
2026-06-12-e8-1
2026-06-12-e8-2
2026-06-12-e8-3
2026-06-12-e8-4
2026-06-12-e8-5
2026-06-12-e8-6
2026-06-12-e8-7
2026-06-12-e8-8
2026-06-12-e8-9
2026-06-12-e8-10
2026-06-12-e8-11
2026-06-08-e9-1
2026-06-08-e9-2
2026-06-08-e9-3
2026-06-08-e9-4
2026-06-08-e9-5
2026-06-08-e9-6
2026-06-08-e9-7
2026-06-09-e10-1
2026-06-09-e10-2
2026-06-09-e10-3
2026-06-09-e10-4
2026-06-09-e10-5
2026-06-09-e10-6
2026-06-09-e10-7
2026-06-09-e10-8
2026-06-11-e11-1
2026-06-11-e11-2
2026-06-11-e11-3
2026-06-11-e11-4
2026-06-11-e11-5
2026-06-11-e11-6
2026-06-11-e11-7
2026-06-11-e11-8
2026-06-11-e11-9
2026-06-11-e12-1
2026-06-11-e12-2
2026-06-11-e12-3
2026-06-11-e12-4
2026-06-11-e12-5
2026-06-11-e12-6
2026-06-11-e12-7
2026-06-11-e13-1
2026-06-11-e13-2
2026-06-11-e13-3
2026-06-11-e13-4
2026-06-11-e13-5
2026-06-12-e14-1
2026-06-12-e14-2
2026-06-12-e14-3
2026-06-12-e14-4
2026-06-12-e14-5
2026-06-12-e14-6
2026-06-12-e15-1
2026-06-12-e15-2
2026-06-12-e15-3
2026-06-12-e15-4
2026-06-12-e15-5
2026-06-12-e16-1
2026-06-12-e16-2
2026-06-12-e16-3
2026-06-12-e16-4
2026-06-12-e16-5
2026-06-13-e17-1
2026-06-13-e17-2
2026-06-13-e17-3
2026-06-13-e17-4
2026-06-13-e17-5
2026-06-14-e18-1
2026-06-14-e18-2
2026-06-14-e18-3
2026-06-14-e18-4
2026-06-14-e19-1
2026-07-02-e20-1
2026-07-02-e20-2
2026-07-02-e20-3
2026-07-02-e20-4
2026-07-02-e20-5
2026-07-02-e20-6
2026-07-02-e21-1
2026-07-02-e21-2
2026-07-02-e21-3
2026-07-02-e21-4
2026-07-02-e21-5
2026-07-04-e22-1
2026-07-04-e22-2
2026-07-04-e22-3
2026-07-04-e22-4
2026-07-06-e23-1
2026-07-06-e23-2
2026-07-06-e23-3
2026-07-06-e23-4
2026-07-06-e24-1
2026-07-06-e24-2
2026-07-06-e24-3
```

---

## Session 2026-06-07 — Qwen 3.6 cross-file invariant failures in net-discovery

### [2026-06-07-e1-1] (high) kb-fact → `index_to_kb`
- title: pfSense LAN IP: `192.168.1.50` — NOT `192.168.1.1` (that's the ASUS AP management IP)
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense LAN IP: `192.168.1.50` — NOT `192.168.1.1` (that's the ASUS AP management IP)
- evidence: pfSense LAN IP: `192.168.1.50` — NOT `192.168.1.1` (that's the ASUS AP management IP)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-2] (high) kb-fact → `index_to_kb`
- title: pfSense OPT1: `192.168.5.1`, OPT2: `192.168.10.1`; ASUS: `192.168.1.1`; Netgear:…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense OPT1: `192.168.5.1`, OPT2: `192.168.10.1`; ASUS: `192.168.1.1`; Netgear: `192.168.5.2`; RUTX50: `192.168.5.3`
- evidence: pfSense OPT1: `192.168.5.1`, OPT2: `192.168.10.1`; ASUS: `192.168.1.1`; Netgear: `192.168.5.2`; RUTX50: `192.168.5.3`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-3] (high) kb-fact → `index_to_kb`
- title: Grafana port: `3002` (host). Topology API: `8766`. llama-server: `8080`. SearxNG: `8088`.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Grafana port: `3002` (host). Topology API: `8766`. llama-server: `8080`. SearxNG: `8088`.
- evidence: Grafana port: `3002` (host). Topology API: `8766`. llama-server: `8080`. SearxNG: `8088`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-4] (low) kb-fact → `index_to_kb` ⚠ secrets redacted — check before approving
- title: Grafana admin password in Vaultwarden as `Grafana_ADMIN_PASSWORD` (value:…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Grafana admin password in Vaultwarden as `Grafana_ADMIN_PASSWORD` (value: <redacted-by-distiller>)
- evidence: Grafana admin password in Vaultwarden as `Grafana_ADMIN_PASSWORD` (value: <redacted-by-distiller>)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-5] (high) kb-fact → `index_to_kb`
- title: Edit tool + NTFS + large Python files = silent truncation. Use heredoc.
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Edit tool + NTFS + large Python files = silent truncation. Use heredoc.
- evidence: Edit tool + NTFS + large Python files = silent truncation. Use heredoc.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-6] (high) kb-fact → `index_to_kb`
- title: Git commits must be run from WSL — sandbox git operations may fail silently or with lock…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Git commits must be run from WSL — sandbox git operations may fail silently or with lock errors
- evidence: Git commits must be run from WSL — sandbox git operations may fail silently or with lock errors
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-7] (high) kb-fact → `index_to_kb`
- title: Qwen 3.6 strength: isolated single-function rewrites. Weakness: multi-file invariants…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Qwen 3.6 strength: isolated single-function rewrites. Weakness: multi-file invariants (IPs, port mappings, cross-file constants). Always provide a canonical facts block in the prompt before asking LSE to touch topology/config files.
- evidence: Qwen 3.6 strength: isolated single-function rewrites. Weakness: multi-file invariants (IPs, port mappings, cross-file constants). Always provide a canonical facts block in the prompt before asking LSE to touch topology/config files.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-8] (high) kb-fact → `index_to_kb`
- title: Dashboard backup: `python3 backup_grafana_dashboards.py` → `grafana-dashboards/*.json`
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Dashboard backup: `python3 backup_grafana_dashboards.py` → `grafana-dashboards/*.json`
- evidence: Dashboard backup: `python3 backup_grafana_dashboards.py` → `grafana-dashboards/*.json`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-9] (medium) skill-candidate → `skill_record`
- task: Human-verified the correct IPs from live snapshot first, then rewrote with explicit…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: Human-verified the correct IPs from live snapshot first, then rewrote with explicit `TIER_NODES`, `TIER_EDGES`, `SUBNET_PARENT` dicts. Never let LSE infer IPs from training knowledge — always read them from `snapshot.json`.
- verification: Human-verified the correct IPs from live snapshot first, then rewrote with explicit `TIER_NODES`, `TIER_EDGES`, `SUBNET_PARENT` dicts.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-10] (low) skill-candidate → `skill_record`
- task: For any `.py` file >100 lines on NTFS, always use `bash cat << 'PYEOF' ... PYEOF`…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: For any `.py` file >100 lines on NTFS, always use `bash cat << 'PYEOF' ... PYEOF` heredoc. Never use Edit tool on large Python files.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-07-e1-11] (medium) kb-fact → `index_to_kb`
- title: `docker start prometheus` — restarts the existing stopped container without naming…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: `docker start prometheus` — restarts the existing stopped container without naming conflict.
- evidence: Attempted: `docker compose up -d prometheus` to restart stopped Prometheus | Failed because: Container `/prometheus` already existed (just stopped). `docker compose up` tries to create a new container → name conflict error. | `docker start prometheus` — restarts the existing stopped container without naming conflict.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-12] (medium) skill-candidate → `skill_record`
- task: Retrieve password from Vaultwarden (`Grafana_ADMIN_PASSWORD`). To rotate: `curl -s -u…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: Retrieve password from Vaultwarden (`Grafana_ADMIN_PASSWORD`). To rotate: `curl -s -u admin:OLDPASS -X PUT http://localhost:3002/api/user/password -H 'Content-Type: application/json' -d '{"oldPassword":"OLD","newPassword":"NEW","confirmNew":"NEW"}'`
- verification: To rotate: `curl -s -u admin:OLDPASS -X PUT http://localhost:3002/api/user/password -H 'Content-Type: application/json' -d '{"oldPassword":"OLD","newPassword":"NEW","confirmNew":"NEW"}'`
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

### [2026-06-07-e1-13] (medium) kb-fact → `index_to_kb`
- title: User must run `rm -f .git/index.lock` from WSL terminal before any git operation from the…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: User must run `rm -f .git/index.lock` from WSL terminal before any git operation from the sandbox.
- evidence: Attempted: Deleting `.git/index.lock` from Cowork sandbox | Failed because: Sandbox cannot delete NTFS lock files — permission denied even with `rm -f`. | User must run `rm -f .git/index.lock` from WSL terminal before any git operation from the sandbox.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen 3.6 cross-file invariant failures in net-discovery).

---

## Session 2026-06-07 — llama-server --flash-attn arg parsing + Edit tool NTFS truncation

### [2026-06-07-e2-1] (high) kb-fact → `index_to_kb`
- title: `--flash-attn` must not be followed by another `--flag` on the next line in a multi-line…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: `--flash-attn` must not be followed by another `--flag` on the next line in a multi-line SSH command — collapse to single line
- evidence: `--flash-attn` must not be followed by another `--flag` on the next line in a multi-line SSH command — collapse to single line
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (llama-server --flash-attn arg parsing + Edit tool NTFS truncation).

### [2026-06-07-e2-2] (high) kb-fact → `index_to_kb`
- title: Verified working llama-server command for node3090: `llama-server -m…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Verified working llama-server command for node3090: `llama-server -m /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf -c 96000 -ngl 129 --flash-attn --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 -t 7 -tb 7 --reasoning-budget 3072 --n-predict 8192 --jinja --metrics --port 8080 --host 0.0.0.0`
- evidence: Verified working llama-server command for node3090: `llama-server -m /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf -c 96000 -ngl 129 --flash-attn --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 -t 7 -tb 7 --reasoning-budget 3072 --n-predict 8192 --jinja --metrics --port 8080 --host 0.0.0.0`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (llama-server --flash-attn arg parsing + Edit tool NTFS truncation).

### [2026-06-07-e2-3] (high) kb-fact → `index_to_kb`
- title: Edit tool + NTFS + emoji in f-strings = silent mid-character truncation (not just…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Edit tool + NTFS + emoji in f-strings = silent mid-character truncation (not just end-of-file)
- evidence: Edit tool + NTFS + emoji in f-strings = silent mid-character truncation (not just end-of-file)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (llama-server --flash-attn arg parsing + Edit tool NTFS truncation).

### [2026-06-07-e2-4] (low) skill-candidate → `skill_record`
- task: Collapse the entire llama-server launch to a single line. Use short flags: `-c` (ctx),…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: Collapse the entire llama-server launch to a single line. Use short flags: `-c` (ctx), `-ngl` (gpu layers), `-t` (threads), `-tb` (threads-batch), `--flash-attn` (no value needed — defaults to auto).
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (llama-server --flash-attn arg parsing + Edit tool NTFS truncation). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-07-e2-5] (medium) skill-candidate → `skill_record`
- task: Use bash Python string replacement for ALL .py edits > 100 lines on NTFS: ```python with…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: Use bash Python string replacement for ALL .py edits > 100 lines on NTFS:
  ```python
  with open(path) as f: src = f.read()
  src = src.replace(old, new, 1)
  with open(path, "w") as f: f.write(src)
  import ast; ast.parse(src)  # verify syntax
  ```
- verification: Use bash Python string replacement for ALL .py edits > 100 lines on NTFS:
  ```python
  with open(path) as f: src = f.read()
  src = src.replace(old, new, 1)
  with open(path, "w") as f: f.write(src)
  import ast; ast.parse(src)  # verify syntax
  ```
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (llama-server --flash-attn arg parsing + Edit tool NTFS truncation).

---

## Session 2026-06-07 — Qwen3.6 reasoning_content field + lse_task.sh double-http

### [2026-06-07-e3-1] (high) kb-fact → `index_to_kb`
- title: Qwen3.6 + llama.cpp: thinking output → `reasoning_content`; actual answer → `content`…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Qwen3.6 + llama.cpp: thinking output → `reasoning_content`; actual answer → `content` (may be empty if model hits token limit or `reasoning_budget` is misset)
- evidence: Qwen3.6 + llama.cpp: thinking output → `reasoning_content`; actual answer → `content` (may be empty if model hits token limit or `reasoning_budget` is misset)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-2] (high) kb-fact → `index_to_kb`
- title: `reasoning_budget: 0` = 0 content tokens (counterintuitive — sounds like "no reasoning")
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: `reasoning_budget: 0` = 0 content tokens (counterintuitive — sounds like "no reasoning")
- evidence: `reasoning_budget: 0` = 0 content tokens (counterintuitive — sounds like "no reasoning")
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-3] (high) kb-fact → `index_to_kb`
- title: Correct way to disable thinking per-request: `"chat_template_kwargs": {"enable_thinking":…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Correct way to disable thinking per-request: `"chat_template_kwargs": {"enable_thinking": False}` in the completions payload
- evidence: Correct way to disable thinking per-request: `"chat_template_kwargs": {"enable_thinking": False}` in the completions payload
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-4] (high) kb-fact → `index_to_kb`
- title: `/no_think` in user message is NOT reliable with llama.cpp — model still enters thinking…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: `/no_think` in user message is NOT reliable with llama.cpp — model still enters thinking mode
- evidence: `/no_think` in user message is NOT reliable with llama.cpp — model still enters thinking mode
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-5] (high) kb-fact → `index_to_kb`
- title: `LLM_URL` pattern: if it already contains `http://`, never wrap it with `http://` again…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: `LLM_URL` pattern: if it already contains `http://`, never wrap it with `http://` again in curl
- evidence: `LLM_URL` pattern: if it already contains `http://`, never wrap it with `http://` again in curl
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-6] (high) kb-fact → `index_to_kb`
- title: node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname `node3090.home.arpa` also works for ping/SSH but use IP for curl to avoid any DNS edge cases.
- evidence: node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname `node3090.home.arpa` also works for ping/SSH but use IP for curl to avoid any DNS edge cases.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-7] (medium) skill-candidate → `skill_record`
- task: `curl -sf "${LLM_URL}/health"` — no extra `http://` prefix. When `LLM_URL` already…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: `curl -sf "${LLM_URL}/health"` — no extra `http://` prefix. When `LLM_URL` already contains the scheme, never wrap it again.
- verification: `curl -sf "${LLM_URL}/health"` — no extra `http://` prefix.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http).

### [2026-06-07-e3-8] (low) skill-candidate → `skill_record`
- task: Remove `reasoning_budget` entirely. Use `chat_template_kwargs: {"enable_thinking":…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: Remove `reasoning_budget` entirely. Use `chat_template_kwargs: {"enable_thinking": False}` to disable thinking at the template level.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-07-e3-9] (low) skill-candidate → `skill_record`
- task: `content = msg.get("content") or ""; content = content or msg.get("reasoning_content",…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-07
- procedure: `content = msg.get("content") or ""; content = content or msg.get("reasoning_content", "")` — fall back to `reasoning_content` when `content` is blank.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-07 (Qwen3.6 reasoning_content field + lse_task.sh double-http). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-06-08 — WSL2 unclean shutdown → Docker overlay2 corruption

### [2026-06-08-e4-1] (high) kb-fact → `index_to_kb`
- title: Docker overlay2 corruption = unclean dockerd kill. Signature: `RWLayer unexpectedly nil`…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Docker overlay2 corruption = unclean dockerd kill. Signature: `RWLayer unexpectedly nil` on `docker start`.
- evidence: Docker overlay2 corruption = unclean dockerd kill. Signature: `RWLayer unexpectedly nil` on `docker start`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-2] (high) kb-fact → `index_to_kb`
- title: Recovery order: start dockerd → prune containers → prune system → compose up.
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Recovery order: start dockerd → prune containers → prune system → compose up.
- evidence: Recovery order: start dockerd → prune containers → prune system → compose up.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-3] (high) kb-fact → `index_to_kb`
- title: Never `docker start` after overlay2 corruption — always prune first or you'll get…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Never `docker start` after overlay2 corruption — always prune first or you'll get cascading errors.
- evidence: Never `docker start` after overlay2 corruption — always prune first or you'll get cascading errors.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-4] (high) kb-fact → `index_to_kb`
- title: `docker ps` failing with socket error = dockerd not running, not a permissions issue.
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: `docker ps` failing with socket error = dockerd not running, not a permissions issue.
- evidence: `docker ps` failing with socket error = dockerd not running, not a permissions issue.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-5] (high) kb-fact → `index_to_kb`
- title: Data safety: grafana, vaultwarden, elasticsearch, prometheus all bind-mount data to host…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Data safety: grafana, vaultwarden, elasticsearch, prometheus all bind-mount data to host dirs — `docker container prune` never touches data.
- evidence: Data safety: grafana, vaultwarden, elasticsearch, prometheus all bind-mount data to host dirs — `docker container prune` never touches data.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-6] (high) kb-fact → `index_to_kb`
- title: `/tmp/dockerd.log` is always writable; `/var/log/dockerd.log` requires root and correct…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: `/tmp/dockerd.log` is always writable; `/var/log/dockerd.log` requires root and correct permissions.
- evidence: `/tmp/dockerd.log` is always writable; `/var/log/dockerd.log` requires root and correct permissions.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

### [2026-06-08-e4-7] (low) skill-candidate → `skill_record`
- task: **Attempted:** `docker start <containers>` after WSL2 restarted **Failed because:**…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Attempted:** `docker start <containers>` after WSL2 restarted
  **Failed because:** dockerd was killed ungracefully (Windows sleep/hibernate while WSL2 running). Docker overlay2 content store left in inconsistent state. All containers show `RWLayer is unexpectedly nil`. Custom-built images show `parent snapshot does not exist`.
  **Fix sequence:**
  ```bash
  sudo dockerd > /tmp/dockerd.log 2>&1 &   # start daemon first
  sleep 5
  docker container prune -f                 # remove all dead containers
  docker system prune -f                    # clear corrupted build cache
  cd /home/sy5/docker && docker compose up -d  # recreate everything
  ```
  Internet required for any missing image pulls. All persistent data is bind-mounted to host — container removal is safe.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-08-e4-8] (low) skill-candidate → `skill_record`
- task: **Attempted:** `sudo dockerd &` then immediate `docker ps` **Failed because:** daemon…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Attempted:** `sudo dockerd &` then immediate `docker ps`
  **Failed because:** daemon needs ~3-5 seconds to create `/var/run/docker.sock` before clients can connect. Always `sleep 5` after starting.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-08-e4-9] (low) skill-candidate → `skill_record`
- task: **Attempted:** `sudo nohup dockerd > /var/log/dockerd.log 2>&1 &` as non-root **Failed…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Attempted:** `sudo nohup dockerd > /var/log/dockerd.log 2>&1 &` as non-root
  **Failed because:** `/var/log/` is root-only. Use `/tmp/dockerd.log` or run from a root shell.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-08-e4-10] (low) skill-candidate → `skill_record`
- task: **Attempted:** `docker compose up -d --pull never` on corrupted storage **Failed…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Attempted:** `docker compose up -d --pull never` on corrupted storage
  **Failed because:** `--pull never` prevents registry pulls but does NOT prevent rebuilding custom images from Dockerfiles. Custom image builds still fail if overlay2 snapshots are corrupted. Use `docker container prune -f` + `docker system prune -f` first, then `docker compose up -d`.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-08-e4-11] (medium) skill-candidate → `skill_record`
- task: **resolv.conf reset on WSL2 restart** **Cause:** Windows hibernate/reboot causes WSL2 to…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **resolv.conf reset on WSL2 restart**
  **Cause:** Windows hibernate/reboot causes WSL2 to fully restart. If `/etc/wsl.conf` has `generateResolvConf = false` but the wsl.conf itself was not persisted (NTFS write issue), WSL2 regenerates resolv.conf with just `nameserver [::1]` (broken for Docker and bare hostnames).
  **Fix:** Restore resolv.conf manually:
  ```bash
  echo -e "nameserver 10.255.255.254\nnameserver 192.168.1.50\nsearch home.arpa" | tee /etc/resolv.conf
  ```
  Then verify wsl.conf is intact: `cat /etc/wsl.conf` — should contain `generateResolvConf = false`.
- verification: **Fix:** Restore resolv.conf manually:
  ```bash
  echo -e "nameserver 10.255.255.254\nnameserver 192.168.1.50\nsearch home.arpa" | tee /etc/resolv.conf
  ```
  Then verify wsl.conf is intact: `cat /etc/wsl.conf` — should contain `generateResolvConf = false`.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 unclean shutdown → Docker overlay2 corruption).

---

## Session 2026-06-08 — WSL2 restart kills host-side exporters / Grafana "no data"

### [2026-06-08-e5-1] (high) kb-fact → `index_to_kb`
- title: Host-side exporter ports: topology API 8766, netobs 9120, nvidia_gpu 9835, llama-context…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Host-side exporter ports: topology API 8766, netobs 9120, nvidia_gpu 9835, llama-context 9836,
- evidence: Host-side exporter ports: topology API 8766, netobs 9120, nvidia_gpu 9835, llama-context 9836,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-2] (high) kb-fact → `index_to_kb`
- title: Recovery: `bash scripts/restart_exporters.sh` — starts all host exporters and topology…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Recovery: `bash scripts/restart_exporters.sh` — starts all host exporters and topology API.
- evidence: Recovery: `bash scripts/restart_exporters.sh` — starts all host exporters and topology API.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-3] (high) kb-fact → `index_to_kb`
- title: The Prometheus curl check above uses `172.17.0.1` (Docker bridge → host). If the error…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: The Prometheus curl check above uses `172.17.0.1` (Docker bridge → host). If the error says
- evidence: The Prometheus curl check above uses `172.17.0.1` (Docker bridge → host). If the error says
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-4] (high) kb-fact → `index_to_kb`
- title: Grafana topology dashboard (`uid: net-topology`) fetches directly from port 8766 via sync…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Grafana topology dashboard (`uid: net-topology`) fetches directly from port 8766 via sync XHR
- evidence: Grafana topology dashboard (`uid: net-topology`) fetches directly from port 8766 via sync XHR
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-5] (high) kb-fact → `index_to_kb`
- title: Full troubleshooting decision tree: `docs/troubleshooting.md`
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Full troubleshooting decision tree: `docs/troubleshooting.md`
- evidence: Full troubleshooting decision tree: `docs/troubleshooting.md`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-6] (medium) skill-candidate → `skill_record`
- task: **Observed:** Grafana dashboards showed "No data" after Docker full reset + WSL2 restart.…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Observed:** Grafana dashboards showed "No data" after Docker full reset + WSL2 restart.
  **Root cause:** "No data" had TWO unrelated causes confused into one: (1) host-side Prometheus
  exporters were killed by WSL2 restart; (2) the topology API (echarts_topology.py) was also
  killed. Docker data itself was fine — Prometheus TSDB and Grafana SQLite are both bind-mounted.
  **Fix:** `bash scripts/restart_exporters.sh` for the host exporters; then `nohup python3
  net-discovery/echarts_topology.py &` for the topology API. Historical metrics reappear in
  Grafana once Prometheus scrapes the restarted exporters (~30s).
  **Lesson:** Always run the Prometheus targets check FIRST before assuming data loss:
  ```bash
  curl -s http://localhost:9090/api/v1/targets | python3 -c "
  import json,sys
  for t in json.load(sys.stdin)['data']['activeTargets']:
      print(t['labels']['job'].ljust(28), t['health'], t.get('lastError','')[:60])
  "
  ```
  `connection refused on 172.17.0.1:983x` = host exporter down (WSL2 killed it).
  `connection refused on <docker-service>:port` = container down (Docker issue).
- verification: **Lesson:** Always run the Prometheus targets check FIRST before assuming data loss:
  ```bash
  curl -s http://localhost:9090/api/v1/targets | python3 -c "
  import json,sys
  for t in json.load(sys.stdin)['data']['activeTargets']:
      print(t['labels']['job'].ljust(28), t['health'], t.get('lastError','')[:60])
  "
  ```
  `connection refused on 172.17.0.1:983x` = host exporter down (WSL2 killed it).
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

### [2026-06-08-e5-7] (medium) skill-candidate → `skill_record`
- task: **Attempted:** `curl -s http://localhost:9101/metrics` to check netobs exporter **Hung:**…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-08
- procedure: **Attempted:** `curl -s http://localhost:9101/metrics` to check netobs exporter
  **Hung:** The netobs exporter is on port **9120**, not 9101. Port 9101 had a half-open TCP
  connection from a previous session. `curl -s` without `--max-time` blocks forever.
  **Fix:** Always use `curl -s --max-time 3` for health checks. Know the correct ports (see KB
  port map below).
- verification: **Attempted:** `curl -s http://localhost:9101/metrics` to check netobs exporter
  **Hung:** The netobs exporter is on port **9120**, not 9101.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (WSL2 restart kills host-side exporters / Grafana "no data").

---

## Session 2026-06-11 — Hermes Agent config v0→v27 + llama-server on node3090

### [2026-06-11-e6-1] (high) kb-fact → `index_to_kb`
- title: Hermes config version: v27 (as of v0.16.0). Check with `hermes config check` → "Config…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Hermes config version: v27 (as of v0.16.0). Check with `hermes config check` → "Config version: 27 ✓".
- evidence: Hermes config version: v27 (as of v0.16.0). Check with `hermes config check` → "Config version: 27 ✓".
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-2] (high) kb-fact → `index_to_kb`
- title: Valid provider name: `custom` — NOT `openai`, NOT `llamacpp`.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Valid provider name: `custom` — NOT `openai`, NOT `llamacpp`.
- evidence: Valid provider name: `custom` — NOT `openai`, NOT `llamacpp`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-3] (high) kb-fact → `index_to_kb`
- title: `custom_providers:` must be a YAML list (items start with `-`), NOT a dict.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: `custom_providers:` must be a YAML list (items start with `-`), NOT a dict.
- evidence: `custom_providers:` must be a YAML list (items start with `-`), NOT a dict.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-4] (high) kb-fact → `index_to_kb`
- title: llama-server binary: `/usr/local/bin/llama-server` (b1-6b80c74)
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: llama-server binary: `/usr/local/bin/llama-server` (b1-6b80c74)
- evidence: llama-server binary: `/usr/local/bin/llama-server` (b1-6b80c74)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-5] (high) kb-fact → `index_to_kb`
- title: Model path:…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Model path: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- evidence: Model path: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-6] (high) kb-fact → `index_to_kb`
- title: Hermes API port: 8642 (`.env` says 8644 but server binds 8642 — always verify with `ss…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Hermes API port: 8642 (`.env` says 8644 but server binds 8642 — always verify with `ss -tlnp | grep 864`).
- evidence: Hermes API port: 8642 (`.env` says 8644 but server binds 8642 — always verify with `ss -tlnp | grep 864`).
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-7] (high) kb-fact → `index_to_kb`
- title: Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires root to read).
- evidence: Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires root to read).
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-8] (high) kb-fact → `index_to_kb`
- title: Disable thinking (llama.cpp direct API): `chat_template_kwargs: {"enable_thinking":…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Disable thinking (llama.cpp direct API): `chat_template_kwargs: {"enable_thinking": false}`.
- evidence: Disable thinking (llama.cpp direct API): `chat_template_kwargs: {"enable_thinking": false}`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-9] (high) kb-fact → `index_to_kb`
- title: Disable thinking (Hermes API): append `/no_think` to user message content.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Disable thinking (Hermes API): append `/no_think` to user message content.
- evidence: Disable thinking (Hermes API): append `/no_think` to user message content.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-10] (high) kb-fact → `index_to_kb`
- title: Performance: ~131 tok/s prompt, ~40 tok/s generation on RTX 3090.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Performance: ~131 tok/s prompt, ~40 tok/s generation on RTX 3090.
- evidence: Performance: ~131 tok/s prompt, ~40 tok/s generation on RTX 3090.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-11] (high) kb-fact → `index_to_kb`
- title: Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`,…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`, `start-hermes-gateway.sh`.
- evidence: Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`, `start-hermes-gateway.sh`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-12] (low) skill-candidate → `skill_record`
- task: Set `provider: custom` (not `llamacpp` or `openai`) + replace `provider_custom:` dict…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: Set `provider: custom` (not `llamacpp` or `openai`) + replace `provider_custom:` dict with `custom_providers:` list:
  ```yaml
  model:
    provider: custom
    model: Qwen3.6-27B-Q4_K_M.gguf
    base_url: http://localhost:8080/v1
  custom_providers:
    - name: Local llama-server (Qwen3.6-27B)
      base_url: http://localhost:8080/v1
      api_key: sk-none
  ```
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-11-e6-13] (medium) skill-candidate → `skill_record`
- task: Always write config.yaml via `tee` or Python AFTER `hermes config migrate` completes.…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: Always write config.yaml via `tee` or Python AFTER `hermes config migrate` completes. Verify with `cat` before starting gateway.
- verification: Verify with `cat` before starting gateway.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-14] (medium) kb-fact → `index_to_kb`
- title: Always use `--flash-attn on` (not bare `--flash-attn`).
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Always use `--flash-attn on` (not bare `--flash-attn`).
- evidence: Attempted: `--flash-attn` as a boolean flag (no argument) | Failed because: llama-server b1-6b80c74 requires an explicit value: `--flash-attn on|off|auto`. Passing it without a value causes: `error: unknown value for --flash-attn: '--cache-type-k'`. | Always use `--flash-attn on` (not bare `--flash-attn`).
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

### [2026-06-11-e6-15] (low) skill-candidate → `skill_record`
- task: **Attempted:** Running Hermes gateway as root (workaround for systemd bus issue) **Failed…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: **Attempted:** Running Hermes gateway as root (workaround for systemd bus issue)
  **Failed later because:** Root-owned `gateway.lock` prevents hermes-admin from starting the gateway subsequently. Symptom: `PermissionError: [Errno 13] Permission denied: '/home/hermes-admin/.hermes/gateway.lock'`.
  **Fix:** `chown -R hermes-admin:hermes-admin /home/hermes-admin/.hermes/`
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-11-e6-16] (medium) skill-candidate → `skill_record`
- task: Hermes ping/pong test: `curl -s http://127.0.0.1:8642/v1/chat/completions` with…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: Hermes ping/pong test: `curl -s http://127.0.0.1:8642/v1/chat/completions` with `/no_think` suffix in user message content.
- verification: Hermes ping/pong test: `curl -s http://127.0.0.1:8642/v1/chat/completions` with `/no_think` suffix in user message content.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-11 (Hermes Agent config v0→v27 + llama-server on node3090).

---

## Session 2026-06-11 — pkill -f self-match killed SSH session and backend

### [2026-06-11-e7-1] (high) kb-fact → `index_to_kb`
- title: An instant return with zero output from an SSH one-liner containing pkill -f =…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: An instant return with zero output from an SSH one-liner containing pkill -f = self-match, not a connection problem
- evidence: An instant return with zero output from an SSH one-liner containing pkill -f = self-match, not a connection problem
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (pkill -f self-match killed SSH session and backend).

### [2026-06-11-e7-2] (high) kb-fact → `index_to_kb`
- title: Diagnostic discriminator: instant return = remote command never completed; ~8s return =…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Diagnostic discriminator: instant return = remote command never completed; ~8s return = ran but silent
- evidence: Diagnostic discriminator: instant return = remote command never completed; ~8s return = ran but silent
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (pkill -f self-match killed SSH session and backend).

### [2026-06-11-e7-3] (high) kb-fact → `index_to_kb`
- title: Cowork sandbox cannot reach 192.168.x.x at all (proxy returns 403 blocked-by-allowlist…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Cowork sandbox cannot reach 192.168.x.x at all (proxy returns 403 blocked-by-allowlist for HTTP, port 22 unreachable) — all node3090 ops go through the user's WSL terminal
- evidence: Cowork sandbox cannot reach 192.168.x.x at all (proxy returns 403 blocked-by-allowlist for HTTP, port 22 unreachable) — all node3090 ops go through the user's WSL terminal
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (pkill -f self-match killed SSH session and backend).

### [2026-06-11-e7-4] (high) kb-fact → `index_to_kb`
- title: node3090 idle VRAM ≈ 18 MiB; READY can be near-instant when model is in page cache
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: node3090 idle VRAM ≈ 18 MiB; READY can be near-instant when model is in page cache
- evidence: node3090 idle VRAM ≈ 18 MiB; READY can be near-instant when model is in page cache
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (pkill -f self-match killed SSH session and backend).

### [2026-06-11-e7-5] (medium) kb-fact → `index_to_kb`
- title: `pkill -f "[l]lama-server"` — bracket class prevents self-match. Restart _Hermes.md step…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: `pkill -f "[l]lama-server"` — bracket class prevents self-match. Restart _Hermes.md step 1 patched accordingly.
- evidence: Attempted: `ssh lse-admin@192.168.5.41 'pkill -f llama-server; ...nvidia-smi...; tail ...'` | Failed because: `pkill -f` matched the remote shell's own command line (it contains the literal string "llama-server"), killing the SSH session before any output printed — and also killing a likely-healthy llama-server. Symptom: command "loops back to empty shell" instantly. Log showed graceful "cleaning up before exit", not OOM. | `pkill -f "[l]lama-server"` — bracket class prevents self-match. Restart _Hermes.md step 1 patched accordingly.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (pkill -f self-match killed SSH session and backend).

---

## Session 2026-06-12 — Model store migration, operator race, silent ES index loss

### [2026-06-12-e8-1] (high) kb-fact → `index_to_kb`
- title: /opt/models on node3090: REAL dir, 18 .gguf chattr +i, hashes in /opt/models/SHA256SUMS +…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: /opt/models on node3090: REAL dir, 18 .gguf chattr +i, hashes in /opt/models/SHA256SUMS + kb/node3090-model-sha256sums.md
- evidence: /opt/models on node3090: REAL dir, 18 .gguf chattr +i, hashes in /opt/models/SHA256SUMS + kb/node3090-model-sha256sums.md
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-2] (high) kb-fact → `index_to_kb`
- title: Canonical launch: /opt/local-se/scripts/start-llama-server.sh (ctx 81920 — SY5 decision;…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: Canonical launch: /opt/local-se/scripts/start-llama-server.sh (ctx 81920 — SY5 decision; q8_0 KV both; threads 7/7; ub/b 512/2048 — benched; log /home/lse-admin/llama-server.log)
- evidence: Canonical launch: /opt/local-se/scripts/start-llama-server.sh (ctx 81920 — SY5 decision; q8_0 KV both; threads 7/7; ub/b 512/2048 — benched; log /home/lse-admin/llama-server.log)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-3] (high) kb-fact → `index_to_kb`
- title: node3090 perf @9k uncached: pp ~1323 t/s, tg ~38 t/s (RTX 3090, Q4_K_M, b9577)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: node3090 perf @9k uncached: pp ~1323 t/s, tg ~38 t/s (RTX 3090, Q4_K_M, b9577)
- evidence: node3090 perf @9k uncached: pp ~1323 t/s, tg ~38 t/s (RTX 3090, Q4_K_M, b9577)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-4] (high) kb-fact → `index_to_kb`
- title: agent_commands.log is at /opt/local-se/ (NOT /opt/local-se/logs/)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: agent_commands.log is at /opt/local-se/ (NOT /opt/local-se/logs/)
- evidence: agent_commands.log is at /opt/local-se/ (NOT /opt/local-se/logs/)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-5] (high) kb-fact → `index_to_kb`
- title: rfc_kb.py upserts by deterministic section_id — re-runs idempotent; --tag-only resumes…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: rfc_kb.py upserts by deterministic section_id — re-runs idempotent; --tag-only resumes (fills empty tags only); --no-tag still embeds (kNN works untagged)
- evidence: rfc_kb.py upserts by deterministic section_id — re-runs idempotent; --tag-only resumes (fills empty tags only); --no-tag still embeds (kNN works untagged)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-6] (high) kb-fact → `index_to_kb`
- title: lse-rfc-kb: 628 chunks / 13 RFCs / all tagged — production-ready; yellow = single-node…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: lse-rfc-kb: 628 chunks / 13 RFCs / all tagged — production-ready; yellow = single-node replica cosmetics
- evidence: lse-rfc-kb: 628 chunks / 13 RFCs / all tagged — production-ready; yellow = single-node replica cosmetics
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-7] (high) kb-fact → `index_to_kb`
- title: 03-kb-seed.py skips existing doc ids — updated files need --reindex
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: 03-kb-seed.py skips existing doc ids — updated files need --reindex
- evidence: 03-kb-seed.py skips existing doc ids — updated files need --reindex
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-8] (high) kb-fact → `index_to_kb`
- title: LSE execute_command timeout = 30s and /opt/ writes are safety-blocked — long/privileged…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: LSE execute_command timeout = 30s and /opt/ writes are safety-blocked — long/privileged jobs run from WSL
- evidence: LSE execute_command timeout = 30s and /opt/ writes are safety-blocked — long/privileged jobs run from WSL
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-9] (high) kb-fact → `index_to_kb`
- title: lse-kb.sqlite is vestigial (0 bytes, no code references it — tool v1.6.4's only sqlite is…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: lse-kb.sqlite is vestigial (0 bytes, no code references it — tool v1.6.4's only sqlite is the OWUI chat DB)
- evidence: lse-kb.sqlite is vestigial (0 bytes, no code references it — tool v1.6.4's only sqlite is the OWUI chat DB)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-10] (high) kb-fact → `index_to_kb`
- title: ~/projects/local-system-engineer is a SYMLINK → /mnt/c repo (since Jun 7) — one real…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: ~/projects/local-system-engineer is a SYMLINK → /mnt/c repo (since Jun 7) — one real repo, not two clones. `diff -rq` empty + exit 0 between "two" paths = check `readlink -f` first.
- evidence: ~/projects/local-system-engineer is a SYMLINK → /mnt/c repo (since Jun 7) — one real repo, not two clones. `diff -rq` empty + exit 0 between "two" paths = check `readlink -f` first.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-11] (high) kb-fact → `index_to_kb`
- title: A failed WSL UNC mount attempt poisons the Cowork sandbox shell for the whole session…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: A failed WSL UNC mount attempt poisons the Cowork sandbox shell for the whole session (every bash call errors "UNC paths are not supported") — file tools keep working; restart session to recover bash.
- evidence: A failed WSL UNC mount attempt poisons the Cowork sandbox shell for the whole session (every bash call errors "UNC paths are not supported") — file tools keep working; restart session to recover bash.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-12] (medium) skill-candidate → `skill_record`
- task: ONE operator at a time. Recover from ground-truth survey, never from agent self-reports…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: ONE operator at a time. Recover from ground-truth survey, never from agent self-reports (Hermes echoed LSE's stale PID 43871; real PID was 44564; at one point nothing ran at all).
- **Attempted:** `sudo ls /path/*.json` (glob in non-root shell)
  **Failed because:** glob expands before sudo → literal "No such file".
  **Fix:** `sudo bash -c 'ls /path/*.json'`.
- **Attempted:** record_error() → 404 on lse-errors
  **Failed because:** es-data Docker volume was lost in the 2026-06-08 WSL cascade; only lse-kb was reseeded. Missing ES indices are SILENT until first read (ES auto-creates on write, 404s on search).
  **Fix:** `rag/02-es-setup.py` (idempotent, canonical mappings — never freehand-create indices). Add index-existence probe to stack health check: `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
- **Attempted:** Cowork mounting WSL paths (\\wsl.localhost\...)
  **Failed because:** "UNC paths are not supported" — product-level, both folder mount and sandbox bash.
  **Fix:** Invert the alias: real files on /mnt/c (NTFS, git), WSL-side symlink for Linux consumers.
- verification: Add index-existence probe to stack health check: `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
- **Attempted:** Cowork mounting WSL paths (\\wsl.localhost\...)
  **Failed because:** "UNC paths are not supported" — product-level, both folder mount and sandbox bash.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

### [2026-06-12-e8-13] (medium) skill-candidate → `skill_record`
- task: Same-fs `mv` of model files under a running llama-server = zero downtime (server holds…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: Same-fs `mv` of model files under a running llama-server = zero downtime (server holds the inode via mmap). Verify first: `stat -c "dev=%d"` on both paths.
- verification: Verify first: `stat -c "dev=%d"` on both paths.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-12 (Model store migration, operator race, silent ES index loss).

---

## Session 2026-06-08 — pfSense log gateway context overflow + parser fixes

### [2026-06-08-e9-1] (high) kb-fact → `index_to_kb`
- title: pfSense REST API returns version as nested dict: {"version": "2.7.x", "base":…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense REST API returns version as nested dict: {"version": "2.7.x", "base": "FreeBSD..."}
- evidence: pfSense REST API returns version as nested dict: {"version": "2.7.x", "base": "FreeBSD..."}
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-2] (high) kb-fact → `index_to_kb`
- title: pfSense only logs blocked/rejected packets by default. Zero pass_count in gateway
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense only logs blocked/rejected packets by default. Zero pass_count in gateway
- evidence: pfSense only logs blocked/rejected packets by default. Zero pass_count in gateway
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-3] (high) kb-fact → `index_to_kb`
- title: Gateway paths: script=/opt/local-se/pfsense-gateway-tools.sh,…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Gateway paths: script=/opt/local-se/pfsense-gateway-tools.sh, py=/opt/local-se/pfsense_log_gateway.py
- evidence: Gateway paths: script=/opt/local-se/pfsense-gateway-tools.sh, py=/opt/local-se/pfsense_log_gateway.py
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-4] (high) kb-fact → `index_to_kb`
- title: Secrets file: /opt/local-se/.lse/secrets — line format: PFSENSE_API_KEY=<key> (no quotes…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Secrets file: /opt/local-se/.lse/secrets — line format: PFSENSE_API_KEY=<key> (no quotes needed)
- evidence: Secrets file: /opt/local-se/.lse/secrets — line format: PFSENSE_API_KEY=<key> (no quotes needed)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-5] (high) kb-fact → `index_to_kb`
- title: Gateway port: 9191. Audit endpoint: GET /compact?hours=24 (use for reports, not /summary)
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Gateway port: 9191. Audit endpoint: GET /compact?hours=24 (use for reports, not /summary)
- evidence: Gateway port: 9191. Audit endpoint: GET /compact?hours=24 (use for reports, not /summary)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-6] (high) kb-fact → `index_to_kb`
- title: Edit tool with replace_all=true on large NTFS Python files truncates the file tail.
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Edit tool with replace_all=true on large NTFS Python files truncates the file tail.
- evidence: Edit tool with replace_all=true on large NTFS Python files truncates the file tail.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-7] (high) kb-fact → `index_to_kb`
- title: Tool version: openwebui-tool-v1.5.28.py — pfsense_log gateway rewrite + LOG ENDPOINT…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Tool version: openwebui-tool-v1.5.28.py — pfsense_log gateway rewrite + LOG ENDPOINT PROHIBITION
- evidence: Tool version: openwebui-tool-v1.5.28.py — pfsense_log gateway rewrite + LOG ENDPOINT PROHIBITION
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-8] (medium) kb-fact → `index_to_kb`
- title: Rewrite pfsense_log_summary to call http://localhost:9191/compact instead. The gateway…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Rewrite pfsense_log_summary to call http://localhost:9191/compact instead.
  The gateway does aggregation server-side. Context cost: <4KB.
- evidence: Attempted: `pfsense_log_summary` calling `pfsense_query('/api/v2/status/logs/firewall')` internally | Failed because: pfsense_query fetches raw log JSON before any aggregation — pfSense
  returns up to 2.7M tokens which overflows the 96k context window mid-response | Rewrite pfsense_log_summary to call http://localhost:9191/compact instead.
  The gateway does aggregation server-side. Context cost: <4KB.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-9] (medium) kb-fact → `index_to_kb`
- title: Move key check inside gateway_ensure_running() with return 1 on missing key. Sourcing is…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Move key check inside gateway_ensure_running() with return 1 on missing key.
  Sourcing is now always silent.
- evidence: Attempted: pfsense-gateway-tools.sh sourced in .bashrc; API key error printed on every terminal open | Failed because: PFSENSE_API_KEY absence check was at top-level scope, outside the
  `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` guard — fires on source, not just direct execution | Move key check inside gateway_ensure_running() with return 1 on missing key.
  Sourcing is now always silent.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-10] (medium) kb-fact → `index_to_kb`
- title: Branch on fields[8] (ip_version). Add sanity check: discard entries where source does not…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Branch on fields[8] (ip_version). Add sanity check: discard entries where source
  does not match r'^[\d.a-fA-F:]+$'
- evidence: Attempted: filterlog CSV parser using hardcoded field indices for all entries | Failed because: pfSense filterlog CSV has different field positions for IPv4 vs IPv6.
  IPv4: src_ip=fields[18], dst_ip=fields[19], src_port=fields[20], dst_port=fields[21], proto=fields[16]
  IPv6: src_ip=fields[15], dst_ip=fields[16], src_port=fields[17], dst_port=fields[18], proto=fields[12]
  Parser was using fields[12]/[13] for ports (IPv4 id/offset fields) — "RTALERT" and "5353"
  appeared as source IPs; "ff02::fb" appeared as destination port | Branch on fields[8] (ip_version). Add sanity check: discard entries where source
  does not match r'^[\d.a-fA-F:]+$'
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

### [2026-06-08-e9-11] (medium) kb-fact → `index_to_kb`
- title: Add LOG ENDPOINT PROHIBITION block to pfsense_query docstring explicitly naming the…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Add LOG ENDPOINT PROHIBITION block to pfsense_query docstring explicitly naming
  the endpoint and calling direct calls a protocol violation.
- evidence: Attempted: pfsense_query docstring lists /api/v2/status/logs/firewall as a "common endpoint" | Failed because: No prohibition — model treated it as a valid call for log analysis,
  bypassing pfsense_log_summary entirely | Add LOG ENDPOINT PROHIBITION block to pfsense_query docstring explicitly naming
  the endpoint and calling direct calls a protocol violation.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-08 (pfSense log gateway context overflow + parser fixes).

---

## Session 2026-06-09 — pfsense-agent _extract_prompt + OWUI API gap

### [2026-06-09-e10-1] (high) kb-fact → `index_to_kb`
- title: `^[ \t]*` not `^\s*` — in multiline Python regex, `\s*` swallows the preceding newline
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: `^[ \t]*` not `^\s*` — in multiline Python regex, `\s*` swallows the preceding newline
- evidence: `^[ \t]*` not `^\s*` — in multiline Python regex, `\s*` swallows the preceding newline
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-2] (high) kb-fact → `index_to_kb`
- title: NTFS + Edit tool truncates Python files >100 lines silently — use heredoc always
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: NTFS + Edit tool truncates Python files >100 lines silently — use heredoc always
- evidence: NTFS + Edit tool truncates Python files >100 lines silently — use heredoc always
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-3] (high) kb-fact → `index_to_kb`
- title: OWUI API tool_ids field exists (found in middleware.py) but requires native FC JSON from…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: OWUI API tool_ids field exists (found in middleware.py) but requires native FC JSON from model — local Qwen3.6 does not emit this
- evidence: OWUI API tool_ids field exists (found in middleware.py) but requires native FC JSON from model — local Qwen3.6 does not emit this
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-4] (high) kb-fact → `index_to_kb`
- title: pfSense auth header: X-API-Key: <key> — NOT Authorization: Bearer <key>
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense auth header: X-API-Key: <key> — NOT Authorization: Bearer <key>
- evidence: pfSense auth header: X-API-Key: <key> — NOT Authorization: Bearer <key>
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-5] (high) kb-fact → `index_to_kb`
- title: Vaultwarden tools: pass via tool_ids only when needed — not default-enabled (security…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Vaultwarden tools: pass via tool_ids only when needed — not default-enabled (security boundary)
- evidence: Vaultwarden tools: pass via tool_ids only when needed — not default-enabled (security boundary)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-6] (high) kb-fact → `index_to_kb`
- title: pfsense-agent.py: --think -> max_tokens=4096, no prefill; --no-think -> max_tokens=2048,…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfsense-agent.py: --think -> max_tokens=4096, no prefill; --no-think -> max_tokens=2048, prefill applied
- evidence: pfsense-agent.py: --think -> max_tokens=4096, no prefill; --no-think -> max_tokens=2048, prefill applied
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-7] (high) kb-fact → `index_to_kb`
- title: DO NOT sentinels: FIRST="DO NOT: query __schema or __type (context bomb -- crashes…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: DO NOT sentinels: FIRST="DO NOT: query __schema or __type (context bomb -- crashes session)", LAST="DO NOT: guess placement index -- read-first always"
- evidence: DO NOT sentinels: FIRST="DO NOT: query __schema or __type (context bomb -- crashes session)", LAST="DO NOT: guess placement index -- read-first always"
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-8] (high) kb-fact → `index_to_kb`
- title: Dify deploy: git clone https://github.com/langgenius/dify && cd dify/docker && cp…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Dify deploy: git clone https://github.com/langgenius/dify && cd dify/docker && cp .env.example .env && docker compose up -d
- evidence: Dify deploy: git clone https://github.com/langgenius/dify && cd dify/docker && cp .env.example .env && docker compose up -d
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-9] (medium) skill-candidate → `skill_record`
- task: Replace ALL `^\s*` with `^[ \t]*` in step-matching regexes. Spaces and tabs only — never…
- occupation: network-engineer | provenance: debrief-backfill-2026-06-09
- procedure: Replace ALL `^\s*` with `^[ \t]*` in step-matching regexes. Spaces and tabs only — never newlines.
  Confirm the bug: `re.search(r"(?m)^\s*Step \d+:", "foo\n\n       Step 2: bar").start()` → 4 (the \n, not 6)
- verification: Confirm the bug: `re.search(r"(?m)^\s*Step \d+:", "foo\n\n       Step 2: bar").start()` → 4 (the \n, not 6)
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-10] (low) skill-candidate → `skill_record`
- task: Walk backwards from step_matches[-1] looking for contiguous descending sequence; use…
- occupation: network-engineer | provenance: debrief-backfill-2026-06-09
- procedure: Walk backwards from step_matches[-1] looking for contiguous descending sequence; use group_start_idx as real start.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-09-e10-11] (medium) kb-fact → `index_to_kb`
- title: Always use `cat > /tmp/file.py << 'PYEOF'` heredoc for ANY .py file >100 lines. Never use…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Always use `cat > /tmp/file.py << 'PYEOF'` heredoc for ANY .py file >100 lines. Never use Edit tool on large Python files in the Windows-mounted workspace.
- evidence: Attempted: Edit tool to patch pfsense-agent.py (331 lines) on NTFS | Failed because: Edit tool silently truncates large Python files on NTFS at ~2600-3000 chars — no error, file written but incomplete. | Always use `cat > /tmp/file.py << 'PYEOF'` heredoc for ANY .py file >100 lines. Never use Edit tool on large Python files in the Windows-mounted workspace.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-12] (medium) kb-fact → `index_to_kb`
- title: **Attempted:** OpenWebUI /api/chat/completions with tool_ids to trigger LSE tool…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: **Attempted:** OpenWebUI /api/chat/completions with tool_ids to trigger LSE tool execution
  **Failed because:** Local Qwen3.6 generates reasoning text about which tools to call — does NOT emit OpenAI-style tool_calls JSON. OWUI agentic loop only fires on structured FC JSON. Chat UI uses a ReAct text-based pattern that the API path does not share.
  **Decision:** Adopted Dify for multi-agent UI. OWUI pipe function deferred.
- evidence: **Attempted:** OpenWebUI /api/chat/completions with tool_ids to trigger LSE tool execution
  **Failed because:** Local Qwen3.6 generates reasoning text about which tools to call — does NOT emit OpenAI-style tool_calls JSON. OWUI agentic loop only fires on structured FC JSON. Chat UI uses a ReAct text-based pattern that the API path does not share.
  **Decision:** Adopted Dify for multi-agent UI. OWUI pipe function deferred.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

### [2026-06-09-e10-13] (medium) skill-candidate → `skill_record`
- task: Writing large Python files via `cat > /tmp/file.py << 'PYEOF'` heredoc + `python3 -c…
- occupation: network-engineer | provenance: debrief-backfill-2026-06-09
- procedure: Writing large Python files via `cat > /tmp/file.py << 'PYEOF'` heredoc + `python3 -c "import ast; ast.parse(...)"` syntax check + `cp` to workspace
- verification: Writing large Python files via `cat > /tmp/file.py << 'PYEOF'` heredoc + `python3 -c "import ast; ast.parse(...)"` syntax check + `cp` to workspace
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-09 (pfsense-agent _extract_prompt + OWUI API gap).

---

## Session 2026-06-11 — Hermes recovery + LSE stale search_kb cache

### [2026-06-11-e11-1] (high) kb-fact → `index_to_kb`
- title: Hermes gateway binary: `/home/hermes-admin/.local/bin/hermes`
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes gateway binary: `/home/hermes-admin/.local/bin/hermes`
- evidence: Hermes gateway binary: `/home/hermes-admin/.local/bin/hermes`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-2] (high) kb-fact → `index_to_kb`
- title: Service ExecStart: `/home/hermes-admin/.local/bin/hermes gateway run --replace`
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Service ExecStart: `/home/hermes-admin/.local/bin/hermes gateway run --replace`
- evidence: Service ExecStart: `/home/hermes-admin/.local/bin/hermes gateway run --replace`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-3] (high) kb-fact → `index_to_kb`
- title: socat: 0.0.0.0:8643 → 127.0.0.1:8642 (hermes-socat.service, co-starts with gateway)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: socat: 0.0.0.0:8643 → 127.0.0.1:8642 (hermes-socat.service, co-starts with gateway)
- evidence: socat: 0.0.0.0:8643 → 127.0.0.1:8642 (hermes-socat.service, co-starts with gateway)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-4] (high) kb-fact → `index_to_kb`
- title: Recovery after gateway crash: `sudo systemctl restart hermes-gateway` on node3090
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Recovery after gateway crash: `sudo systemctl restart hermes-gateway` on node3090
- evidence: Recovery after gateway crash: `sudo systemctl restart hermes-gateway` on node3090
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-5] (high) kb-fact → `index_to_kb`
- title: node3090 canonical model:…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: node3090 canonical model: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- evidence: node3090 canonical model: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-6] (high) kb-fact → `index_to_kb`
- title: node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)
- evidence: node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-7] (high) kb-fact → `index_to_kb`
- title: run_episode.py is NOT in /opt/local-se/ — correct path:
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: run_episode.py is NOT in /opt/local-se/ — correct path:
- evidence: run_episode.py is NOT in /opt/local-se/ — correct path:
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-8] (high) kb-fact → `index_to_kb`
- title: Duplicate model files on node3090 disk (80% full): `/opt/models/...` (stale copy)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Duplicate model files on node3090 disk (80% full): `/opt/models/...` (stale copy)
- evidence: Duplicate model files on node3090 disk (80% full): `/opt/models/...` (stale copy)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-9] (high) kb-fact → `index_to_kb`
- title: hermes-agent 0.16.0 is already latest — /status malformed issue self-resolved on restart
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: hermes-agent 0.16.0 is already latest — /status malformed issue self-resolved on restart
- evidence: hermes-agent 0.16.0 is already latest — /status malformed issue self-resolved on restart
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-10] (medium) kb-fact → `index_to_kb`
- title: Add explicit SSH verification step to task prompt. Never trust LSE-reported file contents…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Add explicit SSH verification step to task prompt. Never trust LSE-reported file
  contents for critical values — verify via `ssh ... cat <file>`.
- evidence: Attempted: LSE `read_file('/opt/local-se/kb/node3090-llama-launch.md')` during live task | Failed because: LSE returned stale in-context cached content — reported model path as
  `/opt/models/...` even though file on disk had `/home/sy5/.lmstudio/models/...`. Both
  `search_kb` and `read_file` can anchor on context-window cache rather than reading disk. | Add explicit SSH verification step to task prompt. Never trust LSE-reported file
  contents for critical values — verify via `ssh ... cat <file>`.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

### [2026-06-11-e11-11] (medium) skill-candidate → `skill_record`
- task: **Attempted:** `sudo -u hermes-admin python3 -m pip install --upgrade hermes-agent`…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: **Attempted:** `sudo -u hermes-admin python3 -m pip install --upgrade hermes-agent`
  **Failed because:** Ubuntu 24.04 PEP 668 externally-managed-environment. No pip binary
  in `/home/hermes-admin/.local/bin/`.
  **Fix (if upgrade needed):** Check `sudo -u hermes-admin pipx list` first. If not pipx,
  upgrade via: `sudo -u hermes-admin python3 -m pip install --upgrade hermes-agent
  --break-system-packages` (safe — targets hermes-admin ~/.local only).
- verification: **Fix (if upgrade needed):** Check `sudo -u hermes-admin pipx list` first.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (Hermes recovery + LSE stale search_kb cache).

---

## Session 2026-06-11 — P20: episodes don't execute commands; perms; Hermes unit

### [2026-06-11-e12-1] (high) kb-fact → `index_to_kb`
- title: Episode harness = EVALUATOR ONLY. Arena "solved" on write challenges measures world state,
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Episode harness = EVALUATOR ONLY. Arena "solved" on write challenges measures world state,
- evidence: Episode harness = EVALUATOR ONLY. Arena "solved" on write challenges measures world state,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-2] (high) kb-fact → `index_to_kb`
- title: Episode #35: model emitted NATIVE tool_calls JSON ({'tool_calls': '[2 items]'}) — harness
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Episode #35: model emitted NATIVE tool_calls JSON ({'tool_calls': '[2 items]'}) — harness
- evidence: Episode #35: model emitted NATIVE tool_calls JSON ({'tool_calls': '[2 items]'}) — harness
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-3] (high) kb-fact → `index_to_kb`
- title: agent_commands.log only records OWUI tool calls — episodes never appear in it
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: agent_commands.log only records OWUI tool calls — episodes never appear in it
- evidence: agent_commands.log only records OWUI tool calls — episodes never appear in it
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-4] (high) kb-fact → `index_to_kb`
- title: /opt/models on node3090: sy5:sy5 775; lse-admin now in sy5 group (WRITE-OK verified)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: /opt/models on node3090: sy5:sy5 775; lse-admin now in sy5 group (WRITE-OK verified)
- evidence: /opt/models on node3090: sy5:sy5 775; lse-admin now in sy5 group (WRITE-OK verified)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-5] (high) kb-fact → `index_to_kb`
- title: Hermes ~/.hermes/memories/ is EMPTY; SOUL.md is the reliable install point for identity
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes ~/.hermes/memories/ is EMPTY; SOUL.md is the reliable install point for identity
- evidence: Hermes ~/.hermes/memories/ is EMPTY; SOUL.md is the reliable install point for identity
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-6] (high) kb-fact → `index_to_kb`
- title: Hermes /status "Agent Running: No" = normal idle (agent spawns per conversation)
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes /status "Agent Running: No" = normal idle (agent spawns per conversation)
- evidence: Hermes /status "Agent Running: No" = normal idle (agent spawns per conversation)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-7] (high) kb-fact → `index_to_kb`
- title: EscalationWrapper auto-indexed 4 junk web-search docs at quality 0.7 during stagnation
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: EscalationWrapper auto-indexed 4 junk web-search docs at quality 0.7 during stagnation
- evidence: EscalationWrapper auto-indexed 4 junk web-search docs at quality 0.7 during stagnation
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

### [2026-06-11-e12-8] (medium) skill-candidate → `skill_record`
- task: Short-term: perform write tasks via interactive LSE chat (OWUI ReAct path), then run the…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: Short-term: perform write tasks via interactive LSE chat (OWUI ReAct path),
  then run the episode as verifier. Long-term: episode actuation layer (v1.7.0-a, P0).
- **Attempted:** seed notes instructing sudo rm via SSH
  **Failed because:** execute_command blocks ANY command containing "sudo" (v1.4.2 substring
  check, even remote sudo inside an ssh string) → sudo_delegation_block → no human present
  during episodes
  **Fix:** never put sudo in episode/seed instructions; fix permissions structurally instead
- **Attempted:** hermes-gateway restarts kept exiting status=1; 19:25 SIGKILL
  **Failed because:** unit had TimeoutStopSec=90s but agent drain_timeout=180s — systemd
  killed the gateway mid-drain (gateway itself logged the warning)
  **Fix:** TimeoutStopSec=210s added to /etc/systemd/system/hermes-gateway.service + daemon-reload
- verification: Short-term: perform write tasks via interactive LSE chat (OWUI ReAct path),
  then run the episode as verifier.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (P20: episodes don't execute commands; perms; Hermes unit).

---

## Session 2026-06-11 — P20 addendum: model deletion incident

### [2026-06-11-e13-1] (high) kb-fact → `index_to_kb`
- title: DUPLICATE-DELETE RULE: before deleting any "duplicate", run readlink -f AND stat -c '%i…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: DUPLICATE-DELETE RULE: before deleting any "duplicate", run readlink -f AND stat -c '%i %h' on BOTH paths —
- evidence: DUPLICATE-DELETE RULE: before deleting any "duplicate", run readlink -f AND stat -c '%i %h' on BOTH paths —
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20 addendum: model deletion incident).

### [2026-06-11-e13-2] (high) kb-fact → `index_to_kb`
- title: A running llama-server pins its deleted model inode via mmap (~15GB invisible to ls, held…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: A running llama-server pins its deleted model inode via mmap (~15GB invisible to ls, held until restart);
- evidence: A running llama-server pins its deleted model inode via mmap (~15GB invisible to ls, held until restart);
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20 addendum: model deletion incident).

### [2026-06-11-e13-3] (high) kb-fact → `index_to_kb`
- title: HF LFS reference hash: curl -s https://huggingface.co/<repo>/raw/main/<file> returns oid…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: HF LFS reference hash: curl -s https://huggingface.co/<repo>/raw/main/<file> returns oid sha256 + size —
- evidence: HF LFS reference hash: curl -s https://huggingface.co/<repo>/raw/main/<file> returns oid sha256 + size —
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20 addendum: model deletion incident).

### [2026-06-11-e13-4] (high) kb-fact → `index_to_kb`
- title: Hermes executed the recovery autonomously (aria2c as hermes-admin → ~/tmp_dl) — agent…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes executed the recovery autonomously (aria2c as hermes-admin → ~/tmp_dl) — agent background jobs run
- evidence: Hermes executed the recovery autonomously (aria2c as hermes-admin → ~/tmp_dl) — agent background jobs run
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20 addendum: model deletion incident).

### [2026-06-11-e13-5] (high) kb-fact → `index_to_kb`
- title: node-t3-005 retired (false premise). Successor: node-t3-006 Model Store Reconciliation —
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: node-t3-005 retired (false premise). Successor: node-t3-006 Model Store Reconciliation —
- evidence: node-t3-005 retired (false premise). Successor: node-t3-006 Model Store Reconciliation —
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-11 (P20 addendum: model deletion incident).

### [2026-06-11-e13-6] (low) skill-candidate → `skill_record`
- task: restored byte-exact from HF via Hermes aria2c (sha256 33625d8d... matches HF LFS), zero…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-11
- procedure: restored byte-exact from HF via Hermes aria2c (sha256 33625d8d... matches HF LFS), zero downtime —
  llama-server served from VRAM throughout; controlled restart after restore.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-11 (P20 addendum: model deletion incident). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-06-12 — P22: Hermes skills inert, Goethe spiral, attention is not a control plane

### [2026-06-12-e14-1] (high) kb-fact → `index_to_kb`
- title: Hermes skill learning (v0.16.0): SKILL.md files in ~/.hermes/skills/, FULL-manifest prompt
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes skill learning (v0.16.0): SKILL.md files in ~/.hermes/skills/, FULL-manifest prompt
- evidence: Hermes skill learning (v0.16.0): SKILL.md files in ~/.hermes/skills/, FULL-manifest prompt
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-2] (high) kb-fact → `index_to_kb`
- title: LSE surpass design: retrieval (top-2 kNN+BM25) beats prompt injection; evidence-gated…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: LSE surpass design: retrieval (top-2 kNN+BM25) beats prompt injection; evidence-gated quality
- evidence: LSE surpass design: retrieval (top-2 kNN+BM25) beats prompt injection; evidence-gated quality
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-3] (high) kb-fact → `index_to_kb`
- title: v1.6.4 search_kb was ALREADY hybrid kNN(0.7)+BM25(0.3) — 1.7.0-design §3.5.2 "kNN-only"…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: v1.6.4 search_kb was ALREADY hybrid kNN(0.7)+BM25(0.3) — 1.7.0-design §3.5.2 "kNN-only" claim
- evidence: v1.6.4 search_kb was ALREADY hybrid kNN(0.7)+BM25(0.3) — 1.7.0-design §3.5.2 "kNN-only" claim
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-4] (high) kb-fact → `index_to_kb`
- title: Cogitator v1.7.2: sha256 eca3b518…, 3356 lines. Budget gate state: <TASKS_DB…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Cogitator v1.7.2: sha256 eca3b518…, 3356 lines. Budget gate state: <TASKS_DB dir>/.search_budget.json.
- evidence: Cogitator v1.7.2: sha256 eca3b518…, 3356 lines. Budget gate state: <TASKS_DB dir>/.search_budget.json.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-5] (high) kb-fact → `index_to_kb`
- title: SearxNG returning arxiv hits for ALL queries = general engines suspended/failing, science
- topic: searxng | source_tier: ground_truth | quality_score: 0.85
- content: SearxNG returning arxiv hits for ALL queries = general engines suspended/failing, science
- evidence: SearxNG returning arxiv hits for ALL queries = general engines suspended/failing, science
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-6] (high) kb-fact → `index_to_kb`
- title: hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.
- evidence: hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

### [2026-06-12-e14-7] (medium) skill-candidate → `skill_record`
- task: v1.7.1 three-layer containment — (1) code-enforced search budget, (2) task_checkpoint/…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: v1.7.1 three-layer containment — (1) code-enforced search budget, (2) task_checkpoint/
  task_resume blocks in /opt/local-se/tasks.db with mandatory findings-vs-UNVERIFIED separation,
  (3) planner-orchestrator pre-flight on Hermes (docs/planner-orchestrator-design.md, 1.7.2).
- **Attempted:** 8-call budget on a 30-min rolling window (v1.7.1 default)
  **Failed because:** window leaked across task_resume sessions — resumed task hit
  "BUDGET EXHAUSTED" on its first search; LSE stalled ~7 min mid-conversation and fell back to
  unverified training-knowledge answers for a router-flash procedure.
  **Fix:** SEARCH_BUDGET_WINDOW_MIN 30→2 (v1.7.2, or live valve edit in OWUI). Rate-limit
  windows for interactive agents must be shorter than a conversation turn.
- **Attempted:** trusting LSE's infra diagnosis ("Teltonika domain unreachable — DNS issue")
  **Failed because:** fbidownload.teltonika-networks.com never existed (zero web references) —
  LSE fabricated the hostname when retrieval was blocked, then narrated the NXDOMAIN as a
  network outage and gave the user the fake URL. Second fabrication-under-pressure
  (Goethe quote was the first). Pattern: blocked retrieval → confident invention + diagnostic story.
  **Fix:** real source is wiki.teltonika-networks.com/view/RUTX50_Firmware_Downloads. Rule:
  NEVER present a URL/hostname that did not come out of a tool result; an NXDOMAIN on a
  self-generated hostname is evidence about the hostname, not the network. Enforced in v1.7.3
  (budget-refusal text + fetch_url docstring).
- **Attempted:** find Hermes' skill modules with find -path "*hermes*" -iname "*skill*"
  **Failed because:** openai/fastapi SDK files match "*skill*" and flooded head -15; hermes
  package dirs sorted later in traversal order.
  **Fix:** ls site-packages | grep -i herm first, then find inside the confirmed package dirs.
- verification: **Fix:** ls site-packages | grep -i herm first, then find inside the confirmed package dirs.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-12 (P22: Hermes skills inert, Goethe spiral, attention is not a control plane).

---

## Session 2026-06-12 — P24: OWUI black-formats tools; "after responding" is unreachable

### [2026-06-12-e15-1] (high) kb-fact → `index_to_kb`
- title: OWUI webui.db: /home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: OWUI webui.db: /home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db (memory + chat tables live here)
- evidence: OWUI webui.db: /home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db (memory + chat tables live here)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-2] (high) kb-fact → `index_to_kb`
- title: call_hermes prepends "CONTEXT:" — grep agent.log for correlation ids, not 'PLAN REQUEST'
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: call_hermes prepends "CONTEXT:" — grep agent.log for correlation ids, not 'PLAN REQUEST'
- evidence: call_hermes prepends "CONTEXT:" — grep agent.log for correlation ids, not 'PLAN REQUEST'
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-3] (high) kb-fact → `index_to_kb`
- title: Hermes memory pointer (MEMORY.md line 3) WORKS — contract is read on every PLAN REQUEST…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: Hermes memory pointer (MEMORY.md line 3) WORKS — contract is read on every PLAN REQUEST turn
- evidence: Hermes memory pointer (MEMORY.md line 3) WORKS — contract is read on every PLAN REQUEST turn
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-4] (high) kb-fact → `index_to_kb`
- title: Playwright run-server is WebSocket-only: plain GET = error page, that's healthy;…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: Playwright run-server is WebSocket-only: plain GET = error page, that's healthy; EADDRINUSE on "restart" means it was already up
- evidence: Playwright run-server is WebSocket-only: plain GET = error page, that's healthy; EADDRINUSE on "restart" means it was already up
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-5] (high) kb-fact → `index_to_kb`
- title: "Message Hermes" via the LSE can land in the WRONG memory store (LSE's own OWUI memory) —…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: "Message Hermes" via the LSE can land in the WRONG memory store (LSE's own OWUI memory) — always verify on node3090: sudo grep PLANNER /home/hermes-admin/.hermes/memories/MEMORY.md
- evidence: "Message Hermes" via the LSE can land in the WRONG memory store (LSE's own OWUI memory) — always verify on node3090: sudo grep PLANNER /home/hermes-admin/.hermes/memories/MEMORY.md
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-6] (medium) skill-candidate → `skill_record`
- task: black-normalize the repo file before hashing (command above) - **Attempted:** Contract v2…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: black-normalize the repo file before hashing (command above)
- **Attempted:** Contract v2 rule "After producing a plan envelope, create ONE card"
  **Failed because:** Emitting the response ENDS the agent's turn — any "after responding, do X" instruction is unreachable. Same dead-path class as v1.7.3 call_hermes error returns
  **Fix:** Contract v2.1 — card creation is step 1, BEFORE the envelope; "ONLY JSON" clarified to refer to final message content, not tool actions
- **Attempted:** Getting Hermes to create the kanban card via contract v2.1 wording
  **Failed because:** Planner session toolset has NO kanban-write tool (proved by tool-hunting in agent.log: cronjob -> skills_list -> gave up). Capability gap, not prompt bug
  **Fix:** Pending v1.7.9 — hermes_plan creates the card itself (enforcement in code). Pre-check kanban_db.py VALID_INITIAL_STATUSES before direct INSERT
- verification: Pre-check kanban_db.py VALID_INITIAL_STATUSES before direct INSERT
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-7] (medium) skill-candidate → `skill_record`
- task: Deploy verification by normalization: `python3 -c "import black,hashlib;…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: Deploy verification by normalization: `python3 -c "import black,hashlib; print(hashlib.sha256(black.format_str(open('tools/cogitator-vX.Y.Z.py').read(), mode=black.Mode()).encode()).hexdigest())"` — compare THIS to the installed tool's sha, never the raw file sha
- verification: Deploy verification by normalization: `python3 -c "import black,hashlib; print(hashlib.sha256(black.format_str(open('tools/cogitator-vX.Y.Z.py').read(), mode=black.Mode()).encode()).hexdigest())"` — compare THIS to the installed tool's sha, never the raw file sha
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable).

### [2026-06-12-e15-8] (low) skill-candidate → `skill_record`
- task: Ground-truthing agent claims via Hermes agent.log: tool calls + char counts reveal what…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: Ground-truthing agent claims via Hermes agent.log: tool calls + char counts reveal what the model actually did (read_file 6871 chars = contract v2.1; then cronjob + skills_list = hunting for a missing board tool)
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-12 (P24: OWUI black-formats tools; "after responding" is unreachable). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-06-12 — P25: triage is the decomposer's inbox; fabrication survives prompt fences

### [2026-06-12-e16-1] (high) kb-fact → `index_to_kb`
- title: kanban.db tasks: created_at INTEGER epoch, no CHECK on status, idempotency_key indexed;…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: kanban.db tasks: created_at INTEGER epoch, no CHECK on status, idempotency_key indexed; t_* ids = Hermes API path; created_by column reveals the writer (auto-decomposer vs lse-cogitator)
- evidence: kanban.db tasks: created_at INTEGER epoch, no CHECK on status, idempotency_key indexed; t_* ids = Hermes API path; created_by column reveals the writer (auto-decomposer vs lse-cogitator)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-2] (high) kb-fact → `index_to_kb`
- title: node3090 ~/.hermes/config.yaml: auto_decompose now FALSE; manual decompose = `hermes…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: node3090 ~/.hermes/config.yaml: auto_decompose now FALSE; manual decompose = `hermes kanban decompose <id>` or dashboard button
- evidence: node3090 ~/.hermes/config.yaml: auto_decompose now FALSE; manual decompose = `hermes kanban decompose <id>` or dashboard button
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-3] (high) kb-fact → `index_to_kb`
- title: P24 "webui.db clean" was a false-negative: verify ABSENCE with storage-shaped queries…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: P24 "webui.db clean" was a false-negative: verify ABSENCE with storage-shaped queries (time-window on chat.updated_at), never text-grep for command text that isn't persisted
- evidence: P24 "webui.db clean" was a false-negative: verify ABSENCE with storage-shaped queries (time-window on chat.updated_at), never text-grep for command text that isn't persisted
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-4] (high) kb-fact → `index_to_kb`
- title: 06-10 22:14 sweep = SY5's "Claude Code Security Check" OWUI chat (npm supply-chain, Check…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: 06-10 22:14 sweep = SY5's "Claude Code Security Check" OWUI chat (npm supply-chain, Check Point) — harness exonerated: run_episode.py -> llama-server direct, never the cogitator, never agent_commands.log
- evidence: 06-10 22:14 sweep = SY5's "Claude Code Security Check" OWUI chat (npm supply-chain, Check Point) — harness exonerated: run_episode.py -> llama-server direct, never the cogitator, never agent_commands.log
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-5] (high) kb-fact → `index_to_kb`
- title: RUTX50: 07.22.3=official Stable, 07.23.4=Latest, NO fix exists (verified 2026-06-12);…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: RUTX50: 07.22.3=official Stable, 07.23.4=Latest, NO fix exists (verified 2026-06-12); webui auth = uhttpd->api_dispatcher.lua(LuaJIT)->ubus session, SSH=dropbear (separate); recovery: /etc/init.d/uhttpd restart; downgrade WITHOUT keep-settings
- evidence: RUTX50: 07.22.3=official Stable, 07.23.4=Latest, NO fix exists (verified 2026-06-12); webui auth = uhttpd->api_dispatcher.lua(LuaJIT)->ubus session, SSH=dropbear (separate); recovery: /etc/init.d/uhttpd restart; downgrade WITHOUT keep-settings
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-6] (medium) skill-candidate → `skill_record`
- task: auto_decompose: false in /home/hermes-admin/.hermes/config.yaml (~line 441, backup…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: auto_decompose: false in /home/hermes-admin/.hermes/config.yaml (~line 441, backup .bak-P25) + systemctl restart hermes-gateway. Verified: next card stayed triage
- **Attempted:** Stopping the rogue work by archiving the cards
  **Failed because:** archive does NOT stop an in-flight worker — pid 11699 kept executing the archived card for 10+ min
  **Fix:** kill tasks.worker_pid explicitly, THEN archive
- **Attempted:** Preventing RUTX50 fabrication via explicit context fence ("no version newer than 07.23.4 exists") + verified ground truth provided
  **Failed because:** LSE fetched the wiki page (07.22.3=Stable/07.23.4=Latest in plain view) and STILL emitted phantom 07.23.5 + 07.22.4 with invented dates/changelogs recombined from the real 07.23 changelog — evidence overwrite at synthesis, fabrication #5
  **Fix:** corrected docs/rutx50/rutx50-remediation-decision.md (correction header). Real fix queued v1.7.10: code-enforced source-claim verification (re-fetch cited sources, diff claimed facts) — fences don't hold at synthesis
- verification: Verified: next card stayed triage
- **Attempted:** Stopping the rogue work by archiving the cards
  **Failed because:** archive does NOT stop an in-flight worker — pid 11699 kept executing the archived card for 10+ min
  **Fix:** kill tasks.worker_pid explicitly, THEN archive
- **Attempted:** Preventing RUTX50 fabrication via explicit context fence ("no version newer than 07.23.4 exists") + verified ground truth provided
  **Failed because:** LSE fetched the wiki page (07.22.3=Stable/07.23.4=Latest in plain view) and STILL emitted phantom 07.23.5 + 07.22.4 with invented dates/changelogs recombined from the real 07.23 changelog — evidence overwrite at synthesis, fabrication #5
  **Fix:** corrected docs/rutx50/rutx50-remediation-decision.md (correction header).
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

### [2026-06-12-e16-7] (medium) skill-candidate → `skill_record`
- task: v1.7.9 direct INSERT into kanban.db: schema has NO CHECK on status;…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-12
- procedure: v1.7.9 direct INSERT into kanban.db: schema has NO CHECK on status; VALID_INITIAL_STATUSES={running,blocked} gates only the Python API. created_at is INTEGER epoch. idempotency_key + INSERT OR IGNORE = re-plan safe
- verification: v1.7.9 direct INSERT into kanban.db: schema has NO CHECK on status; VALID_INITIAL_STATUSES={running,blocked} gates only the Python API.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-12 (P25: triage is the decomposer's inbox; fabrication survives prompt fences).

---

## Session 2026-06-13 — P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache

### [2026-06-13-e17-1] (high) kb-fact → `index_to_kb`
- title: LARGE .py FILES ON NTFS: USE BASH. NOT Write/Edit tools. ALWAYS.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: LARGE .py FILES ON NTFS: USE BASH. NOT Write/Edit tools. ALWAYS.
- evidence: LARGE .py FILES ON NTFS: USE BASH. NOT Write/Edit tools. ALWAYS.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-2] (high) kb-fact → `index_to_kb`
- title: For .md files: use Read/Write/Edit file tools. Bash mount can show stale/truncated NTFS…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: For .md files: use Read/Write/Edit file tools. Bash mount can show stale/truncated NTFS state.
- evidence: For .md files: use Read/Write/Edit file tools. Bash mount can show stale/truncated NTFS state.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-3] (high) kb-fact → `index_to_kb`
- title: ES lse-kb field is source_url (not source). Full schema: content, created_at, doc_id,
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: ES lse-kb field is source_url (not source). Full schema: content, created_at, doc_id,
- evidence: ES lse-kb field is source_url (not source). Full schema: content, created_at, doc_id,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-4] (high) kb-fact → `index_to_kb`
- title: KV cache: K must stay Q8_0 -- lowering K breaks this model. V is the only safe knob:
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: KV cache: K must stay Q8_0 -- lowering K breaks this model. V is the only safe knob:
- evidence: KV cache: K must stay Q8_0 -- lowering K breaks this model. V is the only safe knob:
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-5] (high) kb-fact → `index_to_kb`
- title: SSH v1.7.13: search_kb('{hostname} SSH access') with NO topic_filter before any ssh…
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: SSH v1.7.13: search_kb('{hostname} SSH access') with NO topic_filter before any ssh command.
- evidence: SSH v1.7.13: search_kb('{hostname} SSH access') with NO topic_filter before any ssh command.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-6] (medium) kb-fact → `index_to_kb`
- title: OWUI copy-paste backup is the authoritative source for deployed code.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: OWUI copy-paste backup is the authoritative source for deployed code.
- evidence: Attempted: Reconstructing cogitator from P26 transcript after truncation | Failed because: User paste was last message before context summarization, compressed
  into summary prose, not preserved in JSONL. Largest JSONL message was 43KB; 213KB paste lost. | OWUI copy-paste backup is the authoritative source for deployed code.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-7] (low) skill-candidate → `skill_record`
- task: src.get("source_url"); target by title match, not URL-content match.
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-13
- procedure: src.get("source_url"); target by title match, not URL-content match.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-13-e17-8] (medium) kb-fact → `index_to_kb`
- title: PowerShell: Get-ChildItem ".git\*.lock" | Remove-Item -Force before every commit.
- topic: llama-cpp | source_tier: ground_truth | quality_score: 0.85
- content: PowerShell: Get-ChildItem ".git\*.lock" | Remove-Item -Force before every commit.
- evidence: Attempted: Git commit from Cowork sandbox | Failed because: .git/index.lock and HEAD.lock persisted from crashed session.
  Sandbox cannot delete NTFS lock files -- rm returns "Operation not permitted". | PowerShell: Get-ChildItem ".git\*.lock" | Remove-Item -Force before every commit.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache).

### [2026-06-13-e17-9] (low) skill-candidate → `skill_record`
- task: OWUI backup recovery: copy-paste tool code from OWUI editor to txt then rename .py.
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-13
- procedure: OWUI backup recovery: copy-paste tool code from OWUI editor to txt then rename .py.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-13 (P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-06-14 — P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation

### [2026-06-14-e18-1] (high) kb-fact → `index_to_kb`
- title: `check_hermes_inbox` is EMPTY until the Hermes-side outbox (producer) is installed — that…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: `check_hermes_inbox` is EMPTY until the Hermes-side outbox (producer) is installed — that is correct,
- evidence: `check_hermes_inbox` is EMPTY until the Hermes-side outbox (producer) is installed — that is correct,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation).

### [2026-06-14-e18-2] (high) kb-fact → `index_to_kb`
- title: Hermes skills = SKILL.md (YAML frontmatter + markdown) in `~/.hermes/skills/`, installed…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Hermes skills = SKILL.md (YAML frontmatter + markdown) in `~/.hermes/skills/`, installed via
- evidence: Hermes skills = SKILL.md (YAML frontmatter + markdown) in `~/.hermes/skills/`, installed via
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation).

### [2026-06-14-e18-3] (high) kb-fact → `index_to_kb`
- title: ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds :8642 direct.
- evidence: ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds :8642 direct.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation).

### [2026-06-14-e18-4] (high) kb-fact → `index_to_kb`
- title: Cogitator deploy identity = black-norm sha. v1.7.21 = `79b74fde…` (deployed); v1.7.22 =…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Cogitator deploy identity = black-norm sha. v1.7.21 = `79b74fde…` (deployed); v1.7.22 = `142f155a…`.
- evidence: Cogitator deploy identity = black-norm sha. v1.7.21 = `79b74fde…` (deployed); v1.7.22 = `142f155a…`.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation).

### [2026-06-14-e18-5] (low) skill-candidate → `skill_record`
- task: don't rely on the emitter to escape thinking; route the surface through the model's…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-14
- procedure: don't rely on the emitter to escape thinking; route the surface through the model's
  post-`<think>` reply via a return-value directive (v1.7.21). Emitter kept only as best-effort.
- **Attempted:** treat LSE-ARCHITECTURE.md / ROADMAP.md "modified" in sandbox `git diff` as phantom.
  **Failed because:** the sandbox mount serves a STALE cached copy of existing repo files — it showed
  LSE-ARCHITECTURE.md socat-FREE while the real working tree (host tools + WSL2 git) had an
  uncommitted socat block. The earlier "phantom truncation" was stale-cache, and it is file-specific.
  **Fix:** for existing repo files trust HOST Read/Edit/Grep and WSL2 git — never sandbox bash
  reads/diffs. Bash WRITES of NEW files propagate fine; bash reads of MODIFIED files can be stale.
- **Attempted:** carry a full ssh log through the Hermes inbox marker.
  **Failed because:** the marker rides reply content; large payloads overflow the reply token cap and
  the JSON marker truncates → `json.loads` fails → message lost. Small messages round-trip fine.
  **Fix:** carry large artifacts BY REFERENCE — Hermes writes the log to a file, the envelope body
  holds the path, the LSE fetches via `execute_command` SSH. The inbox is for small control messages.
  Also: the poll's `max_tokens` was 8 (Path A sizing) — raised to 1024 (v1.7.22) so a Path B marker fits.
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

### [2026-06-14-e18-6] (low) skill-candidate → `skill_record`
- task: Building v1.7.20→22 via bash splice with per-replacement `count==1` asserts + `ast.parse`…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-06-14
- procedure: Building v1.7.20→22 via bash splice with per-replacement `count==1` asserts + `ast.parse` +
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-06-14 (P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-06-14 — P31

### [2026-06-14-e19-1] (high) kb-fact → `index_to_kb`
- title: Run throwaway build/verify steps (`npm install`, test runs) in the SANDBOX scratch dir,…
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: Run throwaway build/verify steps (`npm install`, test runs) in the SANDBOX scratch dir, never inside the mounted repo — the sandbox can create on the NTFS mount but cannot unlink, so a `node_modules/` (or any file) written there is unremovable from the sandbox (EPERM) and must be deleted host-side. Copy only source files into the repo.
- evidence: Run throwaway build/verify steps (`npm install`, test runs) in the SANDBOX scratch dir, never inside the mounted repo — the sandbox can create on the NTFS mount but cannot unlink, so a `node_modules/` (or any file) written there is unremovable from the sandbox (EPERM) and must be deleted host-side. Copy only source files into the repo.
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-06-14 (P31).

---

## Session 2026-07-02 — Goethe MCP hardening + Claude stdio bridge

### [2026-07-02-e20-1] (high) kb-fact → `index_to_kb`
- title: Claude Desktop active config:…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Claude Desktop active config: C:\Users\SY5\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
- evidence: Claude Desktop active config: C:\Users\SY5\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-2] (high) kb-fact → `index_to_kb`
- title: Both LocalCache AND %APPDATA% configs present → TWO stdio instances spawn (one per copy)
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Both LocalCache AND %APPDATA% configs present → TWO stdio instances spawn (one per copy)
- evidence: Both LocalCache AND %APPDATA% configs present → TWO stdio instances spawn (one per copy)
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-3] (high) kb-fact → `index_to_kb`
- title: MCP spawn diagnostics: same LocalCache tree, logs\mcp-server-goethe.log
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: MCP spawn diagnostics: same LocalCache tree, logs\mcp-server-goethe.log
- evidence: MCP spawn diagnostics: same LocalCache tree, logs\mcp-server-goethe.log
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-4] (high) kb-fact → `index_to_kb`
- title: stdio transport has NO token — token auth is HTTP-transport only; rotation cannot break…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: stdio transport has NO token — token auth is HTTP-transport only; rotation cannot break the bridge
- evidence: stdio transport has NO token — token auth is HTTP-transport only; rotation cannot break the bridge
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-5] (high) kb-fact → `index_to_kb`
- title: Never bare `pkill -f goethe_mcp.py` — kills the Claude bridge; use…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Never bare `pkill -f goethe_mcp.py` — kills the Claude bridge; use 'goethe_mcp.py.*--transport http'
- evidence: Never bare `pkill -f goethe_mcp.py` — kills the Claude bridge; use 'goethe_mcp.py.*--transport http'
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-6] (high) kb-fact → `index_to_kb`
- title: Cowork sandbox's mounted repo view can lag the real filesystem — verify git state via WSL
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Cowork sandbox's mounted repo view can lag the real filesystem — verify git state via WSL
- evidence: Cowork sandbox's mounted repo view can lag the real filesystem — verify git state via WSL
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

### [2026-07-02-e20-7] (medium) skill-candidate → `skill_record`
- task: Copy-Item the config back into LocalCache — that path is authoritative for the app -…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-07-02
- procedure: Copy-Item the config back into LocalCache — that path is authoritative for the app
- **Attempted:** narrow gateway CORS to 'http://localhost:8080'
  **Failed because:** llama-ui is browsed at http://127.0.0.1:8080 — a different origin string;
  OPTIONS preflight → 400, tool list never fetched (UI showed "connected" but zero tools)
  **Fix:** --cors-origin must match the browser address bar EXACTLY: 'http://127.0.0.1:8080'
- **Attempted:** rotate GOETHE_MCP_TOKEN server-side only
  **Failed because:** llama-ui kept sending the old token → HTTP 401 {"error":"unauthorized"} on initialize
  **Fix:** grep GOETHE_MCP_TOKEN ~/.lse/secrets → paste into llama-ui MCP settings (raw or Bearer both OK)
- **Attempted:** three changes in one gateway restart (token + bind + CORS)
  **Failed because:** simultaneous failures masked root causes — the token was blamed for a CORS break
  **Fix:** one change per restart, verify between each
- verification: Copy-Item the config back into LocalCache — that path is authoritative for the app
- **Attempted:** narrow gateway CORS to 'http://localhost:8080'
  **Failed because:** llama-ui is browsed at http://127.0.0.1:8080 — a different origin string;
  OPTIONS preflight → 400, tool list never fetched (UI showed "connected" but zero tools)
  **Fix:** --cors-origin must match the browser address bar EXACTLY: 'http://127.0.0.1:8080'
- **Attempted:** rotate GOETHE_MCP_TOKEN server-side only
  **Failed because:** llama-ui kept sending the old token → HTTP 401 {"error":"unauthorized"} on initialize
  **Fix:** grep GOETHE_MCP_TOKEN ~/.lse/secrets → paste into llama-ui MCP settings (raw or Bearer both OK)
- **Attempted:** three changes in one gateway restart (token + bind + CORS)
  **Failed because:** simultaneous failures masked root causes — the token was blamed for a CORS break
  **Fix:** one change per restart, verify between each
- why: Corrected value/command from a What-failed-and-why block. From session 2026-07-02 (Goethe MCP hardening + Claude stdio bridge).

---

## Session 2026-07-02 — PROVE-2 contract tests: venv + demotion-floor findings

### [2026-07-02-e21-1] (high) kb-fact → `index_to_kb`
- title: skill_outcome demotion floor DISCREPANCY: code is max(0.0, q - 0.15) (floor 0.0),
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: skill_outcome demotion floor DISCREPANCY: code is max(0.0, q - 0.15) (floor 0.0),
- evidence: skill_outcome demotion floor DISCREPANCY: code is max(0.0, q - 0.15) (floor 0.0),
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-2] (high) kb-fact → `index_to_kb`
- title: record_outcome(success=False) never touches quality_score (v0.2.9) — pinned in-test,
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: record_outcome(success=False) never touches quality_score (v0.2.9) — pinned in-test,
- evidence: record_outcome(success=False) never touches quality_score (v0.2.9) — pinned in-test,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-3] (high) kb-fact → `index_to_kb`
- title: Repo copies identical: /home/sy5/projects/local-system-engineer/tools/goethe.py ==
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Repo copies identical: /home/sy5/projects/local-system-engineer/tools/goethe.py ==
- evidence: Repo copies identical: /home/sy5/projects/local-system-engineer/tools/goethe.py ==
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-4] (high) kb-fact → `index_to_kb`
- title: ES top-level knn score = (1+cosine)/2 — dedup threshold 0.92 => cosine >= 0.84
- topic: infrastructure | source_tier: ground_truth | quality_score: 0.85
- content: ES top-level knn score = (1+cosine)/2 — dedup threshold 0.92 => cosine >= 0.84
- evidence: ES top-level knn score = (1+cosine)/2 — dedup threshold 0.92 => cosine >= 0.84
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-5] (high) kb-fact → `index_to_kb`
- title: pytest 9.1.1 + elasticsearch-py 8.19.3 now in owui venv; ES server 8.13.0
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: pytest 9.1.1 + elasticsearch-py 8.19.3 now in owui venv; ES server 8.13.0
- evidence: pytest 9.1.1 + elasticsearch-py 8.19.3 now in owui venv; ES server 8.13.0
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-6] (medium) kb-fact → `index_to_kb`
- title: /home/sy5/owui/bin/pip install pytest (done this session) and always run goethe-importing…
- topic: openwebui | source_tier: ground_truth | quality_score: 0.85
- content: /home/sy5/owui/bin/pip install pytest (done this session) and always run
  goethe-importing tests with the owui-venv interpreter
- evidence: Attempted: `python3 -m pytest tests/test_kb_contracts.py` with system python3 | Failed because: system python3 on LUCIFER has NO pydantic/elasticsearch — those live
  only in the owui venv (/home/sy5/owui/bin/python3), which is the goethe_mcp runtime | /home/sy5/owui/bin/pip install pytest (done this session) and always run
  goethe-importing tests with the owui-venv interpreter
- why: Corrected value/command from a What-failed-and-why block. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings).

### [2026-07-02-e21-7] (low) skill-candidate → `skill_record`
- task: Run: `cd <repo> && /home/sy5/owui/bin/python3 -m pytest tests/test_kb_contracts.py -q`
- occupation: Local System Engineer | provenance: debrief-backfill-2026-07-02
- procedure: Run: `cd <repo> && /home/sy5/owui/bin/python3 -m pytest tests/test_kb_contracts.py -q`
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-07-02 (PROVE-2 contract tests: venv + demotion-floor findings). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-07-04 — PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix

### [2026-07-04-e22-1] (high) kb-fact → `index_to_kb`
- title: goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of whether the path is written as `/mnt/c/...` or `C:\Users\...` — always delegate git and repo-root writes under this path to a real terminal
- evidence: goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of whether the path is written as `/mnt/c/...` or `C:\Users\...` — always delegate git and repo-root writes under this path to a real terminal
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-2] (high) kb-fact → `index_to_kb`
- title: `~/projects/local-system-engineer` is a symlink to…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: `~/projects/local-system-engineer` is a symlink to `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` — same privileged-path block applies through the symlink for goethe's write_file, but Claude's own mounted-folder file tools (Read/Write/Edit) can write there directly since it's the Cowork workspace folder
- evidence: `~/projects/local-system-engineer` is a symlink to `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` — same privileged-path block applies through the symlink for goethe's write_file, but Claude's own mounted-folder file tools (Read/Write/Edit) can write there directly since it's the Cowork workspace folder
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-3] (high) kb-fact → `index_to_kb`
- title: Three different version strings currently coexist for "Goethe": `tools/goethe.py`…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Three different version strings currently coexist for "Goethe": `tools/goethe.py` title/version = v0.3.8 (live, matches CURRENT-STATE.md changelog line), `goethe_mcp` startup banner = v1.9.3, and the `eval_goethe_rules.py` harness banner prints "Goethe v0.2.2" — none of these were reconciled this session, flagged in eval-report-v7.md instead
- evidence: Three different version strings currently coexist for "Goethe": `tools/goethe.py` title/version = v0.3.8 (live, matches CURRENT-STATE.md changelog line), `goethe_mcp` startup banner = v1.9.3, and the `eval_goethe_rules.py` harness banner prints "Goethe v0.2.2" — none of these were reconciled this session, flagged in eval-report-v7.md instead
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-4] (high) kb-fact → `index_to_kb`
- title: Run 8 baseline (7/9, rules scope only) recorded in CURRENT-STATE.md and…
- topic: lse-operations | source_tier: ground_truth | quality_score: 0.85
- content: Run 8 baseline (7/9, rules scope only) recorded in CURRENT-STATE.md and eval/eval-report-v7.md — commit e84eeb1
- evidence: Run 8 baseline (7/9, rules scope only) recorded in CURRENT-STATE.md and eval/eval-report-v7.md — commit e84eeb1
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-5] (medium) skill-candidate → `skill_record`
- task: `sudo_delegation_block` → user runs it in a real WSL terminal - **Attempted:** first…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-07-04
- procedure: `sudo_delegation_block` → user runs it in a real WSL terminal
- **Attempted:** first delegated git commit attempt, run in Joe's terminal
  **Failed because:** a stale `.git/index.lock` was left behind from the blocked in-sandbox attempt
  **Fix:** `rm -f .git/index.lock` before retrying add+commit
- **Attempted:** multi-line `cat > file << 'EOF' ... EOF` heredoc pasted into the terminal for a ~5KB report with unicode chars
  **Failed because:** paste truncated mid-block; bash sat at the `>` PS2 prompt waiting for the never-arrived `EOF`
  **Fix:** base64-encode the whole file content, single-line `echo '<b64>' | base64 -d > path`, verify with `wc -l` + `head`
- **Attempted (avoided, not actually run):** treating the gateway token-guard assert failure as a stack-health blocker
  **Failed because:** skill's `assert_state` regex expects literal `401`, but `curl 127.0.0.1:9700/` returns `{"error":"unauthorized"}` (JSON body, not a bare status line) — doc is stale, not a real problem
- verification: EOF` heredoc pasted into the terminal for a ~5KB report with unicode chars
  **Failed because:** paste truncated mid-block; bash sat at the `>` PS2 prompt waiting for the never-arrived `EOF`
  **Fix:** base64-encode the whole file content, single-line `echo '<b64>' | base64 -d > path`, verify with `wc -l` + `head`
- **Attempted (avoided, not actually run):** treating the gateway token-guard assert failure as a stack-health blocker
  **Failed because:** skill's `assert_state` regex expects literal `401`, but `curl 127.0.0.1:9700/` returns `{"error":"unauthorized"}` (JSON body, not a bare status line) — doc is stale, not a real problem
- why: Corrected value/command from a What-failed-and-why block. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-6] (medium) skill-candidate → `skill_record`
- task: Checking `curl :8080/slots` for `is_processing:false` before a GPU-bound eval run,…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-07-04
- procedure: Checking `curl :8080/slots` for `is_processing:false` before a GPU-bound eval run, instead of guessing whether the user is mid-conversation
- verification: Checking `curl :8080/slots` for `is_processing:false` before a GPU-bound eval run, instead of guessing whether the user is mid-conversation
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix).

### [2026-07-04-e22-7] (low) skill-candidate → `skill_record`
- task: Delegating git/file writes to a real terminal via `sudo_delegation_block` with a…
- occupation: Local System Engineer | provenance: debrief-backfill-2026-07-04
- procedure: Delegating git/file writes to a real terminal via `sudo_delegation_block` with a base64-encoded one-liner (`echo '<b64>' | base64 -d > file`) instead of a multi-line heredoc — avoids paste truncation on content with em-dashes/checkmarks
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-07-04 (PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---

## Session 2026-07-06 — pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write

### [2026-07-06-e23-1] (high) kb-fact → `index_to_kb`
- title: `queryDiagnosticsTables` (GraphQL) returns ALL built-in pfSense alias/table contents…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: `queryDiagnosticsTables` (GraphQL) returns ALL built-in pfSense alias/table contents inline,
- evidence: `queryDiagnosticsTables` (GraphQL) returns ALL built-in pfSense alias/table contents inline,
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write).

### [2026-07-06-e23-2] (high) kb-fact → `index_to_kb`
- title: pfSense's Config History (`Diagnostics → Backup & Restore → Config History`) logs the…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense's Config History (`Diagnostics → Backup & Restore → Config History`) logs the source of
- evidence: pfSense's Config History (`Diagnostics → Backup & Restore → Config History`) logs the source of
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write).

### [2026-07-06-e23-3] (high) kb-fact → `index_to_kb`
- title: pfSense's Unbound resolver in "forwarding" mode uses System DNS Server Settings
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense's Unbound resolver in "forwarding" mode uses System DNS Server Settings
- evidence: pfSense's Unbound resolver in "forwarding" mode uses System DNS Server Settings
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write).

### [2026-07-06-e23-4] (high) kb-fact → `index_to_kb`
- title: pfSense REST API read-only mode is a one-way lock via API: can be re-enabled…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: pfSense REST API read-only mode is a one-way lock via API: can be re-enabled programmatically
- evidence: pfSense REST API read-only mode is a one-way lock via API: can be re-enabled programmatically
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write).

### [2026-07-06-e23-5] (medium) skill-candidate → `skill_record`
- task: a content-based regex guard targeting known-bad query shapes can never cover this class…
- occupation: network-engineer | provenance: debrief-backfill-2026-07-06
- procedure: a content-based regex guard targeting known-bad query shapes can never cover this class
  of bug (there's no way to enumerate every huge built-in table in advance) — the only fix that
  generalizes is a response-size cap on every `pfsense_graphql` call, applied uniformly regardless
  of which field/table produced the size.
- **Attempted:** local agent tasked with "find these two IPs in the pfSense config" (read-only intent).
  **Failed because:** it executed a real `pfsense_query` write deleting both IPs from System DNS
  Server Settings, with no explicit removal instruction and no confirmation — a direct miss of
  `pfsense_query`'s own docstring "CONFIRMATION PROTOCOL — mandatory for ALL writes." This broke
  Unbound's DNS forwarding (pfSense's own resolver stopped answering queries) until manually fixed.
  **Fix:** the confirmation rule needs to be a code-level gate (e.g. a `confirmed: bool = False`
  parameter the model must explicitly flip), not prose alone — prose was already there and didn't hold.
- verification: **Failed because:** it executed a real `pfsense_query` write deleting both IPs from System DNS
  Server Settings, with no explicit removal instruction and no confirmation — a direct miss of
  `pfsense_query`'s own docstring "CONFIRMATION PROTOCOL — mandatory for ALL writes." This broke
  Unbound's DNS forwarding (pfSense's own resolver stopped answering queries) until manually fixed.
- why: Corrected value/command from a What-failed-and-why block. From session 2026-07-06 (pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write).

---

## Session 2026-07-06 — pfSense Phase 2 extraction: docstring drift and a same-day regression

### [2026-07-06-e24-1] (high) kb-fact → `index_to_kb`
- title: Real venv for goethe/MCP work: `/home/sy5/owui/bin/python3` (has pydantic, requests, etc).
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: Real venv for goethe/MCP work: `/home/sy5/owui/bin/python3` (has pydantic, requests, etc).
- evidence: Real venv for goethe/MCP work: `/home/sy5/owui/bin/python3` (has pydantic, requests, etc).
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense Phase 2 extraction: docstring drift and a same-day regression).

### [2026-07-06-e24-2] (high) kb-fact → `index_to_kb`
- title: `--also` modules registered by `goethe_mcp.py` are separate `Tools()` instances from
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: `--also` modules registered by `goethe_mcp.py` are separate `Tools()` instances from
- evidence: `--also` modules registered by `goethe_mcp.py` are separate `Tools()` instances from
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense Phase 2 extraction: docstring drift and a same-day regression).

### [2026-07-06-e24-3] (high) kb-fact → `index_to_kb`
- title: The entire `lse/` directory is gitignored (`.gitignore:29: lse/`) —…
- topic: pfsense | source_tier: ground_truth | quality_score: 0.85
- content: The entire `lse/` directory is gitignored (`.gitignore:29: lse/`) — `lse/skills/vault/tools.py`
- evidence: The entire `lse/` directory is gitignored (`.gitignore:29: lse/`) — `lse/skills/vault/tools.py`
- why: Key facts bullet — template already writes these as standalone atomic facts. From session 2026-07-06 (pfSense Phase 2 extraction: docstring drift and a same-day regression).

### [2026-07-06-e24-4] (medium) skill-candidate → `skill_record`
- task: **Attempted (found, not caused this session):** `pfsense_query`'s inline docstring…
- occupation: network-engineer | provenance: debrief-backfill-2026-07-06
- procedure: **Attempted (found, not caused this session):** `pfsense_query`'s inline docstring example
  used `src`/`dst`/`dstport` and a lowercase bare `interface` string.
  **Failed because:** this skill's own KB doc (`pfsense-firewall-rules-api.md`) had documented a
  v2.8.0+ breaking schema change since 2026-06-27 — `source`/`destination`/`destination_port`,
  `interface` as an uppercase array — but the docstring the model actually reads was never
  updated to match. The KB being correct doesn't mean the thing the model copies from is.
  **Fix:** corrected the inline example to the current schema; added a `FIELD NAMES` callout in
  the docstring itself so the correction can't silently drift again unnoticed.
- **Attempted (found, not caused this session):** extracting `pfsense_query` into a separate
  module/instance without checking internal callers first.
  **Failed because:** `wake_node()` called `self.pfsense_query(...)` with no `confirmed=True` —
  meaning the confirmed-gate commit from *earlier the same day* (64a3376) had already silently
  broken WoL node-wake before this extraction even started (every call returned an unconfirmed-
  write error). Extraction would have turned that into an unhandled `AttributeError` instead,
  since `--also` modules are separate `Tools()` instances — one instance cannot call a method
  living on another.
  **Fix:** decoupled `wake_node` entirely — it now makes its own minimal direct pfSense POST
  instead of calling into the pfsense skill's `pfsense_query`. `goethe.py` keeps its own
  `PFSENSE_URL`/`PFSENSE_API_KEY`/`PFSENSE_CA_CERT` valves for this one purpose (vault's
  extraction removed `BW_*` entirely because nothing internal depended on it — pfsense couldn't
  do the same).
- verification: **Failed because:** `wake_node()` called `self.pfsense_query(...)` with no `confirmed=True` —
  meaning the confirmed-gate commit from *earlier the same day* (64a3376) had already silently
  broken WoL node-wake before this extraction even started (every call returned an unconfirmed-
  write error).
- why: Corrected value/command from a What-failed-and-why block. From session 2026-07-06 (pfSense Phase 2 extraction: docstring drift and a same-day regression).

### [2026-07-06-e24-5] (low) skill-candidate → `skill_record`
- task: `goethe_mcp.py --list --also <file>` as a zero-risk dry run for `--also` wiring changes —
- occupation: network-engineer | provenance: debrief-backfill-2026-07-06
- procedure: `goethe_mcp.py --list --also <file>` as a zero-risk dry run for `--also` wiring changes —
- verification: Not separately captured in the original debrief entry — verify by re-applying and confirming expected behavior before trusting this skill record.
- why: Reads as a multi-step reusable procedure, not a single fact. From session 2026-07-06 (pfSense Phase 2 extraction: docstring drift and a same-day regression). NEEDS TIGHTENING: no explicit verify step found in the source text — confirm/rewrite verification before approving.

---
