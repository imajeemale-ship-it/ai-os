"""Broad-market regime alerts for paper-only opportunity monitoring."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from ai_os.robinhood_options import append_ledger, send_telegram_alert, utc_now

ROOT = Path.home() / ".ai-os" / "robinhood-options"
STATE = ROOT / "market_regime.json"
ALERTS = ROOT / "market_regime_alerts.jsonl"
BROAD_SYMBOLS = {"SPY", "QQQ", "DIA", "IWM"}

def assess_market_regime(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    broad = {s: signals[s] for s in BROAD_SYMBOLS if s in signals}
    watch = list(signals.values())
    red_broad = [s for s, v in broad.items() if float(v.get("change_pct", 0)) <= -0.005]
    red_watch = [v for v in watch if float(v.get("change_pct", 0)) < 0]
    broad_red = len(red_broad) >= 3
    severity = "severe" if len([s for s, v in broad.items() if float(v.get("change_pct", 0)) <= -0.01]) >= 3 else ("broad_red" if broad_red else "normal")
    return {
        "record_type": "market_regime_snapshot",
        "created_at": utc_now(),
        "broad_symbols_seen": sorted(broad),
        "red_broad_symbols": sorted(red_broad),
        "red_watchlist_count": len(red_watch),
        "watchlist_count": len(watch),
        "broad_red": broad_red,
        "severity": severity,
        "signals": signals,
    }

def monitor_market_regime(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    snapshot = assess_market_regime(signals)
    previous = {}
    if STATE.exists():
        try: previous = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): previous = {}
    event = None
    if snapshot["broad_red"] and not previous.get("broad_red"):
        event = "red_market"
        message = (
            f"ROBINHOOD PAPER ALERT: broad red market detected ({snapshot['severity']}). "
            f"Red indexes: {', '.join(snapshot['red_broad_symbols'])}. "
            "No automatic buy. Recovery watchlist activated."
        )
    elif previous.get("broad_red") and not snapshot["broad_red"]:
        event = "recovery_watch"
        message = (
            "ROBINHOOD PAPER ALERT: broad-market recovery conditions detected. "
            "Review recovery candidates; confirmation is still required before any paper entry."
        )
    if event:
        alert = {**snapshot, "event": event}
        append_ledger(alert, ALERTS)
        send_telegram_alert(message)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    return {**snapshot, "event": event}
