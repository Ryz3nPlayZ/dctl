from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import shutil
import subprocess
from typing import Any


@dataclass(slots=True)
class EnvironmentInfo:
    platform: str
    session_type: str | None
    display: str | None
    wayland_display: str | None
    helpers: dict[str, str | None]

    def to_meta(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "session_type": self.session_type,
        }


def detect_environment() -> EnvironmentInfo:
    system = platform.system().lower()
    helpers = {
        "gdbus": shutil.which("gdbus"),
        "xdotool": shutil.which("xdotool"),
        "ydotool": shutil.which("ydotool"),
        "grim": shutil.which("grim"),
        "spectacle": shutil.which("spectacle"),
        "scrot": shutil.which("scrot"),
        "magick": shutil.which("magick") or shutil.which("convert"),
        "wmctrl": shutil.which("wmctrl"),
        "xdg-open": shutil.which("xdg-open"),
        "gtk-launch": shutil.which("gtk-launch"),
        "open": shutil.which("open"),
        "osascript": shutil.which("osascript"),
        "screencapture": shutil.which("screencapture"),
        "brave": shutil.which("brave") or shutil.which("brave-browser"),
        "google-chrome-stable": shutil.which("google-chrome-stable"),
        "google-chrome": shutil.which("google-chrome"),
        "chromium": shutil.which("chromium") or shutil.which("chromium-browser"),
        "libreoffice": shutil.which("libreoffice"),
        "soffice": shutil.which("soffice"),
    }
    return EnvironmentInfo(
        platform=system,
        session_type=os.environ.get("XDG_SESSION_TYPE"),
        display=os.environ.get("DISPLAY"),
        wayland_display=os.environ.get("WAYLAND_DISPLAY"),
        helpers=helpers,
    )


def command_ok(args: list[str]) -> bool:
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        return completed.returncode == 0
    except OSError:
        return False
