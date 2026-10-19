"""MVI editorial rubric: score only categories supported by reviewed evidence."""
import json
from pathlib import Path
from vindex_adapter import RUBRIC

def build_scorecard(evidence, judgments=None):
    judgments=judgments or {}
    categories={}; total=0; complete=True
    for key,maximum in RUBRIC.items():
        item=judgments.get(key)
        if item is None:
            categories[key]={'score':None,'maximum':maximum,'status':'not_evaluated'};complete=False;continue
        score=item.get('score'); citations=item.get('evidence',[])
        if not isinstance(score,(int,float)) or not 0<=score<=maximum or not citations:
            raise ValueError(f'{key}: valid score and timestamped evidence required')
        for citation in citations:
            if not isinstance(citation.get('timestamp_seconds'),(int,float)) or citation['timestamp_seconds']<0 or citation['timestamp_seconds']>evidence['duration_seconds']:
                raise ValueError(f'{key}: evidence timestamp out of range')
            if not citation.get('observation'):raise ValueError(f'{key}: observation required')
        categories[key]={'score':score,'maximum':maximum,'status':'evaluated','evidence':citations,'feedback':item.get('feedback','')};total+=score
    return {'rubric_version':'mvi-gaming-v1','source_video_hash':evidence.get('video_hash'),'categories':categories,'content_quality_score':total if complete else None,'youtube_optimization_score':None,'recommendation':'PENDING_REVIEW' if not complete else ('PUBLISH' if total>=85 else 'REVISE' if total>=65 else 'REWORK'),'scoring_complete':complete}

def save_scorecard(evidence_file,judgments_file,output):
    result=build_scorecard(json.loads(Path(evidence_file).read_text()),json.loads(Path(judgments_file).read_text()))
    Path(output).write_text(json.dumps(result,indent=2)+'\n');return result
