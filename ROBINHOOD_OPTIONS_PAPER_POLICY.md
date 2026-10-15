# Robinhood Options Agent — Paper Policy v0 (2026-10-14)

Status: CLOUD PAPER ENGINE CONNECTED TO READ-ONLY ROBINHOOD MARKET DATA. Live order tools remain blocked.

## Scope
- Long calls only; buy to open; one standard 100-share contract per trade.
- Premium paid inclusive of opening fees <= $250, target $100–$250; reject orders above cap.
- One open position maximum; one new position daily; candidate watchlist scanning is not permission to buy multiple options. No leverage, margin borrowing, uncovered options, or live orders.
- Prefer liquid stocks/ETFs and tight bid-ask spreads. Primary experiment: 7–21 days to expiration (DTE); comparison: 30 DTE. Rank candidates by budget fit, spread, volume, open interest, DTE, and delta before opening one paper position. Verify actual contract specifications.
- Simulated exit experiment: compare loss thresholds of -20% and -30%, and profit thresholds of +30% and +50%, accounting for spreads/slippage. These are test hypotheses, not guaranteed fills or maximum loss.
- Record intraday quote freshness, volume/open interest, spread, implied volatility, and time decay; reject stale or thinly traded contracts.
- Block entry if market data stale, quotes missing, spread excessive, contract illiquid, or available paper buying power insufficient.
- Paper strategy lanes are measured separately: (1) Dean Ahrens-inspired unusual-flow proxy using option volume/open-interest, tight execution, balanced delta, controlled IV, and positive stock momentum; (2) 20-day breakout continuation; and (3) pullback continuation near the 20-day average inside an established 20/50-day uptrend.
- The unusual-flow lane is explicitly a proxy, not Dean Ahrens's undisclosed proprietary method and not a claim of institutional order-flow visibility.
- New strategy entries require spread <=10%, IV between 15% and 60%, and delta between 0.20 and 0.50 before the existing policy gates are applied.

## Position disposition
- This strategy trades option premium only and closes positions by selling the option contract.
- Exercise is outside strategy scope and remains disabled, including at expiry.
- Positions must be closed before broker exercise deadlines; a decayed option is never rescued through exercise.

## Verification acceptance
- One genuine timestamped option chain/quote, simulated order with fill/slippage, position tracking, risk-gate decisions, exit, net P&L, and durable log.
- Record strategy and reason for every rejection; no fabricated fills or performance claims.
- Live mode remains disabled until repeated paper results, verified risk controls, broker permissions, and explicit approval.

## Verified milestone 1
- Added `ai_os.robinhood_options` as a paper-only long-call engine.
- Added CLI command: `python3 -m ai_os robinhood-options-paper`.
- Durable ledger defaults to `~/.ai-os/robinhood-options/paper_trades.jsonl`.
- Tests cover premium cap, DTE window, spread/liquidity gates, exercise affordability, rejected opportunities, and durable trade records.
- Fixture data is clearly labeled; it is not a profitability claim or broker-sourced market data.

## Verified milestone 2
- Added a regular-options-hours market-session gate.
- Added a read-only Alpaca options-chain adapter for real market-data paper cycles when credentials are present.
- Added CLI support: `python3 -m ai_os robinhood-options-paper --provider alpaca --symbol SPY`.
- Outside valid options hours, the real-data cycle logs `options_market_closed` instead of forcing a stale or invalid trade.

## Next action
Add credentials through local environment only, run the Alpaca real-data cycle during options market hours, then schedule repeated paper scans before any live Robinhood integration. Keep this separate from Supervizor Telegram crypto signals.
