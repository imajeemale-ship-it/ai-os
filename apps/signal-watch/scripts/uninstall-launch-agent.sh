#!/usr/bin/env bash
set -euo pipefail
LABEL="com.ai-os.signal-watch"
PLIST="$HOME/Library/LaunchAgents/com.ai-os.signal-watch.plist"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "Signal Watch launch agent removed. Credentials remain at $HOME/.ai-os/signal_watch.env"
