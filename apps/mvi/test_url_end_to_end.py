"""Local HTTP YouTube intake: mocked retrieval, real extraction, durable reports."""
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


class UrlReportTests(unittest.TestCase):
 def test_browser_continues_polling_during_retrieval(self):
  self.assertIn('j.status==="retrieving"',server.HTML)

 def test_url_generates_same_report_and_handoff_as_upload(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   clip=root/'sample.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi',
    '-i','testsrc2=size=160x90:rate=10','-t','1.5','-pix_fmt','yuv420p','-y',str(clip)],check=True)
   meta={'title':'Mock authorized clip','source':'youtube'}
   with patch.object(server,'ROOT',root/'jobs'), \
        patch.object(server,'retrieve',return_value=(meta,clip)), \
        patch.object(server,'compile_video_evidence',return_value={
         'shots':[{'start_seconds':0.0,'end_seconds':1.5}],'scene_count':1}), \
        patch.object(server,'review',side_effect=lambda *a,**kw:actual_review(*a,enable_local_vision=False)):
    httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
    try:
     port=httpd.server_address[1]
     def request(method,path,body=None,headers=None):
      conn=http.client.HTTPConnection('127.0.0.1',port,timeout=15)
      conn.request(method,path,body=body,headers=headers or {})
      res=conn.getresponse();data=res.read();conn.close()
      return res.status,data
     body=json.dumps({'url':'https://youtu.be/dQw4w9WgXcQ'}).encode()
     status,raw=request('POST','/api/url',body,{'Content-Type':'application/json'})
     self.assertEqual(status,202)
     job=json.loads(raw)['job_id']
     import stat
     self.assertEqual(stat.S_IMODE((root/'jobs'/job).stat().st_mode),0o700)
     deadline=time.monotonic()+20
     while time.monotonic()<deadline:
      code,raw=request('GET','/api/jobs/'+job)
      self.assertEqual(code,200)
      state=json.loads(raw)
      if state['status'] in ('completed','failed'):break
      time.sleep(.2)
     self.assertEqual(state['status'],'completed',state)
     self.assertIsNone(state['creative_score'])
     self.assertEqual(state['metadata']['title'],'Mock authorized clip')
     for kind in ('editor','handoff','timeline'):
      code,raw=request('GET',f'/api/reports/{job}/{kind}')
      self.assertEqual(code,200)
      self.assertTrue(raw)
     saved=json.loads((root/'jobs'/job/'job.json').read_text())
     self.assertEqual(saved['status'],'completed')
     self.assertIn('priority_checks',saved['editor_report'])
    finally:
     httpd.shutdown();httpd.server_close();thread.join(timeout=3)

 def test_retrieval_failure_is_persisted_without_fake_report(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   with patch.object(server,'ROOT',root),patch.object(server,'retrieve',side_effect=RuntimeError('retrieval unavailable')):
    job='a'*32
    directory=root/job;directory.mkdir()
    server.JOBS[job]={'job_id':job,'status':'queued','creative_score':None}
    server.run_url_job(job,'https://youtu.be/dQw4w9WgXcQ',directory)
    saved=json.loads((directory/'job.json').read_text())
    self.assertEqual(saved['status'],'failed')
    self.assertIsNone(saved['creative_score'])
    self.assertFalse((directory/'EDITOR_REPORT.md').exists())
    server.JOBS.pop(job,None)


if __name__=='__main__':unittest.main()
