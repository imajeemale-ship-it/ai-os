#!/usr/bin/env python3
"""Continuously monitor Telegram sources and deliver deduplicated signal alerts.

The app is read-only with respect to Telegram sources and has no broker/exchange
execution code. It reuses the existing Supervizor parser and Telethon session.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sqlite3
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
OUTCOME_RE = re.compile(r"\b(?:TP\s*\d+\s*(?:hit|reached|✅|🎯)|profit\s*[:=]|closed\s+(?:in|with)\s+(?:profit|loss))\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
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
                CREATE TABLE IF NOT EXISTS watch_state (
                    source TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
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
            cursor = db.execute(
                """INSERT OR IGNORE INTO signals
                (source,message_id,sent_at,received_at,ticker,pair,side,entry_json,
                 targets_json,stop_loss,parsed_json,raw_text,dedupe_key,source_url)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (signal.source, signal.message_id, signal.sent_at, utc_now(), ticker,
                 pair, parsed.get("side"), json.dumps(entry), json.dumps(targets),
                 stop_loss, json.dumps(parsed, ensure_ascii=False, sort_keys=True),
                 signal.raw_text, signal.dedupe_key, signal.url),
            )
            return cursor.rowcount == 1

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


def format_alert(row: sqlite3.Row) -> str:
    parsed = json.loads(row["parsed_json"])
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
        "Status: information only · no order placed",
    ]
    if row["source_url"]:
        lines.append(f"Source message: {row['source_url']}")
    if row["raw_text"]:
        excerpt = row["raw_text"].strip()
        lines.extend(["", "Original:", excerpt[:900]])
    message = "\n".join(lines)
    return message[:MAX_ALERT_CHARS]


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
        with urllib.request.urlopen(request, timeout=8) as response:
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
    store = SignalStore(args.db)
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
    parser.add_argument("--chat", action="append", help="Telegram channel/group title, username, or link. Repeat for each.")
    parser.add_argument("--dialog-limit", type=int, default=100)
    parser.add_argument("--backfill", type=int, default=0, help="Import up to N most recent messages per channel before live listening.")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts locally; never send them.")
    parser.add_argument("--once", action="store_true", help="Backfill and exit; useful for testing.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.chat = args.chat or []
    if args.backfill < 0 or args.backfill > 10000:
        parser.error("--backfill must be between 0 and 10000")
    try:
        if args.env is None and not (args.supervizor_root / ".env.telegram").is_file():
            raise FileNotFoundError("Supervizor .env.telegram not found; pass --env or --supervizor-root.")
        if args.chat:
            return asyncio.run(run_watch(args))
        return asyncio.run(list_dialogs(args))
    except KeyboardInterrupt:
        print("Signal Watch stopped.", flush=True)
        return 130
    except Exception as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
