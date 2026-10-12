"""Focused tests for Signal Watch parsing, deduplication, and alerts."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
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

    def make_signal(self, message_id=101, source="Sample Signals", text=None,
                    sent_at="2026-10-06T12:00:00Z", side="buy"):
        raw = text or f"#BTC {'Long' if side == 'buy' else 'Short'}\nEntry: 65000 - 65100\nTargets: 66000, 67000\nStop Loss: 64000"
        parsed = {
            "pair": "BTC/USDT",
            "side": side,
            "entry": {"low": 65000, "high": 65100},
            "targets": [66000, 67000],
            "stop_loss": 64000,
            "leverage_detected": False,
        }
        return watch.Signal(source, message_id, sent_at, raw, parsed,
                            f"hash-{message_id}", "https://t.me/sample/101")

    @staticmethod
    def market_context():
        return {
            "available": True,
            "as_of": "2026-10-06T12:00:00Z",
            "btc_trend": "up",
            "btc_above_ema200": True,
            "btc_24h_change_pct": 4.0,
            "market_volatility": "medium",
            "market_volatility_pct": 3.0,
            "fear_greed_index": 60,
            "fear_greed_label": "Greed",
            "trading_session": "London",
            "day_of_week": "Tuesday",
        }

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

    def test_persists_explainable_conviction_fields(self):
        signal = self.make_signal(source="Wallstreet Queen Official®")
        self.assertTrue(self.db.add(signal))
        row = self.db.pending()[0]
        self.assertIsNotNone(row["conviction_score"])
        self.assertIn(row["confidence_level"], {"LOW", "MEDIUM", "HIGH"})
        reasons = json.loads(row["conviction_reasons_json"])
        self.assertTrue(reasons)
        alert = watch.format_alert(row)
        self.assertIn("Conviction:", alert)
        self.assertIn("Conviction reasons:", alert)
        self.assertIn("Consensus:", alert)
        self.assertIn("Decision:", alert)
        self.assertIn(row["decision"], {"APPROVE", "WATCH", "REJECT"})
        self.assertIsNotNone(row["decision_explanation"])
        self.assertTrue(
            json.loads(row["blocking_reasons_json"])
            or json.loads(row["supporting_reasons_json"])
        )

    def test_market_context_contributes_to_conviction_and_is_persisted(self):
        store = watch.SignalStore(
            Path(self.temp.name) / "market.db",
            market_context_provider=self.market_context,
        )
        signal = self.make_signal(source="Wallstreet Queen Official®", sent_at=watch.utc_now())
        self.assertTrue(store.add(signal))
        row = store.pending()[0]
        context = json.loads(row["market_context_json"])
        self.assertTrue(context["available"])
        self.assertGreater(context["market_context_score"], 75)
        reasons = json.loads(row["conviction_reasons_json"])
        self.assertTrue(any("Market context: BTC trend up" in reason for reason in reasons))
        self.assertIn("Market context:", watch.format_alert(row))

    def test_decision_engine_returns_complete_approve_object(self):
        with self.db.connect() as db:
            signal = self.make_signal(source="Wallstreet Queen Official®", sent_at=watch.utc_now())
            decision = watch.calculate_decision(
                db, signal.source, signal.parsed, signal.sent_at, "BTC",
                signal.parsed["entry"], signal.parsed["targets"], signal.parsed["stop_loss"],
                {"conviction_score": 90.0},
                {"consensus_score": 100.0, "number_of_channels": 2,
                 "agreeing_channels": ["A", "B"], "disagreeing_channels": []},
                self.market_context() | {"market_context_score": 90.0},
            )
        self.assertEqual(decision["decision"], "APPROVE")
        self.assertEqual(decision["position_size_recommendation"], "MEDIUM")
        self.assertGreater(decision["overall_score"], 75)
        self.assertEqual(decision["maximum_risk_percent"], 0.5)
        self.assertTrue(decision["supporting_reasons"])
        self.assertEqual(decision["blocking_reasons"], [])

    def test_decision_engine_rejects_without_market_context(self):
        with self.db.connect() as db:
            signal = self.make_signal(source="Wallstreet Queen Official®", sent_at=watch.utc_now())
            decision = watch.calculate_decision(
                db, signal.source, signal.parsed, signal.sent_at, "BTC",
                signal.parsed["entry"], signal.parsed["targets"], signal.parsed["stop_loss"],
                {"conviction_score": 90.0},
                {"consensus_score": 100.0, "number_of_channels": 2,
                 "agreeing_channels": ["A", "B"], "disagreeing_channels": []},
                watch.unavailable_market_context("test outage"),
            )
        self.assertEqual(decision["decision"], "REJECT")
        self.assertEqual(decision["position_size_recommendation"], "NONE")
        self.assertEqual(decision["maximum_risk_percent"], 0.0)
        self.assertTrue(any("Market context unavailable" in reason for reason in decision["blocking_reasons"]))

    def test_market_context_fails_closed_when_unavailable(self):
        result = watch.score_market_context({"side": "buy"}, watch.unavailable_market_context("test outage"))
        self.assertEqual(result["market_context_score"], 0.0)
        self.assertIn("fail-closed", result["warnings"][0])

    def test_market_context_uses_fresh_local_cache(self):
        cache = Path(self.temp.name) / "market_context.json"
        payload = self.market_context()
        cache.write_text(json.dumps(payload), encoding="utf-8")
        result = watch.fetch_market_context(
            cache,
            now=watch.datetime.fromisoformat("2026-10-06T12:04:00+00:00"),
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["cache_source"], "local_cache")

    def test_consensus_groups_agreeing_channels_within_configured_window(self):
        store = watch.SignalStore(Path(self.temp.name) / "consensus.db", consensus_window_minutes=120)
        first = self.make_signal(message_id=1, source="Channel A")
        second = self.make_signal(message_id=2, source="Channel B", sent_at="2026-10-06T13:00:00Z")
        self.assertTrue(store.add(first))
        self.assertTrue(store.add(second))
        rows = store.pending(limit=10)
        latest = next(row for row in rows if row["message_id"] == 2)
        self.assertEqual(latest["number_of_channels"], 2)
        self.assertEqual(json.loads(latest["agreeing_channels_json"]), ["Channel A", "Channel B"])
        self.assertEqual(json.loads(latest["disagreeing_channels_json"]), [])
        self.assertEqual(latest["consensus_score"], 100.0)
        self.assertEqual(latest["consensus_first_seen"], "2026-10-06T12:00:00Z")
        self.assertEqual(latest["consensus_latest_seen"], "2026-10-06T13:00:00Z")

    def test_consensus_records_disagreement_and_updates_conviction(self):
        store = watch.SignalStore(Path(self.temp.name) / "consensus.db", consensus_window_minutes=120)
        self.assertTrue(store.add(self.make_signal(message_id=1, source="Channel A")))
        self.assertTrue(store.add(self.make_signal(message_id=2, source="Channel B", side="short",
                                                   sent_at="2026-10-06T13:00:00Z")))
        row = next(row for row in store.pending(limit=10) if row["message_id"] == 2)
        self.assertEqual(row["number_of_channels"], 2)
        self.assertEqual(json.loads(row["agreeing_channels_json"]), ["Channel B"])
        self.assertEqual(json.loads(row["disagreeing_channels_json"]), ["Channel A"])
        self.assertEqual(row["consensus_score"], 50.0)
        self.assertTrue(any("Consensus: 50.0/100" in reason for reason in json.loads(row["conviction_reasons_json"])))

    def test_consensus_starts_new_group_outside_window(self):
        store = watch.SignalStore(Path(self.temp.name) / "consensus.db", consensus_window_minutes=60)
        self.assertTrue(store.add(self.make_signal(message_id=1, source="Channel A")))
        self.assertTrue(store.add(self.make_signal(message_id=2, source="Channel B", sent_at="2026-10-06T14:01:00Z")))
        rows = store.pending(limit=10)
        latest = next(row for row in rows if row["message_id"] == 2)
        self.assertEqual(latest["number_of_channels"], 1)
        self.assertEqual(latest["consensus_score"], 50.0)
        self.assertNotEqual(rows[0]["consensus_group_id"], latest["consensus_group_id"])

    def test_consensus_window_must_be_positive(self):
        with self.assertRaises(ValueError):
            watch.SignalStore(Path(self.temp.name) / "invalid.db", consensus_window_minutes=0)

    def test_conviction_uses_historical_results_and_duplicate_agreement(self):
        with self.db.connect() as db:
            db.execute(
                """CREATE TABLE paper_positions (
                id INTEGER PRIMARY KEY, source TEXT, status TEXT,
                realized_pnl_pct REAL)"""
            )
            db.executemany(
                "INSERT INTO paper_positions(source,status,realized_pnl_pct) VALUES(?,?,?)",
                [("Wallstreet Queen Official®", "closed", 5.0),
                 ("Wallstreet Queen Official®", "closed", -1.0)],
            )
        first = self.make_signal(message_id=1, source="Technical CRYPTO Analyst")
        self.assertTrue(self.db.add(first))
        second = self.make_signal(message_id=2, source="Wallstreet Queen Official®")
        self.assertTrue(self.db.add(second))
        row = self.db.pending(limit=10)[-1]
        reasons = json.loads(row["conviction_reasons_json"])
        self.assertTrue(any("Channel history" in reason for reason in reasons))
        self.assertTrue(any("Consensus:" in reason for reason in reasons))

    def test_paper_pipeline_skips_low_conviction_signal(self):
        paper_spec = importlib.util.spec_from_file_location(
            "paper_trade_signals_test", APP / "scripts" / "paper_trade_signals.py"
        )
        paper = importlib.util.module_from_spec(paper_spec)
        assert paper_spec and paper_spec.loader
        sys.modules[paper_spec.name] = paper
        paper_spec.loader.exec_module(paper)
        with self.db.connect() as db:
            paper.init_db(db)
            db.executemany(
                """INSERT INTO paper_positions
                (signal_id,source,ticker,side,entry_price,targets_json,status,opened_at,updated_at,realized_pnl_pct)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [(9001, "Wallstreet Queen Official®", "BTC", "long", 65000, "[66000]", "closed", watch.utc_now(), watch.utc_now(), -10.0),
                 (9002, "Wallstreet Queen Official®", "ETH", "long", 3000, "[3100]", "closed", watch.utc_now(), watch.utc_now(), -10.0)],
            )
        signal = self.make_signal(source="Wallstreet Queen Official®")
        signal = watch.Signal(signal.source, signal.message_id, watch.utc_now(), signal.raw_text,
                              signal.parsed, signal.dedupe_key, signal.url)
        self.assertTrue(self.db.add(signal))
        with self.db.connect() as db:
            events = paper.open_candidates(db, dry_run=True)
        self.assertEqual(events, [])

    def test_paper_pipeline_stores_market_context(self):
        paper_spec = importlib.util.spec_from_file_location(
            "paper_trade_signals_context_test", APP / "scripts" / "paper_trade_signals.py"
        )
        paper = importlib.util.module_from_spec(paper_spec)
        assert paper_spec and paper_spec.loader
        sys.modules[paper_spec.name] = paper
        paper_spec.loader.exec_module(paper)
        path = Path(self.temp.name) / "paper-context.db"
        store = watch.SignalStore(path, market_context_provider=self.market_context)
        with store.connect() as db:
            paper.init_db(db)
        signal = self.make_signal(source="Wallstreet Queen Official®", sent_at=watch.utc_now())
        self.assertTrue(store.add(signal))
        with store.connect() as db:
            events = paper.open_candidates(db, dry_run=False)
            position = db.execute("SELECT market_context_json FROM paper_positions").fetchone()
        self.assertEqual(len(events), 1)
        self.assertTrue(json.loads(position[0])["available"])

    def test_closed_paper_trade_appends_learning_observation_once(self):
        paper_spec = importlib.util.spec_from_file_location(
            "paper_trade_signals_learning_test", APP / "scripts" / "paper_trade_signals.py"
        )
        paper = importlib.util.module_from_spec(paper_spec)
        assert paper_spec and paper_spec.loader
        sys.modules[paper_spec.name] = paper
        paper_spec.loader.exec_module(paper)
        path = Path(self.temp.name) / "learning.db"
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            paper.init_db(db)
            context = self.market_context() | {"market_context_score": 70.0}
            db.execute(
                """INSERT INTO paper_positions
                (signal_id,source,ticker,side,entry_price,remaining_pct,targets_json,status,opened_at,updated_at,
                 predicted_conviction,predicted_decision,predicted_overall_score,predicted_consensus_score,
                 predicted_market_context_score,market_context_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (7, "Wallstreet Queen Official®", "BTC", "long", 100.0, 100.0,
                 "[110,120,130,140]", "open", "2026-10-06T12:00:00Z", "2026-10-06T12:00:00Z",
                 80.0, "APPROVE", 85.0, 80.0, 70.0, json.dumps(context)),
            )
            paper.current_price = lambda ticker: 140.0
            events = paper.update_positions(db, dry_run=False)
            self.assertEqual(len(events), 4)
            observation = db.execute("SELECT * FROM learning_observations").fetchone()
            self.assertIsNotNone(observation)
            self.assertEqual(observation["outcome"], "WIN")
            self.assertAlmostEqual(observation["prediction_error"], -20.0)
            self.assertAlmostEqual(observation["calibration_score"], 80.0)
            self.assertEqual(observation["decision_correct"], 1)
            self.assertEqual(observation["consensus_effective"], 1)
            self.assertIn("up|above_ema200|medium|London|Greed", observation["market_context_key"])
            self.assertFalse(paper.record_learning_observation(db, 1))

            report_spec = importlib.util.spec_from_file_location(
                "report_learning_test", APP / "scripts" / "report_learning.py"
            )
            report = importlib.util.module_from_spec(report_spec)
            assert report_spec and report_spec.loader
            report_spec.loader.exec_module(report)
            result = report.build_report(db)
            self.assertEqual(result["observations"], 1)
            self.assertEqual(result["decision_accuracy_pct"], 100.0)
            self.assertEqual(result["calibration_score"], 80.0)
            self.assertEqual(result["channels"][0]["channel"], "Wallstreet Queen Official®")
            self.assertIn("Calibration score", report.render_markdown(result))

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

    def test_alert_includes_source_trade_plan(self):
        signal = self.make_signal(source="Wallstreet Queen Official®")
        self.assertTrue(self.db.add(signal))
        alert = watch.format_alert(self.db.pending()[0])
        self.assertIn("Source rank: Tier 1", alert)
        self.assertIn("Exit plan: take partial profit around +3%", alert)
        self.assertIn("Timeout:", alert)

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

    def test_paper_eligibility_accepts_fresh_spot_signal(self):
        result = watch.paper_eligibility(
            "Wallstreet Queen Official®",
            {"side": "buy"},
            "2026-10-06T11:00:00Z",
            65000,
            [66000, 67000],
            64000,
            now=watch.datetime.fromisoformat("2026-10-06T12:00:00+00:00"),
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["reasons"], [])

    def test_paper_eligibility_rejects_risky_or_stale_signal(self):
        result = watch.paper_eligibility(
            "Crypto Best Futures Signals",
            {"side": "buy", "leverage_detected": True, "dca_levels": [65000]},
            "2026-10-06T01:00:00Z",
            65000,
            [66000, 67000],
            None,
            now=watch.datetime.fromisoformat("2026-10-06T12:00:00+00:00"),
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(
            result["reasons"],
            ["LEVERAGE_OR_DERIVATIVES", "DCA_NOT_SUPPORTED", "MISSING_STOP_LOSS", "STALE_SIGNAL"],
        )

    def test_paper_eligibility_rejects_invalid_ladder(self):
        result = watch.paper_eligibility(
            "Wallstreet Queen Official®",
            {"side": "buy"},
            "2026-10-06T11:00:00Z",
            65000,
            [64000, 67000, 66000],
            66000,
            now=watch.datetime.fromisoformat("2026-10-06T12:00:00+00:00"),
        )
        self.assertFalse(result["eligible"])
        self.assertIn("STOP_NOT_BELOW_ENTRY", result["reasons"])
        self.assertIn("TARGET_NOT_ABOVE_ENTRY", result["reasons"])
        self.assertIn("TARGETS_NOT_ASCENDING", result["reasons"])

    def test_paper_eligibility_fails_closed_on_malformed_prices(self):
        result = watch.paper_eligibility(
            "Wallstreet Queen Official®",
            {"side": "buy"},
            "2026-10-06T11:00:00Z",
            "not-a-price",
            ["also-not-a-price"],
            "not-a-stop",
            now=watch.datetime.fromisoformat("2026-10-06T12:00:00+00:00"),
        )
        self.assertFalse(result["eligible"])
        self.assertIn("INVALID_ENTRY", result["reasons"])
        self.assertIn("MISSING_STOP_LOSS", result["reasons"])
        self.assertIn("MISSING_TARGETS", result["reasons"])


if __name__ == "__main__":
    unittest.main()
