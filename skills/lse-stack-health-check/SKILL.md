---
name: lse-stack-health-check
description: >
  Runs a pre-session health check of the LSE stack — llama-server, Open WebUI,
  SearxNG, Elasticsearch, and Playwright — and reports per-service status with VRAM usage.
  Use whenever the user says "check the stack", "is everything running",
  "health check", "something seems off", "is the model up", or before running
  an eval session. Also use proactively at session start if any service hasn't
  been verified yet. If a service is down, provide the exact recovery command.
---

# LSE Stack Health Check

Runs six targeted checks and reports a clean status table. If anything is
down, surface the exact recovery command — do not just say "it may be down".

---

## Stack map

| Service       | Port | Process name              | Start script                          |
|---------------|------|---------------------------|---------------------------------------|
| llama-server  | 8080 | `llama-server`            | `/home/sy5/.lse/launch/model.sh`      |
| Open WebUI    | 3000 | `open-webui serve`        | `/home/sy5/.lse/launch/webui.sh`      |
| Playwright    | 3001 | `playwright run-server`   | `/home/sy5/.lse/launch/playwright.sh` |
| SearxNG       | 8088 | Docker container          | `cd /home/sy5/docker && docker compose up -d searxng` |
| Elasticsearch | 9200 | Docker container          | `cd /home/sy5/docker && docker compose up -d elasticsearch` |
| VRAM          | —    | `nvidia-smi`              | —                                     |

Port rule: **8080 = llama-server (WSL-local only), 8088 = SearxNG external**. Never swap them.
SearxNG internal container port is 8080, mapped to host 8088 (compose: `8088:8080`).

**Current build:** llama.cpp b9464 (`5dcb71166`). Launcher: v1.076 (XML profiles).

**Elasticsearch** is managed via `/home/sy5/docker/docker-compose.yml` with
`mem_limit: 2g` and `mem_reservation: 1g` (heap capped at 1g via ES_JAVA_OPTS).
Do NOT start it with a bare `docker run` — memory limits will be lost and ES
will OOM-kill under load (exit code 143).

---

## CHECK SEQUENCE

Run all checks with a single `execute_command` call using `&&`-chained
commands. Do not issue separate tool calls.

```bash
execute_command(
  "curl -s -o /dev/null -w 'llama:%{http_code}\n' http://localhost:8080/health"
  " && curl -s -o /dev/null -w 'webui:%{http_code}\n' http://localhost:3000"
  " && curl -s -o /dev/null -w 'searxng:%{http_code}\n' http://localhost:8088/"
  " && curl -s -o /dev/null -w 'elasticsearch:%{http_code}\n' http://localhost:9200/_cluster/health"
  " && curl -s 'http://localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache,lse-skills/_count' | head -c 200; echo"
  " && (curl -s localhost:9090/api/v1/targets | python3 -c \"import json,sys; ts=json.load(sys.stdin)['data']['activeTargets']; print('prom-targets: ' + ', '.join(t['labels']['job']+'='+t['health'] for t in ts))\" 2>/dev/null || echo 'prom-targets:unreachable')"
  " && (curl -s -o /dev/null -w 'playwright:%{http_code}\n' http://localhost:3001 2>/dev/null || echo 'playwright:000')"
  " && nvidia-smi --query-gpu=name,memory.used,memory.free,temperature.gpu --format=csv,noheader"
)
```

### ES index probe (P21 addition)
The `_count` line must list ALL FIVE indices. An index that was lost (e.g. the
2026-06-08 es-data volume cascade) returns a 404 `index_not_found_exception` in
that line — report it as ❌ and point to `rag/02-es-setup.py` (core indices) /
`rag/06-skills-index-setup.py` (lse-skills) / `kb/kb-reseed-procedure.md`.

### Prometheus scrape-target probe (P22 addition)
Every job must show `=up`. `searxng=down` or `searxng` absent → run the
single-source-of-truth repair (idempotent, verifies end-to-end):
```bash
bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/observability/deploy-observability.sh
```
NEVER hand-edit prometheus.yml or settings.yml tokens from memory — the
canonical token/paths live in `observability/observability.env` (P22 lesson:
three stale token variants in old docs caused a 401 hunt).

Issuing separate tool calls is a protocol violation.

---

