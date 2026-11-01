"""Platform fit checks: deterministic, sourced, advisory.

Honesty rules: a limit becomes a pass/fail check only where several sources agree.
Where sources conflict or are missing, the finding is `info` with the gap stated.
Nothing here predicts views, reach or what an algorithm will do. Current trends are
NOT available in this module; they need a dated research pass.
"""
RETRIEVED = '2026-11-01'
SOURCES = {
    'kapwing': 'https://www.kapwing.com/resources/social-media-video-aspect-ratios-and-sizes-the-2025-guide/ (page dated 2026-01-16)',
    'blitzcut_shorts': 'https://blitzcutai.com/blog/youtube-shorts-length-limits-2026',
    'openclip': 'https://openclip.app/clipping/clip-specs-by-platform.md',
}

VERTICAL = 9 / 16
PLATFORMS = {
    'youtube_long': {'label': 'YouTube (long-form)', 'aspect': 16 / 9, 'confidence': 'medium',
                     'sources': ['kapwing']},
    'youtube_shorts': {'label': 'YouTube Shorts', 'aspect': VERTICAL, 'max_seconds': 180, 'confidence': 'medium',
                       'sources': ['kapwing', 'blitzcut_shorts'],
                       'note': 'A Short is 3 min or less and vertical (9:16) or square; horizontal files are normal videos at any length.'},
    'tiktok': {'label': 'TikTok', 'aspect': VERTICAL, 'confidence': 'low', 'sources': ['kapwing', 'openclip'],
               'note': 'Sources disagree or omit maximum upload length; length is not checked.'},
    'instagram_reels': {'label': 'Instagram Reels', 'aspect': VERTICAL, 'confidence': 'low',
                        'sources': ['kapwing', 'openclip'],
                        'note': 'A source lists both 3 min and 20 min for Reels; length is not checked.'},
    'twitch_clips': {'label': 'Twitch clips', 'aspect': None, 'confidence': 'none', 'sources': [],
                     'note': 'No source gathered. Twitch specs still need a research pass.'},
}


def _aspect(resolution):
    try:
        w, h = (int(x) for x in resolution.lower().split('x'))
        return w, h, w / h
    except Exception:
        return None


def check(platform_key, technical):
    spec = PLATFORMS[platform_key]
    refs = [SOURCES[s] for s in spec['sources']]
    base = {'platform': platform_key, 'label': spec['label'], 'confidence': spec['confidence'],
            'sources': refs, 'retrieved': RETRIEVED}
    out = []
    dims = _aspect(technical.get('resolution', ''))
    dur = technical.get('duration_seconds')
    if spec.get('aspect') and dims:
        w, h, ratio = dims
        ok = abs(ratio - spec['aspect']) / spec['aspect'] < 0.05
        if platform_key == 'youtube_shorts' and abs(ratio - 1) < 0.05:
            ok = True
        out.append({**base, 'check': 'aspect_ratio', 'status': 'pass' if ok else 'warn',
                    'detail': f'File is {w}x{h} ({ratio:.2f}); recommended {"9:16" if spec["aspect"] < 1 else "16:9"}.'})
        if spec['aspect'] < 1 and ok and (w < 1080 or h < 1920):
            out.append({**base, 'check': 'resolution', 'status': 'info',
                        'detail': f'Recommended 1080x1920; this file is {w}x{h}.'})
    if spec.get('max_seconds') and dur:
        classified = dims and (dims[2] <= 1.05)
        if dur > spec['max_seconds']:
            out.append({**base, 'check': 'length', 'status': 'warn',
                        'detail': f'{dur:.0f}s exceeds the {spec["max_seconds"]}s Shorts limit.'})
        elif not classified:
            out.append({**base, 'check': 'length', 'status': 'info',
                        'detail': 'Under the length limit, but a horizontal file is treated as a normal video, not a Short.'})
        else:
            out.append({**base, 'check': 'length', 'status': 'pass', 'detail': f'{dur:.0f}s is within {spec["max_seconds"]}s.'})
    if spec.get('note'):
        out.append({**base, 'check': 'source_gap', 'status': 'info', 'detail': spec['note']})
    return out


def check_all(technical, platforms=None):
    keys = platforms or list(PLATFORMS)
    findings = []
    for k in keys:
        if k in PLATFORMS:
            findings.extend(check(k, technical))
    return {'retrieved': RETRIEVED, 'advisory_only': True,
            'trends': 'not_available: current trending formats need a dated research pass and are not scored here',
            'findings': findings}
