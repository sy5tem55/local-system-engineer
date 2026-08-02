#!/usr/bin/env bash
# sleep-node-after-dream.sh — return node3090 to standby after a dream cycle,
# but ONLY if this cycle is the thing that woke it.
#
# Counterpart to wake-node-for-dream.sh. That script writes WOKE_MARKER only
# when it actually performed a wake; if node3090 was already awake when the
# preflight looked, somebody else owns it -- most likely the operator working
# late -- and powering it off would be destructive.
#
#   RULE: only power down what we powered up.
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
# CONTRACT: always exits 0. A node left running is a cost, not a corruption,
# and must never turn a successful dream cycle into a failed one.

set -uo pipefail

WOKE_MARKER="${GOETHE_DREAM_WOKE_MARKER:-/var/lib/lse-dream/.woke-node3090}"
NODE_USER="${GOETHE_NODE3090_SSH_USER:-lse-admin}"
NODE_HOST="${GOETHE_NODE3090_SSH_HOST:-node3090.home.arpa}"
NODE_SSH="${NODE_USER}@${NODE_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes)

log() { echo "[sleep-node] $(date -u +%H:%M:%SZ) $*"; }

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
