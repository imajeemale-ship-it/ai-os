"""Measure low-volume audio intervals; do not infer dialogue, humor, or editorial intent."""
import re
import subprocess
from pathlib import Path

START = re.compile(r"silence_start:\s*([\d.]+)")
END = re.compile(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")


def parse_silence(log, duration):
 intervals = []
 pending = None
 for line in log.splitlines():
  match = START.search(line)
  if match:
   pending = float(match.group(1))
  match = END.search(line)
  if match:
   end = float(match.group(1))
   start = pending if pending is not None else max(0.0, end-float(match.group(2)))
   if 0 <= start < end <= duration+0.1:
    intervals.append({"start_seconds": round(start, 2),
                      "end_seconds": round(min(end, duration), 2),
                      "duration_seconds": round(min(end, duration)-start, 2)})
   pending = None
 if pending is not None and pending < duration:
  intervals.append({"start_seconds": round(pending, 2),
                    "end_seconds": round(duration, 2),
                    "duration_seconds": round(duration-pending, 2)})
 return intervals


def measure(path, duration, threshold_db=-35, minimum_seconds=0.75):
 """Report measured near-silence, not a claim that content needs trimming."""
 path = Path(path)
 if not path.is_file():
  raise FileNotFoundError(f"Audio file unavailable: {path}")
 cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={minimum_seconds}",
        "-f", "null", "-"]
 result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
 if result.returncode:
  raise RuntimeError("Audio signal scan failed: " + result.stderr[-250:])
 intervals = parse_silence(result.stderr, duration)
 return {"source": "ffmpeg_silencedetect",
         "threshold_db": threshold_db,
         "minimum_seconds": minimum_seconds,
         "intervals": intervals,
         "limitations": ["Low-volume sections can be intentional pauses, muted gameplay, or endings.",
                         "This is a signal-level measurement, not speech recognition or an editorial verdict."]}
