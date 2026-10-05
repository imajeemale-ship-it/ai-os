"""Command-line interface for AI-OS."""

from __future__ import annotations
import argparse
import json
import sys
from typing import Any
from ai_os.bootstrap import bootstrap
from ai_os.loop import ExecutionLoop
from ai_os.planner import Planner
from ai_os.store import AIOS


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ai-os", description="AI-OS local execution control plane")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize the local database")
    commands.add_parser("bootstrap", help="Add known projects without overwriting existing data")
    commands.add_parser("brief", help="Show today's focus and pending decisions")
    commands.add_parser("projects", help="List projects")
    commands.add_parser("tasks", help="List tasks")
    project = commands.add_parser("project").add_subparsers(dest="action", required=True)
    p = project.add_parser("add")
    p.add_argument("name"); p.add_argument("--goal", default=""); p.add_argument("--priority", type=int, default=3)
    task = commands.add_parser("task").add_subparsers(dest="action", required=True)
    t = task.add_parser("add")
    t.add_argument("project_id"); t.add_argument("title"); t.add_argument("--detail", default="")
    t.add_argument("--priority", type=int, default=3); t.add_argument("--due")
    s = task.add_parser("status")
    s.add_argument("task_id"); s.add_argument("value", choices=["ready", "in_progress", "blocked", "done"])
    approval = commands.add_parser("approval").add_subparsers(dest="action", required=True)
    r = approval.add_parser("request")
    r.add_argument("action_type"); r.add_argument("scope"); r.add_argument("--reason", default="")
    d = approval.add_parser("decide")
    d.add_argument("approval_id"); d.add_argument("decision", choices=["approved", "rejected"])
    c = approval.add_parser("check")
    c.add_argument("action_type"); c.add_argument("scope"); c.add_argument("--approval-id")
    commands.add_parser("events")
    commands.add_parser("plan", help="Rank next actions without changing state")
    run = commands.add_parser("run", help="Run one dry planner cycle")
    run.add_argument("--accept-task", help="Accept the currently recommended task")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        store = AIOS()
        if args.command == "init":
            _print({"database": str(store.db_path), "initialized": True})
        elif args.command == "bootstrap":
            _print(bootstrap(store))
        elif args.command == "brief":
            _print(store.daily_brief())
        elif args.command == "plan":
            _print(Planner(store).plan())
        elif args.command == "run":
            _print(ExecutionLoop(store).run_once(args.accept_task))
        elif args.command == "projects":
            _print(store.list_projects())
        elif args.command == "tasks":
            _print(store.list_tasks())
        elif args.command == "project" and args.action == "add":
            _print(store.add_project(args.name, args.goal, args.priority))
        elif args.command == "task" and args.action == "add":
            _print(store.add_task(args.project_id, args.title, args.detail, args.priority, args.due))
        elif args.command == "task" and args.action == "status":
            _print(store.set_task_status(args.task_id, args.value))
        elif args.command == "approval" and args.action == "request":
            _print(store.request_approval(args.action_type, args.scope, args.reason))
        elif args.command == "approval" and args.action == "decide":
            _print(store.decide_approval(args.approval_id, args.decision))
        elif args.command == "approval" and args.action == "check":
            allowed = store.authorize(args.action_type, args.scope, args.approval_id)
            print("authorized" if allowed else "blocked")
            return 0 if allowed else 2
        elif args.command == "events":
            _print(store.recent_events())
        return 0
    except (ValueError, OSError) as exc:
        print(f"ai-os: {exc}", file=sys.stderr)
        return 2
