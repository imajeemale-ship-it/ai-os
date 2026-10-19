import unittest
from pathlib import Path
class Research002(unittest.TestCase):
 def test_source_and_rules(self):
  s=(Path(__file__).parent/'research'/'002_YOUTUBE_MASTERCLASS.md').read_text()
  for term in ['h-8C3bntQRo','Visual anchors','Five C','eye fatigue','auto-captions','unverified']:
   self.assertIn(term.lower(),s.lower())
if __name__=='__main__':unittest.main()
