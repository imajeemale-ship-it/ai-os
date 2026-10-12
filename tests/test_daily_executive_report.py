import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "apps" / "signal-watch" / "scripts" / "report_daily_executive.py"
SPEC = importlib.util.spec_from_file_location("report_daily_executive", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(report)


class DailyExecutiveReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = sqlite3.connect(Path(self.temp.name) / "signals.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE signals (id INTEGER PRIMARY KEY, source TEXT, received_at TEXT, decision TEXT);
            CREATE TABLE paper_positions (
                id INTEGER PRIMARY KEY, source TEXT, ticker TEXT, status TEXT, realized_pnl_pct REAL,
                opened_at TEXT, closed_at TEXT, predicted_conviction REAL, predicted_decision TEXT,
                predicted_overall_score REAL
            );
            CREATE TABLE learning_observations (
                id INTEGER PRIMARY KEY, source TEXT, ticker TEXT, closed_at TEXT, outcome TEXT,
                realized_pnl_pct REAL, decision_correct INTEGER, calibration_score REAL,
                consensus_effective INTEGER, market_context_key TEXT, prediction_error REAL
            );
            """
        )

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_builds_daily_snapshot_and_historical_files(self):
        self.db.executemany(
            "INSERT INTO signals(source,received_at,decision) VALUES(?,?,?)",
            [("Alpha", "2026-10-11T10:00:00Z", "APPROVE"),
             ("Beta", "2026-10-11T11:00:00Z", "WATCH"),
             ("Old", "2026-10-10T11:00:00Z", "REJECT")],
        )
        self.db.executemany(
            """INSERT INTO paper_positions
            (source,ticker,status,realized_pnl_pct,opened_at,closed_at,predicted_conviction,predicted_decision,predicted_overall_score)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            [("Alpha", "BTC", "closed", 12.0, "2026-10-11T10:05:00Z", "2026-10-11T15:00:00Z", 90.0, "APPROVE", 88.0),
             ("Beta", "ETH", "closed", -4.0, "2026-10-11T11:05:00Z", "2026-10-11T16:00:00Z", 85.0, "APPROVE", 82.0)],
        )
        self.db.executemany(
            """INSERT INTO learning_observations
            (source,ticker,closed_at,outcome,realized_pnl_pct,decision_correct,calibration_score,consensus_effective,market_context_key,prediction_error)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [("Alpha", "BTC", "2026-10-11T15:00:00Z", "WIN", 12.0, 1, 90.0, 1, "up|above_ema200|medium|London|Greed", -10.0),
             ("Beta", "ETH", "2026-10-11T16:00:00Z", "LOSS", -4.0, 0, 15.0, 0, "down|below_ema200|high|New York|Fear", 85.0)],
        )
        self.db.commit()

        result = report.build_report(self.db, date(2026, 10, 11))
        self.assertEqual(result["total_signals_received"], 2)
        self.assertEqual(result["paper_trades"]["opened"], 2)
        self.assertEqual(result["paper_trades"]["closed"], 2)
        self.assertEqual(result["paper_trades"]["win_rate_pct"], 50.0)
        self.assertEqual(result["paper_trades"]["net_paper_pnl_pct"], 8.0)
        self.assertEqual(result["best_channel"]["channel"], "Alpha")
        self.assertEqual(result["worst_channel"]["channel"], "Beta")
        self.assertEqual(result["highest_conviction_winner"]["ticker"], "BTC")
        self.assertEqual(result["highest_conviction_loser"]["ticker"], "ETH")
        self.assertEqual(result["consensus_accuracy_pct"], 50.0)
        self.assertEqual(result["calibration_score"], 52.5)
        self.assertEqual(result["decision_accuracy_pct"], 50.0)
        self.assertIn("Alpha", result["recommended_channels_to_follow"])
        self.assertIn("Beta", result["channels_to_mute"])
        self.assertIn("Daily Executive Report", report.render_markdown(result))

        output = Path(self.temp.name) / "daily"
        json_path, markdown_path, written = report.write_report(result, output)
        self.assertTrue(written)
        self.assertTrue(json_path.is_file())
        self.assertTrue(markdown_path.is_file())
        self.assertEqual(json.loads(json_path.read_text())["report_date"], "2026-10-11")
        _, _, written_again = report.write_report(result, output)
        self.assertFalse(written_again)


if __name__ == "__main__":
    unittest.main()
