"""Deterministic restart, lease, retry, and idempotency tests for local queue."""
import tempfile
import stat
import unittest
from pathlib import Path
from durable_queue import DurableQueue


class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "private" / "queue.db"
        self.q = DurableQueue(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_persists_work_and_completion(self):
        self.q.enqueue("clip1", "upload", {"path": "clip.mp4"}, now=100)
        reopened = DurableQueue(self.path)
        claim = reopened.claim("worker-1", now=101)
        self.assertEqual(claim["payload"], {"path": "clip.mp4"})
        self.assertEqual(claim["attempt"], 1)
        self.assertTrue(reopened.complete("clip1", claim["lease_token"], {"report": "ready"}, now=102))
        self.assertEqual(DurableQueue(self.path).get("clip1")["result"], {"report": "ready"})
        self.assertIsNone(reopened.claim("worker-2", now=103))

    def test_fencing_prevents_stale_worker_completion(self):
        self.q.enqueue("clip1", "upload", {"path": "clip.mp4"}, now=100)
        old = self.q.claim("first", lease_seconds=10, now=101)
        new = DurableQueue(self.path).claim("second", lease_seconds=10, now=112)
        self.assertEqual(new["attempt"], 2)
        self.assertNotEqual(old["lease_token"], new["lease_token"])
        self.assertFalse(self.q.complete("clip1", old["lease_token"], now=113))
        self.assertFalse(self.q.fail("clip1", old["lease_token"], "stale", now=113))
        self.assertTrue(self.q.complete("clip1", new["lease_token"], now=113))
        self.assertEqual(self.q.get("clip1")["status"], "completed")

    def test_retry_delay_and_terminal_failure(self):
        self.q.enqueue("clip1", "url", {"url": "https://example.invalid"}, max_attempts=2, now=100)
        first = self.q.claim("worker", now=100)
        self.assertTrue(self.q.fail("clip1", first["lease_token"], "temporary", retry_delay=15, now=101))
        self.assertIsNone(self.q.claim("worker", now=115))
        second = self.q.claim("worker", now=116)
        self.assertEqual(second["attempt"], 2)
        self.assertTrue(self.q.fail("clip1", second["lease_token"], "permanent", now=117))
        self.assertEqual(self.q.get("clip1")["status"], "failed")
        self.assertIsNone(self.q.claim("worker", now=200))

    def test_expired_final_attempt_fails_instead_of_looping(self):
        self.q.enqueue("clip1", "upload", {}, max_attempts=1, now=100)
        claim = self.q.claim("worker", lease_seconds=5, now=101)
        self.assertFalse(self.q.complete("clip1", claim["lease_token"], now=107))
        self.assertIsNone(self.q.claim("other", now=107))
        self.assertEqual(self.q.get("clip1")["status"], "failed")

    def test_idempotency_rejects_changed_payload(self):
        self.q.enqueue("clip1", "upload", {"path": "first"}, now=100)
        self.q.enqueue("clip1", "upload", {"path": "first"}, now=101)
        with self.assertRaises(ValueError):
            self.q.enqueue("clip1", "upload", {"path": "different"}, now=102)
        self.assertEqual(self.q.get("clip1")["payload"], {"path": "first"})

    def test_two_workers_cannot_claim_same_job(self):
        self.q.enqueue("clip1", "upload", {}, now=100)
        first = self.q.claim("one", now=101)
        self.assertIsNotNone(first)
        self.assertIsNone(DurableQueue(self.path).claim("two", now=101))

    def test_renewal_keeps_long_processing_owned(self):
        self.q.enqueue("clip1", "upload", {}, now=100)
        claim = self.q.claim("worker", lease_seconds=10, now=101)
        self.assertTrue(self.q.renew("clip1", claim["lease_token"], lease_seconds=20, now=108))
        self.assertIsNone(DurableQueue(self.path).claim("other", now=113))
        self.assertTrue(self.q.complete("clip1", claim["lease_token"], now=120))
        self.assertFalse(self.q.renew("clip1", claim["lease_token"], now=121))

    def test_database_is_owner_read_write_only(self):
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.q.enqueue("bad", "upload", {}, max_attempts=0)
        with self.assertRaises(ValueError):
            self.q.claim("", now=100)
        with self.assertRaises(ValueError):
            self.q.claim("worker", lease_seconds=0, now=100)


if __name__ == "__main__":
    unittest.main()
