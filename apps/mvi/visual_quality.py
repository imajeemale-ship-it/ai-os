"""Technical Visual Quality: what the pixels of the video actually look like.

This module only MEASURES decoded pixels and frame timing. It never reads the container's
resolution or bitrate to decide a score: a 720p source exported as 4K is detected from how much
real fine detail the decoded frames contain. Measurements are signals for a judge and a
blended subscore, not a verdict, and every threshold here is a draft that needs calibration
against real footage.

Subscore weights (sum 100) follow the owner's spec. Objective measurements feed six of the nine:
source_sharpness, effective_resolution, compression_quality, motion_quality,
color_exposure_integrity, visual_consistency. scale_crop_quality, text_graphics_clarity and
evidence_visibility need a viewer (they depend on what the narration points at), so they are
judged, never guessed from numbers.
"""
import statistics
import subprocess
from pathlib import Path

import cv2
import numpy as np

import frames as framelib

WEIGHTS = {
    'source_sharpness': 15, 'effective_resolution': 15, 'compression_quality': 15,
    'scale_crop_quality': 15, 'text_graphics_clarity': 10, 'motion_quality': 10,
    'color_exposure_integrity': 5, 'visual_consistency': 5, 'evidence_visibility': 10,
}
assert sum(WEIGHTS.values()) == 100
MEASURED = ('source_sharpness', 'effective_resolution', 'compression_quality', 'motion_quality',
            'color_exposure_integrity', 'visual_consistency')
JUDGED_ONLY = ('scale_crop_quality', 'text_graphics_clarity', 'evidence_visibility')
SUBCATEGORY_NAMES = {
    'source_sharpness': 'Source Sharpness', 'effective_resolution': 'Effective Resolution',
    'compression_quality': 'Compression Quality', 'scale_crop_quality': 'Scale / Crop Quality',
    'text_graphics_clarity': 'Text / Graphics Clarity', 'motion_quality': 'Motion Quality',
    'color_exposure_integrity': 'Color / Exposure Integrity', 'visual_consistency': 'Visual Consistency',
    'evidence_visibility': 'Evidence Visibility',
}
MIN_FRAMES = 4
FRAME_COUNT = 16
CROP = 1024            # analysis crop (pixels) for spectral measures
MOTION_WINDOWS = 6     # windows used to inspect frame cadence on long videos
MOTION_WINDOW_SECONDS = 25.0
BANDS = [(90, 'Excellent / professional'), (80, 'Very good'), (70, 'Acceptable'),
         (60, 'Weak'), (40, 'Poor'), (0, 'Unacceptable')]

# Effective vertical detail (pixels) -> score. 4K detail is the top; clean 1080p still scores well.
RES_ANCHORS = [(0, 0), (240, 10), (360, 25), (480, 40), (720, 65), (1080, 85), (1440, 93), (2160, 100)]


def band(score):
    for floor, name in BANDS:
        if score >= floor:
            return name
    return BANDS[-1][1]


def _interp(x, anchors):
    if x <= anchors[0][0]:
        return float(anchors[0][1])
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return float(anchors[-1][1])


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


# ---------------------------------------------------------------- decoding

def read_frames(video, duration, count=FRAME_COUNT):
    """Native-resolution decoded frames (BGR) at evenly spaced timestamps."""
    cap = cv2.VideoCapture(str(video))
    out = []
    try:
        if not cap.isOpened():
            return out
        for t in framelib.timestamps(duration, count):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                out.append((t, frame))
    finally:
        cap.release()
    return out


