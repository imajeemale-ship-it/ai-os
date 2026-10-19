"""Source-bound human frame notes must not turn into unsupported claims."""
import json
import tempfile
import unittest
from pathlib import Path
from human_evidence import file_sha256, load
from review_pipeline import review


class HumanEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'synthetic-media-fixture')
        self.technical = {'duration_seconds': 12, 'audio_present': False,
                          'frames': [{'timestamp_seconds': 2.0, 'file': 'frame_00.jpg'}]}
        self.note = {'source_sha256': file_sha256(self.source),
                     'observations': [{'timestamp_seconds': 2.0,
                                      'observation': 'A vehicle is visible.',
                                      'editor_question': 'Check whether the visual fits the opening.'}]}

    def write(self):
        (self.root / 'human_review.json').write_text(json.dumps(self.note))

    def test_valid_source_bound_notes_become_grounded_review_check(self):
        self.write()
        result = review(self.root, {'title': 'Test'}, self.technical,
                        enable_local_vision=False, source_path=self.source)
        rows = [x for x in result['timeline'] if x['type'] == 'human_inspected_frame']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['evidence_source'], 'human_inspected_sampled_frame')
        self.assertTrue(rows[0]['verified'])
        self.assertEqual(result['review_stages']['human_inspected_frames'], 'completed')
        self.assertIn('A vehicle is visible.', (self.root / 'EDITOR_REPORT.md').read_text())
        self.assertIsNone(result['creative_score'])

    def test_wrong_source_hash_excludes_notes(self):
        self.note['source_sha256'] = 'a' * 64
        self.write()
        result = review(self.root, {}, self.technical,
                        enable_local_vision=False, source_path=self.source)
        self.assertEqual(result['timeline'], [])
        self.assertEqual(result['review_stages']['human_inspected_frames'], 'unavailable')
        self.assertIn('do not match', result['review_warnings'][0])

    def test_unsampled_frame_timestamp_excludes_notes(self):
        self.note['observations'][0]['timestamp_seconds'] = 8
        self.write()
        result = review(self.root, {}, self.technical,
                        enable_local_vision=False, source_path=self.source)
        self.assertEqual(result['timeline'], [])
        self.assertIn('sampled timestamp', result['review_warnings'][0])

    def test_no_notes_is_not_an_error(self):
        result = review(self.root, {}, self.technical,
                        enable_local_vision=False, source_path=self.source)
        self.assertEqual(result['review_warnings'], [])
        self.assertEqual(result['review_stages']['human_inspected_frames'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
