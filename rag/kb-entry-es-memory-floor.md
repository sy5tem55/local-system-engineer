## 2026-06-01 — Elasticsearch memory floor + Compose migration

### What happened
Elasticsearch was repeatedly exiting with code 143 (SIGTERM from Docker OOM enforcement)
during long sessions. Root cause: container was started with a bare `docker run` with
no `--memory` flag, so Docker imposed no limit. Under sustained indexing/search load the
process grew beyond available headroom and was killed.

### Discovery path
- No docker-compose.yml referenced elasticsearch (grep confirmed)
- No launch script in /home/sy5 (grep confirmed)
- No shell history entry
- `docker inspect` revealed: Memory=0, MemoryReservation=0 — completely unconstrained
- ES_JAVA_OPTS already had `-Xms512m -Xmx1g` (heap capped), but OS/Lucene off-heap was unbounded

### Fix applied
Created `/home/sy5/docker/elasticsearch-compose.yml` (later to be merged into
`/home/sy5/docker/docker-compose.yml`) with:

```yaml
mem_limit: 2g
mem_reservation: 1g
environment:
  - ES_JAVA_OPTS=-Xms512m -Xmx1g
  - discovery.type=single-node
  - xpack.security.enabled=false
```

Rationale: heap=1g max → container needs 2g (1g heap + 1g for Lucene page cache).
Going below this causes Lucene cache eviction and index performance collapse.

Existing `es-data` named volume preserved — data survived container recreation.

### Recovery command (canonical — use this, not docker run)
```bash
cd /home/sy5/docker && docker compose up -d elasticsearch
```

### Do NOT do this
```bash
docker run -d --name elasticsearch elasticsearch:8.17.0  # no limits — will OOM again
```

### Verification
```bash
docker inspect elasticsearch --format '{{.HostConfig.Memory}} {{.HostConfig.MemoryReservation}}'
# expected: 2147483648 1073741824

curl -s http://localhost:9200/_cluster/health | python3 -m json.tool
# expected: status green or yellow
```

### Skill updated
lse-stack-health-check SKILL.md updated to:
- Add Elasticsearch to stack map and check sequence
- Add ES recovery section with Compose command and OOM diagnostic
- Mark ES as a critical service (❌ if down)
