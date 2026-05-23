from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import AppInfo, Bounds, WindowInfo
from dctl.selector import Selector, match_selector


@dataclass(slots=True)
class KWinWindowRecord:
    serialized: dict[str, Any]
    kwin_id: str  # KWin internalId


def _kwin_script_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "dctl-kwin-scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_kwin_list_script() -> list[dict[str, Any]]:
    script = (
        'var clients = workspace.windowList();\n'
        'for (var i = 0; i < clients.length; i++) {\n'
        '    var c = clients[i];\n'
        '    var g = c.frameGeometry;\n'
        '    console.info("DCTL_W:" + JSON.stringify({\n'
        '        caption: c.caption,\n'
        '        resourceClass: c.resourceClass,\n'
        '        resourceName: c.resourceName,\n'
        '        pid: c.pid,\n'
        '        internalId: c.internalId + "",\n'
        '        x: g.x,\n'
        '        y: g.y,\n'
        '        width: g.width,\n'
        '        height: g.height,\n'
        '        minimized: c.minimized,\n'
        '        active: c.active\n'
        '    }));\n'
        '}\n'
    )
    marker = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = f"dctl-l-{os.getpid()}-{int(time.monotonic()*1000)%100000}"
    script_path = _kwin_script_dir() / f"{name}.js"
    script_path.write_text(script, encoding="utf-8")

    qdbus = shutil.which("qdbus6") or shutil.which("qdbus")
    if not qdbus:
        raise DctlError("DEPENDENCY_MISSING", "qdbus6 or qdbus is required for KWin scripting.")

    try:
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(script_path), name],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"],
            check=True, capture_output=True, text=True,
        )
        time.sleep(0.4)

        result = subprocess.run(
            ["journalctl", "--user", "-t", "kwin_wayland", "--since", marker, "--no-pager"],
            capture_output=True, text=True, check=False,
        )
    finally:
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name],
            capture_output=True, text=True, check=False,
        )
        script_path.unlink(missing_ok=True)

    windows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        idx = line.find("DCTL_W:")
        if idx == -1:
            continue
        json_str = line[idx + 7:].strip()
        try:
            windows.append(json.loads(json_str))
        except json.JSONDecodeError:
            continue
    return windows


def _run_kwin_focus_script(internal_id: str) -> dict[str, Any]:
    script = (
        'var clients = workspace.windowList();\n'
        f'var targetId = {json.dumps(internal_id)};\n'
        'for (var i = 0; i < clients.length; i++) {\n'
        '    if ((clients[i].internalId + "") === targetId) {\n'
        '        workspace.activeWindow = clients[i];\n'
        '        console.info("DCTL_F:ok:" + clients[i].caption);\n'
        '        break;\n'
        '    }\n'
        '}\n'
    )
    marker = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = f"dctl-f-{os.getpid()}-{int(time.monotonic()*1000)%100000}"
    script_path = _kwin_script_dir() / f"{name}.js"
    script_path.write_text(script, encoding="utf-8")

    qdbus = shutil.which("qdbus6") or shutil.which("qdbus")
    if not qdbus:
        raise DctlError("DEPENDENCY_MISSING", "qdbus6 or qdbus is required for KWin scripting.")

    try:
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(script_path), name],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"],
            check=True, capture_output=True, text=True,
        )
        time.sleep(0.4)

        result = subprocess.run(
            ["journalctl", "--user", "-t", "kwin_wayland", "--since", marker, "--no-pager"],
            capture_output=True, text=True, check=False,
        )
    finally:
        subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name],
            capture_output=True, text=True, check=False,
        )
        script_path.unlink(missing_ok=True)

    for line in result.stdout.splitlines():
        if "DCTL_F:ok:" in line:
            return {"kwin_id": internal_id, "focused": True, "backend": "kwin"}
    raise DctlError("ELEMENT_NOT_FOUND", f"KWin window with id '{internal_id}' not found for focus.")


class KWinWindowProvider:
    def __init__(self) -> None:
        self._cache: list[dict[str, Any]] | None = None

    def list_windows(self) -> list[WindowInfo]:
        raw = self._fetch_windows()
        windows: list[WindowInfo] = []
        for w in raw:
            bounds = Bounds(
                x=int(w.get("x", 0)),
                y=int(w.get("y", 0)),
                width=int(w.get("width", 0)),
                height=int(w.get("height", 0)),
            )
            win = WindowInfo(
                id=w["internalId"],
                title=w.get("caption", ""),
                app_name=w.get("resourceClass", ""),
                pid=w.get("pid"),
                focused=w.get("active", False),
                bounds=bounds,
            )
            if self._is_real_window(win):
                windows.append(win)
        return windows

    def list_apps(self) -> list[AppInfo]:
        grouped: dict[tuple[str, int | None], AppInfo] = {}
        for window in self.list_windows():
            key = (window.app_name, window.pid)
            if key not in grouped:
                grouped[key] = AppInfo(name=window.app_name, pid=window.pid, id=f"app:{window.app_name}")
            grouped[key].windows.append(window)
        return sorted(grouped.values(), key=lambda item: (item.name.lower(), item.pid or -1))

    def find_elements(self, selector: Selector) -> list[KWinWindowRecord]:
        matches: list[KWinWindowRecord] = []
        for window in self.list_windows():
            serialized = self._window_to_element(window)
            if match_selector(serialized, selector):
                matches.append(KWinWindowRecord(serialized=serialized, kwin_id=window.id))
        return matches

    def focus_window(self, kwin_id: str) -> dict[str, Any]:
        return _run_kwin_focus_script(kwin_id)

    def _fetch_windows(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        self._cache = _run_kwin_list_script()
        return self._cache

    def invalidate_cache(self) -> None:
        self._cache = None

    def _window_to_element(self, window: WindowInfo) -> dict[str, Any]:
        state = ["visible"]
        if window.focused:
            state.append("focused")
        path = f"/window[{window.id}]"
        locator = build_locator(app_name=window.app_name, window_title=window.title, path=path)
        return {
            "id": window.id,
            "locator": locator,
            "role": "window",
            "name": window.title,
            "description": None,
            "value": window.title,
            "text": window.title,
            "state": state,
            "actions": ["focus"],
            "bounds": window.bounds.to_dict() if window.bounds else None,
            "path": path,
            "app": {"name": window.app_name, "pid": window.pid},
            "window": {"title": window.title, "id": window.id},
            "children": [],
        }

    def _is_real_window(self, window: WindowInfo) -> bool:
        if window.pid is None and not window.title.strip():
            return False
        if window.bounds and window.bounds.width <= 1 and window.bounds.height <= 1:
            return False
        return True
