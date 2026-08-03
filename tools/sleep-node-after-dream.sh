#!/usr/bin/env bash
# sleep-node-after-dream.sh — return node3090 to standby after a dream cycle,
# but ONLY stopping what this cycle itself started.
#
# Counterpart to wake-node-for-dream.sh. As of the 2026-08-03 rework
# (docs/SPEC-on-demand-engine-start-2026-08.md §4.3), that script tracks two
# INDEPENDENT ownership facts, each with its own marker:
#   WOKE_MARKER   — this cycle changed node3090's POWER STATE; only present
#                   authority to shut the node down.
#   ENGINE_MARKER — this cycle LAUNCHED a llama-server; only present
#                   authority to stop that process.
# A cycle can hold either, both, or neither (e.g. the node was already
# awake but no engine was running yet: engine marker only, node power is
# left alone). Treating these as one fact was Hazard E in the spec — this
# script must not assume "we woke it" implies "we started its engine", or
# the reverse.
#
#   RULE: only power down what we powered up. Only stop what we started.
#
# MECHANISM. Matches goethe_node.shutdown_node(): node3090 carries
# /etc/sudoers.d/lse-shutdown granting lse-admin NOPASSWD on shutdown.
# shutdown_node() is an agent tool and cannot be called from an unattended
# systemd-driven script, so the same pre-approved command is issued here.
#
# Two behaviours copied deliberately from shutdown_node():
#   - BatchMode=yes, so a missing key fails fast rather than hanging on a
#     password prompt inside a nightly job.
#   - ssh exit 255 counts as SUCCESS. sshd drops the connection mid-session as
#     the OS goes down; that looks like an SSH transport error but is exactly
#     the expected outcome. Treating it as failure would log a false alarm on
#     every successful shutdown.
#
# CONTRACT: always exits 0. A node (or engine) left running is a cost, not
# a corruption, and must never turn a successful dream cycle into a failed
# one.

set -uo pipefail

WOKE_MARKER="${GOETHE_DREAM_WOKE_MARKER:-/var/lib/lse-dream/.woke-node3090}"
ENGINE_MARKER="${GOETHE_DREAM_ENGINE_MARKER:-/var/lib/lse-dream/.engine-started-node3090}"
NODE_USER="${GOETHE_NODE3090_SSH_USER:-lse-admin}"
NODE_HOST="${GOETHE_NODE3090_SSH_HOST:-node3090.home.arpa}"
NODE_SSH="${NODE_USER}@${NODE_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes)

log() { echo "[sleep-node] $(date -u +%H:%M:%SZ) $*"; }

# ── Engine: stop only what this cycle started, before anything else ──────
if [[ -f "$ENGINE_MARKER" ]]; then
  log "this cycle started an engine on node3090 -- stopping it before power actions"
  # Bracketed char so pkill -f does not match its own ssh cmdline (the same
  # footgun documented in start-engine-on-node.sh / ssh_run's PKILL RULE).
  if timeout 30 ssh "${SSH_OPTS[@]}" "$NODE_SSH" "pkill -f 'llama[-]server'" >/dev/null 2>&1; then
    log "engine stop signal sent"
  else
    log "WARNING: engine stop failed or nothing was running to stop -- continuing"
  fi
  rm -f "$ENGINE_MARKER" 2>/dev/null || true
else
  log "no engine marker at $ENGINE_MARKER -- this cycle did not start an engine, leaving any running engine alone"
fi

if [[ ! -f "$WOKE_MARKER" ]]; then
  log "no wake marker at $WOKE_MARKER -- node3090 was already awake before this cycle; leaving it running"
  exit 0
fi

log "this cycle woke node3090 -- returning it to standby"

# Best-effort graceful container stop first. The OS shutdown sequence would
# stop them anyway via the docker unit, but only with systemd's default kill
# timeout; asking docker directly gives each container its own stop grace
# period. Entirely optional -- any failure here is logged and ignored.
if timeout 90 ssh "${SSH_OPTS[@]}" "$NODE_SSH" \
    'command -v docker >/dev/null 2>&1 && [ -n "$(docker ps -q)" ] && docker stop $(docker ps -q)' \
    >/dev/null 2>&1; then
  log "containers stopped gracefully"
else
  log "no running containers, or docker stop skipped/failed -- continuing"
fi

timeout 60 ssh "${SSH_OPTS[@]}" "$NODE_SSH" "sudo shutdown -h now" >/dev/null 2>&1
rc=$?
if (( rc == 0 || rc == 255 )); then
  log "shutdown accepted by node3090 (ssh rc=$rc)"
else
  log "WARNING: shutdown failed (ssh rc=$rc) -- node3090 LEFT RUNNING"
fi

rm -f "$WOKE_MARKER" 2>/dev/null || true
exit 0
