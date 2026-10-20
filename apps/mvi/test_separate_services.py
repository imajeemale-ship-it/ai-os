"""Real API and worker subprocesses share one durable data directory."""
import http.client,json,os,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path

class SeparateServiceTests(unittest.TestCase):
 def test_api_worker_independent_processes(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'mvi';root.mkdir()
   video=Path(tmp)/'input.mp4'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
       'testsrc2=size=160x90:rate=10','-t','1','-pix_fmt','yuv420p','-y',str(video)],check=True)
   with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   env={**os.environ,'MVI_DURABLE_QUEUE':'1','MVI_ENABLE_LOCAL_VISION':'0','MVI_DATA_DIR':str(root)}
   api=subprocess.Popen([sys.executable,'server.py','--port',str(port)],env=env,
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   worker=None
   def request(method,path,body=None,headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
    try:
     conn.request(method,path,body=body,headers=headers or {})
     res=conn.getresponse();return res.status,res.read()
    finally:conn.close()
   try:
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
     try:
      if request('GET','/health')[0]==200:break
     except OSError:time.sleep(.1)
    else:self.fail('API did not start')
    data=video.read_bytes()
    status,body=request('POST','/api/upload',data,{'Content-Length':str(len(data)),'X-Filename':'input.mp4'})
    self.assertEqual(status,202,body)
    job=json.loads(body)['job_id']
    self.assertEqual(json.loads(request('GET','/api/jobs/'+job)[1])['status'],'queued')
    worker=subprocess.Popen([sys.executable,'durable_runtime.py','--root',str(root)],env=env,
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
     state=json.loads(request('GET','/api/jobs/'+job)[1])
     if state['status']=='completed':break
     if state['status']=='failed':self.fail(str(state))
     time.sleep(.25)
    else:self.fail('Worker did not complete: '+str(state))
    self.assertEqual(request('GET',f'/api/reports/{job}/editor')[0],200)
    self.assertEqual(request('GET',f'/api/reports/{job}/handoff')[0],200)
   finally:
    for proc in (worker,api):
     if proc is not None:
      proc.terminate()
      try:proc.wait(timeout=5)
      except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':unittest.main()
