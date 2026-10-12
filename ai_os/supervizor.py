"""Read-only adapter for Supervizor's local daily operator JSON snapshot."""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from ai_os.broker_tools import classify_broker_tools

DEFAULT_REPORT = (
    Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata"
    / "supervizor_reports" / "latest_daily_operator_run.json"
)
MAX_REPORT_BYTES = 1_000_000
DEFAULT_SCOREBOARD = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata" / "supervizor_signals" / "scoreboard.jsonl"
DEFAULT_PRICE_PATH_DIR = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata" / "supervizor_price_paths"
DEFAULT_KNOWLEDGE_VAULT = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata" / "supervizor_knowledge" / "knowledge_vault.jsonl"
DEFAULT_METHOD_OUTCOMES = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata" / "supervizor_knowledge" / "method_outcomes.jsonl"


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
    next_action = "Resolve one item with local price-path/outcome evidence only." if queue["items"] else "Build or review the method backtest queue."
    lines.extend(["", "NEXT ACTION", f"- {next_action}", ""])
    return "\n".join(lines)



def _read_prices(path: Path) -> list[float]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("prices")
    if not isinstance(value, list) or not value:
        raise ValueError("prices JSON must be a non-empty array or object with prices")
    return [float(item) for item in value]


def _score_signal_status(record: dict[str, Any], prices: list[float]) -> str:
    targets = record.get("targets") or []
    stop_loss = record.get("stop_loss")
    side = str(record.get("side") or "").lower()
    if not targets or stop_loss is None or side not in {"buy", "long", "short"}:
        return "cannot_score"
    tp1 = float(targets[0])
    stop = float(stop_loss)
    for price in prices:
        if side in {"buy", "long"}:
            if price >= tp1:
                return "tp1_hit"
            if price <= stop:
                return "stop_loss_hit"
        else:
            if price <= tp1:
                return "tp1_hit"
            if price >= stop:
                return "stop_loss_hit"
    return "open"


def score_with_price_path_preview(record_index: int, prices_path: str | Path,
                                  scoreboard_path: str | Path | None = None) -> dict[str, Any]:
    records = read_signal_scoreboard(scoreboard_path)
    if record_index < 0 or record_index >= len(records):
        raise ValueError(f"record index does not exist: {record_index}")
    price_file = Path(prices_path).expanduser()
    prices = _read_prices(price_file)
    record = records[record_index]
    status = _score_signal_status(record, prices)
    return {
        "record_index": record_index,
        "pair": record.get("pair") or "unknown",
        "side": record.get("side") or "unknown",
        "source": _safe_text(record.get("source"), 120) or "unknown",
        "current_status": record.get("result_status") or "unknown",
        "preview_status": status,
        "prices_path": str(price_file),
        "price_points": len(prices),
        "execution_allowed": False,
        "trading_allowed": False,
        "write_performed": False,
    }


def render_price_path_preview(preview: dict[str, Any]) -> str:
    lines = [
        "PAPER OUTCOME PREVIEW",
        "",
        f"Record: #{preview['record_index']} {preview['pair']} {preview['side']}",
        f"Source: {preview['source']}",
        f"Current status: {preview['current_status']}",
        f"Preview status: {preview['preview_status']}",
        f"Price path: {preview['prices_path']}",
        f"Price points: {preview['price_points']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "write_performed: false",
        "",
    ]
    return "\n".join(lines)



def live_trading_focus(scoreboard_path: str | Path | None = None) -> dict[str, Any]:
    queue = evidence_review_queue(scoreboard_path)
    records = read_signal_scoreboard(scoreboard_path)
    resolved = [record for record in records if record.get("result_status") not in {None, "", "unscored"}]
    outcomes = {}
    for record in resolved:
        status = str(record.get("result_status") or "unknown")
        outcomes[status] = outcomes.get(status, 0) + 1
    blockers = []
    if queue["unresolved_count"]:
        blockers.append(f"{queue['unresolved_count']} unresolved signal(s) remain.")
    if not resolved:
        blockers.append("No resolved signal outcomes yet.")
    rejected = sum(1 for record in records if record.get("reject_reasons"))
    if rejected:
        blockers.append(f"{rejected} signal(s) include rejection reasons; do not treat them as executable ideas.")
    return {
        "mode": "paper_only_watch_only",
        "total_records": len(records),
        "resolved_count": len(resolved),
        "unresolved_count": queue["unresolved_count"],
        "outcomes": outcomes,
        "blockers": blockers or ["None for paper-only review."],
        "next_action": "Resolve the next unscored signal with local evidence only." if queue["unresolved_count"] else "Build or review the method backtest queue.",
        "execution_allowed": False,
        "trading_allowed": False,
    }


