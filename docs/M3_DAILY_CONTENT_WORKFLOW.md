# M3 Daily Content Workflow

Goal: turn M3 into a repeatable daily content engine, starting with Rico GTA footage.

Run:

```bash
python3 -m ai_os m3-workflow
```

## Daily Order

1. Choose one Rico GTA footage source.
2. Clip one moment with a clear setup, turn, or payoff.
3. Write one hook and one title before editing further.
4. Publish, schedule, or package one visible asset.
5. Log proof: file name, platform, link or location, and next action.

## Proof Required

- Asset file, draft, scheduled post, or published link.
- Title or hook used.
- Next M3 task created or written down.

## Handoff Rule

If footage access, platform login, or final taste call is required, escalate to KD. Otherwise continue autonomously.

## Proof Logging

Record proof after every M3 action:

```bash
python3 -m ai_os m3-proof --asset "clip-001.mp4" --hook "When the getaway goes wrong" --next-action "Pick tomorrow's clip" --platform local
```

This writes an `m3.proof_logged` event into AI-OS so Johnny 5 can review actual progress instead of relying on memory.

## Source Discovery

Find local Rico, M3, or GTA video sources:

```bash
python3 -m ai_os m3-sources --path ~/Downloads --path ~/Desktop
```

Current strong source candidate:

```text
/Users/unagidon/Downloads/Rico_vs_THE_WORLD_KD_Cut_2_COMPLETE.mp4
```

## Clip Planning

Create candidate short segments from a source video:

```bash
python3 -m ai_os m3-clip-plan /path/to/source.mp4 --length 20
```

Current candidate plan for `Rico_vs_THE_WORLD_KD_Cut_2_COMPLETE.mp4`:

- opening hook: 0s-20s
- middle turn: 59s-79s
- closing payoff: 119s-139s
