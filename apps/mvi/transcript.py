"""Timestamped transcript reader. Parses VTT, SRT and plain text; never invents timing.

Plain text has no timestamps, so its lines carry `start_seconds=None` and can
only support claims about *what is said*, not *when*.
"""
import re

MAX_CHARS = 300_000
_TIME = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})')
_RANGE = re.compile(r'^(\S+)\s+-->\s+(\S+)')
_TAGS = re.compile(r'<[^>]+>')


def _seconds(text):
    m = _TIME.fullmatch(text.strip())
    if not m:
        raise ValueError('bad timestamp')
    h, mnt, s, frac = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s) + int(frac.ljust(3, '0')) / 1000


def _clean(line):
    return re.sub(r'\s+', ' ', _TAGS.sub('', line)).strip()


def parse(text, suffix=''):
    """Return {'format','timed','segments':[{start_seconds,end_seconds,text}]}."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Transcript is empty')
    text = text.replace('\r\n', '\n').replace('\r', '\n')[:MAX_CHARS]
    suffix = suffix.lower()
    if suffix in ('.vtt', '.srt') or '-->' in text[:2000]:
        segments = []
        for block in re.split(r'\n\s*\n', text):
            lines = [l for l in block.split('\n') if l.strip()]
            for i, line in enumerate(lines):
                m = _RANGE.match(line.strip())
                if not m:
                    continue
                try:
                    start, end = _seconds(m.group(1)), _seconds(m.group(2))
                except ValueError:
                    break
                body = _clean(' '.join(lines[i + 1:]))
                if body and end >= start:
                    segments.append({'start_seconds': round(start, 3), 'end_seconds': round(end, 3), 'text': body})
                break
        if not segments:
            raise ValueError('No timed captions found')
        # Auto-captions repeat the previous line as it scrolls; drop exact consecutive repeats.
        deduped = []
        for seg in segments:
            if deduped and deduped[-1]['text'] == seg['text']:
                deduped[-1]['end_seconds'] = max(deduped[-1]['end_seconds'], seg['end_seconds'])
            else:
                deduped.append(seg)
        return {'format': suffix.lstrip('.') or 'captions', 'timed': True, 'segments': deduped}
    lines = [_clean(l) for l in text.split('\n')]
    segments = [{'start_seconds': None, 'end_seconds': None, 'text': l} for l in lines if l]
    if not segments:
        raise ValueError('Transcript is empty')
    return {'format': 'text', 'timed': False, 'segments': segments}


def stats(transcript, duration_seconds):
    segs = transcript['segments']
    words = sum(len(s['text'].split()) for s in segs)
    out = {'segment_count': len(segs), 'word_count': words, 'timed': transcript['timed']}
    if transcript['timed'] and duration_seconds:
        spoken = sum(max(0.0, s['end_seconds'] - s['start_seconds']) for s in segs)
        gaps = []
        for a, b in zip(segs, segs[1:]):
            gap = b['start_seconds'] - a['end_seconds']
            if gap >= 3.0:
                gaps.append({'start_seconds': a['end_seconds'], 'end_seconds': b['start_seconds'], 'gap_seconds': round(gap, 2)})
        out.update(words_per_minute=round(words / (duration_seconds / 60), 1),
                   spoken_seconds=round(spoken, 2), long_gaps=gaps[:20])
    return out


def as_prompt_text(transcript, limit=60_000):
    """Compact timestamped text for a judge. Marked as data, never instructions."""
    rows = []
    for s in transcript['segments']:
        stamp = f"[{s['start_seconds']:.1f}s] " if s['start_seconds'] is not None else ''
        rows.append(stamp + s['text'])
    return '\n'.join(rows)[:limit]
