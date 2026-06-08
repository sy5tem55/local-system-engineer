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
