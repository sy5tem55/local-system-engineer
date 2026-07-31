#!/usr/bin/env bash
# check_goethe_mirror_sync.sh — detect staleness of the Windows-side goethe.py mirror
# D1 audit 2026-07-31: the Windows mirror at /mnt/c is known to lag the live WSL repo.
# This script compares sha256 of the live tools/goethe.py against the mirror copy
# and reports IN SYNC or STALE with a non-zero exit code.
#
# Usage: bash scripts/check_goethe_mirror_sync.sh
#
# Optional crontab (weekly Monday 9am — adjust path to your repo):
#   0 9 * * 1 bash /home/sy5/projects/local-system-engineer/scripts/check_goethe_mirror_sync.sh

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
LIVE="$REPO_ROOT/tools/goethe.py"
MIRROR="/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/tools/goethe.py"

if [[ ! -f "$LIVE" ]]; then
    echo "ERROR: live file not found: $LIVE"
    exit 2
fi

if [[ ! -f "$MIRROR" ]]; then
    echo "ERROR: mirror file not found: $MIRROR"
    echo "       Update MIRROR path in this script if the Windows repo moved."
    exit 2
fi

LIVE_SHA=$(sha256sum "$LIVE" | awk '{print $1}')
MIRROR_SHA=$(sha256sum "$MIRROR" | awk '{print $1}')

LIVE_MTIME=$(stat -c '%Y %n' "$LIVE")
MIRROR_MTIME=$(stat -c '%Y %n' "$MIRROR")

if [[ "$LIVE_SHA" == "$MIRROR_SHA" ]]; then
    echo "IN SYNC"
    echo "  live:   sha256=$LIVE_SHA  mtime=$LIVE_MTIME"
    echo "  mirror: sha256=$MIRROR_SHA mtime=$MIRROR_MTIME"
    exit 0
else
    LIVE_DATE=$(date -d "@${LIVE_MTIME%% *}" '+%Y-%m-%d %H:%M')
    MIRROR_DATE=$(date -d "@${MIRROR_MTIME%% *}" '+%Y-%m-%d %H:%M')
    DELTA_SEC=$(( $(date +%s) - $(date -d "$MIRROR_DATE" +%s) ))
    DELTA_DAYS=$(( DELTA_SEC / 86400 ))

    echo "STALE: mirror differs from tools/goethe.py"
    echo "  live:   sha256=$LIVE_SHA  updated $LIVE_DATE"
    echo "  mirror: sha256=$MIRROR_SHA updated $MIRROR_DATE ($DELTA_DAYS day(s) ago)"
    echo "  → re-copy manually: cp tools/goethe.py '$MIRROR'"
    exit 1
fi
