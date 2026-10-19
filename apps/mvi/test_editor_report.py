import unittest,tempfile
from editor_report import build_report,save_report
class EditorReportTests(unittest.TestCase):
 def test_no_unfounded_scoring(self):
  r=build_report({'title':'Intro'}, {'duration_seconds':61},{'shots':[{'start_seconds':1,'end_seconds':3}]})
  self.assertIsNone(r['creative_score']);self.assertEqual(len(r['timeline']),1)
  self.assertIn('not proof',r['limitations'][0]);self.assertTrue(r['timeline'][0]['verified'])
 def test_bad_vision_timestamps_excluded(self):
  r=build_report({}, {'duration_seconds':10},visual_review={'observations':[{'timestamp_seconds':50,'observation':'Invalid'},{'timestamp_seconds':5,'observation':'Game map visible'}]})
  self.assertEqual(len(r['timeline']),1);self.assertFalse(r['timeline'][0]['verified'])
 def test_persist(self):
  with tempfile.TemporaryDirectory() as d:
   save_report(d,{}, {'duration_seconds':30});from pathlib import Path
   self.assertTrue((Path(d)/'EDITOR_REPORT.md').exists())
if __name__=='__main__':unittest.main()
