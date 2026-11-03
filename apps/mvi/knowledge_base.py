"""Seed principles of 'what is known to work', each with a source. Nothing influences a score until the owner approves it.

Official YouTube Help guidance is high confidence; a secondhand report of a YouTube official is medium. Creator-video lessons come from single speakers
(auto-captions, reviewed by hand) and are low confidence: hypotheses to test against David's judgment.
"""
import json
import os
import tempfile
from pathlib import Path

YT_RETENTION = 'https://support.google.com/youtube/answer/9314415 (YouTube Help, retrieved 2026-11-01)'
YT_TITLES = 'https://support.google.com/youtube/answer/12340300 (YouTube Help, Thumbnail & title tips, retrieved 2026-11-02)'
YT_CTR = 'https://support.google.com/youtube/answer/7628154 (YouTube Help, Impressions & click-through-rate FAQs, retrieved 2026-11-02)'
SEJ = 'https://beta.searchenginejournal.com/how-youtubes-recommendation-system-works-in-2025/538379/ (Search Engine Journal, 2025-01-27, reporting an interview with YouTube\'s Todd Beaupre; secondhand)'
JY = 'Jon Youshaei, YouTube Masterclass 2025, https://youtu.be/h-8C3bntQRo (auto-captions; see research/002_YOUTUBE_MASTERCLASS.md)'
JT = 'Jake Trinder, https://www.youtube.com/watch?v=Dx-c19qXdxM (auto-captions; see research/jake_trinder/EDITORIAL_DOCTRINE.md)'

PRINCIPLES = [
    {'id': 'P-YT-01', 'confidence': 'high', 'source': YT_RETENTION, 'categories': ['opening_hook'],
     'text': 'Intro retention is the share of viewers still watching after 30 seconds. A strong opening matches the title and thumbnail and holds interest; test the first 30 seconds.'},
    {'id': 'P-YT-02', 'confidence': 'high', 'source': YT_RETENTION, 'categories': ['pacing_retention', 'storytelling_engagement'],
     'text': 'Audience size normally shrinks over a video, so compelling content that appears late is a signal to move it earlier.'},
    {'id': 'P-YT-03', 'confidence': 'high', 'source': YT_RETENTION, 'categories': ['pacing_retention'],
     'text': 'A dip in retention means viewers skipped or left at that point; a spike means a segment was more engaging or unclear enough to be rewatched. Both are worth reviewing.'},
    {'id': 'P-YT-04', 'confidence': 'high', 'source': YT_TITLES + '; ' + YT_CTR, 'categories': ['opening_hook', 'ending_payoff', 'promise_match'],
     'text': 'The video must deliver what its title and thumbnail promise. YouTube says misleading packaging makes viewers stop watching, which hurts discoverability, and that clickbait tends to have low average view duration and is less likely to be recommended.'},
    {'id': 'P-YT-06', 'confidence': 'high', 'source': YT_TITLES, 'categories': ['thumbnail_clarity', 'thumbnail_text'],
     'text': 'Keep the thumbnail simple: bold colour and composition catch the eye but too much detail overwhelms it. Any text should use an easy-to-read font. Make the image large, since thumbnails display differently across devices, and make sure it shows the best of the video.'},
    {'id': 'P-YT-07', 'confidence': 'high', 'source': YT_TITLES, 'categories': ['title'],
     'text': 'Titles should be accurate and succinct, with the most important words first. Limit ALL CAPS and emoji, using them mainly to emphasize emotion. Choose deliberately between a searchable title that sets clear expectations and an intriguing title that sparks curiosity, based on who will watch and where they will find the video.'},
    {'id': 'P-YT-05', 'confidence': 'medium', 'source': SEJ, 'categories': ['storytelling_engagement', 'ending_payoff'],
     'text': 'YouTube says it also uses likes, dislikes and viewer surveys to gauge satisfaction, not only what people watch. Keeping viewers by misleading them does not make a video good; reward videos viewers would be glad they watched.'},
    {'id': 'P-JY-01', 'confidence': 'low', 'source': JY, 'categories': ['opening_hook'],
     'text': 'Strong intros often show the result up front, address the viewer\'s likely objection, and get to the point immediately (R.A.I.N.Y.: result, address objection, instant, now, you).'},
    {'id': 'P-JY-02', 'confidence': 'low', 'source': JY, 'categories': ['opening_hook', 'visual_polish'],
     'text': 'For Shorts, the first frame should make the premise legible at once.'},
    {'id': 'P-JY-03', 'confidence': 'low', 'source': JY, 'categories': ['visual_polish'],
     'text': 'Avoid eye fatigue: competing overlays, effects and focal points make it harder to know where to look.'},
    {'id': 'P-JY-04', 'confidence': 'low', 'source': JY, 'categories': ['sound_design'],
     'text': 'Clear sound and preparation matter more than expensive equipment.'},
    {'id': 'P-JT-01', 'confidence': 'low', 'source': JT, 'categories': ['opening_hook', 'ending_payoff'],
     'text': 'A strong opening makes the promise, proof, plan and persona clear, which reduces viewer doubt; the ending is judged on whether it delivers that promise.'},
    {'id': 'P-JT-02', 'confidence': 'low', 'source': JT, 'categories': ['storytelling_engagement', 'pacing_retention', 'ending_payoff'],
     'text': 'Satisfaction is relative to expectations: judge slower sections against what the video promised, not against a universal pace.'},
]
IDS = {p['id'] for p in PRINCIPLES}


def _path(root):
    return Path(root) / 'private' / 'principle_decisions.json'


def _load(root):
    p = _path(root)
    return json.loads(p.read_text()) if p.is_file() else {}


def listing(root):
    d = _load(root)
    return [{**p, 'decision': d.get(p['id'], 'pending')} for p in PRINCIPLES]


def approved(root):
    d = _load(root)
    return [p for p in PRINCIPLES if d.get(p['id']) == 'approve']


def decide(root, pid, decision):
    if pid not in IDS or decision not in ('approve', 'reject', 'pending'):
        raise ValueError('Unknown principle or decision')
    d = _load(root)
    d[pid] = decision
    p = _path(root)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix='.pd-')
    with os.fdopen(fd, 'w') as f:
        json.dump(d, f)
    os.replace(tmp, p)
    return {'id': pid, 'decision': decision}
