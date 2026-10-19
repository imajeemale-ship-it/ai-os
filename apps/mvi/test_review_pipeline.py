import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from review_pipeline import review
class ReviewTests(unittest.TestCase):
 def test_vision_unavailable_is_explicit(self):
  with tempfile.TemporaryDirectory() as d:
   with patch('review_pipeline.evaluate',side_effect=ConnectionError('offline')):
    r=review(d,{'title':'David edit'},{'duration_seconds':15},enable_local_vision=True)
   self.assertEqual(r['review_stages']['sampled_frame_vision'],'unavailable')
   self.assertIsNone(r['creative_score']);self.assertTrue(r['review_warnings'])
 def test_vision_observations_not_verified(self):
  with tempfile.TemporaryDirectory() as d:
   with patch('review_pipeline.evaluate',return_value={'evidence_frames':[{'timestamp_seconds':3,'file':'frame.jpg'}],'observations':[{'timestamp_seconds':3,'observation':'Vehicle visible'}]}):
    r=review(d,{}, {'duration_seconds':15})
   self.assertFalse(r['timeline'][0]['verified'])
if __name__=='__main__':unittest.main()
