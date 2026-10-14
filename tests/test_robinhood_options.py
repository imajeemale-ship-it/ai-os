import json
import tempfile
import unittest
from pathlib import Path

from ai_os.robinhood_options import (
    OptionQuote,
    PaperAccount,
    PaperPolicy,
    exercise_affordability,
    fixture_quote,
    paper_trade_cycle,
    run_fixture_cycle,
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
