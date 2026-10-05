"""One safe planner cycle: propose, record, await explicit acceptance."""

from __future__ import annotations
from typing import Any
from ai_os.planner import Planner
from ai_os.store import AIOS


class ExecutionLoop:
    def __init__(self, store: AIOS):
        self.store = store
        self.planner = Planner(store)

    def run_once(self, accept_task_id: str | None = None) -> dict[str, Any]:
        plan = self.planner.plan()
        selected = plan["recommended_next_action"]
        result: dict[str, Any] = {"plan": plan, "accepted": False, "started_task": None}
        if accept_task_id is None:
            result["message"] = "Plan prepared; no task changed. Pass --accept-task to start one."
            return result
        if not selected or selected["task_id"] != accept_task_id:
            raise ValueError("Only the currently recommended task can be accepted")
        task = self.store.set_task_status(accept_task_id, "in_progress")
        result.update({
            "accepted": True,
            "started_task": task,
            "message": "Accepted task marked in progress. No external action was performed.",
        })
        return result
