#!/usr/bin/env bash
# wake-node-for-dream.sh — ensure node3090's dreamer LLM is reachable before
# a TRAUM cycle starts.
#
# R1 (docs/TRAUM-R1-R3-PLAN.md, Step 1.1). Both real legs of the dreamer
# cascade (call_dream_llm in dream_runner.py) live on node3090; a sleeping
# node has zero fallback inside the cascade itself. This script closes that
# gap from the outside, before the cascade is ever called.
#
# REWORKED 2026-08-03 per docs/SPEC-on-demand-engine-start-2026-08.md.
# The original version polled /health after WoL and treated "did not
# answer within 300s" as a single failure. That conflated two different
# facts: whether the node's *power state* changed, and whether an
# *engine* was ever going to be listening on :8080 to answer. Nothing
# starts llama-server on boot (deliberate — see the spec), so the old
# script's poll was waiting on a service that was never going to appear.
# Measured live 2026-08-02: wake succeeded in 29s, then five more minutes
# were spent polling a port nothing would ever open, the run was logged as
# a failure, and the node sat powered on and idle for hours because the
# false failure meant no wake-marker was written.
#
# CONTRACT
#   exit 0 — node3090 is reachable AND (this cycle's requested role, or
#            whatever was already running) answers /health.
#   exit 1 — it never became reachable within the wake timeout.
#   Never hangs. Never exits non-zero for any reason other than "node did
#   not wake". One log line per state transition, to stdout.
#
# THREE PHASES, each with its own timeout and its own log line:
#   1. wake    — ICMP answering (WoL if needed). Default 120s.
#                The wake marker is written HERE, the moment the node's
#                power state is confirmed changed by this cycle — NOT
#                after the engine is healthy. Conflating "we changed the
#                node's power state" with "a service is ready" is exactly
#                what left node3090 idling for hours on 2026-08-02.
#   2. start   — tools/start-engine-on-node.sh --node node3090 --role dream.
#                Idempotent: does nothing if the requested profile is
#                already running, refuses to kill a different one, refuses
#                a missing profile. Default 300s (model load is >2min).
#   3. verify  — final /health confirmation. Covered by phase 2's own poll;
#                re-checked here to produce a clear phase-3 log line and to
#                give this script's own exit code an independent source of
#                truth rather than trusting phase 2's exit code alone.
#
# ENGINE OWNERSHIP is tracked SEPARATELY from power-state ownership (Hazard
# E, spec §3): a wake marker means "this cycle may power the node down
# afterwards"; an engine marker means "this cycle may stop the engine it
# started". A cycle can own one, both, or neither — e.g. the node was
# already awake (no wake marker) but no engine was running yet (this cycle
# still gets an engine marker and sleep-node-after-dream.sh will stop just
# the engine, leaving the node running, because it does not own the power
# state).
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
# WHY PHASE 1 POLLS ICMP, NOT /health
#   Measured: boot completes ~20s after the packet, but llama-server needs
#   MORE THAN 2 MINUTES beyond that to load the model, AND (as of this
#   rework) nothing starts it automatically at all — phase 2 does that.
#   Polling /health for "is the node awake" was always measuring the wrong
#   thing; it happened to work only by accident, when something else had
#   left an engine running from a previous session.

set -uo pipefail

NODE_NAME="${GOETHE_DREAM_NODE_NAME:-node3090}"
ROLE="${GOETHE_DREAM_ROLE:-dream}"
NODE_HOST="${GOETHE_NODE3090_HOST:-node3090.home.arpa}"
NODE_HEALTH_URL="${GOETHE_NODE3090_LLM_URL:-http://${NODE_HOST}:8080}/health"
NODE_MAC="0c:9d:92:84:6e:6a"

RUTX50_HOST="${GOETHE_RUTX50_HOST:-192.168.5.3}"
RUTX50_USER="${GOETHE_RUTX50_USER:-root}"
RUTX50_KEY="${GOETHE_RUTX50_KEY:-$HOME/.ssh/id_ed25519_rutx50}"
RUTX50_IFACE="${GOETHE_RUTX50_IFACE:-eth0}"

