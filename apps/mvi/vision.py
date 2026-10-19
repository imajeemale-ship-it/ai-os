"""Grounded visual review using locally installed Ollama Qwen3-VL."""
import base64,json,pathlib,urllib.request,urllib.error
CATEGORIES={'opening_hook':20,'storytelling_engagement':20,'pacing':20,'humor_entertainment':15,'sound_design':10,'visual_polish':10,'ending_payoff':5}
def evaluate(evidence_dir, model='qwen3-vl:4b'):
 root=pathlib.Path(evidence_dir); report=json.loads((root/'report.json').read_text());frames=report['frames']
 if not frames:raise ValueError('No frames available')
 images=[base64.b64encode((root/f['file']).read_bytes()).decode() for f in frames[:3]]
 prompt=('You are reviewing a gaming video using ONLY these sampled still frames in chronological order at timestamps '+str([f['timestamp_seconds'] for f in frames])+'. Do not infer motion, audio, jokes, editing pace, dialogue, or full-video narrative from stills. Give concise factual visual observations tied to these exact timestamps. Output ONLY JSON object with keys observations (array of objects with timestamp_seconds, observation, confidence), strengths (array), limitations (array). Do not provide numerical scores.')
 data=json.dumps({'model':model,'stream':False,'think':False,'format':'json','options':{'num_ctx':4096,'num_predict':650},'messages':[{'role':'user','content':prompt,'images':images}]}).encode()
 req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=data,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=240) as resp: answer=json.load(resp)
 except urllib.error.HTTPError as exc:
  details=exc.read(900).decode('utf-8','replace')
  raise RuntimeError(f'Ollama rejected review ({exc.code}): {details}') from exc
 content=answer.get('message',{}).get('content','').strip()
 if not content:raise RuntimeError('Vision model returned no visible answer; review withheld')
 result=json.loads(content);result['model']=model;result['evidence_frames']=frames[:3];result['creative_score']=None;result['limitations']=result.get('limitations',[])+['Still frames only; audio and continuous motion not reviewed. Scores intentionally withheld.']
 (root/'visual_review.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('evidence_dir');a=p.parse_args();print(json.dumps(evaluate(a.evidence_dir),indent=2))
