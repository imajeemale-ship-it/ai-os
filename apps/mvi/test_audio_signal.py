import unittest
from audio_signal import parse_silence
from editor_report import build_report, render_markdown


class AudioSignalTests(unittest.TestCase):
 def test_parse_intervals_and_trailing_silence(self):
  log = """[Parsed_silencedetect_0] silence_start: 16.7361
[Parsed_silencedetect_0] silence_end: 22.469569 | silence_duration: 5.733469
[Parsed_silencedetect_0] silence_start: 52.869524"""
  result = parse_silence(log, 60.882721)
  self.assertEqual(len(result), 2)
  self.assertEqual(result[0]["start_seconds"], 16.74)
  self.assertEqual(result[0]["duration_seconds"], 5.73)
  self.assertEqual(result[1]["end_seconds"], 60.88)

 def test_audio_signal_is_measured_not_editorial_score(self):
  signal = {"threshold_db": -35, "intervals": [
   {"start_seconds": 16.74, "end_seconds": 22.47, "duration_seconds": 5.73}]}
  report = build_report({"title": "Intro"}, {"duration_seconds": 61}, audio_signal=signal)
  self.assertEqual(report["timeline"][0]["type"], "low_audio_signal")
  self.assertTrue(report["timeline"][0]["verified"])
  self.assertIsNone(report["creative_score"])
  self.assertIn("decide", report["timeline"][0]["recommendation"])
  self.assertIn("00:16.74–00:22.47", render_markdown(report))


if __name__ == "__main__":
 unittest.main()
