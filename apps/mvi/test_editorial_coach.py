import unittest
from editorial_coach import coach

class EditorialCoachTests(unittest.TestCase):
    def test_no_fabricated_assessment_from_technical_metadata(self):
        r = coach({'title': 'Amazing GTA Escape.mp4'}, {'duration_seconds': 61})
        self.assertEqual(r['assessment'], 'contextual_review_only')
        self.assertIsNone(r['context']['viewer_promise'])
        self.assertEqual(len(r['prioritized_review']), 3)
        self.assertEqual(r['prioritized_review'][0]['time_range'], '00:00–00:05')
        self.assertTrue(all(i['status'] == 'review_required_not_observed' for i in r['prioritized_review']))
    def test_explicit_context_transforms_editor_guidance(self):
        r = coach({'editorial_context': {
            'viewer_promise': 'Three chaotic GTA escapes', 'audience': 'GTA fans',
            'viewer_outcome': 'A funny escape payoff', 'intended_style': 'raw gameplay',
        }}, {'duration_seconds': 80})
        self.assertFalse(r['missing_context'])
        self.assertTrue(any('Three chaotic GTA escapes' in x for x in r['acceptance_criteria']))
        self.assertTrue(any('raw gameplay' in x for x in r['acceptance_criteria']))
    def test_rendered_report_contains_source_and_actionable_hypotheses(self):
        from editor_report import build_report, render_markdown
        m = {'editorial_context': {'viewer_promise': 'An impossible GTA escape'}}
        output = render_markdown(build_report(m, {'duration_seconds': 61}))
        self.assertIn('Jake Trinder', output)
        self.assertIn('An impossible GTA escape', output)
        self.assertIn('Potential edit if needed', output)
        self.assertIn('not a confirmed problem', output)
    def test_invalid_duration_does_not_invent_timestamps(self):
        for value in (float('nan'), -2, 'unknown', True, 0):
            self.assertFalse(coach({}, {'duration_seconds': value})['prioritized_review'])

if __name__ == '__main__':
    unittest.main()
