"""Shadow comparison ledger for paper-only options strategies."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
from ai_os.robinhood_options import (
    PaperAccount, PaperPolicy, RobinhoodMCPDataAdapter, append_ledger,
    paper_trade_cycle, rank_candidates, utc_now,
)

DEFAULT_ROOT = Path.home() / ".ai-os" / "robinhood-options"
COMPARISON_LEDGER = DEFAULT_ROOT / "strategy_comparison.jsonl"
STRATEGIES = {
    "flow_momentum": {"required": {"dean_ahrens_unusual_flow_proxy"}},
    "breakout": {"required": {"breakout_continuation"}},
    "fibonacci_pullback": {"required": {"pullback_continuation_uptrend"}},
    "combined_confirmation": {
        "required": {"breakout_continuation", "pullback_continuation_uptrend"},
        "minimum_matches": 2,
    },
}

def run_strategy_comparison(
    symbols: str | list[str],
    adapter: RobinhoodMCPDataAdapter | None = None,
    ledger_path: str | Path = COMPARISON_LEDGER,
) -> dict[str, Any]:
    data = adapter or RobinhoodMCPDataAdapter()
    checked = [item.strip().upper() for item in symbols.split(",")] if isinstance(symbols, str) else [item.upper() for item in symbols]
    candidates = []
    rejected = []
    policy = PaperPolicy(min_dte=7, max_dte=21, max_spread_pct=0.05, slippage_pct=0.0)
    for symbol in checked:
        try:
            candidates.extend(data.long_call_candidates(symbol, policy))
        except Exception as exc:
            rejected.append({"symbol": symbol, "reason": str(exc)})
    from ai_os.robinhood_market_regime import monitor_market_regime
    regime = monitor_market_regime(data.directional_signals)
    records = {"market_regime": regime}
    for name, spec in STRATEGIES.items():
        eligible = []
        for quote in candidates:
            instrument_id = quote.source.partition(":")[2]
            matches = set(data.strategy_matches.get(instrument_id, []))
            required = set(spec["required"])
            if (len(matches & required) >= spec.get("minimum_matches", 1)):
                eligible.append(quote)
        ranked = rank_candidates(eligible, policy)
        record = {
            "record_type": "paper_strategy_comparison",
            "created_at": utc_now(),
            "mode": "paper_only_shadow",
            "live_trading_allowed": False,
            "strategy": name,
            "strategy_layer": "comparison_shadow",
            "contract_layer": "deterministic_rank_candidates_v1",
            "symbols_checked": checked,
            "eligible_candidates": len(ranked),
            "rejected_symbols": rejected,
            "policy": asdict(policy),
        }
        if ranked:
            selected = ranked[0]["quote"]
            simulated = paper_trade_cycle(
                selected, PaperAccount(buying_power=250.0, settled_cash=5000.0),
                policy=policy, persist=False,
            )
            instrument_id = selected.source.partition(":")[2]
            context = data.strategy_contexts.get(selected.symbol, {})
            record.update({
                "status": "shadow_candidate",
                "quote": asdict(selected),
                "contract_selection": ranked[0]["due_diligence"],
                "strategy_evidence": {
                    "matches": data.strategy_matches.get(instrument_id, []),
                    "fib_confluence": context.get("fib_confluence"),
                    "nearest_fib_level": context.get("nearest_fib_level"),
                    "established_uptrend": context.get("established_uptrend"),
                },
                "simulated_entry": simulated,
            })
        else:
            record.update({"status": "no_eligible_candidate", "quote": None})
        append_ledger(record, ledger_path)
        records[name] = record
    return records
