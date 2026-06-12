# SearXNG Observability Stack — Complete Deployment Reference

---
## ⚠ CORRECTED 2026-06-12 (P22) — paths/tokens below were STALE and caused a 401 hunt
- Real settings dir: `/home/sy5/docker/searxng_data` (mounted at /etc/searxng). `/home/sy5/searxng-docker/` NO LONGER EXISTS.
- Real prometheus config: `/home/sy5/docker/prometheus/prometheus.yml`
- Real metrics token: `open_metrics: "JZVeoVch20+FvyjXEn4BMVHtu1AM6JCH"` — Prometheus uses basic_auth (empty username + token as password). `metrics-admin-2025` and `searxng-metrics-token-2026` are dead/never-existed.
- Networks: searxng + prometheus + grafana share `docker_searxng_net` → scrape target is `searxng:8080` (container port), host access is :8088.
- SINGLE SOURCE OF TRUTH: repo `observability/observability.env` + `deploy-observability.sh` (idempotent drift repair + end-to-end verify). Read tokens/paths from THERE or from `docker inspect` — never from memory or from the historic sections below.


## Architecture
```
┌─────────────┐     /metrics      ┌──────────────┐     /api/v1/query     ┌──────────────┐     SQLite
│  SearXNG    │ ──────────────► │  Prometheus  │ ──────────────► │  Logger      │ ──────────────► searxng.db
│  :8088      │                 │  :9090       │                 │  (sidecar)   │
└─────────────┘                 └──────────────┘                 └──────────────┘
```

## Port Configuration (HARD FACT)
- **Docker-compose port mapping:** `"8088:8080"` (host:8088 → container:8080)
- **SearXNG internal port:** Always 8080 (hardcoded in image, settings.yml port value ignored)
- **Prometheus scrape target:** `searxng:8080` (internal container port)
- **Prometheus host port:** 9090

## Authentication
- **Metrics auth format:** Basic auth with empty username + password
  - Username: "" (empty string)
  - Password: "metrics-admin-2025"
  - Results in header: `Authorization: Basic Og...`
- **Prometheus basic_auth config:**
  ```yaml
  basic_auth:
    username: ""
    password: "metrics-admin-2025"
  ```

## Polling Configuration
- **Logger polling interval:** 60 seconds (1 minute)
- **Rationale:** Balances granularity (catches transient outages) with database growth (~216 rows/day)
- **Environment variable:** `POLL_INTERVAL=60`

## Data Purging
The SQLite database includes a `purge_before` function to remove old logs:
```sql
DELETE FROM query_log WHERE timestamp < datetime('now', '-7 days');
```

Python purge script:
```python
import sqlite3
conn = sqlite3.connect('/home/sy5/searxng-docker/searxng_data/searxng.db')
conn.execute("DELETE FROM query_log WHERE timestamp < datetime('now', '-7 days')")
conn.commit()
print(f"Purged. Remaining rows: {conn.execute('SELECT COUNT(*) FROM query_log').fetchone()[0]}")
conn.close()
```

## File Locations
- Docker-compose: `/home/sy5/searxng-docker/docker-compose.yml`
- Prometheus config: `/home/sy5/searxng-docker/prometheus/prometheus.yml`
- Prometheus data: `/home/sy5/searxng-docker/prometheus/data/`
- SQLite database: `/home/sy5/searxng-docker/searxng_data/searxng.db`
- Logger code: `/opt/local-se/searxng-logger/logger.py`
- Logger Dockerfile: `/opt/local-se/searxng-logger/Dockerfile`

## Milestone 4 Use Cases
### Prometheus Use Cases
- Engine reliability alerts (<90% threshold)
- Response time anomaly detection
- Rate limiting alerts
- Capacity planning (request count trends)

### SQLite Use Cases
- Daily/monthly engine usage reports
- Zero-result query tracking
- Engine comparison analysis
- Historical performance trending

### Grafana Use Cases
- Real-time engine health dashboard
- Request/response time visualization
- Reliability trend charts
- Custom alerting rules with notifications
- Daily/monthly aggregated reports
- Anomaly detection visualization

### Alternative Dashboard Options
- **Prometheus + SQLite + CLI:** Simple command-line queries
- **Python Flask/Dash:** Custom web dashboard
- **SQLite Browser:** GUI for ad-hoc analysis
- **Prometheus UI:** Basic built-in interface

## Container Names
- SearXNG: `searxng`
- Prometheus: `prometheus`
- Logger: `searxng-logger`

## Quick Verification Commands
```bash
# Check SearXNG web
curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/

# Check Prometheus target
curl -s "http://localhost:9090/api/v1/targets" | python3 -c "import sys,json; [print(f'{t[\"labels\"][\"job\"]}: {t[\"health\"]}') for t in json.load(sys.stdin)['data']['activeTargets']]"

# Check SQLite data
python3 -c "import sqlite3; conn=sqlite3.connect('/home/sy5/searxng-docker/searxng_data/searxng.db'); print(f'Rows: {conn.execute(\"SELECT COUNT(*) FROM query_log\").fetchone()[0]}')"
```
