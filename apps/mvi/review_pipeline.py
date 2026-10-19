"""Optional audiovisual review stages with explicit evidence provenance."""
from pathlib import Path
from editor_report import save_report
from vision import evaluate

def review(directory,metadata,technical,timeline=None,enable_local_vision=True):
 directory=Path(directory)
 visual=None;warnings=[]
 if enable_local_vision:
  try:
   visual=evaluate(directory/'evidence')
  except Exception as exc:
   warnings.append('Local vision review unavailable: '+str(exc)[:220])
 report=save_report(directory,metadata,technical,timeline,visual)
 report['review_stages']={'scene_timeline':'completed' if timeline else 'unavailable','sampled_frame_vision':'completed' if visual else 'unavailable','audio_semantics':'not_implemented','full_motion':'not_implemented'}
 report['review_warnings']=warnings
 report['limitations'].append('A local vision model may misdescribe individual frames; all such observations require human verification.')
 import json
 (directory/'editor_report.json').write_text(json.dumps(report,indent=2)+'\n')
 return report
