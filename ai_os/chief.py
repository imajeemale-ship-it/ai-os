"""Chief of Staff report: inspect work state, repo state, and choose the next autonomous action."""

from __future__ import annotations
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_os.planner import Planner
from ai_os.store import AIOS


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def inspect_repo(path: str | Path) -> dict[str, Any]:
    repo = Path(path).expanduser().resolve()
    if not (repo / ".git").exists():
        return {"path": str(repo), "available": False, "reason": "not a git repository"}
    status = _git(repo, "status", "--short")
    branch = _git(repo, "branch", "--show-current") or "detached"
    commit = _git(repo, "log", "-1", "--oneline") or "no commits"
    remote = _git(repo, "remote", "get-url", "origin") or "no origin remote"
    ahead_behind = _git(repo, "status", "--short", "--branch").splitlines()
    branch_line = ahead_behind[0] if ahead_behind else ""
    return {
        "path": str(repo),
        "name": repo.name,
        "available": True,
        "branch": branch,
        "latest_commit": commit,
        "remote": remote,
        "dirty": bool(status),
        "status_lines": status.splitlines(),
        "branch_status": branch_line,
    }


def default_repo_paths() -> list[Path]:
    configured = os.environ.get("AI_OS_REPOS", "")
    candidates: list[Path] = []
    if configured:
        candidates.extend(Path(item.strip()).expanduser() for item in configured.split(",") if item.strip())
    home = Path.home()
    candidates.extend([
        home / "Documents" / "ai-os",
        home / "Desktop" / "AI-OS",
    ])
    seen: set[str] = set()
    repos: list[Path] = []
    for candidate in candidates:
        resolved = str(candidate.expanduser().resolve())
        if resolved not in seen and (candidate / ".git").exists():
            seen.add(resolved)
            repos.append(candidate)
    return repos


def chief_of_staff_report(store: AIOS, repo_paths: list[str | Path] | None = None) -> dict[str, Any]:
    plan = Planner(store).plan()
    repos = [inspect_repo(path) for path in (repo_paths or default_repo_paths())]
    completed_tasks = store.list_tasks("done")[:5]
    in_progress = store.list_tasks("in_progress")
    blocked = store.list_tasks("blocked")
    dirty_repos = [repo for repo in repos if repo.get("available") and repo.get("dirty")]
    recommended = plan["recommended_next_action"]

    completed = [
        f"{task['project_name']}: {task['title']}" for task in completed_tasks
    ] or ["No completed tasks recorded yet."]
    progress = [
        f"{task['project_name']}: {task['title']}" for task in in_progress
    ]
    if not progress and recommended:
        progress.append(f"Queued: {recommended['project']} - {recommended['title']}")
    if not progress:
        progress.append("No active task selected yet.")

    blockers = [f"Blocked task: {task['project_name']} - {task['title']}" for task in blocked]
    blockers.extend(
        f"Pending approval: {approval['action_type']} - {approval['scope']}"
        for approval in plan["pending_approvals"]
    )
    blockers.extend(
        f"Repo has uncommitted work: {repo['name']} ({len(repo['status_lines'])} file(s))"
        for repo in dirty_repos
    )
    if not blockers:
        blockers.append("None.")

    if dirty_repos:
        first = dirty_repos[0]
        next_action = f"Verify and commit or discard local changes in {first['name']} before assigning new work."
    elif recommended:
        next_action = (
            f"Start {recommended['project']}: {recommended['title']} "
            f"because {recommended['reason']}."
        )
    else:
        next_action = "Create or unblock one concrete task for the highest-priority active project."

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "completed": completed,
        "in_progress": progress,
        "blockers": blockers,
        "next_autonomous_action": next_action,
        "repositories": repos,
    }


def render_chief_of_staff(report: dict[str, Any]) -> str:
    lines = ["COMPLETED"]
    lines.extend(f"- {item}" for item in report["completed"])
    lines.extend(["", "IN PROGRESS"])
    lines.extend(f"- {item}" for item in report["in_progress"])
    lines.extend(["", "BLOCKERS"])
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend(["", "NEXT AUTONOMOUS ACTION", f"- {report['next_autonomous_action']}", ""])
    return "\n".join(lines)


def save_chief_of_staff_report(store: AIOS, repo_paths: list[str | Path] | None = None,
                               directory: str | Path | None = None) -> Path:
    report = chief_of_staff_report(store, repo_paths)
    content = render_chief_of_staff(report)
    output_dir = Path(directory or (Path.home() / ".ai-os" / "chief-of-staff"))
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{datetime.now().astimezone().date().isoformat()}.md"
    fd, temp_name = tempfile.mkstemp(prefix=".chief-", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    store.record_event("report", str(destination), "chief_of_staff.saved", {"path": str(destination)})
    return destination
