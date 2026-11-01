"""MVI local prototype dashboard; bind localhost only until authenticated cloud deployment."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote
import json, os, tempfile, uuid, threading
from urllib.parse import unquote
from url_jobs import retrieve, fetch_captions
from engine import inspect
from editor_handoff import build_brief
from review_pipeline import review
from job_state import save as save_job, load as load_job
import durable_runtime as durable
from vindex_runner import compile_video_evidence
import learning_brain as learning
from link_intake import parse_link
from fallback import build_record
import judges, scoring, transcript as transcriptlib, platforms as platformlib
from job_access import locate
ROOT=Path(os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))

def authorized(handler):
 token=os.environ.get('MVI_API_TOKEN','')
 if not token:
  return os.environ.get('MVI_REQUIRE_AUTH') != '1'  # Private loopback only.
 import hmac
 provided=handler.headers.get('Authorization','')
 return hmac.compare_digest(provided,'Bearer '+token)
HTML=Path(__file__).with_name('brain_studio.html').read_text(encoding='utf-8')
def editorial_context(raw):
 if not isinstance(raw,dict):return {}
 return {key: value.strip()[:240] for key in
         ('audience','viewer_promise','viewer_outcome','intended_style')
         if isinstance((value:=raw.get(key)),str) and value.strip()}

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
   vindex_status="unavailable: "+str(exc)[:3000]
  (directory/"DAVID_EDITOR_HANDOFF.md").write_text(build_brief(meta.get('title','M3 video'),timeline))
  JOBS[job]["status"]="reviewing_frames"
  save_job(directory,JOBS[job])
  editor_report=review(directory,meta,result,timeline,enable_local_vision=os.environ.get('MVI_ENABLE_LOCAL_VISION')=='1',source_path=path)
  JOBS[job].update({"status":"completed","metadata":meta,"technical_report":result,"vindex_status":vindex_status,"timeline":timeline,"editor_handoff_file":"DAVID_EDITOR_HANDOFF.md","editor_report":editor_report,"report_url":f"/api/reports/{job}/editor","handoff_url":f"/api/reports/{job}/handoff","creative_score":None})
 except Exception as exc:
  JOBS[job].update({"status":"failed","error":str(exc)[:500]})
 save_job(directory,JOBS[job])

def run_url_job(job,url,directory,context=None):
 try:
  JOBS[job]["status"]="retrieving"
  save_job(directory,JOBS[job])
  meta,path=retrieve(url,directory)
  if context:meta['editorial_context']=context
  if not any(directory.glob('transcript.*')):
   cap=fetch_captions(url,directory)
   if cap is not None:cap.replace(directory/'transcript.vtt')
 except Exception as exc:
  try:platform=parse_link(url)['platform']
  except ValueError:platform='unknown'
  JOBS[job]=build_record(job,platform,url,str(exc),context or None)
  save_job(directory,JOBS[job])
  return
 run_media_job(job,path,directory,meta)

SCORE_LOCK=threading.Lock()
def get_judge():
 return judges.from_env()

def _job_or_none(job):
 return locate(ROOT,job,durable.enabled(),JOBS)

def run_score_job(job,max_usd,platforms):
 info=_job_or_none(job);status=ROOT/job/'score_status.json'
 try:
  status.write_text(json.dumps({'status':'running','started':__import__('time').time()}))
  judge=get_judge()
  if judge is None:raise RuntimeError('Scoring judge is not configured')
  frames=min(max(int(os.environ.get('MVI_SCORER_FRAMES','24')),2),48)
  ctx=(info['state'].get('metadata') or {}).get('editorial_context')
  result=scoring.score_video(info['video'],info['technical'],info['timeline'],ROOT/job,judge,
                             max_usd=max_usd,platforms=platforms,frame_count=frames,context=ctx)
  scoring._atomic(ROOT/job/'score.json',result)
  status.write_text(json.dumps({'status':'done'}))
 except Exception as exc:
  status.write_text(json.dumps({'status':'failed','error':str(exc)[:300]}))
class Handler(BaseHTTPRequestHandler):
 def respond(self,code,data,kind='application/json'):
  b=data.encode() if isinstance(data,str) else json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/health':return self.respond(200,{'status':'ok','version':'prototype'})
  # The shell is public so it can collect a token in-browser; every API route remains protected.
  if self.path=='/':return self.respond(200,HTML,'text/html; charset=utf-8')
  if not authorized(self):return self.respond(401,{'error':'unauthorized'})
  if self.path.startswith('/api/learn/jobs/'):
   job=self.path.split('/')[-1]
   if not (len(job)==32 and all(c in '0123456789abcdef' for c in job)):
    return self.respond(400,{'error':'invalid job'})
   state=learning.learning_state(ROOT,job)
   return self.respond(200,state) if state is not None else self.respond(404,{'error':'learning job not found'})
  if self.path.startswith('/api/jobs/') and self.path.rsplit('/',1)[-1] in ('score','platform-fit'):
   parts=self.path.split('/')
   job=parts[3] if len(parts)==5 else ''
   if not (len(job)==32 and all(c in '0123456789abcdef' for c in job)):return self.respond(400,{'error':'invalid job'})
   info=_job_or_none(job)
   if info is None:return self.respond(404,{'error':'job not found'})
   if parts[4]=='platform-fit':
    if not info['technical']:return self.respond(409,{'error':'analysis not finished'})
    return self.respond(200,platformlib.check_all(info['technical']))
   done=ROOT/job/'score.json'
   if done.is_file():return self.respond(200,json.loads(done.read_text()))
   st=ROOT/job/'score_status.json'
   body={'status':'not_scored','gate':scoring.gate()['problems']}
   if st.is_file():body.update(json.loads(st.read_text()))
   return self.respond(200,body)
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
  if self.path=='/api/learn/url':
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=4096:return self.respond(400,{'error':'invalid request size'})
    data=json.loads(self.rfile.read(size))
    from link_intake import video_id
    url=data['url']
    ident=video_id(url)
    canonical='https://www.youtube.com/watch?v='+ident
    job=uuid.uuid4().hex;folder=ROOT/job
    folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    durable.enqueue(ROOT,job,'learn_url',{'url':canonical,'title':str(data.get('title') or '')[:240]})
    if not durable.enabled():
     threading.Thread(target=durable.work_once,args=(ROOT,),daemon=True).start()
    return self.respond(202,{'job_id':job,'status':'queued','hemisphere':'learning'})
   except Exception as exc:return self.respond(400,{'error':str(exc)[:240]})
  if self.path=='/api/learn/upload':
   try:
    size=int(self.headers.get('Content-Length','0'))
    title=unquote(self.headers.get('X-Filename',''))
    suffix=Path(title).suffix.lower()
    if suffix not in learning.ALLOWED_UPLOADS:
     return self.respond(400,{'error':'Upload MP4, MOV, TXT, MD, SRT, or VTT'})
    limit=learning.MAX_VIDEO_BYTES if suffix in ('.mp4','.mov') else learning.MAX_TEXT_BYTES
    if not 0<size<=limit:return self.respond(400,{'error':'Learning file exceeds size limit'})
    job=uuid.uuid4().hex;folder=ROOT/job
    folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    filename='learning'+suffix;source=folder/filename
    with source.open('xb') as out:
     os.chmod(source,0o600)
     left=size
     while left:
      block=self.rfile.read(min(left,1024*1024))
      if not block:raise ValueError('Incomplete upload')
      out.write(block);left-=len(block)
    durable.enqueue(ROOT,job,'learn_upload',{'filename':filename,'title':Path(title).name[:240]})
    if not durable.enabled():
     threading.Thread(target=durable.work_once,args=(ROOT,),daemon=True).start()
    return self.respond(202,{'job_id':job,'status':'queued','hemisphere':'learning'})
   except Exception as exc:return self.respond(400,{'error':str(exc)[:240]})
  if self.path=='/api/learn/decide':
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=2048:return self.respond(400,{'error':'invalid request size'})
    data=json.loads(self.rfile.read(size))
    job=data['job_id'];card=data['card_id']
    if not (isinstance(job,str) and len(job)==32 and
            all(c in '0123456789abcdef' for c in job) and
            isinstance(card,str) and len(card)==16 and
            all(c in '0123456789abcdef' for c in card)):
     return self.respond(400,{'error':'invalid learning card'})
    return self.respond(200,learning.decide(ROOT,job,card,data['decision']))
   except (ValueError,KeyError,TypeError) as exc:
    return self.respond(400,{'error':str(exc)[:240]})
  if self.path=='/api/url':
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=4096:return self.respond(400,{'error':'invalid request size'})
    data=json.loads(self.rfile.read(size));url=data['url']
    context=editorial_context(data.get('editorial_context'))
    parse_link(url)
    job=uuid.uuid4().hex;directory=ROOT/job;directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    JOBS[job]={'job_id':job,'status':'queued','url':url,'creative_score':None}
    save_job(directory,JOBS[job])
    if durable.enabled():durable.enqueue(ROOT,job,'url',{'url':url,'editorial_context':context})
    else:threading.Thread(target=run_url_job,args=(job,url,directory,context),daemon=True).start()
    return self.respond(202,JOBS[job])
   except Exception as exc:return self.respond(400,{'error':str(exc)[:250]})
  if self.path.startswith('/api/jobs/') and self.path.rsplit('/',1)[-1] in ('transcript','score'):
   parts=self.path.split('/')
   job=parts[3] if len(parts)==5 else ''
   if not (len(job)==32 and all(c in '0123456789abcdef' for c in job)):return self.respond(400,{'error':'invalid job'})
   info=_job_or_none(job)
   if info is None:return self.respond(404,{'error':'job not found'})
   try:
    if parts[4]=='transcript':
     size=int(self.headers.get('Content-Length','0'))
     name=unquote(self.headers.get('X-Filename',''));suffix=Path(name).suffix.lower()
     if suffix not in ('.txt','.md','.vtt','.srt'):return self.respond(400,{'error':'Upload TXT, MD, VTT or SRT'})
     if not 0<size<=2*1024*1024:return self.respond(400,{'error':'Transcript must be under 2 MB'})
     raw=self.rfile.read(size)
     if len(raw)!=size:return self.respond(400,{'error':'Incomplete upload'})
     text=raw.decode('utf-8',errors='replace')
     parsed=transcriptlib.parse(text,suffix)
     for old in ROOT.joinpath(job).glob('transcript.*'):old.unlink()
     target=ROOT/job/('transcript'+suffix)
     target.write_text(text);os.chmod(target,0o600)
     duration=(info['technical'] or {}).get('duration_seconds')
     return self.respond(200,{'job_id':job,'transcript':transcriptlib.stats(parsed,duration)})
    # score
    g=scoring.gate()
    if not g['enabled']:return self.respond(403,{'error':'Scoring is disabled','reasons':g['problems']})
    if not (info['technical'] and info['video']):return self.respond(409,{'error':'analysis not finished or source video missing'})
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=2048:return self.respond(400,{'error':'invalid request size'})
    data=json.loads(self.rfile.read(size))
    confirm=data.get('confirm_max_usd')
    if isinstance(confirm,bool) or not isinstance(confirm,(int,float)) or confirm<=0:
     return self.respond(400,{'error':'confirm_max_usd is required and must be positive'})
    cap=min(float(confirm),g['max_usd'])
    plats=[p for p in (data.get('platforms') or []) if p in platformlib.PLATFORMS] or None
    tr=scoring.load_transcript(ROOT/job)
    est=scoring.estimate_usd(min(max(int(os.environ.get('MVI_SCORER_FRAMES','24')),2),48),
                             len(transcriptlib.as_prompt_text(tr)) if tr else 0,g)
    if est['estimated_usd']>cap:
     return self.respond(400,{'error':'Estimated cost exceeds the allowed maximum','estimate':est,'allowed_usd':cap})
    if not SCORE_LOCK.acquire(blocking=False):return self.respond(409,{'error':'A scoring run is already in progress'})
    try:
     st=ROOT/job/'score_status.json'
     if st.is_file():
      prior=json.loads(st.read_text())
      fresh=__import__('time').time()-float(prior.get('started') or 0)<1800
      if prior.get('status')=='running' and fresh:
       return self.respond(409,{'error':'This job is already being scored'})
     (ROOT/job/'score_status.json').write_text(json.dumps({'status':'running','started':__import__('time').time()}))
    finally:SCORE_LOCK.release()
    threading.Thread(target=run_score_job,args=(job,cap,plats),daemon=True).start()
    return self.respond(202,{'job_id':job,'status':'scoring','estimate':est,'allowed_usd':cap})
   except (ValueError,KeyError,TypeError) as exc:return self.respond(400,{'error':str(exc)[:240]})
  attach_job=None;blocked=None
  if self.path.startswith('/api/jobs/') and self.path.endswith('/attach'):
   parts=self.path.split('/')
   attach_job=parts[3] if len(parts)==5 else ''
   if not (len(attach_job)==32 and all(c in '0123456789abcdef' for c in attach_job)):
    return self.respond(400,{'error':'invalid job'})
   if durable.enabled():blocked=durable.state(ROOT,attach_job)
   elif attach_job in JOBS:blocked=JOBS[attach_job]
   elif (ROOT/attach_job/'job.json').is_file():blocked=load_job(ROOT/attach_job/'job.json')
   if blocked is None:return self.respond(404,{'error':'job not found'})
   if blocked.get('status')!='needs_fallback':return self.respond(409,{'error':'job does not need a fallback'})
   if blocked.get('resolved_by') or (ROOT/attach_job/'resolved.json').is_file():
    return self.respond(409,{'error':'job already has an attached video'})
  elif self.path!='/api/upload':return self.respond(404,{'error':'not found'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   name=__import__('urllib.parse',fromlist=['unquote']).unquote(self.headers.get('X-Filename',''))
   ext=Path(name).suffix.lower()
   try:context=editorial_context(json.loads(unquote(self.headers.get('X-MVI-Context','{}'))))
   except (ValueError,TypeError):return self.respond(400,{'error':'invalid editorial context'})
   if attach_job and not context:context=editorial_context((blocked or {}).get('editorial_context'))
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
   if attach_job:
    JOBS[job]['fallback_of']=attach_job
    (ROOT/attach_job/'resolved.json').write_text(json.dumps({'resolved_by':job}))
    if attach_job in JOBS:JOBS[attach_job]['resolved_by']=job
   save_job(directory,JOBS[job])
   if durable.enabled():durable.enqueue(ROOT,job,'upload',{'filename':video.name,'title':name[:200],'editorial_context':context})
   else:threading.Thread(target=run_media_job,args=(job,video,directory,{'title':name[:200],'editorial_context':context}),daemon=True).start()
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
