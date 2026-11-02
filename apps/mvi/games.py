"""Games MVI can fetch trends for. Each game maps to the YouTube search phrase used for its trend snapshot.

Add a game by adding one row. Trends are fetched per game and cached separately, so each extra
game costs a few search calls a day from YouTube's free 100/day bucket. 'other' deliberately has
no query: a video for an unlisted game gets no trend score instead of being compared with the wrong game.
"""
import os

GAMES = {
    'gta': {'label': 'GTA Online', 'query': 'gta online'},
    'cod': {'label': 'Call of Duty', 'query': 'call of duty'},
    'other': {'label': 'Other / not listed', 'query': None},
}
DEFAULT = 'gta'


def valid(key):
    return key in GAMES


def query_for(key):
    """Search phrase for a game key. Missing key keeps the old behaviour (MVI_TREND_QUERY, default GTA)."""
    if not key:
        return os.environ.get('MVI_TREND_QUERY', GAMES[DEFAULT]['query'])
    return GAMES[key]['query']


def listing():
    return [{'key': k, 'label': v['label'], 'has_trends': bool(v['query'])} for k, v in GAMES.items()]
