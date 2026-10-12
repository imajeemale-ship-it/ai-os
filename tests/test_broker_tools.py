import unittest

from ai_os.broker_tools import classify_broker_tool, classify_broker_tools, render_broker_tool_classification


class BrokerToolClassificationTests(unittest.TestCase):
    def test_execution_tools_are_critical_and_never_allowed(self):
        row = classify_broker_tool("place_order", "Buy BTC with market order")
        self.assertEqual(row["category"], "execution_or_money_movement")
        self.assertEqual(row["risk"], "critical")
        self.assertFalse(row["allowed_for_live_trading"])

    def test_read_only_tools_are_sensitive_and_never_execution_allowed(self):
        row = classify_broker_tool("get_positions", "Read account portfolio positions")
        self.assertEqual(row["category"], "read_only_or_account_data")
        self.assertEqual(row["risk"], "sensitive")
        self.assertFalse(row["allowed_for_live_trading"])

    def test_unknown_tools_keep_classification_incomplete(self):
        report = classify_broker_tools([{"name": "magic_button", "description": "unclear capability"}])
        rendered = render_broker_tool_classification(report)
        self.assertFalse(report["classification_complete"])
        self.assertFalse(report["execution_allowed"])
        self.assertIn("unknown", rendered)

    def test_mixed_known_tools_complete_but_still_do_not_enable_trading(self):
        report = classify_broker_tools([
            {"name": "get_quote", "description": "market price"},
            {"name": "cancel_order", "description": "cancel an open order"},
        ])
        self.assertTrue(report["classification_complete"])
        self.assertEqual(report["execution_or_money_movement_count"], 1)
        self.assertFalse(report["trading_allowed"])


if __name__ == "__main__":
    unittest.main()
