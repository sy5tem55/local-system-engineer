# LSE Stack Troubleshooting Guide

**Audience:** Models (Qwen3.6, Gemma) and humans diagnosing LSE failures.
**Method:** Start with observation, determine root cause, apply the minimum fix, verify.
**Rule:** Never restart what you haven't confirmed is broken. Never restart what is already working.

---

## 0. Mental Model: What Is the Stack?

The LSE stack has two layers. Understanding the boundary prevents misdiagnosis.

**Layer A — Docker containers** (managed by `docker compose`):
Grafana, Prometheus, Elasticsearch, Open WebUI, Vaultwarden, SearxNG,
node-exporter, searxng-error-exporter, nginx, OpenWebUI pipelines.

All container data is **bind-mounted to `/home/sy5/docker/`** on the host.
Container removal never deletes user data. The `es-data` Elasticsearch volume
is the sole exception — it is a named Docker volume and is lost on full Docker reset.

**Layer B — Host-side processes** (plain `nohup python3` in WSL2):
echarts_topology.py (port 8766), prometheus_exporter.py / netobs (9120),
download-speed-exporter (9838), llamacpp-slots-exporter (9839),
llama-context-exporter (9836), nvidia-gpu-exporter (9835).

These are NOT managed by Docker. WSL2 restart kills them all. Docker restart does not affect them.

**Layer C — Remote nodes** (SSH / LM Studio):
node3090 llama-server or LM Studio (port 1234 or 8080).
LUCIFER llama-server (port 8080) — Worker/Verifier for the pipeline.

---

## 1. Quick Triage: What Is Actually Wrong?

Before touching anything, run this triage sequence. It takes 30 seconds and tells you exactly which layer is broken.

```bash
# 1a. Is Docker running?
docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | head -15 \
  || echo "DOCKER DAEMON NOT RUNNING"

# 1b. Are host exporters running? (Layer B)
ss -tlnp | grep -E "8766|9120|9835|9836|9838|9839" | awk '{print $4}' \
  || echo "NO HOST EXPORTERS LISTENING"

# 1c. Is llama-server running on LUCIFER? (Layer C)
curl -sf http://localhost:8080/health && echo "llama-server UP" || echo "llama-server DOWN"

# 1d. What does Prometheus see? (cross-checks Layers B and C)
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json, sys
for t in json.load(sys.stdin)['data']['activeTargets']:
    print(t['labels'].get('job','?').ljust(28), t['health'],
          ('  — ' + t.get('lastError',''))[:60] if t['health']!='up' else '')
"
```

Match the output to a section below.

---

## 2. Docker Daemon Not Running

**Observation:** `docker ps` returns `Cannot connect to the Docker daemon` or `Is the docker daemon running?`

**Root cause:** The Docker daemon (`dockerd`) is not started. In WSL2, dockerd does not start automatically on reboot unless a startup script is configured.

**Fix:**
```bash
sudo dockerd > /tmp/dockerd.log 2>&1 &
sleep 5   # wait for socket creation — docker ps fails if you skip this
docker ps
```

**Verify:** `docker ps` returns a table (even if empty) without an error.

**If it still fails after sleep 5:**
```bash
tail -20 /tmp/dockerd.log   # look for "failed to start containerd" or storage errors
```
→ Storage errors mean overlay2 corruption. See Section 3.

---

## 3. Docker Containers Won't Start — overlay2 Corruption

**Observation:** `docker start <name>` returns one of:
- `Error response from daemon: RWLayer is unexpectedly nil`
- `parent snapshot does not exist`
- `layer does not exist`

**Root cause:** WSL2 was killed while Docker was running (Windows sleep, hibernate, or forced shutdown). The containerd content store was left in an inconsistent state. The overlay2 filesystem layer references are broken.

**Critical rule:** Do NOT run `docker start` on individual containers. It will partially succeed and leave the stack in a mixed broken/working state. Prune everything first.

**Fix sequence — follow exactly in order:**

