# LSE Operations Runbook

**Date:** 2026-05-25  
**Covers:** Stack start, health checks, model profiles, recovery procedures, tool hot-swap, and session shutdown.

---

## 1. Stack overview

The LSE stack is five services running simultaneously, each in a dedicated Windows Terminal tab. The launcher script (`lse-stack-launch-1.06.ps1`) starts all five with colour-coded tabs in a single invocation.

| Tab colour | Service | Port | Critical? |
|---|---|---|---|
| 🔴 Red | llama-server (Qwen3.6-27B) | 8080 | Yes — inference engine |
| 🔵 Blue | Open WebUI | 3000 | Yes — UI + tool dispatch |
| 🟣 Purple | Playwright browser server | 3001 | No — only needed for browser tools |
| 🟠 Orange | Open Terminal | — | No — optional UI |
| 🟢 Green | LSE Terminal (bash) | — | No — general shell access |

**Port rule (do not swap):** 8080 = llama-server · 8088 = SearxNG · 3000 = Open WebUI · 3001 = Playwright

SearxNG runs as a Docker container and is not launched by the launcher script — it starts automatically if Docker is already running. If it isn't up, see §4.

---

## 2. Starting the stack

### Normal start (launcher script)

Open PowerShell and run:

```powershell
cd "C:\Users\SY5\Documents\Claude\Projects\local-system-engineer"
.\lse-stack-launch-1.06.ps1
```

The launcher shows a profile menu. Select a profile (or press Enter for the default 32k profile). Windows Terminal opens with all five tabs.

**Watch the red tab.** llama-server takes 25–40 seconds to load the model into VRAM. It is ready when it prints:

```
llama server listening at http://0.0.0.0:8080
```

Open WebUI (blue tab) may show connection errors until llama-server is ready — this is expected.

### Start order if launching manually

If the launcher script isn't available, start services in this order:

1. **llama-server** (must be first — WebUI needs the backend)
2. **Open WebUI**
3. **SearxNG** (if not auto-started by Docker)
4. **Playwright** (only if browser tools are needed)

Manual llama-server start (32k default profile):
```bash
/home/sy5/llama.cpp/build/bin/llama-server \
  --model /home/sy5/models/Qwen3.6-27B-Q5_K_M.gguf \
  --ctx-size 32768 \
  --n-gpu-layers 99 \
  --flash-attn on \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --parallel 1 \
  --jinja \
  --threads 8 \
  --reasoning-budget 3072 \
  -n 8192 \
  --host 0.0.0.0 \
  --port 8080
```

---

## 3. Model profiles

The launcher offers three profiles. Choose based on the expected session:

### 32k context — default
```
CtxSize: 32768 · CacheTypeK: q8_0 · CacheTypeV: q8_0
ReasoningBudget: 3072 · MaxTokens: 8192
VRAM usage: ~20–22 GB (fits cleanly on RTX 4090)
```
Use for: standard LSE sessions, eval runs, most development work. The KV cache fits entirely in VRAM with no CPU spillover.

### 64k context
```
CtxSize: 65536 · same KV quant settings
VRAM usage: ~22–24 GB (last ~2 GB of KV spills to CPU RAM)
```
Use for: long sessions with large files, multi-file diffs, or when context handover is impractical. Expect slightly slower generation near the end of a full context due to CPU KV access.

### No-thinking (fast)
```
ReasoningBudget: 0 · MaxTokens: 4096
```
Use for: quick factual lookups, file reads, eval scoring runs where reasoning isn't needed. Roughly 2× faster token generation. Note: `--reasoning-budget 0` suppresses the `<think>` block entirely, so the LSE cannot self-correct using chain-of-thought. Avoid for complex multi-step tasks.

### VRAM budget reference (RTX 4090, 24 GB total)

| Used | Interpretation |
|---|---|
| < 1 GB | llama-server not loaded — model not running |
| 18–22 GB | Normal — 32k ctx profile |
| 22–24 GB | Normal — 64k ctx profile (some CPU KV spill near limit) |
| > 24 GB | Unexpected — check for zombie processes |

Check VRAM live:
```bash
nvidia-smi --query-gpu=name,memory.used,memory.free,temperature.gpu --format=csv,noheader
```

---

## 4. Pre-session health check

