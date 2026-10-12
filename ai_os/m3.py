"""M3 daily content workflow."""

from __future__ import annotations
from datetime import datetime
from typing import Any

DEFAULT_M3_STEPS = [
    "Choose one Rico GTA footage source.",
    "Clip one moment with a clear setup, turn, or payoff.",
    "Write one hook and one title before editing further.",
    "Publish, schedule, or package one visible asset.",
    "Log proof: file name, platform, link or location, and next action.",
]


def build_m3_workflow(source: str = "Rico GTA footage",
                      target: str = "one visible M3 asset") -> dict[str, Any]:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mission": "Turn M3 into a repeatable daily content engine.",
        "source": source,
        "target": target,
        "deadline": "today before sleep",
        "steps": DEFAULT_M3_STEPS,
        "proof_required": [
            "asset file, draft, scheduled post, or published link",
            "title or hook used",
            "next M3 task created or written down",
        ],
        "handoff": "If footage access, platform login, or final taste call is required, escalate to KD. Otherwise continue autonomously.",
    }


def render_m3_workflow(workflow: dict[str, Any]) -> str:
    lines = [
        "M3 DAILY CONTENT WORKFLOW",
        "",
        f"Mission: {workflow['mission']}",
        f"Source: {workflow['source']}",
        f"Target: {workflow['target']}",
        f"Deadline: {workflow['deadline']}",
        "",
        "EXECUTION ORDER",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(workflow["steps"], start=1))
    lines.extend(["", "PROOF REQUIRED"])
    lines.extend(f"- {item}" for item in workflow["proof_required"])
    lines.extend(["", "HANDOFF RULE", f"- {workflow['handoff']}", ""])
    return "\n".join(lines)


def build_m3_proof(asset: str, hook: str, next_action: str,
                   platform: str = "local", source: str = "Rico GTA footage") -> dict[str, Any]:
    if not asset.strip():
        raise ValueError("asset is required")
    if not hook.strip():
        raise ValueError("hook is required")
    if not next_action.strip():
        raise ValueError("next_action is required")
    return {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source.strip(),
        "platform": platform.strip() or "local",
        "asset": asset.strip(),
        "hook": hook.strip(),
        "next_action": next_action.strip(),
        "status": "proof_logged",
    }


def render_m3_proof(proof: dict[str, Any]) -> str:
    return "\n".join([
        "M3 PROOF LOGGED",
        "",
        f"Source: {proof['source']}",
        f"Platform: {proof['platform']}",
        f"Asset: {proof['asset']}",
        f"Hook: {proof['hook']}",
        f"Next action: {proof['next_action']}",
        "",
    ])
