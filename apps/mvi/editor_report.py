"""Readable evidence-grounded editor report; suggestions are review prompts, not findings."""
import json
from pathlib import Path

def timestamp(seconds):
 seconds=max(0,int(seconds));return f'{seconds//60:02d}:{seconds%60:02d}'

def build_report(metadata,technical,timeline=None,visual_review=None):
 duration=technical.get('duration_seconds',0)
 shots=(timeline or {}).get('shots',[])
 title=metadata.get('title') or 'M3 Video'
 rows=[]
 for shot in shots:
  start=shot['start_seconds'];end=shot['end_seconds']
  rows.append({'start_seconds':start,'end_seconds':end,'type':'scene_boundary','observation':'Vindex detected a scene/shot interval.','recommendation':'Check whether this transition advances the story; this is a review prompt, not a quality finding.','evidence_source':'vindex_scene_detection','verified':True})
 for item in (visual_review or {}).get('observations',[]):
  t=item.get('timestamp_seconds');ob=item.get('observation')
  if isinstance(t,(int,float)) and 0<=t<=duration and isinstance(ob,str) and ob.strip():
   rows.append({'start_seconds':t,'end_seconds':t,'type':'sampled_frame_observation','observation':ob.strip(),'recommendation':'Review surrounding footage to decide whether an edit is needed.','evidence_source':'sampled_frame_vision_model','verified':False})
 rows.sort(key=lambda x:x['start_seconds'])
 return {'title':title,'duration_seconds':duration,'creative_score':None,'status':'evidence_review_pending','summary':f'{len(shots)} scene/shot intervals detected; semantic editing quality not yet established.','timeline':rows,'editor_checks':[{'section':'Opening','time_range':'00:00–00:15','question':'Are the GTA stakes or payoff clear in the opening?'},{'section':'Visual focus','time_range':'Throughout','question':'Do overlays and effects compete with gameplay?'},{'section':'Narrative','time_range':'Throughout','question':'Can a new viewer follow Rico’s goal, setback and payoff?'},{'section':'Sound','time_range':'Throughout','question':'Is dialogue intelligible above music and game audio?'},{'section':'Ending','time_range':f'{timestamp(max(0,duration-15))}–{timestamp(duration)}','question':'Does the ending deliver on the opening promise?'}],'limitations':['Scene boundaries are not proof of good or bad pacing.','No retention or CTR analytics available.','Audio quality, humor and narrative cannot be scored from scene detection alone.']}

def render_markdown(report):
 out=[f'# MVI Editor Report — {report["title"]}','',f'**Duration:** {timestamp(report["duration_seconds"])} | **Status:** Evidence review pending | **Creative score:** Not assigned','',report['summary'],'','## Timeline for David']
 for row in report['timeline']:
  out.append(f'- **{timestamp(row["start_seconds"])}–{timestamp(row["end_seconds"])}** [{row["type"]}] {row["observation"]} **Next:** {row["recommendation"]}')
 out+=['','## Editing checklist']
 for item in report['editor_checks']:out.append(f'- **{item["section"]} ({item["time_range"]}):** {item["question"]}')
 out+=['','## Limitations']+['- '+x for x in report['limitations']]
 return '\n'.join(out)+'\n'

def save_report(directory,metadata,technical,timeline=None,visual_review=None):
 directory=Path(directory);r=build_report(metadata,technical,timeline,visual_review)
 (directory/'editor_report.json').write_text(json.dumps(r,indent=2)+'\n')
 (directory/'EDITOR_REPORT.md').write_text(render_markdown(r))
 return r
