from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time
from typing import Any

from dctl.errors import DctlError
from dctl.locator import build_locator
from dctl.models import AppInfo, Bounds, WindowInfo
from dctl.selector import match_selector, parse_selector


@dataclass(slots=True)
class MacSearchMatch:
    kind: str
    serialized: dict[str, Any]
    raw: Any


class MacOSBackend:
    def __init__(self, env: Any) -> None:
        self.env = env
        self.Quartz, self.AS, self.AppKit = self._load_frameworks()

    def list_apps(self) -> list[dict[str, Any]]:
        windows_by_pid: dict[int, list[WindowInfo]] = {}
        for window in self._list_windows_raw():
            windows_by_pid.setdefault(window.pid or -1, []).append(window)

        apps: list[AppInfo] = []
        workspace = self.AppKit.NSWorkspace.sharedWorkspace()
        running = workspace.runningApplications()
        for app in running:
            pid = int(app.processIdentifier())
            name = str(app.localizedName() or "")
            if not name:
                continue
            windows = windows_by_pid.get(pid, [])
            bundle_id = str(app.bundleIdentifier() or "") or None
            apps.append(AppInfo(name=name, pid=pid, id=bundle_id, windows=windows))
        return [app.to_dict() for app in sorted(apps, key=lambda item: (item.name.lower(), item.pid or -1))]

    def list_windows(self) -> list[dict[str, Any]]:
        return [window.to_dict() for window in self._list_windows_raw()]

    def list_launchable(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for app_path in self._app_bundle_paths():
            info = self._bundle_info(app_path)
            items.append(info)
        return items

    def launch(self, target: str) -> dict[str, Any]:
        if not target.strip():
            raise DctlError("INVALID_SELECTOR", "Launch target cannot be empty.")

        path = Path(os.path.expanduser(target))
        if path.exists():
            return self.open_target(str(path))

        if target.startswith(("http://", "https://")):
            return self.open_target(target)

        matched = self._match_launchable(target)
        if matched is None:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No macOS application matching '{target}' was found.",
                suggestion="Run `dctl list-launchable` to inspect available applications.",
            )

        cmd = [self.env.helpers["open"], "-a", matched["path"]]
        self._run_process(cmd)
        return {"launched": matched, "command": cmd}

    def open_target(self, target: str) -> dict[str, Any]:
        if not self.env.helpers.get("open"):
            raise DctlError(
                "DEPENDENCY_MISSING",
                "`open` is not available on this macOS installation.",
            )
        cmd = [self.env.helpers["open"], target]
        self._run_process(cmd)
        return {"opened": target}

    def tree(self, app_name: str | None = None, depth: int = 5) -> dict[str, Any]:
        self._require_accessibility()
        roots: list[dict[str, Any]] = []
        for app in self._running_apps():
            if app_name and app_name.lower() not in app["name"].lower():
                continue
            element = self.AS.AXUIElementCreateApplication(app["pid"])
            roots.append(self._serialize_element(element, app, None, "/application", depth))
        return {"items": roots}

    def element(self, selector_text: str) -> dict[str, Any]:
        matches = [match.serialized for match in self._search(selector_text)]
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
                suggestion="Run `dctl tree` or `dctl list-windows` to gather more context.",
            )
        return {"matches": matches}

    def read(self, selector_text: str) -> dict[str, Any]:
        match = self._resolve_single(selector_text)
        return {
            "locator": match.serialized["locator"],
            "name": match.serialized["name"],
            "role": match.serialized["role"],
            "text": match.serialized.get("text"),
            "value": match.serialized.get("value"),
            "description": match.serialized.get("description"),
            "state": match.serialized.get("state"),
            "bounds": match.serialized.get("bounds"),
        }

    def focus(self, selector_text: str) -> dict[str, Any]:
        if selector_text.strip().startswith("@"):
            return self._coordinate_click(selector_text, focus_only=True)
        match = self._resolve_single(selector_text)
        if match.kind == "window":
            return self._focus_window(match.raw["pid"], match.raw["window_id"])
        if self._perform_action(match.raw, self.AS.kAXPressAction):
            return {"locator": match.serialized["locator"], "focused": True, "backend": "ax"}
        if self._set_bool_attr(match.raw, self.AS.kAXFocusedAttribute, True):
            return {"locator": match.serialized["locator"], "focused": True, "backend": "ax"}
        return self._click_serialized(match.serialized, focus_only=True)

    def click(self, selector_text: str) -> dict[str, Any]:
        if selector_text.strip().startswith("@"):
            return self._coordinate_click(selector_text)
        match = self._resolve_single(selector_text)
        if match.kind == "window":
            self._focus_window(match.raw["pid"], match.raw["window_id"])
            return self._click_serialized(match.serialized)
        for action in (self.AS.kAXPressAction, self.AS.kAXConfirmAction, self.AS.kAXPickAction):
            if self._perform_action(match.raw, action):
                return {"locator": match.serialized["locator"], "action": str(action), "backend": "ax"}
        return self._click_serialized(match.serialized)

    def type_text(self, text: str, selector_text: str | None = None) -> dict[str, Any]:
        if selector_text:
            match = self._resolve_single(selector_text)
            if match.kind == "element":
                if self._set_attr(match.raw, self.AS.kAXValueAttribute, text):
                    return {"locator": match.serialized["locator"], "method": "set_value"}
                self.focus(selector_text)
            else:
                self.focus(selector_text)
        self._post_text(text)
        return {"text": text, "backend": "quartz"}

    def press_key(self, combo: str) -> dict[str, Any]:
        tokens = [token.strip() for token in combo.replace("-", "+").split("+") if token.strip()]
        if not tokens:
            raise DctlError("INVALID_SELECTOR", "Key combo cannot be empty.")
        modifiers, key_token = tokens[:-1], tokens[-1]
        flags = self._modifier_flags(modifiers)
        keycode = self._keycode_for_token(key_token)
        self._post_key_event(keycode, True, flags)
        self._post_key_event(keycode, False, flags)
        return {"combo": combo, "backend": "quartz"}

    def scroll(self, direction: str, amount: int = 1) -> dict[str, Any]:
        normalized = direction.strip().lower()
        delta = {"up": 1, "down": -1, "left": -1, "right": 1}.get(normalized)
        if delta is None:
            raise DctlError("INVALID_SELECTOR", f"Unsupported scroll direction '{direction}'.")
        event = self.Quartz.CGEventCreateScrollWheelEvent(None, self.Quartz.kCGScrollEventUnitLine, 2, delta * amount, 0)
        if normalized in {"left", "right"}:
            event = self.Quartz.CGEventCreateScrollWheelEvent(None, self.Quartz.kCGScrollEventUnitLine, 2, 0, delta * amount)
        self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, event)
        return {"direction": normalized, "amount": amount, "backend": "quartz"}

    def screenshot(
        self,
        *,
        screen: int | None = None,
        window: str | None = None,
        region: str | None = None,
        output_path: str | None = None,
        as_base64: bool = False,
    ) -> dict[str, Any]:
        if not self.env.helpers.get("screencapture"):
            raise DctlError(
                "DEPENDENCY_MISSING",
                "`screencapture` is not available.",
            )
        fd, temp_path = tempfile.mkstemp(prefix="dctl-macos-", suffix=".png")
        os.close(fd)
        target_path = Path(output_path) if output_path else Path(temp_path)

        if screen is not None:
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "Explicit screen selection is not implemented for the current macOS backend.",
            )

        cmd = [self.env.helpers["screencapture"], "-x"]
        if region:
            x, y, width, height = self._parse_region(region)
            cmd.extend(["-R", f"{x},{y},{width},{height}"])
        elif window:
            window_id = self._resolve_window_id(window)
            cmd.extend(["-l", str(window_id)])
        cmd.append(str(target_path))
        self._run_process(cmd)

        result = {"path": str(target_path), "backend": "screencapture", "window": window}
        if region:
            result["region"] = region
        if as_base64:
            result["base64"] = base64.b64encode(target_path.read_bytes()).decode("ascii")
        return result

    def describe(self, x: int, y: int) -> dict[str, Any]:
        if self._is_trusted():
            system = self.AS.AXUIElementCreateSystemWide()
            result = self.AS.AXUIElementCopyElementAtPosition(system, float(x), float(y), None)
            error, element = self._unpack(result)
            if error == self.AS.kAXErrorSuccess and element is not None:
                app = self._app_context_for_element(element)
                return self._serialize_element(element, app, None, "/element", 0)

        for window in reversed(self._list_windows_raw()):
            if window.bounds and window.bounds.x <= x <= window.bounds.x + window.bounds.width and window.bounds.y <= y <= window.bounds.y + window.bounds.height:
                return self._window_to_dict(window)
        raise DctlError("ELEMENT_NOT_FOUND", f"No window or accessible element found at {x},{y}.")

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

    def _search(self, selector_text: str) -> list[MacSearchMatch]:
        selector = parse_selector(selector_text)
        matches: list[MacSearchMatch] = []
        seen: set[str] = set()

        for window in self._list_windows_raw():
            serialized = self._window_to_dict(window)
            key = serialized["locator"]
            if key not in seen and match_selector(serialized, selector):
                matches.append(MacSearchMatch(kind="window", serialized=serialized, raw={"pid": window.pid, "window_id": window.id}))
                seen.add(key)

        if self._is_trusted():
            for app in self._running_apps():
                element = self.AS.AXUIElementCreateApplication(app["pid"])
                matches.extend(self._search_accessible(element, selector, app, None, "/application", seen))

        return matches

    def _search_accessible(
        self,
        element: Any,
        selector: Any,
        app: dict[str, Any],
        window_title: str | None,
        path: str,
        seen: set[str],
    ) -> list[MacSearchMatch]:
        current = self._serialize_element(element, app, window_title, path, 0)
        next_window_title = current["name"] if current["role"] == "window" and current["name"] else window_title
        matches: list[MacSearchMatch] = []
        key = current["locator"] or current["id"]
        if key not in seen and match_selector(current, selector):
            matches.append(MacSearchMatch(kind="element", serialized=current, raw=element))
            seen.add(key)

        for index, child in enumerate(self._children(element)):
            child_path = f"{path}/{self._normalize_role(self._copy_attr(child, self.AS.kAXRoleAttribute, 'unknown'))}[{index}]"
            matches.extend(self._search_accessible(child, selector, app, next_window_title, child_path, seen))
        return matches

    def _resolve_single(self, selector_text: str) -> MacSearchMatch:
        matches = self._search(selector_text)
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
            )
        if len(matches) > 1:
            raise DctlError(
                "MULTIPLE_MATCHES",
                f"Selector '{selector_text}' matched multiple elements.",
                details={"candidates": [match.serialized for match in matches[:20]]},
            )
        return matches[0]

    def _list_windows_raw(self) -> list[WindowInfo]:
        infos = self.Quartz.CGWindowListCopyWindowInfo(
            self.Quartz.kCGWindowListOptionOnScreenOnly | self.Quartz.kCGWindowListExcludeDesktopElements,
            self.Quartz.kCGNullWindowID,
        ) or []
        windows: list[WindowInfo] = []
        front_pid = self._frontmost_pid()
        for item in infos:
            owner = str(item.get(self.Quartz.kCGWindowOwnerName, "") or "")
            pid = item.get(self.Quartz.kCGWindowOwnerPID)
            title = str(item.get(self.Quartz.kCGWindowName, "") or owner)
            layer = int(item.get(self.Quartz.kCGWindowLayer, 0))
            if layer != 0 or not owner:
                continue
            bounds = item.get(self.Quartz.kCGWindowBounds, {}) or {}
            windows.append(
                WindowInfo(
                    id=str(item.get(self.Quartz.kCGWindowNumber)),
                    title=title,
                    app_name=owner,
                    pid=int(pid) if pid is not None else None,
                    focused=int(pid) == front_pid if pid is not None else False,
                    bounds=Bounds(
                        x=int(bounds.get("X", 0)),
                        y=int(bounds.get("Y", 0)),
                        width=int(bounds.get("Width", 0)),
                        height=int(bounds.get("Height", 0)),
                    ),
                )
            )
        return windows

    def _window_to_dict(self, window: WindowInfo) -> dict[str, Any]:
        path = f"/window[{window.id}]"
        locator = build_locator(app_name=window.app_name, window_title=window.title, path=path)
        state = ["visible"]
        if window.focused:
            state.append("focused")
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

    def _running_apps(self) -> list[dict[str, Any]]:
        workspace = self.AppKit.NSWorkspace.sharedWorkspace()
        running = workspace.runningApplications()
        apps: list[dict[str, Any]] = []
        for app in running:
            pid = int(app.processIdentifier())
            name = str(app.localizedName() or "")
            if not name:
                continue
            apps.append({"pid": pid, "name": name, "bundle_id": str(app.bundleIdentifier() or "") or None})
        return apps

    def _serialize_element(
        self,
        element: Any,
        app: dict[str, Any],
        window_title: str | None,
        path: str,
        depth: int,
    ) -> dict[str, Any]:
        role = self._copy_attr(element, self.AS.kAXRoleAttribute, "unknown")
        role_name = self._normalize_role(role)
        title = self._copy_attr(element, self.AS.kAXTitleAttribute) or self._copy_attr(element, self.AS.kAXDescriptionAttribute) or ""
        description = self._copy_attr(element, self.AS.kAXDescriptionAttribute)
        value = self._copy_attr(element, self.AS.kAXValueAttribute)
        actions = [str(action).lower() for action in (self._copy_actions(element) or [])]
        state = self._state_for_element(element)
        bounds = self._bounds_for_element(element)
        next_window_title = title if role_name == "window" and title else window_title
        locator = build_locator(app_name=app["name"], window_title=next_window_title, path=path)
        serialized = {
            "id": f"ax:{app['pid']}:{path}",
            "locator": locator,
            "role": role_name,
            "name": title,
            "description": description,
            "value": self._safe_string(value),
            "text": self._safe_string(value) if isinstance(value, (str, bytes)) else title,
            "state": state,
            "actions": actions,
            "bounds": bounds,
            "path": path,
            "app": {"name": app["name"], "pid": app["pid"]},
            "window": {"title": next_window_title, "id": f"window:{next_window_title}"} if next_window_title else None,
            "children": [],
        }

        if depth > 0:
            for index, child in enumerate(self._children(element)):
                child_role = self._normalize_role(self._copy_attr(child, self.AS.kAXRoleAttribute, "unknown"))
                child_path = f"{path}/{child_role}[{index}]"
                serialized["children"].append(self._serialize_element(child, app, next_window_title, child_path, depth - 1))
        return serialized

    def _children(self, element: Any) -> list[Any]:
        children = self._copy_attr(element, self.AS.kAXChildrenAttribute, [])
        return list(children or [])

    def _copy_attr(self, element: Any, attr: Any, default: Any = None) -> Any:
        try:
            result = self.AS.AXUIElementCopyAttributeValue(element, attr, None)
        except Exception:
            return default
        error, value = self._unpack(result)
        if error != self.AS.kAXErrorSuccess:
            return default
        return value

    def _copy_actions(self, element: Any) -> list[Any]:
        try:
            result = self.AS.AXUIElementCopyActionNames(element, None)
        except Exception:
            return []
        error, value = self._unpack(result)
        if error != self.AS.kAXErrorSuccess:
            return []
        return list(value or [])

    def _perform_action(self, element: Any, action: Any) -> bool:
        try:
            return self.AS.AXUIElementPerformAction(element, action) == self.AS.kAXErrorSuccess
        except Exception:
            return False

    def _set_attr(self, element: Any, attr: Any, value: Any) -> bool:
        try:
            return self.AS.AXUIElementSetAttributeValue(element, attr, value) == self.AS.kAXErrorSuccess
        except Exception:
            return False

    def _set_bool_attr(self, element: Any, attr: Any, value: bool) -> bool:
        return self._set_attr(element, attr, value)

    def _state_for_element(self, element: Any) -> list[str]:
        state: list[str] = []
        if self._copy_attr(element, self.AS.kAXEnabledAttribute, False):
            state.append("enabled")
        if self._copy_attr(element, self.AS.kAXFocusedAttribute, False):
            state.append("focused")
        if self._copy_attr(element, self.AS.kAXMainAttribute, False):
            state.append("main")
        if self._copy_attr(element, self.AS.kAXVisibleAttribute, True):
            state.append("visible")
        return state

    def _bounds_for_element(self, element: Any) -> dict[str, int] | None:
        position = self._copy_attr(element, self.AS.kAXPositionAttribute)
        size = self._copy_attr(element, self.AS.kAXSizeAttribute)
        point = self._point_from_ax_value(position)
        extent = self._size_from_ax_value(size)
        if point is None or extent is None:
            return None
        return {"x": int(point[0]), "y": int(point[1]), "width": int(extent[0]), "height": int(extent[1])}

    def _point_from_ax_value(self, value: Any) -> tuple[float, float] | None:
        if value is None:
            return None
        if hasattr(value, "pointValue"):
            point = value.pointValue()
            return float(point.x), float(point.y)
        if hasattr(value, "x") and hasattr(value, "y"):
            return float(value.x), float(value.y)
        return None

    def _size_from_ax_value(self, value: Any) -> tuple[float, float] | None:
        if value is None:
            return None
        if hasattr(value, "sizeValue"):
            size = value.sizeValue()
            return float(size.width), float(size.height)
        if hasattr(value, "width") and hasattr(value, "height"):
            return float(value.width), float(value.height)
        return None

    def _focus_window(self, pid: int | None, window_id: str | None) -> dict[str, Any]:
        if pid is None:
            raise DctlError("ACTION_NOT_SUPPORTED", "Window does not have a PID for focusing.")
        app = self.AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is not None:
            app.activateWithOptions_(self.AppKit.NSApplicationActivateIgnoringOtherApps)
            return {"focused": True, "pid": pid, "window_id": window_id, "backend": "appkit"}
        raise DctlError("ACTION_NOT_SUPPORTED", "Could not activate the target application.")

    def _coordinate_click(self, selector_text: str, focus_only: bool = False) -> dict[str, Any]:
        selector = parse_selector(selector_text)
        coords_terms = [
            term
            for group in selector.groups
            for term in group
            if term.kind == "coords"
        ]
        if not coords_terms:
            raise DctlError("INVALID_SELECTOR", f"Selector '{selector_text}' did not contain coordinates.")
        x, y = coords_terms[0].value
        point = (float(x), float(y))
        move = self.Quartz.CGEventCreateMouseEvent(None, self.Quartz.kCGEventMouseMoved, point, self.Quartz.kCGMouseButtonLeft)
        self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, move)
        if not focus_only:
            down = self.Quartz.CGEventCreateMouseEvent(None, self.Quartz.kCGEventLeftMouseDown, point, self.Quartz.kCGMouseButtonLeft)
            up = self.Quartz.CGEventCreateMouseEvent(None, self.Quartz.kCGEventLeftMouseUp, point, self.Quartz.kCGMouseButtonLeft)
            self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, down)
            self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, up)
        return {"x": x, "y": y, "backend": "quartz", "focus_only": focus_only}

    def _click_serialized(self, element: dict[str, Any], focus_only: bool = False) -> dict[str, Any]:
        bounds = element.get("bounds")
        if not bounds:
            raise DctlError("ACTION_NOT_SUPPORTED", "Element does not expose bounds for coordinate fallback.")
        x = bounds["x"] + bounds["width"] // 2
        y = bounds["y"] + bounds["height"] // 2
        return self._coordinate_click(f"@{x},{y}", focus_only=focus_only)

    def _post_text(self, text: str) -> None:
        source = self.Quartz.CGEventSourceCreate(self.Quartz.kCGEventSourceStateHIDSystemState)
        down = self.Quartz.CGEventCreateKeyboardEvent(source, 0, True)
        up = self.Quartz.CGEventCreateKeyboardEvent(source, 0, False)
        self.Quartz.CGEventKeyboardSetUnicodeString(down, len(text), text)
        self.Quartz.CGEventKeyboardSetUnicodeString(up, len(text), text)
        self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, down)
        self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, up)

    def _post_key_event(self, keycode: int, key_down: bool, flags: Any) -> None:
        source = self.Quartz.CGEventSourceCreate(self.Quartz.kCGEventSourceStateHIDSystemState)
        event = self.Quartz.CGEventCreateKeyboardEvent(source, keycode, key_down)
        self.Quartz.CGEventSetFlags(event, flags)
        self.Quartz.CGEventPost(self.Quartz.kCGHIDEventTap, event)

    def _modifier_flags(self, modifiers: list[str]) -> Any:
        flags = self.Quartz.CGEventFlags(0)
        mapping = {
            "shift": self.Quartz.kCGEventFlagMaskShift,
            "ctrl": self.Quartz.kCGEventFlagMaskControl,
            "control": self.Quartz.kCGEventFlagMaskControl,
            "alt": self.Quartz.kCGEventFlagMaskAlternate,
            "option": self.Quartz.kCGEventFlagMaskAlternate,
            "cmd": self.Quartz.kCGEventFlagMaskCommand,
            "command": self.Quartz.kCGEventFlagMaskCommand,
            "meta": self.Quartz.kCGEventFlagMaskCommand,
        }
        for token in modifiers:
            flag = mapping.get(token.lower())
            if flag:
                flags |= flag
        return flags

    def _keycode_for_token(self, token: str) -> int:
        lower = token.lower()
        mapping = {
            "a": 0,
            "s": 1,
            "d": 2,
            "f": 3,
            "h": 4,
            "g": 5,
            "z": 6,
            "x": 7,
            "c": 8,
            "v": 9,
            "b": 11,
            "q": 12,
            "w": 13,
            "e": 14,
            "r": 15,
            "y": 16,
            "t": 17,
            "1": 18,
            "2": 19,
            "3": 20,
            "4": 21,
            "6": 22,
            "5": 23,
            "=": 24,
            "9": 25,
            "7": 26,
            "-": 27,
            "8": 28,
            "0": 29,
            "]": 30,
            "o": 31,
            "u": 32,
            "[": 33,
            "i": 34,
            "p": 35,
            "enter": 36,
            "return": 36,
            "l": 37,
            "j": 38,
            "'": 39,
            "k": 40,
            ";": 41,
            "\\": 42,
            ",": 43,
            "/": 44,
            "n": 45,
            "m": 46,
            ".": 47,
            "tab": 48,
            "space": 49,
            "`": 50,
            "backspace": 51,
            "delete": 51,
            "esc": 53,
            "escape": 53,
            "command": 55,
            "shift": 56,
            "capslock": 57,
            "option": 58,
            "alt": 58,
            "control": 59,
            "ctrl": 59,
            "rightshift": 60,
            "rightoption": 61,
            "rightcontrol": 62,
            "fn": 63,
            "f17": 64,
            "volumeup": 72,
            "volumedown": 73,
            "mute": 74,
            "f18": 79,
            "f19": 80,
            "f20": 90,
            "f5": 96,
            "f6": 97,
            "f7": 98,
            "f3": 99,
            "f8": 100,
            "f9": 101,
            "f11": 103,
            "f13": 105,
            "f16": 106,
            "f14": 107,
            "f10": 109,
            "f12": 111,
            "f15": 113,
            "help": 114,
            "home": 115,
            "pageup": 116,
            "forwarddelete": 117,
            "f4": 118,
            "end": 119,
            "f2": 120,
            "pagedown": 121,
            "f1": 122,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
        }
        if lower in mapping:
            return mapping[lower]
        raise DctlError("INVALID_SELECTOR", f"Unsupported macOS key token '{token}'.")

    def _frontmost_pid(self) -> int | None:
        workspace = self.AppKit.NSWorkspace.sharedWorkspace()
        front = workspace.frontmostApplication()
        if front is None:
            return None
        return int(front.processIdentifier())

    def _resolve_window_id(self, target: str) -> str:
        if target.isdigit():
            return target
        match = self._resolve_single(target)
        if match.kind == "window":
            return match.raw["window_id"]
        window = match.serialized.get("window") or {}
        if window.get("id"):
            return str(window["id"])
        raise DctlError("ELEMENT_NOT_FOUND", f"Could not resolve a macOS window ID from '{target}'.")

    def _parse_region(self, geometry: str) -> tuple[int, int, int, int]:
        parts = [part.strip() for part in geometry.split(",")]
        if len(parts) != 4:
            raise DctlError("INVALID_SELECTOR", f"Invalid region '{geometry}'. Expected X,Y,W,H.")
        try:
            return tuple(int(part) for part in parts)  # type: ignore[return-value]
        except ValueError as exc:
            raise DctlError("INVALID_SELECTOR", f"Invalid region '{geometry}'. Expected integer X,Y,W,H.") from exc

    def _app_bundle_paths(self) -> list[Path]:
        roots = [
            Path("/Applications"),
            Path("/System/Applications"),
            Path.home() / "Applications",
        ]
        bundles: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            bundles.extend(sorted(root.glob("*.app")))
        return bundles

    def _bundle_info(self, app_path: Path) -> dict[str, Any]:
        info_plist = app_path / "Contents" / "Info.plist"
        bundle_id = None
        display_name = app_path.stem
        if info_plist.exists():
            try:
                data = plistlib.loads(info_plist.read_bytes())
                bundle_id = data.get("CFBundleIdentifier")
                display_name = data.get("CFBundleDisplayName") or data.get("CFBundleName") or display_name
            except Exception:
                pass
        return {
            "id": bundle_id or app_path.stem,
            "name": display_name,
            "path": str(app_path),
            "bundle_id": bundle_id,
        }

    def _match_launchable(self, target: str) -> dict[str, Any] | None:
        target_norm = target.strip().lower()
        apps = self.list_launchable()
        for app in apps:
            if target_norm in {str(app.get("id", "")).lower(), str(app.get("bundle_id", "")).lower(), app["name"].lower(), Path(app["path"]).name.lower()}:
                return app
        for app in apps:
            if target_norm in app["name"].lower():
                return app
        return None

    def _is_trusted(self) -> bool:
        try:
            options = {self.AS.kAXTrustedCheckOptionPrompt: False}
            return bool(self.AS.AXIsProcessTrustedWithOptions(options))
        except Exception:
            return bool(self.AS.AXIsProcessTrusted())

    def _require_accessibility(self) -> None:
        if not self._is_trusted():
            raise DctlError(
                "PERMISSION_DENIED",
                "Accessibility permission is required on macOS for semantic UI access.",
                suggestion="Grant Accessibility access, then rerun `dctl doctor`.",
            )

    def _app_context_for_element(self, element: Any) -> dict[str, Any]:
        pid = None
        try:
            pid_ref = self.AS.AXUIElementGetPid(element, None)
            error, pid = self._unpack(pid_ref)
            if error != self.AS.kAXErrorSuccess:
                pid = None
        except Exception:
            pid = None
        if pid is None:
            return {"pid": None, "name": "unknown", "bundle_id": None}
        for app in self._running_apps():
            if app["pid"] == int(pid):
                return app
        return {"pid": int(pid), "name": f"pid-{pid}", "bundle_id": None}

    def _normalize_role(self, role: Any) -> str:
        return str(role or "unknown").replace("AX", "").replace("_", " ").strip().lower() or "unknown"

    def _safe_string(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _unpack(self, result: Any) -> tuple[Any, Any]:
        if isinstance(result, tuple):
            if len(result) == 2:
                return result[0], result[1]
            if len(result) == 1:
                return result[0], None
        return result, None

    def _run_process(self, cmd: list[str]) -> None:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if completed.returncode != 0:
            raise DctlError(
                "BACKEND_FAILURE",
                f"Command failed: {' '.join(cmd)}",
                suggestion=(completed.stderr or completed.stdout).strip() or "macOS helper command failed.",
            )

    def _load_frameworks(self) -> tuple[Any, Any, Any]:
        try:
            import Quartz
            import ApplicationServices as AS
            import AppKit
        except Exception as exc:
            raise DctlError(
                "DEPENDENCY_MISSING",
                "The macOS backend requires PyObjC modules for Quartz, ApplicationServices, and AppKit.",
                suggestion="Install `pyobjc-framework-ApplicationServices`, `pyobjc-framework-Quartz`, and `pyobjc-framework-Cocoa`.",
            ) from exc
        return Quartz, AS, AppKit
