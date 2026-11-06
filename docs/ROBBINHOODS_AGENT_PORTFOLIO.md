# Robbinhoods Agent

Robbinhoods Agent is a cloud-hosted, evidence-driven options research and paper-trading system designed with a controlled pathway toward authorized live trading.

## Current status

- Trading mode: paper-only
- Cloud runtime: Oracle-hosted scheduled workers
- Market data: authenticated Robinhood MCP connection verified
- Quote and option-chain retrieval: verified with SPY
- Contract selection: deterministic and policy-gated
- Premium budget: $100–$250 per contract
- Position limit: one open position
- Entry limit: one new position per day
- Live orders: disabled
- Exercise: disabled in the strategy
- Margin and uncovered option selling: disabled
- Alerts: Telegram status and failure reporting
- Automated tests: 152 passing on Oracle

The system records both accepted paper trades and rejected opportunities, including the market evidence, contract details, liquidity checks, spread assumptions, slippage model, exit rule, and reason for rejection.

## Research and execution loop

The operating loop is:

`COLLECT → ANALYZE → VALIDATE → PAPER TRADE → MONITOR → EXIT → SCORE → LEARN`

Strategy selection is separated from deterministic contract validation. The research layer evaluates momentum, breakouts, pullbacks, unusual-flow proxies, market regime, Fibonacci confluence, volatility, liquidity, and scheduled catalysts. The contract layer enforces expiration, premium, spread, volume, open interest, quote freshness, buying power, and position limits.

The paper executor follows the intended live workflow. It uses real market data, applies the same contract and risk gates, simulates the buy using ask-side assumptions and modeled slippage, monitors using fresh bid data, and records the simulated exit. The broker submission step remains disabled.

## Path toward authorized live trading

Live trading is planned, but is not active. Before any live authorization, the system must demonstrate:

1. Repeated forward paper-trading results across multiple market conditions.
2. Point-in-time records with fees, spreads, slippage, drawdown, and rejected setups.
3. Stable real-time data and contract validation.
4. Duplicate-order prevention, stale-signal rejection, restart recovery, and an emergency stop.
5. Independent risk review of the strategy and execution path.
6. Separate explicit owner authorization for live trading.

When that milestone is reached, the live adapter will remain separate from the paper executor and will require its own approval gate. No live order, fund transfer, margin activation, uncovered option sale, or exercise action is authorized by the current system.

## Evidence and limitations

Robinhood MCP authentication and read-only market-data access have been verified from Oracle. A SPY quote and SPY option chain were retrieved successfully. A live-data paper scan correctly rejected the candidate when no contract met the configured policy. This is evidence of connectivity and controls, not evidence of profitability or a proven trading edge.

See [the paper-trading policy](../ROBINHOOD_OPTIONS_PAPER_POLICY.md) for the governing limits and [the portfolio-readiness pull request](https://github.com/imajeemale-ship-it/ai-os/pull/14) for the implementation history.
