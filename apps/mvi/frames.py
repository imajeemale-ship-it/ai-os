"""Evenly spaced, timestamped frame sampling for a judge. Local only; nothing is sent anywhere here."""
import subprocess
from pathlib import Path

MAX_FRAMES_HARD = 48


def timestamps(duration, count):
    count = max(2, min(int(count), MAX_FRAMES_HARD))
    if duration <= 1:
        return [0.0]
    first, last = min(0.3, duration / 2), max(duration - 0.5, 0.0)
    if count == 2:
        return [round(first, 2), round(last, 2)]
    step = (last - first) / (count - 1)
    return [round(first + i * step, 2) for i in range(count)]


def sample(video, out_dir, duration, count=24, width=768):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, t in enumerate(timestamps(duration, count)):
        target = out / f'f{i:02d}.jpg'
        p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(t), '-i', str(video),
                            '-frames:v', '1', '-vf', f'scale={int(width)}:-2', '-q:v', '5', '-y', str(target)],
                           capture_output=True, text=True, timeout=60)
        if p.returncode == 0 and target.is_file() and target.stat().st_size > 0:
            frames.append({'timestamp_seconds': t, 'file': str(target)})
    return frames


def measure_audio(video, windows):
    """Mean/max volume per window with ffmpeg volumedetect. Measurements only."""
    results = []
    for start, end in windows:
        if end - start < 0.2:
            continue
        p = subprocess.run(['ffmpeg', '-hide_banner', '-ss', str(start), '-to', str(end), '-i', str(video),
                            '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True, timeout=120)
        mean = peak = None
        for line in p.stderr.splitlines():
            if 'mean_volume:' in line:
                mean = float(line.split('mean_volume:')[1].split('dB')[0])
            if 'max_volume:' in line:
                peak = float(line.split('max_volume:')[1].split('dB')[0])
        if mean is not None:
            results.append({'start_seconds': start, 'end_seconds': end, 'mean_db': mean, 'peak_db': peak})
    return results
