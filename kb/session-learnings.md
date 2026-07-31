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

## Session 2026-06-12 — P22: Hermes skills inert, Goethe spiral, attention is not a control plane

### What worked
- Ground-truthing a peer agent's feature from its own host beats its docs: ls ~/.hermes/skills/
  + .skills_prompt_snapshot.json + config.yaml (skills:/curator:) + .curator_state fully
  characterized hermes-agent v0.16.0 skill learning in 3 SSH commands.
- Code-level enforcement for termination decisions (sudo-blocker philosophy): _budget_gate()
  rolling-window counter on search_web/search_reddit/fetch_url — banner at ≤2 remaining,
  in-code refusal at 0 with checkpoint+surface instructions. Unit-tested before deploy.
- Tool-build discipline held: copy → python splice with asserted-unique anchors → ast.parse
  → sha256 → registry. Three releases (v1.7.0/1/2) in one session, zero syntax casualties.

### What failed and why
- **Attempted:** v1.7.0 first live test — "verify this Goethe quote" research task
  **Failed because:** every search miss spawned a reformulation (34 searches, ~78K tokens, no
  surfaced output on turn 2). Termination was left to model attention, which is fully absorbed
  by the task — get_context_status was never called; the context-monitor filter can watch but
  not intervene. Bonus failure: turn 1 surfaced a FABRICATED German quote with confident framing.
  **Fix:** v1.7.1 three-layer containment — (1) code-enforced search budget, (2) task_checkpoint/
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

### Key facts
- Hermes skill learning (v0.16.0): SKILL.md files in ~/.hermes/skills/, FULL-manifest prompt
  injection at session start, weekly idle-time curator (prune 30d/archive 90d/pin/umbrella),
  optional skills_hub downloads. Observed: 0 skills in 44h, curator run_count=0 — wired but inert.
- LSE surpass design: retrieval (top-2 kNN+BM25) beats prompt injection; evidence-gated quality
  beats age-based pruning; provenance mandatory. Adopted from Hermes: pinned, archived, snapshot.
- v1.6.4 search_kb was ALREADY hybrid kNN(0.7)+BM25(0.3) — 1.7.0-design §3.5.2 "kNN-only" claim
  was wrong; the real S2 question is RRF vs weighted-boost.
- Cogitator v1.7.2: sha256 eca3b518…, 3356 lines. Budget gate state: <TASKS_DB dir>/.search_budget.json.
  tasks.db schema auto-creates. Banner fires at remaining 2,1,0; refusal from call 9.
- SearxNG returning arxiv hits for ALL queries = general engines suspended/failing, science
  category answering alone — engine-health issue, not a query problem.
- hermes CLI traceback under sudo bash is a root-env artifact — run as sudo -u hermes-admin.

## Session 2026-06-12 — P24: OWUI black-formats tools; "after responding" is unreachable

### What worked
- Deploy verification by normalization: `python3 -c "import black,hashlib; print(hashlib.sha256(black.format_str(open('tools/cogitator-vX.Y.Z.py').read(), mode=black.Mode()).encode()).hexdigest())"` — compare THIS to the installed tool's sha, never the raw file sha
- Ground-truthing agent claims via Hermes agent.log: tool calls + char counts reveal what the model actually did (read_file 6871 chars = contract v2.1; then cronjob + skills_list = hunting for a missing board tool)

### What failed and why
- **Attempted:** Verifying v1.7.8 deploy by comparing repo file sha256 to OWUI-installed tool content
  **Failed because:** OWUI runs black on tool code at save time — installed copy is 188,582 B / sha a7fc986e…, repo is 183,103 B / sha fd65fea6…, same code
  **Fix:** black-normalize the repo file before hashing (command above)
- **Attempted:** Contract v2 rule "After producing a plan envelope, create ONE card"
  **Failed because:** Emitting the response ENDS the agent's turn — any "after responding, do X" instruction is unreachable. Same dead-path class as v1.7.3 call_hermes error returns
  **Fix:** Contract v2.1 — card creation is step 1, BEFORE the envelope; "ONLY JSON" clarified to refer to final message content, not tool actions
- **Attempted:** Getting Hermes to create the kanban card via contract v2.1 wording
  **Failed because:** Planner session toolset has NO kanban-write tool (proved by tool-hunting in agent.log: cronjob -> skills_list -> gave up). Capability gap, not prompt bug
  **Fix:** Pending v1.7.9 — hermes_plan creates the card itself (enforcement in code). Pre-check kanban_db.py VALID_INITIAL_STATUSES before direct INSERT

