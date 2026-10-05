"""macOS LaunchAgent for local daily briefs."""

from __future__ import annotations
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.kd.ai-os.daily-brief"
CYCLE_LABEL = "com.kd.ai-os.daily-cycle"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/launchctl", *args], capture_output=True, text=True, check=False)


def install_daily_brief(hour: int = 15, minute: int = 0) -> dict[str, str]:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Schedule time must be a valid 24-hour time")
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    brief_dir = Path.home() / ".ai-os" / "briefs"
    log_dir = Path.home() / ".ai-os" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "ai_os", "daily-brief", "--save"],
        "WorkingDirectory": str(Path(__file__).resolve().parent.parent),
        "EnvironmentVariables": {"AI_OS_DB": str(Path.home() / ".ai-os" / "ai_os.db")},
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "daily-brief.log"),
        "StandardErrorPath": str(log_dir / "daily-brief.error.log"),
    }
    temp_path = path.with_suffix(".plist.tmp")
    with temp_path.open("wb") as stream:
        plistlib.dump(config, stream, sort_keys=True)
    os.replace(temp_path, path)
    uid = os.getuid()
    domain = f"gui/{uid}"
    _launchctl("bootout", f"{domain}/{LABEL}")
    result = _launchctl("bootstrap", domain, str(path))
    if result.returncode:
        raise RuntimeError(f"Could not load daily brief schedule: {result.stderr.strip() or result.stdout.strip()}")
    return {"label": LABEL, "plist": str(path), "time": f"{hour:02d}:{minute:02d}", "timezone": "Mac local time"}


def uninstall_daily_brief() -> dict[str, str]:
    path = plist_path()
    uid = os.getuid()
    result = _launchctl("bootout", f"gui/{uid}/{LABEL}")
    if path.exists():
        path.unlink()
    return {"label": LABEL, "removed": "yes", "launchctl_status": "unloaded" if result.returncode == 0 else "was not loaded"}


def daily_brief_status() -> dict[str, str]:
    path = plist_path()
    if not path.exists():
        return {"installed": "no"}
    config = plistlib.loads(path.read_bytes())
    schedule = config.get("StartCalendarInterval", {})
    uid = os.getuid()
    result = _launchctl("print", f"gui/{uid}/{LABEL}")
    return {
        "installed": "yes",
        "loaded": "yes" if result.returncode == 0 else "no",
        "time": f"{schedule.get('Hour', '?'):02d}:{schedule.get('Minute', '?'):02d}",
        "timezone": "Mac local time",
        "plist": str(path),
    }


def cycle_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{CYCLE_LABEL}.plist"


def install_daily_cycle(hour: int = 15, minute: int = 5) -> dict[str, str]:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Schedule time must be a valid 24-hour time")
    path = cycle_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / ".ai-os" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "Label": CYCLE_LABEL,
        "ProgramArguments": [sys.executable, "-m", "ai_os", "daily-cycle", "--save"],
        "WorkingDirectory": str(Path(__file__).resolve().parent.parent),
        "EnvironmentVariables": {"AI_OS_DB": str(Path.home() / ".ai-os" / "ai_os.db")},
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "daily-cycle.log"),
        "StandardErrorPath": str(log_dir / "daily-cycle.error.log"),
    }
    temp_path = path.with_suffix(".plist.tmp")
    with temp_path.open("wb") as stream:
        plistlib.dump(config, stream, sort_keys=True)
    os.replace(temp_path, path)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", f"{domain}/{CYCLE_LABEL}")
    result = _launchctl("bootstrap", domain, str(path))
    if result.returncode:
        raise RuntimeError(f"Could not load daily cycle schedule: {result.stderr.strip() or result.stdout.strip()}")
    return {"label": CYCLE_LABEL, "plist": str(path), "time": f"{hour:02d}:{minute:02d}", "timezone": "Mac local time"}


def uninstall_daily_cycle() -> dict[str, str]:
    path = cycle_plist_path()
    result = _launchctl("bootout", f"gui/{os.getuid()}/{CYCLE_LABEL}")
    if path.exists():
        path.unlink()
    return {"label": CYCLE_LABEL, "removed": "yes", "launchctl_status": "unloaded" if result.returncode == 0 else "was not loaded"}


def daily_cycle_status() -> dict[str, str]:
    path = cycle_plist_path()
    if not path.exists():
        return {"installed": "no"}
    config = plistlib.loads(path.read_bytes())
    schedule = config.get("StartCalendarInterval", {})
    result = _launchctl("print", f"gui/{os.getuid()}/{CYCLE_LABEL}")
    return {
        "installed": "yes",
        "loaded": "yes" if result.returncode == 0 else "no",
        "time": f"{schedule.get('Hour', '?'):02d}:{schedule.get('Minute', '?'):02d}",
        "timezone": "Mac local time",
        "plist": str(path),
    }
