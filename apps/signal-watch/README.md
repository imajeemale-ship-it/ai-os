# Signal Watch

A local-first Telegram signal watcher for AI-OS. It reuses Supervizor's existing Telethon session and parser, persists deduplicated signal messages in SQLite, and sends actionable alerts to a Telegram bot destination when configured.

## Safety

Signal Watch only reads Telegram and sends alert messages. It never connects to a broker or exchange and never places, modifies, or cancels an order. Parsed signal alerts are untrusted information; spot-only paper review remains separate. Unknown fields, missing stop loss, short, leverage, derivatives, DCA, or stale messages are visibly flagged.

The paper lane applies a stricter admission gate than alerting: it opens only fresh,
ranked spot-long calls with a numeric entry, a stop below entry, and ascending
targets. Signals that are stale, leveraged, derivative, DCA-based, short, malformed,
or missing a stop/target are logged and alerted for review but never become paper
positions.

Each incoming signal also receives a persisted 0–100 conviction score with LOW,
MEDIUM, or HIGH confidence. The score explains channel history, completeness,
risk/reward, recent cross-channel agreement, and freshness. The paper lane accepts
only MEDIUM or HIGH conviction signals in addition to its existing safety gate.

Consensus groups same-ticker mentions across channels within a configurable window
(6 hours by default). Alerts show the consensus score, channel count, agreeing and
disagreeing channel counts, and the group's first/latest timestamps. Override the
window with `--consensus-window-minutes`.

Live Signal Watch evaluations include a cached market context: BTC trend, BTC
position versus its 200 EMA, 24-hour BTC change, volatility, Fear & Greed, trading
session, and weekday. Market context contributes 15 conviction points and is saved
with paper positions. If required context is unavailable, its score is zero and
the paper lane refuses the trade.

The Decision Engine combines conviction, consensus, market context, and historical
channel performance into a persisted `APPROVE`, `WATCH`, or `REJECT` result with an
overall score, paper-only position-size recommendation, maximum risk percentage,
and explainable supporting or blocking reasons. Missing market context or failed
paper-safety checks produce `REJECT`. These values are advisory only; no broker or
exchange execution is performed.

When a paper position closes, the paper trader appends an immutable learning
observation containing its prediction error, calibration score, decision accuracy,
market-context key, and consensus effectiveness. Export the learning report with:

```sh
python3 apps/signal-watch/scripts/report_learning.py
```

This writes JSON and Markdown to `~/.ai-os/reports/` and never changes historical
signals, positions, or events.

The daily executive report is generated automatically by its LaunchAgent and stored
historically as `~/.ai-os/reports/daily-executive/YYYY-MM-DD.json` and `.md`. Install
the job with `apps/signal-watch/scripts/install-daily-executive-report-agent.sh`.

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
