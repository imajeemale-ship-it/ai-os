import json
import tempfile
import unittest
from pathlib import Path
from ai_os.supervizor import read_supervizor_snapshot, render_supervizor_snapshot


class SupervizorSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "latest_daily_operator_run.json"

    def tearDown(self):
        self.temp.cleanup()

    def report(self, **overrides):
        payload = {
            "generated_at": "2026-10-04T19:18:34Z",
            "operator_status": "PASS",
            "execution_allowed": False,
            "trading_allowed": False,
            "account_mutation_allowed": False,
            "next_move": "Continue paper scoring",
            "current_bottleneck": "Need more resolved evidence",
            "ceo_dashboard": {"ceo_score": 69, "evidence": {
                "signals_count": 5, "unresolved_signals_count": 4,
                "outcomes_count": 0, "backtest_queue_count": 0,
                "robinhood_blocked_capabilities": 9,
                "robinhood_readonly_capabilities": 6,
            }},
        }
        payload.update(overrides)
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_reads_compact_snapshot_and_confirms_all_safety_flags_blocked(self):
        self.report()
        result = read_supervizor_snapshot(self.path)
        self.assertEqual(result["status"], "read_only_pass")
        self.assertEqual(result["ceo_score"], 69)
        self.assertEqual(result["evidence"]["unresolved_signals_count"], 4)
        self.assertFalse(result["execution_allowed"])
        self.assertIn("Supervizor was not executed", render_supervizor_snapshot(result))

    def test_missing_guardrail_flag_is_attention_not_pass(self):
        self.report(trading_allowed=True)
        result = read_supervizor_snapshot(self.path)
        self.assertEqual(result["status"], "attention_required")
        self.assertTrue(result["trading_allowed"])

    def test_missing_and_malformed_files_fail_closed_without_throwing(self):
        missing = read_supervizor_snapshot(Path(self.temp.name) / "missing.json")
        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["reason"], "report_missing")
        self.path.write_text("not json", encoding="utf-8")
        malformed = read_supervizor_snapshot(self.path)
        self.assertEqual(malformed["status"], "unavailable")
        self.assertEqual(malformed["reason"], "report_unreadable")
        self.assertIsNone(malformed["execution_allowed"])

    def test_invalid_top_level_shape_fails_closed(self):
        self.path.write_text("[]", encoding="utf-8")
        result = read_supervizor_snapshot(self.path)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "invalid_report_shape")


if __name__ == "__main__":
    unittest.main()