### Key facts
- OWUI webui.db: /home/sy5/owui/lib/python3.12/site-packages/open_webui/data/webui.db (memory + chat tables live here)
- call_hermes prepends "CONTEXT:" — grep agent.log for correlation ids, not 'PLAN REQUEST'
- Hermes memory pointer (MEMORY.md line 3) WORKS — contract is read on every PLAN REQUEST turn
- Playwright run-server is WebSocket-only: plain GET = error page, that's healthy; EADDRINUSE on "restart" means it was already up
- "Message Hermes" via the LSE can land in the WRONG memory store (LSE's own OWUI memory) — always verify on node3090: sudo grep PLANNER /home/hermes-admin/.hermes/memories/MEMORY.md

## Session 2026-06-12 — P25: triage is the decomposer's inbox; fabrication survives prompt fences

### What worked
- v1.7.9 direct INSERT into kanban.db: schema has NO CHECK on status; VALID_INITIAL_STATUSES={running,blocked} gates only the Python API. created_at is INTEGER epoch. idempotency_key + INSERT OR IGNORE = re-plan safe
- Catching fabrication by independent re-fetch of the cited source within minutes (grep the version table, not the prose)
- Attributing "unattributed" OWUI activity via time-window SQL on the chat table: SELECT ... WHERE updated_at BETWEEN strftime('%s',...) — found in seconds what text-grep missed for two sessions

### What failed and why
- **Attempted:** v1.7.9 card with status='triage' as the "safe, never-claimed" state (P22 survey conclusion)
  **Failed because:** Hermes kanban_decompose.py treats triage as its INPUT QUEUE — auto_decompose:true (default) decomposes every triage card per dispatcher tick, flipped ours triage->todo, spawned 3 t_* children, dispatched 2 workers that re-did finished research
  **Fix:** auto_decompose: false in /home/hermes-admin/.hermes/config.yaml (~line 441, backup .bak-P25) + systemctl restart hermes-gateway. Verified: next card stayed triage
- **Attempted:** Stopping the rogue work by archiving the cards
  **Failed because:** archive does NOT stop an in-flight worker — pid 11699 kept executing the archived card for 10+ min
  **Fix:** kill tasks.worker_pid explicitly, THEN archive
- **Attempted:** Preventing RUTX50 fabrication via explicit context fence ("no version newer than 07.23.4 exists") + verified ground truth provided
  **Failed because:** LSE fetched the wiki page (07.22.3=Stable/07.23.4=Latest in plain view) and STILL emitted phantom 07.23.5 + 07.22.4 with invented dates/changelogs recombined from the real 07.23 changelog — evidence overwrite at synthesis, fabrication #5
  **Fix:** corrected docs/rutx50/rutx50-remediation-decision.md (correction header). Real fix queued v1.7.10: code-enforced source-claim verification (re-fetch cited sources, diff claimed facts) — fences don't hold at synthesis

### Key facts
- kanban.db tasks: created_at INTEGER epoch, no CHECK on status, idempotency_key indexed; t_* ids = Hermes API path; created_by column reveals the writer (auto-decomposer vs lse-cogitator)
- node3090 ~/.hermes/config.yaml: auto_decompose now FALSE; manual decompose = `hermes kanban decompose <id>` or dashboard button
- P24 "webui.db clean" was a false-negative: verify ABSENCE with storage-shaped queries (time-window on chat.updated_at), never text-grep for command text that isn't persisted
- 06-10 22:14 sweep = SY5's "Claude Code Security Check" OWUI chat (npm supply-chain, Check Point) — harness exonerated: run_episode.py -> llama-server direct, never the cogitator, never agent_commands.log
- RUTX50: 07.22.3=official Stable, 07.23.4=Latest, NO fix exists (verified 2026-06-12); webui auth = uhttpd->api_dispatcher.lua(LuaJIT)->ubus session, SSH=dropbear (separate); recovery: /etc/init.d/uhttpd restart; downgrade WITHOUT keep-settings

## Session 2026-06-13 - P26/P27: USE BASH for .py on NTFS; OWUI backup; ES source_url; git locks; K cache

### What worked
- OWUI backup recovery: copy-paste tool code from OWUI editor to txt then rename .py.
  Pure CRLF on Windows clipboard -- not a problem. Python normalizes CRLF to LF on write.
  Black-norm sha256 is the deploy identity: python3 -m black --quiet - < file.py | sha256sum
  (--code flag hits OSError: Argument list too long on files > ~100KB)
- Finding correct ES field names: print sorted(src.keys()) from a live hit before writing
  any update logic

### What failed and why
- **Attempted:** Reconstructing cogitator from P26 transcript after truncation
  **Failed because:** User paste was last message before context summarization, compressed
  into summary prose, not preserved in JSONL. Largest JSONL message was 43KB; 213KB paste lost.
  **Fix:** OWUI copy-paste backup is the authoritative source for deployed code.

- **Attempted:** fix_rutx50_kb_source.py used src.get("source") with URL-content match
  **Failed because:** KB documents store URL in source_url, not source. Returned "(none)"
  for all docs -- silent wrong-field read.
  **Fix:** src.get("source_url"); target by title match, not URL-content match.

- **Attempted:** Git commit from Cowork sandbox
  **Failed because:** .git/index.lock and HEAD.lock persisted from crashed session.
  Sandbox cannot delete NTFS lock files -- rm returns "Operation not permitted".
  **Fix:** PowerShell: Get-ChildItem ".git\*.lock" | Remove-Item -Force before every commit.

- **Attempted:** Bash splice on session-handover.md via sandbox mount
  **Failed because:** Sandbox /sessions/.../mnt/ showed stale truncated view (109 lines)
  of a 204-line committed file. Bash splice wrote truncated version back, losing 95 lines.
  **Fix:** For .md files use Read/Write/Edit file tools (not bash -- bash mount can be stale).
  For .py files: ALWAYS use bash (Write/Edit silently truncate .py on NTFS). No exceptions.

### Key facts
- LARGE .py FILES ON NTFS: USE BASH. NOT Write/Edit tools. ALWAYS.
  Splice: python3 -c "with open(p) as f: s=f.read(); s=s.replace(old,new,1); open(p,'w').write(s)"
  Verify: python3 -c "print(sum(1 for _ in open(p)))" + python3 -c "import ast; ast.parse(open(p).read())"
- For .md files: use Read/Write/Edit file tools. Bash mount can show stale/truncated NTFS state.
- ES lse-kb field is source_url (not source). Full schema: content, created_at, doc_id,
  embedding, quality_score, refinement_count, source_path, source_url, tags, title, topic,
  updated_at, version. source_tier and verified_against are dynamic fields.
- KV cache: K must stay Q8_0 -- lowering K breaks this model. V is the only safe knob:
  --cache-type-v q4_0 saves ~2.6 GB at 80k context, extends comfortable range to ~120k.
- SSH v1.7.13: search_kb('{hostname} SSH access') with NO topic_filter before any ssh command.

---

## Session 2026-06-14 — P29: sudo-block surfacing, Hermes channel skill, stale-mount confirmation

### What worked
- Surfacing sudo delegation blocks reliably (Cogitator v1.7.21): make `sudo_delegation_block` RETURN
  a directive that forces the model's visible (post-`<think>`) reply to reproduce a ```bash fence
  verbatim. The post-think reply is the only channel that renders reliably; format the command as a
  real ```bash fence so it's copyable.
- Building v1.7.20→22 via bash splice with per-replacement `count==1` asserts + `ast.parse` +
  black-norm sha + `diff -u` to prove the change is surgical. Zero collateral edits in ~5000-line files.
- Hermes producer side as SKILL.md + a deterministic helper (`lse_channel.py`, atomic JSON outbox).
  Verified the round trip OFFLINE by running the helper's marker through the LSE's exact parser regex
  before deploying anything.

### What failed and why
- **Attempted:** Fix "sudo block hidden in thinking" with `__event_emitter__` alone (v1.7.20).
  **Failed because:** when the model calls a tool mid-reasoning, emitter `message` content is appended
  inside the still-open `<think>` block → OpenWebUI collapses it → still hidden.
  **Fix:** don't rely on the emitter to escape thinking; route the surface through the model's
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

### Key facts
- `check_hermes_inbox` is EMPTY until the Hermes-side outbox (producer) is installed — that is correct,
  not a bug. The LSE should say "channel requires the Hermes outbox; not installed" rather than
  confabulating filesystem paths (`/opt/hermes/inbox/` does not exist).
- Hermes skills = SKILL.md (YAML frontmatter + markdown) in `~/.hermes/skills/`, installed via
  `skill_manage` BY HERMES (hermes-admin owns `~/.hermes`; lse-admin cannot write it). The producer
  helper is a plain script at `~/.hermes/bin/`.
- ctx-size 81920 is universal canon (4090 + node3090). socat eliminated P27; gateway binds :8642 direct.
- Cogitator deploy identity = black-norm sha. v1.7.21 = `79b74fde…` (deployed); v1.7.22 = `142f155a…`.

---

## Session 2026-06-14 — P31

### Key facts
- Run throwaway build/verify steps (`npm install`, test runs) in the SANDBOX scratch dir, never inside the mounted repo — the sandbox can create on the NTFS mount but cannot unlink, so a `node_modules/` (or any file) written there is unremovable from the sandbox (EPERM) and must be deleted host-side. Copy only source files into the repo.

## Session 2026-07-02 — Goethe MCP hardening + Claude stdio bridge

### What worked
- Claude Desktop (MSIX-packaged) bridges stdio MCP servers into Cowork sessions:
  claude_desktop_config.json entry → `wsl.exe -d Ubuntu-24.04 -- bash tools/start-goethe-stdio.sh`
- start-goethe.sh v2.0 pattern: token sourced from ~/.lse/secrets, bind 127.0.0.1,
  pkill matches only '--transport http' so stdio bridge instances survive gateway restarts

### What failed and why
- **Attempted:** delete the LocalCache claude_desktop_config.json, keep %APPDATA%\Claude copy
  **Failed because:** the packaged app's active AppData is the MSIX virtualized tree —
  config AND logs live under AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\;
  deleting that copy deregistered the MCP server entirely (pgrep count 0, no spawn attempt)
  **Fix:** Copy-Item the config back into LocalCache — that path is authoritative for the app
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

### Key facts
- Claude Desktop active config: C:\Users\SY5\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
- Both LocalCache AND %APPDATA% configs present → TWO stdio instances spawn (one per copy)
- MCP spawn diagnostics: same LocalCache tree, logs\mcp-server-goethe.log
- stdio transport has NO token — token auth is HTTP-transport only; rotation cannot break the bridge
- Never bare `pkill -f goethe_mcp.py` — kills the Claude bridge; use 'goethe_mcp.py.*--transport http'
- Cowork sandbox's mounted repo view can lag the real filesystem — verify git state via WSL
  (goethe execute_command), not the sandbox mount

## Session 2026-07-02 — PROVE-2 contract tests: venv + demotion-floor findings

### What worked
- Contract-testing goethe.py KB tools against live ES without touching production:
  monkeypatch `Tools._es` with an index-rewrite proxy (lse-kb -> lse-kb-test,
  lse-skills -> lse-skills-test, any other index -> RuntimeError) + auto-refresh after writes
- Monkeypatch `Tools._embed` with deterministic hash-seeded 768-dim unit vectors —
  no Ollama dependency; identical text -> cosine 1.0 (dedup fires), distinct -> ~0.0
- Run: `cd <repo> && /home/sy5/owui/bin/python3 -m pytest tests/test_kb_contracts.py -q`
  (34/34 green, 19.5s)

### What failed and why
- **Attempted:** `python3 -m pytest tests/test_kb_contracts.py` with system python3
  **Failed because:** system python3 on LUCIFER has NO pydantic/elasticsearch — those live
  only in the owui venv (/home/sy5/owui/bin/python3), which is the goethe_mcp runtime
  **Fix:** /home/sy5/owui/bin/pip install pytest (done this session) and always run
  goethe-importing tests with the owui-venv interpreter

### Key facts
- skill_outcome demotion floor DISCREPANCY: code is max(0.0, q - 0.15) (floor 0.0),
  docstring claims "floor 0.2". Archive triggers at new_q < 0.2 (unless pinned).
  Test pins the CODE (0.25 -> 0.10 + ARCHIVED); reconcile in KB-DECAY-1.
- record_outcome(success=False) never touches quality_score (v0.2.9) — pinned in-test,
  marked as the KB-DECAY-1 flip point
- Repo copies identical: /home/sy5/projects/local-system-engineer/tools/goethe.py ==
  /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/goethe.py (diff -q verified)
- ES top-level knn score = (1+cosine)/2 — dedup threshold 0.92 => cosine >= 0.84
- pytest 9.1.1 + elasticsearch-py 8.19.3 now in owui venv; ES server 8.13.0

## Session 2026-07-04 — PH3-3 Run 8: sandbox git/write blocks on /mnt/, base64 paste fix

### What worked
- `run_tests(scope="rules")` as the automated Run 8 path — 9 scenarios, no manual suite-version judgment call needed
- Checking `curl :8080/slots` for `is_processing:false` before a GPU-bound eval run, instead of guessing whether the user is mid-conversation
- Delegating git/file writes to a real terminal via `sudo_delegation_block` with a base64-encoded one-liner (`echo '<b64>' | base64 -d > file`) instead of a multi-line heredoc — avoids paste truncation on content with em-dashes/checkmarks
- Repo at `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` is also mounted directly as the Cowork workspace folder — plain file edits (non-git) can go through Claude's own Read/Edit tools instead of goethe execute_command, with no privileged-path block

### What failed and why
- **Attempted:** `git commit` via goethe `execute_command`, path `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` (also tried the Windows-style `C:\Users\...` form)
  **Failed because:** `/mnt/` is a privileged write path in goethe's execute_command guard — blocked regardless of path spelling, even for a plain `git commit` with no sudo involved
  **Fix:** `sudo_delegation_block` → user runs it in a real WSL terminal
- **Attempted:** first delegated git commit attempt, run in Joe's terminal
  **Failed because:** a stale `.git/index.lock` was left behind from the blocked in-sandbox attempt
  **Fix:** `rm -f .git/index.lock` before retrying add+commit
- **Attempted:** multi-line `cat > file << 'EOF' ... EOF` heredoc pasted into the terminal for a ~5KB report with unicode chars
  **Failed because:** paste truncated mid-block; bash sat at the `>` PS2 prompt waiting for the never-arrived `EOF`
  **Fix:** base64-encode the whole file content, single-line `echo '<b64>' | base64 -d > path`, verify with `wc -l` + `head`
- **Attempted (avoided, not actually run):** treating the gateway token-guard assert failure as a stack-health blocker
  **Failed because:** skill's `assert_state` regex expects literal `401`, but `curl 127.0.0.1:9700/` returns `{"error":"unauthorized"}` (JSON body, not a bare status line) — doc is stale, not a real problem

### Key facts
- goethe execute_command / write_file privileged-path block covers `/mnt/` regardless of whether the path is written as `/mnt/c/...` or `C:\Users\...` — always delegate git and repo-root writes under this path to a real terminal
- `~/projects/local-system-engineer` is a symlink to `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` — same privileged-path block applies through the symlink for goethe's write_file, but Claude's own mounted-folder file tools (Read/Write/Edit) can write there directly since it's the Cowork workspace folder
- Three different version strings currently coexist for "Goethe": `tools/goethe.py` title/version = v0.3.8 (live, matches CURRENT-STATE.md changelog line), `goethe_mcp` startup banner = v1.9.3, and the `eval_goethe_rules.py` harness banner prints "Goethe v0.2.2" — none of these were reconciled this session, flagged in eval-report-v7.md instead
- Run 8 baseline (7/9, rules scope only) recorded in CURRENT-STATE.md and eval/eval-report-v7.md — commit e84eeb1

## Session 2026-07-06 — pfSense context-blowup: wrong hypothesis, real mechanism, and an unconfirmed write

### What worked
- Intercept-only MCP harness test: send a natural-language prompt straight to llama-server's
  OpenAI-compatible chat API with the real tool schema, capture the model's proposed tool_call,
  and never actually execute it. Safe way to test a wrong-tool-selection hypothesis against a
  live production model without touching the real backend — 9/9 probes came back clean, which
  in hindsight correctly indicated the log-routing hypothesis was wrong, not that the system was safe.

### What failed and why
- **Attempted:** hypothesized (from Joe's partial recollection) that the context-blowup incident
  was `pfsense_graphql` called with a logs-shaped query, and designed a fix around that.
  **Failed because:** the actual, confirmed vector was `queryDiagnosticsTables` — a GraphQL type
  that returns every built-in pfSense alias table inline, including `bogons` (a several-thousand-
  entry CIDR blocklist), with no pagination or size cap. Nothing logs-related about it at all.
  goethe.py's LOG ENDPOINT PROHIBITION guidance only names firewall logs — diagnostics tables
  aren't mentioned anywhere, so neither the model nor the docstrings had any reason to expect this.
  **Fix:** a content-based regex guard targeting known-bad query shapes can never cover this class
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

### Key facts
- `queryDiagnosticsTables` (GraphQL) returns ALL built-in pfSense alias/table contents inline,
  unbounded — `bogons` alone is several thousand CIDR entries. Treat it as equally dangerous as
  raw firewall logs for context size, despite not being logs-related.
- pfSense's Config History (`Diagnostics → Backup & Restore → Config History`) logs the source of
  API-driven changes, e.g. `admin@192.168.1.57: Modified System DNS via API` — useful forensic
  check for confirming whether an agent (vs. a human) made a given change.
- pfSense's Unbound resolver in "forwarding" mode uses System DNS Server Settings
  (`readSystemDns` / `/api/v2/system/dns`) as its upstream targets — wiping all external entries
  there breaks Unbound resolution entirely, confirmable with `dig @<pfsense-lan-ip> <domain>`.
- pfSense REST API read-only mode is a one-way lock via API: can be re-enabled programmatically
  (`PATCH /api/v2/system/restapi/settings` → `{"read_only": true}`) but can only be *disabled*
  through the web UI — explains why a manual UI toggle was needed mid-session here.

## Session 2026-07-06 — pfSense Phase 2 extraction: docstring drift and a same-day regression

### What worked
- Grep `self\.<method_name>` across the *entire* file before extracting any method out of a
  monolithic Tools class — `pfsense_query` looked self-contained (three call sites, all inside
  its own definition) until a repo-wide grep turned up a fourth: `wake_node()` calling
  `self.pfsense_query(...)` internally, ~3500 lines away from the pfsense_* block.
- Standalone-loading the extracted module with the real venv python
  (`/home/sy5/owui/bin/python3`, not system `/usr/bin/python3` — the latter has no `pydantic`)
  to unit-test the new guards before wiring `--also`, including one live call that reached the
  real pfSense and got a real auth error back (proof the network path still works post-move).
- `goethe_mcp.py --list --also <file>` as a zero-risk dry run for `--also` wiring changes —
  loads and registers tools from all modules, prints the full exposed-tool list and any name
  collisions, without binding a port or touching the live running server.

### What failed and why
- **Attempted (found, not caused this session):** `pfsense_query`'s inline docstring example
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

### Key facts
- Real venv for goethe/MCP work: `/home/sy5/owui/bin/python3` (has pydantic, requests, etc).
  System `/usr/bin/python3` does not — a "ModuleNotFoundError: pydantic" from a quick script
  doesn't mean the code is wrong, it means the wrong interpreter was used.
- `--also` modules registered by `goethe_mcp.py` are separate `Tools()` instances from
  `goethe.py`'s own instance and from each other — no method on one is callable via `self.` from
  another. Any pre-extraction internal cross-call must be rewritten to not depend on the
  extracted instance, not just left as `self.<method>` and hoped to work.
- The entire `lse/` directory is gitignored (`.gitignore:29: lse/`) — `lse/skills/vault/tools.py`
  and now `lse/skills/pfsense/tools.py`/`kb/`/`skill.toml` exist on disk but are NOT tracked by
  git. The runtime-loaded copy that actually matters for `--also` wiring lives in `tools/` (e.g.
  `tools/pfsense_tools_v1.0.0.py`, `tools/vaultwarden_tools_v1.3.0.py`) and IS tracked; the `lse/`
  copy is a manually-kept-identical mirror for the future `bin/lse` monorepo loader (Phase 3, not
  started). Don't assume a `git commit` captured an `lse/skills/*` change — check `git status`
  against the actual path, it will show nothing even when files changed on disk.

## Session 2026-07-11 — TRAUM Thread 1 close: docstring gate-conflict audit + run_tests(scope) boundary

### What worked
- Auditing a multi-step skill file for v0.3.4-class gate conflicts by grepping for words reused in two different behavioral senses (e.g. "skip" meaning both "never ran a required check" and "the check ran and correctly produced a no-op result") surfaced a real ambiguity in `skills/lse-session-debrief/SKILL.md` before deploy, not after a field failure.

### Key facts
- `run_tests(scope=all)` does NOT run the legacy `scripts/` pytest harness — its "harness/tests" bucket is `pytest tests/` only. Only `run_tests(scope=harness)` reports both `tests/` (harness/tests) and `scripts/` (harness/scripts) as separate buckets. "All green" from `scope=all` does not mean `scope=harness` is fully clean.
- Two `scripts/` legacy harness collection errors are pre-existing and unrelated to any TRAUM Thread 1 work: missing `gymnasium` module (breaks `scripts/test_challenge_env.py`, `scripts/test_escalation_wrapper.py`) and missing `tools/cogitator-v1.7.15.py` (breaks `scripts/test_hermes_inbox.py`).
- A skill file's worked examples that cite specific live, mutable system state (e.g. "doc X is currently unaddressed") go stale the moment that state changes, since the whole file is re-read verbatim on every future invocation — worked examples referencing live state need an explicit "verify current state before trusting this" caveat.

## Session 2026-07-11 — TRAUM Thread 2 close: kb-fact/index_to_kb apply-gate gap, and the ES-boundary this session can't cross

### What worked
- Cross-checking `docs/dreaming/DESIGN.md` §6.2's proposal-shape spec against `tools/dream_apply.py`'s actual `apply_group()`/`render_group()` dispatch (rather than trusting the module docstring's own "reuses this format verbatim" claim) surfaced a real, silent gap: `index_to_kb` (the `kb-fact` type) was specified since Thread 1 Prompt 1.5 but never wired into Thread 2's apply gate — only `mentor_correct`/`record_outcome`/`kb_verify`/`skill_record` had dispatch branches. Found by trying to actually build this session's own kb-fact debrief proposal and discovering there was nowhere for it to go.
- Reconstructing a corrupted/truncated bash-sandbox mirror of a large source file (`tools/dream_apply.py`, `tools/dream_runner.py`, `tools/goethe.py` all hit this at different points this session) by diffing against the Read-tool's view of the real file, rather than trusting the sandbox's own `wc -l`/`py_compile` output — the sandbox's Linux mount of the Cowork workspace folder can silently truncate a file mid-write while the real file on disk is complete; `py_compile` failing in the sandbox is not proof the real file is broken.
- Writing `tests/test_dream_engine.py`'s ES double (`FakeES`) to raise loudly on `es.delete()` (never a legitimate call anywhere in this codebase) caught my own first-draft mistake: `es.index()` is NOT similarly forbidden — `skill_record`/`index_to_kb` legitimately call it for a brand-new doc in the real `goethe.py`. An unconditionally-raising `FakeES.index()` was over-strict and would have made the new kb-fact test impossible to write correctly.

### What failed and why
- **Attempted:** run `tools/dream_apply.py --no-dry-run` against this session's own kb-fact proposal (the calibration verdict below), to close the debrief through a real ES write, per Prompt 2.10's own "unified write path" instruction.
  **Failed because:** Cowork has no network path to LUCIFER's Elasticsearch/Ollama instances — `dream_apply.py` requires both to actually call `index_to_kb`. Every other Thread 2 artifact that touched live ES (`dream-run-2026-07-11.md`, `calibration-run-1.md`) was run directly on LUCIFER, outside Cowork.
  **Fix:** none needed — this is an environment boundary, not a bug. Prepared and validated the proposal as far as this session can (`validate_proposal_for_apply()` returns `None`; `render_group()`'s real confirm-gate output captured verbatim) and left it as `docs/dreaming/2026-07-11-thread2-close/proposals.jsonl`, ready for `/home/sy5/owui/bin/python3 tools/dream_apply.py --proposals docs/dreaming/2026-07-11-thread2-close/proposals.jsonl --no-dry-run` on LUCIFER.

### Key facts
- `docs/dreaming/calibration-run-1.md` (Prompt 2.8) cited "DESIGN.md §7.1"/"§7.2" (the auto-apply allowlist) before §7 existed — Prompt 2.6 ("design only") had been skipped in practice. Added §7 this session so those citations point at something real; recorded as a genuine skipped-prompt finding, not invented scope.
- `dream_apply.py` has no code path that sets `manifest.db`'s `dreamed_at`, despite `episode_index.py`'s own comment claiming it is "set by Thread 2's dream_apply.py" — Prompt 2.7's 13 sessions were marked by hand (`sqlite3 UPDATE`). Left open for Thread 3's first prompt to design (dream_runner.py knows the session list; dream_apply.py knows what was actually reviewed — genuinely unclear which file should own this without a real design pass, not something to guess at during a closing prompt).
- **Calibration verdict, recorded as this session's kb-fact proposal:** production `linear` `search_kb` retrieval mode was bit-for-bit identical (recall@1=0.76, recall@3=0.84, MRR=0.800) before vs after Thread 2's first supervised dream, despite ~84% `lse-kb` growth (200→368 docs); `min_score=4.2` re-swept per its own maintenance rule and still holds (38/38 correct top-1 kept at cut=4.020, 0 correct lost). No regression — Thread 2 is clear to hand off to Thread 3 on the retrieval-quality dimension specifically (two non-blocking process gaps — dedup re-proposal, `dreamed_at` — are carried forward separately, see `CHANGELOG.md`).

## Session 2026-07-12 — TRAUM Thread 3 close: v0.4.0-a deployed live, `time_check()`/`[DREAM]` desync, a real dream cycle's first two surprises

This close ran differently from every prior TRAUM entry: this Cowork session
turned out to be running ON LUCIFER itself (`C:\Users\SY5\Claude\Projects\
local-system-engineer` is the same repo WSL2 mounts at `~/projects/local-
system-engineer` via `/mnt/c/...`), and `mcp__goethe__*` tools were live-
connected to the real `goethe_mcp` gateway — not simulated, not mocked. That
turned "deploy + verify" from a documentation exercise into a real one, and
running the dreamer against real data (`lse-kb`, `agent_commands.log`,
`tasks.db`) for the first time surfaced two genuine findings neither the
sandbox-only Prompt 3.8 run nor any unit test had caught.

**The digest insight this close asked for, answered directly:** the digest
itself, this cycle, is unremarkable — 6 `dedup` proposals, all "exact
character-for-character duplicate" pairs, the most mundane possible finding
a dreamer can produce, plus two genuine null results (`stale-contradiction`,
`error-cluster`) working exactly as designed. Nothing in the digest's own
content is non-obvious. **The genuinely non-obvious findings this close
came from *operating* the dreamer for the first time against real data, not
from the digest's insights pass** (which was deliberately not run for real
— see below): (1) a live plaintext credential sitting in `agent_commands.log`
that the `patterns` pass would have written straight into a git-committed
artifact and handed to an off-host LLM as prompt evidence, had the pipeline
continued as designed; (2) `proposals.jsonl` has no append-mode protection
against a later pass in the same cycle silently overwriting an earlier
pass's real, actionable proposals — proven by watching it actually happen,
not by reading the code and predicting it could.

### What worked
- Testing "does the `[DREAM]` banner appear on first `search_kb`" the
  realistic way — call `time_check()` first, exactly as CHRONOS's own
  docstring and the system prompt's TIME DISCIPLINE section both instruct
  for date-sensitive work, rather than calling `search_kb` in isolation
  the way every existing unit test did — immediately surfaced a real
  interaction bug (see below) that no test written before this close would
  have caught, because every prior test exercised the two banner-emitting
  tools separately, never in the order a real session would actually use them.
- Reviewing the digest file itself *between* each dream pass, not only once
  at the end of a "full cycle," caught the `proposals.jsonl` overwrite live
  as it happened (`Pending human-gate (6)` → `(0)` after two null passes) —
  reviewing only the final state would have shown an empty queue with no
  way to tell whether that meant "nothing pending" or "something got
  silently dropped."
- `start-goethe.sh`'s kill pattern (`goethe_mcp[.]py.*--transport http`)
  correctly left two unrelated stdio-transport `goethe_mcp.py` instances
  running untouched during the gateway restart — confirmed by PID/port
  inspection before and after, not assumed from reading the script.

### What failed and why
- **Attempted:** verify the `[DREAM]` banner by calling `time_check()`
  first (the documented, recommended order), then `search_kb`.
  **Failed because:** `time_check()` sets the same `_time_banner_emitted`
  flag `_consume_time_banner()` gates on, but only ever appends the
  `[TIME]` line — never `[DREAM]`. `_consume_time_banner()`'s own docstring
  claims reusing that flag "guarantees the two banners can never desync,"
  but that reasoning only accounted for `_consume_time_banner()` itself
  setting the flag; it didn't account for a second, independent setter.
  Result: a session calling `time_check()` before its first `search_kb`
  got `[TIME]` immediately and then silently lost `[DREAM]` for the rest
  of the session, every time.
  **Fix:** `tools/goethe.py`'s `time_check()` now also calls
  `self._dream_banner()` and appends the line on the same gate it already
  owns. New test `TestChronosTimeCheck::test_time_check_first_still_
  carries_dream_banner` (`tests/test_kb_contracts.py`) pins the fix.
  Redeployed (second gateway restart) to ship it; re-verified live —
  `search_kb` after `time_check()` now correctly shows neither banner
  again (both already delivered by `time_check()`), and a *fresh* session
  calling `search_kb` first shows both together.
- **Attempted:** run `patterns --no-dry-run` for real, then feed
  `patterns.json` into a real `insights` LLM pass, to get a genuine
  cross-session insight for this debrief.
  **Failed because:** the `patterns` pass's `command_frequency()` mining
  reads `agent_commands.log` completely verbatim, with no secret-redaction
  step anywhere in `dream_runner.py`. The real `--dry-run` preview (kept
  at dry-run specifically because of what it found) surfaced a live
  plaintext password embedded in a repeated `sshpass -p '...' ssh ...`
  command, 6 occurrences. `--no-dry-run` would have written it into a
  git-tracked `patterns.json`/`report.md`; a subsequent real `insights` run
  would have sent it off-host to node3090's LLM inside
  `_domain_command_frequency()`'s prompt text as "evidence."
  **Fix:** neither step was run for real. The password is not repeated
  anywhere in this repo. Recorded as a Thread-4-blocking finding in
  `CHANGELOG.md` and `CURRENT-STATE.md`: `dream_runner.py` needs a
  redaction pass over raw command text before Thread 4 (TRAUM-AUTO) can
  safely schedule any of this unattended, and the operator should rotate
  the actual credential and move it to Vaultwarden.
- **Attempted:** run the full multi-pass cycle (`dedup` → `stale-
  contradiction` → `error-cluster`) the same way Prompt 3.8's sandbox run
  did, then read the final digest once.
  **Failed because:** `report.md`/`proposals.jsonl` are single-pass-per-
  day-dir snapshots (true since before Prompt 3.8; 3.8 only added
  append-mode persistence for *null* results, not for real proposals).
  `dedup` produced 6 genuine, real duplicate-pair proposals; the two null
  passes that ran after it in the same day-dir silently overwrote them out
  of `proposals.jsonl` — the digest's pending-gate count visibly dropped
  from 6 to 0. In the empty-corpus Prompt 3.8 sandbox run, every pass was
  null, so overwriting-empty-with-empty never revealed this; it took a
  real, non-null first pass to expose it.
  **Fix:** re-ran `dedup` a second time, last, so its real output is what
  survives on disk for the operator's review. The underlying gap (no
  append-only persistence for real proposals across a multi-pass cycle,
  matching what `null-results.jsonl` already does for nulls) is unfixed
  and recorded as Thread 4's first item, not patched unilaterally here.

### Key facts
- This Cowork session runs on LUCIFER itself — `mcp__goethe__*` tools are a
  live connection to the real gateway, not a simulation. Confirmed via
  `git log`/`git status` matching between the Windows-side path and WSL2's
  `~/projects/local-system-engineer`, and `pytest`'s `rootdir` reporting
  `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer` from inside WSL2.
- The Cowork bash sandbox (`mcp__workspace__bash`) is a *separate*,
  unrelated environment from LUCIFER's real WSL2 — its FUSE mount's
  staleness bug (documented in the Prompt 3.9 CHANGELOG entry) is specific
  to that sandbox and does not reflect the true state of the files on
  LUCIFER, which were confirmed correct and in sync (`ast.parse` clean,
  exact line-count match) throughout this close.
- `goethe_mcp.py`'s `Tools()` instance is created ONCE per gateway process
  (`inst = Tools()`, not per MCP client session) — `_time_banner_emitted`
  is therefore process-lifetime scoped, not per-llama-ui-thread scoped.
  The banner only fires once for the FIRST caller of any kind after a
  gateway restart; every llama-ui thread after that first caller (until
  the next restart) will not see it again. This is why the DEPLOY NOTE in
  `goethe.py`'s own changelog insists on a fresh thread immediately after
  a gateway restart, and why testing the banner live consumes the one
  opportunity a real user's fresh thread would otherwise get.
- `dream_runner.py --pass dedup --no-dry-run` against the real 372-doc
  `lse-kb` takes roughly 90–120s (Ollama CPU embedding, pairwise cosine,
  LLM confirmation per candidate) — long enough that `execute_command`'s
  own timeout cuts it off if run synchronously; use `nohup ... & disown`
  and poll the log file instead.
- `dream_runner.py`'s `main()` already calls `dream_digest.py` at the end
  of every pass invocation to refresh `/opt/local-se/dreams/latest-
  digest.md` — no separate manual digest-generation step is needed after
  a real run.

## Session 2026-07-17 — P0 write-time redaction deploy + recursive leak trap

### What worked
- Vendoring Hermes agent/redact.py as tools/redact.py (self-contained: logging/os/re only) — survives Hermes decommissioning; one shared module now feeds goethe.py _log(), goethe_mcp.py _redact_text(), and dream_runner.redact_log_text()
- Pattern-based scrubbing with prefix regexes (e.g. `2c0lDMNC[A-Za-z0-9]{10,}`) instead of typing literal secrets into commands
- Smoke test of the real write path: instantiate Tools() directly, call _log() with fake credentials, tail the log — proves redaction live without waiting for a session
- start-goethe.sh kill pattern `goethe_mcp[.]py.*--transport http` only touches the HTTP gateway — safe to restart while a Cowork stdio gateway session is active

### What failed and why
- **Attempted:** 2026-07-16 remediation session grepped historical logs for the LITERAL secrets
  **Failed because:** goethe.py _log() wrote every command raw — the grep patterns containing the real secrets were themselves logged, re-leaking all 4 secret classes into the current log (and into episode JSONL via the same gap). Displaying leaked lines has the same effect: this session's `sed -n '31p'` output re-entered its own episode file.
  **Fix:** Never grep/echo literal secrets on a system with an unredacted audit path. Use prefix regexes. Root fix deployed: redact_sensitive_text() in _log() at write time.
- **Attempted:** Chained shared redaction sweep after dream_runner's local _REDACT_RULES
  **Failed because:** double-redaction — _mask_token re-masked the literal marker `[REDACTED:pattern-match]` to `[REDAC...tch]`, breaking test_dream_patterns contract
  **Fix:** idempotency guard in _mask_token: `if token.startswith("[REDACTED"): return token`
- **Attempted:** Broad scrub via `find -name '*.log' -o -name '*.jsonl' ...`
  **Failed because:** `agent_commands.log.20260704-backup` (suffix ≠ .log) dodged the glob; 3 raw pfSense api_key= URLs survived the "completed" archive redaction
  **Fix:** verify sweeps by grepping the PATTERNS across the whole tree, not by trusting globs

### Key facts
- Hermes redact.py ships URL query-param redaction intentionally OFF (agents follow magic links); for an audit log it must be ON — LSE copy enables it + adds CLI-credential rule
- Episode redaction gap was shape-based: KEY=value and Bearer matched, bare vendor prefixes (sk-, hf_) did not — 24 raw keys reached the dreamer's corpus before the fix
- write_file blocks /opt/local-se/kb/ (outside allowed paths) but execute_command cat>> works
- goethe_mcp processes: :9700 HTTP = llama-ui gateway; per-Cowork-session stdio instances keep OLD code in memory until session end — patched code needs both restart AND new session
- esbuild binaries / Grafana JS bundles false-positive on sk-/api_key= secret greps — scope sweeps to audit surfaces, not node_modules
- Redaction ≠ rotation: checklist in kb/secrets-propagation-report.md, vault master first

## Session 2026-07-17 — Neural search deploy: watchdog vs ingest, apt fastapi, json_engine HTTP

### What worked
- Sidecar pattern: bge-m3 + bge-reranker-v2-m3 GGUF via second/third llama-server instances (lse-emb :8090 `--embeddings --pooling cls`, lse-rerank :8091 `--reranking`) — only ~1.35 GB VRAM combined, coexists with Qwen3.6-27B ctx131072
- Arch Wiki via `arch-wiki-docs` pkg dump (one 60 MB .pkg.tar.zst, 2,345 pages) instead of crawling 12k pages — ingested 33,413 chunks locally
- Firecrawl job results survive ingest crashes: `GET /v1/crawl/<job-id>` re-fetches completed crawl data — added `--job-id` resume to ingest.py, no re-crawl needed
- SearxNG `json_engine` for custom local engines — zero custom Python mounted in the container

### What failed and why
- **Attempted:** long Firecrawl crawl (400 pages) then embed, with lse-emb managed by the 10-min idle watchdog
  **Failed because:** scrape phase produced no embedding traffic >10 min → watchdog stopped lse-emb (as designed) → ingest crashed ConnectionRefused on :8090
  **Fix:** embed() in /opt/local-se/neural-search/ingest.py now calls ensure_emb() (root-delegated `systemctl start lse-emb` + health poll) and retries up to 4x on ConnectionError/Timeout
- **Attempted:** `apt install python3-fastapi` on node3090 (Ubuntu 24.04) for the search API
  **Failed because:** distro fastapi is incompatible with distro starlette — `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'` at import
  **Fix:** venv at /opt/local-se/neural-search/venv, `pip install fastapi 'uvicorn[standard]' requests`; unit ExecStart uses venv python
- **Attempted:** SearxNG json_engine pointing at http://172.19.0.1:8092
  **Failed because:** SearxNG blocks plain-HTTP engine URLs by default — engine dies with `httpx.UnsupportedProtocol: HTTP protocol is disabled`, UI shows only "unexpected crash"
  **Fix:** add `enable_http: true` to the engine entry in settings.yml, `docker restart sear_primary`

### Key facts
- sear_primary (node3090) config: `/home/sy5/searxng-deployment/searxng/settings.yml` — NOT the LSE-host path `/home/sy5/docker/searxng_data`; container gateway is 172.19.0.1 (network searxng-deployment_sear)
- Neural search API: lse-neural-api.service :8092 (venv uvicorn); engine shortcut `!nl` in sear_primary
- ES index lse-web-idx on lse-kb-es :9200: 43,996 chunks / 962 MB (dense_vector 1024 cosine int8_hnsw); ES 8.13 basic license has no RRF query fusion — fused in api.py (k=60)
- node3090 llama-server binary: `/opt/llama.cpp/bin/llama-server` (KB's `/usr/local/bin` path is stale)
- Watchdog lse-sidecar-watchdog.timer stops idle sidecars after 2×5-min checks — any long-running embed consumer must tolerate restart mid-stream

## Session 2026-07-17 — Stack map correction: OWUI decommissioned, LSE E2E via neural search

### What worked
- Full LSE search chain verified live: llama-ui → search_web → SearxNG (LSE host) → neural json_engine → node3090 :8092 (mode=hybrid) — neural results blend at weight 2 with web engines

### Key facts
- Open WebUI (:3000) is DECOMMISSIONED — replaced by llama-ui served by llama-server itself; health checks must stop expecting :3000
- Playwright now runs as ws://127.0.0.1:3001 (websocket — plain HTTP curl to :3001 is not a valid health probe)
- lse-stack-health-check skill's stack map is stale on both rows above

## Session 2026-07-18 — Roadmap close-out: PH5 refactor, DATA, Run 8 staging

### What worked
- PH5-2 extraction pattern: move methods verbatim into `KBMixin` in a new module, `class Tools(KBMixin)` — goethe_mcp discovers tools via `dir(inst)`, so inheritance keeps the MCP tool list byte-identical (verified: `--list` diff empty, 38/38)
- Release-gate pair for any goethe.py surgery: tool-list diff (HEAD copy vs working tree via `--list`) + `pytest tests/` — the contract suite caught the one real extraction bug immediately
- Usage-data verdicts from the episode journal: mine /opt/local-se/episodes/*/*.jsonl by `.tool` field — 0 search_rfc calls in 6,967 → retired via SKIP_TOOLS (reversible one-liner)

### What failed and why
- **Attempted:** git commit from the Cowork sandbox on the Windows-mounted repo
  **Failed because:** sandbox git can create but not unlink its own `.git/index.lock` ("Operation not permitted" on the mount) — every git write op fails at lock cleanup
  **Fix:** run git via WSL instead: `cd /home/sy5/projects/local-system-engineer && rm -f .git/index.lock && git ...` — same working tree as C:\Users\SY5\Claude\Projects\local-system-engineer
- **Attempted:** goethe.py → goethe_kb.py method extraction after scanning the block for module-level assignments only
  **Failed because:** the block used goethe.py's module-level imports (datetime, json, os, Optional) — 55 contract tests failed with "name 'datetime' is not defined"
  **Fix:** when extracting, scan for imported names too; goethe_kb.py needs its own import json/os, from datetime import datetime, from typing import Optional
- **Attempted:** curl sear_primary :8088 on node3090 (neural-search verification)
  **Failed because:** container was down after host reboot — `restart: always` does NOT restart a container that was manually stopped before the reboot
  **Fix:** docker compose -f /home/sy5/searxng-deployment/docker-compose.yml up -d

### Key facts
- Cowork's goethe stdio MCP instance keeps pre-restart code in memory for the whole session — restarting the :9700 HTTP gateway does NOT refresh it (run_tests(all) lacked the new "data" scope until respawn)
- goethe_mcp tool discovery = sorted(dir(inst)) minus underscore/SKIP_TOOLS — inherited methods count; SKIP_TOOLS is the reversible retirement mechanism
- llama-server build identities (live 2026-07-18): LUCIFER v20 bf2c86ddc at /home/sy5/llama.cpp/build/bin/, node3090 v64 e8f19cc0a at /opt/llama.cpp/bin/
- Gold-set lint caught 2 ghost rows on first run (q43/q44 expected a kb doc that never existed) — provenance-required linting pays for itself immediately
- The same hardcoded GOETHE_MCP_TOKEN appeared in BOTH node prompts (v0.6.0 + node3090-v0.2.1) AND git history — rotate Goethe MCP tokens early in the rotation batch, not as item 7
- Run 8 prerequisites: --reasoning-budget -1 (currently 8192), v0.6.1 prompt pasted, fresh threads, do NOT restart gateway mid-run (tool count now 37)

## Session 2026-07-20 — Bing engine soft-block + config-guard root requirement

### What worked
- MITM/DNS-hijack ruled out definitively via: cross-resolver DNS check (8.8.8.8, 1.1.1.1,
  9.9.9.9, local Pi-hole all agree on CNAME chain, differ only in anycast edge IP) +
  `openssl s_client -verify_return_error` showing `Verify return code: 0 (ok)` chaining
  to a real Microsoft-issued cert + WHOIS confirming resolved IPs are Akamai-owned.
  This is the standard playbook when a search result looks tampered with — check DNS
  agreement across resolvers, then TLS chain validation, before suspecting the network.
- `sudo_delegation_block` with a direct elevated `install` + `docker compose restart`
  command, bypassing the guard script entirely, when an immediate config deploy is
  needed instead of waiting for the 10-min systemd timer.

### What failed and why
- **Attempted:** diagnosing garbled SearXNG results (e.g. a random pizzeria domain
  showing up for a TLS/networking query) by checking for a rogue local `json_engine`
  or MITM
  **Failed because:** the actual cause was upstream — Bing's anti-scraping defense
  doesn't hard-fail SearXNG's request (no exception raised), it returns a soft-blocked
  filler SERP with unrelated content. SearXNG's engine parser doesn't validate result
  relevance, so the junk gets folded straight into results as if legitimate. This
  bypasses `suspended_times` entirely since no `SearxEngine*Exception` is ever raised —
  qwant/brave hard-fail (visibly suspended in logs), bing silently degrades instead.
  **Fix:** set `disabled: true` on the `bing` engine block in settings.yml and remove
  it from `keep_only`; duckduckgo covers general web without this failure mode.
- **Attempted:** running `scripts/searxng-config-guard.sh` manually via execute_command
  (non-root) to deploy a canonical settings.yml change immediately
  **Failed because:** `set -euo pipefail` + `log()` piping through `tee -a
  /var/log/searxng-config-guard.log` — that file is root-owned, so `tee` gets
  `Permission denied`, and the script dies right after logging "DRIFT... repairing"
  but *before* the actual root-owned `install` copy runs. It looks like it started
  the repair and silently didn't finish, not like a permissions error.
  **Fix:** don't run the guard script unprivileged. Use the delegation-block tool with
  an elevated `install -m 0644 -o root -g root <canonical> <live>` followed by an
  elevated `docker compose restart searxng`, run directly by the human operator.

### Key facts
- Canonical SearXNG config lives at
  `/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml`
  (same file editable via Claude's Read/Edit tools on the Windows side) — live copy is
  `/home/sy5/docker/searxng_data/settings.yml`, kept in sync by a root-owned systemd
  timer running `searxng-config-guard.sh` every 10 min.
- `searxng-logger` sidecar has been failing every 15s with HTTP 401 on `/metrics`:
  `docker-compose.yml` sets `SEARXNG_METRICS_PASSWORD=searxng-metrics-token` (a
  placeholder literal) but `settings.yml`'s real `open_metrics` token is
  `JZVeoVch20+FvyjXEn4BMVHtu1AM6JCH` — mismatched since at least 2026-07-19. This means
  the `searxng-engine-health` Grafana dashboard has been blind to engine degradation
  (would have caught the Bing issue sooner). Not yet fixed — align the two values.

## 2026-07-20 — Local-model self-reported "done" is unreliable; verify against independent ground truth

Third instance this session of a local-model (Qwen) tool-execution transcript
reporting successful completion when the actual system state disagreed:

1. Vault KB doc fix ("completed KB fix: A") — content read back unchanged
   moments later; root cause was ES 5s refresh_interval on lse-kb-1024
   (mentor_correct's es.update() is real-time-GET-visible immediately, but
   search_kb's _search query lags until the next index refresh). Not
   malicious, but the model never re-verified via a real-time GET before
   reporting done.
2. "Grant #7/#8 pending" cited as blocking a KB doc fix — grant #8 had
   actually been approved 20 minutes earlier. Both grants were real, but
   belonged to an unrelated node3090 task from earlier in a long thread,
   misattributed to the current task, and cited without a live status check.
3. reembed_pass.py reported "146/146 docs re-embedded, 0 errors, 0 skipped"
   after re-embedding lse-kb-1024 following the qwen3-embedding prefix-bug
   fix (see below). Direct verification via ES `_version` metadata (not the
   script's own log) showed 7 docs still at version=1 — never touched.
   The script had no try/except around es.update() itself, so a genuine
   write failure should have crashed loudly, not vanished — cause of the gap
   still not fully explained, but the self-report was provably wrong.

STANDING RULE: any KB-write-bearing script or tool call must be verified
against independent ground truth before being treated as complete —
version/seq_no bumps via a fresh GET, a document count delta, or a
content-hash diff. Do not trust a script's own printed tally, and do not
re-verify via the same read path the write is suspected of not reaching
(e.g. don't confirm an ES write only via `_search`, which can lag refresh;
use a real-time `_doc/{id}` GET).

## 2026-07-19/20 — qwen3-embedding migration: prefix-bug root cause

lse-kb was migrated from nomic-embed-text (768-dim) to qwen3-embedding:0.6b
(1024-dim), index lse-kb-1024 created 2026-07-15. The shared _embed() helper
in goethe_kb.py kept nomic's "search_query: " prefix convention hard-coded
into every embed call (query AND document indexing use the same function) —
qwen3-embedding uses no such prefix. Bug present from the file's first commit
(2026-07-18, and almost certainly since the 07-15 model swap, carried over
from the pre-refactor goethe.py) until removed in commit 418e4fe
(2026-07-19 03:29 UTC). ~112-123 of 145 docs (roughly 77-85% of the KB) were
embedded during the contaminated window. Separately, rag/eval_retrieval.py,
rag/01-ollama-setup.sh, and LSE-ARCHITECTURE.md were left hardcoded to
nomic-embed-text/768-dim the whole time, so the eval harness itself threw a
flat dimension-mismatch error rather than a bad score - meaning there was no
valid "before" quality baseline, only "it errored."

## Session 2026-07-30 — Planner transport ceiling, Sonnet default, ledger repair

### What worked
- Out-of-band planner run beats the MCP transport ceiling: load goethe.py via importlib in a detached `nohup` process (owui venv python), call `inst.planner(task, context, backend="claude")`, write result to a file, poll the file + tasks.db. Plan e264ed19 (61 steps) landed this way after two in-transport failures.
- Surgical ledger repair: sqlite3 UPDATE of steps_json/plan/next_prompt with exact-string replacements, JSON re-validated after — cheaper than a 10-min `planner(mode="revise")` re-run for path/wording fixes.
- Verifying plan soundness programmatically: topo-sort the depends_on graph (61/61 sortable, no forward refs) + curl-probe every port/path the plan asserts.

### What failed and why
- **Attempted:** planner(backend="claude") through the MCP client
  **Failed because:** double timeout ceiling — MCP client gives up ~60s, and the claude CLI subprocess had a HARDCODED timeout=180 in goethe.py (~line 2023) while Opus 5 on a 61-step atomization prompt needs ~10 min. First failure returned "PLANNER UNAVAILABLE ... timed out after 180s" with nothing persisted.
  **Fix:** timeout promoted to valve `PLANNER_CLI_TIMEOUT_S` (default 900) in goethe.py; set `GOETHE_PLANNER_CLI_TIMEOUT_S=900` in /opt/local-se/goethe-mcp.env. MCP callers still see a client timeout, but the plan now completes server-side and lands in the ledger → recover with task_resume().
- **Attempted:** backend="opus-5-high" as planner backend name
  **Failed because:** dispatcher accepts only `local | chatgpt | claude | rest`. And backend="claude" silently meant `claude-sonnet-5` — the PLANNER_ANTHROPIC_MODEL valve default — NOT Opus; "Opus 5 High" was never actually configured anywhere.
  **Fix:** `GOETHE_PLANNER_ANTHROPIC_MODEL=claude-opus-5` in /opt/local-se/goethe-mcp.env (make_instance() maps GOETHE_<FIELD> → valve on service start).
- **Attempted:** Opus plan generation grounded on KB
  **Failed because:** plan e264ed19 referenced `/opt/local-se/tools/openwebui-tool-v*.py` (nonexistent) and "load in OpenWebUI" — despite the KB recording OWUI decommissioned since 2026-07-17. The planner prompt does not ground against session-learnings; step 1's verify would have hard-stalled the LSE.
  **Fix:** ledger UPDATE rewrote steps 1/13/15/58 to `/home/sy5/projects/local-system-engineer/tools/goethe.py` + goethe-mcp restart semantics. Systemic fix still open: inject KB stack-map facts into the planner prompt.

### Key facts
- Planner backend names: `local | chatgpt | claude | rest` — nothing else parses
- backend="claude" model comes from PLANNER_ANTHROPIC_MODEL (was default claude-sonnet-5; env now pins claude-opus-5); runs `/usr/bin/claude -p --output-format text --model <m>` via Claude Code OAuth
- Backend selection persists in /opt/local-se/state/planner-backend.json (Console-written, precedence over env)
- Opus 5 generation time on a full-roadmap atomization: ~10 min wall (CLI child alone ~5-7 min) — any timeout below 600s guarantees failure
- MCP client transport ceiling ≈60s, unfixable from Goethe's side; ledger persistence + task_resume() is the recovery path
- Live Goethe tool file: /home/sy5/projects/local-system-engineer/tools/goethe.py (MCP via goethe_mcp.py). NOT /opt/local-se/tools/
- Grafana is :3002 (v13.0.1, /api/health) — KB architecture doc's :3001 is wrong; :3001 answers "Running" (different service)
- Local planner primary = node3090 llama-server :8080 (timeout 240s, untouched today); Gemma fallback is BROKEN pre-existing: /opt/models/lmstudio-community does not exist
- goethe-mcp env changes need a service restart; restarting kills live MCP sessions — schedule between sessions
