#!/usr/bin/env python3
"""Fetch a video link on YOUR computer and send the file to MVI.

Use this when MVI's server could not retrieve a link (bot check, login wall).
The download happens on your own connection. Any browser cookies are read
locally by yt-dlp and are never sent to MVI; only the finished video file is
uploaded. Use it for videos you are allowed to watch and review privately.

Requires: python3, yt-dlp (pip install yt-dlp), ffmpeg.
Token: set MVI_API_TOKEN in your environment (never put it on the command line).

Examples:
  export MVI_API_TOKEN=...
  python3 mvi_local_fetch.py "https://www.tiktok.com/@x/video/123" --server https://mvi-private-pilot.onrender.com
  python3 mvi_local_fetch.py "<link>" --server <url> --attach-to <blocked job id>
  python3 mvi_local_fetch.py "<link>" --server <url> --browser chrome   # use your logged-in Chrome session locally
"""
import argparse, json, os, subprocess, sys, tempfile, urllib.request, urllib.parse
from pathlib import Path

MAX_BYTES = 500 * 1024 * 1024


def fetch(link, folder, browser=None):
    cmd = [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-progress',
           '--max-filesize', '500M', '--merge-output-format', 'mp4',
           '-f', 'bv*[height<=720]+ba/b[height<=720]/bv*+ba/b',
           '-o', str(Path(folder) / 'source.%(ext)s')]
    if browser:
        cmd += ['--cookies-from-browser', browser]  # read locally, never uploaded
    cmd.append(link)
    done = subprocess.run(cmd)
    if done.returncode:
        raise SystemExit('Download failed on this computer too. Screen-record the video and attach the file instead.')
    files = [p for p in Path(folder).glob('source.*') if p.suffix.lower() in ('.mp4', '.mov')]
    if not files:
        raise SystemExit('No MP4/MOV was produced. Try --browser chrome or screen-record the video.')
    return files[0]


def upload(path, server, token, attach_to=None, context=None):
    size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise SystemExit('File is empty or over the 500 MB limit.')
    endpoint = f'/api/jobs/{attach_to}/attach' if attach_to else '/api/upload'
    headers = {'Authorization': 'Bearer ' + token, 'X-Filename': urllib.parse.quote(path.name),
               'Content-Type': 'application/octet-stream', 'Content-Length': str(size)}
    if context:
        headers['X-MVI-Context'] = urllib.parse.quote(json.dumps(context))
    with path.open('rb') as body:
        req = urllib.request.Request(server.rstrip('/') + endpoint, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                return json.load(res)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f'MVI rejected the upload ({exc.code}): {exc.read()[:300].decode(errors="replace")}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('link')
    ap.add_argument('--server', required=True, help='MVI base URL')
    ap.add_argument('--attach-to', help='job id that reported needs_fallback')
    ap.add_argument('--browser', help='chrome, safari, firefox... use that browser login locally')
    a = ap.parse_args()
    token = os.environ.get('MVI_API_TOKEN', '')
    if not token:
        raise SystemExit('Set MVI_API_TOKEN in your environment first.')
    with tempfile.TemporaryDirectory() as folder:
        video = fetch(a.link, folder, a.browser)
        result = upload(video, a.server, token, a.attach_to)
    print(json.dumps({'job_id': result.get('job_id'), 'status': result.get('status')}))


if __name__ == '__main__':
    main()
