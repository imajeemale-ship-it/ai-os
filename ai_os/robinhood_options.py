"""Paper-only Robinhood options agent primitives.

No broker credentials, live orders, margin, or short option selling are used here.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CONTRACT_MULTIPLIER = 100
DEFAULT_OPTIONS_DIR = Path.home() / ".ai-os" / "robinhood-options"
DEFAULT_LEDGER = DEFAULT_OPTIONS_DIR / "paper_trades.jsonl"
DEFAULT_REPORT = DEFAULT_OPTIONS_DIR / "latest_morning_report.md"
PAPER_PAUSE_FILE = DEFAULT_OPTIONS_DIR / "PAPER_ENTRIES_PAUSED"
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
    max_quote_age_seconds: int = 120


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


def _quote_age_seconds(quote_time: str, now: datetime | None = None) -> float | None:
    if not quote_time:
        return None
    try:
        parsed = datetime.fromisoformat(quote_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return (current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()


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
    estimated_cost = round(quote.premium * (1 + policy.slippage_pct) + policy.fee_per_contract, 2)
    if estimated_cost > policy.max_premium:
        reasons.append("estimated_fill_above_premium_cap")
    if account.buying_power < estimated_cost:
        reasons.append("paper_buying_power_insufficient")
    if quote.source.startswith(("alpaca_", "robinhood_")):
        quote_age = _quote_age_seconds(quote.quote_time)
        if quote_age is None:
            reasons.append("quote_time_missing_or_invalid")
        elif quote_age < -5 or quote_age > policy.max_quote_age_seconds:
            reasons.append("quote_stale")
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
    persist: bool = True,
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
    if persist:
        append_ledger(record, ledger_path or DEFAULT_LEDGER)
    return record


def append_ledger(record: dict[str, Any], path: str | Path = DEFAULT_LEDGER) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return destination


def send_telegram_alert(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= getattr(response, "status", 0) < 300
    except Exception:
        return False


def notify_paper_event(record: dict[str, Any]) -> bool:
    status = record.get("status")
    if record.get("record_type") == "paper_position_monitor" and status not in {"closed", "error"}:
        return False
    basket = f"[{record.get('basket')}] " if record.get("basket") else ""
    if status == "filled_and_scored":
        quote = record.get("quote") or {}
        order = record.get("order") or {}
        exit_rule = record.get("exit_rule") or {"profit_target_pct": 0.30, "loss_limit_pct": -0.20}
        message = (
            f"{basket}PAPER OPTION OPENED: {quote.get('symbol')} {quote.get('expiration')} "
            f"{quote.get('strike')}C at ${order.get('fill_price')} per share. "
            f"Cost ${order.get('total_cost')}. Exit plan: "
            f"{exit_rule['profit_target_pct']:+.0%} / {exit_rule['loss_limit_pct']:.0%}."
        )
    elif status == "closed":
        message = (
            f"{basket}PAPER OPTION EXIT: {record.get('symbol')} action={record.get('action')} "
            f"P&L ${record.get('estimated_net_pnl')} ({record.get('pnl_pct', 0):.1%})."
        )
    elif status == "error":
        message = f"ROBINHOOD PAPER AGENT ERROR: {record.get('error')}"
    else:
        reasons = ", ".join(record.get("entry_rejections") or ["unknown_reason"])
        message = f"{basket}NO PAPER TRADE: {reasons}. The agent stayed in cash."
    return send_telegram_alert(message)


def latest_open_position(path: str | Path = DEFAULT_LEDGER) -> dict[str, Any] | None:
    ledger = Path(path)
    if not ledger.exists():
        return None
    position: dict[str, Any] | None = None
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("record_type") == "paper_options_cycle" and record.get("status") == "filled_and_scored":
            position = record
        elif record.get("record_type") == "paper_position_monitor" and record.get("status") == "closed":
            position = None
    return position


def monitor_paper_position(ledger_path: str | Path | None = None) -> dict[str, Any]:
    destination = Path(ledger_path or DEFAULT_LEDGER)
    position = latest_open_position(destination)
    if not position:
        return {"record_type": "paper_position_monitor", "status": "no_open_position", "live_trading_allowed": False}
    session = market_session()
    if not session.options_open:
        return {"record_type": "paper_position_monitor", "status": "market_closed", "live_trading_allowed": False}
    source = str((position.get("quote") or {}).get("source") or "")
    instrument_id = source.partition(":")[2] if source.startswith("robinhood_mcp:") else ""
    if not instrument_id:
        raise MarketDataUnavailable("missing_robinhood_instrument_id")
    adapter = RobinhoodMCPDataAdapter()
    payload = adapter._tool("get_option_quotes", {"instrument_ids": [instrument_id]})
    results = (payload.get("data") or {}).get("results") or []
    quote = (results[0].get("quote") or {}) if results else {}
    current_bid = _as_float(quote.get("bid_price"))
    if current_bid <= 0:
        raise MarketDataUnavailable("missing_monitor_bid")
    entry_price = _as_float((position.get("order") or {}).get("fill_price"))
    configured_rule = position.get("exit_rule") or {"profit_target_pct": 0.30, "loss_limit_pct": -0.20}
    exit_rule = ExitRule(
        _as_float(configured_rule.get("profit_target_pct"), 0.30),
        _as_float(configured_rule.get("loss_limit_pct"), -0.20),
    )
    score = score_exit(entry_price, current_bid, exit_rule)
    action = score["action"]
    opened_at = datetime.fromisoformat(str(position.get("created_at")).replace("Z", "+00:00")).astimezone(EASTERN)
    today = datetime.now(EASTERN).date()
    cursor = opened_at.date()
    business_days_held = 0
    while cursor < today:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            business_days_held += 1
    max_holding_days = _as_int(position.get("max_holding_days"), 0)
    if action == "hold" and max_holding_days and business_days_held >= max_holding_days:
        action = "exit_time_limit"
    record = {
        "record_type": "paper_position_monitor",
        "created_at": utc_now(),
        "mode": "paper_only",
        "live_trading_allowed": False,
        "status": "closed" if action.startswith("exit_") else "holding",
        "basket": position.get("basket"),
        "action": action,
        "instrument_id": instrument_id,
        "symbol": (position.get("quote") or {}).get("symbol"),
        "entry_price": entry_price,
        "current_bid": current_bid,
        "pnl_pct": score["pnl_pct"],
        "estimated_net_pnl": round((current_bid - entry_price) * CONTRACT_MULTIPLIER, 2),
        "quote_time": quote.get("updated_at"),
        "business_days_held": business_days_held,
        "max_holding_days": max_holding_days,
        "exit_rule": asdict(exit_rule),
    }
    append_ledger(record, destination)
    return record


ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
CODEX_CREDENTIALS_FILE = Path.home() / ".codex" / ".credentials.json"


class RobinhoodMCPDataAdapter:
    """Deterministic read-only Robinhood MCP market-data adapter."""

    allowed_tools = {
        "get_equity_quotes",
        "get_equity_historicals",
        "get_option_historicals",
        "get_earnings_results",
        "get_equity_news",
        "get_option_chains",
        "get_option_instruments",
        "get_option_quotes",
    }

    def __init__(self, credentials_path: str | Path = CODEX_CREDENTIALS_FILE, opener: Any | None = None):
        path = Path(credentials_path)
        if not path.exists():
            raise MarketDataUnavailable("missing_robinhood_mcp_credentials")
        credentials = json.loads(path.read_text(encoding="utf-8"))
        entry = next(
            (item for item in credentials.values() if item.get("server_name") == "robinhood-trading"),
            None,
        )
        if not entry or not entry.get("access_token"):
            raise MarketDataUnavailable("missing_robinhood_mcp_credentials")
        expires_at = _as_float(entry.get("expires_at"))
        if expires_at > 10**12:
            expires_at /= 1000
        if expires_at and datetime.now(timezone.utc).timestamp() >= expires_at:
            raise MarketDataUnavailable("robinhood_mcp_credentials_expired")
        self.access_token = entry["access_token"]
        self.opener = opener or urllib.request.urlopen
        self.directional_signals: dict[str, dict[str, Any]] = {}
        self.strategy_contexts: dict[str, dict[str, Any]] = {}
        self.strategy_matches: dict[str, list[str]] = {}

    @staticmethod
    def _sse_payload(text: str) -> dict[str, Any]:
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise MarketDataUnavailable("invalid_robinhood_mcp_response")

    def _tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.allowed_tools:
            raise MarketDataUnavailable("robinhood_mcp_tool_not_allowed")
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }).encode()
        request = urllib.request.Request(
            ROBINHOOD_MCP_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        with self.opener(request, timeout=30) as response:
            outer = self._sse_payload(response.read().decode("utf-8"))
        if outer.get("error"):
            raise MarketDataUnavailable(f"robinhood_mcp_error:{outer['error'].get('message', 'unknown')}")
        result = outer.get("result") or {}
        if result.get("isError"):
            raise MarketDataUnavailable("robinhood_mcp_tool_error")
        text = next((item.get("text") for item in result.get("content", []) if item.get("type") == "text"), None)
        if not text:
            raise MarketDataUnavailable("empty_robinhood_mcp_response")
        return json.loads(text)

    def _underlying_price(self, symbol: str) -> float:
        payload = self._tool("get_equity_quotes", {"symbols": [symbol]})
        results = (payload.get("data") or {}).get("results") or []
        if not results:
            raise MarketDataUnavailable("missing_underlying_quote")
        quote = results[0].get("quote") or {}
        choices = [
            (quote.get("venue_last_trade_time"), quote.get("last_trade_price")),
            (quote.get("venue_last_non_reg_trade_time"), quote.get("last_non_reg_trade_price")),
        ]
        choices = [(stamp, price) for stamp, price in choices if stamp and price]
        if not choices:
            raise MarketDataUnavailable("missing_underlying_price")
        current_price = _as_float(max(choices, key=lambda item: item[0])[1])
        previous_close = _as_float(quote.get("adjusted_previous_close") or quote.get("previous_close"))
        if previous_close <= 0:
            raise MarketDataUnavailable("missing_previous_close")
        change_pct = (current_price - previous_close) / previous_close
        self.directional_signals[symbol] = {
            "current_price": current_price,
            "previous_close": previous_close,
            "change_pct": round(change_pct, 6),
            "rule": "long_calls_require_0.15_to_4_percent_positive_move",
        }
        if change_pct < 0.0015:
            raise MarketDataUnavailable("underlying_momentum_too_weak_for_long_call")
        if change_pct > 0.04:
            raise MarketDataUnavailable("underlying_move_too_extended_for_entry")
        return current_price

    def _strategy_context(self, symbol: str, current_price: float) -> dict[str, Any]:
        if symbol in self.strategy_contexts:
            return self.strategy_contexts[symbol]
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=100)
        payload = self._tool("get_equity_historicals", {
            "symbols": [symbol],
            "start_time": start.isoformat().replace("+00:00", "Z"),
            "end_time": end.isoformat().replace("+00:00", "Z"),
            "interval": "day",
            "bounds": "regular",
            "adjustment_type": "split",
        })
        results = (payload.get("data") or {}).get("results") or []
        bars = (results[0].get("bars") or []) if results else []
        bars = [bar for bar in bars if not bar.get("interpolated")]
        today = datetime.now(EASTERN).date()
        completed = [bar for bar in bars if datetime.fromisoformat(str(bar["begins_at"]).replace("Z", "+00:00")).astimezone(EASTERN).date() < today]
        closes = [_as_float(bar.get("close_price")) for bar in completed]
        highs = [_as_float(bar.get("high_price")) for bar in completed]
        if len(closes) < 50:
            raise MarketDataUnavailable("insufficient_equity_history")
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50
        prior_high20 = max(highs[-20:])
        prior_low20 = min(closes[-20:])
        swing_range = prior_high20 - prior_low20
        fib_levels = {
            "23.6": round(prior_high20 - swing_range * 0.236, 4),
            "38.2": round(prior_high20 - swing_range * 0.382, 4),
            "50.0": round(prior_high20 - swing_range * 0.500, 4),
            "61.8": round(prior_high20 - swing_range * 0.618, 4),
            "78.6": round(prior_high20 - swing_range * 0.786, 4),
        }
        nearest_fib = min(fib_levels.items(), key=lambda item: abs(current_price - item[1]))
        fib_confluence = abs(current_price - nearest_fib[1]) / current_price <= 0.015
        breakout = current_price >= prior_high20 * 1.001
        established_uptrend = sma20 > sma50 and closes[-1] > sma50
        pullback = established_uptrend and sma20 * 0.98 <= current_price <= sma20 * 1.02
        context = {
            "sma20": round(sma20, 4),
            "sma50": round(sma50, 4),
            "prior_high20": round(prior_high20, 4),
            "prior_low20": round(prior_low20, 4),
            "fib_levels": fib_levels,
            "nearest_fib_level": nearest_fib[0],
            "nearest_fib_price": nearest_fib[1],
            "fib_confluence": fib_confluence,
            "breakout_continuation": breakout,
            "established_uptrend": established_uptrend,
            "pullback_continuation": pullback,
        }
        self.strategy_contexts[symbol] = context
        return context

    def long_call_candidates(self, underlying_symbol: str, policy: PaperPolicy | None = None) -> list[OptionQuote]:
        active_policy = policy or PaperPolicy()
        symbol = underlying_symbol.upper()
        chain_payload = self._tool("get_option_chains", {"underlying_symbol": symbol})
        chains = (chain_payload.get("data") or {}).get("chains") or []
        if not chains:
            raise MarketDataUnavailable("empty_option_chain")
        today = datetime.now(EASTERN).date()
        expirations = []
        for value in chains[0].get("expiration_dates") or []:
            try:
                expiry = datetime.fromisoformat(value).date()
            except ValueError:
                continue
            dte = (expiry - today).days
            if active_policy.min_dte <= dte <= active_policy.max_dte:
                expirations.append(value)
        if not expirations:
            raise MarketDataUnavailable("no_expiration_in_primary_window")
        underlying_price = self._underlying_price(symbol)
        strategy_context = self._strategy_context(symbol, underlying_price)
        instruments: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(30):
            args: dict[str, Any] = {
                "chain_symbol": symbol,
                "expiration_dates": ",".join(expirations),
                "type": "call",
                "tradability": "tradable",
            }
            if cursor:
                args["cursor"] = cursor
            payload = self._tool("get_option_instruments", args)
            data = payload.get("data") or {}
            instruments.extend(data.get("instruments") or [])
            cursor = data.get("next")
            if not cursor:
                break
        eligible = [
            item for item in instruments
            if underlying_price <= _as_float(item.get("strike_price")) <= underlying_price * 1.12
        ]
        quotes_by_id: dict[str, dict[str, Any]] = {}
        for start in range(0, len(eligible), 100):
            ids = [item["id"] for item in eligible[start:start + 100]]
            payload = self._tool("get_option_quotes", {"instrument_ids": ids})
            for result in (payload.get("data") or {}).get("results") or []:
                quote_data = result.get("quote") or {}
                if quote_data.get("instrument_id"):
                    quotes_by_id[quote_data["instrument_id"]] = quote_data
        candidates: list[OptionQuote] = []
        for item in eligible:
            data = quotes_by_id.get(item["id"]) or {}
            expiration = str(item.get("expiration_date") or "")
            try:
                dte = (datetime.fromisoformat(expiration).date() - today).days
            except ValueError:
                continue
            bid = _as_float(data.get("bid_price"))
            ask = _as_float(data.get("ask_price"))
            if not bid or not ask:
                continue
            quote = OptionQuote(
                symbol=symbol,
                underlying_price=underlying_price,
                strike=_as_float(item.get("strike_price")),
                expiration=expiration,
                dte=dte,
                bid=bid,
                ask=ask,
                last=_as_float(data.get("mark_price"), (bid + ask) / 2),
                volume=_as_int(data.get("volume")),
                open_interest=_as_int(data.get("open_interest")),
                implied_volatility=_as_float(data.get("implied_volatility")) if data.get("implied_volatility") else None,
                delta=_as_float(data.get("delta")) if data.get("delta") else None,
                gamma=_as_float(data.get("gamma")) if data.get("gamma") else None,
                theta=_as_float(data.get("theta")) if data.get("theta") else None,
                vega=_as_float(data.get("vega")) if data.get("vega") else None,
                quote_time=str(data.get("updated_at") or ""),
                underlying_volume=0,
                source=f"robinhood_mcp:{item['id']}",
            )
            spread_pct = quote.spread / quote.mid if quote.mid else 1.0
            volume_oi_ratio = quote.volume / quote.open_interest if quote.open_interest else 0.0
            controlled_iv = quote.implied_volatility is not None and 0.15 <= quote.implied_volatility <= 0.60
            balanced_delta = quote.delta is not None and 0.20 <= quote.delta <= 0.50
            tight_execution = spread_pct <= 0.10
            matches: list[str] = []
            if quote.volume >= 500 and volume_oi_ratio >= 0.50 and balanced_delta and tight_execution and controlled_iv:
                matches.append("dean_ahrens_unusual_flow_proxy")
            if strategy_context["breakout_continuation"] and balanced_delta and tight_execution and controlled_iv:
                matches.append("breakout_continuation")
            if strategy_context["pullback_continuation"] and balanced_delta and tight_execution and controlled_iv:
                matches.append("pullback_continuation_uptrend")
            if matches and not validate_entry(quote, PaperAccount(buying_power=10_000, settled_cash=10_000), active_policy):
                self.strategy_matches[item["id"]] = matches
                candidates.append(quote)
        if not candidates:
            raise MarketDataUnavailable("no_contract_passed_policy_filters")
        return candidates


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

    def long_call_candidates(
        self,
        underlying_symbol: str,
        policy: PaperPolicy | None = None,
        feed: str = "opra",
    ) -> list[OptionQuote]:
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
        return candidates

    def select_long_call(
        self,
        underlying_symbol: str,
        policy: PaperPolicy | None = None,
        feed: str = "opra",
    ) -> OptionQuote:
        return rank_candidates(self.long_call_candidates(underlying_symbol, policy, feed))[0]["quote"]


def due_diligence_score(quote: OptionQuote, policy: PaperPolicy | None = None) -> dict[str, Any]:
    active_policy = policy or PaperPolicy()
    spread_pct = quote.spread / quote.mid if quote.mid else 1.0
    premium_center = (active_policy.target_min_premium + active_policy.target_max_premium) / 2
    budget_fit = max(0.0, 1.0 - abs(quote.premium - premium_center) / premium_center)
    spread_score = max(0.0, 1.0 - spread_pct / active_policy.max_spread_pct)
    volume_score = min(1.0, quote.volume / 1000)
    oi_score = min(1.0, quote.open_interest / 5000)
    dte_center = (active_policy.min_dte + active_policy.max_dte) / 2
    dte_score = max(0.0, 1.0 - abs(quote.dte - dte_center) / dte_center)
    delta = abs(quote.delta or 0.0)
    delta_score = max(0.0, 1.0 - abs(delta - 0.35) / 0.35) if delta else 0.5
    score = round(
        30 * budget_fit + 25 * spread_score + 20 * volume_score + 15 * oi_score + 5 * dte_score + 5 * delta_score,
        2,
    )
    return {
        "symbol": quote.symbol,
        "score": score,
        "premium": quote.premium,
        "spread_pct": round(spread_pct, 4),
        "volume": quote.volume,
        "open_interest": quote.open_interest,
        "dte": quote.dte,
        "delta": quote.delta,
        "reasons": [
            "premium closest to target budget center",
            "tight spread preferred",
            "higher option volume/open interest preferred",
            "DTE near middle of 7-21 day window preferred",
            "delta near 0.35 preferred for long-call balance",
        ],
    }


def rank_candidates(candidates: list[OptionQuote], policy: PaperPolicy | None = None) -> list[dict[str, Any]]:
    ranked = [{"quote": item, "due_diligence": due_diligence_score(item, policy)} for item in candidates]
    ranked.sort(key=lambda item: item["due_diligence"]["score"], reverse=True)
    return ranked


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
        "This strategy trades premium only and exits by selling the option contract."
    )


def run_alpaca_cycle(
    symbol: str = "SPY",
    ledger_path: str | Path | None = None,
    adapter_kind: str = "alpaca",
) -> dict[str, Any]:
    session = market_session()
    symbols = _normalize_symbols(symbol)
    active_ledger = Path(ledger_path or DEFAULT_LEDGER)
    if PAPER_PAUSE_FILE.exists():
        record = {
            "record_type": "paper_options_cycle", "created_at": utc_now(), "mode": "paper_only",
            "live_trading_allowed": False, "status": "rejected",
            "entry_rejections": ["paper_entries_paused_by_owner"], "symbols_checked": symbols,
            "quote": None, "order": None, "exit_scores": [],
            "morning_summary": "New paper entries are paused by the authorized owner.",
        }
        append_ledger(record, active_ledger)
        return record
    not_before = os.getenv("AI_OS_OPTIONS_NOT_BEFORE", "").strip()
    if not_before and datetime.now(EASTERN).date() < datetime.fromisoformat(not_before).date():
        record = {
            "record_type": "paper_options_cycle",
            "created_at": utc_now(),
            "mode": "paper_only",
            "live_trading_allowed": False,
            "status": "rejected",
            "entry_rejections": ["paper_entry_not_before_date"],
            "symbols_checked": symbols,
            "quote": None,
            "order": None,
            "exit_scores": [],
            "morning_summary": f"Paper entry is locked until {not_before}.",
        }
        append_ledger(record, active_ledger)
        return record
    if latest_open_position(active_ledger):
        record = {
            "record_type": "paper_options_cycle",
            "created_at": utc_now(),
            "mode": "paper_only",
            "live_trading_allowed": False,
            "status": "rejected",
            "entry_rejections": ["max_concurrent_positions_reached"],
            "symbols_checked": symbols,
            "quote": None,
            "order": None,
            "exit_scores": [],
            "morning_summary": "No new paper option was opened because one paper position is already active.",
        }
        append_ledger(record, active_ledger)
        return record
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
    try:
        if adapter_kind == "robinhood":
            adapter = RobinhoodMCPDataAdapter()
        elif adapter_kind == "alpaca":
            adapter = AlpacaOptionsDataAdapter()
        else:
            raise MarketDataUnavailable("unsupported_market_data_adapter")
    except MarketDataUnavailable as exc:
        record = {
            "record_type": "paper_options_cycle",
            "created_at": utc_now(),
            "mode": "paper_only_real_data_blocked",
            "live_trading_allowed": False,
            "status": "rejected",
            "entry_rejections": [str(exc)],
            "market_session": asdict(session),
            "symbols_checked": symbols,
            "quote": None,
            "order": None,
            "exit_scores": [],
            "morning_summary": "No paper option was bought because the real market-data adapter was unavailable.",
        }
        append_ledger(record, ledger_path or DEFAULT_LEDGER)
        return record
    rejected: list[dict[str, str]] = []
    candidates: list[OptionQuote] = []
    for item in symbols:
        try:
            candidates.extend(adapter.long_call_candidates(item))
        except MarketDataUnavailable as exc:
            rejected.append({"symbol": item, "reason": str(exc)})
    ranked = rank_candidates(candidates)
    selected_quote = ranked[0]["quote"] if ranked else None
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
    record = paper_trade_cycle(selected_quote, account, ledger_path=ledger_path, persist=False)
    record["market_session"] = asdict(session)
    record["symbols_checked"] = symbols
    record["rejected_symbols"] = rejected
    record["due_diligence"] = ranked[0]["due_diligence"]
    record["directional_signal"] = getattr(adapter, "directional_signals", {}).get(selected_quote.symbol)
    record["strategy_context"] = getattr(adapter, "strategy_contexts", {}).get(selected_quote.symbol)
    instrument_id = selected_quote.source.partition(":")[2]
    record["strategy_matches"] = getattr(adapter, "strategy_matches", {}).get(instrument_id, [])
    record["candidate_rankings"] = [item["due_diligence"] for item in ranked[:5]]
    record["morning_summary"] = "One paper long call opened from the candidate watchlist because it ranked highest after due diligence and fit the $100-$250 total premium budget."
    record["sell_plan"] = _best_exit_plan(record)
    append_ledger(record, ledger_path or DEFAULT_LEDGER)
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
    if record.get("strategy_matches"):
        lines.extend(["", "MATCHED STRATEGIES", *[f"- {item}" for item in record["strategy_matches"]]])
    if record.get("strategy_context"):
        context = record["strategy_context"]
        lines.extend([
            f"20/50-day averages: {context['sma20']:.2f} / {context['sma50']:.2f}",
            f"Prior 20-day high: {context['prior_high20']:.2f}",
            f"Nearest Fibonacci retracement: {context.get('nearest_fib_level', 'n/a')}% at " + "$" + f"{context.get('nearest_fib_price', 0):.2f}",
            f"Fibonacci confluence: {'yes' if context.get('fib_confluence') else 'no'} (experimental evidence only)",
        ])
    if record.get("due_diligence"):
        diligence = record["due_diligence"]
        lines.extend([
            "",
            "DUE DILIGENCE",
            f"Score: {diligence['score']}/100",
            f"Spread: {diligence['spread_pct']:.2%}",
            f"Volume/OI: {diligence['volume']} / {diligence['open_interest']}",
            f"Delta/DTE: {diligence['delta']} / {diligence['dte']}",
        ])
    if record.get("candidate_rankings"):
        lines.extend(["", "TOP CANDIDATES"])
        for item in record["candidate_rankings"]:
            lines.append(f"- {item['symbol']}: score {item['score']}, premium ${item['premium']:.2f}, spread {item['spread_pct']:.2%}, DTE {item['dte']}")
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
    lines.extend(["", "POSITION POLICY", "Trade premium only; close by selling the option contract. Exercise is disabled."])
    return "\n".join(lines)
