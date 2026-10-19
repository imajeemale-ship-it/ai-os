"""Boundary between Vindex evidence compilation and MVI editorial scoring."""
import json, pathlib, subprocess, sys
RUBRIC={'opening_hook':20,'storytelling_engagement':20,'pacing_retention':20,'humor_entertainment':15,'sound_design':10,'visual_polish':10,'ending_payoff':5}

def normalize(memory):
    timeline=memory.get('timeline',{})
    shots=[]
    for scene in timeline.get('scenes',[]):
        for shot in scene.get('shots',[]):
            shots.append({'start_seconds':shot['start_ms']/1000,'end_seconds':shot['end_ms']/1000,'caption':(shot.get('caption') or {}),'asr_words':shot.get('asr_words',[]),'ocr':shot.get('ocr',[])})
    return {'source':'vindex','schema_version':memory.get('schema_version'),'video_hash':memory.get('video_hash'),'duration_seconds':timeline.get('total_duration_ms',0)/1000,'shots':shots,'scene_count':len(timeline.get('scenes',[])),'rubric_maximums':RUBRIC,'content_quality_score':None,'youtube_optimization_score':None,'evidence_limitations':['Compilation artifacts are observations, not editorial judgments. Scores require grounded category assessment.']}

def compile_with_vindex(video,output,venv_python=None):
    interpreter=venv_python or sys.executable
    cmd=[str(interpreter),'-m','vindex.cli.main','compile',str(pathlib.Path(video).resolve()),'--output-dir',str(pathlib.Path(output).resolve()),'--stages','scene,frame']
    return subprocess.run(cmd,capture_output=True,text=True,timeout=600)

def load_artifact(path):return normalize(json.loads(pathlib.Path(path).read_text()))
