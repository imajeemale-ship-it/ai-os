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
import trends as trendlib
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
    tokens_in = frame_count * PER_IMAGE_TOKENS + transcript_chars // 4 + 7000  # + rubric, principles and trend packet
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


KNOWLEDGE_WEIGHT, TREND_WEIGHT, TREND_MAX = 0.8, 0.2, 20


def _validate_trend(item, trend_packet, now):
    """Trend fit (0-20). Needs a fresh packet and 2+ citations of real packet metrics."""
    if not trend_packet:
        return None, 'no trend snapshot (set YOUTUBE_API_KEY so trends can be fetched)'
    if not trendlib.is_fresh(trend_packet, now):
        return None, 'trend snapshot is older than 48 hours or too small'
    if not isinstance(item, dict):
        return None, 'judge did not evaluate trend fit'
    score, ev = item.get('score'), item.get('evidence')
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= TREND_MAX:
        return None, 'invalid trend score'
    metrics = set(trend_packet['stats'])
    good = [e for e in (ev if isinstance(ev, list) else []) if isinstance(e, dict) and e.get('metric') in metrics
            and isinstance(e.get('observation'), str) and e['observation'].strip()]
    if len(good) < rubric.MIN_CITATIONS:
        return None, f'needs at least {rubric.MIN_CITATIONS} observations citing real trend metrics'
    fixes = [f for f in (item.get('fixes') or []) if isinstance(f, dict) and isinstance(f.get('fix'), str)][:3]
    if score < TREND_MAX * 0.8 and not fixes:
        return None, 'below 80% but no fix given'
    return {'points': score, 'maximum': TREND_MAX, 'evidence': [{'metric': e['metric'], 'observation': e['observation'].strip()[:300]} for e in good][:6],
            'feedback': str(item.get('feedback', ''))[:500], 'fixes': [{'fix': f['fix'][:300]} for f in fixes]}, None


def _validate(judgments, available, duration, principle_ids=frozenset()):
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
        cited = [i for i in (item.get('principles') or []) if i in principle_ids]
        kept[key] = {'principles': cited, 'score': score, 'evidence': [{'timestamp_seconds': e['timestamp_seconds'],
                                                  'observation': e['observation'].strip()[:400]} for e in good][:8],
                     'feedback': str(item.get('feedback', ''))[:600], '_fixes': [
                         {'timestamp_seconds': f['timestamp_seconds'], 'fix': f['fix'][:300]} for f in fixes]}
    return kept, notes


def score_video(video, technical, timeline, job_dir, judge, *, max_usd, platforms=None, frame_count=24,
                video_hash=None, context=None, trends=None, principles=None, now=None):
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
                  'principles': [{k: p[k] for k in ('id', 'text', 'source', 'confidence')} for p in (principles or [])],
                  'trends': trends,
                  'frames': fr, 'transcript_text': transcriptlib.as_prompt_text(tr) if tr else ''}
        judged = judge.judge(packet)
    available = set()
    if fr: available.add('frames')
    if tr: available.add('transcript')
    if timeline: available.add('timeline')
    if measures: available.add('audio_measures')
    kept, notes = _validate(judged, available, duration, frozenset(p['id'] for p in (principles or [])))
    trend_result, trend_note = _validate_trend((judged or {}).get('trend_fit'), trends, now)
    card = build_scorecard({'duration_seconds': duration, 'video_hash': video_hash},
                           {k: {x: v[x] for x in ('score', 'evidence', 'feedback')} for k, v in kept.items()})
    for key, v in kept.items():
        card['categories'][key]['fixes'] = v['_fixes']
        card['categories'][key]['principles'] = v['principles']
    for key, why in notes.items():
        card['categories'][key]['reason'] = why
    knowledge = card['content_quality_score']
    trend_pct = None if trend_result is None else round(trend_result['points'] / TREND_MAX * 100, 1)
    overall = None if knowledge is None or trend_pct is None else round(KNOWLEDGE_WEIGHT * knowledge + TREND_WEIGHT * trend_pct, 1)
    recommendation = 'PENDING_REVIEW' if overall is None else ('PUBLISH' if overall >= 85 else 'REVISE' if overall >= 65 else 'REWORK')
    caveats = ['Draft rubric: weights and cutoffs are unvalidated until calibrated against human scores.',
               'A model judged this; treat it as a second opinion for the editor, not a ground truth.',
               'Trend fit is a dated snapshot of public popularity, 20% of the overall score. It is not knowledge of any platform algorithm.']
    if not principles:
        caveats.append('No approved principles were available: the knowledge part rests on the draft anchors only.')
    result = {'rubric': rubric.VERSION, 'status': 'scored' if overall is not None else 'partial',
              'weights': {'knowledge': KNOWLEDGE_WEIGHT, 'trends': TREND_WEIGHT},
              'knowledge_score': knowledge, 'trend_fit': trend_result if trend_result else {'status': 'not_evaluated', 'reason': trend_note},
              'trend_fit_percent': trend_pct, 'overall_score': overall, 'recommendation': recommendation,
              'scorecard': card, 'inputs': sorted(available), 'estimate': est,
              'principles_used': [p['id'] for p in (principles or [])],
              'trend_snapshot': ({'scope': trends['scope'], 'retrieved_at': trends['retrieved_at'], 'count': trends['stats'].get('count')} if trends else None),
              'usage': (judged or {}).get('_usage'),
              'platform_fit': platformlib.check_all(technical, platforms),
              'caveats': caveats, 'generated_at': time.time()}
    return result
