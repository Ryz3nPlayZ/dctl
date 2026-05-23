from __future__ import annotations

from dataclasses import dataclass
import importlib.util
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
    os_version: str = ""
    desktop: str | None = None

    def to_meta(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "session_type": self.session_type,
            "os_version": self.os_version,
            "desktop": self.desktop,
        }


def detect_environment() -> EnvironmentInfo:
    system = platform.system().lower()
    os_version = platform.version()

    helpers: dict[str, str | None] = {
        # ---- Linux / shared ----
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
        # ---- macOS ----
        "open": shutil.which("open"),
        "osascript": shutil.which("osascript"),
        "screencapture": shutil.which("screencapture"),
        # ---- Windows ----
        "powershell": shutil.which("powershell") or shutil.which("pwsh"),
        "winreg_available": "yes" if importlib.util.find_spec("winreg") is not None else None,
        "comtypes_available": "yes" if importlib.util.find_spec("comtypes") is not None else None,
        # ---- browsers (cross-platform) ----
        "brave": shutil.which("brave") or shutil.which("brave-browser"),
        "google-chrome-stable": shutil.which("google-chrome-stable"),
        "google-chrome": shutil.which("google-chrome"),
        "chromium": shutil.which("chromium") or shutil.which("chromium-browser"),
        # ---- office ----
        "libreoffice": shutil.which("libreoffice"),
        "soffice": shutil.which("soffice"),
        # ---- clipboard ----
        "xclip": shutil.which("xclip"),
        "wl-paste": shutil.which("wl-paste"),
        "wl-copy": shutil.which("wl-copy"),
    }
    return EnvironmentInfo(
        platform=system,
        session_type=os.environ.get("XDG_SESSION_TYPE"),
        display=os.environ.get("DISPLAY"),
        wayland_display=os.environ.get("WAYLAND_DISPLAY"),
        helpers=helpers,
        os_version=os_version,
        desktop=os.environ.get("XDG_CURRENT_DESKTOP"),
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
