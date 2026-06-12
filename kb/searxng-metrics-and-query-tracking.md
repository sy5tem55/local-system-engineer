# SearXNG Metrics & Query Tracking - Deployment Guide

> Last updated: 2025-05-25
> SearXNG version: 2026.5.17+d7e8b7cd1
> Source: Container inspection + official docs + GitHub

---

## Architecture Overview

### Current State (In-Memory Only)

SearXNG's `/stats` page shows **in-memory metrics only**:
- Counts reset on container restart
- No persistent storage
- Tracks: query count, response times, success/failure rates per engine
- Access: `http://localhost:8088/stats`

### Metrics Module (`/usr/local/searxng/searx/metrics/`)

```
metrics/
├── __init__.py          # Main module - initializes counters/histograms
├── models.py            # HistogramStorage, CounterStorage classes
└── error_recorder.py    # Tracks engine errors/suspensions
```

**Key metrics tracked per engine:**
- `engine.{name}.search.count.sent` - total queries sent to engine
- `engine.{name}.search.count.successful` - successful queries
- `engine.{name}.search.count.error` - failed queries
- `engine.{name}.time.http` - HTTP request duration
- `engine.{name}.time.total` - total processing time
- `engine.{name}.result.count` - results returned per query
- `engine.{name}.score` - engine reliability score

### OpenMetrics Endpoint (Prometheus-Compatible)

**Location:** `/usr/local/searxng/searx/webapp.py`, line 1168

**Configuration:**
```yaml
general:
  enable_metrics: true           # Enables metrics collection
  open_metrics: '<password>'     # Password-protects /metrics endpoint
```

**Metrics exposed:**
- `searxng_engines_response_time_total_seconds` (gauge)
- `searxng_engines_response_time_processing_seconds` (gauge)
- `searxng_engines_response_time_http_seconds` (gauge)
- `searxng_engines_result_count_total` (counter)
- `searxng_engines_request_count_total` (counter)
- `searxng_engines_reliability_total` (counter)

**Important:** Metrics are **aggregated, not per-query**. Each counter tracks total queries since startup, not individual query logs.

---

## Query Tracking Options

### Option 1: Prometheus + OpenMetrics (Recommended)

**What it does:** Scrapes `/metrics` endpoint every 15-60s, persists to TSDB, provides Grafana dashboards.

**Pros:**
- ✅ Battle-tested, no custom code
- ✅ Historical trends (days/months/years)
- ✅ Alerting on engine failures
- ✅ Grafana dashboards available
- ✅ Prometheus stores metrics persistently

**Cons:**
- ❌ Aggregated metrics only (no per-query details)
- ❌ Doesn't show individual queries or search terms
- ❌ Requires extra container + storage

### Option 2: Custom SQLite Query Logger (Build)

**What it does:** Middleware that logs every query to SQLite with:
- Timestamp
- Query text (optional, can be hashed for privacy)
- Engine used
- Response time
- Result count
- Success/failure status

**Pros:**
- ✅ Full per-query history
- ✅ Exact daily/monthly counts per engine
- ✅ Query searchability
- ✅ Single file, zero extra containers

**Cons:**
- ❌ Requires custom development
- ❌ No existing SearXNG integration
- ❌ Must be built as a middleware or sidecar

### Option 3: Log Parsing (Quick & Dirty)

**What it does:** Enable debug logging, parse `docker logs` output.

**Pros:**
- ✅ No code changes
- ✅ Shows per-query details
- ✅ Can grep/awk for counts

**Cons:**
- ❌ Logs rotate and disappear
- ❌ No structured data
- ❌ Performance impact
- ❌ Not reliable for long-term tracking

---

## Recommended Approach: Hybrid

**Phase 1:** Enable OpenMetrics + Prometheus (quick, gives aggregated stats)
**Phase 2:** Build SQLite query logger (gives per-query detail)

---

## Prometheus Deployment

### Docker Compose Addition

```yaml
services:
  searxng:
    # ... existing config ...
    environment:
      - SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml

  prometheus:
    container_name: prometheus
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=90d'
    networks:
      - searxng_net
    restart: unless-stopped
```

