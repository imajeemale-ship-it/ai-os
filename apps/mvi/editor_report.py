"""Readable evidence-grounded editor report; suggestions are review prompts, not findings."""
import json
import math
from pathlib import Path
from editorial_coach import coach

def valid_interval(start, end, duration, min_seconds=0):
 """Accept only finite, positive, in-range measured intervals as verified evidence."""
 return (all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
             for v in (start,end,duration))
         and duration>0 and 0<=start<end<=duration+0.1 and end-start>=min_seconds)

def timestamp(seconds):
 seconds=max(0,int(seconds));return f'{seconds//60:02d}:{seconds%60:02d}'

def precise_timestamp(seconds):
 seconds=max(0,float(seconds));minutes=int(seconds//60)
 return f'{minutes:02d}:{seconds-minutes*60:05.2f}'

def priority_audio_checks(audio_signal, duration):
 """Rank measured low-signal intervals for human review; never assert an edit defect."""
 checks=[]
 for interval in (audio_signal or {}).get('intervals',[]):
  if not isinstance(interval,dict):continue
  start=interval.get('start_seconds');end=interval.get('end_seconds')
  if not valid_interval(start,end,duration,min_seconds=1):
   continue
  near_end=end>max(0,duration-15)
  checks.append({'start_seconds':start,'end_seconds':end,'evidence_source':'ffmpeg_silencedetect',
   'verified':True,'reason':f'Measured {end-start:.2f}s low-audio interval'+(' overlapping the final 15 seconds' if near_end else ''),
   'action':'Listen in context; verify whether the low level is intentional'+(' for the outro/end card.' if near_end else ' or needs a mix adjustment.')})
 return sorted(checks,key=lambda c:(-(c['end_seconds']-c['start_seconds']),c['start_seconds']))[:3]

def cross_modal_checks(timeline, audio_signal, duration):
 """Find measured shot/low-audio overlaps; no assumptions about creative quality."""
 import math
 def valid_pair(item):
  if not isinstance(item, dict):
   return None
  a,b=item.get('start_seconds'),item.get('end_seconds')
  if (not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (a,b))
      or not 0 <= a < b <= duration+0.1):
   return None
  return (a,min(b,duration))
 shots=[pair for shot in (timeline or {}).get('shots',[]) if (pair:=valid_pair(shot))]
 silences=[pair for item in (audio_signal or {}).get('intervals',[]) if (pair:=valid_pair(item))]
 checks=[]
 for shot_start,shot_end in shots:
  for quiet_start,quiet_end in silences:
   start,end=max(shot_start,quiet_start),min(shot_end,quiet_end)
   overlap=end-start
   if overlap < 2 or overlap < .7*(shot_end-shot_start):
    continue
   checks.append({'start_seconds':round(start,2),'end_seconds':round(end,2),
                  'overlap_seconds':round(overlap,2),'evidence_sources':['vindex_scene_detection','ffmpeg_silencedetect'],
                  'verified':True,
                  'reason':'Measured shot interval overlaps a low-audio interval; no creative judgment inferred.',
                  'action':'Watch and listen to this section in context; confirm whether the sustained visual and quieter audio are intentional.'})
 return sorted(checks,key=lambda x:(-x['overlap_seconds'],x['start_seconds']))[:3]

def build_report(metadata,technical,timeline=None,visual_review=None,audio_signal=None,human_review=None):
 duration=technical.get('duration_seconds',0)
 shots=(timeline or {}).get('shots',[])
 title=metadata.get('title') or 'M3 Video'
 rows=[]
 for shot in shots:
  start=shot['start_seconds'];end=shot['end_seconds']
  rows.append({'start_seconds':start,'end_seconds':end,'type':'scene_boundary','observation':'Vindex detected a scene/shot interval.','recommendation':'Check whether this transition advances the story; this is a review prompt, not a quality finding.','evidence_source':'vindex_scene_detection','verified':True})
 sampled_times=[f.get('timestamp_seconds') for f in (visual_review or {}).get('evidence_frames',[]) if isinstance(f,dict)]
 for item in (visual_review or {}).get('observations',[]):
  t=item.get('timestamp_seconds');ob=item.get('observation')
  if isinstance(t,(int,float)) and 0<=t<=duration and any(isinstance(s,(int,float)) and abs(t-s)<=0.15 for s in sampled_times) and isinstance(ob,str) and ob.strip():
   rows.append({'start_seconds':t,'end_seconds':t,'type':'sampled_frame_observation','observation':ob.strip(),'recommendation':'Review surrounding footage to decide whether an edit is needed.','evidence_source':'sampled_frame_vision_model','verified':False})
 for item in (audio_signal or {}).get('intervals',[]):
  if not isinstance(item,dict):continue
  start=item.get('start_seconds');end=item.get('end_seconds')
  if valid_interval(start,end,duration):
   rows.append({'start_seconds':start,'end_seconds':end,'type':'low_audio_signal','observation':f'Measured low audio signal for {end-start:.2f} seconds.','recommendation':'Listen here and decide if this pause is intentional.','evidence_source':'ffmpeg_silencedetect','verified':True})
 for item in (human_review or {}).get('observations',[]):
  t=item['timestamp_seconds']
  rows.append({'start_seconds':t,'end_seconds':t,'type':'human_inspected_frame',
               'observation':item['observation'],'recommendation':item['editor_question'],
               'evidence_source':'human_inspected_sampled_frame','verified':True})
 rows.sort(key=lambda x:x['start_seconds'])
 return {'title':title,'duration_seconds':duration,'creative_score':None,'status':'evidence_review_pending','summary':f'{len(shots)} scene/shot intervals detected; semantic editing quality not yet established.','timeline':rows,'priority_checks':priority_audio_checks(audio_signal,duration),'cross_modal_checks':cross_modal_checks(timeline,audio_signal,duration),'editorial_coaching':coach(metadata,technical),'editor_checks':[{'section':'Opening','time_range':'00:00–00:15','question':'Are the GTA stakes or payoff clear in the opening?'},{'section':'Visual focus','time_range':'Throughout','question':'Do overlays and effects compete with gameplay?'},{'section':'Narrative','time_range':'Throughout','question':'Can a new viewer follow Rico’s goal, setback and payoff?'},{'section':'Sound','time_range':'Throughout','question':'Is dialogue intelligible above music and game audio?'},{'section':'Ending','time_range':f'{timestamp(max(0,duration-15))}–{timestamp(duration)}','question':'Does the ending deliver on the opening promise?'}],'limitations':['Scene boundaries are not proof of good or bad pacing.','No retention or CTR analytics available.','Audio quality, humor and narrative cannot be scored from scene detection alone.']}

