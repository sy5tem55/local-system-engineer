#!/usr/bin/env bash
# sync-docker-config.sh
# Syncs repo docker config files → live /home/sy5/docker/
# Run from WSL2 after any config change committed to the repo.
#
# SAFE to run: only copies non-secret config files (prometheus.yml,
# alert-rules.yml, grafana datasources/dashboards). Does NOT touch
# searxng_data/settings.yml (root-owned, managed separately).
#
# Usage: bash scripts/sync-docker-config.sh [--reload]
#   --reload  also send SIGHUP to Prometheus and restart Grafana after copy

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIVE_DOCKER="/home/sy5/docker"

echo "=== sync-docker-config.sh ==="
echo "Repo: $REPO_ROOT/docker/"
echo "Live: $LIVE_DOCKER/"
echo ""

RELOAD=false
[[ "${1:-}" == "--reload" ]] && RELOAD=true

sync_file() {
    local src="$1" dst="$2"
    if [[ ! -f "$src" ]]; then
        echo "  SKIP  $src (not found in repo)"
        return
    fi
    if diff -q "$src" "$dst" &>/dev/null 2>&1; then
        echo "  OK    $(basename "$src") (unchanged)"
    else
        cp "$src" "$dst"
        echo "  SYNCED $(basename "$src")"
    fi
}

# Prometheus
echo "--- Prometheus ---"
sync_file "$REPO_ROOT/prometheus/prometheus.yml"     "$LIVE_DOCKER/prometheus/prometheus.yml"
sync_file "$REPO_ROOT/prometheus/alert-rules.yml"   "$LIVE_DOCKER/prometheus/alert-rules.yml"

# Grafana datasources
echo "--- Grafana ---"
sync_file "$REPO_ROOT/docker/grafana/datasources/datasource.yml" "$LIVE_DOCKER/grafana/datasources/datasource.yml"

# Grafana dashboards
for f in "$REPO_ROOT/docker/grafana/dashboards/"*.{json,yml}; do
    [[ -f "$f" ]] || continue
    fname="$(basename "$f")"
    sync_file "$f" "$LIVE_DOCKER/grafana/dashboards/$fname"
done

echo ""
echo "--- Sync complete ---"

if $RELOAD; then
    echo ""
    echo "Reloading services..."
    if docker kill -s HUP prometheus 2>/dev/null; then
        echo "  prometheus: SIGHUP sent (config reloaded, no restart)"
    else
        echo "  prometheus: not running or SIGHUP failed"
    fi
    sleep 3
    echo ""
    echo "--- Prometheus target health ---"
    curl -s "http://localhost:9090/api/v1/targets" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for t in data['data']['activeTargets']:
    job = t['labels']['job']
    health = t['health']
    err = t.get('lastError', '')[:70]
    marker = '✓' if health == 'up' else '✗'
    print(f'  {marker} {job:35s} {health}  {err}')
" 2>/dev/null || echo "  (could not query Prometheus targets)"
fi

echo ""
echo "REMINDER: searxng_data/settings.yml is root-owned and NOT synced by this script."
echo "To update it: sudo cp \$REPO/docker/searxng_data/settings.yml /home/sy5/docker/searxng_data/settings.yml"
echo "              sudo chown root:root /home/sy5/docker/searxng_data/settings.yml"
echo "              docker compose -f /home/sy5/docker/docker-compose.yml restart searxng"
