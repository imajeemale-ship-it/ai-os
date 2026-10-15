import json
import tempfile
import unittest
from pathlib import Path

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ai_os.robinhood_options import (
    AlpacaOptionsDataAdapter,
    MarketDataUnavailable,
    OptionQuote,
    PaperAccount,
    PaperPolicy,
    RobinhoodMCPDataAdapter,
    exercise_affordability,
    fixture_quote,
    latest_open_position,
    market_session,
    paper_trade_cycle,
    run_alpaca_cycle,
    run_fixture_cycle,
    due_diligence_score,
    rank_candidates,
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

    def test_rejects_estimated_fill_above_total_budget(self):
        quote = fixture_quote()
        near_cap = OptionQuote(**{**quote.__dict__, "bid": 2.40, "ask": 2.45})
        reasons = validate_entry(near_cap, PaperAccount(buying_power=1000, settled_cash=5000), PaperPolicy())
        self.assertIn("estimated_fill_above_premium_cap", reasons)

    def test_rejects_stale_real_market_quote(self):
        quote = fixture_quote()
        stale = OptionQuote(**{**quote.__dict__, "quote_time": "2020-01-01T00:00:00Z", "source": "alpaca_options_chain:test"})
        reasons = validate_entry(stale, PaperAccount(buying_power=1000, settled_cash=5000), PaperPolicy())
        self.assertIn("quote_stale", reasons)

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

    def test_position_state_opens_and_closes_from_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "paper_trades.jsonl"
            opened = run_fixture_cycle(ledger)
            self.assertEqual(latest_open_position(ledger)["order"], opened["order"])
            with ledger.open("a") as handle:
                handle.write(json.dumps({"record_type": "paper_position_monitor", "status": "closed"}) + "\n")
            self.assertIsNone(latest_open_position(ledger))

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

    def test_robinhood_adapter_blocks_order_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(json.dumps({
                "robinhood-trading|test": {
                    "server_name": "robinhood-trading",
                    "access_token": "test-token",
                    "expires_at": 4070908800,
                }
            }))
            adapter = RobinhoodMCPDataAdapter(credentials_path=credentials)
            with self.assertRaisesRegex(MarketDataUnavailable, "robinhood_mcp_tool_not_allowed"):
                adapter._tool("place_option_order", {})

    def test_robinhood_adapter_rejects_expired_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(json.dumps({
                "robinhood-trading|test": {
                    "server_name": "robinhood-trading",
                    "access_token": "expired-token",
                    "expires_at": 1577836800,
                }
            }))
            with self.assertRaisesRegex(MarketDataUnavailable, "robinhood_mcp_credentials_expired"):
                RobinhoodMCPDataAdapter(credentials_path=credentials)

    def test_robinhood_long_call_requires_positive_momentum(self):
        adapter = object.__new__(RobinhoodMCPDataAdapter)
        adapter.directional_signals = {}
        adapter._tool = lambda name, args: {"data": {"results": [{"quote": {
            "last_trade_price": "101.00",
            "venue_last_trade_time": "2026-10-15T14:00:00Z",
            "previous_close": "100.00",
        }}]}}
        self.assertEqual(adapter._underlying_price("TEST"), 101.0)
        self.assertAlmostEqual(adapter.directional_signals["TEST"]["change_pct"], 0.01)
        adapter._tool = lambda name, args: {"data": {"results": [{"quote": {
            "last_trade_price": "99.00",
            "venue_last_trade_time": "2026-10-15T14:00:00Z",
            "previous_close": "100.00",
        }}]}}
        with self.assertRaisesRegex(MarketDataUnavailable, "momentum_too_weak"):
            adapter._underlying_price("TEST")

    def test_robinhood_strategy_context_detects_breakout(self):
        adapter = object.__new__(RobinhoodMCPDataAdapter)
        adapter.strategy_contexts = {}
        start = datetime.now(timezone.utc) - timedelta(days=70)
        bars = []
        for index in range(60):
            price = 100.0 + index
            bars.append({
                "begins_at": (start + timedelta(days=index)).isoformat(),
                "open_price": str(price - 0.5),
                "high_price": str(price + 1),
                "low_price": str(price - 1),
                "close_price": str(price),
                "volume": 1000000,
                "interpolated": False,
            })
        adapter._tool = lambda name, args: {"data": {"results": [{"bars": bars}]}}
        context = adapter._strategy_context("TEST", 170.0)
        self.assertTrue(context["breakout_continuation"])
        self.assertTrue(context["established_uptrend"])

    def test_alpaca_adapter_selects_policy_passing_call(self):
        payload = {
            "snapshots": {
                "SPY261030C00590000": {
                    "details": {"type": "call", "strike_price": 590, "expiration_date": "2026-10-30", "dte": 16},
                    "latestQuote": {"bp": 1.42, "ap": 1.5, "t": datetime.now(timezone.utc).isoformat()},
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
                self.assertIn(record["entry_rejections"][0], {"options_market_closed", "missing_alpaca_market_data_credentials"})

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

    def test_due_diligence_ranks_best_candidate_not_first_candidate(self):
        base = fixture_quote()
        weak = OptionQuote(**{**base.__dict__, "symbol": "SPY", "bid": 1.70, "ask": 2.05, "volume": 80, "open_interest": 150, "delta": 0.15})
        strong = OptionQuote(**{**base.__dict__, "symbol": "QQQ", "bid": 1.69, "ask": 1.75, "volume": 2000, "open_interest": 7000, "delta": 0.35, "dte": 14})
        ranked = rank_candidates([weak, strong])
        self.assertEqual(ranked[0]["quote"].symbol, "QQQ")
        self.assertGreater(due_diligence_score(strong)["score"], due_diligence_score(weak)["score"])

    def test_report_includes_due_diligence_and_top_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "latest.md"
            record = run_fixture_cycle(Path(directory) / "ledger.jsonl")
            record["due_diligence"] = due_diligence_score(fixture_quote())
            record["candidate_rankings"] = [record["due_diligence"]]
            path = save_cycle_report(record, report)
            contents = path.read_text()
            self.assertIn("DUE DILIGENCE", contents)
            self.assertIn("TOP CANDIDATES", contents)
