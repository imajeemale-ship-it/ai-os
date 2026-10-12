import tempfile
import unittest
from pathlib import Path

from ai_os.store import AIOS
from ai_os.workers import assign_next, render_assignment, route_worker


class WorkerRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "workers.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_routes_code_work_to_codex(self):
        route = route_worker("Implement repo inspection tests")
        self.assertEqual(route["worker"], "Codex")

    def test_routes_terminal_work_to_rdc(self):
        route = route_worker("Open the VPS terminal and restart service")
        self.assertEqual(route["worker"], "Remote Desktop Commander")

    def test_routes_sensitive_approval_to_kd(self):
        route = route_worker("Approve API key purchase")
        self.assertEqual(route["worker"], "KD")

    def test_assign_next_creates_required_report_shape_and_event(self):
        project = self.store.add_project("M3", "Content engine", 1)
        self.store.add_task(project["id"], "Build M3 content workflow", priority=1)
        work_order = assign_next(self.store, [])
        rendered = render_assignment(work_order)
        self.assertEqual(work_order["worker"], "Codex")
        self.assertIn("COMPLETED", rendered)
        self.assertIn("IN PROGRESS", rendered)
        self.assertIn("BLOCKERS", rendered)
        self.assertIn("NEXT AUTONOMOUS ACTION", rendered)
        self.assertIn("Assign Codex", rendered)
        event_types = [event["event_type"] for event in self.store.recent_events()]
        self.assertIn("assignment.created", event_types)


if __name__ == "__main__":
    unittest.main()
