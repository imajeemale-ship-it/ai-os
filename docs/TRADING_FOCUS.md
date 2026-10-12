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
