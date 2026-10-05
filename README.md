# AI-OS

A local-first operating system for turning goals into safe, reviewable execution.

## First milestones

- SQLite-backed projects, tasks, approvals, and event journal
- Deterministic planner that ranks existing next actions
- Dry-run execution loop; state changes require explicit task acceptance
- Exact-scope approval gates for consequential actions
- CLI interface and automated tests

The design follows THINK BROADLY, ACT NARROWLY. AI-OS can prepare work autonomously, but records human decisions and keeps consequential actions behind explicit gates.

## Quick start

Requires Python 3.11+; no third-party packages are required.

```sh
python3 -m ai_os init
python3 -m ai_os bootstrap
python3 -m ai_os project add "Supervizor" --priority 1 --goal "Supervise paper crypto strategies safely"
python3 -m ai_os task add <project-id> "Run the paper-trading health check" --priority 1
python3 -m ai_os plan
python3 -m ai_os run
python3 -m ai_os run --accept-task <recommended-task-id>
python3 -m ai_os model-plan  # optional; requires provider environment variables
python3 -m ai_os proposal accept <proposal-id>
python3 -m ai_os proposal reject <proposal-id>
python3 -m unittest discover -s tests -v
```

Database defaults to `~/.ai-os/ai_os.db`. Set `AI_OS_DB` to use another path. Install with `python3 -m pip install -e .`; `python3 -m ai_os` works even when your Python scripts directory is not on PATH.

## Safety model

Actions default to preparation. `send_message`, `spend_money`, `trade`, `publish`, `delete_data`, and `deploy` require an approved, exact-scope record. The current loop does not connect to any external execution system.

Install the default 3:00 PM local report with `python3 -m ai_os schedule install`; check it with `python3 -m ai_os schedule status`. See [the execution loop design](docs/EXECUTION_LOOP.md) and [the local daily brief](docs/DAILY_BRIEF.md).
