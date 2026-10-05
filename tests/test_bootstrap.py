import tempfile
import unittest
from pathlib import Path
from ai_os.bootstrap import bootstrap
from ai_os.store import AIOS


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AIOS(Path(self.temp.name) / "bootstrap.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_bootstrap_is_idempotent_and_creates_no_tasks(self):
        first = bootstrap(self.store)
        self.assertEqual(first["total"], 6)
        self.assertEqual(len(first["created"]), 6)
        second = bootstrap(self.store)
        self.assertEqual(len(second["created"]), 0)
        self.assertEqual(len(second["unchanged"]), 6)
        self.assertEqual(len(self.store.list_tasks()), 0)
        self.assertEqual({p["name"] for p in self.store.list_projects()},
                         {"Supervizor", "AI-OS", "M3", "Grabbit", "Trash or Treasure", "The Orb"})


if __name__ == "__main__":
    unittest.main()
