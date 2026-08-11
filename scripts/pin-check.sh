#!/usr/bin/env bash
# pin-check.sh — will the GUI start? Answer with an exit code, not prose.
#
# Why this exists
# ---------------
# C:\Goethe3.0\...\Scripts\goethe_mcp.py is a no-replace launcher shim. It
# SHA-256s tools/goethe_mcp.py and refuses to launch on any drift. Nothing
# inside this repo mentions that coupling, so on 2026-08-08 an ordinary,
# reviewed, fully-tested edit to that file broke the HTTP gateway — and the
# refusal surfaced two layers below the cause as:
#
#     ProcessLookupError: [Errno 3] No such process
#     [start-goethe-safe] ERROR: launch supervisor degraded before ownership
#                                publication  /  exit 54
#
# This script makes that state visible BEFORE a restart instead of after.
#
# What it deliberately does NOT do
# --------------------------------
# It never writes a hash. The pin is a review checkpoint: the launcher refuses
# source that nobody signed off. A tool that re-pins whenever the source
# changes converts that control into a checksum of "whatever is there" — it
# still runs, but it can no longer refuse anything. Same failure as letting an
# implementer write the test that guards its own work.
#
# So: this reports, and prints the exact command for a human to run. There are
# 15 shims on this machine and only one the GUI launches from; knowing which
# is the whole job, and that part is mechanical.
#
# THE RULE THAT MAKES RE-PINNING SAFE
#   A pin may only ever reference a COMMITTED hash. Pinning a dirty working
#   tree authorises code that exists nowhere but that tree — one git checkout,
#   branch switch or stash and the GUI breaks against a hash git has never
#   seen. Exit 2 exists solely for that case.
#
# Usage
#   scripts/pin-check.sh
#   GOETHE_GUI_DEPLOY_DIR=/mnt/c/Goethe3.0/.deploy-staging/<other>/win-x64 scripts/pin-check.sh
#
# Exit codes
#   0  live shim matches, and the pinned hash is committed — safe to restart
#   1  live shim is STALE — the GUI will NOT start
#   2  live shim matches but the source is UNCOMMITTED — starts now, fragile
#   3  cannot locate the live shim or the source
set -uo pipefail

DEPLOY_DIR="${GOETHE_GUI_DEPLOY_DIR:-/mnt/c/Goethe3.0/.deploy-staging/Goethe.App-20260801-safe-03/win-x64}"
LIVE_SHIM="$DEPLOY_DIR/Scripts/goethe_mcp.py"
CANON_SHIM="/mnt/c/Goethe3.0/Goethe.App/Scripts/goethe_mcp.py"
SOURCE="tools/goethe_mcp.py"

cd "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || {
  echo "[pin-check] not inside the repo" >&2; exit 3; }

[ -f "$SOURCE" ]    || { echo "[pin-check] missing $SOURCE" >&2; exit 3; }
[ -f "$LIVE_SHIM" ] || { echo "[pin-check] live shim not found: $LIVE_SHIM" >&2
                         echo "[pin-check] set GOETHE_GUI_DEPLOY_DIR if the GUI launches elsewhere." >&2
                         exit 3; }

pin_of() { grep -A1 UPSTREAM_SHA256 "$1" 2>/dev/null | grep -oE '[0-9a-f]{64}' | head -1; }

SRC_HASH=$(sha256sum "$SOURCE" | cut -d' ' -f1)
HEAD_HASH=$(git show "HEAD:$SOURCE" 2>/dev/null | sha256sum | cut -d' ' -f1)
LIVE_PIN=$(pin_of "$LIVE_SHIM")
CANON_PIN=$(pin_of "$CANON_SHIM")
DIRTY=0
git diff --quiet -- "$SOURCE" || DIRTY=1

echo "[pin-check] source   $SOURCE"
echo "[pin-check]   working tree $SRC_HASH"
echo "[pin-check]   at HEAD      $HEAD_HASH$( [ "$DIRTY" = 1 ] && echo '   <- differs: UNCOMMITTED' )"
echo "[pin-check] GUI launches from: $DEPLOY_DIR"
echo "[pin-check]   live shim pin  ${LIVE_PIN:-<none found>}"
echo "[pin-check]   canonical pin  ${CANON_PIN:-<none found>}"

# Everything else is noise — count it, do not fail on it.
OTHERS=0; OTHERS_STALE=0
while IFS= read -r f; do
  [ "$f" = "$LIVE_SHIM" ] && continue
  [ "$f" = "$CANON_SHIM" ] && continue
  OTHERS=$((OTHERS+1))
  [ "$(pin_of "$f")" = "$SRC_HASH" ] || OTHERS_STALE=$((OTHERS_STALE+1))
done < <(find /mnt/c/Goethe3.0 -name goethe_mcp.py -path '*Scripts*' 2>/dev/null)
echo "[pin-check] other shims: $OTHERS found, $OTHERS_STALE stale (backups and build outputs — not launched, ignored)"
echo

if [ "$LIVE_PIN" != "$SRC_HASH" ]; then
  echo "[pin-check] STALE: the GUI will NOT start. Expected $SRC_HASH" >&2
  echo "[pin-check] Review the diff, then re-pin BY HAND — this script will not do it:" >&2
  echo "[pin-check]     $SOURCE  ->  $LIVE_SHIM" >&2
  echo "[pin-check]     replace ${LIVE_PIN:-<pin>} with $SRC_HASH" >&2
  exit 1
fi

if [ "$DIRTY" = 1 ]; then
  echo "[pin-check] WARNING: the live pin matches, so the GUI starts — but it"
  echo "[pin-check] authorises a hash that is NOT COMMITTED. A git checkout,"
  echo "[pin-check] branch switch or stash of $SOURCE reverts it to"
  echo "[pin-check] $HEAD_HASH and the GUI breaks."
  echo "[pin-check] Commit $SOURCE. Do not re-pin to fix this."
  exit 2
fi

echo "[pin-check] OK: live shim pins the current, committed source. Safe to restart."
exit 0
