import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from ai_os.cycle import render_cycle, save_daily_cycle
from ai_os.providers.openai_compatible import OpenAICompatibleProvider
from ai_os.store import AIOS


class DailyCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "cycle.db")
        project = self.store.add_project("AI-OS", "Build safe local automation")
        self.task = self.store.add_task(project["id"], "Ship daily loop", priority=1)
        self.provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1:11434/v1", model="qwen-local", api_key=""
        )
        self.fixed = datetime.fromisoformat("2026-10-05T15:00:00-04:00")
        self.snapshot_patch = patch("ai_os.cycle.read_supervizor_snapshot", return_value={
            "status": "unavailable", "execution_allowed": None,
            "trading_allowed": None, "account_mutation_allowed": None,
            "reason": "report_missing",
        })
        self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)

    def tearDown(self):
        self.temp.cleanup()

    @patch("ai_os.cycle.model_proposal")
    def test_cycle_combines_local_brief_and_reviewable_model_proposal(self, propose):
        propose.return_value = {
            "status": "proposed", "id": "mdl_example",
            "proposal": {"title": "Ship daily loop", "project": "AI-OS",
                         "reason": "Highest priority", "task_id": self.task["id"]},
        }
        rendered, result = render_cycle(self.store, self.provider, self.fixed)
        self.assertIn("AI-OS Daily Brief", rendered)
        self.assertIn("## Local model suggestion", rendered)
        self.assertIn("Proposal ID: `mdl_example`", rendered)
        self.assertIn("optional Ollama suggestion is separate", rendered)
        self.assertIn("Supervizor Local Snapshot", rendered)
        self.assertIn("report_missing", rendered)
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")

    @patch("ai_os.cycle.model_proposal")
    def test_cycle_saves_to_distinct_daily_file(self, propose):
        propose.return_value = {"status": "no_tasks", "id": "mdl_none"}
        with tempfile.TemporaryDirectory() as output:
            path, _ = save_daily_cycle(self.store, self.provider, output, self.fixed)
            self.assertEqual(path.name, "2026-10-05-ai-os-cycle.md")
            self.assertIn("Local model suggestion", path.read_text())

    def test_cycle_reports_unavailable_provider_without_touching_task(self):
        with patch("ai_os.providers.openai_compatible.Path.home", return_value=Path(self.temp.name)):
            provider = OpenAICompatibleProvider(base_url="", model="", api_key="")
            rendered, result = render_cycle(self.store, provider, self.fixed)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("Model suggestion unavailable", rendered)
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
