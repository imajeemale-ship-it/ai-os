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
HTML='''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>MVI Studio</title>
<style>body{font:16px system-ui;background:#10151e;color:#e9eef5;max-width:850px;margin:50px auto;padding:20px}button,input{padding:12px;border-radius:8px}button{background:#8cc5ff;border:0;cursor:pointer}pre{white-space:pre-wrap;background:#202b3a;padding:20px;border-radius:12px}small{color:#aab8c7}a{color:#8cc5ff}</style></head>
<body><h1>M3 Video Intelligence</h1>
<p>Private pilot. Enter the pilot token, then upload a video or analyze a YouTube link.</p>
<input id="token" type="password" placeholder="MVI pilot token" autocomplete="off" style="width:70%">
<button onclick="saveToken()">Save token</button>
<hr><input id="url" placeholder="https://www.youtube.com/watch?v=..." style="width:70%"><button onclick="submitUrl()">Analyze link</button>
<hr><input id="file" type="file" accept="video/mp4,video/quicktime"><button onclick="go()">Analyze upload</button>
<p id="status"></p><pre id="result">Awaiting video</pre><div id="downloads"></div>
<small>Token stays in this browser session and is never displayed in results.</small>
<script>
const tokenInput=document.getElementById("token"),result=document.getElementById("result"),status=document.getElementById("status"),downloads=document.getElementById("downloads");
tokenInput.value=sessionStorage.getItem("mvi_token")||"";
function saveToken(){const t=tokenInput.value.trim();if(t)sessionStorage.setItem("mvi_token",t);else sessionStorage.removeItem("mvi_token");status.textContent=t?"Token saved for this session":"Token cleared";}
function headers(extra={}){const t=sessionStorage.getItem("mvi_token")||tokenInput.value.trim();return t?{...extra,Authorization:"Bearer "+t}:extra}
async function api(url,options={}){const r=await fetch(url,{...options,headers:headers(options.headers||{})});let d;try{d=await r.json()}catch{d={error:await r.text()}};return {r,d}}
function showJob(j){result.textContent=JSON.stringify(j,null,2);status.textContent=j.status;downloads.innerHTML="";if(j.report_url){for(const [label,kind] of [["Open editor report","editor"],["Download David handoff","handoff"],["Download timeline","timeline"]]){const b=document.createElement("button");b.textContent=label;b.onclick=()=>downloadReport(j.job_id,kind,label);downloads.append(" ",b)}}}
async function downloadReport(id,kind,label){const r=await fetch("/api/reports/"+id+"/"+kind,{headers:headers()});if(!r.ok){status.textContent="Report download failed ("+r.status+")";return}const blob=await r.blob(),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=id+"-"+kind+(kind==="timeline"?".json":".md");a.click();URL.revokeObjectURL(a.href);status.textContent=label+" ready"}
async function poll(id){try{const x=await api("/api/jobs/"+id),j=x.d;showJob(j);if(j.status==="retrieving"||["queued","running","compiling_timeline","reviewing_frames"].includes(j.status))setTimeout(()=>poll(id),2500)}catch(e){status.textContent=e.message}}
async function submitUrl(){const u=document.getElementById("url").value.trim();status.textContent="Submitting…";const x=await api("/api/url",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:u})});showJob(x.d);if(x.r.ok)poll(x.d.job_id)}
async function go(){const f=document.getElementById("file").files[0];if(!f){status.textContent="Choose an MP4 or MOV first";return}status.textContent="Uploading…";const x=await api("/api/upload",{method:"POST",headers:{"Content-Type":f.type||"application/octet-stream","X-Filename":encodeURIComponent(f.name)},body:f});showJob(x.d);if(x.r.ok)poll(x.d.job_id)}
</script></body></html>'''
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
  if self.path=='/health':return self.respond(200,{'status':'ok','version':'prototype'})
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
 host=os.environ.get('MVI_BIND_HOST','127.0.0.1');port=int(os.environ.get('PORT',a.port))
 print(f'MVI service http://{host}:{port}',flush=True)
 ThreadingHTTPServer((host,port),Handler).serve_forever()
