"""Bounded YouTube media retrieval for the local MVI prototype."""
import json,subprocess,sys
from pathlib import Path
from link_intake import inspect,video_id

def retrieve(url,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    meta=inspect(url)
    canonical=meta['url']
    cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--js-runtimes','node','--max-filesize','300M','-f','bv*[height<=720]+ba/b[height<=720]/bv*+ba/b','-o',str(directory/'source.%(ext)s'),canonical]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if p.returncode:raise RuntimeError('YouTube retrieval unavailable: '+p.stderr[-350:])
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
