"""Command-line interface for AI-OS."""

from __future__ import annotations
import argparse
import json
import sys
from typing import Any
from ai_os.bootstrap import bootstrap
from ai_os.broker_tools import classify_broker_tools, render_broker_tool_classification
from ai_os.chief import chief_of_staff_report, render_chief_of_staff, render_priority_reasoning, save_chief_of_staff_report
from ai_os.cycle import render_cycle, save_daily_cycle
from ai_os.loop import ExecutionLoop
from ai_os.m3 import build_clip_plan, build_m3_proof, build_m3_workflow, export_clip, render_clip_plan, render_export, render_m3_proof, render_m3_sources, render_m3_workflow, scan_m3_sources
from ai_os.planner import Planner
from ai_os.proposal import decide_model_proposal, model_proposal, pending_model_proposals
from ai_os.providers.openai_compatible import OpenAICompatibleProvider
from ai_os.report import render_daily_brief, save_daily_brief
from ai_os.scheduler import (
    daily_brief_status, daily_cycle_status, daily_trading_operator_status,
    install_daily_brief, install_daily_cycle, install_daily_trading_operator,
    uninstall_daily_brief, uninstall_daily_cycle, uninstall_daily_trading_operator,
)
from ai_os.store import AIOS
from ai_os.supervizor import (
    daily_trading_operator, evidence_review_queue, live_trading_focus, method_promotion_review,
    method_readiness, read_supervizor_snapshot, render_daily_trading_operator, render_evidence_review_queue,
    render_live_trading_focus, render_method_promotion_review,
    render_method_readiness, render_price_path_preview, render_real_trading_readiness, render_trading_focus,
    save_daily_trading_operator, score_with_price_path_preview, real_trading_readiness, trading_focus,
)
from ai_os.workers import assign_next, render_assignment


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ai-os", description="AI-OS local execution control plane")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize the local database")
    commands.add_parser("bootstrap", help="Add known projects without overwriting existing data")
    commands.add_parser("brief", help="Show today's focus and pending decisions")
    chief = commands.add_parser("chief-of-staff", help="Run Johnny 5 Chief of Staff review")
    chief.add_argument("--save", action="store_true", help="Save it under ~/.ai-os/chief-of-staff/")
    chief.add_argument("--repo", action="append", default=[], help="Repository path to inspect; may be repeated")
    assign = commands.add_parser("assign-next", help="Route Johnny 5 next action to the right worker")
    assign.add_argument("--repo", action="append", default=[], help="Repository path to inspect; may be repeated")
    commands.add_parser("why-next", help="Explain why Johnny 5 chose the current next action")
    daily = commands.add_parser("daily-brief", help="Generate a local Markdown daily brief")
    daily.add_argument("--save", action="store_true", help="Save it under ~/.ai-os/briefs/")
    cycle = commands.add_parser("daily-cycle", help="Generate a daily brief and optional local model proposal")
    cycle.add_argument("--save", action="store_true", help="Save it under ~/.ai-os/briefs/")
    m3 = commands.add_parser("m3-workflow", help="Show the M3 daily content workflow")
    m3.add_argument("--source", default="Rico GTA footage")
    m3.add_argument("--target", default="one visible M3 asset")
    sources = commands.add_parser("m3-sources", help="Find local M3/Rico/GTA video sources")
    sources.add_argument("--path", action="append", default=[], help="Folder to scan; may be repeated")
    clip = commands.add_parser("m3-clip-plan", help="Create candidate clip segments from a source video")
    clip.add_argument("source")
    clip.add_argument("--length", type=int, default=20)
    export = commands.add_parser("m3-export", help="Export a source video segment")
    export.add_argument("source")
    export.add_argument("--start", type=int, required=True)
    export.add_argument("--duration", type=int, default=20)
    export.add_argument("--label", default="candidate")
    export.add_argument("--output-dir")
    proof = commands.add_parser("m3-proof", help="Log proof for an M3 content asset")
    proof.add_argument("--asset", required=True)
    proof.add_argument("--hook", required=True)
    proof.add_argument("--next-action", required=True)
    proof.add_argument("--platform", default="local")
    proof.add_argument("--source", default="Rico GTA footage")
    commands.add_parser("proposals", help="List pending model proposals for review")
    commands.add_parser("provider-status", help="Check local model configuration and Ollama availability")
    promotions = commands.add_parser("trading-promotions", help="Show paper-only method promotion review")
    promotions.add_argument("--vault")
    promotions.add_argument("--outcomes")
    methods = commands.add_parser("trading-methods", help="Show paper-only method inventory readiness")
    methods.add_argument("--vault")
    methods.add_argument("--outcomes")
    live_trading = commands.add_parser("trading-live-focus", help="Show live scoreboard-based paper trading focus")
    live_trading.add_argument("--scoreboard", help="Path to scoreboard.jsonl")
    evidence = commands.add_parser("trading-evidence", help="Show paper-only unresolved signal review queue")
    evidence.add_argument("--scoreboard", help="Path to scoreboard.jsonl")
    preview = commands.add_parser("trading-outcome-preview", help="Preview a paper outcome from a local price path")
    preview.add_argument("--record-index", type=int, required=True)
    preview.add_argument("--prices", required=True)
    preview.add_argument("--scoreboard")
    daily_trading = commands.add_parser("trading-daily-operator", help="Run the paper trading daily operator report")
    daily_trading.add_argument("--save", action="store_true")
    broker = commands.add_parser("broker-classify", help="Classify broker tool names without enabling trading")
    broker.add_argument("tool", nargs="*", help="Tool name, optionally name:description")
    real = commands.add_parser("trading-real-readiness", help="Show locked real-trading readiness gate")
    trading = commands.add_parser("trading-focus", help="Show paper-only Supervizor trading focus")
    trading.add_argument("--report", help="Path to latest_daily_operator_run.json")
    supervizor_status = commands.add_parser("supervizor-status", help="Read Supervizor's local operator snapshot")
    supervizor_status.add_argument("--report", help="Path to latest_daily_operator_run.json")
    schedule = commands.add_parser("schedule").add_subparsers(dest="action", required=True)
    schedule.add_parser("status", help="Show local daily-brief schedule status")
    schedule.add_parser("uninstall", help="Remove the local daily-brief schedule")
    install = schedule.add_parser("install", help="Install a local daily-brief LaunchAgent")
    install.add_argument("--hour", type=int, default=15)
    install.add_argument("--minute", type=int, default=0)
    schedule.add_parser("cycle-status", help="Show local model-cycle schedule status")
    schedule.add_parser("cycle-uninstall", help="Remove local model-cycle schedule")
    schedule.add_parser("trading-status", help="Show local trading-operator schedule status")
    schedule.add_parser("trading-uninstall", help="Remove local trading-operator schedule")
    trading_install = schedule.add_parser("trading-install", help="Install local trading-operator LaunchAgent")
    trading_install.add_argument("--hour", type=int, default=8)
    trading_install.add_argument("--minute", type=int, default=30)
    cycle_install = schedule.add_parser("cycle-install", help="Install a local model-cycle LaunchAgent")
    cycle_install.add_argument("--hour", type=int, default=15)
    cycle_install.add_argument("--minute", type=int, default=5)
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
    commands.add_parser("model-plan", help="Ask configured model for a validated task proposal")
    proposal = commands.add_parser("proposal").add_subparsers(dest="decision", required=True)
    accept = proposal.add_parser("accept", help="Accept a model proposal and start its task")
    accept.add_argument("proposal_id")
    reject = proposal.add_parser("reject", help="Reject a model proposal")
    reject.add_argument("proposal_id")
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
        elif args.command == "chief-of-staff":
            repo_paths = args.repo or None
            if args.save:
                _print({"saved_to": str(save_chief_of_staff_report(store, repo_paths))})
            else:
                print(render_chief_of_staff(chief_of_staff_report(store, repo_paths)))
        elif args.command == "assign-next":
            print(render_assignment(assign_next(store, args.repo or None)))
        elif args.command == "why-next":
            print(render_priority_reasoning(store))
        elif args.command == "daily-brief":
            if args.save:
                _print({"saved_to": str(save_daily_brief(store))})
            else:
                print(render_daily_brief(store))
        elif args.command == "daily-cycle":
            provider = OpenAICompatibleProvider()
            if args.save:
                path, proposal = save_daily_cycle(store, provider)
                _print({"saved_to": str(path), "proposal": proposal})
            else:
                rendered, _ = render_cycle(store, provider)
                print(rendered)
        elif args.command == "m3-workflow":
            print(render_m3_workflow(build_m3_workflow(args.source, args.target)))
        elif args.command == "m3-sources":
            print(render_m3_sources(scan_m3_sources(args.path or None)))
        elif args.command == "m3-clip-plan":
            print(render_clip_plan(build_clip_plan(args.source, args.length)))
        elif args.command == "m3-export":
            print(render_export(export_clip(args.source, args.start, args.duration, args.output_dir, args.label)))
        elif args.command == "m3-proof":
            proof = build_m3_proof(args.asset, args.hook, args.next_action, args.platform, args.source)
            store.record_event("m3", proof["asset"], "m3.proof_logged", proof)
            print(render_m3_proof(proof))
        elif args.command == "proposals":
            _print(pending_model_proposals(store))
        elif args.command == "provider-status":
            _print(OpenAICompatibleProvider().status())
        elif args.command == "trading-promotions":
            print(render_method_promotion_review(method_promotion_review(args.vault, args.outcomes)))
        elif args.command == "trading-methods":
            print(render_method_readiness(method_readiness(args.vault, args.outcomes)))
        elif args.command == "trading-live-focus":
            print(render_live_trading_focus(live_trading_focus(args.scoreboard)))
        elif args.command == "trading-evidence":
            print(render_evidence_review_queue(evidence_review_queue(args.scoreboard)))
        elif args.command == "trading-outcome-preview":
            print(render_price_path_preview(score_with_price_path_preview(args.record_index, args.prices, args.scoreboard)))
        elif args.command == "trading-daily-operator":
            if args.save:
                _print({"saved_to": str(save_daily_trading_operator())})
            else:
                print(render_daily_trading_operator(daily_trading_operator()))
        elif args.command == "broker-classify":
            tools = []
            for item in args.tool:
                name, _, description = item.partition(":")
                tools.append({"name": name, "description": description})
            print(render_broker_tool_classification(classify_broker_tools(tools)))
        elif args.command == "trading-real-readiness":
            print(render_real_trading_readiness(real_trading_readiness()))
        elif args.command == "trading-focus":
            print(render_trading_focus(trading_focus(args.report)))
        elif args.command == "supervizor-status":
            snapshot = read_supervizor_snapshot(args.report)
            _print(snapshot)
        elif args.command == "schedule" and args.action == "status":
            _print(daily_brief_status())
        elif args.command == "schedule" and args.action == "install":
            _print(install_daily_brief(args.hour, args.minute))
        elif args.command == "schedule" and args.action == "uninstall":
            _print(uninstall_daily_brief())
        elif args.command == "schedule" and args.action == "cycle-install":
            _print(install_daily_cycle(args.hour, args.minute))
        elif args.command == "schedule" and args.action == "cycle-status":
            _print(daily_cycle_status())
        elif args.command == "schedule" and args.action == "cycle-uninstall":
            _print(uninstall_daily_cycle())
        elif args.command == "schedule" and args.action == "trading-install":
            _print(install_daily_trading_operator(args.hour, args.minute))
        elif args.command == "schedule" and args.action == "trading-status":
            _print(daily_trading_operator_status())
        elif args.command == "schedule" and args.action == "trading-uninstall":
            _print(uninstall_daily_trading_operator())
        elif args.command == "plan":
            _print(Planner(store).plan())
        elif args.command == "model-plan":
            _print(model_proposal(store, OpenAICompatibleProvider()))
        elif args.command == "proposal":
            decision = "accepted" if args.decision == "accept" else "rejected"
            _print(decide_model_proposal(store, args.proposal_id, decision))
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
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ai-os: {exc}", file=sys.stderr)
        return 2
