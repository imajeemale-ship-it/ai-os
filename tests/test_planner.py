import tempfile
import unittest
from pathlib import Path
from ai_os.loop import ExecutionLoop
from ai_os.planner import Planner
from ai_os.store import AIOS


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "plan.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_prioritizes_existing_tasks_without_mutating(self):
        p1 = self.store.add_project("Low")
        p2 = self.store.add_project("High")
        low = self.store.add_task(p1["id"], "Low task", priority=4)
        high = self.store.add_task(p2["id"], "High task", priority=1)
        plan = Planner(self.store).plan()
        self.assertEqual(plan["recommended_next_action"]["task_id"], high["id"])
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")
        self.assertEqual(len(plan["ranked_actions"]), 2)
        self.assertTrue(low["id"])

    def test_in_progress_and_overdue_raise_rank(self):
        p = self.store.add_project("Project")
        ready = self.store.add_task(p["id"], "Ready", priority=1)
        active = self.store.add_task(p["id"], "Active", priority=2, due_at="2000-01-01")
        self.store.set_task_status(active["id"], "in_progress")
        plan = Planner(self.store).plan()
        self.assertEqual(plan["recommended_next_action"]["task_id"], active["id"])
        self.assertNotEqual(ready["id"], active["id"])

    def test_loop_is_dry_until_accepted(self):
        p = self.store.add_project("Project")
        task = self.store.add_task(p["id"], "Do work")
        loop = ExecutionLoop(self.store)
        dry = loop.run_once()
        self.assertFalse(dry["accepted"])
        self.assertEqual(self.store.list_tasks()[0]["status"], "ready")
        accepted = loop.run_once(accept_task_id=task["id"])
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["started_task"]["status"], "in_progress")

    def test_loop_rejects_stale_or_nonrecommended_acceptance(self):
        p = self.store.add_project("Project")
        first = self.store.add_task(p["id"], "First", priority=1)
        second = self.store.add_task(p["id"], "Second", priority=3)
        with self.assertRaises(ValueError):
            ExecutionLoop(self.store).run_once(accept_task_id=second["id"])
        self.assertEqual(self.store.list_tasks()[0]["id"], first["id"])


if __name__ == "__main__":
    unittest.main()
