#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/unagidon/Documents/ai-os"
STATE_DIR="$HOME/.ai-os"
LOG_DIR="$STATE_DIR/logs"
PLIST="$HOME/Library/LaunchAgents/com.ai-os.signal-watch-paper-trader.plist"
LABEL="com.ai-os.signal-watch-paper-trader"
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
    <string>set -a; [[ -f '$STATE_DIR/signal_watch.env' ]] &amp;&amp; source '$STATE_DIR/signal_watch.env'; set +a; cd '$REPO_ROOT'; exec '$PYTHON_BIN' apps/signal-watch/scripts/paper_trade_signals.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/signal-watch-paper.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/signal-watch-paper.err.log</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
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
launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
sleep 2

echo "Signal Watch paper trader installed."
echo "Label: $LABEL"
echo "Plist: $PLIST"
echo "Logs: $LOG_DIR/signal-watch-paper.out.log and $LOG_DIR/signal-watch-paper.err.log"
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,80p'
