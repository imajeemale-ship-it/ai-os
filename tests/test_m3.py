import unittest

from ai_os.m3 import build_m3_proof, build_m3_workflow, render_m3_proof, render_m3_sources, render_m3_workflow, scan_m3_sources


class M3WorkflowTests(unittest.TestCase):
    def test_workflow_creates_visible_asset_order(self):
        workflow = build_m3_workflow("GTA footage folder", "one short clip")
        self.assertEqual(workflow["source"], "GTA footage folder")
        self.assertEqual(workflow["target"], "one short clip")
        self.assertIn("Log proof", "\n".join(workflow["steps"]))
        self.assertIn("next M3 task", "\n".join(workflow["proof_required"]))

    def test_render_includes_execution_and_handoff(self):
        rendered = render_m3_workflow(build_m3_workflow())
        self.assertIn("M3 DAILY CONTENT WORKFLOW", rendered)
        self.assertIn("EXECUTION ORDER", rendered)
        self.assertIn("PROOF REQUIRED", rendered)
        self.assertIn("HANDOFF RULE", rendered)


    def test_proof_log_requires_asset_hook_and_next_action(self):
        proof = build_m3_proof("clip-001.mp4", "When the getaway goes wrong", "Pick tomorrow's clip")
        self.assertEqual(proof["status"], "proof_logged")
        rendered = render_m3_proof(proof)
        self.assertIn("M3 PROOF LOGGED", rendered)
        self.assertIn("clip-001.mp4", rendered)
        with self.assertRaises(ValueError):
            build_m3_proof("", "hook", "next")



    def test_scan_m3_sources_finds_keyword_videos(self):
        with __import__("tempfile").TemporaryDirectory() as directory:
            root = __import__("pathlib").Path(directory)
            keep = root / "Rico_clip.mp4"
            keep.write_bytes(b"video")
            skip = root / "random.txt"
            skip.write_text("no")
            candidates = scan_m3_sources([str(root)])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "Rico_clip.mp4")
        self.assertIn("M3 SOURCE CANDIDATES", render_m3_sources(candidates))

if __name__ == "__main__":
    unittest.main()
