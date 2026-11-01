"""Validate and register YouTube submissions without inventing audiovisual evidence."""
import json,re,subprocess
from pathlib import Path
from urllib.parse import urlparse,parse_qs

def video_id(url):
    p=urlparse(url)
    host=(p.hostname or '').lower()
    if host in ('youtube.com','www.youtube.com','m.youtube.com'):
        candidate=parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else p.path.split('/')[2] if p.path.startswith(('/shorts/','/embed/')) and len(p.path.split('/'))>2 else ''
    elif host in ('youtu.be','www.youtu.be'):candidate=p.path.strip('/').split('/')[0]
    else:raise ValueError('Only YouTube links supported for this intake')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',candidate):raise ValueError('Invalid YouTube video ID')
    return candidate

TIKTOK_HOSTS={'tiktok.com','www.tiktok.com','m.tiktok.com','vm.tiktok.com','vt.tiktok.com'}
INSTAGRAM_HOSTS={'instagram.com','www.instagram.com'}
INSTAGRAM_PATHS=('/reel/','/reels/','/p/','/tv/')

def parse_link(url):
    """Return {'platform','url'} for supported public links; reject everything else."""
    if not isinstance(url,str) or len(url)>2048:raise ValueError('Invalid link')
    p=urlparse(url.strip())
    if p.scheme not in ('http','https'):raise ValueError('Link must start with https://')
    host=(p.hostname or '').lower()
    if host in TIKTOK_HOSTS and len(p.path.strip('/'))>0:
        return {'platform':'tiktok','url':f'https://{host}{p.path}'}
    if host in INSTAGRAM_HOSTS and p.path.startswith(INSTAGRAM_PATHS):
        return {'platform':'instagram','url':f'https://{host}{p.path}'}
    return {'platform':'youtube','url':'https://www.youtube.com/watch?v='+video_id(url)}

def inspect(url):
    vid=video_id(url)
    proc=subprocess.run(['python3','-m','yt_dlp','--skip-download','--dump-single-json','--no-playlist',f'https://www.youtube.com/watch?v={vid}'],capture_output=True,text=True,timeout=90)
    if proc.returncode:raise RuntimeError('Video metadata unavailable: '+proc.stderr[-350:])
    meta=json.loads(proc.stdout)
    return {'source':'youtube','video_id':vid,'url':f'https://www.youtube.com/watch?v={vid}','title':meta.get('title'),'duration_seconds':meta.get('duration'),'visibility':meta.get('availability'),'channel':meta.get('channel'),'analysis_status':'awaiting_authorized_media_access','content_quality_score':None,'note':'Metadata alone cannot support editorial scoring.'}

if __name__=='__main__':
 import sys
 print(json.dumps(inspect(sys.argv[1]),indent=2))
