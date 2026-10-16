"""Independent forward paper baskets using live Robinhood market data."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from ai_os.robinhood_options import (
    PaperAccount,
    PaperPolicy,
    RobinhoodMCPDataAdapter,
    _normalize_symbols,
    append_ledger,
    latest_open_position,
    market_session,
    paper_trade_cycle,
    rank_candidates,
    utc_now,
)

DEFAULT_ROOT = Path.home() / ".ai-os" / "robinhood-options"
BASKETS = {
    "tactical": {
        "ledger": DEFAULT_ROOT / "tactical_trades.jsonl",
        "policy": PaperPolicy(min_dte=7, max_dte=21, comparison_dte=30, max_spread_pct=0.05, slippage_pct=0.0),
        "strategies": {"dean_ahrens_unusual_flow_proxy"},
        "exit_rule": {"profit_target_pct": 0.20, "loss_limit_pct": -0.15},
        "max_holding_days": 3,
    },
    "core_trend": {
        "ledger": DEFAULT_ROOT / "core_trend_trades.jsonl",
        "policy": PaperPolicy(min_dte=30, max_dte=60, comparison_dte=45, max_spread_pct=0.05, slippage_pct=0.0),
        "strategies": {"breakout_continuation", "pullback_continuation_uptrend"},
        "exit_rule": {"profit_target_pct": 0.30, "loss_limit_pct": -0.20},
        "max_holding_days": 15,
    },
}


def strategy_allowed(matches: list[str], allowed: set[str]) -> bool:
    return bool(set(matches) & allowed)


def candidate_confirmed(basket: str, matches: list[str], context: dict[str, Any]) -> bool:
    if not context.get("established_uptrend"):
        return False
    if basket == "tactical":
        return "dean_ahrens_unusual_flow_proxy" in matches
    return bool({"breakout_continuation", "pullback_continuation_uptrend"} & set(matches))


def entry_window_open(now: datetime | None = None) -> bool:
    eastern = ZoneInfo("America/New_York")
    current = (now or datetime.now(eastern)).astimezone(eastern)
    return current.weekday() < 5 and time(10, 0) <= current.time() <= time(15, 30)


def entry_opened_today(path: str | Path, now: datetime | None = None) -> bool:
    ledger = Path(path)
    if not ledger.exists():
        return False
    eastern = ZoneInfo("America/New_York")
    today = (now or datetime.now(eastern)).astimezone(eastern).date()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("status") != "filled_and_scored":
            continue
        created = datetime.fromisoformat(str(record.get("created_at", "")).replace("Z", "+00:00"))
        if created.astimezone(eastern).date() == today:
            return True
    return False


def run_basket(
    basket: str,
    symbols: str | list[str],
    ledger_path: str | Path | None = None,
    adapter: RobinhoodMCPDataAdapter | None = None,
) -> dict[str, Any]:
    if basket not in BASKETS:
        raise ValueError(f"unknown_basket:{basket}")
    config = BASKETS[basket]
    ledger = Path(ledger_path or config["ledger"])
    checked = _normalize_symbols(symbols)
    session = market_session()
    base = {
        "record_type": "paper_options_cycle",
        "created_at": utc_now(),
        "mode": "paper_only_research_basket",
        "research_only_shadow": True,
        "live_trading_allowed": False,
        "basket": basket,
        "symbols_checked": checked,
        "policy": asdict(config["policy"]),
        "exit_rule": config["exit_rule"],
        "max_holding_days": config["max_holding_days"],
        "market_session": asdict(session),
    }
    if not entry_window_open():
        record = {**base, "status": "rejected", "entry_rejections": ["outside_confirmed_entry_window"], "quote": None, "order": None}
        append_ledger(record, ledger)
        return record
    if entry_opened_today(ledger):
        record = {**base, "status": "rejected", "entry_rejections": ["daily_basket_entry_limit_reached"], "quote": None, "order": None}
        append_ledger(record, ledger)
        return record
    if latest_open_position(ledger):
        record = {**base, "status": "rejected", "entry_rejections": ["basket_position_already_open"], "quote": None, "order": None}
        append_ledger(record, ledger)
        return record
    if not session.options_open:
        record = {**base, "status": "rejected", "entry_rejections": [session.reason], "quote": None, "order": None}
        append_ledger(record, ledger)
        return record

    data = adapter or RobinhoodMCPDataAdapter()
    candidates = []
    rejected = []
    for symbol in checked:
        try:
            for quote in data.long_call_candidates(symbol, config["policy"]):
                instrument_id = quote.source.partition(":")[2]
                matches = data.strategy_matches.get(instrument_id, [])
                context = data.strategy_contexts.get(quote.symbol) or {}
                if strategy_allowed(matches, config["strategies"]) and candidate_confirmed(basket, matches, context):
                    candidates.append(quote)
        except Exception as exc:
            rejected.append({"symbol": symbol, "reason": str(exc)})
    ranked = rank_candidates(candidates, config["policy"])
    if not ranked:
        record = {
            **base,
            "status": "rejected",
            "entry_rejections": ["no_contract_passed_basket_filters"],
            "rejected_symbols": rejected,
            "quote": None,
            "order": None,
        }
        append_ledger(record, ledger)
        return record

    selected = ranked[0]["quote"]
    record = paper_trade_cycle(
        selected,
        PaperAccount(buying_power=250.0, settled_cash=5000.0),
        policy=config["policy"],
        ledger_path=ledger,
        persist=False,
    )
    instrument_id = selected.source.partition(":")[2]
    record.update(base)
    record["due_diligence"] = ranked[0]["due_diligence"]
    record["strategy_matches"] = data.strategy_matches.get(instrument_id, [])
    record["strategy_context"] = data.strategy_contexts.get(selected.symbol)
    record["directional_signal"] = data.directional_signals.get(selected.symbol)
    record["candidate_rankings"] = [item["due_diligence"] for item in ranked[:5]]
    record["rejected_symbols"] = rejected
    record["sell_plan"] = (
        f"Sell the option at {config['exit_rule']['profit_target_pct']:+.0%} profit or "
        f"{config['exit_rule']['loss_limit_pct']:.0%} loss; time exit after "
        f"{config['max_holding_days']} trading days. Never exercise."
    )
    append_ledger(record, ledger)
    return record


def run_research_baskets(symbols: str | list[str]) -> dict[str, dict[str, Any]]:
    return {name: run_basket(name, symbols) for name in BASKETS}
