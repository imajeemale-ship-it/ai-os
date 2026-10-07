#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
WATCH_PATH = APP_DIR / "watch.py"
DEFAULT_DB = Path.home() / ".ai-os" / "signal_watch.db"

spec = importlib.util.spec_from_file_location("signal_watch", WATCH_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load {WATCH_PATH}")
watch = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watch
spec.loader.exec_module(watch)


@dataclass
class PaperEvent:
    signal_id: int
    action: str
    ticker: str
    source: str
    price: float
    size_pct: float
    pnl_pct: float
    note: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def coinbase_json(path: str):
    req = urllib.request.Request(
        "https://api.exchange.coinbase.com" + path,
        headers={"User-Agent": "AI-OS Signal Watch paper trader"},
    )
    with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def coinbase_product(ticker: str) -> str | None:
    for quote in ("USD", "USDT", "USDC"):
        product = f"{ticker}-{quote}"
        try:
            coinbase_json(f"/products/{product}")
            return product
        except Exception:
            continue
    return None


def current_price(ticker: str) -> float | None:
    product = coinbase_product(ticker)
    if not product:
        return None
    try:
        data = coinbase_json(f"/products/{product}/ticker")
        return float(data["price"])
    except Exception:
        return None


def init_db(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER NOT NULL UNIQUE,
            source TEXT NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            remaining_pct REAL NOT NULL DEFAULT 100,
            stop_loss REAL,
            targets_json TEXT NOT NULL,
            next_target_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open',
            opened_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT,
            realized_pnl_pct REAL NOT NULL DEFAULT 0,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS paper_events (
            id INTEGER PRIMARY KEY,
            position_id INTEGER NOT NULL,
            signal_id INTEGER NOT NULL,
            event_at TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            size_pct REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status, updated_at);
        """
    )


def parse_entry(row: sqlite3.Row) -> float | None:
    if not row["entry_json"]:
        return None
    try:
        entry = json.loads(row["entry_json"])
    except Exception:
        return None
    if isinstance(entry, dict):
        vals = []
        for key in ("low", "high"):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                vals.append(float(value))
            elif isinstance(value, str):
                try:
                    vals.append(float(value.replace(",", "")))
                except Exception:
                    pass
        return sum(vals) / len(vals) if vals else None
    if isinstance(entry, (int, float)):
        return float(entry)
    return None


def parse_targets(row: sqlite3.Row) -> list[float]:
    try:
        raw = json.loads(row["targets_json"] or "[]")
    except Exception:
        return []
    targets = []
    for value in raw:
        try:
            targets.append(float(str(value).replace(",", "")))
        except Exception:
            pass
    return targets[:4]


def normalized_side(row: sqlite3.Row) -> str:
    side = (row["side"] or "").casefold()
    if side in {"short", "sell"}:
        return "short"
    return "long"


def is_allowed_source(source: str) -> bool:
    policy = watch.source_policy(source)
    return policy["rank"] != "Unranked" and policy["bias"] != "watch-only"


def open_candidates(db: sqlite3.Connection, dry_run: bool) -> list[PaperEvent]:
    rows = db.execute(
        """
        SELECT s.* FROM signals s
        LEFT JOIN paper_positions p ON p.signal_id=s.id
        WHERE p.id IS NULL
          AND s.ticker IS NOT NULL
          AND s.entry_json IS NOT NULL
          AND s.targets_json IS NOT NULL
        ORDER BY s.received_at DESC
        LIMIT 50
        """
    ).fetchall()
    events: list[PaperEvent] = []
    for row in rows:
        if not is_allowed_source(row["source"]):
            continue
        side = normalized_side(row)
        if side == "short":
            continue
        entry = parse_entry(row)
        targets = parse_targets(row)
        if entry is None or not targets:
            continue
        policy = watch.source_policy(row["source"])
        note = f"paper open; {policy['rank']} {policy['bias']}; partial exits at targets"
        events.append(PaperEvent(row["id"], "open", row["ticker"], row["source"], entry, 100, 0, note))
        if dry_run:
            continue
        db.execute(
            """
            INSERT INTO paper_positions
            (signal_id,source,ticker,side,entry_price,remaining_pct,stop_loss,targets_json,opened_at,updated_at,note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (row["id"], row["source"], row["ticker"], side, entry, 100.0, row["stop_loss"], json.dumps(targets), utc_now(), utc_now(), note),
        )
    return events


def update_positions(db: sqlite3.Connection, dry_run: bool) -> list[PaperEvent]:
    positions = db.execute("SELECT * FROM paper_positions WHERE status='open' ORDER BY opened_at").fetchall()
    events: list[PaperEvent] = []
    for pos in positions:
        price = current_price(pos["ticker"])
        if price is None:
            continue
        entry = float(pos["entry_price"])
        remaining = float(pos["remaining_pct"])
        realized = float(pos["realized_pnl_pct"])
        targets = json.loads(pos["targets_json"] or "[]")
        next_idx = int(pos["next_target_index"])
        stop_loss = pos["stop_loss"]
        if stop_loss is not None and price <= float(stop_loss):
            pnl = ((price - entry) / entry) * 100
            weighted = pnl * (remaining / 100)
            note = "paper stop hit"
            events.append(PaperEvent(pos["signal_id"], "stop", pos["ticker"], pos["source"], price, remaining, weighted, note))
            if not dry_run:
                db.execute("UPDATE paper_positions SET status='closed', remaining_pct=0, realized_pnl_pct=?, updated_at=?, closed_at=?, note=? WHERE id=?", (realized + weighted, utc_now(), utc_now(), note, pos["id"]))
                db.execute("INSERT INTO paper_events(position_id,signal_id,event_at,action,price,size_pct,pnl_pct,note) VALUES(?,?,?,?,?,?,?,?)", (pos["id"], pos["signal_id"], utc_now(), "stop", price, remaining, weighted, note))
            continue
        while next_idx < len(targets) and price >= float(targets[next_idx]) and remaining > 0:
            tranche = 25.0 if next_idx < 3 else remaining
            tranche = min(tranche, remaining)
            pnl = ((float(targets[next_idx]) - entry) / entry) * 100
            weighted = pnl * (tranche / 100)
            action = f"tp{next_idx + 1}"
            note = f"paper {action} hit"
            events.append(PaperEvent(pos["signal_id"], action, pos["ticker"], pos["source"], float(targets[next_idx]), tranche, weighted, note))
            remaining -= tranche
            realized += weighted
            next_idx += 1
            if dry_run:
                continue
            db.execute("INSERT INTO paper_events(position_id,signal_id,event_at,action,price,size_pct,pnl_pct,note) VALUES(?,?,?,?,?,?,?,?)", (pos["id"], pos["signal_id"], utc_now(), action, float(targets[next_idx - 1]), tranche, weighted, note))
        if not dry_run:
            status = "closed" if remaining <= 0 else "open"
            db.execute("UPDATE paper_positions SET remaining_pct=?, next_target_index=?, status=?, realized_pnl_pct=?, updated_at=?, closed_at=CASE WHEN ?='closed' THEN ? ELSE closed_at END WHERE id=?", (remaining, next_idx, status, realized, utc_now(), status, utc_now(), pos["id"]))
    return events


def notify_events(events: list[PaperEvent], dry_run: bool) -> None:
    for event in events:
        line = (
            f"Paper trade {event.action.upper()} · {event.ticker} · {event.source}\n"
            f"Price: {event.price:g}\nSize: {event.size_pct:g}%\nP/L contribution: {event.pnl_pct:.2f}%\n{event.note}"
        )
        if dry_run:
            print(line)
        else:
            watch.send_alert(line)


def summary(db: sqlite3.Connection) -> dict[str, Any]:
    open_count = db.execute("SELECT COUNT(*) FROM paper_positions WHERE status='open'").fetchone()[0]
    closed_count = db.execute("SELECT COUNT(*) FROM paper_positions WHERE status='closed'").fetchone()[0]
    pnl = db.execute("SELECT COALESCE(SUM(realized_pnl_pct),0) FROM paper_positions").fetchone()[0]
    return {"open_positions": open_count, "closed_positions": closed_count, "realized_pnl_pct_sum": round(float(pnl), 4)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-trade Signal Watch alerts with TP ladder exits. No broker orders are placed.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-alerts", action="store_true")
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db, timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        init_db(db)
        events = open_candidates(db, args.dry_run)
        events.extend(update_positions(db, args.dry_run))
        if not args.no_alerts:
            notify_events(events, args.dry_run)
        print(json.dumps({"events": len(events), "summary": summary(db)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
