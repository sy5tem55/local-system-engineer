#!/usr/bin/env bash
# Canonical unattended TRAUM cycle. The outer systemd timeout bounds the
# complete cycle; each pass retains dream_runner.py's own per-pass budgets.
set -uo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${GOETHE_DREAM_PYTHON:-/usr/bin/python3}"
DREAM_DIR="${GOETHE_DREAM_DIR:-/opt/local-se/dreams}"
EPISODE_DIR="${GOETHE_EPISODE_DIR:-/opt/local-se/episodes}"
STATE_DB="${GOETHE_TRAUM_STATE_DB:-$DREAM_DIR/traum-state.db}"
RUN_ID="${GOETHE_TRAUM_RUN_ID:-run_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
CYCLE_MAX_SECONDS="${GOETHE_DREAM_CYCLE_MAX_SECONDS:-2700}"

if [[ ! "$CYCLE_MAX_SECONDS" =~ ^[0-9]+$ ]] || (( CYCLE_MAX_SECONDS < 60 )); then
  echo "[dream-cycle] invalid GOETHE_DREAM_CYCLE_MAX_SECONDS=$CYCLE_MAX_SECONDS"
  exit 2
fi

cycle_deadline=$(( $(date +%s) + CYCLE_MAX_SECONDS ))

finalize_signal() {
  signal_name="$1"
  echo "[dream-cycle] received $signal_name; finalizing canonical run as CANCELLED"
  "$PYTHON_BIN" "$REPO_DIR/tools/traum_state.py" cancel-run \
    --db "$STATE_DB" --run-id "$RUN_ID" --actor "cycle-$signal_name" || true
  exit 143
}

trap 'finalize_signal TERM' TERM
trap 'finalize_signal INT' INT

passes=(
  dedup
  stale-contradiction
  error-cluster
  patterns
  insights
)
pass_csv="$(IFS=,; echo "${passes[*]}")"
failures=0

# --- R1 preflight: make sure a dreamer is reachable before any pass runs ---
# Both real legs of call_dream_llm's cascade (dream_runner.py) live on
# node3090; a sleeping node has zero fallback inside the cascade itself.
# wake-node-for-dream.sh closes that gap: it is a no-op (fast exit 0) if
# node3090 is already up, otherwise it wakes it via the canonical
# RUTX50-etherwake path and polls /health (never ping — model load alone
# takes >2min after boot). If it still cannot reach node3090, we fall back
# to LUCIFER's own local llama-server by exporting GOETHE_DREAM_LLM_URL,
# which cascade leg 0 tries first and unconditionally when set — so it is
# exported ONLY on this fallback branch, never unconditionally, or it would
# silently demote node3090's larger model on every healthy night.
WAKE_SCRIPT="$REPO_DIR/tools/wake-node-for-dream.sh"
if [[ -x "$WAKE_SCRIPT" ]]; then
  echo "[dream-cycle] preflight: checking node3090 dreamer availability"
  remaining_seconds=$(( cycle_deadline - $(date +%s) ))
  if (( remaining_seconds <= 5 )); then
    echo "[dream-cycle] shared cycle deadline exhausted before wake preflight -- skipping"
  else
    wake_timeout="${GOETHE_DREAM_WAKE_TIMEOUT_S:-300}"
    if (( wake_timeout > remaining_seconds )); then
      wake_timeout=$remaining_seconds
    fi
    GOETHE_DREAM_WAKE_TIMEOUT_S="$wake_timeout" "$WAKE_SCRIPT"
    wake_rc=$?
    if (( wake_rc == 0 )); then
      echo "[dream-cycle] preflight: node3090 reachable -- cascade will use it as usual"
    else
      echo "[dream-cycle] preflight: node3090 could not be woken (rc=$wake_rc) -- checking LUCIFER local fallback"
      if curl -sf -o /dev/null -m 3 "http://127.0.0.1:8080/health"; then
        export GOETHE_DREAM_LLM_URL="http://127.0.0.1:8080"
        echo "[dream-cycle] preflight: LUCIFER local llama-server healthy -- forcing cascade leg 0 to $GOETHE_DREAM_LLM_URL for this cycle"
      else
        echo "[dream-cycle] preflight: no dreamer available (node3090 down, no local fallback) -- proceeding; passes will record the real blocked/failed state"
      fi
    fi
  fi
