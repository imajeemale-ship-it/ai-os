#!/usr/bin/env python3
"""Export append-only paper-trade learning and calibration reports."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path.home() / ".ai-os" / "signal_watch.db"
DEFAULT_OUTPUT_DIR = Path.home() / ".ai-os" / "reports"
SORT_FIELDS = ("observations", "win_rate_pct", "average_return_pct", "calibration_score", "decision_accuracy_pct")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _table_exists(db: sqlite3.Connection) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='learning_observations'"
    ).fetchone() is not None


def _channel_metrics(rows: list[sqlite3.Row]) -> dict[str, Any]:
    wins = sum(row["outcome"] == "WIN" for row in rows)
    losses = sum(row["outcome"] == "LOSS" for row in rows)
    returns = [float(row["realized_pnl_pct"]) for row in rows]
    calibration = [_number(row["calibration_score"]) for row in rows]
    calibration = [value for value in calibration if value is not None]
    decision = [row["decision_correct"] for row in rows if row["decision_correct"] is not None]
    return {
        "channel": rows[0]["source"] if rows else "Unknown",
        "observations": len(rows),
        "wins": wins,
        "losses": losses,
        "draws": len(rows) - wins - losses,
        "win_rate_pct": round(wins / (wins + losses) * 100, 4) if wins + losses else None,
        "average_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "average_prediction_error": round(sum(float(row["prediction_error"]) for row in rows if row["prediction_error"] is not None) /
                                           len([row for row in rows if row["prediction_error"] is not None]), 4)
        if any(row["prediction_error"] is not None for row in rows) else None,
        "calibration_score": round(sum(calibration) / len(calibration), 4) if calibration else None,
        "decision_accuracy_pct": round(sum(decision) / len(decision) * 100, 4) if decision else None,
        "net_paper_pnl_pct": round(sum(returns), 4) if returns else 0.0,
        "last_closed_at": max((row["closed_at"] for row in rows), default=None),
    }


def _improvement(rows: list[sqlite3.Row]) -> dict[str, Any] | None:
    ordered = sorted(rows, key=lambda row: _timestamp(row["closed_at"]) or datetime.min.replace(tzinfo=timezone.utc))
    if len(ordered) < 2:
        return None
    midpoint = max(1, len(ordered) // 2)
    first = ordered[:midpoint]
    recent = ordered[midpoint:]

    def rate(items: list[sqlite3.Row]) -> float:
        decided = sum(row["outcome"] in {"WIN", "LOSS"} for row in items)
        return sum(row["outcome"] == "WIN" for row in items) / decided * 100 if decided else 0.0

    first_rate = rate(first)
    recent_rate = rate(recent)
    return {
        "channel": rows[0]["source"],
        "first_period_win_rate_pct": round(first_rate, 4),
        "recent_period_win_rate_pct": round(recent_rate, 4),
        "improvement_pct_points": round(recent_rate - first_rate, 4),
        "observations": len(ordered),
    }


def build_report(db: sqlite3.Connection, *, sort_by: str = "calibration_score", descending: bool = True) -> dict[str, Any]:
    if sort_by not in SORT_FIELDS:
        raise ValueError(f"Unknown sort field: {sort_by}")
    rows = list(db.execute("SELECT * FROM learning_observations ORDER BY closed_at, id")) if _table_exists(db) else []
    by_channel: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_context: dict[str, list[sqlite3.Row]] = defaultdict(list)
    by_consensus: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_channel[row["source"] or "Unknown"].append(row)
        by_context[row["market_context_key"] or "unknown"].append(row)
        score = _number(row["predicted_consensus_score"])
        band = "unknown" if score is None else "low_0_49" if score < 50 else "medium_50_74" if score < 75 else "high_75_100"
        by_consensus[band].append(row)
    channels = [_channel_metrics(items) for items in by_channel.values()]

    def sort_value(item: dict[str, Any]):
        value = item.get(sort_by)
        return (0, 0.0) if value is None else (1, float(value))

    channels.sort(key=lambda item: (sort_value(item), item["channel"]), reverse=descending)
    for rank, item in enumerate(channels, 1):
        item["rank"] = rank
    improvements = [item for items in by_channel.values() if (item := _improvement(items)) is not None]
    improvements.sort(key=lambda item: (item["improvement_pct_points"], item["channel"]), reverse=True)
    worst = sorted(channels, key=lambda item: ((item["win_rate_pct"] is not None, item["win_rate_pct"] or 0), item["channel"]))

    overconfident = sorted(
        (row for row in rows if row["prediction_error"] is not None),
        key=lambda row: float(row["prediction_error"]), reverse=True,
    )[:10]
    underconfident = sorted(
        (row for row in rows if row["prediction_error"] is not None),
        key=lambda row: float(row["prediction_error"]),
    )[:10]

    def prediction_item(row: sqlite3.Row) -> dict[str, Any]:
        return {"channel": row["source"], "ticker": row["ticker"], "closed_at": row["closed_at"],
                "outcome": row["outcome"], "predicted_conviction": row["predicted_conviction"],
                "prediction_error": row["prediction_error"], "calibration_score": row["calibration_score"]}

    def grouped(items: dict[str, list[sqlite3.Row]]) -> list[dict[str, Any]]:
        result = []
        for key, values in items.items():
            wins = sum(row["outcome"] == "WIN" for row in values)
            result.append({"key": key, "observations": len(values), "wins": wins,
                           "win_rate_pct": round(wins / len(values) * 100, 4) if values else None,
                           "average_return_pct": round(sum(float(row["realized_pnl_pct"]) for row in values) / len(values), 4)})
        return sorted(result, key=lambda item: (item["win_rate_pct"] or 0, item["key"]), reverse=True)

    return {
        "generated_at": utc_now(), "sort_by": sort_by, "descending": descending,
        "observations": len(rows), "channels": channels,
        "most_improved_channels": improvements[:10], "worst_performing_channels": worst[:10],
        "overconfident_predictions": [prediction_item(row) for row in overconfident],
        "underconfident_predictions": [prediction_item(row) for row in underconfident],
        "decision_accuracy_pct": round(sum(row["decision_correct"] for row in rows if row["decision_correct"] is not None) /
                                        len([row for row in rows if row["decision_correct"] is not None]) * 100, 4)
        if any(row["decision_correct"] is not None for row in rows) else None,
        "calibration_score": round(sum(float(row["calibration_score"]) for row in rows if row["calibration_score"] is not None) /
                                    len([row for row in rows if row["calibration_score"] is not None]), 4)
        if any(row["calibration_score"] is not None for row in rows) else None,
        "market_context_statistics": grouped(by_context),
        "consensus_effectiveness": grouped(by_consensus),
    }


def _display(value: Any, suffix: str = "") -> str:
    return "—" if value is None else f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Paper Trading Learning Report", "", f"Generated: `{report['generated_at']}`", f"Observations: `{report['observations']}`", "",
             f"Decision accuracy: **{_display(report['decision_accuracy_pct'], '%')}**  ", f"Calibration score: **{_display(report['calibration_score'], '/100')}**", "",
             "## Channel statistics", "", "| Rank | Channel | Observations | Win rate | Avg return | Prediction error | Calibration | Decision accuracy |", "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in report["channels"]:
        lines.append(f"| {item['rank']} | {str(item['channel']).replace('|', '\\|')} | {item['observations']} | {_display(item['win_rate_pct'], '%')} | {_display(item['average_return_pct'], '%')} | {_display(item['average_prediction_error'])} | {_display(item['calibration_score'], '/100')} | {_display(item['decision_accuracy_pct'], '%')} |")
    lines.extend(["", "## Most improved channels", ""])
    for item in report["most_improved_channels"]:
        lines.append(f"- {item['channel']}: {item['improvement_pct_points']:+.2f} percentage points ({item['first_period_win_rate_pct']:.2f}% → {item['recent_period_win_rate_pct']:.2f}%)")
    lines.extend(["", "## Worst performing channels", ""])
    for item in report["worst_performing_channels"]:
        lines.append(f"- {item['channel']}: {_display(item['win_rate_pct'], '%')} win rate, {_display(item['average_return_pct'], '%')} average return")
    lines.extend(["", "## Calibration", "", "### Overconfident predictions", ""])
    for item in report["overconfident_predictions"]:
        lines.append(f"- {item['channel']} {item['ticker']} ({item['outcome']}): error {item['prediction_error']:+.2f}")
    lines.extend(["", "### Underconfident predictions", ""])
    for item in report["underconfident_predictions"]:
        lines.append(f"- {item['channel']} {item['ticker']} ({item['outcome']}): error {item['prediction_error']:+.2f}")
    lines.extend(["", "## Consensus effectiveness", "", "| Band | Observations | Wins | Win rate | Avg return |", "| --- | ---: | ---: | ---: | ---: |"])
    for item in report["consensus_effectiveness"]:
        lines.append(f"| {item['key']} | {item['observations']} | {item['wins']} | {_display(item['win_rate_pct'], '%')} | {_display(item['average_return_pct'], '%')} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    parser.add_argument("--sort-by", choices=SORT_FIELDS, default="calibration_score")
    parser.add_argument("--ascending", action="store_true")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        raise SystemExit(f"Signal Watch database not found: {args.db}")
    with sqlite3.connect(args.db) as db:
        db.row_factory = sqlite3.Row
        report = build_report(db, sort_by=args.sort_by, descending=not args.ascending)
    json_path = args.json_path or args.output_dir / "paper-trading-learning.json"
    markdown_path = args.markdown_path or args.output_dir / "paper-trading-learning.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"observations": report["observations"], "json": str(json_path), "markdown": str(markdown_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
