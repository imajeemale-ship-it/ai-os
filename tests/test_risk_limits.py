import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_os.risk_limits import risk_limits_draft, render_risk_limits_draft, save_risk_limits_draft, validate_risk_limits


class RiskLimitsTests(unittest.TestCase):
    def test_draft_stays_locked_and_lists_missing_limits(self):
        report = risk_limits_draft(date(2026, 10, 12))
        rendered = render_risk_limits_draft(report)
        self.assertFalse(report["execution_allowed"])
        self.assertIn("starting_capital_usd: TBD", rendered)
        self.assertIn("validation_ready: false", rendered)

    def test_validation_requires_all_fields_and_positive_numbers(self):
        limits = risk_limits_draft()["limits"]
        limits.update({
            "starting_capital_usd": 100,
            "max_daily_loss_usd": 10,
            "max_weekly_loss_usd": 25,
            "max_position_size_usd": 20,
            "max_open_positions": 1,
            "max_trades_per_day": 2,
            "cooldown_after_loss_minutes": 60,
            "kill_switch_trigger": "Stop for the day after max daily loss.",
        })
        result = validate_risk_limits(limits)
        self.assertTrue(result["passed"])
        self.assertFalse(result["execution_allowed"])

    def test_save_risk_limits_draft_creates_daily_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_risk_limits_draft(Path(directory), date(2026, 10, 12))
            self.assertEqual(path.name, "2026-10-12-risk-limits-draft.md")
            self.assertIn("LIVE TRADING RISK LIMITS DRAFT", path.read_text())


if __name__ == "__main__":
    unittest.main()
