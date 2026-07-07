---
name: lse-stack-health
description: >
  Pre-session health check for the LSE stack — llama-server, Open WebUI, SearxNG,
  Elasticsearch, Prometheus, and Playwright — with VRAM usage. Invoke when the user
  says "check the stack", "health check", "is the model up", "something seems off",
  or before starting an eval session. If any service is down, surface the exact
  recovery command immediately.
---

# LSE Stack Health Check

Six targeted checks, one combined command, clean status table. If anything is
down, give the exact recovery command — do not say "it may be down."

## Stack Map

| Service       | Host      | Port | Process / container         | Launcher                                         |
|---------------|-----------|------|-----------------------------|--------------------------------------------------|
| llama-server  | localhost | 8080 | `llama-server`              | `lse-stack-launch-1.076.ps1` → model.sh          |
| Open WebUI    | localhost | 3000 | `open-webui serve`          | `lse-stack-launch-1.076.ps1` → webui.sh          |
| SearxNG       | localhost | 8088 | Docker `searxng` container  | `cd /home/sy5/docker && docker compose up -d searxng` |
| Elasticsearch | localhost | 9200 | Docker `elasticsearch`      | `cd /home/sy5/docker && docker compose up -d elasticsearch` |
| Grafana       | localhost | 3002 | Docker `grafana`            | `cd /home/sy5/docker && docker compose up -d grafana` |
| Prometheus    | localhost | 9090 | Docker `prometheus`         | `cd /home/sy5/docker && docker compose up -d prometheus` |
| Playwright    | localhost | 3001 | `playwright run-server`     | `lse-stack-launch-1.076.ps1` → playwright.sh     |

**Port rule: llama-server=8080, SearxNG=8088. NEVER swap them.**
SearxNG container internal port is 8080, Docker NAT maps it to host:8088.

**ES memory**: always via `docker compose up -d` (never bare `docker run`) — mem_limit=2g enforced by compose.

## CHECK SEQUENCE

One combined `execute_command` — no separate calls:

```bash
curl -s -o /dev/null -w 'llama:%{http_code}\n' http://localhost:8080/health \
  && curl -s -o /dev/null -w 'webui:%{http_code}\n' http://localhost:3000 \
  && curl -s -o /dev/null -w 'searxng:%{http_code}\n' http://localhost:8088/ \
  && curl -s -o /dev/null -w 'elasticsearch:%{http_code}\n' http://localhost:9200/_cluster/health \
  && curl -s 'http://localhost:9200/lse-kb,lse-errors,lse-rfc-kb,lse-search-cache,lse-skills/_count' | head -c 300; echo \
  && (curl -s localhost:9090/api/v1/targets | python3 -c "import json,sys; ts=json.load(sys.stdin)['data']['activeTargets']; print('prom-targets: ' + ', '.join(t['labels']['job']+'='+t['health'] for t in ts))" 2>/dev/null || echo 'prom-targets:unreachable') \
  && (curl -s -o /dev/null -w 'playwright:%{http_code}\n' http://localhost:3001 2>/dev/null || echo 'playwright:000') \
  && nvidia-smi --query-gpu=name,memory.used,memory.free,temperature.gpu --format=csv,noheader
```

### ES index probe
The `_count` must list all five indices: `lse-kb`, `lse-errors`, `lse-rfc-kb`, `lse-search-cache`, `lse-skills`.
A missing index returns `index_not_found_exception` → report ❌ and point to reseed procedure:
- Core indices: `rag/02-es-setup.py`
- Skills index: `rag/06-skills-index-setup.py`
- Reseed guide: `kb/kb-reseed-procedure.md`

### Prometheus scrape-target probe
Every job must show `=up`. `searxng=down` → run the canonical repair (idempotent):
```bash
bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/observability/deploy-observability.sh
```
NEVER hand-edit `prometheus.yml` or SearxNG token from memory — canonical config lives in `observability/observability.env`.

## REPORT FORMAT

```
## LSE Stack Health

| Service       | Status  | Detail                               |
|---------------|---------|--------------------------------------|
| llama-server  | ✅ UP   | localhost:8080 → 200                 |
| Open WebUI    | ✅ UP   | localhost:3000 → 200                 |
| SearxNG       | ✅ UP   | localhost:8088 → 200                 |
| Elasticsearch | ✅ UP   | localhost:9200 → 200 · 5 indices OK  |
| Prometheus    | ✅ UP   | all targets=up                       |
| Playwright    | ⚠️ DOWN | localhost:3001 → 000 (non-critical)  |
| VRAM          | ✅ OK   | 20,442 MiB used / 3,301 MiB free · 62°C |

**All critical services up.** Playwright not running — start if browser tools needed.
```

- ✅ UP/OK, ❌ DOWN/error (critical), ⚠️ DOWN (non-critical: Playwright only)
- Critical: llama-server, Open WebUI, SearxNG, Elasticsearch
- One summary line: "All critical services up." or "[N] critical service(s) down — see recovery below."

## RECOVERY COMMANDS

Append a RECOVERY section if anything is down. Never omit it.

### llama-server down
```bash
pgrep -a llama-server  # check for stale process on :8080
bash /home/sy5/.lse/launch/model.sh
# If scripts missing: run lse-stack-launch-1.076.ps1 from PowerShell first
```

### Open WebUI down
```bash
source /home/sy5/owui/bin/activate \
  && OPENAI_API_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=none open-webui serve --port 3000
```

### SearxNG down
```bash
cd /home/sy5/docker && docker compose up -d searxng \
  && sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
```

### Elasticsearch down
```bash
# ALWAYS via compose — bare docker run loses memory limits (OOM on load, exit 143)
cd /home/sy5/docker && docker compose up -d elasticsearch \
  && sleep 10 && curl -s http://localhost:9200/_cluster/health | python3 -m json.tool
```

### Playwright down (non-critical)
```bash
source /home/sy5/owui/bin/activate && playwright run-server --port 3001
```

## GATE

Trigger: "check the stack", "health check", "is the model up", "something seems off", before eval sessions.
Do NOT trigger every turn. Once per session start or on explicit request.
