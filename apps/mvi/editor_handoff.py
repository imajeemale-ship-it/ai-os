"""A concise editor-facing review brief; evidence is not fabricated."""
from pathlib import Path
from research_rules import PLAYBOOK
SOURCE='https://youtu.be/h-8C3bntQRo'
def build_brief(video_title='David\'s M3 edit', evidence=None):
 evidence=evidence or {}
 scenes=evidence.get('scene_count')
 scene_note=f'Vindex identified {scenes} scenes; scene count is structural, not a quality judgment.' if scenes is not None else 'Scene boundaries pending Vindex compilation.'
 return f'''# M3 Editor Handoff — {video_title}

## What MVI has verified
{scene_note}
Editorial quality, timing of jokes, viewer retention and audio quality have **not** been assessed unless accompanied by timestamped audiovisual observations.

## David's first editing pass
- **Opening (0–15s):** Does the viewer immediately understand the GTA challenge, conflict or stakes? Put the strongest *honest* visual anchor early.
- **Story:** Can a first-time viewer follow what Rico wants, what goes wrong and why it matters? Remove dead time that adds no character or payoff.
- **Visual clarity:** Check whether overlapping text, zooms, stickers and cuts compete for attention. Avoid eye fatigue; keep the focal point clear.
- **Sound:** Keep speech/gameplay intelligible. Use music and effects to strengthen, not mask, a joke or reveal.
- **Payoff:** Deliver on the opening promise, then give the viewer a reason to watch the next M3 episode.
- **Packaging:** Draft three *different* thumbnail concepts using the Five C's (composition, context, clean, curiosity, color). Title must accurately reflect the edit.
- **Shorts:** Treat frame zero as the opening hook; don't assume long-form thumbnail rules apply unchanged.

## M3 team workflow
Rico: supply source gameplay, highlights and context. David: edit, story and packaging drafts. KD: approve creative direction and publishing decisions. MVI: timestamped evidence, review prompts and experiments.

## Research basis
{SOURCE} — Jon Youshaei, YouTube Masterclass 2025. English auto-captions retrieved; these are suggested tests, not guaranteed YouTube rules.
See `{PLAYBOOK.name}` and `002_YOUTUBE_MASTERCLASS.md`.

## Before publishing
Confirm edit quality by watching the actual footage; review phone-size thumbnail; check copyright/music permissions; use YouTube analytics after publication to evaluate hypotheses.
'''
if __name__=='__main__':
 import json,sys
 evidence=json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv)>1 else {}
 print(build_brief(evidence=evidence))
