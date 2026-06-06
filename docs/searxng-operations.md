# SearXNG Operations Guide
> Last updated: 2026-06-04
> Stack: SearXNG on Docker (lse-net) · Prometheus scrape · Grafana dashboards
> Live config: `/home/sy5/docker/searxng_data/settings.yml`
> Project config: `docker/searxng_data/settings.yml` (source of truth, copy to host to deploy)

---

## Quick Reference

| Task | Command |
|---|---|
| Restart SearXNG | `cd ~/docker && docker compose restart searxng` |
| View logs | `docker logs searxng --tail 50` |
| Check active engines | `curl -s "http://localhost:8088/search?q=python&format=json&categories=it" \| python3 -m json.tool \| grep '"engine"' \| sort -u` |
| Backup config | `sudo cp ~/docker/searxng_data/settings.yml ~/docker/searxng_data/settings.yml.bak-$(date +%Y%m%d)` |
| Apply new config | `sudo cp /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml ~/docker/searxng_data/settings.yml` |
| Check metrics | `curl -s -u "metrics-admin-2025:<password>" http://localhost:8088/metrics \| grep searxng_engines` |
| Check suspensions | `docker logs searxng 2>&1 \| grep -i "suspend\|blocked\|429"` |

---

## Architecture

```
OpenWebUI (search_web tool)
    │
    └─► SearXNG :8088 (Docker, lse-net)
            │
            ├─► Google, DuckDuckGo, Bing, Brave, Mojeek, Qwant   (general web)
            ├─► Arxiv, Semantic Scholar, PubMed                    (science)
            ├─► GitHub, StackOverflow, MDN, HackerNews             (technical)
            ├─► PyPI, npm, pkg.go.dev, Docker Hub, HuggingFace     (packages)
            ├─► AskUbuntu, SuperUser                               (sysadmin Q&A)
            ├─► Wikipedia                                          (reference)
            └─► National Vulnerability Database                    (security)
            │
Prometheus :9090 ──scrapes──► SearXNG /metrics (basic auth)
Grafana :3002    ──queries──► Prometheus
```

---

## Metrics

SearXNG exposes Prometheus metrics at `http://localhost:8088/metrics` (basic auth required).

**Auth:** `metrics-admin-2025:<SEARXNG_METRICS_PASSWORD>` (see Vaultwarden)

### Available Metrics

| Metric | Type | Description |
|---|---|---|
| `searxng_engines_request_count_total{engine_name}` | counter | Total requests sent to each engine |
| `searxng_engines_reliability_total{engine_name}` | gauge | Current reliability score 0–100 |
| `searxng_engines_response_time_total_seconds{engine_name}` | gauge | Average total response time |
| `searxng_engines_response_time_http_seconds{engine_name}` | gauge | Average HTTP response time |
| `searxng_engines_response_time_processing_seconds{engine_name}` | gauge | Average processing time |
| `searxng_engines_result_count_total{engine_name}` | counter | Total results returned |

**NOTE:** There is NO `searxng_engines_errors_total` metric. Errors are implied by
`reliability_total < 100`. A reliability of 0 means the engine is silently failing every request.

### Interpreting Reliability

| Reliability | Meaning | Action |
|---|---|---|
| 100% | Healthy | None |
| 70–99% | Occasional failures | Monitor |
| 40–69% | Frequent failures (rate limiting likely) | Reduce weight or investigate |
| < 40% | Severely degraded | Consider disabling |
| 0% (missing from metric) | Silently failing 100% | Disable immediately |

### Grafana Panel Queries

**Current engine error rate (bar gauge):**
```promql
100 - searxng_engines_reliability_total
```

**Response time by engine (bar chart):**
```promql
searxng_engines_response_time_total_seconds
```

**Requests per 5m by engine (stacked time series):**
```promql
increase(searxng_engines_request_count_total[5m])
```

**Estimated errors per 5m by engine (stacked time series):**
```promql
increase(searxng_engines_request_count_total[5m]) * ((100 - searxng_engines_reliability_total) / 100)
```

---

## Engine Categories

Engines only fire on queries matching their category. Verifying "test" returns only
general-web engines — this is correct behaviour, not a missing-engine problem.

| Category | Query parameter | Engines that respond |
|---|---|---|
| general | `categories=general` | google, duckduckgo, bing, brave, mojeek, qwant, wikipedia |
| science | `categories=science` | arxiv, semantic scholar, pubmed, google scholar* |
| it | `categories=it` | stackoverflow, github, mdn, askubuntu, superuser, hackernews |
| news | `categories=news` | duckduckgo news, google news, brave news* |
| images | `categories=images` | google images, duckduckgo images |

