"""Run Vindex's installed scene/frame compiler without requiring optional AI runtimes."""
import json,os,subprocess,sys
from pathlib import Path
from vindex_adapter import load_artifact
VENDOR=Path(__file__).parent/'vendor-evaluation'/'vindex'
PYTHON=Path(__file__).parent/'.venv'/'bin'/'python'
def compile_video_evidence(video,output,timeout=600):
 if not VENDOR.exists():raise RuntimeError('Vindex is not installed; scene analysis unavailable')
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy();env['PYTHONPATH']=str(VENDOR)+os.pathsep+env.get('PYTHONPATH','')
 code='from pathlib import Path;from vindex.compiler.pipeline import compile_video;import sys;compile_video(Path(sys.argv[1]),Path(sys.argv[2]),{"stages":["scene","frame"],"sampling_strategy":"middle","use_cache":True})'
 p=subprocess.run([str(PYTHON if PYTHON.exists() else sys.executable),'-c',code,str(Path(video).resolve()),str(output.resolve())],capture_output=True,text=True,timeout=timeout,env=env)
 if p.returncode:raise RuntimeError('Vindex compilation failed: '+p.stderr[-700:])
 artifact=output/'visual_memory.json'
 if not artifact.exists():raise RuntimeError('Vindex did not produce visual_memory.json')
 result=load_artifact(artifact)
 (output/'mvi_timeline.json').write_text(json.dumps(result,indent=2))
 return result
