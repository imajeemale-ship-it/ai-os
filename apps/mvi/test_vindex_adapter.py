import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from vindex_adapter import normalize,RUBRIC
class AdapterTest(unittest.TestCase):
 def test_scoring_is_independent(self):
  data=normalize({'schema_version':'2.0','video_hash':'abc','timeline':{'total_duration_ms':12000,'scenes':[{'shots':[{'start_ms':0,'end_ms':12000,'caption':None}]}]}})
  self.assertEqual(data['scene_count'],1)
  self.assertEqual(data['shots'][0]['end_seconds'],12)
  self.assertIsNone(data['content_quality_score'])
  self.assertEqual(sum(RUBRIC.values()),100)
if __name__=='__main__':unittest.main()
