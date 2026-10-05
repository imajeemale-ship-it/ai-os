import tempfile
import unittest
from pathlib import Path
from ai_os.store import AIOS


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_project_task_and_brief(self):
        project = self.store.add_project("Orb", "Photo-first camera", 1)
        task = self.store.add_task(project["id"], "Write builder scope", priority=2)
        brief = self.store.daily_brief()
        self.assertEqual(brief["projects"][0]["id"], project["id"])
        self.assertEqual(brief["next_actions"][0]["id"], task["id"])
        self.assertEqual(brief["next_actions"][0]["project_name"], "Orb")

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_project("", priority=1)
        project = self.store.add_project("M3")
        with self.assertRaises(ValueError):
            self.store.add_task(project["id"], " ", priority=1)
        with self.assertRaises(ValueError):
            self.store.add_task(project["id"], "bad priority", priority=8)

    def test_gated_action_needs_exact_approval(self):
        approval = self.store.request_approval("send_message", "email:label@example.com")
        self.assertFalse(self.store.authorize("send_message", "email:label@example.com"))
        self.assertFalse(self.store.authorize("trade", "email:label@example.com", approval["id"]))
        self.store.decide_approval(approval["id"], "approved")
        self.assertTrue(self.store.authorize("send_message", "email:label@example.com", approval["id"]))
        self.assertFalse(self.store.authorize("send_message", "email:other@example.com", approval["id"]))
        with self.assertRaises(ValueError):
            self.store.decide_approval(approval["id"], "rejected")

    def test_expired_approval_blocked(self):
        approval = self.store.request_approval("publish", "youtube:video-1",
                                               expires_at="2000-01-01T00:00:00+00:00")
        self.store.decide_approval(approval["id"], "approved")
        self.assertFalse(self.store.authorize("publish", "youtube:video-1", approval["id"]))

    def test_event_journal_records_lifecycle(self):
        project = self.store.add_project("Trash or Treasure")
        task = self.store.add_task(project["id"], "Implement scan inbox")
        self.store.set_task_status(task["id"], "done")
        types = [event["event_type"] for event in self.store.recent_events()]
        self.assertIn("project.created", types)
        self.assertIn("task.created", types)
        self.assertIn("task.done", types)


if __name__ == "__main__":
    unittest.main()
