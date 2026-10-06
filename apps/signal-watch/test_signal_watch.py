"""Focused tests for Signal Watch parsing, deduplication, and alerts."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("signal_watch", APP / "watch.py")
watch = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = watch
SPEC.loader.exec_module(watch)


class SignalWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = watch.SignalStore(Path(self.temp.name) / "signals.db")

    def tearDown(self):
        self.temp.cleanup()

    def make_signal(self, message_id=101, source="Sample Signals", text=None):
        raw = text or "#BTC Long\nEntry: 65000 - 65100\nTargets: 66000, 67000\nStop Loss: 64000"
        parsed = {
            "pair": "BTC/USDT",
            "side": "buy",
            "entry": {"low": 65000, "high": 65100},
            "targets": [66000, 67000],
            "stop_loss": 64000,
            "leverage_detected": False,
        }
        return watch.Signal(source, message_id, "2026-10-06T12:00:00Z", raw, parsed,
                            f"hash-{message_id}", "https://t.me/sample/101")

    def test_persists_ticker_and_merges_repeated_signal(self):
        signal = self.make_signal()
        self.assertTrue(self.db.add(signal))
        self.assertFalse(self.db.add(signal))
        row = self.db.pending()[0]
        self.assertEqual(row["ticker"], "BTC")
        self.assertEqual(row["side"], "buy")
        self.assertEqual(json.loads(row["targets_json"]), [66000, 67000])
        self.assertIn("BTC", watch.format_alert(row))
        self.assertIn("no order placed", watch.format_alert(row))

    def test_duplicate_text_merges_across_sources(self):
        first = self.make_signal(message_id=1, source="A")
        second = self.make_signal(message_id=2, source="B")
        second = watch.Signal(second.source, second.message_id, second.sent_at, second.raw_text,
                              second.parsed, first.dedupe_key, second.url)
        self.assertTrue(self.db.add(first))
        self.assertFalse(self.db.add(second))

    def test_ticker_fallbacks(self):
        self.assertEqual(self.db.ticker({}, "Accumulation zone on $TAC is 0.0137"), "TAC")
        self.assertEqual(self.db.ticker({}, "Buy BTC/USDT now"), "BTC")
        self.assertEqual(self.db.ticker({}, "#JTO short entry"), "JTO")

    def test_candidate_filter_excludes_outcomes_and_teasers(self):
        self.assertFalse(watch.is_signal_candidate("TP 4 ✅ Profit: +40.2%"))
        self.assertFalse(watch.is_signal_candidate("We will post a buy signal in a few minutes"))
        self.assertTrue(watch.is_signal_candidate("#BTC Open Long Entry: 60000"))

    def test_risk_flags_are_actionable(self):
        parsed = {"side": "short", "targets": [], "stop_loss": None,
                  "leverage_detected": True, "dca_levels": [1, 2]}
        flags = watch.risk_flags(parsed, "2026-10-01T12:00:00Z")
        self.assertTrue(any("LEVERAGE" in flag for flag in flags))
        self.assertTrue(any("SHORT" in flag for flag in flags))
        self.assertTrue(any("STOP LOSS" in flag for flag in flags))
        self.assertTrue(any("STALE" in flag for flag in flags))
        self.assertTrue(any("DCA" in flag for flag in flags))

    def test_delivery_fails_closed_without_bot_configuration(self):
        saved = {key: os.environ.pop(key, None)
                 for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
        try:
            sent, error = watch.send_alert("test", dry_run=False)
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
        self.assertFalse(sent)
        self.assertEqual(error, "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")


if __name__ == "__main__":
    unittest.main()
