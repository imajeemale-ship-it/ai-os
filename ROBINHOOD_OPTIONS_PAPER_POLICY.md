# Robinhood Options Agent — Paper Policy v0 (2026-10-14)

Status: PAPER ENGINE MILESTONE 1 BUILT AND TESTED. Not broker-connected; live trading remains disabled.

## Scope
- Long calls only; buy to open; one standard 100-share contract per trade.
- Premium paid inclusive of opening fees <= $250, target $100–$250; reject orders above cap.
- One open position maximum; one new position daily; no leverage, margin borrowing, uncovered options, or live orders.
- Prefer liquid stocks/ETFs and tight bid-ask spreads. Primary experiment: 7–21 days to expiration (DTE); comparison: 30 DTE. Verify actual contract specifications.
- Simulated exit experiment: compare loss thresholds of -20% and -30%, and profit thresholds of +30% and +50%, accounting for spreads/slippage. These are test hypotheses, not guaranteed fills or maximum loss.
- Record intraday quote freshness, volume/open interest, spread, implied volatility, time decay, and overnight gap risk; reject stale or thinly traded contracts.
- Block entry if market data stale, quotes missing, spread excessive, contract illiquid, or available paper buying power insufficient.

## Exercise gate
- No automatic exercise, including at expiry; warn that broker automatic exercise/assignment rules must be verified before any live use.
- Required cash for a standard call exercise = strike * 100, plus fees; compare to available settled cash and reserves.
- Also assess current share price versus strike, remaining extrinsic value, expiration, and post-exercise concentration.
- A decayed out-of-the-money call is not rescued by exercise; sale or expiration may be preferable.

## Verification acceptance
- One genuine timestamped option chain/quote, simulated order with fill/slippage, position tracking, risk-gate decisions, exit, net P&L, and durable log.
- Record strategy and reason for every rejection; no fabricated fills or performance claims.
- Live mode remains disabled until repeated paper results, broker permissions, affordability checks and explicit approval.

## Verified milestone 1
- Added `ai_os.robinhood_options` as a paper-only long-call engine.
- Added CLI command: `python3 -m ai_os robinhood-options-paper`.
- Durable ledger defaults to `~/.ai-os/robinhood-options/paper_trades.jsonl`.
- Tests cover premium cap, DTE window, spread/liquidity gates, exercise affordability, rejected opportunities, and durable trade records.
- Fixture data is clearly labeled; it is not a profitability claim or broker-sourced market data.

## Next action
Connect a real market-data adapter and validate an actual supported options simulator/API before selecting broker integration. Keep this separate from Supervizor Telegram crypto signals.
