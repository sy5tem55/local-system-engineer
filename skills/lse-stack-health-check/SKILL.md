---
name: lse-stack-health-check
description: >
  Runs a pre-session health check of the LSE stack — llama-server, Open WebUI,
  SearxNG, and Playwright — and reports per-service status with VRAM usage.
  Use whenever the user says "check the stack", "is everything running",
  "health check", "something seems off", "is the model up", or before running
  an eval session. Also use proactively at session start if any service hasn't
  been verified yet. If a service is down, provide the exact recovery command.
---

# LSE Stack Health Check

Runs five targeted checks and reports a clean status table. If anything is
down, surface the exact recovery command — do not just say "it may be down".

---

## Stack map

| Service       | Port | Process name              | Start script                          |
|---------------|------|---------------------------|---------------------------------------|
| llama-server  | 8080 | `llama-server`            | `/home/sy5/.lse/launch/model.sh`      |
| Open WebUI    | 3000 | `open-webui serve`        | `/home/sy5/.lse/launch/webui.sh`      |
| Playwright    | 3001 | `playwright run-server`   | `/home/sy5/.lse/launch/playwright.sh` |
| SearxNG       | 8088 | Docker container          | `cd /home/sy5/searxng-docker && docker compose up -d searxng` |
| VRAM          | —    | `nvidia-smi`              | —                                     |

Port rule: **8080 = llama-server, 8088 = SearxNG**. Never swap them.

---

## CHECK SEQUENCE

Run all five checks with a single `execute_command` call using `&&`-chained
commands. Do not issue five separate tool calls.

```bash
execute_command(
  "curl -s -o /dev/null -w 'llama:%{http_code}\n' http://localhost:8080/health"
  " && curl -s -o /dev/null -w 'webui:%{http_code}\n' http://localhost:3000"
  " && curl -s -o /dev/null -w 'searxng:%{http_code}\n' http://localhost:8088/"
  " && (curl -s -o /dev/null -w 'playwright:%{http_code}\n' http://localhost:3001 2>/dev/null || echo 'playwright:000')"
  " && nvidia-smi --query-gpu=name,memory.used,memory.free,temperature.gpu --format=csv,noheader"
)
```

Issuing five separate tool calls is a protocol violation.

---

## INTERPRETING RESULTS

### HTTP status codes

| Code | Meaning                  |
|------|--------------------------|
| 200  | Service up and healthy   |
| 000  | Connection refused — service not running |
| 5xx  | Service up but unhealthy |

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

| Service      | Status | Detail                          |
|--------------|--------|---------------------------------|
| llama-server | ✅ UP  | localhost:8080 → 200            |
| Open WebUI   | ✅ UP  | localhost:3000 → 200            |
| SearxNG      | ✅ UP  | localhost:8088 → 200            |
| Playwright   | ⚠️ DOWN | localhost:3001 → 000 (not started) |
| VRAM         | ✅ OK  | 20,442 MiB used / 3,301 MiB free · 62°C |

**All critical services up.** Playwright not running — start if browser tools needed.
```

Use ✅ for UP/OK, ❌ for DOWN/error, ⚠️ for non-critical services (Playwright).
Playwright is non-critical — flag it but do not treat it as a blocker.
llama-server, Open WebUI, and SearxNG are critical — ❌ if any of these are down.

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
exist at `/home/sy5/.lse/launch/` — advise running `lse-stack-launch.ps1` from PowerShell.

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
cd /home/sy5/searxng-docker && docker compose up -d searxng
# verify:
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
# expected: 200
```

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