def render_markdown(report):
 out=[f'# MVI Editor Report — {report["title"]}','',f'**Duration:** {timestamp(report["duration_seconds"])} | **Status:** Evidence review pending | **Creative score:** Not assigned','',report['summary'],'','## Timeline for David']
 for row in report['timeline']:
  clock=precise_timestamp if row['type'] in ('low_audio_signal','human_inspected_frame','sampled_frame_observation') else timestamp
  out.append(f'- **{clock(row["start_seconds"])}–{clock(row["end_seconds"])}** [{row["type"]}] {row["observation"]} **Next:** {row["recommendation"]}')
 if report.get('cross_modal_checks'):
  out+=['','## Cross-modal review checkpoints (measured overlap, not editing defects)']
  for item in report['cross_modal_checks']:
   out.append(f'- **{precise_timestamp(item["start_seconds"])}–{precise_timestamp(item["end_seconds"])}** ({item["overlap_seconds"]:.2f}s overlap): {item["reason"]} **Next:** {item["action"]}')
 if report.get('priority_checks'):
  out+=['','## Prioritized evidence checks (not editing defects)']
  for item in report['priority_checks']:
   out.append(f'- **{precise_timestamp(item["start_seconds"])}–{precise_timestamp(item["end_seconds"])}:** {item["reason"]}. **Next:** {item["action"]}')
 guidance=report.get('editorial_coaching')
 if guidance:
  out+=['','## Editorial coaching — expectation-first (questions, not detected defects)']
  out+=['','**Based on:** Jake Trinder, Give Me 15 Minutes and I’ll Make You Disgustingly Good at YouTube (https://www.youtube.com/watch?v=Dx-c19qXdxM).']
  if guidance['missing_context']:
   out+=['','**Provide before judging creative quality:**']+['- '+item for item in guidance['missing_context']]
  out+=['','### Highest-priority review points']
  for item in guidance['prioritized_review']:
   out.append(f'- **{item["time_range"]}**: {item["question"]} **Potential edit if needed:** {item["possible_edit"]} _(Requires footage review; not a confirmed problem.)_')
  out+=['','### Video acceptance criteria']+['- '+item for item in guidance['acceptance_criteria']]
  out+=['','### Do not overinterpret']
  out+=['- '+guidance['style_warning'],'- '+guidance['research_warning'],'- '+guidance['analytics_warning']]
 if report.get('learned_principles'):
  out+=['','## Approved knowledge sources (evaluate relevance; not detected defects)']
  for item in report['learned_principles']:
   source=item.get('source',{})
   out.append('- **'+str(source.get('title') or 'Learning source')+'**: '+str(item['excerpt'])+' — '+item['application'])
 out+=['','## Editing checklist']
 for item in report['editor_checks']:out.append(f'- **{item["section"]} ({item["time_range"]}):** {item["question"]}')
 if report.get('review_stages'):
  out+=['','## Review coverage']+['- '+k+': '+v for k,v in report['review_stages'].items()]
 if report.get('review_warnings'):
  out+=['','## Processing warnings']+['- '+x for x in report['review_warnings']]
 out+=['','## Limitations']+['- '+x for x in report['limitations']]
 return '\n'.join(out)+'\n'

def save_report(directory,metadata,technical,timeline=None,visual_review=None,audio_signal=None,human_review=None):
 directory=Path(directory);r=build_report(metadata,technical,timeline,visual_review,audio_signal,human_review)
 (directory/'editor_report.json').write_text(json.dumps(r,indent=2)+'\n')
 (directory/'EDITOR_REPORT.md').write_text(render_markdown(r))
 return r
