# MVI — David's 61-second intro: evidence-led review

Source examined locally: `~/Downloads/Intro wip 1.mp4`. Duration 60.88 seconds, 1278x720, 30 fps, audio track present. No files were uploaded or published.

## What was actually observed

Seven still frames were inspected visually at approximately 0.50, 6.09, 15.22, 30.44, 45.66, 54.79, and 59.88 seconds. These are snapshots, not continuous playback.

| Time | Direct observation from frame | Editing question, not a finding |
| --- | --- | --- |
| 00:00.5 | GTA gameplay: a character rides a watercraft; on-screen objective reads “Destroy the boats.” | Is this the intended central challenge or an opening montage image? |
| 00:06.1 | A player character aims and fires from behind a rooftop wall toward another labeled player. | Is the relationship to the opening objective clear to a first-time viewer? |
| 00:15.2 | A red sports car drives down a city street. | Does the edit intentionally switch gameplay modes, and is there connective context? |
| 00:30.4 | A vehicle appears amid fire/explosion effects on a city street. | Is this a payoff moment that would be stronger earlier, or is it already in the right place? |
| 00:45.7 | Oversized black text with white outline reads “TRICKS” over gameplay. | Is this title readable for long enough? Is its placement deliberate? |
| 00:54.8 | Black stylized M3 logo appears on a pale background. | Does the logo sequence deliver a call-to-action or simply end the montage? |
| 00:59.9 | Stylized white logo appears on a black background. | Is the final end-card duration useful? |

Vindex compiled 28 shot intervals; shot count alone is not a pacing score.

FFmpeg signal detection, threshold -35 dB with minimum interval 0.75s, found two low-volume spans: **00:16.74–00:22.47 (5.73s)** and **00:52.87–01:00.88 (8.01s)**. These are measurable signal intervals, not proof of missing audio or dead air.

## Highest-value checks for David

1. Watch **00:00–00:16** continuously. Verify whether the watercraft, shooting, and driving are intentionally distinct highlights or part of a comprehensible narrative. A screenshot cannot answer this.
2. Listen to **00:16.74–00:22.47**. Determine whether the 5.73-second low-volume interval is intentional; if not, inspect the mix or trim.
3. Watch **00:28–00:33** continuously. The sampled frame at 00:30.44 contains a striking explosion. Test whether it is a stronger honest hook than the existing first frame; do not assume so without context.
4. Review **00:45–00:53**. Confirm that “TRICKS” is readable, purposeful, and not obscuring critical gameplay during its actual on-screen duration.
5. Review **00:52.87–end**. The 8.01-second low-volume span overlaps the sampled M3 end-card frames. Confirm the intended ending length, sound design, and call-to-action before trimming.

## What remains unverified

No continuous visual viewing, full audio listening, transcript, speaker identification, sound-quality assessment, joke timing, CTR, or retention analytics has been performed. The initial local Qwen3-VL run returned no usable answer after 219 seconds; that is a model failure, not a negative evaluation of David's edit. No creative score is assigned.

Generated local artifacts: `~/.mvi/manual-david-61s/EDITOR_REPORT.md`, `editor_report.json`, Vindex timeline, extracted audio, and sampled frames. Keep original footage unchanged.

## Reproducibility check — 2026-10-19

Ran the current unified MVI media pipeline against the original `~/Downloads/Intro wip 1.mp4` without enabling the local vision model. The job completed, Vindex returned successfully, and the generated report contained 30 timeline rows (28 shot intervals plus two measured low-audio intervals). New report: `~/.mvi/verified-david-61s-20261019/EDITOR_REPORT.md`.

The report now ranks the two audio listening checkpoints by measured interval length: 00:52.87–01:00.88 (8.01s, overlaps the final 15 seconds) first; 00:16.74–00:22.47 (5.73s) second. This is a listening priority, not a claim that the editor made a mistake. Continuous audiovisual understanding, spoken-word recognition, and a creative quality score remain unavailable. The original video was not modified.

## Source-bound sampled-frame annotations — 2026-10-19

The seven already-inspected still-frame observations from this audit were saved locally to `~/.mvi/verified-david-61s-20261019/human_review.json`, keyed to the exact source video's SHA-256. The new `human_evidence.py` loader checks that source hash and matches each observation to an actually extracted frame timestamp before adding it to an editor report. Notes are excluded with an explicit warning if either check fails. The source video and annotations remain on the authorized Mac; the annotations are not committed to the repository.

Rebuilt the local editor report from existing Vindex, FFmpeg, and sampled-frame evidence: **37 timeline entries** (28 detected shot intervals, 2 low-audio intervals, 7 human-inspected still-frame observations). The observations produce timestamped questions for David; they are not full-motion observations or an AI creative score. No continuous playback or audio-semantic evaluation was added.

## Cross-modal evidence review — 2026-10-19

MVI now compares Vindex shot intervals with FFmpeg-measured low-audio intervals, promoting only overlaps of at least 2 seconds covering at least 70% of the shot interval. This is a timing intersection, not speech understanding or a finding that an edit is defective.

Rebuilt the original source-bound local report with 37 timeline evidence entries and two new combined A/V review checkpoints:

- **00:16.74–00:22.43 (5.69s overlap):** Watch and listen to the sustained shot in context; verify whether the quieter mix and visual hold are intentional.
- **00:57.83–01:00.87 (3.03s overlap):** Review the final visual hold and quieter audio together; decide whether this is the intended end-card experience.

No additional footage was semantically viewed, no spoken audio was transcribed, and no creative quality score was generated. Three focused cross-modal tests and the full suite passed (40 tests total). Local report: `~/.mvi/verified-david-61s-20261019/EDITOR_REPORT.md`.
