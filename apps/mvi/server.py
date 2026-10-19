"""MVI local prototype dashboard; bind localhost only until authenticated cloud deployment."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import json, os, tempfile, uuid
from engine import inspect
ROOT=Path(os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))
HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>MVI Studio</title><style>body{font:16px system-ui;background:#10151e;color:#e9eef5;max-width:850px;margin:50px auto;padding:20px}button,input{padding:12px;border-radius:8px}button{background:#8cc5ff;border:0;cursor:pointer}pre{white-space:pre-wrap;background:#202b3a;padding:20px;border-radius:12px}small{color:#aab8c7}</style></head><body><h1>M3 Video Intelligence</h1><p>Upload a gaming video to extract timestamped evidence and technical findings.</p><input id="file" type="file" accept="video/mp4,video/quicktime"><button onclick="go()">Analyze</button><p id="status"></p><pre id="result">Awaiting video</pre><small>Prototype: no creative scoring yet. Local access only. Do not expose to the public internet.</small><script>async function go(){let f=document.getElementById('file').files[0];if(!f)return;document.getElementById('status').textContent='Processing…';try{let r=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':f.type||'application/octet-stream','X-Filename':encodeURIComponent(f.name)},body:f});let data=await r.json();document.getElementById('result').textContent=JSON.stringify(data,null,2);document.getElementById('status').textContent=r.ok?'Analysis finished':'Error';}catch(e){document.getElementById('status').textContent=e.message}}</script></body></html>'''
class Handler(BaseHTTPRequestHandler):
 def respond(self,code,data,kind='application/json'):
  b=data.encode() if isinstance(data,str) else json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/':return self.respond(200,HTML,'text/html; charset=utf-8')
  if self.path=='/health':return self.respond(200,{'status':'ok','version':'prototype'})
  self.respond(404,{'error':'not found'})
 def do_POST(self):
  if self.path!='/api/upload':return self.respond(404,{'error':'not found'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   name=__import__('urllib.parse',fromlist=['unquote']).unquote(self.headers.get('X-Filename',''))
   ext=Path(name).suffix.lower()
   if ext not in ('.mp4','.mov') or not 0<length<=500*1024*1024:return self.respond(400,{'error':'MP4/MOV required; 500MB maximum'})
   job=uuid.uuid4().hex;directory=ROOT/job;directory.mkdir(parents=True,exist_ok=False)
   video=directory/('upload'+ext)
   with video.open('wb') as out:
    remaining=length
    while remaining:
     chunk=self.rfile.read(min(1024*1024,remaining))
     if not chunk:raise ValueError('Incomplete upload')
     out.write(chunk);remaining-=len(chunk)
   result=inspect(video,directory/'evidence');result['job_id']=job
   self.respond(200,result)
  except Exception as exc:self.respond(400,{'error':str(exc)[:250]})
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args()
 print(f'MVI local prototype http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
