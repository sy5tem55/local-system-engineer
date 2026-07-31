#!/usr/bin/env bash
# check_goethe_mirror_sync.sh — detect staleness of the Windows-side goethe mirror
#
# D1 audit 2026-07-31: the Windows mirror at /mnt/c is known to lag the live WSL repo.
# This script compares sha256 of each live tool module against its mirror copy and
# reports IN SYNC or STALE with a non-zero exit code.
#
# D7 UPDATE 2026-07-31: the tool surface used to be one file. It is now six —
# goethe.py plus five mixin modules it imports at load time. A mirror holding a
# post-D7 goethe.py WITHOUT the mixins does not merely lag, it FAILS TO IMPORT
# (ModuleNotFoundError: goethe_netsec). That exact state was found in the mirror
# during the D1-D8 final verification pass, which is why this script now checks
# the whole set rather than goethe.py alone. Watching one file out of six is how a
# guard silently stops guarding.
#
# Usage: bash scripts/check_goethe_mirror_sync.sh
#
# Optional crontab (weekly Monday 9am — adjust path to your repo):
#   0 9 * * 1 bash /home/sy5/projects/local-system-engineer/scripts/check_goethe_mirror_sync.sh

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
MIRROR_ROOT="/mnt/c/Users/SY5/Claude/Projects/local-system-engineer"

# The full tool surface: goethe.py and every module it imports at class-definition
# time. Keep this list in step with goethe.py's own import block — a module added
# there and not here is unguarded.
FILES=(
    "tools/goethe.py"
    "tools/goethe_kb.py"
    "tools/goethe_netsec.py"
    "tools/goethe_node.py"
    "tools/goethe_planner.py"
    "tools/goethe_web.py"
    "tools/goethe_constants.py"
)

stale=0
missing=0
checked=0

for rel in "${FILES[@]}"; do
    LIVE="$REPO_ROOT/$rel"
    MIRROR="$MIRROR_ROOT/$rel"

    if [[ ! -f "$LIVE" ]]; then
        echo "ERROR: live file not found: $LIVE"
        exit 2
    fi

    if [[ ! -f "$MIRROR" ]]; then
        echo "MISSING: $rel absent from mirror"
        echo "         → cp '$LIVE' '$MIRROR'"
        missing=$(( missing + 1 ))
        continue
    fi

    checked=$(( checked + 1 ))
    LIVE_SHA=$(sha256sum "$LIVE" | awk '{print $1}')
    MIRROR_SHA=$(sha256sum "$MIRROR" | awk '{print $1}')

    if [[ "$LIVE_SHA" != "$MIRROR_SHA" ]]; then
        LIVE_DATE=$(date -d "@$(stat -c '%Y' "$LIVE")" '+%Y-%m-%d %H:%M')
        MIRROR_DATE=$(date -d "@$(stat -c '%Y' "$MIRROR")" '+%Y-%m-%d %H:%M')
        echo "STALE: $rel"
        echo "  live:   sha256=${LIVE_SHA:0:16}…  updated $LIVE_DATE"
        echo "  mirror: sha256=${MIRROR_SHA:0:16}…  updated $MIRROR_DATE"
        echo "  → cp '$LIVE' '$MIRROR'"
        stale=$(( stale + 1 ))
    fi
done

if (( missing > 0 )); then
    echo
    echo "FAIL: $missing of ${#FILES[@]} module(s) MISSING from the mirror."
    echo "      A post-D7 goethe.py without its mixins raises ModuleNotFoundError"
    echo "      at import. The mirror is not merely stale, it is unloadable."
    exit 1
fi

if (( stale > 0 )); then
    echo
    echo "FAIL: $stale of $checked module(s) differ from the live tree."
    exit 1
fi

echo "IN SYNC — all ${#FILES[@]} tool modules match the live tree."
exit 0
