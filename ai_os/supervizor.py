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
DEFAULT_SCOREBOARD = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata" / "supervizor_signals" / "scoreboard.jsonl"


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



def trading_focus(path: str | Path | None = None) -> dict[str, Any]:
    snapshot = read_supervizor_snapshot(path)
    evidence = snapshot.get("evidence") or {}
    blockers: list[str] = []
    if snapshot.get("status") != "read_only_pass":
        blockers.append(f"Supervizor snapshot status is {snapshot.get('status')}.")
    if snapshot.get("execution_allowed") is not False:
        blockers.append("Execution flag is not explicitly false.")
    if snapshot.get("trading_allowed") is not False:
        blockers.append("Trading flag is not explicitly false.")
    if snapshot.get("account_mutation_allowed") is not False:
        blockers.append("Account mutation flag is not explicitly false.")
    unresolved = evidence.get("unresolved_signals_count", 0)
    outcomes = evidence.get("outcomes_count", 0)
    backtests = evidence.get("backtest_queue_count", 0)
    if unresolved:
        blockers.append(f"{unresolved} unresolved signal(s) need review before trusting performance.")
    if outcomes == 0:
        blockers.append("No resolved outcomes logged yet; strategy quality is unproven.")
    if backtests == 0:
        blockers.append("Backtest queue is empty; no method has been stress-tested yet.")

    if snapshot.get("next_move"):
        next_action = snapshot["next_move"]
    elif blockers:
        next_action = "Resolve the first blocker without enabling live trading."
    else:
        next_action = "Continue paper-only scoring and produce the next operator report."

    return {
        "mode": "paper_only_watch_only",
        "status": snapshot.get("status"),
        "trading_allowed": False,
        "execution_allowed": False,
        "account_mutation_allowed": False,
        "ceo_score": snapshot.get("ceo_score"),
        "blockers": blockers or ["None for paper-only review."],
        "next_action": next_action,
        "source": snapshot.get("source"),
    }


def render_trading_focus(report: dict[str, Any]) -> str:
    lines = [
        "TRADING FOCUS",
        "",
        f"Mode: {report['mode']}",
        f"Status: {report.get('status')}",
        f"CEO score: {report.get('ceo_score') if report.get('ceo_score') is not None else 'N/A'}",
        "execution_allowed: false",
        "trading_allowed: false",
        "account_mutation_allowed: false",
        "",
        "BLOCKERS",
    ]
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend(["", "NEXT PAPER-TRADING ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)



def read_signal_scoreboard(path: str | Path | None = None) -> list[dict[str, Any]]:
    scoreboard = Path(path or DEFAULT_SCOREBOARD).expanduser()
    if not scoreboard.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(scoreboard.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{scoreboard}:{line_number}: invalid JSONL") from error
        if not isinstance(value, dict):
            raise ValueError(f"{scoreboard}:{line_number}: expected object")
        records.append(value)
    return records


def evidence_review_queue(path: str | Path | None = None) -> dict[str, Any]:
    records = read_signal_scoreboard(path)
    items = []
    for index, record in enumerate(records):
        if record.get("result_status") != "unscored":
            continue
        missing = []
        if not record.get("entry_low") and not isinstance(record.get("entry"), dict):
            missing.append("entry")
        if not record.get("targets"):
            missing.append("targets")
        if record.get("stop_loss") is None:
            missing.append("stop_loss")
        if record.get("leverage_detected"):
            missing.append("leverage_rejected")
        items.append({
            "record_index": index,
            "pair": record.get("pair") or "unknown",
            "side": record.get("side") or "unknown",
            "source": _safe_text(record.get("source"), 120) or "unknown",
            "missing": missing,
            "approved_for_paper_trade": bool(record.get("approved_for_paper_trade")),
            "execution_allowed": False,
            "recommended_review": "collect price path/outcome evidence only; do not trade",
        })
    return {
        "mode": "paper_only_watch_only",
        "total_records": len(records),
        "unresolved_count": len(items),
        "items": items,
        "execution_allowed": False,
        "trading_allowed": False,
    }


def render_evidence_review_queue(queue: dict[str, Any]) -> str:
    lines = [
        "PAPER TRADING EVIDENCE REVIEW QUEUE",
        "",
        f"Mode: {queue['mode']}",
        f"Total records: {queue['total_records']}",
        f"Unresolved records: {queue['unresolved_count']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "ITEMS",
    ]
    if not queue["items"]:
        lines.append("- No unresolved signal records.")
    for item in queue["items"]:
        missing = ", ".join(item["missing"]) if item["missing"] else "outcome"
        lines.append(
            f"- #{item['record_index']} {item['pair']} {item['side']} from {item['source']} | needs: {missing}"
        )
    lines.extend(["", "NEXT ACTION", "- Resolve one item with local price-path/outcome evidence only.", ""])
    return "\n".join(lines)
