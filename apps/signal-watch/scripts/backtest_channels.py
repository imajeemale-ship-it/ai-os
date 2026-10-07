#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
DEFAULT_SUPERVIZOR_ROOT = Path.home() / "Desktop" / "ai-agent-test" / "ft_userdata"
WATCH_PATH = APP_DIR / "watch.py"

spec = importlib.util.spec_from_file_location("signal_watch", WATCH_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load {WATCH_PATH}")
watch = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watch
spec.loader.exec_module(watch)

STABLES = {"USDT", "USDC", "USD", "DAI", "FDUSD", "TUSD"}
NOISE = {"TP", "SL", "VIP"}
OUTCOME_ONLY_RE = re.compile(r"\b(?:take-profit\s+target|target\s*\d*\s*(?:hit|done|✅)|tp\s*\d+\s*(?:hit|✅)|all\s+targets\s+done|profit\s*[:=]|period\s*:|closed\s+(?:in|with)\s+(?:profit|loss))\b", re.I)


@dataclass
class CallResult:
    channel: str
    message_id: int
    sent_at: datetime
    ticker: str
    side: str
    entry: float | None
    price_at_signal: float | None
    final_price: float | None
    max_gain_pct: float | None
    final_return_pct: float | None
    tp1_pct: float | None
    tp4_pct: float | None
    best_tp_hit: int
    ladder_return_pct: float | None
    classification: str
    reason: str
    url: str | None
    text: str


def load_parser(root: Path):
    path = root / "supervizor_signal_parser.py"
    spec = importlib.util.spec_from_file_location("supervizor_signal_parser", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load parser {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.parse_signal


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def normalize_ticker(parsed: dict[str, Any], text: str) -> str | None:
    ticker = watch.SignalStore.ticker(parsed, text)
    if ticker:
        ticker = ticker.upper().strip()
        for suffix in ("USDT", "USDC", "USD"):
            if ticker.endswith(suffix) and len(ticker) > len(suffix) + 1:
                ticker = ticker[: -len(suffix)]
                break
    if ticker in NOISE or ticker in STABLES:
        return None
    return ticker


def _num(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except Exception:
        return None


def entry_from_text(text: str) -> float | None:
    patterns = [
        r"(?:entry|entries|enteries)\s*:?\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:-|–|to)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"(?:entry|entries|enteries)\s*:?\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        nums = [_num(group) for group in match.groups() if group]
        nums = [num for num in nums if num is not None]
        if nums:
            return sum(nums) / len(nums)
    return None


def side_from_text(text: str, parsed: dict[str, Any]) -> str:
    head = text[:220]
    direction = re.search(r"(?:direction\s*:?|📉|📈|📊|🕯|▶️)?\s*\b(LONG|SHORT)\b", head, re.I)
    if direction:
        return direction.group(1).lower()
    side = (parsed.get("side") or "long").lower()
    return side if side in ("long", "short") else "long"


def entry_from_parsed(parsed: dict[str, Any], text: str) -> float | None:
    text_entry = entry_from_text(text)
    if text_entry is not None:
        return text_entry
    entry = parsed.get("entry")
    if isinstance(entry, dict):
        vals = [entry.get("low"), entry.get("high")]
        nums = [float(v) for v in vals if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d+(?:\.\d+)?", v))]
        if nums:
            return sum(nums) / len(nums)
    value = parsed.get("entry_price")
    if isinstance(value, (int, float)):
        return float(value)
    return None



def targets_from_parsed(parsed: dict[str, Any], text: str) -> list[float]:
    values = parsed.get("targets") or []
    targets: list[float] = []
    if isinstance(values, list):
        for value in values:
            try:
                targets.append(float(str(value).replace(",", "")))
            except Exception:
                pass
    if targets:
        return targets
    matches = re.findall(r"(?:target|tp)\s*\d*\s*(?:[:-]|–|to)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?)", text, re.I)
    for value in matches:
        num = _num(value)
        if num is not None:
            targets.append(num)
    return targets


def ladder_result(base: float, side: str, highs: list[float], lows: list[float], targets: list[float]) -> tuple[float | None, float | None, int, float | None]:
    if not targets:
        return None, None, 0, None
    ordered = sorted(targets, reverse=(side == "short"))[:4]
    hit = 0
    for target in ordered:
        if side == "short":
            reached = min(lows) <= target
        else:
            reached = max(highs) >= target
        if reached:
            hit += 1
    def pct(target: float | None) -> float | None:
        if target is None:
            return None
        return ((base - target) / base) * 100 if side == "short" else ((target - base) / base) * 100
    tp1 = pct(ordered[0]) if len(ordered) >= 1 else None
    tp4 = pct(ordered[3]) if len(ordered) >= 4 else None
    if hit == 0:
        return tp1, tp4, 0, 0.0
    per_exit = 1 / min(4, len(ordered))
    ladder = 0.0
    for target in ordered[:hit]:
        ladder += (pct(target) or 0.0) * per_exit
    return tp1, tp4, hit, ladder


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def coinbase_json(path: str, query: dict[str, str] | None = None):
    url = "https://api.exchange.coinbase.com" + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"User-Agent": "AI-OS Signal Watch audit"})
    with urllib.request.urlopen(req, timeout=12, context=ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


_product_cache: dict[str, str | None] = {}
_candle_cache: dict[tuple[str, int, int], list[list[float]]] = {}


def coinbase_product(ticker: str) -> str | None:
    if ticker in _product_cache:
        return _product_cache[ticker]
    for quote in ("USD", "USDT", "USDC"):
        product = f"{ticker}-{quote}"
        try:
            coinbase_json(f"/products/{product}")
            _product_cache[ticker] = product
            return product
        except Exception:
            continue
    _product_cache[ticker] = None
    return None


def candles(product: str, start: datetime, end: datetime, granularity: int = 3600) -> list[list[float]]:
    key = (product, int(start.timestamp()), int(end.timestamp()))
    if key in _candle_cache:
        return _candle_cache[key]
    data = coinbase_json(
        f"/products/{product}/candles",
        {
            "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "granularity": str(granularity),
        },
    )
    rows = sorted(data, key=lambda row: row[0])
    _candle_cache[key] = rows
    time.sleep(0.08)
    return rows


def evaluate(ticker: str, side: str, sent_at: datetime, entry: float | None, targets: list[float], horizon_hours: int) -> tuple[float | None, float | None, float | None, float | None, float | None, float | None, int, float | None, str, str]:
    product = coinbase_product(ticker)
    if not product:
        return None, None, None, None, None, None, 0, None, "unverified", "ticker not on Coinbase USD/USDT/USDC"
    now = datetime.now(timezone.utc)
    start = sent_at - timedelta(hours=1)
    end = min(sent_at + timedelta(hours=horizon_hours), now)
    if end <= sent_at + timedelta(minutes=10):
        return None, None, None, None, None, None, 0, None, "unverified", "too recent"
    try:
        rows = candles(product, start, end)
    except urllib.error.HTTPError as err:
        return None, None, None, None, None, None, 0, None, "unverified", f"Coinbase HTTP {err.code}"
    except Exception as err:
        return None, None, None, None, None, None, 0, None, "unverified", f"price fetch failed: {err.__class__.__name__}"
    after = [row for row in rows if datetime.fromtimestamp(row[0], timezone.utc) >= sent_at]
    if not after:
        return None, None, None, None, None, None, 0, None, "unverified", "no candles after signal"
    base = entry or float(after[0][4])
    first = float(after[0][4])
    final = float(after[-1][4])
    highs = [float(row[2]) for row in after]
    lows = [float(row[1]) for row in after]
    if side == "short":
        max_gain = ((base - min(lows)) / base) * 100
        final_ret = ((base - final) / base) * 100
    else:
        max_gain = ((max(highs) - base) / base) * 100
        final_ret = ((final - base) / base) * 100
    tp1, tp4, best_tp_hit, ladder_return = ladder_result(base, side, highs, lows, targets)
    if best_tp_hit >= 1:
        klass = "tp_hit"
        reason = f"hit TP{best_tp_hit}; ladder return {ladder_return:.2f}%"
    elif max_gain >= 3 and final_ret >= 1:
        klass = "right"
        reason = "moved at least +3% and retained at least +1%"
    elif max_gain >= 3 and final_ret < 1:
        klass = "gave_back"
        reason = "moved +3% but gave back most of it"
    elif final_ret <= -2:
        klass = "wrong"
        reason = "ended -2% or worse"
    else:
        klass = "flat"
        reason = "no clean edge yet"
    return base, first, final, max_gain, tp1, tp4, best_tp_hit, ladder_return, klass, reason + f"; final {final_ret:.2f}%"


async def audit_channel(client, parse_fn, channel: str, limit: int, horizon_hours: int) -> tuple[str, list[CallResult], dict[str, int]]:
    entity = await client.get_entity(channel)
    title = getattr(entity, "title", None) or getattr(entity, "username", None) or channel
    results: list[CallResult] = []
    stats = {"messages": 0, "candidates": 0, "parsed_ticker": 0, "verified": 0}
    async for message in client.iter_messages(entity, limit=limit):
        stats["messages"] += 1
        text = message.message or ""
        if OUTCOME_ONLY_RE.search(text) and not re.search(r"\b(?:entry|enteries|entries|buy\s+zone|sell\s+zone)\b", text, re.I):
            continue
        if not watch.is_signal_candidate(text):
            continue
        stats["candidates"] += 1
        sent = message.date.astimezone(timezone.utc)
        try:
            parsed = parse_fn(text, source=title, message_id=int(message.id), timestamp=sent.isoformat().replace("+00:00", "Z"))
        except Exception:
            continue
        ticker = normalize_ticker(parsed, text)
        if not ticker:
            continue
        stats["parsed_ticker"] += 1
        side = side_from_text(text, parsed)
        entry = entry_from_parsed(parsed, text)
        targets = targets_from_parsed(parsed, text)
        base, first, final, max_gain, tp1, tp4, best_tp_hit, ladder_return, klass, reason = evaluate(ticker, side, sent, entry, targets, horizon_hours)
        if klass != "unverified":
            stats["verified"] += 1
        final_ret = None if base is None or final is None else (((base - final) / base) * 100 if side == "short" else ((final - base) / base) * 100)
        results.append(CallResult(
            channel=title,
            message_id=int(message.id),
            sent_at=sent,
            ticker=ticker,
            side=side,
            entry=entry,
            price_at_signal=base,
            final_price=final,
            max_gain_pct=max_gain,
            final_return_pct=final_ret,
            tp1_pct=tp1,
            tp4_pct=tp4,
            best_tp_hit=best_tp_hit,
            ladder_return_pct=ladder_return,
            classification=klass,
            reason=reason,
            url=watch.message_url(entity, int(message.id)),
            text=" ".join(text.split())[:240],
        ))
    return title, results, stats


def summarize(title: str, results: list[CallResult], stats: dict[str, int]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in results:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    verified = [row for row in results if row.classification not in {"unverified"}]
    avg_final = sum(row.final_return_pct or 0 for row in verified) / len(verified) if verified else None
    avg_max = sum(row.max_gain_pct or 0 for row in verified) / len(verified) if verified else None
    ladder_rows = [row for row in verified if row.ladder_return_pct is not None]
    avg_ladder = sum(row.ladder_return_pct or 0 for row in ladder_rows) / len(ladder_rows) if ladder_rows else None
    tp1_hit_rate = (sum(1 for row in ladder_rows if row.best_tp_hit >= 1) / len(ladder_rows) * 100) if ladder_rows else None
    tp4_hit_rate = (sum(1 for row in ladder_rows if row.best_tp_hit >= 4) / len(ladder_rows) * 100) if ladder_rows else None
    return {
        "channel": title,
        "messages_scanned": stats["messages"],
        "candidate_messages": stats["candidates"],
        "parsed_ticker_calls": stats["parsed_ticker"],
        "verified_calls": len(verified),
        "counts": counts,
        "avg_final_return_pct": avg_final,
        "avg_max_gain_pct": avg_max,
        "avg_ladder_return_pct": avg_ladder,
        "tp1_hit_rate_pct": tp1_hit_rate,
        "tp4_hit_rate_pct": tp4_hit_rate,
    }


async def main_async(args: argparse.Namespace) -> int:
    from telethon import TelegramClient
    root = args.supervizor_root
    env = read_env(args.env or root / ".env.telegram")
    parse_fn = load_parser(root)
    session_dir = args.session_dir or root / "supervizor_sessions"
    client = TelegramClient(str(session_dir / env["TELEGRAM_SESSION_NAME"]), int(env["TELEGRAM_API_ID"]), env["TELEGRAM_API_HASH"])
    report = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "limit": args.limit, "horizon_hours": args.horizon_hours, "channels": []}
    async with client:
        for channel in args.channel:
            title, results, stats = await audit_channel(client, parse_fn, channel, args.limit, args.horizon_hours)
            summary = summarize(title, results, stats)
            report["channels"].append({"summary": summary, "calls": [row.__dict__ | {"sent_at": row.sent_at.isoformat().replace("+00:00", "Z")} for row in results]})
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest recent Telegram signal calls against Coinbase candles.")
    parser.add_argument("--supervizor-root", type=Path, default=DEFAULT_SUPERVIZOR_ROOT)
    parser.add_argument("--env", type=Path)
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--channel", action="append", required=True)
    parser.add_argument("--limit", type=int, default=160)
    parser.add_argument("--horizon-hours", type=int, default=72)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