def _content_box(gray):
    """Crop away black letterbox/pillarbox bars so they do not count as content."""
    rows = np.where(gray.mean(axis=1) > 6)[0]
    cols = np.where(gray.mean(axis=0) > 6)[0]
    if len(rows) < 32 or len(cols) < 32:
        return gray
    return gray[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def _center_crop(gray, size=CROP):
    h, w = gray.shape
    side_h, side_w = min(h, size), min(w, size)
    y0, x0 = ((h - side_h) // 2) // 16 * 16, ((w - side_w) // 2) // 16 * 16   # keep the codec block grid aligned
    return gray[y0:y0 + side_h, x0:x0 + side_w]


# ---------------------------------------------------------------- per-frame measures

def _radial_psd(gray):
    crop = _center_crop(gray).astype(np.float32)
    h, w = crop.shape
    if min(h, w) < 128:
        return None
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    spec = np.abs(np.fft.fftshift(np.fft.fft2((crop - crop.mean()) * win))) ** 2
    fy = np.fft.fftshift(np.fft.fftfreq(h))[:, None]
    fx = np.fft.fftshift(np.fft.fftfreq(w))[None, :]
    radius = np.sqrt(fx * fx + fy * fy)           # cycles per pixel; 0.5 is the Nyquist limit
    idx = np.digitize(radius, np.linspace(0, 0.5, 33)) - 1
    valid = (idx >= 0) & (idx < 32)
    power = np.bincount(idx[valid], weights=spec[valid], minlength=32)[:32]
    count = np.bincount(idx[valid], minlength=32)[:32].clip(min=1)
    psd = np.log10(power / count + 1e-9)
    return psd if np.isfinite(psd).all() else None


# (fine detail relative to mid detail, in decades) -> share of the pixel grid that holds real detail
GAP_TO_RATIO = [(-3.6, 0.30), (-3.0, 0.34), (-2.5, 0.60), (-2.0, 0.90), (-1.6, 1.0)]
# (edge steepness, p99 gradient over contrast) -> share of the pixel grid that holds real detail
EDGE_TO_RATIO = [(1.5, 0.12), (3, 0.20), (5, 0.30), (7, 0.50), (9, 0.70), (10.5, 0.85), (12, 1.0)]


def edge_steepness(gray):
    """p99 gradient magnitude over contrast. High when edges are crisp at the pixel level."""
    g = _center_crop(gray).astype(np.float32)
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    return float(np.percentile(mag, 99) / (g.std() + 1e-6))


def effective_detail_ratio(gray):
    """Share of the pixel grid that carries real picture detail (1.0 = full detail at this size).

    A frame upscaled from a lower resolution has far less fine detail than its pixel count implies,
    whatever the container claims. The estimate takes the weaker of two independent views: how much
    energy survives in the finest spatial frequencies, and how steep the edges are. None if too small.
    """
    psd = _radial_psd(gray)
    if psd is None:
        return None
    r = (np.arange(32) + 0.5) / 64.0
    hi = psd[(r >= 0.30) & (r <= 0.5)].mean()
    mid = psd[(r >= 0.08) & (r <= 0.14)].mean()
    from_spectrum = _interp(hi - mid, GAP_TO_RATIO)
    from_edges = _interp(edge_steepness(gray), EDGE_TO_RATIO)
    return float(min(from_spectrum, from_edges)), float(edge_steepness(gray))


def blockiness(gray):
    """Extra luminance step (gray levels) on 8/16 pixel block borders compared with the rest of the frame."""
    g = _center_crop(gray).astype(np.float32)
    best = 0.0
    for period in (8, 16):
        for axis in (1, 0):
            d = np.abs(np.diff(g, axis=axis))
            n = d.shape[axis]
            pos = np.arange(n) % period == period - 1
            sel = d[:, pos] if axis == 1 else d[pos, :]
            rest = d[:, ~pos] if axis == 1 else d[~pos, :]
            best = max(best, float(sel.mean() - rest.mean()))
    return best


def exposure_stats(gray):
    g = _content_box(gray)
    g = g[::2, ::2]
    p5, p50, p95 = np.percentile(g, [5, 50, 95])
    return {'crushed': float((g <= 8).mean()), 'blown': float((g >= 248).mean()),
            'spread': float(p95 - p5), 'median': float(p50)}


def _frame_scores(gray):
    got = effective_detail_ratio(gray)
    if got is None:
        return None
    ratio, steep = got
    h = gray.shape[0]
    blk = blockiness(gray)
    exp = exposure_stats(gray)
    eff_h = ratio * h
    sharp_score = _clamp(_interp(steep, [(1.5, 0), (3, 15), (5, 35), (7, 55), (9, 72), (11, 88), (13, 100)]))
    res_score = _clamp(_interp(eff_h, RES_ANCHORS))
    blk_score = _clamp(_interp(blk, [(0.0, 100), (0.3, 92), (0.8, 68), (1.5, 38), (3.0, 5)]))
    return {'detail_ratio': round(ratio, 3), 'effective_height': round(eff_h), 'sharpness': round(steep, 2),
            'blockiness': round(blk, 3), 'sharpness_score': sharp_score, 'resolution_score': res_score,
            'blockiness_score': blk_score, 'exposure': exp}


def exposure_score(exp):
    crush = _interp(exp['crushed'], [(0.0, 0), (0.12, 0), (0.35, 18), (0.7, 45)])
    blown = _interp(exp['blown'], [(0.0, 0), (0.03, 0), (0.12, 20), (0.4, 45)])
    flat = _interp(exp['spread'], [(0, 40), (40, 30), (80, 8), (110, 0)])
    dim = 15 if exp['median'] < 22 or exp['median'] > 225 else 0
    return _clamp(100 - crush - blown - flat - dim)


# ---------------------------------------------------------------- frame cadence

def _decode_tiny(video, start, length, size=(160, 90)):
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', str(start), '-t', str(length), '-i', str(video),
           '-an', '-vf', f'scale={size[0]}:{size[1]},format=gray', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']
    p = subprocess.run(cmd, capture_output=True, timeout=240)
    n = size[0] * size[1]
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    frames_n = len(data) // n
    return data[:frames_n * n].reshape(frames_n, size[1], size[0]).astype(np.int16)


def _frame_times(video, start, length):
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-read_intervals', f'{start}%+{length}',
           '-show_entries', 'frame=pts_time,best_effort_timestamp_time', '-of', 'csv=p=0', str(video)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    times = []
    for line in p.stdout.splitlines():
        for part in line.split(','):
            try:
                times.append(float(part))
                break
            except ValueError:
                continue
    return times


def windows(duration):
    if duration <= MOTION_WINDOWS * MOTION_WINDOW_SECONDS:
        return [(0.0, duration)]
    step = (duration - MOTION_WINDOW_SECONDS) / (MOTION_WINDOWS - 1)
    return [(round(i * step, 2), MOTION_WINDOW_SECONDS) for i in range(MOTION_WINDOWS)]


def cadence(video, duration):
    """Dropped, duplicated and unevenly timed frames, with timestamps of the worst stretches."""
    total_frames = dups = irregular_dups = drops = 0
    worst = []
    for start, length in windows(duration):
        tiny = _decode_tiny(video, start, length)
        if len(tiny) < 8:
            continue
        diffs = np.abs(np.diff(tiny, axis=0)).mean(axis=(1, 2))
        moving = diffs[diffs > 0.3]
        if len(moving) < 4 or float(np.median(moving)) < 0.8:
            continue                                   # near-static footage: duplicates prove nothing
        is_dup = diffs < 0.12
        fps_guess = len(tiny) / max(length, 0.1)
        idx = np.where(is_dup)[0]
        total_frames += len(diffs)
        dups += int(is_dup.sum())
        if len(idx) >= 2:
            gaps = [float(x) for x in np.diff(idx)]
            regular = len(gaps) >= 3 and statistics.pstdev(gaps) < 0.25 * statistics.mean(gaps)
        else:
            regular = len(idx) == 0 or len(idx) < 2
        if not regular and len(idx):
            irregular_dups += int(len(idx))
            for i in idx[:3]:
                worst.append(round(start + i / fps_guess, 2))
        times = _frame_times(video, start, length)
        if len(times) > 8:
            deltas = np.diff(np.array(times))
            deltas = deltas[deltas > 0]
            if len(deltas):
                base = float(np.median(deltas))
                gaps_found = deltas > base * 1.8
                drops += int(gaps_found.sum())
                for i in np.where(gaps_found)[0][:3]:
                    worst.append(round(times[i], 2))
    return {'frames_checked': total_frames, 'duplicate_frames': dups, 'irregular_duplicates': irregular_dups,
            'timing_gaps': drops, 'worst_seconds': sorted(set(worst))[:6]}


def motion_score(c):
    n = c['frames_checked']
    if n < 12:
        return None
    irregular = c['irregular_duplicates'] / n
    gaps = c['timing_gaps'] / n
    return _clamp(100 - 260 * irregular - 600 * gaps)


# ---------------------------------------------------------------- orchestration

def _issue(t, text, sub, severity, impact, fix, step):
    return {'timestamp_start': round(max(0.0, t - step / 2), 2), 'timestamp_end': round(t + step / 2, 2),
            'issue': text, 'subcategory': SUBCATEGORY_NAMES[sub], 'severity': severity,
            'impact': impact, 'recommended_fix': fix, 'source': 'measured'}


def measure(video, duration, count=FRAME_COUNT):
    """Return objective subscores (0-100) with the measurements behind them, or None if undecodable."""
    decoded = read_frames(video, duration, count)
    per = []
    for t, bgr in decoded:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        s = _frame_scores(gray)
        if s:
            s['timestamp_seconds'] = t
            s['frame_size'] = [int(bgr.shape[1]), int(bgr.shape[0])]
            s['exposure_score'] = exposure_score(s['exposure'])
            per.append(s)
    if len(per) < MIN_FRAMES:
        return None
    step = max(duration / max(len(per), 1), 0.5)
    med = statistics.median
    sharp = [p['sharpness_score'] for p in per]
    res = [p['resolution_score'] for p in per]
    blk = [p['blockiness_score'] for p in per]
    expo = [p['exposure_score'] for p in per]
    # a video is only as sharp as it looks most of the time: blend the typical frame with the soft end
    def robust(values):
        v = sorted(values)
        low = v[:max(1, len(v) // 4)]
        return 0.7 * med(values) + 0.3 * (sum(low) / len(low))
    cad = cadence(video, duration)
    mscore = motion_score(cad)
    spread = statistics.pstdev(sharp) + 0.6 * statistics.pstdev(res)
    outliers = [p for p in per if p['sharpness_score'] < med(sharp) - 25 or p['resolution_score'] < med(res) - 25]
    consistency = _clamp(100 - 1.1 * spread - 6 * len(outliers))
    subs = {'source_sharpness': _clamp(robust(sharp)), 'effective_resolution': _clamp(robust(res)),
            'compression_quality': _clamp(robust(blk)), 'color_exposure_integrity': _clamp(robust(expo)),
            'visual_consistency': consistency}
    if mscore is not None:
        subs['motion_quality'] = mscore
    issues = []
    for p in per:
        t = p['timestamp_seconds']
        if p['sharpness_score'] < med(sharp) - 25:
            issues.append(_issue(t, 'Frame is much softer than the rest of the video', 'visual_consistency', 'Medium',
                                 'A soft stretch makes the quality feel uneven', 'Replace the clip with a sharper source or match its treatment', step))
        elif p['sharpness_score'] < 35:
            issues.append(_issue(t, 'Footage looks soft', 'source_sharpness', 'Medium',
                                 'Fine detail is hard to see', 'Use a higher quality source or avoid sharpening a soft source', step))
        if p['blockiness'] > 1.5:
            issues.append(_issue(t, 'Visible block-shaped compression artifacts', 'compression_quality', 'Medium',
                                 'Fine detail is lost to blocking', 'Increase export bitrate or replace the compressed source', step))
        if p['exposure']['crushed'] > 0.35:
            issues.append(_issue(t, 'Large areas are crushed to black', 'color_exposure_integrity', 'Medium',
                                 'Detail in the shadows is lost', 'Lift shadows or fix the source gamma', step))
        if p['exposure']['blown'] > 0.12:
            issues.append(_issue(t, 'Highlights are blown out', 'color_exposure_integrity', 'Medium',
                                 'Detail in bright areas is lost', 'Pull highlights down', step))
    for t in cad['worst_seconds']:
        issues.append(_issue(t, 'Uneven frame timing (dropped or repeated frames)', 'motion_quality', 'Medium',
                             'Movement stutters', 'Re-export at the source frame rate, avoid mixed frame rates', 1.0))
    sizes = sorted({tuple(p['frame_size']) for p in per})
    return {'subscores': {k: round(v, 1) for k, v in subs.items()},
            'per_frame': [{k: p[k] for k in ('timestamp_seconds', 'effective_height', 'sharpness', 'blockiness',
                                             'sharpness_score', 'resolution_score')} for p in per],
            'cadence': cad, 'decoded_size': list(sizes[0]) if sizes else None,
            'effective_height_median': round(med([p['effective_height'] for p in per])),
            'frames_measured': len(per), 'issues': issues[:24],
            'limitations': ['Measurements are draft signals that have not been calibrated against real footage.',
                            'Film grain, retro filters and dark scenes can look like quality problems to a measurement; the judge may override.',
                            'Only a sample of frames is inspected, plus the frame timing of up to six windows.']}
