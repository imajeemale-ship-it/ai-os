import os,tempfile,unittest
from unittest.mock import patch
from deployment.preflight import check

class DeploymentPreflightTests(unittest.TestCase):
 def test_rejects_missing_auth_and_queue_mode(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.dict(os.environ,{'MVI_API_TOKEN':'','MVI_DURABLE_QUEUE':'0'}):
    problems=check(tmp)
    self.assertIn('MVI_API_TOKEN missing',problems)
    self.assertIn('MVI_DURABLE_QUEUE must equal 1',problems)
 def test_valid_local_preflight(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.dict(os.environ,{'MVI_DURABLE_QUEUE':'1'}):
    self.assertEqual(check(tmp,require_auth=False),[])

if __name__=='__main__':unittest.main()
