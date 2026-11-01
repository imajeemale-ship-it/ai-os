"""The local helper uploads a finished file to MVI with a bearer token and never sends cookies."""
import json, os, subprocess, sys, tempfile, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import server
sys.path.insert(0,str(Path(__file__).with_name('tools')))
import mvi_local_fetch as helper

class HelperTests(unittest.TestCase):
 def test_upload_to_real_handler_requires_token_and_creates_job(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'j';root.mkdir()
   clip=Path(temp)/'c.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10','-t','1','-pix_fmt','yuv420p','-y',str(clip)],check=True)
   with patch.dict(os.environ,{'MVI_API_TOKEN':'secret-token','MVI_REQUIRE_AUTH':'1','MVI_DURABLE_QUEUE':'1'}),patch.object(server,'ROOT',root):
    httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    t=Thread(target=httpd.serve_forever,daemon=True);t.start()
    base=f'http://127.0.0.1:{httpd.server_address[1]}'
    try:
     with self.assertRaises(SystemExit):helper.upload(clip,base,'wrong')
     r=helper.upload(clip,base,'secret-token')
     self.assertEqual(r['status'],'queued');self.assertEqual(len(r['job_id']),32)
    finally:httpd.shutdown();httpd.server_close()
 def test_cookies_flag_only_goes_to_local_ytdlp(self):
  with patch('subprocess.run') as run,tempfile.TemporaryDirectory() as f:
   run.return_value.returncode=1
   with self.assertRaises(SystemExit):helper.fetch('https://x.test/v',f,'chrome')
   cmd=run.call_args[0][0];self.assertIn('--cookies-from-browser',cmd)
if __name__=='__main__':unittest.main()
