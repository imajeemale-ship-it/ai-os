#!/usr/bin/env python3
"""Generate a historical daily executive report from Signal Watch SQLite."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path.home() / ".ai-os" / "signal_watch.db"
DEFAULT_OUTPUT_DIR = Path.home() / ".ai-os" / "reports" / "daily-executive"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _on_date(value: Any, report_date: date) -> bool:
    timestamp = _timestamp(value)
    return timestamp is not None and timestamp.date() == report_date


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _position_summary(positions: list[sqlite3.Row]) -> dict[str, Any]:
    closed = [row for row in positions if row["status"] == "closed"]
    wins = sum(float(row["realized_pnl_pct"] or 0) > 0 for row in closed)
    losses = sum(float(row["realized_pnl_pct"] or 0) < 0 for row in closed)
    decided = wins + losses
    return {
        "opened": len(positions),
        "closed": len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / decided * 100, 4) if decided else None,
        "net_paper_pnl_pct": round(sum(float(row["realized_pnl_pct"] or 0) for row in closed), 4),
    }


def _channel_metrics(positions: list[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in positions:
        grouped[row["source"] or "Unknown"].append(row)
    result = []
    for channel, rows in grouped.items():
        summary = _position_summary(rows)
        result.append({"channel": channel, **summary})
    return result


def _learning_metrics(observations: list[sqlite3.Row]) -> dict[str, Any]:
    decisions = [row["decision_correct"] for row in observations if row["decision_correct"] is not None]
    calibration = [float(row["calibration_score"]) for row in observations if row["calibration_score"] is not None]
    consensus = [row["consensus_effective"] for row in observations if row["consensus_effective"] is not None]
    return {
        "consensus_accuracy_pct": round(sum(consensus) / len(consensus) * 100, 4) if consensus else None,
        "calibration_score": round(sum(calibration) / len(calibration), 4) if calibration else None,
        "decision_accuracy_pct": round(sum(decisions) / len(decisions) * 100, 4) if decisions else None,
    }


def _context_summary(observations: list[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in observations:
        grouped[row["market_context_key"] or "unknown"].append(row)
    result = []
    for key, rows in grouped.items():
        wins = sum(row["outcome"] == "WIN" for row in rows)
        result.append({"market_context": key, "observations": len(rows), "wins": wins,
                       "win_rate_pct": round(wins / len(rows) * 100, 4) if rows else None,
                       "net_paper_pnl_pct": round(sum(float(row["realized_pnl_pct"] or 0) for row in rows), 4)})
    return sorted(result, key=lambda item: (item["net_paper_pnl_pct"], item["win_rate_pct"] or 0), reverse=True)


def _prediction_extreme(positions: list[sqlite3.Row], winner: bool) -> dict[str, Any] | None:
    closed = [row for row in positions if row["status"] == "closed" and row["predicted_conviction"] is not None]
    eligible = [row for row in closed if (float(row["realized_pnl_pct"] or 0) > 0) == winner]
    if not eligible:
        return None
    row = max(eligible, key=lambda item: float(item["predicted_conviction"]))
    return {"channel": row["source"], "ticker": row["ticker"], "conviction_score": row["predicted_conviction"],
            "decision": row["predicted_decision"], "overall_score": row["predicted_overall_score"],
            "realized_pnl_pct": row["realized_pnl_pct"], "closed_at": row["closed_at"]}


def build_report(db: sqlite3.Connection, report_date: date | str | None = None) -> dict[str, Any]:
    if report_date is None:
        report_date = datetime.now(timezone.utc).date()
    elif isinstance(report_date, str):
        report_date = date.fromisoformat(report_date)
    signals = []
    if _table_exists(db, "signals"):
        signals = [row for row in db.execute("SELECT * FROM signals") if _on_date(row["received_at"], report_date)]
    positions = []
    if _table_exists(db, "paper_positions"):
        positions = [row for row in db.execute("SELECT * FROM paper_positions") if _on_date(row["opened_at"], report_date) or _on_date(row["closed_at"], report_date)]
    opened_positions = [row for row in positions if _on_date(row["opened_at"], report_date)]
    closed_positions = [row for row in positions if _on_date(row["closed_at"], report_date)]
    observations = []
    if _table_exists(db, "learning_observations"):
        observations = [row for row in db.execute("SELECT * FROM learning_observations") if _on_date(row["closed_at"], report_date)]

    daily_positions = _position_summary(closed_positions)
    daily_positions["opened"] = len(opened_positions)
    channels = _channel_metrics(closed_positions)
    best_channel = max(channels, key=lambda item: (item["net_paper_pnl_pct"], item["win_rate_pct"] or 0), default=None)
    worst_channel = min(channels, key=lambda item: (item["net_paper_pnl_pct"], item["win_rate_pct"] or 0), default=None)
    learning = _learning_metrics(observations)
    contexts = _context_summary(observations)

    recommended = [item["channel"] for item in channels if item["net_paper_pnl_pct"] > 0 and (item["win_rate_pct"] or 0) >= 50]
    muted = [item["channel"] for item in channels if item["net_paper_pnl_pct"] < 0 or (item["win_rate_pct"] is not None and item["win_rate_pct"] < 40)]
    if observations:
        best_learning = max(observations, key=lambda row: float(row["calibration_score"] or 0))
        biggest_learning = (
            f"{best_learning['source']} {best_learning['ticker']} produced {best_learning['outcome']} "
            f"with calibration score {_number(best_learning['calibration_score']) or 0:.1f}/100."
        )
    elif contexts:
        biggest_learning = f"Top market condition was {contexts[0]['market_context']} with {contexts[0]['win_rate_pct']:.1f}% wins."
    else:
        biggest_learning = "No completed paper trades were available for learning today."
    watchlist = sorted({row["source"] for row in signals if row["decision"] == "WATCH" and row["source"]})
    watchlist.extend(f"{row['source']} {row['ticker']}" for row in opened_positions if row["source"] and row["ticker"])
    return {
        "report_date": report_date.isoformat(), "generated_at": utc_now(),
        "total_signals_received": len(signals), "paper_trades": daily_positions,
        "best_channel": best_channel, "worst_channel": worst_channel,
        "highest_conviction_winner": _prediction_extreme(closed_positions, True),
        "highest_conviction_loser": _prediction_extreme(closed_positions, False),
        **learning, "top_market_conditions": contexts[:5],
        "recommended_channels_to_follow": recommended, "channels_to_mute": muted,
        "biggest_learning_from_today": biggest_learning,
        "watchlist_for_tomorrow": sorted(set(watchlist)),
    }


def _display(value: Any, suffix: str = "") -> str:
    return "—" if value is None else f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def render_markdown(report: dict[str, Any]) -> str:
    trades = report["paper_trades"]
    lines = [f"# Daily Executive Report — {report['report_date']}", "", f"Generated: `{report['generated_at']}`", "",
             "## Snapshot", "", f"- Signals received: **{report['total_signals_received']}**",
             f"- Paper trades opened: **{trades['opened']}**", f"- Paper trades closed: **{trades['closed']}**",
             f"- Win rate: **{_display(trades['win_rate_pct'], '%')}**", f"- Net paper P/L: **{_display(trades['net_paper_pnl_pct'], '%')}**",
             f"- Consensus accuracy: **{_display(report['consensus_accuracy_pct'], '%')}**", f"- Calibration score: **{_display(report['calibration_score'], '/100')}**",
             f"- Decision accuracy: **{_display(report['decision_accuracy_pct'], '%')}**", ""]
    for label in ("Best channel", "Worst channel"):
        item = report[label.lower().replace(" ", "_")]
        lines.append(f"- {label}: **{item['channel']}** ({_display(item['net_paper_pnl_pct'], '%')})" if item else f"- {label}: **—**")
    lines.extend(["", "## Conviction outcomes", ""])
    for label, key in (("Highest conviction winner", "highest_conviction_winner"), ("Highest conviction loser", "highest_conviction_loser")):
        item = report[key]
        lines.append(f"- {label}: **{item['channel']} {item['ticker']}** at {_display(item['conviction_score'], '/100')}, P/L {_display(item['realized_pnl_pct'], '%')}" if item else f"- {label}: **—**")
    lines.extend(["", "## Market conditions", ""])
    for item in report["top_market_conditions"]:
        lines.append(f"- `{item['market_context']}`: {item['win_rate_pct']:.2f}% win rate, {item['net_paper_pnl_pct']:+.2f}% P/L")
    lines.extend(["", "## Recommendations", "", "Follow: " + (", ".join(report["recommended_channels_to_follow"]) or "—"), "Mute: " + (", ".join(report["channels_to_mute"]) or "—"), "", "## Biggest learning", "", report["biggest_learning_from_today"], "", "## Watchlist for tomorrow", ""])
    lines.extend(f"- {item}" for item in report["watchlist_for_tomorrow"] or ["—"])
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: Path, *, force: bool = False) -> tuple[Path, Path, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / report["report_date"]
    json_path, markdown_path = stem.with_suffix(".json"), stem.with_suffix(".md")
    if not force and json_path.exists() and markdown_path.exists():
        return json_path, markdown_path, False
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--date", dest="report_date", help="UTC date in YYYY-MM-DD format; defaults to today")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        raise SystemExit(f"Signal Watch database not found: {args.db}")
    with sqlite3.connect(args.db) as db:
        db.row_factory = sqlite3.Row
        report = build_report(db, args.report_date)
    json_path, markdown_path, written = write_report(report, args.output_dir, force=args.force)
    print(json.dumps({"report_date": report["report_date"], "written": written, "json": str(json_path), "markdown": str(markdown_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
