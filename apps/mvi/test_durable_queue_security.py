"""Security and recovery regressions for MVI's local durable queue."""
import tempfile
import unittest
from pathlib import Path
from durable_queue import DurableQueue

class QueueSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.q = DurableQueue(Path(self.temp.name) / 'private' / 'queue.db')

    def tearDown(self):
        self.temp.cleanup()

    def test_stale_worker_cannot_renew_or_complete_after_expiry(self):
        self.q.enqueue('a', 'upload', {}, now=100)
        lease = self.q.claim('w', lease_seconds=5, now=100)
        self.assertFalse(self.q.renew('a', lease['lease_token'], now=106))
        self.assertFalse(self.q.complete('a', lease['lease_token'], now=106))
        self.assertFalse(self.q.fail('a', lease['lease_token'], 'late', now=106))
        self.assertEqual(self.q.claim('w2', now=107)['attempt'], 2)

    def test_same_job_id_cannot_change_kind_or_attempt_budget(self):
        self.q.enqueue('a', 'url', {'url':'https://example.invalid'}, now=100)
        with self.assertRaises(ValueError):
            self.q.enqueue('a', 'upload', {'url':'https://example.invalid'}, now=100)
        with self.assertRaises(ValueError):
            self.q.enqueue('a', 'url', {'url':'https://example.invalid'}, max_attempts=4, now=100)

    def test_lease_recovery_preserves_single_owner(self):
        self.q.enqueue('a','upload',{},now=100)
        first=self.q.claim('first',lease_seconds=5,now=100)
        second=DurableQueue(self.q.path).claim('second',lease_seconds=10,now=106)
        self.assertIsNotNone(second)
        self.assertFalse(self.q.complete('a',first['lease_token'],now=107))
        self.assertTrue(self.q.complete('a',second['lease_token'],now=107))
        self.assertEqual(self.q.get('a')['status'],'completed')

if __name__ == '__main__':
    unittest.main()