else
  echo "[dream-cycle] WARNING: $WAKE_SCRIPT missing or not executable -- skipping wake preflight, cascade runs unassisted"
fi

for pass_name in "${passes[@]}"; do
  remaining_seconds=$(( cycle_deadline - $(date +%s) ))
  if (( remaining_seconds <= 5 )); then
    echo "[dream-cycle] shared cycle deadline exhausted before pass: $pass_name"
    failures=$((failures + 1))
    break
  fi
  echo "[dream-cycle] starting pass: $pass_name"
  if timeout --signal=TERM --kill-after=10s "${remaining_seconds}s" \
    "$PYTHON_BIN" "$REPO_DIR/tools/dream_runner.py" \
      --pass "$pass_name" \
      --dream-dir "$DREAM_DIR" \
      --episode-dir "$EPISODE_DIR" \
      --state-db "$STATE_DB" \
      --run-id "$RUN_ID" \
      --run-profile standard \
      --run-source scheduled \
      --requested-passes "$pass_csv" \
      --budget-max-wall-clock-s "$remaining_seconds" \
      --no-dry-run; then
    echo "[dream-cycle] completed pass: $pass_name"
  else
    rc=$?
    failures=$((failures + 1))
    echo "[dream-cycle] pass ended non-successfully: $pass_name (rc=$rc); continuing"
  fi
done

echo "[dream-cycle] refreshing operator digest"
remaining_seconds=$(( cycle_deadline - $(date +%s) ))
if (( remaining_seconds <= 5 )); then
  digest_rc=124
  failures=$((failures + 1))
  echo "[dream-cycle] shared cycle deadline exhausted before digest refresh"
elif timeout --signal=TERM --kill-after=10s "${remaining_seconds}s" \
  "$PYTHON_BIN" "$REPO_DIR/tools/dream_digest.py" \
    --dream-dir "$DREAM_DIR" \
    --episode-dir "$EPISODE_DIR" \
    --no-dry-run; then
  digest_rc=0
else
  digest_rc=$?
  failures=$((failures + 1))
  echo "[dream-cycle] digest refresh failed (rc=$digest_rc)"
fi

if ! "$PYTHON_BIN" "$REPO_DIR/tools/traum_state.py" finalize-cycle \
    --db "$STATE_DB" \
    --run-id "$RUN_ID" \
    --digest-exit "$digest_rc"; then
  failures=$((failures + 1))
  echo "[dream-cycle] canonical finalizer failed"
fi

if ! "$PYTHON_BIN" "$REPO_DIR/tools/traum_state.py" expire-stale \
    --db "$STATE_DB" --stale-days 14; then
  failures=$((failures + 1))
  echo "[dream-cycle] stale-proposal maintenance failed"
fi

# Return node3090 to standby if -- and only if -- this cycle's preflight woke
# it. Runs before the failure check on purpose: a node we woke should go back
# down whether or not the passes succeeded. The helper always exits 0, so it
# can never turn a good cycle into a failed one.
SLEEP_SCRIPT="$REPO_DIR/tools/sleep-node-after-dream.sh"
if [[ -x "$SLEEP_SCRIPT" ]]; then
  "$SLEEP_SCRIPT" || true
else
  echo "[dream-cycle] WARNING: $SLEEP_SCRIPT missing or not executable -- node3090 left as-is"
fi

if (( failures > 0 )); then
  echo "[dream-cycle] completed with $failures non-successful operation(s)"
  exit 1
fi

echo "[dream-cycle] completed successfully: run_id=$RUN_ID"
