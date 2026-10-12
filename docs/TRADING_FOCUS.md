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
