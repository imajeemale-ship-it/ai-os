"""Daily local brief rendering and atomic file output."""

from __future__ import annotations
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from ai_os.planner import Planner
from ai_os.store import AIOS


def render_daily_brief(store: AIOS, generated_at: datetime | None = None) -> str:
    local_now = (generated_at or datetime.now().astimezone())
    brief = store.daily_brief()
    plan = Planner(store).plan()
    lines = [
        "# AI-OS Daily Brief",
        "",
        f"Generated: {local_now.isoformat(timespec='minutes')}",
        "",
        "## Focus",
    ]
    next_action = plan["recommended_next_action"]
    if next_action:
        lines.append(f"- Next action: **{next_action['title']}** ({next_action['project']})")
        lines.append(f"- Why: {next_action['reason']}")
    else:
        lines.append("- No open task is ready to start. Add or unblock a task to give AI-OS work to advance.")
    lines.extend(["", "## Projects"])
    if brief["projects"]:
        for project in brief["projects"]:
            lines.append(
                f"- {project['name']} — priority {project['priority']}/5; "
                f"{project.get('open_tasks', 0)} open task(s)"
            )
    else:
        lines.append("- No active projects.")
    lines.extend(["", "## Open Tasks"])
    if brief["next_actions"]:
        for task in brief["next_actions"]:
            lines.append(f"- [{task['status']}] {task['title']} — {task['project_name']} (priority {task['priority']}/5)")
    else:
        lines.append("- None.")
    lines.extend(["", "## Decisions Needed"])
    if brief["pending_approvals"]:
        for approval in brief["pending_approvals"]:
            lines.append(f"- {approval['action_type']}: {approval['scope']} — {approval['reason'] or 'reason not provided'}")
    else:
        lines.append("- None.")
    lines.extend(["", "_This brief is generated locally. It does not contact a model or perform external actions._", ""])
    return "\n".join(lines)


def save_daily_brief(store: AIOS, directory: str | Path | None = None,
                     generated_at: datetime | None = None) -> Path:
    local_now = generated_at or datetime.now().astimezone()
    output_dir = Path(directory or (Path.home() / ".ai-os" / "briefs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{local_now.date().isoformat()}.md"
    content = render_daily_brief(store, local_now)
    fd, temp_name = tempfile.mkstemp(prefix=".brief-", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return destination
