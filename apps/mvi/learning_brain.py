"""MVI knowledge intake: source -> transcript -> candidate principles -> human gate.

This is evidence-based retrieval, not model fine-tuning. Unreviewed video
claims never become trusted editorial rules. All paths are private to ROOT.
"""
from __future__ import annotations
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ALLOWED_UPLOADS = {'.mp4', '.mov', '.txt', '.md', '.vtt', '.srt'}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MIN_RELEVANCE_SCORE = 2
TERMS = {'edit', 'editing', 'cut', 'hook', 'thumbnail', 'video', 'youtube',
         'viewer', 'audience', 'retention', 'pacing', 'story', 'scene',
         'music', 'audio', 'camera', 'transition', 'title', 'attention',
         'comedy', 'comedic', 'narrative', 'visual', 'engagement',
         'introduction', 'frame', 'watch', 'clip', 'timing', 'sound',
         'emotion', 'payoff', 'intro', 'script'}
SIGNALS = {'should', 'need', 'must', 'avoid', 'never', 'instead', 'because',
           'why', "don't", 'do not', 'important', 'works', 'better',
           'expect', 'problem', 'mistake', 'makes', 'fails', 'fail',
           'reason', 'change'}
MAX_CANDIDATES = 15


def _safe_word(value, max_chars=240):
    if not isinstance(value, str):
        return ''
    return re.sub(r'[\x00-\x1f\x7f]', ' ', value).strip()[:max_chars]


def normalize_captions(source):
    """Remove VTT/SRT cue/timing tags and collapse overlapping live-caption lines."""
    source = source.replace('\ufeff', '')
    blocks = re.split(r'\n\s*\n', source)
    groups = []
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines or lines[0].strip().upper() in ('WEBVTT',):
            continue
        if lines[0].strip().startswith(('Kind:', 'Language:', 'NOTE', 'STYLE', 'REGION')):
            continue
        text_lines = [line for line in lines if '-->' not in line
                      and not re.fullmatch(r'\d+', line.strip())
                      and not re.fullmatch(r'\d\d:\d\d(?::\d\d)?[.,]\d+', line.strip())]
        text = ' '.join(text_lines)
        text = re.sub(r'<[^>]*>', '', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            groups.append(text)
    if not groups:
        return ''
    # YouTube rolling captions repeat the last several words in each cue.
    merged = groups[0].split()
    for group in groups[1:]:
        words = group.split()
        overlap = 0
        for n in range(min(len(merged), len(words), 24), 0, -1):
            if [w.lower() for w in merged[-n:]] == [w.lower() for w in words[:n]]:
                overlap = n
                break
        merged.extend(words[overlap:])
    return ' '.join(merged)[:300000]


def normalize_text(source, suffix):
    if suffix in ('.vtt', '.srt'):
        return normalize_captions(source)
    return re.sub(r'\s+', ' ', source.replace('\ufeff', '')).strip()[:300000]


def extract_candidates(transcript):
    """Extract inspectable candidate excerpts. No semantic 'truth' inference."""
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', transcript)
    ranked = []
    for index, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not 45 <= len(sentence) <= 600:
            continue
        lower = sentence.lower()
        words = set(re.findall(r"[a-z']+", lower))
        relevance = len(words & TERMS)
        principles = sum(1 for signal in SIGNALS if signal in words or
                         (signal in ("do not", "don't") and signal in lower))
        score = min(relevance, 4) + min(principles, 3)
        if relevance < 1 or score < MIN_RELEVANCE_SCORE:
            continue
        # A short source excerpt, not an invented instruction.
        excerpt = sentence[:420].strip()
        identifier = hashlib.sha256(excerpt.encode('utf-8')).hexdigest()[:16]
        ranked.append((score, index, {
            'id': identifier,
            'excerpt': excerpt,
            'score': score,
            'review_status': 'candidate_unverified',
            'source_sentence_index': index,
            'context': 'Source claim for editor review, not an endorsed rule.',
        }))
    ranked.sort(key=lambda p: (-p[0], p[1]))
    seen = set()
    result = []
    for _, _, card in ranked:
        if card['id'] in seen:
            continue
        seen.add(card['id'])
        result.append(card)
        if len(result) >= MAX_CANDIDATES:
            break
    return result


def _extract_youtube_captions(url, output):
    from link_intake import video_id
    ident = video_id(url)
    output = Path(output)
    cmd = [sys.executable, '-m', 'yt_dlp', '--skip-download',
           '--write-subs', '--write-auto-subs',
           '--sub-langs', 'en-orig,en', '--sub-format', 'vtt',
           '--no-playlist', '--no-progress', '-o', str(output / 'source.%(ext)s'),
           'https://www.youtube.com/watch?v=' + ident]
    process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    candidates = sorted(output.glob('source.*.vtt'),
                        key=lambda p: (0 if '.en-orig.' in p.name else 1, p.name))
    if not candidates:
        message = process.stderr[-250:] if process.stderr else 'No captions available.'
        raise RuntimeError('YouTube captions unavailable: ' + message)
    transcript = normalize_text(candidates[0].read_text(errors='replace'), '.vtt')
    if not transcript:
        raise ValueError('Downloaded captions were empty')
    return transcript, {'video_id': ident,
                        'caption_track': candidates[0].name,
                        'capture_method': 'youtube_subtitles'}


def _extract_video_subtitles(video, attempt_dir):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 's',
         '-show_entries', 'stream=index,codec_name', '-of', 'json', str(video)],
        capture_output=True, text=True, timeout=15)
    if result.returncode:
        return None
    try:
        streams = json.loads(result.stdout).get('streams', [])
    except (ValueError, TypeError):
        return None
    if not streams:
        return None
    output = attempt_dir / 'embedded.srt'
    run = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                          '-y', '-i', str(video), '-map', '0:s:0', str(output)],
                         capture_output=True, text=True, timeout=60)
    if run.returncode or not output.exists():
        return None
    return normalize_text(output.read_text(errors='replace'), '.srt')


