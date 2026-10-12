# Johnny 5 Chief of Staff

Johnny 5 Chief of Staff is the AI-OS supervision layer for deciding what should move next without asking KD to manage the queue.

It does not execute risky external actions by itself. It inspects local project state, planner state, approvals, blocked tasks, and repository status, then reports only:

- COMPLETED
- IN PROGRESS
- BLOCKERS
- NEXT AUTONOMOUS ACTION

## Run it

```bash
python3 -m ai_os chief-of-staff
```

Inspect a specific repository:

```bash
python3 -m ai_os chief-of-staff --repo /path/to/repo
```

Save the report:

```bash
python3 -m ai_os chief-of-staff --save
```

Saved reports go to:

```text
~/.ai-os/chief-of-staff/
```

## Repository discovery

By default, AI-OS checks common local repositories:

- `~/Documents/ai-os`
- `~/Desktop/AI-OS`

To define a custom portfolio, set `AI_OS_REPOS` to a comma-separated list:

```bash
export AI_OS_REPOS="$HOME/Documents/ai-os,$HOME/path/to/another-repo"
```

## Operating rule

If a repo has uncommitted work, Johnny 5 treats that as a blocker before assigning new work. This prevents duplicate work, lost changes, and false progress.

## Current limit

This version reads local git repositories and AI-OS tasks. GitHub Issues, Codex worker assignment, and Remote Desktop Commander task execution are the next layer.
