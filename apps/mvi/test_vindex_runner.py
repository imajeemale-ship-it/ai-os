import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from vindex_runner import compile_video_evidence
class TestRunner(unittest.TestCase):
 def test_missing_install(self):
  with patch('vindex_runner.VENDOR',Path('/no/such/vindex')):
   with self.assertRaisesRegex(RuntimeError,'not installed'):compile_video_evidence('x.mp4',tempfile.mkdtemp())
if __name__=='__main__':unittest.main()
