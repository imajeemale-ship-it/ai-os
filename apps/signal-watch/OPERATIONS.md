# Signal Watch operations

## Start a monitor

This runs continuously on Davids-Air-2. Keep the Mac awake and connected to the internet, or later move the monitor to an always-on host with a secure copy of the authorized Telegram session.

```sh
cd /Users/unagidon/Documents/ai-os
python3 apps/signal-watch/watch.py \
  --chat "Predictūm X — The Most Powerful Indicator" \
  --chat "Whales Crypto Guide" \
  --chat "Technical CRYPTO Analyst" \
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
