# AI-OS Planner and Execution Loop

## Current behavior

The planner ranks only tasks that already exist in the registry. It favors a task already in progress, higher task priority, and past-due dates. Blocked tasks are reported separately. It does not infer tasks, call a model, send messages, trade, spend, publish, deploy, or delete.

The loop is dry-run by default. It proposes one next action without changing task state. The operator must pass the recommended task ID with `--accept-task` to mark that task in progress. Acceptance is auditable through the existing event journal.

## Why deterministic first

A predictable baseline gives us a control case before adding LLM planning. We can later compare model suggestions against this baseline, log the reason for every suggestion, and route gated actions through approvals.

## Next extension points

1. Add user-authored project templates and import them without overwriting existing data.
2. Add a daily scheduler that writes a brief locally.
3. Add a model-backed proposal adapter with structured output and strict action allowlists.
4. Connect integrations only after each one has a defined read/write policy and test fixture.
