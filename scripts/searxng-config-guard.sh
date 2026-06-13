#!/usr/bin/env bash
# searxng-config-guard.sh — self-repair SearXNG engine-config drift (LSE).
#
# WHY: the live settings.yml has repeatedly been clobbered (stray cp, image
# recreate, session steps), silently thinning the engine fleet. This guard makes
# the repo copy authoritative: if live drifts from canonical, it validates the
# canonical YAML, backs up live, restores canonical, and restarts searxng.
# Idempotent — a no-op when already in sync. Run by a systemd timer (every 10m + boot).
set -euo pipefail

CANONICAL="${CANONICAL:-/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/docker/searxng_data/settings.yml}"
LIVE="${LIVE:-/home/sy5/docker/searxng_data/settings.yml}"
COMPOSE="${COMPOSE:-/home/sy5/docker/docker-compose.yml}"
LOG="${LOG:-/var/log/searxng-config-guard.log}"

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG" >/dev/null; }

[ -f "$CANONICAL" ] || { log "ERROR canonical missing: $CANONICAL"; exit 1; }

# Never deploy a broken config.
if ! python3 -c "import yaml,sys; yaml.safe_load(open('$CANONICAL'))" 2>/dev/null; then
  log "ERROR canonical is not valid YAML — refusing to deploy"; exit 1
fi

CAN_SHA=$(sha256sum "$CANONICAL" | cut -d' ' -f1)
LIVE_SHA=$([ -f "$LIVE" ] && sha256sum "$LIVE" | cut -d' ' -f1 || echo none)

[ "$CAN_SHA" = "$LIVE_SHA" ] && exit 0   # in sync — nothing to do

log "DRIFT (live=$LIVE_SHA canonical=$CAN_SHA) — repairing"
[ -f "$LIVE" ] && cp -a "$LIVE" "${LIVE}.drift-$(date +%Y%m%d%H%M%S)"
install -m 0644 -o root -g root "$CANONICAL" "$LIVE"
docker compose -f "$COMPOSE" restart searxng >/dev/null 2>&1 \
  || docker restart searxng >/dev/null 2>&1 || true
log "REPAIRED from canonical; searxng restarted"
