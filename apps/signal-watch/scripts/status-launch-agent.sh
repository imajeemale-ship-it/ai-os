#!/usr/bin/env bash
set -euo pipefail
LABEL="com.ai-os.signal-watch"
LOG_DIR="$HOME/.ai-os/logs"
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,120p'
echo
echo "--- stdout tail ---"
tail -n 40 "$LOG_DIR/signal-watch.out.log" 2>/dev/null || true
echo
echo "--- stderr tail ---"
tail -n 40 "$LOG_DIR/signal-watch.err.log" 2>/dev/null || true
