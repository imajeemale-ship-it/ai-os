"""A/V feedback must come from overlapping measured evidence, not inference."""
import unittest
from editor_report import build_report, render_markdown


class CrossModalChecksTests(unittest.TestCase):
    def test_overlapping_shot_and_low_audio_promotes_review_not_verdict(self):
        timeline={'shots':[{'start_seconds':16.7,'end_seconds':22.433},
                           {'start_seconds':30.0,'end_seconds':31.0}]}
        audio={'intervals':[{'start_seconds':16.74,'end_seconds':22.47,'duration_seconds':5.73}]}
        report=build_report({'title':'Intro'}, {'duration_seconds':60.88}, timeline, audio_signal=audio)
        checks=report['cross_modal_checks']
        self.assertEqual(len(checks),1)
        self.assertEqual(checks[0]['start_seconds'],16.74)
        self.assertEqual(checks[0]['end_seconds'],22.43)
        self.assertEqual(checks[0]['evidence_sources'],['vindex_scene_detection','ffmpeg_silencedetect'])
        self.assertIn('intentional',checks[0]['action'])
        self.assertIsNone(report['creative_score'])
        self.assertIn('00:16.74–00:22.43',render_markdown(report))

    def test_no_evidence_no_cross_modal_claim(self):
        shots={'shots':[{'start_seconds':0,'end_seconds':4}]}
        self.assertEqual(build_report({}, {'duration_seconds':10}, shots)['cross_modal_checks'],[])
        self.assertEqual(build_report({}, {'duration_seconds':10}, audio_signal={'intervals':[{'start_seconds':0,'end_seconds':4,'duration_seconds':4}]})['cross_modal_checks'],[])

    def test_short_and_invalid_overlap_not_promoted(self):
        shots={'shots':[{'start_seconds':0,'end_seconds':10},
                        {'start_seconds':float('nan'),'end_seconds':10},
                        {'start_seconds':12,'end_seconds':13}]}
        audio={'intervals':[{'start_seconds':0,'end_seconds':2,'duration_seconds':2},
                            {'start_seconds':12,'end_seconds':12.5,'duration_seconds':.5},
                            {'start_seconds':float('inf'),'end_seconds':15,'duration_seconds':2}]}
        self.assertEqual(build_report({}, {'duration_seconds':20}, shots, audio_signal=audio)['cross_modal_checks'],[])


if __name__=='__main__':
    unittest.main()
