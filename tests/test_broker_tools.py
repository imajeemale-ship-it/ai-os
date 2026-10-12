import json
import tempfile
import unittest
from pathlib import Path

from ai_os.broker_tools import classify_broker_tool, classify_broker_tools, load_broker_tool_inventory, render_broker_tool_classification, write_broker_tool_inventory


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

    def test_order_status_is_read_only_not_execution(self):
        row = classify_broker_tool("get_order_status", "Read status for an existing order")
        self.assertEqual(row["category"], "read_only_or_account_data")
        self.assertEqual(row["risk"], "sensitive")

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

    def test_loads_inventory_from_json_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker_tools.json"
            path.write_text(json.dumps({"tools": [{"name": "get_quote", "description": "market price"}]}))
            self.assertEqual(load_broker_tool_inventory(path), [{"name": "get_quote", "description": "market price"}])

    def test_inventory_requires_named_tool_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker_tools.json"
            path.write_text(json.dumps({"tools": [{"description": "missing name"}]}))
            with self.assertRaises(ValueError):
                load_broker_tool_inventory(path)

    def test_writes_starter_inventory_without_enabling_trading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker-tools.json"
            result = write_broker_tool_inventory(path)
            payload = json.loads(path.read_text())
            self.assertTrue(result["written"])
            self.assertFalse(payload["execution_allowed"])
            self.assertFalse(payload["trading_allowed"])
            self.assertGreaterEqual(len(payload["tools"]), 4)

    def test_inventory_init_does_not_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker-tools.json"
            path.write_text(json.dumps({"tools": []}))
            result = write_broker_tool_inventory(path)
            self.assertFalse(result["written"])
            self.assertEqual(result["reason"], "already_exists")


if __name__ == "__main__":
    unittest.main()
