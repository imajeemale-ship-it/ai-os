"""Draft live-trading risk limits without enabling execution."""

from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_RISK_DIR = Path.home() / ".ai-os" / "trading-policy"

RISK_FIELDS = [
    "starting_capital_usd",
    "max_daily_loss_usd",
    "max_weekly_loss_usd",
    "max_position_size_usd",
    "max_open_positions",
    "max_trades_per_day",
    "cooldown_after_loss_minutes",
    "kill_switch_trigger",
]


def default_risk_limits_path() -> Path:
    return Path.home() / ".ai-os" / "risk-limits.json"


def load_risk_limits(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "limits" in payload:
        payload = payload["limits"]
    if not isinstance(payload, dict):
        raise ValueError("Risk limits must be an object or an object with a limits object")
    return {field: payload.get(field) for field in RISK_FIELDS}


def write_risk_limits_template(path: str | Path | None = None, overwrite: bool = False) -> dict[str, Any]:
    target = Path(path) if path else default_risk_limits_path()
    if target.exists() and not overwrite:
        return {"path": str(target), "written": False, "reason": "already_exists"}
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": "risk_limits_template_live_trading_locked",
        "execution_allowed": False,
        "trading_allowed": False,
        "limits": {field: None for field in RISK_FIELDS},
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"path": str(target), "written": True, "field_count": len(RISK_FIELDS)}


def risk_limits_draft(today: date | None = None) -> dict[str, Any]:
    current = today or date.today()
    return {
        "mode": "draft_only_live_trading_locked",
        "date": current.isoformat(),
        "execution_allowed": False,
        "trading_allowed": False,
        "limits": {field: None for field in RISK_FIELDS},
        "validation_ready": False,
        "next_action": "Fill conservative numeric limits before any live-trading approval review.",
    }


def validate_risk_limits(limits: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in RISK_FIELDS if limits.get(field) in (None, "")]
    numeric_fields = [field for field in RISK_FIELDS if field != "kill_switch_trigger"]
    non_positive = []
    for field in numeric_fields:
        value = limits.get(field)
        if value in (None, ""):
            continue
        try:
            if float(value) <= 0:
                non_positive.append(field)
        except (TypeError, ValueError):
            non_positive.append(field)
    passed = not missing and not non_positive
    return {
        "passed": passed,
        "missing": missing,
        "invalid": non_positive,
        "execution_allowed": False,
        "trading_allowed": False,
    }


def risk_limits_next_questions(limits: dict[str, Any]) -> dict[str, Any]:
    validation = validate_risk_limits(limits)
    questions = {
        "starting_capital_usd": "How much capital is approved for the first live test?",
        "max_daily_loss_usd": "What dollar loss stops trading for the day?",
        "max_weekly_loss_usd": "What dollar loss stops trading for the week?",
        "max_position_size_usd": "What is the largest single position size?",
        "max_open_positions": "How many positions can be open at once?",
        "max_trades_per_day": "How many live trades are allowed per day?",
        "cooldown_after_loss_minutes": "How long must the system wait after a losing trade?",
        "kill_switch_trigger": "What exact condition shuts everything down immediately?",
    }
    next_fields = validation["missing"] + [field for field in validation["invalid"] if field not in validation["missing"]]
    return {
        "mode": "risk_limits_question_queue",
        "passed": validation["passed"],
        "next_fields": next_fields,
        "questions": [{"field": field, "question": questions[field]} for field in next_fields],
        "execution_allowed": False,
        "trading_allowed": False,
    }


def render_risk_limits_questions(report: dict[str, Any]) -> str:
    lines = [
        "RISK LIMITS QUESTIONS",
        "",
        f"Mode: {report['mode']}",
        f"Complete: {str(report['passed']).lower()}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "NEXT FIELDS",
    ]
    if not report["questions"]:
        lines.append("- No missing fields.")
    for row in report["questions"]:
        lines.append(f"- {row['field']}: {row['question']}")
    lines.append("")
    return "\n".join(lines)


def render_risk_limits_draft(report: dict[str, Any]) -> str:
    validation = validate_risk_limits(report["limits"])
    lines = [
        "LIVE TRADING RISK LIMITS DRAFT",
        "",
        f"Date: {report['date']}",
        f"Mode: {report['mode']}",
        "execution_allowed: false",
        "trading_allowed: false",
        f"validation_ready: {str(validation['passed']).lower()}",
        "",
        "LIMITS",
    ]
    for field, value in report["limits"].items():
        shown = "TBD" if value in (None, "") else str(value)
        lines.append(f"- {field}: {shown}")
    lines.extend([
        "",
        "VALIDATION",
        f"- missing: {', '.join(validation['missing']) or 'none'}",
        f"- invalid: {', '.join(validation['invalid']) or 'none'}",
        "",
        "NEXT ACTION",
        f"- {report['next_action']}",
        "",
    ])
    return "\n".join(lines)


def save_risk_limits_draft(output_dir: str | Path | None = None, today: date | None = None) -> Path:
    report = risk_limits_draft(today)
    directory = Path(output_dir) if output_dir else DEFAULT_RISK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report['date']}-risk-limits-draft.md"
    path.write_text(render_risk_limits_draft(report), encoding="utf-8")
    return path
