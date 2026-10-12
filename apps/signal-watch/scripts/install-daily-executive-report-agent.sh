#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/unagidon/Documents/ai-os"
STATE_DIR="$HOME/.ai-os"
LOG_DIR="$STATE_DIR/logs"
PLIST="$HOME/Library/LaunchAgents/com.ai-os.signal-watch-daily-executive.plist"
LABEL="com.ai-os.signal-watch-daily-executive"
PYTHON_BIN="$(command -v python3)"

mkdir -p "$STATE_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$STATE_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd '$REPO_ROOT'; exec '$PYTHON_BIN' apps/signal-watch/scripts/report_daily_executive.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/signal-watch-daily-executive.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/signal-watch-daily-executive.err.log</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>23</integer>
    <key>Minute</key>
    <integer>55</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
  </dict>
</dict>
</plist>
PLIST
chmod 644 "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Signal Watch daily executive report installed."
echo "Label: $LABEL"
echo "Plist: $PLIST"
echo "Reports: $STATE_DIR/reports/daily-executive/YYYY-MM-DD.json and .md"