Before starting any LSE session or eval run, verify all critical services are up. Use the `lse:stack-health-check` skill, or run this manually from the green terminal tab:

```bash
curl -s -o /dev/null -w 'llama:%{http_code}\n' http://localhost:8080/health \
  && curl -s -o /dev/null -w 'webui:%{http_code}\n' http://localhost:3000 \
  && curl -s -o /dev/null -w 'searxng:%{http_code}\n' http://localhost:8088/ \
  && (curl -s -o /dev/null -w 'playwright:%{http_code}\n' http://localhost:3001 2>/dev/null || echo 'playwright:000') \
  && nvidia-smi --query-gpu=name,memory.used,memory.free,temperature.gpu --format=csv,noheader
```

Expected healthy output:
```
llama:200
webui:200
searxng:200
playwright:200   (or 000 if not started — non-critical)
NVIDIA GeForce RTX 4090, 20442 MiB, 3301 MiB, 58
```

---

## 5. Recovery procedures

### llama-server down (red tab, port 8080)

**Symptoms:** `llama:000` from health check. Open WebUI shows "connection error".

```bash
# Check if process exists but port is wrong
pgrep -a llama-server

# If no process: start via launcher tab
bash /home/sy5/.lse/launch/model.sh

# If stale process is holding the port: kill it first
kill <PID>
# then restart
bash /home/sy5/.lse/launch/model.sh
```

If the launcher scripts don't exist (first run, or `/home/sy5/.lse/launch/` was cleaned), re-run `lse-stack-launch-1.06.ps1` from PowerShell — it writes the scripts before opening the tabs.

### Open WebUI down (blue tab, port 3000)

**Symptoms:** `webui:000`. Browser shows nothing at localhost:3000.

```bash
bash /home/sy5/.lse/launch/webui.sh

# or manually:
source /home/sy5/owui/bin/activate
OPENAI_API_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=none \
  open-webui serve --port 3000
```

### SearxNG down (Docker, port 8088)

**Symptoms:** `searxng:000`. Web search tool calls return no results.

```bash
cd /home/sy5/searxng-docker && docker compose up -d searxng

# verify after ~5 seconds:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
# expected: 200
```

If Docker itself isn't running, start it from Windows first (Docker Desktop or the service).

**SearxNG config reminder:** `suspended_times` must live under `search:` in `settings.yml`, not under `outgoing:`. Keys are Python exception class names (`SearxEngineTooManyRequests`, not `"HTTP error [429]"`). See `/opt/local-se/kb/session-learnings.md` for the full incident record.

### Playwright down (purple tab, port 3001)

Non-critical — only affects browser automation tools. Skip if not needed this session.

```bash
bash /home/sy5/.lse/launch/playwright.sh

# or manually:
source /home/sy5/owui/bin/activate
playwright run-server --port 3001
```

### llama-server OOM / VRAM exhausted

**Symptoms:** llama-server exits unexpectedly, red tab shows OOM error, `nvidia-smi` shows process gone.

1. Check the exit message in the red tab for the cause (most common: model too large for ctx-size + quant combination).
2. Restart with the 32k profile instead of 64k, or switch to `q4_0` KV quant to halve KV cache VRAM.
3. If VRAM isn't fully released after the process exits, check for zombie processes:
   ```bash
   pgrep -a llama-server
   kill <PID>   # if found
   nvidia-smi   # verify VRAM drops back to baseline (~300 MiB)
   ```

### Slow generation / high latency

1. Check context fill — if the session is near context limit, generation slows due to attention over the full KV cache. Run `get_context_status()` in the LSE session.
2. Check for CPU KV spill — 64k profile near capacity will spill KV to CPU RAM, adding latency. Consider starting a fresh session.
3. Check VRAM temperature — sustained >80°C can trigger GPU throttling. `nvidia-smi` shows temperature.

---

## 6. Safely hot-swapping a tool version in Open WebUI

Hot-swapping means replacing the active tool version without restarting Open WebUI. The model session continues uninterrupted.

**Steps:**

1. In Open WebUI: Settings → Tools → find the active LSE tool → click the edit (pencil) icon.
2. Select all the content and replace it with the new tool version's Python code.
3. Click Save.
4. **Verify:** Open a new chat. Type a simple command (e.g. `what's the current date?`). Confirm the tool responds — if `execute_command` fires, the new tool is active.

