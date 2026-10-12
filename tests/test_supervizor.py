import json
import tempfile
import unittest
from pathlib import Path
from ai_os.supervizor import (
    daily_trading_operator, evidence_review_queue, live_trading_focus,
    method_promotion_review, method_readiness, read_supervizor_snapshot,
    real_trading_readiness, render_daily_trading_operator,
    render_evidence_review_queue, render_live_trading_focus,
    render_method_promotion_review, render_method_readiness,
    file_based_real_trading_readiness, render_real_trading_readiness, render_supervizor_snapshot,
    render_trading_focus, score_with_price_path_preview, trading_focus,
)


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


    def test_method_readiness_surfaces_thin_inventory(self):
        vault = Path(self.temp.name) / "vault.jsonl"
        outcomes = Path(self.temp.name) / "outcomes.jsonl"
        method = {"id": "m1", "status": "untested", "source_type": "fibonacci", "title": "Fib"}
        vault.write_text(json.dumps(method), encoding="utf-8")
        report = method_readiness(vault, outcomes)
        rendered = render_method_readiness(report)
        self.assertEqual(report["method_count"], 1)
        self.assertEqual(report["outcome_count"], 0)
        self.assertIn("Method inventory is too small", "\n".join(report["blockers"]))
        self.assertIn("METHOD READINESS", rendered)


    def test_method_promotion_review_surfaces_candidates_without_execution(self):
        vault = Path(self.temp.name) / "vault.jsonl"
        outcomes = Path(self.temp.name) / "outcomes.jsonl"
        method = {"id": "m1", "status": "untested", "source_type": "personal_method", "title": "Risk Gate"}
        vault.write_text(json.dumps(method), encoding="utf-8")
        records = [
            {"method_id": "m1", "outcome": "helped"},
            {"method_id": "m1", "outcome": "helped"},
            {"method_id": "m1", "outcome": "helped"},
        ]
        outcomes.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        report = method_promotion_review(vault, outcomes)
        rendered = render_method_promotion_review(report)
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["methods"][0]["recommendation"], "candidate_for_validation")
        self.assertIn("promotion requires human decision", rendered)


    def test_real_trading_readiness_stays_locked_until_required_gates_pass(self):
        report = real_trading_readiness()
        rendered = render_real_trading_readiness(report)
        self.assertFalse(report["ready_for_real_trading"])
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["broker_tool_classification"]["classification_complete"])
        self.assertIn("broker_tool_classification", rendered)
        self.assertIn("human_final_approval", rendered)
        self.assertIn("trading-policy-draft", rendered)

    def test_real_trading_readiness_can_accept_classified_broker_inventory_without_unlocking(self):
        report = real_trading_readiness([
            {"name": "get_quote", "description": "market price"},
            {"name": "place_order", "description": "buy or sell order"},
        ])
        checks = {check["name"]: check for check in report["checks"]}
        self.assertTrue(checks["broker_tool_classification"]["passed"])
        self.assertFalse(report["ready_for_real_trading"])
        self.assertFalse(report["execution_allowed"])



    def test_real_trading_readiness_can_accept_valid_risk_limits_without_unlocking(self):
        limits = {
            "starting_capital_usd": 100,
            "max_daily_loss_usd": 10,
            "max_weekly_loss_usd": 25,
            "max_position_size_usd": 20,
            "max_open_positions": 1,
            "max_trades_per_day": 2,
            "cooldown_after_loss_minutes": 60,
            "kill_switch_trigger": "Stop for the day after max daily loss.",
        }
        report = real_trading_readiness(risk_limits=limits)
        checks = {check["name"]: check for check in report["checks"]}
        self.assertTrue(checks["funding_and_risk_limits"]["passed"])
        self.assertFalse(report["ready_for_real_trading"])
        self.assertFalse(report["execution_allowed"])


    def test_file_based_real_trading_readiness_reads_local_gate_files(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config_dir = home / ".ai-os"
            config_dir.mkdir()
            (config_dir / "broker-tools.json").write_text(json.dumps({"tools": [{"name": "get_quote", "description": "market price"}]}))
            (config_dir / "risk-limits.json").write_text(json.dumps({"limits": {
                "starting_capital_usd": 100,
                "max_daily_loss_usd": 10,
                "max_weekly_loss_usd": 25,
                "max_position_size_usd": 20,
                "max_open_positions": 1,
                "max_trades_per_day": 2,
                "cooldown_after_loss_minutes": 60,
                "kill_switch_trigger": "Stop for day after max daily loss.",
            }}))
            with patch("ai_os.broker_tools.Path.home", return_value=home), patch("ai_os.risk_limits.Path.home", return_value=home):
                report = file_based_real_trading_readiness()
        checks = {check["name"]: check for check in report["checks"]}
        self.assertTrue(checks["broker_tool_classification"]["passed"])
        self.assertTrue(checks["funding_and_risk_limits"]["passed"])
        self.assertFalse(report["ready_for_real_trading"])

    def test_daily_trading_operator_combines_safe_sections(self):
        report = daily_trading_operator()
        rendered = render_daily_trading_operator(report)
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["trading_allowed"])
        self.assertIn("DAILY PAPER TRADING OPERATOR", rendered)
        self.assertIn("REAL TRADING LOCK", rendered)
        self.assertIn("Ready for real trading: false", rendered)


if __name__ == "__main__":
    unittest.main()
