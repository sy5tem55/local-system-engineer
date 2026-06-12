# LSE Session Learnings

Cumulative KB entries from post-session debriefs.

## Session 2026-06-07 — Qwen 3.6 cross-file invariant failures in net-discovery

### What worked
- Rewriting `echarts_topology.py` in one complete heredoc pass (no Edit tool) avoids truncation on NTFS
- Verifying topology output with `curl -s http://localhost:8766/topology | python3 -m json.tool | head -40` before pushing to Grafana
- Running `python3 push_topology_dashboard.py --pass LSEgrafana2026` as a push gate — if the script errors, Grafana is untouched
- Restoring a truncated snapshot: `cp history/snapshot_YYYYMMDDTHHMMSSZ.json snapshot.json`

### What failed and why

- **Attempted:** LSE (Qwen 3.6) wrote `echarts_topology.py` autonomously
  **Failed because:** Model lost track of cross-file invariants — used wrong IPs (pfSense as `192.168.1.1` instead of `192.168.1.50`), omitted tier edges entirely (ASUS/Netgear/RUTX50 floated as islands), routed subnet clients to pfSense directly instead of their tier-2 parent. Required 3 full correction passes.
  **Fix:** Human-verified the correct IPs from live snapshot first, then rewrote with explicit `TIER_NODES`, `TIER_EDGES`, `SUBNET_PARENT` dicts. Never let LSE infer IPs from training knowledge — always read them from `snapshot.json`.

- **Attempted:** LSE used Edit tool on `probe_wifi.py` (>100 lines, NTFS)
  **Failed because:** Edit tool truncates large Python files on NTFS — last lines reduced to a single `l` character. File was silently corrupt; no write error was reported.
  **Fix:** For any `.py` file >100 lines on NTFS, always use `bash cat << 'PYEOF' ... PYEOF` heredoc. Never use Edit tool on large Python files.

- **Attempted:** `docker compose up -d prometheus` to restart stopped Prometheus
  **Failed because:** Container `/prometheus` already existed (just stopped). `docker compose up` tries to create a new container → name conflict error.
  **Fix:** `docker start prometheus` — restarts the existing stopped container without naming conflict.

- **Attempted:** Grafana auth using `GF_ADMIN_PASSWORD` value from `docker inspect`
  **Failed because:** The real Grafana env var is `GF_SECURITY_ADMIN_PASSWORD`, and it is only applied on first boot. `docker inspect` showed a stale/wrong env var name (`GF_ADMIN_PASSWORD`) that Grafana never reads after init.
  **Fix:** Retrieve password from Vaultwarden (`Grafana_ADMIN_PASSWORD`). To rotate: `curl -s -u admin:OLDPASS -X PUT http://localhost:3002/api/user/password -H 'Content-Type: application/json' -d '{"oldPassword":"OLD","newPassword":"NEW","confirmNew":"NEW"}'`

- **Attempted:** Deleting `.git/index.lock` from Cowork sandbox
  **Failed because:** Sandbox cannot delete NTFS lock files — permission denied even with `rm -f`.
  **Fix:** User must run `rm -f .git/index.lock` from WSL terminal before any git operation from the sandbox.

