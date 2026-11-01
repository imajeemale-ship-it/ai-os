"""Evidence-gated scoring. Disabled unless the owner sets a spend cap; judge output is untrusted.

Flow: gather evidence -> sample frames -> judge -> validate per category -> scorecard.
A category with too few citations, a missing prerequisite, or invalid numbers becomes
`not_evaluated` instead of being guessed, and the overall result stays PENDING_REVIEW.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import frames as framelib
import platforms as platformlib
import rubric
import transcript as transcriptlib
from scorecard import build_scorecard
from vindex_adapter import RUBRIC

FRAME_WIDTH = 768
PER_IMAGE_TOKENS = int(FRAME_WIDTH * (FRAME_WIDTH * 9 / 16) / 750)


def _float(name, default=0.0):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def gate():
    cap = _float('MVI_SCORER_MAX_USD')
    price_in, price_out = _float('MVI_SCORER_USD_PER_MTOK_IN'), _float('MVI_SCORER_USD_PER_MTOK_OUT')
    problems = []
    if cap <= 0:
        problems.append('MVI_SCORER_MAX_USD is 0: scoring is disabled until the owner sets a spend cap')
    if not os.environ.get('MVI_SCORER_MODEL'):
        problems.append('MVI_SCORER_MODEL is not set')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        problems.append('ANTHROPIC_API_KEY is not set')
    if price_in <= 0 or price_out <= 0:
        problems.append('Token prices (MVI_SCORER_USD_PER_MTOK_IN/OUT) are not set, so cost cannot be estimated')
    return {'enabled': not problems, 'problems': problems, 'max_usd': cap, 'price_in': price_in, 'price_out': price_out}


def estimate_usd(frame_count, transcript_chars, g=None):
    g = g or gate()
    tokens_in = frame_count * PER_IMAGE_TOKENS + transcript_chars // 4 + 3500
    tokens_out = 4000  # equals the judge's max_tokens, so the estimate is an upper bound on output
    usd = (tokens_in * g['price_in'] + tokens_out * g['price_out']) / 1_000_000
    return {'tokens_in': tokens_in, 'tokens_out': tokens_out, 'estimated_usd': round(usd, 4)}


def _atomic(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.score-')
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def load_transcript(job_dir):
    for suffix in ('.vtt', '.srt', '.txt', '.md'):
        p = Path(job_dir) / ('transcript' + suffix)
        if p.is_file():
            return transcriptlib.parse(p.read_text(errors='replace'), suffix)
    return None


def _validate(judgments, available, duration):
    """Keep only categories that are fully supported; explain every rejection."""
    kept, notes = {}, {}
    cats = (judgments or {}).get('categories')
    cats = cats if isinstance(cats, dict) else {}
    for key, maximum in RUBRIC.items():
        item = cats.get(key)
        missing = rubric.REQUIRES[key] - available
        if missing:
            notes[key] = 'missing input: ' + ', '.join(sorted(missing))
            continue
        if not isinstance(item, dict):
            notes[key] = 'judge did not evaluate this category'
            continue
        score, ev = item.get('score'), item.get('evidence')
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= maximum:
            notes[key] = 'invalid score'
            continue
        if not isinstance(ev, list) or len(ev) < rubric.MIN_CITATIONS:
            notes[key] = f'needs at least {rubric.MIN_CITATIONS} timestamped observations'
            continue
        good = [e for e in ev if isinstance(e, dict) and isinstance(e.get('timestamp_seconds'), (int, float))
                and not isinstance(e.get('timestamp_seconds'), bool)
                and 0 <= e['timestamp_seconds'] <= duration and isinstance(e.get('observation'), str) and e['observation'].strip()]
        if len(good) < rubric.MIN_CITATIONS:
            notes[key] = 'observations missing, empty or outside the video'
            continue
        fixes = [f for f in (item.get('fixes') or []) if isinstance(f, dict) and isinstance(f.get('fix'), str)
                 and isinstance(f.get('timestamp_seconds'), (int, float)) and 0 <= f['timestamp_seconds'] <= duration][:5]
        if score < maximum * 0.8 and not fixes:
            notes[key] = 'below 80% of maximum but no timestamped fix given'
            continue
        kept[key] = {'score': score, 'evidence': [{'timestamp_seconds': e['timestamp_seconds'],
                                                  'observation': e['observation'].strip()[:400]} for e in good][:8],
                     'feedback': str(item.get('feedback', ''))[:600], '_fixes': [
                         {'timestamp_seconds': f['timestamp_seconds'], 'fix': f['fix'][:300]} for f in fixes]}
    return kept, notes


def score_video(video, technical, timeline, job_dir, judge, *, max_usd, platforms=None, frame_count=24,
                video_hash=None, context=None):
    duration = float(technical['duration_seconds'])
    jdir = Path(job_dir)
    tr = load_transcript(jdir)
    with tempfile.TemporaryDirectory() as tmp:
        fr = framelib.sample(video, tmp, duration, frame_count, FRAME_WIDTH)
        windows = [[0.0, duration]]
        for item in (timeline or {}).get('timeline', []):
            if item.get('type') == 'low_audio_signal':
                windows.append([item['start_seconds'], item['end_seconds']])
        measures = framelib.measure_audio(video, windows) if technical.get('audio_present') else []
        g = gate()
        est = estimate_usd(len(fr), len(transcriptlib.as_prompt_text(tr)) if tr else 0, g)
        if est['estimated_usd'] > max_usd:
            raise PermissionError(f"Estimated cost ${est['estimated_usd']} exceeds the allowed ${max_usd}")
        packet = {'facts': {'duration_seconds': duration, 'resolution': technical.get('resolution'),
                            'audio_measures_db': measures, 'editorial_context': context or {},
                            'scene_count': (timeline or {}).get('scene_count'),
                            'transcript_stats': transcriptlib.stats(tr, duration) if tr else None},
                  'frames': fr, 'transcript_text': transcriptlib.as_prompt_text(tr) if tr else ''}
        judged = judge.judge(packet)
    available = set()
    if fr: available.add('frames')
    if tr: available.add('transcript')
    if timeline: available.add('timeline')
    if measures: available.add('audio_measures')
    kept, notes = _validate(judged, available, duration)
    card = build_scorecard({'duration_seconds': duration, 'video_hash': video_hash},
                           {k: {x: v[x] for x in ('score', 'evidence', 'feedback')} for k, v in kept.items()})
    for key, v in kept.items():
        card['categories'][key]['fixes'] = v['_fixes']
    for key, why in notes.items():
        card['categories'][key]['reason'] = why
    result = {'rubric': rubric.VERSION, 'status': 'scored' if card['scoring_complete'] else 'partial',
              'scorecard': card, 'inputs': sorted(available), 'estimate': est,
              'usage': (judged or {}).get('_usage'),
              'platform_fit': platformlib.check_all(technical, platforms),
              'caveats': ['Draft rubric: weights and cutoffs are unvalidated until calibrated against human scores.',
                          'A model judged this; treat it as a second opinion for the editor, not a ground truth.',
                          'Trends and algorithm behavior are not scored.'],
              'generated_at': time.time()}
    return result
