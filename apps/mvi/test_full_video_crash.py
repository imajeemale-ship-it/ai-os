"""End-to-end real-video job resumes after hard-killing an active process."""
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import durable_runtime


def killed_video_worker(root, marker):
    from durable_runtime import queue,process
    from queue_worker import run_once
    from engine import inspect as actual_inspect
    def slow_inspect(path,directory):
        Path(marker).write_text('in-video-processing')
        time.sleep(60)
        return actual_inspect(path,directory)
    with patch.object(durable_runtime,'inspect',side_effect=slow_inspect):
        run_once(queue(root),lambda claim:process(root,claim),lease_seconds=2,heartbeat_seconds=.25)


def resumed_video_worker(root):
    from durable_runtime import queue,process
    from queue_worker import run_once
    with patch.object(durable_runtime,'compile_video_evidence',return_value={'shots':[],'scene_count':0}):
        run_once(queue(root),lambda claim:process(root,claim),lease_seconds=20,heartbeat_seconds=2)

class FullVideoCrashTests(unittest.TestCase):
    def test_real_video_pipeline_recovers_after_process_kill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'data';root.mkdir();job='b'*32
            directory=root/job;directory.mkdir()
            video=directory/'upload.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                'testsrc2=size=160x90:rate=10','-t','1','-pix_fmt','yuv420p','-y',str(video)],check=True)
            durable_runtime.enqueue(root,job,'upload',{'filename':'upload.mp4','title':'crash test'})
            marker=Path(tmp)/'active'
            ctx=mp.get_context('spawn')
            crashed=ctx.Process(target=killed_video_worker,args=(str(root),str(marker)))
            crashed.start()
            try:
                deadline=time.monotonic()+12
                while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(marker.exists(),'Worker did not enter real video pipeline')
                crashed.kill();crashed.join(timeout=5)
                self.assertFalse(crashed.is_alive())
                self.assertEqual(durable_runtime.state(root,job)['status'],'running')
                self.assertIsNone(durable_runtime.report_path(root,job,'editor'))
                time.sleep(2.2)
                resumed=ctx.Process(target=resumed_video_worker,args=(str(root),))
                resumed.start();resumed.join(timeout=25)
                if resumed.is_alive():resumed.kill();resumed.join()
                self.assertEqual(resumed.exitcode,0)
                self.assertEqual(durable_runtime.state(root,job)['status'],'completed')
                self.assertEqual(durable_runtime.state(root,job)['attempt'],2)
                self.assertTrue(durable_runtime.report_path(root,job,'editor').is_file())
                self.assertTrue(durable_runtime.report_path(root,job,'handoff').is_file())
                self.assertEqual(durable_runtime.queue(root).get(job)['attempts'],2)
            finally:
                if crashed.is_alive():crashed.kill();crashed.join()

if __name__=='__main__':unittest.main()
