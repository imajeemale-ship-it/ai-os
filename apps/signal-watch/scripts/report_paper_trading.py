#!/usr/bin/env python3
"""Export sortable channel-level performance reports from Signal Watch SQLite."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB = Path.home() / ".ai-os" / "signal_watch.db"
DEFAULT_OUTPUT_DIR = Path.home() / ".ai-os" / "reports"
SORT_FIELDS = (
    "total_signals",
    "wins",
    "losses",
    "win_rate_pct",
    "average_return_pct",
    "average_hold_hours",
    "net_paper_pnl_pct",
    "profit_factor",
    "maximum_drawdown_pct",
    "last_signal_date",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _hold_hours(opened_at: Any, closed_at: Any) -> float | None:
    opened = _timestamp(opened_at)
    closed = _timestamp(closed_at)
    if opened is None or closed is None or closed < opened:
        return None
    return (closed - opened).total_seconds() / 3600


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _empty_metrics(channel: str, total_signals: int, last_signal_date: str | None) -> dict[str, Any]:
    return {
        "channel": channel,
        "total_signals": total_signals,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": None,
        "average_return_pct": None,
        "average_hold_hours": None,
        "net_paper_pnl_pct": 0.0,
        "profit_factor": None,
        "maximum_drawdown_pct": 0.0,
        "last_signal_date": last_signal_date,
        "closed_positions": 0,
        "open_positions": 0,
        "draws": 0,
    }


def _maximum_drawdown(returns: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def build_report(db: sqlite3.Connection, *, sort_by: str = "net_paper_pnl_pct", descending: bool = True) -> dict[str, Any]:
    """Build a report without modifying the database.

    Outcome metrics use closed paper positions. Net P/L includes realized P/L
    on open positions, while unrealized P/L is intentionally excluded.
    Maximum drawdown is the peak-to-trough decline of closed-position returns,
    ordered by close time, and is reported as a positive percentage magnitude.
    """
    if sort_by not in SORT_FIELDS:
        raise ValueError(f"Unknown sort field: {sort_by}")

    signal_counts: dict[str, int] = defaultdict(int)
    last_signal: dict[str, datetime] = {}
    if _table_exists(db, "signals"):
        for row in db.execute("SELECT source, sent_at FROM signals"):
            channel = row["source"] or "Unknown"
            signal_counts[channel] += 1
            sent = _timestamp(row["sent_at"])
            if sent is not None and (channel not in last_signal or sent > last_signal[channel]):
                last_signal[channel] = sent

    positions: dict[str, list[sqlite3.Row]] = defaultdict(list)
    if _table_exists(db, "paper_positions"):
        for row in db.execute("SELECT * FROM paper_positions"):
            positions[row["source"] or "Unknown"].append(row)

    channels = set(signal_counts) | set(positions)
    metrics: list[dict[str, Any]] = []
    for channel in channels:
        item = _empty_metrics(
            channel,
            signal_counts[channel],
            last_signal[channel].isoformat(timespec="seconds").replace("+00:00", "Z")
            if channel in last_signal else None,
        )
        channel_positions = positions[channel]
        item["open_positions"] = sum(row["status"] == "open" for row in channel_positions)
        settled: list[tuple[sqlite3.Row, float]] = []
        all_realized: list[float] = []
        for row in channel_positions:
            realized = _number(row["realized_pnl_pct"]) or 0.0
            all_realized.append(realized)
            if row["status"] != "closed":
                continue
            settled.append((row, realized))
            if realized > 0:
                item["wins"] += 1
            elif realized < 0:
                item["losses"] += 1
            else:
                item["draws"] += 1

        item["closed_positions"] = len(settled)
        decided = item["wins"] + item["losses"]
        if decided:
            item["win_rate_pct"] = round(item["wins"] / decided * 100, 4)
        if settled:
            item["average_return_pct"] = round(
                sum(realized for _, realized in settled) / len(settled), 4
            )
            hold_times = [
                hold for row, _ in settled
                if (hold := _hold_hours(row["opened_at"], row["closed_at"])) is not None
            ]
            if hold_times:
                item["average_hold_hours"] = round(sum(hold_times) / len(hold_times), 4)
            ordered = sorted(
                settled,
                key=lambda pair: _timestamp(pair[0]["closed_at"]) or datetime.min.replace(tzinfo=timezone.utc),
            )
            item["maximum_drawdown_pct"] = round(
                _maximum_drawdown(realized for _, realized in ordered), 4
            )
            gross_profit = sum(realized for _, realized in settled if realized > 0)
            gross_loss = sum(-realized for _, realized in settled if realized < 0)
            if gross_loss:
                item["profit_factor"] = round(gross_profit / gross_loss, 4)
            elif gross_profit:
                item["profit_factor"] = None
        item["net_paper_pnl_pct"] = round(sum(all_realized), 4)
        metrics.append(item)

    def sort_value(item: dict[str, Any]):
        value = item.get(sort_by)
        if value is None:
            return (0, 0.0)
        if isinstance(value, str):
            return (1, value)
        return (1, float(value))

    metrics.sort(key=lambda item: (sort_value(item), item["channel"]), reverse=descending)
    for rank, item in enumerate(metrics, start=1):
        item["rank"] = rank
    return {
        "generated_at": utc_now(),
        "database": str(getattr(db, "database", "")),
        "sort_by": sort_by,
        "descending": descending,
        "definitions": {
            "average_return_pct": "mean realized P/L percentage of closed paper positions",
            "average_hold_hours": "mean opened_at-to-closed_at duration of closed positions",
            "net_paper_pnl_pct": "sum of realized P/L percentage across open and closed positions",
            "profit_factor": "gross winning P/L divided by absolute gross losing P/L; null when no losses",
            "maximum_drawdown_pct": "positive peak-to-trough decline of closed-position cumulative returns",
            "win_rate_pct": "wins divided by wins plus losses; draws excluded",
        },
        "channels": metrics,
    }


def _display(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Trading Channel Performance",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Sort: `{report['sort_by']}` ({'descending' if report['descending'] else 'ascending'})",
        "",
        "| Rank | Channel | Total signals | Wins | Losses | Win rate | Avg return | Avg hold (h) | Net paper P/L | Profit factor | Max drawdown | Last signal |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["channels"]:
        channel = str(item["channel"]).replace("|", "\\|")
        lines.append(
            "| {rank} | {channel} | {total_signals} | {wins} | {losses} | {win_rate} | {average_return} | {average_hold} | {net_pnl} | {profit_factor} | {drawdown} | {last_signal} |".format(
                rank=item["rank"],
                channel=channel,
                total_signals=item["total_signals"],
                wins=item["wins"],
                losses=item["losses"],
                win_rate=_display(item["win_rate_pct"], "%"),
                average_return=_display(item["average_return_pct"], "%"),
                average_hold=_display(item["average_hold_hours"]),
                net_pnl=_display(item["net_paper_pnl_pct"], "%"),
                profit_factor=_display(item["profit_factor"]),
                drawdown=_display(item["maximum_drawdown_pct"], "%"),
                last_signal=item["last_signal_date"] or "—",
            )
        )
    lines.extend([
        "",
        "Metrics are based on the existing Signal Watch SQLite database. Open-position unrealized P/L is excluded; realized partial exits are included in net paper P/L.",
    ])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--markdown", dest="markdown_path", type=Path)
    parser.add_argument("--sort-by", choices=SORT_FIELDS, default="net_paper_pnl_pct")
    parser.add_argument("--ascending", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    json_path = args.json_path or args.output_dir / "paper-trading-channel-performance.json"
    markdown_path = args.markdown_path or args.output_dir / "paper-trading-channel-performance.md"
    if not args.db.is_file():
        raise SystemExit(f"Signal Watch database not found: {args.db}")
    with sqlite3.connect(args.db) as db:
        db.row_factory = sqlite3.Row
        report = build_report(db, sort_by=args.sort_by, descending=not args.ascending)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"channels": len(report["channels"]), "json": str(json_path), "markdown": str(markdown_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
