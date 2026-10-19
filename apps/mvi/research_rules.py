"""Evidence-safe channel strategy suggestions for MVI reports."""
from pathlib import Path
PLAYBOOK=Path(__file__).parent/'research'/'M3_CHANNEL_PLAYBOOK.md'
FIELDS=('series_premise','viewer_promise','hook_evidence','title_variants','thumbnail_concepts','retention_hypotheses','CTA_opportunities','series_continuity','research_sources')
def report_template(video_id):
 return {'video_id':video_id,'strategy_source':'https://youtu.be/MBQYIgsbSAY','strategy_status':'research_hypotheses_not_video_findings','editorial_score':None,'youtube_optimization_score':None,'research_fields':{name:None for name in FIELDS},'next_steps':['Identify series premise and audience promise','Propose three distinct title/thumbnail concepts','Check actual retention data before conclusions']}
