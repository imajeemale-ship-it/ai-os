"""Integration: real media pipeline through durable queue and worker."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from durable_queue import DurableQueue
from queue_worker import run_once
from engine import inspect

class PipelineWorkerTests(unittest.TestCase):
    def test_real_media_analysis_from_persisted_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            video=root/'clip.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                            'testsrc2=size=160x90:rate=10','-t','1','-pix_fmt','yuv420p',
                            '-y',str(video)],check=True)
            queue=DurableQueue(root/'queue.db')
            queue.enqueue('clip1','upload',{'path':str(video)},now=100)
            reopened=DurableQueue(root/'queue.db')
            def process(claim):
                evidence=root/'evidence'
                report=inspect(Path(claim['payload']['path']),evidence)
                return {'duration_seconds':report['duration_seconds'],
                        'evidence_dir':str(evidence)}
            completed=run_once(reopened,process)
            self.assertEqual(completed['status'],'completed')
            self.assertGreater(completed['result']['duration_seconds'],0)
            self.assertTrue((root/'evidence'/'report.json').exists())
            self.assertEqual(DurableQueue(root/'queue.db').get('clip1')['status'],'completed')

if __name__=='__main__':
    unittest.main()
