import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "apps" / "signal-watch" / "scripts" / "report_paper_trading.py"
SPEC = importlib.util.spec_from_file_location("report_paper_trading", SCRIPT)
report = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(report)


class PaperTradingReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = sqlite3.connect(Path(self.temp.name) / "signals.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE signals (id INTEGER PRIMARY KEY, source TEXT, sent_at TEXT);
            CREATE TABLE paper_positions (
                id INTEGER PRIMARY KEY, signal_id INTEGER, source TEXT, status TEXT,
                opened_at TEXT, closed_at TEXT, realized_pnl_pct REAL
            );
            """
        )

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_build_report_ranks_channels_and_calculates_metrics(self):
        self.db.executemany(
            "INSERT INTO signals VALUES(?,?,?)",
            [
                (1, "Alpha", "2026-10-01T10:00:00Z"),
                (2, "Alpha", "2026-10-02T10:00:00Z"),
                (3, "Beta", "2026-10-03T10:00:00Z"),
            ],
        )
        self.db.executemany(
            "INSERT INTO paper_positions VALUES(?,?,?,?,?,?,?)",
            [
                (1, 1, "Alpha", "closed", "2026-10-01T10:00:00Z", "2026-10-01T12:00:00Z", 5.0),
                (2, 2, "Alpha", "closed", "2026-10-02T10:00:00Z", "2026-10-02T11:00:00Z", -2.0),
                (3, 3, "Beta", "open", "2026-10-03T10:00:00Z", None, 1.0),
            ],
        )
        self.db.commit()

        result = report.build_report(self.db)
        alpha, beta = result["channels"]
        self.assertEqual([item["channel"] for item in result["channels"]], ["Alpha", "Beta"])
        self.assertEqual(alpha["rank"], 1)
        self.assertEqual(alpha["total_signals"], 2)
        self.assertEqual(alpha["wins"], 1)
        self.assertEqual(alpha["losses"], 1)
        self.assertEqual(alpha["win_rate_pct"], 50.0)
        self.assertEqual(alpha["average_return_pct"], 1.5)
        self.assertEqual(alpha["average_hold_hours"], 1.5)
        self.assertEqual(alpha["net_paper_pnl_pct"], 3.0)
        self.assertEqual(alpha["profit_factor"], 2.5)
        self.assertEqual(alpha["maximum_drawdown_pct"], 2.0)
        self.assertEqual(beta["average_return_pct"], None)
        self.assertEqual(beta["net_paper_pnl_pct"], 1.0)
        self.assertEqual(beta["last_signal_date"], "2026-10-03T10:00:00Z")

    def test_report_includes_signal_only_channels_and_markdown(self):
        self.db.execute("INSERT INTO signals VALUES(?,?,?)", (1, "No Trades", "2026-10-01T10:00:00Z"))
        self.db.commit()
        result = report.build_report(self.db, sort_by="total_signals")
        self.assertEqual(result["channels"][0]["channel"], "No Trades")
        self.assertEqual(result["channels"][0]["total_signals"], 1)
        self.assertIn("| Rank | Channel |", report.render_markdown(result))
        self.assertIn("No Trades", report.render_markdown(result))

    def test_json_report_is_serializable_with_undefined_metrics(self):
        result = report.build_report(self.db)
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
