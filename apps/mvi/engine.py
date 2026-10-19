"""MVI evidence extraction. No semantic observations without a vision model."""
import json, math, pathlib, subprocess
from analyze import analyze

def run(*args):
    p=subprocess.run(args,capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1200:])
    return p.stdout

def inspect(path, output_dir):
    path=pathlib.Path(path).expanduser().resolve(); out=pathlib.Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    report=analyze(path); duration=report['duration_seconds']
    # Sample representative visual frames; images remain local until model consent/configuration.
    stamps=sorted(set(round(x,2) for x in [0.5,duration*.1,duration*.25,duration*.5,duration*.75,duration*.9,max(0,duration-1)] if x<duration))
    frames=[]
    for i,t in enumerate(stamps):
        target=out/f'frame_{i:02d}.jpg'
        run('ffmpeg','-hide_banner','-loglevel','error','-ss',str(t),'-i',str(path),'-frames:v','1','-q:v','3','-y',str(target))
        frames.append({'timestamp_seconds':t,'file':target.name})
    audio=out/'audio.wav'
    if report['audio_present']:
        run('ffmpeg','-hide_banner','-loglevel','error','-i',str(path),'-vn','-ac','1','-ar','16000','-y',str(audio))
    report.update({'frames':frames,'audio_extracted':audio.exists(),'evidence_level':'media_extracted_not_semantically_reviewed','revision_checklist':['Review sampled frames and audio with an authorized multimodal model before assigning creative scores.']})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(inspect(a.video,a.output),indent=2))
