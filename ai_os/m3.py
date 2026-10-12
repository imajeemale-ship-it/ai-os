"""M3 daily content workflow."""

from __future__ import annotations
import json
import subprocess
from datetime import datetime
from pathlib import Path
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


def scan_m3_sources(paths: list[str] | None = None) -> list[dict[str, Any]]:
    roots = [Path(p).expanduser() for p in (paths or ["~/Downloads", "~/Desktop", "~/Movies"])]
    extensions = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
    keywords = ("rico", "m3", "gta")
    candidates: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for file in root.rglob("*"):
            if not file.is_file() or file.suffix.lower() not in extensions:
                continue
            name = file.name.lower()
            if not any(keyword in name for keyword in keywords):
                continue
            stat = file.stat()
            candidates.append({
                "path": str(file),
                "name": file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 1),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            })
    candidates.sort(key=lambda item: (-item["size_mb"], item["name"].lower()))
    return candidates


def render_m3_sources(candidates: list[dict[str, Any]]) -> str:
    lines = ["M3 SOURCE CANDIDATES", ""]
    if not candidates:
        lines.append("- No Rico, M3, or GTA video files found in scanned folders.")
    else:
        for index, item in enumerate(candidates, start=1):
            lines.append(f"{index}. {item['name']} ({item['size_mb']} MB)")
            lines.append(f"   {item['path']}")
    lines.append("")
    return "\n".join(lines)


def inspect_video(path: str) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.exists():
        raise ValueError(f"video not found: {source}")
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=codec_type,width,height,r_frame_rate",
        "-of", "json", str(source),
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    data = json.loads(result.stdout)
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
    duration = float(data.get("format", {}).get("duration", 0.0))
    size = int(data.get("format", {}).get("size", 0))
    return {
        "path": str(source),
        "name": source.name,
        "duration_seconds": round(duration, 1),
        "size_mb": round(size / (1024 * 1024), 1),
        "width": video.get("width"),
        "height": video.get("height"),
        "frame_rate": video.get("r_frame_rate"),
    }


def build_clip_plan(path: str, clip_length: int = 20) -> dict[str, Any]:
    meta = inspect_video(path)
    duration = int(meta["duration_seconds"])
    if duration <= 0:
        raise ValueError("video duration is unavailable")
    starts = [0]
    if duration > clip_length * 2:
        starts.append(max(0, duration // 2 - clip_length // 2))
    if duration > clip_length:
        starts.append(max(0, duration - clip_length))
    unique_starts = []
    for start in starts:
        if start not in unique_starts:
            unique_starts.append(start)
    candidates = []
    labels = ["opening hook", "middle turn", "closing payoff"]
    for index, start in enumerate(unique_starts[:3]):
        end = min(duration, start + clip_length)
        candidates.append({
            "label": labels[index],
            "start_seconds": start,
            "end_seconds": end,
            "duration_seconds": end - start,
            "target": f"M3 short candidate {index + 1}",
        })
    return {
        "source": meta,
        "clip_length": clip_length,
        "candidates": candidates,
        "next_action": "Review the candidate segments and export the strongest publishable moment.",
    }


def render_clip_plan(plan: dict[str, Any]) -> str:
    source = plan["source"]
    lines = [
        "M3 CLIP PLAN",
        "",
        f"Source: {source['path']}",
        f"Duration: {source['duration_seconds']} seconds",
        f"Video: {source.get('width')}x{source.get('height')} at {source.get('frame_rate')}",
        "",
        "CANDIDATES",
    ]
    for index, item in enumerate(plan["candidates"], start=1):
        lines.append(
            f"{index}. {item['label']}: {item['start_seconds']}s-{item['end_seconds']}s "
            f"({item['duration_seconds']}s)"
        )
    lines.extend(["", "NEXT ACTION", f"- {plan['next_action']}", ""])
    return "\n".join(lines)
