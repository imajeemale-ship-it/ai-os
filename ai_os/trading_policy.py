"""Draft locked live-trading policy documents without enabling execution."""

from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_POLICY_DIR = Path.home() / ".ai-os" / "trading-policy"

REQUIRED_DECISIONS = [
    "Approved broker/account",
    "Initial capital allocation",
    "Maximum daily loss",
    "Maximum weekly loss",
    "Maximum position size",
    "Allowed markets/symbols",
    "Allowed paper-validated methods",
    "Kill switch rule",
    "Human approval rule",
]


def live_policy_draft(today: date | None = None) -> dict[str, Any]:
    current = today or date.today()
    return {
        "mode": "draft_only_live_trading_locked",
        "date": current.isoformat(),
        "execution_allowed": False,
        "trading_allowed": False,
        "required_decisions": REQUIRED_DECISIONS,
        "approval_status": "not_approved",
        "next_action": "Fill every decision, review risks, then require KD final approval before any live execution work.",
    }


def render_live_policy_draft(policy: dict[str, Any]) -> str:
    lines = [
        "LIVE TRADING POLICY DRAFT",
        "",
        f"Date: {policy['date']}",
        f"Mode: {policy['mode']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "approval_status: not_approved",
        "",
        "REQUIRED DECISIONS",
    ]
    for item in policy["required_decisions"]:
        lines.append(f"- [ ] {item}: TBD")
    lines.extend([
        "",
        "DEFAULT RULES UNTIL APPROVED",
        "- No live orders.",
        "- No credential entry into broker tools.",
        "- No account mutation.",
        "- Paper-only reports and classification are allowed.",
        "",
        "NEXT ACTION",
        f"- {policy['next_action']}",
        "",
    ])
    return "\n".join(lines)


def save_live_policy_draft(output_dir: str | Path | None = None, today: date | None = None) -> Path:
    policy = live_policy_draft(today)
    directory = Path(output_dir) if output_dir else DEFAULT_POLICY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{policy['date']}-live-trading-policy-draft.md"
    path.write_text(render_live_policy_draft(policy), encoding="utf-8")
    return path
