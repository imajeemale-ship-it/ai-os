"""Rubric v0 DRAFT as data. Weights equal vindex_adapter.RUBRIC; anchors are editable proposals.

Nothing here is validated. The owner and David should edit `ANCHORS`, then the
scorer must be calibrated against their human scores before any threshold is trusted.
"""
from vindex_adapter import RUBRIC

VERSION = 'mvi-rubric-draft-v0'
MIN_CITATIONS = 2

# What each category needs the scorer to actually have. Missing inputs => not_evaluated.
REQUIRES = {
    'opening_hook': {'frames'},
    'storytelling_engagement': {'frames', 'transcript'},
    'pacing_retention': {'frames', 'timeline'},
    'humor_entertainment': {'frames', 'transcript'},
    'sound_design': {'audio_measures'},
    'visual_polish': {'frames'},
    'ending_payoff': {'frames'},
}

ANCHORS = {
    'opening_hook': 'In the first 5-10s does a viewer know what this is and why to keep watching? '
                    'High: clear stakes or striking moment at once. Mid: slow to commit. Low: dead air or setup nobody asked for.',
    'storytelling_engagement': 'Is there a followable arc (setup, escalation, turn, resolution) and can a cold viewer follow it? '
                               'High: every section advances the premise. Mid: mostly followable with filler. Low: collage with no thread.',
    'pacing_retention': 'Does rhythm fit the content? High: every section earns its length. Mid: one or two flat patches. '
                        'Low: repeated slow stretches or frantic cutting that hides the point. Shot counts alone prove nothing; label drop-off points as hypotheses.',
    'humor_entertainment': 'Do funny or exciting moments land (setup, beat, punchline visible)? High: several clear moments. '
                           'Mid: some land, some cut early or buried. Low: no identifiable moments. Quote the line or describe the moment with a timestamp.',
    'sound_design': 'Is speech intelligible, music under voice, effects useful? Measured silence or clipping is a signal to check, not proof; '
                    'quiet can be intentional.',
    'visual_polish': 'Is the design readable and tidy: overlays legible at phone size, nothing competing for the eye? '
                     'Judge against the intended style (raw footage is not low polish if raw is intended). '
                     'Technical image quality (sharpness, real resolution, compression, frame timing, exposure) is scored separately as Technical Visual Quality; do not double count it here.',
    'ending_payoff': 'Does the ending deliver what the opening promised and leave a clear next step?',
}


def bands(maximum):
    """High 85-100%, Mid 55-84%, Low under 55% of the maximum."""
    return {'high': (round(maximum * 0.85), maximum), 'mid': (round(maximum * 0.55), round(maximum * 0.85) - 1),
            'low': (0, round(maximum * 0.55) - 1)}


def describe():
    return {k: {'maximum': v, 'bands': bands(v), 'requires': sorted(REQUIRES[k]), 'anchor': ANCHORS[k]}
            for k, v in RUBRIC.items()}
