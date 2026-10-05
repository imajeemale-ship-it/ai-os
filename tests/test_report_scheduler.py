import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from ai_os.report import render_daily_brief, save_daily_brief
from ai_os.scheduler import daily_brief_status, install_daily_brief, uninstall_daily_brief
from ai_os.store import AIOS


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "report.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_brief_reports_empty_focus_and_projects(self):
        self.store.add_project("AI-OS", "Build the operating system", 1)
        rendered = render_daily_brief(self.store, datetime.fromisoformat("2026-10-05T15:00:00-04:00"))
        self.assertIn("AI-OS Daily Brief", rendered)
        self.assertIn("No open task is ready", rendered)
        self.assertIn("AI-OS — priority 1/5", rendered)
        self.assertIn("does not contact a model", rendered)

    def test_brief_includes_task_recommendation(self):
        project = self.store.add_project("M3")
        self.store.add_task(project["id"], "Review editing references", priority=1)
        rendered = render_daily_brief(self.store)
        self.assertIn("Review editing references", rendered)
        self.assertIn("M3", rendered)
        self.assertIn("1 open task(s)", rendered)

    def test_save_is_repeatable_and_creates_daily_file(self):
        fixed = datetime.fromisoformat("2026-10-05T15:00:00-04:00")
        with tempfile.TemporaryDirectory() as out:
            first = save_daily_brief(self.store, out, fixed)
            first_contents = first.read_text()
            second = save_daily_brief(self.store, out, fixed)
            self.assertEqual(first, second)
            self.assertEqual(first.name, "2026-10-05.md")
            self.assertEqual(second.read_text(), first_contents)


class SchedulerTests(unittest.TestCase):
    def test_invalid_schedule_time_rejected(self):
        with self.assertRaises(ValueError):
            install_daily_brief(hour=24, minute=0)
        with self.assertRaises(ValueError):
            install_daily_brief(hour=15, minute=60)

    @patch("ai_os.scheduler.plist_path")
    def test_status_absent_without_writing_or_loading(self, mock_path):
        with tempfile.TemporaryDirectory() as directory:
            mock_path.return_value = Path(directory) / "missing.plist"
            self.assertEqual(daily_brief_status(), {"installed": "no"})

    @patch("ai_os.scheduler._launchctl")
    @patch("ai_os.scheduler.plist_path")
    def test_install_creates_local_time_launch_agent(self, mock_path, launchctl):
        launchctl.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "com.kd.ai-os.daily-brief.plist"
            mock_path.return_value = target
            with patch("ai_os.scheduler.Path.home", return_value=Path(directory)):
                config = install_daily_brief(hour=15, minute=0)
            import plistlib
            parsed = plistlib.loads(target.read_bytes())
            self.assertEqual(parsed["Label"], "com.kd.ai-os.daily-brief")
            self.assertEqual(parsed["StartCalendarInterval"], {"Hour": 15, "Minute": 0})
            self.assertFalse(parsed["RunAtLoad"])
            self.assertEqual(config["time"], "15:00")

    @patch("ai_os.scheduler._launchctl")
    @patch("ai_os.scheduler.plist_path")
    def test_uninstall_removes_plist(self, mock_path, launchctl):
        launchctl.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "schedule.plist"
            target.write_text("test")
            mock_path.return_value = target
            result = uninstall_daily_brief()
            self.assertFalse(target.exists())
            self.assertEqual(result["removed"], "yes")


if __name__ == "__main__":
    unittest.main()
