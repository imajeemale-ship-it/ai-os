"""Fail-closed broker tool classification for future live integrations."""

from __future__ import annotations
from typing import Any

READ_ONLY_HINTS = ("quote", "price", "market", "position", "portfolio", "balance", "account", "history", "order_status")
EXECUTION_HINTS = ("buy", "sell", "order", "trade", "execute", "cancel", "replace", "deposit", "withdraw", "transfer")


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
