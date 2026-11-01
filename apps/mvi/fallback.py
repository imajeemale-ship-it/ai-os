"""Blocked-link fallback ladder: a failed retrieval is never a dead end.

A failed direct fetch becomes a `needs_fallback` job that records what was
tried and which steps remain. It never fabricates media or a score.
"""
import re

_PATTERNS = (
    ('bot_challenge', r"confirm you.?re not a bot|sign in to confirm|use --cookies|bot"),
    ('login_required', r"log ?in|sign ?in|login required|rate-limit reached|authentication"),
    ('private_video', r"private video|this video is private"),
    ('rate_limited', r"429|too many requests"),
    ('too_large', r"exceeds 300mb|max-filesize|larger than"),
    ('unavailable', r"unavailable|not available|removed|does not exist|404|unsupported url"),
)

_MESSAGES = {
    'bot_challenge': 'The platform asked the server to prove it is not a bot.',
    'login_required': 'The platform requires a login to show this video.',
    'private_video': 'The video is private.',
    'rate_limited': 'The platform is rate limiting the server.',
    'too_large': 'The video is larger than the 300 MB retrieval limit.',
    'unavailable': 'The video could not be found or is not available to the server.',
    'retrieval_failed': 'The server could not retrieve this video.',
}


def classify(text):
    low = (text or '').lower()
    for code, pattern in _PATTERNS:
        if re.search(pattern, low):
            return code
    return 'retrieval_failed'


def build_record(job_id, platform, url, error_text, context=None):
    code = classify(error_text)
    actions = [
        {'step': 'upload_file', 'available': True,
         'how': 'Download or screen-record the video on your phone or computer, then attach it to this job.',
         'endpoint': f'/api/jobs/{job_id}/attach'},
        {'step': 'local_helper', 'available': True,
         'how': 'Run tools/mvi_local_fetch.py on your own computer. It fetches the link with your own '
                'connection and sends the file here. Your cookies never leave your computer.',
         'command': f'python3 mvi_local_fetch.py "{url}" --server <MVI URL> --attach-to {job_id}'},
        {'step': 'browser_capture', 'available': False,
         'how': 'Server-side screen capture is not built yet.'},
    ]
    record = {
        'job_id': job_id, 'status': 'needs_fallback', 'platform': platform, 'url': url,
        'reason': code, 'message': _MESSAGES[code],
        'detail': (error_text or '')[-300:],
        'tried': [{'step': 'direct_fetch', 'result': 'failed'}],
        'next_actions': actions, 'creative_score': None,
    }
    if context:
        record['editorial_context'] = context
    return record
