import tempfile,unittest
from pathlib import Path
from deployment.check_service_templates import validate

class ServiceTemplateTests(unittest.TestCase):
 def test_checked_in_templates_meet_private_host_policy(self):
  self.assertEqual(validate(Path(__file__).parent/'deployment'),[])
 def test_missing_templates_are_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   self.assertTrue(validate(tmp))

if __name__=='__main__':unittest.main()
