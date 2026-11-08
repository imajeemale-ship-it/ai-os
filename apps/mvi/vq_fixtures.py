"""Synthetic test footage for Technical Visual Quality. Test support only; nothing here ships to users.

A frame is natural-looking 1/f texture with hard-edged shapes and text, so a real fine-detail
spectrum exists at the native size. Variants (upscale, blur, low bitrate, zoom, grain) are made by
re-encoding that footage the way an editor could.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np


def base_frame(w, h, seed=1):
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    r = np.sqrt(fx * fx + fy * fy)
    r[0, 0] = 1
    spec = (rng.normal(size=(h, w)) + 1j * rng.normal(size=(h, w))) / (r ** 1.15)
    tex = np.real(np.fft.ifft2(spec))
    tex = (tex - tex.min()) / (tex.max() - tex.min())
    img = np.stack([tex * 0.8 + 0.1, tex * 0.9 + 0.05, tex * 0.7 + 0.15], axis=-1)
    img = (img * 200 + 20).astype(np.uint8)
    for i in range(max(60, w * h // 6000)):        # dense hard edges, as in real game footage
        x, y = int(rng.integers(0, w - 80)), int(rng.integers(0, h - 80))
        cv2.rectangle(img, (x, y), (x + int(rng.integers(6, 90)), y + int(rng.integers(6, 70))),
                      tuple(int(c) for c in rng.integers(30, 230, 3)), -1 if i % 3 else 2)
    for i in range(12):
        cv2.putText(img, 'SECURITY CAMERA %d' % i, (int(rng.integers(0, w // 2)), int(rng.integers(40, h - 20))),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.6, h / 900), (255, 255, 255), max(1, h // 540))
    return img


def write_video(path, frames, fps=30, crf=14, extra=None, bitrate=None, size=None):
    h, w = frames[0].shape[:2]
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
           '-pix_fmt', 'yuv420p']
    cmd += (['-b:v', bitrate, '-maxrate', bitrate, '-bufsize', bitrate] if bitrate else ['-crf', str(crf)])
    cmd += (extra or []) + [str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    err = p.stderr.read()
    if p.wait():
        raise RuntimeError(err.decode()[-300:])
    return path


def moving(w, h, n, seed=1, step=14):
    big = base_frame(w + step * n + 8, h, seed)
    return [np.ascontiguousarray(big[:, i * step:i * step + w]) for i in range(n)]


def resize(frames, w, h, interp=cv2.INTER_CUBIC):
    return [cv2.resize(f, (w, h), interpolation=interp) for f in frames]


def native(path, w, h, n=45, fps=30, crf=14, seed=1):
    return write_video(path, moving(w, h, n, seed), fps=fps, crf=crf)


def upscaled(path, src_w, src_h, out_w, out_h, n=45, fps=30, seed=1):
    low = moving(src_w, src_h, n, seed)
    return write_video(path, resize(low, out_w, out_h), fps=fps, crf=14)


def low_bitrate(path, w, h, bitrate='120k', n=45, fps=30, seed=1):
    return write_video(path, moving(w, h, n, seed), fps=fps, bitrate=bitrate)


def blurred_section(path, w, h, n=60, fps=30, start=20, stop=40, seed=1):
    fr = moving(w, h, n, seed)
    for i in range(start, stop):
        fr[i] = cv2.GaussianBlur(fr[i], (0, 0), 6)
    return write_video(path, fr, fps=fps, crf=14)


def over_zoomed(path, w, h, n=45, fps=30, seed=1, factor=5):
    fr = moving(w, h, n, seed)
    out = []
    for f in fr:
        ch, cw = h // factor, w // factor
        y0, x0 = (h - ch) // 2, (w - cw) // 2
        out.append(cv2.resize(f[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_LINEAR))
    return write_video(path, out, fps=fps, crf=14)


def grainy(path, w, h, n=45, fps=30, seed=1, sigma=10):
    rng = np.random.default_rng(7)
    out = []
    for f in moving(w, h, n, seed):
        noise = rng.normal(0, sigma, f.shape[:2])[..., None]
        out.append(np.clip(f.astype(np.float32) + noise, 0, 255).astype(np.uint8))
    return write_video(path, out, fps=fps, crf=14)


def dropped_frames(path, w, h, n=90, fps=30, seed=1):
    """Frames removed at irregular places while the timeline keeps running (stutter)."""
    clean = Path(path).with_name('clean_for_drops.mp4')
    write_video(clean, moving(w, h, n, seed), fps=fps, crf=14)
    expr = "not(eq(mod(n,7),3))*not(between(n,20,21))*not(between(n,45,47))*not(between(n,60,63))"
    p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(clean), '-vf',
                        f"select='{expr}'", '-fps_mode', 'vfr', '-an', '-c:v', 'libx264', '-crf', '14',
                        '-preset', 'veryfast', '-pix_fmt', 'yuv420p', str(path)], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-300:])
    return path


def duplicated_frames(path, w, h, n=60, fps=30, seed=1):
    """30 fps motion shown at 60 fps with every second frame repeated (regular cadence)."""
    out = []
    for f in moving(w, h, n, seed):
        out += [f, f]
    return write_video(path, out, fps=fps * 2, crf=14)


def irregular_dups(path, w, h, n=60, fps=30, seed=1):
    out = []
    rng = np.random.default_rng(3)
    for f in moving(w, h, n, seed):
        out.append(f)
        if rng.random() < 0.3:
            out.append(f)
    return write_video(path, out, fps=fps, crf=14)
