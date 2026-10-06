# Signal Watch

A local-first Telegram signal watcher for AI-OS. It reuses Supervizor's existing Telethon session and parser, persists deduplicated signal messages in SQLite, and sends actionable alerts to a Telegram bot destination when configured.

## Safety

Signal Watch only reads Telegram and sends alert messages. It never connects to a broker or exchange and never places, modifies, or cancels an order. Parsed signal alerts are untrusted information; spot-only paper review remains separate. Unknown fields, missing stop loss, short, leverage, derivatives, DCA, or stale messages are visibly flagged.

## Requirements

- Python 3.11+
- Telethon installed in the environment used to run the watcher
- Existing Supervizor `.env.telegram` and authorized `supervizor_sessions` folder
- Optional alert delivery variables `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

## Run

From the AI-OS repo:

```sh
python3 apps/signal-watch/watch.py --list-dialogs
python3 apps/signal-watch/watch.py --chat "Predictūm X — The Most Powerful Indicator" --dry-run --backfill 10
python3 apps/signal-watch/watch.py --chat "Predictūm X — The Most Powerful Indicator" --backfill 10
```

Configure paths with `SIGNAL_WATCH_SUPERVIZOR_ROOT` or CLI `--supervizor-root`. The watcher starts by collecting a bounded backfill, then listens continuously for new messages. It persists message ids before delivery, so duplicates from reconnects are merged and alerts are retried safely without duplicate database rows. A Telegram send failure remains visible in the `alerts` table for retry.

Use environment variables in the launch process, never commit credentials. Start with `--dry-run` to verify sources and parsing. Then run without `--dry-run` to log records and send alerts if bot delivery variables are set. Without those variables, signals are recorded locally and the summary reports that alerts are not configured.

## Alert contents

Each alert includes source, ticker/pair, side, entry range, targets, stop loss, message age, quality warnings, and a link to the source message when Telegram exposes one. Alerts are informational and require independent review before any trading decision.
