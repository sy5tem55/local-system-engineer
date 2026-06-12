# SearxNG Configuration Reference

---
## ⚠ CORRECTED 2026-06-12 (P22) — paths/tokens below were STALE and caused a 401 hunt
- Real settings dir: `/home/sy5/docker/searxng_data` (mounted at /etc/searxng). `/home/sy5/searxng-docker/` NO LONGER EXISTS.
- Real prometheus config: `/home/sy5/docker/prometheus/prometheus.yml`
- Real metrics token: `open_metrics: "JZVeoVch20+FvyjXEn4BMVHtu1AM6JCH"` — Prometheus uses basic_auth (empty username + token as password). `metrics-admin-2025` and `searxng-metrics-token-2026` are dead/never-existed.
- Networks: searxng + prometheus + grafana share `docker_searxng_net` → scrape target is `searxng:8080` (container port), host access is :8088.
- SINGLE SOURCE OF TRUTH: repo `observability/observability.env` + `deploy-observability.sh` (idempotent drift repair + end-to-end verify). Read tokens/paths from THERE or from `docker inspect` — never from memory or from the historic sections below.

# Path: /opt/local-se/kb/searxng-config.md
# Use this file before proposing any settings.yml changes.

---

## Paths (Docker install)

Settings:  `/home/sy5/searxng-docker/searxng_data/settings.yml`
Limiter:   `/home/sy5/searxng-docker/searxng_data/limiter.toml`
Port:      `8088` (NOT 8080 — 8080 is llama-server)

---

## Section structure

```
use_default_settings:   # top-level — engine list overrides
general:                # top-level
search:                 # top-level — includes suspended_times
server:                 # top-level — includes limiter and secret_key
outgoing:               # top-level — timeouts, pool, HTTP settings
```

---

## suspended_times — under search:, NOT outgoing:

```yaml
search:
  suspended_times:
    SearxEngineAccessDenied:      180      # HTTP 402, 403, access denied
    SearxEngineCaptcha:           3600     # CAPTCHA detected
    SearxEngineTooManyRequests:   180      # HTTP 429, rate limit
    cf_SearxEngineCaptcha:        1296000  # Cloudflare CAPTCHA (15 days)
    cf_SearxEngineAccessDenied:   86400    # Cloudflare access denied (1 day)
    recaptcha_SearxEngineCaptcha: 604800   # reCAPTCHA (7 days)
```

Values are in seconds. Set to 0 to disable a specific suspension.

**Common mistake:** putting suspended_times under outgoing: or at top level.
Both are wrong — the parser ignores them silently.

---

## limiter — under server:, NOT top-level

```yaml
server:
  limiter: true    # enables bot detection / rate limiting
```

Requires limiter.toml at the same path as settings.yml.

---

## outgoing: — correct key names

```yaml
outgoing:
  request_timeout: 6.0       # seconds per engine request (default 3.0)
  pool_connections: 100      # max concurrent connections (default 100)
  pool_maxsize: 20           # keep-alive connections per host (default 20)
  enable_http2: true
  retries: 1                 # correct key name (NOT max_retries)
```

**Wrong keys the model tends to generate (all silently ignored):**
- `pool_limit`     → use `pool_connections` + `pool_maxsize`
- `max_retries`    → use `retries`
- `max_scrape_time` → not a real key in current SearxNG
- `suspicious`     → not a real key
- `"HTTP error [429]"` → suspended_times keys are Python exception class names, not strings

---

## Full verified working settings.yml

```yaml
use_default_settings:
  engines:
    remove:
      - duckduckgo
      - startpage
      - wikidata
      - ahmia
      - torch

server:
  bind_address: "0.0.0.0"
  port: 8088
  limiter: true
  secret_key: "!!SET VIA openssl rand -hex 32!!"

search:
  formats:
    - html
    - json
  ban_time_on_fail: 5
  max_ban_time_on_fail: 120
  suspended_times:
    SearxEngineAccessDenied:      180
    SearxEngineCaptcha:           3600
    SearxEngineTooManyRequests:   180
    cf_SearxEngineCaptcha:        1296000
    cf_SearxEngineAccessDenied:   86400
    recaptcha_SearxEngineCaptcha: 604800

outgoing:
  request_timeout: 6.0
  pool_connections: 100
  pool_maxsize: 20
  enable_http2: true
```

---

## Full limiter.toml reference

```toml
[botdetection]
ipv4_prefix = 32
ipv6_prefix = 48
trusted_proxies = ['127.0.0.0/8', '::1']

[botdetection.ip_limit]
filter_link_local = false
link_token = false        # set true only if valkey/redis is running

[botdetection.ip_lists]
block_ip = []
pass_ip = []
pass_searxng_org = true
```

---

## After any settings.yml or limiter.toml change

```bash
cd /home/sy5/searxng-docker && docker compose restart searxng
# verify:
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/
# expected: 200
```

---

## Source

Verified against official SearxNG source and docs, 2026-05-24.
Do NOT propose config keys without checking this file first.