### Prometheus Config (`prometheus.yml`)

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'searxng'
    static_configs:
      - targets: ['searxng:8088']
    metrics_path: '/metrics'
    params:
      authenticate: ['<password>']
    scrape_interval: 15s
```

### SearXNG Settings Update

```yaml
general:
  enable_metrics: true
  open_metrics: '<password>'  # Set your own password
```

---

## SQLite Query Logger Design

### Schema

```sql
CREATE TABLE IF NOT EXISTS query_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    engine TEXT NOT NULL,
    query_hash TEXT NOT NULL,  -- SHA256 hash for privacy
    query_text TEXT,           -- Optional, can be NULL for privacy
    category TEXT,
    response_time_ms REAL,
    result_count INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT 1,
    error_type TEXT,
    ip_address TEXT DEFAULT 'local'
);

CREATE INDEX idx_timestamp ON query_log(timestamp);
CREATE INDEX idx_engine ON query_log(engine);
CREATE INDEX idx_date ON query_log(date(timestamp));
```

### Query Examples

```sql
-- Daily queries per engine
SELECT date(timestamp) as day, engine, COUNT(*) as queries
FROM query_log
GROUP BY day, engine
ORDER BY day DESC, queries DESC;

-- Monthly summary
SELECT strftime('%Y-%m', timestamp) as month, engine, COUNT(*) as queries,
       SUM(success) as successful, SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed
FROM query_log
GROUP BY month, engine;

-- Engine success rate (last 30 days)
SELECT engine,
       COUNT(*) as total,
       SUM(success) * 100.0 / COUNT(*) as success_rate
FROM query_log
WHERE timestamp >= datetime('now', '-30 days')
GROUP BY engine;
```

### Implementation Options

**A. SearXNG Middleware (Python)**
- Hook into `before_request`/`after_request` in webapp.py
- Log query details to SQLite
- Requires custom Docker image

**B. Sidecar Container**
- Separate Python service that polls SearXNG's `/stats` endpoint
- Writes deltas to SQLite
- Simpler, but less granular

**C. Log Parser**
- Enable debug logging
- Pipe logs to a parser that writes to SQLite
- Least invasive but least structured

---

## Current Engine Error Tracking

### Error Types (from settings.yml)

| Exception | Suspension Time |
|---|---|
| `SearxEngineTooManyRequests` | 180s (3 min) |
| `SearxEngineAccessDenied` | 180s (3 min) |
| `SearxEngineCaptcha` | 3600s (1 hour) |
| `cf_SearxEngineCaptcha` | 1296000s (15 days) |
| `cf_SearxEngineAccessDenied` | 86400s (1 day) |
| `recaptcha_SearxEngineCaptcha` | 604800s (7 days) |

### Engine Removal (from settings.yml)

Currently removed engines:
- duckduckgo
- startpage
- wikidata
- ahmia
- torch

### Brave Suspension Pattern (observed)

- **Error:** `SearxEngineTooManyRequestsException`
- **Suspension:** 180s per occurrence
- **Pattern:** Re-suspends immediately after retry (loop)
- **Root cause:** Brave Search free tier rate limit
- **Fix:** Disable Brave in settings or add proxy

---

## References

1. **SearXNG Admin Docs:** https://docs.searxng.org/admin/installation-searxng.html
2. **SearXNG GitHub Settings:** https://github.com/searxng/searxng/blob/master/searx/settings.yml
3. **OpenMetrics Spec:** https://github.com/prometheus/OpenMetrics/blob/main/specification/OpenMetrics.txt
4. **Prometheus Docs:** https://prometheus.io/docs/prometheus/latest/configuration/configuration/
5. **SearXNG Issue #2154** (OpenMetrics feature request): https://github.com/searxng/searxng/issues/2154

---

## Key Takeaways

1. **SearXNG has NO built-in persistent query logging** - only in-memory metrics
2. **`/metrics` endpoint exists** but is disabled by default - enable via `general.enable_metrics`
3. **Prometheus is the standard solution** for persistent metrics (aggregated only)
4. **SQLite query logger requires custom development** (no existing module)
5. **Brave engine is suspended** due to rate limiting - disable or proxy
6. **Metrics reset on container restart** - persistent storage is mandatory for historical tracking