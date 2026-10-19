"""Crash-safe local job persistence and honest restart status."""
import json
import tempfile
import unittest
from pathlib import Path
from job_state import save,load


class JobStateTests(unittest.TestCase):
 def test_atomic_save_and_terminal_reload(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d)
   save(folder,{'job_id':'a'*32,'status':'queued'})
   self.assertEqual(load(folder/'job.json')['status'],'interrupted')
   self.assertIn('Manual resubmission',load(folder/'job.json')['recovery'])
   self.assertEqual(json.loads((folder/'job.json').read_text())['status'],'queued')
   save(folder,{'job_id':'a'*32,'status':'completed','creative_score':None})
   self.assertEqual(load(folder/'job.json')['status'],'completed')
   self.assertIsNone(load(folder/'job.json')['creative_score'])
   self.assertEqual(list(folder.glob('*.tmp')),[])

 def test_failed_job_remains_failed(self):
  with tempfile.TemporaryDirectory() as d:
   save(d,{'status':'failed','error':'media unreadable'})
   self.assertEqual(load(Path(d)/'job.json')['status'],'failed')


if __name__=='__main__':unittest.main()
