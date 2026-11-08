"""Technical Visual Quality: the 12 required behaviours, on synthetic footage and fake judges."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scoring
import tvq
import visual_quality as vq
import vq_fixtures as F
from test_scoring import FakeJudge, PRICES, VTT, analyze, full, make_clip, visual_out
from test_trends import TREND


def duration(p):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)],
                         capture_output=True, text=True).stdout
    return float(out)


class Footage(unittest.TestCase):
    """Footage is generated once for the whole class (synthetic, so no real video is needed)."""
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name)
        cls.native4k = F.native(d / 'n4k.mp4', 3840, 2160, n=12, fps=6)
        cls.clean1080 = F.native(d / 'n1080.mp4', 1920, 1080, n=60)
        cls.up4k = F.upscaled(d / 'up4k.mp4', 1280, 720, 3840, 2160, n=12, fps=6)
        cls.lowbit = F.low_bitrate(d / 'lb.mp4', 1920, 1080, '120k', n=60)
        cls.zoomed = F.over_zoomed(d / 'zoom.mp4', 1920, 1080, n=60)
        cls.blurry = F.blurred_section(d / 'blur.mp4', 1920, 1080, n=90, start=20, stop=40)
        cls.grain = F.grainy(d / 'grain.mp4', 1920, 1080, n=60)
        cls.irregular = F.irregular_dups(d / 'irr.mp4', 1920, 1080, n=60)
        cls.m = {k: vq.measure(getattr(cls, k), duration(getattr(cls, k)))
                 for k in ('native4k', 'clean1080', 'up4k', 'lowbit', 'zoomed', 'blurry', 'grain', 'irregular')}

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def sub(self, name, key):
        return self.m[name]['subscores'][key]


class MeasurementTests(Footage):
    def test_01_native_4k_scores_high(self):
        self.assertGreaterEqual(self.sub('native4k', 'effective_resolution'), 90)
        self.assertGreaterEqual(self.sub('native4k', 'source_sharpness'), 90)
        self.assertGreaterEqual(self.m['native4k']['effective_height_median'], 1900)

    def test_02_clean_1080p_still_scores_well(self):
        self.assertGreaterEqual(self.sub('clean1080', 'effective_resolution'), 75)
        self.assertGreaterEqual(self.sub('clean1080', 'source_sharpness'), 90)
        self.assertGreaterEqual(self.sub('clean1080', 'compression_quality'), 85)

    def test_03_720p_upscaled_to_4k_is_not_native_4k(self):
        up, nat = self.m['up4k'], self.m['native4k']
        self.assertEqual(up['decoded_size'], nat['decoded_size'])           # same container size...
        self.assertLess(up['subscores']['effective_resolution'], nat['subscores']['effective_resolution'] - 25)
        self.assertLess(up['effective_height_median'], 1000)                # ...but about 720 lines of real detail
        self.assertLess(up['subscores']['source_sharpness'], nat['subscores']['source_sharpness'] - 20)

    def test_04_low_bitrate_loses_compression_points(self):
        self.assertLess(self.sub('lowbit', 'compression_quality'), self.sub('clean1080', 'compression_quality') - 40)
        self.assertTrue(any(i['subcategory'] == 'Compression Quality' for i in self.m['lowbit']['issues']))

    def test_05_zoomed_in_source_loses_detail(self):
        self.assertLess(self.sub('zoomed', 'effective_resolution'), 30)
        self.assertLess(self.sub('zoomed', 'source_sharpness'), 30)
        self.assertLess(self.m['zoomed']['effective_height_median'], 400)

    def test_07_blurry_clip_lowers_visual_consistency(self):
        self.assertLess(self.sub('blurry', 'visual_consistency'), 50)
        self.assertGreaterEqual(self.sub('clean1080', 'visual_consistency'), 90)

    def test_08_intentional_film_grain_does_not_fail(self):
        for key in ('source_sharpness', 'effective_resolution', 'compression_quality', 'visual_consistency'):
            self.assertGreaterEqual(self.sub('grain', key), 75, key)
        self.assertEqual([i for i in self.m['grain']['issues'] if i['severity'] == 'High'], [])

    def test_11_failures_come_with_timestamps_inside_the_video(self):
        d = duration(self.blurry)
        timed = [i for i in self.m['blurry']['issues']]
        self.assertTrue(timed)
        for i in timed:
            self.assertTrue(0 <= i['timestamp_start'] <= i['timestamp_end'] <= d + 1, i)
        blurred_range = (20 / 30 - 0.5, 40 / 30 + 0.5)
        self.assertTrue(any(blurred_range[0] <= i['timestamp_start'] <= blurred_range[1] for i in timed))
        self.assertTrue(self.m['irregular']['cadence']['worst_seconds'])

    def test_irregular_frame_timing_is_penalised(self):
        self.assertLess(self.sub('irregular', 'motion_quality'), 70)
        self.assertGreaterEqual(self.sub('clean1080', 'motion_quality'), 90)

    def test_12_file_metadata_alone_never_decides_the_score(self):
        # Same container size, very different pixels => very different scores; metadata never enters measure().
        self.assertEqual(self.m['native4k']['decoded_size'], self.m['up4k']['decoded_size'])
        a = vq.measure(self.native4k, duration(self.native4k))
        b = vq.measure(self.up4k, duration(self.up4k))
        self.assertGreater(a['subscores']['effective_resolution'] - b['subscores']['effective_resolution'], 25)
        import inspect
        # The only inputs the measurement accepts are the video file and its length; no container facts go in.
        self.assertEqual(list(inspect.signature(vq.measure).parameters), ['video', 'duration', 'count'])
        self.assertEqual(list(inspect.signature(tvq.build).parameters),
                         ['judged', 'measured', 'transcript_text', 'duration', 'has_transcript'])

    def test_undecodable_video_measures_to_none(self):
        with tempfile.TemporaryDirectory() as t:
            junk = Path(t) / 'x.mp4'
            junk.write_bytes(b'not a video')
            self.assertIsNone(vq.measure(junk, 10))


class AggregationTests(unittest.TestCase):
    DUR = 60.0
    TEXT = 'look at this security camera above the door and the guard near it'

    def build(self, judged, measured=None, text=TEXT, has_t=True):
        return tvq.build(judged, measured, text, self.DUR, has_t)

    def test_weights_total_one_hundred_and_match_the_spec(self):
        self.assertEqual(sum(vq.WEIGHTS.values()), 100)
        self.assertEqual(vq.WEIGHTS['source_sharpness'], 15)
        self.assertEqual(vq.WEIGHTS['effective_resolution'], 15)
        self.assertEqual(vq.WEIGHTS['compression_quality'], 15)
        self.assertEqual(vq.WEIGHTS['scale_crop_quality'], 15)
        self.assertEqual(vq.WEIGHTS['text_graphics_clarity'], 10)
        self.assertEqual(vq.WEIGHTS['motion_quality'], 10)
        self.assertEqual(vq.WEIGHTS['color_exposure_integrity'], 5)
        self.assertEqual(vq.WEIGHTS['visual_consistency'], 5)
        self.assertEqual(vq.WEIGHTS['evidence_visibility'], 10)

    def test_default_weight_15_and_visually_driven_20(self):
        self.assertEqual(tvq.weight_for('other'), 0.15)
        self.assertEqual(tvq.weight_for(None), 0.15)
        self.assertEqual(tvq.weight_for('gta'), 0.20)
        self.assertEqual(tvq.weight_for('cod'), 0.20)
        self.assertEqual(tvq.weight_for('other', visually_driven=True), 0.20)

    def test_quality_bands(self):
        for score, name in ((95, 'Excellent / professional'), (85, 'Very good'), (75, 'Acceptable'),
                            (65, 'Weak'), (50, 'Poor'), (10, 'Unacceptable')):
            self.assertEqual(vq.band(score), name)

    def test_total_is_the_weighted_sum(self):
        j = visual_out(80)
        j['subscores']['source_sharpness']['score'] = 100
        r = self.build(j)
        self.assertEqual(r['score'], round((80 * 85 + 100 * 15) / 100, 1))
        self.assertEqual(r['band'], 'Very good')

    def test_scale_crop_over_zoom_lowers_score_and_needs_a_timestamped_issue(self):
        j = visual_out(90)
        j['subscores']['scale_crop_quality']['score'] = 30
        r = self.build(j)
        self.assertIn('scale_crop_quality', r['not_evaluated'])             # no issue given => not trusted
        j['issues'] = [{'timestamp_start': 42, 'timestamp_end': 48, 'issue': 'Screenshot enlarged beyond usable source resolution',
                        'subcategory': 'Scale / Crop Quality', 'severity': 'High', 'impact': 'Small clue becomes soft',
                        'recommended_fix': 'Use the original screenshot'}]
        r = self.build(j)
        self.assertEqual(r['subscores']['scale_crop_quality']['score'], 30)
        self.assertEqual(r['issues'][0]['timestamp_start'], 42)

    def test_06_unreadable_captions_lower_text_clarity_and_the_overall_score(self):
        j = visual_out(90)
        j['subscores']['text_graphics_clarity']['score'] = 30
        j['issues'] = [{'timestamp_start': 186, 'timestamp_end': 186, 'issue': 'Caption unreadable on mobile',
                        'subcategory': 'Text / Graphics Clarity', 'severity': 'High', 'impact': 'Viewer cannot read the support',
                        'recommended_fix': 'Increase size, stroke and contrast'}]
        r = tvq.build(j, None, self.TEXT, 300.0, True)
        self.assertEqual(r['subscores']['text_graphics_clarity']['score'], 30)
        final, steps = tvq.adjust(85.0, r, 0.2)
        self.assertIn('critical_text_unreadable', [s['rule'] for s in steps])
        self.assertLess(final, 85.0)

    def test_09_evidence_visibility_failure_is_flagged_and_penalised(self):
        j = visual_out(90)
        j['evidence_visibility_failures'] = [{'timestamp_seconds': 52, 'narration_claim': 'look at this security camera above the door',
                                              'problem': 'The camera is a few pixels wide and compressed', 'fix': 'Zoom, crop and circle it'}]
        r = self.build(j)
        self.assertEqual(r['evidence_visibility_failures'][0]['flag'], 'EVIDENCE_VISIBILITY_FAILURE')
        self.assertLessEqual(r['subscores']['evidence_visibility']['score'], 79)
        final, steps = tvq.adjust(80.0, r, 0.2)
        self.assertIn('evidence_visibility_failure', [s['rule'] for s in steps])
        self.assertLess(final, 80.0)

    def test_invented_narration_is_not_accepted_as_a_failure(self):
        j = visual_out(90)
        j['evidence_visibility_failures'] = [{'timestamp_seconds': 52, 'narration_claim': 'the helicopter lands on the roof',
                                              'problem': 'Not visible', 'fix': 'Zoom'}]
        self.assertEqual(self.build(j)['evidence_visibility_failures'], [])
        self.assertEqual(self.build(j, has_t=False, text='')['evidence_visibility_failures'], [])

    def test_several_failures_are_penalised_harder(self):
        j = visual_out(90)
        claim = 'look at this security camera above the door'
        one = [{'timestamp_seconds': 5, 'narration_claim': claim, 'problem': 'p', 'fix': 'f'}]
        three = one * 3
        j['evidence_visibility_failures'] = one
        p1 = tvq.adjust(80.0, self.build(j), 0.2)[0]
        j['evidence_visibility_failures'] = three
        r3 = self.build(j)
        p3 = tvq.adjust(80.0, r3, 0.2)[0]
        self.assertLess(p3, p1 - 3)
        self.assertLessEqual(r3['subscores']['evidence_visibility']['score'], 59)

    def test_without_a_transcript_evidence_visibility_is_not_evaluated(self):
        r = self.build(visual_out(90), has_t=False, text='')
        self.assertIn('evidence_visibility', r['not_evaluated'])
        self.assertIsNone(r['score'])
        self.assertIsNotNone(r['provisional_score'])

    def test_intentional_style_is_judged_not_measured(self):
        j = visual_out(90)
        j['intentional_style'] = ['compression_quality']
        measured = {'subscores': {'compression_quality': 20.0}, 'issues': []}
        r = self.build(j, measured)
        self.assertEqual(r['subscores']['compression_quality']['score'], 90)
        j['intentional_style'] = []
        r = self.build(j, measured)
        self.assertEqual(r['subscores']['compression_quality']['score'], 55)    # 50/50 blend of 20 and 90

    def test_judge_garbage_is_rejected(self):
        for junk in (None, {}, {'subscores': []}, {'subscores': {'source_sharpness': {'score': 400, 'observation': 'x'}}}):
            r = self.build(junk)
            self.assertIsNone(r['score'])
        j = visual_out(90)
        j['issues'] = [{'timestamp_start': 999, 'timestamp_end': 1000, 'issue': 'x', 'subcategory': 'Source Sharpness',
                        'severity': 'High', 'impact': 'x', 'recommended_fix': 'x'}]
        self.assertEqual(self.build(j)['issues'], [])       # outside the video

    def test_10_caps_and_penalties_on_the_overall_score(self):
        def result(score):
            j = visual_out(score)
            return self.build(j)
        self.assertEqual(tvq.adjust(95.0, result(90), 0.2)[1], [])
        mid, steps = tvq.adjust(90.0, result(65), 0.2)
        self.assertEqual(steps[0]['rule'], 'tvq_below_70');self.assertEqual(mid, 90.0 - 2.5)
        weak, steps = tvq.adjust(95.0, result(55), 0.2)
        self.assertEqual(weak, 79);self.assertIn('tvq_cap', [s['rule'] for s in steps])
        poor, steps = tvq.adjust(95.0, result(30), 0.2)
        self.assertEqual(poor, 69)
        overridden, steps = tvq.adjust(95.0, result(55), 0.2, cap_override=True)
        self.assertGreater(overridden, 79);self.assertIn('cap_overridden', [s['rule'] for s in steps])


class EndToEnd(unittest.TestCase):
    def run_score(self, visual, game=None, trend_points=20):
        out = full(1.0)
        from test_trends import trend_fit
        out['trend_fit'] = trend_fit(trend_points)
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, PRICES):
            clip = Path(t) / 'c.mp4'
            make_clip(clip)
            jd = Path(t) / 'j'
            jd.mkdir()
            (jd / 'transcript.vtt').write_text(VTT)
            ctx = {'game': game} if game else None
            judge = FakeJudge(out, visual)
            r = scoring.score_video(clip, analyze(clip), {'timeline': [], 'scene_count': 1}, jd, judge,
                                    max_usd=2, frame_count=4, trends=TREND(), context=ctx)
            return r, judge

    def test_10_visual_quality_changes_the_overall_score(self):
        high, _ = self.run_score(visual_out(100))
        mid, _ = self.run_score(visual_out(70))
        self.assertEqual(high['overall_score'], 100.0)
        self.assertEqual(mid['overall_score'], round(0.85 * 100 + 0.15 * 70, 1))
        self.assertLess(mid['overall_score'], high['overall_score'])
        self.assertEqual(high['weights']['technical_visual_quality'], 0.15)

    def test_gaming_videos_use_the_20_percent_weight(self):
        r, _ = self.run_score(visual_out(70), game='gta')
        self.assertEqual(r['weights'], {'knowledge': 0.64, 'trends': 0.16, 'technical_visual_quality': 0.2})
        self.assertEqual(r['overall_score'], round(0.8 * 100 + 0.2 * 70, 1))

    def test_poor_visual_quality_caps_an_otherwise_perfect_video(self):
        r, _ = self.run_score(visual_out(55), game='gta')
        self.assertEqual(r['overall_score'], 79.0)
        self.assertIn('tvq_cap', [a['rule'] for a in r['adjustments']])
        r, _ = self.run_score(visual_out(44), game='gta')      # under 45: capped at 69 even after the 70-point penalty
        self.assertEqual(r['overall_score'], 69.0)
        self.assertEqual(r['recommendation'], 'REVISE')
        r, _ = self.run_score(visual_out(30), game='gta')      # the below-70 penalty alone already pushes this under the cap
        self.assertEqual(r['overall_score'], 66.0)

    def test_visual_judge_failure_leaves_the_rest_scored_but_pending(self):
        class Broken(FakeJudge):
            def judge_visual(self, packet):
                raise RuntimeError('visual judge down')
        out = full(1.0)
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ, PRICES):
            clip = Path(t) / 'c.mp4'
            make_clip(clip)
            jd = Path(t) / 'j'
            jd.mkdir()
            (jd / 'transcript.vtt').write_text(VTT)
            r = scoring.score_video(clip, analyze(clip), {'timeline': [], 'scene_count': 1}, jd, Broken(out),
                                    max_usd=2, frame_count=4, trends=TREND())
        self.assertEqual(r['knowledge_score'], 100.0)
        self.assertIsNone(r['overall_score']);self.assertEqual(r['recommendation'], 'PENDING_REVIEW')
        self.assertIn('visual judge failed', ' '.join(r['technical_visual_quality']['errors']))

    def test_the_visual_judge_sees_frames_and_measurements_not_instructions_from_the_video(self):
        r, judge = self.run_score(visual_out(90))
        packet = judge.visual_packets[0]
        self.assertEqual(len(packet['frames']), scoring.VISUAL_FRAMES)
        self.assertIn('measurements', packet)
        self.assertTrue(packet['transcript_text'])

    def test_cost_estimate_covers_the_second_call(self):
        with patch.dict(os.environ, PRICES):
            est = scoring.estimate_usd(24, 4000)
        self.assertGreaterEqual(est['tokens_out'], 10000)
        self.assertLess(est['estimated_usd'], 1.0)


if __name__ == '__main__':
    unittest.main()
