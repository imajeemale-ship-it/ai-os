"""Validate optional model suggestions against the local task registry."""

from __future__ import annotations
from typing import Any
from ai_os.providers.openai_compatible import OpenAICompatibleProvider
from ai_os.store import AIOS, new_id


def eligible_tasks(store: AIOS) -> list[dict[str, Any]]:
    rows = store._read(
        """SELECT t.id AS task_id, t.title, t.detail, t.status, t.priority, t.due_at,
                  p.name AS project_name, p.goal AS project_goal
           FROM tasks t JOIN projects p ON p.id=t.project_id
           WHERE p.status='active' AND t.status IN ('ready','in_progress')
           ORDER BY t.priority, t.due_at IS NULL, t.due_at, t.created_at"""
    )
    return [dict(row) for row in rows]


def model_proposal(store: AIOS, provider: OpenAICompatibleProvider) -> dict[str, Any]:
    proposal_id = new_id("mdl")
    tasks = eligible_tasks(store)
    if not tasks:
        event_id = store.record_event(
            "model_proposal", proposal_id, "model_proposal.no_tasks", {"eligible_count": 0}
        )
        return {"id": proposal_id, "event_id": event_id,
                "status": "no_tasks", "proposal": None, "eligible_count": 0}
    proposed = provider.propose(tasks)
    selected = next((task for task in tasks if task["task_id"] == proposed["task_id"]), None)
    if selected is None:
        reason = "Provider selected a task outside the eligible task list."
        event_id = store.record_event(
            "model_proposal", proposal_id, "model_proposal.rejected",
            {"eligible_count": len(tasks), "reason": reason},
        )
        return {"id": proposal_id, "event_id": event_id, "status": "rejected",
                "proposal": None, "eligible_count": len(tasks), "reason": reason}
    proposal = {
        "task_id": selected["task_id"],
        "title": selected["title"],
        "project": selected["project_name"],
        "reason": proposed["reason"],
    }
    event_id = store.record_event(
        "model_proposal", proposal_id, "model_proposal.proposed",
        {"eligible_count": len(tasks), **proposal},
    )
    return {
        "id": proposal_id,
        "event_id": event_id,
        "status": "proposed",
        "proposal": proposal,
        "eligible_count": len(tasks),
        "execution": "No task state changed. Explicit operator acceptance is still required.",
    }