def _read_upload(source, attempt_dir):
    ext = source.suffix.lower()
    if ext in ('.txt', '.md', '.vtt', '.srt'):
        if source.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError('Teaching text exceeds 2 MB')
        return normalize_text(source.read_text(errors='replace'), ext), 'uploaded_text'
    if ext in ('.mp4', '.mov'):
        transcript = _extract_video_subtitles(source, attempt_dir)
        return transcript or '', 'embedded_subtitles' if transcript else 'video_requires_transcription'
    raise ValueError('Unsupported learning source')


def process_source(root, claim, attempt_dir):
    """Worker writes tentative artifacts to isolated attempt directory."""
    root = Path(root)
    payload = claim['payload']
    job = claim['job_id']
    if claim['kind'] == 'learn_url':
        transcript, details = _extract_youtube_captions(payload['url'], attempt_dir)
        src = {'type': 'youtube', 'url': payload['url'],
               'title': _safe_word(payload.get('title')) or 'YouTube learning source',
               **details}
    elif claim['kind'] == 'learn_upload':
        filename = payload.get('filename')
        if filename not in {'learning' + ext for ext in ALLOWED_UPLOADS}:
            raise ValueError('Unsafe learning upload filename')
        path = root / job / filename
        if not path.is_file() or path.is_symlink():
            raise ValueError('Learning upload is missing or unsafe')
        transcript, method = _read_upload(path, attempt_dir)
        src = {'type': 'upload', 'title': _safe_word(payload.get('title')),
               'filename': filename, 'capture_method': method}
    else:
        raise ValueError('Unsupported learning kind')
    if len(transcript) > 300000:
        transcript = transcript[:300000]
    # Captions must not be confused with verified advice. Keep raw data private.
    (attempt_dir / 'transcript.txt').write_text(transcript)
    os.chmod(attempt_dir / 'transcript.txt', 0o600)
    cards = extract_candidates(transcript) if transcript else []
    record = {
        'job_id': job,
        'source': src,
        'phase': 'needs_transcript' if not transcript else
                 'candidate_review' if cards else 'no_editing_candidates',
        'transcript_characters': len(transcript),
        'candidate_count': len(cards),
        'candidates': cards,
        'interpretation': 'Automated candidate excerpts require human judgment; no learning is approved automatically.',
    }
    (attempt_dir / 'learning.json').write_text(json.dumps(record, indent=2) + '\n')
    os.chmod(attempt_dir / 'learning.json', 0o600)
    return {'attempt': claim['attempt'], 'kind': 'learning'}