*google scholar: currently disabled (0% reliability, VPS IP blocked by Google)

**To verify all engines for a category:**
```bash
curl -s "http://localhost:8088/search?q=QUERY&format=json&categories=CATEGORY" \
  | python3 -m json.tool | grep '"engine"' | sort -u
```

---

## Configuration Management

### Source of truth
`/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml`

Always edit the project file, never edit the live file directly. Apply via:
```bash
sudo cp /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml \
   ~/docker/searxng_data/settings.yml
cd ~/docker && docker compose restart searxng
```

### Why sudo is required
The `searxng_data/` directory is owned by root (Docker volume mount). Always use
`sudo` for cp operations on this path.

### Config structure
```yaml
use_default_settings:
  engines:
    keep_only:          # Controls WHICH engines are active (allowlist)
      - google
      - arxiv
      # ...

engines:                # Controls per-engine WEIGHTS and TIMEOUTS
  - name: arxiv
    weight: 2
    timeout: 5
    categories: [science, it, technology]

outgoing:
  request_timeout: 4.0  # Global timeout — NOT under search:
```

**Critical:** `request_timeout` must be under `outgoing:`, not `search:`. Placing it
under `search:` is silently ignored.

### Adding an engine
1. Add to `keep_only` list (exact SearXNG registered name)
2. Optionally add weight/timeout under `engines:`
3. Apply + restart
4. Verify: `curl -s "http://localhost:8088/search?q=test&format=json&categories=CATEGORY" | ...`

To find exact registered names:
```bash
docker exec searxng grep -r "^name = " /usr/local/searxng/searx/engines/*.py | awk -F'"' '{print $2}' | sort
```

### Removing an engine
1. Delete from `keep_only`
2. Delete from `engines:` if present
3. Update the hierarchy comment at the top of settings.yml
4. Apply + restart

---

## Known Issues and Workarounds

### Semantic Scholar SSL Fix (2026-06-04) — RESOLVED

**Symptom:** Semantic Scholar returns 0 results. SSL cert verification failure against
api.semanticscholar.org (incomplete chain — missing Sectigo RSA DV intermediate CA).

**Fix (permanent — survives restarts):**
```bash
# 1. Install Sectigo intermediate on host
curl -s "https://crt.sh/?d=5689216" -o /tmp/sectigo-rsa-dv.crt
sudo cp /tmp/sectigo-rsa-dv.crt /usr/local/share/ca-certificates/sectigo-rsa-dv.crt
sudo update-ca-certificates

# 2. docker-compose.yml searxng service already has (committed 2026-06-04):
#    volumes: - /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro
#    environment: - REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# 3. Recreate container
cd ~/docker && docker compose up -d --force-recreate searxng

# 4. Verify
docker exec searxng python3 -c "
import urllib.request
r = urllib.request.urlopen('https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1', timeout=5)
print('SSL OK — HTTP', r.status)
"
```
**If it breaks again:** Re-run steps 1+3 only. The docker-compose.yml change is permanent.

### Google Scholar — 0% reliability (as of 2026-06-04)
- **Symptom:** Appears in `request_count_total` but missing from `reliability_total`
- **Cause:** Google's bot detection blocks VPS IPs. Requests sent, responses rejected.
- **Status:** Disabled in `keep_only` until fixed
- **Debug:**
  ```bash
  docker exec searxng curl -sA "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
    "https://scholar.google.com/scholar?q=test" | head -5
  ```
  If response contains "unusual traffic" or captcha → IP is blocked.
- **Workaround:** Semantic Scholar (100% reliable) now carries science queries at weight 3

### Brave — 40% reliability (VPS rate limiting)
- **Symptom:** `SearxEngineTooManyRequests` in logs, reliability 40%
- **Cause:** Brave Search rate-limits VPS IP ranges
- **Status:** Kept at weight 1, auto-suspended 180s by `suspended_times` config
- **Not a bug** — suspension mechanism working correctly

### Arxiv — 15% reliability, was 3.5s avg response
- **Root cause:** arxiv.org is unreliable from VPS and has strict rate limits
- **Original config mistake:** weight=4, timeout=15s
  - Weight 4 meant it dominated science queries despite failing 85% of the time
  - Timeout 15s meant every failed request held the query open for 15 seconds
- **Fix applied (v2):** weight=2, timeout=5s
  - Latency improvement: science query p85 dropped from ~15s → ~5s

