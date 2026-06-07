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