def learning_state(root, job_id):
    from durable_runtime import queue
    item = queue(root).get(job_id)
    if item is None or item['kind'] not in ('learn_url', 'learn_upload'):
        return None
    state = {'job_id': job_id, 'status': item['status'],
             'attempts': item['attempts'],
             'error': item.get('error') if item['status'] == 'failed' else None}
    if item['status'] == 'completed':
        winner = (item['result'] or {}).get('attempt')
        path = Path(root) / job_id / ('attempt-' + str(winner)) / 'learning.json'
        if path.is_file():
            state.update(json.loads(path.read_text()))
            state['status'] = 'completed'
            state['decisions'] = decisions_for(root, job_id)
    return state


@contextmanager
def _db(root):
    location = Path(root) / 'private'
    location.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = location / 'learning_decisions.db'
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('''CREATE TABLE IF NOT EXISTS decisions
                      (job_id TEXT NOT NULL, card_id TEXT NOT NULL,
                       decision TEXT NOT NULL,
                       PRIMARY KEY (job_id, card_id))''')
        os.chmod(path, 0o600)
        yield db
        db.commit()
    finally:
        db.close()


def decisions_for(root, job_id):
    with _db(root) as db:
        return {row[0]: row[1] for row in
                db.execute('SELECT card_id, decision FROM decisions WHERE job_id=?',
                           (job_id,))}


def decide(root, job_id, card_id, decision):
    if decision not in ('approve', 'reject'):
        raise ValueError('Decision must be approve or reject')
    state = learning_state(root, job_id)
    if state is None or state['status'] != 'completed':
        raise ValueError('Learning source not available')
    if not any(x['id'] == card_id for x in state.get('candidates', [])):
        raise ValueError('Unknown learning card')
    with _db(root) as db:
        db.execute('INSERT OR REPLACE INTO decisions(job_id, card_id, decision) VALUES(?,?,?)',
                   (job_id, card_id, decision))
    return {'job_id': job_id, 'card_id': card_id, 'decision': decision}


def approved_principles(root, title='', max_count=5):
    """Approved *source excerpts* to consider, never proof about a target video."""
    from durable_runtime import queue
    with _db(root) as db:
        rows = db.execute("SELECT job_id,card_id FROM decisions WHERE decision='approve'").fetchall()
    if not rows:
        return []
    words = set(re.findall('[a-z]+', str(title).lower())) - {'the', 'and', 'video'}
    selected = []
    for job_id, card_id in rows:
        record = learning_state(root, job_id)
        if not record or record['status'] != 'completed':
            continue
        for card in record.get('candidates', []):
            if card['id'] != card_id:
                continue
            excerpt = card['excerpt']
            matches = len(words & set(re.findall('[a-z]+', excerpt.lower())))
            selected.append((matches, card['score'], {
                'source': record['source'],
                'excerpt': excerpt,
                'learning_job_id': job_id,
                'application': 'Review whether this sourced principle applies to the target video; do not assume it does.',
                'verified_target_observation': False,
            }))
    selected.sort(key=lambda row: (-row[0], -row[1]))
    return [x[2] for x in selected[:max_count]]
