from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import AppInfo, Bounds, WindowInfo
from dctl.selector import Selector, match_selector


@dataclass(slots=True)
class WindowRecord:
    serialized: dict[str, Any]
    window_id: str


class XdotoolWindowProvider:
    def __init__(self, helper_path: str) -> None:
        self.helper_path = helper_path

    def list_windows(self) -> list[WindowInfo]:
        active = self._active_window_id()
        windows: list[WindowInfo] = []
        for window_id in self._window_ids():
            geometry = self._window_geometry(window_id)
            window = WindowInfo(
                id=window_id,
                title=self._window_name(window_id),
                app_name=self._app_name(window_id),
                pid=self._window_pid(window_id),
                focused=window_id == active,
                bounds=geometry,
            )
            if self._is_real_window(window):
                windows.append(window)
        return windows

    def list_apps(self) -> list[AppInfo]:
        grouped: dict[tuple[str, int | None], AppInfo] = {}
        for window in self.list_windows():
            key = (window.app_name, window.pid)
            if key not in grouped:
                grouped[key] = AppInfo(name=window.app_name, pid=window.pid, id=f"app:{window.app_name}")
            grouped[key].windows.append(window)
        return sorted(grouped.values(), key=lambda item: (item.name.lower(), item.pid or -1))

    def find_elements(self, selector: Selector) -> list[WindowRecord]:
        matches: list[WindowRecord] = []
        for window in self.list_windows():
            serialized = self._window_to_element(window)
            if match_selector(serialized, selector):
                matches.append(WindowRecord(serialized=serialized, window_id=window.id))
        return matches

    def element_at(self, x: int, y: int) -> dict[str, Any]:
        for window in reversed([self._window_to_element(window) for window in self.list_windows()]):
            bounds = window.get("bounds")
            if not bounds:
                continue
            if bounds["x"] <= x <= bounds["x"] + bounds["width"] and bounds["y"] <= y <= bounds["y"] + bounds["height"]:
                return window
        raise DctlError(
            "ELEMENT_NOT_FOUND",
            f"No top-level window found at {x},{y}.",
        )

    def focus_window(self, window_id: str) -> dict[str, Any]:
        self._run(["windowactivate", "--sync", window_id])
        return {"window_id": window_id, "focused": True, "backend": "xdotool"}

    def window_bounds(self, window_id: str) -> Bounds:
        bounds = self._window_geometry(window_id)
        if bounds is None:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"Could not determine geometry for window '{window_id}'.",
            )
        return bounds

    def _window_ids(self) -> list[str]:
        try:
            output = self._run(["search", "--onlyvisible", "--name", ".*"])
        except DctlError:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _window_name(self, window_id: str) -> str:
        return self._run(["getwindowname", window_id]).strip()

    def _window_pid(self, window_id: str) -> int | None:
        output = self._run(["getwindowpid", window_id], allow_failure=True).strip()
        try:
            return int(output)
        except ValueError:
            return None

    def _window_classname(self, window_id: str) -> str:
        return self._run(["getwindowclassname", window_id], allow_failure=True).strip()

    def _window_geometry(self, window_id: str) -> Bounds | None:
        output = self._run(["getwindowgeometry", "--shell", window_id], allow_failure=True)
        values: dict[str, int] = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            try:
                values[key] = int(value)
            except ValueError:
                continue
        required = {"X", "Y", "WIDTH", "HEIGHT"}
        if not required.issubset(values):
            return None
        return Bounds(x=values["X"], y=values["Y"], width=values["WIDTH"], height=values["HEIGHT"])

    def _active_window_id(self) -> str | None:
        output = self._run(["getactivewindow"], allow_failure=True).strip()
        return output or None

    def _app_name(self, window_id: str) -> str:
        pid = self._window_pid(window_id)
        if pid is not None:
            comm_path = Path(f"/proc/{pid}/comm")
            if comm_path.exists():
                name = comm_path.read_text(encoding="utf-8", errors="ignore").strip()
                if name:
                    return name
        classname = self._window_classname(window_id)
        if classname:
            return classname
        title = self._window_name(window_id)
        return title or f"window-{window_id}"

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

    def _run(self, args: list[str], allow_failure: bool = False) -> str:
        result = subprocess.run(
            [self.helper_path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        failed = result.returncode != 0 or "Failed creating new xdo instance." in stdout or "Failed creating new xdo instance." in stderr
        if failed:
            if allow_failure:
                return ""
            message = stderr or stdout or "xdotool command failed."
            raise DctlError(
                "BACKEND_FAILURE",
                f"xdotool command failed: {' '.join(args)}",
                suggestion=message,
            )
        return stdout
