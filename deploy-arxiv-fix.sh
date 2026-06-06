#!/usr/bin/env bash
# Deploy all fixes:
#   - arxiv timeout 6s → 15s
#   - limiter disabled (was blocking LSE requests)
#   - open_metrics enabled under general: section (not server: — webapp reads from general)
#   - logger metrics password synced to match Prometheus/SearXNG
# Run: sudo bash /mnt/c/Users/SY5/Claude/Projects/local-system-engineer/deploy-arxiv-fix.sh
set -e

DOCKER_DIR=/home/sy5/docker
PROJECT=/mnt/c/Users/SY5/Claude/Projects/local-system-engineer

echo "=== [1/5] Deploying SearXNG settings ==="
cp "$PROJECT/searxng_settings.yaml" "$DOCKER_DIR/searxng_data/settings.yml"
echo "  ✓ settings.yml updated"

echo "=== [2/5] Deploying docker-compose.yml (logger password fix) ==="
cp "$PROJECT/docker-compose.yml" "$DOCKER_DIR/docker-compose.yml"
echo "  ✓ docker-compose.yml updated"

echo "=== [3/5] Deploying Grafana dashboard ==="
cp "$PROJECT/grafana-dashboard-searxng-engine-health.json" "$DOCKER_DIR/grafana/dashboards/searxng-engine-health.json"
echo "  ✓ grafana dashboard updated"

echo "=== [4/5] Restarting SearXNG + recreating logger ==="
cd "$DOCKER_DIR"
docker compose restart searxng
docker compose up -d --force-recreate searxng-logger
sleep 6

# Verify metrics endpoint
METRICS=$(curl -s -u "":JZVeoVch20+FvyjXEn4BMVHtu1AM6JCH http://localhost:8088/metrics | head -3)
echo "  Metrics endpoint: $METRICS"
echo "$METRICS" | grep -q "searxng\|#" && echo "  ✓ Metrics enabled" || echo "  ✗ Metrics still not responding — check: docker logs searxng"

echo "=== [5/5] Verifying Prometheus scrape ==="
sleep 20
PROM=$(curl -s "http://localhost:9090/api/v1/query?query=searxng_engines_request_count_total" | python3 -c "import json,sys; d=json.load(sys.stdin); print('data points:', len(d['data']['result']))")
echo "  $PROM"

echo ""
echo "=== Done ==="
