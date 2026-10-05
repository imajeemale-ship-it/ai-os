# Local daily brief

AI-OS can render a Markdown focus report from its local database and save it under `~/.ai-os/briefs/YYYY-MM-DD.md`. Saving is atomic and repeat runs replace that day's generated report.

On macOS, install a user LaunchAgent for 3:00 PM local time:

```sh
python3 -m ai_os schedule install
python3 -m ai_os schedule status
```

The job runs `python -m ai_os daily-brief --save`, reads only the local AI-OS database, and writes a local file. It does not call a model or send a notification. Change the time with `--hour` and `--minute`. Remove it with:

```sh
python3 -m ai_os schedule uninstall
```

LaunchAgents run only while the Mac user session is active. If the Mac is asleep at the scheduled time, the brief may be written after the machine wakes. The CLI status command reports whether the job is installed and loaded.