**What does NOT require a restart:** Tool docstring changes, new tool version Python code.  
**What DOES require a restart:** Filter changes (`lse-routing-filter-v*.py`), context monitor changes, OpenWebUI configuration changes.

**Filter hot-swap:**
1. Settings → Functions → find the active LSE routing filter → edit → replace → save.
2. No OpenWebUI restart needed for filter content changes (filters are re-evaluated per request).

**Never hot-swap the tool while an eval run is in progress** — tool changes take effect immediately and will invalidate results mid-run.

---

## 7. Deploying a new tool version (formal)

When shipping a new versioned release (e.g. v1.5.5):

1. Write the new tool file to `tools/openwebui-tool-vX.Y.Z.py`.
2. Run `lse:docstring-optimizer` on any changed functions before deploying.
3. Hot-swap in Open WebUI (see §6).
4. Run a quick smoke test: stack health check + one sudo delegation check.
5. If a full eval run confirms the version is working, log it with `lse:version-manager`.
6. Commit the file and run `lse:version-manager` to update `VERSION.md` and `prompts/CHANGELOG.md`.

Do not delete old tool files — they are the version history.

---

## 8. Session shutdown

### Normal shutdown

Close Windows Terminal. All five tabs will terminate their processes cleanly when the tab closes.

**SearxNG does not auto-stop** — it runs as a Docker container and persists after Terminal closes. Stop it explicitly if needed:
```bash
cd /home/sy5/searxng-docker && docker compose stop searxng
```

### Before rebuilding llama.cpp

llama-server must be stopped before rebuilding the binary. The model is the active inference engine — rebuilding mid-session terminates the current model and corrupts the binary if the process is writing to it.

**Never run `make` or `cmake --build` while llama-server is running.**

Stop sequence:
1. In Open WebUI: close any active chat that might trigger a tool call.
2. In the red tab: press `Ctrl+C` to send SIGINT. Wait for the graceful shutdown message.
3. Verify: `pgrep -a llama-server` → should return nothing.
4. Then run the build.

---

## 9. Context Alert Pipeline (Prometheus + Grafana → OpenWebUI)

Context monitoring is handled externally — the model does not track its own fill. A Grafana alert fires when KV cache usage exceeds 80% and posts a message to the `lse-alerts` OpenWebUI channel.

### Services

Two systemd services run permanently on the WSL2 host:

| Service | Script | Port | Purpose |
|---|---|---|---|
| `llama-context-exporter` | `/opt/local-se/llama-context-exporter.py` | 9836 | Queries llama-server `/slots` + `/metrics`, exposes `llama_kv_cache_usage_ratio` and `llama_context_size` |
| `grafana-owui-adapter` | `/opt/local-se/grafana-owui-adapter.py` | 9837 | Receives Grafana alert JSON, converts to `{"content":"..."}`, POSTs to OpenWebUI channel webhook |

### Infrastructure

| Component | Location | Config |
|---|---|---|
| Prometheus | Docker container `prometheus` | `/home/sy5/docker/prometheus/prometheus.yml` |
| Grafana | Docker container `grafana` | `http://localhost:3002` |
| Alert rule | Grafana folder `LSE` | `LSE Context Fill > 80%` — `llama_kv_cache_usage_ratio > 0.8`, for=1m |
| Contact point | Grafana | `OpenWebUI LSE Alerts` → `http://172.17.0.1:9837` |
| Channel webhook | OpenWebUI channel `lse-alerts` | Created under channel settings → Webhooks |

### How it works

```
llama-server :8080/slots  →  n_ctx (32768 or 65536, dynamic per profile)
llama-server :8080/metrics →  llamacpp:n_tokens_max (current KV tokens)
        ↓
llama-context-exporter :9836
  llama_kv_cache_usage_ratio = n_tokens_max / n_ctx
  llama_context_size = n_ctx
        ↓
Prometheus scrapes :9836 every 15s  (job: llama-context-exporter)
        ↓
Grafana evaluates alert every 1m
  FIRING when llama_kv_cache_usage_ratio > 0.8 for ≥ 1m
        ↓
Grafana POSTs to grafana-owui-adapter :9837
        ↓
Adapter POSTs {"content": "⚠ LSE context fill critical (XX% full)..."} to OpenWebUI
        ↓
Message appears in lse-alerts channel
```