### Key facts
- pfSense LAN IP: `192.168.1.50` — NOT `192.168.1.1` (that's the ASUS AP management IP)
- pfSense OPT1: `192.168.5.1`, OPT2: `192.168.10.1`; ASUS: `192.168.1.1`; Netgear: `192.168.5.2`; RUTX50: `192.168.5.3`
- Grafana port: `3002` (host). Topology API: `8766`. llama-server: `8080`. SearxNG: `8088`.
- Grafana admin password in Vaultwarden as `Grafana_ADMIN_PASSWORD` (value: `LSEgrafana2026`)
- Edit tool + NTFS + large Python files = silent truncation. Use heredoc.
- Git commits must be run from WSL — sandbox git operations may fail silently or with lock errors
- Qwen 3.6 strength: isolated single-function rewrites. Weakness: multi-file invariants (IPs, port mappings, cross-file constants). Always provide a canonical facts block in the prompt before asking LSE to touch topology/config files.
- Dashboard backup: `python3 backup_grafana_dashboards.py` → `grafana-dashboards/*.json`

## Session 2026-06-07 — llama-server --flash-attn arg parsing + Edit tool NTFS truncation

### What failed and why

- **Attempted:** Multi-line SSH command with backslash continuation, `--flash-attn \` followed by `--cache-type-k q8_0 \` on next line
  **Failed because:** llama-server's arg parser greedily consumed `--cache-type-k` as the value for `--flash-attn` (its signature is `[on|off|auto]`). Backslash-continuation inside a double-quoted SSH heredoc does not protect against this.
  **Fix:** Collapse the entire llama-server launch to a single line. Use short flags: `-c` (ctx), `-ngl` (gpu layers), `-t` (threads), `-tb` (threads-batch), `--flash-attn` (no value needed — defaults to auto).

- **Attempted:** Edit tool to patch lse_agent.py (422 lines on NTFS)
  **Failed because:** Edit tool silently truncated the file at a multi-byte emoji character (🔄, U+1F504). File ended mid-f-string with `{a` — no write error reported.
  **Fix:** Use bash Python string replacement for ALL .py edits > 100 lines on NTFS:
  ```python
  with open(path) as f: src = f.read()
  src = src.replace(old, new, 1)
  with open(path, "w") as f: f.write(src)
  import ast; ast.parse(src)  # verify syntax
  ```

### Key facts
- `--flash-attn` must not be followed by another `--flag` on the next line in a multi-line SSH command — collapse to single line
- Verified working llama-server command for node3090: `llama-server -m /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf -c 96000 -ngl 129 --flash-attn --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 -t 7 -tb 7 --reasoning-budget 3072 --n-predict 8192 --jinja --metrics --port 8080 --host 0.0.0.0`
- Edit tool + NTFS + emoji in f-strings = silent mid-character truncation (not just end-of-file)

## Session 2026-06-07 — Qwen3.6 reasoning_content field + lse_task.sh double-http

### What failed and why

- **Attempted:** `curl -sf "http://${LLM_URL}/health"` in lse_task.sh where `LLM_URL="http://node3090.home.arpa:8080"`
  **Failed because:** Double `http://` — `LLM_URL` already contained the scheme, so the final URL was `http://http://node3090.home.arpa:8080/health`. curl fails silently with `-sf`. Misdiagnosed as a WSL2 TCP/hostname issue for several rounds (ping and nslookup worked, only curl "failed").
  **Fix:** `curl -sf "${LLM_URL}/health"` — no extra `http://` prefix. When `LLM_URL` already contains the scheme, never wrap it again.

- **Attempted:** `reasoning_budget: 0` in chat completions payload to disable Qwen3.6 thinking
  **Failed because:** `reasoning_budget: 0` zeroes the content-generation budget (tokens after thinking), not the thinking budget. Model thought for ~1100 tokens, then had 0 tokens to produce content → `content` field was empty.
  **Fix:** Remove `reasoning_budget` entirely. Use `chat_template_kwargs: {"enable_thinking": False}` to disable thinking at the template level.

- **Attempted:** Reading `resp["choices"][0]["message"]["content"]` for Qwen3.6 with thinking enabled
  **Failed because:** llama.cpp with Qwen3.6 reasoning mode routes the think block to `reasoning_content` and leaves `content` as empty string. Standard OpenAI client code returns `""`.
  **Fix:** `content = msg.get("content") or ""; content = content or msg.get("reasoning_content", "")` — fall back to `reasoning_content` when `content` is blank.

### Key facts
- Qwen3.6 + llama.cpp: thinking output → `reasoning_content`; actual answer → `content` (may be empty if model hits token limit or `reasoning_budget` is misset)
- `reasoning_budget: 0` = 0 content tokens (counterintuitive — sounds like "no reasoning")
- Correct way to disable thinking per-request: `"chat_template_kwargs": {"enable_thinking": False}` in the completions payload
- `/no_think` in user message is NOT reliable with llama.cpp — model still enters thinking mode
- `LLM_URL` pattern: if it already contains `http://`, never wrap it with `http://` again in curl
- node3090 HTTP reachable at `192.168.5.41:8080` from WSL2 (IP). Hostname `node3090.home.arpa` also works for ping/SSH but use IP for curl to avoid any DNS edge cases.

## Session 2026-06-08 — WSL2 unclean shutdown → Docker overlay2 corruption

### What failed and why

- **Attempted:** `docker start <containers>` after WSL2 restarted
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

- **Attempted:** `sudo dockerd &` then immediate `docker ps`
  **Failed because:** daemon needs ~3-5 seconds to create `/var/run/docker.sock` before clients can connect. Always `sleep 5` after starting.

- **Attempted:** `sudo nohup dockerd > /var/log/dockerd.log 2>&1 &` as non-root
  **Failed because:** `/var/log/` is root-only. Use `/tmp/dockerd.log` or run from a root shell.

- **Attempted:** `docker compose up -d --pull never` on corrupted storage
  **Failed because:** `--pull never` prevents registry pulls but does NOT prevent rebuilding custom images from Dockerfiles. Custom image builds still fail if overlay2 snapshots are corrupted. Use `docker container prune -f` + `docker system prune -f` first, then `docker compose up -d`.

- **resolv.conf reset on WSL2 restart**
  **Cause:** Windows hibernate/reboot causes WSL2 to fully restart. If `/etc/wsl.conf` has `generateResolvConf = false` but the wsl.conf itself was not persisted (NTFS write issue), WSL2 regenerates resolv.conf with just `nameserver [::1]` (broken for Docker and bare hostnames).
  **Fix:** Restore resolv.conf manually:
  ```bash
  echo -e "nameserver 10.255.255.254\nnameserver 192.168.1.50\nsearch home.arpa" | tee /etc/resolv.conf
  ```
  Then verify wsl.conf is intact: `cat /etc/wsl.conf` — should contain `generateResolvConf = false`.

### Key facts
- Docker overlay2 corruption = unclean dockerd kill. Signature: `RWLayer unexpectedly nil` on `docker start`.
- Recovery order: start dockerd → prune containers → prune system → compose up.
- Never `docker start` after overlay2 corruption — always prune first or you'll get cascading errors.
- `docker ps` failing with socket error = dockerd not running, not a permissions issue.
- Data safety: grafana, vaultwarden, elasticsearch, prometheus all bind-mount data to host dirs — `docker container prune` never touches data.
- `/tmp/dockerd.log` is always writable; `/var/log/dockerd.log` requires root and correct permissions.

## Session 2026-06-08 — WSL2 restart kills host-side exporters / Grafana "no data"

### What failed and why

- **Observed:** Grafana dashboards showed "No data" after Docker full reset + WSL2 restart.
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

- **Attempted:** `curl -s http://localhost:9101/metrics` to check netobs exporter
  **Hung:** The netobs exporter is on port **9120**, not 9101. Port 9101 had a half-open TCP
  connection from a previous session. `curl -s` without `--max-time` blocks forever.
  **Fix:** Always use `curl -s --max-time 3` for health checks. Know the correct ports (see KB
  port map below).

### What is safe across a full Docker reset

| Data | Storage | Safe after `docker rm`? | Safe after `/var/lib/docker` delete? |
|---|---|---|---|
| Grafana dashboards + users | `./grafana/data/grafana.db` (bind) | YES | YES |
| Prometheus TSDB (metrics history) | `./prometheus/data/` (bind) | YES | YES |
| Elasticsearch indices | `es-data` (named Docker volume) | YES | **NO — recreate volume** |
| Vaultwarden vault | `./vaultwarden/data/` (bind) | YES | YES |

### Key facts
- Host-side exporter ports: topology API 8766, netobs 9120, nvidia_gpu 9835, llama-context 9836,
  download-speed 9838, llamacpp-slots 9839. All killed by WSL2 restart.
- Recovery: `bash scripts/restart_exporters.sh` — starts all host exporters and topology API.
- The Prometheus curl check above uses `172.17.0.1` (Docker bridge → host). If the error says
  "connection refused" on that IP, the process is not running on the host. If it says "timeout",
  the process is running but not responding (check the exporter log).
- Grafana topology dashboard (`uid: net-topology`) fetches directly from port 8766 via sync XHR
  in the panel's getOption function — no Prometheus or Infinity datasource needed.
- Full troubleshooting decision tree: `docs/troubleshooting.md`

## Session 2026-06-11 — Hermes Agent config v0→v27 + llama-server on node3090

### What worked
- System-level systemd service for Hermes gateway:
  `/etc/systemd/system/hermes-gateway.service` with `User=hermes-admin`,
  `Environment=HOME=/home/hermes-admin`, `Environment=XDG_RUNTIME_DIR=/run/user/<UID>`.
  Disable auto-start: `systemctl disable hermes-gateway`. Start on demand: `systemctl start hermes-gateway`.
- Direct llama-server start: `nohup /usr/local/bin/llama-server --model <path> --flash-attn on ... &`
- Hermes ping/pong test: `curl -s http://127.0.0.1:8642/v1/chat/completions` with `/no_think` suffix in user message content.

### What failed and why

- **Attempted:** `provider: llamacpp` + `provider_custom:` (dict) in config.yaml
  **Failed because:** `provider_custom:` is a v0-format dict; Hermes v0.16.0 uses config schema v27 where this section must be a list named `custom_providers:`. With `provider: llamacpp`, the gateway runs ("Custom endpoint") but every chat request returns "No LLM provider configured".
  **Fix:** Set `provider: custom` (not `llamacpp` or `openai`) + replace `provider_custom:` dict with `custom_providers:` list:
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

- **Attempted:** Running `hermes config migrate` to fix config version
  **Failed because:** This command is interactive and rewrites config.yaml during the API-key-collection wizard — it can overwrite manual edits made before or after it runs.
  **Fix:** Always write config.yaml via `tee` or Python AFTER `hermes config migrate` completes. Verify with `cat` before starting gateway.

- **Attempted:** `--flash-attn` as a boolean flag (no argument)
  **Failed because:** llama-server b1-6b80c74 requires an explicit value: `--flash-attn on|off|auto`. Passing it without a value causes: `error: unknown value for --flash-attn: '--cache-type-k'`.
  **Fix:** Always use `--flash-attn on` (not bare `--flash-attn`).

- **Attempted:** Running Hermes gateway as root (workaround for systemd bus issue)
  **Failed later because:** Root-owned `gateway.lock` prevents hermes-admin from starting the gateway subsequently. Symptom: `PermissionError: [Errno 13] Permission denied: '/home/hermes-admin/.hermes/gateway.lock'`.
  **Fix:** `chown -R hermes-admin:hermes-admin /home/hermes-admin/.hermes/`

### Key facts
- Hermes config version: v27 (as of v0.16.0). Check with `hermes config check` → "Config version: 27 ✓".
- Valid provider name: `custom` — NOT `openai`, NOT `llamacpp`.
- `custom_providers:` must be a YAML list (items start with `-`), NOT a dict.
- llama-server binary: `/usr/local/bin/llama-server` (b1-6b80c74)
- Model path: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- Hermes API port: 8642 (`.env` says 8644 but server binds 8642 — always verify with `ss -tlnp | grep 864`).
- Hermes API key: in `/home/hermes-admin/.hermes/.env` under `API_SERVER_KEY=` (requires root to read).
- Disable thinking (llama.cpp direct API): `chat_template_kwargs: {"enable_thinking": false}`.
- Disable thinking (Hermes API): append `/no_think` to user message content.
- Performance: ~131 tok/s prompt, ~40 tok/s generation on RTX 3090.
- Startup scripts on node3090: `/opt/local-se/scripts/start-llama-server.sh`, `start-hermes-gateway.sh`.

## Session 2026-06-11 — pkill -f self-match killed SSH session and backend

### What worked
- Bracket-escaping the pkill pattern in an SSH one-liner: `pkill -f "[l]lama-server"` — the regex can't match its own command line
- Recovery order from Restart _Hermes.md held: VRAM verified ~0 → canonical launch → /health poll → reset-failed → gateway start. Both hermes-gateway and hermes-socat active.

### What failed and why
- **Attempted:** `ssh lse-admin@192.168.5.41 'pkill -f llama-server; ...nvidia-smi...; tail ...'`
  **Failed because:** `pkill -f` matched the remote shell's own command line (it contains the literal string "llama-server"), killing the SSH session before any output printed — and also killing a likely-healthy llama-server. Symptom: command "loops back to empty shell" instantly. Log showed graceful "cleaning up before exit", not OOM.
  **Fix:** `pkill -f "[l]lama-server"` — bracket class prevents self-match. Restart _Hermes.md step 1 patched accordingly.

### Key facts
- An instant return with zero output from an SSH one-liner containing pkill -f = self-match, not a connection problem
- Diagnostic discriminator: instant return = remote command never completed; ~8s return = ran but silent
- Cowork sandbox cannot reach 192.168.x.x at all (proxy returns 403 blocked-by-allowlist for HTTP, port 22 unreachable) — all node3090 ops go through the user's WSL terminal
- node3090 idle VRAM ≈ 18 MiB; READY can be near-instant when model is in page cache

## Session 2026-06-12 — Model store migration, operator race, silent ES index loss

### What worked
- Same-fs `mv` of model files under a running llama-server = zero downtime (server holds the inode via mmap). Verify first: `stat -c "dev=%d"` on both paths.
- `chattr +i` while files are being sha256'd — immutable blocks writes/unlink, not reads.
- ONE launch definition: runbook step 2 now calls /opt/local-se/scripts/start-llama-server.sh (script and runbook had silently forked: missing --cache-type-v/--parallel, threads 8 vs 7/7, log path).
- Hermes memory installs via Hermes's own memory tool (call_hermes task) — never hand-edit .hermes/memories/USER.md (agent-managed, locked).
- Empirical usage check before investing: `grep -c search_rfc agent_commands.log` → 0/44,637 → skipped hours of Ollama tagging for a feature nothing calls (search_rfc wired in the tool since v1.5.18 but never triggered — a docstring/prompt problem, not plumbing).
- Flag bench (scripts/node3090-flag-bench.sh): ub 512→2048 buys only +5% pp (1323→1391 t/s @9k tok), tg flat 38 t/s, +508MB VRAM → canonical stays 512/2048. Question closed with data.
- KB consolidation: /opt/local-se/kb is now a symlink → repo kb/ (one real copy, git-versioned, Cowork-editable). Old copy preserved at /opt/local-se/kb.pre-link.bak.

### What failed and why
- **Attempted:** Claude-guided WSL restart while LSE autonomously ran its own restart
  **Failed because:** Two operators, one stack — pkill killed LSE's fresh server; full stack down.
  **Fix:** ONE operator at a time. Recover from ground-truth survey, never from agent self-reports (Hermes echoed LSE's stale PID 43871; real PID was 44564; at one point nothing ran at all).
- **Attempted:** `sudo ls /path/*.json` (glob in non-root shell)
  **Failed because:** glob expands before sudo → literal "No such file".
  **Fix:** `sudo bash -c 'ls /path/*.json'`.
- **Attempted:** record_error() → 404 on lse-errors
  **Failed because:** es-data Docker volume was lost in the 2026-06-08 WSL cascade; only lse-kb was reseeded. Missing ES indices are SILENT until first read (ES auto-creates on write, 404s on search).
  **Fix:** `rag/02-es-setup.py` (idempotent, canonical mappings — never freehand-create indices). Add index-existence probe to stack health check: `curl -s localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache/_count`
- **Attempted:** Cowork mounting WSL paths (\\wsl.localhost\...)
  **Failed because:** "UNC paths are not supported" — product-level, both folder mount and sandbox bash.
  **Fix:** Invert the alias: real files on /mnt/c (NTFS, git), WSL-side symlink for Linux consumers.

### Key facts
- /opt/models on node3090: REAL dir, 18 .gguf chattr +i, hashes in /opt/models/SHA256SUMS + kb/node3090-model-sha256sums.md
- Canonical launch: /opt/local-se/scripts/start-llama-server.sh (ctx 81920 — SY5 decision; q8_0 KV both; threads 7/7; ub/b 512/2048 — benched; log /home/lse-admin/llama-server.log)
- node3090 perf @9k uncached: pp ~1323 t/s, tg ~38 t/s (RTX 3090, Q4_K_M, b9577)
- agent_commands.log is at /opt/local-se/ (NOT /opt/local-se/logs/)
- rfc_kb.py upserts by deterministic section_id — re-runs idempotent; --tag-only resumes (fills empty tags only); --no-tag still embeds (kNN works untagged)
- lse-rfc-kb: 628 chunks / 13 RFCs / all tagged — production-ready; yellow = single-node replica cosmetics
- 03-kb-seed.py skips existing doc ids — updated files need --reindex
- LSE execute_command timeout = 30s and /opt/ writes are safety-blocked — long/privileged jobs run from WSL
- lse-kb.sqlite is vestigial (0 bytes, no code references it — tool v1.6.4's only sqlite is the OWUI chat DB)
- ~/projects/local-system-engineer is a SYMLINK → /mnt/c repo (since Jun 7) — one real repo, not two clones. `diff -rq` empty + exit 0 between "two" paths = check `readlink -f` first.
- A failed WSL UNC mount attempt poisons the Cowork sandbox shell for the whole session (every bash call errors "UNC paths are not supported") — file tools keep working; restart session to recover bash.

## Session 2026-06-08 — pfSense log gateway context overflow + parser fixes

### What worked
- Gateway architecture: local HTTP proxy on :9191 aggregates pfSense logs server-side
  before LSE sees them. /compact endpoint returns <4KB regardless of log volume.
- Key resolution order for gateway: env PFSENSE_API_KEY → /opt/local-se/.lse/secrets → valve fallback
- pfsense-gateway-tools.sh restart passes PFSENSE_API_KEY via env to nohup subprocess

### What failed and why

- **Attempted:** `pfsense_log_summary` calling `pfsense_query('/api/v2/status/logs/firewall')` internally
  **Failed because:** pfsense_query fetches raw log JSON before any aggregation — pfSense
  returns up to 2.7M tokens which overflows the 96k context window mid-response
  **Fix:** Rewrite pfsense_log_summary to call http://localhost:9191/compact instead.
  The gateway does aggregation server-side. Context cost: <4KB.

- **Attempted:** pfsense-gateway-tools.sh sourced in .bashrc; API key error printed on every terminal open
  **Failed because:** PFSENSE_API_KEY absence check was at top-level scope, outside the
  `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` guard — fires on source, not just direct execution
  **Fix:** Move key check inside gateway_ensure_running() with return 1 on missing key.
  Sourcing is now always silent.

- **Attempted:** filterlog CSV parser using hardcoded field indices for all entries
  **Failed because:** pfSense filterlog CSV has different field positions for IPv4 vs IPv6.
  IPv4: src_ip=fields[18], dst_ip=fields[19], src_port=fields[20], dst_port=fields[21], proto=fields[16]
  IPv6: src_ip=fields[15], dst_ip=fields[16], src_port=fields[17], dst_port=fields[18], proto=fields[12]
  Parser was using fields[12]/[13] for ports (IPv4 id/offset fields) — "RTALERT" and "5353"
  appeared as source IPs; "ff02::fb" appeared as destination port
  **Fix:** Branch on fields[8] (ip_version). Add sanity check: discard entries where source
  does not match r'^[\d.a-fA-F:]+$'

- **Attempted:** pfsense_query docstring lists /api/v2/status/logs/firewall as a "common endpoint"
  **Failed because:** No prohibition — model treated it as a valid call for log analysis,
  bypassing pfsense_log_summary entirely
  **Fix:** Add LOG ENDPOINT PROHIBITION block to pfsense_query docstring explicitly naming
  the endpoint and calling direct calls a protocol violation.

### Key facts
- pfSense REST API returns version as nested dict: {"version": "2.7.x", "base": "FreeBSD..."}
  not a string. Use: v = d.get("version"); pf_version = v.get("version", str(v)) if isinstance(v, dict) else str(v)
- pfSense only logs blocked/rejected packets by default. Zero pass_count in gateway
  output is normal — not a parser bug. Pass logging requires explicit per-rule config.
- Gateway paths: script=/opt/local-se/pfsense-gateway-tools.sh, py=/opt/local-se/pfsense_log_gateway.py
- Secrets file: /opt/local-se/.lse/secrets — line format: PFSENSE_API_KEY=<key> (no quotes needed)
- Gateway port: 9191. Audit endpoint: GET /compact?hours=24 (use for reports, not /summary)
- Edit tool with replace_all=true on large NTFS Python files truncates the file tail.
  Fix: append missing tail with cat >> file << 'EOF'. Strip nulls after any cp on NTFS:
  python3 -c "d=open(f,'rb').read(); open(f,'wb').write(d.replace(b'\x00',b''))"
- Tool version: openwebui-tool-v1.5.28.py — pfsense_log gateway rewrite + LOG ENDPOINT PROHIBITION

## Session 2026-06-09 — pfsense-agent _extract_prompt + OWUI API gap

### What worked
- Anchoring on the LAST DO NOT block via `rfind` to find where the final clean output starts
- Walking backwards through step_matches to find the start of the last CONTIGUOUS ASCENDING SEQUENCE (handles thinking traces with multiple draft Step N: sequences)
- Assistant prefill `{"role":"assistant","content":"Step 1: "}` forces --no-think output to start at Step 1 with zero preamble
- Writing large Python files via `cat > /tmp/file.py << 'PYEOF'` heredoc + `python3 -c "import ast; ast.parse(...)"` syntax check + `cp` to workspace

### What failed and why
- **Attempted:** `re.finditer(r"(?m)^\s*Step \d+:", text)` for step detection in multiline mode
  **Failed because:** `^` + `\s*` in multiline mode — `^` anchors at start of the preceding blank line's `\n`, and `\s*` matches `\n       ` (newline + spaces). `match.start()` lands on the `\n`, not the first space of the Step line. After slicing, `splitlines()[0]` is `''`, `indent=0`, dedent is a no-op.
  **Fix:** Replace ALL `^\s*` with `^[ \t]*` in step-matching regexes. Spaces and tabs only — never newlines.
  Confirm the bug: `re.search(r"(?m)^\s*Step \d+:", "foo\n\n       Step 2: bar").start()` → 4 (the \n, not 6)

- **Attempted:** Using `rfind` on DO NOT anchor + `step_matches[-1]` (last step match only)
  **Failed because:** Found Step 6 (last step in last group) but missed Steps 2-5 before it in the same final output block.
  **Fix:** Walk backwards from step_matches[-1] looking for contiguous descending sequence; use group_start_idx as real start.

- **Attempted:** Edit tool to patch pfsense-agent.py (331 lines) on NTFS
  **Failed because:** Edit tool silently truncates large Python files on NTFS at ~2600-3000 chars — no error, file written but incomplete.
  **Fix:** Always use `cat > /tmp/file.py << 'PYEOF'` heredoc for ANY .py file >100 lines. Never use Edit tool on large Python files in the Windows-mounted workspace.

- **Attempted:** OpenWebUI /api/chat/completions with tool_ids to trigger LSE tool execution
  **Failed because:** Local Qwen3.6 generates reasoning text about which tools to call — does NOT emit OpenAI-style tool_calls JSON. OWUI agentic loop only fires on structured FC JSON. Chat UI uses a ReAct text-based pattern that the API path does not share.
  **Decision:** Adopted Dify for multi-agent UI. OWUI pipe function deferred.

### Key facts
- `^[ \t]*` not `^\s*` — in multiline Python regex, `\s*` swallows the preceding newline
- NTFS + Edit tool truncates Python files >100 lines silently — use heredoc always
- OWUI API tool_ids field exists (found in middleware.py) but requires native FC JSON from model — local Qwen3.6 does not emit this
- pfSense auth header: X-API-Key: <key> — NOT Authorization: Bearer <key>
- Vaultwarden tools: pass via tool_ids only when needed — not default-enabled (security boundary)
- pfsense-agent.py: --think -> max_tokens=4096, no prefill; --no-think -> max_tokens=2048, prefill applied
- DO NOT sentinels: FIRST="DO NOT: query __schema or __type (context bomb -- crashes session)", LAST="DO NOT: guess placement index -- read-first always"
- Dify deploy: git clone https://github.com/langgenius/dify && cd dify/docker && cp .env.example .env && docker compose up -d

## Session 2026-06-11 — Hermes recovery + LSE stale search_kb cache

### What worked
- `sudo systemctl restart hermes-gateway` recovers both gateway and socat in one
  command — hermes-socat.service has `Requires=hermes-gateway.service`, shares
  same start timestamp
- Forcing LSE to verify KB via SSH: add `execute_command('ssh lse-admin@192.168.5.41
  "cat /opt/local-se/kb/node3090-llama-launch.md | grep model"')` explicitly in task
  prompt — more reliable than read_file or search_kb for critical path values
- node-t3-004 "already compliant" path: SOLVED 4/4 in 62s, KB assist, episode #31, 20.8 pts

### What failed and why
- **Attempted:** LSE `read_file('/opt/local-se/kb/node3090-llama-launch.md')` during live task
  **Failed because:** LSE returned stale in-context cached content — reported model path as
  `/opt/models/...` even though file on disk had `/home/sy5/.lmstudio/models/...`. Both
  `search_kb` and `read_file` can anchor on context-window cache rather than reading disk.
  **Fix:** Add explicit SSH verification step to task prompt. Never trust LSE-reported file
  contents for critical values — verify via `ssh ... cat <file>`.

- **Attempted:** `sudo -u hermes-admin python3 -m pip install --upgrade hermes-agent`
  **Failed because:** Ubuntu 24.04 PEP 668 externally-managed-environment. No pip binary
  in `/home/hermes-admin/.local/bin/`.
  **Fix (if upgrade needed):** Check `sudo -u hermes-admin pipx list` first. If not pipx,
  upgrade via: `sudo -u hermes-admin python3 -m pip install --upgrade hermes-agent
  --break-system-packages` (safe — targets hermes-admin ~/.local only).

### Key facts
- Hermes gateway binary: `/home/hermes-admin/.local/bin/hermes`
- Service ExecStart: `/home/hermes-admin/.local/bin/hermes gateway run --replace`
- socat: 0.0.0.0:8643 → 127.0.0.1:8642 (hermes-socat.service, co-starts with gateway)
- Recovery after gateway crash: `sudo systemctl restart hermes-gateway` on node3090
- node3090 canonical model: `/home/sy5/.lmstudio/models/lmstudio-community/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf`
- node3090 canonical ctx-size: 81920 (updated from 96000 this session in KB)
- run_episode.py is NOT in /opt/local-se/ — correct path:
  `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/run_episode.py`
  Run from LUCIFER as: `python3 /mnt/c/.../scripts/run_episode.py --challenge <id>`
- Duplicate model files on node3090 disk (80% full): `/opt/models/...` (stale copy)
  vs canonical `/home/sy5/.lmstudio/models/...`. Cleanup planned as node-t3-005.
- hermes-agent 0.16.0 is already latest — /status malformed issue self-resolved on restart

## Session 2026-06-11 — P20: episodes don't execute commands; perms; Hermes unit

### What worked
- Root-causing via the audit log: every LSE tool call lands in /opt/local-se/agent_commands.log
  (CMD:/BLOCKED:/SUDO-DELEGATE:) — absence of episode commands there proved the harness gap
- Structural permission fix instead of escalation: sudo usermod -aG sy5 lse-admin
  → group write on /opt/models (drwxrwxr-x sy5:sy5), plain rm works, no sudo needed
- Ground-truth reading of harness source before burning a 4th episode

### What failed and why
- **Attempted:** node-t3-005 episode (duplicate GGUF deletion) — 4 runs, identical 2/4
  **Failed because:** run_episode.py calls llama-server DIRECTLY (bare /v1/chat/completions,
  no tools); lse_challenge_env.step() only parses the model's JSON and runs verify_ssh.
  Model-emitted commands are NEVER executed — there is no actuation path. verify_ssh
  overrides self-report, so write-mode challenges pass only if the world is already in the
  target state. Model output, temperature, thinking mode were all irrelevant to the outcome.
  **Fix:** Short-term: perform write tasks via interactive LSE chat (OWUI ReAct path),
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

### Key facts
- Episode harness = EVALUATOR ONLY. Arena "solved" on write challenges measures world state,
  not model capability. t3-004 was actually fixed by the interactive LSE session (19:27/19:33).
- Episode #35: model emitted NATIVE tool_calls JSON ({'tool_calls': '[2 items]'}) — harness
  silently discards them. Actuation layer (1.7.0-a) can parse these directly.
- agent_commands.log only records OWUI tool calls — episodes never appear in it
- /opt/models on node3090: sy5:sy5 775; lse-admin now in sy5 group (WRITE-OK verified)
- Hermes ~/.hermes/memories/ is EMPTY; SOUL.md is the reliable install point for identity
  facts — "two principals" paragraph installed 2026-06-11 (SOUL-INSTALLED)
- Hermes /status "Agent Running: No" = normal idle (agent spawns per conversation)
- EscalationWrapper auto-indexed 4 junk web-search docs at quality 0.7 during stagnation
  (episodes #32-35) — purge + gate is trajectory S0.1/S0.2

## Session 2026-06-11 — P20 addendum: model deletion incident

### What failed and why
- **Attempted:** delete the "stale duplicate" /opt/models/.../Qwen3.6-27B-Q4_K_M.gguf
  **Failed because:** /opt/models/lmstudio-community is a SYMLINK to /home/sy5/.lmstudio/models/lmstudio-community —
  the "duplicate" was ONE inode with two names. rm through the symlinked path deleted the only copy.
  Every pre-delete check (process path, sizes, health) passed because both paths were the same healthy file.
  **Fix:** restored byte-exact from HF via Hermes aria2c (sha256 33625d8d... matches HF LFS), zero downtime —
  llama-server served from VRAM throughout; controlled restart after restore.

### Key facts
- DUPLICATE-DELETE RULE: before deleting any "duplicate", run readlink -f AND stat -c '%i %h' on BOTH paths —
  proceed only if inodes differ; verify the survivor (size + sha256) BEFORE the rm, never after.
- A running llama-server pins its deleted model inode via mmap (~15GB invisible to ls, held until restart);
  /proc/PID/map_files shows it. NEVER restart a server whose model file is missing on disk.
- HF LFS reference hash: curl -s https://huggingface.co/<repo>/raw/main/<file> returns oid sha256 + size —
  the recovery checksum when no local hash was recorded.
- Hermes executed the recovery autonomously (aria2c as hermes-admin → ~/tmp_dl) — agent background jobs run
  under their own user and are invisible to other admins' pkill.
- node-t3-005 retired (false premise). Successor: node-t3-006 Model Store Reconciliation —
  real /opt/models everywhere, no symlinks, chattr +i on model files, sha256 in launch KB.
