"""Fail-closed broker tool classification for future live integrations."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

READ_ONLY_HINTS = ("quote", "price", "market", "position", "portfolio", "balance", "account", "history", "order_status")
EXECUTION_HINTS = ("buy", "sell", "order", "trade", "execute", "cancel", "replace", "deposit", "withdraw", "transfer")


def load_broker_tool_inventory(path: str | Path) -> list[dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tools", [])
    if not isinstance(payload, list):
        raise ValueError("Broker tool inventory must be a list or an object with a tools list")
    tools: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Every broker tool entry must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every broker tool entry needs a non-empty name")
        description = item.get("description", "")
        if not isinstance(description, str):
            raise ValueError("Broker tool descriptions must be strings")
        tools.append({"name": name.strip(), "description": description.strip()})
    return tools


def classify_broker_tool(name: str, description: str = "") -> dict[str, Any]:
    text = f"{name} {description}".lower()
    matched_execution = [hint for hint in EXECUTION_HINTS if hint in text]
    matched_read = [hint for hint in READ_ONLY_HINTS if hint in text]
    if matched_execution:
        category = "execution_or_money_movement"
        allowed = False
        risk = "critical"
    elif matched_read:
        category = "read_only_or_account_data"
        allowed = False
        risk = "sensitive"
    else:
        category = "unknown"
        allowed = False
        risk = "unknown"
    return {
        "name": name,
        "category": category,
        "risk": risk,
        "allowed_for_live_trading": allowed,
        "matched_hints": matched_execution or matched_read,
    }


def load_broker_tool_inventory(path: str | Path) -> list[dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tools", [])
    if not isinstance(payload, list):
        raise ValueError("Broker tool inventory must be a list or an object with a tools list")
    tools: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Every broker tool entry must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every broker tool entry needs a non-empty name")
        description = item.get("description", "")
        if not isinstance(description, str):
            raise ValueError("Broker tool descriptions must be strings")
        tools.append({"name": name.strip(), "description": description.strip()})
    return tools


def classify_broker_tools(tools: list[dict[str, str]]) -> dict[str, Any]:
    rows = [classify_broker_tool(tool.get("name", ""), tool.get("description", "")) for tool in tools]
    unknown = [row for row in rows if row["category"] == "unknown"]
    execution = [row for row in rows if row["category"] == "execution_or_money_movement"]
    return {
        "mode": "broker_tool_classification_only",
        "tools": rows,
        "classified_count": len(rows),
        "unknown_count": len(unknown),
        "execution_or_money_movement_count": len(execution),
        "classification_complete": bool(rows) and not unknown,
        "execution_allowed": False,
        "trading_allowed": False,
        "next_action": "Review all execution or money-movement tools manually before any live policy can be drafted.",
    }


def render_broker_tool_classification(report: dict[str, Any]) -> str:
    lines = [
        "BROKER TOOL CLASSIFICATION",
        "",
        f"Mode: {report['mode']}",
        f"Classified tools: {report['classified_count']}",
        f"Unknown tools: {report['unknown_count']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "TOOLS",
    ]
    if not report["tools"]:
        lines.append("- No broker tools supplied; classification remains blocked.")
    for row in report["tools"]:
        hints = ",".join(row["matched_hints"]) or "none"
        lines.append(f"- {row['name']} | category={row['category']} | risk={row['risk']} | hints={hints}")
    lines.extend(["", "NEXT ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)
