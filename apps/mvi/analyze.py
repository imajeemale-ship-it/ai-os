"""MVI V0 deterministic media inspection; no fabricated creative scores."""
import argparse, json, subprocess, pathlib, statistics

def probe(path):
    result = subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)

def analyze(path):
    p=pathlib.Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() not in ('.mp4','.mov'):
        raise ValueError('Accessible MP4/MOV file required')
    meta=probe(p); streams=meta.get('streams',[]); video=next((s for s in streams if s['codec_type']=='video'),None)
    audio=next((s for s in streams if s['codec_type']=='audio'),None)
    if not video: raise ValueError('No video stream found')
    duration=float(meta['format'].get('duration',0)); fps=video.get('avg_frame_rate','0/1')
    return {'file':p.name,'duration_seconds':round(duration,2),'resolution':f"{video.get('width')}x{video.get('height')}",'frame_rate':fps,'video_codec':video.get('codec_name'),'audio_present':bool(audio),'audio_codec':audio.get('codec_name') if audio else None,'technical_observations':['Audio stream absent' if not audio else 'Audio stream present'],'content_quality_score':None,'youtube_optimization_score':None,'recommendation':'NOT_SCORED','limitations':['Technical metadata only; no visual/audio semantic analysis performed. Creative scoring withheld.']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('video');ap.add_argument('--output');a=ap.parse_args()
    report=analyze(a.video); serialized=json.dumps(report,indent=2)
    if a.output:pathlib.Path(a.output).write_text(serialized+'\n')
    print(serialized)