PFSENSE_URL="${PFSENSE_URL:-https://pfsense.home.arpa}"
PFSENSE_IFACE="opt1"

PHASE1_WAKE_TIMEOUT_S="${GOETHE_DREAM_WAKE_TIMEOUT_S:-120}"
PHASE2_START_TIMEOUT_S="${GOETHE_DREAM_START_TIMEOUT_S:-300}"

# Written when phase 1 changes the node's power state — see header. Presence
# grants sleep-node-after-dream.sh authority to power the node back down.
WOKE_MARKER="${GOETHE_DREAM_WOKE_MARKER:-/var/lib/lse-dream/.woke-node3090}"
# Written when phase 2 actually LAUNCHES an engine (not when one was already
# running). Presence grants sleep-node-after-dream.sh authority to stop it.
# Independent of WOKE_MARKER — see header "ENGINE OWNERSHIP".
ENGINE_MARKER="${GOETHE_DREAM_ENGINE_MARKER:-/var/lib/lse-dream/.engine-started-node3090}"

POLL_INTERVAL_S=5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  echo "[wake-node-for-dream] $(date -u +%H:%M:%SZ) $*"
}

reachable() {
  ping -c 1 -W 2 "$NODE_HOST" >/dev/null 2>&1
}

health_ok() {
  curl -sf -o /dev/null -m 3 "$NODE_HEALTH_URL"
}

# Markers left behind by a previous run (crash, kill -9) must never grant
# ownership to THIS run.
rm -f "$WOKE_MARKER" 2>/dev/null || true
rm -f "$ENGINE_MARKER" 2>/dev/null || true

# ── Phase 1: wake ────────────────────────────────────────────────────────
woke_this_cycle=0

if reachable; then
  log "phase 1 (wake): $NODE_NAME already reachable (ping) -- no wake needed"
  log "phase 1 (wake): no wake performed; this cycle will NOT power the node down afterwards"
