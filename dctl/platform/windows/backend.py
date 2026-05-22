"""
Windows backend — unified facade over UIA, Win32, SendInput, and GDI.

This class mirrors the public interface of MacOSBackend so that
DesktopManager can call it without platform-specific branching
(except for the initial dispatch).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from dctl.errors import DctlError
from dctl.models import Bounds
from dctl.selector import match_selector, parse_selector


@dataclass(slots=True)
class WindowsSearchMatch:
    kind: str           # "accessible" | "window"
    serialized: dict[str, Any]
    raw: Any            # UIARecord | Win32WindowRecord


class WindowsBackend:
    """
    Unified Windows desktop backend.

    Providers are lazily initialised so that import errors on non-Windows
    platforms only surface if the backend is actually used.
    """

    def __init__(self, env: Any) -> None:
        self.env = env
        self._uia_provider: Any | None = None
        self._win32_provider: Any | None = None
        self._input_provider: Any | None = None
        self._capture_provider: Any | None = None
        self._launch_provider: Any | None = None

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        from dctl.capabilities import collect_capabilities
        return collect_capabilities(self.env)

    def doctor(self) -> dict[str, Any]:
        from dctl.doctor import build_doctor_report
        return build_doctor_report(self.capabilities())

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_apps(self) -> list[dict[str, Any]]:
        if self._has_uia():
            return [a.to_dict() for a in self._uia().list_apps()]
        if self._has_win32():
            return self._win32().list_apps()
        raise DctlError("CAPABILITY_UNAVAILABLE", "No Windows app enumeration backend is available.")

    def list_windows(self) -> list[dict[str, Any]]:
        if self._has_win32():
            return [w.to_dict() for w in self._win32().list_windows()]
        if self._has_uia():
            return [w.to_dict() for w in self._uia().list_windows()]
        raise DctlError("CAPABILITY_UNAVAILABLE", "No Windows window enumeration backend is available.")

    def list_launchable(self) -> list[dict[str, Any]]:
        return self._launcher().list_launchable()

    # ------------------------------------------------------------------
    # Launching
    # ------------------------------------------------------------------

    def launch(self, target: str) -> dict[str, Any]:
        return self._launcher().launch(target)

    def open_target(self, target: str) -> dict[str, Any]:
        return self._launcher().open_target(target)

    # ------------------------------------------------------------------
    # Semantic querying
    # ------------------------------------------------------------------

    def tree(self, app_name: str | None = None, depth: int = 5) -> dict[str, Any]:
        if not self._has_uia():
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "UIAutomation is required for accessibility tree dumping on Windows.",
                suggestion="Install comtypes (`pip install comtypes`) and rerun `dctl doctor`.",
            )
        return {"items": self._uia().get_tree(app_name=app_name, depth=depth)}

    def element(self, selector_text: str) -> dict[str, Any]:
        matches = [m.serialized for m in self._search(selector_text)]
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
                suggestion="Run `dctl tree` or `dctl list-windows` for more context.",
            )
        return {"matches": matches}

    def read(self, selector_text: str) -> dict[str, Any]:
        match = self._resolve_single(selector_text)
        s = match.serialized
        return {
            "locator": s["locator"],
            "name": s["name"],
            "role": s["role"],
            "text": s.get("text"),
            "value": s.get("value"),
            "description": s.get("description"),
            "state": s.get("state"),
            "bounds": s.get("bounds"),
        }

    def describe(self, x: int, y: int) -> dict[str, Any]:
        if self._has_uia():
            try:
                return self._uia().element_at(x, y)
            except DctlError:
                pass
        if self._has_win32():
            return self._win32().element_at(x, y)
        raise DctlError("CAPABILITY_UNAVAILABLE", "No describe backend is available on Windows.")

    def wait(self, selector_text: str, timeout: float, interval_ms: int = 250) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = self._search(selector_text)
            if matches:
                return {"matched": True, "match": matches[0].serialized}
            time.sleep(max(interval_ms, 50) / 1000)
        raise DctlError(
            "TIMEOUT",
            f"Timed out waiting for selector '{selector_text}'.",
            suggestion="Increase the timeout or re-check the selector.",
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def focus(self, selector_text: str) -> dict[str, Any]:
        if self._is_coordinate_selector(selector_text):
            return self._coordinate_click(selector_text, focus_only=True)
        match = self._resolve_single(selector_text)
        if match.kind == "accessible":
            try:
                return self._uia().focus(match.raw)
            except DctlError:
                pass
        if match.kind == "window" and self._has_win32():
            return self._win32().focus_window(match.raw.hwnd)
        return self._click_center(match.serialized, focus_only=True)

    def click(self, selector_text: str, button: str = "left", double: bool = False) -> dict[str, Any]:
        if self._is_coordinate_selector(selector_text):
            return self._coordinate_click(selector_text, button=button, double=double)
        match = self._resolve_single(selector_text)
        if match.kind == "accessible":
            try:
                return self._uia().click(match.raw)
            except DctlError:
                pass
        return self._click_center(match.serialized, button=button, double=double)

    def type_text(self, text: str, selector_text: str | None = None) -> dict[str, Any]:
        if selector_text:
            if self._is_coordinate_selector(selector_text):
                self._coordinate_click(selector_text, focus_only=True)
            else:
                match = self._resolve_single(selector_text)
                if match.kind == "accessible":
                    try:
                        return self._uia().set_text(match.raw, text)
                    except DctlError:
                        self._click_center(match.serialized, focus_only=True)
                else:
                    self.focus(selector_text)
        self._input().type_text(text)
        return {"text": text, "backend": "sendinput"}

    def press_key(self, combo: str) -> dict[str, Any]:
        self._input().press_key(combo)
        return {"combo": combo, "backend": "sendinput"}

    def scroll(self, direction: str, amount: int = 1) -> dict[str, Any]:
        self._input().scroll(direction, amount)
        return {"direction": direction, "amount": amount, "backend": "sendinput"}

    def screenshot(
        self,
        *,
        screen: int | None = None,
        window: str | None = None,
        region: str | None = None,
        output_path: str | None = None,
        as_base64: bool = False,
    ) -> dict[str, Any]:
        hwnd = None
        if window:
            hwnd = self._resolve_hwnd(window)
        if screen is not None:
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "Explicit screen selection is not yet implemented for the Windows GDI capture backend.",
            )
        return self._capture().screenshot(
            hwnd=hwnd,
            region=region,
            output_path=output_path,
            as_base64=as_base64,
        )

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    def _search(self, selector_text: str) -> list[WindowsSearchMatch]:
        selector = parse_selector(selector_text)
        matches: list[WindowsSearchMatch] = []
        seen: set[str] = set()

        # Window-level results first (Win32 is always available on Windows)
        if self._has_win32():
            for record in self._win32().find_elements(selector):
                key = record.serialized["locator"] or record.serialized["id"]
                if key not in seen:
                    seen.add(key)
                    matches.append(WindowsSearchMatch(kind="window", serialized=record.serialized, raw=record))

        # Semantic UIA results
        if self._has_uia():
            for record in self._uia().find_elements(selector):
                key = record.serialized["locator"] or record.serialized["id"]
                if key not in seen:
                    seen.add(key)
                    matches.append(WindowsSearchMatch(kind="accessible", serialized=record.serialized, raw=record))

        return matches

    def _resolve_single(self, selector_text: str) -> WindowsSearchMatch:
        matches = self._search(selector_text)
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
                suggestion="Run `dctl tree` or `dctl list-windows` to gather more context.",
            )
        if len(matches) > 1:
            raise DctlError(
                "MULTIPLE_MATCHES",
                f"Selector '{selector_text}' matched multiple elements.",
                suggestion="Add app, window, role, or name terms to narrow the selector.",
                details={"candidates": [m.serialized for m in matches[:20]]},
            )
        return matches[0]

    def _coordinate_click(self, selector_text: str, focus_only: bool = False, button: str = "left", double: bool = False) -> dict[str, Any]:
        selector = parse_selector(selector_text)
        coords = [t for g in selector.groups for t in g if t.kind == "coords"]
        if not coords:
            raise DctlError("INVALID_SELECTOR", f"No coordinates found in selector '{selector_text}'.")
        x, y = coords[0].value
        self._input().mouse_move(x, y)
        if not focus_only:
            self._input().mouse_click(x, y, button=button, double=double)
        return {"x": x, "y": y, "backend": "sendinput", "button": button, "double": double, "focus_only": focus_only}

    def _click_center(self, element: dict[str, Any], focus_only: bool = False, button: str = "left", double: bool = False) -> dict[str, Any]:
        bounds = element.get("bounds")
        if not bounds:
            raise DctlError(
                "ACTION_NOT_SUPPORTED",
                "Element has no bounds for coordinate fallback.",
            )
        x = bounds["x"] + bounds["width"] // 2
        y = bounds["y"] + bounds["height"] // 2
        return self._coordinate_click(f"@{x},{y}", focus_only=focus_only, button=button, double=double)

    def _resolve_hwnd(self, window: str) -> int:
        if window.isdigit():
            return int(window)
        match = self._resolve_single(window)
        if match.kind == "window":
            return match.raw.hwnd
        bounds = match.serialized.get("bounds")
        if bounds:
            from dctl.platform.windows.windowing_win32 import Win32WindowProvider
            wp = self._win32()
            for rec in wp._iter_windows():
                r = rec.serialized.get("bounds") or {}
                if r.get("x") == bounds["x"] and r.get("y") == bounds["y"]:
                    return rec.hwnd
        raise DctlError("ELEMENT_NOT_FOUND", f"Could not resolve a Windows HWND from '{window}'.")

    def _is_coordinate_selector(self, s: str) -> bool:
        return s.strip().startswith("@")

    # ------------------------------------------------------------------
    # Lazy provider accessors
    # ------------------------------------------------------------------

    def _has_uia(self) -> bool:
        try:
            self._uia()
            return True
        except DctlError:
            return False

    def _has_win32(self) -> bool:
        try:
            self._win32()
            return True
        except DctlError:
            return False

    def _uia(self) -> Any:
        if self._uia_provider is None:
            from dctl.platform.windows.accessibility_uia import WindowsUIAProvider
            self._uia_provider = WindowsUIAProvider()
        return self._uia_provider

    def _win32(self) -> Any:
        if self._win32_provider is None:
            from dctl.platform.windows.windowing_win32 import Win32WindowProvider
            self._win32_provider = Win32WindowProvider()
        return self._win32_provider

    def _input(self) -> Any:
        if self._input_provider is None:
            from dctl.platform.windows.input_sendinput import Win32InputProvider
            self._input_provider = Win32InputProvider()
        return self._input_provider

    def _capture(self) -> Any:
        if self._capture_provider is None:
            from dctl.platform.windows.capture_gdi import Win32CaptureProvider
            self._capture_provider = Win32CaptureProvider()
        return self._capture_provider

    def _launcher(self) -> Any:
        if self._launch_provider is None:
            from dctl.platform.windows.launch import Win32LaunchProvider
            self._launch_provider = Win32LaunchProvider()
        return self._launch_provider
