import os,subprocess,sys,unittest
from unittest.mock import patch
import server

class RequiredAuthTests(unittest.TestCase):
 def test_mandatory_auth_without_token_denies_access(self):
  with patch.dict(os.environ,{'MVI_REQUIRE_AUTH':'1','MVI_API_TOKEN':''}):
   self.assertFalse(server.authorized(type('Request',(),{'headers':{}})()))
 def test_service_refuses_to_start_without_required_token(self):
  env={**os.environ,'MVI_REQUIRE_AUTH':'1','MVI_API_TOKEN':''}
  result=subprocess.run([sys.executable,'server.py','--port','0'],env=env,
                        capture_output=True,text=True,timeout=5)
  self.assertNotEqual(result.returncode,0)
  self.assertIn('requires MVI_API_TOKEN',result.stderr+result.stdout)

if __name__=='__main__':unittest.main()
