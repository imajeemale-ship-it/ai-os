# AI-OS

A local-first operating system for turning goals into safe, reviewable execution.

## First milestone

This repository establishes the control plane:

- SQLite-backed projects, tasks, decisions, and event journal
- A CLI for project and task operations
- Explicit approval gates for consequential actions
- A daily brief that surfaces the best next actions
- No external messages, financial execution, or destructive actions without an approval record

The design follows the user's operating doctrine: THINK BROADLY, ACT NARROWLY. AI-OS can prepare work autonomously, but it records human decisions and keeps consequential execution behind explicit gates.

## Quick start

Requires Python 3.11+; no third-party packages are required.

```sh
python3 -m ai_os init
python3 -m ai_os project add "Supervizor" --priority 1 --goal "Supervise paper crypto strategies safely"
python3 -m ai_os task add <project-id> "Run the daily paper-trading health check" --priority 1
python3 -m ai_os brief
python3 -m unittest discover -s tests -v
```

Database defaults to `~/.ai-os/ai_os.db`. Set `AI_OS_DB` to use another path.

## Safety model

Actions default to `prepare`. Action classes such as `send_message`, `spend_money`, `trade`, `publish`, and `delete_data` require a recorded approval before execution. This milestone provides the gate and audit trail; it does not connect to external execution systems.

## Current limits

This is the foundation, not yet the autonomous company. There is no LLM planner, scheduler, remote integration, or agent runtime yet. Those should be added behind the stable task, event, and approval interfaces.
