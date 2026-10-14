import json
import tempfile
import unittest
from pathlib import Path

from datetime import datetime
from zoneinfo import ZoneInfo

from ai_os.robinhood_options import (
    AlpacaOptionsDataAdapter,
    MarketDataUnavailable,
    OptionQuote,
    PaperAccount,
    PaperPolicy,
    exercise_affordability,
    fixture_quote,
    market_session,
    paper_trade_cycle,
    run_alpaca_cycle,
    run_fixture_cycle,
    save_cycle_report,
    validate_entry,
)


class RobinhoodOptionsPaperTests(unittest.TestCase):
    def test_valid_fixture_passes_entry_gates(self):
        reasons = validate_entry(fixture_quote(), PaperAccount(buying_power=1000, settled_cash=5000), PaperPolicy())
        self.assertEqual(reasons, [])

    def test_rejects_premium_above_cap(self):
        quote = fixture_quote()
        expensive = OptionQuote(**{**quote.__dict__, "ask": 3.0, "bid": 2.95})
        reasons = validate_entry(expensive, PaperAccount(buying_power=1000, settled_cash=5000), PaperPolicy())
        self.assertIn("premium_above_cap", reasons)

    def test_rejects_wide_spread_and_thin_liquidity(self):
        quote = fixture_quote()
        thin = OptionQuote(**{**quote.__dict__, "bid": 1.0, "ask": 1.5, "volume": 10, "open_interest": 20})
        reasons = validate_entry(thin, PaperAccount(buying_power=1000, settled_cash=5000), PaperPolicy())
        self.assertIn("spread_too_wide", reasons)
        self.assertIn("option_volume_too_low", reasons)
        self.assertIn("open_interest_too_low", reasons)

    def test_exercise_gate_requires_cash_and_blocks_auto_exercise(self):
        gate = exercise_affordability(fixture_quote(), PaperAccount(buying_power=1000, settled_cash=5000))
        self.assertEqual(gate["required_cash"], 59000.0)
        self.assertFalse(gate["affordable"])
        self.assertFalse(gate["auto_exercise_allowed"])

    def test_cycle_writes_durable_jsonl_record(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "paper_trades.jsonl"
            record = run_fixture_cycle(ledger)
            self.assertEqual(record["status"], "filled_and_scored")
            self.assertFalse(record["live_trading_allowed"])
            rows = ledger.read_text().strip().splitlines()
            self.assertEqual(len(rows), 1)
            saved = json.loads(rows[0])
            self.assertEqual(saved["quote"]["source"], "clearly_labeled_test_fixture")
            self.assertEqual(saved["selected_exit_status"], "exit_profit_target")

    def test_cycle_records_rejected_opportunity(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "paper_trades.jsonl"
            quote = fixture_quote()
            rejected = paper_trade_cycle(
                OptionQuote(**{**quote.__dict__, "dte": 4}),
                PaperAccount(buying_power=1000, settled_cash=5000),
                ledger_path=ledger,
            )
            self.assertEqual(rejected["status"], "rejected")
            self.assertIn("dte_outside_primary_window", rejected["entry_rejections"])


if __name__ == "__main__":
    unittest.main()


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RobinhoodOptionsMarketDataTests(unittest.TestCase):
    def test_market_session_only_tracks_options_hours(self):
        eastern = ZoneInfo("America/New_York")
        overnight = market_session(datetime(2026, 10, 14, 2, 0, tzinfo=eastern))
        regular = market_session(datetime(2026, 10, 14, 10, 0, tzinfo=eastern))
        closed = market_session(datetime(2026, 10, 17, 12, 0, tzinfo=eastern))
        self.assertFalse(overnight.options_open)
        self.assertEqual(overnight.reason, "options_market_closed")
        self.assertTrue(regular.options_open)
        self.assertEqual(regular.reason, "regular_options_session")
        self.assertFalse(closed.options_open)

    def test_alpaca_adapter_requires_credentials(self):
        with self.assertRaises(MarketDataUnavailable):
            AlpacaOptionsDataAdapter(key_id="", secret_key="")

    def test_alpaca_adapter_selects_policy_passing_call(self):
        payload = {
            "snapshots": {
                "SPY261030C00590000": {
                    "details": {"type": "call", "strike_price": 590, "expiration_date": "2026-10-30", "dte": 16},
                    "latestQuote": {"bp": 1.42, "ap": 1.5, "t": "2026-10-14T14:35:00Z"},
                    "latestTrade": {"p": 1.46},
                    "greeks": {"delta": 0.36, "gamma": 0.041, "theta": -0.092, "vega": 0.184},
                    "impliedVolatility": 0.218,
                    "volume": 842,
                    "openInterest": 3910,
                    "underlying": {"price": 585.2, "volume": 42100000},
                }
            }
        }
        seen = {}

        def fake_opener(request, timeout):
            seen["url"] = request.full_url
            return FakeResponse(payload)

        adapter = AlpacaOptionsDataAdapter("key", "secret", opener=fake_opener)
        quote = adapter.select_long_call("spy")
        self.assertEqual(quote.symbol, "SPY")
        self.assertEqual(quote.premium, 150.0)
        self.assertIn("/v1beta1/options/snapshots/SPY", seen["url"])

    def test_real_data_cycle_blocks_outside_options_hours_before_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "paper_trades.jsonl"
            record = run_alpaca_cycle("SPY", ledger)
            if record["status"] == "rejected":
                self.assertFalse(record["live_trading_allowed"])
                self.assertEqual(record["entry_rejections"][0], "options_market_closed")

    def test_save_cycle_report_writes_morning_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "latest.md"
            record = run_fixture_cycle(Path(directory) / "ledger.jsonl")
            record["morning_summary"] = "Fixture bought because gates passed."
            record["sell_plan"] = "Sell at +30% or cut at -20%."
            path = save_cycle_report(record, report)
            contents = path.read_text()
            self.assertIn("WHY", contents)
            self.assertIn("WHEN TO SELL", contents)

    def test_report_makes_watchlist_budget_realistic(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "latest.md"
            record = run_fixture_cycle(Path(directory) / "ledger.jsonl")
            record["symbols_checked"] = ["SPY", "QQQ", "AAPL"]
            path = save_cycle_report(record, report)
            contents = path.read_text()
            self.assertIn("Candidate symbols checked: SPY, QQQ, AAPL", contents)
            self.assertIn("buy at most one contract total", contents)
            self.assertIn("Budget after selected contract", contents)
