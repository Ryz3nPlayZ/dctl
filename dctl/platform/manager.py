from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
from typing import Any

from dctl.capabilities import collect_capabilities
from dctl.doctor import build_doctor_report
from dctl.errors import DctlError
from dctl.platform.base import DesktopBackend
from dctl.platform.detect import EnvironmentInfo, detect_environment
from dctl.platform.linux.accessibility_atspi import AccessibleRecord, LinuxAtspiProvider
from dctl.platform.linux.input import (
    ydotool_click_args,
    ydotool_key_args,
    ydotool_mousemove_args,
)
from dctl.platform.linux.launch import launch_target, list_launchable, open_target
from dctl.platform.linux.windowing import WindowRecord, XdotoolWindowProvider
from dctl.platform.macos import MacOSBackend
from dctl.selector import parse_selector


@dataclass(slots=True)
class SearchMatch:
    kind: str
    serialized: dict[str, Any]
    raw: AccessibleRecord | WindowRecord


class DesktopManager(DesktopBackend):
    def __init__(self) -> None:
        self.env: EnvironmentInfo = detect_environment()
        self._capabilities = collect_capabilities(self.env)
        self._atspi: LinuxAtspiProvider | None = None
        self._windowing: XdotoolWindowProvider | None = None
        self._macos: MacOSBackend | None = None

    def capabilities(self) -> dict[str, Any]:
        return self._capabilities

    def doctor(self) -> dict[str, Any]:
        return build_doctor_report(self._capabilities)

    def list_apps(self) -> list[dict[str, Any]]:
        if self.env.platform == "darwin":
            return self._macos_backend().list_apps()
        if self._has_accessibility():
            return [app.to_dict() for app in self._accessibility_provider().list_apps()]
        if self._has_windowing():
            return [app.to_dict() for app in self._window_provider().list_apps()]
        raise DctlError("CAPABILITY_UNAVAILABLE", "No app enumeration backend is available.")

    def list_windows(self) -> list[dict[str, Any]]:
        if self.env.platform == "darwin":
            return self._macos_backend().list_windows()
        if self._has_windowing():
            return [window.to_dict() for window in self._window_provider().list_windows()]
        if self._has_accessibility():
            return [window.to_dict() for window in self._accessibility_provider().list_windows()]
        raise DctlError("CAPABILITY_UNAVAILABLE", "No window enumeration backend is available.")

    def list_launchable(self) -> list[dict[str, Any]]:
        if self.env.platform == "darwin":
            return self._macos_backend().list_launchable()
        self._require_linux()
        return list_launchable()

    def launch(self, target: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().launch(target)
        self._require_linux()
        return launch_target(target, self.env.helpers.get("xdg-open"), self.env.helpers.get("gtk-launch"))

    def open_target(self, target: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().open_target(target)
        self._require_linux()
        return open_target(target, self.env.helpers.get("xdg-open"))

    def tree(self, app_name: str | None = None, depth: int = 5) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().tree(app_name=app_name, depth=depth)
        if not self._has_accessibility():
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "Accessibility tree dumping requires the AT-SPI backend.",
                suggestion="Enable accessibility support and rerun `dctl doctor`.",
            )
        return {"items": self._accessibility_provider().get_tree(app_name=app_name, depth=depth)}

    def element(self, selector_text: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().element(selector_text)
        matches = [match.serialized for match in self._search_targets(selector_text)]
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
                suggestion="Run `dctl tree`, `dctl list-windows`, or loosen the selector terms.",
            )
        return {"matches": matches}

    def read(self, selector_text: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().read(selector_text)
        match = self._resolve_single(selector_text)
        if match.kind == "accessible":
            return self._accessibility_provider().read_element(match.raw)
        return self._read_window_match(match)

    def focus(self, selector_text: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().focus(selector_text)
        if self._is_coordinate_selector(selector_text):
            return self._pointer_click(selector_text, focus_only=True)
        match = self._resolve_single(selector_text)
        if match.kind == "accessible":
            try:
                return self._accessibility_provider().focus(match.raw)
            except DctlError:
                return self._click_center(match.serialized, focus_only=True)
        return self._window_provider().focus_window(match.raw.window_id)

    def click(self, selector_text: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().click(selector_text)
        if self._is_coordinate_selector(selector_text):
            return self._pointer_click(selector_text)
        match = self._resolve_single(selector_text)
        if match.kind == "accessible":
            try:
                return self._accessibility_provider().click(match.raw)
            except DctlError:
                return self._click_center(match.serialized)
        self._window_provider().focus_window(match.raw.window_id)
        return self._click_center(match.serialized)

    def type_text(self, text: str, selector_text: str | None = None) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().type_text(text, selector_text)
        if selector_text:
            if self._is_coordinate_selector(selector_text):
                self._pointer_click(selector_text, focus_only=True)
                return self._inject_type(text)
            match = self._resolve_single(selector_text)
            if match.kind == "accessible":
                try:
                    return self._accessibility_provider().set_text(match.raw, text)
                except DctlError:
                    self._click_center(match.serialized, focus_only=True)
                    return self._inject_type(text)
            self._window_provider().focus_window(match.raw.window_id)
        return self._inject_type(text)

    def press_key(self, combo: str) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().press_key(combo)
        helper = self._input_helper()
        if helper == "xdotool":
            self._run_helper([self.env.helpers["xdotool"], "key", combo])
            return {"helper": "xdotool", "combo": combo}
        if helper == "ydotool":
            args = [self.env.helpers["ydotool"], "key", *ydotool_key_args(combo)]
            self._run_helper(args)
            return {"helper": "ydotool", "combo": combo}
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            "No supported key injection helper is available.",
            suggestion="Install and configure xdotool or ydotool.",
        )

    def scroll(self, direction: str, amount: int = 1) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().scroll(direction, amount)
        helper = self._input_helper()
        normalized = direction.strip().lower()
        if helper != "xdotool":
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "Scroll injection currently requires xdotool.",
                suggestion="Use xdotool on X11/XWayland or extend the ydotool button mapping if needed.",
            )
        button = {"up": "4", "down": "5", "left": "6", "right": "7"}.get(normalized)
        if button is None:
            raise DctlError("INVALID_SELECTOR", f"Unsupported scroll direction '{direction}'.")
        for _ in range(max(amount, 1)):
            self._run_helper([self.env.helpers["xdotool"], "click", button])
        return {"helper": "xdotool", "direction": normalized, "amount": max(amount, 1)}

    def screenshot(
        self,
        *,
        screen: int | None = None,
        window: str | None = None,
        region: str | None = None,
        output_path: str | None = None,
        as_base64: bool = False,
    ) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().screenshot(
                screen=screen,
                window=window,
                region=region,
                output_path=output_path,
                as_base64=as_base64,
            )
        self._require_linux()
        if screen is not None:
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "Explicit screen selection is not implemented for the current Linux capture backends.",
            )
        fd, temp_path = tempfile.mkstemp(prefix="dctl-", suffix=".png")
        os.close(fd)
        target_path = Path(output_path) if output_path else Path(temp_path)
        geometry = region

        if window and not geometry:
            bounds = self._resolve_window_bounds(window)
            geometry = f"{bounds.x},{bounds.y} {bounds.width}x{bounds.height}"

        if self.env.helpers.get("grim"):
            try:
                cmd = [self.env.helpers["grim"], str(target_path)]
                if geometry:
                    cmd = [self.env.helpers["grim"], "-g", self._region_for_grim(geometry), str(target_path)]
                self._run_helper(cmd)
                result = {"path": str(target_path), "backend": "grim", "screen": screen, "window": window}
            except DctlError:
                result = self._spectacle_screenshot(target_path, geometry, window)
        elif self.env.helpers.get("spectacle"):
            result = self._spectacle_screenshot(target_path, geometry, window)
        elif self.env.helpers.get("scrot"):
            cmd = [self.env.helpers["scrot"], str(target_path)]
            if geometry:
                region_spec = self._region_for_scrot(geometry)
                cmd = [self.env.helpers["scrot"], "-a", region_spec, str(target_path)]
            self._run_helper(cmd)
            result = {"path": str(target_path), "backend": "scrot", "screen": screen, "window": window}
        else:
            raise DctlError(
                "DEPENDENCY_MISSING",
                "No screenshot helper is installed.",
                suggestion="Install `grim` or `scrot`.",
            )

        if as_base64:
            result["base64"] = base64.b64encode(target_path.read_bytes()).decode("ascii")
        if geometry:
            result["region"] = geometry
        return result

    def describe(self, x: int, y: int) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().describe(x, y)
        if self._has_accessibility():
            try:
                return self._accessibility_provider().element_at(x, y)
            except DctlError:
                pass
        if self._has_windowing():
            return self._window_provider().element_at(x, y)
        raise DctlError("CAPABILITY_UNAVAILABLE", "No describe backend is available.")

    def wait(self, selector_text: str, timeout: float, interval_ms: int = 250) -> dict[str, Any]:
        if self.env.platform == "darwin":
            return self._macos_backend().wait(selector_text, timeout, interval_ms)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = self._search_targets(selector_text)
            if matches:
                return {"matched": True, "match": matches[0].serialized}
            time.sleep(max(interval_ms, 50) / 1000)
        raise DctlError(
            "TIMEOUT",
            f"Timed out waiting for selector '{selector_text}'.",
            suggestion="Increase the timeout or re-check the selector.",
        )

    def _search_targets(self, selector_text: str) -> list[SearchMatch]:
        selector = parse_selector(selector_text)
        matches: list[SearchMatch] = []
        seen: set[str] = set()

        if self._has_accessibility():
            for record in self._accessibility_provider().find_elements(selector):
                key = record.serialized["locator"] or record.serialized["id"]
                if key in seen:
                    continue
                seen.add(key)
                matches.append(SearchMatch(kind="accessible", serialized=record.serialized, raw=record))

        if self._has_windowing():
            for record in self._window_provider().find_elements(selector):
                key = record.serialized["locator"] or record.serialized["id"]
                if key in seen:
                    continue
                seen.add(key)
                matches.append(SearchMatch(kind="window", serialized=record.serialized, raw=record))

        return matches

    def _resolve_single(self, selector_text: str) -> SearchMatch:
        matches = self._search_targets(selector_text)
        if not matches:
            raise DctlError(
                "ELEMENT_NOT_FOUND",
                f"No element matching '{selector_text}' was found.",
                suggestion="Run `dctl tree`, `dctl list-windows`, or loosen the selector terms.",
            )
        if len(matches) > 1:
            raise DctlError(
                "MULTIPLE_MATCHES",
                f"Selector '{selector_text}' matched multiple elements.",
                suggestion="Add app, window, role, name, or path terms to narrow the selector.",
                details={"candidates": [match.serialized for match in matches[:20]]},
            )
        return matches[0]

    def _read_window_match(self, match: SearchMatch) -> dict[str, Any]:
        element = match.serialized
        return {
            "locator": element["locator"],
            "name": element["name"],
            "role": element["role"],
            "text": element.get("text"),
            "value": element.get("value"),
            "description": element.get("description"),
            "state": element.get("state"),
            "bounds": element.get("bounds"),
        }

    def _has_accessibility(self) -> bool:
        return self._capabilities["providers"].get("accessibility") == "atspi"

    def _has_windowing(self) -> bool:
        return self._capabilities["providers"].get("windowing") == "xdotool"

    def _input_helper(self) -> str | None:
        return self._capabilities["providers"].get("input")

    def _is_coordinate_selector(self, selector_text: str) -> bool:
        return selector_text.strip().startswith("@")

    def _pointer_click(self, selector_text: str, focus_only: bool = False) -> dict[str, Any]:
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
        helper = self._input_helper()
        if helper == "xdotool":
            args = [self.env.helpers["xdotool"], "mousemove", str(x), str(y)]
            if not focus_only:
                args.extend(["click", "1"])
            else:
                args.extend(["mousedown", "1", "mouseup", "1"])
            self._run_helper(args)
            return {"helper": "xdotool", "x": x, "y": y, "focus_only": focus_only}
        if helper == "ydotool":
            self._run_helper([self.env.helpers["ydotool"], *ydotool_mousemove_args(x, y)])
            self._run_helper([self.env.helpers["ydotool"], *ydotool_click_args("left")])
            return {"helper": "ydotool", "x": x, "y": y, "focus_only": focus_only}
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            "No pointer injection helper is available.",
            suggestion="Install and configure xdotool or ydotool.",
        )

    def _click_center(self, element: dict[str, Any], focus_only: bool = False) -> dict[str, Any]:
        bounds = element.get("bounds")
        if not bounds:
            raise DctlError(
                "ACTION_NOT_SUPPORTED",
                "Element does not expose a semantic action and has no bounds for coordinate fallback.",
            )
        x = bounds["x"] + bounds["width"] // 2
        y = bounds["y"] + bounds["height"] // 2
        return self._pointer_click(f"@{x},{y}", focus_only=focus_only)

    def _inject_type(self, text: str) -> dict[str, Any]:
        helper = self._input_helper()
        if helper == "xdotool":
            self._run_helper([self.env.helpers["xdotool"], "type", "--delay", "1", "--clearmodifiers", text])
            return {"helper": "xdotool", "text": text}
        if helper == "ydotool":
            self._run_helper([self.env.helpers["ydotool"], "type", "--key-delay", "1", text])
            return {"helper": "ydotool", "text": text}
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            "No supported text injection helper is available.",
            suggestion="Install xdotool or ydotool.",
        )

    def _resolve_window_bounds(self, target: str):
        if self._has_windowing():
            if target.isdigit():
                return self._window_provider().window_bounds(target)
            match = self._resolve_single(target)
            if match.kind == "window":
                return self._window_provider().window_bounds(match.raw.window_id)
            if match.serialized.get("bounds"):
                bounds = match.serialized["bounds"]
                from dctl.models import Bounds
                return Bounds(x=bounds["x"], y=bounds["y"], width=bounds["width"], height=bounds["height"])
        raise DctlError(
            "CAPABILITY_UNAVAILABLE",
            "Resolving a screenshot window requires a windowing backend or an accessible target with bounds.",
        )

    def _geometry_to_scrot_region(self, geometry: str) -> str:
        x, y, width, height = self._parse_region(geometry)
        return f"{x},{y},{width},{height}"

    def _region_for_grim(self, geometry: str) -> str:
        x, y, width, height = self._parse_region(geometry)
        return f"{x},{y} {width}x{height}"

    def _region_for_scrot(self, geometry: str) -> str:
        return self._geometry_to_scrot_region(geometry)

    def _parse_region(self, geometry: str) -> tuple[int, int, int, int]:
        geometry = geometry.strip()
        if " " in geometry and "x" in geometry:
            coords, size = geometry.split(" ", 1)
            x, y = coords.split(",", 1)
            width, height = size.split("x", 1)
        else:
            parts = [part.strip() for part in geometry.split(",")]
            if len(parts) != 4:
                raise DctlError(
                    "INVALID_SELECTOR",
                    f"Invalid region '{geometry}'. Expected X,Y,W,H.",
                )
            x, y, width, height = parts
        try:
            return int(x), int(y), int(width), int(height)
        except ValueError as exc:
            raise DctlError(
                "INVALID_SELECTOR",
                f"Invalid region '{geometry}'. Expected integer X,Y,W,H.",
            ) from exc

    def _spectacle_screenshot(self, target_path: Path, geometry: str | None, window: str | None) -> dict[str, Any]:
        spectacle = self.env.helpers.get("spectacle")
        if not spectacle:
            raise DctlError("DEPENDENCY_MISSING", "Spectacle is not installed.")

        capture_path = target_path
        temp_full_path: Path | None = None
        if geometry:
            fd, temp_name = tempfile.mkstemp(prefix="dctl-spectacle-", suffix=".png")
            os.close(fd)
            temp_full_path = Path(temp_name)
            capture_path = temp_full_path

        cmd = [spectacle, "-b", "-n"]
        if window:
            if window.isdigit() and self._has_windowing():
                self._window_provider().focus_window(window)
            else:
                self.focus(window)
            cmd.extend(["-a", "-o", str(capture_path)])
        else:
            cmd.extend(["-f", "-o", str(capture_path)])
        self._run_helper(cmd)

        if geometry:
            if not self.env.helpers.get("magick"):
                raise DctlError(
                    "DEPENDENCY_MISSING",
                    "Cropping a region from the spectacle fallback requires ImageMagick (`magick` or `convert`).",
                )
            x, y, width, height = self._parse_region(geometry)
            self._run_helper(
                [
                    self.env.helpers["magick"],
                    str(capture_path),
                    "-crop",
                    f"{width}x{height}+{x}+{y}",
                    "+repage",
                    str(target_path),
                ]
            )
            if temp_full_path and temp_full_path.exists():
                temp_full_path.unlink(missing_ok=True)

        return {"path": str(target_path), "backend": "spectacle", "window": window}

    def _accessibility_provider(self) -> LinuxAtspiProvider:
        self._require_linux()
        if not self._has_accessibility():
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "AT-SPI accessibility is not available in this session.",
                suggestion="Run `dctl doctor` to inspect accessibility setup.",
            )
        if self._atspi is None:
            self._atspi = LinuxAtspiProvider()
        return self._atspi

    def _window_provider(self) -> XdotoolWindowProvider:
        self._require_linux()
        if not self._has_windowing():
            raise DctlError(
                "CAPABILITY_UNAVAILABLE",
                "xdotool windowing is not available in this session.",
                suggestion="Run `dctl doctor` to inspect xdotool availability.",
            )
        if self._windowing is None:
            self._windowing = XdotoolWindowProvider(self.env.helpers["xdotool"])
        return self._windowing

    def _require_linux(self) -> None:
        if self.env.platform != "linux":
            raise DctlError(
                "PLATFORM_NOT_SUPPORTED",
                f"Current implementation is Linux-first. Active platform is {self.env.platform}.",
            )

    def _macos_backend(self) -> MacOSBackend:
        if self.env.platform != "darwin":
            raise DctlError(
                "PLATFORM_NOT_SUPPORTED",
                f"Current platform is {self.env.platform}, not macOS.",
            )
        if self._macos is None:
            self._macos = MacOSBackend(self.env)
        return self._macos

    def _run_helper(self, args: list[str]) -> None:
        try:
            result = subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            raise DctlError(
                "DEPENDENCY_MISSING",
                f"Required helper is not available: {args[0]}",
            ) from exc

        stderr = (result.stderr or "").strip()
        failed = result.returncode != 0 or "Failed creating new xdo instance." in stderr
        if failed:
            raise DctlError(
                "BACKEND_FAILURE",
                f"Helper command failed: {' '.join(shlex.quote(arg) for arg in args)}",
                suggestion=stderr or "Inspect the helper tool configuration and permissions.",
            )
