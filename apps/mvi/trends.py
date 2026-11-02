"""Current-trend snapshot from the official YouTube Data API v3. No scraping.

A trend packet describes what is recently popular in a niche: durations, title habits and
view levels. It is a dated snapshot of public data, not knowledge of any algorithm, and it
only feeds the minor (20%) trend-fit part of a score. Needs YOUTUBE_API_KEY (free from
Google Cloud). Quota used: videos.list = 1 unit, search.list = 1 call from a 100/day bucket.
TikTok, Instagram and Twitch have no comparable open trend feed wired here yet; they are
not scraped.
"""
import hashlib
import json
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

API = 'https://www.googleapis.com/youtube/v3/'
TTL_SECONDS = 24 * 3600
STALE_AFTER_SECONDS = 48 * 3600
GAMING_CATEGORY = '20'
STOP = set('the a an and or of to in on for with is are was be it this that my your i you we how what why when who at by from as not no vs'.split())


class TrendError(RuntimeError):
    pass


def _clean_error(text, key):
    return (text or '').replace(key or '\0', '[key]')[:200]


def _get_json(endpoint, params, key, timeout=30):
    url = API + endpoint + '?' + urllib.parse.urlencode({**params, 'key': key})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.load(res)
    except Exception as exc:
        raise TrendError('YouTube API request failed: ' + _clean_error(str(exc), key))


def parse_duration(iso):
    m = re.fullmatch(r'P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _summarize(items):
    rows = []
    for it in items:
        sn, st = it.get('snippet', {}), it.get('statistics', {})
        dur = parse_duration(it.get('contentDetails', {}).get('duration'))
        if dur is None or not sn.get('title'):
            continue
        rows.append({'video_id': it.get('id'), 'title': sn['title'][:140], 'channel': sn.get('channelTitle'),
                     'published': sn.get('publishedAt'), 'duration_seconds': dur,
                     'views': int(st['viewCount']) if str(st.get('viewCount', '')).isdigit() else None})
    return rows


def stats(rows):
    if not rows:
        return {'count': 0}
    durs = [r['duration_seconds'] for r in rows]
    views = [r['views'] for r in rows if r['views'] is not None]
    titles = [r['title'] for r in rows]
    n = len(rows)
    words = Counter(w for t in titles for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2)
    bucket = lambda lo, hi: round(sum(lo <= d < hi for d in durs) / n, 2)
    return {
        'count': n,
        'median_duration_seconds': statistics.median(durs),
        'duration_share_under_60s': bucket(0, 60), 'duration_share_1_to_5min': bucket(60, 300),
        'duration_share_5_to_15min': bucket(300, 900), 'duration_share_over_15min': bucket(900, 10**9),
        'median_views': statistics.median(views) if views else None,
        'median_title_chars': statistics.median(len(t) for t in titles),
        'share_titles_with_number': round(sum(bool(re.search(r'\d', t)) for t in titles) / n, 2),
        'share_titles_with_question': round(sum('?' in t for t in titles) / n, 2),
        'share_titles_with_allcaps_word': round(sum(bool(re.search(r'\b[A-Z]{3,}\b', t)) for t in titles) / n, 2),
        'top_title_words': [w for w, _ in words.most_common(10)],
    }


SHORTS_MAX_SECONDS = 180  # same cutoff as platforms.py
FORMS = ('shorts', 'long')


def form_for_duration(seconds):
    """Which trend pool a video belongs in: Shorts (<=180s) or long-form."""
    return 'shorts' if seconds is not None and seconds <= SHORTS_MAX_SECONDS else 'long'


def fetch_youtube(api_key, *, region='US', category=GAMING_CATEGORY, query=None, max_results=25, days=30, now=None,
                  form=None, get=_get_json):
    if not api_key:
        raise TrendError('YOUTUBE_API_KEY is not set')
    now = time.time() if now is None else now
    max_results = max(5, min(int(max_results), 50))
    if form is not None and form not in FORMS:
        raise TrendError('form must be shorts or long')
    if form and not query:
        raise TrendError('a format-specific snapshot needs a search query (MVI_TREND_QUERY)')
    if query:
        after = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - days * 86400))
        # YouTube search buckets: short <4 min, medium 4-20 min, long >20 min.
        buckets = {'shorts': ['short'], 'long': ['medium', 'long']}.get(form, [None])
        ids = []
        for bucket in buckets:
            params = {'part': 'snippet', 'type': 'video', 'q': query, 'order': 'viewCount', 'publishedAfter': after,
                      'videoCategoryId': category, 'maxResults': max_results}
            if bucket:
                params['videoDuration'] = bucket
            found = get('search', params, api_key)
            ids += [i['id']['videoId'] for i in found.get('items', []) if i.get('id', {}).get('videoId') and i['id']['videoId'] not in ids]
        data = get('videos', {'part': 'snippet,contentDetails,statistics', 'id': ','.join(ids)}, api_key) if ids else {'items': []}
        scope = f'search "{query}" in category {category}, last {days} days, by views' + (
            {'shorts': ' (Shorts only, 180s or less)', 'long': ' (long-form only, over 180s)'}[form] if form else '')
    else:
        data = get('videos', {'part': 'snippet,contentDetails,statistics', 'chart': 'mostPopular', 'regionCode': region,
                              'videoCategoryId': category, 'maxResults': max_results}, api_key)
        scope = f'most popular, category {category}, region {region}'
    rows = _summarize(data.get('items', []))
    if form == 'shorts':
        rows = [r for r in rows if r['duration_seconds'] <= SHORTS_MAX_SECONDS]
    elif form == 'long':
        rows = [r for r in rows if r['duration_seconds'] > SHORTS_MAX_SECONDS]
    rows.sort(key=lambda r: r['views'] or 0, reverse=True)
    return {'source': 'youtube_data_api_v3', 'scope': scope, 'region': region, 'form': form, 'retrieved_at': now,
            'note': 'Snapshot of public popularity. Not algorithm knowledge; popularity is not proof of quality.',
            'stats': stats(rows), 'examples': rows[:10]}


def _cache_path(root, region, category, query, form=None):
    tag = hashlib.sha256(f'{region}|{category}|{query or ""}|{form or ""}'.encode()).hexdigest()[:12]
    return Path(root) / 'private' / 'trends' / f'youtube_{tag}.json'


def get(root, *, region=None, category=GAMING_CATEGORY, query=None, form=None, now=None, fetch=fetch_youtube):
    """Cached trend packet, or None when no key is configured. Raises TrendError on API failure with no cache."""
    region = region or os.environ.get('MVI_TREND_REGION', 'US')
    path = _cache_path(root, region, category, query, form)
    now = time.time() if now is None else now
    if path.is_file():
        cached = json.loads(path.read_text())
        if now - cached['retrieved_at'] < TTL_SECONDS:
            return cached
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        return None
    packet = fetch(key, region=region, category=category, query=query, form=form, now=now)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(packet))
    os.chmod(path, 0o600)
    return packet


def is_fresh(packet, now=None):
    now = time.time() if now is None else now
    return bool(packet) and now - packet['retrieved_at'] <= STALE_AFTER_SECONDS and packet['stats'].get('count', 0) >= 5