else
  log "phase 1 (wake): $NODE_NAME not reachable -- attempting wake"

  woken_signal=0

  # --- Primary: SSH to RUTX50, etherwake on node3090's own L2 segment ---
  if [[ -f "$RUTX50_KEY" ]]; then
    log "phase 1 (wake): sending etherwake via RUTX50 ($RUTX50_HOST)"
    if ssh -i "$RUTX50_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
        "${RUTX50_USER}@${RUTX50_HOST}" \
        "etherwake -i ${RUTX50_IFACE} ${NODE_MAC}" >/dev/null 2>&1; then
      log "phase 1 (wake): etherwake command sent via RUTX50"
      woken_signal=1
    else
      log "phase 1 (wake): WARNING SSH/etherwake to RUTX50 failed -- trying pfSense fallback"
    fi
  else
    log "phase 1 (wake): WARNING RUTX50 key not found at $RUTX50_KEY -- trying pfSense fallback"
  fi

  # --- Fallback: pfSense WoL POST, only if a key is already in the environment ---
  if [[ "$woken_signal" -eq 0 ]]; then
    if [[ -n "${PFSENSE_API_KEY:-}" ]]; then
      log "phase 1 (wake): sending WoL via pfSense ($PFSENSE_URL, interface $PFSENSE_IFACE)"
      if curl -sf -m 15 -X POST "${PFSENSE_URL%/}/api/v2/services/wake_on_lan/send" \
          -H "X-API-Key: ${PFSENSE_API_KEY}" -H "Content-Type: application/json" \
          -d "{\"interface\":\"${PFSENSE_IFACE}\",\"mac\":\"${NODE_MAC}\"}" \
          -o /dev/null; then
        log "phase 1 (wake): pfSense WoL POST accepted"
        woken_signal=1
      else
        log "phase 1 (wake): WARNING pfSense WoL POST failed"
      fi
    else
      log "phase 1 (wake): PFSENSE_API_KEY not set in environment -- pfSense fallback skipped (this script never fetches secrets itself; export it before running if that leg is needed)"
    fi
  fi

  if [[ "$woken_signal" -eq 0 ]]; then
    log "phase 1 (wake): no wake mechanism succeeded -- exiting 1 without polling"
    exit 1
  fi

  # --- Poll ICMP, never /health -- boot is ~20s; whether an engine ever ---
  # --- answers /health is phase 2 and phase 3's concern, not phase 1's.  ---
  elapsed=0
  while (( elapsed < PHASE1_WAKE_TIMEOUT_S )); do
    if reachable; then
      log "phase 1 (wake): $NODE_NAME reachable after ${elapsed}s -- awake"
      if mkdir -p "$(dirname "$WOKE_MARKER")" 2>/dev/null && \
         printf 'woken by wake-node-for-dream.sh at %s\n' "$(date -Is)" > "$WOKE_MARKER" 2>/dev/null; then
        log "phase 1 (wake): wrote wake marker $WOKE_MARKER -- this cycle owns the node's power state and may power it down"
        woke_this_cycle=1
      else
        log "phase 1 (wake): WARNING could not write $WOKE_MARKER; the node will be LEFT RUNNING after the cycle"
      fi
      break
    fi
    sleep "$POLL_INTERVAL_S"
    elapsed=$(( elapsed + POLL_INTERVAL_S ))
    log "phase 1 (wake): waiting for ping ... ${elapsed}s/${PHASE1_WAKE_TIMEOUT_S}s"
  done

  if (( elapsed >= PHASE1_WAKE_TIMEOUT_S )) && ! reachable; then
    log "phase 1 (wake): timed out after ${PHASE1_WAKE_TIMEOUT_S}s -- $NODE_NAME did not become reachable"
    exit 1
  fi
fi

# ── Phase 2: start ───────────────────────────────────────────────────────
log "phase 2 (start): invoking start-engine-on-node.sh --node $NODE_NAME --role $ROLE --timeout-s $PHASE2_START_TIMEOUT_S"
start_out=$(bash "$SCRIPT_DIR/start-engine-on-node.sh" --node "$NODE_NAME" --role "$ROLE" --timeout-s "$PHASE2_START_TIMEOUT_S" 2>&1)
start_rc=$?
while IFS= read -r line; do
  log "phase 2 (start): $line"
done <<<"$start_out"

case "$start_rc" in
  0)
    if grep -q '^RESULT=started$' <<<"$start_out"; then
      if mkdir -p "$(dirname "$ENGINE_MARKER")" 2>/dev/null && \
         printf 'engine started by wake-node-for-dream.sh (role=%s) at %s\n' "$ROLE" "$(date -Is)" > "$ENGINE_MARKER" 2>/dev/null; then
        log "phase 2 (start): wrote engine marker $ENGINE_MARKER -- this cycle owns the engine and may stop it"
      else
        log "phase 2 (start): WARNING could not write $ENGINE_MARKER; engine will be LEFT RUNNING after the cycle even if this cycle owns node power"
      fi
    else
      log "phase 2 (start): engine was already running and matching -- this cycle does not own it, no engine marker written"
    fi
    ;;
  3)
    log "phase 2 (start): CONFLICT -- a different profile is already serving ${NODE_NAME}:8080; leaving it running, not treating this as a wake failure"
    ;;
  *)
    log "phase 2 (start): did not start an engine (rc=$start_rc); node power state above is unaffected by this"
    ;;
esac

# ── Phase 3: verify ──────────────────────────────────────────────────────
if health_ok; then
  log "phase 3 (verify): /health OK -- $NODE_NAME up and serving"
  exit 0
fi

log "phase 3 (verify): /health not answering ($NODE_HEALTH_URL) -- $NODE_NAME is awake but not serving"
exit 1