```bash
# Step 1: confirm daemon is running
docker ps 2>/dev/null || { sudo dockerd > /tmp/dockerd.log 2>&1 & sleep 5; }

# Step 2: remove all dead containers (data is safe — it's on bind mounts)
docker container prune -f

# Step 3: clear corrupted build cache and dangling images
docker system prune -f

# Step 4: recreate all containers
cd /home/sy5/docker
docker compose up -d

# Step 5: if any image fails with "manifest unknown" or pull errors — check DNS
cat /etc/resolv.conf   # must show 10.255.255.254 or 192.168.1.50, not ::1
```

**If `docker compose up -d` still fails on a specific image:**
```bash
docker compose pull <service>   # force-pull the base image
docker compose up -d <service>
```

**Verify:**
```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -v "Up"
# Should be empty (all containers Up). Any "Exited" rows need investigation.
```

**Post-recovery check — Elasticsearch named volume:**
```bash
docker volume ls | grep es-data || {
    echo "es-data volume missing — recreating"
    docker volume create es-data
    docker compose up -d elasticsearch
}
```

---

## 4. resolv.conf Lost / DNS Broken

**Observation:** `ping google.com` fails, `nslookup pfsense.home.arpa` fails, or Docker image pulls fail with DNS errors.

**Root cause:** WSL2 regenerates `/etc/resolv.conf` on restart if `generateResolvConf = false` in `/etc/wsl.conf` was lost or overwritten. The default WSL2 resolv.conf contains only `nameserver ::1` which is broken.

**Diagnosis:**
```bash
cat /etc/resolv.conf
# Broken: nameserver ::1
# Correct: nameserver 10.255.255.254 + nameserver 192.168.1.50
```

**Fix:**
```bash
echo -e "nameserver 10.255.255.254\nnameserver 192.168.1.50\nsearch home.arpa" \
  | sudo tee /etc/resolv.conf

# Confirm wsl.conf prevents future overwrites
grep "generateResolvConf" /etc/wsl.conf || \
  echo -e "[network]\ngenerateResolvConf = false" | sudo tee -a /etc/wsl.conf
```

**Verify:**
```bash
ping -c1 google.com && ping -c1 pfsense.home.arpa
```

---

## 5. Grafana Shows "No Data" — Dashboards Are Blank

This is the most common symptom and has four distinct root causes. Work through them in order.

### 5a. Topology map is blank

**Root cause:** `echarts_topology.py` (the topology API on port 8766) was killed by WSL2 restart.

**Diagnosis:**
```bash
curl -s http://localhost:8766/topology | python3 -c \
  "import json,sys; print('nodes:', len(json.load(sys.stdin)['nodes']))" \
  2>/dev/null || echo "topology API not running"
```

**Fix:**
```bash
nohup python3 /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery/echarts_topology.py \
  > /tmp/lse-exporters/topology.log 2>&1 &
sleep 2
curl -s http://localhost:8766/topology | python3 -c \
  "import json,sys; print('nodes:', len(json.load(sys.stdin)['nodes']))"
```

Then Ctrl+Shift+R in Grafana to hard-refresh the Network Topology dashboard.

### 5b. Metric dashboards blank — Prometheus targets down

**Root cause:** Host-side exporters (ports 9838, 9839, 9836, 9835, 9120) were killed by WSL2 restart.

**Diagnosis:**
```bash
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json,sys
for t in json.load(sys.stdin)['data']['activeTargets']:
    if t['health'] != 'up':
        print('DOWN:', t['labels']['job'], '—', t.get('lastError','')[:80])
"
```

If you see `connection refused` on `172.17.0.1:983x` — these are host exporters that need restarting.

**Fix:**
```bash
bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/restart_exporters.sh
```

Allow 30–60 seconds for Prometheus to scrape the newly-started exporters. Then check Grafana — the graphs will show data from the point the exporters restarted; historical data before the WSL2 restart is in the bind-mounted Prometheus TSDB and should reappear.

### 5c. Grafana datasource not found error in browser console

**Observation:** F12 console shows `Datasource ${DS-INFINITY} was not found` or `Datasource uid: xyz not found`.

**Root cause:** A provisioned dashboard is referencing a datasource by UID that was created under a different Grafana instance (e.g., after a full Docker reset).

**Diagnosis:**
```bash
# List current datasources and their UIDs
curl -s -u admin:LSEgrafana2026 http://localhost:3002/api/datasources \
  | python3 -m json.tool | grep -E '"name"|"uid"'
```

