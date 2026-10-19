import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from scorecard import build_scorecard
from vindex_adapter import RUBRIC
class ScoreTest(unittest.TestCase):
 def setUp(self):self.e={'duration_seconds':60,'video_hash':'abc'}
 def test_incomplete_never_scores(self):
  s=build_scorecard(self.e);self.assertIsNone(s['content_quality_score']);self.assertEqual(s['recommendation'],'PENDING_REVIEW')
 def test_evidence_required(self):
  with self.assertRaises(ValueError):build_scorecard(self.e,{'opening_hook':{'score':20,'evidence':[]}})
 def test_complete_score(self):
  j={k:{'score':v,'evidence':[{'timestamp_seconds':1,'observation':'Reviewed scene'}]} for k,v in RUBRIC.items()}
  s=build_scorecard(self.e,j);self.assertEqual(s['content_quality_score'],100);self.assertEqual(s['recommendation'],'PUBLISH')
 def test_timestamp_bounds(self):
  with self.assertRaises(ValueError):build_scorecard(self.e,{'opening_hook':{'score':5,'evidence':[{'timestamp_seconds':999,'observation':'Invalid'}]}})
if __name__=='__main__':unittest.main()
