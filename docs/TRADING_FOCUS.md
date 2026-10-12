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
