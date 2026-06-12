#!/usr/bin/env bash
# deploy-observability.sh — restore SearxNG metrics observability from the repo.
# Idempotent. Run from WSL: bash observability/deploy-observability.sh
#
# WHAT IT FIXES FOR GOOD (P22): the searxng scrape job kept vanishing because
# the token lived in three conflicting docs and prometheus.yml only existed
# inside WSL. This script derives BOTH sides from observability.env (single
# source of truth) and verifies end-to-end.
set -euo pipefail
cd "$(dirname "$0")"
source ./observability.env

[ -n "$METRICS_TOKEN" ] || { echo "FATAL: METRICS_TOKEN empty"; exit 1; }

# ── 0. Discover prometheus.yml if not pinned in the env file ────────────────
if [ -z "${PROMETHEUS_CONFIG}" ]; then
    PROMETHEUS_CONFIG=$(docker inspect prometheus \
        --format '{{range .Mounts}}{{if eq .Destination "/etc/prometheus/prometheus.yml"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)
    [ -n "$PROMETHEUS_CONFIG" ] || { echo "FATAL: cannot locate prometheus.yml mount — set PROMETHEUS_CONFIG in observability.env"; exit 1; }
    echo "discovered PROMETHEUS_CONFIG=$PROMETHEUS_CONFIG (pin it in observability.env)"
fi

# ── 1. SearxNG side: assert settings.yml token matches the env token ────────
LIVE_TOKEN=$(docker exec searxng sh -c "grep '^  open_metrics:' /etc/searxng/settings.yml | cut -d'\"' -f2" 2>/dev/null || true)
if [ "$LIVE_TOKEN" != "$METRICS_TOKEN" ]; then
    echo "DRIFT: settings.yml token differs — rewriting from env"
    sudo sed -i "s|^  open_metrics:.*|  open_metrics: \"$METRICS_TOKEN\"|" "$SEARXNG_DATA_DIR/settings.yml"
    docker restart searxng >/dev/null
    echo "searxng restarted with canonical token"
fi

# ── 2. Prometheus side: ensure the scrape job exists with the SAME token ────
if grep -q 'job_name: "searxng"' "$PROMETHEUS_CONFIG"; then
    # job exists — fix its password in place if drifted
    if ! grep -A6 'job_name: "searxng"' "$PROMETHEUS_CONFIG" | grep -q "$METRICS_TOKEN"; then
        echo "DRIFT: scrape job has wrong token — rewriting password line"
        sudo python3 - "$PROMETHEUS_CONFIG" "$METRICS_TOKEN" << 'PYEOF'
import re, sys
path, token = sys.argv[1], sys.argv[2]
src = open(path).read()
block = re.search(r'(- job_name: "searxng".*?)(?=\n  - job_name:|\Z)', src, re.S).group(1)
fixed = re.sub(r'password: ".*?"', f'password: "{token}"', block)
open(path, "w").write(src.replace(block, fixed))
PYEOF
    fi
else
    echo "scrape job missing — appending"
    sudo tee -a "$PROMETHEUS_CONFIG" >/dev/null << EOF

  - job_name: "searxng"
    static_configs:
      - targets: ["$SCRAPE_TARGET"]
    metrics_path: "/metrics"
    basic_auth:
      username: ""
      password: "$METRICS_TOKEN"
    scrape_interval: 15s
EOF
fi
docker restart prometheus >/dev/null && echo "prometheus restarted"

# ── 3. Verify end-to-end (hard checks, no self-reports) ─────────────────────
sleep 6
M=$(curl -s -o /dev/null -w "%{http_code}" -u ":$METRICS_TOKEN" http://localhost:8088/metrics)
[ "$M" = "200" ] && echo "OK  /metrics auth (200)" || { echo "FAIL /metrics auth ($M)"; exit 1; }

# health is 'unknown' until the first scrape completes — poll up to 60s
for i in $(seq 1 12); do
    READ=$(curl -s localhost:9090/api/v1/targets | python3 -c "
import json, sys
ts = json.load(sys.stdin)['data']['activeTargets']
t = next((t for t in ts if t['labels']['job'] == 'searxng'), None)
print(t['health'] + '|' + (t.get('lastError') or '') if t else 'absent|')" 2>/dev/null || echo "prom-unreachable|")
    H="${READ%%|*}"
    [ "$H" = "up" ] && break
    sleep 5
done
[ "$H" = "up" ] && echo "OK  prometheus target searxng=up" \
    || { echo "FAIL prometheus target searxng=$H lastError='${READ#*|}'"; exit 1; }

echo "GREEN — dashboard repopulates within ~1 min: http://localhost:3002/d/searxng-engine-health"
