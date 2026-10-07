#!/usr/bin/env bash
set -euo pipefail

LABEL="com.ai-os.signal-watch-paper-trader"
LOG_DIR="$HOME/.ai-os/logs"

echo "== launchctl =="
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,100p' || true

echo

echo "== stdout =="
tail -80 "$LOG_DIR/signal-watch-paper.out.log" 2>/dev/null || true

echo

echo "== stderr =="
tail -80 "$LOG_DIR/signal-watch-paper.err.log" 2>/dev/null || true
