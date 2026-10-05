"""Read-only adapter for Supervizor's local daily operator JSON snapshot."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

DEFAULT_REPORT = (
    Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata"
    / "supervizor_reports" / "latest_daily_operator_run.json"
)
MAX_REPORT_BYTES = 1_000_000


def read_supervizor_snapshot(path: str | Path | None = None) -> dict[str, Any]:
    """Return a small, sanitized status view; never invokes or writes to Supervizor."""
    report_path = Path(path or DEFAULT_REPORT).expanduser()
    unavailable = {
        "status": "unavailable",
        "source": str(report_path),
        "execution_allowed": None,
        "trading_allowed": None,
        "account_mutation_allowed": None,
    }
    try:
        if not report_path.is_file():
            return {**unavailable, "reason": "report_missing"}
        if report_path.stat().st_size > MAX_REPORT_BYTES:
            return {**unavailable, "reason": "report_too_large"}
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {**unavailable, "reason": "report_unreadable"}
    if not isinstance(payload, dict):
        return {**unavailable, "reason": "invalid_report_shape"}

    flags = {
        "execution_allowed": payload.get("execution_allowed"),
        "trading_allowed": payload.get("trading_allowed"),
        "account_mutation_allowed": payload.get("account_mutation_allowed"),
    }
    all_blocked = all(value is False for value in flags.values())
    dashboard = payload.get("ceo_dashboard")
    dashboard = dashboard if isinstance(dashboard, dict) else {}
    evidence = dashboard.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    score = dashboard.get("ceo_score")
    score = score if isinstance(score, (int, float)) and not isinstance(score, bool) else None
    current_status = payload.get("operator_status")
    status = "read_only_pass" if current_status == "PASS" and all_blocked else "attention_required"

    return {
        "status": status,
        "source": str(report_path),
        "generated_at": payload.get("generated_at") if isinstance(payload.get("generated_at"), str) else None,
        "operator_status": current_status if isinstance(current_status, str) else "unknown",
        "ceo_score": score,
        "current_bottleneck": _safe_text(payload.get("current_bottleneck")),
        "next_move": _safe_text(payload.get("next_move")),
        "execution_allowed": flags["execution_allowed"],
        "trading_allowed": flags["trading_allowed"],
        "account_mutation_allowed": flags["account_mutation_allowed"],
        "evidence": {
            key: evidence.get(key)
            for key in (
                "signals_count", "unresolved_signals_count", "outcomes_count",
                "backtest_queue_count", "robinhood_blocked_capabilities",
                "robinhood_readonly_capabilities",
            )
            if isinstance(evidence.get(key), int) and not isinstance(evidence.get(key), bool)
        },
    }


def _safe_text(value: Any, limit: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:limit] or None


def render_supervizor_snapshot(snapshot: dict[str, Any]) -> str:
    lines = [
        "Supervizor Local Snapshot",
        f"status: {snapshot['status']}",
        f"generated_at: {snapshot.get('generated_at') or 'unknown'}",
        f"operator_status: {snapshot.get('operator_status', 'unknown')}",
        f"ceo_score: {snapshot.get('ceo_score') if snapshot.get('ceo_score') is not None else 'N/A'}",
        f"execution_allowed: {snapshot.get('execution_allowed')}",
        f"trading_allowed: {snapshot.get('trading_allowed')}",
        f"account_mutation_allowed: {snapshot.get('account_mutation_allowed')}",
    ]
    evidence = snapshot.get("evidence") or {}
    if evidence:
        lines.append("evidence: " + ", ".join(f"{key}={value}" for key, value in evidence.items()))
    if snapshot.get("current_bottleneck"):
        lines.append(f"current_bottleneck: {snapshot['current_bottleneck']}")
    if snapshot.get("next_move"):
        lines.append(f"next_move: {snapshot['next_move']}")
    if snapshot.get("reason"):
        lines.append(f"reason: {snapshot['reason']}")
    lines.append("source_access: local read-only file; Supervizor was not executed")
    return "\n".join(lines)
