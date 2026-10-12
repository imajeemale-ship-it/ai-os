#!/usr/bin/env python3
"""Continuously monitor Telegram sources and deliver deduplicated signal alerts.

The app is read-only with respect to Telegram sources and has no broker/exchange
execution code. It reuses the existing Supervizor parser and Telethon session.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import math
import os
import re
import sqlite3
import statistics
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPERVIZOR_ROOT = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata"
DEFAULT_DB = Path.home() / ".ai-os" / "signal_watch.db"
DEFAULT_LOCK = Path.home() / ".ai-os" / "signal_watch.lock"
CANDIDATE_RE = re.compile(
    r"\b(Long|Short|Entry|Targets?|TP|Stop\s*Loss|Stoploss|DCA|leverage|buy|sell)\b|"
    r"#[A-Z][A-Z0-9]{1,14}\b",
    re.IGNORECASE,
)
TICKER_RE = re.compile(r"#\s*([A-Z][A-Z0-9]{1,14})(?![A-Z0-9])", re.IGNORECASE)
PAIR_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,14})\s*[/_-]\s*(?:USDT|USD|USDC|BTC|ETH)\b", re.IGNORECASE)
DOLLAR_TICKER_RE = re.compile(r"\$([A-Z][A-Z0-9]{1,14})\b")
BARE_TICKER_RE = re.compile(r"^\s*([A-Z][A-Z0-9]{1,14})(?:USDT|USD|USDC|BTC|ETH)?\s+(?:LONG|SHORT|BUY|SELL)\b", re.IGNORECASE)
MAX_ALERT_CHARS = 3800
DEFAULT_CONSENSUS_WINDOW_MINUTES = 360
DEFAULT_MARKET_CONTEXT_CACHE = Path.home() / ".ai-os" / "market_context.json"
MARKET_CONTEXT_CACHE_TTL_SECONDS = 300

SOURCE_POLICIES = {
    "wallstreet queen official": {
        "rank": "Tier 1",
        "bias": "monitor",
        "plan": "take partial profit into the first strong move; do not wait for screenshots",
        "target_pct": 3.0,
        "trail_pct": 2.0,
        "timeout_hours": 12,
    },
    "crypto best futures signals": {
        "rank": "Tier 2",
        "bias": "futures-risk",
        "plan": "fast scalp only; partial profits early and hard timeout",
        "target_pct": 3.0,
        "trail_pct": 2.0,
        "timeout_hours": 6,
    },
    "technical crypto analyst": {
        "rank": "Tier 3",
        "bias": "selective",
        "plan": "use only clean entries with stop loss and target; no chasing",
        "target_pct": 3.0,
        "trail_pct": 2.0,
        "timeout_hours": 12,
    },
    "whales crypto guide": {
        "rank": "Tier 4",
        "bias": "noisy",
        "plan": "quick-take setup; skip if the move already ran",
        "target_pct": 3.0,
        "trail_pct": 1.5,
        "timeout_hours": 6,
    },
    "the bull": {
        "rank": "Tier 5",
        "bias": "watch-only",
        "plan": "paper monitor until newer data improves",
        "target_pct": 3.0,
        "trail_pct": 1.5,
        "timeout_hours": 6,
    },
}

DEFAULT_TRADE_POLICY = {
    "rank": "Unranked",
    "bias": "manual-review",
    "plan": "manual review only; require entry, target, invalidation, and current price check",
    "target_pct": 3.0,
    "trail_pct": 2.0,
    "timeout_hours": 8,
}
OUTCOME_RE = re.compile(r"\b(?:TP\s*\d+\s*(?:hit|reached|✅|🎯)|profit\s*[:=]|closed\s+(?:in|with)\s+(?:profit|loss))\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def unavailable_market_context(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "as_of": utc_now(),
        "btc_trend": None,
        "btc_above_ema200": None,
        "btc_24h_change_pct": None,
        "market_volatility": None,
        "market_volatility_pct": None,
        "fear_greed_index": None,
        "fear_greed_label": None,
        "trading_session": None,
        "day_of_week": None,
    }


def _market_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "AI-OS Signal Watch market context"})
    with urllib.request.urlopen(request, timeout=8, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def _trading_session(timestamp: datetime) -> str:
    hour = timestamp.astimezone(timezone.utc).hour
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 21:
        return "New York"
    return "Asia"


def fetch_market_context(
    cache_path: Path = DEFAULT_MARKET_CONTEXT_CACHE,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch and cache all required market inputs, failing closed on any gap."""
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    cache_path = Path(cache_path).expanduser()
    try:
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_at = _timestamp(cached.get("as_of")) if isinstance(cached, dict) else None
            if cached.get("available") is True and cached_at and (reference - cached_at).total_seconds() <= MARKET_CONTEXT_CACHE_TTL_SECONDS:
                cached["cache_source"] = "local_cache"
                return cached
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    try:
        candles = _market_json("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600")
        closes = sorted((float(row[0]), float(row[4])) for row in candles if len(row) >= 5)
        prices = [value for _, value in closes]
        if len(prices) < 201:
            return unavailable_market_context("insufficient BTC candle history")
        current = prices[-1]
        ema200 = _ema(prices[-201:], 200)
        change_24h = (current / prices[-25] - 1) * 100
        hourly_changes = [(prices[index] / prices[index - 1] - 1) * 100 for index in range(max(1, len(prices) - 24), len(prices))]
        volatility_pct = statistics.pstdev(hourly_changes) * math.sqrt(24) if hourly_changes else None
        if volatility_pct is None:
            return unavailable_market_context("BTC volatility unavailable")
        volatility = "low" if volatility_pct < 2 else "high" if volatility_pct >= 5 else "medium"
        fear_greed = _market_json("https://api.alternative.me/fng/?limit=1")
        item = fear_greed.get("data", [])[0]
        fear_greed_index = int(item["value"])
        timestamp = reference.astimezone(timezone.utc)
        context = {
            "available": True,
            "as_of": _iso_timestamp(timestamp),
            "cache_source": "live",
            "btc_trend": "up" if current > _ema(prices[-25:], 24) and change_24h > 0 else "down" if current < _ema(prices[-25:], 24) and change_24h < 0 else "sideways",
            "btc_price": round(current, 8),
            "btc_ema200": round(ema200, 8),
            "btc_above_ema200": current >= ema200,
            "btc_24h_change_pct": round(change_24h, 4),
            "market_volatility": volatility,
            "market_volatility_pct": round(volatility_pct, 4),
            "fear_greed_index": fear_greed_index,
            "fear_greed_label": str(item.get("value_classification") or "Unknown"),
            "trading_session": _trading_session(timestamp),
            "day_of_week": timestamp.strftime("%A"),
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return context
    except (OSError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        return unavailable_market_context("market data unavailable")


def score_market_context(parsed: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score market conditions for this signal; unavailable context scores zero."""
    if not context.get("available"):
        return {"market_context_score": 0.0, "reasons": [], "warnings": [
            f"Market context unavailable; conviction fail-closed ({context.get('reason', 'unknown reason')})"
        ]}
    direction = _direction(parsed.get("side"))
    points = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    trend = context["btc_trend"]
    if direction:
        aligned = (direction == "long" and trend == "up") or (direction == "short" and trend == "down")
        trend_points = 25.0 if aligned else 8.0 if trend == "sideways" else 0.0
    else:
        trend_points = 12.5
        warnings.append("Market trend cannot be directional without a valid signal side")
    points += trend_points
    reasons.append(f"BTC trend {trend}: {trend_points:.1f}/25")
    above = bool(context["btc_above_ema200"])
    ema_aligned = (direction == "long" and above) or (direction == "short" and not above)
    ema_points = 15.0 if direction and ema_aligned else 7.5 if not direction else 0.0
    points += ema_points
    reasons.append(f"BTC {'above' if above else 'below'} 200 EMA: {ema_points:.1f}/15")
    change = float(context["btc_24h_change_pct"])
    if direction == "short":
        change_points = max(0.0, min(15.0, 7.5 - change * 1.5))
    elif direction == "long":
        change_points = max(0.0, min(15.0, 7.5 + change * 1.5))
    else:
        change_points = 7.5
    points += change_points
    reasons.append(f"BTC 24h change {change:+.2f}%: {change_points:.1f}/15")
    volatility = context["market_volatility"]
    volatility_points = {"low": 12.0, "medium": 10.0, "high": 3.0}.get(volatility, 0.0)
    points += volatility_points
    reasons.append(f"Market volatility {volatility}: {volatility_points:.1f}/15")
    fear = int(context["fear_greed_index"])
    fear_points = 15.0 - min(9.0, abs(fear - 50) / 50 * 9)
    points += fear_points
    reasons.append(f"Fear & Greed {fear} ({context['fear_greed_label']}): {fear_points:.1f}/15")
    session_points = 10.0 if context["trading_session"] in {"London", "New York"} else 7.0
    points += session_points
    reasons.append(f"Trading session {context['trading_session']}: {session_points:.1f}/10")
    day_points = 5.0 if context["day_of_week"] not in {"Saturday", "Sunday"} else 2.0
    points += day_points
    reasons.append(f"Day {context['day_of_week']}: {day_points:.1f}/5")
    return {"market_context_score": round(max(0.0, min(100.0, points)), 2), "reasons": reasons, "warnings": warnings}


def acquire_process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise RuntimeError(f"Signal Watch is already running; lock held at {path}") from error
    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def is_signal_candidate(text: str) -> bool:
    if not text or not CANDIDATE_RE.search(text) or OUTCOME_RE.search(text):
        return False
    lower = text.casefold()
    teaser = any(phrase in lower for phrase in ("in a few minutes", "within the next", "will be posting", "coming soon", "stay tuned"))
    concrete = bool(TICKER_RE.search(text) or PAIR_RE.search(text) or DOLLAR_TICKER_RE.search(text) or BARE_TICKER_RE.search(text))
    has_setup = bool(re.search(r"\b(entry|accumulation zone|current price|targets?|stop ?loss|stoploss)\b", text, re.I))
    has_direction = bool(re.search(r"\b(long|short|buy|sell)\b", text, re.I))
    return not teaser and (concrete or (has_setup and has_direction))


def load_parser(root: Path):
    """Load the established local parser by file path without changing sys.path globally."""
    import importlib.util

    path = root / "supervizor_signal_parser.py"
    if not path.is_file():
        raise FileNotFoundError(f"Supervizor parser not found: {path}")
    spec = importlib.util.spec_from_file_location("signal_watch_supervizor_parser", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.parse_signal


@dataclass(frozen=True)
class Signal:
    source: str
    message_id: int
    sent_at: str
    raw_text: str
    parsed: dict[str, Any]
    dedupe_key: str
    url: str | None


class SignalStore:
    def __init__(self, path: Path, consensus_window_minutes: int = DEFAULT_CONSENSUS_WINDOW_MINUTES,
                 market_context_provider=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        if consensus_window_minutes <= 0:
            raise ValueError("Consensus window must be positive")
        self.consensus_window_minutes = consensus_window_minutes
        self.market_context_provider = market_context_provider
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    ticker TEXT,
                    pair TEXT,
                    side TEXT,
                    entry_json TEXT,
                    targets_json TEXT NOT NULL,
                    stop_loss REAL,
                    parsed_json TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    source_url TEXT,
                    alert_status TEXT NOT NULL DEFAULT 'pending',
                    alerted_at TEXT,
                    UNIQUE(source, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker, sent_at);
                CREATE INDEX IF NOT EXISTS idx_signals_alert ON signals(alert_status, received_at);
                CREATE TABLE IF NOT EXISTS consensus_groups (
                    id INTEGER PRIMARY KEY,
                    ticker TEXT,
                    first_seen TEXT NOT NULL,
                    latest_seen TEXT NOT NULL,
                    window_minutes INTEGER NOT NULL,
                    number_of_channels INTEGER NOT NULL DEFAULT 0,
                    agreeing_channels_json TEXT NOT NULL DEFAULT '[]',
                    disagreeing_channels_json TEXT NOT NULL DEFAULT '[]',
                    consensus_score REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_consensus_groups_ticker ON consensus_groups(ticker, latest_seen);
                CREATE TABLE IF NOT EXISTS watch_state (
                    source TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
            """)
            self._ensure_signal_columns(db)

    @staticmethod
    def _ensure_signal_columns(db: sqlite3.Connection) -> None:
        columns = {row[1] for row in db.execute("PRAGMA table_info(signals)")}
        additions = {
            "conviction_score": "REAL",
            "confidence_level": "TEXT",
            "conviction_reasons_json": "TEXT",
            "conviction_warnings_json": "TEXT",
            "consensus_group_id": "INTEGER",
            "number_of_channels": "INTEGER",
            "agreeing_channels_json": "TEXT",
            "disagreeing_channels_json": "TEXT",
            "consensus_score": "REAL",
            "consensus_first_seen": "TEXT",
            "consensus_latest_seen": "TEXT",
            "market_context_json": "TEXT",
            "decision": "TEXT",
            "overall_score": "REAL",
            "position_size_recommendation": "TEXT",
            "maximum_risk_percent": "REAL",
            "decision_explanation": "TEXT",
            "blocking_reasons_json": "TEXT",
            "supporting_reasons_json": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE signals ADD COLUMN {name} {definition}")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def ticker(parsed: dict[str, Any], text: str) -> str | None:
        pair = parsed.get("pair") or parsed.get("detected_pair")
        if isinstance(pair, str) and pair.strip():
            return pair.split("/")[0].upper()
        symbol = parsed.get("asset_symbol")
        if isinstance(symbol, str) and symbol.strip():
            return symbol.strip().upper()
        match = TICKER_RE.search(text) or PAIR_RE.search(text) or DOLLAR_TICKER_RE.search(text) or BARE_TICKER_RE.search(text)
        return match.group(1).upper() if match else None

    def add(self, signal: Signal) -> bool:
        parsed = signal.parsed
        ticker = self.ticker(parsed, signal.raw_text)
        pair = parsed.get("pair") or parsed.get("detected_pair")
        entry = parsed.get("entry")
        if entry is None and parsed.get("entry_price") is not None:
            entry = {"low": parsed.get("entry_price"), "high": parsed.get("entry_price")}
        targets = parsed.get("targets") or []
        stop_loss = parsed.get("stop_loss")
        with self.connect() as db:
            try:
                market_context = self.market_context_provider() if self.market_context_provider else unavailable_market_context("market context provider not configured")
            except Exception as error:
                market_context = unavailable_market_context(f"market context provider failed: {error.__class__.__name__}")
            cursor = db.execute(
                """INSERT OR IGNORE INTO signals
                (source,message_id,sent_at,received_at,ticker,pair,side,entry_json,
                 targets_json,stop_loss,parsed_json,raw_text,dedupe_key,source_url,
                 conviction_score,confidence_level,conviction_reasons_json,conviction_warnings_json,
                 number_of_channels,agreeing_channels_json,disagreeing_channels_json,
                 consensus_score,consensus_first_seen,consensus_latest_seen,market_context_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (signal.source, signal.message_id, signal.sent_at, utc_now(), ticker,
                 pair, parsed.get("side"), json.dumps(entry), json.dumps(targets),
                 stop_loss, json.dumps(parsed, ensure_ascii=False, sort_keys=True),
                 signal.raw_text, signal.dedupe_key, signal.url, None, None, None, None,
                 None, None, None, None, None, None,
                 json.dumps(market_context, ensure_ascii=False)),
            )
            if cursor.rowcount != 1:
                return False
            signal_id = int(cursor.lastrowid)
            consensus = update_consensus_group(
                db, signal_id, ticker, signal.sent_at, parsed.get("side"), signal.source,
                self.consensus_window_minutes,
            )
            rows = db.execute(
                "SELECT * FROM signals WHERE consensus_group_id=? ORDER BY id",
                (consensus["group_id"],),
            ).fetchall()
            for row in rows:
                row_parsed = json.loads(row["parsed_json"] or "{}")
                row_entry = json.loads(row["entry_json"]) if row["entry_json"] else None
                row_targets = json.loads(row["targets_json"] or "[]")
                row_consensus = consensus_for_signal(db, row, self.consensus_window_minutes)
                row_context = json.loads(row["market_context_json"] or "{}")
                row_conviction = calculate_conviction(
                    db, row["source"], row_parsed, row["sent_at"], row["ticker"],
                    row_entry, row_targets, row["stop_loss"], consensus=row_consensus,
                    market_context=row_context,
                )
                row_context["market_context_score"] = row_conviction["market_context_score"]
                decision = calculate_decision(
                    db, row["source"], row_parsed, row["sent_at"], row["ticker"],
                    row_entry, row_targets, row["stop_loss"], row_conviction,
                    row_consensus, row_context,
                )
                db.execute(
                    """UPDATE signals SET conviction_score=?, confidence_level=?,
                    conviction_reasons_json=?, conviction_warnings_json=?,market_context_json=?,
                    decision=?,overall_score=?,position_size_recommendation=?,maximum_risk_percent=?,
                    decision_explanation=?,blocking_reasons_json=?,supporting_reasons_json=? WHERE id=?""",
                    (row_conviction["conviction_score"], row_conviction["confidence_level"],
                     json.dumps(row_conviction["reasons"], ensure_ascii=False),
                     json.dumps(row_conviction["warnings"], ensure_ascii=False),
                     json.dumps(row_context, ensure_ascii=False), decision["decision"],
                     decision["overall_score"], decision["position_size_recommendation"],
                     decision["maximum_risk_percent"], decision["explanation"],
                     json.dumps(decision["blocking_reasons"], ensure_ascii=False),
                     json.dumps(decision["supporting_reasons"], ensure_ascii=False), row["id"]),
                )
            return True

    def pending(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM signals WHERE alert_status='pending' ORDER BY received_at LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_alert(self, row_id: int, status: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE signals SET alert_status=?, alerted_at=? WHERE id=?",
                (status, utc_now() if status == "sent" else None, row_id),
            )

    def mark_by_source_message(self, source: str, message_id: int, status: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE signals SET alert_status=? WHERE source=? AND message_id=?", (status, source, message_id))

    def set_last_id(self, source: str, message_id: int) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO watch_state(source,last_message_id,updated_at) VALUES(?,?,?)
                ON CONFLICT(source) DO UPDATE SET
                last_message_id=MAX(last_message_id, excluded.last_message_id),
                updated_at=excluded.updated_at""",
                (source, message_id, utc_now()),
            )

    def get_last_id(self, source: str) -> int:
        with self.connect() as db:
            row = db.execute("SELECT last_message_id FROM watch_state WHERE source=?", (source,)).fetchone()
        return int(row[0]) if row else 0


def parse_signal(parse_fn, source: str, message_id: int, sent_at: str, text: str, url: str | None) -> Signal:
    parsed = parse_fn(text, source=source, message_id=message_id, timestamp=sent_at)
    canonical = json.dumps(
        {"text": " ".join(text.casefold().split())},
        sort_keys=True,
    )
    dedupe = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return Signal(source, int(message_id), sent_at, text, parsed, dedupe, url)


def source_policy(source: str) -> dict[str, Any]:
    key = " ".join(re.sub(r"[^a-z0-9 ]+", " ", (source or "").casefold()).split())
    for name, policy in SOURCE_POLICIES.items():
        normalized = " ".join(re.sub(r"[^a-z0-9 ]+", " ", name).split())
        if key == normalized or key.startswith(normalized) or normalized.startswith(key):
            return policy
    return DEFAULT_TRADE_POLICY


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _entry_price(entry: Any) -> float | None:
    if isinstance(entry, dict):
        values = [_number(entry.get(key)) for key in ("low", "high")]
        values = [value for value in values if value is not None]
        return sum(values) / len(values) if values else None
    return _number(entry)


def _direction(value: Any) -> str | None:
    side = str(value or "").casefold()
    if side in {"buy", "long"}:
        return "long"
    if side in {"sell", "short"}:
        return "short"
    return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _historical_channel_stats(db: sqlite3.Connection, source: str) -> dict[str, float | int]:
    empty: dict[str, float | int] = {
        "closed": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
        "profit_factor": 0.0, "average_return": 0.0,
    }
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_positions'"
    ).fetchone()
    if not exists:
        return empty
    rows = db.execute(
        "SELECT realized_pnl_pct FROM paper_positions WHERE source=? AND status='closed'",
        (source,),
    ).fetchall()
    returns = [_number(row[0]) or 0.0 for row in rows]
    if not returns:
        return empty
    wins = sum(value > 0 for value in returns)
    losses = sum(value < 0 for value in returns)
    gross_profit = sum(value for value in returns if value > 0)
    gross_loss = sum(-value for value in returns if value < 0)
    return {
        "closed": len(returns),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / (wins + losses) * 100 if wins + losses else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (2.0 if gross_profit else 0.0),
        "average_return": sum(returns) / len(returns),
    }


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _consensus_result(
    group_id: int,
    ticker: str | None,
    members: list[sqlite3.Row],
    anchor_side: Any,
    window_minutes: int,
) -> dict[str, Any]:
    timestamps = [_timestamp(row["sent_at"]) for row in members]
    timestamps = [value for value in timestamps if value is not None]
    first_seen = _iso_timestamp(min(timestamps)) if timestamps else None
    latest_seen = _iso_timestamp(max(timestamps)) if timestamps else None
    agreeing: set[str] = set()
    disagreeing: set[str] = set()
    direction = _direction(anchor_side)
    channels: set[str] = set()
    for row in members:
        source = str(row["source"] or "Unknown")
        channels.add(source)
        other_direction = _direction(row["side"])
        if direction and other_direction == direction:
            agreeing.add(source)
        elif direction and other_direction and other_direction != direction:
            disagreeing.add(source)
    known_channels = agreeing | disagreeing
    if not ticker or not direction or not known_channels:
        score = 0.0
    elif len(known_channels) == 1:
        score = 50.0
    else:
        score = round(len(agreeing) / len(known_channels) * 100, 2)
    return {
        "group_id": group_id,
        "number_of_channels": len(channels),
        "agreeing_channels": sorted(agreeing),
        "disagreeing_channels": sorted(disagreeing),
        "consensus_score": score,
        "first_seen": first_seen,
        "latest_seen": latest_seen,
        "window_minutes": window_minutes,
    }


def consensus_for_values(
    db: sqlite3.Connection,
    ticker: str | None,
    sent_at: str,
    side: Any,
    window_minutes: int,
) -> dict[str, Any]:
    anchor = _timestamp(sent_at)
    if not ticker or anchor is None:
        return _consensus_result(0, ticker, [], side, window_minutes)
    rows = db.execute("SELECT * FROM signals WHERE ticker=? ORDER BY sent_at, id", (ticker,)).fetchall()
    members = []
    for row in rows:
        timestamp = _timestamp(row["sent_at"])
        if timestamp is not None and abs((anchor - timestamp).total_seconds()) <= window_minutes * 60:
            members.append(row)
    return _consensus_result(0, ticker, members, side, window_minutes)


def update_consensus_group(
    db: sqlite3.Connection,
    signal_id: int,
    ticker: str | None,
    sent_at: str,
    side: Any,
    source: str,
    window_minutes: int,
) -> dict[str, Any]:
    """Assign a signal to a time-bounded ticker group and refresh its members."""
    anchor = _timestamp(sent_at)
    candidate_ids: set[int] = set()
    rows = []
    if ticker and anchor is not None:
        rows = db.execute(
            "SELECT * FROM signals WHERE ticker=? ORDER BY sent_at, id", (ticker,)
        ).fetchall()
        for row in rows:
            timestamp = _timestamp(row["sent_at"])
            if timestamp is not None and abs((anchor - timestamp).total_seconds()) <= window_minutes * 60:
                if row["consensus_group_id"] is not None:
                    candidate_ids.add(int(row["consensus_group_id"]))
        if candidate_ids:
            group_id = min(candidate_ids)
            placeholders = ",".join("?" for _ in candidate_ids)
            db.execute(
                f"UPDATE signals SET consensus_group_id=? WHERE consensus_group_id IN ({placeholders})",
                (group_id, *candidate_ids),
            )
        else:
            cursor = db.execute(
                "INSERT INTO consensus_groups(ticker,first_seen,latest_seen,window_minutes) VALUES(?,?,?,?)",
                (ticker, sent_at, sent_at, window_minutes),
            )
            group_id = int(cursor.lastrowid)
            for row in rows:
                timestamp = _timestamp(row["sent_at"])
                if timestamp is not None and abs((anchor - timestamp).total_seconds()) <= window_minutes * 60:
                    db.execute("UPDATE signals SET consensus_group_id=? WHERE id=?", (group_id, row["id"]))
        db.execute("UPDATE signals SET consensus_group_id=? WHERE id=?", (group_id, signal_id))
        members = db.execute(
            "SELECT * FROM signals WHERE consensus_group_id=? ORDER BY sent_at, id", (group_id,)
        ).fetchall()
    else:
        cursor = db.execute(
            "INSERT INTO consensus_groups(ticker,first_seen,latest_seen,window_minutes) VALUES(?,?,?,?)",
            (ticker, sent_at, sent_at, window_minutes),
        )
        group_id = int(cursor.lastrowid)
        db.execute("UPDATE signals SET consensus_group_id=? WHERE id=?", (group_id, signal_id))
        members = db.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchall()
    result = _consensus_result(group_id, ticker, members, side, window_minutes)
    db.execute(
        """UPDATE consensus_groups SET ticker=?,first_seen=?,latest_seen=?,window_minutes=?,
        number_of_channels=?,agreeing_channels_json=?,disagreeing_channels_json=?,consensus_score=?
        WHERE id=?""",
        (ticker, result["first_seen"] or sent_at, result["latest_seen"] or sent_at, window_minutes,
         result["number_of_channels"], json.dumps(result["agreeing_channels"]),
         json.dumps(result["disagreeing_channels"]), result["consensus_score"], group_id),
    )
    for member in members:
        member_result = _consensus_result(
            group_id, ticker, members, member["side"], window_minutes
        )
        db.execute(
            """UPDATE signals SET number_of_channels=?,agreeing_channels_json=?,
            disagreeing_channels_json=?,consensus_score=?,consensus_first_seen=?,consensus_latest_seen=?
            WHERE id=?""",
            (member_result["number_of_channels"], json.dumps(member_result["agreeing_channels"]),
             json.dumps(member_result["disagreeing_channels"]), member_result["consensus_score"],
             member_result["first_seen"], member_result["latest_seen"], member["id"]),
        )
    return result


def consensus_for_signal(db: sqlite3.Connection, row: sqlite3.Row, window_minutes: int) -> dict[str, Any]:
    fresh = db.execute(
        """SELECT consensus_group_id,number_of_channels,agreeing_channels_json,
        disagreeing_channels_json,consensus_score,consensus_first_seen,consensus_latest_seen
        FROM signals WHERE id=?""", (row["id"],)
    ).fetchone()
    if fresh and fresh["consensus_group_id"] is not None:
        return {
            "group_id": fresh["consensus_group_id"],
            "number_of_channels": fresh["number_of_channels"] or 0,
            "agreeing_channels": json.loads(fresh["agreeing_channels_json"] or "[]"),
            "disagreeing_channels": json.loads(fresh["disagreeing_channels_json"] or "[]"),
            "consensus_score": fresh["consensus_score"] or 0.0,
            "first_seen": fresh["consensus_first_seen"],
            "latest_seen": fresh["consensus_latest_seen"],
            "window_minutes": window_minutes,
        }
    return {
        "group_id": None, "number_of_channels": 0, "agreeing_channels": [],
        "disagreeing_channels": [], "consensus_score": 0.0,
        "first_seen": row["sent_at"], "latest_seen": row["sent_at"],
        "window_minutes": window_minutes,
    }


def calculate_conviction(
    db: sqlite3.Connection,
    source: str,
    parsed: dict[str, Any],
    sent_at: str,
    ticker: str | None,
    entry: Any,
    targets: list[Any],
    stop_loss: Any,
    *,
    consensus: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one signal using transparent, bounded factors totaling 100 points."""
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    history = _historical_channel_stats(db, source)

    if history["closed"]:
        win_score = min(20.0, float(history["win_rate"]) / 100 * 20)
        pf_score = min(12.0, float(history["profit_factor"]) / 2 * 12)
        average_score = max(0.0, min(13.0, 6.5 + float(history["average_return"]) / 5 * 6.5))
        historical_points = win_score + pf_score + average_score
        score += historical_points
        reasons.append(
            f"Channel history: {int(history['closed'])} closed trades, "
            f"{float(history['win_rate']):.1f}% win rate, PF {float(history['profit_factor']):.2f}, "
            f"average return {float(history['average_return']):+.2f}% "
            f"({historical_points:.1f}/45 points)"
        )
    else:
        score += 10.0 + 6.0 + 6.5
        reasons.append("Channel history has no closed paper trades; neutral historical prior applied (22.5/45 points)")

    entry_value = _entry_price(entry)
    stop_value = _number(stop_loss)
    target_values = [_number(value) for value in targets]
    target_values = [value for value in target_values if value is not None]
    completeness = 0.0
    if ticker:
        completeness += 3
    else:
        warnings.append("Ticker is missing or ambiguous")
    direction = _direction(parsed.get("side"))
    if direction:
        completeness += 2
    else:
        warnings.append("Direction is missing or unrecognized")
    if entry_value is not None and entry_value > 0:
        completeness += 3
    else:
        warnings.append("Entry is missing or invalid")
    if target_values:
        completeness += 3
    else:
        warnings.append("Targets are missing or invalid")
    if stop_value is not None and stop_value > 0:
        completeness += 3
    else:
        warnings.append("Stop loss is missing or invalid")
    if not (parsed.get("leverage_detected") or parsed.get("leverage_or_derivatives_detected") or parsed.get("dca_levels")):
        completeness += 1
    else:
        warnings.append("Leverage, derivatives, or DCA language reduces completeness")
    score += completeness
    reasons.append(f"Signal completeness: {completeness:.0f}/15")

    risk_reward = None
    if direction and entry_value is not None and stop_value is not None and target_values:
        if direction == "long":
            risk = entry_value - stop_value
            reward = target_values[0] - entry_value
        else:
            risk = stop_value - entry_value
            reward = entry_value - target_values[0]
        if risk > 0 and reward > 0:
            risk_reward = reward / risk
    if risk_reward is None:
        rr_score = 0.0
        warnings.append("Risk/reward cannot be verified")
    elif risk_reward >= 3:
        rr_score = 10.0
    elif risk_reward >= 2:
        rr_score = 7.5
    elif risk_reward >= 1:
        rr_score = 5.0
    else:
        rr_score = 2.0
        warnings.append(f"Low risk/reward ratio ({risk_reward:.2f})")
    score += rr_score
    reasons.append(f"Risk/reward: {risk_reward:.2f} ({rr_score:.1f}/10)" if risk_reward is not None else "Risk/reward: unavailable (0/10)")

    consensus = consensus or consensus_for_values(
        db, ticker, sent_at, parsed.get("side"), DEFAULT_CONSENSUS_WINDOW_MINUTES
    )
    consensus_points = float(consensus.get("consensus_score") or 0.0) / 10
    agreeing = consensus.get("agreeing_channels") or []
    disagreeing = consensus.get("disagreeing_channels") or []
    if disagreeing:
        warnings.append("Consensus has opposing channel direction")
    score += consensus_points
    reasons.append(
        f"Consensus: {float(consensus.get('consensus_score') or 0.0):.1f}/100 "
        f"({consensus_points:.1f}/10 points), {int(consensus.get('number_of_channels') or 0)} channel(s), "
        f"{len(agreeing)} agreeing, {len(disagreeing)} disagreeing"
    )

    context = market_context or unavailable_market_context("market context not supplied")
    context_result = score_market_context(parsed, context)
    context_points = float(context_result["market_context_score"]) * 0.15
    score += context_points
    reasons.extend(f"Market context: {reason}" for reason in context_result["reasons"])
    warnings.extend(context_result["warnings"])

    freshness_score = 0.0
    age_hours = None
    sent = _timestamp(sent_at)
    if sent is not None:
        age_hours = (datetime.now(timezone.utc) - sent).total_seconds() / 3600
        timeout = float(source_policy(source)["timeout_hours"])
        freshness_score = max(0.0, min(5.0, 5 * (1 - age_hours / timeout)))
        if age_hours > timeout:
            warnings.append(f"Signal is stale ({age_hours:.1f}h; source timeout {timeout:g}h)")
        elif age_hours < -0.25:
            freshness_score = 0.0
            warnings.append("Signal timestamp is in the future")
    else:
        warnings.append("Signal timestamp is invalid")
    score += freshness_score
    reasons.append(f"Freshness: {freshness_score:.1f}/5" + (f" at {age_hours:.1f}h old" if age_hours is not None else " unavailable"))

    score = round(max(0.0, min(100.0, score)), 2)
    confidence = "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
    return {
        "conviction_score": score,
        "confidence_level": confidence,
        "reasons": reasons,
        "warnings": warnings,
        "market_context_score": context_result["market_context_score"],
    }


def calculate_decision(
    db: sqlite3.Connection,
    source: str,
    parsed: dict[str, Any],
    sent_at: str,
    ticker: str | None,
    entry: Any,
    targets: list[Any],
    stop_loss: Any,
    conviction: dict[str, Any],
    consensus: dict[str, Any],
    market_context: dict[str, Any],
) -> dict[str, Any]:
    """Combine existing evidence into a paper-only, non-executing decision."""
    history = _historical_channel_stats(db, source)
    if history["closed"]:
        history_score = (
            min(40.0, float(history["win_rate"]) / 100 * 40)
            + min(30.0, float(history["profit_factor"]) / 2 * 30)
            + max(0.0, min(30.0, 15.0 + float(history["average_return"]) / 5 * 15))
        )
        channel_reason = (
            f"Channel performance {history_score:.1f}/100: {float(history['win_rate']):.1f}% win rate, "
            f"PF {float(history['profit_factor']):.2f}, average return {float(history['average_return']):+.2f}%"
        )
    else:
        history_score = 50.0
        channel_reason = "Channel performance has no settled paper history; neutral prior 50/100"
    consensus_score = float(consensus.get("consensus_score") or 0.0)
    market_score = float(market_context.get("market_context_score") or 0.0)
    conviction_score = float(conviction.get("conviction_score") or 0.0)
    overall = round(
        max(0.0, min(100.0, conviction_score * 0.50 + consensus_score * 0.20 + market_score * 0.15 + history_score * 0.15)),
        2,
    )
    blocking: list[str] = []
    supporting = [
        f"Conviction score {conviction_score:.1f}/100",
        f"Consensus score {consensus_score:.1f}/100 across {int(consensus.get('number_of_channels') or 0)} channel(s)",
        f"Market context score {market_score:.1f}/100",
        channel_reason,
    ]
    if not market_context.get("available"):
        blocking.append("Market context unavailable; decision fails closed")
    eligibility = paper_eligibility(source, parsed, sent_at, _entry_price(entry), [
        value for value in (_number(target) for target in targets) if value is not None
    ], _number(stop_loss))
    blocking.extend(eligibility["reasons"])
    if conviction_score < 50:
        blocking.append(f"Conviction below paper threshold ({conviction_score:.1f} < 50)")
    if consensus_score < 50 and int(consensus.get("number_of_channels") or 0) > 1:
        blocking.append(f"Disagreement or weak consensus ({consensus_score:.1f}/100)")
    if market_score < 40 and market_context.get("available"):
        blocking.append(f"Weak market context ({market_score:.1f}/100)")
    if blocking or overall < 50:
        decision = "REJECT"
    elif overall >= 75:
        decision = "APPROVE"
    else:
        decision = "WATCH"
    if decision == "REJECT":
        size = "NONE"
        risk = 0.0
    elif decision == "WATCH":
        size = "SMALL"
        risk = 0.25
    elif overall >= 90 and conviction_score >= 85 and consensus_score >= 75 and market_score >= 70 and history_score >= 70:
        size = "FULL"
        risk = 1.0
    else:
        size = "MEDIUM"
        risk = 0.5
    if not blocking:
        supporting.append("No decision blockers detected")
    explanation = f"{decision}: overall score {overall:.1f}/100; paper-only recommendation {size} with maximum risk {risk:.2f}%"
    return {
        "decision": decision,
        "overall_score": overall,
        "position_size_recommendation": size,
        "maximum_risk_percent": risk,
        "explanation": explanation,
        "blocking_reasons": blocking,
        "supporting_reasons": supporting,
    }


def trade_plan_lines(source: str, parsed: dict[str, Any]) -> list[str]:
    policy = source_policy(source)
    target_pct = policy["target_pct"]
    trail_pct = policy["trail_pct"]
    timeout_hours = policy["timeout_hours"]
    lines = [
        f"Source rank: {policy['rank']} · {policy['bias']}",
        f"Exit plan: take partial profit around +{target_pct:g}%; move stop or trail by ~{trail_pct:g}% after strength",
        f"Timeout: if no clean move within {timeout_hours:g}h, treat as stale and skip/review",
        f"Rule: {policy['plan']}",
    ]
    if parsed.get("leverage_detected") or parsed.get("leverage_or_derivatives_detected"):
        lines.append("Risk mode: futures/leverage language detected; use paper review or tiny size only")
    return lines


def risk_flags(parsed: dict[str, Any], sent_at: str) -> list[str]:
    warnings: list[str] = []
    if parsed.get("leverage_detected") or parsed.get("leverage_or_derivatives_detected"):
        warnings.append("LEVERAGE/DERIVATIVES DETECTED")
    if parsed.get("side") == "short":
        warnings.append("SHORT SIGNAL: excluded from spot-only paper lane")
    if parsed.get("stop_loss") is None:
        warnings.append("NO STOP LOSS")
    if not (parsed.get("targets") or []):
        warnings.append("NO TARGETS")
    if parsed.get("dca_levels"):
        warnings.append("DCA / averaging down mentioned")
    try:
        sent = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - sent.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours > 24:
            warnings.append(f"STALE ({age_hours:.0f}h old)")
    except ValueError:
        warnings.append("MESSAGE TIME UNKNOWN")
    if not parsed.get("pair") and not parsed.get("detected_pair"):
        warnings.append("TICKER NOT PARSED")
    return warnings


def paper_eligibility(
    source: str,
    parsed: dict[str, Any],
    sent_at: str,
    entry_price: float | None,
    targets: list[float],
    stop_loss: float | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a fail-closed admission decision for the spot paper lane.

    This is deliberately stricter than alerting: a Telegram call can be useful
    context while still being unsuitable for an objective paper-trading result.
    """
    reasons: list[str] = []
    policy = source_policy(source)
    try:
        entry_value = float(entry_price) if entry_price is not None else None
    except (TypeError, ValueError):
        entry_value = None
    try:
        stop_value = float(stop_loss) if stop_loss is not None else None
    except (TypeError, ValueError):
        stop_value = None
    try:
        target_values = [float(target) for target in targets]
    except (TypeError, ValueError):
        target_values = []
    if policy["rank"] == "Unranked" or policy["bias"] == "watch-only":
        reasons.append("SOURCE_NOT_APPROVED")
    if str(parsed.get("side") or "").casefold() in {"short", "sell"}:
        reasons.append("SHORT_NOT_SUPPORTED")
    if parsed.get("leverage_detected") or parsed.get("leverage_or_derivatives_detected"):
        reasons.append("LEVERAGE_OR_DERIVATIVES")
    if parsed.get("dca_levels"):
        reasons.append("DCA_NOT_SUPPORTED")
    if entry_value is None or entry_value <= 0:
        reasons.append("INVALID_ENTRY")
    if stop_value is None or stop_value <= 0:
        reasons.append("MISSING_STOP_LOSS")
    if entry_value is not None and stop_value is not None and stop_value >= entry_value:
        reasons.append("STOP_NOT_BELOW_ENTRY")
    if not target_values:
        reasons.append("MISSING_TARGETS")
    elif entry_value is not None:
        if any(target <= entry_value for target in target_values):
            reasons.append("TARGET_NOT_ABOVE_ENTRY")
        if any(left >= right for left, right in zip(target_values, target_values[1:])):
            reasons.append("TARGETS_NOT_ASCENDING")
    try:
        sent = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        age_hours = (reference - sent.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours > float(policy["timeout_hours"]):
            reasons.append("STALE_SIGNAL")
        if age_hours < -0.25:
            reasons.append("FUTURE_TIMESTAMP")
    except (TypeError, ValueError):
        age_hours = None
        reasons.append("INVALID_TIMESTAMP")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "age_hours": age_hours,
        "policy_rank": policy["rank"],
    }


def format_alert(row: sqlite3.Row) -> str:
    parsed = json.loads(row["parsed_json"])
    market_context = json.loads(row["market_context_json"] or "{}")
    warnings = risk_flags(parsed, row["sent_at"])
    age = "unknown"
    try:
        dt = datetime.fromisoformat(row["sent_at"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = f"{max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() // 60))}m"
    except (ValueError, TypeError):
        pass
    entry = json.loads(row["entry_json"]) if row["entry_json"] else None
    if isinstance(entry, dict):
        entry_text = f"{entry.get('low', '?')}–{entry.get('high', '?')}"
    elif entry is not None:
        entry_text = str(entry)
    else:
        entry_text = "not found"
    targets = json.loads(row["targets_json"])
    target_text = ", ".join(str(value) for value in targets) if targets else "not found"
    lines = [
        f"🚨 SIGNAL · {row['ticker'] or 'TICKER UNKNOWN'} · {(row['side'] or 'SIDE UNKNOWN').upper()}",
        f"Source: {row['source']} · age {age}",
        f"Entry: {entry_text}",
        f"Targets: {target_text}",
        f"Stop loss: {row['stop_loss'] if row['stop_loss'] is not None else 'MISSING'}",
        "Review: " + (" | ".join(warnings) if warnings else "no parser warnings"),
        f"Conviction: {row['conviction_score']:.1f}/100 · {row['confidence_level']}" if row['conviction_score'] is not None else "Conviction: unavailable",
        f"Consensus: {row['consensus_score']:.1f}/100 · {row['number_of_channels'] or 0} channel(s) · "
        f"agreeing {len(json.loads(row['agreeing_channels_json'] or '[]'))} · "
        f"disagreeing {len(json.loads(row['disagreeing_channels_json'] or '[]'))}",
        f"Market context: {market_context.get('market_context_score', 0):.1f}/100 · "
        f"BTC {market_context.get('btc_trend') or 'unavailable'} · "
        f"24h {market_context.get('btc_24h_change_pct') if market_context.get('btc_24h_change_pct') is not None else 'N/A'}% · "
        f"volatility {market_context.get('market_volatility') or 'unavailable'} · "
        f"Fear & Greed {market_context.get('fear_greed_index') if market_context.get('fear_greed_index') is not None else 'N/A'} · "
        f"session {market_context.get('trading_session') or 'unavailable'} · "
        f"{market_context.get('day_of_week') or 'unknown'}",
        f"Decision: {row['decision'] or 'UNAVAILABLE'} · overall {row['overall_score'] if row['overall_score'] is not None else 'N/A'}/100 · "
        f"size {row['position_size_recommendation'] or 'NONE'} · max risk {row['maximum_risk_percent'] if row['maximum_risk_percent'] is not None else 0}%",
        *trade_plan_lines(row["source"], parsed),
        "Status: information only · no order placed",
    ]
    if row["conviction_reasons_json"]:
        lines.append("Conviction reasons: " + " | ".join(json.loads(row["conviction_reasons_json"])))
    if row["conviction_warnings_json"]:
        conviction_warnings = json.loads(row["conviction_warnings_json"])
        if conviction_warnings:
            lines.append("Conviction warnings: " + " | ".join(conviction_warnings))
    if row["consensus_first_seen"] and row["consensus_latest_seen"]:
        lines.append(f"Consensus window: {row['consensus_first_seen']} → {row['consensus_latest_seen']}")
    if row["decision_explanation"]:
        lines.append("Decision explanation: " + row["decision_explanation"])
    if row["blocking_reasons_json"]:
        decision_blocks = json.loads(row["blocking_reasons_json"])
        if decision_blocks:
            lines.append("Decision blockers: " + " | ".join(decision_blocks))
    if row["supporting_reasons_json"]:
        decision_support = json.loads(row["supporting_reasons_json"])
        if decision_support:
            lines.append("Decision support: " + " | ".join(decision_support))
    if row["source_url"]:
        lines.append(f"Source message: {row['source_url']}")
    if row["raw_text"]:
        excerpt = row["raw_text"].strip()
        lines.extend(["", "Original:", excerpt[:900]])
    message = "\n".join(lines)
    return message[:MAX_ALERT_CHARS]


def telegram_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def send_alert(message: str, *, dry_run: bool = False) -> tuple[bool, str]:
    if dry_run:
        return False, "dry_run"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8, context=telegram_ssl_context()) as response:
            body = json.loads(response.read().decode("utf-8"))
        if body.get("ok") is True:
            return True, ""
        return False, str(body.get("description", "Telegram rejected alert"))[:300]
    except Exception as error:
        return False, str(error)[:300]


def deliver_pending(store: SignalStore, dry_run: bool) -> tuple[int, int, int]:
    sent = failed = unconfigured = 0
    for row in store.pending():
        text = format_alert(row)
        ok, error = send_alert(text, dry_run=dry_run)
        if ok:
            store.mark_alert(row["id"], "sent")
            sent += 1
        elif error == "dry_run":
            print("\n--- DRY RUN ALERT ---\n" + text)
        elif error.startswith("missing "):
            store.mark_alert(row["id"], "unconfigured")
            unconfigured += 1
        else:
            failed += 1
    return sent, failed, unconfigured


def message_url(entity: Any, message_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    peer_id = getattr(entity, "id", None)
    if peer_id is not None and getattr(entity, "broadcast", False):
        return f"https://t.me/c/{peer_id}/{message_id}"
    return None


async def list_dialogs(args: argparse.Namespace) -> int:
    from telethon import TelegramClient
    root = args.supervizor_root
    env_path = args.env or root / ".env.telegram"
    env = _read_telethon_env(env_path)
    session = args.session_dir or root / "supervizor_sessions"
    client = TelegramClient(str(session / env["TELEGRAM_SESSION_NAME"]), int(env["TELEGRAM_API_ID"]), env["TELEGRAM_API_HASH"])
    async with client:
        dialogs = await client.get_dialogs(limit=args.dialog_limit)
        for dialog in dialogs:
            entity = dialog.entity
            title = getattr(entity, "title", None) or getattr(entity, "username", None)
            if title:
                print(str(title))
    return 0


def _read_telethon_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Telegram client settings missing: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    required = ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_NAME")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("Missing required Telethon settings: " + ", ".join(missing))
    return values


async def run_watch(args: argparse.Namespace) -> int:
    try:
        from telethon import TelegramClient, events
    except ImportError as error:
        raise RuntimeError("Telethon missing; install it into this Python environment.") from error

    root: Path = args.supervizor_root
    env_path = args.env or root / ".env.telegram"
    env = _read_telethon_env(env_path)
    session_dir = args.session_dir or root / "supervizor_sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    parse_fn = load_parser(root)
    store = SignalStore(args.db, args.consensus_window_minutes, fetch_market_context)
    client = TelegramClient(
        str(session_dir / env["TELEGRAM_SESSION_NAME"]),
        int(env["TELEGRAM_API_ID"]),
        env["TELEGRAM_API_HASH"],
    )
    dialogs: dict[int, Any] = {}
    source_labels: dict[int, str] = {}

    async with client:
        for chat in args.chat:
            entity = await client.get_entity(chat)
            dialogs[int(entity.id)] = entity
            source_labels[int(entity.id)] = getattr(entity, "title", None) or getattr(entity, "username", None) or str(chat)

        async def handle_message(event):
            entity = dialogs.get(int(event.chat_id))
            if entity is None:
                return
            text = event.raw_text or ""
            if not is_signal_candidate(text):
                return
            source = source_labels[int(event.chat_id)]
            sent = event.message.date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            signal = parse_signal(
                parse_fn, source, event.message.id, sent, text,
                message_url(entity, event.message.id),
            )
            if store.add(signal):
                print(f"signal logged: {store.ticker(signal.parsed, text) or 'unknown'} · {source} · #{signal.message_id}", flush=True)
                deliver_pending(store, args.dry_run)

        client.add_event_handler(handle_message, events.NewMessage(chats=list(dialogs.values())))

        # Backfill after handler registration. UNIQUE(source,message_id) and dedupe_key
        # collapse overlap with live updates and reconnect replay.
        for chat_id, entity in dialogs.items():
            source = source_labels[chat_id]
            last_id = store.get_last_id(source)
            backfill_limit = max(0, args.backfill)
            if backfill_limit:
                async for message in client.iter_messages(entity, limit=backfill_limit, min_id=last_id):
                    text = message.message or ""
                    if not is_signal_candidate(text):
                        store.set_last_id(source, int(message.id))
                        continue
                    sent = message.date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    signal = parse_signal(
                        parse_fn, source, int(message.id), sent, text,
                        message_url(entity, int(message.id)),
                    )
                    store.add(signal)
                    store.mark_by_source_message(source, int(message.id), "backfill")
                    store.set_last_id(source, int(message.id))
            sent, failed, unconfigured = deliver_pending(store, args.dry_run)
            print(
                f"watching {source}: last_id={store.get_last_id(source)} "
                f"sent={sent} failed={failed} unconfigured={unconfigured}",
                flush=True,
            )

        if args.once:
            return 0
        print("Signal Watch live; Ctrl-C stops monitoring.", flush=True)
        await client.run_until_disconnected()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supervizor-root", type=Path, default=Path(os.environ.get("SIGNAL_WATCH_SUPERVIZOR_ROOT", DEFAULT_SUPERVIZOR_ROOT)))
    parser.add_argument("--env", type=Path, help="Telethon credentials file; contents are never printed.")
    parser.add_argument("--session-dir", type=Path, help="Existing authorized Telethon session folder.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--chat", action="append", help="Telegram channel/group title, username, or link. Repeat for each.")
    parser.add_argument("--dialog-limit", type=int, default=100)
    parser.add_argument("--backfill", type=int, default=0, help="Import up to N most recent messages per channel before live listening.")
    parser.add_argument("--consensus-window-minutes", type=int, default=DEFAULT_CONSENSUS_WINDOW_MINUTES,
                        help="Group same-ticker signals across channels within this many minutes.")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts locally; never send them.")
    parser.add_argument("--once", action="store_true", help="Backfill and exit; useful for testing.")
    parser.add_argument("--test-alert", action="store_true", help="Send one clearly labeled Telegram delivery test and exit.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.chat = args.chat or []
    if args.test_alert:
        sent, error = send_alert("Signal Watch test: alert delivery is connected. No order was placed.")
        if sent:
            print("test_alert=sent")
            return 0
        print(f"test_alert=failed reason={error}", file=sys.stderr)
        return 2
    if args.backfill < 0 or args.backfill > 10000:
        parser.error("--backfill must be between 0 and 10000")
    if args.consensus_window_minutes <= 0 or args.consensus_window_minutes > 7 * 24 * 60:
        parser.error("--consensus-window-minutes must be between 1 and 10080")
    try:
        if args.env is None and not (args.supervizor_root / ".env.telegram").is_file():
            raise FileNotFoundError("Supervizor .env.telegram not found; pass --env or --supervizor-root.")
        if args.chat:
            lock_handle = acquire_process_lock(args.lock_file)
            try:
                return asyncio.run(run_watch(args))
            finally:
                lock_handle.close()
        return asyncio.run(list_dialogs(args))
    except KeyboardInterrupt:
        print("Signal Watch stopped.", flush=True)
        return 130
    except Exception as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
