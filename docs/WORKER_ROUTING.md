# Worker Routing

Johnny 5 can route the next autonomous action to the worker most likely to complete it with the least KD involvement.

Run:

```bash
python3 -m ai_os assign-next
```

Inspect a specific repository:

```bash
python3 -m ai_os assign-next --repo /path/to/repo
```

## Workers

| Worker | Use When |
| --- | --- |
| Codex | Code, tests, repositories, scripts, automation, APIs, databases, commits, GitHub work |
| Remote Desktop Commander | Browser, terminal, VPS, local computer, UI, login, download, upload, machine operation |
| ChatGPT | Architecture, review, strategy, product judgment, planning |
| Hermes | Telegram, cron, daily delivery, messaging, notification, always-on delivery |
| KD | Credentials, tokens, money, legal approval, final product calls, subjective taste |

## Rule

The router does not execute the task by itself. It creates a clear work order in the Chief of Staff report shape so the next worker can act.
