# Signal Watch paper trading milestone

Status: executed
Date: 2026-10-06

## What is done

- Signal Watch runs as a macOS LaunchAgent on Davids-Air-2.
- It monitors the selected Telegram signal channels.
- Alerts include source ranking, risk flags, and trade-management guidance.
- A reusable channel backtester scores calls with TP ladder behavior.
- A local paper-trading lane exists inside AI-OS.
- The paper trader wakes every 5 minutes through `com.ai-os.signal-watch-paper-trader`.
- It simulates entries from ranked sources with parsed entries and targets.
- It tracks TP1, TP2, TP3, TP4, stop loss, remaining position, and paper P/L.
- It does not connect to a broker and does not place real orders.

## Current channel read

- Wallstreet Queen Official® is the strongest current paper candidate.
- Crypto Best Futures Signals / HedgeX is active but more futures-risk and less clean.
- Technical CRYPTO Analyst remains useful but needs more target-bearing signals.
- Whales Crypto Guide is noisy and should be filtered hard.
- The Bull is currently watch-only until newer data improves.

## Gate before real money

By Saturday, review paper results by channel:

- Usable signal count
- TP1 hit rate
- TP4 hit rate
- Average ladder return
- Stop-loss frequency
- Give-back behavior
- Unsupported or unverified tickers

Only move toward tiny live Coinbase Advanced API execution if the paper data shows repeatable edge.

## Next possible build step

Add a report command that summarizes the paper-trading database by channel and exports the Saturday verdict table.
