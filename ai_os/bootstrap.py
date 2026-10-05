"""Idempotent import of the user's known project portfolio."""

from __future__ import annotations
from ai_os.store import AIOS

PROJECTS = [
    ("Supervizor", "Supervise paper crypto strategies; log outcomes and enforce risk limits.", 1),
    ("AI-OS", "Build the local-first autonomous execution control plane.", 1),
    ("M3", "Build an autonomous content engine for M3 gaming, starting with Rico's GTA footage.", 2),
    ("Grabbit", "Connect nearby shoppers to local inventory and services with low-friction holds.", 2),
    ("Trash or Treasure", "Identify household items and recommend keep, sell, repair, repurpose, donate, or recycle.", 2),
    ("The Orb", "Develop a photo-first palm-launched flying camera that frames shots and returns to hand.", 2),
]


def bootstrap(store: AIOS) -> dict[str, object]:
    existing = {project["name"]: project for project in store.list_projects()}
    created = []
    unchanged = []
    for name, goal, priority in PROJECTS:
        if name in existing:
            unchanged.append(existing[name])
        else:
            created.append(store.add_project(name, goal, priority))
    return {"created": created, "unchanged": unchanged, "total": len(created) + len(unchanged)}
