"""Optional audiovisual review stages with explicit evidence provenance."""
from pathlib import Path
from editor_report import save_report, render_markdown
from vision import evaluate
from audio_signal import measure
from human_evidence import load as load_human_evidence

def review(directory,metadata,technical,timeline=None,enable_local_vision=True,source_path=None):
 directory=Path(directory)
 visual=None;warnings=[]
 if enable_local_vision:
  try:
   visual=evaluate(directory/'evidence')
  except Exception as exc:
   warnings.append('Local vision review unavailable: '+str(exc)[:220])
 audio=None
 if technical.get('audio_present'):
  try:
   audio=measure(directory/'evidence'/'audio.wav',technical.get('duration_seconds',0))
  except Exception as exc:
   warnings.append('Audio signal review unavailable: '+str(exc)[:220])
 human=None
 try:
  human=load_human_evidence(directory,source_path,technical)
 except Exception as exc:
  warnings.append('Human frame notes excluded: '+str(exc)[:220])
 report=save_report(directory,metadata,technical,timeline,visual,audio,human)
 try:
  from learning_brain import approved_principles
  import os
  root=Path(os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))
  report['learned_principles']=approved_principles(root,metadata.get('title',''))
 except Exception as exc:
  warnings.append('Learning library not available: '+str(exc)[:150])
  report['learned_principles']=[]
 report['review_stages']={'scene_timeline':'completed' if timeline else 'unavailable','sampled_frame_vision':'completed' if visual else ('unavailable' if enable_local_vision else 'disabled'),'audio_signal':'completed' if audio else 'unavailable','audio_semantics':'not_implemented','full_motion':'not_implemented','human_inspected_frames':'completed' if human else 'unavailable'}
 report['review_warnings']=warnings
 report['limitations'].append('A local vision model may misdescribe individual frames; all such observations require human verification.')
 import json
 (directory/'editor_report.json').write_text(json.dumps(report,indent=2)+'\n')
 (directory/'EDITOR_REPORT.md').write_text(render_markdown(report))
 return report
