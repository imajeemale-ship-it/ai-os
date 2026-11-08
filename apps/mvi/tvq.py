"""Technical Visual Quality (TVQ): turn measurements plus an untrusted visual judgment into one 0-100 score.

Rules, in plain terms:
- Nine subscores with fixed weights (visual_quality.WEIGHTS).
- Six come from pixel measurements blended 50/50 with the judge; three are judged only.
- The judge's output is untrusted: numbers are range-checked, timestamps must be inside the video,
  and an evidence-visibility failure must quote narration that is really in the transcript.
- A subscore that cannot be supported becomes not_evaluated and the TVQ total stays pending.
- Container metadata (resolution, bitrate) is never an input here.
"""
import re

from visual_quality import (JUDGED_ONLY, MEASURED, SUBCATEGORY_NAMES, WEIGHTS, band)

DEFAULT_WEIGHT = 0.15
VISUAL_WEIGHT = 0.20               # gaming, trailers, UI/tutorial, product demos, detail-driven analysis
VISUAL_GAMES = ('gta', 'cod')      # the M3 channel's own games count as visually driven
SEVERITIES = ('low', 'medium', 'high')
NAME_TO_KEY = {v.lower(): k for k, v in SUBCATEGORY_NAMES.items()}
MAX_ISSUES = 20
BLEND = 0.5                        # measured share of a blended subscore


def weight_for(game, visually_driven=None):
    if visually_driven is None:
        visually_driven = game in VISUAL_GAMES
    return VISUAL_WEIGHT if visually_driven else DEFAULT_WEIGHT


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _key(sub):
    if not isinstance(sub, str):
        return None
    s = sub.strip().lower()
    if s in WEIGHTS:
        return s
    return NAME_TO_KEY.get(s.replace('_', ' '))


def _issues(raw, measured, duration):
    out = []
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        key = _key(it.get('subcategory'))
        start = it.get('timestamp_start', it.get('timestamp_seconds'))
        end = it.get('timestamp_end', start)
        sev = str(it.get('severity', '')).strip().lower()
        if key is None or sev not in SEVERITIES or not _num(start) or not _num(end):
            continue
        if not (0 <= start <= duration and 0 <= end <= duration + 0.5 and end >= start):
            continue
        texts = [it.get(k) for k in ('issue', 'impact', 'recommended_fix')]
        if not all(isinstance(t, str) and t.strip() for t in texts):
            continue
        out.append({'timestamp_start': round(float(start), 2), 'timestamp_end': round(float(end), 2),
                    'issue': texts[0].strip()[:300], 'subcategory': SUBCATEGORY_NAMES[key],
                    'severity': sev.capitalize(), 'impact': texts[1].strip()[:300],
                    'recommended_fix': texts[2].strip()[:300], 'source': 'judge'})
    out = out[:MAX_ISSUES]
    for it in (measured or {}).get('issues', []):
        if len(out) >= MAX_ISSUES + 8:
            break
        out.append(it)
    return out


def _supported(claim, transcript_text):
    """A quoted narration claim must really appear in the transcript (most of its words)."""
    if not isinstance(claim, str) or not transcript_text:
        return False
    words = [w for w in re.findall(r"[a-z0-9']+", claim.lower()) if len(w) > 2]
    if len(words) < 2:
        return False
    have = set(re.findall(r"[a-z0-9']+", transcript_text.lower()))
    return sum(w in have for w in words) / len(words) >= 0.6


def _failures(raw, transcript_text, duration):
    out = []
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        t = it.get('timestamp_seconds', it.get('timestamp'))
        if not _num(t) or not 0 <= t <= duration:
            continue
        if not _supported(it.get('narration_claim'), transcript_text):
            continue
        if not all(isinstance(it.get(k), str) and it[k].strip() for k in ('problem', 'fix')):
            continue
        out.append({'flag': 'EVIDENCE_VISIBILITY_FAILURE', 'timestamp_seconds': round(float(t), 2),
                    'narration_claim': it['narration_claim'].strip()[:300],
                    'problem': it['problem'].strip()[:300], 'fix': it['fix'].strip()[:300]})
    return out[:10]


