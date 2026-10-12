# Signal Watch operations

## Start a monitor

This runs continuously on Davids-Air-2. Keep the Mac awake and connected to the internet, or later move the monitor to an always-on host with a secure copy of the authorized Telegram session.

```sh
cd /Users/unagidon/Documents/ai-os
python3 apps/signal-watch/watch.py \
  --chat "Predictūm X — The Most Powerful Indicator" \
  --chat "Wallstreet Queen Official®" \
  --chat "Crypto Best Futures Signals" \
  --chat "Technical CRYPTO Analyst" \
  --chat "Whales Crypto Guide" \
  --chat "The Bull" \
  --chat "Crypto Goddess CHAT" \
  --chat "Crypto Signal"
```

The default mode records signals and sends alerts only when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in the launch environment. No credential is stored in this repo. Without alert config, the monitor remains listening and logs pending alerts locally.

## Check a bounded sample

```sh
python3 apps/signal-watch/watch.py \
  --chat "Predictūm X — The Most Powerful Indicator" \
  --chat "Whales Crypto Guide" \
  --backfill 50 --once --dry-run
```

Backfill warms the dedupe database and is never delivered as an alert. Do not use a large backfill to decide whether a setup is current; only live arrivals should be treated as potentially timely.

Database: `~/.ai-os/signal_watch.db`.

## Configure alert delivery

Create a Telegram bot through BotFather, send it a direct message from the account that should receive alerts, then set these variables in the shell or a private launch configuration:

```sh
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

Keep the bot token private. Restart Signal Watch after configuring it. Verify with a test alert only after checking that the bot chat ID belongs to you.


## Run as a macOS background service

Install or refresh the LaunchAgent from the AI-OS repo:

```sh
cd /Users/unagidon/Documents/ai-os
apps/signal-watch/scripts/install-launch-agent.sh
```

The installer prompts for the Telegram bot token and chat ID, stores them in `~/.ai-os/signal_watch.env` with owner-only permissions, creates `~/Library/LaunchAgents/com.ai-os.signal-watch.plist`, starts the service immediately, and restarts it automatically if it exits.

Check status and recent logs:

```sh
cd /Users/unagidon/Documents/ai-os
apps/signal-watch/scripts/status-launch-agent.sh
```

Stop and remove the LaunchAgent:

```sh
cd /Users/unagidon/Documents/ai-os
apps/signal-watch/scripts/uninstall-launch-agent.sh
```

Logs are written to `~/.ai-os/logs/signal-watch.out.log` and `~/.ai-os/logs/signal-watch.err.log`.

## Trade execution workflow (manual)

1. Treat a Telegram call as an unverified lead. Check the source post time and whether the entry is still valid.
2. Reject signals with missing entry, ticker ambiguity, no stop/invalidation, leverage, shorts, derivatives, DCA/averaging down, or a stale timestamp under the current Supervizor v0 policy.
3. Confirm the exact asset is tradable in your state and the exact venue/pair. Coin tickers are not globally unique.
4. Check current bid/ask, spread, order-book depth, and whether the move already ran. Skip a setup if the price has left the source entry zone or liquidity is thin.
5. Decide a maximum dollar loss before sizing. Spot size = allowed dollar loss ÷ (entry price − stop price) for a long. Fees, slippage, and gaps make actual loss potentially larger.
6. For fast but price-conscious manual entries, use a limit order at or inside the planned entry zone; if it does not fill while the setup remains valid, reassess rather than chasing. A market order prioritizes getting filled but can execute at an unexpectedly worse price.
7. Before submitting, check quantity, order type, limit/stop values, and available cash on the final review screen. Place manually; then record fill, fees, and the reason for taking or skipping the trade.
8. Use an exit plan only if the broker supports the required order type for that asset and jurisdiction. A stop-limit can fail to fill; a stop-market can fill far from the stop price.

Robinhood Crypto supports market, limit, stop, and stop-limit orders, but availability can differ by asset. Its crypto market orders are price-collared (currently up to 1% above for buys and 5% below for sells) and can remain pending or be canceled when the market moves outside the collar. Limit orders control the worst acceptable price but do not guarantee a fill. Review current broker terms and the asset's availability at order time.

No software can guarantee that you will receive, read, or execute a signal in time. Telegram delivery, Wi-Fi, the computer, the broker, and market liquidity can all add delay. Never let the bot submit trades on your behalf.

## Delivery test

Once the private bot token and your direct-message chat ID are configured in the launch environment, run `python3 apps/signal-watch/watch.py --test-alert`. It sends one clearly labeled test message. It does not connect to sources or a broker.

## Paper trading lane

Signal Watch can run a local paper-trading lane that never places broker or exchange orders. It reads logged signals from `~/.ai-os/signal_watch.db`, opens simulated long positions only from ranked sources with parsed entries and targets, checks Coinbase public prices, takes 25% simulated exits at TP1, TP2, and TP3, closes the remaining runner at TP4, and records stops or realized paper P/L.

Paper admission is fail-closed. A signal must be fresh under its source timeout,
spot-long, non-leveraged, non-DCA, have a numeric entry, a stop below entry, and
ascending targets. This keeps incomplete or risky Telegram calls out of the
performance sample while preserving them in Signal Watch for human review.

Signal Watch persists a conviction score for every newly logged signal. It is a
0–100 explainable score with LOW/MEDIUM/HIGH confidence and factor reasons plus
warnings. Historical channel performance contributes up to 60 points; completeness
15; risk/reward 10; recent duplicate agreement 10; and freshness 5. The paper
trader requires at least 50 points, so low-conviction calls remain visible but are
not added to the paper performance sample.

Consensus is persisted in `consensus_groups` and on each signal row. Signals with
the same ticker are grouped when their timestamps are within the configured window;
the default is 360 minutes. A consensus score of 50 means one channel with no
cross-channel confirmation, while multiple channels are scored by the share of
agreeing versus disagreeing channel directions. Use
`--consensus-window-minutes N` when starting Signal Watch to change the window.

Market context is cached at `~/.ai-os/market_context.json` for five minutes. It
uses public BTC candles, the Alternative.me Fear & Greed endpoint, UTC trading
session, and UTC weekday. The context contributes 15 of 100 conviction points;
historical channel performance contributes 45, completeness 15, risk/reward 10,
consensus 10, and freshness 5. Missing or stale context is recorded as unavailable
and fails closed: the signal remains visible for review but cannot become a paper
position.

The Decision Engine persists one final paper-only evaluation on every signal. It
combines conviction, consensus, market context, and channel performance and
returns `APPROVE`, `WATCH`, or `REJECT`, with an overall score, size recommendation,
maximum risk percentage, explanation, and explicit supporting/blocking reasons.
Unavailable market context and failed paper-admission checks block the decision.
The risk and size fields are recommendations for paper review only and never place
orders.

Install or refresh the scheduled paper trader:

```sh
cd /Users/unagidon/Documents/ai-os
apps/signal-watch/scripts/install-paper-trader-agent.sh
```

Check the scheduled paper trader:

```sh
cd /Users/unagidon/Documents/ai-os
apps/signal-watch/scripts/status-paper-trader-agent.sh
```

The job wakes every 5 minutes through `com.ai-os.signal-watch-paper-trader`, runs once, writes logs to `~/.ai-os/logs/signal-watch-paper.out.log`, then exits. A `last exit code = 0` means the latest run completed cleanly.

Export the channel performance report from the same database:

```sh
cd /Users/unagidon/Documents/ai-os
python3 apps/signal-watch/scripts/report_paper_trading.py
```

This writes `~/.ai-os/reports/paper-trading-channel-performance.json` and
`~/.ai-os/reports/paper-trading-channel-performance.md`. Rows are ranked by
realized net paper P/L by default; use `--sort-by` with a report metric and
`--ascending` for a different sortable view. The report is read-only and does
not wake the paper trader or contact Telegram, Coinbase, or a broker.
