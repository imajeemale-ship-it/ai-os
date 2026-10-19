import unittest
from research_rules import report_template,PLAYBOOK
class TestResearch(unittest.TestCase):
 def test_no_fabricated_evaluation(self):
  report=report_template('dqDqeht_FOE')
  self.assertIsNone(report['editorial_score']);self.assertIsNone(report['youtube_optimization_score'])
  self.assertTrue(all(v is None for v in report['research_fields'].values()))
 def test_playbook_exists(self):self.assertIn('MatPat',PLAYBOOK.read_text())
if __name__=='__main__':unittest.main()
