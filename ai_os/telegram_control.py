"""Authorized two-way Telegram control for the paper options agent."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ai_os.robinhood_options import latest_open_position, send_telegram_alert

ROOT = Path.home() / ".ai-os" / "robinhood-options"
OFFSET_FILE = ROOT / "telegram_offset.json"
PAUSE_FILE = ROOT / "PAPER_ENTRIES_PAUSED"
LEDGERS = {
    "primary": ROOT / "paper_trades.jsonl",
    "tactical": ROOT / "tactical_trades.jsonl",
    "core": ROOT / "core_trend_trades.jsonl",
}


def command_kind(text: str) -> str:
    value = text.strip().lower()
    if value.startswith("/status") or value in {"status", "update", "positions"}:
        return "status"
    if value.startswith("/why") or "why" in value:
        return "why"
    if value.startswith("/pause") or value in {"pause", "stop", "stop trading"}:
        return "pause"
    if value.startswith("/resume") or value in {"resume", "start", "continue"}:
        return "resume"
    if any(word in value for word in ("buy", "sell", "live", "exercise")):
        return "blocked_trade"
    return "help"


def _last_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def status_message() -> str:
    lines = [f"PAPER AGENT STATUS: {'PAUSED' if PAUSE_FILE.exists() else 'ACTIVE'}"]
    for name, path in LEDGERS.items():
        position = latest_open_position(path)
        if position:
            quote = position.get("quote") or {}
            order = position.get("order") or {}
            lines.append(
                f"{name}: OPEN {quote.get('symbol')} {quote.get('expiration')} "
                f"{quote.get('strike')}C, cost ${order.get('total_cost')}"
            )
        else:
            lines.append(f"{name}: no open position")
    lines.append("Live trading: BLOCKED")
    return "\n".join(lines)


def why_message() -> str:
    events = []
    for name, path in LEDGERS.items():
        record = _last_record(path)
        if not record:
            continue
        if record.get("status") == "filled_and_scored":
            quote = record.get("quote") or {}
            matches = ", ".join(record.get("strategy_matches") or ["ranked due diligence"])
            events.append(f"{name}: bought {quote.get('symbol')} because {matches}.")
        else:
            reasons = ", ".join(record.get("entry_rejections") or [record.get("status", "unknown")])
            events.append(f"{name}: no new trade because {reasons}.")
    return "\n".join(events) or "No paper-trading decision has been recorded yet."


def handle_command(text: str) -> str:
    kind = command_kind(text)
    if kind == "status":
        return status_message()
    if kind == "why":
        return why_message()
    if kind == "pause":
        ROOT.mkdir(parents=True, exist_ok=True)
        PAUSE_FILE.write_text("paused_by_authorized_telegram_user\n", encoding="utf-8")
        return "New paper entries paused. Existing paper positions will still be monitored."
    if kind == "resume":
        PAUSE_FILE.unlink(missing_ok=True)
        return "Paper entries resumed. Live trading remains blocked."
    if kind == "blocked_trade":
        return "I cannot place live trades, exercise options, or enable live trading from Telegram."
    return "Reply with: status, why, pause, or resume. This bot controls paper trading only."


def _updates(token: str, offset: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"offset": offset, "timeout": 25, "allowed_updates": json.dumps(["message"])})
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates?{query}", timeout=35) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("result") or []


def run_forever() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    authorized_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not authorized_chat:
        raise RuntimeError("missing Telegram credentials")
    ROOT.mkdir(parents=True, exist_ok=True)
    offset = 0
    if OFFSET_FILE.exists():
        offset = int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    while True:
        try:
            for update in _updates(token, offset):
                offset = int(update["update_id"]) + 1
                OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")
                message = update.get("message") or {}
                chat_id = str((message.get("chat") or {}).get("id", ""))
                text = str(message.get("text") or "")
                if chat_id != authorized_chat or not text:
                    continue
                send_telegram_alert(handle_command(text))
        except Exception:
            time.sleep(5)


if __name__ == "__main__":
    run_forever()
