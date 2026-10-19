import tempfile
import unittest
from pathlib import Path
from durable_queue import DurableQueue
from queue_worker import run_once

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = DurableQueue(Path(self.tmp.name) / 'queue.db')
        self.queue.enqueue('job1','upload',{'file':'sample.mp4'})

    def tearDown(self):
        self.tmp.cleanup()

    def test_success(self):
        state = run_once(self.queue, lambda job: {'review':'ready'})
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(self.queue.get('job1')['result'], {'review':'ready'})
        self.assertIsNone(run_once(self.queue, lambda job: None))

    def test_failure_is_retryable(self):
        def broken(job):
            raise RuntimeError('broken media')
        with self.assertRaisesRegex(RuntimeError, 'broken media'):
            run_once(self.queue, broken)
        state=self.queue.get('job1')
        self.assertEqual(state['status'],'queued')
        self.assertIn('broken media',state['error'])

    def test_lease_loss_cannot_acknowledge(self):
        def superseded(job):
            self.queue.claim('new-worker', now=job['lease_until']+1)
            return {'bad':'late'}
        with self.assertRaisesRegex(RuntimeError, 'lost job lease'):
            run_once(self.queue, superseded)
        self.assertEqual(self.queue.get('job1')['status'],'running')
        self.assertIsNone(self.queue.get('job1')['result'])

    def test_invalid_heartbeat(self):
        with self.assertRaises(ValueError):
            run_once(self.queue, lambda j: None, lease_seconds=10, heartbeat_seconds=10)

if __name__=='__main__':
    unittest.main()
