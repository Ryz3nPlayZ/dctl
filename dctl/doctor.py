from __future__ import annotations

from typing import Any


def build_doctor_report(capabilities: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checks = capabilities.get("diagnostics", {}).get("checks", {})
    helpers = capabilities.get("diagnostics", {}).get("helpers", {})
    providers = capabilities.get("providers", {})
    platform = capabilities.get("platform")

    if platform == "linux":
        if not checks.get("atspi_importable"):
            issues.append(
                {
                    "severity": "error",
                    "area": "accessibility",
                    "message": "Python GObject introspection bindings are not importable.",
                    "suggestion": "Install the system GI bindings for Python and AT-SPI typelib packages.",
                }
            )
        elif not checks.get("atspi_bus"):
            issues.append(
                {
                    "severity": "error",
                    "area": "accessibility",
                    "message": "The AT-SPI accessibility bus is not reachable from this session.",
                    "suggestion": "Enable accessibility support for the desktop session and rerun `dctl doctor`.",
                }
            )

        if helpers.get("xdotool") and not checks.get("xdotool_usable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "windowing",
                    "message": "xdotool is installed but is not usable from this session.",
                    "suggestion": "Ensure an X11/XWayland display is reachable if you want xdotool-based windowing and input.",
                }
            )

        if providers.get("capture") is None:
            issues.append(
                {
                    "severity": "warning",
                    "area": "capture",
                    "message": "No screenshot backend is available.",
                    "suggestion": "Install `grim`, `spectacle`, or `scrot` depending on the desktop environment.",
                }
            )

        if providers.get("input") is None:
            issues.append(
                {
                    "severity": "warning",
                    "area": "input",
                    "message": "No raw input helper is available.",
                    "suggestion": "Install `xdotool` or `ydotool` if you need fallback keyboard and mouse injection.",
                }
            )
        elif providers.get("input") == "ydotool":
            issues.append(
                {
                    "severity": "info",
                    "area": "input",
                    "message": "ydotool is available, but it may require uinput access or a helper service.",
                    "suggestion": "Verify the current user can send events before relying on Wayland injection.",
                }
            )
        elif helpers.get("ydotool") and not checks.get("ydotool_usable"):
            issues.append(
                {
                    "severity": "info",
                    "area": "input",
                    "message": "ydotool is installed but the daemon socket is not currently usable.",
                    "suggestion": "Start ydotoold and ensure the current user can access its socket if you need Wayland-native injection.",
                }
            )

        if not helpers.get("xdg-open"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "launch",
                    "message": "xdg-open is missing.",
                    "suggestion": "Install xdg-utils to enable launch and open commands.",
                }
            )
        if not checks.get("websockets_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "browser",
                    "message": "The `websockets` module is not importable.",
                    "suggestion": "Install the Python `websockets` package to enable browser CDP commands.",
                }
            )
        if not checks.get("browser_binaries"):
            issues.append(
                {
                    "severity": "info",
                    "area": "browser",
                    "message": "No supported Chromium-based browser executable was found on PATH.",
                    "suggestion": "Install Brave, Chrome, or Chromium, or pass `--exec` to `dctl browser start`.",
                }
            )
        if not checks.get("uno_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "office",
                    "message": "The `uno` module is not importable.",
                    "suggestion": "Install the LibreOffice Python UNO bindings.",
                }
            )
        elif not helpers.get("soffice") and not helpers.get("libreoffice"):
            issues.append(
                {
                    "severity": "info",
                    "area": "office",
                    "message": "LibreOffice is not on PATH.",
                    "suggestion": "Install LibreOffice or pass `--exec` when starting it.",
                }
            )
        if not checks.get("docx_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "docx",
                    "message": "The `python-docx` module is not importable.",
                    "suggestion": "Install `python-docx` to enable DOCX commands.",
                }
            )
        if not checks.get("openpyxl_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "xlsx",
                    "message": "The `openpyxl` module is not importable.",
                    "suggestion": "Install `openpyxl` to enable XLSX commands.",
                }
            )
    elif platform == "darwin":
        if not checks.get("ax_importable"):
            issues.append(
                {
                    "severity": "error",
                    "area": "accessibility",
                    "message": "ApplicationServices PyObjC bindings are not importable.",
                    "suggestion": "Install `pyobjc-framework-ApplicationServices`.",
                }
            )
        if not checks.get("quartz_importable") or not checks.get("appkit_importable"):
            issues.append(
                {
                    "severity": "error",
                    "area": "windowing",
                    "message": "Quartz or AppKit PyObjC bindings are not importable.",
                    "suggestion": "Install `pyobjc-framework-Quartz` and `pyobjc-framework-Cocoa`.",
                }
            )
        if checks.get("ax_importable") and not checks.get("accessibility_permission"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "permissions",
                    "message": "Accessibility permission is not granted for this process.",
                    "suggestion": "Grant Accessibility access in System Settings, then rerun `dctl doctor`.",
                }
            )
        if not helpers.get("screencapture"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "capture",
                    "message": "`screencapture` is not available.",
                    "suggestion": "Ensure the standard macOS screenshot utility is present.",
                }
            )
        if not helpers.get("open"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "launch",
                    "message": "`open` is not available.",
                    "suggestion": "Ensure the standard macOS `open` tool is available on PATH.",
                }
            )
        if not checks.get("websockets_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "browser",
                    "message": "The `websockets` module is not importable.",
                    "suggestion": "Install the Python `websockets` package to enable browser CDP commands.",
                }
            )
        if not checks.get("uno_importable"):
            issues.append(
                {
                    "severity": "info",
                    "area": "office",
                    "message": "The `uno` module is not importable.",
                    "suggestion": "Install LibreOffice's Python UNO bindings if you want semantic office control.",
                }
            )
        if not checks.get("docx_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "docx",
                    "message": "The `python-docx` module is not importable.",
                    "suggestion": "Install `python-docx` to enable DOCX commands.",
                }
            )
        if not checks.get("openpyxl_importable"):
            issues.append(
                {
                    "severity": "warning",
                    "area": "xlsx",
                    "message": "The `openpyxl` module is not importable.",
                    "suggestion": "Install `openpyxl` to enable XLSX commands.",
                }
            )
    else:
        issues.append(
            {
                "severity": "error",
                "area": "platform",
                "message": f"Unsupported platform: {platform}",
                "suggestion": "Use Linux or macOS.",
            }
        )

    return {
        "summary": {
            "platform": platform,
            "available_commands": [
                name for name, available in capabilities.get("commands", {}).items() if available
            ],
        },
        "issues": issues,
        "warnings": capabilities.get("warnings", []),
    }
