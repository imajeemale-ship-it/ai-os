"""HTTP-level tests: uploaded clips must produce persisted editor reports."""
import http.client
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server
from review_pipeline import review as actual_review


class UploadReportTests(unittest.TestCase):
 def test_upload_creates_editor_report_and_handoff(self):
  with tempfile.TemporaryDirectory() as temp:
   root = Path(temp)
   clip = root / "sample.mp4"
   subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                   "-i", "testsrc2=size=160x90:rate=10", "-t", "1.5",
                   "-pix_fmt", "yuv420p", "-y", str(clip)], check=True)
   with patch.object(server, "ROOT", root / "jobs"), \
        patch.object(server, "compile_video_evidence", return_value={
         "shots": [{"start_seconds": 0.0, "end_seconds": 1.5}], "scene_count": 1}), \
        patch.object(server, "review", side_effect=lambda *a, **kw: actual_review(*a, enable_local_vision=False)):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
     port = httpd.server_address[1]
     def request(method, path, body=None, headers=None):
      conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
      conn.request(method, path, body=body, headers=headers or {})
      res = conn.getresponse()
      data = res.read()
      conn.close()
      return res.status, data
     body = clip.read_bytes()
     status, raw = request("POST", "/api/upload", body,
                           {"Content-Length": str(len(body)), "X-Filename": "intro.mp4"})
     self.assertEqual(status, 202)
     job = json.loads(raw)["job_id"]
     import stat
     self.assertEqual(stat.S_IMODE((root / "jobs" / job).stat().st_mode),0o700)
     deadline = time.monotonic() + 20
     while time.monotonic() < deadline:
      code, raw = request("GET", "/api/jobs/" + job)
      self.assertEqual(code, 200)
      state = json.loads(raw)
      if state["status"] in ("completed", "failed"):
       break
      time.sleep(0.2)
     self.assertEqual(state["status"], "completed", state)
     self.assertIsNone(state["creative_score"])
     for kind in ("editor", "handoff", "timeline"):
      code, raw = request("GET", f"/api/reports/{job}/{kind}")
      self.assertEqual(code, 200)
      self.assertTrue(raw)
     self.assertTrue((root / "jobs" / job / "job.json").is_file())
     self.assertEqual(request("GET", "/api/reports/not-a-job/editor")[0], 400)
    finally:
     httpd.shutdown()
     httpd.server_close()
     thread.join(timeout=3)


if __name__ == "__main__":
 unittest.main()
