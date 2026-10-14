"""Paper-only Robinhood options agent primitives.

No broker credentials, live orders, margin, or short option selling are used here.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CONTRACT_MULTIPLIER = 100
DEFAULT_OPTIONS_DIR = Path.home() / ".ai-os" / "robinhood-options"
DEFAULT_LEDGER = DEFAULT_OPTIONS_DIR / "paper_trades.jsonl"
DEFAULT_REPORT = DEFAULT_OPTIONS_DIR / "latest_morning_report.md"
ALPACA_SECRET_FILE = Path.home() / ".ai-os" / "secrets" / "alpaca.env"
EASTERN = ZoneInfo("America/New_York")


class MarketDataUnavailable(RuntimeError):
    """Raised when a real market-data adapter cannot return a usable quote."""


@dataclass(frozen=True)
class MarketSession:
    checked_at: str
    options_open: bool
    reason: str


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


def market_session(now: datetime | None = None) -> MarketSession:
    current = now or datetime.now(EASTERN)
    eastern = current.astimezone(EASTERN)
    weekday = eastern.weekday()
    current_time = eastern.time()
    options_open = weekday < 5 and time(9, 30) <= current_time <= time(16, 0)
    reason = "regular_options_session" if options_open else "options_market_closed"
    return MarketSession(
        checked_at=eastern.isoformat(timespec="seconds"),
        options_open=options_open,
        reason=reason,
    )


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_present(data: dict[str, Any], names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return default


def _load_env_file(path: Path = ALPACA_SECRET_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


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


class AlpacaOptionsDataAdapter:
    """Read-only Alpaca options market-data adapter for paper trading."""

    base_url = "https://data.alpaca.markets"

    def __init__(self, key_id: str | None = None, secret_key: str | None = None, opener: Any | None = None):
        file_env = _load_env_file()
        self.key_id = (
            key_id or os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID")
            or file_env.get("APCA_API_KEY_ID") or file_env.get("ALPACA_API_KEY_ID")
        )
        self.secret_key = (
            secret_key or os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY")
            or file_env.get("APCA_API_SECRET_KEY") or file_env.get("ALPACA_API_SECRET_KEY")
        )
        self.opener = opener or urllib.request.urlopen
        if not self.key_id or not self.secret_key:
            raise MarketDataUnavailable("missing_alpaca_market_data_credentials")

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": self.key_id,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Accept": "application/json",
            },
        )
        with self.opener(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def option_chain(self, underlying_symbol: str, feed: str = "opra", **filters: str) -> dict[str, Any]:
        params = {"feed": feed, **{key: value for key, value in filters.items() if value}}
        return self._get_json(f"/v1beta1/options/snapshots/{underlying_symbol.upper()}", params)

    def select_long_call(
        self,
        underlying_symbol: str,
        policy: PaperPolicy | None = None,
        feed: str = "opra",
    ) -> OptionQuote:
        active_policy = policy or PaperPolicy()
        data = self.option_chain(underlying_symbol, feed=feed)
        snapshots = data.get("snapshots") or data
        if not isinstance(snapshots, dict) or not snapshots:
            raise MarketDataUnavailable("empty_option_chain")
        candidates: list[OptionQuote] = []
        for contract_symbol, snapshot in snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            details = snapshot.get("details") or snapshot.get("contract") or {}
            option_type = str(_first_present(details, ("type", "option_type", "optionType"), "call")).lower()
            if option_type not in {"call", "c"}:
                continue
            latest_quote = snapshot.get("latestQuote") or snapshot.get("latest_quote") or {}
            greeks = snapshot.get("greeks") or {}
            latest_trade = snapshot.get("latestTrade") or snapshot.get("latest_trade") or {}
            underlying = snapshot.get("underlying") or snapshot.get("underlyingAsset") or {}
            expiration = str(_first_present(details, ("expiration_date", "expirationDate", "expiration"), ""))
            dte = _as_int(_first_present(details, ("dte", "days_to_expiration", "daysToExpiration"), 0))
            bid = _as_float(_first_present(latest_quote, ("bp", "bid_price", "bidPrice", "bid")))
            ask = _as_float(_first_present(latest_quote, ("ap", "ask_price", "askPrice", "ask")))
            strike = _as_float(_first_present(details, ("strike_price", "strikePrice", "strike")))
            if not bid or not ask or not strike:
                continue
            quote = OptionQuote(
                symbol=underlying_symbol.upper(),
                underlying_price=_as_float(_first_present(underlying, ("price", "p", "last", "last_price"))),
                strike=strike,
                expiration=expiration,
                dte=dte,
                bid=bid,
                ask=ask,
                last=_as_float(_first_present(latest_trade, ("p", "price", "last")), (bid + ask) / 2),
                volume=_as_int(_first_present(snapshot, ("volume", "dayVolume"), 0)),
                open_interest=_as_int(_first_present(snapshot, ("openInterest", "open_interest"), 0)),
                implied_volatility=_as_float(snapshot.get("impliedVolatility") or snapshot.get("implied_volatility"), 0.0),
                delta=_as_float(greeks.get("delta"), 0.0),
                gamma=_as_float(greeks.get("gamma"), 0.0),
                theta=_as_float(greeks.get("theta"), 0.0),
                vega=_as_float(greeks.get("vega"), 0.0),
                quote_time=str(_first_present(latest_quote, ("t", "timestamp", "time"), utc_now())),
                underlying_volume=_as_int(_first_present(underlying, ("volume", "v"), 0)),
                source=f"alpaca_options_chain:{contract_symbol}",
            )
            if not validate_entry(quote, PaperAccount(buying_power=10_000, settled_cash=10_000), active_policy):
                candidates.append(quote)
        if not candidates:
            raise MarketDataUnavailable("no_contract_passed_policy_filters")
        return sorted(candidates, key=lambda item: (abs(item.premium - 175), item.spread))[0]


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


def _normalize_symbols(symbols: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(symbols, str):
        raw = symbols.split(",")
    else:
        raw = list(symbols)
    result = [item.strip().upper() for item in raw if item.strip()]
    return result or ["SPY"]


def _best_exit_plan(record: dict[str, Any]) -> str:
    if not record.get("order"):
        return "No sell plan because no paper position was opened."
    exit_scores = record.get("exit_scores") or []
    profit_30 = next((item for item in exit_scores if item["profit_target_pct"] == 0.30 and item["loss_limit_pct"] == -0.20), None)
    profit_50 = next((item for item in exit_scores if item["profit_target_pct"] == 0.50 and item["loss_limit_pct"] == -0.20), None)
    quote = record["quote"]
    order = record["order"]
    target_30 = round(order["fill_price"] * 1.30, 2)
    target_50 = round(order["fill_price"] * 1.50, 2)
    stop_20 = round(order["fill_price"] * 0.80, 2)
    return (
        f"Primary sell plan: take profit near +30% (${target_30}/contract bid) or cut near -20% (${stop_20}/contract bid). "
        f"Stretch target: +50% (${target_50}/contract bid). Current rule status: "
        f"30%={profit_30['action'] if profit_30 else 'unknown'}, 50%={profit_50['action'] if profit_50 else 'unknown'}. "
        f"Do not exercise; required exercise cash is ${quote['strike'] * CONTRACT_MULTIPLIER:.2f}."
    )


def run_alpaca_cycle(symbol: str = "SPY", ledger_path: str | Path | None = None) -> dict[str, Any]:
    session = market_session()
    symbols = _normalize_symbols(symbol)
    if not session.options_open:
        record = {
            "record_type": "paper_options_cycle",
            "created_at": utc_now(),
            "mode": "paper_only_real_data_blocked",
            "live_trading_allowed": False,
            "status": "rejected",
            "entry_rejections": [session.reason],
            "market_session": asdict(session),
            "symbols_checked": symbols,
            "quote": None,
            "order": None,
            "exit_scores": [],
            "morning_summary": "No paper option was bought because the options market was closed.",
        }
        append_ledger(record, ledger_path or DEFAULT_LEDGER)
        return record
    adapter = AlpacaOptionsDataAdapter()
    rejected: list[dict[str, str]] = []
    selected_quote: OptionQuote | None = None
    for item in symbols:
        try:
            selected_quote = adapter.select_long_call(item)
            break
        except MarketDataUnavailable as exc:
            rejected.append({"symbol": item, "reason": str(exc)})
    if selected_quote is None:
        record = {
            "record_type": "paper_options_cycle",
            "created_at": utc_now(),
            "mode": "paper_only_real_data_blocked",
            "live_trading_allowed": False,
            "status": "rejected",
            "entry_rejections": ["no_symbol_passed_filters"],
            "market_session": asdict(session),
            "symbols_checked": symbols,
            "rejected_symbols": rejected,
            "quote": None,
            "order": None,
            "exit_scores": [],
            "morning_summary": "No paper option was bought because no checked symbol passed the filters.",
        }
        append_ledger(record, ledger_path or DEFAULT_LEDGER)
        return record
    account = PaperAccount(buying_power=250.0, settled_cash=5000.0)
    record = paper_trade_cycle(selected_quote, account, ledger_path=ledger_path)
    record["market_session"] = asdict(session)
    record["symbols_checked"] = symbols
    record["rejected_symbols"] = rejected
    record["morning_summary"] = "One paper long call opened from the candidate watchlist because it fit the $100-$250 total premium budget and passed DTE, liquidity, spread, and buying-power gates."
    record["sell_plan"] = _best_exit_plan(record)
    append_ledger({"record_type": "paper_options_enriched", **record}, ledger_path or DEFAULT_LEDGER)
    return record


def save_cycle_report(record: dict[str, Any], path: str | Path = DEFAULT_REPORT) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_cycle_report(record) + "\n", encoding="utf-8")
    return destination


def render_cycle_report(record: dict[str, Any]) -> str:
    quote = record.get("quote")
    lines = [
        "ROBINHOOD OPTIONS PAPER CYCLE",
        "",
        f"Mode: {record['mode']}",
        "live_trading_allowed: false",
        f"Status: {record['status']}",
    ]
    if record.get("market_session"):
        session = record["market_session"]
        lines.append(f"Market session: {session['reason']} at {session['checked_at']}")
    if record.get("symbols_checked"):
        lines.append(f"Candidate symbols checked: {', '.join(record['symbols_checked'])}")
        lines.append("Budget rule: buy at most one contract total, $100-$250 premium.")
    if record.get("morning_summary"):
        lines.extend(["", "WHY", record["morning_summary"]])
    if quote:
        premium = quote['ask'] * CONTRACT_MULTIPLIER
        lines.extend([
            f"Selected paper contract: {quote['symbol']} {quote['expiration']} {quote['strike']}C",
            f"Premium: ${premium:.2f}",
            f"Budget after selected contract: ${250.0 - premium:.2f}",
            f"DTE: {quote['dte']}",
        ])
    lines.append(f"Entry rejections: {', '.join(record['entry_rejections']) or 'none'}")
    if record.get("order"):
        order = record["order"]
        lines.extend([
            f"Paper fill: ${order['fill_price']:.2f} using {order['fill_assumption']}",
            f"Estimated P&L at mark: ${record['estimated_net_pnl']:.2f}",
            f"Exit status: {record['selected_exit_status']}",
        ])
    if record.get("sell_plan"):
        lines.extend(["", "WHEN TO SELL", record["sell_plan"]])
    if record.get("rejected_symbols"):
        lines.extend(["", "REJECTED SYMBOLS"])
        lines.extend(f"- {item['symbol']}: {item['reason']}" for item in record["rejected_symbols"])
    if record.get("exercise_gate"):
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
