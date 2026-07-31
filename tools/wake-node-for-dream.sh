#!/usr/bin/env bash
# wake-node-for-dream.sh — ensure node3090's dreamer LLM is reachable before
# a TRAUM cycle starts.
#
# R1 (docs/TRAUM-R1-R3-PLAN.md, Step 1.1). Both real legs of the dreamer
# cascade (call_dream_llm in dream_runner.py) live on node3090; a sleeping
# node has zero fallback inside the cascade itself. This script closes that
# gap from the outside, before the cascade is ever called.
#
# CONTRACT
#   exit 0 — node3090 is reachable AND its llama-server answers /health
#   exit 1 — it never came up within the timeout
#   Never hangs. Never exits non-zero for any reason other than "node did
#   not wake". One log line per state transition, to stdout.
#
# WHY etherwake-via-RUTX50 IS PRIMARY, NOT wakeonlan
#   Measured live 2026-07-31 (kb/network-topology.md, docs/TRAUM-R1-R3-PLAN.md
#   §"How the wake facts above were arrived at"): bare `wakeonlan <mac>` from
#   LUCIFER prints "Sending magic packet" and exits 0 whether or not the
#   packet ever arrives — it does NOT wake node3090, and it fails silently.
#   SSHing into the RUTX50 router and running `etherwake` puts the frame
#   directly on node3090's own L2 segment: no routing, no broadcast
#   forwarding, no pfSense state required. This is the canonical procedure
#   per KB doc 842595879f70576d (quality 1.0), used by the operator's own
#   "power up node3090" flow for weeks. Do not replace this with bare
#   wakeonlan; see the KB doc for the full 4-method comparison.
#
# WHY THE pfSense FALLBACK IS CONDITIONAL, NOT SELF-SUFFICIENT
#   goethe_node.py's wake_node() POSTs to pfSense using PFSENSE_API_KEY, and
#   tools/pfsense-gateway-tools.sh documents why that key is deliberately
#   NOT stored anywhere an unattended script can read it on its own:
#   "PFSENSE_API_KEY is not stored here... LSE retrieves it from Vaultwarden
#   and passes it via the PFSENSE_API_KEY env var." This script honours that
#   boundary exactly: if PFSENSE_API_KEY is already present in the
#   environment when this script runs, it will use it as a second leg.
#   Otherwise it skips the pfSense leg and says so in the log. It never
#   fetches a vault secret itself and never hardcodes a key.
#
# WHY /health, NOT ping
#   Measured: boot completes ~20s after the packet, but llama-server needs
#   MORE THAN 2 MINUTES beyond that to load the model. A ping-based check
#   would report "up" while the endpoint this script exists to guarantee is
#   still unusable.

set -uo pipefail

NODE_HOST="${GOETHE_NODE3090_HOST:-node3090.home.arpa}"
NODE_HEALTH_URL="${GOETHE_NODE3090_LLM_URL:-http://${NODE_HOST}:8080}/health"
NODE_MAC="0c:9d:92:84:6e:6a"

RUTX50_HOST="${GOETHE_RUTX50_HOST:-192.168.5.3}"
RUTX50_USER="${GOETHE_RUTX50_USER:-root}"
RUTX50_KEY="${GOETHE_RUTX50_KEY:-$HOME/.ssh/id_ed25519_rutx50}"
RUTX50_IFACE="${GOETHE_RUTX50_IFACE:-eth0}"

PFSENSE_URL="${PFSENSE_URL:-https://pfsense.home.arpa}"
PFSENSE_IFACE="opt1"

WAKE_TIMEOUT_S="${GOETHE_DREAM_WAKE_TIMEOUT_S:-300}"
POLL_INTERVAL_S=5

log() {
  echo "[wake-node-for-dream] $(date -u +%H:%M:%SZ) $*"
}

health_ok() {
  curl -sf -o /dev/null -m 3 "$NODE_HEALTH_URL"
}

if health_ok; then
  log "node3090 already reachable, /health OK -- nothing to do"
  exit 0
fi

log "node3090 /health not responding ($NODE_HEALTH_URL) -- attempting wake"

woken=0

# --- Primary: SSH to RUTX50, etherwake on node3090's own L2 segment ---
if [[ -f "$RUTX50_KEY" ]]; then
  log "sending etherwake via RUTX50 ($RUTX50_HOST)"
  if ssh -i "$RUTX50_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
      "${RUTX50_USER}@${RUTX50_HOST}" \
      "etherwake -i ${RUTX50_IFACE} ${NODE_MAC}" >/dev/null 2>&1; then
    log "etherwake command sent via RUTX50"
    woken=1
  else
    log "WARNING: SSH/etherwake to RUTX50 failed -- trying pfSense fallback"
  fi
else
  log "WARNING: RUTX50 key not found at $RUTX50_KEY -- trying pfSense fallback"
fi

# --- Fallback: pfSense WoL POST, only if a key is already in the environment ---
if [[ "$woken" -eq 0 ]]; then
  if [[ -n "${PFSENSE_API_KEY:-}" ]]; then
    log "sending WoL via pfSense ($PFSENSE_URL, interface $PFSENSE_IFACE)"
    if curl -sf -m 15 -X POST "${PFSENSE_URL%/}/api/v2/services/wake_on_lan/send" \
        -H "X-API-Key: ${PFSENSE_API_KEY}" -H "Content-Type: application/json" \
        -d "{\"interface\":\"${PFSENSE_IFACE}\",\"mac\":\"${NODE_MAC}\"}" \
        -o /dev/null; then
      log "pfSense WoL POST accepted"
      woken=1
    else
      log "WARNING: pfSense WoL POST failed"
    fi
  else
    log "PFSENSE_API_KEY not set in environment -- pfSense fallback skipped (this script never fetches secrets itself; export it before running if that leg is needed)"
  fi
fi

if [[ "$woken" -eq 0 ]]; then
  log "no wake mechanism succeeded -- exiting 1 without polling"
  exit 1
fi

# --- Poll /health, never ping -- boot is ~20s, model load is >2min more ---
elapsed=0
while (( elapsed < WAKE_TIMEOUT_S )); do
  if health_ok; then
    log "node3090 /health OK after ${elapsed}s -- awake"
    exit 0
  fi
  sleep "$POLL_INTERVAL_S"
  elapsed=$(( elapsed + POLL_INTERVAL_S ))
  log "waiting for /health ... ${elapsed}s/${WAKE_TIMEOUT_S}s"
done

log "timed out after ${WAKE_TIMEOUT_S}s -- node3090 did not become healthy"
exit 1
