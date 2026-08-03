#!/usr/bin/env bash
# start-engine-on-node.sh — start (or confirm) a llama-server engine for one
# role on one node, on demand.
#
# SPEC: docs/SPEC-on-demand-engine-start-2026-08.md §4.1.
#
#   start-engine-on-node.sh --node <name> --role <role> [--timeout-s N]
#
# CONTRACT (exit codes are the interface — callers must not parse prose):
#   0  RESULT=already-running   — live process already matches the profile.
#   0  RESULT=started           — this call launched the engine and it
#                                  became healthy within --timeout-s.
#   2  RESULT=missing-profile   — no profiles/<node>/<ROLE>-*.gguf.md found.
#                                  Hard stop. Never falls back to another
#                                  node's profile.
#   3  RESULT=conflict          — a DIFFERENT profile is already serving
#                                  :8080. Nothing is launched or killed.
#   4  RESULT=missing-model     — the model file the profile names is not
#                                  present on the node. Nothing is launched.
#   5  RESULT=started-but-unhealthy — launched, but /health never answered
#                                  within --timeout-s. Last 40 log lines
#                                  from the node are printed.
#
# Every outcome prints a "RESULT=<state>" line on stdout — callers
# (wake-node-for-dream.sh) grep for it rather than relying on exit code
# alone, because exit 0 covers two materially different outcomes for
# marker-writing purposes (already-running vs. this-cycle-started-it).
#
# HAZARD A (spec §3) — profiles are resolved strictly under
# profiles/<node>/, never any other node's directory, and never
# synthesised. A missing profile is a hard stop.
#
# HAZARD B (spec §3) — idempotent start. node_facts.match_live's existing
# identity-flag classification (Hazard A in that module) decides
# already-running vs conflict; this script does not reimplement flag
# comparison.
#
# HAZARD C (spec §3) — no secret literal. This script reads no credential
# of any kind; it only SSHes with the operator's existing key-based auth,
# exactly like wake-node-for-dream.sh / sleep-node-after-dream.sh.
#
# HAZARD D (spec §3) — a node that is up, reachable, but whose engine failed
# to load is reported as its own state (5), with the remote log tail
# attached, never conflated with "did not wake" or with success.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

NODE=""
ROLE=""
TIMEOUT_S=300

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node) NODE="$2"; shift 2 ;;
    --role) ROLE="$2"; shift 2 ;;
    --timeout-s) TIMEOUT_S="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

if [[ -z "$NODE" || -z "$ROLE" ]]; then
  echo "usage: start-engine-on-node.sh --node <name> --role <role> [--timeout-s N]" >&2
  exit 64
fi

log() { echo "[start-engine-on-node] $(date -u +%H:%M:%SZ) $*"; }