def build(judged, measured, transcript_text, duration, has_transcript):
    """Return the TVQ result dict. `judged` may be None (judge unavailable)."""
    judged = judged if isinstance(judged, dict) else {}
    subs_in = judged.get('subscores') if isinstance(judged.get('subscores'), dict) else {}
    styled = {k for k in (judged.get('intentional_style') or []) if k in WEIGHTS}
    issues = _issues(judged.get('issues'), measured, duration)
    failures = _failures(judged.get('evidence_visibility_failures'), transcript_text, duration) if has_transcript else []
    m_subs = (measured or {}).get('subscores', {})
    subs, notes = {}, {}
    for key, weight in WEIGHTS.items():
        item = subs_in.get(key)
        j = None
        if isinstance(item, dict) and _num(item.get('score')) and 0 <= item['score'] <= 100 \
                and isinstance(item.get('observation'), str) and item['observation'].strip():
            j = float(item['score'])
        m = m_subs.get(key)
        if key == 'evidence_visibility' and not has_transcript:
            notes[key] = 'missing input: transcript (the narration is what the picture must support)'
            continue
        if key in JUDGED_ONLY:
            if j is None:
                notes[key] = 'judge did not evaluate this' if measured is not None or judged else 'judge unavailable'
                continue
            score, source = j, 'judge'
        elif m is not None and j is not None:
            score, source = (j, 'judge (intentional style)') if key in styled else (BLEND * m + (1 - BLEND) * j, 'measured + judge')
        elif m is not None:
            score, source = m, 'measured only'
        elif j is not None:
            score, source = j, 'judge'
        else:
            notes[key] = 'could not be measured or judged'
            continue
        has_issue = any(_key(i['subcategory']) == key for i in issues)
        if key in JUDGED_ONLY and score < 70 and not has_issue:
            notes[key] = 'below 70 but the judge gave no timestamped issue for it'
            continue
        subs[key] = {'score': round(score, 1), 'weight': weight, 'source': source,
                     'measured': m, 'judged': j,
                     'observation': (item or {}).get('observation', '')[:400] if isinstance(item, dict) else ''}
    if failures and 'evidence_visibility' in subs:
        cap = 59.0 if len(failures) >= 3 else 79.0
        subs['evidence_visibility']['score'] = round(min(subs['evidence_visibility']['score'], cap), 1)
        subs['evidence_visibility']['capped_by'] = 'EVIDENCE_VISIBILITY_FAILURE x%d' % len(failures)
    done = {k: v for k, v in subs.items()}
    complete = len(done) == len(WEIGHTS)
    total = round(sum(v['score'] * v['weight'] for v in done.values()) / 100, 1) if complete else None
    provisional = None
    if not complete and done:
        w = sum(v['weight'] for v in done.values())
        provisional = round(sum(v['score'] * v['weight'] for v in done.values()) / w, 1)
    result = {'status': 'evaluated' if complete else 'partial', 'score': total, 'provisional_score': provisional,
              'band': band(total) if total is not None else None, 'weights': dict(WEIGHTS),
              'subscores': subs, 'not_evaluated': notes, 'issues': issues,
              'evidence_visibility_failures': failures,
              'summary': str(judged.get('summary', ''))[:600],
              'strongest_visual_quality': str(judged.get('strongest_visual_quality', ''))[:300],
              'weakest_visual_quality': str(judged.get('weakest_visual_quality', ''))[:300],
              'highest_priority_fix': str(judged.get('highest_priority_fix', ''))[:300],
              'measurements': {k: v for k, v in (measured or {}).items() if k in
                               ('effective_height_median', 'decoded_size', 'cadence', 'frames_measured', 'limitations')},
              'intentional_style': sorted(styled)}
    return result


def adjust(overall, tvq, tvq_weight, cap_override=False):
    """Apply the owner's caps and penalties. Returns (final_overall, adjustments)."""
    steps = []
    score = overall
    s = tvq['score']
    if s < 70:
        pen = round(0.5 * (70 - s), 1)
        steps.append({'rule': 'tvq_below_70', 'points': -pen,
                      'why': 'Technical Visual Quality is %.1f, under 70' % s})
        score -= pen
    text = tvq['subscores'].get('text_graphics_clarity')
    if text and text['score'] < 50 and any(i['subcategory'] == SUBCATEGORY_NAMES['text_graphics_clarity']
                                          and i['severity'] == 'High' for i in tvq['issues']):
        steps.append({'rule': 'critical_text_unreadable', 'points': -3,
                      'why': 'Text or graphics a viewer needs cannot be read'})
        score -= 3
    n = len(tvq['evidence_visibility_failures'])
    if n:
        pen = 2 if n == 1 else min(12, 3 * n)
        steps.append({'rule': 'evidence_visibility_failure', 'points': -pen,
                      'why': '%d moment(s) where the viewer cannot see what the narration points at' % n})
        score -= pen
    cap = 69 if s < 45 else 79 if s < 60 else None
    if cap is not None and score > cap:
        if cap_override:
            steps.append({'rule': 'cap_overridden', 'points': 0, 'why': 'Cap of %d overridden by the owner' % cap})
        else:
            steps.append({'rule': 'tvq_cap', 'points': round(cap - score, 1),
                          'why': 'Technical Visual Quality %.1f limits the overall score to %d' % (s, cap)})
            score = cap
    return max(0.0, round(score, 1)), steps
