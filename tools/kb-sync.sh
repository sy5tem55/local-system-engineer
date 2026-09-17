#!/usr/bin/env bash
# kb-sync.sh — sync the NAS KB file layer into the repo's versioned snapshot.
#
# Convention (kb/nas-kb-architecture.md):
#   NAS \\n45.home.arpa\Models\goethe\KB = live source of truth (file layer)
#   repo kb/                             = versioned snapshot
#   add/update only — NO --delete during soak (deletions only after soak ends)
#
# Usage: tools/kb-sync.sh   (run on node4090, after big KB sessions)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAS_KB="/opt/local-se/nas/Models/goethe/KB"
REPO_KB="$REPO_DIR/kb"

[ -d "$NAS_KB" ] || { echo "ERROR: NAS KB not mounted: $NAS_KB" >&2; exit 1; }

# add/update only — NEVER --delete during soak
rsync -a "$NAS_KB/" "$REPO_KB/"

cd "$REPO_DIR"
if git status --porcelain kb/ | grep -q .; then
  git add kb/
  git commit -m "kb: sync from NAS ($(date -u +%Y-%m-%dT%H:%MZ), $(find "$NAS_KB" -type f | wc -l) files)"
else
  echo "kb/ unchanged — nothing to commit"
fi
