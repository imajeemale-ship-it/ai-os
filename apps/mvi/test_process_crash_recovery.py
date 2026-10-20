"""Kill a real worker process and prove another process reclaims its lease."""
import multiprocessing as mp
import tempfile
import time
import unittest
from pathlib import Path
from durable_queue import DurableQueue
from queue_worker import run_once


def stuck_worker(db_path, marker):
    q=DurableQueue(db_path)
    def handler(claim):
        Path(marker).write_text('claimed')
        time.sleep(60)
    run_once(q,handler,worker_id='crashed',lease_seconds=2,heartbeat_seconds=.3)


def replacement_worker(db_path, result_path):
    q=DurableQueue(db_path)
    def handler(claim):
        Path(result_path).write_text(str(claim['attempt']))
        return {'recovered':True}
    run_once(q,handler,worker_id='replacement',lease_seconds=5,heartbeat_seconds=1)

class ProcessCrashTests(unittest.TestCase):
    def test_killed_process_is_recovered_after_lease_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db=root/'queue.db';marker=root/'claimed';result=root/'result'
            q=DurableQueue(db);q.enqueue('crash1','upload',{'path':'test.mp4'})
            ctx=mp.get_context('spawn')
            crashed=ctx.Process(target=stuck_worker,args=(str(db),str(marker)))
            crashed.start()
            try:
                deadline=time.monotonic()+10
                while not marker.exists() and time.monotonic()<deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists(),'First worker did not claim')
                self.assertEqual(q.get('crash1')['status'],'running')
                crashed.kill();crashed.join(timeout=5)
                self.assertFalse(crashed.is_alive())
                self.assertEqual(q.get('crash1')['status'],'running')
                # The killed process cannot renew its lease.
                time.sleep(2.2)
                replacement=ctx.Process(target=replacement_worker,args=(str(db),str(result)))
                replacement.start();replacement.join(timeout=12)
                if replacement.is_alive():replacement.kill();replacement.join()
                self.assertEqual(replacement.exitcode,0)
                self.assertEqual(result.read_text(),'2')
                self.assertEqual(q.get('crash1')['status'],'completed')
                self.assertEqual(q.get('crash1')['result'],{'recovered':True})
            finally:
                if crashed.is_alive():crashed.kill();crashed.join()

if __name__=='__main__':unittest.main()
