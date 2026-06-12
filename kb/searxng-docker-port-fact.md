# SearXNG Docker Port Mapping — HARD FACT

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
