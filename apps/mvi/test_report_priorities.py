"""Prioritized feedback must be supported by measured audio evidence."""
import unittest
from editor_report import build_report, render_markdown


class PriorityChecksTests(unittest.TestCase):
 def test_longest_audio_interval_first_and_outro_context(self):
  audio={'intervals':[
   {'start_seconds':16.74,'end_seconds':22.47,'duration_seconds':5.73},
   {'start_seconds':52.87,'end_seconds':60.88,'duration_seconds':8.01}]}
  report=build_report({'title':'Intro'}, {'duration_seconds':60.88}, audio_signal=audio)
  checks=report['priority_checks']
  self.assertEqual(len(checks),2)
  self.assertEqual(checks[0]['start_seconds'],52.87)
  self.assertIn('final 15 seconds',checks[0]['reason'])
  self.assertIn('outro/end card',checks[0]['action'])
  self.assertEqual(checks[1]['start_seconds'],16.74)
  self.assertTrue(all(c['verified'] and c['evidence_source']=='ffmpeg_silencedetect' for c in checks))
  self.assertIsNone(report['creative_score'])
  self.assertIn('00:52.87–01:00.88',render_markdown(report))

 def test_no_measurement_means_no_priorities(self):
  self.assertEqual(build_report({}, {'duration_seconds':61})['priority_checks'],[])

 def test_bad_or_tiny_intervals_not_promoted(self):
  report=build_report({}, {'duration_seconds':20}, audio_signal={'intervals':[
   {'start_seconds':2,'end_seconds':2.5,'duration_seconds':0.5},
   {'start_seconds':21,'end_seconds':23,'duration_seconds':2}]})
  self.assertEqual(report['priority_checks'],[])

 def test_invalid_audio_evidence_never_becomes_verified_feedback(self):
  audio={'intervals':[
   {'start_seconds':float('nan'),'end_seconds':7,'duration_seconds':3},
   {'start_seconds':2,'end_seconds':float('inf'),'duration_seconds':3},
   {'start_seconds':True,'end_seconds':8,'duration_seconds':7},
   {'start_seconds':3,'end_seconds':30,'duration_seconds':27},
   None,
   {'start_seconds':4,'end_seconds':7,'duration_seconds':999}]}
  report=build_report({}, {'duration_seconds':20}, audio_signal=audio)
  self.assertEqual(len(report['priority_checks']),1)
  self.assertEqual(len(report['timeline']),1)
  self.assertEqual(report['timeline'][0]['observation'],'Measured low audio signal for 3.00 seconds.')
  self.assertEqual(report['priority_checks'][0]['start_seconds'],4)
  self.assertIsNone(report['creative_score'])


if __name__=='__main__':unittest.main()
