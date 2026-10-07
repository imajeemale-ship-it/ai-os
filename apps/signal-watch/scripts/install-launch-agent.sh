#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/unagidon/Documents/ai-os"
APP_DIR="$REPO_ROOT/apps/signal-watch"
STATE_DIR="$HOME/.ai-os"
LOG_DIR="$STATE_DIR/logs"
ENV_FILE="$STATE_DIR/signal_watch.env"
PLIST="$HOME/Library/LaunchAgents/com.ai-os.signal-watch.plist"
LABEL="com.ai-os.signal-watch"
PYTHON_BIN="$(command -v python3)"

mkdir -p "$STATE_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"
chmod 700 "$STATE_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

read -r -p "Telegram bot token: " TELEGRAM_BOT_TOKEN
read -r -p "Telegram chat id: " TELEGRAM_CHAT_ID

if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
  echo "Token and chat id are required." >&2
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<ENV
TELEGRAM_BOT_TOKEN='$TELEGRAM_BOT_TOKEN'
TELEGRAM_CHAT_ID='$TELEGRAM_CHAT_ID'
SIGNAL_WATCH_SUPERVIZOR_ROOT='/Users/unagidon/Desktop/ai-agent-test/ft_userdata'
ENV
chmod 600 "$ENV_FILE"

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
    <string>set -a; source '$ENV_FILE'; set +a; cd '$REPO_ROOT'; exec '$PYTHON_BIN' apps/signal-watch/watch.py --chat 'Predictūm X — The Most Powerful Indicator' --chat 'Wallstreet Queen Official®' --chat 'Crypto Best Futures Signals' --chat 'Technical CRYPTO Analyst' --chat 'Whales Crypto Guide' --chat 'The Bull' --chat 'Crypto Goddess CHAT' --chat 'Crypto Signal'</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$REPO_ROOT</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/signal-watch.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/signal-watch.err.log</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
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
sleep 3

echo "Signal Watch launch agent installed."
echo "Label: $LABEL"
echo "Plist: $PLIST"
echo "Env: $ENV_FILE"
echo "Logs: $LOG_DIR/signal-watch.out.log and $LOG_DIR/signal-watch.err.log"
launchctl print "gui/$(id -u)/$LABEL" | sed -n '1,80p'