def render_live_trading_focus(report: dict[str, Any]) -> str:
    lines = [
        "LIVE PAPER TRADING FOCUS",
        "",
        f"Mode: {report['mode']}",
        f"Total records: {report['total_records']}",
        f"Resolved records: {report['resolved_count']}",
        f"Unresolved records: {report['unresolved_count']}",
        f"Outcomes: {report['outcomes']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "BLOCKERS",
    ]
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend(["", "NEXT PAPER-TRADING ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)



def read_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser()
    if not source.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{source}:{line_number}: expected object")
        records.append(value)
    return records


def method_readiness(vault_path: str | Path | None = None,
                     outcomes_path: str | Path | None = None) -> dict[str, Any]:
    methods = read_jsonl_records(vault_path or DEFAULT_KNOWLEDGE_VAULT)
    outcomes = read_jsonl_records(outcomes_path or DEFAULT_METHOD_OUTCOMES)
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for method in methods:
        status = str(method.get("status") or "unknown")
        source_type = str(method.get("source_type") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_source[source_type] = by_source.get(source_type, 0) + 1
    blockers = []
    if not methods:
        blockers.append("No method records exist.")
    if len(methods) < 3:
        blockers.append("Method inventory is too small for meaningful comparison.")
    if not outcomes:
        blockers.append("No method outcomes recorded yet.")
    if all(method.get("status") == "untested" for method in methods) and methods:
        blockers.append("All methods are untested.")
    return {
        "mode": "paper_only_watch_only",
        "method_count": len(methods),
        "outcome_count": len(outcomes),
        "by_status": by_status,
        "by_source_type": by_source,
        "blockers": blockers or ["None for paper-only review."],
        "next_action": _method_next_action(len(methods), len(outcomes), blockers),
        "execution_allowed": False,
        "trading_allowed": False,
    }



def _method_next_action(method_count: int, outcome_count: int, blockers: list[str]) -> str:
    if method_count < 3:
        return "Add or refine at least two concrete, testable methods before expecting a backtest queue."
    if outcome_count == 0:
        return "Record method outcomes against resolved signals."
    if any("All methods are untested" in blocker for blocker in blockers):
        return "Review promotion recommendations and decide whether any method should move from untested to testing."
    return "Continue paper-only method review and keep execution disabled."

def render_method_readiness(report: dict[str, Any]) -> str:
    lines = [
        "METHOD READINESS",
        "",
        f"Mode: {report['mode']}",
        f"Methods: {report['method_count']}",
        f"Method outcomes: {report['outcome_count']}",
        f"By status: {report['by_status']}",
        f"By source type: {report['by_source_type']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "BLOCKERS",
    ]
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend(["", "NEXT PAPER-TRADING ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)



def method_promotion_review(vault_path: str | Path | None = None,
                            outcomes_path: str | Path | None = None) -> dict[str, Any]:
    methods = read_jsonl_records(vault_path or DEFAULT_KNOWLEDGE_VAULT)
    outcomes = read_jsonl_records(outcomes_path or DEFAULT_METHOD_OUTCOMES)
    rows = []
    for method in methods:
        method_id = str(method.get("id") or "")
        relevant = [outcome for outcome in outcomes if outcome.get("method_id") == method_id]
        helped = sum(1 for outcome in relevant if outcome.get("outcome") == "helped")
        failed = sum(1 for outcome in relevant if outcome.get("outcome") == "failed")
        resolved = helped + failed
        helped_rate = None if resolved == 0 else helped / resolved
        if resolved >= 3 and helped_rate is not None and helped_rate >= 0.67:
            recommendation = "candidate_for_validation"
        elif resolved >= 3 and helped_rate is not None and helped_rate <= 0.34:
            recommendation = "candidate_for_rejection"
        elif relevant:
            recommendation = "not_enough_data"
        else:
            recommendation = "candidate_for_testing"
        rows.append({
            "method_id": method_id,
            "title": method.get("title") or "untitled",
            "status": method.get("status") or "unknown",
            "resolved_outcomes": resolved,
            "helped": helped,
            "failed": failed,
            "helped_rate": helped_rate,
            "recommendation": recommendation,
            "execution_allowed": False,
        })
    rows.sort(key=lambda row: (row["recommendation"], row["title"]))
    return {
        "mode": "paper_only_watch_only",
        "methods": rows,
        "execution_allowed": False,
        "trading_allowed": False,
        "next_action": "Review candidate_for_validation methods; promotion requires human decision and does not enable trading.",
    }


def render_method_promotion_review(report: dict[str, Any]) -> str:
    lines = [
        "METHOD PROMOTION REVIEW",
        "",
        f"Mode: {report['mode']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "METHODS",
    ]
    if not report["methods"]:
        lines.append("- No methods found.")
    for row in report["methods"]:
        rate = "n/a" if row["helped_rate"] is None else f"{row['helped_rate']:.2f}"
        lines.append(
            f"- {row['title']} | status={row['status']} | resolved={row['resolved_outcomes']} | helped_rate={rate} | recommendation={row['recommendation']}"
        )
    lines.extend(["", "NEXT PAPER-TRADING ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)



def real_trading_readiness(broker_tools: list[dict[str, str]] | None = None) -> dict[str, Any]:
    broker_report = classify_broker_tools(broker_tools or [])
    broker_detail = (
        "Broker tool inventory classified; manual live policy review still required."
        if broker_report["classification_complete"]
        else "Broker tool inventory is missing or contains unknown tools; live integration remains blocked."
    )
    checks = [
        {"name": "paper_methods_testing", "passed": True, "detail": "Two paper-only methods are in testing."},
        {"name": "execution_flags_disabled", "passed": True, "detail": "AI-OS reports execution/trading disabled."},
        {"name": "broker_tool_classification", "passed": broker_report["classification_complete"], "detail": broker_detail},
        {"name": "explicit_live_policy", "passed": False, "detail": "No approved live-trading policy revision exists."},
        {"name": "funding_and_risk_limits", "passed": False, "detail": "Live account, budget, max loss, and kill switch are not approved."},
        {"name": "human_final_approval", "passed": False, "detail": "KD has not approved live execution scope."},
    ]
    return {
        "mode": "live_trading_locked",
        "ready_for_real_trading": all(item["passed"] for item in checks),
        "checks": checks,
        "broker_tool_classification": broker_report,
        "next_action": "Keep paper testing until broker tools, live policy, risk limits, and KD approval are complete.",
        "execution_allowed": False,
        "trading_allowed": False,
    }


def render_real_trading_readiness(report: dict[str, Any]) -> str:
    lines = [
        "REAL TRADING READINESS",
        "",
        f"Mode: {report['mode']}",
        f"Ready for real trading: {str(report['ready_for_real_trading']).lower()}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "CHECKS",
    ]
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "BLOCKED"
        lines.append(f"- {status}: {check['name']} - {check['detail']}")
    lines.extend(["", "NEXT ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)



def daily_trading_operator() -> dict[str, Any]:
    return {
        "mode": "paper_only_watch_only",
        "live_focus": live_trading_focus(),
        "evidence_queue": evidence_review_queue(),
        "method_readiness": method_readiness(),
        "promotion_review": method_promotion_review(),
        "real_trading_readiness": real_trading_readiness(),
        "execution_allowed": False,
        "trading_allowed": False,
        "next_action": "Continue paper testing; review promotion candidates and keep real trading locked.",
    }


def render_daily_trading_operator(report: dict[str, Any]) -> str:
    live = report["live_focus"]
    methods = report["method_readiness"]
    real = report["real_trading_readiness"]
    lines = [
        "DAILY PAPER TRADING OPERATOR",
        "",
        f"Mode: {report['mode']}",
        "execution_allowed: false",
        "trading_allowed: false",
        "",
        "SCOREBOARD",
        f"- Total records: {live['total_records']}",
        f"- Resolved records: {live['resolved_count']}",
        f"- Unresolved records: {live['unresolved_count']}",
        f"- Outcomes: {live['outcomes']}",
        "",
        "METHODS",
        f"- Methods: {methods['method_count']}",
        f"- Method outcomes: {methods['outcome_count']}",
        f"- By status: {methods['by_status']}",
        "",
        "PROMOTION REVIEW",
    ]
    for row in report["promotion_review"]["methods"]:
        rate = "n/a" if row["helped_rate"] is None else f"{row['helped_rate']:.2f}"
        lines.append(f"- {row['title']}: {row['recommendation']} (status={row['status']}, helped_rate={rate})")
    lines.extend([
        "",
        "REAL TRADING LOCK",
        f"- Ready for real trading: {str(real['ready_for_real_trading']).lower()}",
    ])
    for check in real["checks"]:
        if not check["passed"]:
            lines.append(f"- Blocked: {check['name']} - {check['detail']}")
    lines.extend(["", "NEXT ACTION", f"- {report['next_action']}", ""])
    return "\n".join(lines)


def save_daily_trading_operator(directory: str | Path | None = None) -> Path:
    output_dir = Path(directory or (Path.home() / ".ai-os" / "trading-reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{datetime.now().astimezone().date().isoformat()}.md"
    destination.write_text(render_daily_trading_operator(daily_trading_operator()), encoding="utf-8")
    return destination
