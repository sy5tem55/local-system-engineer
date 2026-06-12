# SearXNG Docker Port Mapping — HARD FACT

---
## ⚠ CORRECTED 2026-06-12 (P22) — paths/tokens below were STALE and caused a 401 hunt
- Real settings dir: `/home/sy5/docker/searxng_data` (mounted at /etc/searxng). `/home/sy5/searxng-docker/` NO LONGER EXISTS.
- Real prometheus config: `/home/sy5/docker/prometheus/prometheus.yml`
- Real metrics token: `open_metrics: "JZVeoVch20+FvyjXEn4BMVHtu1AM6JCH"` — Prometheus uses basic_auth (empty username + token as password). `metrics-admin-2025` and `searxng-metrics-token-2026` are dead/never-existed.
- Networks: searxng + prometheus + grafana share `docker_searxng_net` → scrape target is `searxng:8080` (container port), host access is :8088.
- SINGLE SOURCE OF TRUTH: repo `observability/observability.env` + `deploy-observability.sh` (idempotent drift repair + end-to-end verify). Read tokens/paths from THERE or from `docker inspect` — never from memory or from the historic sections below.


## Critical Configuration
- **Docker-compose port mapping MUST be: `"8088:8080"`** (host:8088 → container:8080)
- **NEVER use `"8088:8088"`** — the SearXNG image always listens on internal port 8080, regardless of settings.yml
- **Prometheus scrape target MUST be: `searxng:8080`** (internal container port)

## Why
The SearXNG Docker image hardcodes its internal listening port to 8080. The `settings.yml` port value does NOT change this. The docker-compose port mapping must bridge host:8088 to container:8080.

## Prometheus Auth
- SearXNG metrics uses `open_metrics: "metrics-admin-2025"`
- Prometheus basic_auth format: `username: ""` + `password: "metrics-admin-2025"`
- This produces Basic auth header: `Authorization: Basic Og...` (empty username colon password)

## References
- docker-compose: `/home/sy5/searxng-docker/docker-compose.yml`
- Prometheus config: `/home/sy5/searxng-docker/prometheus/prometheus.yml`
- Settings: `/home/sy5/searxng-docker/searxng_data/settings.yml`
