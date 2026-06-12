# SearXNG SQLite Query Logger - Deployment Plan

> Target: Persistent per-engine query counting with daily/monthly aggregation
> Strategy: Custom SQLite logger via sidecar container (no SearXNG code changes)
> Estimated effort: 4 milestones, ~2 hours total

---

## Milestone 1: Enable OpenMetrics + Test Prometheus Scrape
**Goal:** Get aggregated per-engine metrics working with persistence

### Steps:
1. Update SearXNG `settings.yml` to enable metrics:
   ```yaml
   general:
     enable_metrics: true
     open_metrics: '<password>'
   ```
2. Create Prometheus config
3. Add Prometheus container to `docker-compose.yml`
4. Verify `/metrics` endpoint returns data
5. Verify Prometheus scrapes successfully

### Success Criteria:
- ✅ `curl http://localhost:8088/metrics?authenticate=<password>` returns metrics
- ✅ Prometheus UI at `:9090` shows `searxng` target as UP
- ✅ `searxng_engines_request_count_total` counter increments on searches

### Risk: LOW - Standard configuration, well-documented

---

## Milestone 2: Build SQLite Query Logger (Sidecar)
**Goal:** Python service that polls `/stats` endpoint and writes to SQLite

### Architecture:
```
┌─────────────┐     /stats      ┌──────────────┐
│  SearXNG    │ ──────────────► │  Logger      │
│  :8088      │                 │  (sidecar)   │
└─────────────┘                 └──────────────┘
                                     │
                                     ▼
                               searxng.db (host mount)
```

### Steps:
1. Create logger service (`/opt/local-se/searxng-logger/`)
   - Polls `/stats` every 10s
   - Compares delta from previous scrape
   - Writes new query counts to SQLite
2. Create SQLite schema (see KB doc)
3. Build Docker image (or run directly on host)
4. Add to `docker-compose.yml`

### Success Criteria:
- ✅ Logger container starts and connects to SearXNG
- ✅ SQLite file created at `/home/sy5/searxng-docker/searxng_data/searxng.db`
- ✅ `query_log` table populated after searches
- ✅ Can query daily/monthly counts

### Risk: MEDIUM - Requires new Python service, untested

---

## Milestone 3: Build Query Detail Logger (Optional)
**Goal:** Capture individual query details (text, category, engine)

### Architecture:
Instead of polling `/stats`, hook into SearXNG's internal metrics:
- Access `/stats/errors` JSON endpoint
- Parse Docker logs for query details
- Or use a custom middleware (requires image rebuild)

### Steps:
1. Enable debug logging in SearXNG (temporary)
2. Build log parser that extracts:
   - Timestamp
   - Query text
   - Engine used
   - Response time
   - Success/failure
3. Write parser output to SQLite
4. Disable debug logging

### Success Criteria:
- ✅ Individual queries logged with timestamps
- ✅ Can search query history by text or engine
- ✅ No performance degradation

### Risk: HIGH - Requires log parsing, potential performance impact

---

## Milestone 4: Dashboard + Alerting
**Goal:** Visual dashboard showing engine health + rate limit alerts

### Steps:
1. Create Grafana dashboard (if using Prometheus)
2. Build simple CLI query tool for SQLite:
   ```bash
   ./query-stats.sh --daily    # Show daily counts
   ./query-stats.sh --monthly  # Show monthly summary
   ./query-stats.sh --engine brave  # Show Brave stats
   ```
3. Set up alerting for:
   - Engine success rate < 80%
   - Daily queries > threshold
   - Rate limit errors

### Success Criteria:
- ✅ One-command query stats display
- ✅ Alert when Brave (or any engine) hits rate limits
- ✅ Historical trend visibility

### Risk: LOW - Standard monitoring setup

---

## File Structure

```
/home/sy5/searxng-docker/
├── docker-compose.yml          # Updated with prometheus + logger
├── prometheus/
│   ├── prometheus.yml          # Prometheus config
│   └── data/                   # Prometheus TSDB (mounted)
├── logger/
│   ├── logger.py               # SQLite query logger
│   └── Dockerfile              # Logger container
└── searxng_data/
    ├── settings.yml            # SearXNG config (updated)
    ├── limiter.toml
    └── searxng.db              # SQLite database (created)
```

---

## Dependencies

| Component | Version | Purpose |
|---|---|---|
| SearXNG | 2026.5.17 | Search engine |
| Prometheus | latest | Metrics collection |
| SQLite | 3.x | Query log storage |
| Python | 3.14 | Logger service |
| Docker | current | Container runtime |

---

## Rollback Plan

- **Metrics enablement:** Remove `general.enable_metrics` from settings, restart
- **Prometheus:** Remove from compose, docker rm
- **SQLite logger:** Remove from compose, docker rm
- **Database:** Delete `searxng.db` file

No destructive changes to existing SearXNG configuration.

---

## Next Steps

1. [ ] Approve Milestone 1 (enable OpenMetrics)
2. [ ] Test metrics endpoint
3. [ ] Approve Milestone 2 (build logger)
4. [ ] Deploy logger
5. [ ] Verify query counts
6. [ ] Approve Milestone 4 (dashboard)