## INTERPRETING RESULTS

### HTTP status codes

| Code | Meaning                  |
|------|--------------------------|
| 200  | Service up and healthy   |
| 000  | Connection refused — service not running |
| 5xx  | Service up but unhealthy |

### Elasticsearch health
A 200 from `/_cluster/health` means ES is up. For a quick sanity check of
cluster state, the response body will contain `"status":"green"` (healthy),
`"status":"yellow"` (single-node, normal), or `"status":"red"` (shards missing).

### VRAM interpretation (RTX 4090, 24 GB total)

| Used      | State                                              |
|-----------|----------------------------------------------------|
| < 1 GB    | llama-server not loaded — model not running        |
| 18–22 GB  | Normal — 32k ctx profile loaded                    |
| 22–24 GB  | Normal — 64k ctx profile loaded (some CPU KV spill)|
| > 24 GB   | Unexpected — report the raw figure                 |

---

## REPORT FORMAT

Always produce a status table in exactly this format:

```
## LSE Stack Health

| Service       | Status | Detail                          |
|---------------|--------|---------------------------------|
| llama-server  | ✅ UP  | localhost:8080 → 200            |
| Open WebUI    | ✅ UP  | localhost:3000 → 200            |
| SearxNG       | ✅ UP  | localhost:8088 → 200            |
| Elasticsearch | ✅ UP  | localhost:9200 → 200 (green)    |
| Playwright    | ⚠️ DOWN | localhost:3001 → 000 (not started) |
| VRAM          | ✅ OK  | 20,442 MiB used / 3,301 MiB free · 62°C |

**All critical services up.** Playwright not running — start if browser tools needed.
```

Use ✅ for UP/OK, ❌ for DOWN/error, ⚠️ for non-critical services (Playwright).
Playwright is non-critical — flag it but do not treat it as a blocker.
llama-server, Open WebUI, SearxNG, and Elasticsearch are critical — ❌ if any are down.

After the table, write one summary line: either "All critical services up." or
"[N] critical service(s) down — see recovery below."

---

## RECOVERY COMMANDS

If a service is down, append a RECOVERY section immediately after the table.
Do not omit the recovery commands — the user needs to know the exact fix.

### llama-server down
```bash
# Check if a stale process is holding port 8080
pgrep -a llama-server
# Start via launcher tab (preferred) or manually:
bash /home/sy5/.lse/launch/model.sh
```
Note: if the launcher hasn't been run yet this session, the scripts may not
exist at `/home/sy5/.lse/launch/` — advise running `lse-stack-launch-1.076.ps1` from
PowerShell (`C:\Users\SY5\Claude\Projects\LSEStack_gui\lse-stack-launch-1.076.ps1`).
Model profiles are loaded from `lse-profiles.xml` in the same folder — edit that file
to add or modify profiles, not the launcher script.

### Open WebUI down
```bash
bash /home/sy5/.lse/launch/webui.sh
# or manually:
source /home/sy5/owui/bin/activate
OPENAI_API_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=none \
  open-webui serve --port 3000
```

### SearxNG down
```bash
cd /home/sy5/docker && docker compose up -d searxng
# verify:
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
# expected: 200
```

### Elasticsearch down
```bash
# ALWAYS start via Compose — never bare docker run (limits will be lost)
cd /home/sy5/docker && docker compose up -d elasticsearch
# verify:
sleep 10 && curl -s http://localhost:9200/_cluster/health | python3 -m json.tool
# expected: status green or yellow, no red
```
If ES exits immediately after starting, check for OOM: `dmesg | tail -20 | grep -i oom`
Memory limits: mem_limit=2g, mem_reservation=1g, heap=-Xms512m -Xmx1g

### Playwright down (non-critical)
```bash
bash /home/sy5/.lse/launch/playwright.sh
# or manually:
source /home/sy5/owui/bin/activate
playwright run-server --port 3001
```

### VRAM critically low (< 500 MiB free)
```bash
# Check what's holding VRAM:
nvidia-smi
# If a zombie llama-server process exists:
pgrep -a llama-server
kill <PID>
```

---

## GATE

Call this skill when the user asks about stack status, before starting an eval
session, or when a tool call fails in a way that suggests a service is unreachable.
Do NOT call this every turn — only on explicit request or at session start.
