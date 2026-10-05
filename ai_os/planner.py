"""Deterministic next-action planner. Suggestions are advisory, never executed."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from ai_os.store import AIOS


def _is_overdue(due_at: str | None) -> bool:
    if not due_at:
        return False
    try:
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < datetime.now(timezone.utc)
    except ValueError:
        return False


class Planner:
    def __init__(self, store: AIOS):
        self.store = store

    def plan(self) -> dict[str, Any]:
        """Rank existing actionable tasks, report blocked items and approval gates."""
        brief = self.store.daily_brief()
        actions = []
        for task in brief["next_actions"]:
            if task["status"] == "blocked":
                continue
            score = (6 - task["priority"]) * 10
            if task["status"] == "in_progress":
                score += 25
            if _is_overdue(task.get("due_at")):
                score += 40
            actions.append({
                "task_id": task["id"],
                "project": task["project_name"],
                "title": task["title"],
                "status": task["status"],
                "priority_score": score,
                "reason": self._reason(task),
                "proposed_action": "continue" if task["status"] == "in_progress" else "start",
            })
        actions.sort(key=lambda item: (-item["priority_score"], item["project"], item["title"]))
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "recommended_next_action": actions[0] if actions else None,
            "ranked_actions": actions,
            "blocked_tasks": [
                {"task_id": t["id"], "project": t["project_name"], "title": t["title"]}
                for t in brief["next_actions"] if t["status"] == "blocked"
            ],
            "pending_approvals": brief["pending_approvals"],
            "guardrails": [
                "The planner does not create tasks or execute external actions.",
                "Starting a task requires explicit acceptance through the CLI.",
                "Gated actions require an approved exact-scope approval.",
            ],
        }

    @staticmethod
    def _reason(task: dict[str, Any]) -> str:
        reasons = [f"priority {task['priority']}/5"]
        if task["status"] == "in_progress":
            reasons.append("already in progress")
        if _is_overdue(task.get("due_at")):
            reasons.append("past due")
        return "; ".join(reasons)
