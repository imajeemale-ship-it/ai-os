import unittest, tempfile, pathlib, subprocess, sys
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from engine import inspect
class TestEngine(unittest.TestCase):
 def test_synthetic_clip(self):
  with tempfile.TemporaryDirectory() as d:
   clip=pathlib.Path(d)/'test.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10','-t','2','-pix_fmt','yuv420p','-y',str(clip)],check=True)
   result=inspect(clip,pathlib.Path(d)/'out')
   self.assertEqual(result['content_quality_score'],None)
   self.assertTrue(result['frames'])
   self.assertTrue((pathlib.Path(d)/'out/report.json').exists())
if __name__=='__main__': unittest.main()