### Verify the pipeline is healthy

```bash
# Both services running?
systemctl status llama-context-exporter grafana-owui-adapter --no-pager

# Exporter returning metrics?
curl -s http://localhost:9836/metrics

# Prometheus scraping the exporter?
curl -s "http://localhost:9090/api/v1/query?query=llama_kv_cache_usage_ratio" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['data']['result'])"

# Grafana alert state?
curl -s "http://localhost:3002/api/prometheus/grafana/api/v1/alerts" \
  -H "Authorization: Bearer <API_KEY>" | python3 -c "
import sys,json
for a in json.load(sys.stdin)['data']['alerts']:
    print(a['state'], a['labels']['alertname'])
"
```

### Restart after a system reboot

Both systemd services are enabled and start automatically. The Docker containers (Prometheus, Grafana) start automatically if Docker is configured with `--restart unless-stopped`. Verify after reboot:

```bash
systemctl status llama-context-exporter grafana-owui-adapter
docker ps | grep -E "prometheus|grafana"
```

### Restart after a llama-server profile switch

The exporter queries `/slots` on every scrape — it picks up the new `n_ctx` automatically within 15 seconds of llama-server restarting with a different profile. No manual action needed.

### Key credentials

- Grafana API key: stored in Vaultwarden (`glsa_...`)
- OpenWebUI channel webhook URL: stored in the `lse-alerts` channel settings → Webhooks → `Grafana Context Monitor`
- Bridge gateway IP (Docker → host): `172.17.0.1` (verify with `docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'`)

### Docker network

All monitoring containers are on `lse-net` for DNS resolution between containers:

```bash
docker network inspect lse-net --format '{{range .Containers}}{{.Name}} {{end}}'
# → prometheus vaultwarden searxng node-exporter grafana
```

Prometheus reaches Grafana and other containers by name (`http://prometheus:9090`). The exporter and adapter on the WSL2 host are reached via the bridge gateway IP `172.17.0.1`.

---

## 10. Key paths reference

| Purpose | Path |
|---|---|
| Launcher script | `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\lse-stack-launch-1.06.ps1` |
| Launch scripts (WSL) | `/home/sy5/.lse/launch/` |
| llama-server binary | `/home/sy5/llama.cpp/build/bin/llama-server` |
| Models directory | `/home/sy5/models/` |
| Open WebUI venv | `/home/sy5/owui/bin/activate` |
| SearxNG docker dir | `/home/sy5/searxng-docker/` |
| SearxNG config | `/home/sy5/searxng-docker/searxng/settings.yml` |
| LSE state file | `/opt/local-se/session-handover.md` |
| LSE knowledge base | `/opt/local-se/kb/` |
| Audit log | `/opt/local-se/audit.log` |
| Tool versions | `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\tools\` |
| Prompt versions | `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\prompts\` |
| Version registry | `C:\Users\SY5\Documents\Claude\Projects\local-system-engineer\VERSION.md` |

## 10. Dreaming operations (TRAUM)

The TRAUM loop runs nightly, unattended: `goethe-dream.timer` fires
`goethe-dream.service` at 03:30 (±15 min jitter), which runs the five
dream passes (`dedup`, `stale-contradiction`, `error-cluster`, `patterns`,
`insights`) via `tools/dream_runner.py --no-dry-run`. The runner only ever
PROPOSES — nothing reaches Elasticsearch without a human yes through
`tools/dream_apply.py`. Every command below was executed and verified on
LUCIFER on 2026-07-13.

### 10.1 The 5-minute morning review loop

```bash
# 1. What happened overnight? (≤30 lines, always current)
cat /opt/local-se/dreams/latest-digest.md

# 2. What's waiting on you? (all day-dirs, oldest first, grouped by type;
#    proposals >14 days old are auto-expired with reason on this call)
cd /home/sy5/local-system-engineer
python3 tools/dream_apply.py --queue

