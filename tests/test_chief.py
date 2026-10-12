import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_os.chief import chief_of_staff_report, inspect_repo, render_chief_of_staff, render_priority_reasoning, save_chief_of_staff_report
from ai_os.store import AIOS


def run(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


class ChiefOfStaffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = AIOS(self.root / "chief.db")

    def tearDown(self):
        self.temp.cleanup()

    def make_repo(self):
        repo = self.root / "repo"
        repo.mkdir()
        run(repo, "init")
        run(repo, "config", "user.email", "kd@example.com")
        run(repo, "config", "user.name", "KD")
        (repo / "README.md").write_text("# Test\n")
        run(repo, "add", "README.md")
        run(repo, "commit", "-m", "Initial commit")
        return repo

    def test_inspects_git_repository_without_network(self):
        repo = self.make_repo()
        snapshot = inspect_repo(repo)
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["name"], "repo")
        self.assertIn("Initial commit", snapshot["latest_commit"])
        self.assertFalse(snapshot["dirty"])

    def test_report_uses_required_sections_and_next_task(self):
        repo = self.make_repo()
        project = self.store.add_project("M3", "Content engine", 1)
        self.store.add_task(project["id"], "Ship one visible clip", priority=1)
        report = chief_of_staff_report(self.store, [repo])
        rendered = render_chief_of_staff(report)
        self.assertIn("COMPLETED", rendered)
        self.assertIn("IN PROGRESS", rendered)
        self.assertIn("BLOCKERS", rendered)
        self.assertIn("NEXT AUTONOMOUS ACTION", rendered)
        self.assertIn("Ship one visible clip", rendered)

    def test_dirty_repo_blocks_new_assignment_until_reviewed(self):
        repo = self.make_repo()
        (repo / "new.txt").write_text("local work")
        project = self.store.add_project("AI-OS", "Control plane", 1)
        self.store.add_task(project["id"], "Add worker routing", priority=1)
        report = chief_of_staff_report(self.store, [repo])
        self.assertIn("Repo has uncommitted work", "\n".join(report["blockers"]))
        self.assertIn("Verify and commit", report["next_autonomous_action"])

    def test_save_records_report_event(self):
        repo = self.make_repo()
        destination = save_chief_of_staff_report(self.store, [repo], self.root / "reports")
        self.assertTrue(destination.exists())
        events = self.store.recent_events()
        self.assertEqual(events[0]["event_type"], "chief_of_staff.saved")


    def test_priority_reasoning_explains_selected_task(self):
        project = self.store.add_project("M3", "Content engine", 1)
        self.store.add_task(project["id"], "Build daily workflow", priority=1)
        rendered = render_priority_reasoning(self.store)
        self.assertIn("WHY JOHNNY 5 CHOSE THIS", rendered)
        self.assertIn("Selected M3", rendered)
        self.assertIn("Build daily workflow", rendered)


if __name__ == "__main__":
    unittest.main()
