# Trading Focus

AI-OS can summarize Supervizor's current trading readiness without touching external accounts.

Run:

```bash
python3 -m ai_os trading-focus
```

Current policy:

- Paper-only.
- Watch-only.
- Fail-closed.
- No live orders.
- No broker account mutation.
- No credentials required for this report.

The command reads Supervizor's local operator JSON snapshot and reports:

- execution permission flags
- unresolved signal count
- outcomes count
- backtest queue count
- next paper-trading action

Current safest next action is to improve evidence quality before any execution capability is considered.

## Evidence Review Queue

Show unresolved local signal records that need outcome evidence:

```bash
python3 -m ai_os trading-evidence
```

This is read-only. It does not call brokers, place orders, log into accounts, or mutate Supervizor files.

Current queue summary:

- ZEREBRO/USDT buy: missing stop-loss; leverage rejected.
- DOT/USDT buy: missing entry, targets, stop-loss; leverage rejected.
- JTO/USDT short: leverage rejected, but has entry/targets/stop-loss and is reviewable for evidence.
- LINK/USDT buy: missing entry, targets, stop-loss; leverage rejected.

## Outcome Preview

Preview one local signal outcome against a local price path without writing:

```bash
python3 -m ai_os trading-outcome-preview --record-index 3 --prices ~/Desktop/ai-agent-test/ft_userdata/supervizor_price_paths/jtousdt.json
```

JTO record #3 previewed as `stop_loss_hit` from the local price path. The local Supervizor scorer then updated the scoreboard with `execution_allowed: false` and no broker/account calls.

## Live Scoreboard Focus

Use the current local scoreboard instead of the older operator snapshot:

```bash
python3 -m ai_os trading-live-focus
```

Current live scoreboard state:

- Total records: 5
- Resolved records: 2
- Unresolved records: 3
- Outcomes: `stop_loss_hit: 2`
- Execution/trading remain disabled.

## Current Evidence State

After local-only outcome review:

- Total scoreboard records: 5
- Resolved records: 5
- Unresolved records: 0
- Outcomes: `cannot_score: 3`, `stop_loss_hit: 2`
- Method backtest queue: 0 items
- Execution/trading remain disabled.

Next bottleneck: build or refine method inventory so resolved signals can produce testable strategy evidence.

## Method Readiness

Show whether Supervizor has enough method inventory for backtesting:

```bash
python3 -m ai_os trading-methods
```

Current method state:

- Methods: 1
- Method outcomes: 0
- Status: all untested
- Source type: fibonacci only

Next bottleneck: add or refine at least two concrete, testable methods before expecting a meaningful backtest queue.

## Method Outcome State

After adding two paper-only method templates and reviewing queue items locally:

- Method records: 3
- Method outcomes: 3
- Spot Long Risk-Complete Signal Template: 3 helped outcomes
- Promotion engine recommendation: candidate_for_validation
- Remaining queue focuses on Rejected Leverage Signal Filter
- Execution/trading remain disabled.

## End-to-End Paper Review Result

Paper-only review completed locally:

- Scoreboard unresolved records: 0
- Signal outcomes: `cannot_score: 3`, `stop_loss_hit: 2`
- Method records: 3
- Method outcomes: 6
- Spot Long Risk-Complete Signal Template: candidate_for_validation
- Rejected Leverage Signal Filter: candidate_for_validation
- Method backtest queue: 0 items
- Execution/trading remain disabled.

Next decision: review promotion recommendations and decide whether any method should move from `untested` to `testing`. No automatic promotion is performed.

## Promotion Review

Show paper-only method promotion recommendations:

```bash
python3 -m ai_os trading-promotions
```

Current recommendations:

- Rejected Leverage Signal Filter: candidate_for_validation
- Spot Long Risk-Complete Signal Template: candidate_for_validation
- Fibonacci Confluence Placeholder: candidate_for_testing

Promotion requires human decision and does not enable trading.


## Broker Tool Classification

Classify future broker/RPC tools before any live integration work:

```bash
python3 -m ai_os broker-classify get_quote:market_price place_order:buy_or_sell cancel_order:cancel_open_order
```

Or classify a saved inventory file:

```bash
python3 -m ai_os broker-classify --file examples/broker-tools.example.json
python3 -m ai_os broker-classify --file ~/.ai-os/broker-tools.json
python3 -m ai_os trading-real-readiness --broker-tools ~/.ai-os/broker-tools.json
```

The classifier is offline and fail-closed. Read-only/account tools are marked sensitive, order or money-movement tools are marked critical, and unknown tools keep classification incomplete. No classification enables trading by itself.

## Real Trading Readiness Gate

Show the locked path toward future real trading:

```bash
python3 -m ai_os trading-real-readiness
```

Current state:

- Paper methods in testing: pass
- Execution flags disabled: pass
- Broker tool classification: blocked
- Live trading policy revision: blocked
- Funding/risk limits/kill switch: blocked
- KD final approval: blocked

This keeps future real trading easy to prepare for but impossible to enable accidentally.

## Daily Paper Trading Operator

Run the full paper-only trading cockpit:

```bash
python3 -m ai_os trading-daily-operator
```

Save the daily report:

```bash
python3 -m ai_os trading-daily-operator --save
```

Saved reports go to:

```text
~/.ai-os/trading-reports/
```

The report combines live scoreboard status, method readiness, promotion review, and the locked real-trading gate.


## Daily Schedule

Install the Mac LaunchAgent for the paper-only trading operator:

```bash
python3 -m ai_os schedule trading-install --hour 8 --minute 30
```

Check whether it is installed and loaded:

```bash
python3 -m ai_os schedule trading-status
```

Remove it if needed:

```bash
python3 -m ai_os schedule trading-uninstall
```

The schedule uses Mac local time and writes reports to `~/.ai-os/trading-reports/`. It does not enable live trading; the real-trading readiness gate remains locked until broker classification, live policy, risk limits, and KD final approval are complete.