**Fix:** The topology dashboard does not use any external datasource — it fetches from the topology API directly via JavaScript. If the topology dashboard shows this error, it means an old provisioned version is still cached. Update it:
```bash
python3 /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/net-discovery/push_topology_dashboard.py \
  --pass LSEgrafana2026
```

### 5d. Grafana itself has no dashboards

**Observation:** The Grafana dashboard list at `http://localhost:3002/dashboards` is empty.

**Root cause (unlikely but possible):** Grafana's SQLite database at `./grafana/data/grafana.db` was deleted or corrupted. This database is bind-mounted from `/home/sy5/docker/grafana/data/` and survives Docker container restarts.

**Diagnosis:**
```bash
ls -lh /home/sy5/docker/grafana/data/grafana.db
curl -s -u admin:LSEgrafana2026 http://localhost:3002/api/dashboards/home \
  | python3 -m json.tool | head -10
```

**Fix (if database is intact but Grafana can't read it):**
```bash
docker restart grafana
sleep 5
curl -s -u admin:LSEgrafana2026 http://localhost:3002/api/search | python3 -m json.tool | grep title
```

**Fix (if database is genuinely lost):** Restore from backup:
```bash
python3 /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/backup_grafana_dashboards.py
# This saves all dashboard JSON to grafana-dashboards/
# Reverse: import each JSON via Grafana UI → Dashboards → Import
```

---

## 6. llama-server Not Running (Pipeline Fails)

**Observation:** `lse_task.sh` exits with `llama-server is not running at http://localhost:8080`.

**Diagnosis:**
```bash
curl -sf http://localhost:8080/health && echo "up" || echo "down"
# If down:
ps aux | grep llama-server | grep -v grep
```

**Fix — restart Qwen3.6 Worker on LUCIFER:**
```bash
# Check VRAM is free first
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader

# Start llama-server (adjust model path and ctx as needed)
nohup llama-server \
  -m /path/to/Qwen3.6-27B-Q4_K_M.gguf \
  -c 96000 -ngl 129 --flash-attn \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --parallel 1 -t 7 -tb 7 \
  --reasoning-budget 3072 --n-predict 8192 \
  --jinja --metrics --port 8080 --host 0.0.0.0 \
  > /tmp/llama-server.log 2>&1 &

sleep 10
curl -sf http://localhost:8080/health
```

**For node3090 Planner (LM Studio on port 1234):**
```bash
# Check reachability
ping -c1 192.168.5.41

# Check LM Studio API
curl -sf http://192.168.5.41:1234/v1/models | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])" \
  2>/dev/null || echo "LM Studio not running — start it manually on node3090"
```

LM Studio must be started manually on node3090. It is not scriptable from LUCIFER.

---

## 7. Prometheus Scrape Target Permanently Down

**Observation:** A Prometheus target shows `health: down` with `connection refused` but `restart_exporters.sh` says it started successfully, yet the target stays down.

**Root cause candidates (in order):**
1. The exporter started but crashed immediately — check the log.
2. The exporter is bound to `127.0.0.1` instead of `0.0.0.0` — Docker bridge (`172.17.0.1`) can only reach the host on `0.0.0.0`.
3. Prometheus config references the wrong port.

**Diagnosis:**
```bash
# Check which interface the exporter actually bound
ss -tlnp | grep "<port>"
# Should show 0.0.0.0:<port>  not  127.0.0.1:<port>

# Read the exporter log
cat /tmp/lse-exporters/<name>.log | tail -20

# Check Prometheus config for this job
grep -A5 "job_name.*<name>" \
  /sessions/exciting-amazing-bohr/mnt/local-system-engineer/prometheus/prometheus.yml
```

**Fix:** If bound to 127.0.0.1, the exporter script needs `server_address = ('0.0.0.0', PORT)`. This is a code fix, not a restart fix.

---

## 8. lse_task.sh Pipeline Errors

### Planner output is not valid JSON

**Root cause:** The Planner LLM (Gemma or Qwen) returned a fenced code block, markdown prose, or a thinking block instead of raw JSON.

**Fix options (try in order):**
1. Re-run with `--skip-planner` to bypass the Planner and use a manual task spec.
2. Confirm LM Studio on node3090 is using Gemma-4-26B-A4B, not a 4B variant — 4B reliably fails JSON schema compliance.
3. Check that the `PLANNER_URL` in `lse_task.sh` points to LM Studio (`http://192.168.5.41:1234`), not the local llama-server.

### Pipeline exits with "task is empty"

**Root cause:** The `--task` argument was not passed, or positional arguments were used instead of named flags.

**Correct invocation:**
```bash
./lse_task.sh \
  --task "Describe what you want done" \
  --files path/to/file1.py path/to/file2.json \
  --target path/to/file1.py
```

### Worker returns empty content

**Root cause:** Qwen3.6 with `reasoning_budget: 0` in the payload produces 0 content tokens. The thinking block is routed to `reasoning_content`; `content` is empty.

**Diagnosis:** Check `lse_agent.py` — the `run_worker()` call must read `msg.get("content") or msg.get("reasoning_content", "")`.

**Fix:** Remove `reasoning_budget` from the payload entirely, or ensure `lse_agent.py` has the reasoning_content fallback.

---

## 9. Edit Tool Corrupts Python Files (NTFS)

**Observation:** A Python file was edited with the Edit tool, now it has a syntax error or ends mid-line.

**Root cause:** The Edit tool silently truncates large Python files on NTFS, especially at emoji characters (e.g., `🔄`, U+1F504). No error is reported.

**Rule:** Never use the Edit tool on `.py` files larger than 100 lines stored on NTFS. Use `bash cat << 'PYEOF'` heredoc instead.

**Fix — rewrite the file via heredoc:**
```bash
cat << 'PYEOF' > /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/<path>
<complete file contents here>
PYEOF

# Always verify syntax immediately
python3 -c "import ast; ast.parse(open('<path>').read()); print('syntax OK')"
```

**Fix — Python string-replace patch for targeted edits:**
```python
path = "/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/<file>.py"
with open(path) as f: src = f.read()
src = src.replace(
    "old string to replace",
    "new string",
    1   # replace only first occurrence
)
with open(path, "w") as f: f.write(src)
import ast; ast.parse(src)  # raises SyntaxError if corrupted
```

---

## 10. Git Commit Fails from Cowork Sandbox

**Observation:** `git commit` from the Cowork bash tool returns permission errors, lock file errors, or silently does nothing.

**Root cause:** The sandbox cannot reliably write NTFS git metadata. `.git/index.lock` may be left behind.

**Fix:** Always run git operations from a WSL terminal, not from the Cowork bash tool.
```bash
# In WSL terminal (not Cowork bash):
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
git add -A
git commit -m "fix: <description>"
```

If `.git/index.lock` exists:
```bash
rm -f .git/index.lock
git status   # should now work
```

---

## Quick Reference: Port Map

| Port  | Service                  | Layer  | Restart command |
|-------|--------------------------|--------|-----------------|
| 3002  | Grafana                  | Docker | `docker restart grafana` |
| 8080  | llama-server (Worker)    | Host   | `nohup llama-server ... &` |
| 8088  | SearxNG                  | Docker | `docker restart searxng` |
| 8766  | Topology API             | Host   | `restart_exporters.sh` |
| 9090  | Prometheus               | Docker | `docker restart prometheus` |
| 9100  | node-exporter            | Docker | `docker restart node-exporter` |
| 9120  | netobs exporter          | Host   | `restart_exporters.sh` |
| 9200  | Elasticsearch            | Docker | `docker restart elasticsearch` |
| 9835  | nvidia-gpu exporter      | Host   | `restart_exporters.sh` |
| 9836  | llama-context-exporter   | Host   | `restart_exporters.sh` |
| 9837  | searxng-error-exporter   | Docker | `docker restart searxng-error-exporter` |
| 9838  | download-speed exporter  | Host   | `restart_exporters.sh` |
| 9839  | llamacpp-slots exporter  | Host   | `restart_exporters.sh` |
| 1234  | LM Studio (node3090)     | Remote | Manual — start on node3090 |

**Single command to recover all host exporters after WSL2 restart:**
```bash
bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/scripts/restart_exporters.sh
```
