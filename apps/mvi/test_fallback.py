"""Blocked links become needs_fallback jobs that can be resumed by attaching a file."""
import http.client, json, os, subprocess, tempfile, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import server, durable_runtime as durable
from fallback import classify, build_record
from link_intake import parse_link
from review_pipeline import review as actual_review


class ParseTests(unittest.TestCase):
 def test_platforms(self):
  self.assertEqual(parse_link('https://www.tiktok.com/@a/video/123?x=1')['platform'],'tiktok')
  self.assertEqual(parse_link('https://vm.tiktok.com/ZMabc/')['url'],'https://vm.tiktok.com/ZMabc/')
  self.assertEqual(parse_link('https://www.instagram.com/reel/AbC123/?igsh=z')['url'],'https://www.instagram.com/reel/AbC123/')
  self.assertEqual(parse_link('https://youtu.be/dQw4w9WgXcQ')['platform'],'youtube')
 def test_rejects_lookalikes_and_other_hosts(self):
  for bad in ('https://tiktok.com.evil.test/@a/video/1','https://evil.test/www.tiktok.com/x',
              'https://www.instagram.com/accounts/login/','file:///etc/passwd','http://169.254.169.254/'):
   with self.assertRaises(ValueError,msg=bad):parse_link(bad)


class ClassifyTests(unittest.TestCase):
 def test_reasons(self):
  self.assertEqual(classify("Sign in to confirm you're not a bot"),'bot_challenge')
  self.assertEqual(classify('rate-limit reached or login required'),'login_required')
  self.assertEqual(classify('HTTP Error 429: Too Many Requests'),'rate_limited')
  self.assertEqual(classify('Video exceeds 300MB limit'),'too_large')
  self.assertEqual(classify('something odd'),'retrieval_failed')
 def test_record_never_scores_and_offers_next_steps(self):
  r=build_record('a'*32,'tiktok','https://www.tiktok.com/@a/video/1','login required',{'audience':'x'})
  self.assertEqual(r['status'],'needs_fallback');self.assertIsNone(r['creative_score'])
  steps={a['step']:a['available'] for a in r['next_actions']}
  self.assertTrue(steps['upload_file'] and steps['local_helper']);self.assertFalse(steps['browser_capture'])
  self.assertEqual(r['editorial_context'],{'audience':'x'})


def _clip(folder):
 clip=Path(folder)/'sample.mp4'
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10',
  '-t','1.5','-pix_fmt','yuv420p','-y',str(clip)],check=True)
 return clip


class AttachFlowTests(unittest.TestCase):
 def _run(self,durable_mode):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'jobs';root.mkdir();clip=_clip(temp)
   env={'MVI_DURABLE_QUEUE':'1'} if durable_mode else {}
   with patch.dict(os.environ,env),patch.object(server,'ROOT',root), \
        patch.object(server,'retrieve',side_effect=RuntimeError('Sign in to confirm you are not a bot')), \
        patch.object(durable,'retrieve',side_effect=RuntimeError('Sign in to confirm you are not a bot')), \
        patch.object(server,'compile_video_evidence',return_value={'shots':[{'start_seconds':0.0,'end_seconds':1.5}],'scene_count':1}), \
        patch.object(durable,'compile_video_evidence',return_value={'shots':[{'start_seconds':0.0,'end_seconds':1.5}],'scene_count':1}), \
        patch.object(server,'review',side_effect=lambda *a,**k:actual_review(*a,enable_local_vision=False)):
    httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    Thread(target=httpd.serve_forever,daemon=True).start()
    port=httpd.server_address[1]
    def req(method,path,body=None,headers=None):
     c=http.client.HTTPConnection('127.0.0.1',port,timeout=20);c.request(method,path,body=body,headers=headers or {})
     r=c.getresponse();d=r.read();c.close();return r.status,json.loads(d) if d[:1]==b'{' else d
    def wait(job,done):
     end=time.monotonic()+30
     while time.monotonic()<end:
      if durable_mode:durable.work_once(root)
      code,st=req('GET','/api/jobs/'+job)
      if code==200 and st['status'] in done:return st
      time.sleep(.2)
     self.fail('timeout '+str(st))
    try:
     ctx={'audience':'gamers'}
     code,r=req('POST','/api/url',json.dumps({'url':'https://www.tiktok.com/@a/video/123','editorial_context':ctx}).encode(),{'Content-Type':'application/json'})
     self.assertEqual(code,202)
     blocked=wait(r['job_id'],('needs_fallback','failed','completed'))
     self.assertEqual(blocked['status'],'needs_fallback',blocked)
     self.assertEqual(blocked['reason'],'bot_challenge');self.assertIsNone(blocked['creative_score'])
     self.assertEqual(blocked['platform'],'tiktok')
     # attach validation
     self.assertEqual(req('POST','/api/jobs/'+'0'*32+'/attach',b'x',{'X-Filename':'a.mp4','Content-Length':'1'})[0],404)
     body=clip.read_bytes()
     hdr={'X-Filename':'mine.mp4','Content-Length':str(len(body)),'Content-Type':'video/mp4'}
     code,new=req('POST',f"/api/jobs/{blocked['job_id']}/attach",body,hdr)
     self.assertEqual(code,202,new);self.assertEqual(new['fallback_of'],blocked['job_id'])
     done=wait(new['job_id'],('completed','failed'))
     self.assertEqual(done['status'],'completed',done)
     self.assertIsNone(done['creative_score'])
     self.assertEqual(done['metadata']['editorial_context'],ctx)
     again=req('GET','/api/jobs/'+blocked['job_id'])[1]
     self.assertEqual(again['resolved_by'],new['job_id'])
     self.assertEqual(req('POST',f"/api/jobs/{blocked['job_id']}/attach",body,hdr)[0],409)
     # a completed job cannot be attached to
     self.assertEqual(req('POST',f"/api/jobs/{new['job_id']}/attach",body,hdr)[0],409)
    finally:
     httpd.shutdown();httpd.server_close()
 def test_plain_mode(self):self._run(False)
 def test_durable_mode(self):self._run(True)

if __name__=='__main__':unittest.main()