# ── SSH target resolution — per-node override via env, else <node>.home.arpa ──
NODE_UPPER=$(echo "$NODE" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_')
hostvar="GOETHE_${NODE_UPPER}_SSH_HOST"
uservar="GOETHE_${NODE_UPPER}_SSH_USER"
NODE_HOST="${!hostvar:-${NODE}.home.arpa}"
NODE_USER="${!uservar:-lse-admin}"
NODE_SSH="${NODE_USER}@${NODE_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes)
HEALTH_URL="http://${NODE_HOST}:8080/health"

# ── Step 1: resolve profiles/<node>/<ROLE>-*.gguf.md — hard stop if absent ──
ROLE_UPPER=$(echo "$ROLE" | tr '[:lower:]' '[:upper:]')
PROFILE_GLOB="${REPO_ROOT}/profiles/${NODE}/${ROLE_UPPER}-"*".gguf.md"
profile=""
for f in $PROFILE_GLOB; do
  [[ -f "$f" ]] && profile="$f" && break
done

if [[ -z "$profile" ]]; then
  echo "RESULT=missing-profile"
  echo "no profile found matching profiles/${NODE}/${ROLE_UPPER}-*.gguf.md"
  echo "(profiles are never resolved from another node's directory; this is a hard stop, not a fallback)"
  exit 2
fi
log "resolved profile: $profile"

# ── Step 2: probe :8080 on the node via SSH pgrep (ground truth, not /health — ──
# a mid-load process won't answer /health yet but must still be seen).
# Bracket one char of the pattern so pgrep -f does not match its own
# "pgrep -fa 'llama[-]server'" cmdline over the ssh channel (documented
# footgun in this repo, ssh_run PKILL RULE).
LIVE_LINE=$(ssh "${SSH_OPTS[@]}" "$NODE_SSH" "pgrep -fa 'llama[-]server' | head -1" 2>/dev/null)
LIVE_PID=""
LIVE_CMD=""
if [[ -n "$LIVE_LINE" ]]; then
  LIVE_PID=$(awk '{print $1}' <<<"$LIVE_LINE")
  LIVE_CMD=$(cut -d' ' -f2- <<<"$LIVE_LINE")
fi

MATCH_OUT=$(SCRIPT_DIR="$SCRIPT_DIR" PROFILE_PATH="$profile" LIVE_CMD_LINE="$LIVE_CMD" LIVE_PID_VAL="$LIVE_PID" python3 - <<'PY'
import os, sys, shlex
sys.path.insert(0, os.environ["SCRIPT_DIR"])
import node_facts as nf

profile_path = os.environ["PROFILE_PATH"]
live_cmd = os.environ.get("LIVE_CMD_LINE", "")
live_pid_raw = os.environ.get("LIVE_PID_VAL", "")
live_pid = int(live_pid_raw) if live_pid_raw.isdigit() else None

prof = nf.parse_profile(profile_path)
model_path = prof["flags"].get("-m") or prof["flags"].get("--model") or ""
log_file = prof["flags"].get("--log-file") or ""

live_flags = None
if live_cmd:
    tokens = shlex.split(live_cmd)
    live_flags = nf._parse_flags_from_tokens(tokens[1:])  # skip binary path

match = nf.match_live({profile_path: prof}, live_pid, live_flags)
print(f"MODEL_PATH={model_path}")
print(f"LOG_FILE={log_file}")
print(f"VERDICT={match['verdict']}")
PY
)
eval "$MATCH_OUT"

if [[ "$VERDICT" == "exact" ]]; then
  echo "RESULT=already-running"
  echo "profile $profile already matches the live process (pid $LIVE_PID) on ${NODE}:8080 -- nothing to do"
  exit 0
fi

if [[ "$VERDICT" == "closest" ]]; then
  echo "RESULT=conflict"
  echo "a DIFFERENT engine is already serving ${NODE}:8080 (pid $LIVE_PID) -- not killing it"
  echo "requested profile: $profile"
  echo "live cmdline:      $LIVE_CMD"
  echo "something else -- plausibly the operator -- owns this process. Report and stop."
  exit 3
fi

log "nothing serving ${NODE}:8080 -- proceeding to launch"

# ── Step 3: verify the model file exists on the node before launching ──
if [[ -z "$MODEL_PATH" ]]; then
  echo "RESULT=missing-model"
  echo "profile $profile has no -m/--model flag -- cannot verify or launch"
  exit 4
fi
if ! ssh "${SSH_OPTS[@]}" "$NODE_SSH" "test -f '$MODEL_PATH'" 2>/dev/null; then
  echo "RESULT=missing-model"
  echo "model file $MODEL_PATH not found on $NODE"
  exit 4
fi
log "model file confirmed present on $NODE: $MODEL_PATH"

# ── Step 4: launch detached ──
# The profile file's first block (up to the first line that is exactly
# "---") IS the literal runnable command, verbatim, backslash-continued.
CMD_TEXT=$(awk '/^---$/{exit} {print}' "$profile")

LAUNCH_LOCAL=$(mktemp)
trap 'rm -f "$LAUNCH_LOCAL"' EXIT
cat > "$LAUNCH_LOCAL" <<EOF
#!/usr/bin/env bash
set -uo pipefail
nohup $CMD_TEXT </dev/null >/tmp/start-engine-launch-${NODE}.out 2>&1 &
disown
EOF

ssh "${SSH_OPTS[@]}" "$NODE_SSH" "cat > /tmp/start-engine-launcher-${NODE}.sh && chmod +x /tmp/start-engine-launcher-${NODE}.sh" < "$LAUNCH_LOCAL"
ssh "${SSH_OPTS[@]}" "$NODE_SSH" "nohup /tmp/start-engine-launcher-${NODE}.sh </dev/null >/tmp/start-engine-launcher-${NODE}.out 2>&1 & disown; sleep 1; true"
log "launch dispatched on $NODE (role=$ROLE); polling ${HEALTH_URL}"

# ── Step 5/6: poll /health up to --timeout-s ──
elapsed=0
poll_interval="${GOETHE_START_ENGINE_POLL_INTERVAL_S:-5}"
while (( elapsed < TIMEOUT_S )); do
  if curl -sf -o /dev/null -m 3 "$HEALTH_URL"; then
    echo "RESULT=started"
    echo "engine healthy on ${NODE}:8080 after ${elapsed}s (profile: $profile)"
    exit 0
  fi
  sleep "$poll_interval"
  elapsed=$(( elapsed + poll_interval ))
  log "waiting for /health ... ${elapsed}s/${TIMEOUT_S}s"
done

TAIL=""
if [[ -n "$LOG_FILE" ]]; then
  TAIL=$(ssh "${SSH_OPTS[@]}" "$NODE_SSH" "tail -n 40 '$LOG_FILE' 2>/dev/null")
fi
echo "RESULT=started-but-unhealthy"
echo "engine did not answer /health within ${TIMEOUT_S}s on $NODE (profile: $profile)"
echo "----- last 40 lines of ${LOG_FILE:-<no --log-file in profile>} on $NODE -----"
echo "$TAIL"
exit 5
