#!/usr/bin/env bash
# start-unsloth-studio.sh — node4090 (LUCIFER) launch guard.
# Checks whether Unsloth Studio is running. If it is, does nothing.
# If it isn't, starts it. Nothing more.
set -u

if pgrep -f 'unsloth studio' >/dev/null 2>&1; then
  echo "Unsloth Studio already running:"
  pgrep -af 'unsloth studio' | head -1
  exit 0
fi

echo "Unsloth Studio not running — starting (port 8888)..."
nohup ~/.local/bin/unsloth studio -p 8888 > /tmp/unsloth-studio-node4090.log 2>&1 &
echo "Launched (pid $!). Log: /tmp/unsloth-studio-node4090.log"
