import json
import tempfile
import unittest
from pathlib import Path
from ai_os.supervizor import evidence_review_queue, read_supervizor_snapshot, render_evidence_review_queue, render_supervizor_snapshot, render_trading_focus, render_live_trading_focus, score_with_price_path_preview, live_trading_focus, trading_focus


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


    def test_trading_focus_stays_paper_only_and_surfaces_evidence_blockers(self):
        self.report()
        focus = trading_focus(self.path)
        rendered = render_trading_focus(focus)
        self.assertFalse(focus["trading_allowed"])
        self.assertFalse(focus["execution_allowed"])
        self.assertIn("4 unresolved signal", "\n".join(focus["blockers"]))
        self.assertIn("paper_only_watch_only", rendered)
        self.assertIn("NEXT PAPER-TRADING ACTION", rendered)


    def test_evidence_review_queue_lists_unresolved_signals_without_execution(self):
        scoreboard = Path(self.temp.name) / "scoreboard.jsonl"
        records = [
            {"pair": "JTO/USDT", "side": "short", "source": "Test", "result_status": "unscored", "entry_low": 1, "targets": [0.9], "stop_loss": 1.1, "leverage_detected": True},
            {"pair": "XRP/USDT", "side": "buy", "source": "Test", "result_status": "tp1_hit"},
        ]
        scoreboard.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        queue = evidence_review_queue(scoreboard)
        rendered = render_evidence_review_queue(queue)
        self.assertEqual(queue["unresolved_count"], 1)
        self.assertFalse(queue["execution_allowed"])
        self.assertIn("JTO/USDT", rendered)
        self.assertIn("leverage_rejected", rendered)


    def test_price_path_preview_scores_without_writing(self):
        scoreboard = Path(self.temp.name) / "scoreboard.jsonl"
        prices = Path(self.temp.name) / "prices.json"
        records = [{"pair": "JTO/USDT", "side": "short", "source": "Test", "result_status": "unscored", "targets": [0.512], "stop_loss": 0.545}]
        scoreboard.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        prices.write_text(json.dumps({"prices": [0.55, 0.56]}), encoding="utf-8")
        preview = score_with_price_path_preview(0, prices, scoreboard)
        self.assertEqual(preview["preview_status"], "stop_loss_hit")
        self.assertFalse(preview["write_performed"])
        unchanged = json.loads(scoreboard.read_text(encoding="utf-8"))
        self.assertEqual(unchanged["result_status"], "unscored")


    def test_live_trading_focus_uses_scoreboard_counts(self):
        scoreboard = Path(self.temp.name) / "scoreboard.jsonl"
        records = [
            {"pair": "JTO/USDT", "side": "short", "source": "Test", "result_status": "stop_loss_hit", "reject_reasons": ["leverage"]},
            {"pair": "DOT/USDT", "side": "buy", "source": "Test", "result_status": "unscored", "reject_reasons": ["missing"]},
        ]
        scoreboard.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        focus = live_trading_focus(scoreboard)
        rendered = render_live_trading_focus(focus)
        self.assertEqual(focus["resolved_count"], 1)
        self.assertEqual(focus["unresolved_count"], 1)
        self.assertEqual(focus["outcomes"], {"stop_loss_hit": 1})
        self.assertIn("LIVE PAPER TRADING FOCUS", rendered)


if __name__ == "__main__":
    unittest.main()
