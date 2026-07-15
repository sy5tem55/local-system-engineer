#!/usr/bin/env bash
# Canonical unattended TRAUM cycle. The outer systemd timeout bounds the
# complete cycle; each pass retains dream_runner.py's own per-pass budgets.
set -euo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${GOETHE_DREAM_PYTHON:-/usr/bin/python3}"

passes=(
  dedup
  stale-contradiction
  error-cluster
  patterns
  insights
)

for pass_name in "${passes[@]}"; do
  echo "[dream-cycle] starting pass: $pass_name"
  "$PYTHON_BIN" "$REPO_DIR/tools/dream_runner.py" \
    --pass "$pass_name" \
    --no-dry-run
done

echo "[dream-cycle] refreshing operator digest"
"$PYTHON_BIN" "$REPO_DIR/tools/dream_digest.py" --no-dry-run
