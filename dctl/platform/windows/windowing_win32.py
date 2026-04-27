"""
Windows window management via Win32 API (User32).

Enumerates top-level windows, retrieves geometry, titles, PIDs,
and can bring a window to the foreground.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import Bounds, WindowInfo


@dataclass(slots=True)
class Win32WindowRecord:
    hwnd: int
    serialized: dict[str, Any]


class Win32WindowProvider:
    """
    Wraps EnumWindows / GetWindowText / GetWindowRect etc. from User32.dll.
    """

    def __init__(self) -> None:
        try:
            import ctypes
            import ctypes.wintypes
            self._ctypes = ctypes
            self._wintypes = ctypes.wintypes
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
        except Exception as exc:
            raise DctlError(
                "PLATFORM_NOT_SUPPORTED",
                "Win32 windowing APIs are not available.",
                suggestion="This backend requires Windows.",
            ) from exc

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        return [_dict_to_window_info(r.serialized) for r in self._iter_windows()]

    def list_apps(self) -> list[dict[str, Any]]:
        by_pid: dict[int, dict[str, Any]] = {}
        for record in self._iter_windows():
            s = record.serialized
            pid = (s.get("app") or {}).get("pid") or 0
            name = (s.get("app") or {}).get("name") or "unknown"
            if pid not in by_pid:
                by_pid[pid] = {"name": name, "pid": pid, "id": str(pid), "windows": []}
            by_pid[pid]["windows"].append(s)
        return list(by_pid.values())

    def find_elements(self, selector: Any) -> list[Win32WindowRecord]:
        from dctl.selector import match_selector
        matches: list[Win32WindowRecord] = []
        for record in self._iter_windows():
            if match_selector(record.serialized, selector):
                matches.append(record)
        return matches

    def focus_window(self, hwnd_or_id: str | int) -> dict[str, Any]:
        hwnd = int(hwnd_or_id)
        self._user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        self._user32.SetForegroundWindow(hwnd)
        return {"focused": True, "hwnd": hwnd, "backend": "win32"}

    def window_bounds(self, hwnd_or_id: str | int) -> Bounds:
        hwnd = int(hwnd_or_id)
        return self._get_rect(hwnd)

    def element_at(self, x: int, y: int) -> dict[str, Any]:
        hwnd = self._user32.WindowFromPoint(self._make_point(x, y))
        if not hwnd:
            raise DctlError("ELEMENT_NOT_FOUND", f"No window found at {x},{y}.")
        for record in self._iter_windows():
            if record.hwnd == hwnd:
                return record.serialized
        raise DctlError("ELEMENT_NOT_FOUND", f"No window record found for hwnd {hwnd}.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_windows(self) -> list[Win32WindowRecord]:
        records: list[Win32WindowRecord] = []
        ctypes = self._ctypes
        user32 = self._user32

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def _callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if not title:
                return True
            pid_val = ctypes.wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
            pid = int(pid_val.value)
            app_name = _process_name_for_pid(self._kernel32, pid)
            bounds = self._get_rect(hwnd)
            path = f"/window[hwnd={hwnd}]"
            locator = build_locator(app_name=app_name, window_title=title, path=path)
            state = ["visible"]
            if user32.GetForegroundWindow() == hwnd:
                state.append("focused")
            serialized = {
                "id": str(hwnd),
                "locator": locator,
                "role": "window",
                "name": title,
                "description": None,
                "value": title,
                "text": title,
                "state": state,
                "actions": ["focus"],
                "bounds": bounds.to_dict() if bounds else None,
                "path": path,
                "app": {"name": app_name, "pid": pid},
                "window": {"title": title, "id": str(hwnd)},
                "children": [],
            }
            records.append(Win32WindowRecord(hwnd=hwnd, serialized=serialized))
            return True

        cb = EnumWindowsProc(_callback)
        user32.EnumWindows(cb, 0)
        return records

    def _get_rect(self, hwnd: int) -> Bounds | None:
        from ctypes import wintypes
        rect = wintypes.RECT()
        if self._user32.GetWindowRect(hwnd, self._ctypes.byref(rect)):
            return Bounds(
                x=rect.left,
                y=rect.top,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
            )
        return None

    def _make_point(self, x: int, y: int) -> Any:
        """Pack x,y into a POINT struct value for WindowFromPoint."""
        # WindowFromPoint accepts a POINT by value on 32-bit and 64-bit
        # via ctypes ctypes.wintypes.POINT
        from ctypes import wintypes
        pt = wintypes.POINT(x, y)
        # Win32 packs POINT as a single 64-bit value on 64-bit Windows
        return pt


def _dict_to_window_info(s: dict[str, Any]) -> WindowInfo:
    bounds_dict = s.get("bounds")
    bounds = None
    if bounds_dict:
        bounds = Bounds(
            x=bounds_dict.get("x", 0),
            y=bounds_dict.get("y", 0),
            width=bounds_dict.get("width", 0),
            height=bounds_dict.get("height", 0),
        )
    return WindowInfo(
        id=s["id"],
        title=s["name"],
        app_name=(s.get("app") or {}).get("name") or "",
        pid=(s.get("app") or {}).get("pid"),
        focused="focused" in (s.get("state") or []),
        bounds=bounds,
    )


def _process_name_for_pid(kernel32: Any, pid: int) -> str:
    if pid <= 0:
        return "unknown"
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return f"pid-{pid}"
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(handle)
        full_path = buf.value
        if full_path:
            import os
            return os.path.splitext(os.path.basename(full_path))[0]
        return f"pid-{pid}"
    except Exception:
        return f"pid-{pid}"
