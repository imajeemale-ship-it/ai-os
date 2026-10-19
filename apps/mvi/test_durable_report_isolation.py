"""Only the queue-acknowledged attempt can be served to HTTP readers."""
import json,tempfile,unittest
from pathlib import Path
from durable_queue import DurableQueue
from durable_runtime import state,report_path

class ReportIsolationTests(unittest.TestCase):
 def test_stale_attempt_never_visible(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);job='a'*32;directory=root/job;directory.mkdir()
   q=DurableQueue(root/'private'/'queue.db')
   q.enqueue(job,'upload',{'filename':'upload.mp4'},now=100)
   old=q.claim('old',lease_seconds=5,now=101)
   stale=directory/'attempt-1';stale.mkdir()
   (stale/'EDITOR_REPORT.md').write_text('STALE')
   (stale/'job.json').write_text(json.dumps({'job_id':job,'attempt':1}))
   self.assertIsNone(report_path(root,job,'editor'))
   new=q.claim('new',lease_seconds=10,now=107)
   winner=directory/'attempt-2';winner.mkdir()
   (winner/'EDITOR_REPORT.md').write_text('WINNER')
   (winner/'job.json').write_text(json.dumps({'job_id':job,'attempt':2}))
   self.assertFalse(q.complete(job,old['lease_token'],{'attempt':1},now=108))
   self.assertTrue(q.complete(job,new['lease_token'],{'attempt':2},now=108))
   self.assertEqual(report_path(root,job,'editor').read_text(),'WINNER')
   self.assertEqual(state(root,job)['attempt'],2)

if __name__=='__main__':unittest.main()
