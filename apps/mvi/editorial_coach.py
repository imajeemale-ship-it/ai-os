"""Source-grounded editorial questions, not unsupported creative judgments.

Reference: Jake Trinder, Give Me 15 Minutes and I'll Make You Disgustingly
Good at YouTube, https://www.youtube.com/watch?v=Dx-c19qXdxM (2026-10-14).
"""
import math

SOURCE = {
    'id': 'Dx-c19qXdxM',
    'url': 'https://www.youtube.com/watch?v=Dx-c19qXdxM',
    'author': 'Jake Trinder',
    'method': 'expectation-first editorial decisions',
    'reference_version': 'editorial-brain-v1',
}

def _safe_text(value):
    return value.strip()[:240] if isinstance(value, str) and value.strip() else None

def _duration(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 else 0

def _clock(seconds):
    n = max(0, int(seconds))
    return f'{n // 60:02d}:{n % 60:02d}'

def coach(metadata, technical):
    """Supply tests an editor can apply without fabricating visual/semantic observations.

    Context is optional and explicit. A filename/title is NOT treated as a verified
    video promise. Suggestions are hypotheses until a human or model examines
    actual audiovisual content.
    """
    metadata = metadata or {}
    duration = _duration((technical or {}).get('duration_seconds'))
    context = metadata.get('editorial_context') or {}
    if not isinstance(context, dict):
        context = {}
    audience = _safe_text(context.get('audience'))
    promise = _safe_text(context.get('viewer_promise'))
    intended_style = _safe_text(context.get('intended_style'))
    goal = _safe_text(context.get('viewer_outcome'))
    missing = []
    if not audience:
        missing.append('Target viewer: who is this video intended to entertain or help?')
    if not promise:
        missing.append('Viewer promise: what does the title/thumbnail/opening lead viewers to expect?')
    if not goal:
        missing.append('Payoff: what should viewers feel, understand, or see by the end?')
    if not intended_style:
        missing.append('Style intent: raw gameplay, comedic montage, cinematic trailer, tutorial, etc.?')

    opening = min(duration, 5 if duration <= 90 else 15)
    closing_start = max(opening, duration - (6 if duration <= 90 else 15))
    priority = [
        {
            'time_range': f'00:00–{_clock(opening)}',
            'principle': '10:13–11:45: hook resolves expectation and doubt',
            'question': 'Is the promised experience recognizable immediately, with an understandable reason to keep watching?',
            'possible_edit': 'If not, move the clearest stakes, funny reaction, result preview, or evidence earlier; remove setup that delays the premise.',
            'status': 'review_required_not_observed',
        },
        {
            'time_range': f'{_clock(opening)}–{_clock(closing_start)}',
            'principle': '11:45–13:18: acceptance criteria derived from the promise',
            'question': 'Does each substantial beat help deliver the promise, establish necessary context, or strengthen the eventual payoff?',
            'possible_edit': 'If not, shorten, move, or remove that beat. Keep slower moments that intentionally build suspense, humor, or trust.',
            'status': 'review_required_not_observed',
        },
        {
            'time_range': f'{_clock(closing_start)}–{_clock(duration)}',
            'principle': '13:18–14:17: satisfaction relative to expectation',
            'question': 'Does the ending pay off the promise or intentionally set up a clear next part?',
            'possible_edit': 'If not, move the actual payoff into the ending or revise the opening so it promises only what the video delivers.',
            'status': 'review_required_not_observed',
        },
    ] if duration else []

    criteria = [
        'Viewer understands what this video offers early enough for its format.',
        'Every major beat serves the promised experience or sets up its payoff.',
        'Editing density and polish support the intended style rather than compete with it.',
        'The ending delivers the promise or clearly frames an intentional continuation.',
    ]
    if promise:
        criteria.insert(0, f'Explicit promised experience to test against footage: {promise}')
    if audience:
        criteria.append(f'Check examples, jokes, and context for the intended audience: {audience}')
    if goal:
        criteria.append(f'Check desired viewer payoff: {goal}')
    if intended_style:
        criteria.append(f'Check stylistic consistency with: {intended_style}')

    return {
        'source': SOURCE.copy(),
        'assessment': 'contextual_review_only',
        'context': {'audience': audience, 'viewer_promise': promise,
                    'viewer_outcome': goal, 'intended_style': intended_style},
        'missing_context': missing,
        'prioritized_review': priority,
        'acceptance_criteria': criteria,
        'style_warning': 'More transitions, faster cuts, and extra effects are not inherently better; judge against intended viewer expectations (00:40–01:45).',
        'research_warning': 'Topic demand and thumbnail effectiveness require external research; cannot be inferred from video footage alone (03:02–10:13).',
        'analytics_warning': 'CTR, retention, satisfaction, and engagement require actual post-publish data. Treat each metric as a diagnostic signal, not a command (13:18–15:52).',
        'evidence_limit': 'No claims of viewer satisfaction, narrative success, or actual editing defects are made without audiovisual or audience evidence.',
    }
