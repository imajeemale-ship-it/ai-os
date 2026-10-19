import unittest
from editor_handoff import build_brief
class TestHandoff(unittest.TestCase):
 def test_does_not_invent_review(self):
  s=build_brief(evidence={'scene_count':5})
  self.assertIn('5 scenes',s);self.assertIn('not** been assessed',s);self.assertIn('David:',s)
 def test_pending(self):self.assertIn('pending',build_brief())
if __name__=='__main__':unittest.main()