### Reddit — blocked on VPS IPs
- **Status:** Deliberately excluded from `keep_only`
- **Workaround:** Use `site:reddit.com` appended to Google queries
- **Future:** Custom engine with Reddit OAuth API (planned)

### Docker Compose restart shows `0/1`
- **Symptom:** `[+] restart 0/1` with spinner at 1.5s
- **Cause:** Docker Compose display quirk — the container may still be restarting
  when the progress bar renders
- **Check actual status:** `docker ps | grep searxng`
- **Check for errors:** `docker logs searxng --tail 30`

---

## Suspension Mechanism

SearXNG auto-suspends engines that hit rate limits. Configured in `search.suspended_times`:

| Error type | Suspension |
|---|---|
| `SearxEngineAccessDenied` | 180s (3 min) |
| `SearxEngineTooManyRequests` | 180s (3 min) |
| `SearxEngineCaptcha` | 3600s (1 hour) |
| `cf_SearxEngineAccessDenied` | 86400s (1 day) |
| `cf_SearxEngineCaptcha` | 1296000s (15 days) |
| `recaptcha_SearxEngineCaptcha` | 604800s (7 days) |

Suspensions are ephemeral — they reset on container restart.

---

## Engine Performance Baseline (2026-06-04)

| Engine | Reliability | Avg Response | Weight | Notes |
|---|---|---|---|---|
| google | 100% | 0.3s | 4 | Primary |
| duckduckgo | 100% | 1.0s | 2 | Primary fallback |
| pypi | 100% | 0.2s | 1 | Fastest engine |
| stackoverflow | 100% | 0.3s | 1 | |
| askubuntu | 100% | 0.3s | 1 | |
| superuser | 100% | 0.3s | 1 | |
| docker hub | 100% | 0.5s | 1 | |
| pubmed | 100% | 0.7s | 2 | |
| semantic scholar | 100% | 1.0s | 3 | Primary science |
| github | 85% | 0.4s | 1 | |
| wikipedia | 85% | 0.6s | 1 | |
| mdn | 85% | 0.4s | 1 | |
| duckduckgo news | unknown | unknown | 2 | |
| brave | 40% | 0.8s | 1 | VPS rate limited |
| arxiv | 15% | 3.5s | 2 | Unreliable, use cautiously |
| google scholar | 0% | — | disabled | VPS blocked |

---

## Deployment Checklist

Before applying any settings.yml change — run every step in order, do not skip:

```bash
# 1. Backup (required — the searxng_data dir is root-owned, always use sudo)
sudo cp ~/docker/searxng_data/settings.yml \
  ~/docker/searxng_data/settings.yml.bak-$(date +%Y%m%d_%H%M%S)

# 2. Validate YAML BEFORE applying — catches syntax errors before they break the container
python3 -c "
import yaml, sys
try:
    yaml.safe_load(open('/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml'))
    print('YAML OK — safe to apply')
except yaml.YAMLError as e:
    print(f'YAML ERROR: {e}')
    sys.exit(1)
"

# 3. Apply (only if step 2 printed "YAML OK")
sudo cp /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml \
  ~/docker/searxng_data/settings.yml

# 4. Restart
cd ~/docker && docker compose restart searxng

# 5. Check container came up (ignore the 0/1 display quirk — check logs instead)
sleep 8 && docker logs searxng --tail 10

# 6. Verify engines — use CATEGORY-SPECIFIC queries, NOT "test"
# "test" only returns general-web engines — does NOT prove other engines are active
curl -s "http://localhost:8088/search?q=transformer+attention+mechanism&format=json&categories=science" \
  | python3 -m json.tool | grep '"engine"' | sort -u

curl -s "http://localhost:8088/search?q=python+asyncio+exception+handling&format=json&categories=it" \
  | python3 -m json.tool | grep '"engine"' | sort -u

# 7. Watch metrics for ~5 min
curl -s -u "metrics-admin-2025:<password>" http://localhost:8088/metrics \
  | grep -E "reliability|response_time_total" | sort
```

**Why "test" is the wrong verification query:**
`"test"` is a generic word with no category signals. SearXNG routes it to general-web
engines only (google, duckduckgo, wikipedia). Science, IT, news, and package engines
won't fire on it. Always use domain-specific queries with `&categories=` to verify
those engine groups are active.

**Why YAML validation matters:**
A YAML syntax error in settings.yml causes SearXNG to fail on startup. Docker's
restart policy then tries to bring it back repeatedly, but it keeps failing.
The container appears to be running (docker ps shows it) but it's crash-looping
and serving nothing, or serving stale results from before the restart.
Validating before applying catches this before it happens.
