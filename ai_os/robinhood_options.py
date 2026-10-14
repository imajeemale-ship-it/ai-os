"""Paper-only Robinhood options agent primitives.

No broker credentials, live orders, margin, or short option selling are used here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_MULTIPLIER = 100
DEFAULT_LEDGER = Path.home() / ".ai-os" / "robinhood-options" / "paper_trades.jsonl"


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    underlying_price: float
    strike: float
    expiration: str
    dte: int
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    quote_time: str
    underlying_volume: int
    source: str = "fixture"

    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2, 4)

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 4)

    @property
    def premium(self) -> float:
        return round(self.ask * CONTRACT_MULTIPLIER, 2)


@dataclass(frozen=True)
class PaperPolicy:
    max_premium: float = 250.0
    target_min_premium: float = 100.0
    target_max_premium: float = 250.0
    min_dte: int = 7
    max_dte: int = 21
    comparison_dte: int = 30
    max_spread_pct: float = 0.18
    min_volume: int = 50
    min_open_interest: int = 100
    max_concurrent_positions: int = 1
    contracts: int = 1
    fee_per_contract: float = 0.0
    slippage_pct: float = 0.03


@dataclass(frozen=True)
class PaperAccount:
    buying_power: float
    settled_cash: float
    open_positions: int = 0


@dataclass(frozen=True)
class ExitRule:
    profit_target_pct: float
    loss_limit_pct: float


DEFAULT_EXIT_RULES = (
    ExitRule(0.30, -0.20),
    ExitRule(0.50, -0.20),
    ExitRule(0.30, -0.30),
    ExitRule(0.50, -0.30),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_entry(quote: OptionQuote, account: PaperAccount, policy: PaperPolicy) -> list[str]:
    reasons: list[str] = []
    if account.open_positions >= policy.max_concurrent_positions:
        reasons.append("max_concurrent_positions_reached")
    if quote.premium > policy.max_premium:
        reasons.append("premium_above_cap")
    if quote.premium < policy.target_min_premium:
        reasons.append("premium_below_target")
    if not policy.min_dte <= quote.dte <= policy.max_dte:
        reasons.append("dte_outside_primary_window")
    if quote.ask <= 0 or quote.bid <= 0 or quote.bid > quote.ask:
        reasons.append("invalid_quote")
    spread_pct = quote.spread / quote.mid if quote.mid else 1.0
    if spread_pct > policy.max_spread_pct:
        reasons.append("spread_too_wide")
    if quote.volume < policy.min_volume:
        reasons.append("option_volume_too_low")
    if quote.open_interest < policy.min_open_interest:
        reasons.append("open_interest_too_low")
    estimated_cost = quote.premium + policy.fee_per_contract
    if account.buying_power < estimated_cost:
        reasons.append("paper_buying_power_insufficient")
    return reasons


def exercise_affordability(quote: OptionQuote, account: PaperAccount) -> dict[str, Any]:
    required_cash = round(quote.strike * CONTRACT_MULTIPLIER, 2)
    intrinsic = max(0.0, quote.underlying_price - quote.strike)
    extrinsic = round(max(0.0, quote.mid - intrinsic), 4)
    return {
        "required_cash": required_cash,
        "settled_cash": account.settled_cash,
        "affordable": account.settled_cash >= required_cash,
        "underlying_price": quote.underlying_price,
        "strike": quote.strike,
        "intrinsic_value_per_share": round(intrinsic, 4),
        "estimated_extrinsic_value_per_share": extrinsic,
        "auto_exercise_allowed": False,
        "recommendation": "sell_or_hold_option_before_expiration; exercise_requires_explicit_approval",
    }


def simulate_fill(quote: OptionQuote, policy: PaperPolicy) -> dict[str, Any]:
    fill_price = round(quote.ask * (1 + policy.slippage_pct), 4)
    gross_cost = round(fill_price * CONTRACT_MULTIPLIER * policy.contracts, 2)
    total_cost = round(gross_cost + policy.fee_per_contract, 2)
    return {
        "side": "buy_to_open",
        "contracts": policy.contracts,
        "fill_price": fill_price,
        "gross_cost": gross_cost,
        "fees": policy.fee_per_contract,
        "total_cost": total_cost,
        "fill_assumption": f"ask_plus_{policy.slippage_pct:.0%}_slippage",
    }


def score_exit(entry_price: float, current_bid: float, rule: ExitRule) -> dict[str, Any]:
    pnl_pct = (current_bid - entry_price) / entry_price if entry_price else 0.0
    if pnl_pct >= rule.profit_target_pct:
        action = "exit_profit_target"
    elif pnl_pct <= rule.loss_limit_pct:
        action = "exit_loss_limit"
    else:
        action = "hold"
    return {
        "profit_target_pct": rule.profit_target_pct,
        "loss_limit_pct": rule.loss_limit_pct,
        "current_bid": current_bid,
        "pnl_pct": round(pnl_pct, 4),
        "action": action,
    }


def paper_trade_cycle(
    quote: OptionQuote,
    account: PaperAccount,
    policy: PaperPolicy | None = None,
    exit_bid: float | None = None,
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    active_policy = policy or PaperPolicy()
    entry_rejections = validate_entry(quote, account, active_policy)
    record: dict[str, Any] = {
        "record_type": "paper_options_cycle",
        "created_at": utc_now(),
        "mode": "paper_only",
        "live_trading_allowed": False,
        "quote": asdict(quote),
        "policy": asdict(active_policy),
        "entry_rejections": entry_rejections,
        "exercise_gate": exercise_affordability(quote, account),
    }
    if entry_rejections:
        record.update({"status": "rejected", "order": None, "exit_scores": []})
    else:
        order = simulate_fill(quote, active_policy)
        mark_bid = quote.bid if exit_bid is None else exit_bid
        exit_scores = [score_exit(order["fill_price"], mark_bid, rule) for rule in DEFAULT_EXIT_RULES]
        best_action = next((item for item in exit_scores if item["action"] != "hold"), exit_scores[0])
        realized_value = round(mark_bid * CONTRACT_MULTIPLIER * active_policy.contracts, 2)
        pnl = round(realized_value - order["total_cost"], 2)
        record.update({
            "status": "filled_and_scored",
            "order": order,
            "exit_scores": exit_scores,
            "selected_exit_status": best_action["action"],
            "mark_bid": mark_bid,
            "estimated_exit_value": realized_value,
            "estimated_net_pnl": pnl,
        })
    append_ledger(record, ledger_path or DEFAULT_LEDGER)
    return record


def append_ledger(record: dict[str, Any], path: str | Path = DEFAULT_LEDGER) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return destination


def fixture_quote() -> OptionQuote:
    return OptionQuote(
        symbol="SPY",
        underlying_price=585.20,
        strike=590.0,
        expiration="2026-10-30",
        dte=16,
        bid=1.42,
        ask=1.50,
        last=1.46,
        volume=842,
        open_interest=3910,
        implied_volatility=0.218,
        delta=0.36,
        gamma=0.041,
        theta=-0.092,
        vega=0.184,
        quote_time="2026-10-14T14:35:00+00:00",
        underlying_volume=42100000,
        source="clearly_labeled_test_fixture",
    )


def run_fixture_cycle(ledger_path: str | Path | None = None) -> dict[str, Any]:
    account = PaperAccount(buying_power=1000.0, settled_cash=5000.0)
    return paper_trade_cycle(fixture_quote(), account, exit_bid=2.05, ledger_path=ledger_path)


def render_cycle_report(record: dict[str, Any]) -> str:
    quote = record["quote"]
    lines = [
        "ROBINHOOD OPTIONS PAPER CYCLE",
        "",
        f"Mode: {record['mode']}",
        "live_trading_allowed: false",
        f"Status: {record['status']}",
        f"Contract: {quote['symbol']} {quote['expiration']} {quote['strike']}C",
        f"Premium: ${quote['ask'] * CONTRACT_MULTIPLIER:.2f}",
        f"DTE: {quote['dte']}",
        f"Entry rejections: {', '.join(record['entry_rejections']) or 'none'}",
    ]
    if record.get("order"):
        order = record["order"]
        lines.extend([
            f"Paper fill: ${order['fill_price']:.2f} using {order['fill_assumption']}",
            f"Estimated P&L at mark: ${record['estimated_net_pnl']:.2f}",
            f"Exit status: {record['selected_exit_status']}",
        ])
    gate = record["exercise_gate"]
    lines.extend([
        "",
        "EXERCISE GATE",
        f"Required cash: ${gate['required_cash']:.2f}",
        f"Settled cash: ${gate['settled_cash']:.2f}",
        f"Affordable: {str(gate['affordable']).lower()}",
        "Auto exercise allowed: false",
    ])
    return "\n".join(lines)
