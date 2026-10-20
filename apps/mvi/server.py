"""MVI local prototype dashboard; bind localhost only until authenticated cloud deployment."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote
import json, os, tempfile, uuid, threading
from url_jobs import retrieve
from engine import inspect
from editor_handoff import build_brief
from review_pipeline import review
from job_state import save as save_job, load as load_job
import durable_runtime as durable
from vindex_runner import compile_video_evidence
ROOT=Path(os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))

def authorized(handler):
 token=os.environ.get('MVI_API_TOKEN','')
 if not token:
  return os.environ.get('MVI_REQUIRE_AUTH') != '1'  # Private loopback only.
 import hmac
 provided=handler.headers.get('Authorization','')
 return hmac.compare_digest(provided,'Bearer '+token)
HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>MVI Studio</title><style>body{font:16px system-ui;background:#10151e;color:#e9eef5;max-width:850px;margin:50px auto;padding:20px}button,input{padding:12px;border-radius:8px}button{background:#8cc5ff;border:0;cursor:pointer}pre{white-space:pre-wrap;background:#202b3a;padding:20px;border-radius:12px}small{color:#aab8c7}</style></head><body><h1>M3 Video Intelligence</h1><p>Paste a YouTube link, or upload a video. Processing runs locally.</p><input id="url" placeholder="https://www.youtube.com/watch?v=..." style="width:70%"><button onclick="submitUrl()">Analyze link</button><hr><input id="file" type="file" accept="video/mp4,video/quicktime"><button onclick="go()">Analyze</button><p id="status"></p><pre id="result">Awaiting video</pre><small>Prototype: no creative scoring yet. Local access only. Do not expose to the public internet.</small><script>async function submitUrl(){let u=document.getElementById("url").value;document.getElementById("status").textContent="Submitting…";try{let r=await fetch("/api/url",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});let d=await r.json();document.getElementById("result").textContent=JSON.stringify(d,null,2);if(!r.ok)return;let id=d.job_id;let poll=async()=>{let x=await fetch("/api/jobs/"+id);let j=await x.json();document.getElementById("result").textContent=JSON.stringify(j,null,2);document.getElementById("status").textContent=j.status;if(j.report_url){document.getElementById("status").innerHTML="Completed — <a style=\"color:#8cc5ff\" href=\""+j.report_url+"\" target=\"_blank\">Open editor report</a> · <a style=\"color:#8cc5ff\" href=\""+j.handoff_url+"\" target=\"_blank\">David handoff</a>";}if(j.status==="queued"||j.status==="retrieving"||j.status==="running"||j.status==="compiling_timeline"||j.status==="reviewing_frames")setTimeout(poll,2500)};poll()}catch(e){document.getElementById("status").textContent=e.message}} async function go(){let f=document.getElementById('file').files[0];if(!f)return;document.getElementById('status').textContent='Processing…';try{let r=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':f.type||'application/octet-stream','X-Filename':encodeURIComponent(f.name)},body:f});let data=await r.json();document.getElementById('result').textContent=JSON.stringify(data,null,2);document.getElementById('status').textContent=r.ok?'Analysis queued':'Error';if(r.ok)pollUpload(data.job_id);}catch(e){document.getElementById('status').textContent=e.message}} async function pollUpload(id){try{let r=await fetch('/api/jobs/'+id);let j=await r.json();document.getElementById('result').textContent=JSON.stringify(j,null,2);document.getElementById('status').textContent=j.status;if(j.report_url){document.getElementById('status').innerHTML='Completed — <a href="'+j.report_url+'">Open editor report</a> · <a href="'+j.handoff_url+'">David handoff</a>';}if(['queued','running','compiling_timeline','reviewing_frames'].includes(j.status))setTimeout(()=>pollUpload(id),2500)}catch(e){document.getElementById('status').textContent=e.message}}</script></body></html>'''
JOBS={}
def run_media_job(job,path,directory,meta):
 """Produce identical reports for uploaded videos and retrieved links."""
 try:
  JOBS[job]["status"]="running"
  save_job(directory,JOBS[job])
  result=inspect(path,directory/"evidence")
  JOBS[job]["status"]="compiling_timeline"
  save_job(directory,JOBS[job])
  try:
   timeline=compile_video_evidence(path,directory/"vindex")
   vindex_status="completed"
  except Exception as exc:
   timeline=None
   vindex_status="unavailable: "+str(exc)[:250]
  (directory/"DAVID_EDITOR_HANDOFF.md").write_text(build_brief(meta.get('title','M3 video'),timeline))
  JOBS[job]["status"]="reviewing_frames"
  save_job(directory,JOBS[job])
  editor_report=review(directory,meta,result,timeline,enable_local_vision=os.environ.get('MVI_ENABLE_LOCAL_VISION')=='1',source_path=path)
  JOBS[job].update({"status":"completed","metadata":meta,"technical_report":result,"vindex_status":vindex_status,"timeline":timeline,"editor_handoff_file":"DAVID_EDITOR_HANDOFF.md","editor_report":editor_report,"report_url":f"/api/reports/{job}/editor","handoff_url":f"/api/reports/{job}/handoff","creative_score":None})
 except Exception as exc:
  JOBS[job].update({"status":"failed","error":str(exc)[:500]})
 save_job(directory,JOBS[job])

def run_url_job(job,url,directory):
 try:
  JOBS[job]["status"]="retrieving"
  save_job(directory,JOBS[job])
  meta,path=retrieve(url,directory)
 except Exception as exc:
  JOBS[job].update({"status":"failed","error":str(exc)[:500]})
  save_job(directory,JOBS[job])
  return
 run_media_job(job,path,directory,meta)
class Handler(BaseHTTPRequestHandler):
 def respond(self,code,data,kind='application/json'):
  b=data.encode() if isinstance(data,str) else json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if not authorized(self):return self.respond(401,{'error':'unauthorized'})
  if self.path=='/':return self.respond(200,HTML,'text/html; charset=utf-8')
  if self.path.startswith('/api/jobs/'):
   job=self.path.split('/')[-1]
   if not (len(job)==32 and all(c in '0123456789abcdef' for c in job)):return self.respond(400,{'error':'invalid job'})
   if durable.enabled():
    queued=durable.state(ROOT,job)
    return self.respond(200,queued) if queued is not None else self.respond(404,{'error':'job not found'})
   if job in JOBS:return self.respond(200,JOBS[job])
   saved=ROOT/job/'job.json'
   return self.respond(200,load_job(saved)) if saved.is_file() else self.respond(404,{'error':'job not found'})
  if self.path.startswith('/api/reports/'):
   parts=self.path.split('/')
   if len(parts)!=5:return self.respond(404,{'error':'not found'})
   _,api,reports,job,kind=parts
   if len(job)!=32 or any(c not in '0123456789abcdef' for c in job):return self.respond(400,{'error':'invalid job'})
   names={'editor':'EDITOR_REPORT.md','handoff':'DAVID_EDITOR_HANDOFF.md','timeline':'editor_report.json'}
   if kind not in names:return self.respond(404,{'error':'unknown report'})
   if durable.enabled():
    path=durable.report_path(ROOT,job,kind)
    if path is None:return self.respond(404,{'error':'report not ready'})
   else:path=ROOT/job/names[kind]
   if not path.is_file():return self.respond(404,{'error':'report not ready'})
   return self.respond(200,path.read_text(),'application/json' if kind=='timeline' else 'text/markdown; charset=utf-8')
  if self.path=='/health':return self.respond(200,{'status':'ok','version':'prototype'})
  self.respond(404,{'error':'not found'})
 def do_POST(self):
  if not authorized(self):return self.respond(401,{'error':'unauthorized'})
  if self.path=='/api/url':
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=4096:return self.respond(400,{'error':'invalid request size'})
    data=json.loads(self.rfile.read(size));url=data['url']
    from link_intake import video_id
    video_id(url)
    job=uuid.uuid4().hex;directory=ROOT/job;directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    JOBS[job]={'job_id':job,'status':'queued','url':url,'creative_score':None}
    save_job(directory,JOBS[job])
    if durable.enabled():durable.enqueue(ROOT,job,'url',{'url':url})
    else:threading.Thread(target=run_url_job,args=(job,url,directory),daemon=True).start()
    return self.respond(202,JOBS[job])
   except Exception as exc:return self.respond(400,{'error':str(exc)[:250]})
  if self.path!='/api/upload':return self.respond(404,{'error':'not found'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   name=__import__('urllib.parse',fromlist=['unquote']).unquote(self.headers.get('X-Filename',''))
   ext=Path(name).suffix.lower()
   if ext not in ('.mp4','.mov') or not 0<length<=500*1024*1024:return self.respond(400,{'error':'MP4/MOV required; 500MB maximum'})
   job=uuid.uuid4().hex;directory=ROOT/job;directory.mkdir(mode=0o700,parents=True,exist_ok=False)
   video=directory/('upload'+ext)
   with video.open('wb') as out:
    remaining=length
    while remaining:
     chunk=self.rfile.read(min(1024*1024,remaining))
     if not chunk:raise ValueError('Incomplete upload')
     out.write(chunk);remaining-=len(chunk)
   JOBS[job]={'job_id':job,'status':'queued','title':name[:200],'creative_score':None}
   save_job(directory,JOBS[job])
   if durable.enabled():durable.enqueue(ROOT,job,'upload',{'filename':video.name,'title':name[:200]})
   else:threading.Thread(target=run_media_job,args=(job,video,directory,{'title':name[:200]}),daemon=True).start()
   self.respond(202,JOBS[job])
  except Exception as exc:self.respond(400,{'error':str(exc)[:250]})
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args()
 if os.environ.get('MVI_REQUIRE_AUTH')=='1' and not os.environ.get('MVI_API_TOKEN'):
  raise SystemExit('MVI_REQUIRE_AUTH=1 requires MVI_API_TOKEN')
 print(f'MVI local prototype http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
