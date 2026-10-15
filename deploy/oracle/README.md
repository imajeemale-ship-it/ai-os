# Oracle paper-options deployment

This deployment runs the paper-only options cycle at 09:35 America/New_York on weekdays.

Safety properties:

- Live trading remains disabled in application records.
- At most one paper contract is selected per cycle.
- Total estimated fill must remain within the $100-$250 premium budget.
- Stale or missing real-data quote timestamps are rejected.
- Credentials are loaded only from `/home/ubuntu/.ai-os/secrets/alpaca.env`.
- The service can write only to `/home/ubuntu/.ai-os` while system files and home content remain read-only.

The Oracle timer is authoritative. The old macOS LaunchAgent is not required after cloud verification.
