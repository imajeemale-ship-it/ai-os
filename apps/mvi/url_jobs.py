"""Bounded YouTube media retrieval for the local MVI prototype."""
import json,subprocess,sys
from pathlib import Path
from link_intake import inspect,video_id,parse_link

def retrieve(url,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    link=parse_link(url)
    platform=link['platform']
    if platform=='youtube':
        meta=inspect(url)
    else:
        meta={'source':platform,'url':link['url'],'title':platform.capitalize()+' video','content_quality_score':None,'analysis_status':'awaiting_authorized_media_access'}
    canonical=meta['url']
    cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--socket-timeout','20','--js-runtimes','node','--max-filesize','300M','-f','bv*[height<=720]+ba/b[height<=720]/bv*+ba/b','-o',str(directory/'source.%(ext)s'),canonical]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if p.returncode:raise RuntimeError(platform.capitalize()+' retrieval unavailable: '+p.stderr[-350:])
    matches=[x for x in directory.glob('source.*') if x.suffix.lower() in ('.mp4','.webm','.mkv','.mov')]
    if not matches:raise RuntimeError('No supported media retrieved')
    path=matches[0]
    if path.stat().st_size>300*1024*1024: path.unlink();raise RuntimeError('Video exceeds 300MB limit')
    if path.suffix.lower() not in ('.mp4','.mov'):
        converted=directory/'source.mp4'
        mux=subprocess.run(['ffmpeg','-y','-i',str(path),'-c','copy',str(converted)],capture_output=True,text=True,timeout=120)
        if mux.returncode:raise RuntimeError('Cannot remux retrieved video to MP4: '+mux.stderr[-250:])
        path.unlink();path=converted
    return meta,path


def fetch_captions(url,directory):
    """Best effort: save English captions as captions.vtt. Never raises; missing captions are normal."""
    directory=Path(directory)
    try:
        from link_intake import parse_link
        if parse_link(url)['platform']!='youtube':return None
        subprocess.run([sys.executable,'-m','yt_dlp','--skip-download','--no-playlist','--write-subs','--write-auto-subs',
            '--sub-langs','en.*,en','--sub-format','vtt','--socket-timeout','20','-o',str(directory/'cap.%(ext)s'),url],
            capture_output=True,text=True,timeout=90)
        found=sorted(directory.glob('cap*.vtt'))
        if not found:return None
        target=directory/'captions.vtt'
        found[0].replace(target)
        for extra in found[1:]:extra.unlink()
        return target
    except Exception:
        return None
