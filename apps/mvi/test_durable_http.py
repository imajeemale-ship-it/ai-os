"""HTTP ingestion to durable worker, real video, and report retrieval."""
import http.client,json,os,subprocess,tempfile,time,unittest
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server,durable_runtime

class DurableHttpTests(unittest.TestCase):
 def test_upload_survives_server_and_is_processed_by_worker(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/'jobs';root.mkdir()
   video=Path(temp)/'clip.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
     'testsrc2=size=160x90:rate=10','-t','1','-pix_fmt','yuv420p','-y',str(video)],check=True)
   with patch.dict(os.environ,{'MVI_DURABLE_QUEUE':'1','MVI_ENABLE_LOCAL_VISION':'0'}),patch.object(server,'ROOT',root),patch.object(durable_runtime,'compile_video_evidence',return_value={'shots':[],'scene_count':0}):
    httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
    def request(method,path,body=None,headers=None):
     conn=http.client.HTTPConnection('127.0.0.1',httpd.server_address[1],timeout=15)
     conn.request(method,path,body=body,headers=headers or {})
     res=conn.getresponse();code=res.status;data=res.read();conn.close();return code,data
    try:
     data=video.read_bytes()
     code,raw=request('POST','/api/upload',data,{'Content-Length':str(len(data)),'X-Filename':'clip.mp4'})
     self.assertEqual(code,202,raw)
     job=json.loads(raw)['job_id']
     self.assertEqual(json.loads(request('GET','/api/jobs/'+job)[1])['status'],'queued')
     self.assertEqual(request('GET',f'/api/reports/{job}/editor')[0],404)
     # Simulate API restart; worker has no dependency on the old HTTP process.
     httpd.shutdown();httpd.server_close();thread.join()
     durable_runtime.work_once(root)
     httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
     thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
     code,raw=request('GET','/api/jobs/'+job)
     self.assertEqual(code,200)
     self.assertEqual(json.loads(raw)['status'],'completed')
     self.assertEqual(request('GET',f'/api/reports/{job}/editor')[0],200)
     self.assertEqual(request('GET',f'/api/reports/{job}/handoff')[0],200)
    finally:
     httpd.shutdown();httpd.server_close();thread.join()

if __name__=='__main__':unittest.main()
