#!/usr/bin/env bash
# =============================================================================
# lse-monitor.sh — Persistent Local System Engineer command stream monitor
# =============================================================================
#
# Creates a named tmux session with:
#   - Top pane  (70%): live tail of the agent command log
#   - Bottom pane (30%): interactive sudo console for delegation commands
#
# Behaviour:
#   - First run  → creates the session and attaches
#   - Any subsequent run → re-attaches to the existing session
#   - Closing the terminal window → session keeps running in background
#   - WSL shutdown → session ends (log file persists on disk)
#
# Usage:
#   bash /home/sy5/lse-monitor.sh
#   (or via the dedicated Windows Terminal profile — see README)
#
# To detach (leave session running): Ctrl+B then D
# To kill the session cleanly:       tmux kill-session -t lse
# =============================================================================

set -euo pipefail

SESSION="lse"
LOG_DIR="/home/sy5/.lse"
LOG_FILE="$LOG_DIR/agent_commands.log"
BANNER="━━━  LSE Agent Command Stream  ━━━  Ctrl+B D to detach  ━━━"
SUDO_BANNER="━━━  Sudo console — run delegation commands here  ━━━"

# ── Ensure log infrastructure exists ─────────────────────────────────────────
mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

# ── If session already exists, just attach ───────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Attaching to existing LSE session..."
    sleep 0.5
    exec tmux attach-session -t "$SESSION"
fi

# ── Create a new detached session ────────────────────────────────────────────
tmux new-session -d -s "$SESSION" -n "monitor"

# ── Configure tmux appearance for this session ───────────────────────────────
tmux set-option -t "$SESSION" status-style "bg=colour235,fg=colour250"
tmux set-option -t "$SESSION" status-left  "#[fg=colour39,bold] LSE #[fg=colour250]| "
tmux set-option -t "$SESSION" status-right "#[fg=colour244]%H:%M  %Y-%m-%d "
tmux set-option -t "$SESSION" pane-border-style "fg=colour238"
tmux set-option -t "$SESSION" pane-active-border-style "fg=colour39"

# ── Top pane: agent command stream ───────────────────────────────────────────
tmux send-keys -t "$SESSION:0.0" \
    "echo '$BANNER' && echo '' && tail -f '$LOG_FILE'" Enter

# ── Split: bottom pane is the sudo console (30% of height) ──────────────────
tmux split-window -t "$SESSION:0" -v -p 30

# ── Bottom pane: interactive sudo console ────────────────────────────────────
tmux send-keys -t "$SESSION:0.1" \
    "echo '$SUDO_BANNER' && echo '' && cd ~" Enter

# ── Focus bottom pane so the user lands there ready to type ─────────────────
tmux select-pane -t "$SESSION:0.1"

# ── Attach ───────────────────────────────────────────────────────────────────
exec tmux attach-session -t "$SESSION"
