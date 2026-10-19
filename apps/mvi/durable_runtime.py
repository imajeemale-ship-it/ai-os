"""Opt-in durable MVI API/worker runtime. Single-host private prototype."""
import json
import tempfile
import os
import time
from pathlib import Path
from durable_queue import DurableQueue
from queue_worker import run_once
from job_state import save as save_job
from url_jobs import retrieve
from engine import inspect
from vindex_runner import compile_video_evidence
from editor_handoff import build_brief
from review_pipeline import review


def enabled():
    return os.environ.get('MVI_DURABLE_QUEUE') == '1'


def queue(root):
    return DurableQueue(Path(root)/'private'/'queue.db')


def enqueue(root, job_id, kind, payload):
    return queue(root).enqueue(job_id, kind, payload)


def state(root, job_id):
    entry=queue(root).get(job_id)
    if entry is None:
        return None
    status=entry['status']
    if status=='completed':
        winner=(entry.get('result') or {}).get('attempt')
        if winner is not None:
            path=Path(root)/job_id/('attempt-'+str(winner))/'job.json'
            if path.is_file():
                result=json.loads(path.read_text())
                result.update(status='completed',
                    report_url=f'/api/reports/{job_id}/editor',
                    handoff_url=f'/api/reports/{job_id}/handoff')
                return result
    return {'job_id':job_id,'status':status,'attempts':entry['attempts'],
            'error':entry['error'] if status=='failed' else None,
            'creative_score':None}


def report_path(root,job_id,kind):
    entry=queue(root).get(job_id)
    if entry is None or entry['status']!='completed':
        return None
    winner=(entry.get('result') or {}).get('attempt')
    if not isinstance(winner,int):
        return None
    names={'editor':'EDITOR_REPORT.md','handoff':'DAVID_EDITOR_HANDOFF.md',
           'timeline':'editor_report.json'}
    if kind not in names:
        return None
    path=Path(root)/job_id/('attempt-'+str(winner))/names[kind]
    return path if path.is_file() else None

def process(root, claim):
    job=claim['job_id'];directory=Path(root)/job
    payload=claim['payload']
    # Keep each attempt's outputs isolated; no retry may publish over a previous attempt.
    attempt_dir=directory/('attempt-'+str(claim['attempt']))
    attempt_dir.mkdir(mode=0o700,exist_ok=False)
    if claim['kind']=='url':
        meta,path=retrieve(payload['url'],attempt_dir)
    else:
        path=directory/payload['filename']
        if not path.is_file():
            raise FileNotFoundError('Durable upload is missing')
        meta={'title':payload['title']}
    technical=inspect(path,attempt_dir/'evidence')
    try:
        timeline=compile_video_evidence(path,attempt_dir/'vindex')
        vindex_status='completed'
    except Exception as exc:
        timeline=None
        vindex_status='unavailable: '+str(exc)[:250]
    (attempt_dir/'DAVID_EDITOR_HANDOFF.md').write_text(build_brief(meta.get('title','M3 video'),timeline))
    report=review(attempt_dir,meta,technical,timeline,
                  enable_local_vision=os.environ.get('MVI_ENABLE_LOCAL_VISION')=='1',source_path=path)
    result={'job_id':job,'status':'completed','metadata':meta,
            'technical_report':technical,'vindex_status':vindex_status,
            'timeline':timeline,'editor_report':report,
            'creative_score':None,'attempt':claim['attempt']}
    # This is an attempt-local staging record. The API uses it only if the
    # durable queue reports completed with the matching attempt.
    save_job(attempt_dir,result)
    return {'attempt':claim['attempt']}


def work_once(root):
    # Reports stay in the winning attempt directory, so readers never observe
    # partially copied artifacts or output from an expired competing worker.
    return run_once(queue(root),lambda claim:process(root,claim))

def serve_worker(root,poll=2):
    while True:
        try:
            if work_once(root) is None:
                time.sleep(poll)
        except Exception as exc:
            print('MVI worker attempt failed:',str(exc)[:250],flush=True)
            time.sleep(poll)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default=os.environ.get('MVI_DATA_DIR',str(Path.home()/'.mvi')))
    p.add_argument('--once',action='store_true');args=p.parse_args()
    if args.once: print(work_once(args.root))
    else: serve_worker(args.root)
