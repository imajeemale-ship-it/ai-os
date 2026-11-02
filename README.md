# AI-OS

> **v0.1 release candidate:** The verified core is a local-first planning and task-acceptance control plane, not an unattended external-action agent. [Architecture](docs/ARCHITECTURE_V0_1.md) · [Verification evidence](docs/RELEASE_VERIFICATION.md) · [Draft release notes](docs/RELEASE_NOTES_V0_1.md).


A local-first operating system for turning goals into safe, reviewable execution.

## First milestones

- SQLite-backed projects, tasks, approvals, and event journal
- Deterministic planner that ranks existing next actions
- Dry-run execution loop; state changes require explicit task acceptance
- Exact-scope approval gates for consequential actions
- CLI interface and automated tests

The design follows THINK BROADLY, ACT NARROWLY. AI-OS can prepare work autonomously, but records human decisions and keeps consequential actions behind explicit gates.

## Quick start: isolated core demo

Requires Python 3.11+. The core package has no third-party runtime dependencies.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
export AI_OS_DB="$(mktemp -d)/ai_os.db"
.venv/bin/ai-os init
.venv/bin/ai-os project add "Portfolio Demo" --priority 1 --goal "Demonstrate safe planning"
.venv/bin/ai-os projects
```

Copy the `id` of the created project into the next command (replace `PROJECT_ID` with the actual identifier):

```sh
.venv/bin/ai-os task add PROJECT_ID "Review a task" --priority 1
.venv/bin/ai-os plan
.venv/bin/ai-os run
```

The default `run` only prepares a plan. Copy the recommended task's `task_id` into the following command:

```sh
.venv/bin/ai-os run --accept-task TASK_ID
.venv/bin/ai-os tasks
.venv/bin/python -m unittest discover -s tests -v
```

These shell commands target macOS/Linux. Windows users must adapt virtual environment paths and temporary-directory syntax. The demonstration was verified with an isolated SQLite database; it performs **no external action**.

For advanced commands (optional model providers, local reports, paper-trading integrations, and scheduling), see the documentation. These integrations are **not** part of the verified core demo.

Database defaults to `~/.ai-os/ai_os.db` when `AI_OS_DB` is unset. Optional model settings can be read from `~/.ai-os/model.json`, with environment overrides. Local Ollama can use a base URL and model without an API key.

## Safety model

The core approval registry requires an approved, exact-scope record for `send_message`, `spend_money`, `trade`, `publish`, `delete_data`, and `deploy`. Enforcement depends on callers using that registry. The demonstrated task-acceptance loop does not connect to an external execution system. Local database access is trusted; approval records are not a sandbox. See [security boundaries](docs/SECURITY_BOUNDARIES_V0_1.md) for data handling and integration limits.

Install the default 3:00 PM local report with `python3 -m ai_os schedule install`; check it with `python3 -m ai_os schedule status`. The optional daily model cycle also includes a compact Supervizor snapshot. The paper-trading operator can be installed with `python3 -m ai_os schedule trading-install`; check it with `python3 -m ai_os schedule trading-status`. By default, `supervizor-status` reads `~/Desktop/ai-agent-test/ft_userdata/supervizor_reports/latest_daily_operator_run.json`; pass `--report PATH` to read a different report. It never starts Supervizor or modifies its files. See [the execution loop design](docs/EXECUTION_LOOP.md) and [the local daily brief](docs/DAILY_BRIEF.md).
