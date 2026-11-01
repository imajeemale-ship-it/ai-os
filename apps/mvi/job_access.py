"""Locate a finished job's evidence and source video in either runtime mode."""
import json
from pathlib import Path


def locate(root, job_id, durable_mode, memory=None):
    """Return dict(state, dir, video, technical, timeline) or None. Never raises for missing files."""
    root = Path(root)
    job_dir = root / job_id
    if not job_dir.is_dir():
        return None
    state, search = None, [job_dir]
    if durable_mode:
        import durable_runtime as durable
        state = durable.state(root, job_id)
        entry = durable.queue(root).get(job_id)
        winner = ((entry or {}).get('result') or {}).get('attempt')
        if isinstance(winner, int):
            search.insert(0, job_dir / f'attempt-{winner}')
    else:
        state = (memory or {}).get(job_id)
        if state is None and (job_dir / 'job.json').is_file():
            state = json.loads((job_dir / 'job.json').read_text())
    video = None
    for d in search:
        for name in ('upload.mp4', 'upload.mov', 'source.mp4', 'source.mov'):
            p = d / name
            if p.is_file() and not p.is_symlink():
                video = p
                break
        if video:
            break
    state = state or {}
    return {'state': state, 'dir': job_dir, 'video': video,
            'technical': state.get('technical_report'), 'timeline': state.get('timeline')}
