import tempfile
import unittest
from datetime import date
from pathlib import Path

from ai_os.trading_policy import live_policy_draft, render_live_policy_draft, save_live_policy_draft


class TradingPolicyTests(unittest.TestCase):
    def test_policy_draft_is_locked_and_requires_decisions(self):
        policy = live_policy_draft(date(2026, 10, 12))
        rendered = render_live_policy_draft(policy)
        self.assertFalse(policy["execution_allowed"])
        self.assertFalse(policy["trading_allowed"])
        self.assertIn("Maximum daily loss", rendered)
        self.assertIn("approval_status: not_approved", rendered)
        self.assertIn("No live orders", rendered)

    def test_save_policy_draft_creates_daily_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_live_policy_draft(Path(directory), date(2026, 10, 12))
            self.assertEqual(path.name, "2026-10-12-live-trading-policy-draft.md")
            self.assertIn("LIVE TRADING POLICY DRAFT", path.read_text())


if __name__ == "__main__":
    unittest.main()
