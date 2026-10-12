"""Worker routing for Johnny 5 Chief of Staff assignments."""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_os.chief import chief_of_staff_report
from ai_os.store import AIOS

WORKERS = {
    "Codex": "Primary software engineer for code, tests, repos, scripts, and automation.",
    "Remote Desktop Commander": "Machine operator for browser, terminal, UI, and local computer control.",
    "ChatGPT": "Architect, reviewer, strategist, and product decision support.",
    "Hermes": "Always-on messenger, cron runner, and lightweight delivery layer.",
    "KD": "Required only for credentials, money, legal approval, final product calls, and subjective taste.",
}

CODE_TERMS = ("code", "test", "repo", "script", "implement", "build", "cli", "api", "database", "commit", "github")
MACHINE_TERMS = ("browser", "terminal", "click", "download", "upload", "login", "vps", "desktop", "oracle")
STRATEGY_TERMS = ("strategy", "review", "architecture", "product", "decide", "prioritize", "plan")
HERMES_TERMS = ("telegram", "daily", "cron", "schedule", "message", "delivery", "notification")
KD_TERMS = ("credential", "password", "token", "api key", "pay", "purchase", "legal", "approve", "girlfriend")


def route_worker(action: str, blockers: list[str] | None = None) -> dict[str, str]:
    text = " ".join([action, *(blockers or [])]).lower()
    if any(term in text for term in KD_TERMS):
        worker = "KD"
        reason = "requires private access, approval, money, legal judgment, or a subjective decision"
    elif any(term in text for term in CODE_TERMS):
        worker = "Codex"
        reason = "the next action is software, repository, test, or automation work"
    elif any(term in text for term in MACHINE_TERMS):
        worker = "Remote Desktop Commander"
        reason = "the next action needs direct computer, browser, VPS, or terminal operation"
    elif any(term in text for term in HERMES_TERMS):
        worker = "Hermes"
        reason = "the next action is scheduled delivery, messaging, or always-on notification work"
    elif any(term in text for term in STRATEGY_TERMS):
        worker = "ChatGPT"
        reason = "the next action needs architecture, review, planning, or product judgment"
    else:
        worker = "ChatGPT"
        reason = "the action needs clarification into an executable work order before assignment"
    return {"worker": worker, "reason": reason, "capability": WORKERS[worker]}


def assign_next(store: AIOS, repo_paths: list[str | Path] | None = None) -> dict[str, Any]:
    report = chief_of_staff_report(store, repo_paths)
    route = route_worker(report["next_autonomous_action"], report["blockers"])
    work_order = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "worker": route["worker"],
        "reason": route["reason"],
        "capability": route["capability"],
        "assignment": report["next_autonomous_action"],
        "report": report,
    }
    store.record_event("assignment", route["worker"], "assignment.created", {
        "worker": route["worker"],
        "assignment": report["next_autonomous_action"],
    })
    return work_order


def render_assignment(work_order: dict[str, Any]) -> str:
    report = work_order["report"]
    lines = ["COMPLETED"]
    lines.extend(f"- {item}" for item in report["completed"])
    lines.extend(["", "IN PROGRESS"])
    lines.extend(f"- {item}" for item in report["in_progress"])
    lines.extend(["", "BLOCKERS"])
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend([
        "",
        "NEXT AUTONOMOUS ACTION",
        f"- Assign {work_order['worker']}: {work_order['assignment']}",
        f"- Reason: {work_order['reason']}.",
        "",
    ])
    return "\n".join(lines)