# 3. Apply/reject a day's batch interactively (per-proposal yes/no;
#    invariant validation happens regardless of your answer):
python3 tools/dream_apply.py --proposals /opt/local-se/dreams/<date>/proposals-<pass>.jsonl --no-dry-run
```

The `[DREAM]` banner on your first `search_kb`/`time_check` of a session
carries digest date + pending-gate count — if it says pending > 0, run
step 2.

### 10.2 Timer health

```bash
systemctl list-timers goethe-dream.timer --no-pager   # NEXT ≈ tomorrow 03:30-03:45
journalctl -u goethe-dream --no-pager -n 50           # last run's stdout/stderr
systemctl status goethe-dream.timer --no-pager        # enabled + active (waiting)
# fire one full cycle by hand, off-schedule (needs root):
sudo systemctl start goethe-dream.service
```

### 10.3 Failed nights

A crashed pass writes `report-<pass>.md` with a `## FAILED` banner plus a
line in `crashes.jsonl` in that day-dir, files a `record_error` to
`lse-errors` (context=`dream-runner`, provenance=`dream-infra`), and does
NOT mark sessions dreamed (safe re-dream). `Restart=no` — the timer just
fires again the next night. **3 consecutive failed nights escalates in the
digest header** — that banner is your signal to read the newest
`crashes.jsonl`:

```bash
ls /opt/local-se/dreams/*/crashes.jsonl        # empty today: no crashed nights yet
tail -1 "$(ls -t /opt/local-se/dreams/*/crashes.jsonl 2>/dev/null | head -1)"
```

If a run died holding the lock: the lock self-expires (default 4 h) and
carries the holder PID (liveness-probed) — a dead holder's lock is broken
automatically. Manual inspect/clear:

```bash
cat /opt/local-se/dreams/.dream.lock 2>/dev/null || echo "no lock held"
rm /opt/local-se/dreams/.dream.lock   # only if the PID inside is dead
```

### 10.4 Re-dreaming a session

Sessions are consumed once (`dreamed_at` in the manifest). To re-dream one
(e.g. after a crash you don't trust, or a redaction/parser fix you want
re-applied to history):

```bash
sqlite3 /opt/local-se/episodes/manifest.db \
  "SELECT session_id, dreamed_at FROM sessions ORDER BY start_ts DESC LIMIT 10;"
sqlite3 /opt/local-se/episodes/manifest.db \
  "UPDATE sessions SET dreamed_at=NULL WHERE session_id='<session_id>';"
# then either wait for tonight's timer or run one pass by hand:
python3 /home/sy5/local-system-engineer/tools/dream_runner.py --pass <pass> --no-dry-run
```

(A hand run during the day usually needs `--ignore-guards` — the 30-min
session-activity guard will correctly refuse while you're using the LSE.)

### 10.5 Tracing a KB doc back to its dream

Every dream-applied write carries `origin=dream` +
`provenance=dream-YYYY-MM-DD`:

```bash
curl -s "http://127.0.0.1:9200/lse-kb/_search" -H 'Content-Type: application/json' \
  -d '{"query":{"term":{"origin":"dream"}},"size":10,"_source":["title","provenance","origin"]}'
```

The provenance date names the day-dir: `/opt/local-se/dreams/<date>/`
holds `report-<pass>.md` (the WHY), `proposals-<pass>.jsonl` (the exact
proposed call), `applied.jsonl` (the human yes + what was written),
`rejected.jsonl` / `expired.jsonl` (everything that didn't land, with
reason). Day-dirs before 2026-07-13 use the legacy shared
`report.md`/`proposals.jsonl` names.

### 10.6 Paths

| What | Where |
|---|---|
| Episode corpus | `/opt/local-se/episodes/YYYY-MM-DD/<session>.jsonl` + `manifest.db` |
| Dream output | `/opt/local-se/dreams/YYYY-MM-DD/` |
| Morning digest | `/opt/local-se/dreams/latest-digest.md` |
| Units (installed) | `/etc/systemd/system/goethe-dream.{service,timer}` |
| Unit templates (repo) | `lse/services/goethe-dream.{service,timer}.tmpl` |
| Runner sandbox cwd | `/var/lib/lse/dream-sandbox` (holds nothing durable) |

### 10.7 Create or refresh the TRAUM operator KB entry

Use the copy-paste prompt in
[`docs/dreaming/KB-ENTRY-PROMPT.md`](dreaming/KB-ENTRY-PROMPT.md). It requires
live read-only verification before claiming ground truth, previews the proposed
entry before indexing, and never applies dream proposals as part of documentation.
Users without GOETHE tools receive the same entry as reviewable Markdown/JSON and
must label unverified fields instead of presenting them as live facts.
